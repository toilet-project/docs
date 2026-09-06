#!/usr/bin/env python3
"""Promote a fresh, private local restore result. Default dry-run; no DB/R2/network/deletion."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

HASH = re.compile(r'[a-f0-9]{64}')
UUID = re.compile(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}')
NAME = re.compile(r'toilet-db-[0-9]{8}-[0-9]{6}\.sql\.gz\.enc')
KEY = 'GEUPDDONG_RESTORE_VERIFIED_BACKUP_SHA256'
MAX_AGE = dt.timedelta(hours=36)
MAX_RESULT_AGE = dt.timedelta(hours=1)

def require(ok):
    if not ok: raise ValueError('RESTORE_VERIFICATION_REJECTED')

def utc(value):
    require(isinstance(value,str) and (value.endswith('Z') or value.endswith('+00:00')))
    result = dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    require(result.utcoffset() == dt.timedelta(0))
    return result

def unique(pairs):
    data = {}
    for key,value in pairs:
        require(key not in data)
        data[key] = value
    return data

def config_values(raw):
    text = raw.decode('utf-8')
    require('\x00' not in text)
    result = {}
    for key in ['GEUPDDONG_MYSQL_SERVER_UUID','GEUPDDONG_DATABASE_EPOCH',KEY]:
        values = re.findall(r'^'+key+r'=([^\r\n]*)\r?$',text,re.M)
        require(len(values)==1)
        result[key]=values[0]
    require(HASH.fullmatch(result[KEY]) is not None)
    for key in ['GEUPDDONG_MYSQL_SERVER_UUID','GEUPDDONG_DATABASE_EPOCH']:
        require(UUID.fullmatch(result[key]) is not None)
    return result

def validate(result,meta,config,now):
    require(type(result) is dict and type(meta) is dict)
    require(type(result.get('version')) is int and result['version']==1)
    require(isinstance(result.get('metadataSha256'),str) and HASH.fullmatch(result['metadataSha256']) is not None)
    require(result.get('outcome') in ['STRUCTURE_VERIFIED_NOT_ERASURE_CLEARED','V11_SYNTHETIC_VERIFIED_NOT_ERASURE_CLEARED'])
    for field in ['structureVerified','captureMetadataVerified','sourceMetadataUnchanged','sourceBackupUnchanged','containerRemoved']:
        require(result.get(field) is True)
    require(result.get('productionDatabaseModified') is False and result.get('retentionEligible') is False)
    require(type(result.get('foreignKeyOrphans')) is int and result['foreignKeyOrphans']==0)
    require(type(result.get('tableCount')) is int and result['tableCount']>0)
    if result['outcome'].startswith('V11_'):
        require(result.get('networkRemoved') is True and result.get('syntheticReplayVerified') is True)
        v = result.get('v11Verification',{})
        require(v.get('outcome')=='V11_SYNTHETIC_REPLAY_VERIFIED')
        for name in ['originalDataUnchanged','syntheticFixturesRemoved','identityConflictAtomic','unknownForeignKeyRollback','idempotenceVerified']:
            require(v.get(name) is True)
    require(set(meta)=={'version','database','filename','sha256','bytes','serverUuid','databaseEpoch','captureStartedAt','captureCompletedAt'})
    require(type(meta.get('version')) is int and meta['version']==1 and meta.get('database')=='toilet_db')
    require(meta.get('serverUuid')==config['GEUPDDONG_MYSQL_SERVER_UUID'] and meta.get('databaseEpoch')==config['GEUPDDONG_DATABASE_EPOCH'])
    require(isinstance(meta.get('filename'),str) and NAME.fullmatch(meta['filename']) is not None)
    require(isinstance(meta.get('sha256'),str) and HASH.fullmatch(meta['sha256']) is not None)
    require(type(meta.get('bytes')) is int and meta['bytes']>0)
    require(result.get('backupFilename')==meta['filename'] and result.get('backupSha256')==meta['sha256'] and result.get('backupBytes')==meta['bytes'])
    capture_start,capture_end = utc(meta['captureStartedAt']),utc(meta['captureCompletedAt'])
    started,completed = utc(result['startedAt']),utc(result['completedAt'])
    require(capture_start<=capture_end<=started<=completed<=now)
    require(now-capture_end<=MAX_AGE and now-completed<=MAX_RESULT_AGE)
    require(result.get('captureStartedAt')==meta['captureStartedAt'] and result.get('captureCompletedAt')==meta['captureCompletedAt'])
    return {'version':1,'scope':'backup-restorability-only','backupFilename':meta['filename'],
            'backupSha256':meta['sha256'],'metadataSha256':result['metadataSha256'],
            'databaseEpoch':meta['databaseEpoch'],'serverUuid':meta['serverUuid'],
            'captureCompletedAt':meta['captureCompletedAt'],'verifiedAt':result['completedAt'],
            'productionLedgerReplayVerified':False,'retentionEligible':False}

def private_dir(path):
    require(path.is_absolute() and path!=Path('/') and path.resolve(strict=True)==path)
    info=path.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.geteuid() and info.st_mode & 0o077==0)

def read_private(path,limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and info.st_mode & 0o077==0)
        raw=stream.read(limit+1)
        require(len(raw)<=limit)
        return raw

def digest_private(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid==os.geteuid() and before.st_mode & 0o077==0)
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
        after=os.fstat(stream.fileno())
        require((before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns))
        return digest,before.st_size

def sync_dir(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)

def refresh(root,config_path,result_path,expected_result_hash,expected_previous_hash,receipt_dir,apply,now):
    for directory in [root,config_path.parent,result_path.parent,receipt_dir]: private_dir(directory)
    require(not receipt_dir.is_relative_to(root) and not config_path.is_relative_to(root))
    require(HASH.fullmatch(expected_result_hash) is not None and HASH.fullmatch(expected_previous_hash) is not None)
    raw_config=read_private(config_path,262144)
    config=config_values(raw_config)
    require(config[KEY]==expected_previous_hash)
    raw_result=read_private(result_path,1048576)
    require(hashlib.sha256(raw_result).hexdigest()==expected_result_hash)
    result=json.loads(raw_result,object_pairs_hook=unique)
    filename=result.get('backupFilename')
    require(isinstance(filename,str) and NAME.fullmatch(filename) is not None)
    path=root/filename
    raw_meta=read_private(Path(str(path)+'.metadata.json'),8192)
    require(hashlib.sha256(raw_meta).hexdigest()==result.get('metadataSha256'))
    meta=json.loads(raw_meta,object_pairs_hook=unique)
    receipt=validate(result,meta,config,now)
    digest,size=digest_private(path)
    require(digest==meta['sha256'] and size==meta['bytes'])
    checksum=read_private(Path(str(path)+'.sha256'),1024).decode().strip()
    require(checksum in [digest+'  '+filename,digest+'  '+str(path)])
    # Never promote an older capture over the currently protected backup.
    previous=[]
    for entry in root.iterdir():
        if NAME.fullmatch(entry.name):
            entry_meta=Path(str(entry)+'.metadata.json')
            if entry_meta.exists():
                current=json.loads(read_private(entry_meta,8192),object_pairs_hook=unique)
                if current.get('sha256')==expected_previous_hash:
                    require(digest_private(entry)[0]==expected_previous_hash)
                    require(current.get('databaseEpoch')==meta['databaseEpoch'] and current.get('serverUuid')==meta['serverUuid'])
                    previous.append(current)
    require(len(previous)==1 and utc(meta['captureCompletedAt'])>=utc(previous[0]['captureCompletedAt']))
    if not apply: return 'READY_DRY_RUN'
    if digest==expected_previous_hash: return 'ALREADY_CURRENT'
    receipt['resultSha256']=expected_result_hash
    receipt['previousBackupSha256']=expected_previous_hash
    receipt_bytes=json.dumps(receipt,separators=(',',':')).encode()
    target=receipt_dir/('restore-'+expected_result_hash+'.json')
    try:
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except FileExistsError:
        require(read_private(target,8192)==receipt_bytes)
    else:
        with os.fdopen(fd,'wb') as out:
            out.write(receipt_bytes);out.flush();os.fsync(out.fileno())
        sync_dir(receipt_dir)
    # Receipt means a verified result, not an assertion that config replacement completed.
    require(read_private(config_path,262144)==raw_config)
    updated=re.sub(rb'(?m)^'+KEY.encode()+rb'=[^\r\n]*',KEY.encode()+b'='+digest.encode(),raw_config)
    fd,name=tempfile.mkstemp(prefix='.restore-config-',dir=config_path.parent)
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(updated);out.flush();os.fsync(out.fileno())
        require(read_private(config_path,262144)==raw_config)
        os.replace(name,config_path)
        sync_dir(config_path.parent)
    finally:
        if os.path.exists(name): os.unlink(name)
    return 'PROMOTED'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result-file',type=Path,required=True)
    parser.add_argument('--result-sha256',required=True)
    parser.add_argument('--previous-sha256',required=True)
    parser.add_argument('--backup-dir',type=Path,default=Path('/home/luha/backups/geupddong/mysql'))
    parser.add_argument('--config',type=Path,default=Path('/home/luha/.config/geupddong/backup-retention.env'))
    parser.add_argument('--receipt-dir',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    try:
        import fcntl  # Linux runtime only; policy validation is portable for tests.
        os.umask(0o077)
        private_dir(args.backup_dir)
        fd=os.open(args.backup_dir/'.backup.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
        try:
            info=os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_size==0 and info.st_uid==os.geteuid() and info.st_mode&0o077==0)
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            outcome=refresh(args.backup_dir,args.config,args.result_file,args.result_sha256,args.previous_sha256,
                            args.receipt_dir,args.apply,dt.datetime.now(dt.timezone.utc))
            print('RESTORE_VERIFICATION_'+outcome+' backupDeletion=false retentionEligible=false')
        finally: os.close(fd)
        return 0
    except Exception:
        print('RESTORE_VERIFICATION_REFRESH_FAILED_REVIEW_REQUIRED',file=sys.stderr)
        return 1

if __name__=='__main__': sys.exit(main())
