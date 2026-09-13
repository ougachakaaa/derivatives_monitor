"""TEST DOUBLE Indicator projection over real SQLite, Market Frame and SkewService."""
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest

from query.indicator_service import (IndicatorRegistry, IndicatorRequestError, IndicatorService,
                             SkewIndicatorProvider, SKEW_INDICATOR_ID, indicator_envelope,
                             skew_indicator_service)
from data_provider.market_calendar import DEFAULT_DIRECTORY
from analytics.skew_references import ReferenceRepository
from analytics.skew_service import SkewService
from data_provider.storage import Store
from query.tests.test_skew_api import DAY, MONTH, START, append_chain, make_database, write_package


class IndicatorServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        refs = self.root / 'references'
        write_package(refs)
        self.db = make_database(self.root)
        self.addCleanup(self.db.close)
        append_chain(self.db, START + timedelta(minutes=1))
        self.skew = SkewService(Store(self.root), ReferenceRepository(refs, allow_synthetic=True),
                                DEFAULT_DIRECTORY, target_month=MONTH)
        self.service = skew_indicator_service(self.skew)

    def request(self, **changes):
        request = {
            'schema_version': 1,
            'indicator_id': SKEW_INDICATOR_ID,
            'scope': {'exchange': 'CFFEX', 'product': 'MO', 'month': MONTH},
            'parameters': {},
            'requested_at': (START + timedelta(minutes=1)).isoformat(),
        }
        request.update(changes)
        return request

    def test_skew_provider_is_an_exact_business_result_projection(self):
        expected = self.skew.query('latest', month=MONTH,
                                   at=(START + timedelta(minutes=1)).isoformat())
        result = self.service.evaluate(self.request())
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

    def test_sample_key_is_stable_across_raw_revision_and_request_time(self):
        first = self.service.evaluate(self.request())
        append_chain(self.db, START + timedelta(minutes=1))
        revised = self.service.evaluate(self.request())
        later = self.service.evaluate(self.request(
            requested_at=(START + timedelta(minutes=1, seconds=20)).isoformat()))
        self.assertNotEqual(first['evidence']['raw_revision'], revised['evidence']['raw_revision'])
        self.assertEqual(first['sample_key'], revised['sample_key'])
        self.assertEqual(first['sample_key'], later['sample_key'])
        self.assertTrue(first['sample_key'].startswith('indicator-sample-v1:'))

    def test_unknown_position_has_no_sample_key_but_preserves_failure(self):
        result = self.service.evaluate(self.request(
            requested_at='2026-09-16T09:30:30+08:00'))
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertEqual(result['reasons'], ['WAITING_FOR_MINUTE'])
        self.assertIsNone(result['value'])
        self.assertIsNone(result['effective_at'])
        self.assertIsNone(result['sample_key'])
        self.assertEqual(result['evidence']['skew_25d_vp'], result['value'])

    def test_registry_is_explicit_and_rejects_duplicates_or_unknown_indicators(self):
        registry = IndicatorRegistry()
        provider = SkewIndicatorProvider(self.skew)
        registry.register(SKEW_INDICATOR_ID, provider)
        self.assertIs(registry.resolve(SKEW_INDICATOR_ID), provider)
        with self.assertRaises(ValueError):
            registry.register(SKEW_INDICATOR_ID, provider)
        with self.assertRaises(IndicatorRequestError):
            IndicatorService(registry).evaluate(self.request(indicator_id='unknown-v1'))

    def test_common_envelope_rejects_non_finite_provider_values(self):
        evidence = self.skew.query('latest', month=MONTH,
                                   at=(START + timedelta(minutes=1)).isoformat())
        with self.assertRaises(ValueError):
            indicator_envelope('TEST-DOUBLE-v1', {}, evidence, value=float('nan'),
                             unit='TEST_DOUBLE_UNIT', effective_at=evidence['valuation_at'])

    def test_request_scope_parameters_and_time_are_strict(self):
        invalid = [
            self.request(schema_version=True),
            self.request(scope={'exchange': 'CFFEX', 'product': 'MO'}),
            self.request(scope={'exchange': 'cffex', 'product': 'MO', 'month': MONTH}),
            self.request(scope={'exchange': 'CFFEX', 'product': 'MO', 'month': MONTH, 'day': DAY}),
            self.request(parameters={'sigma_max': 10}),
            self.request(requested_at='2026-09-16T09:31:00'),
        ]
        for request in invalid:
            with self.subTest(request=request), self.assertRaises(IndicatorRequestError):
                self.service.evaluate(request)


if __name__ == '__main__':
    unittest.main()
