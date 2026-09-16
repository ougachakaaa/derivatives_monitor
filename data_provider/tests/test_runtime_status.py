"""TEST DOUBLE: runtime SQLite read invariants, no production state."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from data_provider.errors import DataUnavailableError
from data_provider.runtime_status import diagnostic, read_runtime_status
from data_provider.tests.runtime_fixture import write_runtime, update_runtime


class RuntimeStatusTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='test-double-runtime-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def test_missing_and_legacy_json_do_not_create_or_prove_liveness(self):
        (self.directory / '.collector-status.json').write_text('{"process_state":"running"}')
        (self.directory / '.collector-coverage.json').write_text('{}')
        before = sorted(p.name for p in self.directory.iterdir())
        self.assertIsNone(read_runtime_status(self.directory))
        self.assertFalse(diagnostic(None)['process_alive'])
        self.assertEqual(before, sorted(p.name for p in self.directory.iterdir()))

    def test_current_snapshot_is_read_only_and_health_is_not_evaluated(self):
        path = write_runtime(self.directory, {'logged_in': False, 'connected': False})
        before = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        snapshot = read_runtime_status(self.directory)
        self.assertIsNone(snapshot[0]['trading_day'])
        self.assertIsNone(snapshot[0]['last_tick_received_us'])
        now = snapshot[0]['heartbeat_us']
        self.assertEqual(diagnostic(snapshot, now)['status'], 'running')
        self.assertTrue(diagnostic(snapshot, now)['process_alive'])
        self.assertEqual(diagnostic(snapshot, now + 10_000_001)['status'], 'stale')
        self.assertEqual(diagnostic(snapshot, now - 1)['status'], 'stale')
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.directory.iterdir()})
        path.unlink()
        path.symlink_to(self.directory / 'missing')
        with self.assertRaises(DataUnavailableError):
            read_runtime_status(self.directory)

    def test_incompatible_or_inconsistent_rows_fail_closed(self):
        cases = [
            'ALTER TABLE runtime_snapshots ADD COLUMN incompatible INTEGER',
            "UPDATE current_status SET trading_day='20260230'",
            'UPDATE current_status SET subscribed_count=2',
            "UPDATE instrument_status SET run_id='wrong'",
            'UPDATE instrument_status SET updated_us=1',
            'UPDATE current_status SET ticks_received=1',
            "UPDATE current_status SET connected='true'",
            'DELETE FROM instrument_status',
            'DELETE FROM current_status',
            "UPDATE current_status SET process_state='healthy'",
        ]
        for sql in cases:
            with self.subTest(sql=sql):
                (self.directory / 'collector-runtime.sqlite').unlink(missing_ok=True)
                write_runtime(self.directory)
                update_runtime(self.directory, sql)
                with self.assertRaises(DataUnavailableError):
                    read_runtime_status(self.directory)

    def test_user_version_is_not_a_runtime_schema_version(self):
        write_runtime(self.directory)
        update_runtime(self.directory, 'PRAGMA user_version=99')
        self.assertEqual(read_runtime_status(self.directory)[0]['run_id'], 'a' * 32)

    def test_writer_transaction_is_invisible_until_committed_and_lock_is_bounded(self):
        path = write_runtime(self.directory)
        with closing(sqlite3.connect(path)) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE current_status SET process_state='starting'")
            self.assertEqual(read_runtime_status(self.directory)[0]['process_state'], 'running')
            db.commit()
            self.assertEqual(read_runtime_status(self.directory)[0]['process_state'], 'starting')
            db.execute('BEGIN EXCLUSIVE')
            started = time.monotonic()
            with self.assertRaises(DataUnavailableError):
                read_runtime_status(self.directory)
            self.assertLess(time.monotonic() - started, 1)
            db.rollback()
        self.assertEqual(read_runtime_status(self.directory)[0]['process_state'], 'starting')


if __name__ == '__main__':
    unittest.main()
