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
