"""Read audited, immutable Skew input packages; no Raw or network access.

Package layout and the offline import command are documented in query/README.md.
Hashes cover original bytes, never a JSON reserialization or a self-hash.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit

from query.analytics import _parse_reference, _semantic_reference_reasons
from data_provider.market_calendar import Calendar, parse_day, parse_at
from data_provider.market_frame import Scope, Universe

IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}')
PACKAGE_FILES = ('manifest.json', 'bundle.json', 'universe.json', 'calendar.json')
SOURCE_FILES = ('listing.source', 'rules.source', 'rate.source')


class ReferenceUnavailable(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def read_bytes(path):
    with Path(path).open('rb') as stream:
        value = stream.read(8 * 1024 * 1024 + 1)
    if len(value) > 8 * 1024 * 1024:
        raise ValueError('reference file exceeds 8 MiB')
    return value


def digest(value):
    return hashlib.sha256(value).hexdigest()


def decode(value):
    def constant(value):
        raise ValueError('nonfinite JSON constant')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    return json.loads(value, parse_constant=constant, object_pairs_hook=pairs)


@dataclass(frozen=True)
class ReferenceContext:
    bundle: dict
    scope: Scope
    calendar: Calendar
    manifest_sha256: str
    listing_sha256: str | None


def load_package(path, day, month, bundle_id, *, allow_synthetic=False):
    """Pin all files to verified bytes before any Market Frame read."""
    try:
        path = Path(path).resolve(strict=True)
        manifest_bytes = read_bytes(path / 'manifest.json')
        manifest = decode(manifest_bytes)
        if manifest['schema_version'] != 1 or manifest['bundle_id'] != bundle_id:
            raise ValueError('package identity mismatch')
        contents = {}
        for name in ('bundle.json', 'universe.json', 'calendar.json'):
            contents[name] = read_bytes(path / name)
            if digest(contents[name]) != manifest['sha256'][name]:
                raise ValueError('package hash mismatch')
        bundle = decode(contents['bundle.json'])
        if 'bundle_sha256' in bundle:
            raise ValueError('bundle hash belongs to external manifest')
        bundle['bundle_sha256'] = digest(contents['bundle.json'])
        contracts = _parse_reference(bundle)
        if (bundle['bundle_id'], bundle['valid_trading_day'], bundle['month']) != (bundle_id, day, month):
            raise ValueError('bundle scope mismatch')
        if bundle['source_kind'] != 'OFFICIAL' and not (
                allow_synthetic and bundle['source_kind'] == 'SYNTHETIC'
                and 'TEST DOUBLE' in bundle['review']):
            raise ValueError('production requires OFFICIAL reviewed reference')
        universe_manifest = decode(contents['universe.json'])
        if bundle['source_kind'] == 'OFFICIAL':
            sources = (
                ('listing.source', universe_manifest['products']['MO']['source'],
                 manifest['sha256']['listing.source'], ('cffex.com.cn',)),
                ('rules.source', bundle['product_rules']['source_url'],
                 bundle['product_rules']['source_sha256'], ('cffex.com.cn',)),
                ('rate.source', bundle['rate']['source_url'], bundle['rate']['source_sha256'],
                 ('chinamoney.com.cn', 'chinamoney.org.cn', 'shibor.org')),
            )
            for name, url, expected_hash, domains in sources:
                parsed = urlsplit(url)
                host = parsed.hostname or ''
                if (parsed.scheme != 'https' or parsed.username or parsed.password
                        or not any(host == domain or host.endswith('.' + domain) for domain in domains)
                        or digest(read_bytes(path / name)) != expected_hash
                        or manifest['sha256'][name] != expected_hash):
                    raise ValueError('official source archive or URL invalid')
        universe = Universe.from_manifest(universe_manifest, 'CFFEX', 'MO', day,
                                          bundle['universe']['version'])
        scope = Scope.select(universe, 'CFFEX', 'MO', month=month, option_chain=True)
        if not scope.universe_complete:
            raise ReferenceUnavailable('UNIVERSE_INCOMPLETE')
        listing = {r['id']: r for r in universe_manifest['products']['MO']['instruments']
                   if r['month'] == month}
        if set(listing) != set(contracts) or not contracts:
            raise ValueError('reference and official listing members differ')
        for code, contract in contracts.items():
            if any(listing[code][key] != contract[key] for key in ('side', 'strike', 'expiry')):
                raise ValueError('official contract metadata differs')
        calendar = Calendar(None, content=contents['calendar.json'])
        for name in ('universe', 'calendar'):
            if bundle[name]['sha256'] != digest(contents[name + '.json']):
                raise ValueError('reference context hash mismatch')
        days = [r['trading_day'] for r in calendar.data['exchanges']['CFFEX']['days']]
        if day not in days or days.index(day) == 0:
            raise ReferenceUnavailable('CALENDAR_UNKNOWN')
        if bundle['calendar']['previous_cffex_trading_day'] != days[days.index(day) - 1]:
            raise ReferenceUnavailable('RATE_MISSING')
        # Validate semantic reference requirements before any database query.
        reasons, _, _ = _semantic_reference_reasons(
            {'scope': scope.as_dict(), 'trading_day': day,
             'calendar_version': calendar.data['version']}, bundle, contracts,
            parse_at(day[:4] + '-' + day[4:6] + '-' + day[6:] + 'T09:31:00+08:00'))
        if reasons:
            raise ReferenceUnavailable(reasons[0])
        return ReferenceContext(bundle, scope, calendar, digest(manifest_bytes),
                                manifest['sha256'].get('listing.source'))
    except ReferenceUnavailable:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise ReferenceUnavailable('REFERENCE_INVALID') from None


class ReferenceRepository:
    def __init__(self, directory, *, allow_synthetic=False):
        self.directory = Path(directory)
        self.allow_synthetic = allow_synthetic

    def load(self, day, month, bundle_id=None):
        parse_day(day)
        if bundle_id is None:
            try:
                selection = decode(read_bytes(self.directory / day / (month + '.json')))
                bundle_id = selection['bundle_id']
            except FileNotFoundError:
                raise ReferenceUnavailable('REFERENCE_MISSING') from None
            except (OSError, ValueError, TypeError, KeyError):
                raise ReferenceUnavailable('REFERENCE_INVALID') from None
        if not isinstance(bundle_id, str) or not IDENTIFIER.fullmatch(bundle_id):
            raise ReferenceUnavailable('REFERENCE_INVALID')
        path = self.directory / day / bundle_id
        if not path.exists():
            raise ReferenceUnavailable('REFERENCE_MISSING')
        return load_package(path, day, month, bundle_id, allow_synthetic=self.allow_synthetic)


def main():
    parser = argparse.ArgumentParser(description='Validate/import an audited OFFICIAL Skew package offline')
    parser.add_argument('package', type=Path)
    parser.add_argument('--directory', required=True, type=Path)
    args = parser.parse_args()
    bundle = decode(read_bytes(args.package / 'bundle.json'))
    day, month, bundle_id = (bundle[k] for k in ('valid_trading_day', 'month', 'bundle_id'))
    parse_day(day)
    if not isinstance(bundle_id, str) or not IDENTIFIER.fullmatch(bundle_id):
        raise ValueError('invalid bundle ID')
    load_package(args.package, day, month, bundle_id)
    parent = args.directory / day
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / bundle_id
    if destination.exists():
        raise ValueError('immutable package already exists')
    with tempfile.TemporaryDirectory(prefix='.import-', dir=parent) as temporary:
        staged = Path(temporary) / bundle_id
        staged.mkdir()
        for name in PACKAGE_FILES + SOURCE_FILES:
            shutil.copyfile(args.package / name, staged / name)
        load_package(staged, day, month, bundle_id)
        staged.rename(destination)
    print(json.dumps({'imported': bundle_id, 'trading_day': day, 'month': month,
                      'selection': {'bundle_id': bundle_id}}))


if __name__ == '__main__':
    main()
