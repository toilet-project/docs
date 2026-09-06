#!/usr/bin/env python3
"""Isolated backup rehearsal; optional V11/synthetic replay. Never promotes a restore or writes production."""
import datetime as dt
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import signal
import stat
import subprocess
import sys
import time
import uuid


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identifier(value):
    if not re.fullmatch(r"[A-Za-z0-9_]+", value):
        raise ValueError("unexpected SQL identifier")
    return "`" + value + "`"


def verify_metadata(backup, expected_epoch, expected_server_uuid):
    path = Path(str(backup) + ".metadata.json")
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8192:
        raise ValueError("metadata required")
    raw = path.read_bytes()
    data = json.loads(raw)
    fields = {"version", "filename", "sha256", "bytes", "captureStartedAt", "captureCompletedAt",
              "database", "serverUuid", "databaseEpoch"}
    if not isinstance(data, dict) or set(data) != fields or type(data["version"]) is not int or data["version"] != 1:
        raise ValueError("metadata shape")
    for value in (expected_epoch, expected_server_uuid):
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", value):
            raise ValueError("independently supplied identity required")
    if (data["filename"] != backup.name or data["database"] != "toilet_db"
            or data["databaseEpoch"] != expected_epoch or data["serverUuid"] != expected_server_uuid
            or type(data["bytes"]) is not int or data["bytes"] != backup.stat().st_size
            or data["sha256"] != digest(backup)):
        raise ValueError("metadata mismatch")
    times = []
    for name in ("captureStartedAt", "captureCompletedAt"):
        value = data[name]
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
            raise ValueError("invalid capture time")
        times.append(dt.datetime.fromisoformat(value.replace("Z", "+00:00")))
    if times[0] > times[1] or times[1] > dt.datetime.now(dt.timezone.utc):
        raise ValueError("capture time order")
    return {"metadataSha256": hashlib.sha256(raw).hexdigest(), "captureMetadataVerified": True,
            "captureStartedAt": data["captureStartedAt"], "captureCompletedAt": data["captureCompletedAt"]}


def main():
    def interrupted(signum, frame):
        raise InterruptedError('restore interrupted; cleanup required')
    signal.signal(signal.SIGTERM, interrupted)
    phase = "preflight"
    container = None
    network = None
    volume_names = []
    errors = None
    run = uuid.uuid4().hex
    result = {"version": 1, "mode": "STRUCTURE_ONLY", "startedAt": utc(),
              "productionDatabaseModified": False, "erasureReplayVerified": False,
              "retentionEligible": False, "containerRemoved": False}
    work = None
    attempted = False
    original = None
    backup = None
    env = os.environ.copy()
    try:
        replay = len(sys.argv) == 4 and sys.argv[3] == "--v11-synthetic-replay"
        if len(sys.argv) != 3 and not replay:
            raise ValueError("explicit backup and work directory required")
        backup = Path(sys.argv[1])
        approved = Path("/home/luha/backups/geupddong/mysql")
        if backup.parent != approved or backup.resolve(strict=True) != backup or not re.fullmatch(r"toilet-db-[0-9]{8}-[0-9]{6}\.sql\.gz\.enc", backup.name):
            raise ValueError("invalid backup path")
        work = Path(sys.argv[2])
        if not str(work).startswith("/tmp/geupddong-live-backup-check.") or work.resolve(strict=True) != work:
            raise ValueError("isolated directory required")
        info = work.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError("private directory required")
        for name in ("result.json", "private-errors.log", "ATTEMPTED"):
            if (work / name).exists() or (work / name).is_symlink():
                raise ValueError("fresh attempt directory required")
        (work / "ATTEMPTED").write_text("isolated-live-backup-rehearsal-v1\n")
        attempted = True
        errors = (work / "private-errors.log").open("xb")
        original = backup.stat()
        actual_hash = digest(backup)
        checksum = Path(str(backup) + ".sha256")
        if checksum.is_symlink() or checksum.stat().st_size > 1024:
            raise ValueError("invalid checksum file")
        text = checksum.read_text().strip()
        if text not in (actual_hash + "  " + str(backup), actual_hash + "  " + backup.name):
            raise ValueError("checksum mismatch")
        key = Path("/home/luha/.config/geupddong/backup.key")
        if not key.is_file():
            raise ValueError("key unavailable")
        result.update(backupFilename=backup.name, backupSha256=actual_hash, backupBytes=original.st_size,
                      backupModifiedAt=dt.datetime.fromtimestamp(original.st_mtime, dt.timezone.utc).isoformat(),
                      captureMetadataPresent=Path(str(backup) + ".metadata.json").exists())
        if result["captureMetadataPresent"] or env.get("REHEARSAL_METADATA_REQUIRED") == "true":
            phase = "capture-metadata"
            result.update(verify_metadata(backup, env.get("REHEARSAL_EXPECTED_EPOCH"),
                                          env.get("REHEARSAL_EXPECTED_SERVER_UUID")))
        if replay:
            for name in ("v1.11-account-withdrawal-retention.sql", "LiveBackupV11Replay.java", "lib"):
                artifact = work / name
                if artifact.resolve(strict=True) != artifact or artifact.is_symlink():
                    raise ValueError("local rehearsal artifact required")
            result.update(mode="V11_SYNTHETIC_REPLAY", ddlSha256=digest(work / "v1.11-account-withdrawal-retention.sql"),
                          replaySourceSha256=digest(work / "LiveBackupV11Replay.java"))

        def command(args, timeout=60):
            return subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=errors,
                                  env=env, timeout=timeout).stdout.decode().strip()

        phase = "image-identity"
        image = command(["docker", "inspect", "-f", "{{.Image}}", "toilet-mysql"])
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
            raise ValueError("invalid image")
        result["mysqlImageId"] = image
        env["MYSQL_ROOT_PASSWORD"] = secrets.token_hex(24)
        env["MYSQL_PWD"] = env["MYSQL_ROOT_PASSWORD"]
        network_mode = "none"
        mysql_options = []
        if replay:
            phase = "network-create"
            network = "geupddong-backup-check-" + run
            command(["docker", "network", "create", "--internal", "--label", "geupddong.backup.rehearsal=" + run, network])
            net = json.loads(command(["docker", "network", "inspect", network]))[0]
            if not net["Internal"] or net["Labels"].get("geupddong.backup.rehearsal") != run:
                raise ValueError("network isolation failure")
            network_mode = network
            env["MYSQL_ROOT_HOST"] = "%"
            mysql_options = ["--port=43317"]
        phase = "container-create"
        container = command(["docker", "run", "-d", "--pull=never", "--name", "geupddong-backup-check-" + run,
                             "--label", "geupddong.backup.rehearsal=" + run, "--network=" + network_mode, "--memory=1g", "--cpus=1",
                             *(["-e", "MYSQL_ROOT_HOST"] if replay else []),
                             "-e", "MYSQL_ROOT_PASSWORD", image, "--skip-log-bin", "--event-scheduler=DISABLED",
                             "--local-infile=OFF", "--secure-file-priv=NULL", "--default-time-zone=+09:00",
                             "--innodb-flush-log-at-trx-commit=2", "--max-allowed-packet=1073741824", *mysql_options], timeout=120)
        env.pop("MYSQL_ROOT_PASSWORD", None)
        if not re.fullmatch(r"[a-f0-9]{64}", container):
            raise ValueError("invalid container identity")
        details = json.loads(command(["docker", "inspect", container]))[0]
        if details["Config"]["Labels"].get("geupddong.backup.rehearsal") != run or details["HostConfig"]["NetworkMode"] != network_mode or details["HostConfig"].get("PortBindings"):
            raise ValueError("isolation failure")
        if any(m["Type"] != "volume" or m["Destination"] != "/var/lib/mysql" for m in details["Mounts"]):
            raise ValueError("unexpected mount")
        volume_names = [m["Name"] for m in details["Mounts"]]
        if len(volume_names) != 1 or not re.fullmatch(r"[a-f0-9]{64}", volume_names[0]):
            raise ValueError("anonymous data volume required")
        phase = "container-ready"
        for attempt in range(60):
            ping = subprocess.run(["docker", "exec", "-e", "MYSQL_PWD", container, "mysqladmin", "--protocol=tcp", "-h127.0.0.1", "-P43317" if replay else "-P3306", "-uroot", "ping", "--silent"],
                                  env=env, stdout=subprocess.DEVNULL, stderr=errors, timeout=5)
            if ping.returncode == 0:
                break
            time.sleep(1)
        else:
            raise ValueError("isolated startup failed")

        def query(sql):
            return command(["docker", "exec", "-e", "MYSQL_PWD", container, "mysql", "--binary-mode", "--local-infile=0", "-uroot", "-N", "-B", "-e", sql])

        phase = "server-guards"
        guards = query("SELECT @@version, @@event_scheduler, @@log_bin, @@local_infile, @@secure_file_priv, @@global.time_zone;").split("\t")
        if len(guards) != 6 or guards[0] != "8.0.46" or guards[1:5] != ["DISABLED", "0", "0", "NULL"] or guards[5] != "+09:00":
            raise ValueError("database guards failed")
        result["mysqlVersion"] = guards[0]
        phase = "backup-import"
        # Plaintext goes only through pipes into the isolated MySQL. Never save it to a host file.
        processes = []
        try:
            decrypt = subprocess.Popen(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-pass", "file:" + str(key), "-in", str(backup)], stdout=subprocess.PIPE, stderr=errors)
            processes.append(decrypt)
            unpack = subprocess.Popen(["gzip", "-dc"], stdin=decrypt.stdout, stdout=subprocess.PIPE, stderr=errors)
            processes.append(unpack)
            decrypt.stdout.close()
            mysql = subprocess.Popen(["docker", "exec", "-i", "-e", "MYSQL_PWD", container, "mysql", "--binary-mode", "--local-infile=0", "--skip-reconnect", "-uroot"],
                                     stdin=unpack.stdout, stdout=subprocess.DEVNULL, stderr=errors, env=env)
            processes.append(mysql)
            unpack.stdout.close()
            statuses = [p.wait(timeout=900) for p in reversed(processes)]
            if any(statuses):
                raise ValueError("backup import failed")
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        phase = "isolated-durability-restore"
        query("SET GLOBAL innodb_flush_log_at_trx_commit=1; FLUSH ENGINE LOGS;")
        if query("SELECT @@global.innodb_flush_log_at_trx_commit;") != "1":
            raise ValueError("isolated durability restore failed")
        result["isolatedImportFlushMode"] = "2 during import; 1 plus FLUSH ENGINE LOGS before verification"
        phase = "aggregate-checks"
        tables = query("SELECT table_name FROM information_schema.tables WHERE table_schema='toilet_db' AND table_type='BASE TABLE' ORDER BY table_name;").splitlines()
        if "toilet" not in tables or "app_user" not in tables or "toilet_report" not in tables:
            raise ValueError("required schema missing")
        counts = {table: int(query("SELECT COUNT(*) FROM toilet_db." + identifier(table) + ";")) for table in tables}
        if counts["toilet"] == 0:
            raise ValueError("empty toilets")
        fk_rows = query("SELECT table_name,constraint_name,column_name,referenced_table_name,referenced_column_name FROM information_schema.key_column_usage WHERE table_schema='toilet_db' AND referenced_table_schema='toilet_db' ORDER BY table_name,constraint_name,ordinal_position;").splitlines()
        groups = {}
        for row in fk_rows:
            table, constraint, child, parent, ref = row.split("\t")
            groups.setdefault((table, constraint, parent), []).append((child, ref))
        orphan_total = 0
        for (table, constraint, parent), pairs in groups.items():
            joins = " AND ".join("c." + identifier(child) + "=p." + identifier(ref) for child, ref in pairs)
            notnull = " AND ".join("c." + identifier(child) + " IS NOT NULL" for child, ref in pairs)
            orphan_total += int(query("SELECT COUNT(*) FROM toilet_db." + identifier(table) + " c LEFT JOIN toilet_db." + identifier(parent) + " p ON " + joins + " WHERE " + notnull + " AND p." + identifier(pairs[0][1]) + " IS NULL;"))
        result.update(tableCount=len(tables), rowCounts=counts, foreignKeysChecked=len(groups), foreignKeyOrphans=orphan_total,
                      accountWithdrawalTablePresent="account_withdrawal" in tables, structureVerified=orphan_total == 0)
        if orphan_total:
            raise ValueError("foreign key orphans")
        if replay:
            phase = "v11-synthetic-replay"
            details = json.loads(command(["docker", "inspect", container]))[0]
            networks = details["NetworkSettings"]["Networks"]
            if set(networks) != {network}:
                raise ValueError("unexpected network attachment")
            address = networks[network]["IPAddress"]
            ip = ipaddress.ip_address(address)
            if ip.version != 4 or not any(ip in ipaddress.ip_network(cidr) for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
                raise ValueError("private bridge address required")
            query("CREATE TABLE toilet_db.erasure_restore_guard(marker CHAR(32) PRIMARY KEY); INSERT INTO toilet_db.erasure_restore_guard VALUES ('" + run + "');")
            env["V11_REPLAY_IP"] = address
            env["V11_REPLAY_MARKER"] = run
            env["V11_REPLAY_UUID"] = query("SELECT @@server_uuid;")
            output = command(["java", "-Xmx512m", "-Duser.timezone=UTC", "-cp", str(work / "lib" / "*"),
                              str(work / "LiveBackupV11Replay.java"), str(work / "v1.11-account-withdrawal-retention.sql")], timeout=300)
            checked = json.loads(output)
            if checked.get("outcome") != "V11_SYNTHETIC_REPLAY_VERIFIED" or checked.get("originalDataUnchanged") is not True:
                raise ValueError("replay verification failure")
            result["v11Verification"] = checked
            result["syntheticReplayVerified"] = True
        phase = "source-preservation"
        after = backup.stat()
        if (original.st_size, original.st_mtime_ns, original.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino) or digest(backup) != actual_hash:
            raise ValueError("source changed")
        result["sourceBackupUnchanged"] = True
        if result.get("captureMetadataVerified"):
            if digest(Path(str(backup) + ".metadata.json")) != result["metadataSha256"]:
                raise ValueError("source metadata changed")
            result["sourceMetadataUnchanged"] = True
        result["outcome"] = "V11_SYNTHETIC_VERIFIED_NOT_ERASURE_CLEARED" if replay else "STRUCTURE_VERIFIED_NOT_ERASURE_CLEARED"
    except Exception as error:
        result.update(outcome="FAILED", failurePhase=phase,
                      failureKind="TIMEOUT" if isinstance(error, subprocess.TimeoutExpired) else "CHECK_OR_COMMAND_FAILED")
        print("LIVE_BACKUP_REHEARSAL_FAILED phase=" + phase, file=sys.stderr)
    finally:
        removed = container is None
        if container is None and phase == "container-create":
            try:
                recovered = subprocess.run(["docker", "ps", "-aq", "--no-trunc", "--filter", "label=geupddong.backup.rehearsal=" + run],
                                           check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10).stdout.decode().splitlines()
                if len(recovered) == 1:
                    container = recovered[0]
                elif recovered:
                    removed = False
            except Exception:
                removed = False
        if container and re.fullmatch(r"[a-f0-9]{64}", container):
            try:
                inspection = subprocess.run(["docker", "inspect", "-f", '{{index .Config.Labels "geupddong.backup.rehearsal"}}', container],
                                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10, check=True)
                if inspection.stdout.decode().strip() != run:
                    raise ValueError("cleanup ownership mismatch")
                subprocess.run(["docker", "rm", "-fv", container], check=True, stdout=subprocess.DEVNULL, stderr=errors, timeout=60)
                remaining = subprocess.run(["docker", "volume", "ls", "-q"], check=True, stdout=subprocess.PIPE,
                                           stderr=subprocess.DEVNULL, timeout=10).stdout.decode().splitlines()
                removed = all(name not in remaining for name in volume_names)
            except Exception:
                removed = False
        result["containerRemoved"] = removed
        if network:
            try:
                net = json.loads(subprocess.run(["docker", "network", "inspect", network], check=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10).stdout)[0]
                if net["Labels"].get("geupddong.backup.rehearsal") != run or net["Containers"]:
                    raise ValueError("network cleanup ownership mismatch")
                subprocess.run(["docker", "network", "rm", network], check=True, stdout=subprocess.DEVNULL, stderr=errors, timeout=30)
                result["networkRemoved"] = True
            except Exception:
                result["networkRemoved"] = False
                removed = False
        result["completedAt"] = utc()
        if not removed:
            result["outcome"] = "FAILED_CLEANUP_REVIEW_REQUIRED"
            print("LIVE_BACKUP_CLEANUP_FAILED", file=sys.stderr)
        env.pop("MYSQL_PWD", None)
        if errors:
            errors.close()
        if attempted:
            with (work / "result.json").open("x") as out:
                json.dump(result, out, indent=2)
            os.chmod(work / "result.json", 0o600)
    if result.get("outcome") in ("STRUCTURE_VERIFIED_NOT_ERASURE_CLEARED", "V11_SYNTHETIC_VERIFIED_NOT_ERASURE_CLEARED") and result["containerRemoved"]:
        print("LIVE_BACKUP_REHEARSAL_OK tables=" + str(result["tableCount"]) + " toilets=" + str(result["rowCounts"]["toilet"]) + " foreignKeyOrphans=0 containerRemoved=true retentionEligible=false")
        return 0
    return 1


if __name__ == "__main__":
    os.umask(0o077)
    sys.exit(main())
