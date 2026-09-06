#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
mode="${1:---dry-run}"
[[ "$#" -le 1 && ( "$mode" == --dry-run || "$mode" == --apply ) ]]
backup_dir="${GEUPDDONG_BACKUP_DIR:-/home/luha/backups/geupddong/mysql}"
state_dir="${GEUPDDONG_RETENTION_STATE_DIR:-/home/luha/.local/state/geupddong-backup-retention}"
tool_dir="${GEUPDDONG_ERASURE_TOOL_DIR:-/home/luha/erasure-tools}"
[[ "$backup_dir" == /* && "$backup_dir" != / && -d "$backup_dir" && ! -L "$backup_dir" && "$(realpath "$backup_dir")" == "$backup_dir" ]]
[[ "$state_dir" == /* && "$state_dir" != / && ! -L "$state_dir" ]]
install -d -m 700 "$state_dir"
[[ "$(realpath "$state_dir")" == "$state_dir" && "$state_dir" != "$backup_dir" && "$state_dir" != "$backup_dir/"* ]]
[[ ! -L "$backup_dir/.backup.lock" && -d "$tool_dir/lib" ]]
[[ ! -e "$backup_dir/.backup.lock" || ( -f "$backup_dir/.backup.lock" && ! -s "$backup_dir/.backup.lock" ) ]]
# Do not truncate an unexpected existing lock file before obtaining the lock.
exec 9>>"$backup_dir/.backup.lock"
# Same flock as capture, independent of whether the latest capture succeeded.
flock -n 9 || { printf 'BACKUP_RETENTION_LOCK_BUSY\n' >&2; exit 1; }
export GEUPDDONG_BACKUP_DIR="$backup_dir"
export GEUPDDONG_RETENTION_STATE_DIR="$state_dir"
export GEUPDDONG_RETENTION_LOCK_HELD=true
# flock only covers cooperating backup processes. The apply CLI also requires restore/writer exclusion.
exec java -cp "$tool_dir/lib/*" com.example.toiletbatch.account.BackupRetentionCli "$mode"
