"""Finite job identity, shared lease, frozen context and no-network stage gates."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from compset import workspace_jobs as jobs


class WorkspaceJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.selection = {'run_id': 'a' * 24, 'subject': {'listing_id': '123'},
                          'context': {'listing_id': '123', 'currency': 'AED'},
                          'selected': [{'listing_id': '456'}]}
        self.write('compset-latest.json', self.selection)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding='utf-8')

    def start(self, dataset='aketa', mode='fresh'):
        return jobs.reserve_job(self.root, {'dataset_id': dataset, 'mode': mode})

    def calendar(self, **kwargs):
        report = {'state': 'complete', 'context': kwargs['context_override'], 'records': [],
                  'processed': 1, 'total': 1, 'direct_requests_this_run': 1, 'bootstrap_browser_visits': 1}
        kwargs['progress_fn'](report)
        return report

    def prices(self, **kwargs):
        report = {'state': 'partial', 'total_date_cells': 60, 'quoted_date_cells': 1, 'calendar_skipped_date_cells': 2,
                  'unknown_date_cells': 57, 'direct_requests_this_run': 1, 'bootstrap_browser_visits': 1}
        kwargs['progress_fn'](report)
        return report

    def test_read_is_idle_without_creating_job_or_network(self):
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))
        self.assertEqual(jobs.read_job(self.root)['state'], 'idle')
        self.assertEqual(before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*')))

    def test_unknown_fields_and_bad_dataset_are_rejected_before_claim(self):
        for values in ({'dataset_id': 'unknown'}, {'dataset_id': 'aketa', 'command': 'run'},
                       {'dataset_id': 'aketa', 'mode': []}, {'dataset_id': 'aketa', 'adults': 2}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                jobs.reserve_job(self.root, values)
        self.assertFalse((self.root / 'collection-lease.json').exists())

    def test_frozen_airbnb_context_and_membership_are_not_client_controlled(self):
        job = self.start('airbnb-compset')
        context = job['context']
        self.assertEqual((context['adults'], context['children'], context['infants'], context['pets']), (1, 0, 0, 0))
        self.assertEqual(context['currency'], 'AED')
        self.assertEqual((datetime.fromisoformat(context['end_date']) - datetime.fromisoformat(context['start_date'])).days, 30)
        saved = jobs._json(jobs._job_path(self.root, job['job_id']) / 'selection.json')
        self.assertEqual(saved, self.selection)

    def test_malformed_selection_and_missing_currency_fail_before_worker_claim(self):
        for mutation in ('subject', 'currency', 'run_id', 'duplicate_subject'):
            data = deepcopy(self.selection)
            if mutation == 'subject':
                data['subject'] = []
            elif mutation == 'currency':
                data['context'].pop('currency')
            elif mutation == 'run_id':
                data.pop('run_id')
            else:
                data['selected'].append({'listing_id': '123'})
            self.write('compset-latest.json', data)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.start('airbnb-compset')
            self.assertFalse((self.root / 'collection-lease.json').exists())

    def test_workspace_and_legacy_controls_share_lease_in_both_directions(self):
        job = self.start()
        with self.assertRaises(jobs.BusyError):
            jobs.reserve_legacy(self.root, {})
        with self.assertRaises(jobs.BusyError):
            self.start('airbnb-compset')
        jobs.fail_start(self.root, job['job_id'])
        legacy = jobs.reserve_legacy(self.root, {'listing_id': '123'})
        with self.assertRaises(jobs.BusyError):
            self.start()
        status = jobs.read_job(self.root)
        self.assertTrue(status['busy'])
        self.assertIsNone(status['job_id'])
        self.assertFalse(status['pause_supported'])
        self.assertEqual(status['progress'], {})
        jobs.finish_legacy(self.root, legacy)
        self.assertFalse(jobs.read_job(self.root)['busy'])

    def test_pause_requires_exact_active_job_and_survives_status_reload(self):
        job = self.start()
        for wrong in ('../wrong', 'b' * 32, None):
            with self.assertRaises(jobs.BusyError):
                jobs.request_pause(self.root, wrong)
        self.assertTrue(jobs.request_pause(self.root, job['job_id'])['pause_requested'])
        self.assertTrue(jobs.read_job(self.root)['pause_requested'])
        jobs.fail_start(self.root, job['job_id'])
        with self.assertRaises(jobs.BusyError):
            jobs.request_pause(self.root, job['job_id'])

    def test_resume_requires_previous_job_and_preserves_old_selection(self):
        with self.assertRaises(ValueError):
            self.start('airbnb-compset', 'resume')
        prior = self.start('airbnb-compset')
        jobs._finish(self.root, prior['job_id'], 'partial', 'partial')
        newer = deepcopy(self.selection)
        newer['selected'] = [{'listing_id': '789'}]
        self.write('compset-latest.json', newer)
        resumed = self.start('airbnb-compset', 'resume')
        plan = jobs._json(jobs._job_path(self.root, resumed['job_id']) / 'selection.json')
        self.assertEqual(plan['selected'], [{'listing_id': '456'}])
        self.assertEqual(resumed['context'], prior['context'])
        self.assertNotEqual(resumed['job_id'], prior['job_id'])

    def test_resume_expired_window_does_not_silently_retarget_today(self):
        job = self.start()
        jobs._finish(self.root, job['job_id'], 'partial', 'partial')
        path = jobs._job_path(self.root, job['job_id']) / 'job.json'
        value = jobs._json(path)
        value['collector_context']['start_date'] = '2000-01-01'
        path.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.start(mode='resume')
        self.assertFalse((self.root / 'collection-lease.json').exists())

    def test_stopped_calendar_only_allows_no_network_quote_checkpoint(self):
        job = self.start('airbnb-compset')
        def stopped(**kwargs):
            return {**self.calendar(**kwargs), 'state': 'stopped', 'stop_reason': 'access_or_rate_limit_429'}
        def no_network(**kwargs):
            self.assertEqual(kwargs['request_budget'], 0)
            self.assertEqual(kwargs['skip_network_reason'], 'access_or_rate_limit_429')
            self.assertFalse(kwargs['force_fresh'])
            return {**self.prices(**kwargs), 'state': 'stopped'}
        with patch('compset.nightly.collect_selected', side_effect=stopped), \
                patch('compset.one_night.collect_one_night', side_effect=no_network) as quote:
            result = jobs.run_worker(self.root, job['job_id'])
        self.assertEqual(result['state'], 'stopped')
        quote.assert_called_once()
        self.assertFalse(result['busy'])

    def test_successful_calendar_passes_frozen_plan_and_finite_fresh_budget(self):
        job = self.start('airbnb-compset')
        with patch('compset.nightly.collect_selected', side_effect=self.calendar) as calendar, \
                patch('compset.one_night.collect_one_night', side_effect=self.prices) as quotes, \
                patch.object(jobs.time, 'sleep') as pacing:
            result = jobs.run_worker(self.root, job['job_id'])
        self.assertEqual(calendar.call_args.kwargs['request_budget'], 100)
        self.assertEqual(quotes.call_args.kwargs['request_budget'], 100)
        self.assertTrue(calendar.call_args.kwargs['fresh'])
        self.assertTrue(quotes.call_args.kwargs['force_fresh'])
        self.assertEqual(calendar.call_args.kwargs['snapshot'], self.selection)
        self.assertEqual(quotes.call_args.kwargs['snapshot'], self.selection)
        self.assertEqual(quotes.call_args.kwargs['interval_seconds'], 3)
        self.assertEqual(result['state'], 'partial')
        self.assertEqual(result['progress']['prices_unknown_date_cells'], 57)
        pacing.assert_called_once_with(3)

    def test_recent_source_stop_cannot_be_bypassed_by_fresh_button(self):
        self.write('nightly-monitoring-latest.json', {'state': 'stopped', 'stop_reason': 'challenge_detected',
                                                     'updated_at': datetime.now(timezone.utc).isoformat()})
        job = self.start('airbnb-compset')
        with patch('compset.nightly.collect_selected') as calendar, patch('compset.one_night.collect_one_night') as quotes:
            result = jobs.run_worker(self.root, job['job_id'])
        self.assertEqual(result['state'], 'stopped')
        calendar.assert_not_called()
        quotes.assert_not_called()
        self.assertIn('cooldown', result['message'])

    def test_hotel_worker_bounds_and_old_report_archive_survive_partial(self):
        self.write('hotel-pipelines/latest.json', {'state': 'partial', 'old': 'evidence'})
        original = (self.root / 'hotel-pipelines/latest.json').read_bytes()
        job = self.start()
        def collect(**kwargs):
            self.assertTrue(kwargs['fresh'])
            self.assertTrue(kwargs['respect_cooldowns'])
            self.assertEqual(kwargs['request_budget'], 8)
            self.assertEqual(kwargs['interval_seconds'], 3)
            result = {'state': 'complete', 'summary': {'unknown_cells': 149}, 'capture_calls_this_run': 1}
            kwargs['progress_fn'](result)
            return result
        with patch('compset.hotel_jobs.run_pipeline', side_effect=collect):
            result = jobs.run_worker(self.root, job['job_id'])
        self.assertEqual(result['state'], 'partial')
        archive = jobs._job_path(self.root, job['job_id']) / 'before/hotel-pipelines-latest.json'
        self.assertEqual(archive.read_bytes(), original)

    def test_second_worker_cannot_execute_same_job(self):
        job = self.start()
        with patch('compset.hotel_jobs.run_pipeline', return_value={'state': 'partial', 'summary': {'unknown_cells': 1}}) as collector:
            jobs.run_worker(self.root, job['job_id'])
            with self.assertRaises(jobs.BusyError):
                jobs.run_worker(self.root, job['job_id'])
        collector.assert_called_once()

    def test_source_exception_preserves_checkpoint_and_releases_lease(self):
        job = self.start('airbnb-compset')
        with patch('compset.nightly.collect_selected', side_effect=RuntimeError('source problem')), \
                patch('compset.one_night.collect_one_night') as quotes:
            with self.assertRaises(RuntimeError):
                jobs.run_worker(self.root, job['job_id'])
        self.assertEqual(jobs.read_job(self.root)['state'], 'failed')
        self.assertFalse((self.root / 'collection-lease.json').exists())
        quotes.assert_not_called()

    def test_subprocess_launcher_has_fixed_command_and_one_hour_bound(self):
        job = self.start()
        with patch.object(jobs.subprocess, 'run') as process:
            process.return_value.returncode = 1
            jobs.launch_worker(self.root, job['job_id'])
        args, kwargs = process.call_args
        self.assertEqual(args[0][1:4], ['-m', 'compset', 'workspace-worker'])
        self.assertEqual(kwargs['timeout'], 3600)
        self.assertNotIn('shell', kwargs)
        self.assertEqual(jobs.read_job(self.root)['state'], 'failed')


if __name__ == '__main__':
    unittest.main()
