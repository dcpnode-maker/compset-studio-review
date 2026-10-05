from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from compset.provider_receipts import (
    AKETA, RAMADA, build_provider_receipts, load_provider_receipts,
)

FAIRFIELD = 'official:fairfield-dehradun'
ONIX = 'osm:node:6066360185'
STAMP = '2026-09-30T16:05:04.757Z'
GOOGLE_ID = 'ChgI98PmmYGh5fJgGgwvZy8xMmNueDRyN3IQAQ'
GOOGLE_URL = 'https://www.google.com/travel/hotels/entity/' + GOOGLE_ID


def booking(hotel_id, provider, path):
    return {
        'hotel_id': hotel_id, 'provider_id': provider,
        'checkin': '2026-09-30', 'checkout': '2026-10-01',
        'adults': 1, 'rooms': 1, 'currency': 'INR', 'amount': 8500,
        'amount_type': 'booking_display_stay_total', 'source': 'booking.com',
        'source_url': 'https://www.booking.com' + path
            + '?aid=2438770&checkin=2026-09-30&checkout=2026-10-01'
              '&no_rooms=1&group_adults=1&selected_currency=INR',
        'observed_at': STAMP, 'room_type': None, 'meal_plan': None,
        'cancellation': None,
        'taxes_fees': 'legally_required_display_charges_included_additional_charges_may_apply',
    }


def fixture():
    a = booking(AKETA, '449888', '/hotel/in/aketa.html')
    f = booking(FAIRFIELD, '7986048', '/hotel/in/fairfield-by-marriott-dehradun.html')
    requested = {
        'hotel_name': 'Hotel Aketa', 'provider_hotel_id': GOOGLE_ID,
        'source': 'google_hotels', 'timezone': 'Asia/Kolkata',
        'start_date': '2026-09-30', 'days': 2, 'rooms': 1,
        'adults': 1, 'children': 0, 'currency': 'INR', 'stay_nights': 1,
    }
    return {
        'schema_version': 'hotel-provider-receipts.v1', 'assembled_at': STAMP,
        'start_date': '2026-09-30', 'detailed_end_date': '2026-10-30',
        'annual_end_date': '2027-09-29', 'currency': 'INR',
        'party': {'adults': 1, 'rooms': 1, 'stay_nights': 1},
        'roster': [
            {'id': AKETA, 'name': 'Hotel Aketa', 'source_url': GOOGLE_URL},
            {'id': FAIRFIELD, 'name': 'Fairfield by Marriott Dehradun',
             'source_url': 'https://www.marriott.com/en-us/hotels/dedfi-fairfield-dehradun/overview/'},
            {'id': RAMADA, 'name': 'Ramada by Wyndham Dehradun Chakrata Road',
             'source_url': 'https://www.wyndhamhotels.com/ramada/dehradun-india/ramada-dehradun-chakrata-road/overview'},
            {'id': ONIX, 'name': 'Hotel The Onix',
             'source_url': 'https://www.hoteltheonix.com/'},
        ],
        'profiles': {
            AKETA: {'id': 449888, 'name': 'Hotel Aketa Rajpur Road Dehradun, Dehradun',
                    'source': 'booking.com', 'source_url': a['source_url'],
                    'observed_at': STAMP,
                    'location': {'city_name': 'Dehradun', 'country_code': 'in'}},
            FAIRFIELD: {'id': 7986048, 'name': 'Fairfield by Marriott Dehradun',
                        'source': 'booking.com', 'source_url': f['source_url'],
                        'observed_at': STAMP,
                        'location': {'city_name': 'Dehradun', 'country_code': 'in'}},
            RAMADA: {'source': 'wyndham_direct', 'provider_id': '51110',
                     'observed_at': STAMP,
                     'detail': {'name': 'Ramada by Wyndham Dehradun Chakrata Road',
                                'city': 'Dehradun', 'countryCode': 'IN',
                                'uri': 'uttarakhand/dehradun/ramada-by-wyndham-dehradun-chakrata-road',
                                'email': 'private@example.test'}},
        },
        'rates': [a, f],
        'direct_rates': [{
            'hotel_id': RAMADA, 'provider_id': '51110',
            'checkin': '2026-10-01', 'checkout': '2026-10-02',
            'adults': 1, 'children': 0, 'rooms': 1, 'currency': 'INR',
            'amount': 4950, 'amount_type': 'direct_best_available_per_night',
            'source': 'wyndham_direct', 'observed_at': STAMP,
            'source_url': 'https://www.wyndhamhotels.com/ramada/dehradun-india/'
                'ramada-dehradun-chakrata-road/rooms-rates?brand_id=RA&children=0'
                '&adults=1&rooms=1&checkInDate=10%2F01%2F2026&checkOutDate=10%2F02%2F2026',
        }],
        'google_saved': {
            'source_url': GOOGLE_URL, 'observed_at': STAMP,
            'requested_context': requested,
            'observed_context': {
                **requested, 'rooms': None, 'requested_rooms': 1,
                'room_count_verified': False,
            },
            'rates': [{
                'checkin': day, 'checkout': checkout, 'currency': 'INR',
                'amount': 4206, 'display_amount': '₹4,206',
                'precision': 'displayed_integer', 'amount_type': 'google_calendar_minimum',
                'direct_supplier_quote': False, 'room_count_verified': False,
            } for day, checkout in [
                ('2026-09-30', '2026-10-01'), ('2026-10-01', '2026-10-02')]],
        },
        # These untrusted claims must not affect the computed result.
        'coverage': {'annual_complete': True, 'all_ota_lowest_verified': True},
        'research': [{'cookie': 'private-token'}],
    }


def all_offers(result):
    return [o for h in result['hotels'] for c in h['calendar'] for o in c['offers']]


class ProviderReceiptsTests(unittest.TestCase):
    def test_annual_grid_source_semantics_unknowns_and_input_immutability(self):
        raw = fixture()
        before = deepcopy(raw)
        result = build_provider_receipts(raw)
        self.assertEqual(raw, before)
        self.assertEqual(len(result['dates']), 365)
        self.assertEqual(result['dates'][-1], '2027-09-29')
        self.assertEqual(result['summary']['observed_series_cells'], 5)
        self.assertEqual(result['summary']['coverage'], {
            'planned_cells': 1460, 'observed_cells': 4,
            'unknown_cells': 1456, 'annual_complete': False})
        self.assertFalse(result['summary']['all_ota_lowest_verified'])
        for hotel in result['hotels']:
            self.assertEqual(len(hotel['calendar']), 365)
            self.assertEqual(hotel['calendar'][-1]['state'], 'unknown')
            self.assertNotIn('amount', hotel['calendar'][0])
        offers = all_offers(result)
        display = next(o for o in offers if o['series_id'] == 'booking_display')
        google = next(o for o in offers if o['series_id'] == 'google_indicative')
        direct = next(o for o in offers if o['series_id'] == 'wyndham_direct')
        self.assertIsNone(display['children'])
        self.assertFalse(display['party_context_verified'])
        self.assertFalse(display['direct_supplier_quote'])
        self.assertIsNone(google['rooms'])
        self.assertFalse(google['room_count_verified'])
        self.assertTrue(direct['direct_supplier_quote'])
        self.assertTrue(direct['party_context_verified'])
        for offer in offers:
            self.assertIsNone(offer['taxes_included'])
            self.assertIsNone(offer['fees_included'])
            self.assertIsNone(offer['room_type'])
            self.assertIsNone(offer['meal_plan'])
            self.assertIsNone(offer['cancellation'])
        public = json.dumps(result)
        self.assertNotIn('private-token', public)
        self.assertNotIn('private@example.test', public)
        self.assertNotIn('aid=', public)

    def test_duplicates_and_conflicting_prices_never_inflate_cells_or_create_minimum(self):
        raw = fixture()
        raw['rates'].append(deepcopy(raw['rates'][0]))
        duplicate = build_provider_receipts(raw)
        self.assertEqual(duplicate['summary']['duplicate_rows'], 1)
        self.assertEqual(duplicate['summary']['unique_offers'], 5)
        self.assertEqual(duplicate['summary']['observed_series_cells'], 5)
        raw['rates'][-1]['amount'] = 9999
        varied = build_provider_receipts(raw)
        self.assertEqual(varied['summary']['unique_offers'], 6)
        self.assertEqual(varied['summary']['observed_series_cells'], 5)
        cell = next(h for h in varied['hotels'] if h['id'] == AKETA)['calendar'][0]
        self.assertEqual(len(cell['offers']), 3)
        self.assertNotIn('minimum', cell)
        self.assertNotIn('amount', cell)

    def test_booking_identity_stay_party_currency_and_url_mismatches_are_quarantined(self):
        changes = [
            ('hotel_id', RAMADA), ('hotel_id', {}), ('hotel_id', []), ('provider_id', '2029258'),
            ('source', 'wyndham_direct'), ('currency', 'USD'),
            ('adults', 1.0), ('rooms', True), ('children', False),
            ('checkin', '2027-09-30'), ('checkout', '2026-10-02'),
            ('amount', 'NaN'), ('amount', 0), ('observed_at', '2026-09-30T16:00:00'),
            ('source_url', 'https://www.booking.com.evil.test/hotel/in/aketa.html'),
            ('source_url', 'https://user:secret@www.booking.com/hotel/in/aketa.html'),
            ('source_url', fixture()['rates'][0]['source_url'].replace(
                'checkin=2026-09-30', 'checkin=2026-10-01')),
            ('source_url', fixture()['rates'][0]['source_url'] + '&cookie=secret'),
        ]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                raw = fixture()
                raw['rates'][0][field] = value
                result = build_provider_receipts(raw)
                booking_rows = [o for o in all_offers(result)
                                if o['series_id'] == 'booking_display']
                self.assertEqual(len(booking_rows), 1)
                self.assertTrue(result['rejections'])

    def test_profile_city_provider_and_property_path_mismatch_reject_rates(self):
        for change in ('city', 'provider', 'path', 'name'):
            with self.subTest(change=change):
                raw = fixture()
                profile = raw['profiles'][AKETA]
                if change == 'city':
                    profile['location']['city_name'] = 'Marrakech'
                elif change == 'provider':
                    profile['id'] = 2029258
                elif change == 'path':
                    profile['source_url'] = raw['rates'][1]['source_url']
                else:
                    profile['name'] = 'Hotel Central Palace'
                result = build_provider_receipts(raw)
                self.assertFalse(any(o['hotel_id'] == AKETA
                                     and o['series_id'] == 'booking_display'
                                     for o in all_offers(result)))
                self.assertEqual(len(result['hotels']), 4)

    def test_google_context_room_precision_and_row_identity_cannot_be_laundered(self):
        for change in ('entity', 'rooms', 'row_identity', 'date', 'precision', 'row_entity', 'row_url', 'row_timestamp'):
            with self.subTest(change=change):
                raw = fixture()
                saved = raw['google_saved']
                if change == 'entity':
                    saved['observed_context']['provider_hotel_id'] = 'another-entity'
                elif change == 'rooms':
                    saved['observed_context']['room_count_verified'] = True
                elif change == 'row_identity':
                    saved['rates'][0]['hotel_id'] = FAIRFIELD
                elif change == 'date':
                    saved['rates'][0]['checkin'] = '2026-10-30'
                    saved['rates'][0]['checkout'] = '2026-10-31'
                elif change == 'row_entity':
                    saved['rates'][0]['provider_hotel_id'] = 'another-entity'
                elif change == 'row_url':
                    saved['rates'][0]['source_url'] = 'https://evil.example/wrong-property'
                elif change == 'row_timestamp':
                    saved['rates'][0]['observed_at'] = '2026-09-29T16:00:00Z'
                else:
                    saved['rates'][0]['precision'] = 'abbreviated'
                result = build_provider_receipts(raw)
                count = sum(o['series_id'] == 'google_indicative'
                            for o in all_offers(result))
                self.assertLess(count, 2)
                self.assertTrue(result['rejections'])

    def test_direct_branch_city_and_party_mismatch_reject_quote(self):
        for change in ('branch', 'city', 'children', 'url'):
            with self.subTest(change=change):
                raw = fixture()
                if change == 'branch':
                    raw['profiles'][RAMADA]['detail']['uri'] = 'another-ramada'
                elif change == 'city':
                    raw['profiles'][RAMADA]['detail']['hotelCity'] = 'Delhi'
                elif change == 'children':
                    raw['direct_rates'][0]['children'] = 1
                else:
                    raw['direct_rates'][0]['source_url'] = (
                        raw['direct_rates'][0]['source_url'].replace(
                            'ramada-dehradun-chakrata-road', 'another-ramada'))
                result = build_provider_receipts(raw)
                self.assertFalse(any(o['series_id'] == 'wyndham_direct'
                                     for o in all_offers(result)))

    def test_bad_envelopes_and_roster_identity_are_rejected(self):
        for change in ('window', 'party', 'duplicate', 'name', 'url'):
            with self.subTest(change=change):
                raw = fixture()
                if change == 'window':
                    raw['annual_end_date'] = '2027-09-30'
                elif change == 'party':
                    raw['party']['adults'] = True
                elif change == 'duplicate':
                    raw['roster'].append(deepcopy(raw['roster'][0]))
                elif change == 'name':
                    raw['roster'][0]['name'] = 'Ramada'
                else:
                    raw['roster'][0]['source_url'] = 'http://127.0.0.1/'
                with self.assertRaises(ValueError):
                    build_provider_receipts(raw)

    def test_loader_reads_only_fixed_path_without_writes(self):
        paths = []
        def read(path, **kwargs):
            paths.append(path)
            self.assertEqual(kwargs, {'encoding': 'utf-8-sig'})
            return json.dumps(fixture())
        with patch.object(Path, 'read_text', read), \
                patch.object(Path, 'write_text', side_effect=AssertionError('write')), \
                patch.object(Path, 'mkdir', side_effect=AssertionError('mkdir')):
            result = load_provider_receipts(Path('saved-data'))
        self.assertEqual(paths, [
            Path('saved-data/provider-receipts/20260930/aketa-provider-receipts.json')])
        self.assertEqual(result['summary']['roster_count'], 4)


if __name__ == '__main__':
    unittest.main()
