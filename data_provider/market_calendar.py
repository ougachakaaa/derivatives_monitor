"""Exchange/product session interpretation. Standard library only; never writes raw data."""
import argparse
from bisect import bisect_right
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Asia/Shanghai')
DEFAULT_DIRECTORY = Path(__file__).with_name('calendars')
CFFEX_PRODUCTS = ('IF', 'IH', 'IC', 'IM', 'TS', 'TF', 'T', 'TL', 'IO', 'HO', 'MO')
SHFE_PRODUCTS = ('AU', 'AG')
PRODUCTS = {'CFFEX': CFFEX_PRODUCTS, 'SHFE': SHFE_PRODUCTS}
# (start, end, phase); all times are Asia/Shanghai and intervals are [start,end).
EQUITY = (('09:25', '09:30', 'AUCTION'), ('09:30', '11:30', 'CONTINUOUS'),
          ('13:00', '15:00', 'CONTINUOUS'))
BOND = EQUITY[:2] + (('13:00', '15:15', 'CONTINUOUS'),)
OPTION = EQUITY[:2] + (('13:00', '14:57', 'CONTINUOUS'), ('14:57', '15:00', 'AUCTION'))
METAL = (('08:55', '09:00', 'AUCTION'), ('09:00', '10:15', 'CONTINUOUS'),
         ('10:30', '11:30', 'CONTINUOUS'), ('13:30', '15:00', 'CONTINUOUS'))
NIGHT = (('20:55', '21:00', 'AUCTION'), ('21:00', '02:30', 'CONTINUOUS'))
PROFILES = {('CFFEX', p): (BOND if p in ('TS', 'TF', 'T', 'TL') else OPTION if p in ('IO', 'HO', 'MO') else EQUITY, ())
            for p in CFFEX_PRODUCTS}
PROFILES.update({('SHFE', p): (METAL, NIGHT) for p in SHFE_PRODUCTS})


class CalendarError(ValueError):
    pass


def parse_day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{8}', value):
        raise CalendarError('calendar dates must be YYYYMMDD')
    try:
        return datetime.strptime(value, '%Y%m%d').date()
    except ValueError as error:
        raise CalendarError('invalid calendar date') from error


def parse_at(value=None):
    if value is None:
        return datetime.now(ZONE)
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('at must include a UTC offset')
    return result.astimezone(ZONE)


def selected_products(exchange=None, product=None):
    if exchange is None:
        if product is not None:
            raise ValueError('product requires exchange')
        return list(PROFILES)
    exchange = exchange.upper()
    if exchange not in PRODUCTS:
        raise ValueError('unsupported exchange')
    if product is None:
        return [(exchange, p) for p in PRODUCTS[exchange]]
    product = product.upper()
    if product not in PRODUCTS[exchange]:
        raise ValueError('unsupported exchange/product')
    return [(exchange, product)]


def unknown(exchange, product, at, reason):
    return dict(exchange=exchange, product=product, as_of=at.isoformat(), timezone='Asia/Shanghai',
                trading_day=None, session_state='UNKNOWN', session=None, phase=None,
                is_continuous=False, quote_expected=None, current_session=None,
                latest_session=None, next_session=None, calendar_version=None, reason=reason)


class Calendar:
    def __init__(self, path, *, content=None):
        try:
            if content is None:
                with Path(path).open('rb') as stream:
                    raw = stream.read(1024 * 1024 + 1)
            else:
                raw = content
            if len(raw) > 1024 * 1024:
                raise CalendarError('calendar exceeds 1 MiB')
            self.data = json.loads(raw)
            data = self.data
            if data['schema_version'] != 1 or not isinstance(data['version'], str) or not data['version']:
                raise CalendarError('unsupported calendar schema/version')
            self.start, self.end = parse_day(data['valid_from']), parse_day(data['valid_through'])
            if self.start > self.end or self.start.year != self.end.year:
                raise CalendarError('calendar must cover one ordered year')
            parse_day(data['reviewed_on'])
            if set(data['exchanges']) != set(PRODUCTS):
                raise CalendarError('missing exchange calendar')
            for exchange, content in data['exchanges'].items():
                if not content['sources'] or not all(isinstance(s, str) and s.startswith('https://') for s in content['sources']):
                    raise CalendarError('calendar requires source URLs')
                records = content['days']
                if not isinstance(records, list) or not 1 <= len(records) <= 366:
                    raise CalendarError('invalid trading day list')
                previous = None
                for record in records:
                    trading_day = parse_day(record['trading_day'])
                    if not self.start <= trading_day <= self.end or (previous and trading_day <= previous):
                        raise CalendarError('unordered/duplicate/out-of-range trading day')
                    if record['night_start'] is not None:
                        night = parse_day(record['night_start'])
                        if exchange != 'SHFE' or night != previous or night >= trading_day:
                            raise CalendarError('night must start on the previous listed trading day')
                    previous = trading_day
        except (OSError, KeyError, TypeError, ValueError, AttributeError) as error:
            raise CalendarError('calendar missing or invalid: ' + str(error)) from error
        self._periods = {}

    def periods(self, exchange, product):
        key = (exchange, product)
        if key in self._periods:
            return self._periods[key]
        day_profile, night_profile = PROFILES[key]
        result = []
        for record in self.data['exchanges'][exchange]['days']:
            for kind, anchor, profile in [('DAY', record['trading_day'], day_profile),
                                           ('NIGHT', record['night_start'], night_profile)]:
                if anchor is None:
                    continue
                anchor = parse_day(anchor)
                for start, end, phase in profile:
                    begin = datetime.combine(anchor, time.fromisoformat(start), ZONE)
                    finish = datetime.combine(anchor, time.fromisoformat(end), ZONE)
                    if finish <= begin:
                        finish += timedelta(days=1)
                    result.append(dict(start=begin, end=finish, session=kind, phase=phase,
                                       trading_day=record['trading_day']))
        result.sort(key=lambda p: p['start'])
        self._periods[key] = result
        return result

    def query(self, exchange, product, at):
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError('at must be timezone aware')
        exchange, product = selected_products(exchange, product)[0]
        at = at.astimezone(ZONE)
        if not self.start <= at.date() <= self.end:
            return unknown(exchange, product, at, 'outside calendar coverage')
        periods = self.periods(exchange, product)
        index = bisect_right([p['start'] for p in periods], at)
        before = periods[index - 1] if index else None
        after = periods[index] if index < len(periods) else None
        active = before if before and at < before['end'] else None
        continuous = [p for p in periods if p['phase'] == 'CONTINUOUS']
        ci = bisect_right([p['start'] for p in continuous], at)
        latest = continuous[ci - 1] if ci else None
        upcoming = continuous[ci] if ci < len(continuous) else None
        state, kind, phase = 'CLOSED', None, None
        if active:
            state, kind, phase = 'OPEN', active['session'], active['phase']
            trading_day = active['trading_day']
        elif (before and after and before['session'] == after['session'] == 'DAY'
              and before['trading_day'] == after['trading_day']):
            state, kind, trading_day = 'BREAK', 'DAY', before['trading_day']
        elif after:
            trading_day = after['trading_day']
        else:
            return unknown(exchange, product, at, 'next trading day outside calendar coverage')
        def serialize(period):
            return {k: v.isoformat() if isinstance(v, datetime) else v for k, v in period.items()} if period else None
        result = unknown(exchange, product, at, '')
        result.update(trading_day=trading_day, session_state=state, session=kind, phase=phase,
                      is_continuous=phase == 'CONTINUOUS', quote_expected=phase == 'CONTINUOUS',
                      current_session=serialize(active), latest_session=serialize(latest),
                      next_session=serialize(upcoming), calendar_version=self.data['version'],
                      valid_from=self.data['valid_from'], valid_through=self.data['valid_through'],
                      reviewed_on=self.data['reviewed_on'], sources=self.data['exchanges'][exchange]['sources'])
        return result


def sessions(at=None, exchange=None, product=None, directory=DEFAULT_DIRECTORY):
    at = parse_at(at) if not isinstance(at, datetime) else at
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError('at must be timezone aware')
    at = at.astimezone(ZONE)
    pairs = selected_products(exchange, product)
    try:
        calendar = Calendar(Path(directory) / f'{at.year}.json')
    except CalendarError:
        rows = [unknown(e, p, at, 'calendar missing or invalid for requested year') for e, p in pairs]
    else:
        rows = [calendar.query(e, p, at) for e, p in pairs]
    return dict(schema_version=1, as_of=at.isoformat(), timezone='Asia/Shanghai', markets=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calendar-dir', type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument('--exchange')
    parser.add_argument('--product')
    parser.add_argument('--at')
    parser.add_argument('--validate', type=Path, help='validate one reference file without querying')
    args = parser.parse_args()
    try:
        if args.validate:
            calendar = Calendar(args.validate)
            print(json.dumps(dict(valid=True, version=calendar.data['version'])))
            return 0
        result = sessions(args.at, args.exchange, args.product, args.calendar_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if any(r['session_state'] == 'UNKNOWN' for r in result['markets']) else 0
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
