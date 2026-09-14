import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from query.app import create_app


class CoverageApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.client = TestClient(create_app(self.directory))
        self.addCleanup(self.client.close)

    def test_transport_parameters_and_data_provider_error_mapping(self):
        self.assertEqual(self.client.get('/api/coverage?day=20260907').status_code, 400)
        (self.directory / 'collector-runtime.sqlite').write_text('{')
        response = self.client.get('/api/coverage')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'error': 'Coverage files unavailable or invalid'})

    def test_empty_diagnostics_are_projected(self):
        response = self.client.get('/api/coverage')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertFalse(response.json()['collector_current'])


if __name__ == '__main__':
    unittest.main()
