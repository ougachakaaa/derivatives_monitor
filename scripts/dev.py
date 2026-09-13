#!/usr/bin/env python3
"""Component-scoped diagnostics for the local development runner."""

from __future__ import annotations

import argparse
import errno
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler


ROOT = Path(__file__).absolute().parents[1]
COMPONENTS = ("collector", "query", "dashboard")
DEFAULT_QUERY_PORT = 8000
DEFAULT_DASHBOARD_PORT = 8101
STOP_TIMEOUT_SECONDS = 60.0
HTTP_CHECK_TIMEOUT_SECONDS = 10.0


class Report:
    def __init__(self) -> None:
        self.blockers = 0
        self.unknowns = 0

    def emit(self, level: str, component: str, message: str) -> None:
        print(f"{level:<7} [{component}] {message}", flush=True)
        if level == "ERROR":
            self.blockers += 1
        elif level == "UNKNOWN":
            self.unknowns += 1

    def pass_(self, component: str, message: str) -> None:
        self.emit("PASS", component, message)

    def warn(self, component: str, message: str) -> None:
        self.emit("WARNING", component, message)

    def error(self, component: str, message: str) -> None:
        self.emit("ERROR", component, message)

    def unknown(self, component: str, message: str) -> None:
        self.emit("UNKNOWN", component, message)


def absolute_user_path(value: str, invocation_cwd: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = invocation_cwd / path
    return Path(os.path.normpath(os.path.abspath(path)))


def parse_port(value: str, option: str) -> int:
    if not value or not value.isascii() or not value.isdecimal():
        raise argparse.ArgumentTypeError(f"{option} must be an integer in 1..65535")
    port = int(value)
    if port < 1 or port > 65535:
        raise argparse.ArgumentTypeError(f"{option} must be an integer in 1..65535")
    return port


def env_port(name: str, default: int, parser: argparse.ArgumentParser) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return parse_port(value, name)
    except argparse.ArgumentTypeError as error:
        parser.error(str(error))


def command_output(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=15,
        check=False,
    )


def check_regular_file(report: Report, component: str, path: Path, label: str, executable: bool = False) -> bool:
    if not path.is_file():
        report.error(component, f"{label} is missing or not a regular file: {path}")
        return False
    if executable and not os.access(path, os.X_OK):
        report.error(component, f"{label} is not executable: {path}")
        return False
    report.pass_(component, f"{label}: {path}")
    return True


def check_directory(report: Report, component: str, path: Path, label: str, missing_warning: bool = False) -> bool:
    if path.exists() and not path.is_dir():
        report.error(component, f"{label} is not a directory: {path}")
        return False
    if not path.exists():
        if missing_warning:
            report.warn(component, f"{label} does not exist yet; the component may create or tolerate it at runtime: {path}")
            return True
        report.error(component, f"{label} is missing: {path}")
        return False
    report.pass_(component, f"{label}: {path}")
    return True


def check_port(report: Report, component: str, port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError as error:
        if error.errno in {errno.EADDRINUSE, 48, 10048}:
            report.error(component, f"127.0.0.1:{port} is already in use")
        elif error.errno in {errno.EACCES, 10013}:
            report.error(component, f"permission denied while checking 127.0.0.1:{port}")
        else:
            report.unknown(component, f"could not check 127.0.0.1:{port} ({error.__class__.__name__})")
    else:
        report.pass_(component, f"listen port is currently available: 127.0.0.1:{port}")
    finally:
        sock.close()


def collector_paths(config: Path) -> tuple[Path, Path]:
    """Extract only orchestration paths with the Collector parser's exact line rules."""
    values: dict[str, str] = {}
    section = ""
    with config.open("r", errors="surrogateescape") as source:
        for raw_line in source:
            line = raw_line.strip(" \t\r\n")
            if not line or line[0] in "#;":
                continue
            if line[0] == "[" and line[-1] == "]":
                section = line[1:-1].strip(" \t\r\n")
                continue
            if section != "config" or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip(" \t\r\n")
            if key in {"DataDirectory", "FlowPath"}:
                values[key] = value.strip(" \t\r\n")
    base = config.parent
    data_dir = Path(values.get("DataDirectory") or "data")
    flow_dir = Path(values.get("FlowPath") or "flow")
    if not data_dir.is_absolute():
        data_dir = base / data_dir
    if not flow_dir.is_absolute():
        flow_dir = base / flow_dir
    return Path(os.path.normpath(data_dir)), Path(os.path.normpath(flow_dir))


def collector_doctor(report: Report, config: Path) -> Path | None:
    component = "collector"
    binary = ROOT / "collector/build/Release/bin/data_collector"
    binary_ready = check_regular_file(report, component, binary, "Release executable", executable=True)
    config_ready = check_regular_file(report, component, config, "configuration")
    if not binary_ready:
        report.warn(component, "build with: cmake -S collector -B collector/build/Release -DCMAKE_BUILD_TYPE=Release && cmake --build collector/build/Release -j")
    if not binary_ready or not config_ready:
        return None

    try:
        help_result = command_output([str(binary), "--help"])
    except (OSError, subprocess.TimeoutExpired) as error:
        report.error(component, f"Release executable could not be inspected ({error.__class__.__name__})")
        return None
    if help_result.returncode != 0:
        report.error(component, "Release executable failed its --help runtime check")
        return None
    report.warn(component, "Release executable is runnable but does not expose a version")

    ldd = shutil.which("ldd")
    if ldd is None:
        report.unknown(component, "ldd is unavailable; shared-library dependencies were not checked")
    else:
        try:
            ldd_result = command_output([ldd, str(binary)])
        except (OSError, subprocess.TimeoutExpired) as error:
            report.unknown(component, f"shared-library dependencies could not be checked ({error.__class__.__name__})")
        else:
            combined = ldd_result.stdout + "\n" + ldd_result.stderr
            if ldd_result.returncode != 0 or re.search(r"=>\s+not found(?:\s|$)", combined):
                report.error(component, "one or more runtime shared libraries are unresolved; run ldd on the Collector executable")
            else:
                report.pass_(component, "runtime shared libraries are resolved")

    try:
        checked = command_output([str(binary), "--config", str(config), "--check-config"])
    except (OSError, subprocess.TimeoutExpired) as error:
        report.error(component, f"configuration check could not run ({error.__class__.__name__}); no Collector output was shown")
        return None
    if checked.returncode != 0:
        report.error(component, "Collector rejected the configuration; output was redacted because it may contain credentials or source lines")
        report.warn(component, "inspect it locally with data_collector --config PATH --check-config")
        return None
    prefix = "event=config_valid "
    line = next((line for line in checked.stdout.splitlines() if line.startswith(prefix)), "")
    marker = " data_directory="
    if marker not in line:
        report.unknown(component, "Collector accepted the configuration but did not report an effective data directory")
        return None
    data_text = line.split(marker, 1)[1]
    if not data_text:
        report.unknown(component, "Collector accepted the configuration but reported an empty data directory")
        return None
    data_dir = Path(os.path.normpath(data_text))
    if not data_dir.is_absolute():
        report.unknown(component, "Collector accepted the configuration but its reported data directory was not absolute")
        return None
    try:
        parsed_data_dir, flow_dir = collector_paths(config)
    except OSError as error:
        report.unknown(component, f"effective paths could not be read after validation ({error.__class__.__name__})")
        return None
    if parsed_data_dir != data_dir:
        report.unknown(component, "Collector data path could not be reconciled with its validated output")
        return None
    report.pass_(component, "Collector accepted the existing configuration")
    check_directory(report, component, data_dir, "effective data directory", missing_warning=True)
    check_directory(report, component, flow_dir, "effective flow directory", missing_warning=True)
    return data_dir


def query_doctor(report: Report, data_dir: Path, port: int) -> None:
    component = "query"
    workdir = ROOT / "query"
    check_directory(report, component, workdir, "working directory")
    python = workdir / ".venv/bin/python"
    if check_regular_file(report, component, python, "Python environment", executable=True):
        code = (
            "import importlib.metadata as m,sys;"
            "print('.'.join(map(str,sys.version_info[:3])));"
            "print(m.version('fastapi'));print(m.version('uvicorn'))"
        )
        try:
            result = command_output([str(python), "-c", code], cwd=workdir)
        except (OSError, subprocess.TimeoutExpired) as error:
            report.error(component, f"Python dependencies could not be inspected ({error.__class__.__name__})")
        else:
            versions = result.stdout.splitlines()
            if result.returncode != 0 or len(versions) != 3:
                report.error(component, "Python environment is missing required FastAPI/Uvicorn runtime dependencies")
                report.warn(component, "install with: cd query && poetry config virtualenvs.in-project true --local && poetry sync")
            elif node_version(versions[0]) is None:
                report.error(component, "Python environment returned an unrecognized version")
            elif node_version(versions[0])[:2] != (3, 12):
                report.error(component, f"Python {versions[0]} is unsupported; Query requires Python 3.12")
            else:
                report.pass_(component, f"Python {versions[0]}, FastAPI {versions[1]}, Uvicorn {versions[2]}")
    else:
        report.warn(component, "install with: cd query && poetry config virtualenvs.in-project true --local && poetry sync")
    check_directory(report, component, data_dir, "effective data directory", missing_warning=True)
    check_port(report, component, port)


def node_version(text: str) -> tuple[int, ...] | None:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text.strip())
    return tuple(map(int, match.groups())) if match else None


def dashboard_doctor(report: Report, port: int, query_url: str) -> None:
    component = "dashboard"
    workdir = ROOT / "dashboard"
    check_directory(report, component, workdir, "working directory")
    check_regular_file(report, component, workdir / "package.json", "package manifest")
    node = shutil.which("node")
    if node is None:
        report.error(component, "Node is missing from PATH; install Linux Node 22.12+")
    else:
        try:
            result = command_output([node, "--version"], cwd=workdir)
        except (OSError, subprocess.TimeoutExpired) as error:
            report.error(component, f"Node could not be inspected ({error.__class__.__name__})")
        else:
            version = node_version(result.stdout) if result.returncode == 0 else None
            if version is None:
                report.error(component, "Node returned an unrecognized version")
            elif version < (22, 12, 0):
                report.error(component, f"Node {result.stdout.strip()} is unsupported; Dashboard requires 22.12+")
            else:
                report.pass_(component, f"Node {result.stdout.strip()}")
    vite = workdir / "node_modules/.bin/vite"
    if check_regular_file(report, component, vite, "Vite executable", executable=True):
        try:
            result = command_output([str(vite), "--version"], cwd=workdir)
        except (OSError, subprocess.TimeoutExpired) as error:
            report.error(component, f"Vite could not be inspected ({error.__class__.__name__})")
        else:
            if result.returncode != 0:
                report.error(component, "Vite executable failed its version check")
            else:
                report.pass_(component, f"Vite {result.stdout.strip()}")
    else:
        report.warn(component, "install with: cd dashboard && npm ci")
    try:
        parsed = urlsplit(query_url)
        parsed_host = parsed.hostname
        parsed_port = parsed.port
    except ValueError:
        parsed = None
        parsed_host = None
        parsed_port = None
        valid_port = False
    else:
        valid_port = True
    if parsed is None or parsed.scheme not in {"http", "https"} or not parsed_host or not valid_port:
        report.error(component, "QUERY_URL must be an absolute HTTP(S) URL; its value was not shown")
    elif parsed.username is not None or parsed.password is not None:
        report.error(component, "QUERY_URL must not contain authentication information; its value was not shown")
    else:
        host = f"[{parsed_host}]" if ":" in parsed_host else parsed_host
        safe_target = f"{parsed.scheme}://{host}" + (f":{parsed_port}" if parsed_port is not None else "")
        report.pass_(component, f"Query proxy target: {safe_target} (path/query details redacted)")
    check_port(report, component, port)


def add_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", metavar="PATH")
    parser.add_argument("--data-dir", metavar="PATH")
    parser.add_argument("--query-port", metavar="N")
    parser.add_argument("--dashboard-port", metavar="N")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dev", description="Run and diagnose repository components in a foreground development session.")
    parser.set_defaults(config=None, data_dir=None, query_port=None, dashboard_port=None)
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    up = subparsers.add_parser(
        "up",
        help="run all components or one selected component in the foreground",
        description="Run all components when COMPONENT is omitted; otherwise run the selected component.",
    )
    up.add_argument("--config", metavar="PATH")
    up.add_argument("--query-port", metavar="N")
    up.add_argument("--dashboard-port", metavar="N")
    components = up.add_subparsers(dest="component", metavar="COMPONENT")
    child = components.add_parser("collector", help="run collector in the foreground")
    child.add_argument("--config", metavar="PATH")
    child = components.add_parser("query", help="run query in the foreground")
    child.add_argument("--data-dir", metavar="PATH")
    child.add_argument("--query-port", metavar="N")
    child = components.add_parser("dashboard", help="run dashboard in the foreground")
    child.add_argument("--dashboard-port", metavar="N")
    doctor = subparsers.add_parser("doctor", help="check component-scoped local runtime prerequisites")
    doctor.add_argument("component", nargs="?", choices=COMPONENTS, help="default: all components")
    add_options(doctor)
    return parser


def reject_inapplicable(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    scope = args.component
    if scope == "collector" and any((args.data_dir, args.query_port, args.dashboard_port)):
        parser.error("doctor collector only accepts --config")
    if scope == "query" and any((args.config, args.dashboard_port)):
        parser.error("doctor query only accepts --data-dir and --query-port")
    if scope == "dashboard" and any((args.config, args.data_dir, args.query_port)):
        parser.error("doctor dashboard only accepts --dashboard-port; set QUERY_URL in the environment")
    if scope is None and args.data_dir is not None:
        parser.error("combined doctor derives the Query data directory from Collector config and does not accept --data-dir")


def reject_start_inapplicable(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.component == "collector" and any((args.data_dir, args.query_port, args.dashboard_port)):
        parser.error("up collector only accepts --config")
    if args.component == "query" and any((args.config, args.dashboard_port)):
        parser.error("up query only accepts --data-dir and --query-port")
    if args.component == "dashboard" and any((args.config, args.data_dir, args.query_port)):
        parser.error("up dashboard only accepts --dashboard-port; set QUERY_URL in the environment")


def doctor(args: argparse.Namespace, parser: argparse.ArgumentParser, invocation_cwd: Path) -> int:
    reject_inapplicable(parser, args)
    report = Report()
    scope = args.component
    config_value = args.config if args.config is not None else str(ROOT / "collector/config.ini")
    config = absolute_user_path(config_value, invocation_cwd)
    query_port = None
    if scope in (None, "query"):
        query_port = parse_port(args.query_port, "--query-port") if args.query_port is not None else env_port("QUERY_PORT", DEFAULT_QUERY_PORT, parser)
    dashboard_port = None
    if scope in (None, "dashboard"):
        dashboard_port = parse_port(args.dashboard_port, "--dashboard-port") if args.dashboard_port is not None else env_port("DASHBOARD_PORT", DEFAULT_DASHBOARD_PORT, parser)
    if scope is None and query_port == dashboard_port:
        parser.error("combined doctor requires different Query and Dashboard ports")

    collector_data: Path | None = None
    if scope in (None, "collector"):
        collector_data = collector_doctor(report, config)

    if scope in (None, "query"):
        if scope == "query":
            data_value = args.data_dir if args.data_dir is not None else os.environ.get("DATA_DIR", str(ROOT / "collector/data"))
            data_dir = absolute_user_path(data_value, invocation_cwd)
        elif collector_data is not None:
            data_dir = collector_data
            env_data = os.environ.get("DATA_DIR")
            if env_data is not None and absolute_user_path(env_data, invocation_cwd) != data_dir:
                report.error("runner", "DATA_DIR conflicts with the directory derived from Collector config; clear DATA_DIR")
        else:
            data_dir = ROOT / "collector/data"
            report.unknown("runner", "Query data directory could not be derived because Collector config validation did not succeed")
        query_doctor(report, data_dir, query_port)

    if scope in (None, "dashboard"):
        if scope == "dashboard":
            query_url = os.environ.get("QUERY_URL", f"http://127.0.0.1:{DEFAULT_QUERY_PORT}")
        else:
            query_url = f"http://127.0.0.1:{query_port}"
            if "QUERY_URL" in os.environ and os.environ["QUERY_URL"] != query_url:
                report.error("runner", "QUERY_URL conflicts with the proxy derived from the Query port; clear QUERY_URL")
        dashboard_doctor(report, dashboard_port, query_url)

    if report.blockers or report.unknowns:
        print(f"doctor failed: {report.blockers} blocking error(s), {report.unknowns} unknown check(s)")
        return 1
    print("doctor passed")
    return 0


class ProcessSpec:
    def __init__(
        self,
        name: str,
        command: list[str],
        cwd: Path,
        environment: dict[str, str],
        clean_exit_ok: bool = True,
    ) -> None:
        self.name = name
        self.command = command
        self.cwd = cwd
        self.environment = environment
        self.clean_exit_ok = clean_exit_ok


class ProcessState:
    def __init__(self, spec: ProcessSpec, process: subprocess.Popen[str], output_thread: threading.Thread) -> None:
        self.spec = spec
        self.process = process
        self.pgid = process.pid
        self.output_thread = output_thread
        self.exit_reported = False
        self.term_sent = False
        self.stop_deadline: float | None = None
        self.forced = False
        self.force_deadline: float | None = None
        self.cleanup_finished = False


def _runner_log(message: str) -> None:
    try:
        print(f"[runner] {message}", flush=True)
    except (BrokenPipeError, OSError):
        pass


def _copy_output(name: str, stream) -> None:
    try:
        for line in stream:
            try:
                print(f"[{name}] {line}", end="", flush=True)
            except (BrokenPipeError, OSError):
                # Keep draining so a closed terminal cannot block the child.
                continue
    finally:
        stream.close()


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _signal_owned_group(pgid: int, signum: int) -> bool:
    try:
        os.killpg(pgid, signum)
    except ProcessLookupError:
        return False
    except PermissionError:
        _runner_log(f"cannot signal owned process group {pgid}: permission denied")
        return True
    return True


def _spawn_component(spec: ProcessSpec) -> ProcessState | None:
    _runner_log(f"starting {spec.name} in {spec.cwd}")
    try:
        process = subprocess.Popen(
            spec.command,
            cwd=spec.cwd,
            env=spec.environment,
            stdin=None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            start_new_session=True,
        )
    except OSError as error:
        _runner_log(f"failed to start {spec.name}: {error.__class__.__name__}")
        return None
    _runner_log(f"started {spec.name} pid={process.pid} pgid={process.pid}")
    assert process.stdout is not None
    output_thread = threading.Thread(
        target=_copy_output, args=(spec.name, process.stdout), daemon=True, name=f"dev-{spec.name}-output"
    )
    output_thread.start()
    return ProcessState(spec, process, output_thread)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def _http_reachable(url: str, timeout: float) -> bool:
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(url, timeout=timeout) as response:
            return 200 <= response.status < 400
    except (HTTPError, URLError, OSError, TimeoutError):
        return False


def _startup_http_phase(
    states: list[ProcessState],
    checks: list[tuple[str, str]],
    requested_signal: list[int],
    timeout: float,
) -> None:
    if not checks or requested_signal:
        return
    _runner_log("starting one bounded HTTP reachability phase; this does not check business readiness")
    by_name = {state.spec.name: state for state in states}
    pending = dict(checks)
    deadline = time.monotonic() + timeout
    while pending and not requested_signal and time.monotonic() < deadline:
        for name, url in list(pending.items()):
            state = by_name.get(name)
            if state is None:
                _runner_log(f"WARNING {name} HTTP check skipped because its process did not start")
                pending.pop(name)
                continue
            if state.process.poll() is not None:
                _runner_log(f"WARNING {name} HTTP check stopped because its process exited")
                pending.pop(name)
                continue
            remaining = max(0.01, deadline - time.monotonic())
            if _http_reachable(url, min(0.25, remaining)):
                _runner_log(f"{name} HTTP is reachable at {url}; process ownership and business readiness are separate")
                pending.pop(name)
        if pending and not requested_signal:
            time.sleep(0.05)
    if requested_signal:
        _runner_log("HTTP startup phase interrupted by the session stop request")
        return
    for name, url in pending.items():
        _runner_log(f"WARNING {name} HTTP was not reachable at {url} during the bounded startup check; session status is unchanged")


def _begin_stop(state: ProcessState, stop_timeout: float, reason: str) -> None:
    if state.term_sent or not _group_alive(state.pgid):
        return
    _runner_log(f"{reason}; sending SIGTERM to {state.spec.name}")
    _signal_owned_group(state.pgid, signal.SIGTERM)
    state.term_sent = True
    state.stop_deadline = time.monotonic() + stop_timeout


def _cleanup_states(states: list[ProcessState], stop_timeout: float) -> bool:
    """Best-effort simultaneous cleanup used only for runner failure paths."""
    active = [state for state in states if _group_alive(state.pgid)]
    for state in active:
        _begin_stop(state, stop_timeout, "runner failure cleanup")
    deadline = time.monotonic() + stop_timeout
    while any(_group_alive(state.pgid) for state in active) and time.monotonic() < deadline:
        for state in active:
            state.process.poll()
        time.sleep(0.05)
    forced = False
    for state in active:
        state.process.poll()
        if _group_alive(state.pgid):
            forced = True
            state.forced = True
            _runner_log(f"{state.spec.name} did not stop during runner failure cleanup; sending SIGKILL")
            _signal_owned_group(state.pgid, signal.SIGKILL)
    for state in states:
        if state.process.poll() is None:
            try:
                state.process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                forced = True
    return forced


def supervise_components(
    specs: list[ProcessSpec],
    http_checks: list[tuple[str, str]] | None = None,
    stop_timeout: float = STOP_TIMEOUT_SECONDS,
    http_timeout: float = HTTP_CHECK_TIMEOUT_SECONDS,
) -> int:
    """Supervise direct component entrypoints without coupling their lifecycles."""
    requested_signal: list[int] = []

    def request_stop(signum, _frame) -> None:
        if not requested_signal:
            requested_signal.append(signum)

    handled = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    previous = {signum: signal.getsignal(signum) for signum in handled}
    for signum in handled:
        signal.signal(signum, request_stop)

    states: list[ProcessState] = []
    failed = False
    normal_finish = False
    handled_signal: int | None = None
    try:
        for spec in specs:
            if requested_signal:
                break
            state = _spawn_component(spec)
            if state is None:
                failed = True
            else:
                states.append(state)

        _startup_http_phase(states, http_checks or [], requested_signal, http_timeout)

        while True:
            now = time.monotonic()
            for state in states:
                returncode = state.process.poll()
                if returncode is not None and not state.exit_reported:
                    state.exit_reported = True
                    _runner_log(f"{state.spec.name} exited with status {returncode}")
                    if handled_signal is None and (returncode != 0 or not state.spec.clean_exit_ok):
                        failed = True
                        if returncode == 0 and not state.spec.clean_exit_ok:
                            _runner_log(f"{state.spec.name} exited unexpectedly; recording session failure")
                    if _group_alive(state.pgid):
                        _begin_stop(state, stop_timeout, f"{state.spec.name} entrypoint exited with controlled descendants remaining")

            if requested_signal and handled_signal is None:
                handled_signal = requested_signal[0]
                _runner_log(f"received {signal.Signals(handled_signal).name}; stopping all owned components")
                for state in states:
                    _begin_stop(state, stop_timeout, "user ended the development session")

            for state in states:
                state.process.poll()
                group_alive = _group_alive(state.pgid)
                if not group_alive:
                    state.cleanup_finished = True
                elif state.term_sent and not state.forced \
                        and state.stop_deadline is not None and now >= state.stop_deadline:
                    state.forced = True
                    failed = True
                    _runner_log(f"{state.spec.name} did not stop within {stop_timeout:g}s; sending SIGKILL to its owned process group")
                    _signal_owned_group(state.pgid, signal.SIGKILL)
                    state.force_deadline = now + 1.0
                elif state.forced and state.force_deadline is not None and now >= state.force_deadline:
                    state.cleanup_finished = True
                    _runner_log(f"{state.spec.name} process group still has unreaped members after SIGKILL")

            if all(state.cleanup_finished for state in states):
                break
            time.sleep(0.05)

        for state in states:
            state.process.poll()
            if not state.exit_reported:
                state.exit_reported = True
                returncode = state.process.poll()
                _runner_log(f"{state.spec.name} exited with status {returncode}")
                if handled_signal is None and (returncode not in (0, None) or not state.spec.clean_exit_ok):
                    failed = True
                    if returncode == 0 and not state.spec.clean_exit_ok:
                        _runner_log(f"{state.spec.name} exited unexpectedly; recording session failure")
            state.output_thread.join(timeout=1.0)
        normal_finish = True
        if failed:
            return 1
        if handled_signal is not None:
            return 128 + handled_signal
        return 0
    finally:
        if not normal_finish:
            _cleanup_states(states, stop_timeout)
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def supervise_component(spec: ProcessSpec, stop_timeout: float = STOP_TIMEOUT_SECONDS) -> int:
    return supervise_components([spec], stop_timeout=stop_timeout)


def query_environment(base: dict[str, str], invocation_cwd: Path) -> dict[str, str]:
    """Resolve reference paths before switching to the Query working directory."""
    environment = base.copy()
    for name in ("MARKET_CALENDAR_DIR", "SKEW_REFERENCE_DIR"):
        if name in environment:
            environment[name] = str(absolute_user_path(environment[name], invocation_cwd))
    return environment


def component_spec(args: argparse.Namespace, parser: argparse.ArgumentParser, invocation_cwd: Path) -> ProcessSpec:
    reject_start_inapplicable(parser, args)
    environment = os.environ.copy()
    if args.component == "collector":
        config_value = args.config if args.config is not None else str(ROOT / "collector/config.ini")
        config = absolute_user_path(config_value, invocation_cwd)
        return ProcessSpec(
            "collector",
            [str(ROOT / "collector/build/Release/bin/data_collector"), "--config", str(config)],
            ROOT,
            environment,
        )
    if args.component == "query":
        data_value = args.data_dir if args.data_dir is not None else os.environ.get("DATA_DIR", str(ROOT / "collector/data"))
        data_dir = absolute_user_path(data_value, invocation_cwd)
        port = parse_port(args.query_port, "--query-port") if args.query_port is not None else env_port("QUERY_PORT", DEFAULT_QUERY_PORT, parser)
        environment = query_environment(environment, invocation_cwd)
        environment["DATA_DIR"] = str(data_dir)
        return ProcessSpec(
            "query",
            [str(ROOT / "query/.venv/bin/python"), "-m", "uvicorn", "query.app:app", "--host", "127.0.0.1", "--port", str(port), "--no-proxy-headers"],
            ROOT,
            environment,
            clean_exit_ok=False,
        )
    port = parse_port(args.dashboard_port, "--dashboard-port") if args.dashboard_port is not None else env_port("DASHBOARD_PORT", DEFAULT_DASHBOARD_PORT, parser)
    environment["QUERY_URL"] = os.environ.get("QUERY_URL", f"http://127.0.0.1:{DEFAULT_QUERY_PORT}")
    node = shutil.which("node") or "node"
    return ProcessSpec(
        "dashboard",
        [node, str(ROOT / "dashboard/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", str(port), "--strictPort"],
        ROOT / "dashboard",
        environment,
        clean_exit_ok=False,
    )


def up_specs(args: argparse.Namespace, parser: argparse.ArgumentParser, invocation_cwd: Path) -> tuple[list[ProcessSpec], list[tuple[str, str]]]:
    config_value = args.config if args.config is not None else str(ROOT / "collector/config.ini")
    config = absolute_user_path(config_value, invocation_cwd)
    data_dir, _ = collector_paths(config)
    query_port = parse_port(args.query_port, "--query-port") if args.query_port is not None else env_port("QUERY_PORT", DEFAULT_QUERY_PORT, parser)
    dashboard_port = parse_port(args.dashboard_port, "--dashboard-port") if args.dashboard_port is not None else env_port("DASHBOARD_PORT", DEFAULT_DASHBOARD_PORT, parser)
    base_environment = os.environ.copy()

    collector = ProcessSpec(
        "collector",
        [str(ROOT / "collector/build/Release/bin/data_collector"), "--config", str(config)],
        ROOT,
        base_environment.copy(),
    )
    query_env = query_environment(base_environment, invocation_cwd)
    query_env["DATA_DIR"] = str(data_dir)
    query = ProcessSpec(
        "query",
        [str(ROOT / "query/.venv/bin/python"), "-m", "uvicorn", "query.app:app", "--host", "127.0.0.1", "--port", str(query_port), "--no-proxy-headers"],
        ROOT,
        query_env,
        clean_exit_ok=False,
    )
    dashboard_environment = base_environment.copy()
    dashboard_environment["QUERY_URL"] = f"http://127.0.0.1:{query_port}"
    dashboard = ProcessSpec(
        "dashboard",
        [(shutil.which("node") or "node"), str(ROOT / "dashboard/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", str(dashboard_port), "--strictPort"],
        ROOT / "dashboard",
        dashboard_environment,
        clean_exit_ok=False,
    )
    checks = [
        ("query", f"http://127.0.0.1:{query_port}/healthz"),
        ("dashboard", f"http://127.0.0.1:{dashboard_port}/"),
    ]
    return [collector, query, dashboard], checks


def run_component(args: argparse.Namespace, parser: argparse.ArgumentParser, invocation_cwd: Path) -> int:
    reject_start_inapplicable(parser, args)
    diagnostic_args = argparse.Namespace(
        component=args.component,
        config=args.config,
        data_dir=args.data_dir,
        query_port=args.query_port,
        dashboard_port=args.dashboard_port,
    )
    if doctor(diagnostic_args, parser, invocation_cwd) != 0:
        _runner_log(f"{args.component} was not started because its diagnostic failed")
        return 1
    return supervise_component(component_spec(args, parser, invocation_cwd))


def run_up(args: argparse.Namespace, parser: argparse.ArgumentParser, invocation_cwd: Path) -> int:
    diagnostic_args = argparse.Namespace(
        component=None,
        config=args.config,
        data_dir=None,
        query_port=args.query_port,
        dashboard_port=args.dashboard_port,
    )
    if doctor(diagnostic_args, parser, invocation_cwd) != 0:
        _runner_log("no components were started because the combined diagnostic failed")
        return 1
    try:
        specs, checks = up_specs(args, parser, invocation_cwd)
    except OSError as error:
        _runner_log(f"could not derive the combined component paths after validation ({error.__class__.__name__})")
        return 1
    return supervise_components(specs, http_checks=checks)


def main(argv: list[str] | None = None) -> int:
    invocation_cwd = Path.cwd()
    parser = build_parser()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] in COMPONENTS:
        parser.error(f"'{raw_argv[0]}' moved under 'up'; use ./dev up {raw_argv[0]}")
    args = parser.parse_args(raw_argv)
    if args.command == "up" and args.component is not None and raw_argv[1] != args.component:
        parser.error(f"options for up {args.component} must follow the component; use ./dev up {args.component} [options]")
    if args.command is None:
        parser.print_help()
        return 0
    try:
        if args.command == "doctor":
            return doctor(args, parser, invocation_cwd)
        if args.command == "up":
            if args.component is None:
                return run_up(args, parser, invocation_cwd)
            return run_component(args, parser, invocation_cwd)
    except argparse.ArgumentTypeError as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
