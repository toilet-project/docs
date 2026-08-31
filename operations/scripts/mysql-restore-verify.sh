#!/usr/bin/env bash
set -euo pipefail

backup_dir="${GEUPDDONG_BACKUP_DIR:-/home/luha/backups/geupddong/mysql}"
key_file="${GEUPDDONG_BACKUP_KEY_FILE:-/home/luha/.config/geupddong/backup.key}"
backup_file="${1:-$(find "$backup_dir" -maxdepth 1 -type f -name 'toilet-db-*.sql.gz.enc' | sort | tail -n 1)}"
verify_container="geupddong-restore-verify-$$"
cleanup() {
  local status=$?
  if [[ $status -ne 0 ]]; then docker logs --tail 40 "$verify_container" >&2 || true; fi
  docker rm -f "$verify_container" >/dev/null 2>&1 || true
  return "$status"
}
trap cleanup EXIT

if [[ -z "$backup_file" || ! -r "$backup_file" || ! -r "$key_file" ]]; then
  echo "검증할 백업 또는 암호화 키를 읽을 수 없습니다." >&2; exit 1
fi
(cd "$(dirname "$backup_file")" && sha256sum -c "$(basename "$backup_file").sha256")
docker run -d --name "$verify_container" -e MYSQL_ALLOW_EMPTY_PASSWORD=yes mysql:8.0 \
  --max-allowed-packet=1073741824 >/dev/null
for _ in $(seq 1 60); do
  if docker exec "$verify_container" mysqladmin -uroot ping --silent; then break; fi
  sleep 2
done
docker exec "$verify_container" mysqladmin -uroot ping --silent
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$key_file" -in "$backup_file" \
  | gzip -dc | docker exec -i "$verify_container" mysql -uroot
table_count="$(docker exec "$verify_container" mysql -N -uroot -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='toilet_db';")"
toilet_count="$(docker exec "$verify_container" mysql -N -uroot -e "SELECT COUNT(*) FROM toilet_db.toilet;")"
if [[ "$table_count" -lt 1 || "$toilet_count" -lt 1 ]]; then
  echo "복구 검증 실패: table_count=$table_count, toilet_count=$toilet_count" >&2; exit 1
fi
echo "복구 검증 성공: table_count=$table_count, toilet_count=$toilet_count"
