"""TEST DOUBLE Feature HTTP over real SQLite, Market State and SkewService."""
from datetime import timedelta
import fcntl
import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from app import create_app
from feature_service import SKEW_FEATURE_ID
from skew_references import ReferenceRepository
from tests.test_skew_api import DAY, MONTH, START, append_chain, make_database, write_package


class FeatureApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.refs = self.root / 'references'
        self.package = write_package(self.refs)
        self.repository = ReferenceRepository(self.refs, allow_synthetic=True)
        self.db = make_database(self.root)
        self.addCleanup(self.db.close)
        append_chain(self.db, START + timedelta(minutes=1))
        self.client = TestClient(create_app(
            self.root, target_month=MONTH, reference_repository=self.repository))
        self.addCleanup(self.client.close)

    def body(self, **changes):
        body = {
            'schema_version': 1,
            'feature_id': SKEW_FEATURE_ID,
            'scope': {'exchange': 'CFFEX', 'product': 'MO', 'month': MONTH},
            'parameters': {},
            'requested_at': (START + timedelta(minutes=1)).isoformat(),
        }
        body.update(changes)
        return body

    def post(self, **changes):
        response = self.client.post('/api/features/evaluate', json=self.body(**changes))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        return response.json()

    def test_http_envelope_equals_existing_skew_result_and_is_read_only(self):
        path = self.root / (DAY + '.sqlite')
        before = path.read_bytes()
        old = self.client.get('/api/skew/latest', params={
            'month': MONTH, 'at': (START + timedelta(minutes=1)).isoformat()})
        self.assertEqual(old.status_code, 200, old.text)
        result = self.post()
        expected = old.json()
        self.assertEqual(result['schema_version'], 1)
        self.assertEqual(result['feature_id'], SKEW_FEATURE_ID)
        self.assertEqual(result['parameters'], {})
        self.assertEqual(result['value'], expected['skew_25d_vp'])
        self.assertEqual(result['unit'], expected['unit'])
        self.assertEqual(result['scope'], expected['scope'])
        self.assertEqual(result['status'], expected['status'])
        self.assertEqual(result['reasons'], expected['reasons'])
        self.assertEqual(result['effective_at'], expected['valuation_at'])
        self.assertEqual(result['evaluated_at'], expected['evaluated_at'])
        self.assertEqual(result['historical'], expected['historical'])
        self.assertEqual(result['current_usable'], expected['current_usable'])
        self.assertEqual(result['evidence'], expected)
        self.assertEqual(path.read_bytes(), before)
        json.dumps(result, allow_nan=False)

    def test_historical_partial_stale_and_unavailable_semantics_are_preserved(self):
        partial = self.post()
        self.assertEqual(partial['status'], 'OK')
        self.assertEqual(partial['reasons'], ['PARTIAL_INPUT'])
        self.assertEqual(partial['evidence']['quality']['completeness'], 'PARTIAL')
        historical = self.post(requested_at='2026-09-16T12:00:00+08:00')
        self.assertTrue(historical['historical'])
        self.assertFalse(historical['current_usable'])
        stale = self.post(requested_at='2026-09-16T09:31:29+08:00')
        self.assertEqual(stale['status'], 'OK')
        self.assertFalse(stale['current_usable'])
        waiting = self.post(requested_at='2026-09-16T09:30:30+08:00')
        self.assertEqual(waiting['status'], 'UNAVAILABLE')
        self.assertIsNone(waiting['value'])
        self.assertIsNone(waiting['sample_key'])

    def test_structure_version_feature_scope_parameters_and_time_are_strict(self):
        invalid = [
            {}, [], self.body(extra=True), self.body(schema_version=2), self.body(schema_version=True),
            self.body(feature_id='unknown-v1'), self.body(feature_id=1),
            self.body(scope={'exchange': 'CFFEX', 'product': 'MO'}),
            self.body(scope={'exchange': 'CFFEX', 'product': 'MO', 'month': MONTH, 'day': DAY}),
            self.body(scope={'exchange': 'CFFEX', 'product': 'IM', 'month': MONTH}),
            self.body(scope={'exchange': 'CFFEX', 'product': 'MO', 'month': '2613'}),
            self.body(parameters=[]), self.body(parameters={'solver': 'looser'}),
            self.body(requested_at='2026-09-16T09:31:00'), self.body(requested_at=1),
        ]
        for body in invalid:
            with self.subTest(body=body):
                response = self.client.post('/api/features/evaluate', json=body)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_json_query_and_method_failures(self):
        cases = [
            self.client.post('/api/features/evaluate', content=b'{', headers={'content-type': 'application/json'}),
            self.client.post('/api/features/evaluate', content=b'', headers={'content-type': 'application/json'}),
            self.client.post('/api/features/evaluate', data={'schema_version': '1'}),
            self.client.post('/api/features/evaluate?sql=select', json=self.body()),
            self.client.post('/api/features/evaluate?x=1&x=2', json=self.body()),
            self.client.post('/api/features/evaluate',
                             content=b'{"schema_version":1,"schema_version":1}',
                             headers={'content-type': 'application/json'}),
            self.client.post('/api/features/evaluate',
                             content=b'{"schema_version":NaN}',
                             headers={'content-type': 'application/json'}),
        ]
        for response in cases:
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(self.client.get('/api/features/evaluate').status_code, 405)

    def test_unexpected_provider_error_remains_an_http_failure(self):
        class BrokenProvider:
            def evaluate(self, body):
                raise RuntimeError('TEST DOUBLE provider failure')

        with TestClient(create_app(self.root, feature_service=BrokenProvider()),
                        raise_server_exceptions=False) as client:
            response = client.post('/api/features/evaluate', json=self.body())
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('value', response.text)

    def test_raw_404_and_503_are_not_wrapped_as_feature_unavailable(self):
        self.db.close()
        path = self.root / (DAY + '.sqlite')
        saved = path.read_bytes()
        path.unlink()
        response = self.client.post('/api/features/evaluate', json=self.body())
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('status', response.json())
        path.write_bytes(saved)
        with (self.root / '.collector.lock').open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            response = self.client.post('/api/features/evaluate', json=self.body())
            self.assertEqual(response.status_code, 503)
            self.assertIn('stop Collector', response.json()['error'])

    def test_production_registry_rejects_synthetic_reference(self):
        with TestClient(create_app(
                self.root, reference_directory=self.refs, target_month=MONTH)) as client:
            response = client.post('/api/features/evaluate', json=self.body())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'UNAVAILABLE')
        self.assertEqual(response.json()['reasons'], ['REFERENCE_INVALID'])


if __name__ == '__main__':
    unittest.main()
