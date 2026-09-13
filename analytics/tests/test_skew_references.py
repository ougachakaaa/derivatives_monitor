"""TEST DOUBLE owner tests for immutable Skew reference packages."""
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from analytics.skew_references import (ReferenceRepository, ReferenceUnavailable, digest,
                                       load_package)
from analytics.tests.support import DAY, MONTH, START, make_database, write_package
from data_provider.market_frame import MarketFrameReader
from data_provider.storage import Store


class SkewReferenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.references = self.root / 'references'
        self.package = write_package(self.references)
        self.repository = ReferenceRepository(self.references, allow_synthetic=True)

    def test_reference_context_is_pinned_to_loaded_bytes(self):
        database = make_database(self.root)
        self.addCleanup(database.close)
        context = self.repository.load(DAY, MONTH)
        (self.package / 'calendar.json').write_text('{}')
        frame = MarketFrameReader(Store(self.root), calendar=context.calendar).minute(
            context.scope, START, evaluated_at=START + timedelta(minutes=1),
            stale_after_us=30_000_000)
        self.assertEqual(frame['calendar_version'], context.bundle['calendar']['version'])
        with self.assertRaises(ReferenceUnavailable):
            self.repository.load(DAY, MONTH)

    def test_reference_wrong_previous_day_and_metadata_are_rejected(self):
        for field in ('previous_day', 'expiry', 'hash', 'version'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
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

    def test_offline_import_verifies_archives_and_never_overwrites(self):
        # TEST DOUBLE official-format envelope; no URL is fetched and these
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
        command = [sys.executable, '-m', 'analytics.skew_references',
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
