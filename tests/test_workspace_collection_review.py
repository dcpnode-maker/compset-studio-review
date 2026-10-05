"""Independent Order011 collection boundary proof; no live source requests."""
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from contextlib import closing
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from compset import server

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceJobIndependentReviewTests(unittest.TestCase):
    def setUp(self):
        from compset import workspace_jobs
        self.jobs = workspace_jobs
        self.directory = TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.snapshot = {'run_id': 'independent-audit', 'context': {'listing_id': '101', 'currency': 'AED'},
                         'subject': {'listing_id': '101'}, 'selected': [{'listing_id': '102'}]}
        self.save('compset-latest.json', self.snapshot)

    def save(self, name, value):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def reserve(self, dataset='aketa', mode='fresh'):
        return self.jobs.reserve_job(self.root, {'dataset_id': dataset, 'mode': mode})

    def test_concurrent_reservations_have_one_winner_and_one_durable_identity(self):
        barrier = threading.Barrier(2)
        def request():
            barrier.wait(timeout=5)
            try:
                return self.reserve()
            except self.jobs.BusyError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: request(), range(2)))
        winners = [x for x in results if x]
        self.assertEqual(len(winners), 1)
        self.assertEqual(self.jobs.read_job(self.root)['job_id'], winners[0]['job_id'])
        self.assertEqual(len(list((self.root / 'workspace-jobs').glob('*/job.json'))), 1)

    def test_shared_lease_blocks_workspace_and_legacy_in_both_directions(self):
        legacy = self.jobs.reserve_legacy(self.root, {'listing_id': '101', 'adults': 1})
        with self.assertRaises(self.jobs.BusyError):
            self.reserve()
        status = self.jobs.read_job(self.root)
        self.assertTrue(status['legacy']); self.assertTrue(status['busy'])
        self.assertFalse(status['pause_supported']); self.assertIsNone(status['job_id'])
        self.jobs.finish_legacy(self.root, 'other-owner')
        self.assertTrue(self.jobs.read_job(self.root)['busy'])
        self.jobs.finish_legacy(self.root, legacy)
        job = self.reserve()
        with self.assertRaises(self.jobs.BusyError):
            self.jobs.reserve_legacy(self.root, {})
        self.assertEqual(self.jobs.read_job(self.root)['job_id'], job['job_id'])

    def test_pause_is_identity_scoped_and_duplicate_worker_cannot_start(self):
        job = self.reserve()
        with self.assertRaises(self.jobs.BusyError):
            self.jobs.request_pause(self.root, '0' * 32)
        self.assertFalse(self.jobs.read_job(self.root)['pause_requested'])
        paused = self.jobs.request_pause(self.root, job['job_id'])
        self.assertTrue(paused['pause_requested'])
        folder = self.root / 'workspace-jobs' / job['job_id']
        (folder / 'worker.started').touch()
        with patch('compset.hotel_jobs.run_pipeline') as collector:
            with self.assertRaises(self.jobs.BusyError):
                self.jobs.run_worker(self.root, job['job_id'])
            collector.assert_not_called()

    def test_resume_requires_prior_job_and_preserves_frozen_cohort_after_saved_edit(self):
        with self.assertRaises(ValueError):
            self.reserve('airbnb-compset', 'resume')
        job = self.reserve('airbnb-compset')
        self.jobs._finish(self.root, job['job_id'], 'partial', 'Fixture budget ended')
        self.snapshot['selected'] = [{'listing_id': '999'}]
        self.snapshot['context']['currency'] = 'USD'
        self.save('compset-latest.json', self.snapshot)
        resumed = self.reserve('airbnb-compset', 'resume')
        self.assertNotEqual(resumed['job_id'], job['job_id'])
        self.assertEqual(resumed['context'], job['context'])
        saved = json.loads((self.root / 'workspace-jobs' / resumed['job_id'] / 'selection.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['selected'], [{'listing_id': '102'}])
        self.assertEqual(saved['context']['currency'], 'AED')

    def test_stopped_calendar_only_publishes_zero_network_quote_checkpoint(self):
        job = self.reserve('airbnb-compset')
        calendar = {'state': 'stopped', 'stop_reason': 'access_or_rate_limit_429',
                    'context': job['context'], 'records': []}
        def no_network_quote(**kwargs):
            self.assertEqual(kwargs['request_budget'], 0)
            self.assertEqual(kwargs['skip_network_reason'], 'access_or_rate_limit_429')
            self.assertEqual(kwargs['job_id'], job['job_id'])
            self.assertEqual(kwargs['calendar_report'], calendar)
            self.assertEqual(kwargs['context_override']['currency'], 'AED')
            return {'state': 'stopped', 'quoted_date_cells': 0, 'unknown_date_cells': 60}
        with patch('compset.nightly.collect_selected', return_value=calendar) as calendars, \
                patch('compset.one_night.collect_one_night', side_effect=no_network_quote) as quotes, \
                patch('compset.collect.collect') as browser:
            result = self.jobs.run_worker(self.root, job['job_id'])
            calendars.assert_called_once(); quotes.assert_called_once(); browser.assert_not_called()
        self.assertEqual(result['state'], 'stopped')
        self.assertFalse((self.root / 'collection-lease.json').exists())

    def test_recent_airbnb_access_stop_cannot_be_bypassed_by_fresh_or_relabels_previous_data(self):
        report = {'state': 'stopped', 'stop_reason': 'access_or_rate_limit_403',
                  'updated_at': datetime.now(timezone.utc).isoformat(), 'context': {'adults': 1},
                  'records': [{'review': 'earlier evidence retained'}]}
        self.save('one-night-latest.json', report)
        before = (self.root / 'one-night-latest.json').read_bytes()
        job = self.reserve('airbnb-compset')
        with patch('compset.nightly.collect_selected') as calendars, \
                patch('compset.one_night.collect_one_night') as quotes:
            result = self.jobs.run_worker(self.root, job['job_id'])
            calendars.assert_not_called(); quotes.assert_not_called()
        self.assertEqual(result['state'], 'stopped')
        self.assertIn('cooldown', result['message'])
        self.assertEqual((self.root / 'one-night-latest.json').read_bytes(), before)

    def test_pause_arriving_during_interphase_pacing_prevents_quote_transport(self):
        job = self.reserve('airbnb-compset')
        calendar = {'state': 'complete', 'context': job['context'], 'records': []}
        def pause_during_wait(seconds):
            self.assertGreaterEqual(seconds, 3)
            self.jobs.request_pause(self.root, job['job_id'])
        def checkpoint_only(**kwargs):
            self.assertEqual(kwargs['request_budget'], 0)
            self.assertEqual(kwargs['skip_network_reason'], 'pause_requested')
            self.assertFalse(kwargs['force_fresh'])
            return {'state': 'paused', 'quoted_date_cells': 0, 'unknown_date_cells': 60}
        with patch('compset.nightly.collect_selected', return_value=calendar), \
                patch('compset.workspace_jobs.time.sleep', side_effect=pause_during_wait) as sleep, \
                patch('compset.one_night.collect_one_night', side_effect=checkpoint_only), \
                patch('compset.collect.collect') as browser:
            result = self.jobs.run_worker(self.root, job['job_id'])
            sleep.assert_called_once(); browser.assert_not_called()
        self.assertEqual(result['state'], 'paused')

    def test_progress_uses_current_job_callback_not_previous_source_job_counts(self):
        self.save('hotel-pipelines/latest.json', {'state': 'complete', 'job_id': 'old-job',
                 'summary': {'unknown_cells': 0, 'quoted_cells': 150}, 'capture_calls_this_run': 999})
        job = self.reserve()
        def bounded(**kwargs):
            self.assertEqual(kwargs['request_budget'], 8); self.assertEqual(kwargs['interval_seconds'], 3)
            self.assertTrue(kwargs['fresh']); self.assertTrue(kwargs['respect_cooldowns'])
            result = {'state': 'complete', 'capture_calls_this_run': 1,
                      'summary': {'unknown_cells': 149, 'quoted_cells': 1}}
            kwargs['progress_fn'](result)
            return result
        with patch('compset.hotel_jobs.run_pipeline', side_effect=bounded):
            result = self.jobs.run_worker(self.root, job['job_id'])
        self.assertEqual(result['state'], 'partial')
        self.assertEqual(result['job_id'], job['job_id'])
        self.assertEqual(result['progress']['prices_capture_calls_this_run'], 1)
        self.assertEqual(result['progress']['coverage']['unknown_cells'], 149)
        self.assertNotIn('999', json.dumps(result))
        self.assertTrue((self.root / 'workspace-jobs' / job['job_id'] / 'before' / 'hotel-pipelines-latest.json').exists())

    def test_interrupted_worker_is_visible_and_new_reservation_never_stops_live_owner(self):
        job = self.reserve()
        with patch('compset.workspace_jobs._alive', return_value=False):
            status = self.jobs.read_job(self.root)
            self.assertEqual(status['state'], 'interrupted')
            replacement = self.reserve()
        self.assertNotEqual(replacement['job_id'], job['job_id'])
        old = json.loads((self.root / 'workspace-jobs' / job['job_id'] / 'job.json').read_text(encoding='utf-8'))
        self.assertEqual(old['state'], 'interrupted')
        with self.assertRaises(self.jobs.BusyError):
            self.reserve()


class WorkspaceCollectorFlowIndependentReviewTests(unittest.TestCase):
    def test_resumed_subject_bootstrap_has_actual_source_time_not_original_job_time(self):
        from datetime import timedelta
        from compset.nightly import collect_selected
        from compset.one_night import plan_quotes
        from tests.test_nightly import bootstrap, CalendarSession
        from tests.test_one_night_job import setup_sources
        with TemporaryDirectory() as directory:
            root = Path(directory); original = setup_sources(root)
            snapshot = json.loads((root / 'compset-latest.json').read_text(encoding='utf-8'))
            latest = json.loads((root / 'latest.json').read_text(encoding='utf-8'))
            source = json.loads((root / 'runs' / latest['run_id'] / 'source.json').read_text(encoding='utf-8'))
            old_context = {**original, 'observed_at': (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()}
            captured = []
            def capture(context, **kwargs):
                captured.append(deepcopy(context))
                result = bootstrap(context, **kwargs)
                payloads = deepcopy(source['payloads'])
                for payload in payloads:
                    payload['request_context']['locale'] = context['locale']
                result['payloads'] = payloads
                return result
            CalendarSession.calls = 0; CalendarSession.status = 200; CalendarSession.unknown = False
            with patch('compset.collect.collect', side_effect=capture), \
                    patch('scrapling.fetchers.FetcherSession', CalendarSession), patch('compset.nightly.time.sleep'):
                report = collect_selected(data_dir=root, request_budget=1, snapshot=snapshot,
                                          context_override=old_context, job_id='b' * 32)
            actual = datetime.fromisoformat(captured[0]['observed_at'])
            self.assertLess((datetime.now(timezone.utc) - actual).total_seconds(), 60)
            self.assertNotEqual(captured[0]['observed_at'], old_context['observed_at'])
            self.assertEqual(captured[0]['start_date'], old_context['start_date'])
            self.assertEqual(captured[0]['adults'], old_context['adults'])
            _, _, plan = plan_quotes(root, snapshot=snapshot, calendar_report=report, context_override=old_context)
            self.assertEqual(plan[0]['calendar_run_id'], report['subject_record']['run_id'])
            self.assertNotEqual(plan[0]['preflight']['reason'], 'fresh_calendar_not_observed')

    def test_quote_resume_reuses_verified_raw_but_fresh_requests_again_and_preserves_history(self):
        from compset.one_night import collect_one_night
        from tests.test_one_night_job import setup_sources, quote_bootstrap
        with TemporaryDirectory() as directory:
            root = Path(directory); setup_sources(root)
            with patch('compset.collect.collect', side_effect=quote_bootstrap) as browser, \
                    patch('scrapling.fetchers.FetcherSession'):
                first = collect_one_night(data_dir=root, request_budget=1)
                self.assertEqual(browser.call_count, 1)
            old_run = next(r['run_id'] for r in first['records'] if r['status'] == 'quoted')
            old_source = (root / 'runs' / old_run / 'source.json').read_bytes()
            with patch('compset.collect.collect') as browser:
                resumed = collect_one_night(data_dir=root, request_budget=1)
                browser.assert_not_called()
            self.assertEqual(resumed['quoted_date_cells'], 1)
            with patch('compset.collect.collect', side_effect=quote_bootstrap) as browser, \
                    patch('scrapling.fetchers.FetcherSession'):
                fresh = collect_one_night(data_dir=root, request_budget=1, force_fresh=True)
                browser.assert_called_once()
            new_run = next(r['run_id'] for r in fresh['records'] if r['status'] == 'quoted')
            self.assertNotEqual(old_run, new_run)
            self.assertEqual((root / 'runs' / old_run / 'source.json').read_bytes(), old_source)
            with closing(sqlite3.connect(root / 'compset.sqlite3')) as db:
                count = db.execute("SELECT COUNT(DISTINCT run_id) FROM observations WHERE kind='one_night_quote'").fetchone()[0]
                self.assertEqual(count, 2)

    def test_current_subject_calendar_block_supersedes_old_latest_subject_before_quotes(self):
        from compset.one_night import plan_quotes, collect_one_night
        from compset.pipeline import build_result, persist
        from tests.test_one_night_job import setup_sources
        with TemporaryDirectory() as directory:
            root = Path(directory); setup_sources(root)
            old_latest = (root / 'latest.json').read_bytes()
            old = json.loads(old_latest)
            source = json.loads((root / 'runs' / old['run_id'] / 'source.json').read_text(encoding='utf-8'))
            context = source.pop('context')
            context['observed_at'] = datetime.now(timezone.utc).isoformat()
            for day in source['payloads'][0]['body']['data']['merlin']['pdpAvailabilityCalendar']['calendarMonths'][0]['days']:
                day['available'] = False
            parsed = build_result(source, context); persist(source, parsed, root, update_latest=False)
            calendar = json.loads((root / 'nightly-monitoring-latest.json').read_text(encoding='utf-8'))
            calendar['subject_record'] = {'listing_id': context['listing_id'], 'run_id': parsed['run_id']}
            _, _, plan = plan_quotes(root, calendar_report=calendar)
            self.assertEqual(plan[0]['preflight']['reason'], 'sleeping_night_unavailable')
            self.assertEqual(plan[0]['calendar_run_id'], parsed['run_id'])
            with patch('compset.collect.collect') as browser:
                result = collect_one_night(data_dir=root, calendar_report=calendar, request_budget=1, force_fresh=True)
                browser.assert_not_called()
            self.assertEqual(result['calendar_skipped_date_cells'], 60)
            self.assertEqual((root / 'latest.json').read_bytes(), old_latest)

    def test_calendar_fresh_bypasses_valid_cache_resume_retains_subject_record_and_paces(self):
        from compset.nightly import collect_selected
        from tests.test_nightly import setup_snapshot, bootstrap, CalendarSession
        from datetime import date, timedelta
        def full_bootstrap(context, **kwargs):
            capture = bootstrap(context, **kwargs)
            start = date.fromisoformat(context['start_date'])
            days = [{'calendarDate': str(start + timedelta(days=i)), 'available': True,
                     'availableForCheckin': True, 'availableForCheckout': True, 'minNights': 1} for i in range(31)]
            capture['payloads'] = [{'source_url': 'https://www.airbnb.com/api/v3/PdpAvailabilityCalendar/hash',
                'status': 200, 'request_context': {'listing_id': context['listing_id'], 'currency': context['currency'],
                'locale': context['locale'], 'calendar_year': start.year, 'calendar_month': start.month, 'calendar_month_count': 2},
                'body': {'data': {'merlin': {'pdpAvailabilityCalendar': {'calendarMonths': [
                    {'listingId': context['listing_id'], 'days': days}]}}}}}]
            return capture
        with TemporaryDirectory() as directory:
            root = Path(directory); setup_snapshot(root, 1)
            CalendarSession.calls = 0; CalendarSession.status = 200; CalendarSession.unknown = False
            with patch('compset.collect.collect', side_effect=full_bootstrap) as browser, \
                    patch('scrapling.fetchers.FetcherSession', CalendarSession), patch('compset.nightly.time.sleep') as sleep:
                first = collect_selected(data_dir=root, request_budget=1, fresh=True)
                self.assertEqual(browser.call_count, 1); self.assertEqual(CalendarSession.calls, 1)
                self.assertTrue(sleep.called)
                self.assertTrue(all(0 <= call.args[0] <= 3 for call in sleep.call_args_list))
            with patch('compset.collect.collect') as browser:
                resumed = collect_selected(data_dir=root, request_budget=1)
                browser.assert_not_called()
            self.assertEqual(resumed['subject_record'], first['subject_record'])
            checkpoint = root / 'nightly-monitoring-latest.json'
            saved = json.loads(checkpoint.read_text(encoding='utf-8')); saved.pop('subject_record')
            checkpoint.write_text(json.dumps(saved), encoding='utf-8')
            with patch('compset.collect.collect', side_effect=full_bootstrap) as browser, \
                    patch('scrapling.fetchers.FetcherSession', CalendarSession), patch('compset.nightly.time.sleep'):
                strict_resume = collect_selected(data_dir=root, request_budget=1, job_id='a' * 32)
                browser.assert_called_once()
            self.assertIn('subject_record', strict_resume)
            self.assertEqual(CalendarSession.calls, 1)
            with patch('compset.collect.collect', side_effect=full_bootstrap) as browser, \
                    patch('scrapling.fetchers.FetcherSession', CalendarSession), patch('compset.nightly.time.sleep'):
                collected = collect_selected(data_dir=root, request_budget=1, fresh=True)
                browser.assert_called_once()
            self.assertEqual(collected['direct_requests_this_run'], 1)
            self.assertEqual(CalendarSession.calls, 2)

    def test_hotel_fresh_rechecks_healthy_prices_and_negative_but_respects_failure_cooldown(self):
        from compset import hotel_jobs
        from tests.test_hotel_portfolio_review import observation
        for initial in ['quoted', 'unavailable', 'unknown']:
            with self.subTest(initial=initial), TemporaryDirectory() as directory:
                root = Path(directory); calls = []
                def capture(source, hotel, context, output):
                    calls.append(context['checkin'])
                    return {'observed_at': datetime.now(timezone.utc).isoformat(), 'value': len(calls)}
                def parse(raw, hotel, source, context):
                    item = observation(hotel, source, context, priced=initial == 'quoted')
                    item['observed_at'] = raw['observed_at']
                    if initial == 'unavailable':
                        item.update(status='unavailable', unavailability_verified=True)
                    return item
                with patch('compset.hotel_jobs.parse_source', side_effect=parse), patch('compset.hotel_jobs.time.sleep'):
                    first = hotel_jobs.run_pipeline(root=root, sources=('agoda',), live=True,
                                                   request_budget=1, capture_fn=capture)
                    self.assertEqual(len(calls), 1)
                    with closing(sqlite3.connect(root / 'evidence.sqlite3')) as db:
                        before = db.execute('SELECT capture_id,raw_json FROM hotel_captures').fetchall()
                    result = hotel_jobs.run_pipeline(root=root, sources=('agoda',), live=True, request_budget=1,
                                                    capture_fn=capture, fresh=True, respect_cooldowns=True)
                    self.assertEqual(len(calls), 1 if initial == 'unknown' else 2)
                    if initial != 'unknown':
                        self.assertEqual(calls[0], calls[1])
                        self.assertFalse(result['observations'][0]['reused'])
                    else:
                        self.assertEqual(result['capture_calls_this_run'], 0)
                    with closing(sqlite3.connect(root / 'evidence.sqlite3')) as db:
                        after = db.execute('SELECT capture_id,raw_json FROM hotel_captures').fetchall()
                    self.assertTrue(all(row in after for row in before))


@unittest.skipUnless(shutil.which('node'), 'Node is required for independent client proof')
class WorkspaceCollectionClientIndependentReviewTests(unittest.TestCase):
    def test_legacy_controls_follow_workspace_busy_partial_and_interrupted_without_posts(self):
        script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('./compset/static/index.html','utf8');
const ids=new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(x=>x[1]));
class E {
 constructor(id=''){this.id=id;this.hidden=true;this.value='';this.events={};this.attrs={};this.children=[];this.textContent='';this.dataset={};
 const classes=new Set();this.classList={add:x=>classes.add(x),remove:x=>classes.delete(x),toggle:(x,b)=>b?classes.add(x):classes.delete(x),contains:x=>classes.has(x)};}
 addEventListener(k,f){this.events[k]=f;} setAttribute(k,v){this.attrs[k]=v;} removeAttribute(k){delete this.attrs[k];}
 querySelector(){return new E();} querySelectorAll(){return this.id==='collection-form'?[nodes.get('run-button'),nodes.get('discover-button')]:[];} replaceChildren(...v){this.children=v;} append(...v){this.children.push(...v);} appendChild(v){this.children.push(v);return v;}
 focus(){} scrollIntoView(){} reportValidity(){return true;} get childElementCount(){return this.children.length;} get options(){return this.children;}
}
const nodes=new Map([...ids].map(id=>[id,new E(id)])),calls=[];
const document={body:new E('body'),getElementById:id=>{assert(ids.has(id),`missing HTML id ${id}`);return nodes.get(id)},querySelectorAll:()=>[],createElement:tag=>new E(tag)};
const window={document,CompSetRates:{mount(){}},addEventListener(){}};
const context={window,document,console,URL,Intl,Date,Set,Map,Promise,JSON,Option:class extends E{constructor(text,value){super();this.textContent=text;this.value=value;}},
 setTimeout:()=>1,clearTimeout(){},fetch:async(path,options={})=>{calls.push({path,method:options.method||'GET'});
 return {ok:path==='/api/status',status:path==='/api/status'?200:404,json:async()=>path==='/api/status'?{state:'partial',message:'Bounded collection ended with unknowns.'}:{error:'not saved'}};}};
vm.runInNewContext(fs.readFileSync('./compset/static/app.js','utf8'),context);
setImmediate(async()=>{
 assert.equal(nodes.get('connection-error').hidden,true);
 assert.match(nodes.get('job-label').textContent,/partial|incomplete/i);
 window.CompSetCollectionStatus({state:'running',job_id:'a'.repeat(32),dataset_id:'aketa',message:'Collecting Aketa'});
 assert.equal(nodes.get('run-button').disabled,true);
 assert.equal(nodes.get('inventory-refresh-button').disabled,true);
 assert.equal(nodes.get('inventory-pause-button').disabled,true);
 await nodes.get('run-button').events.click();
 window.CompSetCollectionStatus({state:'partial',job_id:'a'.repeat(32),dataset_id:'aketa',message:'Unknown prices remain'});
 assert.equal(nodes.get('run-button').disabled,false);
 assert.equal(nodes.get('inventory-refresh-button').disabled,false);
 assert.equal(nodes.get('connection-error').hidden,true);
 window.CompSetCollectionStatus({state:'interrupted',job_id:'a'.repeat(32),dataset_id:'aketa',message:'Interrupted'});
 assert.match(nodes.get('job-label').textContent,/interrupted/i);
 await new Promise(resolve=>setImmediate(resolve));
 assert(calls.every(c=>c.method==='GET'));
 console.log(JSON.stringify({passed:true,requests:calls.length}));
});
'''
        result = subprocess.run(['node', '-'], input=script, cwd=ROOT, capture_output=True,
                                text=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['passed'])


class WorkspaceCollectionApiIndependentReviewTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.directory = self.stack.enter_context(TemporaryDirectory())
        self.data = Path(self.directory)
        self.stack.enter_context(patch.object(server, 'DATA', self.data))
        self.original_state = deepcopy(server.STATE)
        server.STATE.clear()
        server.STATE.update(state='idle', message='Independent review fixture')
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=2)
        self.stack.close()
        server.STATE.clear()
        server.STATE.update(self.original_state)

    def request(self, path='/api/workspace/job', *, method='GET', payload=None, headers=None):
        connection = HTTPConnection('127.0.0.1', self.http.server_port, timeout=5)
        values = dict(headers or {})
        body = json.dumps(payload) if payload is not None else None
        try:
            connection.request(method, path, body=body, headers=values)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), json.loads(response.read())
        finally:
            connection.close()

    def post(self, path, payload, **headers):
        return self.request(path, method='POST', payload=payload, headers={
            'Origin': f'http://127.0.0.1:{self.http.server_port}',
            'X-CompSet-Request': 'dashboard-v1', 'Content-Type': 'application/json', **headers})

    def test_initial_status_get_is_guarded_no_store_and_never_starts_collection(self):
        with patch.object(server, 'collect_job') as legacy, \
                patch.object(server.subprocess, 'run') as process:
            status, headers, job = self.request()
            self.assertEqual(status, 200)
            self.assertEqual(job['state'], 'idle')
            self.assertIsNone(job['job_id'])
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertNotIn('Access-Control-Allow-Origin', headers)
            for header in [{'Host': 'evil.example'}, {'Origin': 'https://evil.example'}, {'Origin': 'null'}]:
                self.assertEqual(self.request(headers=header)[0], 403)
            legacy.assert_not_called(); process.assert_not_called()

    def test_start_rejects_client_controlled_scope_paths_commands_and_context(self):
        invalid = [None, [], 'aketa', {}, {'dataset_id': 'other'},
                   {'dataset_id': 'aketa', 'mode': 'fast'}, {'dataset_id': ['aketa']},
                   {'dataset_id': 'aketa', 'mode': True}]
        invalid.extend({'dataset_id': 'aketa', key: value} for key, value in [
            ('adults', 2), ('start_date', '2000-01-01'), ('sources', ['agoda']),
            ('request_budget', 1000000), ('command', 'anything'), ('path', '../private.json'),
            ('source_url', 'http://localhost/private'), ('filters', {'state': 'quoted'}),
            ('job_id', '../private')])
        with patch.object(server, 'collect_job') as legacy, \
                patch.object(server.subprocess, 'run') as process:
            for payload in invalid:
                with self.subTest(payload=payload):
                    self.assertEqual(self.post('/api/workspace/collect', payload)[0], 400)
            legacy.assert_not_called(); process.assert_not_called()
        self.assertNotEqual(server.STATE.get('state'), 'running')

    def test_pause_wrong_inactive_or_path_job_id_never_creates_pause_flags(self):
        with patch.object(server, 'collect_job') as legacy, \
                patch.object(server.subprocess, 'run') as process:
            for job_id in ['a' * 32, '../private', 'other', None]:
                with self.subTest(job_id=job_id):
                    self.assertIn(self.post('/api/workspace/pause', {'job_id': job_id})[0], [400, 409])
            legacy.assert_not_called(); process.assert_not_called()
        self.assertFalse(list(self.data.rglob('*.flag')))

    def test_start_and_pause_require_existing_dashboard_security_headers(self):
        with patch.object(server.subprocess, 'run') as process:
            for path, payload in [('/api/workspace/collect', {'dataset_id': 'aketa'}),
                                  ('/api/workspace/pause', {'job_id': 'a' * 32})]:
                self.assertEqual(self.request(path, method='POST', payload=payload)[0], 403)
                self.assertEqual(self.post(path, payload, Origin='https://evil.example')[0], 403)
                self.assertEqual(self.post(path, payload, **{'Content-Type': 'text/plain'})[0], 415)
            process.assert_not_called()

    def test_http_start_has_one_worker_blocks_legacy_and_pause_keeps_job_identity(self):
        from compset import workspace_jobs
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        calls = []
        def worker(job_id):
            calls.append(job_id); entered.set()
            release.wait(timeout=5)
            result = workspace_jobs._finish(self.data, job_id, 'paused', 'Independent review pause')
            with server.LOCK:
                server.STATE.update(state=result['state'], message=result['message'])
            finished.set()
        try:
            with patch.object(server, 'launch_workspace_job', side_effect=worker), \
                    patch.object(server, 'collect_job') as legacy:
                status, _, job = self.post('/api/workspace/collect', {'dataset_id': 'aketa'})
                self.assertEqual(status, 202); self.assertTrue(entered.wait(timeout=2))
                self.assertEqual(job['mode'], 'fresh')
                self.assertEqual(job['context']['adults'], 1); self.assertEqual(job['context']['rooms'], 1)
                self.assertEqual(job['context']['currency'], 'INR'); self.assertEqual(job['context']['days'], 30)
                self.assertEqual(self.post('/api/workspace/collect', {'dataset_id': 'aketa'})[0], 409)
                self.assertEqual(self.post('/api/run', {})[0], 409)
                self.assertEqual(self.post('/api/workspace/pause', {'job_id': '0' * 32})[0], 409)
                paused = self.post('/api/workspace/pause', {'job_id': job['job_id']})
                self.assertEqual(paused[0], 202); self.assertTrue(paused[2]['pause_requested'])
                (self.data / 'progress.json').write_text('{"message":"wrong earlier job progress"}', encoding='utf-8')
                current = self.request('/api/status')[2]
                self.assertEqual(current['job_id'], job['job_id'])
                self.assertNotIn('wrong earlier', current['message'])
                legacy.assert_not_called()
                release.set(); self.assertTrue(finished.wait(timeout=2))
                final = self.request()[2]
                self.assertEqual(final['job_id'], job['job_id']); self.assertEqual(final['state'], 'paused')
                self.assertEqual(len(calls), 1)
        finally:
            release.set(); finished.wait(timeout=2)

    def test_worker_launch_failure_releases_lease_and_reports_failed(self):
        from compset import workspace_jobs
        job = workspace_jobs.reserve_job(self.data, {'dataset_id': 'aketa'})
        with patch.object(workspace_jobs.subprocess, 'run', side_effect=OSError('fixture launch error')):
            workspace_jobs.launch_worker(self.data, job['job_id'])
        self.assertEqual(workspace_jobs.read_job(self.data)['state'], 'failed')
        self.assertFalse((self.data / 'collection-lease.json').exists())
        replacement = workspace_jobs.reserve_job(self.data, {'dataset_id': 'aketa'})
        self.assertNotEqual(job['job_id'], replacement['job_id'])

    def test_thread_start_failure_releases_reserved_lease_and_returns_503(self):
        real_thread = threading.Thread
        class FailedThread:
            def start(self):
                raise RuntimeError('fixture thread startup failure')
        def thread_factory(*args, **kwargs):
            return FailedThread() if kwargs.get('target') is server.launch_workspace_job else real_thread(*args, **kwargs)
        with patch.object(server.threading, 'Thread', side_effect=thread_factory), \
                patch.object(server.subprocess, 'run') as process:
            status, _, _ = self.post('/api/workspace/collect', {'dataset_id': 'aketa'})
            self.assertEqual(status, 503)
            process.assert_not_called()
        self.assertEqual(self.request()[2]['state'], 'failed')
        self.assertFalse((self.data / 'collection-lease.json').exists())

    def test_legacy_preparation_failure_releases_lease_without_launch(self):
        with patch.object(server, '_write_json', side_effect=OSError('fixture disk full')), \
                patch.object(server, 'collect_job') as legacy:
            status, _, _ = self.post('/api/run', {})
            self.assertEqual(status, 503)
            legacy.assert_not_called()
        self.assertFalse((self.data / 'collection-lease.json').exists())
        self.assertNotEqual(server.STATE.get('state'), 'running')


if __name__ == '__main__':
    unittest.main()
