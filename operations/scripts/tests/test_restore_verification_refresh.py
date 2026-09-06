"""Synthetic fixtures only: no production DB, backups, keys, Docker or network."""
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'refresh-restore-verification.py'
spec = importlib.util.spec_from_file_location('refresh_verification', SOURCE)
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)
NOW = dt.datetime(2026, 9, 7, 4, 0, tzinfo=dt.timezone.utc)
SERVER = '11111111-1111-1111-1111-111111111111'
EPOCH = '22222222-2222-2222-2222-222222222222'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def fixture(now=NOW):
    def stamp(minutes):
        return (now - dt.timedelta(minutes=minutes)).isoformat().replace('+00:00', 'Z')
    meta = dict(version=1, database='toilet_db', filename='toilet-db-20260907-033000.sql.gz.enc',
                sha256=digest(b'new synthetic ciphertext'), bytes=len(b'new synthetic ciphertext'),
                serverUuid=SERVER, databaseEpoch=EPOCH,
                captureStartedAt=stamp(30), captureCompletedAt=stamp(29))
    result = dict(version=1, mode='STRUCTURE_ONLY', outcome='STRUCTURE_VERIFIED_NOT_ERASURE_CLEARED',
                  structureVerified=True, captureMetadataVerified=True, sourceMetadataUnchanged=True,
                  sourceBackupUnchanged=True, containerRemoved=True, productionDatabaseModified=False,
                  retentionEligible=False, foreignKeyOrphans=0, tableCount=16,
                  backupFilename=meta['filename'], backupSha256=meta['sha256'], backupBytes=meta['bytes'],
                  captureStartedAt=meta['captureStartedAt'], captureCompletedAt=meta['captureCompletedAt'],
                  metadataSha256=digest(json.dumps(meta).encode()), startedAt=stamp(20), completedAt=stamp(19),
                  rowCounts={'private_fixture': 123})
    config = {'GEUPDDONG_MYSQL_SERVER_UUID': SERVER, 'GEUPDDONG_DATABASE_EPOCH': EPOCH, refresh.KEY: 'a'*64}
    return result, meta, config


class PolicyTest(unittest.TestCase):
    def test_structure_success_is_not_erasure_clearance_and_receipt_has_no_rows(self):
        result, meta, config = fixture()
        receipt = refresh.validate(result, meta, config, NOW)
        self.assertEqual('backup-restorability-only', receipt['scope'])
        self.assertFalse(receipt['retentionEligible'])
        self.assertFalse(receipt['productionLedgerReplayVerified'])
        self.assertNotIn('rowCounts', receipt)

    def test_failures_missing_flags_and_wrong_types_rejected(self):
        result, meta, config = fixture()
        cases = [('outcome', 'FAILED_CLEANUP_REVIEW_REQUIRED'), ('version', True),
                 ('productionDatabaseModified', True), ('retentionEligible', True),
                 ('foreignKeyOrphans', 1), ('foreignKeyOrphans', False), ('tableCount', 0),
                 ('backupSha256', 'b'*64), ('backupFilename', '../bad'), ('metadataSha256', 'bad')]
        cases += [(key, value) for key in ['structureVerified', 'captureMetadataVerified',
                  'sourceMetadataUnchanged', 'sourceBackupUnchanged', 'containerRemoved']
                  for value in [False, None, 1, 'true']]
        for key, value in cases:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                refresh.validate({**result, key: value}, meta, config, NOW)

    def test_v11_requires_all_replay_and_cleanup_proofs(self):
        result, meta, config = fixture()
        result.update(outcome='V11_SYNTHETIC_VERIFIED_NOT_ERASURE_CLEARED', networkRemoved=True,
                      syntheticReplayVerified=True, v11Verification=dict(outcome='V11_SYNTHETIC_REPLAY_VERIFIED',
                      originalDataUnchanged=True, syntheticFixturesRemoved=True, identityConflictAtomic=True,
                      unknownForeignKeyRollback=True, idempotenceVerified=True))
        refresh.validate(result, meta, config, NOW)
        for key in ['networkRemoved', 'syntheticReplayVerified']:
            with self.subTest(key=key), self.assertRaises(ValueError):
                refresh.validate({**result, key: False}, meta, config, NOW)
        for key in result['v11Verification']:
            wrong = copy.deepcopy(result)
            del wrong['v11Verification'][key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                refresh.validate(wrong, meta, config, NOW)

    def test_stale_capture_even_when_restore_is_fresh_rejected(self):
        result, meta, config = fixture()
        meta.update(captureStartedAt='2026-09-05T00:00:00Z', captureCompletedAt='2026-09-05T00:01:00Z')
        result.update(captureStartedAt=meta['captureStartedAt'], captureCompletedAt=meta['captureCompletedAt'])
        with self.assertRaises(ValueError): refresh.validate(result, meta, config, NOW)

    def test_old_result_future_result_reversed_or_naive_times_rejected(self):
        result, meta, config = fixture()
        for change in [dict(startedAt='2026-09-07T02:00:00Z', completedAt='2026-09-07T02:01:00Z'),
                       dict(completedAt='2026-09-07T04:01:00Z'), dict(completedAt='2026-09-07T03:00:00Z'),
                       dict(completedAt='2026-09-07T03:45:00')]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                refresh.validate({**result, **change}, meta, config, NOW)

    def test_metadata_identity_schema_mismatch_rejected(self):
        result, meta, config = fixture()
        for change in [dict(databaseEpoch=SERVER), dict(serverUuid=EPOCH), dict(bytes=True),
                       dict(database='other_db'), dict(unexpected='field'), dict(version=True)]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                refresh.validate(result, {**meta, **change}, config, NOW)

    def test_duplicate_json_and_ambiguous_config_rejected(self):
        with self.assertRaises(ValueError): json.loads('{"x":1,"x":2}', object_pairs_hook=refresh.unique)
        _, _, config = fixture()
        raw = ''.join(f'{k}={v}\n' for k, v in config.items()).encode()
        self.assertEqual(config, refresh.config_values(raw))
        for wrong in [raw + (refresh.KEY+'='+'a'*64+'\n').encode(), raw.replace(SERVER.encode(), b''),
                      raw.replace(b'a'*64, b'"'+b'a'*64+b'"')]:
            with self.assertRaises(ValueError): refresh.config_values(wrong)


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux ownership, flock, O_NOFOLLOW, fsync tests')
class FilesystemTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root, self.settings, self.results, self.receipts = [self.base / p for p in ['backups', 'settings', 'results', 'receipts']]
        for path in [self.root, self.settings, self.results, self.receipts]: path.mkdir(mode=0o700)
        self.result, self.meta, config = fixture(dt.datetime.now(dt.timezone.utc))
        self.previous = digest(b'old synthetic ciphertext')
        old = {**self.meta, 'filename': 'toilet-db-20260906-033000.sql.gz.enc',
               'sha256': self.previous, 'bytes': len(b'old synthetic ciphertext'),
               'captureStartedAt': '2026-09-06T03:30:00Z', 'captureCompletedAt': '2026-09-06T03:31:00Z'}
        # Older than candidate regardless of the actual CI run date.
        old['captureStartedAt'] = old['captureCompletedAt'] = '2000-01-01T00:00:00Z'
        self.old_path = self.root / old['filename']
        self.write(self.old_path, b'old synthetic ciphertext')
        self.write(Path(str(self.old_path)+'.metadata.json'), json.dumps(old).encode())
        self.backup = self.root / self.meta['filename']
        self.write(self.backup, b'new synthetic ciphertext')
        self.metadata = Path(str(self.backup)+'.metadata.json')
        self.checksum = Path(str(self.backup)+'.sha256')
        self.write(self.metadata, json.dumps(self.meta).encode())
        self.write(self.checksum, (self.meta['sha256']+'  '+self.backup.name+'\n').encode())
        self.result_path = self.results / 'result.json'
        self.save_result()
        config[refresh.KEY] = self.previous
        self.config = self.settings / 'retention.env'
        self.raw_config = ('# preserve comment\nUNRELATED=preserve-me\n'+''.join(f'{k}={v}\n' for k,v in config.items())).encode()
        self.write(self.config, self.raw_config)
        self.before = {p.name: p.read_bytes() for p in self.root.iterdir()}

    def write(self, path, content):
        path.write_bytes(content)
        path.chmod(0o600)

    def save_result(self):
        raw = json.dumps(self.result).encode()
        self.write(self.result_path, raw)
        self.result_hash = digest(raw)

    def run_refresh(self, apply=False, **kwargs):
        return refresh.refresh(self.root, self.config, self.result_path, self.result_hash,
                               kwargs.get('previous', self.previous), self.receipts, apply,
                               dt.datetime.now(dt.timezone.utc))

    def assert_unchanged(self):
        self.assertEqual(self.raw_config, self.config.read_bytes())
        self.assertEqual([], list(self.receipts.iterdir()))

    def test_dry_run_never_changes_files(self):
        self.assertEqual('READY_DRY_RUN', self.run_refresh())
        self.assert_unchanged()
        self.assertEqual(self.before, {p.name:p.read_bytes() for p in self.root.iterdir()})

    def test_apply_changes_only_protected_hash_with_sanitized_receipt(self):
        self.assertEqual('PROMOTED', self.run_refresh(apply=True))
        self.assertEqual(self.raw_config.replace(self.previous.encode(), self.meta['sha256'].encode()), self.config.read_bytes())
        self.assertEqual(0o600, self.config.stat().st_mode & 0o777)
        self.assertEqual(self.before, {p.name:p.read_bytes() for p in self.root.iterdir()})
        receipt_path, = list(self.receipts.iterdir())
        self.assertEqual(0o600, receipt_path.stat().st_mode & 0o777)
        receipt = json.loads(receipt_path.read_bytes())
        self.assertNotIn('rowCounts', receipt)
        self.assertFalse(receipt['retentionEligible'])
        self.assertEqual('ALREADY_CURRENT', self.run_refresh(apply=True, previous=self.meta['sha256']))
        with self.assertRaises(ValueError): self.run_refresh(apply=True)  # stale caller CAS

    def test_result_tampering_rejected(self):
        self.result_path.write_bytes(self.result_path.read_bytes()+b' ')
        with self.assertRaises(ValueError): self.run_refresh(apply=True)
        self.assert_unchanged()

    def test_metadata_tampering_rejected(self):
        self.metadata.write_bytes(self.metadata.read_bytes()+b' ')
        with self.assertRaises(ValueError): self.run_refresh(apply=True)
        self.assert_unchanged()

    def test_backup_tampering_rejected(self):
        self.backup.write_bytes(b'wrong ciphertext')
        with self.assertRaises(ValueError): self.run_refresh(apply=True)
        self.assert_unchanged()

    def test_checksum_tampering_rejected(self):
        self.checksum.write_bytes(b'wrong checksum')
        with self.assertRaises(ValueError): self.run_refresh(apply=True)
        self.assert_unchanged()

    def test_missing_previous_backup_rejected(self):
        self.old_path.unlink()
        with self.assertRaises(ValueError): self.run_refresh(apply=True)
        self.assert_unchanged()

    def test_older_candidate_cannot_replace_newer_capture(self):
        path = Path(str(self.old_path)+'.metadata.json')
        meta = json.loads(path.read_bytes())
        meta['captureCompletedAt'] = dt.datetime.now(dt.timezone.utc).isoformat()
        self.write(path, json.dumps(meta).encode())
        with self.assertRaises(ValueError): self.run_refresh(apply=True)
        self.assert_unchanged()

    def test_symlink_rejected(self):
        actual = self.results / 'actual.json'
        self.result_path.rename(actual)
        self.result_path.symlink_to(actual)
        with self.assertRaises(OSError): self.run_refresh(apply=True)
        self.assert_unchanged()

    def test_world_readable_input_rejected(self):
        self.result_path.chmod(0o644)
        with self.assertRaises(ValueError): self.run_refresh(apply=True)
        self.assert_unchanged()

    def test_receipt_collision_cannot_overwrite_existing_evidence(self):
        target = self.receipts / ('restore-'+self.result_hash+'.json')
        self.write(target, b'other receipt')
        with self.assertRaises(ValueError): self.run_refresh(apply=True)
        self.assertEqual(b'other receipt', target.read_bytes())
        self.assertEqual(self.raw_config, self.config.read_bytes())

    def test_atomic_replace_failure_preserves_config_and_backups(self):
        with patch.object(refresh.os, 'replace', side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError): self.run_refresh(apply=True)
        self.assertEqual(self.raw_config, self.config.read_bytes())
        self.assertEqual([], list(self.settings.glob('.restore-config-*')))
        self.assertEqual(self.before, {p.name:p.read_bytes() for p in self.root.iterdir()})
        # Receipt records verification, not config commit; retry can use same evidence.
        self.assertEqual('PROMOTED', self.run_refresh(apply=True))

    def test_cli_default_dry_run_and_actual_lock_contention(self):
        import fcntl
        command = [sys.executable, str(SOURCE), '--result-file', str(self.result_path),
                   '--result-sha256', self.result_hash, '--previous-sha256', self.previous,
                   '--backup-dir', str(self.root), '--config', str(self.config), '--receipt-dir', str(self.receipts)]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn('READY_DRY_RUN', completed.stdout)
        self.assert_unchanged()
        with (self.root / '.backup.lock').open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
            blocked = subprocess.run(command+['--apply'], capture_output=True, text=True, timeout=10)
        self.assertEqual(1, blocked.returncode)
        self.assertEqual('RESTORE_VERIFICATION_REFRESH_FAILED_REVIEW_REQUIRED\n', blocked.stderr)
        self.assert_unchanged()


if __name__ == '__main__': unittest.main()
