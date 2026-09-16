#!/usr/bin/env python3
"""Public contract discovery only. Prices from these responses are never ingested.

SHFE ContractBaseInfo supplies AU/AG futures. CFFEX jycs.js supplies dated XML.
Sina fallback uses
its expiry selector and OptionService.getOptionData; no generated contracts.
"""
import contextlib
import argparse
from datetime import datetime, timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

# Reference calendar is a pure stdlib Data Provider module; this helper does not start Query.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from data_provider.market_calendar import sessions

ZONE = ZoneInfo('Asia/Shanghai')
CFFEX_PRODUCTS = ('IF', 'IH', 'IC', 'IM', 'TS', 'TF', 'T', 'TL', 'IO', 'HO', 'MO')
SHFE_PRODUCTS = ('AU', 'AG')
PRODUCTS = CFFEX_PRODUCTS + SHFE_PRODUCTS
OPTIONS = ('IO', 'HO', 'MO')
CONTRACT = re.compile(r'^(IF|IH|IC|IM|TS|TF|TL|T|IO|HO|MO|au|ag)(\d{2}(?:0[1-9]|1[0-2]))(?:-([CP])-(\d+(?:\.\d+)?))?$')
# SHA-256 of the whitespace-free ordered (type, name, DDL) concatenation from Raw Boundary.
RUNTIME_SCHEMA_FINGERPRINT = '8fb54c462453fc5b4319604b289472fa6e6265fcadc94778cb9d69292e1d53e5'


def runtime_schema_fingerprint(db):
    rows = db.execute(
        "SELECT type,name,sql FROM sqlite_master "
        "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type,name"
    ).fetchall()
    canonical = ''.join('\x1f'.join(row) for row in rows)
    return hashlib.sha256(re.sub(r'\s+', '', canonical).encode()).hexdigest()


def contract(code, expiry=None):
    match = CONTRACT.fullmatch(code)
    if not match:
        raise ValueError('invalid supported contract: ' + code)
    product, month, side, strike = match.groups()
    product = product.upper()
    if (product in OPTIONS) != bool(side):
        raise ValueError('contract type mismatch: ' + code)
    return dict(id=code, exchange='SHFE' if product in SHFE_PRODUCTS else 'CFFEX',
                product=product, month=month, side=side, strike=strike, expiry=expiry)


def day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{8}', value):
        raise ValueError('date must be YYYYMMDD')
    return datetime.strptime(value, '%Y%m%d').date()


def check_chain(rows):
    if not rows:
        raise ValueError('empty product')
    if rows[0]['product'] in OPTIONS:
        pairs = {}
        for row in rows:
            pairs.setdefault((row['month'], row['strike']), set()).add(row['side'])
        if any(sides != {'C', 'P'} for sides in pairs.values()):
            raise ValueError('incomplete call/put pairs')
    return sorted({r['id']: r for r in rows}.values(), key=lambda r: r['id'])


def parse_cffex(raw, requested_day):
    root = ET.fromstring(raw)
    groups = {p: [] for p in CFFEX_PRODUCTS}
    errors = {}
    for node in root.findall('INDEX'):
        product = (node.findtext('PRODUCT_ID') or '').strip()
        if product not in groups:
            continue
        try:
            value = lambda key: (node.findtext(key) or '').strip()
            if value('TRADING_DAY') != requested_day:
                raise ValueError('wrong source date')
            expiry = value('END_TRADING_DAY')
            if day(value('OPEN_DATE')) > day(requested_day) or day(expiry) < day(requested_day):
                continue
            row = contract(value('INSTRUMENT_ID'), expiry)
            if row['product'] != product or row['month'] != value('INSTRUMENT_MONTH'):
                raise ValueError('product/month mismatch')
            groups[product].append(row)
        except ValueError as error:
            errors[product] = str(error)
    result = {}
    for product, rows in groups.items():
        try:
            if product in errors:
                raise ValueError(errors[product])
            result[product] = check_chain(rows)
        except ValueError as error:
            errors[product] = str(error)
    return result, errors


def parse_shfe(raw, requested_day):
    payload = json.loads(raw)
    records = payload['ContractBaseInfo']
    if not isinstance(records, list):
        raise ValueError('invalid SHFE contract list')
    groups, errors = {p: [] for p in SHFE_PRODUCTS}, {}
    for node in records:
        product = str(node.get('COMMODITYID', '')).strip().upper()
        if product not in groups:
            continue
        try:
            value = lambda key: str(node[key]).strip()
            if value('EXCHANGEID') != 'SHFE' or value('TRADINGDAY') != requested_day:
                raise ValueError('wrong SHFE exchange/source date')
            row = contract(value('INSTRUMENTID'), value('EXPIREDATE'))
            if row['exchange'] != 'SHFE' or row['product'] != product:
                raise ValueError('SHFE product/code mismatch')
            opened, expiry = day(value('OPENDATE')), day(row['expiry'])
            if opened > expiry:
                raise ValueError('invalid listing lifetime')
            if not opened <= day(requested_day) <= expiry:
                continue
            row['listed_on'] = value('OPENDATE')
            if any(old['id'] == row['id'] and old != row for old in groups[product]):
                raise ValueError('conflicting duplicate contract')
            groups[product].append(row)
        except (ValueError, KeyError, TypeError) as error:
            errors[product] = str(error)
    result = {}
    for product, rows in groups.items():
        try:
            if product in errors:
                raise ValueError(errors[product])
            result[product] = check_chain(rows)
        except ValueError as error:
            errors[product] = str(error)
    return result, errors


def requested_dates(explicit=None, now=None):
    if explicit is not None:
        day(explicit)
        return dict(CFFEX=explicit, SHFE=explicit)
    now = now or datetime.now(ZONE)
    interpreted = sessions(now, 'SHFE', 'AU')['markets'][0]
    return dict(CFFEX=now.astimezone(ZONE).strftime('%Y%m%d'), SHFE=interpreted['trading_day'])


def parse_expiries(raw, product):
    text = raw.decode('gb18030', errors='replace')
    # Only explicit option values, not generic dates elsewhere on the page.
    months = sorted(set(re.findall(r'data-value=["\']' + product.lower() + r'(\d{4})["\']', text)))
    if not months or any(not re.fullmatch(r'\d{2}(0[1-9]|1[0-2])', m) for m in months):
        raise ValueError('no valid published expiry selector')
    return months


def parse_sina(raw, product, month):
    response = json.loads(raw)['result']
    if response['status']['code'] != 0:
        raise ValueError('Sina response error')
    rows = []
    for key, side in [('up', 'C'), ('down', 'P')]:
        values = response['data'][key]
        if not values:
            raise ValueError('empty option side')
        for value in values:
            codes = [s for s in value if isinstance(s, str) and re.fullmatch(
                product.lower() + month + side + r'\d+(?:\.\d+)?', s, re.I)]
            if len(codes) != 1:
                raise ValueError('missing exact option code')
            code = codes[0].upper()
            row = contract(product + month + '-' + side + '-' + code[len(product) + 5:])
            rows.append(row)
    return check_chain(rows)


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class Fetcher:
    def __init__(self, directory):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.requests = []

    def __call__(self, url):
        entry = dict(url=url, fetched_us=time.time_ns() // 1000)
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'DerivativesMonitor/1.0',
                'Referer': 'https://stock.finance.sina.com.cn/'})
            with urllib.request.urlopen(request, timeout=8) as response:
                raw = response.read(16 * 1024 * 1024 + 1)
                entry['http_status'] = response.status
            if len(raw) > 16 * 1024 * 1024:
                raise ValueError('response exceeds 16 MiB')
            name = hashlib.sha256(url.encode()).hexdigest()[:20] + '.raw'
            (self.directory / name).write_bytes(raw)
            entry.update(file=name, sha256=hashlib.sha256(raw).hexdigest())
            return raw
        except Exception as error:
            entry['error'] = type(error).__name__ + ': ' + str(error)
            raise
        finally:
            self.requests.append(entry)
            atomic_json(self.directory / 'requests.json', self.requests)


def discover(fetch, requested_day, shfe_day=True):
    found, failures = {}, {}
    # A dated older official file remains useful, but never counts as current.
    for offset in range(10):
        source_day = (day(requested_day) - timedelta(days=offset)).strftime('%Y%m%d')
        url = f'http://www.cffex.com.cn/sj/jycs/{source_day[:6]}/{source_day[6:]}/index.xml'
        try:
            products, errors = parse_cffex(fetch(url), source_day)
            failures.update(errors)
            for product, rows in products.items():
                rows = [r for r in rows if r['expiry'] >= requested_day]
                if rows and product not in found:
                    found[product] = dict(instruments=rows, source=url, data_date=source_day,
                        verified=source_day == requested_day, stale=source_day != requested_day,
                        error='' if source_day == requested_day else 'using older official publication')
            # Once a real publication exists, do not make nine more requests for a missing product.
            if products:
                break
        except Exception as error:
            failures['CFFEX'] = str(error)
    for product in OPTIONS:
        if product in found and found[product]['verified']:
            continue
        base = 'https://stock.finance.sina.com.cn/futures/'
        page = base + f'view/optionsCffexDP.php/{product.lower()}/cffex'
        try:
            months = parse_expiries(fetch(page), product)
            rows = []
            for month in months:
                params = urllib.parse.urlencode(dict(type='futures', product=product.lower(),
                    exchange='cffex', pinzhong=product.lower() + month))
                rows.extend(parse_sina(fetch(base + 'api/openapi.php/OptionService.getOptionData?' + params), product, month))
            # Preserve official expiry metadata for contracts also seen in the fallback.
            old_rows = {r['id']: r for r in found.get(product, {}).get('instruments', [])}
            old_rows.update({r['id']: dict(r, expiry=old_rows.get(r['id'], {}).get('expiry')) for r in rows})
            found[product] = dict(instruments=sorted(old_rows.values(), key=lambda r: r['id']),
                source=page, data_date=None, verified=False, stale=False,
                error='public chain only; not verified against current official listing')
        except Exception as error:
            failures[product] = str(error)
    # Independently fail SHFE products without erasing the CFFEX result.
    shfe_day = requested_day if shfe_day is True else shfe_day
    if shfe_day is None:
        failures['SHFE'] = 'calendar unavailable; night-session trading day is unknown'
    else:
        for offset in range(10):
            source_day = (day(shfe_day) - timedelta(days=offset)).strftime('%Y%m%d')
            url = f'https://www.shfe.com.cn/data/busiparamdata/future/ContractBaseInfo{source_day}.dat'
            try:
                products, errors = parse_shfe(fetch(url), source_day)
                failures.update(errors)
                for product, rows in products.items():
                    rows = [r for r in rows if r['expiry'] >= shfe_day]
                    if rows:
                        found[product] = dict(instruments=rows, source=url, data_date=source_day,
                            verified=source_day == shfe_day, stale=source_day != shfe_day,
                            error='' if source_day == shfe_day else 'using older official publication')
                if products:
                    break
            except Exception as error:
                failures['SHFE'] = str(error)
    return found, failures


def merge(previous, found, failures, requested_day, dates=None):
    dates = dates or dict(CFFEX=requested_day, SHFE=requested_day)
    result = {}
    for product in PRODUCTS:
        exchange = 'SHFE' if product in SHFE_PRODUCTS else 'CFFEX'
        target_day = dates[exchange]
        old = previous.get('products', {}).get(product, {})
        candidate = found.get(product)
        if candidate:
            candidate = dict(candidate)
            rows = {r['id']: r for r in candidate['instruments']}
            # Do not silently delete still-live contracts after truncated source responses.
            retained = [r for r in old.get('instruments', []) if r['id'] not in rows
                and (not target_day or not r.get('expiry') or r['expiry'] >= target_day)]
            if retained:
                rows.update({r['id']: r for r in retained})
                candidate.update(verified=False, stale=True, error='retained previously discovered unexpired contracts missing from source')
            candidate['discovered_count'] = len(candidate['instruments'])
            candidate['discovered_ids'] = [r['id'] for r in candidate['instruments']]
            candidate['instruments'] = sorted(rows.values(), key=lambda r: r['id'])
            result[product] = candidate
        else:
            result[product] = dict(old, instruments=old.get('instruments', []),
                discovered_count=0, discovered_ids=[], verified=False, stale=True,
                error=failures.get(product, failures.get(exchange, 'no product listing available')))
        result[product].update(exchange=exchange, requested_day=target_day)
    return dict(schema_version=1, updated_us=time.time_ns() // 1000, requested_day=requested_day,
        requested_days=dates, complete=all(p.get('verified') and not p.get('stale') for p in result.values()), products=result)


def publish(directory, manifest, restart=None, run=subprocess.run):
    universe = directory / 'universe'
    universe.mkdir(parents=True, exist_ok=True)
    instruments = sorted({r['id'] for p in manifest['products'].values() for r in p['instruments']})
    if not instruments:
        raise ValueError('no usable contracts; existing universe unchanged')
    if len(instruments) > 10000:
        raise ValueError('more than 10000 instruments; existing universe unchanged')
    content = ''.join(code + '\n' for code in instruments)
    current = universe / 'current'
    previous = (current / 'instruments.txt').read_text() if current.exists() else ''
    changed = previous != content
    generation = universe / 'generations' / uuid.uuid4().hex
    generation.mkdir(parents=True)
    (generation / 'instruments.txt').write_text(content)
    atomic_json(generation / 'manifest.json', manifest)
    temporary = universe / ('current-' + uuid.uuid4().hex)
    temporary.symlink_to(generation.relative_to(universe), target_is_directory=True)
    os.replace(temporary, current)
    needs_restart = changed
    diagnostic = directory / 'collector-runtime.sqlite'
    if restart and diagnostic.exists():
        try:
            import sqlite3
            if diagnostic.is_symlink():
                raise ValueError('runtime database must not be a symlink')
            if any(diagnostic.with_name(diagnostic.name + suffix).is_symlink() for suffix in ('-journal', '-wal', '-shm')):
                raise ValueError('runtime sidecar must not be a symlink')
            with contextlib.closing(sqlite3.connect(diagnostic.absolute().as_uri() + '?mode=ro', uri=True, timeout=0.1)) as db:
                db.execute('PRAGMA query_only=ON')
                db.execute('BEGIN')
                if (runtime_schema_fingerprint(db) != RUNTIME_SCHEMA_FINGERPRINT
                        or db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete'):
                    raise ValueError('unsupported runtime schema')
                status = db.execute('SELECT run_id,updated_us,target_count FROM current_status WHERE singleton=1').fetchone()
                rows = db.execute('SELECT instrument_id,run_id,updated_us FROM instrument_status').fetchall()
                if not status or len(rows) != status[2] or any(row[1:] != status[:2] for row in rows):
                    raise ValueError('inconsistent runtime snapshot')
                needs_restart |= {row[0] for row in rows} != set(instruments)
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
            needs_restart = True
    if needs_restart and restart:
        active = run(['systemctl', '--user', 'is-active', '--quiet', restart], check=False)
        if active.returncode == 0:
            run(['systemctl', '--user', 'restart', '--no-block', restart], check=True)
    return changed, len(instruments)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--date', help='explicit publication trading day for both exchanges (YYYYMMDD)')
    parser.add_argument('--restart-service')
    parser.add_argument('--scheduled', action='store_true', help='skip retries after a complete refresh today')
    parser.add_argument('--if-needed', action='store_true', help='skip an already attempted startup refresh today')
    args = parser.parse_args()
    dates = requested_dates(args.date)
    args.date = dates['CFFEX']
    args.data_dir.mkdir(parents=True, exist_ok=True)
    with (args.data_dir / '.universe.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        status_path = args.data_dir / '.universe-status.json'
        previous_path = args.data_dir / 'universe/current/manifest.json'
        previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
        status = json.loads(status_path.read_text()) if status_path.exists() else {}
        if (args.if_needed or (args.scheduled and status.get('complete'))) and status.get('requested_days') == dates and previous:
            return 0
        attempt = datetime.now(ZONE).strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
        fetch = Fetcher(args.data_dir / 'universe/raw' / attempt)
        try:
            found, failures = discover(fetch, args.date, dates['SHFE'])
            manifest = merge(previous, found, failures, args.date, dates)
            manifest['evidence'] = str(fetch.directory.relative_to(args.data_dir))
            changed, count = publish(args.data_dir, manifest, args.restart_service)
            status = dict(requested_day=args.date, requested_days=dates, updated_us=time.time_ns() // 1000,
                complete=manifest['complete'], changed=changed, count=count, error='', evidence=manifest['evidence'])
            print(json.dumps(status, ensure_ascii=False), flush=True)
            atomic_json(status_path, status)
            return 0 if manifest['complete'] else 2
        except Exception as error:
            atomic_json(status_path, dict(requested_day=args.date, requested_days=dates, updated_us=time.time_ns() // 1000,
                complete=False, error=str(error), evidence=str(fetch.directory.relative_to(args.data_dir))))
            print('universe update failed: ' + str(error), file=sys.stderr)
            return 1


if __name__ == '__main__':
    sys.exit(main())
