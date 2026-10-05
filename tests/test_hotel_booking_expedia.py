from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from compset.hotel_booking_expedia import capture, parse, _sanitize_snapshot, _write_capture


HOTEL = {'id': 'aketa-dehradun', 'name': 'Hotel Aketa', 'city': 'Dehradun', 'timezone': 'Asia/Kolkata',
         'sources': {'expedia': {'url': 'https://www.expedia.co.in/Dehradun-Hotels-Hotel-Aketa-Dehradun.h92850456.Hotel-Information', 'provider_id': '92850456', 'verified': True},
                     'booking': {'url': 'https://www.booking.com/hotel/in/aketa.en-gb.html', 'provider_id': None, 'verified': False}}}
CONTEXT = {'start_date': '2026-09-28', 'days': 30, 'checkin': '2026-09-28', 'checkout': '2026-09-29',
           'stay_nights': 1, 'rooms': 1, 'adults': 1, 'children': 0, 'currency': 'INR'}


def fixture(source='expedia'):
    url = HOTEL['sources'][source]['url']
    return {'source': source, 'hotel_id': HOTEL['id'], 'source_url': url,
            'observed_at': '2026-09-28T05:25:00+00:00', 'requested_context': deepcopy(CONTEXT),
            'browser_status': 200, 'stop_reason': None, 'browser_navigations': 1, 'direct_requests': 0,
            'method': 'scrapling_dynamic_public_page', 'responses': [],
            'snapshots': [{'url': url, 'title': 'Hotel Aketa Rajpur Road Dehradun, Dehradun - Expedia',
                           'headings': ['Hotel Aketa Rajpur Road Dehradun, Dehradun'],
                           'visible_text': 'Choose dates to view prices\nTravellers\n2 travellers, 1 room\n'
                                           'The current price is ₹12,625\n₹14,897 total\nincludes taxes & fees\n12 Oct - 13 Oct',
                           'controls': []}]}


class HotelBookingExpediaTests(unittest.TestCase):
    def test_default_date_teaser_is_not_requested_price(self):
        result = parse(fixture(), HOTEL, CONTEXT)
        self.assertEqual(result['rates'], [])
        self.assertEqual(result['reason'], 'exact_stay_contract_not_discovered')
        self.assertTrue(result['observed_context']['property_identity_verified'])
        self.assertNotIn('adults', result['observed_context'])

    def test_http_200_is_not_evidence_of_full_coverage(self):
        result = parse(fixture(), HOTEL, CONTEXT)
        self.assertEqual(result['status'], 'unknown')
        self.assertNotIn('unavailable', json.dumps(result))

    def test_booking_challenge_has_no_prices(self):
        item = fixture('booking')
        item['browser_status'] = None
        item['stop_reason'] = 'challenge_detected'
        item['snapshots'][0]['visible_text'] = "In order to continue, we need to verify that you're not a robot."
        result = parse(item, HOTEL, CONTEXT)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['reason'], 'challenge_detected')
        self.assertEqual(result['rates'], [])

    def test_all_access_statuses_stop_even_with_teaser(self):
        for status in [401, 403, 429]:
            with self.subTest(status=status):
                item = fixture()
                item['responses'] = [{'status': status}]
                result = parse(item, HOTEL, CONTEXT)
                self.assertEqual(result['status'], 'blocked')
                self.assertEqual(result['reason'], f'access_or_rate_limit_{status}')
                self.assertEqual(result['rates'], [])

    def test_browser_error_is_not_sold_out(self):
        item = fixture()
        item['stop_reason'] = 'browser_error'
        self.assertEqual(parse(item, HOTEL, CONTEXT)['status'], 'source_error')

    def test_cannot_launder_capture_through_another_stay_or_party(self):
        for key, value in [('checkin', '2026-09-29'), ('checkout', '2026-09-30'),
                           ('adults', 2), ('children', 1), ('rooms', 2), ('currency', 'USD')]:
            with self.subTest(key=key):
                item = fixture()
                item['requested_context'][key] = value
                self.assertEqual(parse(item, HOTEL, CONTEXT)['reason'], 'capture_context_mismatch')

    def test_quote_objects_cannot_bypass_evidence_parser(self):
        item = fixture()
        item.update(rates=[{'amount': '14897', 'context_verified': True}], observed_context=deepcopy(CONTEXT))
        self.assertEqual(parse(item, HOTEL, CONTEXT)['rates'], [])

    def test_search_result_name_is_not_property_identity(self):
        item = fixture()
        item['snapshots'][0]['url'] = 'https://www.expedia.co.in/Hotel-Search'
        self.assertEqual(parse(item, HOTEL, CONTEXT)['reason'], 'property_identity_not_verified')

    def test_wrong_property_capture_rejected(self):
        item = fixture()
        item['hotel_id'] = 'other-hotel'
        self.assertEqual(parse(item, HOTEL, CONTEXT)['reason'], 'capture_context_mismatch')

    def test_wrong_expedia_id_rejected_before_network(self):
        hotel = deepcopy(HOTEL)
        hotel['sources']['expedia']['provider_id'] = '99'
        with self.assertRaises(ValueError):
            capture('expedia', hotel, CONTEXT, output_dir=Path('unused'))

    def test_arbitrary_hosts_and_non_property_urls_rejected_before_network(self):
        for url in ['http://127.0.0.1/', 'https://www.expedia.co.in.evil.test/x',
                    'https://www.expedia.co.in/Hotel-Search',
                    HOTEL['sources']['expedia']['url'] + '?token=secret']:
            hotel = deepcopy(HOTEL)
            hotel['sources']['expedia']['url'] = url
            with self.subTest(url=url), self.assertRaises(ValueError):
                capture('expedia', hotel, CONTEXT, output_dir=Path('unused'))

    def test_challenge_fingerprint_and_query_tokens_not_persisted(self):
        result = _sanitize_snapshot({'title': 'Challenge',
                                     'visible_text': "Show us your human side...\nWe can't tell if you're a human or a bot.\nsecret-fingerprint",
                                     'controls': [{'name': 'session_token', 'value': 'secret-token'}]},
                                    'https://www.expedia.co.in/Hotel-Search?session=secret-query')
        self.assertTrue(result['challenge_detected'])
        self.assertNotIn('secret', json.dumps(result))
        self.assertEqual(result['controls'], [])

    def test_control_allowlist_discards_headers_and_sensitive_inputs(self):
        result = _sanitize_snapshot({'controls': [{'name': 'adults', 'value': '2', 'headers': {'cookie': 'secret'}},
                                                  {'name': 'email', 'value': 'secret@example.com'}]}, HOTEL['sources']['expedia']['url'])
        self.assertEqual(len(result['controls']), 1)
        self.assertNotIn('secret', json.dumps(result))

    def test_capture_write_preserves_append_only_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            first = _write_capture(fixture(), Path(directory))
            second = _write_capture(fixture(), Path(directory))
            self.assertNotEqual(first['artifact_path'], second['artifact_path'])
            self.assertEqual(first['artifact_sha256'], second['artifact_sha256'])
            self.assertEqual(len(list(Path(directory).glob('*.json'))), 2)

    def test_browser_exception_has_one_attempt_and_safe_error_type(self):
        with tempfile.TemporaryDirectory() as directory, patch('scrapling.fetchers.DynamicSession') as session:
            session.return_value.__enter__.return_value.fetch.side_effect = TimeoutError('secret transport data')
            result = capture('expedia', HOTEL, CONTEXT, output_dir=Path(directory))
            self.assertEqual(session.call_args.kwargs['retries'], 1)
            self.assertEqual(session.return_value.__enter__.return_value.fetch.call_count, 1)
            self.assertEqual(result['stop_reason'], 'browser_error')
            self.assertEqual(result['error_type'], 'TimeoutError')
            self.assertNotIn('secret', json.dumps(result))
            self.assertEqual(result['direct_requests'], 0)


if __name__ == '__main__':
    unittest.main()
