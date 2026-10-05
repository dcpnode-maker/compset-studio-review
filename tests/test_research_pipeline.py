import copy
from contextlib import closing
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from compset.rate_policy import comparison_key,comparable_minima,freshness,calendar_windows
from compset.provider_queue import Queue
from compset.ota_tool_adapters import normalize_vio_calendar,normalize_vio_offers,normalize_expedia
from compset.google_calendar_network import currency_option


def task(**overrides):
    return {'provider':'vio','vertical':'hotel','method':'connector_calendar',
            'hotel_id':'osm:node:11740798982','provider_id':'1659409','identity_verified':True,
            'start_date':'2026-09-30','end_date':'2026-10-30','currency':'INR',
            'party':[{'adults':1,'children':[]}],'mode':'calendar',**overrides}


def capture():
    return {'observed_at':datetime.now(timezone.utc).isoformat(),'currency':'INR','nights':1,
            'startDate':'2026-09-30','endDate':'2026-10-30','roomConfiguration':[{'adults':1,'children':[]}],
            'priceScope':'all_rooms_combined','priceLogic':'base','complete':True,
            'availability':[{'hotelId':'1659409','checkIn':'2026-10-01',
                             'cheapestRate':{'base':100,'taxes':18,'hotelFees':0,'displayPrice':100}}]}


class PolicyTests(unittest.TestCase):
    def test_fresh_fetch_does_not_attest_upstream(self):
        now=datetime.now(timezone.utc)
        result=freshness((now-timedelta(days=2)).isoformat(),now=now,http_age_seconds=0)
        self.assertFalse(result['capture_recent'])
        self.assertEqual(result['upstream_freshness'],'unknown')
        self.assertFalse(result['uncached_verified'])
        with self.assertRaises(ValueError): freshness((now+timedelta(seconds=1)).isoformat(),now=now)

    def test_comparable_scope_kind_and_nested_unknown(self):
        row={'hotel_id':'hotel','checkin':'2026-10-01','checkout':'2026-10-02','currency':'INR',
             'amount_basis':'one_night_display','price_scope':'per_room','party':[{'adults':1,'children':[]}],
             'taxes_included':True,'fees_included':True,'room_product':'single','meals':'none',
             'cancellation':'nonrefundable','payment':'pay_now','membership':'none','coupon':'none',
             'evidence_kind':'provider_display','property_identity_verified':True,'party_verified':True,
             'terms_verified':True,'amount':'100'}
        self.assertIsNotNone(comparison_key(row))
        self.assertNotEqual(comparison_key(row),comparison_key({**row,'price_scope':'all_rooms_combined'}))
        self.assertNotEqual(comparison_key(row),comparison_key({**row,'evidence_kind':'direct_quote'}))
        self.assertIsNone(comparison_key({**row,'room_product':{'id':None}}))
        self.assertEqual(comparable_minima([row,{**row,'amount':'90'}])['groups'][0]['amount'],'90')

    def test_exact_365_plan(self):
        from datetime import date
        windows=calendar_windows('2026-09-30')
        self.assertEqual(sum((date.fromisoformat(w['end_date'])-date.fromisoformat(w['start_date'])).days+1 for w in windows),365)
        self.assertEqual(windows[-1]['end_date'],'2027-09-29')

    def test_poll_complete_is_not_price_coverage(self):
        result=normalize_vio_calendar(capture(),task())
        self.assertTrue(result['provider_poll_complete'])
        self.assertFalse(result['price_date_coverage_complete'])
        self.assertEqual(result['unknown_dates'],30)

    def test_reject_context_identity_money(self):
        for key,value in [('currency','USD'),('roomConfiguration',[{'adults':True,'children':[]}])]:
            with self.assertRaises(ValueError): normalize_vio_calendar({**capture(),key:value},task())
        raw=capture();raw['availability'][0]['hotelId']='wrong'
        self.assertEqual(normalize_vio_calendar(raw,task())['observed_dates'],0)
        raw=capture();raw['availability'][0]['cheapestRate']['displayPrice']=120
        self.assertEqual(normalize_vio_calendar(raw,task())['observed_dates'],0)

    def test_real_canaries(self):
        p=Path(__file__).resolve().parents[1]/'data/research-pipelines/20260930/aketa-vio-expedia-canary.json'
        raw=json.loads(p.read_text())
        calendar={**raw['vio_calendar'],'observed_at':raw['fetched_at']}
        result=normalize_vio_calendar(calendar,task(start_date='2026-10-01',end_date='2026-10-07'))
        self.assertEqual(result['observed_dates'],5)
        offers={**raw['vio_offers'],'observed_at':raw['fetched_at']}
        target=task(start_date='2026-10-01',end_date='2026-10-01',mode='detailed',method='connector_offers')
        self.assertEqual(len(normalize_vio_offers(offers,target)['rates']),6)
        offers=copy.deepcopy(offers);offers['hotels'][0]['offers']['items'][0]['rate']['displayPrice']=1
        with self.assertRaises(ValueError):normalize_vio_offers(offers,target)
        expedia={**raw['expedia'],'observed_at':raw['fetched_at']}
        target=task(provider='expedia',provider_id='92850456',method='connector_display',mode='detailed',currency='USD',start_date='2026-10-01',end_date='2026-10-01')
        self.assertEqual(normalize_expedia(expedia,target)['rates'][0]['amount'],'130')
        with self.assertRaises(ValueError):normalize_expedia(expedia,{**target,'currency':'INR'})
        expedia=copy.deepcopy(expedia);expedia['data'][0]['url']='https://www.expedia.com/.h123.Hotel-Information'
        with self.assertRaises(ValueError):normalize_expedia(expedia,target)

    def test_currency_requires_unique_observed_option(self):
        option={'text':'Indian Rupee (INR)','selector':'observed'}
        self.assertEqual(currency_option({'controls':[option]}),option)
        self.assertIsNone(currency_option({'controls':[option,option]}))


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.queue=Queue(self.temp.name)

    def test_typed_plan_and_unsupported_provider(self):
        for bad in [{'hotel_id':[]},{'provider_id':True},{'currency':False},
                    {'party':[{'adults':False,'children':None}]},{'identity_verified':1}]:
            with self.assertRaises(ValueError): self.queue.plan(task(**bad))
        ident=self.queue.plan(task(provider='goibibo',method='public_browser'))
        self.assertEqual(self.queue.get(ident)['state'],'unsupported')
        self.assertFalse(self.queue.claim(ident))
        ident=self.queue.plan(task(party=[{'adults':1,'children':[],'authorization':'secret'}]))
        self.assertNotIn('secret',self.queue.get(ident)['task_json'])

    def test_durable_capture_resume_history_and_privacy(self):
        ident=self.queue.plan(task());self.assertTrue(self.queue.claim(ident))
        raw={**capture(),'session_token':'secret','raw_body':'private','headers':{'cookie':'secret'}}
        self.queue.capture(ident,raw)
        stored=self.queue.get(ident)['capture_json']
        self.assertNotIn('secret',stored);self.assertNotIn('raw_body',stored)
        result=self.queue.run([ident],lambda _:self.fail('network must not run'),normalize_vio_calendar,budget=1,parser_version='2')
        self.assertEqual(result['capture_calls'],0)
        self.assertEqual(result['results'][0]['observed_dates'],1)
        self.assertFalse(self.queue.refresh(ident))
        self.assertTrue(self.queue.refresh(ident,now=datetime.now(timezone.utc)+timedelta(days=1)))
        with closing(self.queue.connect()) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM provider_capture_history').fetchone()[0],1)

    def test_access_stop_survives_new_window_restart(self):
        for status in [401,403,429,'challenge']:
            with self.subTest(status=status):
                q=Queue(Path(self.temp.name)/str(status));first=q.plan(task())
                blocked={'http_status':status} if type(status) is int else {'challenge_detected':True}
                result=q.run([first],lambda _:blocked,normalize_vio_calendar,budget=1,parser_version='1')
                self.assertEqual(result['capture_calls'],1)
                q=Queue(Path(self.temp.name)/str(status));second=q.plan(task(start_date='2026-11-01',end_date='2026-11-30'))
                result=q.run([second],lambda _:self.fail('blocked scope'),normalize_vio_calendar,budget=1,parser_version='1',fresh=True)
                self.assertEqual(result['capture_calls'],0)
                other=q.plan(task(method='connector_offers',mode='detailed',start_date='2026-10-01',end_date='2026-10-01'))
                self.assertFalse(q.claim(other))

    def test_money_leaf_cannot_hide_private_object(self):
        ident=self.queue.plan(task());self.queue.claim(ident)
        raw=capture();raw['availability'][0]['cheapestRate']['base']={'session_token':'secret'}
        with self.assertRaises(ValueError): self.queue.capture(ident,raw)
        self.assertIsNone(self.queue.get(ident)['capture_json'])

    def test_interrupted_not_automatically_replayed(self):
        ident=self.queue.plan(task());self.queue.claim(ident)
        self.assertEqual(self.queue.interrupted(),1)
        self.assertEqual(self.queue.run([ident],lambda _:self.fail('uncertain task'),normalize_vio_calendar,budget=1,parser_version='1')['capture_calls'],0)

    def test_failure_does_not_abort_other_provider(self):
        first=self.queue.plan(task());second=self.queue.plan(task(provider='expedia',provider_id='92850456',method='connector_display',mode='detailed',start_date='2026-10-01',end_date='2026-10-01',currency='USD'))
        def fetch(target):
            if target['provider']=='vio': raise RuntimeError('transport failed')
            return {'observed_at':datetime.now(timezone.utc).isoformat(),'occupants':[{'adults':1,'child_ages':[]}],'data':[]}
        with patch('compset.provider_queue.time.sleep'):
            result=self.queue.run([first,second],fetch,lambda raw,target:{'rates':[]},budget=2,parser_version='1')
        self.assertEqual(result['capture_calls'],2)
        self.assertEqual(len(result['results']),1)
        self.assertEqual(self.queue.get(first)['state'],'uncertain')


if __name__=='__main__':unittest.main()
