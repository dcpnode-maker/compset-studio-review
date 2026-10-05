from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from compset import intelligence as api
from compset.portfolio_compsets import build_portfolio

STAMP = '2026-09-28T00:00:00+00:00'


class IntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.properties = []
        for index in range(31):
            self.properties.append({'property_id': str(index + 1), 'title': f'Observed apartment {index}',
                'city': 'London' if index == 30 else 'Dubai', 'currency': 'GBP' if index == 30 else 'AED',
                'bedrooms': 0 if index == 30 else 1, 'bathrooms': 1, 'beds': 1, 'person_capacity': 2,
                'latitude': 25, 'longitude': 55, 'room_type': 'Entire home/apt', 'observed_at': STAMP,
                'public_property_url': 'https://bnbmehomes.com/property/test?token=secret',
                'calendar': [{'date': '2026-09-28', 'available_room': 1, 'availability': 'available',
                    'currency': 'GBP' if index == 30 else 'AED', 'price_basis': 'website_calendar_rate',
                    'non_refundable_price': '123.45', 'refundable_price': '151.25', 'observed_at': STAMP,
                    'source_url': 'https://api.bnbmehomes.com/api/v1/inventory/get-inventory?token=secret'}]})
        self.portfolio = {'properties': self.properties, 'airbnb_listings': [
            {'listing_id': '1', 'title': 'Unlinked host property', 'observed_at': STAMP, 'currency': 'AED', 'city': 'Dubai'}]}
        self.write('portfolio-latest.json', self.portfolio)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def test_summary_compact_identity_headers_no_calendars_raw_or_automatic_links(self):
        result = api.summary(self.root)
        self.assertEqual(len(result['str']['properties']), 32)
        ids = {r['id'] for r in result['str']['properties']}
        self.assertIn('bnbme_direct:1', ids)
        self.assertIn('airbnb:1', ids)
        self.assertEqual(result['str']['summary']['cross_platform_identity_links_created'], 0)
        self.assertEqual(result['str']['calendar_bounds'], {'start': '2026-09-28', 'end': '2026-09-29'})
        encoded = json.dumps(result)
        self.assertNotIn('non_refundable_price', encoded)
        self.assertNotIn('secret', encoded)
        self.assertNotIn('123.45', encoded)

    def test_filters_apply_to_whole_inventory_before_pagination(self):
        result = api.str_calendar(self.root, start='2026-09-28', query='apartment 30', bedrooms=0, currency='GBP')
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['entities'][0]['id'], 'bnbme_direct:31')
        self.assertEqual(result['request']['query'], 'apartment 30')
        self.assertEqual(len(result['cells']), 14)

    def test_pagination_and_unknown_day_grid_are_bounded(self):
        result = api.str_calendar(self.root, start='2026-09-28', days=31, offset=25)
        self.assertEqual(result['total'], 31)
        self.assertEqual(len(result['entities']), 6)
        self.assertEqual(len(result['cells']), 6 * 31)
        self.assertEqual(result['cells'][1]['state'], 'unknown')
        self.assertIsNone(result['cells'][1]['observed_at'])

    def test_calendar_prices_indicative_keep_refundability_and_unknown_guests(self):
        result = api.str_calendar(self.root, start='2026-09-28', days=1, limit=1)
        cell = result['cells'][0]
        self.assertEqual(cell['state'], 'indicative')
        self.assertEqual(cell['availability'], 'available')
        self.assertEqual(cell['amount'], '123.45')
        self.assertEqual([o['amount'] for o in cell['offers']], ['123.45', '151.25'])
        self.assertEqual(cell['amount_basis'], 'website_calendar_rate')
        self.assertIsNone(result['source_context']['bnbme_direct']['adults'])
        self.assertIsNone(result['source_context']['bnbme_direct']['taxes_included'])

    def test_unavailable_is_typed_and_retains_indicative_alternatives_without_sellable_amount(self):
        self.properties[0]['calendar'][0].update(available_room=0, availability='unavailable')
        self.write('portfolio-latest.json', self.portfolio)
        cell = api.str_calendar(self.root, start='2026-09-28', days=1, limit=1)['cells'][0]
        self.assertEqual(cell['state'], 'unavailable')
        self.assertEqual(len(cell['offers']), 2)
        self.assertIsNone(cell['amount'])
        self.assertNotIn('booked', cell)

    def test_malformed_count_currency_time_or_basis_cannot_be_available_rate(self):
        for changes in ({'available_room': '0', 'availability': 'unavailable'}, {'currency': 'SAR'},
                        {'observed_at': None}, {'price_basis': 'stay_total'}):
            with self.subTest(changes=changes):
                original = self.properties[0]['calendar'][0].copy()
                self.properties[0]['calendar'][0].update(changes)
                self.write('portfolio-latest.json', self.portfolio)
                cell = api.str_calendar(self.root, start='2026-09-28', days=1, limit=1)['cells'][0]
                self.assertEqual(cell['state'], 'unknown')
                self.assertIsNone(cell['amount'])
                self.properties[0]['calendar'][0] = original

    def test_airbnb_does_not_borrow_same_numeric_direct_property_rate(self):
        result = api.str_calendar(self.root, start='2026-09-28', days=1, namespace='airbnb')
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['cells'][0]['entity_id'], 'airbnb:1')
        self.assertEqual(result['cells'][0]['state'], 'unknown')
        self.assertIsNone(result['cells'][0]['amount'])

    def test_input_limits_and_types_are_not_silently_coerced(self):
        invalid = ({'days': 32}, {'days': True}, {'limit': 26}, {'offset': -1}, {'start': '2026-02-30'},
                   {'namespace': 'other'}, {'bedrooms': '1'}, {'bedrooms': True}, {'currency': 'aed'},
                   {'city': 'Mars'}, {'query': 'x' * 121}, {'query': '\n'}, {'start': '9999-12-31'})
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                api.str_calendar(self.root, **{'start': '2026-09-28', **values})

    def test_read_cache_invalidates_when_source_changes_and_never_writes(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        first = api.summary(self.root)
        api.str_calendar(self.root, start='2026-09-28')
        after = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        first['str']['properties'][0]['title'] = 'Consumer modification'
        self.assertNotEqual(api.summary(self.root)['str']['properties'][0]['title'], 'Consumer modification')
        self.properties[0]['title'] = 'Observed new title'
        self.write('portfolio-latest.json', self.portfolio)
        second = api.summary(self.root)
        self.assertEqual(second['str']['properties'][0]['title'], 'Observed new title')
        self.assertNotEqual(first['revision'], second['revision'])

    def test_compset_paginates_all_decisions_and_retains_full_compact_map(self):
        rows = [{**self.properties[0], 'listing_id': str(i + 100), 'calendar': []} for i in range(56)]
        self.write('compset-latest.json', {'candidates': rows, 'observed_at': STAMP})
        build_portfolio(data_root=self.root, now=datetime(2026, 9, 28, tzinfo=timezone.utc))
        result = api.str_compset(self.root, 'bnbme_direct:1', offset=50, limit=10)
        self.assertEqual(result['candidate_total'], 57)
        self.assertEqual(len(result['map_points']), 57)
        self.assertEqual(len(result['candidates']), 7)
        self.assertEqual(result['request'], {'subject_id': 'bnbme_direct:1', 'offset': 50, 'limit': 10, 'decision': None, 'candidate_id': None})
        self.assertNotIn('candidate_outcomes', json.dumps(result['adaptive']))
        self.assertTrue(result['candidates'][0]['adaptive_history'])
        selected = api.str_compset(self.root, 'bnbme_direct:1', decision='selected', limit=100)
        self.assertEqual(selected['candidate_total'], 56)
        self.assertEqual(selected['all_candidate_total'], 57)
        one = api.str_compset(self.root, 'bnbme_direct:1', candidate_id='airbnb:155')
        self.assertEqual(one['candidate_total'], 1)
        self.assertEqual(one['candidates'][0]['id'], 'airbnb:155')
        self.assertEqual(len(one['map_points']), 57)

    def test_compset_rejects_bad_identity_and_artifact_escape(self):
        for identity in ('../secret', '123', 'airbnb:../x', 'hotel:1'):
            with self.assertRaises(ValueError):
                api.str_compset(self.root, identity)
        with self.assertRaises(KeyError):
            api.str_compset(self.root, 'airbnb:999')
        self.write('outside.json', {'secret': 'private-data'})
        self.write('portfolio-compsets/latest.json', {'subjects': [{'subject_id': 'airbnb:1', 'artifact': '../outside.json'}]})
        result = api.str_compset(self.root, 'airbnb:1')
        self.assertEqual(result['candidates'], [])
        self.assertNotIn('private-data', json.dumps(result))
        self.assertTrue(any('Invalid comparison artifact' in w for w in result['warnings']))

    def test_missing_hotel_evidence_does_not_invent_market_rates(self):
        result = api.hotel(self.root)
        self.assertEqual(result['compset']['candidates'], [])
        self.assertTrue(result['warnings'])
        self.assertTrue(all(c['state'] == 'unknown' for c in result['dataset']['cells']))
        self.assertEqual(result['portfolio']['coverage']['status'], 'not_imported')

    def test_imported_hotel_identities_are_separate_and_unsupported_for_rates(self):
        from compset.hotel_portfolio import import_hotel_portfolio
        observation = {'schema_version': 'lighthouse-portfolio-observation.v1', 'observed_at': STAMP,
            'source_url': 'https://app.mylighthouse.com/portfolio?token=credential-canary-8534',
            'coverage': {'account_subject_count': 1, 'subject_list_complete': True, 'competitor_membership_complete': False, 'notes': []},
            'hotels': [{'provider_id': 'owned-aketa', 'title': 'Aketa account entry', 'roles': ['subject']}], 'relations': []}
        import_hotel_portfolio(observation, self.root)
        result = api.hotel(self.root)
        self.assertEqual(result['portfolio']['profiles'][0]['id'], 'lighthouse:owned-aketa')
        self.assertFalse(result['portfolio']['profiles'][0]['rate_coverage']['collection_supported'])
        self.assertEqual(result['dataset']['id'], 'aketa')
        self.assertNotIn('credential-canary-8534', json.dumps(result))
        header = api.summary(self.root)['hotel']['portfolio']['profiles'][0]
        self.assertEqual(header['id'], 'lighthouse:owned-aketa')
        self.assertNotIn('field_evidence', header)

    def test_malformed_hotel_portfolio_does_not_hide_aketa_dataset(self):
        self.write('hotel-portfolio/latest.json', {'schema_version': 'wrong', 'profiles': [{'secret': 'private'}]})
        result = api.hotel(self.root)
        self.assertEqual(result['portfolio']['coverage']['status'], 'read_error')
        self.assertEqual(result['dataset']['id'], 'aketa')
        self.assertNotIn('private', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
