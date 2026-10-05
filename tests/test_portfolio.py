import base64
import json
from pathlib import Path
import unittest
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch
from compset.portfolio import (parse_portfolio,validate_profile_url,subject_profile_identity,redact_catalog,
    collect_property_details,collect_catalog_details,collect_website_quote,collect_website_inventory)


def gid(namespace,identifier):return base64.b64encode(f'{namespace}:{identifier}'.encode()).decode()

class PortfolioTests(unittest.TestCase):
    def test_profile_listing_ids_and_declared_count_only_for_requested_identity(self):
        payload={'data':[{'__typename':'ContextualUser','id':gid('ContextualUser','123'),
            'staySupplyListings':{'pageInfo':{'totalCount':60,'hasNextPage':True},'edges':[
                {'node':{'__typename':'StaySupplyListing','id':gid('StaySupplyListing','5777080')}},
                {'node':{'__typename':'StaySupplyListing','id':gid('StaySupplyListing','5777080')}}]},
            'reviews':{'pageInfo':{'totalCount':5311}},'biography':'must not persist','phone':'private'},
            {'__typename':'ContextualUser','id':gid('ContextualUser','999'),
             'staySupplyListings':{'pageInfo':{'totalCount':900},'edges':[
                {'node':{'__typename':'StaySupplyListing','id':gid('StaySupplyListing','555')}}]}}]}
        r=parse_portfolio(payload,'123')
        self.assertEqual(r['listing_ids'],['5777080']);self.assertEqual(r['declared_listing_count'],60)
        self.assertNotIn('private',json.dumps(r));self.assertNotIn('biography',json.dumps(r))
        self.assertNotIn('555',json.dumps(r));self.assertNotIn('5311',json.dumps(r))

    def test_profile_unknown_count_or_wrong_namespace_stays_unknown(self):
        r=parse_portfolio({'__typename':'ContextualUser','id':gid('User','123')},'123')
        self.assertEqual(r['listing_ids'],[]);self.assertIsNone(r['declared_listing_count'])
        self.assertIsNone(r['host_name'])

    def test_profile_url_exact_public_origin(self):
        good='https://www.airbnb.co.in/users/profile/1462596679799875992?previous_page_name=PdpHomeMarketplace'
        self.assertEqual(validate_profile_url(good),'1462596679799875992')
        for bad in (good.replace('airbnb.co.in','airbnb.co.in.evil.com'),good.replace('https:','http:'),
                    good.replace('/users/profile/','/account/'),good.replace('www.airbnb.co.in','user@www.airbnb.co.in')):
            with self.assertRaises(ValueError):validate_profile_url(bad)


class CatalogCollectionTests(unittest.TestCase):
    def property(self):
        return {'id':'241600','slug':'bnbme-public-home-241600','currency':'AED',
                'property_details_uuid':'cdc38a8c-4bcb-4498-9739-1c1bf720cda8'}
    def context(self):return {'checkin':'2026-10-17','checkout':'2026-10-20','adults':2}

    def test_host_identity_mapping_requires_both_explicit_passport_ids(self):
        data={'hostInfo':{'passportData':{'name':'Laya','userId':gid('DemandUser','16121555'),
                   'contextualUserId':gid('ContextualUser','1462596679799875992')}}}
        identity=subject_profile_identity(data,'1462596679799875992')
        self.assertEqual(identity['host_id'],'16121555')
        self.assertIsNone(subject_profile_identity(data,'different'))
        data['hostInfo']['passportData']['userId']=gid('OtherUser','16121555')
        self.assertIsNone(subject_profile_identity(data,'1462596679799875992'))

    def test_signed_urls_contacts_and_internal_audit_identity_are_removed(self):
        data={'image':'https://cdn.example.com/image.webp?AWSAccessKeyId=private&Signature=secret',
              'title':'Public home','phone':'private','created_by_uuid':'staff-id',
              'description':'contact name@example.com','beds':2}
        clean=redact_catalog(data)
        self.assertEqual(clean['image'],'https://cdn.example.com/image.webp')
        for value in ('private','secret','staff-id','name@example.com'):self.assertNotIn(value,json.dumps(clean))
        self.assertEqual(clean['beds'],2)

    def test_actual_dated_page_verifies_active_status_without_invented_quotes(self):
        context=self.context();property_record=dict(self.property(),status='ACTIVE',non_refundable_price=None,refundable_price=None)
        response=SimpleNamespace(status=200,css=lambda selector:[SimpleNamespace(text=json.dumps({'props':{'pageProps':{
            'singleHotelDetails':property_record,'query':{'startDate':'2026-10-17','endDate':'2026-10-20','adults':'2'}}}}))])
        with patch('scrapling.fetchers.FetcherSession') as session:
            session.return_value.__enter__.return_value.get.return_value=response
            result=collect_property_details(self.property(),context)
        self.assertEqual(result['report']['active_status'],'ACTIVE')
        self.assertFalse(result['report']['price_values_observed'])
        self.assertTrue(result['price_fields']['dated_context_matches'])
        self.assertIsNone(result['price_fields']['refundable_price'])

    def test_quote_replays_observed_pet_spelling_and_reports_guest_currency_basis(self):
        result={'body':{'data':{'after_discount':{'total':2288}}},'report':{'status':200}}
        with patch('compset.portfolio._public_price_read',return_value=result) as read:
            quote=collect_website_quote(self.property(),self.context())
        params=read.call_args.args[1]
        self.assertEqual(params['no_of_pats'],'0');self.assertNotIn('adults',params)
        self.assertFalse(quote['report']['price_endpoint_guest_parameter'])
        self.assertFalse(quote['report']['bookability_verified'])
        self.assertEqual(quote['context']['currency'],'AED')

    def test_inventory_limit_is_inclusive365_and_never_implies_booked(self):
        with self.assertRaises(ValueError):
            collect_website_inventory(self.property(),{'calendar_start_date':'2027-01-01','calendar_end_date':'2026-01-01'})
        response={'body':{'data':{'2026-09-01':[{'available_room':0,'non_refundable_price':339}]}},'report':{'status':200}}
        with patch('compset.portfolio._public_price_read',return_value=response):
            result=collect_website_inventory(self.property(),{})
        self.assertEqual(result['report']['observed_date_count'],1)
        self.assertIn('no booked-status inference',result['report']['available_room_meaning'])

    def test_access_limit_stops_serial_batch_and_checkpoint_resume(self):
        property_record=dict(self.property(),status='ACTIVE')
        detail={'property':property_record,'source_url':'https://bnbmehomes.com/property/public','observed_at':'now',
            'request_context':self.context(),'observed_query':{},'price_fields':{},'report':{'status':200,'stop_reason':None}}
        blocked={'body':None,'report':{'status':429,'stop_reason':'access_or_rate_limit_429'}}
        with TemporaryDirectory() as temporary,patch('compset.portfolio.collect_property_details',return_value=detail) as get_detail,\
             patch('compset.portfolio.collect_website_quote',return_value=blocked) as get_quote,\
             patch('compset.portfolio.collect_website_inventory') as get_inventory,patch('time.sleep'):
            path=Path(temporary)/'checkpoint.json';catalog={'properties':[self.property(),dict(self.property(),id='other')]}
            result=collect_catalog_details(catalog,self.context(),path)
            self.assertEqual(result['report']['requests_this_run'],2)
            self.assertEqual(result['report']['stop_reason'],'access_or_rate_limit_429')
            self.assertTrue(path.exists());self.assertFalse(result['report']['complete_for_catalog_rows'])
            collect_catalog_details(catalog,self.context(),path)
            self.assertEqual(get_detail.call_count,1);self.assertEqual(get_quote.call_count,1);get_inventory.assert_not_called()


    def test_sold_out_quote_response_is_retained_and_scoped_to_the_stay(self):
        from compset.portfolio import _public_price_read,QUOTE_URL
        response=SimpleNamespace(status=200,body=b'{"message":"SOLD_OUT"}')
        with patch('scrapling.fetchers.FetcherSession') as session:
            session.return_value.__enter__.return_value.get.return_value=response
            result=_public_price_read(QUOTE_URL,{'from_date':'2026-10-17','to_date':'2026-10-20'})
        self.assertEqual(result['body'],{'message':'SOLD_OUT'})
        self.assertEqual(result['report']['stay_quote_availability'],'SOLD_OUT')
        self.assertIsNone(result['report']['stop_reason'])
        self.assertEqual(result['request_context']['to_date'],'2026-10-20')

    def test_manual_pause_flag_stops_before_first_http_and_preserves_checkpoint(self):
        with TemporaryDirectory() as temporary,patch('compset.portfolio.collect_property_details') as read:
            path=Path(temporary)/'checkpoint.json';(Path(temporary)/'pause-inventory.flag').write_text('pause')
            result=collect_catalog_details({'properties':[self.property()]},self.context(),path)
            read.assert_not_called();self.assertTrue(path.exists())
            self.assertEqual(result['report']['stop_reason'],'manual_pause')
            self.assertEqual(result['report']['requests_this_run'],0)

    def test_unknown_json_quote_body_is_preserved_without_values(self):
        from compset.portfolio import _public_price_read,QUOTE_URL
        response=SimpleNamespace(status=200,body=b'{"message":"New upstream state","other":[1]}')
        with patch('scrapling.fetchers.FetcherSession') as session:
            session.return_value.__enter__.return_value.get.return_value=response
            result=_public_price_read(QUOTE_URL,{})
        self.assertEqual(result['body']['other'],[1])
        self.assertEqual(result['report']['stop_reason'],'unknown_price_schema')


    def test_shared_transport_is_reused_without_opening_a_per_request_session(self):
        context=self.context();record=dict(self.property(),status='ACTIVE')
        response=SimpleNamespace(status=200,css=lambda selector:[SimpleNamespace(text=json.dumps({'props':{'pageProps':{
            'singleHotelDetails':record,'query':{'startDate':'2026-10-17','endDate':'2026-10-20','adults':'2'}}}}))])
        transport=SimpleNamespace(get=lambda url:response)
        with patch('scrapling.fetchers.FetcherSession') as factory:
            result=collect_property_details(self.property(),context,session=transport)
            factory.assert_not_called()
        self.assertEqual(result['report']['active_status'],'ACTIVE')

    def test_leap_year_inventory_window_is_explicitly_clipped_to365_days(self):
        response={'body':{'data':{}},'report':{'status':200}}
        with patch('compset.portfolio._public_price_read',return_value=response) as read:
            result=collect_website_inventory(self.property(),{'calendar_start_date':'2027-03-01','calendar_end_date':'2028-02-29'})
        self.assertEqual(read.call_args.args[1]['to_date'],'2028-02-28')
        self.assertTrue(result['report']['calendar_window_clipped_to_365_days'])
        self.assertEqual(result['report']['requested_end_date_inclusive'],'2028-02-29')

    def test_missing_inventory_ids_are_counted_as_placeholders_not_free_nights(self):
        response={'body':{'data':{'2026-09-01':[{'inventory_uuid':None,'available_room':0,'non_refundable_price':0}]}},'report':{'status':200}}
        with patch('compset.portfolio._public_price_read',return_value=response):
            result=collect_website_inventory(self.property(),{})
        self.assertEqual(result['report']['placeholder_date_count'],1)
        self.assertIn('no booked-status inference',result['report']['available_room_meaning'])


    def test_checkpoint_replace_retries_a_brief_windows_read_lock(self):
        from compset.portfolio import _atomic_checkpoint
        with TemporaryDirectory() as temporary,patch.object(Path,'replace',side_effect=[PermissionError('reader locked'),None]) as replace,patch('time.sleep') as sleep:
            _atomic_checkpoint(Path(temporary)/'state.json',{'observations':[]})
            self.assertEqual(replace.call_count,2);sleep.assert_called_once_with(0.25)

if __name__=='__main__':unittest.main()
