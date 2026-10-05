"""Contract tests derived from the observed Aketa Agoda room-grid and MMT canary."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from compset.hotel_mmt_agoda import (AGODA_URL, MMT_URL, ROOM_GRID, capture, parse,
                                     project_agoda_capture, _project_grid, _wait_for_agoda_result)


HOTEL = {'id': 'aketa-dehradun', 'name': 'Hotel Aketa', 'city': 'Dehradun',
         'sources': {'agoda': {'url': AGODA_URL, 'provider_id': '110205', 'verified': True},
                     'makemytrip': {'url': MMT_URL, 'provider_id': '202108231240265962', 'verified': True}}}
CONTEXT = {'hotel_id': HOTEL['id'], 'checkin': '2026-09-28', 'checkout': '2026-09-29',
           'start_date': '2026-09-28', 'days': 30, 'stay_nights': 1,
           'rooms': 1, 'adults': 1, 'children': 0, 'currency': 'INR'}


def fixture():
    return {'source': 'agoda', 'observed_at': '2026-09-28T05:40:05+00:00', 'browser_status': 200,
            'hotel_id': HOTEL['id'], 'source_url': AGODA_URL, 'stop_reason': None,
            'snapshots': [{'stage': 'after search', 'url': AGODA_URL,
                           'headings': ['Hotel Aketa Rajpur Road Dehradun, Dehradun'],
                           'controls': [{'aria_label': 'Price display in India Rupee'},
                                        {'id': 'check-in-box', 'aria_label': 'Check-in 28 Sep 2026 Monday'},
                                        {'id': 'check-out-box', 'aria_label': 'Check-out 29 Sep 2026 Tuesday'},
                                        {'id': 'occupancy-box', 'aria_label': 'Guests and rooms 1 adult 1 room'}]}],
            'network': [{'url': ROOM_GRID, 'status': 200, 'method': 'POST',
                         'request': {'propertyId': '110205', 'searchCriteria': {
                             'adults': 1, 'rooms': 1, 'childrenAges': [], 'durationType': 'nightly',
                             'checkIn': '2026-09-28', 'checkOut': '2026-09-29'}},
                         'response': {'propertyId': 110205, 'propertyName': 'Hotel Aketa Rajpur Road Dehradun, Dehradun ',
                                      'searchCriteriaDescription': 'Sep 28 - Sep 29, 1 guest',
                                      'isSoldOut': False, 'rooms': [{
                                          'typeId': 661829068, 'name': 'Premium Single Room', 'isSoldOut': False,
                                          'offers': [{
                                              'typeId': 661829068, 'isFit': True,
                                              'price': {'priceInfo': ['Per night before taxes'], 'final': {
                                                  'amount': '5,182', 'amountNumber': 5182.0, 'currency': '₹', 'text': '₹ 5,182'}},
                                              'occupancyItems': [{'text': '1 adult', 'occupancyTags': ['1 room']}],
                                              'benefits': [{'text': 'Breakfast Included', 'type': 'BENEFIT1'}],
                                              'policies': [{'name': 'Cancellation policy', 'descriptions': ['First night charge within 1 day.']},
                                                           {'name': 'Payment', 'descriptions': ['Book and pay now']}],
                                              'conditions': [{'type': 'SEASONAL_PROMOTION', 'text': 'MEMBERS ONLY'},
                                                             {'type': 'AUTO_APPLY_COUPON', 'text': 'AGODA_SPONSORED - ₹ 2,653 off!'}]}]}]}}]}


def offer(e):
    return e['network'][0]['response']['rooms'][0]['offers'][0]


class AgodaContractTests(unittest.TestCase):
    def test_observed_integer_price_remains_indicative_with_conditions(self):
        result = parse(fixture(), HOTEL, CONTEXT)
        self.assertEqual(result['status'], 'indicative')
        rate = result['rates'][0]
        self.assertEqual(rate['amount'], '5182.0')
        self.assertEqual(rate['precision'], 'displayed_integer')
        self.assertTrue(rate['context_verified'])
        self.assertFalse(rate['direct_supplier_quote'])
        self.assertFalse(rate['taxes_included'])
        self.assertIsNone(rate['fees_included'])
        self.assertTrue(rate['membership_required'])
        self.assertEqual(len(rate['discount_conditions']), 1)

    def test_observed_before_taxes_and_fees_price_remains_indicative(self):
        e = fixture()
        offer(e)['price'].update(priceInfo=['Per night before taxes & fees'])
        offer(e)['price']['final'].update(amount='5,169', amountNumber=5169.0, text='₹ 5,169')
        result = parse(e, HOTEL, CONTEXT)
        self.assertEqual(result['status'], 'indicative')
        self.assertEqual(len(result['rates']), 1)
        rate = result['rates'][0]
        self.assertEqual(rate['amount'], '5169.0')
        self.assertEqual(rate['amount_type'], 'ota_display_price')
        self.assertEqual(rate['source_amount_basis'], 'nightly_room_rate')
        self.assertEqual(rate['precision'], 'displayed_integer')
        self.assertFalse(rate['direct_supplier_quote'])
        self.assertFalse(rate['taxes_included'])
        self.assertFalse(rate['fees_included'])
        self.assertIsNone(rate['taxes'])
        self.assertIsNone(rate['fees'])
        self.assertTrue(rate['context_verified'])
        self.assertTrue(rate['membership_required'])
        self.assertEqual(len(rate['discount_conditions']), 1)

    def test_unknown_or_ambiguous_price_labels_remain_unknown(self):
        for label in [None, 'Per night before taxes & fees', [],
                      ['Per night after taxes & fees'], ['Total before taxes & fees'],
                      ['Per night before taxes & fees', 'Taxes included']]:
            with self.subTest(label=label):
                e = fixture(); offer(e)['price']['priceInfo'] = label
                result = parse(e, HOTEL, CONTEXT)
                self.assertEqual(result['status'], 'unknown')
                self.assertEqual(result['reason'], 'no_verified_offer_prices')
                self.assertEqual(result['rates'], [])

    def test_before_taxes_and_fees_requires_context_and_numeric_agreement(self):
        for mutator in [
                lambda e: e['network'][0]['request']['searchCriteria'].update(adults=2),
                lambda e: offer(e)['price']['final'].update(amount='5,183')]:
            e = fixture(); offer(e)['price']['priceInfo'] = ['Per night before taxes & fees']
            mutator(e)
            result = parse(e, HOTEL, CONTEXT)
            self.assertEqual(result['status'], 'unknown')
            self.assertEqual(result['rates'], [])

    def test_context_mutations_never_produce_rate(self):
        for field, value in [('adults', 2), ('adults', True), ('rooms', 2), ('childrenAges', [7]),
                             ('checkIn', '2026-10-02'), ('checkOut', '2026-09-30'), ('durationType', 'hourly')]:
            with self.subTest(field=field, value=value):
                e = fixture(); e['network'][0]['request']['searchCriteria'][field] = value
                self.assertEqual(parse(e, HOTEL, CONTEXT)['rates'], [])

    def test_wrong_property_or_response_context_never_produces_rate(self):
        for field, value in [('propertyId', 999), ('propertyName', 'Other Hotel'),
                             ('searchCriteriaDescription', 'Sep 28 - Sep 29, 2 guests')]:
            e = fixture(); e['network'][0]['response'][field] = value
            self.assertEqual(parse(e, HOTEL, CONTEXT)['rates'], [])

    def test_default_party_response_before_matching_stay_is_ignored(self):
        e = fixture(); initial = deepcopy(e['network'][0])
        initial['request']['searchCriteria']['adults'] = 2
        initial['response']['searchCriteriaDescription'] = 'Sep 28 - Sep 29, 2 guests'
        e['network'].insert(0, initial)
        self.assertEqual(len(parse(e, HOTEL, CONTEXT)['rates']), 1)

    def test_contradictory_property_availability_is_unknown(self):
        e = fixture(); e['network'][0]['response']['isSoldOut'] = True
        self.assertEqual(parse(e, HOTEL, CONTEXT)['rates'], [])

    def test_optional_fit_field_is_not_required_when_offer_occupancy_explicit(self):
        e = fixture(); offer(e).pop('isFit')
        offer(e)['benefits'].append({'type': 'AMENITIES', 'text': 'AGODA_SPONSORED - ₹ 2,653 off!'})
        result = parse(e, HOTEL, CONTEXT)
        self.assertEqual(len(result['rates']), 1)
        self.assertEqual(len(result['rates'][0]['discount_conditions']), 2)

    def test_child_promotion_does_not_change_verified_zero_child_request(self):
        e = fixture(); offer(e)['occupancyItems'].append({'text': 'Your kid can stay for FREE!'})
        result = parse(e, HOTEL, CONTEXT)
        self.assertEqual(len(result['rates']), 1)
        self.assertEqual(result['rates'][0]['observed_context']['children'], 0)
        self.assertEqual(len(result['rates'][0]['offer_occupancy']), 2)
        offer(e)['occupancyItems'].append({'text': '2 adults', 'occupancyTags': ['1 room']})
        self.assertEqual(parse(e, HOTEL, CONTEXT)['rates'], [])

    def test_missing_form_currency_and_changed_dates_are_unknown(self):
        for i in range(4):
            e = fixture(); e['snapshots'][0]['controls'].pop(i)
            self.assertEqual(parse(e, HOTEL, CONTEXT)['rates'], [])

    def test_alternate_two_adult_offer_not_laundered_into_request_party(self):
        e = fixture(); offer(e)['occupancyItems'][0]['text'] = '2 adults'
        self.assertEqual(parse(e, HOTEL, CONTEXT)['rates'], [])

    def test_empty_rooms_without_explicit_negative_remain_unknown(self):
        e = fixture(); e['network'][0]['response'].update(isSoldOut=False, rooms=[])
        result = parse(e, HOTEL, CONTEXT)
        self.assertEqual(result['rates'], [])
        self.assertEqual(result['status'], 'unknown')

    def test_source_proven_negative_exact_stay_is_unavailable(self):
        # Observed September 29 room-grid shape: boolean true and explicit empty rooms.
        e = fixture(); c = {**CONTEXT, 'checkin': '2026-09-29', 'checkout': '2026-09-30'}
        e['snapshots'][0]['controls'][1]['aria_label'] = 'Check-in 29 Sep 2026 Tuesday'
        e['snapshots'][0]['controls'][2]['aria_label'] = 'Check-out 30 Sep 2026 Wednesday'
        e['network'][0]['request']['searchCriteria'].update(checkIn=c['checkin'], checkOut=c['checkout'])
        e['network'][0]['response'].update(searchCriteriaDescription='Sep 29 - Sep 30, 1 guest', isSoldOut=True, rooms=[])
        result = parse(e, HOTEL, c)
        self.assertEqual(result['status'], 'unavailable')
        self.assertTrue(result['unavailability_verified'])
        self.assertEqual(result['reason'], 'source_unavailable_for_requested_stay')
        self.assertEqual(result['rates'], [])
        self.assertEqual(result['observed_context']['checkin'], '2026-09-29')
        self.assertEqual(result['observed_context']['rooms'], 1)

    def test_negative_with_wrong_context_or_untyped_flag_is_unknown(self):
        for mutator in [
                lambda e: e['network'][0]['request']['searchCriteria'].update(adults=2),
                lambda e: e['network'][0]['request']['searchCriteria'].update(childrenAges=[7]),
                lambda e: e['network'][0]['response'].update(propertyId=999),
                lambda e: e['network'][0]['response'].update(searchCriteriaDescription='Sep 28 - Sep 29, 2 guests'),
                lambda e: e['network'][0]['response'].update(isSoldOut='true'),
                lambda e: e['network'][0]['response'].update(isSoldOut=1),
                lambda e: e['snapshots'][0]['controls'].pop(0),
                lambda e: e['network'][0].update(status=429)]:
            e = fixture(); e['network'][0]['response'].update(isSoldOut=True, rooms=[])
            mutator(e)
            result = parse(e, HOTEL, CONTEXT)
            self.assertEqual(result['status'], 'unknown')
            self.assertFalse(result.get('unavailability_verified', False))

    def test_conflicting_available_and_unavailable_responses_are_unknown(self):
        e = fixture(); negative = deepcopy(e['network'][0])
        negative['response'].update(isSoldOut=True, rooms=[])
        e['network'].append(negative)
        result = parse(e, HOTEL, CONTEXT)
        self.assertEqual(result['rates'], [])
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['reason'], 'conflicting_stay_availability')

    def test_missing_rooms_schema_cannot_become_empty_inventory(self):
        e = fixture(); e['network'][0]['response']['isSoldOut'] = True
        e['network'][0]['response'].pop('rooms')
        projected = project_agoda_capture(e, HOTEL, CONTEXT)
        self.assertIsNone(projected['network'][0]['response']['rooms'])
        self.assertEqual(parse(projected, HOTEL, CONTEXT)['status'], 'unknown')

    def test_semantics_and_numeric_disagreement_are_rejected(self):
        for change in [{'amount': '5,183'}, {'amountNumber': 0}, {'amountNumber': True}, {'currency': '$'}]:
            e = fixture(); offer(e)['price']['final'].update(change)
            self.assertEqual(parse(e, HOTEL, CONTEXT)['rates'], [])
        e = fixture(); offer(e)['price']['priceInfo'] = ['Total for 3 nights']
        self.assertEqual(parse(e, HOTEL, CONTEXT)['rates'], [])

    def test_same_type_id_different_meal_plans_are_preserved(self):
        e = fixture(); variant = deepcopy(offer(e))
        variant['benefits'].append({'text': 'Lunch included', 'type': 'BENEFIT1'})
        variant['price']['final'].update(amount='5,802', amountNumber=5802.0)
        e['network'][0]['response']['rooms'][0]['offers'].append(variant)
        rows = parse(e, HOTEL, CONTEXT)['rates']
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]['product_variant_id'], rows[1]['product_variant_id'])
        self.assertIn('Lunch included', rows[1]['meals'])

    def test_same_product_conflicting_price_is_quarantined(self):
        e = fixture(); variant = deepcopy(offer(e))
        variant['price']['final'].update(amount='5,802', amountNumber=5802.0)
        e['network'][0]['response']['rooms'][0]['offers'].append(variant)
        self.assertEqual(parse(e, HOTEL, CONTEXT)['reason'], 'conflicting_duplicate_offer')

    def test_block_and_schema_failures_have_no_price(self):
        for change in [{'status': 429}, {'response_error': True}, {'response': None}, {'request': None}]:
            e = fixture(); e['network'][0].update(change)
            self.assertEqual(parse(e, HOTEL, CONTEXT)['rates'], [])
        e = fixture(); e['stop_reason'] = 'challenge_detected'
        self.assertEqual(parse(e, HOTEL, CONTEXT)['reason'], 'challenge_detected')

    def test_projection_removes_unneeded_values_and_graphql_queries(self):
        e = fixture(); e['network'][0]['request'].update(token='do-not-save', query='query private{}')
        offer(e)['bookingDetails'] = {'token': 'do-not-save', 'bookingUrl': 'https://example.com'}
        offer(e)['price']['final']['sessionId'] = 'do-not-save'
        p = project_agoda_capture(e, HOTEL, CONTEXT)
        self.assertNotIn('do-not-save', json.dumps(p))
        self.assertNotIn('query private', json.dumps(p))
        self.assertEqual(len(parse(p, HOTEL, CONTEXT)['rates']), 1)

    def test_malformed_nested_text_does_not_copy_arbitrary_objects(self):
        e = fixture(); offer(e)['name'] = {'secret': 'do-not-save'}
        p = project_agoda_capture(e, HOTEL, CONTEXT)
        self.assertNotIn('do-not-save', json.dumps(p))


class MmtDiagnosticTests(unittest.TestCase):
    def test_saved_diagnostic_reparse_has_zero_network_and_actual_old_context(self):
        prior = {'source_url': MMT_URL, 'observed_at': '2026-09-28T04:55:39+00:00',
                 'report': {'browser_status': 200},
                 'snapshots': [{'stage': 'after one-adult APPLY navigation', 'visible_text': '200-OK'}],
                 'returned_url_public_fields': [{'path': '$.query.' + k, 'value': v} for k, v in {
                     'checkin': '09282026', 'checkout': '09292026', 'hotelId': '202108231240265962',
                     'roomStayQualifier': '1e0e', 'rsc': '1e1e0e', '_uCurrency': 'INR'}.items()]}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'prior.json'; path.write_text(json.dumps(prior), encoding='utf-8')
            with patch('compset.hotel_mmt_agoda.MMT_PRIOR', path):
                e = capture('makemytrip', HOTEL, CONTEXT, output_dir=Path(temp) / 'out')
            result = parse(e, HOTEL, {**CONTEXT, 'checkin': '2026-09-29', 'checkout': '2026-09-30'})
        self.assertEqual(e['browser_navigations'], 0)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['observed_context']['checkin'], '2026-09-28')
        self.assertEqual(result['rates'], [])
        self.assertEqual(result['reason'], 'source_contract_unavailable')

    def test_missing_saved_diagnostic_is_unknown_not_live_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('compset.hotel_mmt_agoda.MMT_PRIOR', Path(temp) / 'missing.json'):
                e = capture('makemytrip', HOTEL, CONTEXT, output_dir=temp)
        self.assertEqual(e['browser_navigations'], 0)
        self.assertEqual(e['stop_reason'], 'prior_source_diagnostic_missing')

    def test_context_validation_precedes_capture(self):
        for change in [{'adults': True}, {'currency': 'USD'}, {'rooms': 2}, {'checkout': '2026-09-30'}]:
            with self.assertRaises(ValueError):
                capture('makemytrip', HOTEL, {**CONTEXT, **change}, output_dir='unused')


class AgodaCaptureWaitTests(unittest.TestCase):
    class Clock:
        def __init__(self):
            self.value = 0

        def __call__(self):
            return self.value

    class Handle:
        def __init__(self, value):
            self.value = value

        def json_value(self):
            return self.value

        def dispose(self):
            pass

    class Page:
        def __init__(self, clock, transitions):
            self.clock = clock
            self.transitions = iter(transitions)
            self.calls = []
            self.last_state = False

        def wait_for_function(self, function, *, arg, timeout):
            from playwright.sync_api import TimeoutError
            self.calls.append({'labels': arg, 'timeout': timeout})
            transition = next(self.transitions, None)
            if transition is not None:
                self.last_state = transition()
            if not self.last_state:
                self.clock.value += timeout / 1000
                raise TimeoutError('Current document is not ready')
            return AgodaCaptureWaitTests.Handle(self.last_state)

        def wait_for_timeout(self, timeout):
            self.clock.value += timeout / 1000

    def test_waits_for_new_document_and_exact_stay_response_after_navigation(self):
        clock = self.Clock()
        raw = {'network': [], 'stop_reason': None}
        wanted = fixture()['network'][0]
        initial = deepcopy(wanted)
        initial['request']['searchCriteria']['adults'] = 2

        def old_default_response():
            raw['network'].append(initial)
            return False  # New document is still empty after navigation.

        def current_form_only():
            return 'ready'  # A complete DOM is insufficient without the new JSON.

        def current_response():
            raw['network'].append(wanted)
            return 'ready'

        page = self.Page(clock, [old_default_response, current_form_only, current_response])
        self.assertTrue(_wait_for_agoda_result(page, raw, CONTEXT, clock=clock))
        self.assertEqual(len(page.calls), 3)
        self.assertEqual(page.calls[-1]['labels']['checkin'], 'Check-in 28 Sep 2026 Monday')
        self.assertIsNone(raw['stop_reason'])

    def test_missing_response_expires_instead_of_accepting_current_form(self):
        clock = self.Clock(); raw = {'network': [], 'stop_reason': None}
        page = self.Page(clock, [lambda: 'ready'])
        self.assertFalse(_wait_for_agoda_result(page, raw, CONTEXT, timeout_ms=600, clock=clock))
        self.assertEqual(raw['stop_reason'], 'submitted_result_timeout')
        self.assertLessEqual(clock.value, 0.601)

    def test_source_stop_during_wait_ends_without_another_search(self):
        clock = self.Clock(); raw = {'network': [], 'stop_reason': None}

        def blocked():
            raw['stop_reason'] = 'access_or_rate_limit_429'
            return 'ready'

        page = self.Page(clock, [blocked])
        self.assertFalse(_wait_for_agoda_result(page, raw, CONTEXT, clock=clock))
        self.assertEqual(len(page.calls), 1)
        self.assertEqual(raw['stop_reason'], 'access_or_rate_limit_429')

    def test_challenge_visible_during_render_is_not_waited_through(self):
        clock = self.Clock(); raw = {'network': [], 'stop_reason': None}
        page = self.Page(clock, [lambda: 'challenge'])
        self.assertFalse(_wait_for_agoda_result(page, raw, CONTEXT, clock=clock))
        self.assertEqual(raw['stop_reason'], 'challenge_detected')

    def test_empty_final_snapshot_cannot_borrow_earlier_valid_controls(self):
        e = fixture(); e['snapshots'][0]['stage'] = 'one adult selected'
        e['snapshots'].append({'stage': 'after search', 'url': AGODA_URL, 'headings': [], 'controls': []})
        result = parse(e, HOTEL, CONTEXT)
        self.assertEqual(result['rates'], [])
        self.assertEqual(result['reason'], 'currency_not_verified')


if __name__ == '__main__':
    unittest.main()
