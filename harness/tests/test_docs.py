"""Regression tests for stable documentation and architecture invariants."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_docs import production_dependency_errors, module_dependency_errors, link_and_anchor_errors, maintained_markdown


class ProductionDependencyDirectionTest(unittest.TestCase):
    def check_fixture(self, files, boundaries):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative, content in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            return production_dependency_errors(root, boundaries)

    def test_production_owned_dependency_and_unrelated_mentions_are_legal(self):
        errors = self.check_fixture(
            {
                'collector/CMakeLists.txt': 'include(cmake/ctp_sdk.cmake)\n',
                'collector/cmake/ctp_sdk.cmake': 'set(CTP_SDK_ROOT collector/third_party/ctp)\n',
                'docs/notes.md': 'TEST DOUBLE mention of experiments/ctp/sdk.\n',
                'experiments/ctp/demo.py': 'from collector import support\n',
            },
            {'collector': ('collector/CMakeLists.txt', 'collector/cmake/ctp_sdk.cmake')},
        )
        self.assertEqual(errors, [])

    def test_build_input_dependency_direction(self):
        self.assertEqual(self.check_fixture({}, {
            'query': ('harness/fixtures/analytics-skew-v1.json',)}), [])
        errors = self.check_fixture({}, {'collector': ('query/app.py',)})
        self.assertEqual(len(errors), 1, errors)
        self.assertIn('crosses module boundary', errors[0])

    def test_cmake_dependency_into_experiments_is_rejected_with_location_and_sor(self):
        errors = self.check_fixture(
            {'collector/CMakeLists.txt': 'include(../experiments/ctp/common/ctp.cmake)\n'},
            {'collector': ('collector/CMakeLists.txt',)},
        )
        self.assertEqual(len(errors), 1)
        self.assertIn('collector/CMakeLists.txt:1', errors[0])
        self.assertIn('production dependency points into experiments/', errors[0])
        self.assertIn('ARCHITECTURE.md', errors[0])

    def test_experiment_owned_docker_input_is_rejected(self):
        errors = self.check_fixture(
            {'experiments/ctp/sdk/header.h': 'fixture\n'},
            {'collector': ('experiments/ctp/sdk/header.h',)},
        )
        self.assertEqual(len(errors), 1)
        self.assertIn('collector Docker input is experiment-owned', errors[0])
        self.assertIn('docs/contracts/deployment.md', errors[0])


class BoundaryChecksTest(unittest.TestCase):
    """All temporary repositories and source inputs here are TEST DOUBLE."""

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
        errors = link_and_anchor_errors(self.root, maintained_markdown(self.root))
        self.assertEqual(len(errors), 4, errors)
        self.assertTrue(any('missing anchor #lost' in error for error in errors))

    def test_scan_excludes_data_dependencies_and_experiments(self):
        for path in ('collector/data/private.md', 'query/.venv/vendor.md',
                     'collector/third_party/sdk.md', 'experiments/local.md',
                     'dashboard/node_modules/dependency.md'):
            self.write(path, '[TEST DOUBLE](missing.md)\n')
        self.write('query/CONTRACT.md', '# TEST DOUBLE\n')
        self.write('monitoring/AGENTS.md', '# TEST DOUBLE\n')
        self.assertEqual(set(maintained_markdown(self.root)),
                         {'query/CONTRACT.md', 'monitoring/AGENTS.md'})

    def test_legal_calendar_tool_and_local_imports(self):
        self.write('collector/scripts/universe.py', '# TEST DOUBLE\nfrom market_calendar import Calendar\n')
        self.write('query/service.py', '# TEST DOUBLE\nfrom query import analytics\nfrom market_calendar import Calendar\n')
        self.write('query/tests/test_fake.py', '# TEST DOUBLE\nimport monitoring\n')
        self.assertEqual(module_dependency_errors(self.root), [])

    def test_illegal_runtime_imports_and_collector_include(self):
        for path, source in {
            'query/service.py': 'import monitoring\n',
            'monitoring/main.py': 'from query import analytics\n',
            'collector/runtime.py': 'from market_calendar import Calendar\n',
            'collector/scripts/universe.py': 'from query import analytics\n',
            'collector/src/main.cpp': '#include "../../query/private.h"\n',
        }.items():
            self.write(path, source)
        errors = module_dependency_errors(self.root)
        self.assertEqual(len(errors), 5, errors)

    def test_experiment_import_outside_build_manifest(self):
        self.write('query/new_service.py', '# TEST DOUBLE\nfrom experiments.ctp import demo\n')
        self.assertIn('experiments.ctp', module_dependency_errors(self.root)[0])

    def test_sdk_integrity(self):
        import hashlib
        from check_docs import sdk_errors
        sdk = 'collector/third_party/ctp/v6.7.13_20260225/'
        names = ('ThostFtdcMdApi.h', 'ThostFtdcUserApiDataType.h',
                 'ThostFtdcUserApiStruct.h', 'thostmduserapi_se.so')
        digest = hashlib.sha256(b'TEST DOUBLE').hexdigest()
        entries = []
        for name in names:
            self.write(sdk + 'linux64/mdapi/' + name, 'TEST DOUBLE')
            suffix = '.sha256' if name.endswith('.so') else '.repository_sha256'
            entries.append(name + suffix + '=' + digest)
        self.write(sdk + 'MANIFEST.txt', '\n'.join(entries))
        self.assertEqual(sdk_errors(self.root), [])
        self.write(sdk + 'linux64/mdapi/' + names[0], 'TEST DOUBLE damaged')
        self.assertEqual(sdk_errors(self.root), ['SDK hash mismatch: ' + names[0]])

    def test_docker_missing_input_and_leak(self):
        from check_docs import docker_boundary_errors
        boundaries = {'query': ('query/main.py',)}
        self.write('query/main.py', '# TEST DOUBLE\n')
        policy = self.write('query/Dockerfile.dockerignore', '**\n!query/main.py\n')
        self.assertEqual(docker_boundary_errors(self.root, boundaries), [])
        policy.write_text('**\n!query/main.py\n!docs/**\n')
        self.assertTrue(any('exposes private/unrelated input' in error
                            for error in docker_boundary_errors(self.root, boundaries)))
        (self.root / 'query/main.py').unlink()
        self.assertTrue(any('input missing' in error
                            for error in docker_boundary_errors(self.root, boundaries)))


if __name__ == '__main__':
    unittest.main()
