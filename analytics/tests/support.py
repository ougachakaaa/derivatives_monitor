"""Shared TEST DOUBLE package and Raw builders for Analytics and HTTP tests."""
import json
import sqlite3

from analytics.skew_references import digest
from analytics.tests.test_skew import CHAIN, reference
from data_provider.market_calendar import DEFAULT_DIRECTORY, parse_at
from data_provider.market_frame import OBSERVATION_COLUMNS, micros


DAY = '20260916'
MONTH = '2610'
START = parse_at('2026-09-16T09:30:00+08:00')


def write_package(root):
    bundle = reference()
    bundle.pop('bundle_sha256')
    rows = [dict(id=row['instrument'], month=MONTH, side=row['side'], strike=row['strike'],
                 expiry='20261016') for row in CHAIN['rows']]
    universe = {'schema_version': 1, 'requested_day': DAY, 'products': {'MO': {
        'exchange': 'CFFEX', 'requested_day': DAY, 'verified': True, 'stale': False,
        'data_date': DAY, 'source': 'fixture://TEST-DOUBLE', 'instruments': rows}}}
    content = {'calendar.json': (DEFAULT_DIRECTORY / '2026.json').read_bytes(),
               'universe.json': json.dumps(universe).encode()}
    bundle['calendar']['version'] = json.loads(content['calendar.json'])['version']
    for name in ('universe', 'calendar'):
        bundle[name]['sha256'] = digest(content[name + '.json'])
    content['bundle.json'] = json.dumps(bundle).encode()
    content['manifest.json'] = json.dumps({'schema_version': 1, 'bundle_id': bundle['bundle_id'],
        'sha256': {name: digest(value) for name, value in content.items()}}).encode()
    package = root / DAY / bundle['bundle_id']
    package.mkdir(parents=True)
    for name, value in content.items():
        (package / name).write_bytes(value)
    (root / DAY / (MONTH + '.json')).write_text(json.dumps({'bundle_id': bundle['bundle_id']}))
    return package


def make_database(root):
    database = sqlite3.connect(root / (DAY + '.sqlite'), check_same_thread=False)
    database.executescript('''PRAGMA application_id=1145914161; PRAGMA user_version=1;
        CREATE TABLE dataset(singleton INTEGER PRIMARY KEY, trading_day TEXT, schema_version INTEGER);
        INSERT INTO dataset VALUES(1,'20260916',1);''')
    definitions = []
    for name in OBSERVATION_COLUMNS:
        if name == 'id':
            definitions.append('id INTEGER PRIMARY KEY')
        elif name in ('sequence', 'received_us', 'snapshot_us', 'UpdateMillisec',
                      'BidVolume1', 'AskVolume1'):
            definitions.append(name + ' INTEGER')
        elif name in ('TradingDay', 'ExchangeID', 'InstrumentID', 'ExchangeInstID',
                      'ActionDay', 'UpdateTime', 'run_id'):
            definitions.append(name + ' TEXT')
        else:
            definitions.append(name + ' REAL')
    database.execute('CREATE TABLE snapshots(' + ','.join(definitions) + ')')
    database.execute('CREATE INDEX snapshots_instrument_time '
                     'ON snapshots(InstrumentID,received_us,id)')
    database.commit()
    (root / '.collector.lock').touch()
    return database


def append_chain(database, end, *, invalid=False):
    for row in CHAIN['rows']:
        received = micros(end) - row['age_us']
        values = dict(run_id='TEST_DOUBLE_RUN', sequence=row['id'], received_us=received,
                      snapshot_us=micros(end) + 1_000_000, TradingDay=DAY, ExchangeID='CFFEX',
                      InstrumentID=row['instrument'], ActionDay=DAY, UpdateTime='09:30:40',
                      UpdateMillisec=0, BidPrice1=row['bid'], AskPrice1=row['ask'],
                      BidVolume1=0 if invalid else row['bid_volume'],
                      AskVolume1=row['ask_volume'])
        database.execute('INSERT INTO snapshots(' + ','.join(values) + ') VALUES('
                         + ','.join('?' for _ in values) + ')', tuple(values.values()))
    database.commit()
