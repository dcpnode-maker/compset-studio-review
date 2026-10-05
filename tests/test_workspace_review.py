"""Independent order010 proof for a read-only, evidence-preserving workspace."""
from contextlib import ExitStack
from copy import deepcopy
import csv
import hashlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import subprocess
import threading
import unittest
from unittest.mock import patch

from compset.server import Handler
from compset.workspace import build_workspace, public_property_url

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node is required for independent client proof')
class WorkspaceClientIndependentReviewTests(unittest.TestCase):
    def node(self, script):
        result = subprocess.run(['node', '-'], input=script, cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_model_paging_filters_export_and_formula_defenses(self):
        result = self.node(r'''
const {model:m} = require('./compset/static/rates-workspace.js');
const dates=Array.from({length:9},(_,i)=>`2026-10-${String(i+1).padStart(2,'0')}`);
const dataset={id:'test',label:'Test',currency:'INR',context:{adults:1,rooms:1,currency:'INR'},dates,
 entities:[{id:'a',label:'=HYPERLINK("evil")',source:'agoda',role:'channel',source_url:'javascript:alert(1)'},
 {id:'b',label:'Booking',source:'booking',role:'channel'}],
 cells:[{entity_id:'a',date:dates[7],checkout:dates[8],state:'indicative',amount:'5169.0',currency:'INR',offers:[],reason:'\t=FORMULA'},
 {entity_id:'a',date:dates[8],state:'unknown',amount:'999',currency:'INR',offers:[]},
 {entity_id:'b',date:dates[7],state:'indicative',amount:'1',currency:'INR',offers:[]}]};
const before=JSON.stringify(dataset);
const view=m.visibleModel(dataset,{page:1,source:'agoda',state:'indicative'});
console.log(JSON.stringify({dates:view.dates,rows:view.rows.length,cells:view.cells.length,
 csv:m.exportCsv(dataset,{page:1,source:'agoda',state:'indicative'}),
 unknownCsv:m.exportCsv(dataset,{page:1,source:'agoda',state:'unknown'}),
 nochange:before===JSON.stringify(dataset),
 guarded:['=SUM(1,2)',' +SUM(1,2)','\t@FORMULA','\rFORMULA','-10'].map(m.csvField),
 unknown:m.priceLabel({state:'unknown',amount:'0',currency:'INR'}),
 unsafe:['javascript:alert(1)','file:///private','http://127.0.0.1/','http://localhost/','https://u:p@example.com/','https://example.com:8765/'].map(m.safeUrl)}));
''')
        self.assertEqual(result['dates'], ['2026-10-08', '2026-10-09'])
        self.assertEqual((result['rows'], result['cells']), (1, 1)); self.assertTrue(result['nochange'])
        rows = list(csv.DictReader(io.StringIO(result['csv'])))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['amount'], '5169.0'); self.assertEqual(row['observation_source'], 'agoda')
        self.assertEqual(row['entity'], '\'=HYPERLINK("evil")'); self.assertEqual(row['source_url'], '')
        self.assertTrue(row['reason'].startswith("'\t="))
        self.assertEqual(json.loads(row['requested_context'])['adults'], 1)
        self.assertEqual(list(csv.DictReader(io.StringIO(result['unknownCsv'])))[0]['amount'], '')
        self.assertEqual(result['unknown'], 'Unknown'); self.assertTrue(all(x is None for x in result['unsafe']))
        self.assertTrue(all(x.startswith('"\'') for x in result['guarded']))

    def test_legacy_integration_mounts_new_default_and_switches_every_existing_view(self):
        result = self.node(r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('./compset/static/index.html','utf8');
assert(html.indexOf('src="/rates-workspace.js"')<html.indexOf('src="/app.js"'));
const ids=new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(x=>x[1]));
class E {
 constructor(id=''){this.id=id;this.hidden=false;this.value='';this.events={};this.attrs={};this.children=[];this.textContent='';this.dataset={};
 const classes=new Set();this.classList={add:x=>classes.add(x),remove:x=>classes.delete(x),toggle:(x,b)=>b?classes.add(x):classes.delete(x),contains:x=>classes.has(x)};}
 addEventListener(k,f){this.events[k]=f;} setAttribute(k,v){this.attrs[k]=v;} removeAttribute(k){delete this.attrs[k];}
 querySelector(){return new E();} querySelectorAll(){return [];} replaceChildren(...v){this.children=v;} append(...v){this.children.push(...v);} appendChild(v){this.children.push(v);return v;}
 focus(){} scrollIntoView(){} reportValidity(){return true;}
 get childElementCount(){return this.children.length;}
 get options(){return this.children;}
}
const nodes=new Map([...ids].map(id=>[id,new E(id)])),calls=[],mounts=[];
const document={body:new E('body'),getElementById:id=>{assert(ids.has(id),`missing HTML id ${id}`);return nodes.get(id)},
 querySelectorAll:()=>[],createElement:tag=>new E(tag)};
const window={document,CompSetRates:{mount:root=>mounts.push(root.id)},addEventListener(){}};
const context={window,document,console,URL,Intl,Date,Set,Map,Promise,JSON,Option:class extends E {constructor(text,value){super();this.textContent=text;this.value=value;}},
 setTimeout:()=>1,clearTimeout(){},fetch:async(path,options={})=>{calls.push({path,method:options.method||'GET'});
 return {ok:path==='/api/status',status:path==='/api/status'?200:404,json:async()=>path==='/api/status'?{state:'idle',message:'review'}:{error:'not saved'}};}};
vm.runInNewContext(fs.readFileSync('./compset/static/app.js','utf8'),context);
assert.deepEqual(mounts,['rates-workspace']);assert.equal(nodes.get('rates-workspace').hidden,false);
const views={};
for(const v of ['portfolio','comparison','prices','rates']){
 nodes.get('view-'+v).events.click();
 views[v]={visible:!nodes.get(v==='rates'?'rates-workspace':v+'-workspace').hidden,
 ratesHidden:nodes.get('rates-workspace').hidden,pressed:nodes.get('view-'+v).attrs['aria-pressed']};
}
setImmediate(()=>console.log(JSON.stringify({mounts,views,calls})));
''')
        self.assertEqual(result['mounts'], ['rates-workspace'])
        self.assertTrue(all(v['visible'] and v['pressed'] == 'true' for v in result['views'].values()))
        self.assertFalse(result['views']['rates']['ratesHidden'])
        self.assertTrue(all(v['ratesHidden'] for k, v in result['views'].items() if k != 'rates'))
        self.assertTrue(result['calls']); self.assertTrue(all(c['method'] == 'GET' for c in result['calls']))


class WorkspaceProjectionIndependentReviewTests(unittest.TestCase):
    """Small synthetic public evidence, independent of current local captures."""

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.data = Path(self.directory.name)
        self.context = dict(hotel_id='aketa-dehradun', start_date='2026-09-28',
                            days=2, stay_nights=1, rooms=1, adults=1, children=0,
                            currency='INR')
        self.stay = {**self.context, 'checkin': '2026-09-28', 'checkout': '2026-09-29'}
        self.hotel = dict(context=self.context, hotel={'id': 'aketa-dehradun', 'sources': {}},
                          rates=[], coverage=[], observations=[], source_states=[])
        self.air_context = dict(listing_id='123', start_date='2026-09-28',
                                end_date='2026-09-30', stay_nights=1,
                                adults=1, children=0, infants=0, pets=0, currency='AED')
        self.air_stay = {**self.air_context, 'checkin': '2026-09-28', 'checkout': '2026-09-29'}
        self.comp = dict(run_id='review-run', subject={'listing_id': '123', 'title': 'Subject'},
                         selected=[{'listing_id': '456', 'title': 'Competitor'}], candidates=[])
        self.nightly = dict(context=self.air_context, amount_kind='one_night_stay_total',
                            compset_run_id='review-run', listing_ids=['123', '456'], records=[])

    def save(self, name, value):
        path = self.data / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def project(self, dataset='aketa'):
        self.save('hotel-pipelines/latest.json', self.hotel)
        self.save('compset-latest.json', self.comp)
        self.save('one-night-latest.json', self.nightly)
        return next(d for d in build_workspace(self.data)['datasets'] if d['id'] == dataset)

    def cell(self, result, entity='agoda', day='2026-09-28'):
        return next(c for c in result['cells'] if c['entity_id'] == entity and c['date'] == day)

    def rate(self, amount='5169.0'):
        return dict(source='agoda', channel='agoda', hotel_id='aketa-dehradun',
                    checkin=self.stay['checkin'], checkout=self.stay['checkout'],
                    currency='INR', amount=amount, amount_type='ota_display_price',
                    source_amount_basis='nightly_room_rate', precision='displayed_integer',
                    display_amount='5,169', direct_supplier_quote=False, context_verified=True,
                    observed_context=deepcopy(self.stay), taxes_included=False, fees_included=False,
                    membership_required=True, conditions=[{'text': 'Members only'}],
                    observed_at='2026-09-28T07:00:00+00:00')

    def negative(self):
        return dict(source='agoda', hotel_id='aketa-dehradun', status='unavailable',
                    unavailability_verified=True, rates=[], observed_at='2026-09-28T07:00:00+00:00',
                    requested_context=deepcopy(self.stay), observed_context=deepcopy(self.stay))

    def quote_record(self, amount='650.40', stamp='2026-09-28T07:00:00+00:00'):
        return dict(context=deepcopy(self.air_stay), status='quoted', observed_at=stamp,
                    quotes=[dict(**self.air_stay, status='quoted', amount=amount,
                                 amount_kind='one_night_stay_total', guest_context_verified=True,
                                 observed_at=stamp, taxes_included=None, fees_included=None)])

    def preflight(self, reason='sleeping_night_unavailable'):
        field = {'sleeping_night_unavailable': 'available', 'minimum_stay_not_met': 'min_nights',
                 'checkin_not_allowed': 'available_for_checkin', 'checkout_not_allowed': 'available_for_checkout'}[reason]
        day = self.air_stay['checkout' if field == 'available_for_checkout' else 'checkin']
        evidence = dict(listing_id='123', date=day, field=field, value=3 if field == 'min_nights' else False, http_status=200)
        return dict(context=deepcopy(self.air_stay), status='calendar_skipped', quotes=[],
                    observed_at='2026-09-28T07:00:00+00:00',
                    preflight=dict(decision='skip_quote', reason=reason,
                                   context=deepcopy(self.air_stay), evidence=[evidence]))

    def test_planned_grid_retains_unknowns_and_never_uses_declared_summary(self):
        self.hotel['rates'] = [self.rate()]
        self.hotel['summary'] = {'quoted_cells': 999, 'date_cells': 1}
        result = self.project()
        self.assertEqual(result['summary'], dict(date_cells=10, quoted_cells=0, indicative_cells=1,
                                                unavailable_cells=0, restricted_cells=0, unknown_cells=9, rate_rows=1))
        self.assertEqual(self.cell(result)['amount'], '5169.0')
        self.assertTrue(self.cell(result)['offers'][0]['membership_required'])
        for cell in result['cells']:
            if cell['state'] == 'unknown':
                self.assertIsNone(cell['amount'])

    def test_rate_identity_party_dates_currency_and_boolean_types_do_not_cross_associate(self):
        changes = [('hotel_id', 'elsewhere'), ('currency', 'AED'), ('checkout', '2026-09-30'),
                   ('source', 'invented'), ('channel', 'expedia'), ('context_verified', False)]
        for field, value in changes:
            with self.subTest(field=field):
                rate = self.rate('1'); rate[field] = value; self.hotel['rates'] = [rate]
                self.assertEqual(self.project()['summary']['rate_rows'], 0)
        for field, value in [('hotel_id', 'other'), ('checkin', '2026-09-29'), ('checkout', '2026-10-01'),
                             ('adults', 2), ('adults', True), ('children', 1), ('rooms', 2), ('currency', 'USD')]:
            with self.subTest(observed=field, value=value):
                rate = self.rate('1'); rate['observed_context'][field] = value; self.hotel['rates'] = [rate]
                self.assertEqual(self.project()['summary']['rate_rows'], 0)

    def test_zero_negative_nan_and_invalid_timestamp_cannot_be_prices(self):
        for value in ['0', '-1', 'NaN', 'Infinity', True, None]:
            with self.subTest(amount=value):
                self.hotel['rates'] = [self.rate(value)]
                self.assertEqual(self.cell(self.project())['state'], 'unknown')
        for value in ['2026-09-28T07:00:00', 'yesterday', None]:
            rate = self.rate(); rate['observed_at'] = value; self.hotel['rates'] = [rate]
            self.assertEqual(self.cell(self.project())['state'], 'unknown')

    def test_coverage_alone_cannot_prove_unavailability(self):
        self.hotel['coverage'] = [dict(hotel_id='aketa-dehradun', source='agoda', checkin='2026-09-28',
                                       state='unavailable', reason='soldout')]
        self.assertEqual(self.cell(self.project())['state'], 'unknown')
        self.hotel['observations'] = [self.negative()]
        cell = self.cell(self.project())
        self.assertEqual(cell['state'], 'unavailable'); self.assertIsNone(cell['amount'])
        for field, value in [('adults', 2), ('checkin', '2026-09-27'), ('currency', 'AED')]:
            negative = self.negative(); negative['observed_context'][field] = value
            self.hotel['observations'] = [negative]
            self.assertEqual(self.cell(self.project())['state'], 'unknown')

    def test_explicit_legacy_profile_negative_does_not_mark_canonical_profile_unavailable(self):
        for section in [None, 'observed_context', 'requested_context']:
            for field in ['provider_id', 'provider_hotel_id']:
                with self.subTest(section=section, field=field):
                    negative = self.negative()
                    (negative if section is None else negative[section])[field] = '27746358'
                    self.hotel['observations'] = [negative]
                    self.assertEqual(self.cell(self.project())['state'], 'unknown')

    def test_price_and_negative_conflict_stays_unknown(self):
        self.hotel['rates'] = [self.rate()]; self.hotel['observations'] = [self.negative()]
        cell = self.cell(self.project())
        self.assertEqual(cell['state'], 'unknown'); self.assertIsNone(cell['amount'])
        self.assertEqual(len(cell['offers']), 1)

    def test_different_tax_bases_keep_all_offers_without_claiming_comparable_minimum(self):
        first, second = self.rate('5000'), self.rate('7000')
        second['taxes_included'] = True
        self.hotel['rates'] = [first, second]
        cell = self.cell(self.project())
        self.assertEqual(cell['state'], 'indicative'); self.assertIsNone(cell['amount'])
        self.assertEqual(len(cell['offers']), 2)
        self.assertEqual(cell['reason'], 'different_price_bases_or_terms')

    def test_google_abbreviation_is_not_exact_and_partner_amount_does_not_replace_calendar(self):
        rate = self.rate('5000')
        rate.update(source='google_hotels', channel='google_hotels', amount=None,
                    amount_type='google_calendar_minimum', precision='abbreviated',
                    display_amount='5K', approximate_amount='5000')
        partner = deepcopy(rate); partner.update(amount='4200', approximate_amount=None,
                                                 amount_type='google_partner_nightly_total', precision='displayed_decimal')
        self.hotel['rates'] = [rate, partner]
        cell = self.cell(self.project(), 'google_hotels')
        self.assertEqual(cell['state'], 'indicative'); self.assertIsNone(cell['amount'])
        self.assertEqual(cell['display_amount'], '5K'); self.assertEqual(len(cell['offers']), 2)
        self.assertTrue(all(not o['direct_supplier_quote'] for o in cell['offers']))

    def test_airbnb_exact_context_only_and_summary_has_full_planned_grid(self):
        self.nightly['records'] = [self.quote_record()]
        result = self.project('airbnb-compset')
        self.assertEqual(result['summary']['date_cells'], 4)
        self.assertEqual(result['summary']['quoted_cells'], 1)
        self.assertEqual(self.cell(result, '123')['amount'], '650.40')
        for field, value in [('listing_id', '456'), ('adults', 2), ('children', True), ('pets', 1),
                             ('currency', 'USD'), ('checkout', '2026-09-30'), ('guest_context_verified', False)]:
            record = self.quote_record(); record['quotes'][0][field] = value
            self.nightly['records'] = [record]
            self.assertEqual(self.project('airbnb-compset')['summary']['quoted_cells'], 0)

    def test_airbnb_restrictions_are_distinct_from_unavailable_with_contextual_field_proof(self):
        for reason, state in [('sleeping_night_unavailable', 'unavailable'),
                              ('minimum_stay_not_met', 'restricted'), ('checkin_not_allowed', 'restricted'),
                              ('checkout_not_allowed', 'restricted')]:
            with self.subTest(reason=reason):
                record = self.preflight(reason); self.nightly['records'] = [record]
                cell = self.cell(self.project('airbnb-compset'), '123')
                self.assertEqual(cell['state'], state); self.assertIsNone(cell['amount'])
                for field, value in [('listing_id', '999'), ('date', '2026-09-27'),
                                     ('http_status', 403), ('value', 'false')]:
                    invalid = deepcopy(record); invalid['preflight']['evidence'][0][field] = value
                    self.nightly['records'] = [invalid]
                    self.assertEqual(self.cell(self.project('airbnb-compset'), '123')['state'], 'unknown')

    def test_newest_source_time_uses_instant_order_not_lexical_offset(self):
        old = self.quote_record('600', '2026-09-28T12:00:00+05:30')
        recent = self.quote_record('700', '2026-09-28T07:00:00+00:00')
        self.nightly['records'] = [recent, old]
        cell = self.cell(self.project('airbnb-compset'), '123')
        self.assertEqual(cell['amount'], '700')
        self.assertEqual(cell['observed_at'], '2026-09-28T07:00:00+00:00')

    def test_planned_listing_cohort_survives_missing_or_changed_comp_set(self):
        self.comp = {}
        result = self.project('airbnb-compset')
        self.assertEqual({x['id'] for x in result['entities']}, {'123', '456'})
        self.assertEqual(result['summary']['date_cells'], 4)
        self.assertTrue(result['warnings'])

    def test_rate_options_keep_selected_and_refundable_alternative_with_original_context(self):
        record = self.quote_record('610.36'); quote = record['quotes'][0]
        quote['rate_plan'] = 'Non-refundable'
        quote['rate_options'] = [dict(status='quoted', amount_kind='one_night_stay_total', currency='AED',
                                      amount=amount, is_selected=selected, rate_plan=name,
                                      cancellation_terms=name, sources=[{'observed_request_context': self.air_stay,
                                                                        'observed_at': record['observed_at']}])
                                 for amount, selected, name in [('610.36', True, 'Non-refundable'),
                                                                ('650.40', False, 'Refundable')]]
        self.nightly['records'] = [record]
        cell = self.cell(self.project('airbnb-compset'), '123'); offer = cell['offers'][0]
        self.assertEqual(cell['amount'], '610.36'); self.assertEqual(offer['rate_plan_name'], 'Non-refundable')
        self.assertEqual([(o['amount'], o['is_selected']) for o in offer['rate_options']], [('610.36', True), ('650.40', False)])
        quote['rate_options'][1]['sources'][0]['observed_request_context'] = {**self.air_stay, 'adults': 2}
        self.assertEqual(len(self.cell(self.project('airbnb-compset'), '123')['offers'][0]['rate_options']), 1)

    def test_public_projection_drops_artifact_paths_tokens_and_api_urls_without_mutating_inputs(self):
        rate = self.rate(); rate.update(token='review-secret', provenance={'source_artifact': 'C:\\private\\capture.json',
                       'source_url': 'https://www.agoda.com/aketa/hotel/dehradun.html?token=review-secret'})
        self.hotel['rates'] = [rate]
        self.save('portfolio-latest.json', {'properties': [{'property_id': 'property1', 'title': 'Room',
                 'source_url': 'https://api.bnbmehomes.com/api/v1/property/search-property-v2',
                 'raw': {'secret': 'review-secret'}}]})
        self.project()
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.data.rglob('*.json')}
        result = build_workspace(self.data); encoded = json.dumps(result)
        self.assertNotIn('review-secret', encoded); self.assertNotIn('C:\\\\private', encoded)
        self.assertNotIn('search-property-v2', encoded)
        self.assertIsNone(result['portfolio']['properties'][0]['source_url'])
        self.assertEqual(before, {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.data.rglob('*.json')})

    def test_public_links_reject_private_and_script_targets_and_strip_session_queries(self):
        for url in ['javascript:alert(1)', 'file:///C:/private', 'https://localhost/property/a',
                    'https://127.0.0.1/property/a', 'https://user:secret@www.airbnb.com/rooms/123',
                    'https://www.airbnb.com:123/rooms/123', 'https://www.airbnb.com.evil.example/rooms/123',
                    'https://api.bnbmehomes.com/api/v1/property/search-property-v2']:
            with self.subTest(url=url):
                self.assertIsNone(public_property_url(url))
        self.assertEqual(public_property_url('https://www.airbnb.com/rooms/123?token=secret#section'),
                         'https://www.airbnb.com/rooms/123')


class WorkspaceApiIndependentReviewTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.directory = self.stack.enter_context(TemporaryDirectory())
        self.data = Path(self.directory)
        self.stack.enter_context(patch('compset.server.DATA', self.data))
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.stack.close()

    def request(self, path='/api/workspace', *, method='GET', headers=None):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_workspace_is_local_no_store_read_only_and_never_collects(self):
        with patch('compset.server.collect_job') as collect, \
                patch('compset.server.subprocess.run') as process:
            status, headers, body = self.request()
            self.assertEqual(status, 200)
            result = json.loads(body)
            self.assertEqual(result['schema_version'], 1)
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
            self.assertNotIn('Access-Control-Allow-Origin', headers)
            origin = f'http://127.0.0.1:{self.server.server_port}'
            self.assertEqual(self.request(method='POST', headers={
                'Origin': origin, 'X-CompSet-Request': 'dashboard-v1',
                'Content-Type': 'application/json'})[0], 404)
            collect.assert_not_called()
            process.assert_not_called()
        self.assertEqual(list(self.data.iterdir()), [])

    def test_host_origin_and_fixed_route_guards(self):
        self.assertEqual(self.request(headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request(headers={'Origin': 'https://evil.example'})[0], 403)
        origin = f'http://localhost:{self.server.server_port}'
        self.assertEqual(self.request(headers={'Origin': origin})[0], 200)
        for path in ['/api/workspace/../../private.json', '/api/workspace/other',
                     '/api/%2e%2e/workspace', '/api/workspace/%2e%2e/private.json']:
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)

    def test_query_cannot_select_arbitrary_file_or_trigger_refresh(self):
        secret = self.data / 'private.json'
        secret.write_text('{"password":"review-sentinel-do-not-expose"}', encoding='utf-8')
        before = secret.read_bytes()
        with patch('compset.server.collect_job') as collect, \
                patch('compset.server.subprocess.run') as process:
            status, _, body = self.request('/api/workspace?file=private.json&live=true&refresh=true')
            self.assertEqual(status, 200)
            self.assertNotIn(b'review-sentinel-do-not-expose', body)
            collect.assert_not_called()
            process.assert_not_called()
        self.assertEqual(secret.read_bytes(), before)

    def test_same_path_saved_revision_invalidates_projection_cache_without_collection(self):
        saved = self.data / 'portfolio-latest.json'
        saved.write_text(json.dumps({'properties': [{'property_id': '1', 'title': 'Before'}]}), encoding='utf-8')
        with patch('compset.server.collect_job') as collect, \
                patch('compset.server.subprocess.run') as process:
            first = json.loads(self.request()[2])
            self.assertEqual(first['portfolio']['properties'][0]['title'], 'Before')
            stamp = saved.stat().st_mtime_ns
            saved.write_text(json.dumps({'properties': [{'property_id': '1', 'title': 'After!'}]}), encoding='utf-8')
            os.utime(saved, ns=(stamp + 1_000_000_000, stamp + 1_000_000_000))
            second = json.loads(self.request()[2])
            self.assertEqual(second['portfolio']['properties'][0]['title'], 'After!')
            collect.assert_not_called(); process.assert_not_called()

    def test_malformed_evidence_is_visible_without_zero_price_or_collection(self):
        saved = self.data / 'one-night-latest.json'
        saved.write_text('{"records":', encoding='utf-8')
        before = saved.read_bytes()
        with patch('compset.server.collect_job') as collect:
            status, _, body = self.request()
            self.assertEqual(status, 200)
            result = json.loads(body)
            self.assertTrue(result['warnings'] or any(x.get('warnings') for x in result['datasets']))
            for dataset in result['datasets']:
                self.assertEqual(dataset['summary']['quoted_cells'], 0)
                self.assertTrue(all(cell['amount'] is None for cell in dataset['cells']))
            collect.assert_not_called()
        self.assertEqual(saved.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
