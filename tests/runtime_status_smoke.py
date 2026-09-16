#!/usr/bin/env python3
"""TEST DOUBLE: running C++ Collector -> runtime SQLite -> Python/HTTP and healthcheck."""
from contextlib import closing
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from data_provider.runtime_status import read_runtime_status
from query.app import create_app


def wait(predicate, seconds=22):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.1)
    raise AssertionError('TEST DOUBLE runtime condition timed out')


def main():
    binary = ROOT / 'collector/build/Release/bin/data_collector'
    sdk = ROOT / 'collector/build/Release/libfake_md.so'
    healthcheck = ROOT / 'collector/scripts/healthcheck.sh'
    with tempfile.TemporaryDirectory(prefix='test-double-runtime-integration-') as temporary:
        work = Path(temporary)
        data = work / 'data'
        config = work / 'config.ini'
        config.write_text('# TEST DOUBLE only\n[config]\nFrontMdAddr=test-double\nInstruments=IF2609\n'
                          'DataDirectory=data\nFlowPath=flow\nConnectTimeoutSeconds=2\n')
        # Deliberately preserve old evidence; neither publisher nor consumers may use it.
        data.mkdir()
        old = data / '.collector-status.json'
        old.write_text('{"process_state":"failed"}')
        old_coverage = data / '.collector-coverage.json'
        old_coverage.write_text('TEST DOUBLE - invalid old coverage')
        runtime = data / 'collector-runtime.sqlite'
        def current():
            snapshot = read_runtime_status(data)
            return snapshot[0] if snapshot else None
        def sql(path, query):
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
                return db.execute(query).fetchone()[0]
        def schema(sql):
            with closing(sqlite3.connect(runtime)) as db:
                db.execute(sql)
        def check_cli(expected):
            result = subprocess.run(['sh', str(healthcheck), str(runtime)], capture_output=True, text=True)
            assert (result.returncode == 0) == expected, result.stderr
        child = None
        with (work / 'collector.log').open('wb') as log, TestClient(create_app(data)) as client:
            try:
                child = subprocess.Popen([str(binary), '--config', str(config)], stdout=log, stderr=log,
                    env=dict(os.environ, LD_PRELOAD=str(sdk), DM_TEST_DAY1='20260908', DM_TEST_DAY2='20260908', DM_TEST_SCENARIO='runtime'))
                wait(lambda: runtime.exists() and client.get('/api/health').json()['collector']['process_alive'])
                first = current()
                run_id = first['run_id']
                wait(lambda: current()['heartbeat_us'] > first['heartbeat_us'])
                wait(lambda: current()['last_market_commit_us'] is not None)
                published = current()
                assert published['ticks_received'] > 0 and published['bars_written'] > 0
                response = client.get('/api/health').json()['collector']
                assert response['status'] == 'running' and response['heartbeat']['run_id'] == run_id
                assert response['heartbeat']['accepted'] == response['heartbeat']['ticks_received']
                assert client.get('/api/coverage').json()['collector_current']
                check_cli(True)
                # user_version is not a Runtime protocol version; the complete DDL is authoritative.
                before_version_change = current()['heartbeat_us']
                schema('PRAGMA user_version=99')
                wait(lambda: current()['heartbeat_us'] > before_version_change)
                check_cli(True)
                # An incompatible diagnostic DB cannot stop Market persistence or advance heartbeat.
                schema('CREATE TABLE incompatible_runtime_schema(value INTEGER)')
                frozen = sql(runtime, 'SELECT heartbeat_us FROM current_status')
                before = sql(data / '20260908.sqlite', 'SELECT count(*) FROM market_bars')
                wait(lambda: sql(data / '20260908.sqlite', 'SELECT count(*) FROM market_bars') > before)
                assert child.poll() is None
                assert sql(runtime, 'SELECT heartbeat_us FROM current_status') == frozen
                assert client.get('/api/health').json()['collector']['status'] == 'unknown'
                assert client.get('/api/coverage').status_code == 503
                check_cli(False)
                schema('DROP TABLE incompatible_runtime_schema')
                wait(lambda: current()['heartbeat_us'] > frozen)
                assert current()['run_id'] == run_id
                assert current()['bars_written'] > published['bars_written']
                check_cli(True)
                child.send_signal(signal.SIGTERM)
                assert child.wait(timeout=5) == 0
                final = current()
                assert final['process_state'] == 'stopped'
                assert not final['connected'] and not final['logged_in'] and final['subscribed_count'] == 0
                assert client.get('/api/health').json()['collector']['status'] == 'stopped'
                check_cli(False)
                assert old.read_text() == '{"process_state":"failed"}'
                assert old_coverage.read_text() == 'TEST DOUBLE - invalid old coverage'
                assert 'status_write_failed' in (work / 'collector.log').read_text()
                # TEST DOUBLE clock mutations after the process stopped: mtime cannot prove liveness.
                for stamp in (time.time_ns() // 1000 - 11_000_000, time.time_ns() // 1000 + 20_000_000):
                    with closing(sqlite3.connect(runtime)) as db, db:
                        db.execute("UPDATE current_status SET process_state='starting',heartbeat_us=?,updated_us=?",
                                   (stamp, stamp))
                    os.utime(runtime, None)
                    check_cli(False)
            finally:
                if child is not None and child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
        print('PASS: TEST DOUBLE C++ runtime, atomic read adapter, HTTP/coverage, CLI liveness, diagnostic failure isolation/recovery, shutdown')
        print('No live CTP, service deployment, Calendar Health or historical completeness claim.')


if __name__ == '__main__':
    main()
