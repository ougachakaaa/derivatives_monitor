"""Deterministic Market Frames over persisted Raw observations; never writes Raw.

Public contract v1: Universe, Scope, MarketFrameReader, JSON-compatible results.
All times supplied by callers; source exchange clocks are retained as facts.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import re

from contract_coverage import match_id
from market_calendar import Calendar, CalendarError, DEFAULT_DIRECTORY, ZONE, selected_products
from storage import Store, QueryError, validate_day

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
MAX_MEMBERS = 10000
# Explicit projection fixes the v1 output schema and fails clearly on incompatible files.
OBSERVATION_COLUMNS = (
    'id run_id sequence received_us snapshot_us TradingDay ExchangeID InstrumentID '
    'ExchangeInstID ActionDay UpdateTime UpdateMillisec LastPrice PreSettlementPrice '
    'PreClosePrice PreOpenInterest OpenPrice HighestPrice LowestPrice Volume Turnover '
    'OpenInterest ClosePrice SettlementPrice UpperLimitPrice LowerLimitPrice PreDelta '
    'CurrDelta BidPrice1 BidVolume1 AskPrice1 AskVolume1 BidPrice2 BidVolume2 AskPrice2 '
    'AskVolume2 BidPrice3 BidVolume3 AskPrice3 AskVolume3 BidPrice4 BidVolume4 AskPrice4 '
    'AskVolume4 BidPrice5 BidVolume5 AskPrice5 AskVolume5 AveragePrice BandingUpperPrice '
    'BandingLowerPrice'
).split()


def product_pair(exchange, product):
    if not isinstance(exchange, str) or not isinstance(product, str):
        raise ValueError('scope requires an explicit exchange and product')
    return selected_products(exchange, product)[0]


def aware(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('time must be a timezone-aware datetime')
    return value.astimezone(ZONE)


def micros(value):
    delta = aware(value) - EPOCH
    return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds


def identity(code):
    match = match_id(code) if isinstance(code, str) else None
    if not match:
        raise ValueError('unsupported instrument identity')
    product = match[1].upper()
    return ('SHFE' if product in ('AU', 'AG') else 'CFFEX', product, match[2])


@dataclass(frozen=True)
class Universe:
    """Caller-supplied, day-specific listing evidence, independent of observations."""
    trading_day: str
    version: str
    instruments: tuple[str, ...]
    complete: bool

    def __post_init__(self):
        validate_day(self.trading_day)
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError('universe requires a version/source identifier')
        if type(self.complete) is not bool:
            raise ValueError('universe completeness must be explicit')
        if isinstance(self.instruments, str):
            raise ValueError('instruments must be a collection of codes')
        codes = tuple(self.instruments)
        if len(codes) > MAX_MEMBERS:
            raise ValueError('universe exceeds 10000 members')
        for code in codes:
            identity(code)
        object.__setattr__(self, 'instruments', tuple(sorted(set(codes))))

    @classmethod
    def from_manifest(cls, manifest, exchange, product, trading_day, version):
        """Consume an explicitly selected manifest, never universe/current implicitly.

        Completeness is limited to this product and its day-matched verified entry.
        A partial/stale entry remains usable as an explicitly incomplete listing.
        """
        exchange, product = product_pair(exchange, product)
        if manifest.get('schema_version') != 1:
            raise ValueError('unsupported manifest version')
        entry = manifest.get('products', {}).get(product)
        if not isinstance(entry, dict):
            raise ValueError('manifest has no requested product')
        if (entry.get('exchange', exchange) != exchange
                or entry.get('requested_day', manifest.get('requested_day')) != trading_day):
            raise ValueError('manifest exchange/day mismatch')
        codes = []
        for row in entry.get('instruments', []):
            code = row['id']
            if identity(code) != (exchange, product, row['month']):
                raise ValueError('manifest instrument identity mismatch')
            codes.append(code)
        complete = (entry.get('verified') is True and entry.get('stale') is False
                    and entry.get('data_date') == trading_day and bool(codes))
        return cls(trading_day, version, tuple(codes), complete)


@dataclass(frozen=True)
class Scope:
    kind: str
    exchange: str
    product: str
    trading_day: str
    instruments: tuple[str, ...]
    universe_version: str
    universe_complete: bool
    month: str | None = None

    def __post_init__(self):
        if self.kind not in ('instrument', 'product', 'month', 'option_chain'):
            raise ValueError('unsupported scope kind')
        if product_pair(self.exchange, self.product) != (self.exchange, self.product):
            raise ValueError('scope exchange/product must be canonical')
        universe = Universe(self.trading_day, self.universe_version, self.instruments, self.universe_complete)
        object.__setattr__(self, 'instruments', universe.instruments)
        if self.kind in ('month', 'option_chain'):
            if not isinstance(self.month, str) or not re.fullmatch(r'[0-9]{2}(?:0[1-9]|1[0-2])', self.month):
                raise ValueError('month must be YYMM')
        elif self.month is not None:
            raise ValueError('month only applies to month/option_chain scope')
        if self.kind == 'option_chain' and self.product not in ('IO', 'HO', 'MO'):
            raise ValueError('option_chain requires an option product')
        if self.kind == 'instrument' and len(self.instruments) != 1:
            raise ValueError('instrument scope requires exactly one code')
        for code in self.instruments:
            exchange, product, month = identity(code)
            if (exchange, product) != (self.exchange, self.product) or (self.month and month != self.month):
                raise ValueError('scope contains an instrument outside its product/month')

    @classmethod
    def instrument(cls, code, trading_day):
        exchange, product, _ = identity(code)
        return cls('instrument', exchange, product, trading_day, (code,), 'explicit-instrument', True)

    @classmethod
    def select(cls, universe, exchange, product, *, month=None, option_chain=False):
        exchange, product = product_pair(exchange, product)
        kind = 'option_chain' if option_chain else 'month' if month is not None else 'product'
        codes = tuple(code for code in universe.instruments
                      if identity(code)[:2] == (exchange, product)
                      and (month is None or identity(code)[2] == month))
        return cls(kind, exchange, product, universe.trading_day, codes,
                   universe.version, universe.complete, month)

    def as_dict(self):
        return dict(kind=self.kind, exchange=self.exchange, product=self.product,
                    trading_day=self.trading_day, month=self.month,
                    instruments=list(self.instruments), universe_version=self.universe_version,
                    universe_complete=self.universe_complete)


def period_dict(period):
    return {key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in period.items()}


def quality(observation, age_reference_us, stale_after_us, scope):
    if observation is None:
        return dict(missing=True, stale=False, invalid=False, usable=False,
                    flags=['MISSING'], reasons=[], quote_age_us=None)
    age = age_reference_us - observation['received_us']
    reasons = []
    for field in ('BidPrice1', 'AskPrice1', 'BidVolume1', 'AskVolume1'):
        value = observation[field]
        if (not isinstance(value, (int, float)) or not math.isfinite(value)
                or value <= 0 or abs(value) == float.fromhex('0x1.fffffffffffffp+1023')):
            reasons.append('invalid_' + field)
    if not reasons and observation['BidPrice1'] > observation['AskPrice1']:
        reasons.append('crossed_book')
    if observation['TradingDay'] != scope.trading_day:
        reasons.append('trading_day_mismatch')
    # CTP ExchangeID can legitimately be empty. A populated contradiction cannot.
    if observation['ExchangeID'] not in ('', scope.exchange):
        reasons.append('exchange_mismatch')
    if observation['snapshot_us'] < observation['received_us']:
        reasons.append('snapshot_before_observation')
    stale = age > stale_after_us
    flags = (['STALE'] if stale else []) + (['INVALID'] if reasons else [])
    return dict(missing=False, stale=stale, invalid=bool(reasons), usable=not flags,
                flags=flags, reasons=reasons, quote_age_us=age)


class MarketFrameReader:
    """One short, read-only SQLite transaction per frame; no implicit current clock."""

    def __init__(self, store, calendar_directory=DEFAULT_DIRECTORY, *, calendar=None):
        self.store = store
        self.calendar_directory = calendar_directory
        self.calendar = calendar

    def _calendar(self, at):
        from pathlib import Path
        if self.calendar is not None:
            return self.calendar
        return Calendar(Path(self.calendar_directory) / f'{at.year}.json')

    @staticmethod
    def _policy(stale_after_us, raw_revision):
        if type(stale_after_us) is not int or stale_after_us < 0:
            raise ValueError('stale_after_us must be a nonnegative integer')
        if raw_revision is not None and (type(raw_revision) is not int or raw_revision < 0):
            raise ValueError('raw_revision must be a nonnegative integer')

    def as_of(self, scope, at, *, stale_after_us=60000000, raw_revision=None):
        """Point-in-time state, inclusive of observations received exactly at at."""
        at = aware(at)
        calendar = self._calendar(at)
        state = calendar.query(scope.exchange, scope.product, at)
        if state['market_state'] != 'OPEN':
            raise ValueError('as_of must be inside a known market period')
        period = next(p for p in calendar.periods(scope.exchange, scope.product)
                      if p['start'] <= at < p['end'])
        return self._frame(scope, calendar, period, at, True, at, stale_after_us, raw_revision)

    def minute(self, scope, minute, *, evaluated_at, stale_after_us=60000000, raw_revision=None):
        """State just before the end of [minute, minute+1m); no minute resampling."""
        minute, evaluated_at = aware(minute), aware(evaluated_at)
        if minute.second or minute.microsecond:
            raise ValueError('minute must be aligned to a whole minute')
        end = minute + timedelta(minutes=1)
        if evaluated_at < minute:
            raise ValueError('evaluated_at precedes minute')
        calendar = self._calendar(minute)
        state = calendar.query(scope.exchange, scope.product, minute)
        if state['market_state'] != 'OPEN':
            raise ValueError('minute must be inside a known market period')
        period = next((p for p in calendar.periods(scope.exchange, scope.product)
                       if p['start'] <= minute and end <= p['end']), None)
        if period is None:
            raise ValueError('minute crosses a market period boundary')
        # An unfinished minute only knows receipts through evaluated_at.
        sealed = evaluated_at >= end
        cutoff = end if sealed else evaluated_at
        result = self._frame(scope, calendar, period, cutoff, not sealed, cutoff,
                             stale_after_us, raw_revision)
        result.update(kind='minute', minute=minute.isoformat(), minute_end=end.isoformat(),
                      evaluated_at=evaluated_at.isoformat(), sealed=sealed)
        return result

    def _frame(self, scope, calendar, period, cutoff, inclusive, age_reference,
               stale_after_us, raw_revision):
        self._policy(stale_after_us, raw_revision)
        if period['trading_day'] != scope.trading_day:
            raise ValueError('scope trading_day does not match selected market period')
        lower, upper, age_us = micros(period['start']), micros(cutoff), micros(age_reference)
        with self.store.connect(scope.trading_day) as db:
            maximum = db.execute('SELECT COALESCE(MAX(id),0) FROM snapshots').fetchone()[0]
            revision = maximum if raw_revision is None else raw_revision
            if revision > maximum:
                raise ValueError('raw_revision exceeds the visible daily database revision')
            rows = []
            comparison = '<=' if inclusive else '<'
            for code in scope.instruments:
                record = db.execute(
                    'SELECT ' + ','.join(OBSERVATION_COLUMNS) + ' FROM snapshots WHERE InstrumentID=? AND received_us>=? '
                    f'AND received_us{comparison}? AND id<=? '
                    'ORDER BY received_us DESC,id DESC LIMIT 1',
                    (code, lower, upper, revision)).fetchone()
                observation = dict(record) if record is not None else None
                q = quality(observation, age_us, stale_after_us, scope)
                rows.append(dict(instrument=code, observation=observation, quality=q))
        observed = sum(not row['quality']['missing'] for row in rows)
        usable = sum(row['quality']['usable'] for row in rows)
        counts = {name + '_count': sum(row['quality'][name] for row in rows)
                  for name in ('missing', 'stale', 'invalid')}
        status = ('EMPTY' if not observed else 'COMPLETE' if scope.universe_complete
                  and usable == len(rows) else 'PARTIAL')
        return dict(schema_version=1, kind='as_of', scope=scope.as_dict(),
                    trading_day=scope.trading_day, calendar_version=calendar.data['version'],
                    session=period_dict(period), effective_as_of=cutoff.isoformat(),
                    cutoff_inclusive=inclusive, age_reference=age_reference.isoformat(),
                    observation_clock='received_us', raw_revision=revision,
                    stale_after_us=stale_after_us, completeness=status,
                    expected_count=len(rows), observed_count=observed, usable_count=usable,
                    **counts, rows=rows)

    def latest(self, scope, at, *, stale_after_us=60000000, raw_revision=None):
        """Current period when OPEN; explicitly historical last period otherwise."""
        at = aware(at)
        self._policy(stale_after_us, raw_revision)
        try:
            calendar = self._calendar(at)
        except CalendarError as error:
            return dict(schema_version=1, requested_at=at.isoformat(), market_state='UNKNOWN',
                        calendar_trading_day=None, calendar_version=None, historical=None,
                        reason=str(error), frame=None)
        state = calendar.query(scope.exchange, scope.product, at)
        result = dict(schema_version=1, requested_at=at.isoformat(), market_state=state['market_state'],
                      calendar_trading_day=state['trading_day'], calendar_version=state['calendar_version'],
                      historical=None, reason=state['reason'], frame=None)
        if state['market_state'] == 'UNKNOWN':
            return result
        periods = calendar.periods(scope.exchange, scope.product)
        historical = state['market_state'] != 'OPEN'
        if historical:
            period = next((p for p in reversed(periods) if p['end'] <= at), None)
            if period is None:
                result.update(historical=True, reason='no previous market period in calendar coverage')
                return result
            cutoff, inclusive = period['end'], False
        else:
            period = next(p for p in periods if p['start'] <= at < p['end'])
            cutoff, inclusive = at, True
        result.update(historical=historical,
                      frame=self._frame(scope, calendar, period, cutoff, inclusive, at,
                                        stale_after_us, raw_revision))
        return result


def main(argv=None):
    """Small reproducible JSON entry point; no server or scheduler required."""
    import argparse
    import json
    from pathlib import Path
    from market_calendar import parse_at

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('minute', 'as-of', 'latest'))
    parser.add_argument('--data-dir', required=True, type=Path)
    parser.add_argument('--calendar-dir', type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument('--day', required=True, help='actual frame trading day, not next calendar day')
    parser.add_argument('--at', required=True, help='aware ISO time; minute label in minute mode')
    parser.add_argument('--evaluated-at', help='required for minute mode')
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--instrument')
    selection.add_argument('--universe', type=Path, help='explicit day/version/instruments/complete JSON')
    parser.add_argument('--exchange')
    parser.add_argument('--product')
    parser.add_argument('--month')
    parser.add_argument('--option-chain', action='store_true')
    parser.add_argument('--stale-after-us', type=int, default=60000000)
    parser.add_argument('--raw-revision', type=int)
    args = parser.parse_args(argv)
    try:
        if (args.mode == 'minute') != (args.evaluated_at is not None):
            raise ValueError('--evaluated-at is required only for minute mode')
        if args.instrument:
            if args.exchange or args.product or args.month or args.option_chain:
                raise ValueError('instrument cannot be combined with product/month selectors')
            scope = Scope.instrument(args.instrument, args.day)
        else:
            with args.universe.open('rb') as stream:
                raw = stream.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError('universe exceeds 8 MiB')
            universe = Universe(**json.loads(raw))
            if universe.trading_day != args.day:
                raise ValueError('universe day differs from --day')
            scope = Scope.select(universe, args.exchange, args.product, month=args.month,
                                 option_chain=args.option_chain)
        reader = MarketFrameReader(Store(args.data_dir), args.calendar_dir)
        policy = dict(stale_after_us=args.stale_after_us, raw_revision=args.raw_revision)
        at = parse_at(args.at)
        if args.mode == 'minute':
            result = reader.minute(scope, at, evaluated_at=parse_at(args.evaluated_at), **policy)
        elif args.mode == 'as-of':
            result = reader.as_of(scope, at, **policy)
        else:
            result = reader.latest(scope, at, **policy)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (ValueError, TypeError, KeyError, OSError, QueryError) as error:
        message = error.message if isinstance(error, QueryError) else str(error)
        print(json.dumps(dict(error=message, status=error.status if isinstance(error, QueryError) else 400)))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
