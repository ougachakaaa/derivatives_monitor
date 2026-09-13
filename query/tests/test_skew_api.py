"""TEST DOUBLE quotes/references; real SQLite, Market Frame, Analytics and HTTP."""
from datetime import timedelta
import fcntl
import json
import math
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from query.app import create_app
from query.market_calendar import Calendar, DEFAULT_DIRECTORY, parse_at
from query.market_frame import MarketFrameReader, OBSERVATION_COLUMNS, micros
from query.skew_references import ReferenceRepository, ReferenceUnavailable, digest, load_package
from query.storage import Store
from query.tests.test_analytics import CHAIN, reference

DAY = '20260916'
MONTH = '2610'
START = parse_at('2026-09-16T09:30:00+08:00')


def write_package(root):
    bundle = reference()
    bundle.pop('bundle_sha256')
    rows = [dict(id=r['instrument'], month=MONTH, side=r['side'], strike=r['strike'],
                 expiry='20261016') for r in CHAIN['rows']]
    universe = {'schema_version': 1, 'requested_day': DAY, 'products': {'MO': {
        'exchange': 'CFFEX', 'requested_day': DAY, 'verified': True, 'stale': False,
        'data_date': DAY, 'source': 'fixture://TEST-DOUBLE', 'instruments': rows}}}
    content = {'calendar.json': (DEFAULT_DIRECTORY / '2026.json').read_bytes(),
               'universe.json': json.dumps(universe).encode()}
    bundle['calendar']['version'] = json.loads(content['calendar.json'])['version']
    for name in ('universe', 'calendar'):
        bundle[name]['sha256'] = digest(content[name + '.json'])
    content['bundle.json'] = json.dumps(bundle).encode()
    content['manifest.json'] = json.dumps({'schema_version': 1, 'bundle_id': bundle['bundle_id'],
        'sha256': {name: digest(value) for name, value in content.items()}}).encode()
    package = root / DAY / bundle['bundle_id']
    package.mkdir(parents=True)
    for name, value in content.items():
        (package / name).write_bytes(value)
    (root / DAY / (MONTH + '.json')).write_text(json.dumps({'bundle_id': bundle['bundle_id']}))
    return package


def make_database(root):
    db = sqlite3.connect(root / (DAY + '.sqlite'), check_same_thread=False)
    db.executescript('''PRAGMA application_id=1145914161; PRAGMA user_version=1;
        CREATE TABLE dataset(singleton INTEGER PRIMARY KEY, trading_day TEXT, schema_version INTEGER);
        INSERT INTO dataset VALUES(1,'20260916',1);''')
    definitions = []
    for name in OBSERVATION_COLUMNS:
        if name == 'id':
            definitions.append('id INTEGER PRIMARY KEY')
        elif name in ('sequence', 'received_us', 'snapshot_us', 'UpdateMillisec', 'BidVolume1', 'AskVolume1'):
            definitions.append(name + ' INTEGER')
        elif name in ('TradingDay', 'ExchangeID', 'InstrumentID', 'ExchangeInstID', 'ActionDay', 'UpdateTime', 'run_id'):
            definitions.append(name + ' TEXT')
        else:
            definitions.append(name + ' REAL')
    db.execute('CREATE TABLE snapshots(' + ','.join(definitions) + ')')
    db.execute('CREATE INDEX snapshots_instrument_time ON snapshots(InstrumentID,received_us,id)')
    db.commit()
    (root / '.collector.lock').touch()
    return db


def append_chain(db, end, *, invalid=False):
    for row in CHAIN['rows']:
        received = micros(end) - row['age_us']
        values = dict(run_id='TEST_DOUBLE_RUN', sequence=row['id'], received_us=received,
                      snapshot_us=micros(end) + 1_000_000, TradingDay=DAY, ExchangeID='CFFEX',
                      InstrumentID=row['instrument'], ActionDay=DAY, UpdateTime='09:30:40',
                      UpdateMillisec=0, BidPrice1=row['bid'], AskPrice1=row['ask'],
                      BidVolume1=0 if invalid else row['bid_volume'], AskVolume1=row['ask_volume'])
        db.execute('INSERT INTO snapshots(' + ','.join(values) + ') VALUES('
                   + ','.join('?' for _ in values) + ')', tuple(values.values()))
    db.commit()


class SkewApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.refs = self.root / 'references'
        self.package = write_package(self.refs)
        self.repository = ReferenceRepository(self.refs, allow_synthetic=True)
        self.db = make_database(self.root)
        self.addCleanup(self.db.close)
        append_chain(self.db, START + timedelta(minutes=1))
        self.app = create_app(self.root, target_month=MONTH, reference_repository=self.repository)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def get(self, mode='latest', **params):
        params.setdefault('at', (START + timedelta(minutes=1)).isoformat())
        if mode != 'latest':
            params.setdefault('day', DAY)
        if mode == 'minute':
            params.setdefault('minute', START.isoformat())
        response = self.client.get('/api/skew/' + mode, params=params)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        return response.json()

    def test_complete_vertical_slice_and_public_provenance(self):
        before = (self.root / (DAY + '.sqlite')).read_bytes()
        result = self.get()
        self.assertEqual(result['status'], 'OK', result['reasons'])
        self.assertFalse(result['historical'])
        self.assertTrue(result['current_usable'])
        self.assertEqual(result['minute'], START.isoformat())
        # Far wings in the frozen fixture have zero bids; required nodes are valid.
        self.assertEqual(result['quality']['completeness'], 'PARTIAL')
        self.assertEqual(result['reasons'], ['PARTIAL_INPUT'])
        self.assertEqual(result['reference']['source_kind'], 'SYNTHETIC')
        self.assertEqual(result['scope'], {'exchange': 'CFFEX', 'product': 'MO', 'month': MONTH, 'trading_day': DAY})
        self.assertEqual(result['reference']['sha256'], digest((self.package / 'bundle.json').read_bytes()))
        for row in result['provenance']:
            self.assertEqual(row['run_id'], 'TEST_DOUBLE_RUN')
            self.assertEqual(row['source_time']['trading_day'], DAY)
            self.assertGreater(row['snapshot_us'], micros(START + timedelta(minutes=1)))
        wire = json.dumps(result, allow_nan=False)
        for private in ('BidPrice1', 'AskPrice1', 'InstrumentID', 'SELECT ', 'snapshots', str(self.root)):
            self.assertNotIn(private, wire)
        historical = self.get('minute', at='2026-09-17T12:00:00+08:00')
        self.assertEqual(historical['skew_25d_vp'], result['skew_25d_vp'])
        self.assertTrue(historical['historical'])
        self.assertFalse(historical['current_usable'])
        self.assertEqual((self.root / (DAY + '.sqlite')).read_bytes(), before)

    def test_current_staleness_does_not_erase_valid_minute(self):
        result = self.get(at='2026-09-16T09:31:29+08:00')
        self.assertEqual(result['status'], 'OK')
        self.assertFalse(result['current_usable'])
        self.assertFalse(result['historical'])
        later = self.get(at='2026-09-16T09:32:00+08:00')
        self.assertEqual(later['status'], 'UNAVAILABLE')
        self.assertIsNone(later['skew_25d_vp'])
        self.assertEqual(later['minute'], '2026-09-16T09:31:00+08:00')
        self.assertIn('STALE_QUOTE', later['reasons'])

    def test_http_against_frozen_oracle_using_black_time_scaling(self):
        # Independent identity: keep D and sigma*sqrt(T) constant when moving the
        # frozen 15:00 synthetic vector to a Calendar continuous minute.
        bundle = json.loads((self.package / 'bundle.json').read_bytes())
        original_seconds = 30 * 86400
        actual_seconds = (parse_at(bundle['expiry_at']) - START - timedelta(minutes=1)).total_seconds()
        scale = math.sqrt(original_seconds / actual_seconds)
        bundle['rate']['decimal'] *= original_seconds / actual_seconds
        bundle['rate']['percent'] = 100 * bundle['rate']['decimal']
        raw = json.dumps(bundle).encode()
        (self.package / 'bundle.json').write_bytes(raw)
        manifest = json.loads((self.package / 'manifest.json').read_bytes())
        manifest['sha256']['bundle.json'] = digest(raw)
        (self.package / 'manifest.json').write_text(json.dumps(manifest))
        result = self.get()
        self.assertEqual(result['status'], 'OK')
        self.assertLessEqual(abs(result['forward']['value'] - CHAIN['expected_forward']), 1e-6)
        self.assertLessEqual(abs(result['skew_25d_vp'] - CHAIN['expected_skew_vp'] * scale), 2e-5)

    def test_first_minute_lunch_auction_and_next_day(self):
        for value in ('09:30:00', '09:30:59', '13:00:30'):
            result = self.get(at='2026-09-16T' + value + '+08:00')
            self.assertEqual(result['reasons'], ['WAITING_FOR_MINUTE'])
            self.assertFalse(result['current_usable'])
        for value, expected in (('12:00:00', '11:29'), ('14:58:00', '14:56'), ('16:00:00', '14:56')):
            result = self.get(at='2026-09-16T' + value + '+08:00')
            self.assertTrue(result['historical'])
            self.assertFalse(result['current_usable'])
            self.assertEqual(result['minute'], '2026-09-16T' + expected + ':00+08:00')
            self.assertEqual(result['scope']['trading_day'], DAY)
        result = self.get(at='2026-09-17T09:26:00+08:00')
        self.assertEqual(result['scope']['trading_day'], DAY)
        self.assertEqual(result['market_session']['trading_day'], '20260917')

    def test_history_unsupported_unsealed_and_bad_parameters(self):
        for minute in ('09:25', '11:30', '12:30', '14:57'):
            result = self.get('minute', minute='2026-09-16T' + minute + ':00+08:00',
                              at='2026-09-16T16:00:00+08:00')
            self.assertEqual(result['reasons'], ['UNSUPPORTED_SESSION'])
        result = self.get('minute', at='2026-09-16T09:30:30+08:00')
        self.assertEqual(result['reasons'], ['MINUTE_UNSEALED'])
        for params in ({'month': '2613'}, {'month': '../'}, {'at': '2026-09-16T09:31:00'},
                       {'raw_revision': '-1'}, {'raw_revision': '1.2'}, {'bundle_id': '../x'}, {'sql': 'select'}):
            self.assertEqual(self.client.get('/api/skew/latest', params=params).status_code, 400, params)
        for url in ('/api/skew/minute', '/api/skew/series', '/api/skew/latest?month=2610&month=2609',
                    '/api/skew/minute?day=20260916&minute=2026-09-16T09:30:01Z'):
            self.assertEqual(self.client.get(url).status_code, 400, url)

    def test_reference_missing_corrupt_synthetic_rejected_and_target_missing(self):
        with TestClient(create_app(self.root, reference_directory=self.refs, target_month=MONTH)) as client:
            result = client.get('/api/skew/latest', params={'at': '2026-09-16T09:31:00+08:00'}).json()
            self.assertEqual(result['reasons'], ['REFERENCE_INVALID'])
        result = self.get(month='2609')
        self.assertEqual(result['reasons'], ['REFERENCE_MISSING'])
        (self.package / 'bundle.json').write_text('{}')
        result = self.get()
        self.assertEqual(result['reasons'], ['REFERENCE_INVALID'])
        self.assertIsNone(result['skew_25d_vp'])
        with TestClient(create_app(self.root)) as client:
            with patch.dict('os.environ', {}, clear=True):
                self.assertEqual(client.get('/api/skew/latest').json()['reasons'], ['TARGET_MONTH_MISSING'])

    def test_unknown_calendar(self):
        self.assertEqual(self.get(at='2030-09-16T09:31:00+08:00')['reasons'], ['CALENDAR_UNKNOWN'])

    def test_missing_raw_and_locked_historical_preserve_http_errors(self):
        self.db.close()
        path = self.root / (DAY + '.sqlite')
        saved = path.read_bytes()
        path.unlink()
        response = self.client.get('/api/skew/latest', params={'at': '2026-09-16T09:31:00+08:00'})
        self.assertEqual(response.status_code, 404)
        path.write_bytes(saved)
        with (self.root / '.collector.lock').open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            response = self.client.get('/api/skew/minute', params={'day': DAY, 'minute': START.isoformat(),
                                                                  'at': '2026-09-16T09:31:00+08:00'})
            self.assertEqual(response.status_code, 503)
            self.assertIn('stop Collector', response.json()['error'])

    def test_fixed_revision_replays_late_invalid_observation(self):
        old = self.get('minute')
        append_chain(self.db, START + timedelta(minutes=1), invalid=True)
        changed = self.get('minute')
        self.assertEqual(changed['status'], 'UNAVAILABLE')
        self.assertGreater(changed['raw_revision'], old['raw_revision'])
        replay = self.get('minute', raw_revision=old['raw_revision'], bundle_id=old['reference']['bundle_id'])
        self.assertEqual(replay, old)
        response = self.client.get('/api/skew/latest', params={'at': '2026-09-16T09:31:00+08:00',
                                                              'raw_revision': 999999})
        self.assertEqual(response.status_code, 400)

    def test_series_gaps_baseline_change_and_period_enumeration(self):
        append_chain(self.db, START + timedelta(minutes=2))
        series = self.get('series', at='2026-09-16T09:33:00+08:00')
        self.assertEqual(len(series['points']), 3)
        self.assertEqual([p['status'] for p in series['points']], ['OK', 'OK', 'UNAVAILABLE'])
        self.assertIsNone(series['change_vp'])
        self.assertEqual(series['baseline']['minute'], START.isoformat())
        two = self.get('series', at='2026-09-16T09:32:00+08:00')
        self.assertEqual(two['change_vp'], two['points'][1]['skew_25d_vp'] - two['points'][0]['skew_25d_vp'])
        full = self.get('series', at='2026-09-16T16:00:00+08:00')
        self.assertEqual(len(full['points']), 237)  # Calendar MO: 120 + 117 continuous minutes.
        self.assertEqual(full['points'][119]['minute'][11:16], '11:29')
        self.assertEqual(full['points'][120]['minute'][11:16], '13:00')
        self.assertEqual(full['points'][-1]['minute'][11:16], '14:56')
        self.assertTrue(all(p['historical'] for p in full['points']))
        waiting = self.get('series', at='2026-09-16T09:30:30+08:00')
        self.assertEqual(waiting['points'], [])
        self.assertIsNone(waiting['raw_revision'])

    def test_series_pins_revision_during_late_write(self):
        append_chain(self.db, START + timedelta(minutes=2))
        original = MarketFrameReader.minute
        calls = []
        def read(reader, *args, **kwargs):
            result = original(reader, *args, **kwargs)
            calls.append(kwargs['raw_revision'])
            if len(calls) == 1:
                append_chain(self.db, START + timedelta(minutes=2), invalid=True)
            return result
        with patch.object(MarketFrameReader, 'minute', read):
            result = self.get('series', at='2026-09-16T09:32:00+08:00')
        self.assertEqual(calls, [None, result['raw_revision']])
        self.assertEqual([p['status'] for p in result['points']], ['OK', 'OK'])
        self.assertEqual({p['raw_revision'] for p in result['points']}, {result['raw_revision']})
        self.assertEqual(self.get('minute', minute='2026-09-16T09:31:00+08:00',
                                  at='2026-09-16T09:32:00+08:00')['status'], 'UNAVAILABLE')

    def test_reference_context_pinned_to_loaded_bytes(self):
        context = self.repository.load(DAY, MONTH)
        (self.package / 'calendar.json').write_text('{}')
        frame = MarketFrameReader(Store(self.root),
                                  calendar=context.calendar).minute(context.scope, START,
                                  evaluated_at=START + timedelta(minutes=1), stale_after_us=30_000_000)
        self.assertEqual(frame['calendar_version'], context.bundle['calendar']['version'])
        with self.assertRaises(ReferenceUnavailable):
            self.repository.load(DAY, MONTH)

    def test_reference_wrong_previous_day_and_metadata_rejected(self):
        for field in ('previous_day', 'expiry', 'hash', 'version'):
            with tempfile.TemporaryDirectory() as temporary:
                path = write_package(Path(temporary))
                bundle = json.loads((path / 'bundle.json').read_bytes())
                if field == 'previous_day':
                    bundle['calendar']['previous_cffex_trading_day'] = '20260914'
                    bundle['rate']['fixing_date'] = '20260914'
                elif field == 'expiry':
                    bundle['universe']['instruments'][0]['expiry'] = '20261015'
                elif field == 'hash':
                    bundle['universe']['sha256'] = 'b' * 64
                else:
                    bundle['calendar']['version'] = 'different'
                raw = json.dumps(bundle).encode()
                (path / 'bundle.json').write_bytes(raw)
                manifest = json.loads((path / 'manifest.json').read_bytes())
                manifest['sha256']['bundle.json'] = digest(raw)
                (path / 'manifest.json').write_text(json.dumps(manifest))
                with self.assertRaises(ReferenceUnavailable):
                    load_package(path, DAY, MONTH, bundle['bundle_id'], allow_synthetic=True)

    def test_offline_import_verifies_source_archives_and_never_overwrites(self):
        # TEST DOUBLE official-format envelope: URLs are never fetched and these
        # temporary bytes are not real official publications or live evidence.
        bundle = json.loads((self.package / 'bundle.json').read_bytes())
        bundle['source_kind'] = 'OFFICIAL'
        bundle['product_rules']['source_url'] = 'https://www.cffex.com.cn/TEST_DOUBLE'
        bundle['rate']['source_url'] = 'https://www.chinamoney.com.cn/TEST_DOUBLE'
        manifest = json.loads((self.package / 'manifest.json').read_bytes())
        for name, field in (('rules.source', 'product_rules'), ('rate.source', 'rate'),
                            ('listing.source', None)):
            content = ('TEST DOUBLE source: ' + name).encode()
            (self.package / name).write_bytes(content)
            manifest['sha256'][name] = digest(content)
            if field:
                bundle[field]['source_sha256'] = digest(content)
        universe = json.loads((self.package / 'universe.json').read_bytes())
        universe['products']['MO']['source'] = 'https://www.cffex.com.cn/TEST_DOUBLE'
        raw = json.dumps(universe).encode()
        (self.package / 'universe.json').write_bytes(raw)
        bundle['universe']['sha256'] = manifest['sha256']['universe.json'] = digest(raw)
        raw = json.dumps(bundle).encode()
        (self.package / 'bundle.json').write_bytes(raw)
        manifest['sha256']['bundle.json'] = digest(raw)
        (self.package / 'manifest.json').write_text(json.dumps(manifest))
        destination = self.root / 'imported'
        command = [sys.executable, '-m', 'query.skew_references',
                   str(self.package), '--directory', str(destination)]
        first = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertFalse((destination / DAY / (MONTH + '.json')).exists())
        imported = ReferenceRepository(destination).load(DAY, MONTH, bundle['bundle_id'])
        self.assertEqual(imported.bundle['bundle_sha256'], digest(raw))
        again = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(again.returncode, 0)
        self.assertIn('immutable package already exists', again.stderr)
        (self.package / 'rate.source').write_text('TEST DOUBLE damaged source')
        with self.assertRaises(ReferenceUnavailable):
            load_package(self.package, DAY, MONTH, bundle['bundle_id'])


if __name__ == '__main__':
    unittest.main()
