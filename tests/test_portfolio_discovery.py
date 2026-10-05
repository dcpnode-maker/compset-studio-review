"""Regional discovery safeguards: deterministic fixtures, never external transport."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from compset import discovery, workflows
from tests.test_discovery import SUBJECT, FakeSession, response_body, row, template


class Clock:
    def __init__(self): self.now = 100.0; self.sleeps = []
    def monotonic(self): return self.now
    def sleep(self, seconds): self.sleeps.append(seconds); self.now += seconds


class Session(FakeSession):
    def __init__(self, clock, replies): super().__init__(); self.clock = clock; self.replies = iter(replies); self.started = []
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs)); self.started.append(self.clock.now)
        reply = next(self.replies)
        if isinstance(reply, Exception): raise reply
        if isinstance(reply, tuple): status, body = reply
        else: status, body = 200, reply
        return SimpleNamespace(status=status, body=body if isinstance(body, bytes) else json.dumps(body).encode())


def geographic_template(lat=25.1929, lng=55.2716, city='Dubai', currency='AED'):
    result = template()
    values = discovery.circle_bounds(lat, lng, 2)
    result['body']['variables']['staysSearchRequest']['rawParams'] = [
        {'filterName': key, 'filterValues': [str(value)]} for key, value in values.items()]
    result['body']['variables']['staysSearchRequest']['rawParams'].extend([
        {'filterName': 'query', 'filterValues': [city]}, {'filterName': 'currency', 'filterValues': [currency]}])
    return result


class DiscoverySafetyTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.patches = [patch('compset.discovery.time.monotonic', self.clock.monotonic),
                        patch('compset.discovery.time.sleep', self.clock.sleep)]
        for p in self.patches: p.start(); self.addCleanup(p.stop)

    def replay(self, session, **kwargs):
        return discovery.replay_tiles(template(), SUBJECT, session,
            bounds=discovery.circle_bounds(25.1929, 55.2716, 2), **kwargs)

    def test_explicit_regions_use_local_city_and_currency(self):
        for city, lat, lng, currency in [('Dubai',25.19,55.27,'AED'),('Riyadh',24.76,46.72,'SAR'),('London',51.5,-.17,'GBP')]:
            with self.subTest(city=city):
                resolved = discovery.search_location({'city': city}, {}, lat, lng)
                self.assertIn('/s/'+city+'--', resolved['url'])
                self.assertEqual(resolved['currency'], currency)
                discovery.observed_geography(geographic_template(lat,lng,city,currency),resolved,discovery.circle_bounds(lat,lng,2))

    def test_unknown_coordinates_never_assume_dubai(self):
        self.assertEqual(discovery.search_location({}, {}, 25.19,55.27)['city'],'Dubai')
        for lat,lng in [(24.76,46.72),(51.5,-.17),(0,0),(None,None)]:
            with self.subTest(coords=(lat,lng)), self.assertRaises(ValueError):
                discovery.search_location({}, {}, lat,lng)

    def test_city_subject_context_and_search_url_must_agree(self):
        cases = [({'city':'London'},{},25.19,55.27),({'city':'Riyadh'},{'city':'Dubai'},24.76,46.72),
                 ({'city':'Unknown'},{},25.19,55.27),({'city':'London'},{'search_url':'https://www.airbnb.com/s/Dubai--UAE/homes'},51.5,-.17),
                 ({'city':'London'},{'search_url':'https://www.airbnb.com.evil/s/London/homes'},51.5,-.17),
                 ({'city':'London'},{'search_url':'https://user:secret@www.airbnb.com/s/London/homes'},51.5,-.17)]
        for subject, context, lat,lng in cases:
            with self.subTest(subject=subject,context=context), self.assertRaises(ValueError):
                discovery.search_location(subject,context,lat,lng)
        value = discovery.search_location({'city':'London'},{'search_url':'https://www.airbnb.co.in/s/London--United-Kingdom/homes?checkin=old'},51.5,-.17)
        self.assertNotIn('?', value['url'])

    def test_observed_wrong_city_bbox_currency_rejected(self):
        loc = discovery.search_location({'city':'London'}, {},51.5,-.17)
        bounds = discovery.circle_bounds(51.5,-.17,2)
        for bad in [geographic_template(),geographic_template(51.5,-.17,'Dubai','GBP'),geographic_template(51.5,-.17,'London','AED'),template()]:
            with self.subTest(template=bad), self.assertRaises(ValueError): discovery.observed_geography(bad,loc,bounds)

    def test_replay_minimum_spacing_including_browser_boundary(self):
        session = Session(self.clock,[response_body()]*4)
        result = self.replay(session,last_request_started=99.0)
        self.assertEqual(session.started,[102.0,105.0,108.0,111.0])
        self.assertEqual(self.clock.sleeps,[2.0,3.0,3.0,3.0])
        self.assertTrue(result['report']['complete_for_requested_cells'])

    def test_non_success_and_challenge_globally_stop_after_first_call(self):
        for reply in [(500,{}),(302,{}),(401,{}),(403,{}),(429,{}),(200,b'<html>verify you are human</html>')]:
            with self.subTest(reply=reply):
                session=Session(self.clock,[reply,response_body()])
                result=self.replay(session)
                self.assertEqual(len(session.calls),1)
                self.assertFalse(result['report']['complete_for_requested_cells'])
                self.assertTrue(result['report']['stop_reason'])
                self.assertEqual(sum(c['status']=='unvisited' for c in result['report']['cells']),3)

    def test_contract_and_transport_errors_never_proceed_to_next_tile(self):
        for reply in [{}, [], {'errors':[{'message':'upstream'}]}, {'data':{'paginationInfo':{'pageCursors':[]}}}, response_body([{'renamedListing':{'id':'2'}}]),
                      b'{bad', RuntimeError('private-cookie'), response_body(cursors=['first'])]:
            if isinstance(reply,dict) and 'data' in reply and 'presentation' in reply['data']:
                del reply['data']['presentation']['staysSearch']['results']['paginationInfo']
            with self.subTest(reply=reply):
                session=Session(self.clock,[reply,response_body()]);result=self.replay(session)
                self.assertEqual(len(session.calls),1)
                self.assertFalse(result['report']['complete_for_requested_cells'])
                self.assertNotIn('private-cookie',json.dumps(result))

    def test_previous_valid_candidates_survive_later_failure(self):
        session=Session(self.clock,[response_body([row('7')]),(500,{})])
        result=self.replay(session)
        self.assertEqual([r['listing_id'] for r in result['candidates']],['7'])
        self.assertEqual(len(session.calls),2)
        self.assertEqual(result['report']['stop_reason'],'non_success_response')

    def test_missing_bbox_contract_stops_before_any_call(self):
        bad=template();bad['body']['variables']['staysSearchRequest']['rawParams'].pop()
        session=Session(self.clock,[])
        result=discovery.replay_tiles(bad,SUBJECT,session,bounds=discovery.circle_bounds(25,55,2))
        self.assertEqual(session.calls,[])
        self.assertEqual(result['report']['stop_reason'],'observed_request_contract_changed')
        self.assertEqual(result['report']['cells'][0]['status'],'error')

    def test_cursor_cycle_and_malformed_pagination_are_global_stops(self):
        body=response_body([row()]);body['data']['presentation']['staysSearch']['results']['paginationInfo']={'nextPageCursor':'same'}
        session=Session(self.clock,[body,body,response_body()]);result=self.replay(session)
        self.assertEqual(len(session.calls),2);self.assertEqual(result['report']['stop_reason'],'cursor_cycle')
        bad=response_body();bad['data']['presentation']['staysSearch']['results']['paginationInfo']['pageCursors']='changed'
        session=Session(self.clock,[bad,response_body()]);result=self.replay(session)
        self.assertEqual(len(session.calls),1);self.assertEqual(result['report']['stop_reason'],'pagination_schema_changed')

    def browser(self, *, event='valid', click_event=None, failure=False, subject=None, budget=1):
        subject = subject or SUBJECT
        owner=self
        observed=geographic_template(subject.get('latitude'),subject.get('longitude'),subject.get('city','Dubai'),
                                      {'Riyadh':'SAR','London':'GBP'}.get(subject.get('city'),'AED'))
        calls={'clicks':[],'locators':[],'url':None,'fetcher':0}
        class Page:
            def __init__(self): self.callbacks={}
            def on(self,name,callback): self.callbacks[name]=callback
            def emit(self,kind):
                t=deepcopy(observed)
                if kind=='wrong_city':t=geographic_template()
                request=SimpleNamespace(url=t['url'],method='POST',post_data_json=t['body'],headers=t['headers'])
                self.callbacks['request'](request)
                if kind=='request_failed':self.callbacks['requestfailed'](request);return
                payload={} if kind=='schema' else response_body([row()])
                status=429 if kind=='blocked' else 500 if kind=='server_error' else 200
                response=SimpleNamespace(url=t['url'],status=status,body=lambda:json.dumps(payload).encode(),json=lambda:payload)
                self.callbacks['response'](response)
            def wait_for_timeout(self,ms): owner.clock.now+=ms/1000
            def locator(self,selector):
                calls['locators'].append(selector)
                page=self
                class Control:
                    @property
                    def first(self): return self
                    def count(self): return 1
                    def click(self,**kwargs):
                        calls['clicks'].append(selector)
                        if click_event:page.emit(click_event)
                return Control()
        class Browser:
            def __init__(self,**kwargs): pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def fetch(self,url,**kwargs):
                calls['url']=url;page=Page();kwargs['page_setup'](page)
                if event:page.emit(event)
                if failure:raise RuntimeError('secret-cookie')
                kwargs['page_action'](page)
                return SimpleNamespace(url=url,status=200,body=b'<html>ordinary search</html>',css=lambda selector:[])
        class Direct:
            def __init__(self,**kwargs):calls['fetcher']+=1
            def __enter__(self):return Session(owner.clock,[response_body()]*4)
            def __exit__(self,*args):pass
        with patch('scrapling.fetchers.DynamicSession',Browser),patch('scrapling.fetchers.FetcherSession',Direct):
            result=discovery.discover(subject,{'budget':budget})
        return result,calls

    def test_browser_failure_blocks_next_zoom_and_replay(self):
        for event, expected in [('blocked','access_or_rate_limit_429'),('server_error','non_success_response'),
                                ('schema','search_results_schema_missing'),('request_failed','browser_request_failed')]:
            with self.subTest(event=event):
                result,calls=self.browser(event=event,budget=8)
                self.assertEqual(calls['clicks'],[]);self.assertEqual(calls['locators'],[]);self.assertEqual(calls['fetcher'],0)
                self.assertEqual(result['report']['stop_reason'],expected)

    def test_browser_failure_after_template_does_not_fall_through_to_replay(self):
        result,calls=self.browser(failure=True,budget=8)
        self.assertEqual(calls['fetcher'],0);self.assertEqual(calls['clicks'],[])
        self.assertEqual(result['report']['stop_reason'],'browser_error')
        self.assertNotIn('secret-cookie',json.dumps(result))

    def test_next_failure_prevents_zoom_and_direct_replay(self):
        result,calls=self.browser(event=None,click_event='blocked',budget=8)
        self.assertEqual(calls['clicks'],['a[aria-label="Next"]'])
        self.assertEqual(calls['fetcher'],0)
        self.assertEqual(result['report']['stop_reason'],'access_or_rate_limit_429')

    def test_regional_browser_uses_correct_city_currency_and_budget(self):
        for city,lat,lng,currency in [('Riyadh',24.76,46.72,'SAR'),('London',51.5,-.17,'GBP')]:
            with self.subTest(city=city):
                result,calls=self.browser(subject={**SUBJECT,'city':city,'latitude':lat,'longitude':lng})
                self.assertIn('/s/'+city+'--',calls['url'])
                self.assertEqual(parse_qs(urlsplit(calls['url']).query)['currency'],[currency])
                self.assertEqual(calls['clicks'],[]);self.assertEqual(calls['fetcher'],0)
                self.assertEqual(result['report']['stop_reason'],'request_budget_reached')

    def test_wrong_observed_region_blocks_every_followup(self):
        result,calls=self.browser(event='wrong_city',subject={**SUBJECT,'city':'London','latitude':51.5,'longitude':-.17},budget=8)
        self.assertEqual(calls['clicks'],[]);self.assertEqual(calls['fetcher'],0)
        self.assertEqual(result['report']['stop_reason'],'observed_search_city_mismatch')

    def workflow(self, reason, *, later_reason=None):
        subject={**SUBJECT,'detail_status':'observed','title':'Subject'}
        candidate={'listing_id':'2','title':'Saved candidate','field_sources':{}}
        discovered={'candidates':[candidate],'report':{'stop_reason':reason,'total_search_requests':1}}
        details=[];expansions=[]
        def detail(identifier,context,stop=None):
            details.append((identifier,bool(stop and stop.is_set())))
            if len(details)==1:return subject
            if stop and stop.is_set():return {'listing_id':identifier,'detail_status':'deferred_after_access_limit'}
            return {**candidate,'detail_status':'observed'}
        def compare(subject,rows,criteria,**kwargs):
            expansions.append(kwargs['discovery_callback'](subject,criteria))
            expansions.append(kwargs['discovery_callback'](subject,criteria))
            return {'selected':[],'candidates':rows,'summary':{}}
        with tempfile.TemporaryDirectory() as directory,patch('compset.workflows.DATA',Path(directory)), \
             patch('compset.workflows.listing_detail',side_effect=detail), \
             patch('compset.discovery.discover',return_value={'candidates':[{'listing_id':'3','field_sources':{}}],
                 'report':{'stop_reason':later_reason,'total_search_requests':1}}) as discover, \
             patch('compset.adaptive.run_adaptive_comparison',side_effect=compare):
            result=workflows.discover_compset({'listing':'1','budget':8},discovery_result=discovered)
        return result,details,expansions,discover.call_count

    def test_initial_source_stop_keeps_candidates_and_blocks_enrichment_and_expansion(self):
        for reason in ['access_or_rate_limit_429','non_success_response','browser_error','pagination_schema_missing','cursor_cycle']:
            with self.subTest(reason=reason):
                result,details,expansions,count=self.workflow(reason)
                self.assertEqual(count,0)
                self.assertEqual(details,[('1',False),('2',True)])
                self.assertEqual(result['candidates'][0]['title'],'Saved candidate')
                self.assertEqual(result['summary']['source_stop_reason'],reason)
                self.assertTrue(all(item['report']['stop_reason']==reason for item in expansions))

    def test_later_discovery_stop_blocks_new_detail_and_next_expansion(self):
        result,details,expansions,count=self.workflow(None,later_reason='source_or_parser_error')
        self.assertEqual(count,1)
        self.assertEqual(details,[('1',False),('2',False)])
        self.assertEqual(expansions[0]['candidates'][0]['listing_id'],'3')
        self.assertEqual(expansions[1]['report']['stop_reason'],'source_or_parser_error')

    def test_stopped_workflow_uses_real_cache_reader_without_transport(self):
        stamp=datetime.now(timezone.utc).isoformat()
        actual_detail=workflows.listing_detail
        subject={**SUBJECT,'detail_status':'observed','title':'Subject'}
        def detail(identifier,context,stop=None):
            return subject if identifier=='1' else actual_detail(identifier,context,stop)
        def compare(subject,rows,criteria,**kwargs):
            return {'selected':[],'candidates':rows,'summary':{}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cache=root/'cache'/'listings';cache.mkdir(parents=True)
            raw=cache/'2-AED.json';raw.write_text(json.dumps({'observed_at':stamp,'payloads':[]}),encoding='utf-8')
            (cache/'2-AED.parsed.json').write_text(json.dumps({
                'parser_sha256':hashlib.sha256((workflows.ROOT/'compset'/'normalize.py').read_bytes()).hexdigest(),
                'source_mtime_ns':raw.stat().st_mtime_ns,
                'listing':{'listing_id':'2','title':'Cached title','bedrooms':1,'details_observed_at':stamp}}),encoding='utf-8')
            found={'candidates':[{'listing_id':'2','title':'Search title'},{'listing_id':'3','title':'No cached detail'}],
                   'report':{'stop_reason':'browser_error','total_search_requests':1}}
            with patch('compset.workflows.DATA',root),patch('compset.workflows.listing_detail',side_effect=detail), \
                 patch('compset.adaptive.run_adaptive_comparison',side_effect=compare), \
                 patch('scrapling.fetchers.Fetcher.get') as fetch:
                result=workflows.discover_compset({'listing':'1'},discovery_result=found)
            fetch.assert_not_called()
            self.assertEqual([r['title'] for r in result['candidates']],['Cached title','No cached detail'])
            self.assertEqual(result['candidates'][0]['details_observed_at'],stamp)

    def test_budget_and_candidate_cap_are_not_source_failures(self):
        for reason in ['request_budget_reached','candidate_cap_reached']:
            with self.subTest(reason=reason):
                result,details,expansions,count=self.workflow(reason)
                self.assertEqual(details[:2],[('1',False),('2',False)])
                self.assertIsNone(result['summary']['source_stop_reason'])
                self.assertGreater(count,0)


if __name__ == '__main__':unittest.main()
