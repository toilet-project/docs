import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

source = Path(__file__).resolve().parents[1] / 'scripts' / 'worker-health-monitor.py'
spec = importlib.util.spec_from_file_location('worker_monitor', source)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def checks(code):
    return [{'result': code}]


class MonitorTests(unittest.TestCase):
    def test_healthy(self):
        self.assertEqual(m.classify(200, '<html>급똥 toilet/1102</html>'), 'OK')

    def test_resource_limit(self):
        self.assertEqual(m.classify(500, 'error code: 1102'), 'WORKER_RESOURCE_LIMIT')
        self.assertEqual(m.classify(500, '<h1>Error <span>1102</span></h1>'), 'WORKER_RESOURCE_LIMIT')

    def test_request_limit(self):
        self.assertEqual(m.classify(530, 'error code: 1027'), 'REQUEST_LIMIT')

    def test_no_false_limit(self):
        self.assertEqual(m.classify(503, 'toilet 1102 unavailable'), 'HTTP_5XX')

    def test_other_statuses(self):
        for status, code in [(429, 'RATE_LIMIT'), (403, 'ACCESS_BLOCKED'), (502, 'HTTP_5XX'), (302, 'HTTP_UNEXPECTED'), (404, 'HTTP_UNEXPECTED')]:
            self.assertEqual(m.classify(status, ''), code)
        self.assertEqual(m.classify(200, '<html>Challenge</html>'), 'CONTENT_MISMATCH')

    def test_limit_immediate(self):
        state, event = m.decision({}, checks('WORKER_RESOURCE_LIMIT'), 100)
        self.assertEqual(event['kind'], 'failure')
        self.assertNotIn('notified', state)

    def test_transient_waits(self):
        state, event = m.decision({}, checks('NETWORK_ERROR'), 100)
        self.assertIsNone(event)
        state, event = m.decision(state, checks('NETWORK_ERROR'), 400)
        self.assertEqual(event['kind'], 'failure')

    def test_delivery_failure_retries(self):
        state, event = m.decision({}, checks('WORKER_RESOURCE_LIMIT'), 100)
        state, retry = m.decision(state, checks('WORKER_RESOURCE_LIMIT'), 400)
        self.assertEqual(retry, event)

    def test_dedup_and_reminder(self):
        state, event = m.decision({}, checks('WORKER_RESOURCE_LIMIT'), 100)
        m.delivered(state, event, 100)
        state, event = m.decision(state, checks('WORKER_RESOURCE_LIMIT'), 400)
        self.assertIsNone(event)
        state, event = m.decision(state, checks('WORKER_RESOURCE_LIMIT'), 1900)
        self.assertEqual(event['kind'], 'failure')

    def test_recovery_two_successes(self):
        state = {'notified': 'HTTP_5XX', 'notified_at': 1}
        state, event = m.decision(state, checks('OK'), 100)
        self.assertIsNone(event)
        state, event = m.decision(state, checks('OK'), 400)
        self.assertEqual(event['kind'], 'recovery')
        # Failed recovery delivery retries, successful one clears the incident.
        state, event = m.decision(state, checks('OK'), 700)
        self.assertIsNotNone(event)
        m.delivered(state, event, 700)
        state, event = m.decision(state, checks('OK'), 1000)
        self.assertIsNone(event)

    def test_changed_error_alerts(self):
        state = {'notified': 'HTTP_5XX', 'notified_at': 100, 'failures': 2}
        state, event = m.decision(state, checks('REQUEST_LIMIT'), 200)
        self.assertEqual(event['fingerprint'], 'REQUEST_LIMIT')

    def test_transient_recovers_without_notification(self):
        state, _ = m.decision({}, checks('NETWORK_ERROR'), 100)
        state, event = m.decision(state, checks('OK'), 400)
        self.assertIsNone(event)
        self.assertEqual(state['failures'], 0)

    def test_state_restart_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            m.save(path, {'notified': 'HTTP_5XX', 'notified_at': 100, 'failures': 2})
            state, event = m.decision(json.loads(path.read_text()), checks('HTTP_5XX'), 400)
            self.assertIsNone(event)

    def test_rotation_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for _ in range(4):
                (path / 'checks.jsonl').write_text('x' * 1048576)
                m.log(path, {'result': 'OK'})
            self.assertEqual(len(list(path.glob('checks.jsonl*'))), 3)

    def test_webhook_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('BATCH_FAILURE_WEBHOOK_URL=https://example.com/api/webhooks/fake\n')
            self.assertRaises(ValueError, m.webhook_from_file, path)
            path.write_text('BATCH_FAILURE_WEBHOOK_URL="https://discord.com/api/webhooks/test/fake"\n')
            self.assertEqual(m.webhook_from_file(path), 'https://discord.com/api/webhooks/test/fake')

    def test_network_failure_is_redacted(self):
        with patch.object(m.urllib.request, 'build_opener', side_effect=RuntimeError('secret must not be logged')):
            row = m.probe('https://preview.geupddong.com', '/')
        self.assertEqual(row['result'], 'NETWORK_ERROR')
        self.assertNotIn('secret', json.dumps(row))


if __name__ == '__main__':
    unittest.main()
