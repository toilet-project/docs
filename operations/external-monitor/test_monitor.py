import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock

import monitor as m

NOW = 2000000000
HEALTH = 'API server is running (DB: toilet_db)'
HEADERS = {'cache-control': 'no-cache, no-store', 'cf-cache-status': 'DYNAMIC'}


def row(target='api', code='OK', status=200):
    return dict(target=target, code=code, status=status, latency_ms=1)


def state(notified=None, notified_at=NOW-10, checked_at=NOW-10):
    return dict(version=1, notified=notified or [], notified_at=notified_at, checked_at=checked_at)


class Classification(unittest.TestCase):
    def test_api_live_db_health(self):
        self.assertEqual(m.classify('api', 200, HEADERS, HEALTH), 'OK')

    def test_api_requires_db_body(self):
        self.assertEqual(m.classify('api', 200, HEADERS, 'OK'), 'CONTENT')

    def test_wrong_database(self):
        self.assertEqual(m.classify('api', 200, HEADERS, 'API server is running (DB: other)'), 'CONTENT')

    def test_cached_api_rejected(self):
        for code in ('HIT', 'STALE', 'UPDATING', 'REVALIDATED'):
            with self.subTest(code=code):
                self.assertEqual(m.classify('api', 200, dict(HEADERS, **{'cf-cache-status': code}), HEALTH), 'CACHED_HEALTH')

    def test_missing_no_store_rejected(self):
        self.assertEqual(m.classify('api', 200, {}, HEALTH), 'CACHED_HEALTH')

    def test_positive_age_rejected(self):
        self.assertEqual(m.classify('api', 200, dict(HEADERS, age='1'), HEALTH), 'CACHED_HEALTH')

    def test_web_head_html(self):
        self.assertEqual(m.classify('web', 200, {'content-type': 'text/html; charset=utf-8'}, ''), 'OK')

    def test_web_non_html(self):
        self.assertEqual(m.classify('web', 200, {'content-type': 'application/json'}, ''), 'CONTENT')

    def test_redirect_not_followed_or_healthy(self):
        self.assertEqual(m.classify('web', 302, {}, ''), 'HTTP_ERROR')

    def test_server_error(self):
        self.assertEqual(m.classify('api', 503, {}, ''), 'HTTP_ERROR')

    def test_access_status_and_challenge(self):
        for status, headers in ((403, {}), (401, {}), (200, {'cf-mitigated': 'challenge'})):
            self.assertEqual(m.classify('web', status, headers, ''), 'ACCESS_BLOCKED')


class Collection(unittest.TestCase):
    def test_healthy_one_probe_each(self):
        probe = Mock(side_effect=lambda target: row(target))
        sleep = Mock()
        self.assertEqual(len(m.collect(probe, sleep)), 2)
        self.assertEqual(probe.call_count, 2)
        sleep.assert_not_called()

    def test_failure_confirmation_only_failed_target(self):
        probe = Mock(side_effect=[row('web'), row('api', 'NETWORK', 0), row('api', 'NETWORK', 0)])
        result = m.collect(probe, Mock())
        self.assertEqual(probe.call_count, 3)
        self.assertEqual(result[1]['code'], 'NETWORK')

    def test_challenge_not_retried(self):
        probe = Mock(side_effect=[row('web', 'ACCESS_BLOCKED', 403), row('api')])
        result = m.collect(probe, Mock())
        self.assertEqual(probe.call_count, 2)
        self.assertEqual(result[0]['code'], 'ACCESS_BLOCKED')

    def test_transient_is_not_full_recovery(self):
        probe = Mock(side_effect=[row('web'), row('api', 'NETWORK', 0), row('api')])
        self.assertEqual(m.collect(probe, Mock())[1]['code'], 'FLAPPING')

    def test_curl_timeout_sanitized(self):
        with patch.object(m.subprocess, 'run', side_effect=subprocess.TimeoutExpired('curl', 12)):
            self.assertEqual(m.probe('api')['code'], 'NETWORK')

    def test_curl_tls_error_sanitized(self):
        result = Mock(stdout=b'000', returncode=60, stderr=b'sensitive fixture')
        with patch.object(m.subprocess, 'run', return_value=result):
            self.assertNotIn('sensitive', json.dumps(m.probe('api')))
            self.assertEqual(m.probe('api')['code'], 'TLS')

    def test_no_redirect_cookie_or_custom_identity(self):
        result = Mock(stdout=b'000', returncode=7)
        with patch.object(m.subprocess, 'run', return_value=result) as run:
            m.probe('api')
        args = run.call_args.args[0]
        for forbidden in ('--location', '-L', '--insecure', '-k', '--cookie', '--user-agent', '-A'):
            self.assertNotIn(forbidden, args)
        self.assertEqual(args[-1], m.TARGETS['api'])


class StateDecision(unittest.TestCase):
    def test_state_restored(self):
        self.assertTrue(m.valid_state(state(), NOW))

    def test_extra_fields_rejected(self):
        self.assertFalse(m.valid_state(dict(state(), arbitrary='secret'), NOW))

    def test_unknown_signature_rejected(self):
        self.assertFalse(m.valid_state(state(['https://evil.invalid']), NOW))

    def test_stale_state_rejected(self):
        self.assertFalse(m.valid_state(state(checked_at=NOW-m.MAX_STATE_AGE-1), NOW))

    def test_future_state_rejected(self):
        self.assertFalse(m.valid_state(state(checked_at=NOW+61), NOW))

    def test_bad_type_rejected(self):
        self.assertFalse(m.valid_state(state(checked_at=True), NOW))
        self.assertFalse(m.valid_state([], NOW))

    def test_first_failure_alert(self):
        self.assertEqual(m.decide(m.empty_state(), [row('api', 'NETWORK')], NOW)['kind'], 'failure')

    def test_unchanged_failure_suppressed(self):
        self.assertIsNone(m.decide(state(['api:NETWORK']), [row('api', 'NETWORK')], NOW))

    def test_hourly_reminder(self):
        self.assertIsNotNone(m.decide(state(['api:NETWORK'], NOW-3601), [row('api', 'NETWORK')], NOW))

    def test_failure_changed(self):
        self.assertIsNotNone(m.decide(state(['api:NETWORK']), [row('api', 'HTTP_ERROR')], NOW))

    def test_recovery_only_after_delivered_incident(self):
        self.assertEqual(m.decide(state(['api:NETWORK']), [row()], NOW)['kind'], 'recovery')
        self.assertIsNone(m.decide(state(), [row()], NOW))


class Execution(unittest.TestCase):
    def run_mode(self, mode, codes=('OK', 'OK'), accepted=True, previous=None):
        with tempfile.TemporaryDirectory() as directory:
            path, summary = Path(directory)/'state.json', Path(directory)/'summary.json'
            if previous:
                path.write_text(json.dumps(previous))
            probe = lambda target: row(target, codes[list(m.TARGETS).index(target)])
            sender = Mock(return_value=accepted)
            with contextlib.redirect_stdout(io.StringIO()) as output:
                result = m.execute(mode, path, summary, 'secret-fixture', probe, Mock(), sender, NOW)
            saved = json.loads(path.read_text()) if path.exists() else None
            self.assertNotIn('secret-fixture', output.getvalue())
            return result, saved, json.loads(summary.read_text()), sender

    def test_probe_no_state_no_notification(self):
        result, saved, _, sender = self.run_mode('probe', ('OK', 'NETWORK'))
        self.assertEqual(result, 1)
        self.assertIsNone(saved)
        sender.assert_not_called()

    def test_success_acknowledges_incident(self):
        result, saved, summary, sender = self.run_mode('monitor', ('OK', 'NETWORK'))
        self.assertEqual(result, 0)
        self.assertEqual(saved['notified'], ['api:NETWORK'])
        self.assertFalse(summary['healthy'])
        sender.assert_called_once()

    def test_failed_delivery_does_not_acknowledge(self):
        result, saved, _, _ = self.run_mode('monitor', ('OK', 'NETWORK'), False)
        self.assertEqual(result, 1)
        self.assertEqual(saved['notified'], [])

    def test_failed_recovery_preserves_incident(self):
        result, saved, _, _ = self.run_mode('monitor', accepted=False, previous=state(['api:NETWORK']))
        self.assertEqual(result, 1)
        self.assertEqual(saved['notified'], ['api:NETWORK'])

    def test_recovery_clears_only_after_delivery(self):
        result, saved, _, _ = self.run_mode('monitor', previous=state(['api:NETWORK']))
        self.assertEqual(result, 0)
        self.assertEqual(saved['notified'], [])

    def test_test_message_exactly_one_and_no_state(self):
        result, saved, _, sender = self.run_mode('notification-test')
        self.assertEqual(result, 0)
        self.assertIsNone(saved)
        sender.assert_called_once()
        self.assertIn('실제 장애가 아닙니다', sender.call_args.args[1])

    def test_healthy_initialization_silent(self):
        result, _, _, sender = self.run_mode('monitor')
        self.assertEqual(result, 0)
        sender.assert_not_called()

    def test_cache_corruption_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'state'
            for content in ('{', '[]', 'x'*5000):
                path.write_text(content)
                self.assertEqual(m.read_state(path, NOW)[1], 'missing_or_invalid')


class NotificationSafety(unittest.TestCase):
    def test_notification_rejected_outside_main(self):
        with patch.dict(m.os.environ, {'GITHUB_REPOSITORY': 'toilet-project/docs', 'GITHUB_REF': 'refs/heads/feature/test', 'EXTERNAL_MONITOR_ENABLED': 'true'}, clear=True), patch('sys.argv', ['monitor.py', '--mode', 'monitor']), patch.object(m, 'execute') as execute, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                m.main()
            execute.assert_not_called()

    def test_main_requires_explicit_activation(self):
        with patch.dict(m.os.environ, {'GITHUB_REPOSITORY': 'toilet-project/docs', 'GITHUB_REF': 'refs/heads/main'}, clear=True), patch('sys.argv', ['monitor.py', '--mode', 'notification-test']), patch.object(m, 'execute') as execute, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                m.main()
            execute.assert_not_called()

    def test_bad_webhook_never_requested(self):
        bad = ['http://discord.com/api/webhooks/1/a', 'https://evil.invalid/api/webhooks/1/a',
               'https://discord.com.evil.invalid/api/webhooks/1/a', 'https://discord.com:bad/',
               'https://u:p@discord.com/api/webhooks/1/a', 'https://discord.com/api/webhooks/1/a?x=y',
               'https://discord.com/api/webhooks/1/a#x', 'https://discord.com:443/api/webhooks/1/a']
        with patch.object(m.urllib.request, 'build_opener') as opener:
            for url in bad:
                self.assertFalse(m.send(url, 'fixture'))
            opener.assert_not_called()

    def test_redirect_refused(self):
        self.assertIsNone(m.NoRedirect().redirect_request(None))

    def test_mentions_disabled(self):
        response = Mock()
        response.__enter__ = Mock(return_value=Mock(status=200, read=Mock(return_value=b'{"id":"123"}')))
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with patch.object(m.urllib.request, 'build_opener', return_value=opener):
            self.assertTrue(m.send('https://discord.com/api/webhooks/1/fixture', '@everyone'))
        self.assertEqual(json.loads(opener.open.call_args.args[0].data)['allowed_mentions'], {'parse': []})
        self.assertEqual(opener.open.call_args.args[0].get_header('User-agent'), m.DISCORD_USER_AGENT)
        self.assertTrue(opener.open.call_args.args[0].full_url.endswith('?wait=true'))

    def test_missing_saved_message_is_failure(self):
        response = Mock()
        response.__enter__ = Mock(return_value=Mock(status=200, read=Mock(return_value=b'{}')))
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with patch.object(m.urllib.request, 'build_opener', return_value=opener):
            self.assertFalse(m.send('https://discord.com/api/webhooks/1/fixture', 'test'))

    def test_http_error_only_status_is_logged(self):
        opener = Mock()
        opener.open.side_effect = m.urllib.error.HTTPError('https://discord.com/api/webhooks/1/secret-fixture', 403, 'secret-fixture', {}, None)
        with patch.object(m.urllib.request, 'build_opener', return_value=opener), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertFalse(m.send('https://discord.com/api/webhooks/1/fixture', 'test'))
        self.assertIn('403', out.getvalue())
        self.assertNotIn('secret-fixture', out.getvalue())

    def test_send_failure_no_exception_or_secret_output(self):
        opener = Mock()
        opener.open.side_effect = OSError('secret-fixture')
        with patch.object(m.urllib.request, 'build_opener', return_value=opener), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertFalse(m.send('https://discord.com/api/webhooks/1/fixture', 'test'))
        self.assertNotIn('secret-fixture', out.getvalue())


if __name__ == '__main__':
    unittest.main()
