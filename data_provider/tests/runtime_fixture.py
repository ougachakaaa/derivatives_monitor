"""TEST DOUBLE runtime database fixtures. Never used by production publishers."""
import sqlite3
import time
from contextlib import closing


def write_runtime(directory, heartbeat=None, instruments=None):
    hb = dict(run_id='a'*32, updated_us=time.time_ns() // 1000, process_state='running',
              connected=True, logged_in=True, connections=1, disconnections=0,
              accepted=0, written=0)
    hb.update(heartbeat or {})
    active = hb['process_state'] in ('starting', 'running')
    rows = instruments if instruments is not None else [dict(id='IF2609', subscription='subscribed',
                                                            received=hb['accepted'], error_id=0)]
    ticks = sum(row.get('received', 0) for row in rows)
    current = dict(singleton=1, run_id=hb['run_id'], heartbeat_us=hb['updated_us'], updated_us=hb['updated_us'],
        process_state=hb['process_state'], connected=int(hb['connected']) if active else 0,
        logged_in=int(hb['logged_in']) if active else 0, target_count=len(rows), subscribed_count=0,
        subscription_failed=0, trading_day='20260908' if ticks else None, total_ticks_today=ticks,
        ticks_received=ticks, last_tick_received_us=hb.get('last_received_us') or hb['updated_us'] if ticks else None,
        last_market_commit_us=hb.get('last_commit_us') or hb['updated_us'] if hb['written'] else None,
        connections=hb['connections'], disconnections=hb['disconnections'], callbacks_accepted=ticks,
        bars_written=hb['written'], partial_bars=0, late_callbacks=0, invalid_trading_day=0,
        invalid_event_time=0, unknown_instrument=0, event_time_regressions=0)
    result = []
    for i, row in enumerate(rows):
        received = row.get('received', 0)
        state = row.get('subscription', 'not_sent') if current['logged_in'] else 'not_sent'
        current['subscribed_count'] += state == 'subscribed'
        current['subscription_failed'] += state == 'failed'
        result.append(dict(instrument_id=row['id'], run_id=current['run_id'], updated_us=current['updated_us'],
            subscription=state, error_id=row.get('error_id', 0), ticks_received=received,
            last_tick_received_us=(row.get('last_received_us') or current['last_tick_received_us']) if received else None,
            callbacks_accepted=received, bars_written=hb['written'] if i == 0 else 0,
            partial_bars=0, late_callbacks=0, invalid_event_time=0))
    path = directory / 'collector-runtime.sqlite'
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('PRAGMA user_version=1')
        # Independent TEST DOUBLE schema: production DDL constraints are exercised by CTest.
        for table, record in [('current_status', current), ('instrument_status', result[0])]:
            text = {'run_id', 'process_state', 'trading_day', 'instrument_id', 'subscription'}
            db.execute('CREATE TABLE IF NOT EXISTS ' + table + '(' + ','.join(
                key + (' TEXT' if key in text else ' INTEGER') for key in record) + ')')
            db.execute('DELETE FROM ' + table)
        db.execute('INSERT INTO current_status VALUES(' + ','.join('?' for _ in current) + ')', tuple(current.values()))
        for row in result:
            db.execute('INSERT INTO instrument_status VALUES(' + ','.join('?' for _ in row) + ')', tuple(row.values()))
    return path


def update_runtime(directory, sql, parameters=()):
    with closing(sqlite3.connect(directory / 'collector-runtime.sqlite')) as db, db:
        db.execute(sql, parameters)
