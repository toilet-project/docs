#!/usr/bin/env python3
"""External, bounded Worker probes. Never logs response bodies or webhook URLs."""
import argparse
import fcntl
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ORIGINS = {'https://preview.geupddong.com', 'https://geupddong.com'}
PATHS = ('/', '/toilet/13144')
LIMITS = {'WORKER_RESOURCE_LIMIT', 'REQUEST_LIMIT'}


def stamp():
    return datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def classify(status, body):
    # Only recognize a platform code in a failed response, never a toilet ID.
    if status >= 400:
        if re.search(r'(?:error(?:\s+code)?[\s:<>/a-z="-]{0,80})1102\b', body, re.I):
            return 'WORKER_RESOURCE_LIMIT'  # 1102 can mean CPU OR memory limit.
        if re.search(r'(?:error(?:\s+code)?[\s:<>/a-z="-]{0,80})1027\b', body, re.I):
            return 'REQUEST_LIMIT'
    if status == 429:
        return 'RATE_LIMIT'  # Could be WAF/rate limiting, not necessarily Workers quota.
    if status in (401, 403):
        return 'ACCESS_BLOCKED'
    if status >= 500:
        return 'HTTP_5XX'
    if status != 200:
        return 'HTTP_UNEXPECTED'
    if '<html' not in body.lower() or '급똥' not in body:
        return 'CONTENT_MISMATCH'
    return 'OK'


def probe(origin, path):
    started = time.monotonic()
    request = urllib.request.Request(origin + path, headers={'User-Agent': 'Geupddong-Health-Monitor/1.0', 'Accept': 'text/html'})
    try:
        try:
            response = urllib.request.build_opener(NoRedirect).open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status = response.code
            body = response.read(65536).decode('utf-8', errors='replace')
        result = classify(status, body)
    except Exception:
        status, result = None, 'NETWORK_ERROR'
    return {'path': path, 'status': status, 'result': result, 'latency_ms': round((time.monotonic() - started) * 1000)}


def webhook_from_file(path):
    # Parse a single value as data, never source/execute the environment file.
    value = ''
    for line in path.read_text().splitlines():
        if line.startswith('BATCH_FAILURE_WEBHOOK_URL='):
            value = line.split('=', 1)[1].strip().strip('\"\'')
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != 'https' or parsed.hostname not in {'discord.com', 'discordapp.com'} or not parsed.path.startswith('/api/webhooks/') or parsed.username or parsed.password:
        raise ValueError('Discord webhook is missing or invalid')
    return value


def send(url, content):
    payload = json.dumps({'content': content, 'allowed_mentions': {'parse': []}}, ensure_ascii=False).encode()
    request = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'Geupddong-Health-Monitor/1.0'}, method='POST')
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def decision(previous, results, now):
    state = dict(previous)
    failures = sorted({row['result'] for row in results if row['result'] != 'OK'})
    state['failures'] = state.get('failures', 0) + 1 if failures else 0
    state['successes'] = state.get('successes', 0) + 1 if not failures else 0
    fingerprint = ','.join(failures)
    event = None
    if failures and (set(failures) & LIMITS or state['failures'] >= 2):
        if not state.get('notified') or fingerprint != state.get('notified') or now - state.get('notified_at', 0) >= 1800:
            event = {'kind': 'failure', 'fingerprint': fingerprint}
    elif not failures and state['successes'] >= 2 and state.get('notified'):
        event = {'kind': 'recovery', 'fingerprint': ''}
    return state, event


def delivered(state, event, now):
    # Only acknowledge alerts after Discord actually accepts them.
    state['notified'] = event['fingerprint']
    state['notified_at'] = now


def save(path, value):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.state-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def log(directory, entry):
    path = directory / 'checks.jsonl'
    # Bounded local history: current plus two 1 MiB rotations, private files.
    if path.exists() and path.stat().st_size >= 1048576:
        older, recent = directory / 'checks.jsonl.2', directory / 'checks.jsonl.1'
        if recent.exists():
            os.replace(recent, older)
        os.replace(path, recent)
    with path.open('a') as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Probe only, no state or Discord changes')
    parser.add_argument('--test-notification', action='store_true', help='Send one clearly labelled delivery test, no incident state changes')
    args = parser.parse_args()
    os.umask(0o077)
    origin = os.environ.get('GEUPDDONG_WORKER_ORIGIN', 'https://preview.geupddong.com')
    if origin not in ORIGINS:
        raise SystemExit('Unapproved probe origin')
    env_file = Path(os.environ.get('GEUPDDONG_MONITOR_WEBHOOK_ENV_FILE', '/home/luha/toilet-batch/.env'))
    if args.test_notification:
        ok = send(webhook_from_file(env_file), f'🧪 급똥 Workers 감시 연결 테스트\n시각: {stamp()}\n실제 장애가 아닙니다. 무료 플랜 유지·자동 유료 전환 없음.')
        print(json.dumps({'test_notification_accepted': ok}))
        return 0 if ok else 1
    directory = Path(os.environ.get('GEUPDDONG_WORKER_STATE_DIR', '/home/luha/.local/state/geupddong-worker-monitor'))
    if args.dry_run:
        results = [probe(origin, path) for path in PATHS]
        print(json.dumps({'origin': origin, 'checks': results, 'dry_run': True}, ensure_ascii=False))
        return int(any(row['result'] != 'OK' for row in results))
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / 'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        state_path = directory / 'state.json'
        state_error = False
        try:
            previous = json.loads(state_path.read_text()) if state_path.exists() else {}
            if not isinstance(previous, dict):
                raise ValueError('invalid state')
        except (ValueError, OSError):
            previous, state_error = {}, True
        results = [probe(origin, path) for path in PATHS]
        now = int(time.time())
        # A later explicit production cutover must not inherit preview incidents.
        if previous.get('origin') != origin:
            previous = {}
        state, event = decision(previous, results, now)
        state['origin'] = origin
        notification = 'none'
        if event:
            if event['kind'] == 'recovery':
                message = '✅ 급똥 Workers 접속 복구\n연속 2회 정상 응답을 확인했습니다.'
            else:
                message = '🚨 급똥 Workers 오류 감지\n분류: ' + event['fingerprint']
                if set(event['fingerprint'].split(',')) & LIMITS:
                    message += '\n리소스/요청 한도 오류입니다. Cloudflare 로그와 유료 전환 필요 여부를 확인해 주세요.'
                else:
                    message += '\n통신·원본 서버·접근 정책도 원인일 수 있어 유료 전환만으로 해결된다고 보지 않습니다.'
            message += f'\n대상: {origin}\n시각: {stamp()}\n플랜 자동 변경 없음.'
            try:
                accepted = send(webhook_from_file(env_file), message)
            except Exception:
                accepted = False
            notification = 'accepted' if accepted else 'failed_retry_next_check'
            if accepted:
                delivered(state, event, now)
        entry = {'checked_at': stamp(), 'origin': origin, 'checks': results, 'notification': notification, 'state_reset_due_to_error': state_error}
        log(directory, entry)
        save(state_path, state)
        print(json.dumps(entry, ensure_ascii=False))
        return int(notification == 'failed_retry_next_check' or any(row['result'] != 'OK' for row in results))


if __name__ == '__main__':
    raise SystemExit(main())
