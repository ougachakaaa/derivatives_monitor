"""Pure MVP MO IV/Skew analytics over a Market Frame minute view.

The module never opens Raw storage, reads current reference files, or supplies
fallback inputs.  Contract: query/contracts/analytics-skew.md (mo-skew-25d-v1).
"""
from datetime import datetime, timedelta
import math
import re

from market_frame import ZONE, aware, micros


CONTRACT_ID = 'mo-skew-25d-v1'
ALGORITHM_VERSION = '1.0.0'
MAX_AGE_US = 30_000_000
MAX_PAIR_SPAN_US = 5_000_000
MAX_INPUT_SPAN_US = 15_000_000
MAX_CURRENT_DISPLAY_AGE_US = 60_000_000
DELTA_TOLERANCE = 1e-10
MIN_DELTA = .10
MAX_DELTA = .40
TARGET_DELTA = .25
MAX_DELTA_GAP = .10
TICK_SIZE = .2
TICK_TOLERANCE = 1e-8
MIN_MID = 1.0
MAX_RELATIVE_SPREAD = .20
SPREAD_TOLERANCE = 1e-12
RATE_MIN = -.05
RATE_MAX = .20
SIGMA_MIN = .0001
SIGMA_MAX = 5.0
SIGMA_TOLERANCE = 1e-8
PRICE_ABSOLUTE_TOLERANCE = 1e-8
PRICE_SCALE_TOLERANCE = 1e-10
MIN_TIME_VALUE = .1
MIN_VEGA = 1.0
MAX_ITERATIONS = 128
YEAR_SECONDS = 365 * 86400
DAY_360_SECONDS = 360 * 86400

CODE = re.compile(r'^MO(\d{4})-([CP])-(\d+(?:\.\d+)?)$')
HEX64 = re.compile(r'^[0-9a-f]{64}$')


class SolverFailure(Exception):
    def __init__(self, reason, details=None):
        super().__init__(reason)
        self.reason = reason
        self.details = details or {}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _required(mapping, fields, label):
    if not isinstance(mapping, dict):
        raise ValueError(f'{label} must be an object')
    missing = [field for field in fields if field not in mapping]
    if missing:
        raise ValueError(f'{label} missing fields: {", ".join(missing)}')


def _timestamp(value, label):
    if not isinstance(value, str):
        raise ValueError(f'{label} must be an aware ISO timestamp')
    try:
        return aware(datetime.fromisoformat(value))
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError(f'{label} must be an aware ISO timestamp') from error


def _normal(value):
    return .5 * math.erfc(-value / math.sqrt(2))


def black_price(side, forward, strike, t_years, discount, sigma):
    """Frozen Black-76 price in index points; all arguments are decimals."""
    if side not in ('C', 'P'):
        raise ValueError('side must be C or P')
    if not all(_finite(v) and v > 0 for v in (forward, strike, t_years, discount, sigma)):
        raise ValueError('Black inputs must be finite and positive')
    width = sigma * math.sqrt(t_years)
    d1 = math.log(forward / strike) / width + width / 2
    d2 = d1 - width
    if side == 'C':
        return discount * (forward * _normal(d1) - strike * _normal(d2))
    return discount * (strike * _normal(-d2) - forward * _normal(-d1))


def solve_iv(side, forward, strike, t_years, discount, market_price):
    """Frozen bounded bisection. Failure is data, never a clipped IV."""
    if side not in ('C', 'P'):
        raise ValueError('side must be C or P')
    if not all(_finite(v) and v > 0 for v in (forward, strike, t_years, discount, market_price)):
        raise SolverFailure('NUMERICAL_ERROR')
    intrinsic = discount * max((forward - strike) if side == 'C' else (strike - forward), 0)
    upper = discount * (forward if side == 'C' else strike)
    if not intrinsic < market_price < upper:
        raise SolverFailure('PRICE_OUT_OF_BOUNDS', {'lower': intrinsic, 'upper': upper})
    if market_price - intrinsic <= MIN_TIME_VALUE:
        raise SolverFailure('TIME_VALUE_TOO_SMALL', {'lower': intrinsic})
    low, high = SIGMA_MIN, SIGMA_MAX
    low_price = black_price(side, forward, strike, t_years, discount, low)
    high_price = black_price(side, forward, strike, t_years, discount, high)
    if not low_price <= market_price <= high_price:
        raise SolverFailure('IV_OUT_OF_RANGE', {'price_at_sigma_min': low_price,
                                                'price_at_sigma_max': high_price})
    price_tolerance = max(PRICE_ABSOLUTE_TOLERANCE,
                          PRICE_SCALE_TOLERANCE * max(forward, strike))
    iterations = 0
    model_price = math.nan
    while iterations < MAX_ITERATIONS:
        iterations += 1
        sigma = (low + high) / 2
        model_price = black_price(side, forward, strike, t_years, discount, sigma)
        if not math.isfinite(model_price):
            raise SolverFailure('NUMERICAL_ERROR')
        if high - low <= SIGMA_TOLERANCE and abs(model_price - market_price) <= price_tolerance:
            width = sigma * math.sqrt(t_years)
            d1 = math.log(forward / strike) / width + width / 2
            vega = discount * forward * math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi) * math.sqrt(t_years)
            if not math.isfinite(vega):
                raise SolverFailure('NUMERICAL_ERROR')
            if vega < MIN_VEGA:
                raise SolverFailure('LOW_VEGA', {'vega': vega})
            delta = _normal(d1) - (1 if side == 'P' else 0)
            return {'sigma': sigma, 'forward_delta': delta, 'vega': vega,
                    'model_price': model_price, 'price_error': model_price - market_price,
                    'iterations': iterations, 'bracket': [low, high]}
        if model_price < market_price:
            low = sigma
        else:
            high = sigma
    raise SolverFailure('IV_NOT_CONVERGED', {'iterations': iterations,
                                              'bracket': [low, high],
                                              'price_error': model_price - market_price})


def _parse_reference(reference):
    _required(reference, ('schema_version', 'bundle_id', 'bundle_sha256', 'valid_trading_day',
                          'exchange', 'product', 'month', 'reviewed_at', 'review', 'source_kind',
                          'universe', 'calendar', 'product_rules', 'expiry_at', 'rate'), 'reference')
    _required(reference['universe'], ('version', 'sha256', 'instruments'), 'reference.universe')
    _required(reference['calendar'], ('version', 'sha256', 'previous_cffex_trading_day'),
              'reference.calendar')
    _required(reference['product_rules'], ('underlying_index', 'exercise', 'settlement', 'currency',
              'price_unit', 'tick_size', 'multiplier', 'source_url', 'source_version',
              'source_sha256'), 'reference.product_rules')
    _required(reference['rate'], ('name', 'tenor', 'percent', 'decimal', 'fixing_date',
              'published_at', 'source_url', 'source_sha256', 'retrieved_at', 'day_count',
              'compounding', 'settlement'), 'reference.rate')
    if not isinstance(reference['universe']['instruments'], list):
        raise ValueError('reference.universe.instruments must be a list')
    contracts = {}
    for index, item in enumerate(reference['universe']['instruments']):
        _required(item, ('id', 'side', 'strike', 'expiry'), f'reference contract {index}')
        if not isinstance(item['id'], str) or item['id'] in contracts:
            raise ValueError('reference contract IDs must be unique strings')
        if item['side'] not in ('C', 'P') or not _finite(item['strike']) or item['strike'] <= 0:
            raise ValueError('reference contract side/strike invalid')
        contracts[item['id']] = item
    return contracts


def _base_output(frame, reference, valuation_at, requested_at, historical):
    return {
        'schema_version': 1, 'contract_id': CONTRACT_ID,
        'algorithm_version': ALGORITHM_VERSION, 'status': 'UNAVAILABLE', 'reasons': [],
        'scope': frame['scope'], 'valuation_at': valuation_at.isoformat(),
        'requested_at': requested_at.isoformat(), 'historical': historical,
        'current_usable': False, 'reconstructed': False,
        'display_age_us': micros(requested_at) - micros(valuation_at),
        'observation_clock': frame.get('observation_clock'), 'raw_revision': frame['raw_revision'],
        'universe': {'version': frame['scope'].get('universe_version'),
                     'sha256': reference['universe']['sha256']},
        'calendar': {'version': frame.get('calendar_version'),
                     'sha256': reference['calendar']['sha256']},
        'reference': {'bundle_id': reference['bundle_id'],
                      'sha256': reference['bundle_sha256'],
                      'source_kind': reference['source_kind'],
                      'reviewed_at': reference['reviewed_at'],
                      'universe_sha256': reference['universe']['sha256'],
                      'calendar_sha256': reference['calendar']['sha256'],
                      'product_rules_sha256': reference['product_rules']['source_sha256'],
                      'rate_sha256': reference['rate']['source_sha256'],
                      'rate_fixing_date': reference['rate']['fixing_date']},
        'algorithm': {
            'pricing_model': 'BLACK_76',
            'forward': 'PUT_CALL_PARITY_MEDIAN_3',
            'delta': 'UNDISCOUNTED_UNADJUSTED_FORWARD',
            'skew': '100*(put_iv_25-call_iv_25)',
            'interpolation': 'LINEAR_SIGMA_IN_ABS_DELTA',
            'solver': {'name': 'BISECTION', 'sigma_min': SIGMA_MIN,
                       'sigma_max': SIGMA_MAX, 'max_iterations': MAX_ITERATIONS,
                       'sigma_bracket_tolerance': SIGMA_TOLERANCE,
                       'price_absolute_tolerance': PRICE_ABSOLUTE_TOLERANCE,
                       'price_scale_tolerance': PRICE_SCALE_TOLERANCE,
                       'min_time_value_points_exclusive': MIN_TIME_VALUE,
                       'min_vega_per_unit_sigma': MIN_VEGA},
            'quotes': {'price': 'BID_ASK_MID', 'max_age_us': MAX_AGE_US,
                       'max_pair_span_us': MAX_PAIR_SPAN_US,
                       'max_input_span_us': MAX_INPUT_SPAN_US,
                       'min_mid_points': MIN_MID,
                       'max_relative_spread': MAX_RELATIVE_SPREAD,
                       'tick_size': TICK_SIZE}},
        'input_completeness': frame.get('completeness'),
        'expected_count': frame.get('expected_count'),
        'observed_count': frame.get('observed_count'), 'eligible_count': 0,
        'excluded_count': 0,
        'forward': None, 'rate_decimal': None, 't_years': None, 'tau360': None,
        'discount': None, 'effective_rate': None,
        'discount_convention': 'SHIBOR_3M_FLAT_SIMPLE_ACT360',
        'dividend_yield': None, 'wings': None, 'skew_25d_vp': None, 'provenance': []
    }


def _semantic_reference_reasons(frame, reference, contracts, valuation_at):
    reasons = []
    scope = frame['scope']
    hashes = (reference['bundle_sha256'], reference['universe']['sha256'],
              reference['calendar']['sha256'], reference['product_rules']['source_sha256'],
              reference['rate']['source_sha256'])
    if reference['schema_version'] != 1 or any(not isinstance(h, str) or not HEX64.fullmatch(h) for h in hashes):
        reasons.append('REFERENCE_INVALID')
    if not isinstance(reference['bundle_id'], str) or not reference['bundle_id'].strip():
        reasons.append('REFERENCE_INVALID')
    if (reference['exchange'], reference['product'], reference['month']) != ('CFFEX', 'MO', scope['month']):
        reasons.append('REFERENCE_INVALID')
    if reference['valid_trading_day'] != frame['trading_day']:
        reasons.append('REFERENCE_INVALID')
    if reference['source_kind'] not in ('OFFICIAL', 'SYNTHETIC'):
        reasons.append('REFERENCE_INVALID')
    if (reference['source_kind'] == 'SYNTHETIC'
            and (not isinstance(reference['review'], str)
                 or 'TEST DOUBLE' not in reference['review'])):
        reasons.append('REFERENCE_INVALID')
    try:
        reviewed = _timestamp(reference['reviewed_at'], 'reference.reviewed_at')
        expiry = _timestamp(reference['expiry_at'], 'reference.expiry_at')
        published = _timestamp(reference['rate']['published_at'], 'reference.rate.published_at')
        retrieved = _timestamp(reference['rate']['retrieved_at'], 'reference.rate.retrieved_at')
    except ValueError:
        return ['REFERENCE_INVALID'], None, None
    expected_expiry = expiry.strftime('%Y%m%d')
    if expiry.timetz().replace(tzinfo=None) != datetime.strptime('15:00:00', '%H:%M:%S').time():
        reasons.append('REFERENCE_INVALID')
    if any((item['expiry'] != expected_expiry or CODE.fullmatch(item['id']) is None
            or CODE.fullmatch(item['id']).group(1) != scope['month']
            or CODE.fullmatch(item['id']).group(2) != item['side']
            or not math.isclose(float(CODE.fullmatch(item['id']).group(3)), item['strike'],
                                rel_tol=0, abs_tol=1e-12))
           for item in contracts.values()):
        reasons.append('REFERENCE_INVALID')
    contract_keys = [(item['side'], item['strike']) for item in contracts.values()]
    if len(set(contract_keys)) != len(contract_keys):
        reasons.append('REFERENCE_INVALID')
    rules = reference['product_rules']
    expected_rules = ('CSI1000', 'EUROPEAN', 'CASH', 'CNY', 'INDEX_POINT')
    if tuple(rules[key] for key in ('underlying_index', 'exercise', 'settlement', 'currency', 'price_unit')) != expected_rules:
        reasons.append('REFERENCE_INVALID')
    if rules['tick_size'] != TICK_SIZE or rules['multiplier'] != 100:
        reasons.append('REFERENCE_INVALID')
    if any(not isinstance(rules[key], str) or not rules[key].strip()
           for key in ('source_url', 'source_version')):
        reasons.append('REFERENCE_INVALID')
    rate = reference['rate']
    if tuple(rate[key] for key in ('name', 'tenor', 'day_count', 'compounding', 'settlement')) != (
            'SHIBOR', '3M', 'ACT/360', 'SIMPLE', 'T+0'):
        reasons.append('REFERENCE_INVALID')
    if not isinstance(rate['source_url'], str) or not rate['source_url'].strip():
        reasons.append('REFERENCE_INVALID')
    previous = reference['calendar']['previous_cffex_trading_day']
    if rate['fixing_date'] != previous:
        reasons.append('RATE_MISSING')
    try:
        for value in (previous, rate['fixing_date']):
            if datetime.strptime(value, '%Y%m%d').strftime('%Y%m%d') != value:
                raise ValueError
    except (ValueError, TypeError):
        reasons.append('REFERENCE_INVALID')
    try:
        day_start = datetime.strptime(reference['valid_trading_day'] + '0900+0800',
                                      '%Y%m%d%H%M%z').astimezone(ZONE)
    except (ValueError, TypeError):
        return ['REFERENCE_INVALID'], None, None
    if published >= day_start:
        reasons.append('REFERENCE_INVALID')
    if (not _finite(rate['percent']) or not _finite(rate['decimal'])
            or not math.isclose(rate['decimal'], rate['percent'] / 100, rel_tol=0, abs_tol=1e-15)
            or not RATE_MIN <= rate['decimal'] <= RATE_MAX):
        reasons.append('REFERENCE_INVALID')
    versions = (scope.get('universe_version'), frame.get('calendar_version'),
                reference['universe']['version'], reference['calendar']['version'])
    if (any(not isinstance(version, str) or not version.strip()
            or version.upper() == 'UNKNOWN' for version in versions)
            or reference['universe']['version'] != scope.get('universe_version')
            or reference['calendar']['version'] != frame.get('calendar_version')):
        reasons.append('REFERENCE_INVALID')
    if not isinstance(reference['review'], str) or not reference['review'].strip():
        reasons.append('REFERENCE_INVALID')
    if set(contracts) != set(scope['instruments']):
        reasons.append('REFERENCE_INVALID')
    if not scope.get('universe_complete'):
        reasons.append('UNIVERSE_INCOMPLETE')
    return sorted(set(reasons)), expiry, {'reviewed': reviewed, 'retrieved': retrieved}


def _quote_record(row, contract, valuation_us, trading_day):
    instrument = row.get('instrument')
    observation = row.get('observation')
    quality = row.get('quality') if isinstance(row.get('quality'), dict) else {}
    record = {'instrument': instrument, 'trading_day': trading_day,
              'observation_id': None, 'run_id': None,
              'received_us': None, 'snapshot_us': None, 'source_time': None,
              'side': contract.get('side') if contract else None,
              'strike': contract.get('strike') if contract else None,
              'bid': None, 'ask': None, 'mid': None, 'quality': quality,
              'eligible': False, 'exclusions': [], 'roles': [], 'solver': None}
    reasons = []
    if observation is None:
        reasons.append('MISSING')
    else:
        record.update(observation_id=observation.get('id'), run_id=observation.get('run_id'),
                      received_us=observation.get('received_us'), snapshot_us=observation.get('snapshot_us'),
                      source_time={'TradingDay': observation.get('TradingDay'),
                                   'ActionDay': observation.get('ActionDay'),
                                   'UpdateTime': observation.get('UpdateTime'),
                                   'UpdateMillisec': observation.get('UpdateMillisec')},
                      bid=observation.get('BidPrice1'), ask=observation.get('AskPrice1'))
        if (contract is None or observation.get('InstrumentID') != instrument
                or observation.get('TradingDay') != trading_day
                or observation.get('ExchangeID') not in ('', 'CFFEX')
                or not isinstance(observation.get('run_id'), str)
                or not observation.get('run_id')
                or type(observation.get('snapshot_us')) is not int
                or quality.get('invalid')):
            reasons.append('INVALID_IDENTITY')
        if quality.get('missing'):
            reasons.append('MISSING')
        if quality.get('stale'):
            reasons.append('STALE_QUOTE')
        bid, ask = record['bid'], record['ask']
        bv, av = observation.get('BidVolume1'), observation.get('AskVolume1')
        if (not _finite(bid) or not _finite(ask) or bid <= 0 or ask <= 0 or bid > ask
                or type(bv) is not int or type(av) is not int or bv < 1 or av < 1):
            reasons.append('INVALID_BOOK')
        if _finite(bid) and _finite(ask):
            if any(abs(value - round(value / TICK_SIZE) * TICK_SIZE) > TICK_TOLERANCE
                   for value in (bid, ask)):
                reasons.append('INVALID_TICK')
            mid = (bid + ask) / 2
            record['mid'] = mid
            if mid < MIN_MID:
                reasons.append('PRICE_TOO_SMALL')
            elif (ask - bid) / mid > MAX_RELATIVE_SPREAD + SPREAD_TOLERANCE:
                reasons.append('SPREAD_TOO_WIDE')
        received = record['received_us']
        if type(received) is not int or received > valuation_us:
            reasons.append('NEGATIVE_AGE')
        elif valuation_us - received > MAX_AGE_US:
            reasons.append('STALE_QUOTE')
    record['exclusions'] = sorted(set(reasons))
    record['eligible'] = not record['exclusions']
    return record


def _unavailable(output, reasons):
    output['reasons'] = sorted(set(reasons))
    for record in output.get('provenance', []):
        record['exclusions'].sort()
        record['roles'].sort()
    return output


def _choose_wing(side, nodes, provenance):
    ordered = sorted(nodes, key=lambda node: (node['strike'], node['instrument']))
    for left, right in zip(ordered, ordered[1:]):
        change = right['x'] - left['x']
        if (side == 'P' and change < -DELTA_TOLERANCE) or (side == 'C' and change > DELTA_TOLERANCE):
            raise SolverFailure('NON_MONOTONE_DELTA')
    by_x = sorted(nodes, key=lambda node: (node['x'], node['strike'], node['instrument']))
    deduplicated, discarded = [], []
    cursor = 0
    while cursor < len(by_x):
        anchor = by_x[cursor]['x']
        end = cursor + 1
        while end < len(by_x) and by_x[end]['x'] - anchor <= DELTA_TOLERANCE:
            end += 1
        group = by_x[cursor:end]
        chosen = min(group, key=lambda node: (node['strike'], node['instrument']))
        deduplicated.append(chosen)
        discarded.extend(node for node in group if node is not chosen)
        cursor = end
    for node in discarded:
        provenance[node['instrument']]['roles'].append('DELTA_DUPLICATE_DISCARDED')
    exact = sorted((node for node in deduplicated if abs(node['x'] - TARGET_DELTA) <= DELTA_TOLERANCE),
                   key=lambda node: (abs(node['x'] - TARGET_DELTA), node['strike'], node['instrument']))
    if exact:
        selected = exact[0]
        provenance[selected['instrument']]['roles'].append(side + '_WING_EXACT')
        return {'side': side, 'method': 'EXACT', 'iv': selected['sigma'],
                'nodes': [_public_node(selected, 1.0)], 'discarded': [n['instrument'] for n in discarded]}
    lows = [node for node in deduplicated if node['x'] < TARGET_DELTA]
    highs = [node for node in deduplicated if node['x'] > TARGET_DELTA]
    if not lows or not highs:
        raise SolverFailure('WING_UNBRACKETED')
    low = max(lows, key=lambda node: node['x'])
    high = min(highs, key=lambda node: node['x'])
    gap = high['x'] - low['x']
    if gap > MAX_DELTA_GAP + DELTA_TOLERANCE:
        raise SolverFailure('WING_GAP_TOO_WIDE', {'gap': gap})
    alpha = (TARGET_DELTA - low['x']) / gap
    iv = (1 - alpha) * low['sigma'] + alpha * high['sigma']
    provenance[low['instrument']]['roles'].append(side + '_WING_LOW')
    provenance[high['instrument']]['roles'].append(side + '_WING_HIGH')
    return {'side': side, 'method': 'LINEAR_SIGMA_IN_ABS_DELTA', 'iv': iv,
            'alpha': alpha, 'delta_gap': gap,
            'nodes': [_public_node(low, 1 - alpha), _public_node(high, alpha)],
            'discarded': [n['instrument'] for n in discarded]}


def _public_node(node, weight):
    return {'instrument': node['instrument'], 'observation_id': node['observation_id'],
            'strike': node['strike'], 'sigma': node['sigma'],
            'forward_delta': node['forward_delta'], 'abs_delta': node['x'], 'weight': weight}


def calculate_skew(frame, reference, requested_at, *, historical):
    """Calculate one sealed MO continuous minute; returns JSON-compatible data."""
    _required(frame, ('schema_version', 'kind', 'minute', 'minute_end', 'evaluated_at',
              'sealed', 'scope', 'trading_day', 'calendar_version', 'session',
              'effective_as_of', 'observation_clock', 'raw_revision', 'stale_after_us', 'completeness',
              'expected_count', 'observed_count', 'rows'), 'frame')
    _required(frame['scope'], ('kind', 'exchange', 'product', 'trading_day', 'month',
              'instruments', 'universe_version', 'universe_complete'), 'frame.scope')
    _required(frame['session'], ('phase',), 'frame.session')
    if (frame['schema_version'] != 1 or frame['kind'] != 'minute'
            or frame['scope']['kind'] != 'option_chain'
            or (frame['scope']['exchange'], frame['scope']['product']) != ('CFFEX', 'MO')
            or not isinstance(frame['scope']['month'], str)
            or not isinstance(frame['scope']['instruments'], list)
            or any(not isinstance(code, str) for code in frame['scope']['instruments'])
            or len(set(frame['scope']['instruments'])) != len(frame['scope']['instruments'])
            or not isinstance(frame['rows'], list)
            or type(frame['sealed']) is not bool
            or frame['scope']['trading_day'] != frame['trading_day']
            or type(frame['scope']['universe_complete']) is not bool
            or type(frame['raw_revision']) is not int or frame['raw_revision'] < 0
            or frame['observation_clock'] != 'received_us'
            or frame['completeness'] not in ('COMPLETE', 'PARTIAL', 'EMPTY')):
        raise ValueError('Analytics requires a Market Frame v1 MO option_chain minute view')
    if frame['stale_after_us'] != MAX_AGE_US:
        raise ValueError('Analytics requires Market Frame stale_after_us=30000000')
    contracts = _parse_reference(reference)
    valuation_at = _timestamp(frame['effective_as_of'], 'frame.effective_as_of')
    minute_at = _timestamp(frame['minute'], 'frame.minute')
    minute_end = _timestamp(frame['minute_end'], 'frame.minute_end')
    evaluated_at = _timestamp(frame['evaluated_at'], 'frame.evaluated_at')
    if minute_end - minute_at != timedelta(minutes=1):
        raise ValueError('Analytics requires an exact one-minute frame')
    if frame['sealed']:
        if valuation_at != minute_end or evaluated_at < minute_end:
            raise ValueError('sealed Analytics valuation_at must equal the minute end')
    elif valuation_at != evaluated_at or not minute_at <= valuation_at < minute_end:
        raise ValueError('unsealed Analytics valuation_at must equal evaluated_at within the minute')
    requested_at = aware(requested_at)
    if requested_at < valuation_at:
        raise ValueError('requested_at precedes valuation_at')
    if type(historical) is not bool:
        raise ValueError('historical must be an explicit boolean')
    output = _base_output(frame, reference, valuation_at, requested_at, historical)
    reasons, expiry, reference_times = _semantic_reference_reasons(
        frame, reference, contracts, valuation_at)
    if reasons:
        return _unavailable(output, reasons)
    output['reconstructed'] = max(reference_times.values()) > valuation_at
    if not frame.get('sealed'):
        return _unavailable(output, ['MINUTE_UNSEALED'])
    if frame['session']['phase'] != 'CONTINUOUS':
        return _unavailable(output, ['UNSUPPORTED_SESSION'])
    if valuation_at.date() == expiry.date():
        return _unavailable(output, ['EXPIRY_DAY_UNSUPPORTED'])
    if valuation_at >= expiry:
        return _unavailable(output, ['EXPIRED'])
    seconds = (expiry - valuation_at).total_seconds()
    t_years, tau360 = seconds / YEAR_SECONDS, seconds / DAY_360_SECONDS
    if not 0 < t_years <= 1:
        return _unavailable(output, ['REFERENCE_INVALID'])
    rate = reference['rate']['decimal']
    denominator = 1 + rate * tau360
    if not math.isfinite(denominator) or denominator <= 0:
        return _unavailable(output, ['REFERENCE_INVALID'])
    discount = 1 / denominator
    output.update(rate_decimal=rate, t_years=t_years, tau360=tau360, discount=discount,
                  effective_rate=math.log1p(rate * tau360) / t_years)
    valuation_us = micros(valuation_at)
    rows_by_instrument = {}
    observation_ids = set()
    for row in frame['rows']:
        if not isinstance(row, dict) or not isinstance(row.get('instrument'), str):
            raise ValueError('frame rows require unique instrument strings')
        if row['instrument'] in rows_by_instrument:
            raise ValueError('frame contains duplicate instruments')
        observation = row.get('observation')
        if observation is not None:
            if (not isinstance(observation, dict) or type(observation.get('id')) is not int
                    or observation.get('id') < 0 or observation.get('id') in observation_ids):
                raise ValueError('frame observations require unique IDs')
            observation_ids.add(observation.get('id'))
        rows_by_instrument[row['instrument']] = row
    if set(rows_by_instrument) != set(frame['scope']['instruments']):
        raise ValueError('frame rows differ from scope members')
    provenance = {code: _quote_record(rows_by_instrument[code], contracts.get(code), valuation_us,
                                      frame['trading_day'])
                  for code in sorted(rows_by_instrument)}
    output['provenance'] = list(provenance.values())
    eligible = [record for record in provenance.values() if record['eligible']]
    excluded_reasons = sorted({reason for record in provenance.values() for reason in record['exclusions']})
    output['eligible_count'] = len(eligible)
    output['excluded_count'] = len(provenance) - len(eligible)
    grouped = {}
    for record in eligible:
        grouped.setdefault(record['strike'], {})[record['side']] = record
    pairs = []
    for strike, sides in grouped.items():
        if set(sides) != {'C', 'P'}:
            continue
        call, put = sides['C'], sides['P']
        if abs(call['received_us'] - put['received_us']) > MAX_PAIR_SPAN_US:
            call['roles'].append('FORWARD_PAIR_UNSYNCHRONIZED')
            put['roles'].append('FORWARD_PAIR_UNSYNCHRONIZED')
            continue
        pairs.append((abs(call['mid'] - put['mid']), strike, call, put))
    pairs.sort(key=lambda pair: (pair[0], pair[1], pair[2]['instrument'], pair[3]['instrument']))
    selected_pairs = pairs[:3]
    if len(selected_pairs) < 3:
        return _unavailable(output, excluded_reasons + ['FORWARD_PAIRS_MISSING'])
    pair_inputs = [record for pair in selected_pairs for record in pair[2:]]
    pair_span = max(r['received_us'] for r in pair_inputs) - min(r['received_us'] for r in pair_inputs)
    if pair_span > MAX_INPUT_SPAN_US:
        return _unavailable(output, ['FORWARD_UNSYNCHRONIZED'])
    forwards = [strike + (call['mid'] - put['mid']) / discount
                for _, strike, call, put in selected_pairs]
    if any(not math.isfinite(value) or value <= 0 for value in forwards):
        return _unavailable(output, ['FORWARD_INCONSISTENT'])
    forward = sorted(forwards)[1]
    deviations = [abs(value - forward) / forward for value in forwards]
    details = []
    for pair, value, deviation in zip(selected_pairs, forwards, deviations):
        _, strike, call, put = pair
        call['roles'].append('FORWARD_PAIR')
        put['roles'].append('FORWARD_PAIR')
        details.append({'strike': strike, 'call_instrument': call['instrument'],
                        'call_observation_id': call['observation_id'], 'call_mid': call['mid'],
                        'put_instrument': put['instrument'],
                        'put_observation_id': put['observation_id'], 'put_mid': put['mid'],
                        'forward': value, 'relative_deviation': deviation})
    output['forward'] = {'value': forward, 'method': 'PUT_CALL_PARITY_MEDIAN_3',
                         'selection_rank': ['abs(call_mid-put_mid)', 'strike',
                                            'call_instrument_id', 'put_instrument_id'],
                         'pairs': details, 'time_span_us': pair_span,
                         'max_relative_deviation': max(deviations)}
    if max(deviations) > .001:
        return _unavailable(output, ['FORWARD_INCONSISTENT'])
    nodes = {'P': [], 'C': []}
    solver_reasons = []
    forward_ids = {record['observation_id'] for record in pair_inputs}
    for record in eligible:
        side, strike = record['side'], record['strike']
        if (side == 'P' and strike >= forward) or (side == 'C' and strike <= forward):
            continue
        if max([r['received_us'] for r in pair_inputs] + [record['received_us']]) - min(
                [r['received_us'] for r in pair_inputs] + [record['received_us']]) > MAX_INPUT_SPAN_US:
            record['roles'].append('WING_INPUT_UNSYNCHRONIZED')
            continue
        try:
            solution = solve_iv(side, forward, strike, t_years, discount, record['mid'])
            record['solver'] = solution
            x = abs(solution['forward_delta'])
            if MIN_DELTA - DELTA_TOLERANCE <= x <= MAX_DELTA + DELTA_TOLERANCE:
                nodes[side].append({'instrument': record['instrument'],
                    'observation_id': record['observation_id'], 'strike': strike,
                    'sigma': solution['sigma'], 'forward_delta': solution['forward_delta'], 'x': x})
                record['roles'].append(side + '_WING_CANDIDATE')
        except SolverFailure as failure:
            record['solver'] = {'status': 'FAILED', 'reason': failure.reason, **failure.details}
            record['roles'].append('IV_FAILED')
            solver_reasons.append(failure.reason)
    try:
        wings = {side: _choose_wing(side, nodes[side], provenance) for side in ('P', 'C')}
    except SolverFailure as failure:
        return _unavailable(output, solver_reasons + [failure.reason])
    used_ids = set(forward_ids)
    for wing in wings.values():
        used_ids.update(node['observation_id'] for node in wing['nodes'])
    used = [record for record in provenance.values() if record['observation_id'] in used_ids]
    input_span = max(record['received_us'] for record in used) - min(record['received_us'] for record in used)
    if input_span > MAX_INPUT_SPAN_US:
        return _unavailable(output, ['INPUTS_UNSYNCHRONIZED'])
    output['wings'] = wings
    output['skew_25d_vp'] = 100 * (wings['P']['iv'] - wings['C']['iv'])
    output['status'] = 'OK'
    output['reasons'] = ['PARTIAL_INPUT'] if frame['completeness'] == 'PARTIAL' else []
    newest_requested_age = max(micros(requested_at) - record['received_us'] for record in used)
    output['current_usable'] = (not output['historical']
        and output['display_age_us'] <= MAX_CURRENT_DISPLAY_AGE_US
        and newest_requested_age <= MAX_AGE_US)
    output['forward']['final_input_span_us'] = input_span
    for record in output['provenance']:
        record['roles'].sort()
    return output
