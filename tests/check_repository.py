#!/usr/bin/env python3
"""Check repository ownership, dependency direction, and packaging policy shape."""
import ast
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MODULES = {'collector', 'data_provider', 'query', 'dashboard'}
EXCLUDED_DIRS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__',
                 'build', 'dist', 'artifacts', 'data', 'flow', 'logs',
                 'third_party', 'experiments', '.cache'}
EXPERIMENT_PATH = re.compile(r'(?<![A-Za-z0-9_-])experiments[/\\]')
EXPERIMENT_IMPORT = re.compile(r'^\s*(?:from|import)\s+experiments(?:\.|\s|$)')
LEGACY_VERIFICATION_PATH = re.compile(r'(?<![A-Za-z0-9_-])harness[/\\]')
REPOSITORY_ENTRYPOINTS = ('compose.yaml', 'dev', 'scripts/deploy.sh', 'scripts/dev.py')


def source_files(root, folders):
    for folder in folders:
        if not (root / folder).is_dir():
            continue
        for directory, dirs, files in os.walk(root / folder):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
            for name in sorted(files):
                yield Path(directory) / name


def production_dependency_errors(root=ROOT):
    """Reject production/build inputs that point into experiment-owned paths."""
    errors = []
    paths = [root / relative for relative in REPOSITORY_ENTRYPOINTS]
    production_suffixes = {'.py', '.sh', '.c', '.cc', '.cpp', '.h', '.hpp',
                           '.cmake', '.yaml', '.yml'}
    production_names = {'CMakeLists.txt', 'Dockerfile', 'Dockerfile.dockerignore'}
    paths.extend(path for path in source_files(root, sorted(MODULES))
                 if 'tests' not in path.relative_to(root).parts
                 and (path.suffix in production_suffixes or path.name in production_names))
    for path in sorted(set(paths)):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        for line_number, line in enumerate(path.read_text(errors='replace').splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith(('//', '/*', '*', '<!--')) \
                    or (stripped.startswith('#') and not stripped.startswith('#include')):
                continue
            if EXPERIMENT_PATH.search(line) or EXPERIMENT_IMPORT.search(line):
                errors.append(f'{relative}:{line_number}: production dependency points into experiments/; '
                              'move it to a production-owned path (ARCHITECTURE.md, docs/contracts/deployment.md)')
            if LEGACY_VERIFICATION_PATH.search(line):
                errors.append(f'{relative}:{line_number}: production dependency points into the retired '
                              'top-level verification directory (ARCHITECTURE.md)')
    return errors


def module_dependency_errors(root=ROOT):
    errors = []
    for path in source_files(root, sorted(MODULES)):
        relative = path.relative_to(root)
        if 'tests' in relative.parts:
            continue
        owner = relative.parts[0]
        if path.suffix == '.py':
            try:
                tree = ast.parse(path.read_text(errors='replace'))
            except SyntaxError as error:
                errors.append(f'{relative}: cannot inspect Python imports: {error}')
                continue
            targets = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and not node.level:
                    targets.add(node.module or '')
                elif isinstance(node, ast.Import):
                    targets.update(alias.name for alias in node.names)
            for target in sorted(targets):
                other = target.split('.')[0]
                if other in {'harness', 'tests'}:
                    errors.append(f'{relative}: production imports repository verification: {target} '
                                  '(ARCHITECTURE.md)')
                    continue
                if other not in MODULES or other == owner:
                    continue
                if owner == 'query' and other == 'data_provider':
                    continue
                if relative.as_posix() == 'collector/scripts/universe.py' \
                        and target == 'data_provider.market_calendar':
                    continue
                errors.append(f'{relative}: forbidden module dependency: {target} (ARCHITECTURE.md)')
        elif (path.suffix in {'.c', '.cc', '.cpp', '.h', '.hpp', '.cmake'}
              or path.name == 'CMakeLists.txt') and owner == 'collector':
            for line in path.read_text(errors='replace').splitlines():
                if line.lstrip().startswith(('# ', '//', '/*', '*')):
                    continue
                if re.search(r'(?<![\w-])(?:query|dashboard|experiments)[/\\]', line):
                    errors.append(f'{relative}: Collector runtime depends on another component (ARCHITECTURE.md)')
    return errors


def packaging_policy_errors(root=ROOT):
    """Validate policy ownership without reproducing Docker ignore matching semantics."""
    errors = []
    if (root / '.dockerignore').exists():
        errors.append('Root .dockerignore must not own formal image boundaries')
    for service in ('collector', 'query', 'dashboard'):
        policy = root / service / 'Dockerfile.dockerignore'
        if not policy.is_file():
            errors.append(f'{service}: missing Dockerfile.dockerignore')
            continue
        rules = [line.strip() for line in policy.read_text().splitlines()
                 if line.strip() and not line.lstrip().startswith('#')]
        if not rules or rules[0] != '**':
            errors.append(f'{service}: Docker boundary must start deny-by-default with **')
        for rule in rules[1:]:
            if not rule.startswith('!'):
                continue
            allowed = rule[1:].lstrip('/')
            roots = {service, 'data_provider'} if service == 'query' else {service}
            if '..' in Path(allowed).parts or not any(
                    allowed == root or allowed.startswith(root + '/') for root in roots):
                errors.append(f'{service}: Docker allow rule crosses owner boundary: {rule}')
            if 'experiments/' in allowed:
                errors.append(f'{service}: Docker allow rule exposes experiments: {rule}')
    return errors


def check(root=ROOT):
    errors = []
    if (root / 'collector/compose.yaml').exists():
        errors.append('Deprecated collector/compose.yaml exists; compose.yaml owns system composition')
    if (root / 'collector/scripts/deploy.sh').exists():
        errors.append('Deprecated collector/scripts/deploy.sh exists; scripts/deploy.sh owns deployment')
    errors.extend(production_dependency_errors(root))
    errors.extend(module_dependency_errors(root))
    errors.extend(packaging_policy_errors(root))
    return errors


def main():
    errors = check()
    for error in errors:
        print('FAIL:', error)
    if not errors:
        print('PASS: repository ownership, dependency direction, and Docker policy ownership')
        print('Scope: structural invariants only; Docker filtering is exercised by the packaging profile.')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
