"""Independent order008 proof: contexts, history, source isolation and coverage."""
from copy import deepcopy
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from compset.hotel_contracts import SEED, context_for, normalize_observation, stay_context
from compset import hotel_jobs, hotel_store


def seed():
    return deepcopy(SEED['hotels'][0])


def observation(hotel, source, context, *, priced=True):
    actual = {key: context[key] for key in (
        'hotel_id', 'checkin', 'checkout', 'rooms', 'adults', 'children', 'currency')}
    return {
        'hotel_id': hotel['id'], 'source': source,
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'requested_context': deepcopy(context), 'observed_context': actual,
        'status': 'quoted' if priced else 'unknown',
        'reason': None if priced else 'source_contract_not_observed',
        'rates': [{
            'hotel_id': hotel['id'], 'source': source, 'channel': source,
            'checkin': context['checkin'], 'checkout': context['checkout'],
            'currency': 'INR', 'amount': '4800.25', 'amount_type': 'one_night_stay_total',
            'observed_context': deepcopy(actual), 'context_verified': True,
            'direct_supplier_quote': True, 'precision': 'exact',
        }] if priced else [],
    }


class HotelPortfolioIndependentReviewTests(unittest.TestCase):
    def setUp(self):
        self.hotel = seed()
        self.context = stay_context(context_for(self.hotel))

    def test_context_type_and_identity_mutations_cannot_authorize_direct_price(self):
        original = observation(self.hotel, 'booking', self.context)
        baseline = deepcopy(original)
        for key, value in [('rooms', True), ('adults', 1.0), ('children', False),
                           ('currency', 'USD'), ('hotel_id', 'another-hotel'),
                           ('checkin', '2099-01-01')]:
            with self.subTest(field=key):
                item = deepcopy(original)
                item['rates'][0]['observed_context'][key] = value
                result = normalize_observation(item, self.hotel, 'booking', self.context)
                self.assertEqual(result['rates'], [])
        self.assertEqual(original, baseline)

    def test_conflicting_row_identity_is_rejected_not_overwritten(self):
        for key, value in [('hotel_id', 'another-hotel'), ('source', 'expedia'), ('channel', 'agoda')]:
            with self.subTest(field=key):
                item = observation(self.hotel, 'booking', self.context)
                item['rates'][0][key] = value
                result = normalize_observation(item, self.hotel, 'booking', self.context)
                self.assertEqual(result['rates'], [])

    def test_failed_observation_cannot_emit_prices(self):
        for status in ['blocked', 'error', 'unknown', 'not_requested']:
            with self.subTest(status=status):
                item = observation(self.hotel, 'booking', self.context)
                item.update(status=status, reason='access_or_contract_failure')
                result = normalize_observation(item, self.hotel, 'booking', self.context)
                self.assertEqual(result['rates'], [])

    def test_conflicting_requested_context_is_rejected(self):
        item = observation(self.hotel, 'booking', self.context)
        item['requested_context']['adults'] = 2
        try:
            result = normalize_observation(item, self.hotel, 'booking', self.context)
        except ValueError:
            return
        self.assertEqual(result['rates'], [])

    def test_invalid_direct_amounts_are_never_quotes(self):
        for amount in [None, True, 'NaN', 'Infinity', '-1', '0', '₹10.2K']:
            with self.subTest(amount=amount):
                item = observation(self.hotel, 'booking', self.context)
                item['rates'][0]['amount'] = amount
                result = normalize_observation(item, self.hotel, 'booking', self.context)
                self.assertEqual(result['rates'], [])

    def test_approximate_direct_amount_is_never_an_exact_quote(self):
        for change in [
            {'amount': None, 'approximate_amount': '10200', 'precision': 'abbreviated'},
            {'amount': '10200', 'approximate_amount': None, 'precision': 'abbreviated'},
        ]:
            with self.subTest(change=change):
                item = observation(self.hotel, 'booking', self.context)
                item['rates'][0].update(change)
                result = normalize_observation(item, self.hotel, 'booking', self.context)
                self.assertEqual(result['rates'], [])

    def test_direct_ota_display_with_verified_context_remains_indicative(self):
        item = observation(self.hotel, 'agoda', self.context)
        item['status'] = 'indicative'
        item['rates'][0].update(amount='5182', amount_type='ota_display_price',
            source_amount_basis='nightly_room_rate', precision='displayed_integer',
            direct_supplier_quote=False, taxes_included=False)
        result = normalize_observation(item, self.hotel, 'agoda', self.context)
        self.assertEqual(len(result['rates']), 1)
        self.assertFalse(result['rates'][0]['direct_supplier_quote'])
        report = hotel_jobs.build_report(self.hotel, context_for(self.hotel), [result], sources=('agoda',))
        self.assertEqual(report['summary']['quoted_cells'], 0)
        self.assertEqual(report['summary']['indicative_cells'], 1)
        self.assertEqual(report['summary']['unknown_cells'], 29)
        poisoned = deepcopy(item)
        poisoned['rates'][0]['observed_context']['rooms'] = 2
        self.assertEqual(normalize_observation(poisoned, self.hotel, 'agoda', self.context)['rates'], [])

    def test_verified_negative_requires_exact_actual_stay_and_typed_party(self):
        item = observation(self.hotel, 'agoda', self.context, priced=False)
        item.update(status='unavailable', reason='source_confirmed_no_offers', unavailability_verified=True)
        valid = normalize_observation(item, self.hotel, 'agoda', self.context)
        self.assertEqual(valid['status'], 'unavailable')
        self.assertTrue(valid['unavailability_verified'])
        for key, value in [('hotel_id', 'another-hotel'), ('rooms', True), ('adults', 2),
                           ('children', False), ('currency', 'USD'), ('checkin', '2099-01-01')]:
            with self.subTest(field=key):
                bad = deepcopy(item)
                bad['observed_context'][key] = value
                result = normalize_observation(bad, self.hotel, 'agoda', self.context)
                self.assertNotEqual(result['status'], 'unavailable')
                self.assertIsNot(result.get('unavailability_verified'), True)
        contradictory = observation(self.hotel, 'agoda', self.context)
        contradictory.update(status='unavailable', unavailability_verified=True)
        result = normalize_observation(contradictory, self.hotel, 'agoda', self.context)
        self.assertNotEqual(result['status'], 'unavailable')
        self.assertIsNot(result.get('unavailability_verified'), True)

    def test_verified_negative_covers_one_stay_only_and_does_not_stop_next_date(self):
        calls = []
        def capture(source, hotel, context, output):
            calls.append(context['checkin'])
            return {'source': source, 'observed_at': datetime.now(timezone.utc).isoformat()}
        def parse(raw, hotel, source, context):
            item = observation(hotel, source, context, priced=len(calls) > 1)
            if len(calls) == 1:
                item.update(status='unavailable', reason='source_confirmed_no_offers', unavailability_verified=True)
            return item
        with TemporaryDirectory() as tmp, patch('compset.hotel_jobs.parse_source', side_effect=parse), \
                patch('compset.hotel_jobs.parser_hash', return_value='parser-one'), \
                patch('compset.hotel_jobs.time.sleep'):
            report = hotel_jobs.run_pipeline(root=tmp, sources=('agoda',), live=True,
                request_budget=2, capture_fn=capture)
        self.assertEqual(len(calls), 2)
        self.assertEqual(report['summary']['unavailable_cells'], 1)
        self.assertEqual(report['summary']['quoted_cells'], 1)
        self.assertEqual(report['summary']['unknown_cells'], 28)
        self.assertEqual(sum(row['state'] == 'unavailable' for row in report['coverage']), 1)

    def test_sqlite_history_is_append_only_and_exact_repeats_are_idempotent(self):
        item = observation(self.hotel, 'booking', self.context)
        raw = {'source': 'booking', 'capture': 'one', 'requested_context': self.context}
        raw_copy = deepcopy(raw)
        with TemporaryDirectory() as tmp:
            first = hotel_store.record(tmp, raw, item, self.context, 'parser-one')
            same = hotel_store.record(tmp, raw, item, self.context, 'parser-one')
            self.assertEqual(first, same)
            revised = deepcopy(item)
            revised['rates'][0]['amount'] = '4801.25'
            second = hotel_store.record(tmp, raw, revised, self.context, 'parser-two')
            self.assertEqual(first['capture_id'], second['capture_id'])
            self.assertNotEqual(first['interpretation_id'], second['interpretation_id'])
            newer = {**raw, 'capture': 'two'}
            third = hotel_store.record(tmp, newer, revised, self.context, 'parser-two')
            self.assertNotEqual(first['capture_id'], third['capture_id'])
            with closing(sqlite3.connect(Path(tmp) / 'evidence.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM hotel_captures').fetchone()[0], 2)
                self.assertEqual(db.execute('SELECT count(*) FROM hotel_interpretations').fetchone()[0], 3)
                saved = json.loads(db.execute(
                    'SELECT observation_json FROM hotel_interpretations WHERE interpretation_id=?',
                    (first['interpretation_id'],)).fetchone()[0])
                self.assertEqual(saved['rates'][0]['amount'], '4800.25')
        self.assertEqual(raw, raw_copy)

    def test_cache_is_exact_context_bound_and_rejects_expired_or_future_evidence(self):
        stamp = datetime.now(timezone.utc)
        item = observation(self.hotel, 'booking', self.context)
        item['observed_at'] = stamp.isoformat()
        with TemporaryDirectory() as tmp:
            hotel_store.record(tmp, {'sentinel': 7}, item, self.context, 'parser-one')
            result = hotel_store.cached(tmp, self.hotel['id'], 'booking', self.context, now=stamp)
            self.assertEqual(result['raw'], {'sentinel': 7})
            for key, value in [('adults', 2), ('rooms', 2), ('currency', 'USD'),
                               ('checkin', '2099-01-01'), ('hotel_id', 'other')]:
                with self.subTest(field=key):
                    self.assertIsNone(hotel_store.cached(tmp, self.hotel['id'], 'booking',
                        {**self.context, key: value}, now=stamp))
            self.assertIsNone(hotel_store.cached(tmp, self.hotel['id'], 'expedia', self.context, now=stamp))
            self.assertIsNone(hotel_store.cached(tmp, 'other', 'booking', self.context, now=stamp))
            self.assertIsNone(hotel_store.cached(tmp, self.hotel['id'], 'booking', self.context,
                                                now=stamp + timedelta(hours=7)))
            self.assertIsNone(hotel_store.cached(tmp, self.hotel['id'], 'booking', self.context,
                                                now=stamp - timedelta(seconds=1)))

    def test_cached_raw_is_reparsed_by_current_parser_without_network(self):
        version = {'amount': '4800.25', 'parser': 'parser-one'}
        def parse(raw, hotel, source, context):
            item = observation(hotel, source, context)
            item['observed_at'] = raw['observed_at']
            item['rates'][0]['amount'] = version['amount']
            return item
        raw = {'source': 'booking', 'observed_at': datetime.now(timezone.utc).isoformat(), 'sentinel': 9}
        with TemporaryDirectory() as tmp, patch('compset.hotel_jobs.parse_source', side_effect=parse), \
                patch('compset.hotel_jobs.parser_hash', side_effect=lambda source: version['parser']):
            with patch('compset.hotel_jobs.capture_source', return_value=deepcopy(raw)) as capture:
                first = hotel_jobs.run_pipeline(root=tmp, sources=('booking',), live=True, request_budget=1)
                capture.assert_called_once()
            version.update(amount='4801.25', parser='parser-two')
            with patch('compset.hotel_jobs.capture_source') as capture:
                second = hotel_jobs.run_pipeline(root=tmp, sources=('booking',))
                capture.assert_not_called()
            self.assertEqual(first['rates'][0]['amount'], '4800.25')
            self.assertEqual(second['rates'][0]['amount'], '4801.25')
            self.assertTrue(second['observations'][0]['reused'])
            with closing(sqlite3.connect(Path(tmp) / 'evidence.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM hotel_captures').fetchone()[0], 1)
                self.assertEqual(db.execute('SELECT count(*) FROM hotel_interpretations').fetchone()[0], 2)
                self.assertEqual(json.loads(db.execute('SELECT raw_json FROM hotel_captures').fetchone()[0]), raw)

    def test_zero_budget_and_pause_keep_full_unknown_grid_and_never_capture(self):
        with TemporaryDirectory() as tmp:
            with patch('compset.hotel_jobs.capture_source') as capture:
                report = hotel_jobs.run_pipeline(root=tmp)
                capture.assert_not_called()
            self.assertEqual(report['summary']['date_cells'], 150)
            self.assertEqual(report['summary']['unknown_cells'], 150)
            self.assertEqual(report['summary']['quoted_cells'], 0)
            self.assertFalse((Path(tmp) / 'running.lock').exists())
            (Path(tmp) / 'pause.flag').touch()
            with patch('compset.hotel_jobs.capture_source') as capture:
                report = hotel_jobs.run_pipeline(root=tmp, live=True, request_budget=5)
                capture.assert_not_called()
            self.assertEqual(report['state'], 'paused')
            self.assertEqual(report['summary']['unknown_cells'], 150)

    def test_source_capture_failure_does_not_abort_other_sources(self):
        calls = []
        def capture(source, hotel, context, output):
            calls.append(source)
            if source == 'booking':
                raise TimeoutError('fixture timeout')
            return {'fixture': True}
        def parse(raw, hotel, source, context):
            return observation(hotel, source, context, priced=False)
        with TemporaryDirectory() as tmp, patch('compset.hotel_jobs.parse_source', side_effect=parse), \
                patch('compset.hotel_jobs.parser_hash', return_value='parser-one'), \
                patch('compset.hotel_jobs.time.sleep'):
            report = hotel_jobs.run_pipeline(root=tmp, sources=('booking', 'expedia'), live=True,
                request_budget=2, capture_fn=capture)
        self.assertEqual(calls, ['booking', 'expedia'])
        self.assertEqual(report['capture_calls_this_run'], 2)
        self.assertEqual(report['summary']['unknown_cells'], 60)
        self.assertEqual(report['summary']['quoted_cells'], 0)

    def test_parser_shape_error_is_isolated_and_failed_raw_remains_reparsable(self):
        def capture(source, hotel, context, output):
            return {'source': source, 'fixture': 'changed_shape'}
        def parse(raw, hotel, source, context):
            if source == 'booking':
                raise AttributeError('changed source structure')
            return observation(hotel, source, context, priced=False)
        with TemporaryDirectory() as tmp, patch('compset.hotel_jobs.parse_source', side_effect=parse), \
                patch('compset.hotel_jobs.parser_hash', return_value='parser-one'), \
                patch('compset.hotel_jobs.time.sleep'):
            report = hotel_jobs.run_pipeline(root=tmp, sources=('booking', 'expedia'), live=True,
                request_budget=2, capture_fn=capture)
            self.assertEqual({r['source'] for r in report['observations']}, {'booking', 'expedia'})
            self.assertEqual(report['summary']['unknown_cells'], 60)
            raw_files = list((Path(tmp) / 'raw').glob('*.json'))
            self.assertEqual(len(raw_files), 2)
            with closing(sqlite3.connect(Path(tmp) / 'evidence.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM hotel_captures').fetchone()[0], 2)

    def test_non_object_raw_does_not_make_failure_handler_abort_other_sources(self):
        def capture(source, hotel, context, output):
            return [] if source == 'booking' else {'source': source}
        def parse(raw, hotel, source, context):
            raw.get('source')  # The source changed from an object to an array.
            return observation(hotel, source, context, priced=False)
        with TemporaryDirectory() as tmp, patch('compset.hotel_jobs.parse_source', side_effect=parse), \
                patch('compset.hotel_jobs.parser_hash', return_value='parser-one'), \
                patch('compset.hotel_jobs.time.sleep'):
            report = hotel_jobs.run_pipeline(root=tmp, sources=('booking', 'expedia'), live=True,
                request_budget=2, capture_fn=capture)
        self.assertEqual({r['source'] for r in report['observations']}, {'booking', 'expedia'})
        self.assertEqual(report['summary']['unknown_cells'], 60)

    def test_each_source_receives_a_canary_before_first_source_spends_budget(self):
        sources = ('makemytrip', 'booking', 'expedia', 'agoda')
        calls = []
        def capture(source, hotel, context, output):
            calls.append(source)
            return {'fixture': True}
        def parse(raw, hotel, source, context):
            return observation(hotel, source, context)
        with TemporaryDirectory() as tmp, patch('compset.hotel_jobs.parse_source', side_effect=parse), \
                patch('compset.hotel_jobs.parser_hash', return_value='parser-one'), \
                patch('compset.hotel_jobs.time.sleep'):
            report = hotel_jobs.run_pipeline(root=tmp, sources=sources, live=True,
                request_budget=4, capture_fn=capture)
        self.assertEqual(calls, list(sources))
        self.assertEqual(report['capture_calls_this_run'], 4)
        self.assertEqual(report['summary']['date_cells'], 120)


if __name__ == '__main__':
    unittest.main()
