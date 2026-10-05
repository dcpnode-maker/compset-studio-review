from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from compset.google_calendar_network import (decode_rpc, project_calendar, compare_calendar,
                                              safe_leaf, verified_replay_frame,
                                              observation_for_index, write_replay)


def row():
    values = [None] * 16
    values[1] = ['₹4,453', None, 4452.5, None, 4453]
    values[8] = [[2026, 10, 13], [2026, 10, 14], 1, None, 0]
    values[15] = 'INR'
    return values


class GoogleCalendarNetworkTests(unittest.TestCase):
    def test_framed_json_is_decoded_without_evaluating_strings(self):
        envelope = json.dumps([['wrb.fr', 'observedRpc', json.dumps([1, 2]), None]])
        self.assertEqual(decode_rpc(")]}'\n\n" + str(len(envelope)) + '\n' + envelope),
                         [{'rpc_id':'observedRpc', 'payload':[1,2]}])

    def test_live_observed_layout_keeps_display_rounding_and_unknown_inclusions(self):
        values = project_calendar([[[2026, 9, 30], [2026, 10, 31], 1], [row()]])
        self.assertEqual(values[0]['amount'], 4453)
        self.assertEqual(values[0]['observed_money_fields'][2], 4452.5)
        self.assertIs(values[0]['taxes_included'], None)
        self.assertIs(values[0]['direct_supplier_quote'], False)
        report = {'rates':[{'amount_type':'google_calendar_minimum','checkin':'2026-10-13','amount':4453}]}
        self.assertTrue(compare_calendar(values, report)['all_displayed_dates_match'])

    def test_context_drift_missing_price_and_multinight_do_not_supply_prices(self):
        for change in ('currency', 'display', 'stay', 'date_scalar', 'price_scalar'):
            values = row()
            if change == 'currency': values[15] = 'USD'
            elif change == 'display': values[1][0] = '₹5,000'
            elif change == 'stay': values[8][1][2] = 15
            elif change == 'date_scalar': values[8][0][0] = True
            else: values[1][4] = None
            self.assertEqual(project_calendar([None,[values]]), [], change)

    def test_rounded_raw_value_cannot_authorize_mismatching_exported_amount(self):
        values = row()
        values[1] = ['₹4,452', None, 4452.5, None, 4452]
        rates = project_calendar([None, [values]])
        report = {'rates':[{'amount_type':'google_calendar_minimum','checkin':'2026-10-13','amount':4453}]}
        comparison = compare_calendar(rates, report)
        self.assertEqual(comparison['matched_dates'], 0)
        self.assertFalse(comparison['all_displayed_dates_match'])
        self.assertTrue(any(d['matched_dates'] == 1 for d in comparison['rounding_diagnostics']))

    def test_unproven_hotel_identity_prevents_api_export_even_with_matching_prices(self):
        frame = {'display_comparison':{'all_displayed_dates_match':True}}
        replay = {'status':200, 'frames':[frame]}
        for evidence in ({}, {'request_contains_known_hotel_entity':False},
                         {'request_contains_known_hotel_entity':'true'}):
            self.assertIsNone(verified_replay_frame(replay, evidence))
        self.assertIs(verified_replay_frame(replay, {'request_contains_known_hotel_entity':True}), frame)

    def test_parse_error_entries_cannot_shift_the_request_identity_evidence(self):
        wrong = {'index':None, 'parse_error':'ValueError', 'request_contains_known_hotel_entity':True}
        actual = {'index':0, 'request_contains_known_hotel_entity':False}
        selected = observation_for_index([wrong, actual], 0)
        self.assertIs(selected, actual)
        replay = {'status':200,'frames':[{'display_comparison':{'all_displayed_dates_match':True}}]}
        self.assertIsNone(verified_replay_frame(replay, selected))
        self.assertEqual(observation_for_index([wrong], 0), {})
        self.assertEqual(observation_for_index([actual, actual], 0), {})

    def test_access_limit_reason_is_persisted_without_changing_rendered_evidence(self):
        rendered = {'state':'complete_indicative_calendar','stop_reason':None}
        with tempfile.TemporaryDirectory() as tmp:
            for status in (401, 403, 429):
                with self.subTest(status=status):
                    path = Path(tmp)/f'replay-{status}.json'
                    write_replay(path, {'status':status,'frames':[]})
                    self.assertEqual(json.loads(path.read_text())['stop_reason'],
                                     f'access_or_rate_limit_{status}')
        self.assertEqual(rendered, {'state':'complete_indicative_calendar','stop_reason':None})

    def test_conflicting_date_prices_are_dropped(self):
        other = deepcopy(row()); other[1] = ['₹5,000',None,4999.6,None,5000]
        self.assertEqual(project_calendar([None,[row(),other]]), [])

    def test_sanitizer_redacts_unrelated_opaque_strings(self):
        self.assertEqual(safe_leaf(['opaque-session-value','INR','₹4,453']),
                         ['<string:20>', 'INR','₹4,453'])


if __name__ == '__main__':
    unittest.main()
