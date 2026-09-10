#!/usr/bin/env python3
"""Isolated runner diagnostics and entrypoint tests (all fixtures are TEST DOUBLE)."""

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import dev


def completed(command, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


class DevDoctorTests(unittest.TestCase):
    def run_main(self, argv, *, cwd, environ=None):
        out = io.StringIO()
        err = io.StringIO()
        environment = {} if environ is None else environ
        with mock.patch.dict(os.environ, environment, clear=True), \
                mock.patch.object(Path, "cwd", return_value=cwd), \
                redirect_stdout(out), redirect_stderr(err):
            try:
                result = dev.main(argv)
            except SystemExit as error:
                result = error.code
        return result, out.getvalue(), err.getvalue()

    def make_file(self, root, relative, executable=False):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("TEST DOUBLE\n")
        if executable:
            path.chmod(0o755)
        return path

    def test_help_lists_commands_and_up_help(self):
        with tempfile.TemporaryDirectory() as temporary:
            cwd = Path(temporary)
            code, output, _ = self.run_main(["--help"], cwd=cwd)
            self.assertEqual(code, 0)
            for command in ("up", "doctor"):
                self.assertIn(command, output)
            self.assertIn("run all components or one selected component in the foreground", output)
            self.assertNotIn("available in a later implementation task", output)
            code, output, error = self.run_main(["up", "--help"], cwd=cwd)
            self.assertEqual((code, error), (0, ""))
            self.assertIn("--config", output)
            self.assertNotIn("--data-dir", output)
            self.assertIn("Run all components when COMPONENT is omitted", output)
            self.assertNotIn("available in a later implementation task", output)
            for component, options in (
                ("collector", ("--config",)),
                ("query", ("--data-dir", "--query-port")),
                ("dashboard", ("--dashboard-port",)),
            ):
                code, output, error = self.run_main(["up", component, "--help"], cwd=cwd)
                self.assertEqual((code, error), (0, ""))
                self.assertIn(f"usage: dev up {component}", output)
                for option in options:
                    self.assertIn(option, output)

    def test_retired_component_commands_return_usage_error_without_dispatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            cwd = Path(temporary)
            for component in dev.COMPONENTS:
                for suffix in ((), ("--help",), ("--config", "TEST_DOUBLE")):
                    with self.subTest(component=component, suffix=suffix), \
                            mock.patch.object(dev, "doctor") as doctor, \
                            mock.patch.object(dev, "supervise_component") as supervise:
                        code, _, error = self.run_main([component, *suffix], cwd=cwd)
                        self.assertEqual(code, 2)
                        self.assertIn(f"./dev up {component}", error)
                        doctor.assert_not_called()
                        supervise.assert_not_called()

    def test_up_dispatches_combined_or_one_component(self):
        with tempfile.TemporaryDirectory() as temporary:
            cwd = Path(temporary)
            with mock.patch.object(dev, "run_up", return_value=17) as run_up, \
                    mock.patch.object(dev, "run_component", return_value=19) as run_component:
                self.assertEqual(dev.main(["up"]), 17)
                run_up.assert_called_once()
                run_component.assert_not_called()

                self.assertEqual(dev.main(["up", "query", "--query-port", "18000"]), 19)
                run_component.assert_called_once()
                self.assertEqual(run_component.call_args.args[0].component, "query")

    def test_up_component_argument_boundaries_are_usage_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            cwd = Path(temporary)
            cases = (
                ["up", "--config", "TEST_DOUBLE.ini", "collector"],
                ["up", "collector", "--query-port", "18000"],
                ["up", "query", "--config", "TEST_DOUBLE.ini"],
                ["up", "dashboard", "--query-port", "18000"],
                ["up", "all"],
                ["up", "collector", "query"],
            )
            for argv in cases:
                with self.subTest(argv=argv), \
                        mock.patch.object(dev, "run_up") as run_up, \
                        mock.patch.object(dev, "run_component") as run_component:
                    code, _, _ = self.run_main(argv, cwd=cwd)
                    self.assertEqual(code, 2)
                    run_up.assert_not_called()
                    run_component.assert_not_called()

    def test_component_specs_use_direct_existing_entrypoints(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            caller = Path(temporary) / "caller"
            caller.mkdir(parents=True)
            parser = dev.build_parser()
            environment = {
                "DATA_DIR": "wrong-data",
                "QUERY_PORT": "9999",
                "QUERY_URL": "http://127.0.0.1:17777",
                "DASHBOARD_PORT": "9998",
            }
            cases = (
                (
                    ["up", "collector", "--config", "selected.ini"],
                    "collector",
                    [str(root / "collector/build/Release/bin/data_collector"), "--config", str(caller / "selected.ini")],
                    root,
                ),
                (
                    ["up", "query", "--data-dir", "raw", "--query-port", "18000"],
                    "query",
                    [str(root / "query/.venv/bin/python"), "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "18000", "--no-proxy-headers"],
                    root / "query",
                ),
                (
                    ["up", "dashboard", "--dashboard-port", "18101"],
                    "dashboard",
                    ["/test/node", str(root / "dashboard/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", "18101", "--strictPort"],
                    root / "dashboard",
                ),
            )
            with mock.patch.object(dev, "ROOT", root), \
                    mock.patch.dict(os.environ, environment, clear=True), \
                    mock.patch.object(dev.shutil, "which", return_value="/test/node"):
                for argv, name, command, workdir in cases:
                    with self.subTest(component=name):
                        spec = dev.component_spec(parser.parse_args(argv), parser, caller)
                        self.assertEqual(spec.name, name)
                        self.assertEqual(spec.command, command)
                        self.assertEqual(spec.cwd, workdir)
                        if name == "query":
                            self.assertEqual(spec.environment["DATA_DIR"], str(caller / "raw"))
                        if name == "dashboard":
                            self.assertEqual(spec.environment["QUERY_URL"], environment["QUERY_URL"])

    def test_failed_component_diagnostic_prevents_spawn(self):
        parser = dev.build_parser()
        args = parser.parse_args(["up", "collector"])
        with mock.patch.object(dev, "doctor", return_value=1), \
                mock.patch.object(dev, "supervise_component") as supervise, \
                redirect_stdout(io.StringIO()):
            code = dev.run_component(args, parser, Path("/test/caller"))
        self.assertEqual(code, 1)
        supervise.assert_not_called()

    def test_spawn_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            spec = dev.ProcessSpec(
                "test-double",
                [str(Path(temporary) / "missing-entrypoint")],
                Path(temporary),
                os.environ.copy(),
            )
            output = io.StringIO()
            with redirect_stdout(output):
                code = dev.supervise_component(spec, stop_timeout=0.1)
            self.assertEqual(code, 1)
            self.assertIn("failed to start test-double", output.getvalue())

    def test_query_diagnostic_does_not_require_other_components(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            python = self.make_file(root, "query/.venv/bin/python", executable=True)
            data = root / "input"
            data.mkdir()

            def run(command, cwd=None):
                self.assertEqual(command[0], str(python))
                return completed(command, stdout="3.12.7\n0.135.0\n0.41.0\n")

            with mock.patch.object(dev, "ROOT", root), mock.patch.object(dev, "command_output", side_effect=run):
                code, output, error = self.run_main(
                    ["doctor", "query", "--data-dir", str(data), "--query-port", "32119"],
                    cwd=root,
                    environ={
                        "DATA_DIR": str(root / "wrong"),
                        "QUERY_PORT": "not-a-port",
                        "DASHBOARD_PORT": "not-a-port",
                    },
                )
            self.assertEqual((code, error), (0, ""))
            self.assertIn("doctor passed", output)
            self.assertNotIn("collector", output)
            self.assertNotIn("dashboard", output)

    def test_collector_diagnostic_ignores_other_component_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = self.make_file(root, "collector/build/Release/bin/data_collector", executable=True)
            config = self.make_file(root, "collector/config.ini")
            data = root / "collector/data"
            flow = root / "collector/flow"

            def run(command, cwd=None):
                if command == [str(binary), "--help"]:
                    return completed(command, stdout="Usage\n")
                if command[0] == "/usr/bin/ldd":
                    return completed(command, stdout="all resolved\n")
                return completed(command, stdout=f"event=config_valid instruments=1 data_directory={data}\n")

            with mock.patch.object(dev, "ROOT", root), \
                    mock.patch.object(dev.shutil, "which", return_value="/usr/bin/ldd"), \
                    mock.patch.object(dev, "command_output", side_effect=run):
                code, output, error = self.run_main(
                    ["doctor", "collector"], cwd=root,
                    environ={"QUERY_PORT": "bad", "DASHBOARD_PORT": "bad", "DATA_DIR": "ignored"},
                )
            self.assertEqual((code, error), (0, ""))
            self.assertIn(str(data), output)
            self.assertIn(str(flow), output)

    def test_dashboard_diagnostic_does_not_require_other_components(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_file(root, "dashboard/package.json")
            vite = self.make_file(root, "dashboard/node_modules/.bin/vite", executable=True)

            def run(command, cwd=None):
                if command == ["/usr/bin/node", "--version"]:
                    return completed(command, stdout="v22.12.0\n")
                self.assertEqual(command, [str(vite), "--version"])
                return completed(command, stdout="vite/7.3.0 linux-x64 node-v22.12.0\n")

            with mock.patch.object(dev, "ROOT", root), \
                    mock.patch.object(dev.shutil, "which", return_value="/usr/bin/node"), \
                    mock.patch.object(dev, "command_output", side_effect=run):
                code, output, error = self.run_main(
                    ["doctor", "dashboard", "--dashboard-port", "32118"], cwd=root,
                    environ={"DATA_DIR": "ignored", "QUERY_PORT": "bad"},
                )
            self.assertEqual((code, error), (0, ""))
            self.assertIn("doctor passed", output)
            self.assertNotIn("collector", output)
            self.assertNotIn("[query]", output)

    def test_dashboard_redacts_authenticated_proxy_url(self):
        secret = "do-not-leak"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_file(root, "dashboard/package.json")
            vite = self.make_file(root, "dashboard/node_modules/.bin/vite", executable=True)

            def run(command, cwd=None):
                if command == ["/usr/bin/node", "--version"]:
                    return completed(command, stdout="v22.12.0\n")
                return completed([str(vite), "--version"], stdout="vite/7.3.0 linux-x64 node-v22.12.0\n")

            with mock.patch.object(dev, "ROOT", root), \
                    mock.patch.object(dev.shutil, "which", return_value="/usr/bin/node"), \
                    mock.patch.object(dev, "command_output", side_effect=run):
                code, output, error = self.run_main(
                    ["doctor", "dashboard", "--dashboard-port", "32116"], cwd=root,
                    environ={"QUERY_URL": f"http://user:{secret}@127.0.0.1:8000/private?token={secret}"},
                )
            self.assertEqual(code, 1)
            self.assertIn("must not contain authentication", output)
            self.assertNotIn(secret, output + error)

    def test_collector_relative_paths_use_selected_symlink_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = self.make_file(root, "elsewhere/real.ini")
            target.write_text("[config]\nDataDirectory=raw\nFlowPath=state\n")
            selected = root / "selected/config.ini"
            selected.parent.mkdir()
            selected.symlink_to(target)
            data, flow = dev.collector_paths(selected)
            self.assertEqual(data, selected.parent / "raw")
            self.assertEqual(flow, selected.parent / "state")

    def test_relative_data_path_uses_invocation_directory_and_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            caller = Path(temporary) / "caller"
            caller.mkdir()
            self.make_file(root, "query/.venv/bin/python", executable=True)
            bad_path = caller / "raw"
            bad_path.write_text("TEST DOUBLE, not a directory")
            with mock.patch.object(dev, "ROOT", root), mock.patch.object(
                dev, "command_output", return_value=completed([], stdout="3.12.1\n0.135.0\n0.41.0\n")
            ):
                code, output, _ = self.run_main(
                    ["doctor", "query", "--data-dir", "raw", "--query-port", "32120"], cwd=caller
                )
            self.assertEqual(code, 1)
            self.assertIn(str(bad_path), output)
            self.assertIn("not a directory", output)

    def test_collector_config_failure_redacts_all_subprocess_output(self):
        secret = "Password=do-not-leak"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = self.make_file(root, "collector/build/Release/bin/data_collector", executable=True)
            config = self.make_file(root, "collector/config.ini")

            def run(command, cwd=None):
                if command[-1] == "--help":
                    return completed(command, stdout="Usage: data_collector\n")
                if command[0] == "/usr/bin/ldd":
                    return completed(command, stdout="libc.so => /lib/libc.so\n")
                self.assertEqual(command, [str(binary), "--config", str(config), "--check-config"])
                return completed(command, 1, stdout=secret, stderr=f"bad source line: {secret}")

            with mock.patch.object(dev, "ROOT", root), \
                    mock.patch.object(dev.shutil, "which", return_value="/usr/bin/ldd"), \
                    mock.patch.object(dev, "command_output", side_effect=run):
                code, output, error = self.run_main(["doctor", "collector"], cwd=root)
            self.assertEqual(code, 1)
            self.assertNotIn(secret, output + error)
            self.assertIn("output was redacted", output)

    def test_invalid_and_occupied_ports_are_blocking(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_file(root, "query/.venv/bin/python", executable=True)
            with mock.patch.object(dev, "ROOT", root):
                code, _, error = self.run_main(
                    ["doctor", "query", "--query-port", "0"], cwd=root
                )
            self.assertEqual(code, 2)
            self.assertIn("1..65535", error)

            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            try:
                with mock.patch.object(dev, "ROOT", root), mock.patch.object(
                    dev, "command_output", return_value=completed([], stdout="3.12.1\n0.135.0\n0.41.0\n")
                ):
                    code, output, _ = self.run_main(
                        ["doctor", "query", "--query-port", str(port)], cwd=root
                    )
            finally:
                listener.close()
            self.assertEqual(code, 1)
            self.assertIn("already in use", output)

    def test_combined_diagnostic_rejects_derived_environment_conflicts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = self.make_file(root, "collector/build/Release/bin/data_collector", executable=True)
            config = self.make_file(root, "collector/config.ini")
            python = self.make_file(root, "query/.venv/bin/python", executable=True)
            self.make_file(root, "dashboard/package.json")
            vite = self.make_file(root, "dashboard/node_modules/.bin/vite", executable=True)
            data = root / "collector/data"
            data.mkdir(parents=True)

            def run(command, cwd=None):
                if command == [str(binary), "--help"]:
                    return completed(command, stdout="Usage\n")
                if command[0] == "/usr/bin/ldd":
                    return completed(command, stdout="all resolved\n")
                if command == [str(binary), "--config", str(config), "--check-config"]:
                    return completed(command, stdout=f"event=config_valid instruments=1 data_directory={data}\n")
                if command[0] == str(python):
                    return completed(command, stdout="3.12.1\n0.135.0\n0.41.0\n")
                if command == ["/usr/bin/node", "--version"]:
                    return completed(command, stdout="v22.12.0\n")
                if command == [str(vite), "--version"]:
                    return completed(command, stdout="vite/7.3.0 linux-x64 node-v22.12.0\n")
                self.fail(f"unexpected command: {command}")

            environment = {"DATA_DIR": str(root / "other"), "QUERY_URL": "http://127.0.0.1:9999"}
            before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            with mock.patch.object(dev, "ROOT", root), \
                    mock.patch.object(dev.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), \
                    mock.patch.object(dev, "command_output", side_effect=run):
                code, output, _ = self.run_main(["doctor"], cwd=root, environ=environment)
            after = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            self.assertEqual(code, 1)
            self.assertEqual(before, after)
            self.assertIn("DATA_DIR conflicts", output)
            self.assertIn("QUERY_URL conflicts", output)

    def test_combined_diagnostic_rejects_equal_ports_before_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(dev, "ROOT", root):
                code, _, error = self.run_main(
                    ["doctor", "--query-port", "32117", "--dashboard-port", "32117"], cwd=root
                )
            self.assertEqual(code, 2)
            self.assertIn("different Query and Dashboard ports", error)

    def test_diagnostic_has_no_persistent_writes_or_manager_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_file(root, "query/.venv/bin/python", executable=True)
            before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            calls = []

            def run(command, cwd=None):
                calls.append(command)
                return completed(command, stdout="3.12.2\n0.135.0\n0.41.0\n")

            with mock.patch.object(dev, "ROOT", root), mock.patch.object(dev, "command_output", side_effect=run):
                code, _, _ = self.run_main(
                    ["doctor", "query", "--data-dir", "missing-data", "--query-port", "32121"], cwd=root
                )
            after = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            self.assertEqual(code, 0)
            self.assertEqual(before, after)
            flat = " ".join(part for call in calls for part in call)
            self.assertNotIn("systemctl", flat)
            self.assertNotIn("docker", flat)
            self.assertNotIn("native", flat)
            self.assertFalse((root / "collector/data").exists())
            self.assertFalse((root / "collector/flow").exists())


if __name__ == "__main__":
    unittest.main()
