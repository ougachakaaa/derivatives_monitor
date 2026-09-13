"""Versioned Indicator envelopes over existing Query business services."""
from hashlib import sha256
import json
import math
import re

from data_provider.market_calendar import parse_at


SCHEMA_VERSION = 1
SKEW_INDICATOR_ID = 'mo-skew-25d-v1'
SKEW_SCOPE_KEYS = frozenset(('exchange', 'product', 'month'))
MONTH = re.compile(r'[0-9]{2}(?:0[1-9]|1[0-2])')


class IndicatorRequestError(ValueError):
    """The caller supplied a request outside the frozen Indicator v1 contract."""


class IndicatorRegistry:
    """Small explicit registry; production providers are registered explicitly."""

    def __init__(self):
        self._providers = {}

    def register(self, indicator_id, provider):
        if not isinstance(indicator_id, str) or not indicator_id or indicator_id in self._providers:
            raise ValueError('indicator_id must be a unique non-empty string')
        self._providers[indicator_id] = provider

    def resolve(self, indicator_id):
        try:
            return self._providers[indicator_id]
        except (KeyError, TypeError):
            raise IndicatorRequestError('Indicator is not registered') from None


def sample_key(indicator_id, result):
    """Return an opaque identity for a known logical sample position."""
    scope = result.get('scope')
    minute = result.get('minute')
    if not isinstance(scope, dict) or not scope.get('trading_day') or not minute:
        return None
    identity = {
        'indicator_id': indicator_id,
        'scope': {key: scope.get(key) for key in ('exchange', 'product', 'month', 'trading_day')},
        'minute': minute,
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()
    return 'indicator-sample-v1:' + sha256(canonical).hexdigest()


def indicator_envelope(indicator_id, parameters, evidence, *, value, unit, effective_at):
    """Build the shared v1 wire shape without interpreting provider evidence."""
    if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
        raise ValueError('Indicator value must be a finite scalar or null')
    if evidence['status'] not in ('OK', 'UNAVAILABLE'):
        raise ValueError('Indicator status must be OK or UNAVAILABLE')
    return {
        'schema_version': SCHEMA_VERSION,
        'indicator_id': indicator_id,
        'parameters': parameters,
        'scope': evidence['scope'],
        'value': value,
        'unit': unit,
        'status': evidence['status'],
        'reasons': evidence['reasons'],
        'effective_at': effective_at,
        'evaluated_at': evidence['evaluated_at'],
        'historical': evidence['historical'],
        'current_usable': evidence['current_usable'],
        'sample_key': sample_key(indicator_id, evidence),
        'evidence': evidence,
    }


class SkewIndicatorProvider:
    """Thin projection of the frozen MO Skew latest business query."""

    indicator_id = SKEW_INDICATOR_ID

    def __init__(self, skew_service):
        self.skew_service = skew_service

    def evaluate(self, scope, parameters, requested_at):
        if (type(scope) is not dict or set(scope) != SKEW_SCOPE_KEYS
                or scope.get('exchange') != 'CFFEX' or scope.get('product') != 'MO'
                or type(scope.get('month')) is not str or not MONTH.fullmatch(scope['month'])):
            raise IndicatorRequestError('Invalid scope for mo-skew-25d-v1')
        if type(parameters) is not dict or parameters:
            raise IndicatorRequestError('mo-skew-25d-v1 parameters must be an empty object')
        if type(requested_at) is not str:
            raise IndicatorRequestError('requested_at must be a timezone-aware ISO datetime')
        try:
            requested_at = parse_at(requested_at)
        except (ValueError, TypeError, OverflowError):
            raise IndicatorRequestError('requested_at must be a timezone-aware ISO datetime') from None

        evidence = self.skew_service.query('latest', month=scope['month'], at=requested_at.isoformat())
        return indicator_envelope(self.indicator_id, {}, evidence,
                                value=evidence['skew_25d_vp'], unit=evidence['unit'],
                                effective_at=evidence['valuation_at'])


class IndicatorService:
    """Validate a single Indicator v1 request and dispatch to its provider."""

    REQUEST_KEYS = frozenset(('schema_version', 'indicator_id', 'scope', 'parameters', 'requested_at'))

    def __init__(self, registry):
        self.registry = registry

    def evaluate(self, request):
        if type(request) is not dict or set(request) != self.REQUEST_KEYS:
            raise IndicatorRequestError('Invalid Indicator request structure')
        if type(request['schema_version']) is not int or request['schema_version'] != SCHEMA_VERSION:
            raise IndicatorRequestError('Unsupported Indicator schema_version')
        if type(request['indicator_id']) is not str:
            raise IndicatorRequestError('indicator_id must be a string')
        provider = self.registry.resolve(request['indicator_id'])
        return provider.evaluate(request['scope'], request['parameters'], request['requested_at'])


def skew_indicator_service(skew_service):
    registry = IndicatorRegistry()
    registry.register(SKEW_INDICATOR_ID, SkewIndicatorProvider(skew_service))
    return IndicatorService(registry)
