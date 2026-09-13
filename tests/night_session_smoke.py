#!/usr/bin/env python3
"""Synthetic night/day source timestamps through real C++ writer and read-only Query.

Run with query/.venv/bin/python. No real credentials, data or services are used.
"""
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
from fastapi.testclient import TestClient
from query.app import create_app


def read(path, sql):
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        return db.execute(sql).fetchall()


def wait(predicate):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except (OSError, ValueError, sqlite3.Error):
            pass
        time.sleep(.05)
    raise AssertionError('synthetic night scenario did not complete')


def main():
    binary = ROOT / 'collector/build/Release/bin/data_collector'
    fake = ROOT / 'collector/build/Release/libfake_md.so'
    with tempfile.TemporaryDirectory(prefix='dm-night-test-') as folder:
        directory = Path(folder)
        data = directory / 'data'
        config = directory / 'config.ini'
        config.write_text('[config]\nFrontMdAddr=test-double\nInstruments=IF2609,au2610,ag2610\n'
                          'DataDirectory=data\nFlowPath=flow\nSnapshotIntervalMs=100\n'
                          'ConnectTimeoutSeconds=2\nStatusIntervalSeconds=1\n')
        day1, day2 = data / '20260908.sqlite', data / '20260909.sqlite'
        previous_counts = None
        for run in range(2):
            with (directory / 'collector.log').open('ab') as log:
                child = subprocess.Popen([str(binary), '--config', str(config)], stdout=log, stderr=log,
                    env=dict(os.environ, LD_PRELOAD=str(fake), DM_TEST_SCENARIO='shfe-night'))
            try:
                wait(lambda: read(day2, 'SELECT count(*) FROM runs')[0][0] == run + 1)
                # Live Query sees the active partition; closed history keeps the existing WAL guard.
                with TestClient(create_app(data)) as client:
                    for day in ('20260909',):
                        response = client.get('/api/snapshots', params={'day': day, 'limit': 200})
                        assert response.status_code == 200, response.text
                        assert all(r['TradingDay'] == day for r in response.json()['rows'])
                    session = client.get('/api/sessions', params={'exchange': 'SHFE', 'product': 'AU',
                        'at': '2026-09-08T00:00:00+08:00'}).json()['markets'][0]
                    assert session['trading_day'] == '20260908' and session['is_continuous']
                child.send_signal(signal.SIGTERM)
                assert child.wait(timeout=10) == 0
            finally:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=10)
            with TestClient(create_app(data)) as client:
                for day in ('20260908', '20260909'):
                    response = client.get('/api/snapshots', params={'day': day, 'limit': 200})
                    assert response.status_code == 200, response.text
                    assert all(r['TradingDay'] == day for r in response.json()['rows'])
            assert not (data / '20260907.sqlite').exists()  # Natural night start is not a partition.
            assert sorted(p.name for p in data.glob('*.sqlite')) == ['20260908.sqlite', '20260909.sqlite']
            assert read(day1, "SELECT DISTINCT InstrumentID FROM snapshots ORDER BY InstrumentID") == [('IF2609',), ('ag2610',), ('au2610',)]
            for instrument in ('au2610', 'ag2610'):
                rows = read(day1, "SELECT DISTINCT ActionDay,UpdateTime FROM snapshots WHERE InstrumentID='" + instrument + "'")
                for stamp in [('20260907','21:00:00'),('20260907','23:59:59'),('20260908','00:00:00'),
                              ('20260908','02:29:59'),('20260908','09:00:00'),('20260908','14:59:59')]:
                    assert stamp in rows, (instrument, stamp, rows)
            for path in (day1, day2):
                assert read(path, 'PRAGMA journal_mode') == [('wal',)]
                assert read(path, 'PRAGMA integrity_check') == [('ok',)]
                assert read(path, 'PRAGMA foreign_key_check') == []
                assert read(path, 'SELECT count(*) FROM runs WHERE stopped_us IS NULL') == [(0,)]
                assert read(path, 'SELECT count(*) FROM snapshots WHERE received_us<=0 OR snapshot_us<received_us') == [(0,)]
                assert read(path, "SELECT count(*) FROM snapshots WHERE InstrumentID IN ('au2610','ag2610') AND ExchangeID!='SHFE'") == [(0,)]
            counts = [read(path, 'SELECT count(*) FROM snapshots')[0][0] for path in (day1, day2)]
            if previous_counts:
                assert all(after > before for before, after in zip(previous_counts, counts))
            previous_counts = counts
            heartbeat = json.loads((data / '.collector-status.json').read_text())
            assert heartbeat['accepted'] > heartbeat['written'] > 0
            assert heartbeat['connections'] == 2 and heartbeat['disconnections'] == 1
            assert heartbeat['process_state'] == 'stopped'
        text = (directory / 'collector.log').read_text()
        assert 'TEST DOUBLE' in text and 'event=snapshot_commit' in text
        print('PASS: synthetic AU/AG night → midnight → day → next TradingDay; CFFEX coexistence, reconnect, Query, restart append, WAL, timestamps')
        print('TEST DOUBLE only; real AU/AG night acceptance is separate. SnapshotIntervalMs=100 accelerates fixture; default 15000 is covered by CTest.')


if __name__ == '__main__':
    main()
