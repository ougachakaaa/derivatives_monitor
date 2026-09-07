from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from market_calendar import Calendar, CalendarError, DEFAULT_DIRECTORY, PRODUCTS, sessions


class CalendarTest(unittest.TestCase):
    def result(self, at, exchange='SHFE', product='AU'):
        return sessions(at, exchange, product)['markets'][0]

    def test_metal_day_boundaries(self):
        for stamp, state, phase in [('08:54:59','CLOSED',None),('08:55:00','OPEN','AUCTION'),
                ('09:00:00','OPEN','CONTINUOUS'),('10:14:59','OPEN','CONTINUOUS'),
                ('10:15:00','BREAK',None),('10:30:00','OPEN','CONTINUOUS'),
                ('11:30:00','BREAK',None),('13:30:00','OPEN','CONTINUOUS'),('15:00:00','CLOSED',None)]:
            with self.subTest(stamp=stamp):
                r=self.result('2026-09-08T'+stamp+'+08:00')
                self.assertEqual((r['market_state'],r['phase']),(state,phase))
                self.assertEqual(r['is_continuous'],phase=='CONTINUOUS')
                self.assertEqual(r['quote_expected'],phase=='CONTINUOUS')

    def test_night_midnight_and_day_share_logical_day(self):
        for product in ('AU','AG'):
            for at in ('2026-09-07T21:00:00','2026-09-07T23:59:59','2026-09-08T00:00:00',
                       '2026-09-08T02:29:59','2026-09-08T09:00:00','2026-09-08T14:59:59'):
                r=self.result(at+'+08:00',product=product)
                self.assertEqual(r['trading_day'],'20260908')
                self.assertTrue(r['is_continuous'])
            r=self.result('2026-09-08T02:30:00+08:00',product=product)
            self.assertEqual(r['market_state'],'CLOSED')
            self.assertEqual(r['trading_day'],'20260908')
            self.assertEqual(r['latest_session']['session'],'NIGHT')
            self.assertEqual(r['next_session']['start'],'2026-09-08T09:00:00+08:00')
        self.assertEqual(self.result('2026-09-07T20:55:00+08:00')['phase'],'AUCTION')
        self.assertEqual(self.result('2026-09-07T20:54:59+08:00')['market_state'],'CLOSED')

    def test_friday_night_is_monday_sunday_has_no_night(self):
        for at in ('2026-09-04T21:00:00','2026-09-05T01:00:00'):
            r=self.result(at+'+08:00');self.assertEqual(r['market_state'],'OPEN')
            self.assertEqual(r['trading_day'],'20260907')
        for at in ('2026-09-05T03:00:00','2026-09-06T21:00:00'):
            r=self.result(at+'+08:00');self.assertEqual(r['market_state'],'CLOSED')
            self.assertEqual(r['trading_day'],'20260907')
            self.assertEqual(r['latest_session']['trading_day'],'20260907')

    def test_holidays_cancellations_makeup_weekends(self):
        for at in ('2026-01-01T10:00:00','2026-01-04T10:00:00','2026-02-14T10:00:00',
                   '2026-02-16T10:00:00','2026-02-28T10:00:00','2026-05-09T10:00:00',
                   '2026-09-20T10:00:00','2026-10-10T10:00:00'):
            for exchange,product in [('SHFE','AG'),('CFFEX','IF')]:
                self.assertEqual(self.result(at+'+08:00',exchange,product)['market_state'],'CLOSED')
        for at in ('2026-02-13T21:00:00','2026-04-03T21:00:00','2026-04-30T21:00:00',
                   '2026-06-18T21:00:00','2026-09-24T21:00:00','2026-09-30T21:00:00',
                   '2026-10-01T01:00:00','2026-10-07T21:00:00'):
            self.assertEqual(self.result(at+'+08:00')['market_state'],'CLOSED')
        r=self.result('2026-09-24T22:00:00+08:00')
        self.assertEqual(r['trading_day'],'20260928')
        self.assertEqual(r['next_session']['start'],'2026-09-28T09:00:00+08:00')
        for at in ('2026-01-05T09:00:00','2026-02-24T09:00:00','2026-10-08T09:00:00'):
            self.assertEqual(self.result(at+'+08:00')['market_state'],'OPEN')

    def test_product_profiles_and_auction(self):
        for p in ('IF','IH','IC','IM'):
            self.assertEqual(self.result('2026-09-07T15:00:00+08:00','CFFEX',p)['market_state'],'CLOSED')
        for p in ('TS','TF','T','TL'):
            self.assertTrue(self.result('2026-09-07T15:14:59+08:00','CFFEX',p)['is_continuous'])
            self.assertEqual(self.result('2026-09-07T15:15:00+08:00','CFFEX',p)['market_state'],'CLOSED')
        for p in ('IO','HO','MO'):
            r=self.result('2026-09-07T14:57:00+08:00','CFFEX',p)
            self.assertEqual((r['market_state'],r['phase'],r['is_continuous']),('OPEN','AUCTION',False))
        rows=sessions('2026-09-07T21:30:00+08:00')['markets']
        self.assertEqual(len(rows),13)
        self.assertTrue(all(r['market_state']==('OPEN' if r['exchange']=='SHFE' else 'CLOSED') for r in rows))

    def test_timezone_validation_and_latest(self):
        self.assertEqual(self.result('2026-09-07T16:00:00Z')['as_of'],'2026-09-08T00:00:00+08:00')
        r=self.result('2026-09-08T10:20:00+08:00')
        self.assertEqual(r['latest_session']['start'],'2026-09-08T09:00:00+08:00')
        self.assertEqual(r['next_session']['start'],'2026-09-08T10:30:00+08:00')
        for value in ('2026-09-07','2026-09-07T10:00:00','broken'):
            with self.assertRaises(ValueError): sessions(value)
        with self.assertRaises(ValueError): sessions(datetime(2026,9,7))
        for kwargs in ({'product':'AU'},{'exchange':'DCE'},{'exchange':'SHFE','product':'CU'}):
            with self.assertRaises(ValueError): sessions('2026-09-07T10:00:00Z',**kwargs)

    def test_unknown_year_file_and_validation(self):
        for at in ('2027-01-01T10:00:00+08:00','2026-12-31T21:00:00+08:00'):
            r=self.result(at)
            self.assertEqual(r['market_state'],'UNKNOWN');self.assertIsNone(r['trading_day'])
            self.assertIsNone(r['quote_expected'])
        with tempfile.TemporaryDirectory() as folder:
            r=sessions('2026-09-07T21:00:00+08:00',directory=folder)['markets']
            self.assertTrue(all(row['market_state']=='UNKNOWN' for row in r))
            path=Path(folder)/'2026.json';path.write_text('{')
            with self.assertRaises(CalendarError): Calendar(path)
            data=json.loads((DEFAULT_DIRECTORY/'2026.json').read_text())
            data['exchanges']['SHFE']['days'][1]['night_start']='20260104'
            path.write_text(json.dumps(data))
            with self.assertRaises(CalendarError): Calendar(path)
            data['exchanges']['SHFE']['days'][1]['night_start']=None
            data['exchanges']['CFFEX']['days'].reverse();path.write_text(json.dumps(data))
            with self.assertRaises(CalendarError): Calendar(path)

    def test_independent_cli(self):
        module=DEFAULT_DIRECTORY.parent/'market_calendar.py'
        result=subprocess.run([sys.executable,'-I',str(module),'--validate',str(DEFAULT_DIRECTORY/'2026.json')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        result=subprocess.run([sys.executable,'-I',str(module),'--exchange','SHFE','--product','AU','--at','2026-09-07T21:00:00+08:00'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['markets'][0]['trading_day'],'20260908')
