from datetime import datetime
import unittest

from market_state import Scope, Universe, aware, micros


def at(value):
    return datetime.fromisoformat('2026-09-08T' + value + '+08:00')


class ScopeTest(unittest.TestCase):
    def test_explicit_scope_and_order(self):
        universe = Universe('20260908', 'fixture-v1', ('MO2609-P-5000', 'IF2609',
                            'MO2609-C-5000', 'MO2609-P-5000', 'MO2610-C-5000'), True)
        scope = Scope.select(universe, 'CFFEX', 'MO', month='2609', option_chain=True)
        self.assertEqual(scope.instruments, ('MO2609-C-5000', 'MO2609-P-5000'))
        self.assertEqual(scope.kind, 'option_chain')
        self.assertEqual(len(Scope.select(universe, 'CFFEX', 'MO').instruments), 3)
        self.assertEqual(Scope.instrument('au2610', '20260908').exchange, 'SHFE')
        self.assertEqual(Scope.select(universe, 'SHFE', 'AG', month='2609').instruments, ())

    def test_invalid_contract(self):
        for code in ('MO2609', 'IF2609-C-5000', 'AU2609', "';--", 'IF2613'):
            with self.assertRaises(ValueError):
                Scope.instrument(code, '20260908')
        universe = Universe('20260908', 'v1', ('IF2609',), False)
        self.assertFalse(Scope.select(universe, 'CFFEX', 'IF').universe_complete)
        for kwargs in ({'option_chain': True}, {'month': '2613'}, {'month': '2609', 'option_chain': True}):
            with self.assertRaises(ValueError):
                Scope.select(universe, 'CFFEX', 'IF', **kwargs)
        with self.assertRaises(ValueError):
            Universe('20260908', '', (), True)
        with self.assertRaises(ValueError):
            Universe('20260908', 'v1', 'IF2609', True)
        with self.assertRaises(ValueError):
            aware(datetime(2026, 9, 8))
        self.assertEqual(micros(at('09:30:00.000001')) - micros(at('09:30:00')), 1)

    def test_explicit_manifest_evidence(self):
        entry = dict(exchange='CFFEX', requested_day='20260908', data_date='20260908',
                     verified=True, stale=False, instruments=[dict(id='MO2609-C-5000', month='2609')])
        manifest = dict(schema_version=1, products={'MO': entry})
        def read():
            return Universe.from_manifest(manifest, 'CFFEX', 'MO', '20260908', 'saved-manifest-v1')
        self.assertTrue(read().complete)
        entry['stale'] = True
        self.assertFalse(read().complete)
        entry['requested_day'] = '20260907'
        with self.assertRaises(ValueError):
            read()

import fcntl
import hashlib
from pathlib import Path
import sqlite3
import tempfile

from market_state import MarketStateReader
from storage import QueryError, Store

# Actual v1 fact columns; same names/types as Collector VisitFacts, no mock Store.
TEXT_FIELDS = 'TradingDay ExchangeID InstrumentID ExchangeInstID ActionDay UpdateTime'.split()
INT_FIELDS = 'UpdateMillisec Volume BidVolume1 AskVolume1 BidVolume2 AskVolume2 BidVolume3 AskVolume3 BidVolume4 AskVolume4 BidVolume5 AskVolume5'.split()
REAL_FIELDS = ('LastPrice PreSettlementPrice PreClosePrice PreOpenInterest OpenPrice HighestPrice '
               'LowestPrice Turnover OpenInterest ClosePrice SettlementPrice UpperLimitPrice '
               'LowerLimitPrice PreDelta CurrDelta BidPrice1 AskPrice1 BidPrice2 AskPrice2 '
               'BidPrice3 AskPrice3 BidPrice4 AskPrice4 BidPrice5 AskPrice5 AveragePrice '
               'BandingUpperPrice BandingLowerPrice').split()


class FrameTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.lock = (self.directory / '.collector.lock').open('w')
        self.addCleanup(self.lock.close)
        self.path = self.directory / '20260908.sqlite'
        self.db = sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        self.db.executescript('''
            PRAGMA journal_mode=WAL;
            PRAGMA application_id=1145914161;
            PRAGMA user_version=1;
            CREATE TABLE dataset(singleton INTEGER PRIMARY KEY, trading_day TEXT, schema_version INTEGER);
            INSERT INTO dataset VALUES(1,'20260908',1);
            CREATE TABLE runs(run_id TEXT PRIMARY KEY, started_us INTEGER, stopped_us INTEGER,
                              last_write_us INTEGER, snapshot_interval_ms INTEGER, instruments TEXT, source TEXT);
            INSERT INTO runs VALUES('a',1,NULL,2,15000,'MO2609-C-5000','TEST_DOUBLE_MARKET_STATE');
            INSERT INTO runs VALUES('b',3,NULL,4,1000,'MO2609-C-5000','TEST_DOUBLE_MARKET_STATE');
        ''')
        columns = (['id INTEGER PRIMARY KEY', 'run_id TEXT', 'sequence INTEGER',
                    'received_us INTEGER', 'snapshot_us INTEGER']
                   + [name + ' TEXT' for name in TEXT_FIELDS]
                   + [name + ' INTEGER' for name in INT_FIELDS]
                   + [name + ' REAL' for name in REAL_FIELDS])
        self.db.execute('CREATE TABLE snapshots(' + ','.join(columns) + ',UNIQUE(run_id,sequence))')
        self.db.execute('CREATE INDEX snapshots_instrument_time ON snapshots(InstrumentID,received_us,id)')
        self.db.commit()
        # Active writer semantics: reader must consume existing WAL/SHM.
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.reader = MarketStateReader(Store(self.directory))
        self.scope = Scope.instrument('MO2609-C-5000', '20260908')
        self.sequence = 0

    def insert(self, received='09:30:45', code='MO2609-C-5000', **changes):
        self.sequence += 1
        received_us = micros(at(received)) if isinstance(received, str) else micros(received)
        values = dict(run_id='a', sequence=self.sequence, received_us=received_us,
                      snapshot_us=received_us + 15000000, TradingDay='20260908',
                      ExchangeID='CFFEX', InstrumentID=code, ActionDay='20260908',
                      UpdateTime='09:30:44', UpdateMillisec=123, LastPrice=101,
                      BidPrice1=100, AskPrice1=102, BidVolume1=3, AskVolume1=4,
                      Volume=1000, OpenInterest=2000)
        values.update(changes)
        self.db.execute('INSERT INTO snapshots(' + ','.join(values) + ') VALUES('
                        + ','.join('?' for _ in values) + ')', tuple(values.values()))
        self.db.commit()
        return self.sequence

    def frame(self, minute='09:30:00', **kwargs):
        return self.reader.minute(self.scope, at(minute), evaluated_at=at('16:00:00'), **kwargs)

    def test_minute_point_boundary_and_late_materialization(self):
        self.insert('09:29:59')  # previous auction: never inherited
        self.insert('09:30:45', snapshot_us=micros(at('09:31:05')))
        self.insert('09:31:00')
        frame = self.frame()
        row = frame['rows'][0]
        self.assertEqual(row['observation']['id'], 2)
        self.assertEqual(row['observation']['snapshot_us'], micros(at('09:31:05')))
        self.assertEqual(row['quality']['quote_age_us'], 15000000)
        self.assertEqual(row['observation']['UpdateMillisec'], 123)
        self.assertEqual(row['observation']['ActionDay'], '20260908')
        self.assertEqual(frame['completeness'], 'COMPLETE')
        self.assertTrue(frame['sealed'])
        self.assertFalse(frame['cutoff_inclusive'])
        point = self.reader.as_of(self.scope, at('09:31:00'))
        self.assertEqual(point['rows'][0]['observation']['id'], 3)
        self.assertEqual(point['rows'][0]['quality']['quote_age_us'], 0)
        self.assertEqual(self.frame(), frame)

    def test_ties_cross_run_source_clock_and_invalid_not_fallback(self):
        self.insert('09:30:45', sequence=999)
        self.insert('09:30:45', run_id='b', sequence=1, UpdateTime='09:00:00', BidPrice1=104)
        frame = self.frame()
        self.assertEqual(frame['rows'][0]['observation']['id'], 2)
        self.assertEqual(frame['rows'][0]['quality']['reasons'], ['crossed_book'])
        self.assertEqual(frame['completeness'], 'PARTIAL')

    def test_chain_completeness_missing_stale_invalid(self):
        codes = tuple(f'MO2609-{side}-{strike}' for side in ('C', 'P') for strike in range(4000, 8000, 100))
        self.scope = Scope.select(Universe('20260908', 'synthetic-full-chain', codes, True),
                                  'CFFEX', 'MO', month='2609', option_chain=True)
        for code in codes:
            self.insert(code=code)
        frame = self.frame()
        self.assertEqual((frame['expected_count'], frame['observed_count'], frame['usable_count']), (80, 80, 80))
        self.assertEqual(frame['completeness'], 'COMPLETE')
        self.assertEqual(len({r['instrument'] for r in frame['rows']}), 80)
        self.assertEqual([r['instrument'] for r in frame['rows']], sorted(codes))
        self.db.execute('DELETE FROM snapshots WHERE InstrumentID=?', (codes[0],))
        self.db.commit()
        self.insert('09:30:50', code=codes[1], AskPrice1=None)
        frame = self.frame(stale_after_us=12000000)
        self.assertEqual(frame['completeness'], 'PARTIAL')
        self.assertEqual((frame['missing_count'], frame['invalid_count'], frame['stale_count']), (1, 1, 78))
        self.assertIsNone(next(r for r in frame['rows'] if r['instrument'] == codes[0])['observation'])

    def test_empty_and_unverified_listing(self):
        self.assertEqual(self.frame()['completeness'], 'EMPTY')
        self.insert()
        self.scope = Scope.select(Universe('20260908', 'partial-listing', self.scope.instruments, False), 'CFFEX', 'MO')
        self.assertEqual(self.frame()['completeness'], 'PARTIAL')
        self.scope = Scope.select(Universe('20260908', 'empty', (), True), 'CFFEX', 'MO')
        self.assertEqual(self.frame()['completeness'], 'EMPTY')

    def test_age_threshold_and_explicit_same_period_carry(self):
        self.insert('09:30:00')
        self.assertEqual(self.frame()['stale_count'], 0)  # age == threshold
        later = self.frame('09:31:00')
        self.assertEqual(later['stale_count'], 1)
        self.assertEqual(later['rows'][0]['observation']['received_us'], micros(at('09:30:00')))
        self.assertEqual(later['rows'][0]['quality']['quote_age_us'], 120000000)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0], 1)

    def test_period_isolation_and_input_validation(self):
        self.insert('11:29:59')
        self.assertEqual(self.frame('13:00:00')['completeness'], 'EMPTY')
        self.insert('14:56:59')
        self.assertEqual(self.frame('14:57:00')['completeness'], 'EMPTY')
        for minute in ('11:30:00', '12:00:00', '15:00:00', '09:30:01'):
            with self.assertRaises(ValueError):
                self.frame(minute)
        with self.assertRaises(ValueError):
            self.frame(stale_after_us=-1)
        with self.assertRaises(ValueError):
            self.frame(raw_revision=999)
        with self.assertRaises(ValueError):
            self.reader.minute(self.scope, at('09:30:00'), evaluated_at=at('09:29:00'))
        with self.assertRaises(ValueError):
            self.reader.as_of(Scope.instrument('MO2609-C-5000', '20260907'), at('09:30:00'))

    def test_unsealed_minute_does_not_look_ahead(self):
        self.insert('09:30:10')
        self.insert('09:30:45')
        frame = self.reader.minute(self.scope, at('09:30:00'), evaluated_at=at('09:30:20'))
        self.assertFalse(frame['sealed'])
        self.assertEqual(frame['rows'][0]['observation']['id'], 1)
        self.assertEqual(frame['rows'][0]['quality']['quote_age_us'], 10000000)

    def test_append_revision_replay(self):
        self.insert('09:30:30')
        first = self.frame()
        self.insert('09:30:59', snapshot_us=micros(at('09:32:00')))
        self.assertNotEqual(self.frame(), first)
        self.assertEqual(self.frame(raw_revision=first['raw_revision']), first)
        self.assertEqual(self.frame(raw_revision=0)['completeness'], 'EMPTY')

    def test_offline_read_only_and_no_files_created(self):
        self.insert()
        self.db.close()
        fcntl.flock(self.lock, fcntl.LOCK_UN)
        before_files = set(self.directory.iterdir())
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.assertEqual(self.frame()['completeness'], 'COMPLETE')
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)
        self.assertEqual(set(self.directory.iterdir()), before_files)
        with self.reader.store.connect('20260908') as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute('DELETE FROM snapshots')

    def test_missing_database_is_not_empty(self):
        with self.assertRaises(QueryError) as caught:
            self.reader.as_of(Scope.instrument('MO2609-C-5000', '20260909'),
                              datetime.fromisoformat('2026-09-09T09:30:00+08:00'))
        self.assertEqual(caught.exception.status, 404)

    def test_shfe_night_day_and_break_isolation(self):
        self.scope = Scope.instrument('au2610', '20260908')
        self.insert(datetime.fromisoformat('2026-09-07T23:59:45+08:00'), code='au2610', ExchangeID='SHFE')
        midnight = self.frame('00:00:00')
        self.assertEqual(midnight['rows'][0]['quality']['quote_age_us'], 75000000)
        self.assertEqual(midnight['session']['session'], 'NIGHT')
        self.assertEqual(self.frame('09:00:00')['completeness'], 'EMPTY')
        self.insert('10:14:59', code='au2610', ExchangeID='SHFE')
        self.assertEqual(self.frame('10:30:00')['completeness'], 'EMPTY')
