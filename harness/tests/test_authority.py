"""Negative and positive tests for scoped repository authority validation."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from authority import authority_errors, link_and_anchor_errors


ROOT_MANIFEST = {
    'version': 1,
    'scope': {'id': 'repo', 'root': '.', 'parent': None, 'entrypoint': 'README.md', 'status': 'existing'},
    'documents': [
        {'path': 'README.md', 'role': 'entrypoint'},
        {'path': 'CONTRACT.md', 'role': 'contract'},
        {'path': 'acceptance.md', 'role': 'acceptance'},
    ],
    'claims': [{
        'id': 'repository.shared',
        'definition': {'path': 'CONTRACT.md', 'anchor': 'shared'},
        'constrained_scopes': ['alpha', 'beta'],
    }],
    'claim_references': [],
    'migration_exceptions': [],
    'cross_scope_dependencies': [],
}


class AuthorityValidationTest(unittest.TestCase):
    def fixture(self, mutate=None, extra_files=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        manifests = {
            '.authority.json': deepcopy(ROOT_MANIFEST),
            'alpha/.authority.json': {
                'version': 1,
                'scope': {'id': 'alpha', 'root': 'alpha', 'parent': 'repo',
                          'entrypoint': 'alpha/README.md', 'status': 'existing'},
                'documents': [{'path': 'alpha/README.md', 'role': 'entrypoint'}],
                'claims': [],
                'claim_references': [{'claim': 'repository.shared', 'path': 'alpha/README.md'}],
            },
            'beta/.authority.json': {
                'version': 1,
                'scope': {'id': 'beta', 'root': 'beta', 'parent': 'repo',
                          'entrypoint': 'beta/README.md', 'status': 'existing'},
                'documents': [{'path': 'beta/README.md', 'role': 'entrypoint'}],
                'claims': [],
                'claim_references': [{'claim': 'repository.shared', 'path': 'beta/README.md'}],
            },
        }
        files = {
            'README.md': '[Alpha](alpha/README.md) [Beta](beta/README.md) '
                         '[Contract](CONTRACT.md) [Evidence](acceptance.md)\n',
            'CONTRACT.md': '<a id="shared"></a>\n\n# Shared\n\nOne shared rule.\n',
            'acceptance.md': '# Evidence\n',
            'alpha/README.md': '[Parent](../README.md)\n',
            'beta/README.md': '[Parent](../README.md)\n',
        }
        if mutate:
            mutate(manifests, files)
        files.update(extra_files or {})
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        for relative, data in manifests.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data))
        return root

    def test_valid_scope_tree_claim_and_navigation(self):
        self.assertEqual(authority_errors(self.fixture()), [])

    def test_duplicate_claim_definition_is_rejected(self):
        def mutate(manifests, _files):
            manifests['alpha/.authority.json']['claims'] = [deepcopy(ROOT_MANIFEST['claims'][0])]
        errors = authority_errors(self.fixture(mutate))
        self.assertTrue(any('exactly one definition' in error for error in errors), errors)

    def test_undefined_claim_reference_is_rejected(self):
        def mutate(manifests, _files):
            manifests['alpha/.authority.json']['claim_references'][0]['claim'] = 'missing.claim'
        errors = authority_errors(self.fixture(mutate))
        self.assertTrue(any('reference to undefined claim' in error for error in errors), errors)

    def test_acceptance_cannot_define_business_authority(self):
        def mutate(manifests, _files):
            claim = manifests['.authority.json']['claims'][0]
            claim['definition'] = {'path': 'acceptance.md', 'anchor': 'evidence'}
            _files['acceptance.md'] = '<a id="evidence"></a>\n# Evidence\n'
        errors = authority_errors(self.fixture(mutate))
        self.assertTrue(any('cannot define authority' in error for error in errors), errors)

    def test_child_claim_for_shared_rule_is_rejected_without_exact_migration(self):
        def mutate(manifests, files):
            claim = manifests['.authority.json']['claims'].pop()
            claim['definition'] = {'path': 'alpha/CONTRACT.md', 'anchor': 'shared'}
            manifests['alpha/.authority.json']['documents'].append(
                {'path': 'alpha/CONTRACT.md', 'role': 'contract'})
            manifests['alpha/.authority.json']['claims'].append(claim)
            files['alpha/CONTRACT.md'] = '<a id="shared"></a>\n# Shared\n'
        errors = authority_errors(self.fixture(mutate))
        self.assertTrue(any('smallest common scope repo' in error for error in errors), errors)

    def test_exact_named_migration_allows_current_wrong_scope(self):
        def mutate(manifests, files):
            claim = manifests['.authority.json']['claims'].pop()
            claim['definition'] = {'path': 'alpha/CONTRACT.md', 'anchor': 'shared'}
            claim['migration_exception'] = 'shared-to-s2'
            manifests['alpha/.authority.json']['documents'].append(
                {'path': 'alpha/CONTRACT.md', 'role': 'contract'})
            manifests['alpha/.authority.json']['claims'].append(claim)
            manifests['alpha/.authority.json']['migration_exceptions'] = [{
                'id': 'shared-to-s2', 'claim': 'repository.shared',
                'current_path': 'alpha/CONTRACT.md', 'target_path': 'CONTRACT.md',
                'target_scope': 'repo', 'exit_stage': 'S2'}]
            files['alpha/CONTRACT.md'] = '<a id="shared"></a>\n# Shared\n'
            files['alpha/README.md'] += '[Temporary contract](CONTRACT.md)\n'
        self.assertEqual(authority_errors(self.fixture(mutate)), [])

    def test_migration_rejects_parent_and_windows_style_target_paths(self):
        for target in ('../CONTRACT.md', 'C:\\repo\\CONTRACT.md'):
            with self.subTest(target=target):
                def mutate(manifests, _files):
                    claim = manifests['.authority.json']['claims'][0]
                    claim['migration_exception'] = 'bad-path'
                    manifests['.authority.json']['migration_exceptions'] = [{
                        'id': 'bad-path', 'claim': 'repository.shared',
                        'current_path': 'CONTRACT.md', 'target_path': target,
                        'target_scope': 'repo', 'exit_stage': 'S2'}]
                errors = authority_errors(self.fixture(mutate))
                self.assertTrue(any('invalid target path' in error for error in errors), errors)

    def test_missing_explicit_claim_anchor_is_rejected(self):
        def mutate(_manifests, files):
            files['CONTRACT.md'] = '# Shared\n'
        errors = authority_errors(self.fixture(mutate))
        self.assertTrue(any('missing stable explicit anchor' in error for error in errors), errors)

    def test_inline_reference_links_and_anchors_are_checked(self):
        root = self.fixture(extra_files={
            'links.md': '[ok](CONTRACT.md#shared) [bad][missing]\n\n[missing]: CONTRACT.md#absent\n'})
        errors = link_and_anchor_errors(root, ['links.md'])
        self.assertEqual(errors, ['links.md: missing anchor CONTRACT.md#absent'])

    def test_parent_cycle_and_orphan_entrypoint_are_rejected(self):
        def mutate(manifests, _files):
            manifests['alpha/.authority.json']['scope']['parent'] = 'alpha'
            manifests['beta/.authority.json']['scope']['entrypoint'] = 'alpha/README.md'
        errors = authority_errors(self.fixture(mutate))
        self.assertTrue(any('parent cycle' in error for error in errors), errors)
        self.assertTrue(any('entrypoint is outside scope' in error for error in errors), errors)

    def test_duplicate_normative_paragraph_is_rejected(self):
        paragraph = ('This normative paragraph deliberately contains enough repeated words to exceed the '
                     'minimum fingerprint length and must not become a second authoritative definition.')
        def mutate(manifests, files):
            files['CONTRACT.md'] = f'<a id="shared"></a>\n# Shared\n\n{paragraph}\n'
            files['alpha/CONTRACT.md'] = f'<a id="local"></a>\n# Local\n\n{paragraph}\n'
            manifests['alpha/.authority.json']['documents'].append(
                {'path': 'alpha/CONTRACT.md', 'role': 'contract'})
            manifests['alpha/.authority.json']['claims'].append({
                'id': 'alpha.local', 'definition': {'path': 'alpha/CONTRACT.md', 'anchor': 'local'},
                'constrained_scopes': ['alpha']})
        errors = authority_errors(self.fixture(mutate))
        self.assertTrue(any('duplicate normative paragraph' in error for error in errors), errors)

    def test_unregistered_cross_scope_python_import_is_rejected(self):
        def mutate(_manifests, files):
            files['alpha/runtime.py'] = 'import beta.runtime\n'
            files['beta/runtime.py'] = 'VALUE = 1\n'
        errors = authority_errors(self.fixture(mutate))
        self.assertTrue(any('unregistered cross-scope dependency' in error for error in errors), errors)

    def test_test_and_experiment_imports_are_not_production_dependencies(self):
        root = self.fixture(extra_files={
            'alpha/tests/test_runtime.py': 'import beta.runtime\n',
            'experiments/probe.py': 'import alpha.runtime\n',
            'beta/runtime.py': 'VALUE = 1\n',
        })
        self.assertEqual(authority_errors(root), [])

    def test_unregistered_cross_scope_include_is_rejected(self):
        def mutate(_manifests, files):
            files['alpha/runtime.cpp'] = '#include "../beta/public.hpp"\n'
            files['beta/public.hpp'] = '#pragma once\n'
        errors = authority_errors(self.fixture(mutate))
        self.assertTrue(any('source-include alpha/runtime.cpp' in error for error in errors), errors)

    def test_registered_cross_scope_build_input_is_accepted(self):
        def mutate(manifests, files):
            manifests['.authority.json']['cross_scope_dependencies'].append({
                'from': 'alpha', 'to': 'beta', 'source': 'beta/input.json', 'kind': 'build-input',
                'constraint_claim': 'repository.shared'})
            files['beta/input.json'] = '{}\n'
        root = self.fixture(mutate)
        self.assertEqual(authority_errors(root, {'alpha': ('beta/input.json',)}), [])


if __name__ == '__main__':
    unittest.main()
