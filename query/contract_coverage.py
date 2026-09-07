"""Read-only coverage diagnostics, independent of SQLite schema and query locks."""
from datetime import datetime
import json
import re
import time
from zoneinfo import ZoneInfo

PRODUCTS = ('IF', 'IH', 'IC', 'IM', 'TS', 'TF', 'T', 'TL', 'IO', 'HO', 'MO')
ID = re.compile(r'^(IF|IH|IC|IM|TS|TF|TL|T|IO|HO|MO)(\d{4})(?:-[CP]-\d+(?:\.\d+)?)?$')


def read_json(path, limit=8 * 1024 * 1024):
    with path.open('rb') as stream:
        value = json.loads(stream.read(limit + 1))
    if not isinstance(value, dict) or value.get('schema_version', 1) != 1:
        raise ValueError('unsupported diagnostic schema')
    return value


def coverage(store):
    from storage import QueryError
    store.check_directory()
    try:
        manifest = read_json(store.directory / 'universe/current/manifest.json')
    except FileNotFoundError:
        manifest = dict(products={}, complete=False)
    try:
        update = read_json(store.directory / '.universe-status.json')
    except FileNotFoundError:
        update = {}
    try:
        snapshot = read_json(store.directory / '.collector-coverage.json')
    except FileNotFoundError:
        snapshot = {}
    heartbeat = store.heartbeat()
    alive = heartbeat['process_alive']
    hb = heartbeat.get('heartbeat') or {}
    age = (time.time_ns() // 1000 - snapshot.get('updated_us', 0)) / 1_000_000
    current = alive and snapshot.get('run_id') == hb.get('run_id') and 0 <= age <= 10
    items = snapshot.get('instruments', [])
    if not isinstance(items, list) or len(items) > 10000:
        raise QueryError(503, 'Invalid Collector coverage diagnostic')
    statuses = {}
    for item in items:
        if (not isinstance(item, dict) or not isinstance(item.get('id'), str)
                or item.get('subscription') not in ('not_sent', 'pending', 'subscribed', 'failed')
                or type(item.get('received')) is not int or item['received'] < 0
                or type(item.get('error_id')) is not int):
            raise QueryError(503, 'Invalid instrument diagnostic')
        statuses[item['id']] = item
    current = current and len(statuses) == hb.get('expected')
    today = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')
    groups, details = [], []
    listing_complete = manifest.get('complete', False) and manifest.get('requested_day') == today and update.get('complete', True)
    all_targets = set()
    for product in PRODUCTS:
        entry = manifest.get('products', {}).get(product, {})
        rows = entry.get('instruments', [])
        targets = {r['id']: r for r in rows}
        all_targets.update(targets)
        discovered = set(entry.get('discovered_ids', []))
        active = {code: s for code, s in statuses.items() if ID.fullmatch(code) and ID.fullmatch(code)[1] == product}
        months = sorted({r['month'] for r in rows} | {ID.fullmatch(code)[2] for code in active}) or ['—']
        for month in months:
            expected_ids = {code for code, r in targets.items() if r['month'] == month}
            actual_ids = {code for code in active if ID.fullmatch(code)[2] == month}
            selected = [active[code] for code in sorted(actual_ids)]
            fresh_listing = bool(entry.get('verified')) and not entry.get('stale') and entry.get('data_date') == today
            row = dict(product=product, month=month, discovered=len(discovered & expected_ids),
                listed=len(expected_ids), target=len(actual_ids) if current else None,
                subscribed=sum(s['subscription'] == 'subscribed' for s in selected) if current else None,
                failed=sum(s['subscription'] == 'failed' for s in selected) if current else None,
                pending=sum(s['subscription'] in ('pending', 'not_sent') for s in selected) if current else None,
                received=sum(s['received'] > 0 for s in selected) if current else None,
                no_push=sum(s['subscription'] == 'subscribed' and s['received'] == 0 for s in selected) if current else None,
                source=entry.get('source'), data_date=entry.get('data_date'), verified=fresh_listing,
                stale=entry.get('stale', True) or manifest.get('requested_day') != today,
                error=entry.get('error', '尚未发现合约'),
                missing_targets=sorted(expected_ids - actual_ids) if current else None,
                extra_targets=sorted(actual_ids - expected_ids) if current else None)
            groups.append(row)
        for code in sorted(set(targets) | set(active)):
            state = active.get(code) if current else None
            details.append(dict(id=code, product=product, month=ID.fullmatch(code)[2],
                subscription=state['subscription'] if state else 'unknown',
                error_id=state['error_id'] if state else None,
                received=state['received'] if state else None,
                last_received_us=state.get('last_received_us') if state else None))
    return dict(schema_version=1, updated_us=manifest.get('updated_us'), requested_day=manifest.get('requested_day'),
        collector_current=current, run_id=snapshot.get('run_id'), listing_complete=bool(listing_complete),
        complete=bool(listing_complete and current and all_targets == set(statuses)
            and all(s['subscription'] == 'subscribed' for s in statuses.values())),
        groups=groups, instruments=details, update=update)
