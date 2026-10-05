from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from compset.hotel_aketa import (SOURCE_URL, TRAVELERS, build_report, calendar_rows,
                                export_capture, partner_rows, price_value, requested_context)


def controls():
    return [{'aria_label': TRAVELERS, 'text': '1'},
            {'aria_label': 'Price displayedNightly total', 'text': 'Nightly total'},
            {'aria_label': None, 'text': 'Currency\u200bINR'},
            {'aria_label': 'Check-in', 'value': 'Mon, Sep 28'},
            {'aria_label': 'Check-out', 'value': 'Tue, Sep 29'}]


def snapshot(text, stage='calendar'):
    return {'title': 'Hotel Aketa - Google hotels', 'url': SOURCE_URL,
            'stage': stage, 'visible_text': text, 'controls': controls()}


def calendar_text():
    return ('September\n28\n₹4,626\n29\n₹4,898\n30\n₹5,450\nOctober\n' +
            '\n'.join(f'{day}\n₹10.2K' if day == 19 else f'{day}\n₹4,484' for day in range(1, 32)) +
            '\nNovember\nDecember\nJanuary 2027\nBest prices for 1-night stay\nNightly total\n')


def offers():
    return ('Hotel Aketa\nNightly total\nSponsored·Featured options\nBooking.com\n'
            'Superior Single Room\n1 single bed · 1 guest · breakfast\n₹11,730\nVisit site\n'
            'Deluxe King Room\n1 king bed · 2 guests · breakfast\n₹18,556\nVisit site\n'
            'Agoda\nFree Wi-Fi · Free breakfast · 1 guest\n₹6,066\nVisit site\n')


def capture():
    proof = snapshot('Adults\n1\nChildren\n0', 'party proof')
    proof['controls'] += [{'aria_label': 'Remove adult', 'disabled': True},
                          {'aria_label': 'Remove child', 'disabled': True}]
    return {'observed_at': '2026-09-28T05:15:00+00:00', 'browser_status': 200,
            'stop_reason': None, 'snapshots': [proof, snapshot(calendar_text()), snapshot(offers(), 'selected night')]}


class HotelAketaTests(unittest.TestCase):
    def setUp(self):
        self.context = requested_context('2026-09-28')

    def test_default_window_changes_at_indian_midnight_not_utc_midnight(self):
        for utc_instant, expected in [('2026-09-27T18:29:59+00:00', '2026-09-27'),
                                      ('2026-09-27T18:30:00+00:00', '2026-09-28')]:
            instant = datetime.fromisoformat(utc_instant)
            class FrozenDateTime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)
            with self.subTest(utc_instant=utc_instant), patch('compset.hotel_aketa.datetime', FrozenDateTime):
                context = requested_context()
                self.assertEqual(context['start_date'], expected)
                self.assertEqual(context['timezone'], 'Asia/Kolkata')

    def test_build_report_without_explicit_context_needs_no_iana_database(self):
        instant = datetime.fromisoformat('2026-09-27T18:30:00+00:00')
        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)
        with patch('compset.hotel_aketa.datetime', FrozenDateTime), patch(
                'zoneinfo.ZoneInfo', side_effect=RuntimeError('IANA timezone database unavailable')):
            report = build_report(capture())
        self.assertEqual(report['requested_context']['start_date'], '2026-09-28')
        self.assertEqual(report['summary']['calendar_price_rows'], 30)

    def test_exact_display_is_still_indicative_and_room_count_unknown(self):
        report = build_report(capture(), self.context)
        self.assertEqual(report['summary']['indicative_dates'], 30)
        self.assertEqual(report['summary']['quoted_dates'], 0)
        self.assertEqual(report['context']['rooms'], None)
        self.assertEqual(report['context']['requested_rooms'], 1)
        self.assertEqual(report['requested_context']['rooms'], 1)
        self.assertTrue(all(r['direct_supplier_quote'] is False for r in report['rates']))
        self.assertTrue(all(r['taxes_included'] is None for r in report['rates']))

    def test_abbreviated_prices_never_become_exact(self):
        parsed = price_value('₹10.2K')
        self.assertIsNone(parsed['amount'])
        self.assertEqual(parsed['approximate_amount'], 10200)
        self.assertEqual(parsed['display_amount'], '₹10.2K')
        for bad in ['₹0', '₹NaN', 'INR 10', '₹-10', None]:
            self.assertIsNone(price_value(bad))

    def test_year_anchor_and_one_night_are_required(self):
        for removed in ['January 2027', 'Best prices for 1-night stay']:
            s = snapshot(calendar_text().replace(removed, ''))
            self.assertEqual(calendar_rows(s, self.context, capture()['observed_at']), [])
        rows = calendar_rows(snapshot(calendar_text()), self.context, capture()['observed_at'])
        self.assertEqual(rows[0]['checkin'], '2026-09-28')
        self.assertEqual(rows[-1]['checkout'], '2026-10-28')

    def test_wrong_hotel_currency_or_party_cannot_supply_prices(self):
        for field, value in [('title', 'Another Hotel - Google hotels'), ('url', SOURCE_URL + '/other')]:
            s = snapshot(calendar_text()); s[field] = value
            self.assertEqual(calendar_rows(s, self.context, capture()['observed_at']), [])
        for label in ['Number of travelers. Current number of travelers is 2.', None]:
            s = snapshot(calendar_text()); s['controls'][0]['aria_label'] = label
            self.assertEqual(calendar_rows(s, self.context, capture()['observed_at']), [])
        s = snapshot(calendar_text()); s['controls'][2]['text'] = 'CurrencyUSD'
        self.assertEqual(calendar_rows(s, self.context, capture()['observed_at']), [])

    def test_unknown_is_never_sold_out(self):
        for change in [{'browser_status': 429}, {'stop_reason': 'challenge_detected'}, {'snapshots': []}]:
            c = capture(); c.update(change); report = build_report(c, self.context)
            self.assertEqual(report['summary']['unknown_dates'], 30)
            self.assertEqual(report['summary']['unavailable_dates'], 0)
            self.assertEqual(report['rates'], [])

    def test_future_party_proof_cannot_backfill_earlier_prices(self):
        c = capture(); c['snapshots'] = c['snapshots'][1:] + c['snapshots'][:1]
        report = build_report(c, self.context)
        self.assertEqual(report['rates'], [])

    def test_explicit_two_guest_room_is_excluded(self):
        rows = partner_rows(snapshot(offers()), self.context, capture()['observed_at'])
        self.assertEqual([(r['provider'], r['amount']) for r in rows], [('Booking.com', 11730), ('Agoda', 6066)])
        self.assertEqual(rows[0]['room_name'], 'Superior Single Room')
        self.assertEqual(rows[0]['meals'], 'breakfast')

    def test_unknown_provider_never_inherits_previous_provider(self):
        rows = partner_rows(snapshot(offers().replace('\nAgoda\n', '\nUnknownRooms.com\n')),
                            self.context, capture()['observed_at'])
        self.assertEqual([(r['provider'], r['amount']) for r in rows], [('Booking.com', 11730)])

    def test_negative_breakfast_text_is_not_an_inclusion(self):
        text = offers().replace('Free breakfast', 'Breakfast not included')
        rows = partner_rows(snapshot(text), self.context, capture()['observed_at'])
        agoda = next(r for r in rows if r['provider'] == 'Agoda')
        self.assertIsNone(agoda['meals'])
        self.assertIn('Breakfast not included', agoda['source_description'])

    def test_multinight_or_duplicate_date_inputs_are_rejected(self):
        for value in ['Wed, Sep 30', 'Tue, Oct 29']:
            s = snapshot(offers()); s['controls'][-1]['value'] = value
            self.assertEqual(partner_rows(s, self.context, capture()['observed_at']), [])
        s = snapshot(offers()); s['controls'].append(s['controls'][-1])
        self.assertEqual(partner_rows(s, self.context, capture()['observed_at']), [])

    def test_conflicting_calendar_observations_remove_only_that_date(self):
        c = capture(); c['snapshots'].append(snapshot(calendar_text().replace('₹4,898', '₹5,001'), 'changed'))
        report = build_report(c, self.context)
        self.assertEqual(report['summary']['calendar_price_rows'], 29)
        self.assertEqual(next(r for r in report['dates'] if r['checkin'] == '2026-09-29')['state'], 'unknown')

    def test_context_scalars_and_timezone_are_strict(self):
        for key, value in [('rooms', True), ('adults', 1.0), ('children', False), ('currency', 'AED')]:
            with self.assertRaises(ValueError):
                build_report(capture(), {**self.context, key: value})
        c = capture(); c['observed_at'] = '2026-09-28T05:00:00'
        with self.assertRaises(ValueError):
            build_report(c, self.context)

    def test_export_keeps_unknown_fields_empty_and_preserves_raw_display(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp); source = path / 'source.json'
            source.write_text(json.dumps(capture()), encoding='utf-8')
            report = export_capture(source, path / 'output', start_date='2026-09-28')
            csv = (path / 'output' / 'rates.csv').read_text(encoding='utf-8-sig')
            self.assertIn('₹10.2K', csv)
            self.assertEqual(len(report['dates']), 30)
            self.assertEqual(report['state'], 'complete_indicative_calendar')


if __name__ == '__main__':
    unittest.main()
