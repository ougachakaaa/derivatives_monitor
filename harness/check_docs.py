#!/usr/bin/env python3
"""Check maintained documentation and required build inputs.

No network, data directory reads, service management or experiments mutations.
Docker ignore checks deliberately cover this repository's simple glob allowlist;
real Docker semantics and COPY are additionally exercised by the docker profile.
"""
import ast
import fnmatch
import hashlib
import os
from collections import Counter
from pathlib import Path
import re
from urllib.parse import unquote

from docker_boundaries import BOUNDARIES, FORBIDDEN_SAMPLES

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = (
    'README.md', 'AGENTS.md', 'docs/README.md', 'docs/mvp.md',
    'DESIGN.md', 'ARCHITECTURE.md', 'docs/operations.md',
    'harness/README.md', 'harness/CONTRACT.md',
    'compose.yaml', 'dev', 'scripts/deploy.sh', 'scripts/dev.py',
    *(f'{module}/CONTRACT.md' for module in
      ('collector', 'collector/scripts', 'query', 'dashboard', 'monitoring')),
    *(f'docs/contracts/{name}.md' for name in
      ('raw-boundary', 'read-path', 'market-session', 'deployment',
       'developer-runner', 'features')),
    *(f'query/contracts/{name}' for name in
      ('market-state.md', 'analytics-skew.md', 'analytics-skew-v1.json', 'references.md')),
    'harness/fixtures/analytics-skew-v1.json',
)

# These production entrypoints are not image inputs, so the Docker boundary
# manifest cannot supply them to the dependency-direction check.
NON_IMAGE_PRODUCTION_INPUTS = (
    'compose.yaml',
    'dev',
    'scripts/deploy.sh',
    'scripts/dev.py',
    'collector/scripts/native.py',
    'collector/scripts/native.sh',
    'collector/scripts/universe.py',
)

EXPERIMENT_PATH = re.compile(r'(?<![A-Za-z0-9_-])experiments[/\\]')
EXPERIMENT_IMPORT = re.compile(r'^\s*(?:from|import)\s+experiments(?:\.|\s|$)')


def docker_included(relative, rules):
    included = True
    # The repository uses anchored simple globs (including **) and no escapes.
    for rule in rules:
        if not rule or rule.startswith('#'):
            continue
        allow = rule.startswith('!')
        pattern = rule.lstrip('!').strip('/')
        candidates = [relative, *[str(p) for p in Path(relative).parents if str(p) != '.']]
        if any(fnmatch.fnmatchcase(candidate, pattern) for candidate in candidates):
            included = allow
    return included


def production_dependency_errors(root=ROOT, boundaries=BOUNDARIES):
    """Reject formal build/runtime inputs that depend on experiment-owned paths."""
    errors = []
    inputs = set(NON_IMAGE_PRODUCTION_INPUTS)
    for service, declared_inputs in boundaries.items():
        for relative in declared_inputs:
            target = Path(relative).parts[0]
            if target in MODULES | {'harness'} and target != service and not (
                    service == 'query' and relative == 'harness/fixtures/analytics-skew-v1.json'):
                errors.append(f'{service} Docker input crosses module boundary: {relative} (ARCHITECTURE.md)')
            if Path(relative).parts[:1] == ('experiments',):
                errors.append(
                    f'{service} Docker input is experiment-owned: {relative}; formal images must only '
                    'consume production-owned inputs (ARCHITECTURE.md, docs/contracts/deployment.md)'
                )
            if '/tests/' not in relative and '/third_party/' not in relative \
                    and not relative.endswith('Dockerfile.dockerignore') \
                    and not relative.startswith('harness/'):
                inputs.add(relative)

    for relative in sorted(inputs):
        path = root / relative
        if not path.is_file():
            continue
        try:
            lines = path.read_text(errors='replace').splitlines()
        except OSError as error:
            errors.append(f'{relative}: production dependency input unavailable: {error}')
            continue
        for line_number, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith(('//', '/*', '*', '<!--')) \
                    or (stripped.startswith('#') and not stripped.startswith('#include')):
                continue
            if EXPERIMENT_PATH.search(line) or EXPERIMENT_IMPORT.search(line):
                errors.append(
                    f'{relative}:{line_number}: production dependency points into experiments/; '
                    'move the dependency to a production-owned path '
                    '(ARCHITECTURE.md, docs/contracts/deployment.md)'
                )
    return errors


def _explicit_anchors(text: str):
    return set(re.findall(r'<a\s+(?:name|id)=["\']([^"\']+)["\']\s*>', text, re.I))


def _heading_slug(title: str):
    title = re.sub(r'[`*_~]', '', title.strip().lower())
    title = re.sub(r'[^\w\-\u4e00-\u9fff ]', '', title)
    return re.sub(r'[\s-]+', '-', title).strip('-')


def markdown_anchors(text: str):
    anchors = _explicit_anchors(text)
    counts = Counter()
    for title in re.findall(r'^#{1,6}\s+(.+?)\s*#*$', text, re.M):
        base = _heading_slug(title)
        if not base:
            continue
        suffix = counts[base]
        counts[base] += 1
        anchors.add(base if suffix == 0 else f'{base}-{suffix}')
    return anchors


def markdown_links(text: str):
    """Return inline and reference-style Markdown targets outside code fences."""
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    definitions = {
        key.lower(): target.strip('<>')
        for key, target in re.findall(r'^\s*\[([^]]+)\]:\s*(\S+)', text, re.M)
    }
    targets = [target.strip('<>') for target in re.findall(r'(?<!!)\[[^]]+\]\(([^)]+)\)', text)]
    for key in re.findall(r'(?<!!)\[[^]]+\]\[([^]]*)\]', text):
        if key.lower() in definitions:
            targets.append(definitions[key.lower()])
    return targets


def link_and_anchor_errors(root: Path, markdown_paths):
    errors = []
    for relative in sorted(set(markdown_paths)):
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(errors='replace')
        for raw_target in markdown_links(text):
            target = raw_target.split(None, 1)[0]
            if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', target):
                continue
            file_part, marker, anchor = unquote(target).partition('#')
            destination = path if not file_part else path.parent / file_part
            if not destination.exists():
                errors.append(f'{relative}: broken link {raw_target}')
                continue
            if marker and anchor:
                if not destination.is_file() or destination.suffix.lower() not in ('.md', '.markdown'):
                    errors.append(f'{relative}: anchor target is not Markdown: {raw_target}')
                elif anchor not in markdown_anchors(destination.read_text(errors='replace')):
                    errors.append(f'{relative}: missing anchor {raw_target}')
    return errors


# Scan source trees only: never traverse live data, SDKs or build dependencies.
EXCLUDED_DIRS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__',
                 'build', 'dist', 'artifacts', 'data', 'flow', 'logs',
                 'third_party', 'experiments', '.cache'}
MODULES = {'collector', 'query', 'dashboard', 'monitoring'}


def source_files(root, folders):
    for folder in folders:
        for directory, dirs, files in os.walk(root / folder):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
            for name in sorted(files):
                yield Path(directory) / name


def maintained_markdown(root):
    paths = list(root.glob('*.md'))
    paths.extend(p for p in source_files(root, sorted(MODULES | {'docs', 'harness'}))
                 if p.suffix == '.md')
    return [p.relative_to(root).as_posix() for p in paths]


def module_dependency_errors(root=ROOT):
    """Check runtime imports directly against the system's component boundaries.

    Universe's pure Calendar dependency is the sole cross-module Python import.
    Deployment tools may launch components; they are not Collector runtime.
    """
    errors = []
    for path in source_files(root, sorted(MODULES)):
        relative = path.relative_to(root)
        if 'tests' in relative.parts:
            continue
        owner = relative.parts[0]
        targets = set()
        if path.suffix == '.py':
            content = path.read_text(errors='replace')
            try:
                tree = ast.parse(content)
            except SyntaxError as error:
                errors.append(f'{relative}: cannot inspect Python imports: {error}')
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and not node.level:
                    targets.add(node.module or '')
                elif isinstance(node, ast.Import):
                    targets.update(alias.name for alias in node.names)
            for target in sorted(targets):
                other = target.split('.')[0]
                # universe.py bootstraps query/ on sys.path to import Calendar.
                if target == 'market_calendar' and owner != 'query':
                    other = 'query'
                if other not in MODULES | {'harness', 'experiments'} or other == owner:
                    continue
                if relative.as_posix() == 'collector/scripts/universe.py' and target in (
                        'market_calendar', 'query.market_calendar'):
                    continue
                errors.append(f'{relative}: forbidden module dependency: {target} (ARCHITECTURE.md)')
        elif (path.suffix in {'.c', '.cc', '.cpp', '.h', '.hpp', '.cmake'}
              or path.name == 'CMakeLists.txt') and owner == 'collector':
            content = path.read_text(errors='replace')
            for line in content.splitlines():
                if line.lstrip().startswith(('# ', '//', '/*', '*')):
                    continue
                if re.search(r'(?<![\w-])(?:query|dashboard|monitoring|experiments)[/\\]', line):
                    errors.append(f'{relative}: Collector runtime depends on another component (ARCHITECTURE.md)')
    return errors


def check(root=ROOT):
    errors = []
    for relative in REQUIRED_PATHS:
        if not (root / relative).is_file():
            errors.append('Missing document: ' + relative)
    if (root / 'collector/compose.yaml').exists():
        errors.append('Deprecated collector/compose.yaml exists; system Compose is owned by '
                      'compose.yaml (docs/contracts/deployment.md)')
    if (root / 'collector/scripts' / 'deploy.sh').exists():
        errors.append('Deprecated collector/scripts/deploy.sh exists; system deployment is owned by '
                      'scripts/deploy.sh (docs/contracts/deployment.md)')
    errors.extend(production_dependency_errors(root))
    errors.extend(module_dependency_errors(root))
    errors.extend(link_and_anchor_errors(root, maintained_markdown(root)))
    errors.extend(sdk_errors(root))
    errors.extend(docker_boundary_errors(root))

    return errors


def sdk_errors(root=ROOT):
    errors = []
    sdk = root / 'collector/third_party/ctp/v6.7.13_20260225'
    try:
        entries = dict(line.split('=', 1) for line in (sdk / 'MANIFEST.txt').read_text().splitlines() if '=' in line)
        for name in ('ThostFtdcMdApi.h', 'ThostFtdcUserApiDataType.h', 'ThostFtdcUserApiStruct.h', 'thostmduserapi_se.so'):
            key = name + ('.sha256' if name.endswith('.so') else '.repository_sha256')
            if hashlib.sha256((sdk / 'linux64/mdapi' / name).read_bytes()).hexdigest() != entries[key]:
                errors.append('SDK hash mismatch: ' + name)
    except (OSError, ValueError, KeyError) as error:
        errors.append('SDK manifest invalid: ' + str(error))
    return errors


def docker_boundary_errors(root=ROOT, boundaries=BOUNDARIES):
    errors = []
    if (root / '.dockerignore').exists():
        errors.append('Root .dockerignore must not own formal image boundaries')
    for service, inputs in boundaries.items():
        policy_path = root / service / 'Dockerfile.dockerignore'
        try:
            rules = policy_path.read_text().splitlines()
        except OSError as error:
            errors.append(f'{service} Docker boundary unavailable: {error}')
            continue
        active_rules = [line.strip() for line in rules if line.strip() and not line.startswith('#')]
        if not active_rules or active_rules[0] != '**':
            errors.append(f'{service} Docker boundary must start deny-by-default with **')
        for path in inputs:
            if not (root / path).is_file():
                errors.append(f'{service} Docker input missing: {path}')
            elif not docker_included(path, rules):
                errors.append(f'{service} Docker input excluded: {path}')
        for path in FORBIDDEN_SAMPLES:
            if docker_included(path, rules):
                errors.append(f'{service} Docker boundary exposes private/unrelated input: {path}')
    return errors


def main():
    errors = check()
    for error in errors:
        print('FAIL:', error)
    if not errors:
        print('PASS: links/anchors, module dependencies, SDK hashes and Docker allowlists')
        print('Scope: offline structural checks; no external URL availability or business correctness claim.')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
