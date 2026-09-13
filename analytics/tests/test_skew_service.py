import unittest

from analytics.errors import AnalyticsRequestError
from analytics.skew_service import SkewService, latest_minute
from data_provider.market_calendar import Calendar, DEFAULT_DIRECTORY, parse_at


class SkewServiceBoundaryTest(unittest.TestCase):
    def test_invalid_request_is_transport_neutral(self):
        service = SkewService(None, None, DEFAULT_DIRECTORY)
        with self.assertRaisesRegex(AnalyticsRequestError, 'Invalid Skew query parameters'):
            service.query('latest', month='2613', at='2026-09-16T09:31:00+08:00')
        self.assertFalse(hasattr(AnalyticsRequestError('x'), 'status'))

    def test_latest_minute_uses_calendar_continuous_period(self):
        calendar = Calendar(DEFAULT_DIRECTORY / '2026.json')
        minute, day, historical, reason, state = latest_minute(
            calendar, parse_at('2026-09-16T09:31:20+08:00'))
        self.assertEqual(minute.isoformat(), '2026-09-16T09:30:00+08:00')
        self.assertEqual(day, '20260916')
        self.assertFalse(historical)
        self.assertIsNone(reason)
        self.assertTrue(state['is_continuous'])


if __name__ == '__main__':
    unittest.main()
