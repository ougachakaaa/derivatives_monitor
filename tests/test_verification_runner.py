"""Ensure evidence cannot turn missing, skipped, failing or timed-out checks green."""
from pathlib import Path
import os
import signal
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run import run_step, step


class EvidenceTest(unittest.TestCase):
    def execute(self, code, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_step(step('fixture', [sys.executable, '-c', code], **kwargs), Path(tmp))
            if 'log' in result:
                self.assertTrue((Path(tmp) / result['log']).exists())
                self.assertEqual(len(result['log_sha256']), 64)
            return result

    def test_pass_and_nonzero(self):
        self.assertEqual(self.execute("print('fixture passed')")['status'], 'PASS')
        result = self.execute('raise SystemExit(7)')
        self.assertEqual((result['status'], result['exit_code']), ('FAIL', 7))

    def test_skipped_success_is_not_pass(self):
        for text in ('OK (skipped=1)', 'Docker test NOT RUN.', '1 skipped',
                     'Ran 0 tests in 0.000s', 'No tests were found!!!'):
            with self.subTest(text=text):
                self.assertEqual(self.execute('print(' + repr(text) + ')')['status'], 'NOT_RUN')

    def test_missing_and_timeout(self):
        result = self.execute('print(1)', requires=['/nonexistent/dm-verification-command'])
        self.assertEqual(result['status'], 'NOT_RUN')
        result = self.execute('import time; time.sleep(5)', timeout=.1)
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('TimeoutError', result['reason'])

    def test_timeout_cleans_runner_controlled_child_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'child.pid'
            child = (
                "import os,signal,time; "
                f"open({str(marker)!r},'w').write(str(os.getpid())); "
                "signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(SystemExit(0))); "
                "time.sleep(30)"
            )
            supervisor = (
                "import os,sys; from pathlib import Path; "
                "from scripts.dev import ProcessSpec, supervise_component; "
                f"spec=ProcessSpec('fixture',[sys.executable,'-c',{child!r}],Path.cwd(),os.environ.copy()); "
                "raise SystemExit(supervise_component(spec,stop_timeout=1))"
            )
            result = run_step(step('nested-timeout', [sys.executable, '-c', supervisor],
                                   cwd=Path(__file__).resolve().parents[1], timeout=.5), Path(tmp))
            self.assertEqual(result['status'], 'FAIL')
            self.assertIn('TimeoutError', result['reason'])
            self.assertTrue(marker.exists())
            pid = int(marker.read_text())
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(.05)
            else:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.fail(f'runner-controlled child {pid} survived verification timeout')

    def test_synthetic_environment_is_not_inherited(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {'DM_TEST_SCENARIO': 'shfe-night', 'KEEP_RUNNING': '1'}):
            self.assertEqual(self.execute("import os; assert 'DM_TEST_SCENARIO' not in os.environ; assert os.environ['KEEP_RUNNING']=='0'")['status'], 'PASS')

if __name__ == '__main__':
    unittest.main()
