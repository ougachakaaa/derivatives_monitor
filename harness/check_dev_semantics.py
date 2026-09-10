#!/usr/bin/env python3
"""Opt-in migration acceptance. Temporary TEST DOUBLE config; no market connection."""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def invoke(*args):
    return subprocess.run([str(ROOT / 'dev'), *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=30)


def credentials():
    binary = ROOT / 'collector/build/Release/bin/data_collector'
    if not binary.is_file():
        print('NOT_RUN credentials: Collector Release build missing')
        return 2
    for fields in ('', 'UserID=\nPassword=\n'):
        with tempfile.TemporaryDirectory(prefix='dm-semantics-') as folder:
            config = Path(folder) / 'config.ini'
            content = ('# TEST DOUBLE: configuration only; no connection\n[config]\n'
                       'FrontMdAddr=tcp://127.0.0.1:1\nInstruments=IF2609\n'
                       'DataDirectory=data\nFlowPath=flow\n' + fields)
            config.write_text(content)
            result = invoke('doctor', 'collector', '--config', str(config))
            output = result.stdout + result.stderr
            if result.returncode or 'userid' in output.lower() or 'password' in output.lower():
                print('FAIL credentials: optional fields must not become diagnostic items')
                return 1
            if config.read_text() != content or set(Path(folder).iterdir()) != {config}:
                print('FAIL credentials: diagnostic changed persistent files')
                return 1
    print('PASS credentials: omitted/empty fields; no persistent writes (TEST DOUBLE)')
    return 0


def cli():
    failed = False
    for component in ('collector', 'query', 'dashboard'):
        result = invoke('up', component, '--help')
        if result.returncode or f'usage: dev up {component}' not in result.stdout:
            print(f'FAIL cli: up {component} --help')
            failed = True
        # --help makes this safe even against the old, still accepted CLI.
        result = invoke(component, '--help')
        if result.returncode != 2 or f'up {component}' not in result.stdout + result.stderr:
            print(f'FAIL cli: retired {component} must return 2 with migration hint')
            failed = True
    for args in (('--help',), ('up', '--help'), ('doctor', '--help')):
        if invoke(*args).returncode:
            print(f'FAIL cli: {args}')
            failed = True
    if not failed:
        print('PASS cli: public help and retired-command boundary; no services started')
    return int(failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=('credentials', 'cli', 'all'), default='all')
    args = parser.parse_args()
    results = []
    for name, check in (('credentials', credentials), ('cli', cli)):
        if args.scope in (name, 'all'):
            try:
                results.append(check())
            except (OSError, subprocess.TimeoutExpired) as error:
                print(f'NOT_RUN {name}: {type(error).__name__}')
                results.append(2)
    return 1 if 1 in results else 2 if 2 in results else 0


if __name__ == '__main__':
    raise SystemExit(main())
