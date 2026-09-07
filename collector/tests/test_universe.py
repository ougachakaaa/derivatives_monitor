import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

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
        codes = [p + '2609' for p in u.PRODUCTS if p not in u.OPTIONS]
        codes += [p + month + '-' + side + '-' + strike for p in u.OPTIONS
                  for month in ('2609', '2612') for side in ('C', 'P') for strike in ('3000', '3500')]
        result, errors = u.parse_cffex(xml(codes + codes[:1]), '20260907')
        self.assertFalse(errors)
        self.assertEqual(set(result), set(u.PRODUCTS))
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
            self.assertEqual(run.call_args_list[-1].args[0], ['systemctl', '--user', 'restart', '--no-block', 'collector.service'])
            run.reset_mock()
            self.assertEqual(u.publish(directory, manifest, 'collector.service', run), (False, 1))
            run.assert_not_called()
            path = directory / 'universe/current/instruments.txt'
            before = path.read_text()
            with self.assertRaises(ValueError): u.publish(directory, u.merge({}, {}, {}, '20260907'))
            self.assertEqual(path.read_text(), before)
            # A failed restart after publication must be retried even with unchanged text.
            (directory / '.collector-coverage.json').write_text(json.dumps({'instruments': [{'id': 'IC2609'}]}))
            run.reset_mock()
            u.publish(directory, manifest, 'collector.service', run)
            self.assertEqual(run.call_count, 2)
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


if __name__ == '__main__': unittest.main()
