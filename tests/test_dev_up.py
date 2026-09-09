#!/usr/bin/env python3
"""Isolated TEST DOUBLE coverage for the combined developer session."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

from scripts import dev


ROOT = Path(__file__).resolve().parents[1]
MULTI_SUPERVISOR = textwrap.dedent(
    """
    import json
    import os
    from pathlib import Path
    import sys
    from scripts.dev import ProcessSpec, supervise_components

    root = Path(sys.argv[1])
    modes = sys.argv[2].split(',')
    specs = []
    for name, mode in zip(('collector', 'query', 'dashboard'), modes):
        workdir = root / name
        workdir.mkdir()
        command = [str(root / 'missing')] if mode == 'missing' else [
            sys.executable, str(root / 'component.py'), mode, str(workdir)
        ]
        specs.append(ProcessSpec(name, command, workdir, os.environ.copy()))
    checks = json.loads(sys.argv[3])
    raise SystemExit(supervise_components(
        specs,
        http_checks=[tuple(item) for item in checks],
        stop_timeout=float(sys.argv[4]),
        http_timeout=float(sys.argv[5]),
    ))
    """
)
COMPONENT = textwrap.dedent(
    """
    # TEST DOUBLE: isolated lifecycle behavior only; no real services or data.
    import os
    from pathlib import Path
    import signal
    import sys
    import time

    mode = sys.argv[1]
    workdir = Path(sys.argv[2])

    def write(name, value):
        (workdir / name).write_text(str(value))

    if mode == 'normal':
        print('normal', flush=True)
        raise SystemExit(0)
    if mode == 'abnormal':
        write('abnormal.done', os.getpid())
        print('abnormal', flush=True)
        raise SystemExit(9)

    def stop(_signum, _frame):
        write('stopped', 'SIGTERM')
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    write('started.pid', os.getpid())
    if mode == 'finite':
        time.sleep(0.5)
        raise SystemExit(0)
    if mode == 'counter':
        count = 0
        while True:
            count += 1
            write('count', count)
            time.sleep(0.03)
    while True:
        time.sleep(0.05)
    """
)


def wait_for(path: Path, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not path.exists():
        raise AssertionError(f"timed out waiting for {path}")


def pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def unused_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class UpConfigurationTests(unittest.TestCase):
    def test_up_derives_data_and_proxy_without_cli_overrides(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            caller = Path(temporary) / "caller"
            caller.mkdir(parents=True)
            config = caller / "selected.ini"
            config.write_text("[config]\nDataDirectory=relative-raw\nFlowPath=relative-flow\n")
            parser = dev.build_parser()
            args = parser.parse_args([
                "up", "--config", "selected.ini", "--query-port", "18000", "--dashboard-port", "18101"
            ])
            environment = {"DATA_DIR": str(caller / "relative-raw"), "QUERY_URL": "http://127.0.0.1:18000"}
            with mock.patch.object(dev, "ROOT", root), \
                    mock.patch.dict(os.environ, environment, clear=True), \
                    mock.patch.object(dev.shutil, "which", return_value="/test/node"):
                specs, checks = dev.up_specs(args, parser, caller)
            self.assertEqual(specs[0].command[-1], str(config))
            self.assertEqual(specs[1].environment["DATA_DIR"], str(caller / "relative-raw"))
            self.assertEqual(specs[2].environment["QUERY_URL"], "http://127.0.0.1:18000")
            self.assertEqual(checks, [
                ("query", "http://127.0.0.1:18000/healthz"),
                ("dashboard", "http://127.0.0.1:18101/"),
            ])
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parser.parse_args(["up", "--data-dir", "forbidden"])

    def test_combined_preflight_failure_spawns_nothing(self):
        parser = dev.build_parser()
        args = parser.parse_args(["up"])
        with mock.patch.object(dev, "doctor", return_value=1), \
                mock.patch.object(dev, "up_specs") as specs, \
                mock.patch.object(dev, "supervise_components") as supervise, \
                redirect_stdout(io.StringIO()):
            result = dev.run_up(args, parser, Path("/test/caller"))
        self.assertEqual(result, 1)
        specs.assert_not_called()
        supervise.assert_not_called()

    def test_conflicting_environment_fails_before_supervision(self):
        parser = dev.build_parser()
        args = parser.parse_args(["up", "--query-port", "18000", "--dashboard-port", "18101"])
        data = Path("/test/config/raw")
        environment = {"DATA_DIR": "/conflict", "QUERY_URL": "http://127.0.0.1:9999"}
        with mock.patch.dict(os.environ, environment, clear=True), \
                mock.patch.object(dev, "collector_doctor", return_value=data), \
                mock.patch.object(dev, "query_doctor"), \
                mock.patch.object(dev, "dashboard_doctor"), \
                mock.patch.object(dev, "supervise_components") as supervise, \
                redirect_stdout(io.StringIO()):
            result = dev.run_up(args, parser, Path("/test/caller"))
        self.assertEqual(result, 1)
        supervise.assert_not_called()


class UpLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "component.py").write_text(COMPONENT)
        self.runners = []
        self.owned_groups = []

    def tearDown(self):
        for runner in self.runners:
            if runner.poll() is None:
                runner.send_signal(signal.SIGTERM)
                try:
                    runner.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    runner.kill()
                    runner.wait(timeout=2)
        for pgid in self.owned_groups:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.temporary.cleanup()

    def launch(self, modes, checks=(), stop_timeout=1.0, http_timeout=0.15):
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        runner = subprocess.Popen(
            [
                sys.executable, "-c", MULTI_SUPERVISOR, str(self.root), ",".join(modes),
                json.dumps(checks), str(stop_timeout), str(http_timeout),
            ],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.runners.append(runner)
        return runner

    def remember(self, name):
        path = self.root / name / "started.pid"
        wait_for(path)
        pid = int(path.read_text())
        self.owned_groups.append(pid)
        return pid

    def forget_stopped(self, *pids):
        for pid in pids:
            self.assertFalse(pid_exists(pid))
            self.owned_groups.remove(pid)

    def finish(self, runner, timeout=5):
        output, _ = runner.communicate(timeout=timeout)
        return runner.returncode, output

    def test_partial_spawn_failure_does_not_stop_started_companion(self):
        runner = self.launch(("missing", "graceful", "normal"))
        query_pid = self.remember("query")
        time.sleep(0.15)
        self.assertIsNone(runner.poll())
        runner.send_signal(signal.SIGTERM)
        code, output = self.finish(runner)
        self.assertEqual(code, 1)
        self.assertTrue((self.root / "query/stopped").exists())
        self.assertIn("failed to start collector", output)
        self.assertIn("dashboard exited with status 0", output)
        self.forget_stopped(query_pid)

    def test_component_failure_is_remembered_while_companion_keeps_running(self):
        runner = self.launch(("abnormal", "counter", "normal"))
        query_pid = self.remember("query")
        wait_for(self.root / "collector/abnormal.done")
        wait_for(self.root / "query/count")
        first = int((self.root / "query/count").read_text())
        time.sleep(0.2)
        second = int((self.root / "query/count").read_text())
        self.assertGreater(second, first)
        runner.send_signal(signal.SIGTERM)
        code, output = self.finish(runner)
        self.assertEqual(code, 1)
        self.assertIn("collector exited with status 9", output)
        self.assertEqual(output.count("starting collector"), 1)
        self.forget_stopped(query_pid)

    def test_signal_during_http_startup_stops_all_owned_components(self):
        checks = [
            ["query", f"http://127.0.0.1:{unused_port()}/healthz"],
            ["dashboard", f"http://127.0.0.1:{unused_port()}/"],
        ]
        runner = self.launch(("graceful", "graceful", "graceful"), checks=checks, http_timeout=5)
        pids = tuple(self.remember(name) for name in ("collector", "query", "dashboard"))
        time.sleep(0.2)
        runner.send_signal(signal.SIGHUP)
        code, output = self.finish(runner)
        self.assertEqual(code, 128 + signal.SIGHUP)
        self.assertIn("starting one bounded HTTP reachability phase", output)
        self.assertIn("HTTP startup phase interrupted", output)
        self.assertNotIn("was not reachable", output)
        self.assertIn("received SIGHUP", output)
        for name in ("collector", "query", "dashboard"):
            self.assertTrue((self.root / name / "stopped").exists())
        self.forget_stopped(*pids)

    def test_http_timeout_warns_once_without_changing_success(self):
        checks = [
            ["query", f"http://127.0.0.1:{unused_port()}/healthz"],
            ["dashboard", f"http://127.0.0.1:{unused_port()}/"],
        ]
        runner = self.launch(("finite", "finite", "finite"), checks=checks, http_timeout=0.12)
        pids = tuple(self.remember(name) for name in ("collector", "query", "dashboard"))
        code, output = self.finish(runner)
        self.assertEqual(code, 0)
        self.assertEqual(output.count("starting one bounded HTTP reachability phase"), 1)
        self.assertIn("WARNING query HTTP was not reachable", output)
        self.assertIn("WARNING dashboard HTTP was not reachable", output)
        self.assertIn("session status is unchanged", output)
        self.forget_stopped(*pids)


if __name__ == "__main__":
    unittest.main()
