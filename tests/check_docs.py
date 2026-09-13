#!/usr/bin/env python3
"""Check maintained documentation links, anchors, and required authorities."""
import os
from collections import Counter
from pathlib import Path
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PATHS = (
    'README.md', 'AGENTS.md', 'DESIGN.md', 'ARCHITECTURE.md',
    'docs/README.md', 'docs/mvp.md', 'docs/operations.md',
    'docs/acceptance.md', 'docs/verification.md', 'docs/live-acceptance-template.md',
    'tests/README.md', 'tests/run.py', 'compose.yaml', 'dev',
    'scripts/deploy.sh', 'scripts/dev.py',
    *(f'{module}/CONTRACT.md' for module in
      ('collector', 'collector/scripts', 'data_provider', 'query', 'dashboard')),
    *(f'docs/contracts/{name}.md' for name in
      ('raw-boundary', 'read-path', 'market-session', 'deployment',
       'developer-runner', 'indicators')),
    *(f'query/contracts/{name}' for name in
      ('market-frame.md', 'analytics-skew.md', 'analytics-skew-v1.json', 'references.md')),
    'query/tests/fixtures/analytics-skew-v1.json',
)
EXCLUDED_DIRS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__',
                 'build', 'dist', 'artifacts', 'data', 'flow', 'logs',
                 'third_party', 'experiments', '.cache'}
MAINTAINED_FOLDERS = {'collector', 'data_provider', 'query', 'dashboard', 'docs', 'tests'}
TEXT_SUFFIXES = {'.md', '.py', '.js', '.jsx', '.cpp', '.hpp', '.h', '.sh', '.cmake', '.txt', '.yaml', '.yml'}
TEXT_NAMES = {'Dockerfile', 'Dockerfile.dockerignore', 'compose.yaml', 'dev'}
LEGACY_PATHS = (
    'docs/contracts/' + 'fea' + 'tures.md',
    'query/' + 'market_' + 'state.py',
    'query/' + 'fea' + 'ture_service.py',
    'query/contracts/' + 'market-' + 'state.md',
    'query/tests/test_' + 'market_' + 'state.py',
    'query/tests/test_' + 'fea' + 'ture_service.py',
    'query/tests/test_' + 'fea' + 'tures_api.py',
)


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
            elif marker and anchor:
                if not destination.is_file() or destination.suffix.lower() not in ('.md', '.markdown'):
                    errors.append(f'{relative}: anchor target is not Markdown: {raw_target}')
                elif anchor not in markdown_anchors(destination.read_text(errors='replace')):
                    errors.append(f'{relative}: missing anchor {raw_target}')
    return errors


def source_files(root, folders):
    for folder in folders:
        if not (root / folder).is_dir():
            continue
        for directory, dirs, files in os.walk(root / folder):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
            for name in sorted(files):
                yield Path(directory) / name


def maintained_markdown(root):
    paths = list(root.glob('*.md'))
    paths.extend(p for p in source_files(root, sorted(MAINTAINED_FOLDERS))
                 if p.suffix == '.md')
    return [p.relative_to(root).as_posix() for p in paths]


def terminology_errors(root: Path):
    """Reject superseded market-analysis names from maintained source and docs."""
    errors = [f'Deprecated market-analysis path still exists: {relative}'
              for relative in LEGACY_PATHS if (root / relative).exists()]
    paths = [p for p in root.iterdir() if p.is_file()]
    paths.extend(source_files(root, sorted(MAINTAINED_FOLDERS | {'scripts'})))
    legacy_tokens = (
        'market_' + 'state',
        'Market' + 'State',
        'fea' + 'ture_id',
        'fea' + 'ture_service',
        'fea' + 'ture-sample',
    )
    legacy_domain_word = re.compile(r'\b' + 'fea' + r'tures?\b', re.I)
    reserved_term = 'Market' + ' State'
    for path in sorted(set(paths)):
        if path.suffix not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
            continue
        relative = path.relative_to(root).as_posix()
        for number, line in enumerate(path.read_text(errors='replace').splitlines(), 1):
            if any(token in line for token in legacy_tokens) or legacy_domain_word.search(line):
                errors.append(f'{relative}:{number}: deprecated market-analysis terminology')
            if reserved_term in line and relative != 'DESIGN.md':
                errors.append(f'{relative}:{number}: reserved decision-layer term used outside Design authority')
    return errors


def check(root=ROOT):
    errors = [f'Missing authority: {relative}' for relative in REQUIRED_PATHS
              if not (root / relative).is_file()]
    errors.extend(link_and_anchor_errors(root, maintained_markdown(root)))
    errors.extend(terminology_errors(root))
    return errors


def main():
    errors = check()
    for error in errors:
        print('FAIL:', error)
    if not errors:
        print('PASS: required authorities and maintained Markdown links/anchors')
        print('Scope: offline documentation structure only; no semantic equivalence or business correctness claim.')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
