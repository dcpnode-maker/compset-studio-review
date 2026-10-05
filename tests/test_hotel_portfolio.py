"""Synthetic account-import proofs; no real account information in fixtures."""
from copy import deepcopy
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from compset.hotel_portfolio import (INPUT_SCHEMA, build_hotel_portfolio,
    import_hotel_portfolio, load_hotel_portfolio, source_url)


STAMP = '2026-09-28T12:00:00+00:00'


def fixture():
    return {'schema_version': INPUT_SCHEMA, 'observed_at': STAMP,
            'source_url': 'https://app.mylighthouse.com/hotels',
            'coverage': {'account_subject_count': 2, 'subject_list_complete': True,
                         'competitor_membership_complete': False, 'notes': ['Synthetic fixture only']},
            'hotels': [{'provider_id': '001', 'name': 'North Hotel', 'role': 'subject', 'city': 'Test City', 'room_count': 40},
                       {'provider_id': '002', 'name': 'South Hotel', 'role': 'subject'},
                       {'provider_id': '900', 'name': 'North Hotel', 'role': 'competitor'}],
            'relations': [{'subject_provider_id': '001', 'competitor_provider_id': '900'}]}


class HotelPortfolioTests(unittest.TestCase):
    def test_identity_namespaces_leading_zero_and_homonyms_preserved(self):
        result = build_hotel_portfolio(fixture())
        self.assertEqual({p['id'] for p in result['profiles']}, {'lighthouse:001', 'lighthouse:002', 'lighthouse:900'})
        self.assertEqual(result['coverage']['profile_count'], 3)
        self.assertEqual(sum(p['title'] == 'North Hotel' for p in result['profiles']), 2)
        self.assertTrue(all(p['provider_id'] in ('001', '002', '900') for p in result['profiles']))

    def test_duplicate_exact_ids_merge_roles_and_relationship_evidence(self):
        raw = fixture()
        raw['hotels'].append({'provider_id': '002', 'name': 'South Hotel', 'role': 'competitor'})
        raw['relations'].extend([{'subject_provider_id': '001', 'competitor_provider_id': '002'}, raw['relations'][0]])
        result = build_hotel_portfolio(raw)
        profile = next(p for p in result['profiles'] if p['provider_id'] == '002')
        self.assertEqual(profile['roles'], ['competitor', 'subject'])
        self.assertEqual(len(result['relations']), 2)
        self.assertEqual(len(result['relations'][0]['evidence']), 1)

    def test_complete_list_requires_count_reconciliation(self):
        raw = fixture()
        raw['coverage']['account_subject_count'] = 3
        with self.assertRaisesRegex(ValueError, 'reconciliation'):
            build_hotel_portfolio(raw)
        raw['coverage']['subject_list_complete'] = False
        result = build_hotel_portfolio(raw)
        self.assertEqual(result['coverage']['status'], 'partial_subject_list')
        self.assertEqual(result['coverage']['observed_subject_count'], 2)
        raw['coverage']['account_subject_count'] = 1
        with self.assertRaisesRegex(ValueError, 'exceed'):
            build_hotel_portfolio(raw)

    def test_no_ota_match_or_rate_support_inferred_from_hotel_name(self):
        raw = fixture()
        raw['hotels'][0]['name'] = 'Hotel Aketa'
        result = build_hotel_portfolio(raw)
        profile = next(p for p in result['profiles'] if p['provider_id'] == '001')
        self.assertEqual(profile['id'], 'lighthouse:001')
        self.assertEqual(profile['ota_mappings'], [])
        self.assertFalse(profile['rate_coverage']['collection_supported'])
        self.assertEqual(profile['rate_coverage']['status'], 'not_collected')

    def test_relations_require_existing_observed_roles_and_not_self(self):
        for relation in ({'subject_provider_id': '001', 'competitor_provider_id': '777'},
                         {'subject_provider_id': '900', 'competitor_provider_id': '001'},
                         {'subject_provider_id': '001', 'competitor_provider_id': '001'}):
            with self.subTest(relation=relation):
                raw = fixture(); raw['relations'] = [relation]
                with self.assertRaises(ValueError):
                    build_hotel_portfolio(raw)

    def test_observation_timestamps_require_timezone(self):
        raw = fixture(); raw['observed_at'] = '2026-09-28T12:00:00'
        with self.assertRaisesRegex(ValueError, 'timezone'):
            build_hotel_portfolio(raw)

    def test_public_fields_keep_unknown_and_reject_bad_types(self):
        result = build_hotel_portfolio(fixture())
        profile = next(p for p in result['profiles'] if p['provider_id'] == '002')
        self.assertIsNone(profile['currency'])
        self.assertIsNone(profile['latitude'])
        for key, value in (('provider_id', 1), ('room_count', True), ('star_classification', 4.6), ('latitude', float('nan'))):
            raw = fixture(); raw['hotels'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_hotel_portfolio(raw)

    def test_conflicting_attributes_preserved_without_arbitrary_guess(self):
        raw = fixture()
        raw['hotels'].append({'provider_id': '001', 'name': 'North Hotel Renamed', 'role': 'subject', 'room_count': 42})
        result = build_hotel_portfolio(raw)
        profile = next(p for p in result['profiles'] if p['provider_id'] == '001')
        self.assertIsNone(profile['room_count'])
        self.assertEqual(profile['attribute_conflicts']['room_count'], [40, 42])
        self.assertEqual(profile['aliases'], ['North Hotel', 'North Hotel Renamed'])

    def test_coordinate_conflict_clears_pair_and_keeps_evidence(self):
        raw = fixture()
        raw['hotels'][0].update(latitude=30, longitude=78)
        raw['hotels'].append({'provider_id': '001', 'name': 'North Hotel', 'role': 'subject', 'latitude': 31, 'longitude': 78})
        result = build_hotel_portfolio(raw)
        profile = next(p for p in result['profiles'] if p['provider_id'] == '001')
        self.assertIsNone(profile['latitude']); self.assertIsNone(profile['longitude'])
        self.assertEqual(profile['attribute_conflicts']['latitude'], [30, 31])
        with TemporaryDirectory() as directory:
            import_hotel_portfolio(raw, directory)
            loaded = load_hotel_portfolio(directory)
        profile = next(p for p in loaded['profiles'] if p['provider_id'] == '001')
        self.assertEqual(profile['attribute_conflicts']['latitude'], [30, 31])

    def test_links_drop_queries_and_fragments_reject_foreign_hosts(self):
        self.assertEqual(source_url('https://app.mylighthouse.com/hotels?token=secret#token=also-secret'), 'https://app.mylighthouse.com/hotels')
        for url in ('http://app.mylighthouse.com/', 'https://app.mylighthouse.com.evil.test/',
                    'https://user:password@app.mylighthouse.com/', 'javascript:alert(1)',
                    'https://app.mylighthouse.com:443/', 'https://app.mylighthouse.com/token/secret'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                source_url(url)

    def test_credentials_and_unrequested_account_fields_rejected(self):
        raw = fixture(); raw['hotels'][0]['cookie'] = 'secret'
        with self.assertRaisesRegex(ValueError, 'Unsupported fields'):
            build_hotel_portfolio(raw)
        raw = fixture(); raw['password'] = 'secret'
        with self.assertRaisesRegex(ValueError, 'Unsupported fields'):
            build_hotel_portfolio(raw)

    def test_source_time_retained_and_input_not_mutated(self):
        raw = fixture(); before = deepcopy(raw)
        raw['hotels'][0]['observed_at'] = '2026-09-25T10:00:00Z'; before = deepcopy(raw)
        result = build_hotel_portfolio(raw)
        self.assertEqual(raw, before)
        self.assertEqual(next(p for p in result['profiles'] if p['provider_id'] == '001')['observed_at'], '2026-09-25T10:00:00Z')
        self.assertEqual(result, build_hotel_portfolio(raw))

    def test_atomic_latest_failed_publish_preserves_previous_json(self):
        with TemporaryDirectory() as directory:
            first = import_hotel_portfolio(fixture(), directory)
            old = Path(first['path']).read_bytes()
            changed = fixture(); changed['hotels'][0]['name'] = 'New Name'
            with patch('compset.hotel_portfolio.os.replace', side_effect=OSError('write failure')):
                with self.assertRaises(OSError):
                    import_hotel_portfolio(changed, directory)
            self.assertEqual(Path(first['path']).read_bytes(), old)
            self.assertFalse(list(Path(directory).rglob('*.tmp')))

    def test_snapshot_history_idempotence_and_formula_safe_csv(self):
        raw = fixture(); raw['hotels'][0]['name'] = '=HYPERLINK("https://example.test")'
        with TemporaryDirectory() as directory:
            first = import_hotel_portfolio(raw, directory)
            second = import_hotel_portfolio(raw, directory)
            self.assertEqual(first['sha256'], second['sha256'])
            previous = Path(first['history_path']).read_bytes()
            raw['hotels'][0]['name'] = 'Changed'
            import_hotel_portfolio(raw, directory)
            self.assertEqual(Path(first['history_path']).read_bytes(), previous)
            import_hotel_portfolio(fixture() | {'hotels': [dict(fixture()['hotels'][0], name='=SUM(1)')] + fixture()['hotels'][1:]}, directory)
            with (Path(directory)/'hotel-portfolio/profiles.csv').open(encoding='utf-8-sig', newline='') as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(next(p for p in rows if p['provider_id'] == '001')['title'], "'=SUM(1)")

    def test_projection_rejects_secret_nested_values_and_never_enables_collection(self):
        with TemporaryDirectory() as directory:
            result = import_hotel_portfolio(fixture(), directory)
            path = Path(result['path']); raw = json.loads(path.read_text(encoding='utf-8'))
            raw['account_secret'] = 'credential-canary-7a59'
            raw['profiles'][0]['cookie'] = 'credential-canary-7a59'
            raw['profiles'][0]['rate_coverage']['collection_supported'] = True
            raw['profiles'][0]['ota_mappings'] = [{'token': 'credential-canary-7a59'}]
            path.write_text(json.dumps(raw), encoding='utf-8')
            projection = load_hotel_portfolio(directory)
            self.assertNotIn('credential-canary-7a59', json.dumps(projection))
            self.assertTrue(all(not p['rate_coverage']['collection_supported'] for p in projection['profiles']))
            raw['profiles'][0]['field_evidence']['title'][0]['value'] = {'secret': 'credential'}
            path.write_text(json.dumps(raw), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_hotel_portfolio(directory)

    def test_missing_portfolio_is_unknown_not_complete(self):
        with TemporaryDirectory() as directory:
            result = load_hotel_portfolio(directory)
        self.assertEqual(result['profiles'], [])
        self.assertEqual(result['coverage']['status'], 'not_imported')
        self.assertFalse(result['coverage']['subject_list_complete'])


if __name__ == '__main__':
    unittest.main()
