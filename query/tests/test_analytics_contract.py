"""Protect frozen goldens from sign/delta/selection drift; not production tests."""
import copy
import json
from pathlib import Path
import sys
import unittest

from query.tests.analytics_contract import POLICY, FIXTURES, check, eligible, solve, price


class AnalyticsContractTest(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(POLICY.read_text())
        self.fixtures = json.loads(FIXTURES.read_text())

    def test_frozen_examples(self):
        check(self.policy, self.fixtures)

    def test_reject_wrong_sign_discounted_delta_and_selection(self):
        wrong = copy.deepcopy(self.fixtures)
        wrong['chains'][0]['expected_skew_vp'] *= -1
        with self.assertRaises(AssertionError):
            check(self.policy, wrong)
        wrong = copy.deepcopy(self.fixtures)
        wrong['vectors'][0]['expected_delta'] *= wrong['vectors'][0]['discount']
        with self.assertRaises(AssertionError):
            check(self.policy, wrong)
        wrong = copy.deepcopy(self.fixtures)
        wrong['chains'][0]['expected_forward_pairs'][0]['call_id'] += 1
        with self.assertRaises(AssertionError):
            check(self.policy, wrong)

    def test_all_seven_decisions_must_be_frozen(self):
        self.policy['decisions']['underlying_semantics'] = 'TBD'
        with self.assertRaises(AssertionError):
            check(self.policy, self.fixtures)

    def test_age_spread_and_tick_boundaries(self):
        row = dict(bid=9.0, ask=11.0, bid_volume=1, ask_volume=1, age_us=30000000)
        self.assertTrue(eligible(row, self.policy))
        self.assertFalse(eligible(dict(row, age_us=30000001), self.policy))
        self.assertFalse(eligible(dict(row, age_us=-1), self.policy))
        self.assertFalse(eligible(dict(row, bid_volume=0), self.policy))
        self.assertFalse(eligible(dict(row, bid=8.8), self.policy))
        self.assertFalse(eligible(dict(row, ask=10.9), self.policy))

    def test_solver_must_fail_instead_of_clipping_or_returning_last_iterate(self):
        for mid, reason in ((0, 'PRICE_OUT_OF_BOUNDS'), (.1, 'TIME_VALUE_TOO_SMALL'),
                            (100, 'PRICE_OUT_OF_BOUNDS')):
            with self.subTest(mid=mid), self.assertRaisesRegex(ValueError, reason):
                solve('C', 100, 100, .5, 1, mid, self.policy)
        too_high = price('C', 100, 100, .5, 1, 6)
        with self.assertRaisesRegex(ValueError, 'IV_OUT_OF_RANGE'):
            solve('C', 100, 100, .5, 1, too_high, self.policy)
        self.policy['solver']['max_iterations'] = 1
        with self.assertRaisesRegex(ValueError, 'IV_NOT_CONVERGED'):
            solve('C', 100, 100, .5, 1, 5, self.policy)


if __name__ == '__main__':
    unittest.main()
