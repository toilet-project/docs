#!/usr/bin/env bash
set -euo pipefail

backup_dir="${GEUPDDONG_BACKUP_DIR:-/home/luha/backups/geupddong/mysql}"
key_file="${GEUPDDONG_BACKUP_KEY_FILE:-/home/luha/.config/geupddong/backup.key}"
env_file="${GEUPDDONG_API_ENV_FILE:-/home/luha/toilet-api/.env}"
retention_days="${GEUPDDONG_BACKUP_RETENTION_DAYS:-14}"
container="${GEUPDDONG_MYSQL_CONTAINER:-toilet-mysql}"
database="${GEUPDDONG_MYSQL_DATABASE:-toilet_db}"

read_env() { local name="$1"; sed -n "s/^${name}=//p" "$env_file" | tail -n 1; }

if [[ ! -r "$env_file" || ! -r "$key_file" ]]; then
  echo "필수 환경 파일 또는 암호화 키를 읽을 수 없습니다." >&2; exit 1
fi
db_user="$(read_env SPRING_DB_USERNAME)"
db_password="$(read_env SPRING_DB_PASSWORD)"
if [[ -z "$db_user" || -z "$db_password" ]]; then echo "DB 계정 정보를 읽지 못했습니다." >&2; exit 1; fi

install -d -m 700 "$backup_dir"
timestamp="$(date '+%Y%m%d-%H%M%S')"
target="$backup_dir/toilet-db-${timestamp}.sql.gz.enc"
temporary="${target}.tmp"
trap 'rm -f "$temporary"' EXIT

docker exec -e MYSQL_PWD="$db_password" "$container" \
  mysqldump --protocol=socket -u "$db_user" --single-transaction --quick \
  --no-tablespaces --skip-extended-insert --routines --triggers --events --databases "$database" \
  | gzip -9 \
  | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 -pass "file:$key_file" -out "$temporary"

mv "$temporary" "$target"
chmod 600 "$target"
sha256sum "$target" > "${target}.sha256"
chmod 600 "${target}.sha256"
find "$backup_dir" -type f \( -name 'toilet-db-*.sql.gz.enc' -o -name 'toilet-db-*.sql.gz.enc.sha256' \) -mtime "+$retention_days" -delete
echo "백업 완료: $target"
