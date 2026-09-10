#!/usr/bin/env python3
"""Validate repository authority manifests without reading runtime data.

The manifests contain navigation and ownership relationships only.  Business
rules remain in the documents named by each claim definition.
"""
from __future__ import annotations

import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import unquote


MANIFEST = '.authority.json'
VERSION = 1
AUTHORITY_ROLES = {'architecture', 'contract', 'design', 'governance', 'operations', 'product'}
NON_AUTHORITY_ROLES = {'acceptance', 'agent-guidance', 'entrypoint', 'execution-plan', 'reference'}
ALL_ROLES = AUTHORITY_ROLES | NON_AUTHORITY_ROLES
EXIT_STAGES = {f'S{number}' for number in range(2, 9)}
IGNORED_PARTS = {'.git', 'artifacts', 'archive', 'node_modules', '__pycache__'}


def _relative(root: Path, value: str) -> Path:
    if not isinstance(value, str) or '\\' in value or re.match(r'^[A-Za-z]:', value):
        raise ValueError(f'path must use repository-relative POSIX form: {value}')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError(f'path must be repository-relative without ..: {value}')
    return root.joinpath(*path.parts)


def _load_manifests(root: Path):
    loaded = []
    for path in sorted(root.rglob(MANIFEST)):
        if any(part in IGNORED_PARTS for part in path.relative_to(root).parts):
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError) as error:
            loaded.append((path, None, f'invalid JSON: {error}'))
        else:
            loaded.append((path, data, None))
    return loaded


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


def _ancestor_chain(scope_id, scopes):
    chain = []
    seen = set()
    while scope_id is not None:
        if scope_id in seen or scope_id not in scopes:
            return None
        seen.add(scope_id)
        chain.append(scope_id)
        scope_id = scopes[scope_id]['parent']
    return chain


def _smallest_common_scope(scope_ids, scopes):
    chains = [_ancestor_chain(scope_id, scopes) for scope_id in scope_ids]
    if not chains or any(chain is None for chain in chains):
        return None
    shared = set(chains[0]).intersection(*map(set, chains[1:]))
    return next((scope for scope in chains[0] if scope in shared), None)


def _path_scope(relative: str, scopes):
    candidates = []
    parts = PurePosixPath(relative).parts
    for scope_id, scope in scopes.items():
        scope_parts = PurePosixPath(scope['root']).parts if scope['root'] != '.' else ()
        if parts[:len(scope_parts)] == scope_parts:
            candidates.append((len(scope_parts), scope_id))
    return max(candidates)[1] if candidates else None


def _claimed_section(text: str, anchor: str):
    marker = re.search(rf'<a\s+(?:name|id)=["\']{re.escape(anchor)}["\']\s*>', text, re.I)
    if not marker:
        return ''
    rest = text[marker.end():]
    heading = re.search(r'^(#{1,6})\s+', rest, re.M)
    if not heading:
        return rest.strip()
    level = len(heading.group(1))
    start = heading.start()
    later = re.search(rf'^#{{1,{level}}}\s+', rest[heading.end():], re.M)
    end = heading.end() + later.start() if later else len(rest)
    return rest[start:end].strip()


def _normalized_paragraphs(text: str):
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    paragraphs = re.split(r'\n\s*\n', text)
    normalized = []
    for paragraph in paragraphs:
        paragraph = re.sub(r'<a\s+[^>]+>', '', paragraph)
        paragraph = re.sub(r'^#{1,6}\s+.*$', '', paragraph, flags=re.M)
        paragraph = re.sub(r'\[[^]]+\]\([^)]+\)', 'LINK', paragraph)
        paragraph = re.sub(r'\s+', ' ', paragraph).strip()
        if len(paragraph) >= 120 and not paragraph.startswith(('|', '-', '*', '>')):
            normalized.append(paragraph)
    return normalized


def _source_cross_scope_edges(root: Path, scopes):
    top_levels = {PurePosixPath(scope['root']).parts[0]: scope_id for scope_id, scope in scopes.items()
                  if scope['root'] != '.' and len(PurePosixPath(scope['root']).parts) == 1}
    edges = set()
    for path in root.rglob('*.py'):
        relative = path.relative_to(root).as_posix()
        if any(part in IGNORED_PARTS | {'tests', 'experiments'} for part in path.relative_to(root).parts):
            continue
        source_scope = _path_scope(relative, scopes)
        if not source_scope:
            continue
        try:
            tree = ast.parse(path.read_text(errors='replace'))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            module = node.module if isinstance(node, ast.ImportFrom) else None
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
            for imported in ([module] if module else []) + names:
                target_scope = top_levels.get(imported.split('.', 1)[0])
                if target_scope and target_scope != source_scope:
                    edges.add((source_scope, target_scope, relative, 'python-import'))
    source_names = {'CMakeLists.txt', *[path.name for path in root.rglob('*.cmake')]}
    source_suffixes = {'.c', '.cc', '.cpp', '.h', '.hh', '.hpp'}
    for path in root.rglob('*'):
        if not path.is_file() or (path.name not in source_names and path.suffix.lower() not in source_suffixes):
            continue
        relative = path.relative_to(root).as_posix()
        if any(part in IGNORED_PARTS | {'tests', 'experiments', 'third_party'} for part in path.relative_to(root).parts):
            continue
        source_scope = _path_scope(relative, scopes)
        for target_text in re.findall(r'#include\s*["<]([^">]+)|(?:include|add_subdirectory)\s*\(\s*([^\s)]+)',
                                      path.read_text(errors='replace'), re.I):
            raw = next(value for value in target_text if value)
            candidates = [root / raw, path.parent / raw]
            target_path = next((candidate.resolve() for candidate in candidates if candidate.exists()), None)
            if target_path is None:
                first = PurePosixPath(raw).parts[:1]
                target_scope = top_levels.get(first[0]) if first else None
            else:
                try:
                    target_scope = _path_scope(target_path.relative_to(root).as_posix(), scopes)
                except ValueError:
                    target_scope = None
            if target_scope and target_scope != source_scope:
                edges.add((source_scope, target_scope, relative, 'source-include'))
    return edges


def authority_errors(root: Path, boundaries=None):
    root = Path(root)
    errors = []
    manifests = _load_manifests(root)
    if not manifests:
        return ['No .authority.json manifests found']
    scopes = {}
    documents = {}
    claims = defaultdict(list)
    references = []
    relations = []
    migrations = {}
    declared_dependencies = set()

    for path, data, load_error in manifests:
        relative_manifest = path.relative_to(root).as_posix()
        if load_error:
            errors.append(f'{relative_manifest}: {load_error}')
            continue
        if data.get('version') != VERSION:
            errors.append(f'{relative_manifest}: unsupported authority version {data.get("version")!r}')
        scope = data.get('scope', {})
        scope_id = scope.get('id')
        expected_root = path.parent.relative_to(root).as_posix() or '.'
        if not scope_id or scope_id in scopes:
            errors.append(f'{relative_manifest}: missing or duplicate scope id {scope_id!r}')
            continue
        if scope.get('root') != expected_root:
            errors.append(f'{relative_manifest}: scope root must be {expected_root!r}')
        scopes[scope_id] = dict(scope, manifest=relative_manifest)
        for pending in data.get('pending_scopes', []):
            pending_id = pending.get('id')
            if not pending_id or pending_id in scopes:
                errors.append(f'{relative_manifest}: missing or duplicate pending scope id {pending_id!r}')
            else:
                scopes[pending_id] = dict(pending, manifest=relative_manifest, virtual=True)
        for document in data.get('documents', []):
            doc_path, role = document.get('path'), document.get('role')
            if doc_path in documents:
                errors.append(f'{relative_manifest}: document registered more than once: {doc_path}')
            if role not in ALL_ROLES:
                errors.append(f'{relative_manifest}: invalid document role {role!r}: {doc_path}')
            documents[doc_path] = dict(document, scope=scope_id)
        for claim in data.get('claims', []):
            claims[claim.get('id')].append(dict(claim, manifest_scope=scope_id))
        references.extend((scope_id, item) for item in data.get('claim_references', []))
        relations.extend((scope_id, item) for item in data.get('relations', []))
        for migration in data.get('migration_exceptions', []):
            migration_id = migration.get('id')
            if not migration_id or migration_id in migrations:
                errors.append(f'{relative_manifest}: missing or duplicate migration id {migration_id!r}')
            else:
                migrations[migration_id] = migration
        for edge in data.get('cross_scope_dependencies', []):
            declared_dependencies.add((edge.get('from'), edge.get('to'), edge.get('source'), edge.get('kind')))

    roots = [scope_id for scope_id, scope in scopes.items() if scope.get('parent') is None]
    if roots != ['repo']:
        errors.append(f'authority scope tree must have only repo root; found {roots}')
    for scope_id, scope in scopes.items():
        parent = scope.get('parent')
        if parent is not None and parent not in scopes:
            errors.append(f'{scope["manifest"]}: unknown parent scope {parent!r}')
        if _ancestor_chain(scope_id, scopes) is None:
            errors.append(f'{scope["manifest"]}: scope parent cycle or missing ancestor')
        entrypoint = scope.get('entrypoint')
        if scope.get('virtual'):
            if scope.get('status') != 'frozen_pending' or entrypoint is not None:
                errors.append(f'{scope["manifest"]}: pending scope {scope_id} must be frozen_pending without entrypoint')
            continue
        if not entrypoint or not (root / entrypoint).is_file():
            errors.append(f'{scope["manifest"]}: missing scope entrypoint {entrypoint!r}')
        elif _path_scope(entrypoint, scopes) != scope_id and scope_id != 'repo':
            exception = scope.get('entrypoint_migration', {})
            if exception.get('current_path') != entrypoint \
                    or exception.get('target_path') != f'{scope["root"]}/README.md' \
                    or exception.get('exit_stage') not in EXIT_STAGES:
                errors.append(f'{scope["manifest"]}: entrypoint is outside scope without exact migration: {entrypoint}')

    for scope_id, scope in scopes.items():
        if scope_id == 'repo' or scope.get('virtual'):
            continue
        parent = scopes.get(scope.get('parent'))
        if not parent:
            continue
        parent_entrypoint, child_entrypoint = parent.get('entrypoint'), scope.get('entrypoint')
        if parent_entrypoint == child_entrypoint:
            continue
        parent_path = root / parent_entrypoint
        targets = []
        if parent_path.is_file():
            for target in markdown_links(parent_path.read_text(errors='replace')):
                file_part = unquote(target.split(None, 1)[0].split('#', 1)[0])
                if file_part and not re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', file_part):
                    targets.append((parent_path.parent / file_part).resolve())
        if (root / child_entrypoint).resolve() not in targets:
            errors.append(f'{scope["manifest"]}: parent entrypoint does not navigate to {child_entrypoint}')

    markdown_paths = {path for path, document in documents.items()
                      if isinstance(path, str) and path.lower().endswith('.md')}
    errors.extend(link_and_anchor_errors(root, markdown_paths))

    graph = defaultdict(set)
    for relative in markdown_paths:
        path = root / relative
        if not path.is_file():
            continue
        for target in markdown_links(path.read_text(errors='replace')):
            file_part = unquote(target.split(None, 1)[0].split('#', 1)[0])
            if not file_part or re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', file_part):
                continue
            destination = (path.parent / file_part).resolve()
            try:
                target_relative = destination.relative_to(root.resolve()).as_posix()
            except ValueError:
                continue
            if target_relative in documents:
                graph[relative].add(target_relative)
    reachable, pending = set(), ['README.md']
    while pending:
        current = pending.pop()
        if current in reachable:
            continue
        reachable.add(current)
        pending.extend(graph[current] - reachable)
    for relative, document in documents.items():
        if relative not in reachable and document['role'] not in {'agent-guidance'}:
            errors.append(f'registered document is not navigable from README.md: {relative}')

    for path, document in documents.items():
        try:
            actual = _relative(root, path)
        except (TypeError, ValueError) as error:
            errors.append(f'invalid registered document path {path!r}: {error}')
            continue
        if not actual.is_file():
            errors.append(f'missing registered document: {path}')
        owner = _path_scope(path, scopes)
        if owner != document['scope']:
            errors.append(f'{path}: registered by {document["scope"]}, physical owner is {owner}')

    for claim_id, definitions in claims.items():
        if not claim_id or len(definitions) != 1:
            errors.append(f'claim must have exactly one definition: {claim_id!r} ({len(definitions)})')
            continue
        claim = definitions[0]
        definition = claim.get('definition', {})
        path, anchor = definition.get('path'), definition.get('anchor')
        if path not in documents:
            errors.append(f'{claim_id}: definition document is not registered: {path}')
            continue
        if documents[path]['role'] not in AUTHORITY_ROLES:
            errors.append(f'{claim_id}: {documents[path]["role"]} cannot define authority')
        actual = root / path
        selector = definition.get('selector')
        if not actual.is_file():
            errors.append(f'{claim_id}: definition file is missing: {path}')
        elif actual.suffix.lower() in ('.md', '.markdown'):
            if not anchor or anchor not in _explicit_anchors(actual.read_text(errors='replace')):
                errors.append(f'{claim_id}: missing stable explicit anchor {path}#{anchor}')
        elif selector != '/':
            errors.append(f'{claim_id}: machine authority requires stable root selector: {path}#/')
        constrained = claim.get('constrained_scopes', [])
        expected_scope = _smallest_common_scope(constrained, scopes)
        actual_scope = _path_scope(path, scopes)
        migration_id = claim.get('migration_exception')
        migration = migrations.get(migration_id) if migration_id else None
        if migration_id and (not migration or migration.get('claim') != claim_id
                             or migration.get('current_path') != path
                             or migration.get('target_scope') != expected_scope
                             or migration.get('exit_stage') not in EXIT_STAGES):
            errors.append(f'{claim_id}: invalid exact migration exception {migration_id!r}')
        if expected_scope != actual_scope:
            if not migration or migration.get('claim') != claim_id \
                    or migration.get('current_path') != path \
                    or migration.get('target_scope') != expected_scope \
                    or migration.get('exit_stage') not in EXIT_STAGES:
                errors.append(f'{claim_id}: definition scope {actual_scope} is not smallest common scope '
                              f'{expected_scope}; exact migration exception required')

    for scope_id, reference in references:
        claim_id = reference.get('claim')
        if claim_id not in claims or len(claims[claim_id]) != 1:
            errors.append(f'{scope_id}: reference to undefined claim {claim_id!r}')
        if not reference.get('path') or not (root / reference.get('path', '')).is_file():
            errors.append(f'{scope_id}: claim reference path is missing: {reference.get("path")!r}')

    for scope_id, relation in relations:
        if relation.get('kind') not in {'evidence', 'reference', 'projection'}:
            errors.append(f'{scope_id}: invalid authority relation kind {relation.get("kind")!r}')
        if relation.get('to_claim') not in claims:
            errors.append(f'{scope_id}: relation to undefined claim {relation.get("to_claim")!r}')
        if not relation.get('from') or not (root / relation.get('from', '')).is_file():
            errors.append(f'{scope_id}: relation source is missing: {relation.get("from")!r}')

    used_migrations = {definitions[0].get('migration_exception') for definitions in claims.values()
                       if len(definitions) == 1 and definitions[0].get('migration_exception')}
    for migration_id, migration in migrations.items():
        if migration_id not in used_migrations:
            errors.append(f'unused migration exception: {migration_id}')
        for field in ('claim', 'current_path', 'target_path', 'target_scope', 'exit_stage'):
            if not migration.get(field):
                errors.append(f'{migration_id}: migration exception missing {field}')
        target = migration.get('target_path')
        if target:
            try:
                _relative(root, target)
            except (TypeError, ValueError) as error:
                errors.append(f'{migration_id}: invalid target path: {error}')
            else:
                if _path_scope(target, scopes) != migration.get('target_scope'):
                    errors.append(f'{migration_id}: target path is outside target scope')

    fingerprints = defaultdict(list)
    for definitions in claims.values():
        if len(definitions) != 1:
            continue
        definition = definitions[0].get('definition', {})
        path, anchor = definition.get('path'), definition.get('anchor')
        actual = root / path if path else None
        if actual and actual.is_file() and anchor and actual.suffix.lower() in ('.md', '.markdown'):
            for paragraph in _normalized_paragraphs(_claimed_section(actual.read_text(errors='replace'), anchor)):
                fingerprints[hashlib.sha256(paragraph.encode()).hexdigest()].append(f'{path}#{anchor}')
    for locations in fingerprints.values():
        if len({location.split('#', 1)[0] for location in locations}) > 1:
            errors.append('duplicate normative paragraph in registered claims: ' + ', '.join(sorted(set(locations))))

    discovered = _source_cross_scope_edges(root, scopes)
    if boundaries:
        for service, inputs in boundaries.items():
            if service not in scopes:
                continue
            for relative in inputs:
                target = _path_scope(relative, scopes)
                if target and target != service:
                    discovered.add((service, target, relative, 'build-input'))
    for edge in sorted(discovered):
        if edge not in declared_dependencies:
            errors.append('unregistered cross-scope dependency: ' + ' -> '.join(edge[:2])
                          + f' ({edge[3]} {edge[2]})')
    for source, target, path, kind in sorted(declared_dependencies):
        if source not in scopes or target not in scopes:
            errors.append(f'declared dependency has unknown scope: {source} -> {target}')
        if not path or not (root / path).is_file():
            errors.append(f'declared dependency source missing: {path}')
        if (source, target, path, kind) not in discovered and kind != 'path-bootstrap-import':
            errors.append(f'declared dependency not observed: {source} -> {target} ({kind} {path})')
    for data in (item for _, manifest_data, error in manifests if not error for item in manifest_data.get('cross_scope_dependencies', [])):
        if data.get('constraint_claim') not in claims:
            errors.append(f'dependency constraint claim is undefined: {data.get("constraint_claim")!r}')
    return errors
