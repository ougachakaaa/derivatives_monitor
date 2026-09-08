from copy import deepcopy
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import analytics
from analytics import (ALGORITHM_VERSION, CONTRACT_ID, SolverFailure, black_price,
                       _choose_wing, calculate_skew, solve_iv)
from market_state import (OBSERVATION_COLUMNS, MarketStateReader, Scope, Universe,
                          micros)
from storage import Store


ROOT = Path(__file__).resolve().parents[2]
GOLDEN = json.loads((ROOT / 'harness/fixtures/analytics-skew-v1.json').read_text())
CHAIN = GOLDEN['chains'][0]
VALUATION = datetime.fromisoformat('2026-09-16T15:00:00+08:00')
EXPIRY = datetime.fromisoformat('2026-10-16T15:00:00+08:00')
HASH = 'a' * 64


def reference(rows=None):
    rows = rows or CHAIN['rows']
    contracts = []
    for row in rows:
        contracts.append({'id': row['instrument'], 'side': row['side'],
                          'strike': row['strike'], 'expiry': '20261016'})
    return {
        'schema_version': 1, 'bundle_id': 'synthetic-reference-v1',
        'bundle_sha256': HASH, 'valid_trading_day': '20260916',
        'exchange': 'CFFEX', 'product': 'MO', 'month': '2610',
        'reviewed_at': '2026-09-15T12:00:00+08:00',
        'review': 'TEST DOUBLE reviewed reference', 'source_kind': 'SYNTHETIC',
        'universe': {'version': 'synthetic-chain-v1', 'sha256': HASH,
                     'instruments': contracts},
        'calendar': {'version': '2026-cn-futures-v1', 'sha256': HASH,
                    'previous_cffex_trading_day': '20260915'},
        'product_rules': {'underlying_index': 'CSI1000', 'exercise': 'EUROPEAN',
            'settlement': 'CASH', 'currency': 'CNY', 'price_unit': 'INDEX_POINT',
            'tick_size': .2, 'multiplier': 100, 'source_url': 'fixture://cffex',
            'source_version': 'fixture-v1', 'source_sha256': HASH},
        'expiry_at': EXPIRY.isoformat(),
        'rate': {'name': 'SHIBOR', 'tenor': '3M', 'percent': 2.0, 'decimal': .02,
            'fixing_date': '20260915', 'published_at': '2026-09-15T11:00:00+08:00',
            'source_url': 'fixture://cfets', 'source_sha256': HASH,
            'retrieved_at': '2026-09-15T12:00:00+08:00', 'day_count': 'ACT/360',
            'compounding': 'SIMPLE', 'settlement': 'T+0'}
    }


def frame(rows=None):
    rows = rows or CHAIN['rows']
    end_us = micros(VALUATION)
    members = [row['instrument'] for row in rows]
    market_rows = []
    for row in rows:
        received = end_us - row['age_us']
        observation = {'id': row['id'], 'run_id': 'synthetic-run', 'sequence': row['id'],
            'received_us': received, 'snapshot_us': received + 1_000_000,
            'TradingDay': '20260916', 'ExchangeID': 'CFFEX',
            'InstrumentID': row['instrument'], 'ActionDay': '20260916',
            'UpdateTime': '14:59:50', 'UpdateMillisec': 0,
            'BidPrice1': row['bid'], 'AskPrice1': row['ask'],
            'BidVolume1': row['bid_volume'], 'AskVolume1': row['ask_volume']}
        market_rows.append({'instrument': row['instrument'], 'observation': observation,
            'quality': {'missing': False, 'stale': False, 'invalid': False,
                        'usable': True, 'flags': [], 'reasons': [],
                        'quote_age_us': row['age_us']}})
    return {'schema_version': 1, 'kind': 'minute', 'minute': '2026-09-16T14:59:00+08:00',
        'minute_end': VALUATION.isoformat(), 'evaluated_at': VALUATION.isoformat(),
        'sealed': True, 'scope': {'kind': 'option_chain', 'exchange': 'CFFEX',
            'product': 'MO', 'trading_day': '20260916', 'month': '2610',
            'instruments': members, 'universe_version': 'synthetic-chain-v1',
            'universe_complete': True}, 'trading_day': '20260916',
        'calendar_version': '2026-cn-futures-v1',
        'session': {'session': 'DAY', 'phase': 'CONTINUOUS'},
        'effective_as_of': VALUATION.isoformat(), 'cutoff_inclusive': False,
        'age_reference': VALUATION.isoformat(), 'observation_clock': 'received_us',
        'raw_revision': 999, 'stale_after_us': 30_000_000, 'completeness': 'COMPLETE',
        'expected_count': len(members), 'observed_count': len(members),
        'usable_count': len(members), 'missing_count': 0, 'stale_count': 0,
        'invalid_count': 0, 'rows': market_rows}


def calculate(value=None, bundle=None, requested_at=VALUATION, historical=False):
    return calculate_skew(value or frame(), bundle or reference(), requested_at,
                          historical=historical)


class PricingTest(unittest.TestCase):
    def test_all_independent_oracle_vectors(self):
        for vector in GOLDEN['vectors']:
            with self.subTest(vector=vector['name']):
                t = vector['t_years']
                price = black_price(vector['side'], vector['forward'], vector['strike'], t,
                                    vector['discount'], vector['input_sigma'])
                self.assertAlmostEqual(price, vector['expected_price'], places=9)
                solved = solve_iv(vector['side'], vector['forward'], vector['strike'], t,
                                  vector['discount'], vector['expected_price'])
                self.assertLessEqual(abs(solved['sigma'] - vector['expected_iv']), 1e-7)
                self.assertLessEqual(abs(solved['forward_delta'] - vector['expected_delta']), 1e-8)
                self.assertLessEqual(abs(solved['price_error']),
                                     max(1e-8, 1e-10 * max(vector['forward'], vector['strike'])))

    def test_solver_failure_is_explicit(self):
        cases = [(0, 'NUMERICAL_ERROR'), (100, 'PRICE_OUT_OF_BOUNDS'),
                 (.1, 'TIME_VALUE_TOO_SMALL')]
        for price, reason in cases:
            with self.subTest(price=price), self.assertRaises(SolverFailure) as caught:
                solve_iv('C', 100, 100, .5, 1, price)
            self.assertEqual(caught.exception.reason, reason)
        outside = black_price('C', 100, 100, .5, 1, 6)
        with self.assertRaises(SolverFailure) as caught:
            solve_iv('C', 100, 100, .5, 1, outside)
        self.assertEqual(caught.exception.reason, 'IV_OUT_OF_RANGE')

    def test_solver_sigma_bounds_low_vega_and_iteration_failure(self):
        for sigma in (analytics.SIGMA_MIN, analytics.SIGMA_MAX):
            price = black_price('C', 6000, 6000, 1, 1, sigma)
            solved = solve_iv('C', 6000, 6000, 1, 1, price)
            self.assertLessEqual(abs(solved['sigma'] - sigma), 1e-8)
        low_vega_price = black_price('C', 100, 120, .01, 1, 1)
        with self.assertRaises(SolverFailure) as caught:
            solve_iv('C', 100, 120, .01, 1, low_vega_price)
        self.assertEqual(caught.exception.reason, 'LOW_VEGA')
        market_price = black_price('C', 100, 100, .5, 1, .2)
        with patch.object(analytics, 'MAX_ITERATIONS', 1):
            with self.assertRaises(SolverFailure) as caught:
                solve_iv('C', 100, 100, .5, 1, market_price)
        self.assertEqual(caught.exception.reason, 'IV_NOT_CONVERGED')


class SkewTest(unittest.TestCase):
    def test_actual_market_state_reader_frame_is_consumed(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            path = directory / '20260916.sqlite'
            db = sqlite3.connect(path)
            db.executescript('''
                PRAGMA application_id=1145914161;
                PRAGMA user_version=1;
                CREATE TABLE dataset(singleton INTEGER PRIMARY KEY, trading_day TEXT,
                                     schema_version INTEGER);
                INSERT INTO dataset VALUES(1,'20260916',1);
            ''')
            definitions = []
            for name in OBSERVATION_COLUMNS:
                if name == 'id':
                    definitions.append('id INTEGER PRIMARY KEY')
                elif name in ('sequence', 'received_us', 'snapshot_us', 'UpdateMillisec',
                              'BidVolume1', 'AskVolume1'):
                    definitions.append(name + ' INTEGER')
                elif name in ('TradingDay', 'ExchangeID', 'InstrumentID', 'ExchangeInstID',
                              'ActionDay', 'UpdateTime', 'run_id'):
                    definitions.append(name + ' TEXT')
                else:
                    definitions.append(name + ' REAL')
            db.execute('CREATE TABLE snapshots(' + ','.join(definitions) + ')')
            db.execute('CREATE INDEX snapshots_instrument_time '
                       'ON snapshots(InstrumentID,received_us,id)')
            integration_end = datetime.fromisoformat('2026-09-16T14:57:00+08:00')
            for row in CHAIN['rows']:
                received = micros(integration_end) - row['age_us']
                values = {'id': row['id'], 'run_id': 'synthetic-run',
                          'sequence': row['id'], 'received_us': received,
                          'snapshot_us': received + 1_000_000, 'TradingDay': '20260916',
                          'ExchangeID': 'CFFEX', 'InstrumentID': row['instrument'],
                          'ActionDay': '20260916', 'UpdateTime': '14:56:40',
                          'UpdateMillisec': 0, 'BidPrice1': row['bid'],
                          'AskPrice1': row['ask'], 'BidVolume1': row['bid_volume'],
                          'AskVolume1': row['ask_volume']}
                db.execute('INSERT INTO snapshots(' + ','.join(values) + ') VALUES('
                           + ','.join('?' for _ in values) + ')', tuple(values.values()))
            db.commit()
            db.close()
            (directory / '.collector.lock').touch()
            members = tuple(row['instrument'] for row in CHAIN['rows'])
            universe = Universe('20260916', 'synthetic-chain-v1', members, True)
            scope = Scope.select(universe, 'CFFEX', 'MO', month='2610', option_chain=True)
            reader = MarketStateReader(Store(directory))
            actual_frame = reader.minute(scope, integration_end - timedelta(minutes=1),
                                         evaluated_at=integration_end,
                                         stale_after_us=30_000_000)
            bundle = reference()
            bundle['calendar']['version'] = actual_frame['calendar_version']
            result = calculate_skew(actual_frame, bundle, integration_end, historical=False)
            self.assertEqual(result['status'], 'OK',
                             {'reasons': result['reasons'], 'session': actual_frame['session']})
            self.assertEqual(result['raw_revision'], max(row['id'] for row in CHAIN['rows']))
            self.assertTrue(math.isfinite(result['skew_25d_vp']))

    def test_happy_path_matches_frozen_chain_and_trace(self):
        result = calculate()
        self.assertEqual(result['status'], 'OK')
        self.assertEqual((result['contract_id'], result['algorithm_version']),
                         (CONTRACT_ID, ALGORITHM_VERSION))
        self.assertAlmostEqual(result['forward']['value'], CHAIN['expected_forward'], places=6)
        self.assertLessEqual(abs(result['skew_25d_vp'] - CHAIN['expected_skew_vp']), 2e-5)
        self.assertEqual([pair['call_observation_id'] for pair in result['forward']['pairs']],
                         [pair['call_id'] for pair in CHAIN['expected_forward_pairs']])
        self.assertEqual(result['raw_revision'], 999)
        self.assertEqual(result['universe'], {'version': 'synthetic-chain-v1', 'sha256': HASH})
        self.assertEqual(result['calendar'], {'version': '2026-cn-futures-v1', 'sha256': HASH})
        self.assertEqual(result['reference']['bundle_id'], 'synthetic-reference-v1')
        self.assertEqual(result['algorithm']['pricing_model'], 'BLACK_76')
        self.assertEqual(result['algorithm']['solver']['name'], 'BISECTION')
        json.dumps(result, allow_nan=False)
        self.assertEqual(len(result['provenance']), len(CHAIN['rows']))
        self.assertEqual(result['excluded_count'] + result['eligible_count'],
                         result['expected_count'])
        self.assertTrue(any(row['roles'] for row in result['provenance']))
        self.assertTrue(result['current_usable'])

    def test_other_sign_and_partial_unrelated_missing(self):
        second = GOLDEN['chains'][1]
        result = calculate(frame(second['rows']), reference(second['rows']))
        self.assertLess(result['skew_25d_vp'], 0)
        self.assertLessEqual(abs(result['skew_25d_vp'] - second['expected_skew_vp']), 2e-5)
        partial = frame()
        target = partial['rows'][0]
        target['observation'] = None
        target['quality'] = {'missing': True, 'stale': False, 'invalid': False,
                             'usable': False, 'flags': ['MISSING'], 'reasons': [],
                             'quote_age_us': None}
        partial.update(completeness='PARTIAL', observed_count=len(partial['rows']) - 1,
                       usable_count=len(partial['rows']) - 1, missing_count=1)
        result = calculate(partial)
        self.assertEqual((result['status'], result['reasons']), ('OK', ['PARTIAL_INPUT']))
        self.assertEqual(next(row for row in result['provenance']
                              if row['instrument'] == target['instrument'])['exclusions'], ['MISSING'])

    def test_flat_smile_skew_is_zero(self):
        def flat_solver(side, forward, strike, t_years, discount, market_price):
            x = (.0003 * (strike - 5000) if side == 'P'
                 else .0003 * (7000 - strike))
            return {'sigma': .2, 'forward_delta': -x if side == 'P' else x,
                    'vega': 100, 'model_price': market_price, 'price_error': 0,
                    'iterations': 1, 'bracket': [.2, .2]}

        with patch.object(analytics, 'solve_iv', side_effect=flat_solver):
            result = calculate()
        self.assertEqual(result['status'], 'OK')
        self.assertEqual(result['wings']['P']['iv'], .2)
        self.assertEqual(result['wings']['C']['iv'], .2)
        self.assertEqual(result['skew_25d_vp'], 0)

    def test_stale_invalid_and_missing_are_not_fallbacks(self):
        for mutation, expected in (
            ('stale', 'STALE_QUOTE'), ('future', 'NEGATIVE_AGE'),
            ('invalid', 'INVALID_IDENTITY'), ('missing', 'MISSING')):
            value = frame()
            for row in value['rows']:
                if mutation == 'stale':
                    row['observation']['received_us'] = micros(VALUATION) - 30_000_001
                    row['quality'].update(stale=True, usable=False, flags=['STALE'],
                                          quote_age_us=30_000_001)
                elif mutation == 'future':
                    row['observation']['received_us'] = micros(VALUATION) + 1
                elif mutation == 'invalid':
                    row['observation']['BidPrice1'] = row['observation']['AskPrice1'] + .2
                    row['quality'].update(invalid=True, usable=False, flags=['INVALID'])
                else:
                    row['observation'] = None
                    row['quality'].update(missing=True, usable=False, flags=['MISSING'],
                                          quote_age_us=None)
            result = calculate(value)
            self.assertEqual(result['status'], 'UNAVAILABLE')
            self.assertIn(expected, result['reasons'])
            self.assertIn('FORWARD_PAIRS_MISSING', result['reasons'])
            self.assertIsNone(result['skew_25d_vp'])

        with patch.object(analytics, 'solve_iv', side_effect=SolverFailure('IV_NOT_CONVERGED')):
            result = calculate()
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertIn('IV_NOT_CONVERGED', result['reasons'])
        self.assertIsNone(result['skew_25d_vp'])

    def test_quote_quality_boundaries(self):
        for field, value, reason in (
            ('BidVolume1', 0, 'INVALID_BOOK'), ('BidPrice1', 1.1, 'INVALID_TICK'),
            ('BidPrice1', .2, 'PRICE_TOO_SMALL')):
            market = frame()
            for row in market['rows']:
                row['observation'][field] = value
                if field == 'BidPrice1' and value == .2:
                    row['observation']['AskPrice1'] = .4
            result = calculate(market)
            self.assertIn(reason, result['reasons'])
            self.assertEqual(result['status'], 'UNAVAILABLE')
        market = frame()
        for row in market['rows']:
            row['observation']['BidPrice1'] = .8
            row['observation']['AskPrice1'] = 1.2
        self.assertIn('SPREAD_TOO_WIDE', calculate(market)['reasons'])

    def test_pair_and_forward_synchronization_boundaries(self):
        market = frame()
        calls = {row['observation']['InstrumentID']: row['observation']['received_us']
                 for row in market['rows'] if '-C-' in row['instrument']}
        for row in market['rows']:
            if '-P-' in row['instrument']:
                call_code = row['instrument'].replace('-P-', '-C-')
                row['observation']['received_us'] = calls[call_code] - 5_000_000
        self.assertEqual(calculate(market)['status'], 'OK')

    def test_forward_pair_count_and_consistency_fail_closed(self):
        market = frame()
        kept_put_strikes = {5900, 6000}
        for row in market['rows']:
            if '-P-' in row['instrument']:
                strike = int(row['instrument'].rsplit('-', 1)[1])
                if strike not in kept_put_strikes:
                    row['observation'] = None
                    row['quality'].update(missing=True, usable=False, flags=['MISSING'],
                                          quote_age_us=None)
        result = calculate(market)
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertIn('FORWARD_PAIRS_MISSING', result['reasons'])

        market = frame()
        changes = {'MO2610-C-5900': -20, 'MO2610-C-6100': 20}
        for row in market['rows']:
            change = changes.get(row['instrument'])
            if change is not None:
                row['observation']['BidPrice1'] += change
                row['observation']['AskPrice1'] += change
        result = calculate(market)
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertEqual(result['reasons'], ['FORWARD_INCONSISTENT'])

        market = frame()
        for row in market['rows']:
            if '-P-' in row['instrument']:
                row['observation']['received_us'] -= 5_000_001
        result = calculate(market)
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertIn('FORWARD_PAIRS_MISSING', result['reasons'])
        market = frame()
        pairs = CHAIN['expected_forward_pairs']
        ages = {pairs[0]['call_id']: 0, pairs[0]['put_id']: 0,
                pairs[1]['call_id']: 7_500_000, pairs[1]['put_id']: 7_500_000,
                pairs[2]['call_id']: 15_000_001, pairs[2]['put_id']: 15_000_001}
        for row in market['rows']:
            if row['observation']['id'] in ages:
                row['observation']['received_us'] = micros(VALUATION) - ages[row['observation']['id']]
        result = calculate(market)
        self.assertEqual(result['reasons'], ['FORWARD_UNSYNCHRONIZED'])

        ages[pairs[2]['call_id']] = 15_000_000
        ages[pairs[2]['put_id']] = 15_000_000
        market = frame()
        for row in market['rows']:
            if row['observation']['id'] in ages:
                row['observation']['received_us'] = micros(VALUATION) - ages[row['observation']['id']]
        self.assertEqual(calculate(market)['status'], 'OK')

    def test_age_boundary_and_wing_failure_reasons(self):
        market = frame()
        for row in market['rows']:
            row['observation']['received_us'] = micros(VALUATION) - 30_000_000
            row['quality']['quote_age_us'] = 30_000_000
        result = calculate(market)
        self.assertEqual(result['status'], 'OK')
        self.assertTrue(result['current_usable'])

        def node(instrument, strike, x):
            return {'instrument': instrument, 'observation_id': instrument, 'strike': strike,
                    'sigma': .2, 'forward_delta': -x, 'x': x}

        provenance = {name: {'roles': []} for name in ('a', 'b')}
        with self.assertRaises(SolverFailure) as caught:
            _choose_wing('P', [node('a', 1, .30), node('b', 2, .20)], provenance)
        self.assertEqual(caught.exception.reason, 'NON_MONOTONE_DELTA')
        with self.assertRaises(SolverFailure) as caught:
            _choose_wing('P', [node('a', 1, .15), node('b', 2, .30)], provenance)
        self.assertEqual(caught.exception.reason, 'WING_GAP_TOO_WIDE')
        with self.assertRaises(SolverFailure) as caught:
            _choose_wing('P', [node('a', 1, .20)], {'a': {'roles': []}})
        self.assertEqual(caught.exception.reason, 'WING_UNBRACKETED')

    def test_reference_scope_and_session_fail_closed(self):
        bundle = reference()
        bundle['rate']['fixing_date'] = '20260914'
        self.assertEqual(calculate(bundle=bundle)['reasons'], ['RATE_MISSING'])
        bundle = reference()
        bundle['rate']['decimal'] = .03
        self.assertEqual(calculate(bundle=bundle)['reasons'], ['REFERENCE_INVALID'])
        bundle = reference(); bundle['valid_trading_day'] = '20260915'
        self.assertEqual(calculate(bundle=bundle)['reasons'], ['REFERENCE_INVALID'])
        bundle = reference(); bundle['rate']['day_count'] = 'ACT/365'
        self.assertEqual(calculate(bundle=bundle)['reasons'], ['REFERENCE_INVALID'])
        bundle = reference(); bundle['calendar']['version'] = 'UNKNOWN'
        market = frame(); market['calendar_version'] = 'UNKNOWN'
        self.assertEqual(calculate(market, bundle)['reasons'], ['REFERENCE_INVALID'])
        market = frame()
        market['scope']['universe_complete'] = False
        self.assertEqual(calculate(market)['reasons'], ['UNIVERSE_INCOMPLETE'])
        market = frame(); market['sealed'] = False
        market['minute'] = '2026-09-16T09:30:00+08:00'
        market['minute_end'] = '2026-09-16T09:31:00+08:00'
        market['evaluated_at'] = '2026-09-16T09:30:30+08:00'
        market['effective_as_of'] = market['evaluated_at']
        requested = datetime.fromisoformat(market['evaluated_at'])
        self.assertEqual(calculate(market, requested_at=requested)['reasons'],
                         ['MINUTE_UNSEALED'])
        market = frame(); market['session']['phase'] = 'AUCTION'
        self.assertEqual(calculate(market)['reasons'], ['UNSUPPORTED_SESSION'])

    def test_expiry_historical_reconstructed_and_no_input_mutation(self):
        bundle = reference()
        bundle['expiry_at'] = '2026-09-16T15:00:00+08:00'
        for contract in bundle['universe']['instruments']:
            contract['expiry'] = '20260916'
        before = deepcopy(bundle)
        result = calculate(bundle=bundle)
        self.assertEqual(result['reasons'], ['EXPIRY_DAY_UNSUPPORTED'])
        self.assertEqual(bundle, before)
        bundle = reference()
        bundle['expiry_at'] = '2026-09-15T15:00:00+08:00'
        for contract in bundle['universe']['instruments']:
            contract['expiry'] = '20260915'
        self.assertEqual(calculate(bundle=bundle)['reasons'], ['EXPIRED'])
        bundle = reference()
        bundle['reviewed_at'] = '2026-09-16T16:00:00+08:00'
        result = calculate(bundle=bundle)
        self.assertTrue(result['reconstructed'])
        requested = VALUATION + timedelta(seconds=10)
        result = calculate(requested_at=requested, historical=True)
        self.assertTrue(result['historical'])
        self.assertFalse(result['current_usable'])
        self.assertEqual(result['display_age_us'], 10_000_000)

    def test_negative_rate_day_counts_lunch_history_and_revision_replay(self):
        bundle = reference()
        bundle['rate']['percent'] = -.5
        bundle['rate']['decimal'] = -.005
        result = calculate(bundle=bundle)
        self.assertEqual(result['status'], 'OK')
        seconds = (EXPIRY - VALUATION).total_seconds()
        self.assertEqual(result['t_years'], seconds / (365 * 86400))
        self.assertEqual(result['tau360'], seconds / (360 * 86400))
        self.assertEqual(result['discount'], 1 / (1 - .005 * seconds / (360 * 86400)))
        self.assertGreater(result['discount'], 1)

        market = frame()
        lunch_end = datetime.fromisoformat('2026-09-16T11:30:00+08:00')
        shift_us = micros(VALUATION) - micros(lunch_end)
        market.update(minute='2026-09-16T11:29:00+08:00',
                      minute_end=lunch_end.isoformat(), effective_as_of=lunch_end.isoformat(),
                      evaluated_at='2026-09-16T12:00:00+08:00')
        for row in market['rows']:
            row['observation']['received_us'] -= shift_us
        requested = datetime.fromisoformat(market['evaluated_at'])
        lunch = calculate(market, requested_at=requested, historical=True)
        self.assertEqual(lunch['status'], 'OK')
        self.assertTrue(lunch['historical'])
        self.assertFalse(lunch['current_usable'])

        first = calculate()
        replay = calculate(deepcopy(frame()), deepcopy(reference()))
        self.assertEqual(first, replay)
        revised = frame(); revised['raw_revision'] = 1000
        self.assertEqual(calculate(revised)['raw_revision'], 1000)

    def test_structural_errors_raise_instead_of_becoming_empty(self):
        with self.assertRaises(ValueError):
            calculate_skew(frame(), reference(), VALUATION, historical=None)
        market = frame(); market['stale_after_us'] = 60_000_000
        with self.assertRaises(ValueError):
            calculate(market)
        market = frame(); market['rows'].append(deepcopy(market['rows'][0]))
        with self.assertRaises(ValueError):
            calculate(market)
        market = frame(); market['minute_end'] = market['minute']
        with self.assertRaises(ValueError):
            calculate(market)
        bundle = reference(); del bundle['rate']['decimal']
        with self.assertRaises(ValueError):
            calculate(bundle=bundle)


if __name__ == '__main__':
    unittest.main()
