"""Regression tests for stable documentation and architecture invariants."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_docs import production_dependency_errors


class ProductionDependencyDirectionTest(unittest.TestCase):
    def check_fixture(self, files, boundaries):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative, content in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            return production_dependency_errors(root, boundaries)

    def test_production_owned_dependency_and_historical_mentions_are_legal(self):
        errors = self.check_fixture(
            {
                'collector/CMakeLists.txt': 'include(cmake/ctp_sdk.cmake)\n',
                'collector/cmake/ctp_sdk.cmake': 'set(CTP_SDK_ROOT collector/third_party/ctp)\n',
                'docs/archive/old.md': 'Collector once used experiments/ctp/sdk.\n',
                'experiments/ctp/demo.py': 'from collector import support\n',
            },
            {'collector': ('collector/CMakeLists.txt', 'collector/cmake/ctp_sdk.cmake')},
        )
        self.assertEqual(errors, [])

    def test_cmake_dependency_into_experiments_is_rejected_with_location_and_sor(self):
        errors = self.check_fixture(
            {'collector/CMakeLists.txt': 'include(../experiments/ctp/common/ctp.cmake)\n'},
            {'collector': ('collector/CMakeLists.txt',)},
        )
        self.assertEqual(len(errors), 1)
        self.assertIn('collector/CMakeLists.txt:1', errors[0])
        self.assertIn('production dependency points into experiments/', errors[0])
        self.assertIn('docs/architecture.md', errors[0])

    def test_experiment_owned_docker_input_is_rejected(self):
        errors = self.check_fixture(
            {'experiments/ctp/sdk/header.h': 'fixture\n'},
            {'collector': ('experiments/ctp/sdk/header.h',)},
        )
        self.assertEqual(len(errors), 1)
        self.assertIn('collector Docker input is experiment-owned', errors[0])
        self.assertIn('docs/contracts/deployment.md', errors[0])


if __name__ == '__main__':
    unittest.main()
