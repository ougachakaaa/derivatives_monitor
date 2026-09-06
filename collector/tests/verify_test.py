#!/usr/bin/env python3
"""Exercise the actual SQLite CLI against fixtures in a read-only host directory.

Only /app/data is substituted in a temporary copy of the verifier. Docker mounts
themselves are covered by docker_smoke.sh, not by these tests.
"""
import fcntl
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/verify.sh'


@unittest.skipUnless(shutil.which('sqlite3'), 'SQLite CLI required for this developer test')
class VerifyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='dm-verify-test-')
        self.root = Path(self.temp.name); self.data = self.root / 'data'; self.data.mkdir()
        self.script = self.root / 'verify.sh'
        self.script.write_text(SCRIPT.read_text().replace('/app/data', str(self.data)))
        self.path = self.data / '20260907.sqlite'
        self.lock = self.data / '.collector.lock'; self.lock.touch()

    def tearDown(self):
        self.data.chmod(0o700)
        for path in self.data.iterdir(): path.chmod(0o600)
        self.temp.cleanup()

    def create(self, extra=''):
        db = sqlite3.connect(self.path)
        db.executescript('''
            PRAGMA journal_mode=WAL;
            PRAGMA application_id=1145914161;
            PRAGMA user_version=1;
            CREATE TABLE dataset(trading_day TEXT, schema_version INTEGER);
            INSERT INTO dataset VALUES('20260907',1);
            CREATE TABLE runs(run_id TEXT PRIMARY KEY, source TEXT, started_us INTEGER, stopped_us INTEGER);
            INSERT INTO runs VALUES('test','TEST DOUBLE - verifier fixture',1,NULL);
            CREATE TABLE snapshots(TradingDay TEXT, InstrumentID TEXT, received_us INTEGER, run_id TEXT REFERENCES runs(run_id));
            INSERT INTO snapshots VALUES('20260907','IF2609',1788750000000000,'test');
        ''' + extra)
        db.commit()
        return db

    def readonly(self):
        for path in self.data.iterdir(): path.chmod(0o444)
        self.data.chmod(0o555)

    def verify(self, day='20260907'):
        return subprocess.run(['sh', str(self.script), day], capture_output=True, text=True, timeout=10)

    def test_closed_wal_without_sidecars(self):
        self.create().close()
        self.assertFalse(Path(str(self.path) + '-wal').exists())
        before = self.path.read_bytes(); self.readonly()
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('TEST DOUBLE', result.stdout)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(Path(str(self.path) + '-shm').exists())

    def test_active_writer_reads_wal_not_stale_main_file(self):
        db = self.create()
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        db.execute("INSERT INTO snapshots VALUES('20260907','WAL_ONLY',1788750001000000,'test')")
        db.commit()
        with self.lock.open('r') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.readonly(); result = self.verify()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('WAL_ONLY', result.stdout)
        self.data.chmod(0o700); db.close()

    def test_empty_wrong_day_schema_and_broken_reference(self):
        for sql in ('DELETE FROM snapshots;',
                    "UPDATE dataset SET trading_day='20260904';",
                    "UPDATE snapshots SET TradingDay='20260904';",
                    'PRAGMA user_version=99;',
                    "UPDATE snapshots SET run_id='missing';"):
            with self.subTest(sql=sql):
                self.create(sql).close()
                before = self.path.read_bytes()
                result = self.verify()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.path.read_bytes(), before)
                self.path.unlink()

    def test_missing_and_corrupt_never_create_database(self):
        self.assertNotEqual(self.verify().returncode, 0)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.verify('../bad').returncode, 2)
        self.path.write_bytes(b'not a SQLite database')
        self.assertNotEqual(self.verify().returncode, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
