#!/usr/bin/env bash
set -euo pipefail

backup_dir="${GEUPDDONG_BACKUP_DIR:-/home/luha/backups/geupddong/mysql}"
key_file="${GEUPDDONG_BACKUP_KEY_FILE:-/home/luha/.config/geupddong/backup.key}"
backup_file="${1:-$(find "$backup_dir" -maxdepth 1 -type f -name 'toilet-db-*.sql.gz.enc' | sort | tail -n 1)}"
# A structure-only restore is not proof that erased identities cannot return.
# Default to the guarded erasure rehearsal; the old check needs an explicit opt-in.
restore_mode="${GEUPDDONG_RESTORE_MODE:-erasure}"
if [[ "$restore_mode" == erasure ]]; then
  erasure_script="${GEUPDDONG_ERASURE_RESTORE_SCRIPT:-/home/luha/.local/bin/mysql-restore-erasure-verify.sh}"
  [[ -r "$erasure_script" ]] || { echo '파기 재적용 도구를 먼저 설치해야 합니다. 운영 연결 금지.' >&2; exit 1; }
  export GEUPDDONG_BACKUP_KEY_FILE="$key_file"
  exec bash "$erasure_script" "$backup_file"
fi
[[ "$restore_mode" == structure-only ]] || { echo '알 수 없는 복원 검증 모드입니다.' >&2; exit 1; }
verify_container="geupddong-restore-verify-$$"
cleanup() {
  local status=$?
  # Never dump database logs into a shared terminal: imported data can be sensitive.
  docker rm -fv "$verify_container" >/dev/null 2>&1 || true
  return "$status"
}
trap cleanup EXIT

if [[ -z "$backup_file" || ! -r "$backup_file" || ! -r "$key_file" ]]; then
  echo "검증할 백업 또는 암호화 키를 읽을 수 없습니다." >&2; exit 1
fi
(cd "$(dirname "$backup_file")" && sha256sum -c "$(basename "$backup_file").sha256")
docker run -d --name "$verify_container" --network none --memory 1g --cpus 1 -e MYSQL_ALLOW_EMPTY_PASSWORD=yes mysql:8.0 \
  --skip-log-bin --event-scheduler=OFF --local-infile=OFF --max-allowed-packet=1073741824 >/dev/null
for _ in $(seq 1 60); do
  # The entrypoint's temporary initialization server has a socket but no TCP port.
  # Wait for the final server so initialization shutdown cannot interrupt restore.
  if docker exec "$verify_container" mysqladmin --protocol=tcp -h127.0.0.1 -uroot ping --silent 2>/dev/null; then break; fi
  sleep 2
done
docker exec "$verify_container" mysqladmin --protocol=tcp -h127.0.0.1 -uroot ping --silent
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$key_file" -in "$backup_file" \
  | gzip -dc | docker exec -i "$verify_container" mysql -uroot
table_count="$(docker exec "$verify_container" mysql -N -uroot -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='toilet_db';")"
toilet_count="$(docker exec "$verify_container" mysql -N -uroot -e "SELECT COUNT(*) FROM toilet_db.toilet;")"
if [[ "$table_count" -lt 1 || "$toilet_count" -lt 1 ]]; then
  echo "복구 검증 실패: table_count=$table_count, toilet_count=$toilet_count" >&2; exit 1
fi
echo "구조 검증만 성공: table_count=$table_count, toilet_count=$toilet_count; 회원 파기 재적용 미검증 · 운영 연결 금지"
