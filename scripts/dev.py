#!/usr/bin/env python3
"""Component-scoped diagnostics for the local development runner."""

from __future__ import annotations

import argparse
import errno
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
from urllib.parse import urlsplit


ROOT = Path(__file__).absolute().parents[1]
COMPONENTS = ("collector", "query", "dashboard")
DEFAULT_QUERY_PORT = 8000
DEFAULT_DASHBOARD_PORT = 8101


class Report:
    def __init__(self) -> None:
        self.blockers = 0
        self.unknowns = 0

    def emit(self, level: str, component: str, message: str) -> None:
        print(f"{level:<7} [{component}] {message}")
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
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    for command in COMPONENTS + ("up",):
        child = subparsers.add_parser(command, help=f"run {command} (available in a later implementation task)")
        add_options(child)
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


def main(argv: list[str] | None = None) -> int:
    invocation_cwd = Path.cwd()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command != "doctor":
        parser.error(f"{args.command} is reserved but is not implemented in task 2; use doctor")
    try:
        return doctor(args, parser, invocation_cwd)
    except argparse.ArgumentTypeError as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
