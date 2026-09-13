#!/usr/bin/env python3
"""Explicit, isolated acceptance profiles with persistent per-command evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / 'query/.venv/bin/python'
BUILD = ROOT / 'collector/build/Release'


def step(name, argv, cwd=ROOT, requires=(), timeout=900):
    return dict(name=name, argv=[str(x) for x in argv], cwd=str(cwd),
                requires=[str(x) for x in requires], timeout=timeout)


def build_steps():
    return [step('configure', ['cmake', '-S', 'collector', '-B', BUILD,
                              '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_TESTING=ON', '-DCTP_LINK_MODE=SHARED']),
            step('build', ['cmake', '--build', BUILD, '-j', '2'])]


def profiles(profile):
    checks = [step('docs', [sys.executable, ROOT / 'tests/check_docs.py']),
              step('repository-boundaries', [sys.executable, ROOT / 'tests/check_repository.py']),
              step('collector-sdk', [sys.executable, '-m', 'unittest',
                                     'collector.tests.test_sdk_manifest', '-v'])]
    if profile == 'docs':
        return checks + [step('repository-check-tests', [sys.executable, '-m', 'unittest',
                              'tests.test_repository_checks', '-v'])]
    checks += [step('verification-tests', [sys.executable, '-m', 'unittest',
                    'tests.test_repository_checks', 'tests.test_verification_runner', '-v'])]
    if profile == 'analytics-contract':
        return checks + analytics_contract_steps()
    if profile == 'analytics':
        return checks + analytics_contract_steps() + [
                         step('analytics-production', [PYTHON, '-m', 'unittest',
                              'analytics.tests.test_skew', 'analytics.tests.test_skew_service',
                              'analytics.tests.test_indicator_service',
                              'analytics.tests.test_skew_references',
                              'query.tests.test_skew_api', '-v'])]
    if profile in ('docker', 'packaging'):
        checks += [step('docker-engine', ['docker', 'version'], timeout=30),
                   step('docker-context', [sys.executable, 'tests/check_docker_context.py'], requires=['docker'], timeout=150)]
        if profile == 'packaging':
            return checks
        return checks + [step('docker-compose', ['docker', 'compose', 'version'], timeout=30),
                         step('docker-read-path', ['bash', 'tests/read_path_docker_smoke.sh'], requires=['docker'], timeout=1800),
                         step('docker-collector', ['bash', 'collector/tests/docker_smoke.sh'], requires=['docker'], timeout=1800)]
    checks += build_steps()
    if profile == 'offline':
        checks += [step('ctest', ['ctest', '--test-dir', BUILD, '--output-on-failure']),
                   step('dev-runner-tests', [sys.executable, '-m', 'unittest', 'discover',
                                             '-s', 'tests', '-p', 'test_dev*.py', '-v']),
                   step('dev-runner-smoke', [sys.executable, 'tests/dev_runner_smoke.py'],
                        requires=[BUILD / 'bin/data_collector', BUILD / 'libfake_md.so',
                                  PYTHON, 'node', ROOT / 'dashboard/node_modules/vite/bin/vite.js'],
                        timeout=180),
                   step('query', [PYTHON, '-m', 'unittest', 'discover', '-s', 'query/tests', '-t', '.', '-v']),
                   step('data-provider', [PYTHON, '-m', 'unittest', 'discover', '-s', 'data_provider/tests', '-t', '.', '-v']),
                   step('analytics', [PYTHON, '-m', 'unittest', 'discover', '-s', 'analytics/tests', '-t', '.', '-v']),
                   step('universe', [sys.executable, '-m', 'unittest', 'discover', '-s', 'collector/tests', '-p', 'test_*.py', '-v']),
                   step('deploy', [sys.executable, 'collector/tests/deploy_test.py']),
                   step('verify', [sys.executable, 'collector/tests/verify_test.py'], requires=['sqlite3']),
                   step('react', ['npm', 'test'], ROOT / 'dashboard', requires=['node', ROOT / 'dashboard/node_modules/.bin/vitest']),
                   step('frontend-build', ['npm', 'run', 'build'], ROOT / 'dashboard', requires=['node'])]
    else:
        checks += [step('night-session', [PYTHON, 'tests/night_session_smoke.py']),
                   step('read-path', [PYTHON, 'tests/read_path_smoke.py'] + (['--browser'] if profile == 'browser' else []),
                        requires=['node'] if profile == 'browser' else [])]
    return checks


def analytics_contract_steps():
    return [step('analytics-contract-tests', [sys.executable, '-m', 'unittest',
                 'analytics.tests.test_analytics_contract', '-v']),
            step('analytics-contract', [sys.executable, 'analytics/tests/analytics_contract.py'])]


def available(executable):
    if '/' in executable:
        return os.path.isfile(executable) and os.access(executable, os.X_OK)
    return shutil.which(executable) is not None


def run_step(spec, folder):
    record = {k: v for k, v in spec.items() if k != 'requires'}
    record.update(status='NOT_RUN', exit_code=None, duration_seconds=0)
    missing = [p for p in [spec['argv'][0], *spec['requires']] if not available(p)]
    if missing:
        record['reason'] = 'Missing prerequisites: ' + ', '.join(missing)
        return record
    log_path = folder / (spec['name'] + '.log')
    record['log'] = log_path.name
    started = time.monotonic()
    env = dict(os.environ, KEEP_RUNNING='0', PYTHONDONTWRITEBYTECODE='1')
    # Never inherit a caller's synthetic SDK into unrelated commands.
    env.pop('LD_PRELOAD', None)
    env.pop('DM_TEST_SCENARIO', None)
    process = None
    try:
        with log_path.open('wb') as log:
            process = subprocess.Popen(spec['argv'], cwd=spec['cwd'], env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            while True:
                try:
                    process.wait(timeout=min(20, max(.1, spec['timeout'] - (time.monotonic() - started))))
                    break
                except subprocess.TimeoutExpired:
                    elapsed = time.monotonic() - started
                    if elapsed >= spec['timeout']:
                        raise TimeoutError(f'Command exceeded {spec["timeout"]} seconds')
                    print(f'RUNNING {spec["name"]}: {int(elapsed)}s; log={log_path}', flush=True)
        output = log_path.read_text(errors='replace')
        record['exit_code'] = process.returncode
        if process.returncode != 0:
            record.update(status='FAIL', reason='Command returned nonzero; inspect log')
        elif re.search(r'\bNOT RUN\b|\bskipped=\d*[1-9]\d*\b|\b[1-9]\d* skipped\b|\bRan 0 tests\b|No tests were found', output):
            record.update(status='NOT_RUN', reason='Command reported skipped, empty or unexecuted checks')
        else:
            record['status'] = 'PASS'
    except (OSError, TimeoutError, KeyboardInterrupt) as error:
        record.update(status='FAIL', reason=f'{type(error).__name__}: {error}')
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        record['duration_seconds'] = round(time.monotonic() - started, 3)
        if log_path.exists():
            record['log_sha256'] = hashlib.sha256(log_path.read_bytes()).hexdigest()
    return record


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=('docs', 'analytics-contract', 'analytics', 'offline',
                                            'native', 'browser', 'packaging', 'docker'))
    args = parser.parse_args()
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder = ROOT / 'artifacts/verification' / (timestamp + '-' + args.profile + '-' + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    report = dict(schema_version=1, profile=args.profile, started_at_utc=timestamp,
                  revision=git('rev-parse', 'HEAD'), worktree_status=git('status', '--short'),
                  platform=platform.platform(), python=sys.version.split()[0],
                  evidence_kind='STRUCTURAL' if args.profile == 'docs' else 'OFFLINE_OR_SYNTHETIC',
                  mvp_complete=False, steps=[])
    # Preserve changed source and untracked source hashes; never copy configuration/runtime data.
    diff = subprocess.check_output(['git', 'diff', 'HEAD', '--', '.', ':!experiments'], cwd=ROOT)
    (folder / 'worktree.patch').write_bytes(diff)
    report['worktree_patch_sha256'] = hashlib.sha256(diff).hexdigest()
    untracked = git('ls-files', '--others', '--exclude-standard').splitlines()
    report['untracked_source_sha256'] = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                                       for p in untracked if (ROOT / p).is_file()}
    report_path = folder / 'result.json'
    blocked = False
    for spec in profiles(args.profile):
        if blocked:
            result = dict(name=spec['name'], status='NOT_RUN', reason='Earlier required step did not pass')
        else:
            print('RUN', spec['name'], flush=True)
            result = run_step(spec, folder)
            print(result['status'], spec['name'], result.get('reason', ''), flush=True)
        report['steps'].append(result)
        blocked = blocked or result['status'] != 'PASS'
        report['status'] = 'IN_PROGRESS'
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    statuses = {s['status'] for s in report['steps']}
    report['status'] = 'FAIL' if 'FAIL' in statuses else 'NOT_RUN' if 'NOT_RUN' in statuses else 'PASS'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f'{report["status"]}: {report_path}\nScope is this profile only. MVP/live gates remain manual.', flush=True)
    return 0 if report['status'] == 'PASS' else 1 if report['status'] == 'FAIL' else 2


if __name__ == '__main__':
    raise SystemExit(main())
