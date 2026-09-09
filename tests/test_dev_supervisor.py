#!/usr/bin/env python3
"""Process lifecycle tests for the developer runner using only TEST DOUBLE children."""

import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

from scripts import dev


ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = textwrap.dedent(
    """
    import os
    from pathlib import Path
    import sys
    from scripts.dev import ProcessSpec, supervise_component

    workdir = Path(sys.argv[1])
    spec = ProcessSpec(
        "test-double",
        [sys.executable, str(workdir / "component.py"), sys.argv[2], str(workdir)],
        workdir,
        os.environ.copy(),
    )
    raise SystemExit(supervise_component(spec, stop_timeout=float(sys.argv[3])))
    """
)
COMPONENT = textwrap.dedent(
    """
    # TEST DOUBLE: no network, production configuration, data, flow, or manager access.
    import os
    from pathlib import Path
    import signal
    import subprocess
    import sys
    import time

    mode = sys.argv[1]
    workdir = Path(sys.argv[2])

    def write(name, value):
        (workdir / name).write_text(str(value))

    if mode == "normal":
        print("normal output", flush=True)
        raise SystemExit(0)
    if mode == "abnormal":
        print("abnormal output", flush=True)
        raise SystemExit(7)
    if mode == "leaf":
        write("descendant.pid", os.getpid())
        def leaf_stop(_signum, _frame):
            write("descendant.stopped", "SIGTERM")
            raise SystemExit(0)
        signal.signal(signal.SIGTERM, leaf_stop)
        while True:
            time.sleep(0.05)

    if mode == "ignore":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    elif mode == "graceful":
        def graceful_stop(_signum, _frame):
            write("term.received", time.monotonic())
            time.sleep(0.3)
            raise SystemExit(0)
        signal.signal(signal.SIGTERM, graceful_stop)
    elif mode == "descendant":
        child = subprocess.Popen([sys.executable, __file__, "leaf", str(workdir)])
        while not (workdir / "descendant.pid").exists():
            time.sleep(0.01)
        def parent_stop(_signum, _frame):
            child.wait(timeout=2)
            write("parent.stopped", "SIGTERM")
            raise SystemExit(0)
        signal.signal(signal.SIGTERM, parent_stop)
    write("started.pid", os.getpid())
    while True:
        time.sleep(0.05)
    """
)


def wait_for(path: Path, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not path.exists():
        raise AssertionError(f"timed out waiting for {path.name}")


def pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class SupervisorTests(unittest.TestCase):
    def test_production_stop_timeout_is_sixty_seconds(self):
        self.assertEqual(dev.STOP_TIMEOUT_SECONDS, 60.0)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workdir = Path(self.temporary.name)
        (self.workdir / "component.py").write_text(COMPONENT)
        self.runners = []
        self.owned_groups = []

    def tearDown(self):
        for runner in self.runners:
            if runner.poll() is None:
                runner.send_signal(signal.SIGTERM)
                try:
                    runner.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    runner.kill()
                    runner.wait(timeout=2)
        for pgid in self.owned_groups:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.temporary.cleanup()

    def launch(self, mode: str, stop_timeout: float = 1.0):
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        runner = subprocess.Popen(
            [sys.executable, "-c", SUPERVISOR, str(self.workdir), mode, str(stop_timeout)],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.runners.append(runner)
        return runner

    def finish(self, runner, timeout=5):
        output, _ = runner.communicate(timeout=timeout)
        return runner.returncode, output

    def remember_component_group(self):
        wait_for(self.workdir / "started.pid")
        pgid = int((self.workdir / "started.pid").read_text())
        self.owned_groups.append(pgid)
        return pgid

    def test_normal_and_abnormal_exit_status(self):
        normal = self.launch("normal")
        code, output = self.finish(normal)
        self.assertEqual(code, 0)
        self.assertIn("[test-double] normal output", output)
        self.assertIn("exited with status 0", output)

        abnormal = self.launch("abnormal")
        code, output = self.finish(abnormal)
        self.assertEqual(code, 1)
        self.assertIn("[test-double] abnormal output", output)
        self.assertIn("exited with status 7", output)

    def test_int_term_and_hup_request_normal_cleanup(self):
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=signum.name):
                for marker in ("started.pid", "term.received"):
                    (self.workdir / marker).unlink(missing_ok=True)
                runner = self.launch("graceful", stop_timeout=1.5)
                self.remember_component_group()
                runner.send_signal(signum)
                code, output = self.finish(runner)
                self.assertEqual(code, 128 + signum)
                self.assertTrue((self.workdir / "term.received").exists())
                self.assertFalse(pid_exists(self.owned_groups[-1]))
                self.owned_groups.pop()
                self.assertNotIn("SIGKILL", output)
                self.assertIn(f"received {signum.name}", output)

    def test_full_grace_period_precedes_forced_owned_cleanup(self):
        runner = self.launch("ignore", stop_timeout=0.35)
        pgid = self.remember_component_group()
        started = time.monotonic()
        runner.send_signal(signal.SIGTERM)
        code, output = self.finish(runner)
        elapsed = time.monotonic() - started
        self.assertEqual(code, 1)
        self.assertGreaterEqual(elapsed, 0.30)
        self.assertIn("did not stop within 0.35s", output)
        deadline = time.monotonic() + 2
        while pid_exists(pgid) and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(pid_exists(pgid))
        self.owned_groups.remove(pgid)

    def test_controlled_descendant_is_stopped_with_component_group(self):
        runner = self.launch("descendant", stop_timeout=1.5)
        parent = self.remember_component_group()
        wait_for(self.workdir / "descendant.pid")
        descendant = int((self.workdir / "descendant.pid").read_text())
        runner.send_signal(signal.SIGTERM)
        code, output = self.finish(runner)
        self.assertEqual(code, 128 + signal.SIGTERM)
        self.assertTrue((self.workdir / "descendant.stopped").exists())
        self.assertTrue((self.workdir / "parent.stopped").exists())
        self.assertFalse(pid_exists(parent))
        self.assertFalse(pid_exists(descendant))
        self.owned_groups.remove(parent)
        self.assertNotIn("SIGKILL", output)

    def test_external_process_is_not_signalled(self):
        external = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
        try:
            runner = self.launch("graceful", stop_timeout=1.5)
            self.remember_component_group()
            runner.send_signal(signal.SIGTERM)
            code, _ = self.finish(runner)
            self.assertEqual(code, 128 + signal.SIGTERM)
            self.assertFalse(pid_exists(self.owned_groups[-1]))
            self.owned_groups.pop()
            self.assertIsNone(external.poll())
        finally:
            external.terminate()
            external.wait(timeout=2)


if __name__ == "__main__":
    unittest.main()
