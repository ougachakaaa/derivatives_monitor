#!/usr/bin/env python3
"""Check maintained documentation, archived originals and required build inputs.

No network, data directory reads, service management or experiments mutations.
Docker ignore checks deliberately cover this repository's simple glob allowlist;
real Docker semantics and COPY are additionally exercised by the docker profile.
"""
import fnmatch
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote

from docker_boundaries import BOUNDARIES, FORBIDDEN_SAMPLES

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = (
    'README.md',
    'AGENTS.md',
    'docs/README.md',
    'docs/mvp.md',
    'docs/design.md',
    'docs/architecture.md',
    'docs/acceptance.md',
    'docs/operations.md',
    'docs/references/README.md',
    'docs/archive/README.md',
    'harness/README.md',
    'harness/live-acceptance-template.md',
    'compose.yaml',
    'scripts/deploy.sh',
    *(f'docs/contracts/{name}.md' for name in
      ('collector', 'read-path', 'market-state', 'market-session', 'deployment', 'analytics-skew')),
    'docs/contracts/analytics-skew-v1.json',
    'docs/references/analytics-skew-sources.md',
    'harness/fixtures/analytics-skew-v1.json',
)

# These production entrypoints are not image inputs, so the Docker boundary
# manifest cannot supply them to the dependency-direction check.
NON_IMAGE_PRODUCTION_INPUTS = (
    'compose.yaml',
    'scripts/deploy.sh',
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
            if Path(relative).parts[:1] == ('experiments',):
                errors.append(
                    f'{service} Docker input is experiment-owned: {relative}; formal images must only '
                    'consume production-owned inputs (docs/architecture.md, docs/contracts/deployment.md)'
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
                    '(docs/architecture.md, docs/contracts/deployment.md)'
                )
    return errors


def check(root=ROOT):
    errors = []
    for relative in REQUIRED_PATHS:
        if not (root / relative).is_file():
            errors.append('Missing document: ' + relative)
    if (root / 'docs/tasks').exists():
        errors.append('Deprecated process specs must not return under docs/tasks; '
                      'use the durable authority map in docs/README.md')
    if (root / 'collector/compose.yaml').exists():
        errors.append('Deprecated collector/compose.yaml exists; system Compose is owned by '
                      'compose.yaml (docs/contracts/deployment.md)')
    if (root / 'collector/scripts' / 'deploy.sh').exists():
        errors.append('Deprecated collector/scripts/deploy.sh exists; system deployment is owned by '
                      'scripts/deploy.sh (docs/contracts/deployment.md)')
    errors.extend(production_dependency_errors(root))
    files = [root / p for p in ('README.md', 'AGENTS.md', 'collector/README.md',
                               'query/README.md', 'query/calendars/README.md', 'dashboard/README.md')]
    files += list((root / 'docs').rglob('*.md')) + list((root / 'harness').rglob('*.md'))
    for path in files:
        if not path.is_file():
            continue
        content = re.sub(r'```.*?```', '', path.read_text(), flags=re.S)
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', content):
            target = target.strip('<>')
            if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', target) or target.startswith('#'):
                continue
            relative = unquote(target.split('#', 1)[0])
            if relative and not (path.parent / relative).exists():
                errors.append(f'{path.relative_to(root)}: broken link {target}')
    manifest_path = root / 'docs/references/originals/manifest.json'
    try:
        manifest = json.loads(manifest_path.read_text())
        for artifact in manifest['artifacts']:
            path = manifest_path.parent / artifact['path']
            if hashlib.sha256(path.read_bytes()).hexdigest() != artifact['sha256']:
                errors.append('Archived original hash mismatch: ' + artifact['path'])
    except (OSError, ValueError, KeyError) as error:
        errors.append('Reference manifest invalid: ' + str(error))
    sdk = root / 'collector/third_party/ctp/v6.7.13_20260225'
    try:
        entries = dict(line.split('=', 1) for line in (sdk / 'MANIFEST.txt').read_text().splitlines() if '=' in line)
        for name in ('ThostFtdcMdApi.h', 'ThostFtdcUserApiDataType.h', 'ThostFtdcUserApiStruct.h', 'thostmduserapi_se.so'):
            key = name + ('.sha256' if name.endswith('.so') else '.repository_sha256')
            if hashlib.sha256((sdk / 'linux64/mdapi' / name).read_bytes()).hexdigest() != entries[key]:
                errors.append('SDK hash mismatch: ' + name)
    except (OSError, ValueError, KeyError) as error:
        errors.append('SDK manifest invalid: ' + str(error))
    if (root / '.dockerignore').exists():
        errors.append('Root .dockerignore must not own formal image boundaries')
    for service, inputs in BOUNDARIES.items():
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
        print('PASS: maintained links, authority entrypoints, dependency direction, hashes and per-image Docker allowlists')
        print('Scope: offline structural checks; no external URL availability, Markdown anchors or business correctness claim.')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
