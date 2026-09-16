#!/usr/bin/env python3
"""Native deployment liveness guard. Only systemd restarts the Collector.

Policy authority: docs/contracts/deployment.md#native-heartbeat-recovery.
No Query dependency and no Runtime DB writes.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

CHECK_INTERVAL = 1.0
CHECK_TIMEOUT = 2.0
STARTUP_GRACE = 15.0
STOP_GRACE = 60.0
HEALTHCHECK = Path(__file__).with_name('healthcheck.sh')


def log(event, **fields):
    print(json.dumps(dict(event=event, utc_us=time.time_ns() // 1000,
                          monotonic_ns=time.monotonic_ns(), **fields)), flush=True)


def signal_group(process, sig):
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass


def probe(database, minimum, run_id, stopping, *, timeout=CHECK_TIMEOUT, checker=HEALTHCHECK):
    """Bound the entire shell/SQLite pipeline, including stop responsiveness."""
    process = subprocess.Popen(['sh', str(checker), str(database), str(minimum), run_id or ''],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    deadline = time.monotonic() + timeout
    try:
        while not stopping.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None, 'probe_timeout'
            try:
                out, error = process.communicate(timeout=min(.05, remaining))
                if process.returncode:
                    return None, error.decode(errors='replace').strip().split('\n')[-1] or 'probe_failed'
                value = out.decode().strip()
                if len(value) != 32 or any(c not in '0123456789abcdef' for c in value):
                    return None, 'probe_invalid_output'
                return value, None
            except subprocess.TimeoutExpired:
                pass
        return None, 'stopping'
    finally:
        # Always clean descendants, even if the shell exited before its children.
        signal_group(process, signal.SIGKILL)
        process.communicate()


def terminate(child, *, grace=STOP_GRACE):
    if child.poll() is None:
        log('collector_terminate', collector_pid=child.pid, signal='SIGTERM')
        signal_group(child, signal.SIGTERM)
        try:
            child.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            log('collector_force_kill', collector_pid=child.pid, signal='SIGKILL')
            signal_group(child, signal.SIGKILL)
            child.wait()
    # The SDK must not leave descendants behind even after a normal exit.
    signal_group(child, signal.SIGKILL)


def supervise(command, database, *, interval=CHECK_INTERVAL, timeout=CHECK_TIMEOUT,
              startup_grace=STARTUP_GRACE, stop_grace=STOP_GRACE, checker=HEALTHCHECK):
    stopping = threading.Event()
    previous = {sig: signal.signal(sig, lambda *_: stopping.set())
                for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    child = None
    run_id = None
    try:
        # Recorded before spawn: a previous Process cannot satisfy this identity gate.
        minimum = time.time_ns() // 1000
        started = time.monotonic()
        if stopping.is_set():
            return 0
        child = subprocess.Popen(command, start_new_session=True)
        log('collector_spawn', collector_pid=child.pid, minimum_started_us=minimum)
        while not stopping.is_set():
            result = child.poll()
            if result is not None:
                log('collector_exit', collector_pid=child.pid, run_id=run_id, returncode=result)
                # Even zero exit is restarted by the Collector unit's Restart=always.
                return 0 if result == 0 else 1
            accepted, reason = probe(database, minimum, run_id, stopping, timeout=timeout, checker=checker)
            if stopping.is_set():
                break
            if accepted:
                if run_id is None:
                    run_id = accepted
                    log('collector_run_bound', collector_pid=child.pid, run_id=run_id)
            elif run_id is not None or time.monotonic() - started >= startup_grace:
                log('runtime_failed', collector_pid=child.pid, run_id=run_id, reason=reason)
                return 1
            # A probe takes at most timeout; the next one starts within interval.
            stopping.wait(interval)
        log('supervisor_stopping', collector_pid=child.pid, run_id=run_id)
        return 0
    except Exception as error:
        log('runtime_failed', collector_pid=child.pid if child else None, run_id=run_id,
            reason=type(error).__name__, message=str(error))
        return 1
    finally:
        if child is not None:
            terminate(child, grace=stop_grace)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('Collector command is required after --')
    return supervise(command, args.database)


if __name__ == '__main__':
    raise SystemExit(main())
