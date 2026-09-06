#!/usr/bin/env python3
"""Standalone systemd OnFailure handler: no JVM, DB, R2, shell or journal parsing."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener

COOLDOWN_SECONDS = 6 * 60 * 60
RESULTS = {"resources", "timeout", "exit-code", "signal", "core-dump", "watchdog",
           "start-limit-hit", "oom-kill", "protocol", "exec-condition"}


def event_from(env):
    expected = env.get("GEUPDDONG_FAILURE_EXPECTED_UNIT", "geupddong-backup-retention.service")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}\.service", expected):
        raise ValueError("invalid unit")
    if env.get("MONITOR_UNIT") != expected:
        raise ValueError("unexpected source")
    invocation = env.get("MONITOR_INVOCATION_ID", "")
    if not re.fullmatch(r"[a-f0-9]{32}", invocation):
        raise ValueError("missing invocation")
    result = env.get("MONITOR_SERVICE_RESULT", "")
    if result not in RESULTS:
        raise ValueError("invalid failure result")
    code = env.get("MONITOR_EXIT_CODE") or "unknown"
    status = env.get("MONITOR_EXIT_STATUS") or "unknown"
    if code not in {"exited", "killed", "dumped", "unknown"}:
        raise ValueError("invalid exit code")
    if not re.fullmatch(r"(?:[0-9]{1,3}|[A-Z][A-Z0-9]{0,24}|unknown)", status):
        raise ValueError("invalid exit status")
    return {"unit": expected, "invocation": invocation, "result": result, "code": code, "status": status}


def fingerprint(event):
    fields = [event[name] for name in ("unit", "result", "code", "status")]
    return hashlib.sha256(json.dumps(fields, separators=(",", ":")).encode()).hexdigest()


def payload(event, test=False):
    label = "장애 알림 연결 테스트 · 실제 장애 아님" if test else "백업 만료 점검 실패"
    if not test and event["unit"] == "geupddong-mysql-backup.service":
        label = "MySQL 백업 실패"
    if not test and event["unit"] == "geupddong-backup-retention.service" and event["code"] == "exited" and event["status"] == "2":
        label = "백업 만료 점검 확인 필요"
    return {"content": f"[급똥] {label}\n작업: {event['unit']}\n"
                       f"결과: {event['result']} · {event['code']}/{event['status']}\n"
                       "운영자가 systemd 상태를 확인해 주세요. 이 알림은 데이터 삭제를 실행하지 않습니다.",
            "allowed_mentions": {"parse": []}}


def checked_state(value):
    if not isinstance(value, dict) or set(value) != {"version", "fingerprint", "invocation", "sentAt"}:
        raise ValueError("invalid state")
    if type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("invalid state")
    if not isinstance(value["fingerprint"], str) or not re.fullmatch(r"[a-f0-9]{64}", value["fingerprint"]):
        raise ValueError("invalid state")
    if not isinstance(value["invocation"], str) or not re.fullmatch(r"[a-f0-9]{32}", value["invocation"]):
        raise ValueError("invalid state")
    if type(value["sentAt"]) is not int or value["sentAt"] < 0:
        raise ValueError("invalid state")
    return value


def duplicate_reject(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def private_directory(raw):
    directory = Path(raw)
    if not directory.is_absolute() or directory == Path("/") or directory.resolve(strict=True) != directory:
        raise ValueError("invalid state directory")
    info = directory.stat(follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError("insecure state directory")
    return directory


def read_state(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError("invalid state file")
        raw = stream.read(1025)
    if len(raw) > 1024:
        raise ValueError("state too large")
    return checked_state(json.loads(raw, object_pairs_hook=duplicate_reject))


def write_state(directory, value):
    fd, name = tempfile.mkstemp(prefix=".notice-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, directory / "notice-state.json")
        parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def checked_url(url):
    if not isinstance(url, str) or not re.fullmatch(r"https://discord\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]+", url):
        raise ValueError("invalid webhook")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "discord.com" or parsed.query or parsed.fragment:
        raise ValueError("invalid webhook")
    if not re.fullmatch(r"/api/webhooks/[0-9]+/[A-Za-z0-9_-]+", parsed.path):
        raise ValueError("invalid webhook")
    return url


def read_webhook(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("invalid config")
        raw = stream.read(262145)
    if len(raw) > 262144:
        raise ValueError("oversize config")
    values = [line.partition("=")[2].strip() for line in raw.decode().splitlines()
              if line.startswith("BATCH_FAILURE_WEBHOOK_URL=")]
    if len(values) != 1:
        raise ValueError("missing or duplicated webhook")
    return checked_url(values[0])


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def send_discord(url, body):
    checked_url(url)
    request = Request(url, data=json.dumps(body, ensure_ascii=False).encode(),
                      headers={"Content-Type": "application/json", "User-Agent": "GeupddongSystemdNotifier/1.0"}, method="POST")
    # No proxy inheritance, redirects or automatic retries; delivery may be ambiguous after a timeout.
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=10) as response:
        if not 200 <= response.status < 300:
            raise ValueError("delivery rejected")


def notify(event, directory, sender, now, test=False):
    import fcntl  # Linux-only execution; pure formatting tests can be imported on other platforms.
    fd = os.open(directory / ".notice.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_size:
            raise ValueError("invalid notification lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        previous = read_state(directory / "notice-state.json")
        digest = fingerprint(event)
        if previous:
            if now < previous["sentAt"]:
                raise ValueError("clock reversed")
            if previous["invocation"] == event["invocation"] or (previous["fingerprint"] == digest and now - previous["sentAt"] < COOLDOWN_SECONDS):
                return "SUPPRESSED"
        sender(payload(event, test))
        write_state(directory, {"version": 1, "fingerprint": digest, "invocation": event["invocation"], "sentAt": now})
        return "SENT"
    finally:
        os.close(fd)


def main():
    stage = "preflight"
    try:
        if os.environ.get("GEUPDDONG_SYSTEMD_FAILURE_ENABLED") != "true":
            print("SYSTEMD_FAILURE_NOTICE_DISABLED")
            return 0
        event = event_from(os.environ)
        directory = private_directory(os.environ["GEUPDDONG_FAILURE_STATE_DIR"])
        url = read_webhook(os.environ.get("GEUPDDONG_FAILURE_WEBHOOK_FILE", "/home/luha/toilet-batch/.env"))
        test = os.environ.get("GEUPDDONG_FAILURE_TEST_MESSAGE") == "true"
        stage = "delivery-or-state"
        outcome = notify(event, directory, lambda body: send_discord(url, body), int(time.time()), test)
        print("SYSTEMD_FAILURE_NOTICE_" + outcome)
        return 0
    except Exception:
        # Do not emit traceback, exception text, config, command output or webhook URL.
        print("SYSTEMD_FAILURE_NOTICE_FAILED stage=" + stage, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
