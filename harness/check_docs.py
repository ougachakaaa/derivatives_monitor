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

ROOT = Path(__file__).resolve().parents[1]


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


def check(root=ROOT):
    errors = []
    required = ['README.md', 'AGENTS.md', 'docs/README.md', 'docs/mvp.md',
                'docs/architecture.md', 'docs/acceptance.md', 'docs/operations.md',
                'docs/references/README.md', 'docs/archive/README.md',
                'harness/README.md', 'harness/live-acceptance-template.md']
    required += ['docs/contracts/' + name + '.md' for name in
                 ('collector', 'read-path', 'market-state', 'market-session', 'deployment', 'analytics-skew')]
    required += ['docs/contracts/analytics-skew-v1.json', 'docs/references/analytics-skew-sources.md',
                 'harness/fixtures/analytics-skew-v1.json']
    for relative in required:
        if not (root / relative).is_file():
            errors.append('Missing document: ' + relative)
    if (root / 'docs/tasks').exists():
        errors.append('Process specs must not return under docs/tasks; maintain the durable design.')
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
    rules = (root / '.dockerignore').read_text().splitlines()
    # Explicit COPY inputs and all tracked Python test/source/calendar files in Query.
    inputs = [str(p.relative_to(root)) for p in (root / 'query').glob('*.py')]
    inputs += [str(p.relative_to(root)) for p in (root / 'query/tests').glob('*.py')]
    inputs += [str(p.relative_to(root)) for p in (root / 'query/calendars').glob('*.json')]
    inputs += ['query/pyproject.toml', 'query/poetry.lock', 'collector/src/main.cpp',
               'collector/cmake/ctp_sdk.cmake', 'collector/include/client_support.hpp',
               'collector/third_party/ctp/v6.7.13_20260225/MANIFEST.txt',
               'dashboard/src/App.jsx',
               'collector/third_party/ctp/v6.7.13_20260225/linux64/mdapi/thostmduserapi_se.so']
    for path in inputs:
        if not docker_included(path, rules):
            errors.append('Required Docker input excluded: ' + path)
    for path in ('collector/config.ini', 'collector/data/sample.sqlite', 'collector/flow/state',
                 'query/secrets.json', 'query/tests/private.log', 'dashboard/.env',
                 'docs/references/originals/csc-ctp-mvp-questions-and-replies.docx',
                 'artifacts/harness/result.json'):
        if docker_included(path, rules):
            errors.append('Private/runtime Docker input included: ' + path)
    return errors


def main():
    errors = check()
    for error in errors:
        print('FAIL:', error)
    if not errors:
        print('PASS: maintained local file links, design entrypoints, original/SDK hashes, Docker input allowlist')
        print('Scope: offline structural checks; no external URL availability, Markdown anchors or business correctness claim.')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
