"""MO business queries over Market Frame and frozen Analytics, without Raw SQL."""
from datetime import timedelta
from pathlib import Path
import re
import time

from analytics import ALGORITHM_VERSION, CONTRACT_ID, calculate_skew
from market_calendar import Calendar, CalendarError, parse_at, parse_day
from market_frame import MarketFrameReader, micros
from skew_references import IDENTIFIER, ReferenceUnavailable, read_bytes
from storage import QueryError

MINUTE = timedelta(minutes=1)
QUALITY_REASONS = {
    'invalid_BidPrice1': 'invalid_bid', 'invalid_AskPrice1': 'invalid_ask',
    'invalid_BidVolume1': 'invalid_bid_size', 'invalid_AskVolume1': 'invalid_ask_size',
}


def latest_minute(calendar, at):
    """Frozen Skew selection; calendar minutes, never search for older quotes."""
    state = calendar.query('CFFEX', 'MO', at)
    if state['session_state'] == 'UNKNOWN':
        return None, None, True, 'CALENDAR_UNKNOWN', state
    if state['is_continuous']:
        period = state['current_session']
        minute = at.replace(second=0, microsecond=0) - MINUTE
        if minute < parse_at(period['start']):
            return None, period['trading_day'], False, 'WAITING_FOR_MINUTE', state
        return minute, period['trading_day'], False, None, state
    periods = calendar.periods('CFFEX', 'MO')
    period = next((p for p in reversed(periods)
                   if p['phase'] == 'CONTINUOUS' and p['end'] <= at), None)
    if period is None:
        return None, None, True, 'CALENDAR_UNKNOWN', state
    return period['end'] - MINUTE, period['trading_day'], True, None, state


def unavailable(month, day, at, reason, minute=None, historical=True):
    end = minute + MINUTE if minute is not None else None
    cutoff = min(end, at) if end else None
    return dict(schema_version=1, contract_id=CONTRACT_ID, algorithm_version=ALGORITHM_VERSION,
                status='UNAVAILABLE', reasons=[reason],
                scope={'exchange': 'CFFEX', 'product': 'MO', 'month': month, 'trading_day': day},
                minute=minute.isoformat() if minute else None,
                minute_end=end.isoformat() if end else None, sealed=end <= at if end else None,
                valuation_at=cutoff.isoformat() if cutoff else None,
                effective_as_of=cutoff.isoformat() if cutoff else None, requested_at=at.isoformat(),
                evaluated_at=at.isoformat(), historical=historical, current_usable=False,
                reconstructed=None, display_age_us=micros(at) - micros(cutoff) if cutoff else None,
                raw_revision=None, universe=None, calendar=None, reference=None,
                quality=None, session=None, skew_25d_vp=None, unit='vol_point',
                provenance=[], forward=None, wings=None)


def public_result(result, frame):
    # Analytics output is explicit business data; do not serialize the Raw frame.
    result = {key: result[key] for key in (
        'schema_version', 'contract_id', 'algorithm_version', 'status', 'reasons',
        'valuation_at', 'requested_at', 'historical', 'current_usable', 'reconstructed',
        'display_age_us', 'observation_clock', 'raw_revision', 'universe', 'calendar',
        'reference', 'algorithm', 'input_completeness', 'expected_count', 'observed_count',
        'eligible_count', 'excluded_count', 'forward', 'rate_decimal', 't_years', 'tau360',
        'discount', 'effective_rate', 'discount_convention', 'dividend_yield', 'wings',
        'skew_25d_vp', 'provenance')}
    result['scope'] = {k: frame['scope'][k] for k in ('exchange', 'product', 'month', 'trading_day')}
    result.update(minute=frame['minute'], minute_end=frame['minute_end'], sealed=frame['sealed'],
                  effective_as_of=frame['effective_as_of'],
                  evaluated_at=frame['evaluated_at'], session=frame['session'], unit='vol_point',
                  quality={k: frame[k] for k in ('completeness', 'expected_count', 'observed_count',
                            'usable_count', 'missing_count', 'stale_count', 'invalid_count')})
    for record in result['provenance']:
        record['quality'] = dict(record['quality'], reasons=[QUALITY_REASONS.get(r, r)
                                for r in record['quality']['reasons']])
        source = record['source_time']
        if source is not None:
            record['source_time'] = dict(trading_day=source['TradingDay'], action_day=source['ActionDay'],
                                        time=source['UpdateTime'], millisec=source['UpdateMillisec'])
    return result


class SkewService:
    def __init__(self, store, references, calendar_directory, target_month=None):
        self.store = store
        self.references = references
        self.calendar_directory = Path(calendar_directory)
        self.target_month = target_month

    def query(self, mode, *, month=None, at=None, day=None, minute=None,
              raw_revision=None, bundle_id=None):
        result = self._query(mode, month=month, at=at, day=day, minute=minute,
                             raw_revision=raw_revision, bundle_id=bundle_id)
        if mode == 'series':
            result.setdefault('points', [])
            result.setdefault('baseline', None)
            result.setdefault('change_vp', None)
            result.setdefault('change_minute', None)
        return result

    def _query(self, mode, *, month, at, day, minute, raw_revision, bundle_id):
        try:
            at = parse_at(at)
            month = self.target_month if month is None else month
            if month is not None and not re.fullmatch(r'[0-9]{2}(?:0[1-9]|1[0-2])', month):
                raise ValueError('month')
            if raw_revision is not None and (type(raw_revision) is not int or raw_revision < 0):
                raise ValueError('revision')
            if bundle_id is not None and not IDENTIFIER.fullmatch(bundle_id):
                raise ValueError('bundle')
            if day is not None:
                parse_day(day)
            if mode == 'minute':
                minute = parse_at(minute)
                if minute.second or minute.microsecond or minute > at:
                    raise ValueError('minute')
                if day != minute.strftime('%Y%m%d'):
                    raise ValueError('minute/day')
        except (ValueError, TypeError, OverflowError):
            raise QueryError(400, 'Invalid Skew query parameters (timezone and whole minute required)') from None
        if month is None:
            return unavailable(None, day, at, 'TARGET_MONTH_MISSING')

        context = None
        reference_error = None
        if mode != 'latest':
            try:
                context = self.references.load(day, month, bundle_id)
            except ReferenceUnavailable as error:
                reference_error = error.reason
        try:
            calendar = context.calendar if context else Calendar(
                None, content=read_bytes(self.calendar_directory / f'{(day or str(at.year))[:4]}.json'))
        except (CalendarError, OSError, ValueError):
            return unavailable(month, day, at, 'CALENDAR_UNKNOWN', minute if mode == 'minute' else None)
        selected, selected_day, historical, selection_error, state = latest_minute(calendar, at)
        if mode == 'latest':
            minute, day = selected, selected_day
            if selection_error:
                result = unavailable(month, day, at, selection_error, historical=historical)
                result['market_session'] = state
                return result
            try:
                context = self.references.load(day, month, bundle_id)
                # A latest query cannot select with one calendar and compute with another.
                if context.calendar.data != calendar.data:
                    raise ReferenceUnavailable('REFERENCE_INVALID')
                calendar = context.calendar
            except ReferenceUnavailable as error:
                reference_error = error.reason
        if mode == 'series':
            return self._series(month, day, at, raw_revision, context, calendar, reference_error)
        if mode == 'minute':
            historical = True  # Explicit replay never claims to be a current quote.
            period = next((p for p in calendar.periods('CFFEX', 'MO')
                           if p['start'] <= minute and minute + MINUTE <= p['end']
                           and p['trading_day'] == day), None)
            if period is None or period['phase'] != 'CONTINUOUS':
                return unavailable(month, day, at, 'UNSUPPORTED_SESSION', minute)
            if minute + MINUTE > at:
                return unavailable(month, day, at, 'MINUTE_UNSEALED', minute)
        if reference_error:
            return unavailable(month, day, at, reference_error, minute, historical) | {'market_session': state}
        result = self._calculate(context, minute, at, historical, raw_revision)
        result['market_session'] = state
        return result

    def _calculate(self, context, minute, at, historical, revision):
        reader = MarketFrameReader(self.store, calendar=context.calendar)
        try:
            frame = reader.minute(context.scope, minute, evaluated_at=at,
                                  stale_after_us=30_000_000, raw_revision=revision)
        except ValueError:
            raise QueryError(400, 'Minute or revision does not match available Market Frame') from None
        result = calculate_skew(frame, context.bundle, at, historical=historical)
        result['reference'].update(manifest_sha256=context.manifest_sha256,
                                   listing_sha256=context.listing_sha256)
        return public_result(result, frame)

    def _series(self, month, day, at, revision, context, calendar, reference_error):
        deadline = time.monotonic() + 10
        minutes = []
        for period in calendar.periods('CFFEX', 'MO'):
            if period['trading_day'] != day or period['phase'] != 'CONTINUOUS':
                continue
            minute = period['start']
            while minute + MINUTE <= min(period['end'], at):
                minutes.append(minute)
                minute += MINUTE
        if not any(p['trading_day'] == day for p in calendar.periods('CFFEX', 'MO')):
            return unavailable(month, day, at, 'UNSUPPORTED_SESSION') | {'points': [], 'baseline': None,
                                                                           'change_vp': None}
        points = []
        selected, selected_day, historical, _, state = latest_minute(calendar, at)
        for minute in minutes:
            if time.monotonic() >= deadline:
                raise QueryError(503, 'Skew series execution budget exceeded')
            if reference_error:
                result = unavailable(month, day, at, reference_error, minute)
            else:
                result = self._calculate(context, minute, at,
                                         historical or selected_day != day or minute != selected, revision)
                if revision is None:
                    revision = result['raw_revision']
            points.append(result)
        if time.monotonic() >= deadline:
            raise QueryError(503, 'Skew series execution budget exceeded')
        baseline = next((p for p in points if p['status'] == 'OK'), None)
        last = points[-1] if points else None
        # Do not pick the last *valid* value when the selected minute failed.
        waiting_current_period = selected is None and selected_day == day
        change = (last['skew_25d_vp'] - baseline['skew_25d_vp']
                  if baseline and last['status'] == 'OK' and not waiting_current_period else None)
        reasons = ([reference_error] if reference_error else ['WAITING_FOR_MINUTE'] if not points
                   else sorted({r for p in points for r in p['reasons']}))
        return dict(schema_version=1, contract_id=CONTRACT_ID, algorithm_version=ALGORITHM_VERSION,
                    scope={'exchange': 'CFFEX', 'product': 'MO', 'month': month, 'trading_day': day},
                    requested_at=at.isoformat(), raw_revision=revision if context and points else None,
                    status='OK' if baseline else 'UNAVAILABLE', reasons=reasons,
                    market_session=state, points=points, unit='vol_point',
                    baseline=({'minute': baseline['minute'], 'skew_25d_vp': baseline['skew_25d_vp']}
                              if baseline else None), change_vp=change,
                    change_minute=last['minute'] if change is not None else None)
