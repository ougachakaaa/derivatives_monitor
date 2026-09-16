"""TEST DOUBLE runtime database fixtures. Never used by production publishers."""
import sqlite3
import time
from contextlib import closing


RUNTIME_SCHEMA = """
CREATE TABLE runs(run_id TEXT PRIMARY KEY NOT NULL CHECK(length(run_id)=32 AND run_id NOT GLOB '*[^0-9a-f]*'),started_us INTEGER NOT NULL CHECK(started_us>0),ended_us INTEGER,terminal_state TEXT CHECK(terminal_state IN('stopped','failed')),instruments TEXT NOT NULL,source TEXT NOT NULL,CHECK((ended_us IS NULL AND terminal_state IS NULL) OR (ended_us IS NOT NULL AND ended_us>=started_us AND terminal_state IS NOT NULL)));
CREATE TABLE current_status(singleton INTEGER PRIMARY KEY CHECK(singleton=1),run_id TEXT NOT NULL REFERENCES runs(run_id),heartbeat_us INTEGER NOT NULL CHECK(heartbeat_us>0),updated_us INTEGER NOT NULL CHECK(updated_us=heartbeat_us),process_state TEXT NOT NULL CHECK(process_state IN('starting','running','stopped','failed')),connected INTEGER NOT NULL CHECK(connected IN(0,1)),logged_in INTEGER NOT NULL CHECK(logged_in IN(0,1) AND logged_in<=connected),target_count INTEGER NOT NULL CHECK(target_count>=0),subscribed_count INTEGER NOT NULL CHECK(subscribed_count>=0 AND subscribed_count<=target_count),subscription_failed INTEGER NOT NULL CHECK(subscription_failed>=0 AND subscription_failed<=target_count),trading_day TEXT CHECK(length(trading_day)=8 AND trading_day NOT GLOB '*[^0-9]*'),total_ticks_today INTEGER NOT NULL CHECK(total_ticks_today>=0),ticks_received INTEGER NOT NULL CHECK(ticks_received>=0),last_tick_received_us INTEGER CHECK(last_tick_received_us>0),last_market_commit_us INTEGER CHECK(last_market_commit_us>0),connections INTEGER NOT NULL CHECK(connections>=0),disconnections INTEGER NOT NULL CHECK(disconnections>=0),callbacks_accepted INTEGER NOT NULL CHECK(callbacks_accepted>=0),bars_written INTEGER NOT NULL CHECK(bars_written>=0),partial_bars INTEGER NOT NULL CHECK(partial_bars>=0 AND partial_bars<=bars_written),late_callbacks INTEGER NOT NULL CHECK(late_callbacks>=0),invalid_trading_day INTEGER NOT NULL CHECK(invalid_trading_day>=0),invalid_event_time INTEGER NOT NULL CHECK(invalid_event_time>=0),unknown_instrument INTEGER NOT NULL CHECK(unknown_instrument>=0),event_time_regressions INTEGER NOT NULL CHECK(event_time_regressions>=0),CHECK(ticks_received=callbacks_accepted+late_callbacks));
CREATE TABLE instrument_status(instrument_id TEXT PRIMARY KEY NOT NULL,run_id TEXT NOT NULL REFERENCES runs(run_id),updated_us INTEGER NOT NULL CHECK(updated_us>0),subscription TEXT NOT NULL CHECK(subscription IN('not_sent','pending','subscribed','failed')),error_id INTEGER NOT NULL,ticks_received INTEGER NOT NULL CHECK(ticks_received>=0),last_tick_received_us INTEGER CHECK(last_tick_received_us>0),callbacks_accepted INTEGER NOT NULL CHECK(callbacks_accepted>=0),bars_written INTEGER NOT NULL CHECK(bars_written>=0),partial_bars INTEGER NOT NULL CHECK(partial_bars>=0 AND partial_bars<=bars_written),late_callbacks INTEGER NOT NULL CHECK(late_callbacks>=0),invalid_event_time INTEGER NOT NULL CHECK(invalid_event_time>=0),CHECK(ticks_received=callbacks_accepted+late_callbacks));
CREATE TABLE runtime_snapshots(run_id TEXT NOT NULL REFERENCES runs(run_id),interval_start_us INTEGER NOT NULL CHECK(interval_start_us%15000000=0),interval_end_us INTEGER NOT NULL CHECK(interval_end_us=interval_start_us+15000000),observed_us INTEGER NOT NULL CHECK(observed_us>=interval_end_us),process_state TEXT NOT NULL CHECK(process_state IN('starting','running')),connected INTEGER NOT NULL CHECK(connected IN(0,1)),logged_in INTEGER NOT NULL CHECK(logged_in IN(0,1) AND logged_in<=connected),target_count INTEGER NOT NULL CHECK(target_count>=0),subscribed_count INTEGER NOT NULL CHECK(subscribed_count>=0 AND subscribed_count<=target_count),subscription_failed INTEGER NOT NULL CHECK(subscription_failed>=0 AND subscription_failed<=target_count),tick_count INTEGER NOT NULL CHECK(tick_count>=0),market_bar_count INTEGER NOT NULL CHECK(market_bar_count>=0),partial_bar_count INTEGER NOT NULL CHECK(partial_bar_count>=0 AND partial_bar_count<=market_bar_count),last_tick_received_us INTEGER CHECK(last_tick_received_us>0),last_market_commit_us INTEGER CHECK(last_market_commit_us>0),PRIMARY KEY(run_id,interval_start_us));
CREATE INDEX runtime_snapshots_interval ON runtime_snapshots(interval_start_us);
"""


def create_runtime_schema(db):
    db.executescript(RUNTIME_SCHEMA)


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
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone():
            create_runtime_schema(db)
        db.execute('DELETE FROM current_status')
        db.execute('DELETE FROM instrument_status')
        db.execute('INSERT OR IGNORE INTO runs(run_id,started_us,instruments,source) VALUES(?,?,?,?)',
                   (current['run_id'], current['updated_us'], '[]', 'TEST DOUBLE'))
        db.execute('INSERT INTO current_status VALUES(' + ','.join('?' for _ in current) + ')', tuple(current.values()))
        for row in result:
            db.execute('INSERT INTO instrument_status VALUES(' + ','.join('?' for _ in row) + ')', tuple(row.values()))
    return path


def update_runtime(directory, sql, parameters=()):
    with closing(sqlite3.connect(directory / 'collector-runtime.sqlite')) as db, db:
        # Deliberately permit impossible TEST DOUBLE rows so reader validation is exercised too.
        db.execute('PRAGMA ignore_check_constraints=ON')
        db.execute(sql, parameters)
