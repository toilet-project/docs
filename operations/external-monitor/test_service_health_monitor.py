"""Run the installed-style shell monitor against synthetic commands only."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.name == 'posix', 'shell monitor fixture runs on Linux CI')
class ServiceHealthMonitorTest(unittest.TestCase):
    def run_monitor(self, body, failed=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = {
                'curl': '''#!/usr/bin/env python3
import os, sys
url = sys.argv[-1]
if url.endswith('/api/health'):
    if os.environ.get('FIXTURE_HTTP_FAILURE') == 'true': sys.exit(22)
    print(os.environ['FIXTURE_HEALTH_BODY'])
elif url.endswith('/actuator/health'):
    print('{"status":"UP"}')
elif url.endswith('/oauth2/authorization/google'):
    print('HTTP/1.1 302 Found\\r\\nlocation: https://accounts.google.com/fixture\\r\\n')
elif url.endswith('/oauth2/authorization/kakao'):
    print('HTTP/1.1 302 Found\\r\\nlocation: https://kauth.kakao.com/fixture\\r\\n')
else:
    raise SystemExit('Unexpected fixture destination')
''',
                'docker': '''#!/usr/bin/env python3
import sys
print('healthy' if any('.State.Health' in value for value in sys.argv) else 'true')
''',
                'systemctl': '''#!/usr/bin/env python3
import sys
sys.exit(1 if sys.argv[-1] == 'docker.service' else 0)
''',
            }
            for name, script in commands.items():
                path = root / name
                path.write_text(script)
                path.chmod(0o700)
            log = root / 'access.log'
            log.write_text('')
            env = os.environ | {
                'PATH': str(root) + os.pathsep + os.environ['PATH'],
                'GEUPDDONG_MONITOR_STATE_DIR': str(root / 'state'),
                'GEUPDDONG_MONITOR_WEBHOOK_ENV_FILE': str(root / 'absent.env'),
                'GEUPDDONG_NGINX_ACCESS_LOG': str(log),
                'FIXTURE_HEALTH_BODY': body,
                'FIXTURE_HTTP_FAILURE': 'true' if failed else 'false',
            }
            script = Path(__file__).resolve().parents[1] / 'scripts/service-health-monitor.sh'
            return subprocess.run(['bash', str(script)], env=env, capture_output=True, text=True, timeout=15)

    def test_old_and_new_healthy_responses(self):
        for body in ('API server is running (DB: toilet_db)', '{"status":"UP"}', '{ "status": "UP" }'):
            with self.subTest(body=body):
                result = self.run_monitor(body)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_database_failure_and_unexpected_payload_are_not_healthy(self):
        for body in ('{"status":"DOWN"}', 'API database connection failed: synthetic',
                     'prefix DB: toilet_db suffix', 'API server is running (DB: other)',
                     '{"status":"UP","detail":"unexpected"}', '{}', 'null', '[]'):
            with self.subTest(body=body):
                self.assertEqual(self.run_monitor(body).returncode, 1)

    def test_http_failure_rejects_even_an_up_body(self):
        self.assertEqual(self.run_monitor('{"status":"UP"}', failed=True).returncode, 1)


if __name__ == '__main__':
    unittest.main()
