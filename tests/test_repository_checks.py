"""Regression tests for documentation and repository structural checks."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_docs import link_and_anchor_errors, maintained_markdown, terminology_errors
from check_repository import (module_dependency_errors, packaging_policy_errors,
                              production_dependency_errors)
from check_docker_context import declared_files, validate_declared


class DocumentationChecksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='test-double-docs-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_links_and_anchors(self):
        self.write('README.md', '# TEST DOUBLE\n[local](#test-double)\n'
                   '[section][ref]\n[ref]: query/CONTRACT.md#规则\n'
                   '[repeat](query/CONTRACT.md#规则-1)\n'
                   '[explicit](query/CONTRACT.md#stable)\n')
        self.write('query/CONTRACT.md', '# 规则\n# 规则\n<a id="stable"></a>\n')
        self.assertEqual(link_and_anchor_errors(self.root, maintained_markdown(self.root)), [])
        self.write('README.md', '[missing](lost.md)\n[anchor](query/CONTRACT.md#lost)\n'
                   '[self](#lost)\n[missing ref][ref]\n[ref]: gone.md\n')
        self.assertEqual(len(link_and_anchor_errors(self.root, maintained_markdown(self.root))), 4)

    def test_scan_excludes_runtime_dependencies_and_experiments(self):
        for path in ('collector/data/private.md', 'query/.venv/vendor.md',
                     'collector/third_party/sdk.md', 'experiments/local.md',
                     'dashboard/node_modules/dependency.md'):
            self.write(path, '[TEST DOUBLE](missing.md)\n')
        self.write('query/CONTRACT.md', '# TEST DOUBLE\n')
        self.assertEqual(set(maintained_markdown(self.root)), {'query/CONTRACT.md'})

    def test_reconciled_market_terminology_is_enforced(self):
        reserved = 'Market' + ' State'
        self.write('DESIGN.md', f'# TEST DOUBLE\n{reserved} is a reserved decision layer.\n')
        deprecated = 'market_' + 'state'
        self.write('query/service.py', f'payload = {{"{deprecated}": "OPEN"}}\n')
        self.assertTrue(terminology_errors(self.root))
        self.write('query/service.py', 'payload = {"session_state": "OPEN"}\n')
        self.assertEqual(terminology_errors(self.root), [])


class RepositoryChecksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='test-double-repository-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_production_dependency_rejects_experiment_path(self):
        self.write('collector/CMakeLists.txt', 'include(../experiments/ctp/common/ctp.cmake)\n')
        errors = production_dependency_errors(self.root)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn('collector/CMakeLists.txt:1', errors[0])
        self.assertIn('ARCHITECTURE.md', errors[0])

    def test_production_rejects_repository_verification_dependencies(self):
        self.write('query/Dockerfile', 'COPY harness/fixture.json /fixture.json\n')
        self.write('query/service.py', 'from tests import private_oracle\n')
        self.assertEqual(len(production_dependency_errors(self.root)), 1)
        errors = module_dependency_errors(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn('repository verification', errors[0])

    def test_legal_calendar_tool_and_local_imports(self):
        self.write('collector/scripts/universe.py', 'from data_provider.market_calendar import Calendar\n')
        self.write('data_provider/market_calendar.py', 'class Calendar: pass\n')
        self.write('analytics/skew.py', 'from data_provider.market_calendar import Calendar\n')
        self.write('query/service.py', 'from analytics import skew\nfrom data_provider.market_calendar import Calendar\n')
        self.write('query/tests/test_fake.py', 'import dashboard\n')
        self.assertEqual(module_dependency_errors(self.root), [])

    def test_illegal_runtime_imports_and_collector_include(self):
        for path, source in {
            'query/service.py': 'import dashboard\n',
            'dashboard/service.py': 'from analytics import skew\n',
            'collector/runtime.py': 'from data_provider.market_calendar import Calendar\n',
            'collector/scripts/universe.py': 'from analytics import skew\n',
            'collector/src/main.cpp': '#include "../../query/private.h"\n',
        }.items():
            self.write(path, source)
        self.assertEqual(len(module_dependency_errors(self.root)), 5)

    def test_source_packages_enforce_downstream_only_dependencies(self):
        self.write('data_provider/store.py', 'import analytics\n')
        self.write('analytics/skew.py', 'import query\n')
        self.write('collector/scripts/other.py', 'from data_provider.market_calendar import Calendar\n')
        errors = module_dependency_errors(self.root)
        self.assertEqual(len(errors), 3, errors)
        self.assertTrue(all('forbidden module dependency' in error for error in errors))

    def test_packaging_policy_is_deny_first_and_owner_local(self):
        for service in ('collector', 'query', 'dashboard'):
            self.write(f'{service}/Dockerfile.dockerignore', f'**\n!{service}/\n!{service}/main.py\n')
        self.assertEqual(packaging_policy_errors(self.root), [])
        self.write('query/Dockerfile.dockerignore', '**\n!query/main.py\n!docs/private.txt\n')
        self.assertTrue(any('crosses owner boundary' in error
                            for error in packaging_policy_errors(self.root)))
        self.write('query/Dockerfile.dockerignore', '!query/main.py\n')
        self.assertTrue(any('deny-by-default' in error
                            for error in packaging_policy_errors(self.root)))
        self.write('query/Dockerfile.dockerignore',
                   '**\n!query/main.py\n!data_provider/storage.py\n!analytics/skew.py\n')
        self.assertEqual(packaging_policy_errors(self.root), [])

    def test_packaging_expected_files_come_from_literal_owner_policy(self):
        self.write('query/Dockerfile.dockerignore',
                   '**\n!query/\nquery/**\n!query/main.py\n!query/generated-*.py\n')
        self.write('query/main.py', '# TEST DOUBLE\n')
        self.assertEqual(declared_files('query', self.root), {'query/main.py'})
        with mock.patch('check_docker_context.subprocess.check_output',
                        return_value='query/main.py\nquery/.env\n'):
            validate_declared('query', {'query/main.py'}, self.root)
            with self.assertRaisesRegex(AssertionError, 'crosses owner boundary'):
                validate_declared('query', {'docs/private.txt'}, self.root)
            with self.assertRaisesRegex(AssertionError, 'sensitive/runtime'):
                validate_declared('query', {'query/.env'}, self.root)
        self.write('data_provider/storage.py', '# TEST DOUBLE\n')
        self.write('analytics/skew.py', '# TEST DOUBLE\n')
        with mock.patch('check_docker_context.subprocess.check_output',
                        return_value=('query/main.py\ndata_provider/storage.py\n'
                                      'analytics/skew.py\n')):
            validate_declared('query', {'query/main.py', 'data_provider/storage.py',
                                        'analytics/skew.py'}, self.root)


if __name__ == '__main__':
    unittest.main()
