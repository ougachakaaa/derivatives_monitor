"""Read-only adapter for the current Collector runtime schema; no History/Health evaluation."""
from datetime import datetime
import hashlib
import re
import sqlite3
import time

from data_provider.errors import DataUnavailableError

CURRENT_COUNTERS = (
    'target_count', 'subscribed_count', 'subscription_failed', 'total_ticks_today',
    'ticks_received', 'connections', 'disconnections', 'callbacks_accepted', 'bars_written',
    'partial_bars', 'late_callbacks', 'invalid_trading_day', 'invalid_event_time',
    'unknown_instrument', 'event_time_regressions',
)
INSTRUMENT_COUNTERS = ('ticks_received', 'callbacks_accepted', 'bars_written', 'partial_bars',
                       'late_callbacks', 'invalid_event_time')
CURRENT_COLUMNS = {'singleton', 'run_id', 'heartbeat_us', 'updated_us', 'process_state',
                   'connected', 'logged_in', 'trading_day', 'last_tick_received_us',
                   'last_market_commit_us', *CURRENT_COUNTERS}
INSTRUMENT_COLUMNS = {'instrument_id', 'run_id', 'updated_us', 'subscription', 'error_id',
                      'last_tick_received_us', *INSTRUMENT_COUNTERS}
# SHA-256 of the whitespace-free ordered (type, name, DDL) concatenation from Raw Boundary.
RUNTIME_SCHEMA_FINGERPRINT = '8fb54c462453fc5b4319604b289472fa6e6265fcadc94778cb9d69292e1d53e5'


def _schema_fingerprint(connection):
    rows = connection.execute(
        "SELECT type,name,sql FROM sqlite_master "
        "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type,name"
    ).fetchall()
    canonical = ''.join('\x1f'.join(row) for row in rows)
    canonical = re.sub(r'\s+', '', canonical).encode()
    return hashlib.sha256(canonical).hexdigest()


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _validate(current, instruments):
    if set(current) != CURRENT_COLUMNS or current['singleton'] != 1:
        raise ValueError('invalid current status')
    if not isinstance(current['run_id'], str) or not re.fullmatch('[0-9a-f]{32}', current['run_id']):
        raise ValueError('invalid run identity')
    if current['process_state'] not in ('starting', 'running', 'stopped', 'failed'):
        raise ValueError('invalid process state')
    if any(not _integer(current[k]) for k in CURRENT_COUNTERS):
        raise ValueError('invalid counter')
    if any(not _integer(current[k], 1) for k in ('heartbeat_us', 'updated_us')):
        raise ValueError('invalid heartbeat')
    if current['heartbeat_us'] != current['updated_us']:
        raise ValueError('inconsistent publication')
    if any(type(current[k]) is not int or current[k] not in (0, 1) for k in ('connected', 'logged_in')):
        raise ValueError('invalid session')
    if current['logged_in'] and not current['connected']:
        raise ValueError('login without connection')
    for key in ('last_tick_received_us', 'last_market_commit_us'):
        if current[key] is not None and not _integer(current[key], 1):
            raise ValueError('invalid timestamp')
    day = current['trading_day']
    if day is not None:
        if not isinstance(day, str) or not re.fullmatch('[0-9]{8}', day):
            raise ValueError('invalid trading day')
        datetime.strptime(day, '%Y%m%d')
    if (day is None) != (current['ticks_received'] == 0):
        raise ValueError('inconsistent trading day')
    if ((current['last_tick_received_us'] is None) != (current['ticks_received'] == 0)
            or current['total_ticks_today'] > current['ticks_received']
            or (day is not None and current['total_ticks_today'] == 0)):
        raise ValueError('inconsistent tick count')
    if (current['last_market_commit_us'] is None) != (current['bars_written'] == 0):
        raise ValueError('inconsistent market commit')
    if current['callbacks_accepted'] + current['late_callbacks'] != current['ticks_received']:
        raise ValueError('inconsistent reception counters')
    if current['partial_bars'] > current['bars_written']:
        raise ValueError('invalid partial count')
    if len(instruments) != current['target_count'] or not 0 < len(instruments) <= 10000:
        raise ValueError('inconsistent target count')
    seen = set()
    for row in instruments:
        if set(row) != INSTRUMENT_COLUMNS:
            raise ValueError('invalid instrument columns')
        code = row['instrument_id']
        if not isinstance(code, str) or not code or code in seen:
            raise ValueError('invalid instrument identity')
        seen.add(code)
        if row['run_id'] != current['run_id'] or row['updated_us'] != current['updated_us']:
            raise ValueError('mixed runtime snapshots')
        if row['subscription'] not in ('not_sent', 'pending', 'subscribed', 'failed'):
            raise ValueError('invalid subscription')
        if type(row['error_id']) is not int or any(not _integer(row[k]) for k in INSTRUMENT_COUNTERS):
            raise ValueError('invalid instrument counters')
        stamp = row['last_tick_received_us']
        if stamp is not None and not _integer(stamp, 1):
            raise ValueError('invalid instrument timestamp')
        if ((stamp is None) != (row['ticks_received'] == 0)
                or row['callbacks_accepted'] + row['late_callbacks'] != row['ticks_received']
                or row['partial_bars'] > row['bars_written']):
            raise ValueError('inconsistent instrument counts')
    for key in INSTRUMENT_COUNTERS:
        # Invalid event time for unknown instruments is rejected before this counter.
        if sum(row[key] for row in instruments) != current[key]:
            raise ValueError('inconsistent aggregate counters')
    for field, state in (('subscribed_count', 'subscribed'), ('subscription_failed', 'failed')):
        if sum(row['subscription'] == state for row in instruments) != current[field]:
            raise ValueError('inconsistent subscription count')
    if not current['logged_in'] and any(row['subscription'] != 'not_sent' for row in instruments):
        raise ValueError('subscriptions without login')
    if current['process_state'] in ('stopped', 'failed') and (current['connected'] or current['logged_in']):
        raise ValueError('session after shutdown')


def read_runtime_status(directory):
    """Return one committed snapshot. A missing DB is distinct from an unreadable one."""
    path = directory / 'collector-runtime.sqlite'
    connection = None
    try:
        if path.is_symlink():
            raise ValueError('runtime database must not be a symlink')
        if not path.exists():
            return None
        for suffix in ('-journal', '-wal', '-shm'):
            if path.with_name(path.name + suffix).is_symlink():
                raise ValueError('runtime sidecar must not be a symlink')
        connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=0.1)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        if connection.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
            raise ValueError('unsupported runtime journal')
        if _schema_fingerprint(connection) != RUNTIME_SCHEMA_FINGERPRINT:
            raise ValueError('invalid runtime schema')
        rows = connection.execute('SELECT * FROM current_status LIMIT 2').fetchall()
        if len(rows) != 1:
            raise ValueError('invalid current status cardinality')
        current = dict(rows[0])
        instruments = [dict(row) for row in connection.execute('SELECT * FROM instrument_status ORDER BY instrument_id LIMIT 10001')]
        _validate(current, instruments)
        current['connected'] = bool(current['connected'])
        current['logged_in'] = bool(current['logged_in'])
        return current, instruments
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, OverflowError):
        raise DataUnavailableError('Invalid or unavailable Collector runtime status') from None
    finally:
        if connection is not None:
            connection.close()


def diagnostic(snapshot, now_us=None):
    if snapshot is None:
        return {'status': 'unknown', 'process_alive': False, 'heartbeat': None}
    current, _ = snapshot
    age = ((time.time_ns() // 1000 if now_us is None else now_us) - current['heartbeat_us']) / 1_000_000
    fresh = 0 <= age <= 10
    state = current['process_state']
    heartbeat = dict(current, schema_version=1, expected=current['target_count'],
                     subscribed=current['subscribed_count'], accepted=current['ticks_received'],
                     written=current['bars_written'], last_received_us=current['last_tick_received_us'],
                     last_commit_us=current['last_market_commit_us'])
    heartbeat.pop('singleton')
    return {'status': state if fresh else 'stale',
            'process_alive': fresh and state in ('starting', 'running'),
            'age_seconds': round(age, 3), 'heartbeat': heartbeat}
