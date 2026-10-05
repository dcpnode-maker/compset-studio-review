"""Evidence projection tests: denominator, context, price bases and public fields."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from compset.hotel_contracts import SEED
from compset.workspace import build_workspace, public_property_url

STAMP = '2026-09-28T06:00:00+00:00'
HOTEL_CONTEXT = {'hotel_id': 'aketa-dehradun', 'start_date': '2026-09-28', 'days': 2,
                 'stay_nights': 1, 'rooms': 1, 'adults': 1, 'children': 0, 'currency': 'INR'}
AIR_CONTEXT = {'listing_id': '123', 'start_date': '2026-09-28', 'end_date': '2026-09-30',
               'stay_nights': 1, 'adults': 1, 'children': 0, 'infants': 0, 'pets': 0, 'currency': 'AED'}


def hotel_rate(source='agoda', amount='5000'):
    actual = {**HOTEL_CONTEXT, 'checkin': '2026-09-28', 'checkout': '2026-09-29'}
    row = {'hotel_id': 'aketa-dehradun', 'source': source, 'channel': source,
           'checkin': actual['checkin'], 'checkout': actual['checkout'], 'amount': amount,
           'currency': 'INR', 'amount_type': 'ota_display_price', 'source_amount_basis': 'nightly_room_rate',
           'precision': 'displayed_integer', 'context_verified': True, 'direct_supplier_quote': False,
           'observed_context': actual, 'taxes_included': False, 'fees_included': False,
           'provenance': {'observed_at': STAMP, 'source_artifact': 'C:\\secret.json',
                          'source_url': 'https://www.agoda.com/hotel-aketa/hotel/dehradun-in.html?token=secret'}}
    if source == 'google_hotels':
        row.update(amount_type='google_calendar_minimum', channel=None, source_amount_basis=None,
                   context_verified=False)
        row['observed_context']['rooms'] = None
    return row


def hotel_report(rates=None):
    return {'hotel': deepcopy(SEED['hotels'][0]), 'context': deepcopy(HOTEL_CONTEXT),
            'rates': rates or [], 'coverage': [], 'observations': [], 'updated_at': '2026-09-30T12:00:00+00:00'}


def quote_record(listing_id='123', day='2026-09-28', amount='650.40'):
    context = {**AIR_CONTEXT, 'listing_id': listing_id, 'checkin': day,
               'checkout': '2026-09-29' if day == '2026-09-28' else '2026-09-30'}
    quote = {**context, 'amount': amount, 'amount_kind': 'one_night_stay_total', 'status': 'quoted',
             'guest_context_verified': True, 'observed_at': STAMP}
    return {'context': context, 'status': 'quoted', 'observed_at': STAMP, 'quotes': [quote]}


def air_reports(records=None):
    compset = {'run_id': 'set1', 'subject': {'listing_id': '123', 'title': 'Subject'},
               'selected': [{'listing_id': '456', 'title': 'Competitor'}], 'candidates': [],
               'context': deepcopy(AIR_CONTEXT)}
    nightly = {'compset_run_id': 'set1', 'context': deepcopy(AIR_CONTEXT), 'listing_ids': ['123', '456'],
               'records': records or [], 'amount_kind': 'one_night_stay_total'}
    return compset, nightly


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def save(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def hotel(self, value):
        self.save('hotel-pipelines/latest.json', value)
        return build_workspace(self.root)['datasets'][0]

    def air(self, compset, nightly):
        self.save('compset-latest.json', compset)
        self.save('one-night-latest.json', nightly)
        return build_workspace(self.root)['datasets'][1]

    def test_missing_files_and_malformed_documents_are_visible_without_mutations(self):
        result = build_workspace(self.root)
        self.assertEqual(len(result['warnings']), 5)
        self.assertEqual(list(self.root.iterdir()), [])
        self.save('hotel-pipelines/latest.json', [])
        path = self.root / 'one-night-latest.json'
        path.write_text('{broken', encoding='utf-8')
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = build_workspace(self.root)
        self.assertTrue(any('could not be read' in w for w in result['warnings']))
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_hotel_grid_has_all_planned_sources_and_dates_and_source_timestamp(self):
        result = self.hotel(hotel_report([hotel_rate()]))
        self.assertEqual(result['summary']['date_cells'], 10)
        self.assertEqual(result['summary']['indicative_cells'], 1)
        self.assertEqual(result['summary']['unknown_cells'], 9)
        self.assertEqual(result['observed_at'], STAMP)
        cell = next(c for c in result['cells'] if c['state'] == 'indicative')
        self.assertEqual(cell['amount'], '5000')
        self.assertEqual(cell['offers'][0]['taxes_included'], False)

    def test_wrong_hotel_party_currency_and_date_do_not_contaminate_minimum(self):
        for field, value in [('hotel_id', 'other'), ('adults', 2), ('rooms', True),
                             ('currency', 'USD'), ('checkin', '2026-09-29')]:
            with self.subTest(field=field):
                bad = hotel_rate(amount='1')
                bad['observed_context'][field] = value
                result = self.hotel(hotel_report([hotel_rate(), bad]))
                cell = next(c for c in result['cells'] if c['state'] == 'indicative')
                self.assertEqual(cell['amount'], '5000')
                self.assertEqual(len(cell['offers']), 1)

    def test_google_partner_is_not_mixed_into_calendar_minimum(self):
        calendar = hotel_rate('google_hotels', '4600')
        partner = deepcopy(calendar)
        partner.update(amount='4000', amount_type='google_partner_nightly_total', channel='booking', provider='Booking.com')
        result = self.hotel(hotel_report([partner, calendar]))
        cell = next(c for c in result['cells'] if c['state'] == 'indicative')
        self.assertEqual(cell['amount'], '4600')
        self.assertEqual(cell['amount_basis'], 'google_calendar_minimum')
        self.assertEqual(len(cell['offers']), 2)
        self.assertIn('calendar display', cell['selection_note'])

    def test_explicit_provider_conflict_or_google_unknown_precision_is_rejected(self):
        for source in ('agoda', 'google_hotels'):
            for field in ('hotel_id', 'provider_id', 'provider_hotel_id'):
                with self.subTest(source=source, field=field):
                    row = hotel_rate(source)
                    row['observed_context'][field] = 'another-property'
                    self.assertEqual(self.hotel(hotel_report([row]))['summary']['rate_rows'], 0)
        row = hotel_rate('google_hotels')
        row['precision'] = []
        self.assertEqual(self.hotel(hotel_report([row]))['summary']['rate_rows'], 0)

    def test_abbreviated_display_has_no_exact_amount(self):
        row = hotel_rate('google_hotels', '5000')
        row.update(precision='abbreviated', approximate_amount='5000', display_amount='5K')
        cell = next(c for c in self.hotel(hotel_report([row]))['cells'] if c['state'] == 'indicative')
        self.assertIsNone(cell['amount'])
        self.assertEqual(cell['display_amount'], '5K')
        self.assertIsNone(cell['offers'][0]['amount'])

    def test_different_basis_or_tax_semantics_do_not_produce_common_minimum(self):
        a, b = hotel_rate(), hotel_rate(amount='1')
        b['taxes_included'] = True
        result = self.hotel(hotel_report([a, b]))
        cell = next(c for c in result['cells'] if c['state'] == 'indicative')
        self.assertIsNone(cell['amount'])
        self.assertEqual(cell['reason'], 'different_price_bases_or_terms')
        self.assertEqual(len(cell['offers']), 2)

    def test_unavailable_coverage_requires_contextual_negative_evidence(self):
        report = hotel_report()
        report['coverage'] = [{'hotel_id': 'aketa-dehradun', 'source': 'agoda', 'checkin': '2026-09-28',
                               'checkout': '2026-09-29', 'state': 'unavailable'}]
        self.assertEqual(self.hotel(report)['summary']['unavailable_cells'], 0)
        actual = {**HOTEL_CONTEXT, 'checkin': '2026-09-28', 'checkout': '2026-09-29'}
        report['observations'] = [{'hotel_id': 'aketa-dehradun', 'source': 'agoda', 'status': 'unavailable',
                                  'unavailability_verified': True, 'requested_context': deepcopy(actual),
                                  'observed_context': deepcopy(actual), 'observed_at': STAMP, 'rates': []}]
        self.assertEqual(self.hotel(report)['summary']['unavailable_cells'], 1)
        report['observations'][0]['observed_context']['adults'] = 2
        self.assertEqual(self.hotel(report)['summary']['unavailable_cells'], 0)

    def test_negative_provider_conflict_cannot_mark_the_canonical_profile_unavailable(self):
        actual = {**HOTEL_CONTEXT, 'checkin': '2026-09-28', 'checkout': '2026-09-29'}
        observation = {'hotel_id': 'aketa-dehradun', 'source': 'agoda', 'status': 'unavailable',
                       'unavailability_verified': True, 'requested_context': deepcopy(actual),
                       'observed_context': deepcopy(actual), 'observed_at': STAMP, 'rates': []}
        for location in (None, 'requested_context', 'observed_context'):
            for key in ('provider_id', 'provider_hotel_id'):
                with self.subTest(location=location, key=key):
                    obs = deepcopy(observation)
                    target = obs if location is None else obs[location]
                    target[key] = '27746358'
                    report = hotel_report()
                    report['observations'] = [obs]
                    self.assertEqual(self.hotel(report)['summary']['unavailable_cells'], 0)
        observation['observed_context']['provider_id'] = '110205'
        report = hotel_report()
        report['observations'] = [observation]
        self.assertEqual(self.hotel(report)['summary']['unavailable_cells'], 1)

    def test_unknown_coverage_and_malformed_rows_never_become_zero_or_unavailable(self):
        report = hotel_report([None, 'bad', {'source': 'agoda', 'amount_type': []}])
        report['coverage'] = [None, {'source': 'agoda', 'checkin': [], 'hotel_id': 'aketa-dehradun'}]
        result = self.hotel(report)
        self.assertEqual(result['summary']['unknown_cells'], 10)
        self.assertTrue(all(c['amount'] is None for c in result['cells']))

    def test_malformed_nested_price_fields_are_rejected_without_breaking_the_grid(self):
        for field in ('amount_type', 'source_amount_basis', 'precision', 'currency', 'observed_context'):
            for value in ([], {}):
                with self.subTest(field=field, value=value):
                    row = hotel_rate()
                    row[field] = value
                    result = self.hotel(hotel_report([row]))
                    self.assertEqual(result['summary']['unknown_cells'], 10)

    def test_airbnb_abbreviated_quote_cannot_be_promoted_to_exact(self):
        record = quote_record(amount='5000')
        record['quotes'][0].update(precision='abbreviated', display_amount='5K')
        result = self.air(*air_reports([record]))
        self.assertEqual(result['summary']['quoted_cells'], 0)

    def test_public_field_allowlist_strips_raw_artifacts_credentials_and_query(self):
        row = hotel_rate()
        row.update(password='secret', raw_payload={'token': 'secret'}, conditions=[{'text': 'Members only', 'cookie': 'secret'}])
        result = self.hotel(hotel_report([row]))
        encoded = json.dumps(result)
        self.assertNotIn('secret', encoded)
        self.assertNotIn('source_artifact', encoded)
        self.assertIn('Members only', encoded)
        self.assertNotIn('token=', encoded)

    def test_public_property_links_reject_nonpublic_destinations_and_api_paths(self):
        for url in ['javascript:alert(1)', 'https://user:password@www.agoda.com/h/hotel/in.html',
                    'http://127.0.0.1/rooms/123', 'https://api.bnbmehomes.com/api/v1/search',
                    'file:///C:/secret', 'https://www.airbnb.com/api/v3/private']:
            self.assertIsNone(public_property_url(url))
        self.assertEqual(public_property_url('https://www.airbnb.com/rooms/123?token=abc#secret'), 'https://www.airbnb.com/rooms/123')

    def test_airbnb_full_planned_denominator_and_party_rejection(self):
        compset, nightly = air_reports([quote_record()])
        bad = quote_record('456', amount='1')
        bad['quotes'][0]['adults'] = 2
        nightly['records'].append(bad)
        result = self.air(compset, nightly)
        self.assertEqual(result['summary']['date_cells'], 4)
        self.assertEqual(result['summary']['quoted_cells'], 1)
        self.assertEqual(result['summary']['unknown_cells'], 3)

    def test_airbnb_missing_compset_preserves_planned_listing_denominator(self):
        compset, nightly = air_reports([quote_record()])
        result = self.air({}, nightly)
        self.assertEqual(result['summary']['date_cells'], 4)
        self.assertEqual(result['summary']['quoted_cells'], 1)
        self.assertTrue(any('missing comp-set run' in w for w in result['warnings']))

    def test_minimum_stay_and_arrival_rules_are_restricted_not_booked(self):
        for reason, field, value, expected_state in [
            ('sleeping_night_unavailable', 'available', False, 'unavailable'),
            ('minimum_stay_not_met', 'min_nights', 2, 'restricted'),
            ('checkin_not_allowed', 'available_for_checkin', False, 'restricted'),
            ('checkout_not_allowed', 'available_for_checkout', False, 'restricted')]:
            with self.subTest(reason=reason):
                record = quote_record()
                actual = record['context']
                record.update(status='calendar_skipped', quotes=[], calendar_observed_at=STAMP,
                              preflight={'decision': 'skip_quote', 'reason': reason, 'context': actual,
                                         'evidence': [{'listing_id': '123', 'date': actual['checkout'] if reason == 'checkout_not_allowed' else actual['checkin'],
                                                       'field': field, 'value': value, 'http_status': 200}]})
                result = self.air(*air_reports([record]))
                self.assertEqual(result['cells'][0]['state'], expected_state)
                self.assertIsNone(result['cells'][0]['amount'])
                record['preflight']['evidence'][0]['listing_id'] = '456'
                self.assertEqual(self.air(*air_reports([record]))['cells'][0]['state'], 'unknown')

    def test_selected_plan_and_refundable_alternative_remain_in_detail(self):
        record = quote_record(amount='610.36')
        quote = record['quotes'][0]
        quote['rate_plan'] = 'Non-refundable'
        quote['rate_options'] = [{'rate_plan_id': '3', 'rate_plan': 'Refundable', 'is_selected': False,
                                 'amount': '650.40', 'currency': 'AED', 'amount_kind': 'one_night_stay_total',
                                 'status': 'quoted', 'cancellation_terms': 'Free until stated date',
                                 'sources': [{'observed_request_context': deepcopy(record['context']), 'observed_at': STAMP}]}]
        cell = self.air(*air_reports([record]))['cells'][0]
        self.assertEqual(cell['amount'], '610.36')
        self.assertEqual(cell['offers'][0]['rate_plan_name'], 'Non-refundable')
        option = cell['offers'][0]['rate_options'][0]
        self.assertEqual(option['amount'], '650.40')
        self.assertEqual(option['cancellation_terms'], 'Free until stated date')

    def test_freshness_orders_instants_not_lexical_offsets(self):
        older = quote_record(amount='1')
        older['observed_at'] = older['quotes'][0]['observed_at'] = '2026-09-28T12:00:00+05:30'
        newer = quote_record(amount='2')
        newer['observed_at'] = newer['quotes'][0]['observed_at'] = '2026-09-28T07:00:00+00:00'
        result = self.air(*air_reports([newer, older]))
        self.assertEqual(result['cells'][0]['amount'], '2')
        self.assertEqual(result['observed_at'], newer['observed_at'])

    def test_discovery_and_price_context_are_not_relabelled(self):
        compset, nightly = air_reports()
        compset['candidate_discovery_context'] = {**AIR_CONTEXT, 'adults': 2, 'checkin': '2026-10-17', 'checkout': '2026-10-20'}
        result = self.air(compset, nightly)
        self.assertEqual(result['context']['adults'], 1)
        self.assertEqual(result['discovery_context']['adults'], 2)
        self.assertTrue(any('Candidate discovery' in w for w in result['warnings']))

    def test_portfolio_retains_inventory_separate_and_uses_public_property_url(self):
        self.save('portfolio-latest.json', {'observed_at': STAMP, 'properties': [{
            'property_id': '123', 'title': 'Home', 'publication_status': 'active_in_public_details',
            'source_url': 'https://api.bnbmehomes.com/api/v1/search',
            'public_property_url': 'https://bnbmehomes.com/property/home-123', 'observed_at': STAMP,
            'quotes': [{'amount': 1}], 'attributes': {'password': 'secret'}}],
            'summary': {'property_count': 1, 'active_inventory_complete': False}})
        result = build_workspace(self.root)
        prop = result['portfolio']['properties'][0]
        self.assertEqual(prop['source_url'], 'https://bnbmehomes.com/property/home-123')
        self.assertNotIn('quotes', prop)
        self.assertFalse(result['portfolio']['summary']['active_inventory_complete'])


if __name__ == '__main__':
    unittest.main()
