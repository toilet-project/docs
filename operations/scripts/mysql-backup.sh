#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

backup_dir="${GEUPDDONG_BACKUP_DIR:-/home/luha/backups/geupddong/mysql}"
key_file="${GEUPDDONG_BACKUP_KEY_FILE:-/home/luha/.config/geupddong/backup.key}"
env_file="${GEUPDDONG_API_ENV_FILE:-/home/luha/toilet-api/.env}"
container="${GEUPDDONG_MYSQL_CONTAINER:-toilet-mysql}"
database="${GEUPDDONG_MYSQL_DATABASE:-toilet_db}"
epoch="${GEUPDDONG_DATABASE_EPOCH:-}"
phase=preflight
temporary_dir=''
cleanup() {
  local status=$?
  if [[ -n "$temporary_dir" && "$temporary_dir" == "$backup_dir"/.capture.* && -d "$temporary_dir" && ! -L "$temporary_dir" ]]; then
    rm -f -- "$temporary_dir/dump" "$temporary_dir/checksum" "$temporary_dir/metadata"
    rmdir -- "$temporary_dir" 2>/dev/null || true
  fi
  if (( status != 0 )); then printf 'MYSQL_BACKUP_FAILED: %s\n' "$phase" >&2; fi
  return "$status"
}
trap cleanup EXIT

read_env() { local name="$1"; sed -n "s/^${name}=//p" "$env_file" | tail -n 1; }

[[ "$database" == toilet_db && "$container" =~ ^[a-zA-Z0-9_.-]+$ ]]
[[ "$epoch" =~ ^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$ ]]
[[ -r "$env_file" && -r "$key_file" && "$backup_dir" == /* && "$backup_dir" != / ]]
command -v flock >/dev/null
install -d -m 700 "$backup_dir"
[[ ! -L "$backup_dir" && "$(realpath "$backup_dir")" == "$backup_dir" ]]
# Serializes this script only, not all restore/erasure writers.
[[ ! -L "$backup_dir/.backup.lock" ]]
exec 9>"$backup_dir/.backup.lock"
flock -n 9
db_user="$(read_env SPRING_DB_USERNAME)"
db_password="$(read_env SPRING_DB_PASSWORD)"
[[ -n "$db_user" && -n "$db_password" ]]

phase=database-identity
server_uuid="$(docker exec -e MYSQL_PWD="$db_password" "$container" mysql --protocol=socket -u "$db_user" -N -B -e 'SELECT @@server_uuid' 2>/dev/null)"
[[ "$server_uuid" =~ ^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$ ]]
started="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
timestamp="$(date -u '+%Y%m%d-%H%M%S')"
filename="toilet-db-${timestamp}.sql.gz.enc"
target="$backup_dir/$filename"
[[ ! -e "$target" && ! -L "$target" && ! -e "$target.sha256" && ! -L "$target.sha256" && ! -e "$target.metadata.json" && ! -L "$target.metadata.json" ]]
temporary_dir="$(mktemp -d "$backup_dir/.capture.XXXXXXXX")"
phase=encrypted-capture

docker exec -e MYSQL_PWD="$db_password" "$container" \
  mysqldump --protocol=socket -u "$db_user" --single-transaction --quick \
  --no-tablespaces --skip-extended-insert --routines --triggers --events --databases "$database" 2>/dev/null \
  | gzip -9 \
  | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 -pass "file:$key_file" -out "$temporary_dir/dump" 2>/dev/null
completed="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
[[ "$completed" == "$started" || "$completed" > "$started" ]]
phase=metadata
after_uuid="$(docker exec -e MYSQL_PWD="$db_password" "$container" mysql --protocol=socket -u "$db_user" -N -B -e 'SELECT @@server_uuid' 2>/dev/null)"
[[ "$after_uuid" == "$server_uuid" ]]
digest="$(sha256sum "$temporary_dir/dump")"; digest="${digest%% *}"
bytes="$(stat -c '%s' "$temporary_dir/dump")"
[[ "$digest" =~ ^[a-f0-9]{64}$ && "$bytes" =~ ^[0-9]+$ && "$bytes" -gt 0 ]]
printf '%s  %s\n' "$digest" "$filename" > "$temporary_dir/checksum"
# All strings below are fixed/validated. No credential or SQL row enters metadata.
printf '{"version":1,"filename":"%s","sha256":"%s","bytes":%s,"captureStartedAt":"%s","captureCompletedAt":"%s","database":"%s","serverUuid":"%s","databaseEpoch":"%s"}\n' \
  "$filename" "$digest" "$bytes" "$started" "$completed" "$database" "$server_uuid" "$epoch" > "$temporary_dir/metadata"

phase=publish
# Atomic no-clobber publication per file; metadata is last. Partial publication fails closed at scan.
ln -- "$temporary_dir/dump" "$target"
ln -- "$temporary_dir/checksum" "$target.sha256"
ln -- "$temporary_dir/metadata" "$target.metadata.json"
# No retention deletion. An independent, reviewed cleanup tool is still required before deployment.
printf 'MYSQL_BACKUP_COMPLETE: metadataVersion=1 bytes=%s retentionCleanup=not-run\n' "$bytes"
