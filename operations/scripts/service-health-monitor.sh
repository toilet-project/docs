#!/usr/bin/env bash
set -u

state_dir="${GEUPDDONG_MONITOR_STATE_DIR:-/home/luha/.local/state/geupddong-monitor}"
webhook_env_file="${GEUPDDONG_MONITOR_WEBHOOK_ENV_FILE:-/home/luha/toilet-batch/.env}"
nginx_access_log="${GEUPDDONG_NGINX_ACCESS_LOG:-/var/log/nginx/access.log}"
webhook_name="${GEUPDDONG_MONITOR_WEBHOOK_NAME:-BATCH_FAILURE_WEBHOOK_URL}"

mkdir -p "$state_dir"
chmod 700 "$state_dir"

failures=()

add_failure() {
  failures+=("$1")
}

check_http_body() {
  local label="$1" url="$2" expected="$3" body
  if ! body="$(curl -fsS --max-time 15 "$url" 2>/dev/null)"; then
    add_failure "$label 응답 실패"
    return
  fi
  if [[ "$body" != *"$expected"* ]]; then
    add_failure "$label 응답 내용 불일치"
  fi
}

check_oauth_redirect() {
  local label="$1" url="$2" expected_host="$3" headers
  if ! headers="$(curl -sS -D - -o /dev/null --max-time 15 "$url" 2>/dev/null)"; then
    add_failure "$label OAuth 시작 경로 응답 실패"
    return
  fi
  if ! grep -Eq '^HTTP/[^ ]+ 302([[:space:]]|$)' <<<"$headers"; then
    add_failure "$label OAuth 시작 경로가 302가 아님"
    return
  fi
  if ! grep -Eiq "^location: https://$expected_host" <<<"$headers"; then
    add_failure "$label OAuth 리다이렉트 대상 불일치"
  fi
}

if ! systemctl is-active --quiet snap.docker.dockerd.service; then
  add_failure "Snap Docker 비활성"
fi
if systemctl is-active --quiet docker.service; then
  add_failure "금지된 systemd Docker가 실행 중"
fi

for container in toilet-api toilet-admin toilet-batch toilet-mysql toilet-redis portainer; do
  if [[ "$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" != "true" ]]; then
    add_failure "$container 컨테이너 중지"
  fi
done

redis_health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' toilet-redis 2>/dev/null || true)"
if [[ "$redis_health" != "healthy" ]]; then
  add_failure "toilet-redis 상태 $redis_health"
fi

check_http_body "내부 API·DB" "http://127.0.0.1:8085/api/health" "DB: toilet_db"
check_http_body "내부 관리자 API" "http://127.0.0.1:8089/actuator/health" '"status":"UP"'
check_http_body "외부 API·DB" "https://api.geupddong.com/api/health" "DB: toilet_db"
check_oauth_redirect "Google" "https://api.geupddong.com/oauth2/authorization/google" "accounts.google.com"
check_oauth_redirect "Kakao" "https://api.geupddong.com/oauth2/authorization/kakao" "kauth.kakao.com"

# 새 OAuth callback 5xx가 생긴 경우에만 한 번 알린다. 과거 로그는 첫 실행에서 기준값으로만 저장한다.
oauth_line="$(tail -n 2000 "$nginx_access_log" 2>/dev/null | grep -E '/login/oauth2/code/(google|kakao).*( 500 | 502 | 503 | 504 )' | tail -n 1 || true)"
oauth_hash=""
if [[ -n "$oauth_line" ]]; then
  oauth_hash="$(printf '%s' "$oauth_line" | sha256sum | cut -d' ' -f1)"
fi
oauth_state_file="$state_dir/last-oauth-5xx.sha256"
previous_oauth_hash="$(cat "$oauth_state_file" 2>/dev/null || true)"
if [[ -n "$oauth_hash" && -n "$previous_oauth_hash" && "$oauth_hash" != "$previous_oauth_hash" ]]; then
  add_failure "OAuth callback 5xx 신규 발생"
fi
printf '%s' "$oauth_hash" > "$oauth_state_file"
chmod 600 "$oauth_state_file"

status="ok"
detail=""
if (( ${#failures[@]} > 0 )); then
  status="failure"
  detail="$(printf '%s\n' "${failures[@]}" | sort -u | paste -sd ', ' -)"
fi

fingerprint="$(printf '%s|%s' "$status" "$detail" | sha256sum | cut -d' ' -f1)"
status_file="$state_dir/status"
fingerprint_file="$state_dir/fingerprint"
previous_status="$(cat "$status_file" 2>/dev/null || true)"
previous_fingerprint="$(cat "$fingerprint_file" 2>/dev/null || true)"

webhook_url=""
if [[ -r "$webhook_env_file" ]]; then
  webhook_url="$(sed -n "s/^${webhook_name}=//p" "$webhook_env_file" | tail -n 1)"
fi

send_webhook() {
  local message="$1" payload
  [[ -n "$webhook_url" ]] || return 0
  payload="$(MESSAGE="$message" python3 -c 'import json, os; print(json.dumps({"content": os.environ["MESSAGE"]}, ensure_ascii=False))')"
  curl -fsS --max-time 15 -H 'Content-Type: application/json' --data "$payload" "$webhook_url" >/dev/null
}

checked_at="$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S KST')"
host="$(hostname)"
if [[ "$status" == "failure" && "$fingerprint" != "$previous_fingerprint" ]]; then
  send_webhook "🚨 급똥 운영 장애 감지\n호스트: $host\n시각: $checked_at\n항목: $detail"
elif [[ "$status" == "ok" && "$previous_status" == "failure" ]]; then
  send_webhook "✅ 급똥 운영 서비스 복구\n호스트: $host\n시각: $checked_at\n자동 점검 항목이 모두 정상입니다."
fi

printf '%s' "$status" > "$status_file"
printf '%s' "$fingerprint" > "$fingerprint_file"
chmod 600 "$status_file" "$fingerprint_file"

if [[ "$status" == "failure" ]]; then
  echo "장애 감지: $detail" >&2
  exit 1
fi

echo "자동 점검 정상: $checked_at"
