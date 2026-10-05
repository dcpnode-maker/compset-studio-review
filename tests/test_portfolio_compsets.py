import copy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from compset.portfolio_compsets import (build_portfolio, candidate_pool, cached_sources,
                                       compare_subject, enrich_official_subject, _profile)

STAMP = '2026-09-28T00:00:00+00:00'
NOW = datetime(2026, 9, 28, 10, tzinfo=timezone.utc)


def listing(identifier='2', **changes):
    return {'listing_id': identifier, 'title': 'Saved public listing', 'latitude': 25, 'longitude': 55,
            'bedrooms': 1, 'beds': 1, 'bathrooms': 1, 'person_capacity': 2, 'room_type': 'Entire home/apt',
            'amenities': ['Wifi', 'Kitchen'], 'observed_at': STAMP, **changes}


def pool(rows, **snapshot):
    return candidate_pool([{'sha256': 'source-a', 'snapshot': {'candidates': rows, 'observed_at': STAMP, **snapshot}}])


def official(**changes):
    return enrich_official_subject({**listing(), 'property_id': '1', 'currency': 'SAR', 'city': 'Riyadh',
                                    'public_property_url': 'https://bnbmehomes.com/property/test', **changes})


class PortfolioCompsetTests(unittest.TestCase):
    def test_unknown_privacy_is_provisional_and_blocks_relaxation(self):
        result = compare_subject(official(room_type=None), pool([listing(), listing('3', bedrooms=2)]), now=NOW)
        self.assertEqual(result['currency'], 'SAR')
        self.assertEqual(result['selected_candidate_ids'], [])
        self.assertEqual(result['provisional_physical_candidate_ids'], ['airbnb:2'])
        self.assertEqual(result['adaptive']['stop_reason'], 'subject_core_fields_unknown')
        self.assertEqual(len(result['adaptive']['steps']), 1)
        self.assertEqual(len(result['candidates']), 2)

    def test_explicit_privacy_quote_is_provenance_not_marketing_title(self):
        text = 'Guests have full private access to the entire apartment and all building facilities.'
        subject = official(room_type=None, detail_attributes={'description': text}, details_observed_at=STAMP)
        self.assertEqual(subject['room_type'], 'Entire home/apt')
        evidence = subject['field_sources']['room_type']
        self.assertEqual(evidence['source_path'], 'detail_attributes.description')
        self.assertEqual(evidence['matched_quote'], text.split(' and ')[0])
        for description in ('Luxury entire apartment', 'You do not have exclusive use of the apartment.', 'No exclusive use of the apartment.'):
            subject = official(room_type=None, title='Entire apartment', detail_attributes={'description': description, 'room_types_name': 'Entire apartment'})
            self.assertIsNone(subject['room_type'])

    def test_namespaces_keep_same_numeric_id_distinct_and_no_corporate_join(self):
        direct = official(property_id='2', operator_name='BnBMe')
        result = compare_subject(direct, pool([listing('2', host_id='99')]), now=NOW)
        self.assertEqual(result['selected_candidate_ids'], ['airbnb:2'])
        self.assertEqual(result['candidates'][0]['operator_relation'], 'unknown_or_different')
        self.assertTrue(any('same physical unit' in w for w in result['warnings']))
        airbnb = _profile(listing('2'), 'airbnb', '2')
        self.assertEqual(compare_subject(airbnb, pool([listing('2')]), now=NOW)['candidates'], [])

    def test_ten_gate_relaxes_but_eleven_stays_strict(self):
        baseline = [listing(str(i + 10)) for i in range(11)]
        strict = compare_subject(official(), pool(baseline), now=NOW)
        self.assertEqual(len(strict['adaptive']['steps']), 1)
        relaxed = compare_subject(official(), pool(baseline[:10] + [listing('99', bathrooms=2)]), now=NOW)
        self.assertEqual([s['counts']['eligible_count'] for s in relaxed['adaptive']['steps']], [10, 11])
        self.assertEqual(relaxed['criteria']['bedroom_tolerance'], 0)
        self.assertEqual(len(relaxed['candidates']), 11)

    def test_radius_uses_saved_geo_only_and_keeps_exclusions(self):
        result = compare_subject(official(), pool([listing('2', longitude=55.025), listing('3', longitude=56)]), now=NOW)
        self.assertGreater(result['adaptive']['automatic_radius_changes'], 0)
        self.assertEqual(result['summary']['candidate_counts_within_km'], {'2': 0, '5': 1, '10': 1})
        self.assertEqual(len(result['candidates']), 2)
        self.assertFalse(result['source_coverage']['complete_for_requested_cells'])
        self.assertTrue(all(not s['discovery_performed'] for s in result['adaptive']['steps']))

    def test_fields_choose_actual_timestamp_not_lexical_and_keep_conflicts(self):
        old = listing(bedrooms=1, observed_at='2026-09-28T12:00:00+05:30')
        new = listing(bedrooms=2, bathrooms=None, observed_at='2026-09-28T07:00:00+00:00')
        result = pool([old, new])
        row = result['profiles'][0]
        self.assertEqual(row['bedrooms'], 2)
        self.assertEqual(row['bathrooms'], 1)
        self.assertEqual(row['field_sources']['bathrooms']['observed_at'], old['observed_at'])
        self.assertEqual(len(row['field_conflicts']['bedrooms']), 2)
        self.assertEqual(result['observation_count'], 2)

    def test_staleness_does_not_retimestamp_source(self):
        result = compare_subject(official(), pool([listing()]), now=NOW + timedelta(days=10))
        self.assertEqual(result['subject']['observed_at'], STAMP)
        self.assertEqual(result['subject_freshness']['status'], 'stale')

    def test_operator_size_requires_explicit_public_host_evidence(self):
        rows = [listing(str(i + 10), host_id='999') for i in range(10)] + [listing('99', host_name='Big Corp')]
        result = compare_subject(official(), pool(rows), now=NOW)
        classified = {r['candidate_id']: r for r in result['candidates']}
        self.assertEqual(classified['airbnb:10']['operator_size'], 'large')
        self.assertEqual(classified['airbnb:10']['observed_host_listing_count'], 10)
        self.assertEqual(classified['airbnb:99']['operator_size'], 'unknown')

    def test_no_coords_preserves_unknown_distance_and_all_rows(self):
        result = compare_subject(official(latitude=None), pool([listing()]), now=NOW)
        self.assertIsNone(result['candidates'][0]['distance_km'])
        self.assertFalse(result['candidates'][0]['provisional_physical_match'])
        self.assertEqual(result['adaptive']['stop_reason'], 'subject_coordinates_unknown')

    def test_malformed_pool_rows_audited_and_unknown_namespace_rejected(self):
        result = pool([{}, None, listing()])
        self.assertEqual(len(result['rejected_rows']), 2)
        self.assertEqual(result['unique_candidate_count'], 1)
        with self.assertRaises(ValueError):
            pool([listing()], source_namespace='bnbme_direct')

    def test_exact_cache_identity_and_observed_request_currency(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'cache/listings'
            folder.mkdir(parents=True)
            body = {'data': {'presentation': {'stayProductDetailPage': {'sections': {'sections': [
                {'section': {'__typename': 'PdpTitleSection', 'title': 'Exact cache title'}}]}}}}}
            envelope = {'source_url': 'https://www.airbnb.com/rooms/2?token=secret', 'status': 200,
                        'request_context': {'currency': 'GBP'}, 'body': body}
            path = folder / '2-AED.json'
            path.write_text(json.dumps({'observed_at': STAMP, 'payloads': [envelope]}))
            sources, errors = cached_sources(root, {'2'})
            result = candidate_pool(sources)['profiles'][0]
            self.assertEqual(result['title'], 'Exact cache title')
            self.assertEqual(result['currency'], 'GBP')
            self.assertNotIn('secret', json.dumps(result))
            envelope['source_url'] = 'https://www.airbnb.com/rooms/3'
            path.write_text(json.dumps({'observed_at': STAMP, 'payloads': [envelope]}))
            self.assertEqual(cached_sources(root, {'2'})[0], [])

    def test_build_preserves_history_sources_and_explicit_subject_membership(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            portfolio = {'observed_at': STAMP, 'properties': [{**listing(), 'property_id': '2', 'currency': 'AED', 'room_type': None}],
                         'airbnb_listings': [listing('2')]}
            (root / 'portfolio-latest.json').write_text(json.dumps(portfolio))
            (root / 'compset-latest.json').write_text(json.dumps({'candidates': [listing('3')], 'observed_at': STAMP}))
            before = (root / 'portfolio-latest.json').read_bytes()
            first = build_portfolio(data_root=root, now=NOW)
            self.assertEqual(first['summary']['total_comparison_records'], 2)
            self.assertEqual(first['summary']['cross_platform_identity_links_created'], 0)
            self.assertEqual({r['subject_id'] for r in first['subjects']}, {'bnbme_direct:2', 'airbnb:2'})
            prior_path = root / 'portfolio-compsets' / first['subjects'][0]['artifact']
            prior_bytes = prior_path.read_bytes()
            second = build_portfolio(data_root=root, now=NOW + timedelta(hours=1))
            self.assertNotEqual(first['build_id'], second['build_id'])
            self.assertEqual(prior_path.read_bytes(), prior_bytes)
            self.assertEqual((root / 'portfolio-latest.json').read_bytes(), before)
            self.assertEqual(second['summary']['unique_candidates'], 2)


if __name__ == '__main__':
    unittest.main()
