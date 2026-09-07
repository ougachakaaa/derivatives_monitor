"""Deterministic market state over persisted Raw observations; never writes Raw.

Public contract v1: Universe, Scope, MarketStateReader, JSON-compatible results.
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
        exchange, product = selected_products(exchange, product)[0]
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
        if selected_products(self.exchange, self.product) != [(self.exchange, self.product)]:
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
        exchange, product = selected_products(exchange, product)[0]
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
