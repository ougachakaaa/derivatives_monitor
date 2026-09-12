#!/usr/bin/env python3
"""Export and verify Docker contexts from their owner-maintained policies."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ('collector', 'query', 'dashboard')
SENSITIVE_SUFFIXES = ('.key', '.pem', '.p12', '.pfx', '.db', '.log')
RUNTIME_PARTS = {'data', 'flow', 'build', 'dist', 'node_modules', '__pycache__',
                 'tmp', 'artifacts'}


def declared_files(service, root=ROOT):
    """Read literal file allow rules; Docker itself remains the matching authority."""
    policy = root / service / 'Dockerfile.dockerignore'
    files = set()
    for raw in policy.read_text().splitlines():
        rule = raw.strip()
        if not rule.startswith('!'):
            continue
        relative = rule[1:].lstrip('/').rstrip('/')
        if any(character in relative for character in '*?['):
            continue
        path = root / relative
        if path.is_file():
            files.add(relative)
    return files


def validate_declared(service, expected, root=ROOT):
    tracked = set(subprocess.check_output(
        ['git', 'ls-files', '--', service], cwd=root, text=True).splitlines())
    for relative in expected:
        path = Path(relative)
        if path.parts[0] != service:
            raise AssertionError(f'{service} context crosses owner boundary: {relative}')
        if relative not in tracked:
            raise AssertionError(f'{service} context input is not version controlled: {relative}')
        name = path.name
        sensitive = (name == 'config.ini' or name == '.env' or name.startswith('.env.')
                     or name.startswith('credentials.') or name.startswith('secrets.')
                     or '.sqlite' in name or name.endswith('.db-wal')
                     or path.suffix in SENSITIVE_SUFFIXES or RUNTIME_PARTS.intersection(path.parts))
        if sensitive:
            raise AssertionError(f'{service} context exposes sensitive/runtime input: {relative}')


def main():
    with tempfile.TemporaryDirectory(prefix='dm-build-context-') as temporary:
        for service in SERVICES:
            expected = declared_files(service)
            validate_declared(service, expected)
            destination = Path(temporary) / service
            subprocess.run([
                'docker', 'build', '--network=none', '--pull=false',
                '--target', 'context-audit',
                '--output', 'type=local,dest=' + str(destination),
                '--file', f'{service}/Dockerfile', str(ROOT),
            ], check=True, timeout=120)
            actual = {path.relative_to(destination).as_posix()
                      for path in destination.rglob('*') if path.is_file()}
            if actual != expected:
                raise AssertionError(
                    f'{service} context mismatch; missing={sorted(expected - actual)}, '
                    f'extra={sorted(actual - expected)}')
            for relative in expected:
                if (destination / relative).read_bytes() != (ROOT / relative).read_bytes():
                    raise AssertionError(f'{service} context changed input bytes: {relative}')
            size = sum((destination / relative).stat().st_size for relative in expected)
            print(f'PASS: {service} context contains exactly {len(expected)} policy-declared files ({size} bytes)')
        print('Scope: actual Dockerfile-specific context filtering only; no runtime or live CTP claim.')


if __name__ == '__main__':
    main()
