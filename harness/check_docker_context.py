#!/usr/bin/env python3
"""Export and verify each Dockerfile-specific context without registry access."""
from pathlib import Path
import subprocess
import tempfile

from docker_boundaries import BOUNDARIES

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='dm-build-context-') as temporary:
        for service, expected_inputs in BOUNDARIES.items():
            destination = Path(temporary) / service
            subprocess.run([
                'docker', 'build', '--network=none', '--pull=false',
                '--target', 'context-audit',
                '--output', 'type=local,dest=' + str(destination),
                '--file', f'{service}/Dockerfile', str(ROOT),
            ], check=True, timeout=120)
            expected = set(expected_inputs)
            actual = {str(path.relative_to(destination)) for path in destination.rglob('*') if path.is_file()}
            if actual != expected:
                missing = sorted(expected - actual)
                extra = sorted(actual - expected)
                raise AssertionError(f'{service} context mismatch; missing={missing}, extra={extra}')
            for relative in expected:
                original, exported = ROOT / relative, destination / relative
                if exported.read_bytes() != original.read_bytes():
                    raise AssertionError(f'{service} context changed input bytes: {relative}')
            size = sum((destination / relative).stat().st_size for relative in expected)
            print(f'PASS: {service} context contains exactly {len(expected)} declared files ({size} bytes)')
        print('Scope: actual Dockerfile-specific context filtering only; no runtime or live CTP claim.')


if __name__ == '__main__':
    main()
