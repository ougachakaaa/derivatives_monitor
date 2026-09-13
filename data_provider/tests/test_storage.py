import fcntl
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from data_provider.errors import (DataNotFoundError, DataProviderInputError,
                                  DataUnavailableError)
from data_provider.storage import Store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.store = Store(self.directory)
        self.lock = (self.directory / '.collector.lock').open('w')
        self.addCleanup(self.lock.close)

    def database(self, active=False):
        path = self.directory / '20260904.sqlite'
        db = sqlite3.connect(path)
        db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA application_id=1145914161;
            PRAGMA user_version=1;
            CREATE TABLE dataset(singleton INTEGER, trading_day TEXT, schema_version INTEGER);
            INSERT INTO dataset VALUES(1,'20260904',1);
            CREATE TABLE runs(run_id TEXT, source TEXT, started_us INTEGER, stopped_us INTEGER, last_write_us INTEGER);
            INSERT INTO runs VALUES('test-run','TEST_DOUBLE_DATA_PROVIDER',1,NULL,2);
            CREATE TABLE snapshots(id INTEGER PRIMARY KEY, run_id TEXT,sequence INTEGER,
                received_us INTEGER,snapshot_us INTEGER,TradingDay TEXT,InstrumentID TEXT,
                UpdateTime TEXT,LastPrice REAL,BidPrice1 REAL,AskPrice1 REAL,Volume INTEGER,OpenInterest REAL);
            INSERT INTO snapshots VALUES(1,'test-run',1,100,101,'20260904','IF2609','09:00:00',4000,3999,4001,10,20);
        """)
        if active:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.addCleanup(db.close)
            return db
        db.close()
        return path

    def test_read_only_summary_snapshots_and_lock(self):
        path = self.database()
        before = path.read_bytes()
        os.chmod(path, 0o444)
        os.chmod(self.directory, 0o555)
        self.addCleanup(os.chmod, self.directory, 0o755)
        self.assertEqual(self.store.days()[0]['day'], '20260904')
        self.assertEqual(self.store.summary('20260904')['rows'], 1)
        self.assertEqual(self.store.snapshots('20260904', 'IF2609', 1)['rows'][0]['Volume'], 10)
        with self.store.connect('20260904') as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute('DELETE FROM snapshots')
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(Path(str(path) + '-wal').exists())

    def test_live_wal_observes_commits_without_reader_files(self):
        db = self.database(active=True)
        os.chmod(self.directory, 0o555)
        self.addCleanup(os.chmod, self.directory, 0o755)
        before = set(self.directory.iterdir())
        db.execute("INSERT INTO snapshots SELECT 2,run_id,2,200,201,TradingDay,InstrumentID,UpdateTime,LastPrice,BidPrice1,AskPrice1,Volume,OpenInterest FROM snapshots WHERE id=1")
        db.commit()
        self.assertEqual(self.store.summary('20260904')['rows'], 2)
        self.assertEqual(set(self.directory.iterdir()), before)

    def test_failures_are_transport_neutral(self):
        with self.assertRaises(DataNotFoundError):
            self.store.summary('20260904')
        with self.assertRaises(DataProviderInputError):
            self.store.summary('../secrets')
        path = self.database()
        with sqlite3.connect(path) as db:
            db.execute("UPDATE dataset SET trading_day='20260905'")
        with self.assertRaises(DataUnavailableError):
            self.store.summary('20260904')
        self.assertFalse(hasattr(DataUnavailableError('x'), 'status'))

    def test_active_writer_requires_wal_sidecars(self):
        self.database()
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with self.assertRaisesRegex(DataUnavailableError, 'stop Collector'):
            self.store.summary('20260904')

    def test_heartbeat_distinguishes_health_and_staleness(self):
        path = self.directory / '.collector-status.json'
        heartbeat = dict(schema_version=1, run_id='a' * 32, updated_us=time.time_ns() // 1000,
                         process_state='running', connected=True, logged_in=True,
                         connections=1, disconnections=0, expected=1, subscribed=1,
                         subscription_failed=0, accepted=0, written=0,
                         last_received_us=0, last_commit_us=0)
        path.write_text(json.dumps(heartbeat))
        self.assertEqual(self.store.heartbeat()['status'], 'healthy')
        heartbeat['updated_us'] = 1
        path.write_text(json.dumps(heartbeat))
        self.assertEqual(self.store.heartbeat()['status'], 'stale')


if __name__ == '__main__':
    unittest.main()
