#!/usr/bin/env python3
"""Bounded public probes; no SSH, private endpoints, cookies, or repair actions."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

TARGETS = {'web': 'https://geupddong.com/', 'api': 'https://api.geupddong.com/api/health'}
CODES = {'OK', 'NETWORK', 'TLS', 'ACCESS_BLOCKED', 'HTTP_ERROR', 'CONTENT', 'CACHED_HEALTH', 'FLAPPING'}
MAX_STATE_AGE = 3 * 86400
REMINDER = 3600
DISCORD_USER_AGENT = 'DiscordBot (https://github.com/toilet-project/docs, 1.0)'


def api_health_ok(body):
    # Keep the previous exact response during rollout and image rollback.
    if body == 'API server is running (DB: toilet_db)':
        return True
    try:
        return json.loads(body) == {'status': 'UP'}
    except (ValueError, TypeError):
        return False


def classify(target, status, headers, body):
    if headers.get('cf-mitigated') or status in (401, 403):
        return 'ACCESS_BLOCKED'  # Never retry with a different identity or bypass a challenge.
    if status != 200:
        return 'HTTP_ERROR'
    if target == 'api':
        if (headers.get('cf-cache-status', '').upper() in {'HIT', 'STALE', 'UPDATING', 'REVALIDATED'}
                or headers.get('age', '0') != '0' or 'no-store' not in headers.get('cache-control', '').lower()):
            return 'CACHED_HEALTH'
        if not api_health_ok(body.strip()):
            return 'CONTENT'
    elif 'text/html' not in headers.get('content-type', '').lower():
        return 'CONTENT'
    return 'OK'


def probe(target):
    url = TARGETS[target]  # No caller-provided URLs, no redirects, no cookies or auth.
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='external-probe-') as directory:
        headers_path, body_path = Path(directory) / 'headers', Path(directory) / 'body'
        args = ['curl', '--silent', '--show-error', '--proto', '=https', '--connect-timeout', '4',
                '--max-time', '10', '--max-filesize', '65536', '--dump-header', str(headers_path),
                '--output', str(body_path), '--write-out', '%{http_code}']
        if target == 'web':
            args.append('--head')  # Availability only; not a functional rendering assertion.
        try:
            result = subprocess.run(args + [url], capture_output=True, timeout=12, check=False)
            status = int(result.stdout.strip()) if re.fullmatch(rb'\d{3}', result.stdout.strip()) else 0
            if result.returncode:
                code = 'TLS' if result.returncode in (35, 51, 58, 60, 77) else 'NETWORK'
            else:
                raw = headers_path.read_text(errors='replace')[:32768]
                headers = {}
                for line in raw.splitlines():
                    if line.startswith('HTTP/'):
                        headers = {}
                    elif ':' in line:
                        key, value = line.split(':', 1)
                        headers[key.lower().strip()] = value.strip()
                body = body_path.read_bytes()[:65536].decode('utf-8', errors='replace')
                code = classify(target, status, headers, body)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            status, code = 0, 'NETWORK'
    return {'target': target, 'status': status, 'code': code,
            'latency_ms': round((time.monotonic() - started) * 1000)}


def collect(probe_fn=probe, sleep_fn=time.sleep):
    first = [probe_fn(target) for target in TARGETS]
    # Recheck failures only; an edge challenge is terminal for this invocation.
    retry = [row['target'] for row in first if row['code'] not in {'OK', 'ACCESS_BLOCKED'}]
    if retry:
        sleep_fn(5)
    second = {target: probe_fn(target) for target in retry}
    checks = []
    for row in first:
        confirmed = second.get(row['target'])
        if confirmed and confirmed['code'] == 'OK':
            row = dict(confirmed, code='FLAPPING')  # Do not announce full recovery from a transient failure.
        elif confirmed:
            row = confirmed
        checks.append(row)
    return checks


def empty_state():
    return {'version': 1, 'notified': [], 'notified_at': 0, 'checked_at': 0}


def valid_state(value, now):
    if not isinstance(value, dict) or set(value) != {'version', 'notified', 'notified_at', 'checked_at'}:
        return False
    allowed = {target + ':' + code for target in TARGETS for code in CODES - {'OK'}}
    if value['version'] != 1 or not isinstance(value['notified'], list) or len(value['notified']) > 2:
        return False
    if not all(isinstance(item, str) and item in allowed for item in value['notified']):
        return False
    for key in ('notified_at', 'checked_at'):
        if type(value[key]) is not int or not 0 <= value[key] <= now + 60:
            return False
    return 0 <= now - value['checked_at'] <= MAX_STATE_AGE


def read_state(path, now):
    try:
        if path.stat().st_size > 4096:
            raise ValueError('oversized state')
        value = json.loads(path.read_text())
        if valid_state(value, now):
            return value, 'restored'
    except (OSError, ValueError, TypeError):
        pass
    return empty_state(), 'missing_or_invalid'  # Cache is not durable: duplicates are possible.


def decide(previous, checks, now):
    signature = sorted(row['target'] + ':' + row['code'] for row in checks if row['code'] != 'OK')
    if signature:
        if signature != previous['notified'] or now - previous['notified_at'] >= REMINDER:
            return {'kind': 'failure', 'signature': signature}
    elif previous['notified']:
        return {'kind': 'recovery', 'signature': []}
    return None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def send(webhook, message):
    try:
        parsed = urllib.parse.urlsplit(webhook)
        valid = (parsed.scheme == 'https' and parsed.hostname == 'discord.com' and parsed.port is None
                 and not (parsed.username or parsed.password or parsed.query or parsed.fragment)
                 and re.fullmatch(r'/api/webhooks/[0-9]+/[A-Za-z0-9_-]+', parsed.path))
    except ValueError:
        valid = False
    if not valid:
        print(json.dumps({'notification_error': 'INVALID_WEBHOOK_CONFIGURATION'}))
        return False
    payload = json.dumps({'content': message, 'allowed_mentions': {'parse': []}}, ensure_ascii=False).encode()
    request = urllib.request.Request(webhook + '?wait=true', data=payload, method='POST',
                                    headers={'Content-Type': 'application/json', 'User-Agent': DISCORD_USER_AGENT})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
            accepted = response.status == 200 and bool(json.loads(response.read(16384)).get('id'))
            print(json.dumps({'notification_http_status': response.status, 'saved_message_confirmed': accepted}))
            return accepted
    except urllib.error.HTTPError as error:
        print(json.dumps({'notification_http_status': error.code, 'saved_message_confirmed': False}))
        error.close()
        return False
    except (OSError, urllib.error.URLError, ValueError, AttributeError):
        print(json.dumps({'notification_error': 'TRANSPORT_OR_CONFIRMATION', 'saved_message_confirmed': False}))
        return False  # Never print exception text: it may contain the webhook URL.


def message_for(event):
    if event['kind'] == 'recovery':
        return '✅ 급똥 외부 접속 복구\n공개 웹·API 점검 정상. 서비스 자동 재시작 없음.'
    return ('🚨 급똥 외부 접속 이상\n분류: ' + ', '.join(event['signature'])
            + '\n미니 PC·네트워크·Cloudflare·접근 정책을 확인해 주세요. 원인 확정이나 자동 복구는 하지 않습니다.')


def save_state(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.state-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def execute(mode, state_path, summary_path, webhook='', probe_fn=probe, sleep_fn=time.sleep,
            send_fn=send, now=None):
    now = int(time.time()) if now is None else now
    checks = collect(probe_fn, sleep_fn)
    previous, state_status = read_state(state_path, now) if mode == 'monitor' else (empty_state(), 'not_used')
    event = decide(previous, checks, now) if mode == 'monitor' else None
    delivery = 'none'
    if mode == 'notification-test':
        delivery = 'accepted' if send_fn(webhook, '🧪 급똥 외부 감시 연결 테스트\n실제 장애가 아닙니다. 개인정보·회원 데이터·서버 식별자 미포함.') else 'failed'
    elif event:
        delivery = 'accepted' if send_fn(webhook, message_for(event)) else 'failed'
        if delivery == 'accepted':
            previous['notified'], previous['notified_at'] = event['signature'], now
    if mode == 'monitor':
        previous['checked_at'] = now
        save_state(state_path, previous)
    summary = {'checked_at_epoch': now, 'mode': mode, 'checks': checks, 'healthy': all(c['code'] == 'OK' for c in checks),
               'state': state_status, 'notification': delivery}
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary))
    # A monitor job's success means execution/delivery success, NOT necessarily healthy service.
    return int(delivery == 'failed' or (mode == 'probe' and not summary['healthy']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['probe', 'monitor', 'notification-test'], default='probe')
    parser.add_argument('--state', type=Path, default=Path('.external-monitor/state.json'))
    parser.add_argument('--summary', type=Path, default=Path('.external-monitor-summary/result.json'))
    args = parser.parse_args()
    # This public checkout never sends notifications outside the approved main workflow context.
    if args.mode != 'probe' and not (os.environ.get('GITHUB_REPOSITORY') == 'toilet-project/docs'
            and os.environ.get('GITHUB_REF') == 'refs/heads/main' and os.environ.get('EXTERNAL_MONITOR_ENABLED') == 'true'):
        parser.error('Notification mode requires approved main context and activation flag')
    webhook = os.environ.get('DISCORD_EXTERNAL_MONITOR_WEBHOOK', '').strip()
    if args.mode != 'probe' and not webhook:
        parser.error('Dedicated notification secret is missing')
    return execute(args.mode, args.state, args.summary, webhook)


if __name__ == '__main__':
    raise SystemExit(main())
