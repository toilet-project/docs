#!/usr/bin/env python3
"""Daily isolated structure restore, then guarded hash promotion. No production SQL writes."""
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

spec = importlib.util.spec_from_file_location('promotion', Path(__file__).with_name('refresh-restore-verification.py'))
promotion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(promotion)


def select_backup(root, config, now):
    candidates = []
    for entry in root.iterdir():
        if not promotion.NAME.fullmatch(entry.name):
            continue
        meta_path = Path(str(entry)+'.metadata.json')
        if not meta_path.exists() and not meta_path.is_symlink():
            continue  # Legacy remains a HOLD in retention; never invent capture metadata.
        raw = promotion.read_private(meta_path, 8192)
        meta = json.loads(raw, object_pairs_hook=promotion.unique)
        promotion.require(meta.get('filename') == entry.name and meta.get('database') == 'toilet_db')
        promotion.require(meta.get('databaseEpoch') == config['GEUPDDONG_DATABASE_EPOCH']
                          and meta.get('serverUuid') == config['GEUPDDONG_MYSQL_SERVER_UUID'])
        started, completed = promotion.utc(meta['captureStartedAt']), promotion.utc(meta['captureCompletedAt'])
        promotion.require(started <= completed <= now)
        candidates.append((completed, entry.name, entry))
    promotion.require(bool(candidates))
    completed, _, latest = max(candidates)
    promotion.require(now - completed <= promotion.MAX_AGE)
    return latest


def cleanup_success(work):
    promotion.private_dir(work)
    promotion.require(work.parent == Path('/tmp') and work.name.startswith('geupddong-live-backup-check.'))
    allowed = {'ATTEMPTED', 'result.json', 'private-errors.log'}
    paths = list(work.iterdir())
    promotion.require({p.name for p in paths} == allowed)
    for path in paths:
        promotion.require(not path.is_symlink() and path.is_file())
    for path in paths:
        path.unlink()  # Only this successful run's three technical artifacts, never backups.
    work.rmdir()


def write_new(path, data):
    raw = json.dumps(data, separators=(',', ':')).encode()
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(raw); out.flush(); os.fsync(out.fileno())
    promotion.sync_dir(path.parent)


def run(root, config_path, state):
    import fcntl
    receipts = state/'receipts'
    work = None
    process = None
    fd = None
    def interrupted(signum, frame):
        raise InterruptedError('interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        os.umask(0o077)
        for directory in [root, config_path.parent, state, receipts]: promotion.private_dir(directory)
        promotion.require(not (state/'failed-run.json').exists() and not (state/'failed-run.json').is_symlink())
        fd = os.open(root/'.backup.lock', os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW, 0o600)
        info = os.fstat(fd)
        promotion.require(promotion.stat.S_ISREG(info.st_mode) and info.st_size == 0
                          and info.st_uid == os.geteuid() and info.st_mode & 0o077 == 0)
        fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
        config = promotion.config_values(promotion.read_private(config_path, 262144))
        backup = select_backup(root, config, dt.datetime.now(dt.timezone.utc))
        work = Path(tempfile.mkdtemp(prefix='geupddong-live-backup-check.', dir='/tmp'))
        env = dict(os.environ, REHEARSAL_METADATA_REQUIRED='true',
                   REHEARSAL_EXPECTED_EPOCH=config['GEUPDDONG_DATABASE_EPOCH'],
                   REHEARSAL_EXPECTED_SERVER_UUID=config['GEUPDDONG_MYSQL_SERVER_UUID'])
        process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('verify-live-backup-isolated.py')),
                                    str(backup), str(work)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        promotion.require(process.wait(timeout=1500) == 0)
        result_path = work/'result.json'
        result_hash = hashlib.sha256(promotion.read_private(result_path, 1048576)).hexdigest()
        # The parent holds the SAME real flock throughout restore and promotion.
        outcome = promotion.refresh(root, config_path, result_path, result_hash, config[promotion.KEY],
                                    receipts, True, dt.datetime.now(dt.timezone.utc))
        # Even if the protected hash is already current, retain aggregate evidence for this new test.
        write_new(receipts/('checked-'+result_hash+'.json'), {
            'version': 1, 'outcome': outcome, 'resultSha256': result_hash,
            'checkedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
            'backupFilename': backup.name, 'backupSha256': promotion.digest_private(backup)[0],
            'productionDatabaseModified': False, 'retentionEligible': False})
        cleanup_success(work)
        work = None
        print('BACKUP_RESTORE_VERIFIED_AND_PROTECTED productionDatabaseModified=false retentionEligible=false')
        return 0
    except Exception:
        if process is not None and process.poll() is None:
            process.terminate()  # Runner handles SIGTERM and attempts owned Docker cleanup.
            try: process.wait(timeout=120)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=10)
        if work is not None:
            try:
                write_new(state/'failed-run.json', {'version': 1, 'workDirectory': str(work),
                    'failedAt': dt.datetime.now(dt.timezone.utc).isoformat(), 'manualReviewRequired': True})
            except Exception: pass
        print('BACKUP_RESTORE_FAILED_REVIEW_REQUIRED', file=sys.stderr)
        return 1
    finally:
        if fd is not None: os.close(fd)


if __name__ == '__main__':
    sys.exit(run(Path('/home/luha/backups/geupddong/mysql'),
                 Path('/home/luha/.config/geupddong/backup-retention.env'),
                 Path('/home/luha/.local/state/geupddong-backup-restore')))
