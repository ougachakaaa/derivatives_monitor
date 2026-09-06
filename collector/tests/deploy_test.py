#!/usr/bin/env python3
"""Host-script tests using a Docker CLI double; these do NOT validate Docker itself."""
import json
import os
from pathlib import Path
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

COLLECTOR = Path(__file__).resolve().parents[1]
MOCK = r'''
import json, os, pathlib, sys
a=sys.argv[1:]; log=pathlib.Path(os.environ['MOCK_LOG']); state=log.with_suffix('.state')
with log.open('a') as f: f.write(json.dumps(a)+'\n')
if a[0]=='version':
 if os.environ.get('MOCK_ENGINE_FAIL'): sys.exit(1)
 print(os.environ.get('MOCK_ARCH','linux/amd64'))
elif a[:2]==['compose','version']: print('Docker Compose version v2.test')
elif a[0]=='compose':
 op=a[5]
 if op=='ps' and state.exists(): print('test-container')
 elif op=='build' and os.environ.get('MOCK_BUILD_FAIL'): sys.exit(1)
 elif op=='up': state.write_text('running')
 elif op=='stop': state.write_text('exited')
 elif op=='logs': print('event=health accepted=10 written=5')
elif a[0]=='inspect':
 if 'project.config_files' in a[2]: print(os.environ.get('MOCK_CONFIG_FILES',os.environ['COLLECTOR_DIR']+'/compose.yaml'))
 elif '.Mounts' in a[2]: print(os.environ['COLLECTOR_DIR']+'/config.ini')
 else: print('status=running restart_count=0 last_exit_code=0')
elif a[0]=='run' and os.environ.get('MOCK_PREFLIGHT_FAIL'): sys.exit(1)
'''


class DeployTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='dm deploy test ')
        self.root = Path(self.temp.name)
        self.collector = self.root / 'collector'
        (self.collector / 'scripts').mkdir(parents=True)
        for name in ('deploy.sh', 'verify.sh'):
            shutil.copy2(COLLECTOR / 'scripts' / name, self.collector / 'scripts' / name)
        for name in ('config.example.ini', 'compose.yaml'):
            shutil.copy2(COLLECTOR / name, self.collector / name)
        bindir = self.root / 'bin'; bindir.mkdir()
        docker = bindir / 'docker'
        docker.write_text('#!' + sys.executable + '\n' + MOCK); docker.chmod(0o755)
        self.log = self.root / 'docker.jsonl'
        self.env = dict(os.environ, PATH=str(bindir) + ':' + os.environ['PATH'], MOCK_LOG=str(self.log))
        self.script = self.collector / 'scripts/deploy.sh'

    def tearDown(self):
        self.temp.cleanup()

    def run_script(self, *args, **env):
        return subprocess.run([str(self.script), *args], cwd=self.root, env=dict(self.env, **env),
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)

    def config(self, extra=''):
        path = self.collector / 'config.ini'
        path.write_text('[config]\nFrontMdAddr=tcp://127.0.0.1:1\nInstruments=IF2609\n'
                        'DataDirectory=data\nFlowPath=flow\nRunSeconds=0\n' + extra)
        return path

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def assert_no_up(self):
        self.assertFalse(any(a[0] == 'compose' and len(a) > 5 and a[5] == 'up' for a in self.calls()))

    def test_noninteractive_missing_config_and_engine_failure(self):
        result = self.run_script('up')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('首次部署需要交互终端', result.stderr)
        self.assertFalse((self.collector / 'config.ini').exists()); self.assert_no_up()
        result = self.run_script('up', MOCK_ENGINE_FAIL='1')
        self.assertIn('Docker 不可用', result.stderr)
        result = self.run_script('up', MOCK_ARCH='linux/arm64')
        self.assertIn('x86-64', result.stderr)

    def test_first_run_hidden_password_and_reuse(self):
        master, slave = pty.openpty()
        process = subprocess.Popen([str(self.script), 'up'], cwd=self.root, env=self.env,
                                   stdin=slave, stdout=slave, stderr=slave)
        os.close(slave); transcript = b''
        secret = b'secret$(touch NEVER_EXECUTE)'
        try:
            for prompt, answer in [(b'FrontMdAddr [', b''), (b'BrokerID [', b''),
                                   (b'UserID', b'demo'), (b'Password', secret),
                                   (b'Instruments', b'IF2609,IO2609-C-4000')]:
                deadline = time.monotonic() + 5
                while prompt not in transcript:
                    self.assertLess(time.monotonic(), deadline)
                    if select.select([master], [], [], .1)[0]: transcript += os.read(master, 65536)
                # Wait for the full prompt/read setup before typing into the terminal.
                time.sleep(.03); os.write(master, answer + b'\n')
            deadline = time.monotonic() + 10
            while process.poll() is None:
                self.assertLess(time.monotonic(), deadline, 'deployment test subprocess hung')
                if select.select([master], [], [], .1)[0]:
                    try: transcript += os.read(master, 65536)
                    except OSError: break
            self.assertEqual(process.wait(timeout=5), 0, transcript.decode(errors='replace'))
        finally:
            if process.poll() is None: process.kill(); process.wait()
            os.close(master)
        path = self.collector / 'config.ini'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertIn('ConnectTimeoutSeconds=120', path.read_text())
        self.assertIn(secret.decode(), path.read_text())
        self.assertNotIn(secret, transcript)
        self.assertFalse((self.root / 'NEVER_EXECUTE').exists())
        before = path.read_bytes()
        self.assertEqual(self.run_script('up').returncode, 0)
        self.assertEqual(path.read_bytes(), before)

    def test_unsafe_config_rejected_without_leaking_raw_line(self):
        for value in ('DataDirectory=/tmp/data', 'FlowPath=elsewhere', 'RunSeconds=30',
                      'CsvOutputPath=secret.csv', 'malformed_secret_line'):
            self.config(value + '\n')
            result = self.run_script('up')
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('malformed_secret_line', result.stdout + result.stderr)
            self.assert_no_up()

    def test_config_never_executed_and_preflight_order(self):
        marker = self.root / 'executed'
        path = self.config(f'Password=$(touch "{marker}")\n')
        before = path.read_bytes()
        result = self.run_script('up')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists()); self.assertEqual(path.read_bytes(), before)
        calls = self.calls()
        build = next(i for i, a in enumerate(calls) if a[0]=='compose' and len(a)>5 and a[5]=='build')
        preflight = next(i for i, a in enumerate(calls) if a[0]=='run')
        up = next(i for i, a in enumerate(calls) if a[0]=='compose' and len(a)>5 and a[5]=='up')
        self.assertLess(build, preflight); self.assertLess(preflight, up)
        self.assertIn(f'type=bind,src={path},dst=/app/config.ini,readonly', calls[preflight])

    def test_build_and_permission_failures_preserve_existing_service(self):
        self.config(); self.log.with_suffix('.state').write_text('running')
        for variable in ('MOCK_BUILD_FAIL', 'MOCK_PREFLIGHT_FAIL'):
            result = self.run_script('up', **{variable: '1'})
            self.assertNotEqual(result.returncode, 0); self.assert_no_up()
            self.assertEqual(self.log.with_suffix('.state').read_text(), 'running')

    def test_another_checkout_not_replaced(self):
        self.config(); self.log.with_suffix('.state').write_text('running')
        result = self.run_script('up', MOCK_CONFIG_FILES='/different/compose.yaml')
        self.assertNotEqual(result.returncode, 0); self.assert_no_up()

    def test_verify_missing_and_readonly_mount(self):
        result = self.run_script('verify', '20260907')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.collector / 'data/20260907.sqlite').exists())
        data = self.collector / 'data'; data.mkdir(); (data / '20260907.sqlite').touch()
        self.assertEqual(self.run_script('verify', '20260907').returncode, 0)
        call = self.calls()[-1]
        self.assertIn('--read-only', call)
        self.assertIn(f'type=bind,src={data},dst=/app/data,readonly', call)
        self.assertEqual(self.run_script('verify', '../bad').returncode, 2)

    def test_logs_status_stop_do_not_build(self):
        self.config(); self.log.with_suffix('.state').write_text('running')
        for command in ('logs', 'status', 'stop'):
            self.assertEqual(self.run_script(command).returncode, 0)
        self.assertFalse(any('build' in a for a in self.calls()))
        self.assertEqual(self.log.with_suffix('.state').read_text(), 'exited')


if __name__ == '__main__':
    unittest.main(verbosity=2)
