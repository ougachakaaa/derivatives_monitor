#!/usr/bin/env python3
"""TEST DOUBLE SDK + real user systemd; only unique temporary units/data are touched."""
from contextlib import closing
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from collector.scripts.native import collector_unit, quote


def wait(predicate, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.1)
    raise AssertionError('TEST DOUBLE recovery condition timed out')


def main():
    try:
        available = subprocess.run(['systemctl', '--user', 'show-environment'],
                                   capture_output=True, timeout=5)
        manager_available = available.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        manager_available = False
    if not manager_available:
        print('NOT RUN: user systemd manager unavailable; no simulated replacement.')
        return 0  # Repository runner classifies NOT RUN as NOT_RUN, never PASS.
    identity = uuid.uuid4().hex
    folder = ROOT / 'artifacts/native-recovery' / identity
    folder.mkdir(parents=True)
    name = 'dm-test-double-recovery-' + identity + '.service'
    unit_path = folder / name
    control = folder / 'control'
    control.write_text('normal')
    config = folder / 'config.ini'
    config.write_text('# TEST DOUBLE only; no real front or credentials\n[config]\n'
                      'FrontMdAddr=test-double\nInstruments=IF2609\nDataDirectory=data\nFlowPath=flow\n'
                      'ConnectTimeoutSeconds=2\nRetryIntervalSeconds=1\nStatusIntervalSeconds=2\nRunSeconds=0\n')
    data = folder / 'data'
    binary = ROOT / 'collector/build/Release/bin/data_collector'
    sdk = ROOT / 'collector/build/Release/libfake_md.so'
    log = folder / 'service.log'
    unit_path.write_text(collector_unit(binary, sys.executable, config, data, folder)
        + f'Environment={quote("LD_PRELOAD=" + str(sdk))}\n'
        + f'Environment={quote("DM_TEST_CONTROL=" + str(control))}\n'
        + f'StandardOutput=append:{log}\nStandardError=inherit\n')
    evidence = dict(kind='TEST DOUBLE SDK / real user systemd', unit=name, cases=[])
    stopped = False

    def ctl(*args, check=True):
        return subprocess.run(['systemctl', '--user', *args], capture_output=True,
                              text=True, check=check, timeout=8)

    def properties():
        result = ctl('show', name, '-p', 'MainPID', '-p', 'NRestarts', '-p', 'ActiveState',
                     '-p', 'SubState', '-p', 'Result', '-p', 'ExecMainStatus')
        return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)

    def events():
        rows = []
        if log.exists():
            for line in log.read_text().splitlines():
                if line.startswith('{'):
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # Concurrent append; the next poll reads the complete line.
        return rows

    def current():
        path = data / 'collector-runtime.sqlite'
        try:
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.1)) as db:
                db.row_factory = sqlite3.Row
                row = db.execute('SELECT * FROM current_status').fetchone()
                return dict(row) if row else {}
        except sqlite3.Error:
            return {}

    def bound():
        rows = [e for e in events() if e['event'] == 'collector_run_bound']
        return rows[-1] if rows else {}

    def child_pid():
        return bound()['collector_pid']

    def record(case, **values):
        evidence['cases'].append(dict(case=case, **values))
        (folder / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
        print('PASS:', case, json.dumps(values), flush=True)

    def stable(mode, predicate):
        before, props = current(), properties()
        pid = child_pid()
        control.write_text(mode)
        wait(lambda: predicate(current()))
        started = time.monotonic()
        last = current()['heartbeat_us']
        # Longer than both liveness window and restart delay, with continuous assertions.
        while time.monotonic() - started < 12:
            value = current()
            assert value['run_id'] == before['run_id'] and child_pid() == pid
            assert properties()['NRestarts'] == props['NRestarts']
            assert predicate(value), (mode, value)
            time.sleep(.2)
        assert current()['heartbeat_us'] > last
        control.write_text('normal')
        wait(lambda: current().get('subscribed_count') == 1)
        record(mode + '_without_restart', pid=pid, run_id=before['run_id'], duration_seconds=12)

    def recovery(case, trigger, *, stalled=False):
        old = current()
        pid = child_pid()
        restarts = int(properties()['NRestarts'])
        started = time.monotonic()
        offset = log.stat().st_size
        trigger()
        if case == 'main_loop_stall_callbacks_continue':
            wait(lambda: 'event=test_double_main_stall' in log.read_text()[offset:])
            frozen = current()['heartbeat_us']
            wait(lambda: log.read_text()[offset:].count('event=test_double_callback_during_stall') >= 2)
            assert current()['heartbeat_us'] == frozen
            callbacks = log.read_text()[offset:].count('event=test_double_callback_during_stall')
            wait(lambda: any(e['event'] == 'runtime_failed' and e.get('collector_pid') == pid for e in events()), timeout=15)
            assert log.read_text()[offset:].count('event=test_double_callback_during_stall') > callbacks
            # The blocked SDK call stays blocked; only the next Process sees normal mode.
            control.write_text('normal')
        if case in ('exit_zero', 'exit_nonzero'):
            wait(lambda: properties()['SubState'] == 'auto-restart')
            control.write_text('normal')
        wait(lambda: bound().get('run_id') not in (None, old['run_id']), timeout=88)
        new = bound()
        spawned = next(e for e in reversed(events())
                       if e['event'] == 'collector_spawn' and e['collector_pid'] == new['collector_pid'])
        # The child spawn event uses the same host monotonic clock as the injection.
        elapsed = spawned['monotonic_ns'] / 1_000_000_000 - started
        assert new['collector_pid'] != pid
        assert int(properties()['NRestarts']) > restarts
        assert not Path(f'/proc/{pid}').exists()
        if stalled:
            assert elapsed <= 83, elapsed
            failures = [e for e in events() if e['event'] == 'runtime_failed' and e.get('collector_pid') == pid]
            assert failures and failures[-1]['reason'] == 'heartbeat_stale', failures
            assert any(e['event'] == 'collector_force_kill' and e['collector_pid'] == pid for e in events())
        wait(lambda: current().get('run_id') == new['run_id'] and current().get('bars_written', 0) > 0)
        value = current()
        with closing(sqlite3.connect((data / 'collector-runtime.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
            old_run = db.execute('SELECT * FROM runs WHERE run_id=?', (old['run_id'],)).fetchone()
            if stalled:
                assert old_run[2:4] == (None, None), old_run
        market = data / (value['trading_day'] + '.sqlite')
        with closing(sqlite3.connect(market.as_uri() + '?mode=ro', uri=True)) as db:
            assert db.execute('SELECT count(*) FROM market_bars WHERE run_id=?', (new['run_id'],)).fetchone()[0] > 0
        record(case, old_pid=pid, new_pid=new['collector_pid'], old_run_id=old['run_id'],
               new_run_id=new['run_id'], observed_recovery_seconds=round(elapsed, 3),
               spawn_utc_us=spawned['utc_us'], previous=old, current=value, systemd=properties())

    def stays_stopped(case):
        baseline = len([e for e in events() if e['event'] == 'collector_spawn'])
        # This is the same atomic systemd operation used by Universe publication.
        ctl('try-restart', '--no-block', name)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            props = properties()
            assert props['ActiveState'] == 'inactive' and props['MainPID'] == '0', props
            assert len([e for e in events() if e['event'] == 'collector_spawn']) == baseline
            time.sleep(.2)
        record(case, systemd=properties(), spawn_count=baseline)

    def interrupted(*_):
        raise KeyboardInterrupt('TEST DOUBLE verification interrupted')

    previous = signal.signal(signal.SIGTERM, interrupted)
    linked = False
    try:
        subprocess.run(['systemd-analyze', '--user', 'verify', str(unit_path)], check=True, timeout=10)
        ctl('link', '--runtime', str(unit_path))
        linked = True
        ctl('daemon-reload')
        ctl('start', name)
        wait(lambda: bound() and current().get('bars_written', 0) > 0)
        stable('disconnect', lambda s: s.get('connected') == 0)
        stable('login-pending', lambda s: s.get('connected') == 1 and s.get('logged_in') == 0)
        stable('subscription-failed', lambda s: s.get('logged_in') == 1 and s.get('subscribed_count') == 0)
        recovery('main_loop_stall_callbacks_continue', lambda: control.write_text('stall'), stalled=True)
        recovery('sigstop', lambda: os.kill(child_pid(), signal.SIGSTOP), stalled=True)
        recovery('exit_zero', lambda: control.write_text('exit-zero'))
        recovery('exit_nonzero', lambda: control.write_text('exit-failure'))
        recovery('collector_sigkill', lambda: os.kill(child_pid(), signal.SIGKILL))
        recovery('wrapper_sigkill', lambda: os.kill(int(properties()['MainPID']), signal.SIGKILL))
        pid = child_pid()
        ctl('stop', name)
        assert not Path(f'/proc/{pid}').exists()
        assert current()['process_state'] == 'stopped'
        stays_stopped('manual_stop_and_universe_try_restart')
        old = bound()['run_id']
        ctl('start', name)
        wait(lambda: bound().get('run_id') != old)
        os.kill(child_pid(), signal.SIGKILL)
        wait(lambda: properties()['SubState'] == 'auto-restart')
        ctl('stop', name)
        stays_stopped('manual_stop_during_restart_delay')
        stopped = True
        evidence['status'] = 'PASS'
    finally:
        signal.signal(signal.SIGTERM, previous)
        if linked:
            # Cancellation must not leave a test unit restarting outside the runner's process group.
            if not stopped:
                ctl('stop', '--no-block', name, check=False)
                ctl('kill', '--kill-who=all', '--signal=SIGKILL', name, check=False)
            ctl('stop', name, check=False)
            ctl('reset-failed', name, check=False)
            ctl('disable', '--runtime', name)
            ctl('daemon-reload')
            loaded = ctl('show', name, '-p', 'LoadState', check=False)
            assert 'LoadState=not-found' in loaded.stdout, loaded.stdout
        evidence.setdefault('status', 'FAIL')
        (folder / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
        print('TEST DOUBLE evidence:', folder, flush=True)
    print('PASS: real systemd native recovery; no live CTP or production service claim.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
