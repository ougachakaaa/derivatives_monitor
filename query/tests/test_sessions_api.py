import json
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
from query.app import create_app


class SessionsApiTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        self.client=TestClient(create_app(self.directory/'no-raw-data'))
        self.addCleanup(self.client.close)

    def test_independent_multimarket_and_filters(self):
        before=list(self.directory.rglob('*'))
        r=self.client.get('/api/sessions',params={'at':'2026-09-07T21:30:00+08:00'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.headers['cache-control'],'no-store')
        payload=r.json();self.assertEqual(payload['schema_version'],1)
        rows=payload['markets'];self.assertEqual(len(rows),13)
        self.assertTrue(all('session_state' in row for row in rows))
        self.assertEqual(next(row for row in rows if row['product']=='AU')['trading_day'],'20260908')
        self.assertEqual(next(row for row in rows if row['product']=='IF')['session_state'],'CLOSED')
        for params, count in [({'exchange':'SHFE'},2),({'exchange':'shfe','product':'ag'},1),({'exchange':'CFFEX'},11)]:
            params['at']='2026-09-07T21:30:00+08:00'
            self.assertEqual(len(self.client.get('/api/sessions',params=params).json()['markets']),count)
        self.assertEqual(before,list(self.directory.rglob('*')))

    def test_parameters_and_unknown(self):
        for params in ({'exchange':'DCE'},{'product':'AU'},{'exchange':'CFFEX','product':'AU'},
                       {'at':'2026-09-07T21:00:00'},{'at':'wrong'},{'extra':'x'}):
            self.assertEqual(self.client.get('/api/sessions',params=params).status_code,400)
        self.assertEqual(self.client.get('/api/sessions?exchange=SHFE&exchange=CFFEX').status_code,400)
        r=self.client.get('/api/sessions',params={'at':'2027-01-04T10:00:00+08:00'})
        self.assertEqual(r.status_code,200)
        self.assertTrue(all(row['session_state']=='UNKNOWN' for row in r.json()['markets']))
        with TestClient(create_app(self.directory, self.directory/'missing')) as client:
            r=client.get('/api/sessions',params={'at':'2026-09-07T10:00:00+08:00'})
            self.assertTrue(all(row['session_state']=='UNKNOWN' for row in r.json()['markets']))
