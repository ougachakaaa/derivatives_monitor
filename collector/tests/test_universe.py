from datetime import datetime
import importlib.util
import json
from pathlib import Path
import subprocess
import sqlite3
from contextlib import closing
import tempfile
import unittest
from unittest.mock import Mock, patch
from data_provider.tests.runtime_fixture import create_runtime_schema

spec = importlib.util.spec_from_file_location('universe', Path(__file__).resolve().parents[1] / 'scripts/universe.py')
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)


def xml(codes, date='20260907'):
    return ('<tradeproperty>' + ''.join('<INDEX><PRODUCT_ID>' + u.contract(code)['product'] + '</PRODUCT_ID>'
        '<INSTRUMENT_ID>' + code + '</INSTRUMENT_ID><INSTRUMENT_MONTH>' + u.contract(code)['month'] + '</INSTRUMENT_MONTH>'
        '<TRADING_DAY>' + date + '</TRADING_DAY><OPEN_DATE>20260301</OPEN_DATE>'
        '<END_TRADING_DAY>20260918</END_TRADING_DAY></INDEX>' for code in codes) + '</tradeproperty>').encode()


def found(codes):
    return {'IF': dict(instruments=[u.contract(c, '20260918') for c in codes],
        verified=True, stale=False, data_date='20260907', source='test', error='')}


class UniverseTest(unittest.TestCase):
    def test_official_all_products_months_pairs_deduplicate(self):
        codes = [p + '2609' for p in u.CFFEX_PRODUCTS if p not in u.OPTIONS]
        codes += [p + month + '-' + side + '-' + strike for p in u.OPTIONS
                  for month in ('2609', '2612') for side in ('C', 'P') for strike in ('3000', '3500')]
        result, errors = u.parse_cffex(xml(codes + codes[:1]), '20260907')
        self.assertFalse(errors)
        self.assertEqual(set(result), set(u.CFFEX_PRODUCTS))
        self.assertEqual(len(result['IF']), 1)
        self.assertEqual(len(result['MO']), 8)
        wrong, _ = u.parse_cffex(xml(codes), '20260908')
        self.assertFalse(wrong)
        incomplete, _ = u.parse_cffex(xml(['IO2609-C-3000', 'IF2609']), '20260907')
        self.assertNotIn('IO', incomplete)
        self.assertIn('IF', incomplete)

    def test_sina_exact_codes_and_selector(self):
        months = u.parse_expiries(b'<li data-value="io2609">x</li><li data-value="io2612">y</li>', 'IO')
        self.assertEqual(months, ['2609', '2612'])
        body = {'result': {'status': {'code': 0}, 'data': {'up': [['1', 'io2609C4000']], 'down': [['io2609P4000']]}}}
        self.assertEqual([r['id'] for r in u.parse_sina(json.dumps(body).encode(), 'IO', '2609')], ['IO2609-C-4000', 'IO2609-P-4000'])
        body['result']['data']['down'] = []
        with self.assertRaises(ValueError): u.parse_sina(json.dumps(body).encode(), 'IO', '2609')

    def test_product_failure_preserves_old_and_removal_requires_expiry(self):
        old = u.merge({}, found(['IF2609', 'IF2612']), {}, '20260907')
        missing = u.merge(old, {}, {'IF': 'network failed'}, '20260908')
        self.assertEqual(missing['products']['IF']['instruments'], old['products']['IF']['instruments'])
        self.assertTrue(missing['products']['IF']['stale'])
        partial = u.merge(old, found(['IF2612']), {}, '20260907')
        self.assertEqual(len(partial['products']['IF']['instruments']), 2)
        self.assertFalse(partial['products']['IF']['verified'])
        expired = u.merge(old, found(['IF2612']), {}, '20260919')
        self.assertEqual(len(expired['products']['IF']['instruments']), 1)

    def test_fallback_failure_does_not_erase_official(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if 'index.xml' in url: return xml(['IF2609'])
            raise OSError('offline')
        result, errors = u.discover(fetch, '20260907')
        self.assertEqual(result['IF']['instruments'][0]['id'], 'IF2609')
        self.assertIn('IO', errors)
        self.assertEqual(sum('index.xml' in url for url in calls), 1)

    def test_atomic_publish_change_restart_and_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            run = Mock(return_value=subprocess.CompletedProcess([], 0))
            manifest = u.merge({}, found(['IF2609']), {}, '20260907')
            self.assertEqual(u.publish(directory, manifest, 'collector.service', run), (True, 1))
            run.assert_called_once_with(['systemctl', '--user', 'try-restart', '--no-block', 'collector.service'], check=True)
            run.reset_mock()
            self.assertEqual(u.publish(directory, manifest, 'collector.service', run), (False, 1))
            run.assert_not_called()
            path = directory / 'universe/current/instruments.txt'
            before = path.read_text()
            with self.assertRaises(ValueError): u.publish(directory, u.merge({}, {}, {}, '20260907'))
            self.assertEqual(path.read_text(), before)
            # TEST DOUBLE runtime snapshot: unchanged targets require no restart and reads are non-mutating.
            diagnostic = directory / 'collector-runtime.sqlite'
            with closing(sqlite3.connect(diagnostic)) as db, db:
                create_runtime_schema(db)
                run_id = 'a' * 32
                db.execute("INSERT INTO runs VALUES(?,100,NULL,NULL,'[\"IF2609\"]','TEST DOUBLE')", (run_id,))
                db.execute("INSERT INTO current_status VALUES(1,?,100,100,'running',1,1,1,1,0,NULL,0,0,NULL,NULL,1,0,0,0,0,0,0,0,0,0)", (run_id,))
                db.execute("INSERT INTO instrument_status VALUES('IF2609',?,100,'subscribed',0,0,NULL,0,0,0,0,0)", (run_id,))
            before_runtime = diagnostic.read_bytes()
            run.reset_mock()
            u.publish(directory, manifest, 'collector.service', run)
            run.assert_not_called()
            self.assertEqual(diagnostic.read_bytes(), before_runtime)
            with closing(sqlite3.connect(diagnostic)) as db, db:
                db.execute('CREATE TABLE incompatible_runtime_schema(value INTEGER)')
            u.publish(directory, manifest, 'collector.service', run)
            self.assertEqual(run.call_count, 1)
            with closing(sqlite3.connect(diagnostic)) as db, db:
                db.execute('DROP TABLE incompatible_runtime_schema')
            run.reset_mock()
            with closing(sqlite3.connect(diagnostic)) as db, db:
                db.execute("UPDATE instrument_status SET instrument_id='IC2609'")
            u.publish(directory, manifest, 'collector.service', run)
            self.assertEqual(run.call_count, 1)
            # A failed restart after publication must be retried even with unchanged text.
            (directory / 'collector-runtime.sqlite').write_text('TEST DOUBLE - unreadable runtime')
            run.reset_mock()
            u.publish(directory, manifest, 'collector.service', run)
            self.assertEqual(run.call_count, 1)
            oversized = u.merge({}, found(['IF2609']), {}, '20260907')
            oversized['products']['IF']['instruments'] = [dict(id='X' + str(i)) for i in range(10001)]
            with self.assertRaises(ValueError): u.publish(directory, oversized)
            self.assertEqual(path.read_text(), before)

    def test_startup_and_scheduled_retries(self):
        with tempfile.TemporaryDirectory() as folder:
            args = ['universe.py', '--data-dir', folder, '--date', '20260907']
            partial = found(['IF2609'])
            with patch.object(u, 'discover', return_value=(partial, {})) as fetch:
                with patch('sys.argv', args): self.assertEqual(u.main(), 2)
                with patch('sys.argv', args + ['--if-needed']): self.assertEqual(u.main(), 0)
                self.assertEqual(fetch.call_count, 1)
                with patch('sys.argv', args + ['--scheduled']): self.assertEqual(u.main(), 2)
                self.assertEqual(fetch.call_count, 2)
                status_path = Path(folder) / '.universe-status.json'
                status = json.loads(status_path.read_text()); status['complete'] = True
                status_path.write_text(json.dumps(status))
                with patch('sys.argv', args + ['--scheduled']): self.assertEqual(u.main(), 0)
                self.assertEqual(fetch.call_count, 2)
                with patch('sys.argv', ['universe.py', '--data-dir', folder, '--date', '20260908', '--if-needed']):
                    u.main()
                self.assertEqual(fetch.call_count, 3)

    def test_shfe_exact_official_codes_and_lifetime(self):
        def payload(code, commodity, **extra):
            return dict(INSTRUMENTID=code, COMMODITYID=commodity, EXCHANGEID='SHFE',
                        TRADINGDAY='20260908', OPENDATE='20260101', EXPIREDATE='20260915', **extra)
        au, ag = payload('au2610', 'au'), payload('ag2609', 'ag')
        body = dict(ContractBaseInfo=[au, ag, au, payload('cu2609', 'cu')])
        result, errors = u.parse_shfe(json.dumps(body).encode(), '20260908')
        self.assertFalse(errors)
        self.assertEqual(set(result), {'AU', 'AG'})
        self.assertEqual(result['AU'][0]['id'], 'au2610')
        self.assertEqual(result['AU'][0]['exchange'], 'SHFE')
        self.assertEqual(result['AU'][0]['listed_on'], '20260101')
        self.assertNotIn('BASISPRICE', result['AU'][0])
        for key, value in [('TRADINGDAY','20260907'),('EXCHANGEID','INE'),
                           ('INSTRUMENTID','AU2610'),('INSTRUMENTID','au2610C800'),
                           ('INSTRUMENTID','ag2610'),('EXPIREDATE','bad')]:
            bad = dict(au); bad[key] = value
            result, errors = u.parse_shfe(json.dumps(dict(ContractBaseInfo=[bad, ag])).encode(), '20260908')
            self.assertNotIn('AU', result)
            self.assertIn('AU', errors)
            self.assertIn('AG', result)
        for changes in ({'OPENDATE':'20260909'}, {'EXPIREDATE':'20260907'}):
            result, _ = u.parse_shfe(json.dumps(dict(ContractBaseInfo=[dict(au, **changes), ag])).encode(), '20260908')
            self.assertNotIn('AU', result)
        self.assertEqual(u.parse_shfe(b'{"ContractBaseInfo":[]}', '20260908')[0], {})
        with self.assertRaises(ValueError): u.parse_shfe(b'{', '20260908')
        for code in ('au2610-C-800','AG2609','cu2609','ag2613'):
            with self.assertRaises(ValueError): u.contract(code)

    def test_shfe_failure_and_partial_retention_atomic(self):
        metal = {'AU': dict(instruments=[u.contract(c, '20261015') for c in ('au2609','au2610')],
                    verified=True, stale=False, source='official', data_date='20260908')}
        old = u.merge({}, dict(found(['IF2609']), **metal), {}, '20260908')
        failed = u.merge(old, found(['IF2609']), {'SHFE':'timeout'}, '20260909')
        self.assertEqual(failed['products']['AU']['instruments'], old['products']['AU']['instruments'])
        self.assertIn('timeout', failed['products']['AU']['error'])
        self.assertFalse(failed['complete'])
        metal['AU']['instruments'] = metal['AU']['instruments'][:1]
        partial = u.merge(old, metal, {}, '20260909')
        self.assertEqual(len(partial['products']['AU']['instruments']), 2)
        self.assertTrue(partial['products']['AU']['stale'])
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            u.publish(folder, old)
            content = (folder/'universe/current/instruments.txt').read_text()
            u.publish(folder, failed)
            self.assertEqual((folder/'universe/current/instruments.txt').read_text(),content)
            self.assertIn('IF2609', content); self.assertIn('au2610', content)

    def test_shfe_discovery_calendar_date_and_unavailable_calendar(self):
        calls=[]
        def fetch(url):
            calls.append(url)
            if 'index.xml' in url: return xml(['IF2609'])
            if 'ContractBaseInfo20260908' in url:
                return json.dumps(dict(ContractBaseInfo=[dict(INSTRUMENTID=p+'2610',COMMODITYID=p,
                    TRADINGDAY='20260908',EXCHANGEID='SHFE',OPENDATE='20260101',EXPIREDATE='20261015')
                    for p in ('au','ag')])).encode()
            raise OSError('source unavailable')
        result, _ = u.discover(fetch, '20260907', '20260908')
        self.assertEqual(result['AU']['data_date'], '20260908')
        self.assertTrue(result['AU']['verified'])
        self.assertIn('IF',result)
        calls.clear(); result, errors = u.discover(fetch, '20260907', None)
        self.assertFalse(any('ContractBaseInfo' in url for url in calls))
        self.assertNotIn('AU',result); self.assertIn('calendar',errors['SHFE'])
        self.assertEqual(u.requested_dates(now=datetime.fromisoformat('2026-09-07T23:00:00+08:00')),
                         dict(CFFEX='20260907',SHFE='20260908'))
        self.assertEqual(u.requested_dates(now=datetime.fromisoformat('2026-09-04T23:00:00+08:00'))['SHFE'],'20260907')
        self.assertEqual(u.requested_dates('20260907'),dict(CFFEX='20260907',SHFE='20260907'))
        self.assertIsNone(u.requested_dates(now=datetime.fromisoformat('2027-01-04T21:00:00+08:00'))['SHFE'])
        for value in ('202691','20260230'):
            with self.assertRaises(ValueError): u.requested_dates(value)


if __name__ == '__main__': unittest.main()
