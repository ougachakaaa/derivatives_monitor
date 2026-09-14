#!/usr/bin/env python3
"""Native-process acceptance, NOT Docker or live CTP acceptance. Temporary test data only."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def runtime_status(directory):
    # TEST DOUBLE process output; never opens a real data directory.
    with closing(sqlite3.connect((directory / 'collector-runtime.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        return dict(db.execute('SELECT * FROM current_status WHERE singleton=1').fetchone())


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait(check, description, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(.2)
    raise AssertionError("Timed out: " + description)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true", help="Also run Playwright against Vite and actual API")
    args = parser.parse_args()
    binary = ROOT / "collector/build/Release/bin/data_collector"
    fake = ROOT / "collector/build/Release/libfake_md.so"
    python = ROOT / "query/.venv/bin/python"
    for path in (binary, fake, python):
        if not path.is_file():
            raise SystemExit(f"Required build/dependency missing: {path}")
    processes = []
    with tempfile.TemporaryDirectory(prefix="dm-read-path-") as folder:
        work = Path(folder)
        (work / "config.ini").write_text("[config]\nFrontMdAddr=tcp://127.0.0.1:1\nInstruments=IF2609\nDataDirectory=data\nFlowPath=flow\nSnapshotIntervalMs=100\nStatusIntervalSeconds=1\nConnectTimeoutSeconds=20\nRunSeconds=0\n")
        query_port = port()
        base = f"http://127.0.0.1:{query_port}"

        def get(path):
            with urllib.request.urlopen(base + path, timeout=4) as response:
                return json.load(response)

        def start(command, cwd, name, **env):
            log = open(work / (name + ".log"), "ab")
            try:
                process = subprocess.Popen([str(x) for x in command], cwd=cwd, env=dict(os.environ, **env), stdout=log, stderr=log)
            finally:
                log.close()
            processes.append(process)
            return process

        def query():
            return start([python, "-m", "uvicorn", "query.app:app", "--host", "127.0.0.1", "--port", str(query_port)], ROOT, "query", DATA_DIR=str(work / "data"))

        def collector():
            return start([binary, "--config", work / "config.ini"], ROOT, "collector", LD_PRELOAD=str(fake))

        try:
            api = query()
            wait(lambda: get("/healthz")["status"] == "ok", "API without Collector")
            assert not get("/api/health")["collector"]["process_alive"]
            cpp = collector()
            wait(lambda: get("/api/summary?day=20260907")["rows"] > 2, "live WAL rows")
            wait(lambda: get("/api/health")["collector"]["status"] == "running", "Collector heartbeat")
            before = get("/api/summary?day=20260907")["rows"]
            wait(lambda: get("/api/summary?day=20260907")["rows"] > before, "continuous commits")
            assert "TEST DOUBLE" in get("/api/summary?day=20260907")["runs"][0]["source"]
            if args.browser:
                web_port = port()
                web = start(["node", "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"], ROOT / "dashboard", "dashboard", QUERY_URL=base)
                web_url = f"http://127.0.0.1:{web_port}"
                wait(lambda: urllib.request.urlopen(web_url, timeout=2).status == 200, "Vite frontend")
                subprocess.run(["node", "tests/browser.mjs", web_url], cwd=ROOT / "dashboard", check=True, timeout=60)
                web.terminate(); web.wait(timeout=10)
            api.terminate(); assert api.wait(timeout=10) in (0, -signal.SIGTERM)
            assert "Application shutdown complete" in (work / "query.log").read_text()
            before = runtime_status(work / "data")["bars_written"]
            wait(lambda: runtime_status(work / "data")["bars_written"] > before + 2, "Collector writes without Python")
            api = query()
            wait(lambda: get("/api/summary?day=20260907")["rows"] > 2, "API restart reads existing data")
            cpp.send_signal(signal.SIGTERM); assert cpp.wait(timeout=10) == 0
            assert get("/api/health")["collector"]["status"] == "stopped"
            assert get("/api/summary?day=20260904")["rows"] > 0
            rows = get("/api/summary?day=20260907")["rows"]
            assert get("/healthz")["status"] == "ok"
            cpp = collector()
            wait(lambda: get("/api/summary?day=20260907")["rows"] > rows, "Collector restart appends")
            wait(lambda: get("/api/health")["collector"]["status"] == "running", "new heartbeat")
            cpp.kill(); cpp.wait(timeout=10)
            wait(lambda: get("/api/health")["collector"]["status"] == "stale", "SIGKILL heartbeat expiry", seconds=15)
            assert not get("/api/health")["collector"]["process_alive"]
            print("PASS: real native C++ → SQLite → FastAPI HTTP; independent stops/restarts, persistent counts, SIGKILL expiry" + ("; React browser rendering/recovery" if args.browser else ""))
            print("Source: TEST DOUBLE synthetic SDK. Docker and real CTP acceptance are separate.")
        except BaseException:
            for path in work.glob("*.log"):
                print(path.name + ":\n" + path.read_text(errors="replace")[-8000:])
            raise
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait()


if __name__ == "__main__":
    main()
