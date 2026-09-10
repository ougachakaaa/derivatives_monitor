#!/usr/bin/env python3
"""Actual ./dev native chain with a TEST DOUBLE CTP SDK and temporary state only."""

import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import tempfile
import time
from urllib.error import URLError
from urllib.request import build_opener, ProxyHandler


ROOT = Path(__file__).resolve().parents[1]
DAY = "20260907"


def unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait(check, description: str, seconds: float = 20):
    deadline = time.monotonic() + seconds
    last_error = None
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (OSError, ValueError, KeyError, sqlite3.Error, URLError) as error:
            last_error = error
        time.sleep(0.1)
    suffix = f" ({type(last_error).__name__})" if last_error is not None else ""
    raise AssertionError(f"Timed out: {description}{suffix}")


def json_get(base: str, path: str):
    opener = build_opener(ProxyHandler({}))
    with opener.open(base + path, timeout=3) as response:
        return json.load(response)


def row_count(data: Path, day: str = DAY) -> int:
    database = data / f"{day}.sqlite"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=2) as connection:
        return connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]


def run_count(data: Path, day: str = DAY) -> int:
    database = data / f"{day}.sqlite"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=2) as connection:
        return connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def wait_pids(log_path: Path) -> dict[str, int]:
    pattern = re.compile(r"^\[runner\] started (collector|query|dashboard) pid=(\d+) pgid=\2$", re.M)

    def read_started():
        matches = pattern.findall(log_path.read_text(errors="replace"))
        return {name: int(pid) for name, pid in matches} if len(matches) == 3 else None

    return wait(read_started, "three ./dev-owned component process groups")


def stop_runner(process: subprocess.Popen, pids: dict[str, int], expected: tuple[int, ...]) -> int:
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
    try:
        returncode = process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        for pid in pids.values():
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            returncode = process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            for pid in pids.values():
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.kill()
            returncode = process.wait(timeout=3)
    if returncode not in expected:
        raise AssertionError(f"unexpected ./dev exit status {returncode}, expected {expected}")
    wait(lambda: all(not process_exists(pid) for pid in pids.values()), "owned component cleanup", seconds=5)
    return returncode


def main() -> None:
    binary = ROOT / "collector/build/Release/bin/data_collector"
    fake = ROOT / "collector/build/Release/libfake_md.so"
    python = ROOT / "query/.venv/bin/python"
    vite = ROOT / "dashboard/node_modules/vite/bin/vite.js"
    for path in (ROOT / "dev", binary, fake, python, vite):
        if not path.is_file():
            raise SystemExit(f"Required runner smoke dependency missing: {path}")
    if shutil.which("node") is None:
        raise SystemExit("Required runner smoke dependency missing: Linux node")

    runners: list[tuple[subprocess.Popen, dict[str, int]]] = []
    with tempfile.TemporaryDirectory(prefix="dm-dev-runner-test-double-") as folder:
        work = Path(folder)
        data = work / "data"
        flow = work / "flow"
        sdk = work / "sdk"
        data.mkdir()
        flow.mkdir()
        sdk.mkdir()
        (sdk / "thostmduserapi_se.so").symlink_to(fake)
        config = work / "config.ini"
        config.write_text(
            "[config]\n"
            "FrontMdAddr=TEST-DOUBLE\n"
            "Instruments=IF2609\n"
            "DataDirectory=data\n"
            "FlowPath=flow\n"
            "SnapshotIntervalMs=100\n"
            "StatusIntervalSeconds=1\n"
            "ConnectTimeoutSeconds=2\n"
            "RunSeconds=0\n"
        )
        environment = os.environ.copy()
        for name in ("DATA_DIR", "QUERY_URL", "QUERY_PORT", "DASHBOARD_PORT", "LD_PRELOAD", "DM_TEST_SCENARIO"):
            environment.pop(name, None)
        existing_library_path = environment.get("LD_LIBRARY_PATH")
        environment["LD_LIBRARY_PATH"] = str(sdk) + ((":" + existing_library_path) if existing_library_path else "")
        environment["PYTHONDONTWRITEBYTECODE"] = "1"

        def start_session(label: str):
            query_port = unused_port()
            dashboard_port = unused_port()
            while dashboard_port == query_port:
                dashboard_port = unused_port()
            log_path = work / f"{label}.log"
            log = log_path.open("wb")
            try:
                process = subprocess.Popen(
                    [str(ROOT / "dev"), "up", "--config", "config.ini", "--query-port", str(query_port),
                     "--dashboard-port", str(dashboard_port)],
                    cwd=work,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            finally:
                log.close()
            pids: dict[str, int] = {}
            runners.append((process, pids))
            pids.update(wait_pids(log_path))
            return process, pids, log_path, query_port, dashboard_port

        try:
            first, first_pids, first_log, query_port, dashboard_port = start_session("first")
            query_base = f"http://127.0.0.1:{query_port}"
            dashboard_base = f"http://127.0.0.1:{dashboard_port}"
            wait(lambda: json_get(query_base, "/healthz")["status"] == "ok", "Query /healthz")
            summary = wait(
                lambda: (value if value["rows"] > 2 else None)
                if (value := json_get(query_base, f"/api/summary?day={DAY}")) else None,
                "Query reading Collector's temporary Raw directory",
            )
            assert "TEST DOUBLE" in summary["runs"][0]["source"]
            proxied = json_get(dashboard_base, f"/api/summary?day={DAY}")
            assert proxied["day"] == DAY and proxied["rows"] > 0
            assert json_get(dashboard_base, "/api/health")["data"]["readable"]

            port_conflict = subprocess.run(
                [str(ROOT / "dev"), "up", "query", "--data-dir", str(data), "--query-port", str(query_port)],
                cwd=work,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=20,
                check=False,
            )
            assert port_conflict.returncode == 1 and "already in use" in port_conflict.stdout
            assert json_get(query_base, "/healthz")["status"] == "ok"

            before_writer_conflict = row_count(data)
            writer_conflict = subprocess.run(
                [str(ROOT / "dev"), "up", "collector", "--config", "config.ini"],
                cwd=work,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=20,
                check=False,
            )
            assert writer_conflict.returncode == 1
            assert "data directory already owned by another collector" in writer_conflict.stdout
            assert process_exists(first_pids["collector"])
            wait(lambda: row_count(data) > before_writer_conflict, "existing Collector after writer conflict")

            before_downstream_stop = row_count(data)
            os.killpg(first_pids["query"], signal.SIGTERM)
            os.killpg(first_pids["dashboard"], signal.SIGTERM)
            wait(
                lambda: "query exited with status" in first_log.read_text(errors="replace")
                and "dashboard exited with status" in first_log.read_text(errors="replace"),
                "runner recording downstream exits",
            )
            assert process_exists(first_pids["collector"])
            wait(lambda: row_count(data) > before_downstream_stop + 2, "Collector commits after downstream exit")
            stop_runner(first, first_pids, expected=(1,))
            assert json.loads((data / ".collector-status.json").read_text())["process_state"] == "stopped"

            rows_before_restart = row_count(data)
            runs_before_restart = run_count(data)
            second, second_pids, second_log, query_port, dashboard_port = start_session("second")
            query_base = f"http://127.0.0.1:{query_port}"
            dashboard_base = f"http://127.0.0.1:{dashboard_port}"
            wait(lambda: json_get(query_base, "/healthz")["status"] == "ok", "restarted Query")
            wait(lambda: row_count(data) > rows_before_restart, "Collector appending after ./dev restart")
            wait(lambda: run_count(data) > runs_before_restart, "new Collector run retained beside prior run")
            restarted_summary = wait(
                lambda: (value if value["rows"] > rows_before_restart else None)
                if (value := json_get(dashboard_base, f"/api/summary?day={DAY}")) else None,
                "restarted Dashboard proxy reading preserved Raw data",
            )
            assert "TEST DOUBLE" in restarted_summary["runs"][0]["source"]
            stop_runner(second, second_pids, expected=(128 + signal.SIGTERM,))
            assert "sending SIGKILL" not in second_log.read_text(errors="replace")
            assert json.loads((data / ".collector-status.json").read_text())["process_state"] == "stopped"

            with sqlite3.connect((data / f"{DAY}.sqlite").as_uri() + "?mode=ro", uri=True) as connection:
                assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                assert connection.execute("SELECT COUNT(*) FROM runs WHERE source LIKE '%TEST DOUBLE%'").fetchone()[0] >= 2
                assert connection.execute("SELECT COUNT(*) FROM runs WHERE stopped_us IS NULL").fetchone()[0] == 0

            print("PASS: actual ./dev TEST DOUBLE Collector -> SQLite -> Uvicorn -> Vite chain")
            print("PASS: shared Raw, Dashboard proxy, downstream independence, conflicts, clean stop and preserved restart")
            print("Scope: temporary paths/random ports only; no real config, CTP, deployment manager, Docker, or browser.")
        except BaseException:
            for log_path in work.glob("*.log"):
                print(f"{log_path.name}:\n{log_path.read_text(errors='replace')[-12000:]}")
            raise
        finally:
            for process, pids in reversed(runners):
                if process.poll() is None:
                    try:
                        stop_runner(process, pids, expected=(1, 128 + signal.SIGTERM))
                    except BaseException:
                        for pid in pids.values():
                            try:
                                os.killpg(pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                        if process.poll() is None:
                            process.kill()
                            process.wait(timeout=3)


if __name__ == "__main__":
    main()
