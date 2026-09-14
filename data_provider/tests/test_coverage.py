from data_provider.tests.runtime_fixture import write_runtime, update_runtime
from datetime import datetime
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
from data_provider.contract_coverage import coverage
from data_provider.errors import DataUnavailableError
from data_provider.storage import Store


class CoverageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.store = Store(self.directory)
        self.now = time.time_ns() // 1000
        self.today = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')
        self.hb = dict(schema_version=1, run_id='a'*32, updated_us=self.now, process_state='running',
            connected=True, logged_in=True, connections=1, disconnections=0, expected=3, subscribed=2,
            subscription_failed=1, accepted=1, written=1, last_received_us=self.now, last_commit_us=self.now)
        self.items = [dict(id='IF2609', subscription='subscribed', error_id=0, received=1, last_received_us=self.now),
            dict(id='IO2609-C-4000', subscription='subscribed', error_id=0, received=0, last_received_us=0),
            dict(id='IO2609-P-4000', subscription='failed', error_id=31, received=0, last_received_us=0)]
        write_runtime(self.directory, self.hb, self.items)
        self.write('universe/current/manifest.json', dict(schema_version=1, complete=False, requested_day=self.today,
            updated_us=self.now, products={p: dict(instruments=[dict(id=s['id'], month='2609') for s in self.items if s['id'].startswith(p)],
                discovered_ids=[s['id'] for s in self.items if s['id'].startswith(p)], verified=True, stale=False,
                data_date=self.today, source='http://www.cffex.com.cn/', error='') for p in ('IF', 'IO')}))

    def write(self, path, data):
        path = self.directory / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def get(self):
        return coverage(self.store)

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
        update_runtime(self.directory, "UPDATE instrument_status SET run_id=?", ('b'*32,))
        with self.assertRaises(DataUnavailableError):
            self.get()
        self.hb['updated_us'] = 1
        write_runtime(self.directory, self.hb, self.items)
        self.assertFalse(self.get()['complete'])

    def test_invalid_and_missing_diagnostics(self):
        (self.directory / 'collector-runtime.sqlite').write_text('{')
        with self.assertRaises(DataUnavailableError):
            self.get()
        (self.directory / 'collector-runtime.sqlite').unlink()
        self.assertFalse(self.get()['collector_current'])

    def test_shfe_night_target_date_and_market_health_separation(self):
        now = datetime.fromisoformat('2026-09-07T23:00:00+08:00')
        extra = [dict(id='au2610', subscription='subscribed', error_id=0, received=0, last_received_us=0),
                 dict(id='ag2610', subscription='failed', error_id=31, received=0, last_received_us=0)]
        self.hb['expected'] = 5
        write_runtime(self.directory, self.hb, self.items + extra)
        manifest=json.loads((self.directory/'universe/current/manifest.json').read_text())
        for product,code in [('AU','au2610'),('AG','ag2610')]:
            manifest['products'][product]=dict(exchange='SHFE',requested_day='20260908',data_date='20260908',
                instruments=[dict(id=code,month='2610')],discovered_ids=[code],verified=True,stale=False,source='https://www.shfe.com.cn/')
        self.write('universe/current/manifest.json',manifest)
        with patch('data_provider.contract_coverage.datetime') as clock:
            clock.now.return_value=now
            result=self.get()
        au=next(r for r in result['groups'] if r['product']=='AU')
        ag=next(r for r in result['groups'] if r['product']=='AG')
        self.assertEqual((au['exchange'],au['target'],au['no_push']),('SHFE',1,1))
        self.assertEqual(ag['failed'],1)
        self.assertTrue(au['verified']);self.assertFalse(au['stale'])
        self.assertEqual(result['requested_days']['SHFE'],'20260908')
        self.assertFalse(result['complete'])
        self.assertEqual(next(r for r in result['instruments'] if r['id']=='au2610')['subscription'],'subscribed')
        result=coverage(self.store, self.directory/'missing')
        au=next(r for r in result['groups'] if r['product']=='AU')
        self.assertFalse(au['verified']);self.assertTrue(au['stale'])
        self.assertEqual(au['subscribed'],1) # Calendar failure cannot erase CTP facts.


if __name__ == '__main__': unittest.main()
