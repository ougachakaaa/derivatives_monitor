#!/usr/bin/env python3
"""Collector-owned integrity checks for the bundled CTP SDK manifest."""
import hashlib
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SDK_RELATIVE = Path('collector/third_party/ctp/v6.7.13_20260225')
NAMES = ('ThostFtdcMdApi.h', 'ThostFtdcUserApiDataType.h',
         'ThostFtdcUserApiStruct.h', 'thostmduserapi_se.so')


def sdk_errors(root=ROOT):
    sdk = root / SDK_RELATIVE
    errors = []
    try:
        entries = dict(line.split('=', 1) for line in (sdk / 'MANIFEST.txt').read_text().splitlines()
                       if '=' in line)
        for name in NAMES:
            key = name + ('.sha256' if name.endswith('.so') else '.repository_sha256')
            digest = hashlib.sha256((sdk / 'linux64/mdapi' / name).read_bytes()).hexdigest()
            if digest != entries[key]:
                errors.append('SDK hash mismatch: ' + name)
    except (OSError, ValueError, KeyError) as error:
        errors.append('SDK manifest invalid: ' + str(error))
    return errors


class SdkManifestTest(unittest.TestCase):
    def test_repository_sdk_matches_manifest(self):
        self.assertEqual(sdk_errors(), [])

    def test_damage_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='test-double-sdk-') as temporary:
            root = Path(temporary)
            sdk = root / SDK_RELATIVE
            source = sdk / 'linux64/mdapi'
            source.mkdir(parents=True)
            digest = hashlib.sha256(b'TEST DOUBLE').hexdigest()
            entries = []
            for name in NAMES:
                (source / name).write_bytes(b'TEST DOUBLE')
                suffix = '.sha256' if name.endswith('.so') else '.repository_sha256'
                entries.append(name + suffix + '=' + digest)
            (sdk / 'MANIFEST.txt').write_text('\n'.join(entries))
            self.assertEqual(sdk_errors(root), [])
            (source / NAMES[0]).write_bytes(b'TEST DOUBLE damaged')
            self.assertEqual(sdk_errors(root), ['SDK hash mismatch: ' + NAMES[0]])


if __name__ == '__main__':
    unittest.main()
