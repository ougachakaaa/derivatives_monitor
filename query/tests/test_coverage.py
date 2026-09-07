from datetime import datetime
import json
from pathlib import Path
import tempfile
import time
import unittest
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient
from app import create_app


class CoverageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.client = TestClient(create_app(self.directory))
        self.addCleanup(self.client.close)
        self.now = time.time_ns() // 1000
        self.today = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')
        self.hb = dict(schema_version=1, run_id='a'*32, updated_us=self.now, process_state='running',
            connected=True, logged_in=True, connections=1, disconnections=0, expected=3, subscribed=2,
            subscription_failed=1, accepted=1, written=1, last_received_us=self.now, last_commit_us=self.now)
        self.items = [dict(id='IF2609', subscription='subscribed', error_id=0, received=1, last_received_us=self.now),
            dict(id='IO2609-C-4000', subscription='subscribed', error_id=0, received=0, last_received_us=0),
            dict(id='IO2609-P-4000', subscription='failed', error_id=31, received=0, last_received_us=0)]
        self.write('.collector-status.json', self.hb)
        self.write('.collector-coverage.json', dict(schema_version=1, run_id='a'*32, updated_us=self.now, instruments=self.items))
        self.write('universe/current/manifest.json', dict(schema_version=1, complete=False, requested_day=self.today,
            updated_us=self.now, products={p: dict(instruments=[dict(id=s['id'], month='2609') for s in self.items if s['id'].startswith(p)],
                discovered_ids=[s['id'] for s in self.items if s['id'].startswith(p)], verified=True, stale=False,
                data_date=self.today, source='http://www.cffex.com.cn/', error='') for p in ('IF', 'IO')}))

    def write(self, path, data):
        path = self.directory / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def get(self):
        response = self.client.get('/api/coverage')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_counts_failure_no_push_and_read_only(self):
        before = {str(p): p.read_bytes() for p in self.directory.rglob('*') if p.is_file()}
        result = self.get()
        row = next(g for g in result['groups'] if g['product'] == 'IO')
        self.assertEqual((row['discovered'], row['target'], row['subscribed'], row['failed'], row['no_push']), (2,2,1,1,1))
        self.assertFalse(result['complete'])
        self.assertTrue(result['collector_current'])
        self.assertEqual(next(g for g in result['groups'] if g['product'] == 'TL')['listed'], 0)
        after = {str(p): p.read_bytes() for p in self.directory.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_old_session_and_stale_heartbeat_clear_live_counts(self):
        self.write('.collector-coverage.json', dict(schema_version=1, run_id='b'*32, updated_us=self.now, instruments=self.items))
        self.assertFalse(self.get()['collector_current'])
        self.assertTrue(all(g['subscribed'] is None for g in self.get()['groups']))
        self.hb['updated_us'] = 1
        self.write('.collector-status.json', self.hb)
        self.assertFalse(self.get()['complete'])

    def test_invalid_missing_and_parameters(self):
        self.assertEqual(self.client.get('/api/coverage?day=20260907').status_code, 400)
        (self.directory / '.collector-coverage.json').write_text('{')
        self.assertEqual(self.client.get('/api/coverage').status_code, 503)
        (self.directory / '.collector-coverage.json').unlink()
        self.assertFalse(self.get()['collector_current'])


if __name__ == '__main__': unittest.main()
