#!/usr/bin/env python3
"""Verify the actual Docker context with a scratch build, without registry access."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='dm-build-context-') as temporary:
        destination = Path(temporary) / 'export'
        subprocess.run(['docker', 'build', '--network=none', '--pull=false',
                        '--output', 'type=local,dest=' + str(destination),
                        '-f', '-', str(ROOT)], input='FROM scratch\nCOPY . /\n',
                       text=True, check=True, timeout=120)
        expected = ['query/app.py', 'query/storage.py', 'query/contract_coverage.py',
                    'query/market_calendar.py', 'query/market_state.py', 'query/calendars/2026.json',
                    'query/poetry.lock', 'collector/src/main.cpp', 'dashboard/src/App.jsx',
                    'experiments/ctp/sdk/v6.7.13_20260225/linux64/mdapi/thostmduserapi_se.so']
        for relative in expected:
            original, exported = ROOT / relative, destination / relative
            if not exported.is_file() or exported.read_bytes() != original.read_bytes():
                raise AssertionError('Missing or changed build input: ' + relative)
        for relative in ('collector/config.ini', 'collector/data', 'collector/flow', 'collector/build',
                         'docs', 'artifacts', 'dashboard/node_modules', 'query/.venv', '.git'):
            if (destination / relative).exists():
                raise AssertionError('Private/runtime files entered context: ' + relative)
        for path in destination.rglob('*'):
            if path.is_file() and (path.name.startswith(('.env', 'credentials.', 'secrets.'))
                                   or path.name.endswith(('.log', '.pem', '.key'))
                                   or '.sqlite' in path.name):
                raise AssertionError('Private/runtime file entered context: ' + str(path.relative_to(destination)))
        print('PASS: actual Docker COPY preserves required source/calendar/SDK bytes and excludes runtime/private directories')
        print('Scope: scratch build context only; no runtime image, container lifecycle or live CTP claim.')


if __name__ == '__main__':
    main()
