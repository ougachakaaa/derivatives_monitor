from data_provider.tests.runtime_fixture import write_runtime, update_runtime
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from fastapi.testclient import TestClient
from query.app import create_app


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.client = TestClient(create_app(self.directory))
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.client.close)
        self.lock = open(self.directory / ".collector.lock", "w")
        self.addCleanup(self.lock.close)

    def database(self, active=False):
        path = self.directory / "20260904.sqlite"
        db = sqlite3.connect(path)
        db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA application_id=1145914161;
            PRAGMA user_version=1;
            CREATE TABLE dataset(singleton INTEGER, trading_day TEXT, schema_version INTEGER);
            INSERT INTO dataset VALUES(1,'20260904',1);
            CREATE TABLE runs(run_id TEXT, source TEXT, started_us INTEGER, stopped_us INTEGER, last_write_us INTEGER);
            INSERT INTO runs VALUES('test-run','TEST_DOUBLE_QUERY',1,NULL,2);
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

    def test_offline_read_only_and_routes(self):
        path = self.database()
        before = path.read_bytes()
        os.chmod(path, 0o444)
        os.chmod(self.directory, 0o555)
        self.addCleanup(os.chmod, self.directory, 0o755)
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 404)  # Python has no frontend
        self.assertEqual(self.client.get("/api/days").json()["days"][0]["day"], "20260904")
        summary = self.client.get("/api/summary?day=20260904").json()
        self.assertEqual(summary["rows"], 1)
        self.assertEqual(summary["runs"][0]["source"], "TEST_DOUBLE_QUERY")
        self.assertEqual(self.client.get("/api/snapshots?day=20260904&instrument=IF2609&limit=1").json()["rows"][0]["Volume"], 10)
        self.assertEqual(self.client.get("/api/snapshots?day=20260904&instrument=missing").json()["rows"], [])
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(Path(str(path) + "-wal").exists())

    def test_live_wal_latest_commits_and_no_reader_files(self):
        db = self.database(active=True)
        os.chmod(self.directory, 0o555)
        self.addCleanup(os.chmod, self.directory, 0o755)
        before = set(self.directory.iterdir())
        self.assertEqual(self.client.get("/api/summary?day=20260904").json()["rows"], 1)
        db.execute("INSERT INTO snapshots SELECT 2,run_id,2,200,201,TradingDay,InstrumentID,UpdateTime,LastPrice,BidPrice1,AskPrice1,Volume,OpenInterest FROM snapshots WHERE id=1")
        db.commit()
        self.assertEqual(self.client.get("/api/summary?day=20260904").json()["rows"], 2)
        self.assertEqual(self.client.get("/api/snapshots?day=20260904&limit=1").json()["rows"][0]["id"], 2)
        self.assertEqual(set(self.directory.iterdir()), before)

    def test_historical_without_sidecars_while_writer_active(self):
        self.database()
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        response = self.client.get("/api/summary?day=20260904")
        self.assertEqual(response.status_code, 503)
        self.assertIn("stop Collector", response.json()["error"])

    def test_bad_inputs_empty_and_missing(self):
        self.assertEqual(self.client.get("/api/days").json(), {"days": []})
        self.assertEqual(self.client.get("/api/summary?day=20260904").status_code, 404)
        for query in ("day=../secrets", "day=20260230", "day=20260904&limit=201",
                      "day=20260904&limit=0", "day=20260904&limit=abc", "day=20260904&instrument=';--",
                      "day=20260904&day=20260905", "day=20260904&sql=DELETE", ""):
            self.assertEqual(self.client.get("/api/snapshots?" + query).status_code, 400, query)
        self.assertEqual(self.client.post("/api/days").status_code, 405)
        self.assertEqual(list(self.directory.glob("*.sqlite")), [])

    def test_schema_corruption_and_symlink(self):
        path = self.database()
        with sqlite3.connect(path) as db:
            db.execute("UPDATE dataset SET trading_day='20260905'")
        db.close()
        self.assertEqual(self.client.get("/api/summary?day=20260904").status_code, 503)
        path.write_bytes(b"corrupt")
        self.assertEqual(self.client.get("/api/summary?day=20260904").status_code, 503)
        path.unlink()
        path.symlink_to("/etc/passwd")
        self.assertEqual(self.client.get("/api/summary?day=20260904").status_code, 503)
        self.assertEqual(self.client.get("/api/days").json(), {"days": []})

    def test_heartbeat_no_quotes_stale_stop_and_malformed(self):
        path = self.directory / "collector-runtime.sqlite"
        self.assertEqual(self.client.get("/api/health").json()["collector"]["status"], "unknown")
        heartbeat = dict(schema_version=1, run_id="a" * 32, updated_us=time.time_ns() // 1000,
                         process_state="running", connected=True, logged_in=True,
                         connections=1, disconnections=0, expected=1, subscribed=1,
                         subscription_failed=0, accepted=0, written=0,last_received_us=0,last_commit_us=0)
        def read(**changes):
            write_runtime(self.directory, heartbeat | changes)
            return self.client.get("/api/health").json()["collector"]
        self.assertEqual(read()["status"], "running")
        self.assertTrue(read()["process_alive"])
        self.assertEqual(read(logged_in=False)["status"], "running")
        self.assertFalse(read(process_state="stopped")["process_alive"])
        self.assertEqual(read(updated_us=1)["status"], "stale")
        self.assertEqual(read(updated_us=time.time_ns() // 1000 + 20_000_000)["status"], "stale")
        read()
        update_runtime(self.directory, "UPDATE current_status SET connected='yes'")
        self.assertEqual(self.client.get('/api/health').json()['collector']['status'], 'unknown')
        path.write_text("invalid")
        self.assertFalse(self.client.get("/api/health").json()["collector"]["process_alive"])

    def test_backend_health_independent_of_storage(self):
        with TestClient(create_app(self.directory / "missing")) as client:
            self.assertEqual(client.get("/healthz").status_code, 200)
            self.assertFalse(client.get("/api/health").json()["data"]["readable"])
            self.assertEqual(client.get("/api/days").status_code, 503)

    def test_empty_valid_database(self):
        path = self.database()
        with sqlite3.connect(path) as db:
            db.execute("DELETE FROM snapshots")
        db.close()
        self.assertEqual(self.client.get("/api/summary?day=20260904").json()["rows"], 0)


if __name__ == "__main__":
    unittest.main()
