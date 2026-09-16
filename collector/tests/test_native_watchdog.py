"""TEST DOUBLE: native liveness, process ownership and deployment policy."""
from contextlib import closing
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from collector.scripts import native, native_watchdog as guard
from data_provider.tests.runtime_fixture import write_runtime, update_runtime


def wait(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.02)
    raise AssertionError('TEST DOUBLE condition timed out')


def alive(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().split()[2] != 'Z'
    except FileNotFoundError:
        return False


class LivenessTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='TEST DOUBLE health ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1_800_000_000_000_000
        self.database = write_runtime(self.root, {'updated_us': self.now})
        bindir = self.root / 'bin'
        bindir.mkdir()
        date = bindir / 'date'
        date.write_text(f'#!/bin/sh\necho {self.now}\n')
        date.chmod(0o755)
        self.env = dict(os.environ, PATH=str(bindir) + ':' + os.environ['PATH'])

    def check(self, reason=None, *args):
        before = self.database.read_bytes() if self.database.exists() else None
        result = subprocess.run(['sh', str(guard.HEALTHCHECK), str(self.database), *map(str, args)],
                                env=self.env, capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode == 0, reason is None, result.stderr)
        if reason:
            self.assertIn(reason, result.stderr)
        if before is not None:
            self.assertEqual(self.database.read_bytes(), before)
        return result

    def heartbeat(self, age):
        update_runtime(self.root, 'UPDATE current_status SET heartbeat_us=?,updated_us=?',
                       (self.now - age, self.now - age))

    def test_exact_liveness_boundaries_and_identity(self):
        self.assertEqual(self.check().stdout, '')
        self.assertEqual(self.check(None, self.now, 'a' * 32).stdout.strip(), 'a' * 32)
        self.check('runtime_previous_process', self.now + 1)
        self.check('runtime_run_changed', self.now, 'b' * 32)
        for age, reason in [(0, None), (10_000_000, None), (10_000_001, 'heartbeat_stale'), (-1, 'heartbeat_future')]:
            self.heartbeat(age)
            self.check(reason)

    def test_session_facts_do_not_change_liveness(self):
        for state, connected, logged_in, subscribed, failed in [
                ('starting', 0, 0, 0, 0), ('starting', 1, 0, 0, 0),
                ('running', 0, 0, 0, 0), ('running', 1, 1, 0, 1)]:
            update_runtime(self.root, 'UPDATE current_status SET process_state=?,connected=?,logged_in=?,subscribed_count=?,subscription_failed=?',
                           (state, connected, logged_in, subscribed, failed))
            self.check()
        update_runtime(self.root, "UPDATE current_status SET process_state='stopped'")
        self.check('runtime_unavailable')

    def test_missing_corrupt_schema_and_symlinks(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('CREATE TABLE unexpected(value TEXT)')
        self.check('runtime_schema')
        self.database.write_text('TEST DOUBLE corrupt SQLite')
        self.check('runtime_unreadable')
        self.database.unlink()
        self.check('runtime_missing_or_symlink')
        self.assertFalse(self.database.exists())
        self.database.symlink_to(self.root / 'missing')
        self.check('runtime_missing_or_symlink')
        self.database.unlink()
        write_runtime(self.root, {'updated_us': self.now})
        self.database.with_name(self.database.name + '-journal').symlink_to(self.root / 'missing')
        self.check('runtime_sidecar_symlink')

    def test_lock_is_bounded_and_no_database_mutation(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('BEGIN EXCLUSIVE')
            # Opening/closing another fd in this process would release SQLite's POSIX locks.
            result = subprocess.run(['sh', str(guard.HEALTHCHECK), str(self.database)],
                                    env=self.env, capture_output=True, text=True, timeout=3)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('runtime_unreadable', result.stderr)
            db.rollback()


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='TEST DOUBLE guard ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.checker = self.root / 'check.sh'
        self.checker.write_text('#!/bin/sh\necho aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n')

    def start(self, code, **kwargs):
        child_script = self.root / 'child.py'
        child_script.write_text('import os,signal,time\n'
                                f'open({str(self.root / "pid")!r},"w").write(str(os.getpid()))\n' + code)
        settings = dict(interval=.02, timeout=.15, startup_grace=.2, stop_grace=.15, checker=str(self.checker))
        settings.update(kwargs)
        call = ('from collector.scripts.native_watchdog import supervise; '
                f'raise SystemExit(supervise({[sys.executable, str(child_script)]!r}, '
                f'{str(self.root / "runtime.sqlite")!r}, **{settings!r}))')
        log = (self.root / 'log').open('w')
        self.addCleanup(log.close)
        process = subprocess.Popen([sys.executable, '-c', call], cwd=ROOT, stdout=log, stderr=log)
        def cleanup():
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=3)
        self.addCleanup(cleanup)
        wait(lambda: (self.root / 'pid').exists() or process.poll() is not None)
        return process

    def events(self):
        return [json.loads(line) for line in (self.root / 'log').read_text().splitlines()]

    def test_failure_terminates_and_reaps_child(self):
        p = self.start('time.sleep(30)\n', startup_grace=30)
        wait(lambda: any(e['event'] == 'collector_run_bound' for e in self.events()))
        self.checker.write_text('#!/bin/sh\necho heartbeat_stale >&2\nexit 1\n')
        self.assertEqual(p.wait(timeout=3), 1)
        pid = int((self.root / 'pid').read_text())
        self.assertFalse(alive(pid))
        self.assertTrue(any(e.get('reason') == 'heartbeat_stale' for e in self.events()))

    def test_startup_grace_and_sigkill(self):
        self.checker.write_text('#!/bin/sh\nexit 1\n')
        started = time.monotonic()
        p = self.start('signal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(30)\n')
        self.assertEqual(p.wait(timeout=3), 1)
        self.assertGreaterEqual(time.monotonic() - started, .35)
        self.assertTrue(any(e['event'] == 'collector_force_kill' for e in self.events()))
        self.assertFalse(alive(int((self.root / 'pid').read_text())))

    def test_stop_during_probe_cleans_probe_descendants_and_collector(self):
        probe_pid = self.root / 'probe-pid'
        self.checker.write_text(f'#!/bin/sh\nsleep 30 &\necho $! > "{probe_pid}"\nwait\n')
        p = self.start('time.sleep(30)\n', timeout=2)
        wait(probe_pid.exists)
        p.terminate()
        self.assertEqual(p.wait(timeout=3), 0)
        wait(lambda: not alive(int(probe_pid.read_text())))
        self.assertFalse(alive(int((self.root / 'pid').read_text())))

    def test_probe_timeout_cleans_entire_pipeline(self):
        pid = self.root / 'probe-pid'
        self.checker.write_text(f'#!/bin/sh\nsleep 30 &\necho $! > "{pid}"\nwait\n')
        value, reason = guard.probe('unused', 0, None, threading.Event(), timeout=.15, checker=self.checker)
        self.assertEqual((value, reason), (None, 'probe_timeout'))
        wait(lambda: not alive(int(pid.read_text())))

    def test_unexpected_checker_failure_still_cleans_child(self):
        p = self.start('time.sleep(30)\n', checker='/TEST-DOUBLE-missing-checker')
        self.assertEqual(p.wait(timeout=3), 1)
        self.assertFalse(alive(int((self.root / 'pid').read_text())))


class UnitTest(unittest.TestCase):
    def test_collector_policy_and_escaped_paths(self):
        unit = native.collector_unit('/tmp/TEST DOUBLE/a%/collector', '/usr/bin/python3',
                                     '/tmp/TEST DOUBLE/config.ini', '/tmp/TEST DOUBLE/data', '/tmp/TEST DOUBLE')
        for text in ['Restart=always\n', 'RestartSec=10\n', 'TimeoutStopSec=60\n',
                     'StartLimitIntervalSec=0\n', 'KillMode=control-group\n', 'SendSIGKILL=yes\n',
                     'FinalKillSignal=SIGKILL\n', 'native_watchdog.py', 'a%%/collector']:
            self.assertIn(text, unit)
        self.assertNotIn('ExecStartPre=', unit)
        self.assertNotIn('universe.py', unit)
        self.assertEqual((guard.CHECK_INTERVAL, guard.CHECK_TIMEOUT, guard.STARTUP_GRACE, guard.STOP_GRACE),
                         (1, 2, 15, 60))


if __name__ == '__main__':
    unittest.main(verbosity=2)
