import contextlib
import datetime as dt
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import test_restore_verification_refresh as fixtures

source = Path(__file__).resolve().parents[1]/'verify-and-refresh-backup.py'
spec = importlib.util.spec_from_file_location('pipeline', source)
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux private filesystem orchestration')
class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.files = fixtures.FilesystemTest()
        self.files.setUp()
        self.addCleanup(self.files.doCleanups)
        self.state = self.files.base/'state'
        self.state.mkdir(mode=0o700)
        (self.state/'receipts').mkdir(mode=0o700)

    def execute(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return pipeline.run(self.files.root, self.files.config, self.state)

    def test_pipeline_success_promotes_and_cleans_only_own_artifacts(self):
        files = self.files
        class FakeRestore:
            def __init__(self, command, **kwargs):
                self.work = Path(command[-1])
                result = files.result
                result['metadataSha256'] = fixtures.digest(files.metadata.read_bytes())
                files.write(self.work/'result.json', json.dumps(result).encode())
                files.write(self.work/'ATTEMPTED', b'synthetic')
                files.write(self.work/'private-errors.log', b'synthetic private log')
            def wait(self, timeout): return 0
            def poll(self): return 0
        with patch.object(pipeline.subprocess, 'Popen', FakeRestore):
            self.assertEqual(0, self.execute())
        self.assertIn(files.meta['sha256'], files.config.read_text())
        self.assertEqual(2, len(list((self.state/'receipts').iterdir())))
        self.assertFalse((self.state/'failed-run.json').exists())
        self.assertEqual(files.before, {p.name:p.read_bytes() for p in files.root.iterdir() if p.name!='.backup.lock'})

    def test_previous_failure_blocks_new_docker_execution(self):
        self.files.write(self.state/'failed-run.json', b'{}')
        with patch.object(pipeline.subprocess, 'Popen') as start:
            self.assertEqual(1, self.execute())
            start.assert_not_called()

    def test_no_metadata_never_falls_back_to_legacy_mtime(self):
        self.files.metadata.unlink()
        Path(str(self.files.old_path)+'.metadata.json').unlink()
        with patch.object(pipeline.subprocess, 'Popen') as start:
            self.assertEqual(1, self.execute())
            start.assert_not_called()

    def test_failure_does_not_promote_and_preserves_review_marker(self):
        class Failed:
            def __init__(self, command, **kwargs): self.work=Path(command[-1])
            def wait(self, timeout): return 1
            def poll(self): return 1
        with patch.object(pipeline.subprocess, 'Popen', Failed):
            self.assertEqual(1, self.execute())
        marker=json.loads((self.state/'failed-run.json').read_bytes())
        work=Path(marker['workDirectory'])
        self.addCleanup(work.rmdir)  # Test owns this empty temporary fixture directory.
        self.assertTrue(marker['manualReviewRequired'])
        self.assertEqual(self.files.raw_config, self.files.config.read_bytes())

    def test_restore_failure_notification_label(self):
        spec=importlib.util.spec_from_file_location('notice',source.with_name('systemd-retention-failure.py'))
        notice=importlib.util.module_from_spec(spec);spec.loader.exec_module(notice)
        event={'unit':'geupddong-backup-restore.service','invocation':'a'*32,'result':'exit-code','code':'exited','status':'1'}
        self.assertIn('백업 격리 복원 검증 실패',notice.payload(event)['content'])


if __name__=='__main__': unittest.main()
