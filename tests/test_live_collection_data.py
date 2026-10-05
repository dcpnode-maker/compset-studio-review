"""Bounded read-only dashboard projections from synthetic saved evidence."""
from datetime import date, timedelta, datetime, timezone
import hashlib
import json
import lzma
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from contextlib import closing
from unittest.mock import patch

from compset import live_collection_data as view


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding='utf-8')


class LiveCollectionDataTests(unittest.TestCase):
    def test_provider_proxy_quality_needs_fresh_valid_summary(self):
        save(self.collector/'provider-route-quality.json',{
            'schema':'compset.airbnb-route-quality.v1','updated_at':datetime.now(timezone.utc).isoformat(),
            'fresh_neutral_and_recent_airbnb_validated_ipv4':3,'secret':'never exposed'})
        result=view._provider_proxy_quality(self.collector)
        self.assertEqual(result['validated_ipv4'],3)
        self.assertTrue(result['fresh'])
        self.assertNotIn('secret',json.dumps(result))
        save(self.collector/'provider-route-quality.json',{
            'schema':'compset.airbnb-route-quality.v1','updated_at':'2020-01-01T00:00:00+00:00',
            'fresh_neutral_and_recent_airbnb_validated_ipv4':3})
        self.assertIsNone(view._provider_proxy_quality(self.collector)['validated_ipv4'])

    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.base=root/'base';self.base.mkdir()
        self.collector=root/'collector';self.collector.mkdir()
        self.proxy=root/'proxy';self.proxy.mkdir()
        self.control=root/'control';self.control.mkdir()
        self.config={k:str(v) for k,v in [('base_root',self.base),('collector_root',self.collector),
                                           ('proxy_runtime_root',self.proxy),('control_root',self.control)]}
        self.market=self.base/'market.sqlite'
        db=sqlite3.connect(self.market)
        db.executescript('''CREATE TABLE observations(observation_id TEXT PRIMARY KEY,provider TEXT,
          listing_id TEXT,kind TEXT,captured_at TEXT,context_json TEXT);
          CREATE TABLE profile_fields(observation_id TEXT,field_name TEXT,status TEXT,value_json TEXT);
          CREATE TABLE calendar_days(observation_id TEXT,calendar_date TEXT,fields_json TEXT);''')
        now=datetime.now(timezone.utc).isoformat()
        context=json.dumps({'currency':'AED','source_kind':'public_api_response','adults':None,
                            'children':None,'source_url':'https://secret.example'})
        db.executemany('INSERT INTO observations VALUES(?,?,?,?,?,?)',[
            ('old','airbnb','123','profile','2026-01-01T00:00:00+00:00',context),
            ('new','airbnb','123','profile',now,context),
            ('cal','airbnb','123','calendar',now,context)])
        db.executemany('INSERT INTO profile_fields VALUES(?,?,?,?)',[
            ('old','title','observed',json.dumps('Old title')),
            ('new','title','observed',json.dumps('New title')),
            ('new','bedrooms','observed','2'),('new','instant_book','observed','true'),
            ('new','latitude','observed','25.1'),('new','longitude','observed','55.2'),
            ('new','beds','missing','null')])
        self.today=date.today().isoformat()
        db.execute('INSERT INTO calendar_days VALUES(?,?,?)',('cal',self.today,json.dumps({
            'available':{'status':'observed','value':True},
            'bookable':{'status':'null','value':None},
            'minNights':{'status':'observed','value':2},
            'localPriceFormatted':{'status':'null','value':None}})))
        db.commit();db.close()
        save(self.collector/'STATUS.json',{'state':'running','updated_at':now,
            'selected_tasks':10,'new_completed_tasks':3,'new_quarantined_tasks':1,
            'admission':{'effective_pacing':{'hour':360}}})
        save(self.collector/'PROCESS.json',{'launcher_pid':999,'launcher_start_utc_ticks':123})
        save(self.collector/'failure-queue.json',{'immutable_records':[
            {'path':'failures/'+'a'*32+'.json'}]})
        save(self.collector/'failure-queue/failures'/('a'*32+'.json'),{'record':{
            'parent_token':'a'*32,'attempt':{'admitted_at':now,'listing_id':'123',
                'kind':'profile','diagnostic':{'category':'proxy_error','message':'secret'},
                'state':'stopped'}}})
        until=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()
        save(self.proxy/'working_proxies.json',{'global_stop':None,'proxies':[
            {'endpoint':'secret:1','origin':'8.8.8.8','alive':True,'tls_verified':True,'valid_until':until},
            {'endpoint':'secret:2','origin':'8.8.8.8','alive':True,'tls_verified':True,'valid_until':until}]})
        save(self.control/'repairs'/'job.json',{'id':'job','state':'proposed','model':'model-x',
            'summary':'Review proposed fix','secret':'never returned','started_at':now})

    def test_latest_profile_and_distinct_counts_with_unknown_daily_price(self):
        response=view.listings(self.config,{'query':'New','bedrooms':2})
        self.assertEqual(response['total'],1)
        item=response['listings'][0]
        self.assertEqual(item['title'],'New title')
        self.assertEqual(item['beds'],None)
        self.assertTrue(item['instant_book'])
        self.assertEqual(item['fields']['beds'],{'status':'missing','value':None})
        self.assertEqual(view.listings(self.config,{'query':'Old'})['total'],0)
        with patch.object(view,'_process_alive',return_value=False):
            status=view.status(self.config)
        self.assertEqual(status['counts'],{'profiles':1,'calendars':1,'calendar_rows':1,'daily_prices':0})
        self.assertEqual(status['state'],'unavailable')
        self.assertFalse(status['process_alive'])
        self.assertEqual(status['rate']['measured_provider_limit'],None)
        self.assertEqual(status['proxy_pool'],{'healthy':2,'distinct_ipv4':1})
        self.assertEqual(status['progress'],{'completed':3,'total':10,'quarantined':1})
        serialized=json.dumps(status)
        self.assertNotIn('secret',serialized)
        self.assertNotIn(str(self.base),serialized)

    def test_map_covers_all_matching_latest_profiles_and_paginates_points(self):
        with closing(sqlite3.connect(self.market)) as db:
            for index in range(55):
                observation=f'map-{index}'
                listing_id=str(1000+index)
                db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?)',
                    (observation,'airbnb',listing_id,'profile',f'2026-02-{index+1:02d}T00:00:00Z','{}'))
                db.executemany('INSERT INTO profile_fields VALUES(?,?,?,?)',[
                    (observation,'title','observed',json.dumps(f'Dubai stay {index}')),
                    (observation,'bedrooms','observed','2' if index<53 else '3'),
                    (observation,'latitude','observed',json.dumps(0 if index==0 else 25.1)),
                    (observation,'longitude','observed',json.dumps(0 if index==0 else 55.2)),
                    (observation,'beds','observed','2'),
                    (observation,'guest_capacity','observed','4'),
                    (observation,'room_type','observed',json.dumps('Entire home')),
                    (observation,'instant_book','observed','true')])
            # The existing 123 listing has old and new profile observations; only the latest matches.
            db.commit()
        first=view.map(self.config,{'query':'Dubai','bedrooms':2,'limit':50})
        self.assertEqual(first['total'],53)
        self.assertEqual(first['mapped_total'],53)
        self.assertEqual(first['unmapped_total'],0)
        self.assertEqual(len(first['points']),50)
        self.assertEqual(first['next_offset'],50)
        self.assertEqual(first['points'][0]['guest_capacity'],4)
        second=view.map(self.config,{'query':'Dubai','bedrooms':2,'limit':50,'offset':first['next_offset']})
        self.assertEqual(len(second['points']),3)
        self.assertIsNone(second['next_offset'])
        self.assertEqual(len({p['listing_id'] for p in first['points']+second['points']}),53)
        self.assertEqual(view.listings(self.config,{'query':'Dubai','bedrooms':2})['total'],53)
        origin=next(p for p in first['points']+second['points'] if p['listing_id']=='1000')
        self.assertEqual((origin['latitude'],origin['longitude']),(0,0))
        self.assertEqual(set(origin),{'listing_id','title','latitude','longitude','bedrooms',
            'beds','guest_capacity','room_type','instant_book'})

    def test_map_deduplicates_latest_and_counts_invalid_coordinates_as_unmapped(self):
        with closing(sqlite3.connect(self.market)) as db:
            rows=[('bool-coord','2001',True,55.2),('nan-coord','2002',float('nan'),55.2),
                  ('range-coord','2003',91,55.2),('lat-zero','2004',0,0)]
            for observation,listing_id,latitude,longitude in rows:
                db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?)',
                    (observation,'airbnb',listing_id,'profile','2026-03-01T00:00:00Z','{}'))
                db.executemany('INSERT INTO profile_fields VALUES(?,?,?,?)',[
                    (observation,'title','observed',json.dumps(observation)),
                    (observation,'bedrooms','observed','2'),
                    (observation,'latitude','observed',json.dumps(latitude)),
                    (observation,'longitude','observed',json.dumps(longitude))])
            db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?)',
                ('newer-bool','airbnb','2001','profile','2026-03-02T00:00:00Z','{}'))
            db.executemany('INSERT INTO profile_fields VALUES(?,?,?,?)',[
                ('newer-bool','title','observed',json.dumps('latest valid')),
                ('newer-bool','bedrooms','observed','2'),
                ('newer-bool','latitude','observed','25.2'),
                ('newer-bool','longitude','observed','55.3')])
            db.commit()
        result=view.map(self.config,{'bedrooms':2})
        by_id={point['listing_id']:point for point in result['points']}
        self.assertEqual(result['total'],5)
        self.assertEqual(result['mapped_total'],3)
        self.assertEqual(result['unmapped_total'],2)
        self.assertEqual(by_id['2001']['title'],'latest valid')
        self.assertIn('2004',by_id)
        self.assertNotIn('2002',by_id)
        self.assertNotIn('2003',by_id)
        for query in ({'limit':2001},{'offset':-1},{'query':'x'*121}):
            with self.assertRaises(ValueError):view.map(self.config,query)

    def test_map_projection_batches_profile_fields_past_sqlite_parameter_limit(self):
        with closing(sqlite3.connect(self.market)) as db:
            for index in range(1005):
                observation=f'bulk-{index}'
                db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?)',
                    (observation,'airbnb',str(5000+index),'profile',f'2026-04-{index%28+1:02d}T00:00:00Z','{}'))
                db.executemany('INSERT INTO profile_fields VALUES(?,?,?,?)',[
                    (observation,'title','observed',json.dumps(f'Bulk stay {index}')),
                    (observation,'latitude','observed','25.1'),
                    (observation,'longitude','observed','55.2')])
            db.commit()
        result=view.map(self.config,{'query':'Bulk'})
        self.assertEqual(result['total'],1005)
        self.assertEqual(result['mapped_total'],1005)
        self.assertEqual(len(result['points']),1005)
        self.assertIsNone(result['next_offset'])

    def test_calendar_preserves_unknown_days_and_context(self):
        result=view.calendar(self.config,{'listing_id':'123','start':self.today,'days':2})
        self.assertEqual(len(result['dates']),2)
        self.assertTrue(result['dates'][0]['available'])
        self.assertIsNone(result['dates'][0]['bookable'])
        self.assertEqual(result['dates'][0]['min_nights'],2)
        self.assertIsNone(result['dates'][0]['nightly_price'])
        self.assertIsNone(result['dates'][1]['available'])
        self.assertIsNone(result['context']['party']['adults'])
        self.assertNotIn('source_url',result['context'])
        self.assertIsNone(view.calendar(self.config,{'listing_id':'999','start':self.today,'days':1})['dates'][0]['available'])

    def test_full_profile_has_latest_values_and_scoped_booking_context(self):
        before=self.market.read_bytes()
        result=view.profile(self.config,{'listing_id':'123'})
        self.assertEqual(result['fields']['title']['value'],'New title')
        self.assertEqual(result['fields']['beds'],{'status':'missing','value':None})
        self.assertIsNone(result['context']['adults'])
        self.assertNotIn('secret.example',json.dumps(result))
        self.assertEqual(view.profile(self.config,{'listing_id':'999'})['fields'],{})
        with self.assertRaises(ValueError):view.profile(self.config,{'listing_id':'../private'})
        self.assertEqual(before,self.market.read_bytes())

    def test_studio_filter_requires_explicit_studio_or_zero_bedrooms(self):
        with closing(sqlite3.connect(self.market)) as db:
            db.execute("UPDATE profile_fields SET status='missing',value_json='null' WHERE observation_id='new' AND field_name='bedrooms'")
            db.commit()
        self.assertEqual(view.listings(self.config,{'bedrooms':0})['total'],0)
        with closing(sqlite3.connect(self.market)) as db:
            db.execute('INSERT INTO profile_fields VALUES(?,?,?,?)',('new','studio','observed','true'))
            db.commit()
        result=view.listings(self.config,{'bedrooms':0})
        self.assertEqual(result['total'],1)
        self.assertIsNone(result['listings'][0]['bedrooms'])

    def test_query_bounds_and_no_mutation(self):
        before=self.market.read_bytes()
        for query in ({'limit':101},{'offset':-1},{'query':'x'*121},{'bedrooms':-1}):
            with self.assertRaises(ValueError):view.listings(self.config,query)
        for query in ({'listing_id':'abc','start':self.today},
                      {'listing_id':'123','start':'2026-1-1'},
                      {'listing_id':'123','start':self.today,'days':367},
                      {'listing_id':'123','start':self.today,'extra':'x'},
                      {'listing_id':'123','start':'9999-12-31','days':2}):
            with self.assertRaises(ValueError):view.calendar(self.config,query)
        self.assertEqual(self.market.read_bytes(),before)

    def test_waiting_owner_stays_healthy_and_repair_state_is_visible(self):
        saved=json.loads((self.collector/'STATUS.json').read_text())
        saved['state']='waiting_pool';save(self.collector/'STATUS.json',saved)
        repair=self.control/'repairs'/'job.json'
        data=json.loads(repair.read_text());data.update(state='needs_attention',
            summary='Private path C:\\private\\trace.log');save(repair,data)
        with patch.object(view,'_process_alive',return_value=True):
            answer=view.status(self.config)
        self.assertEqual(answer['state'],'waiting_pool')
        self.assertTrue(answer['process_alive'])
        self.assertEqual(answer['refresh']['state'],'running')
        self.assertEqual(answer['repairs'][0]['state'],'needs_attention')
        self.assertNotIn('private',json.dumps(answer))
        self.assertEqual(answer['revision'],view.listings(self.config)['revision'])

    def test_discovery_wait_is_visible_without_claiming_provider_collection(self):
        saved=json.loads((self.collector/'STATUS.json').read_text())
        saved.update(state='waiting_discovery',discovery_pages=8,discovered_listing_ids=123,
            new_in_bounds_listing_ids=90,discovery_state='reviewed_search_plan_exhausted')
        save(self.collector/'STATUS.json',saved)
        with patch.object(view,'_process_alive',return_value=True):answer=view.status(self.config)
        self.assertEqual(answer['state'],'waiting_discovery')
        self.assertEqual(answer['refresh']['state'],'waiting')
        self.assertEqual(answer['discovery']['new_in_bounds_ids'],90)
        self.assertFalse(answer['discovery']['full_market_census'])

    def test_unreadable_coverage_is_unknown_not_zero(self):
        with patch.object(view,'_counts',side_effect=sqlite3.OperationalError('busy')),patch.object(view,'_database',side_effect=sqlite3.OperationalError('busy')):
            answer=view.status(self.config)
        self.assertTrue(all(v is None for v in answer['counts'].values()))
        self.assertIsNone(answer['rate']['validated_last_hour'])
        self.assertEqual(answer['sources'][0]['state'],'unavailable')

    def test_hotel_rates_keep_indicative_and_approximate_separate(self):
        hotel=Path(self.tmp.name)/'hotel';hotel.mkdir();self.config['hotel_root']=str(hotel)
        db=sqlite3.connect(hotel/'market.sqlite3')
        db.executescript('''CREATE TABLE hotels(id TEXT PRIMARY KEY,name TEXT);
          CREATE TABLE profile_versions(id TEXT PRIMARY KEY,hotel_id TEXT);
          CREATE TABLE profile_observations(id TEXT,version_id TEXT,observed_at TEXT);
          CREATE TABLE blobs(sha TEXT PRIMARY KEY,codec TEXT,bytes INTEGER,payload BLOB);
          CREATE TABLE rates(id TEXT PRIMARY KEY,hotel_id TEXT,checkin TEXT,provider TEXT,
            channel TEXT,observed_at TEXT,payload_sha TEXT);''')
        db.execute('INSERT INTO hotels VALUES(?,?)',('hotel:1','Test Hotel'))
        for name,amount,approx,when in [('older','1000',None,'2026-01-01T00:00:00Z'),
                                        ('new','1200',None,'2026-01-02T00:00:00Z'),
                                        ('approx',None,1450.0,'2026-01-02T00:01:00Z')]:
            payload={'hotel_id':'hotel:1','checkin':self.today,
                'checkout':(date.fromisoformat(self.today)+timedelta(days=1)).isoformat(),
                'basis':'indicative_calendar_minimum','amount':amount,
                'approximate_amount':approx,'currency':'INR','identity_verified':True,
                'context_verified':False,'taxes_included':None,'mandatory_fees_included':None,
                'public_eligibility_verified':None}
            raw=json.dumps(payload).encode();sha=hashlib.sha256(raw).hexdigest()
            db.execute('INSERT INTO blobs VALUES(?,?,?,?)',(sha,'xz',len(raw),lzma.compress(raw)))
            db.execute('INSERT INTO rates VALUES(?,?,?,?,?,?,?)',
                       (name,'hotel:1',self.today,'google_hotels','desktop_web',when,sha))
        db.commit();db.close()
        response=view.hotels(self.config,{'hotel_id':'hotel:1','start':self.today,'days':1})
        self.assertEqual(response['total'],1)
        self.assertEqual(response['rate_count'],2)
        self.assertEqual({r['price_status'] for r in response['rates']},{'indicative','approximate'})
        self.assertTrue(all(not r['comparable_public_total'] for r in response['rates']))
        self.assertTrue(all(r['taxes_included'] is None for r in response['rates']))
        self.assertEqual(next(r['amount'] for r in response['rates'] if r['price_status']=='indicative'),'1200')


if __name__=='__main__':unittest.main()
