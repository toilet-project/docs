import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "systemd-retention-failure.py"
spec = importlib.util.spec_from_file_location("retention_notice", SOURCE)
notice = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notice)


def environment():
    return {"MONITOR_UNIT": "geupddong-backup-retention.service", "MONITOR_INVOCATION_ID": "a" * 32,
            "MONITOR_SERVICE_RESULT": "exit-code", "MONITOR_EXIT_CODE": "exited", "MONITOR_EXIT_STATUS": "1"}


class PolicyTests(unittest.TestCase):
    def test_backup_failure_has_distinct_label(self):
        env = {**environment(), "MONITOR_UNIT": "geupddong-mysql-backup.service",
               "GEUPDDONG_FAILURE_EXPECTED_UNIT": "geupddong-mysql-backup.service", "MONITOR_EXIT_STATUS": "2"}
        self.assertIn("MySQL 백업 실패", notice.payload(notice.event_from(env))["content"])

    def test_valid_failure_is_aggregate_only(self):
        event = notice.event_from(environment())
        body = notice.payload(event)
        self.assertEqual([], body["allowed_mentions"]["parse"])
        self.assertNotIn(event["invocation"], json.dumps(body))
        self.assertNotIn("WEBHOOK", json.dumps(body))

    def test_test_message_is_explicit_and_exit_two_is_attention(self):
        event = notice.event_from(environment())
        self.assertIn("실제 장애 아님", notice.payload(event, True)["content"])
        event["status"] = "2"
        self.assertIn("확인 필요", notice.payload(event)["content"])

    def test_reject_foreign_source_success_and_injection(self):
        for field, value in [("MONITOR_UNIT", "unrelated.service"), ("MONITOR_SERVICE_RESULT", "success"),
                             ("MONITOR_INVOCATION_ID", "bad"), ("MONITOR_EXIT_CODE", "text"),
                             ("MONITOR_EXIT_STATUS", "1\nSECRET")]:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    notice.event_from({**environment(), field: value})

    def test_resource_failure_without_exit_status_is_supported(self):
        env = environment()
        env["MONITOR_SERVICE_RESULT"] = "resources"
        env.pop("MONITOR_EXIT_CODE")
        env.pop("MONITOR_EXIT_STATUS")
        self.assertEqual("unknown", notice.event_from(env)["status"])

    def test_webhook_allowlist(self):
        good = "https://discord.com/api/webhooks/123/fixture_only"
        self.assertEqual(good, notice.checked_url(good))
        for bad in [good + "?x=1", good + "#x", "\n" + good, good.replace("https", "http"),
                    good.replace("discord.com", "example.com"), good.replace("discord.com", "discord.com:443")]:
            with self.assertRaises(ValueError):
                notice.checked_url(bad)

    def test_no_redirect_and_no_proxy_inheritance(self):
        self.assertIsNone(notice.NoRedirect().redirect_request(None, None, None, None, None, None))
        class Response:
            status = 204
            def __enter__(self): return self
            def __exit__(self, *args): return False
        class Opener:
            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return Response()
        opener = Opener()
        with patch.object(notice, "build_opener", return_value=opener) as builder:
            notice.send_discord("https://discord.com/api/webhooks/123/fixture", {"content": "synthetic"})
        self.assertEqual({}, builder.call_args.args[0].proxies)
        self.assertEqual(10, opener.timeout)
        self.assertEqual("POST", opener.request.method)

    def test_state_schema_and_duplicate_keys_rejected(self):
        state = {"version": 1, "fingerprint": "b" * 64, "invocation": "a" * 32, "sentAt": 100}
        self.assertEqual(state, notice.checked_state(state))
        for change in [{"version": True}, {"sentAt": "100"}, {"sentAt": -1}, {"secret": "fixture"}]:
            with self.assertRaises(ValueError): notice.checked_state({**state, **change})
        with self.assertRaises(ValueError):
            notice.duplicate_reject([("version", 1), ("version", 1)])

    def test_disabled_does_not_read_keys_or_send(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(notice, "read_webhook") as read:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, notice.main())
            read.assert_not_called()

    def test_errors_do_not_print_exception_or_secret(self):
        with patch.dict(os.environ, {"GEUPDDONG_SYSTEMD_FAILURE_ENABLED": "true"}, clear=True):
            with patch.object(notice, "event_from", side_effect=RuntimeError("SECRET_FIXTURE")):
                output = io.StringIO()
                with contextlib.redirect_stderr(output): self.assertEqual(1, notice.main())
                self.assertNotIn("SECRET", output.getvalue())
                self.assertNotIn("Traceback", output.getvalue())


@unittest.skipUnless(sys.platform == "linux", "Linux POSIX/flock filesystem verification")
class LinuxStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="retention-notice-test-")
        self.directory = Path(self.temporary.name)
        self.directory.chmod(0o700)
        self.event = notice.event_from(environment())
        self.sent = []
    def tearDown(self): self.temporary.cleanup()
    def notify(self, event=None, now=100000):
        return notice.notify(event or self.event, self.directory, self.sent.append, now)

    def test_delivered_then_suppressed_with_private_durable_state(self):
        self.assertEqual("SENT", self.notify())
        state = notice.read_state(self.directory / "notice-state.json")
        self.assertEqual(100000, state["sentAt"])
        self.assertEqual(0o600, (self.directory / "notice-state.json").stat().st_mode & 0o777)
        self.assertEqual("SUPPRESSED", self.notify(now=100001))
        self.assertEqual("SUPPRESSED", self.notify({**self.event, "invocation": "b" * 32}, now=100002))
        self.assertEqual(1, len(self.sent))
        self.assertEqual("SENT", self.notify({**self.event, "invocation": "b" * 32}, now=121600))

    def test_changed_failure_and_clock_reversal(self):
        self.notify()
        with self.assertRaises(ValueError): self.notify(now=99999)
        self.assertEqual("SENT", self.notify({**self.event, "invocation": "b" * 32, "status": "2"}, now=100001))

    def test_transport_failure_does_not_acknowledge(self):
        def fail(body): raise OSError("synthetic")
        with self.assertRaises(OSError): notice.notify(self.event, self.directory, fail, 100000)
        self.assertIsNone(notice.read_state(self.directory / "notice-state.json"))
        self.assertEqual("SENT", self.notify())

    def test_corrupt_state_fails_closed(self):
        state = self.directory / "notice-state.json"
        state.write_text("{}")
        state.chmod(0o600)
        with self.assertRaises(ValueError): self.notify()
        self.assertEqual([], self.sent)

    def test_state_and_lock_symlinks_rejected(self):
        target = self.directory / "target"
        target.write_text("unchanged")
        state = self.directory / "notice-state.json"
        state.symlink_to(target)
        with self.assertRaises(OSError): self.notify()
        state.unlink()
        (self.directory / ".notice.lock").unlink()
        (self.directory / ".notice.lock").symlink_to(target)
        with self.assertRaises(OSError): self.notify()
        self.assertEqual("unchanged", target.read_text())

    def test_real_lock_prevents_simultaneous_send(self):
        import fcntl
        path = self.directory / ".notice.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError): self.notify()
        finally: os.close(fd)
        self.assertEqual([], self.sent)

    def test_directory_permissions_and_links_rejected(self):
        self.assertEqual(self.directory, notice.private_directory(str(self.directory)))
        self.directory.chmod(0o750)
        with self.assertRaises(ValueError): notice.private_directory(str(self.directory))
        self.directory.chmod(0o700)
        link = self.directory / "link"
        link.symlink_to(self.directory)
        with self.assertRaises(ValueError): notice.private_directory(str(link))

    def test_read_only_selected_webhook_and_reject_duplicates(self):
        config = self.directory / "synthetic.env"
        value = "https://discord.com/api/webhooks/123/fixture"
        config.write_text("IGNORED=not-used\nBATCH_FAILURE_WEBHOOK_URL=" + value + "\n")
        self.assertEqual(value, notice.read_webhook(config))
        config.write_text("BATCH_FAILURE_WEBHOOK_URL=" + value + "\nBATCH_FAILURE_WEBHOOK_URL=" + value)
        with self.assertRaises(ValueError): notice.read_webhook(config)


if __name__ == "__main__":
    unittest.main()
