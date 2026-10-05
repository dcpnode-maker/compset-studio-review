import base64
import json
from types import SimpleNamespace
import unittest
from compset.discovery import (circle_bounds,distance_km,listing_identifier,parse_search,replay_tiles,
                                search_operation,split_bounds,tile_request,MAX_REQUESTS)

SUBJECT={'listing_id':'1','latitude':25.1929,'longitude':55.2716}

def row(identifier='2',lat=25.193,lng=55.272):
    return {'demandStayListing':{'id':base64.b64encode(('DemandStayListing:'+identifier).encode()).decode(),
            'location':{'coordinate':{'latitude':lat,'longitude':lng}}},
            'subtitle':'Public home','avgRatingLocalized':'4.92','avgRatingA11yLabel':'4.92 out of 5, 1,234 reviews',
            'structuredContent':{'primaryLine':[{'body':'1 bedroom'},{'body':'2 king beds'},{'body':'1.5 bathrooms'}]}}

def response_body(rows=None,cursors=None):
    return {'data':{'presentation':{'staysSearch':{'results':{'searchResults':rows or [],
        'paginationInfo':{'pageCursors':cursors or []}}}}}}

def template():
    req={'cursor':'observed-page-two','rawParams':[{'filterName':k,'filterValues':['0']} for k in ('neLat','neLng','swLat','swLng')],
         'skipHydrationListingIds':['2'],'preferredStayListings':[{'listingId':'2'}]}
    return {'url':'https://www.airbnb.co.in/api/v3/StaysSearch/current?operationName=StaysSearch',
        'method':'POST','headers':{'cookie':'private-cookie'},'body':{'operationName':'StaysSearch',
        'variables':{'staysSearchRequest':req},'extensions':{'persistedQuery':{'sha256Hash':'current','version':1}}}}

class FakeSession:
    def __init__(self,bodies=None,status=200,error=None):self.calls=[];self.bodies=bodies or [];self.status=status;self.error=error
    def post(self,url,**kwargs):
        self.calls.append((url,kwargs))
        if self.error:raise self.error
        body=self.bodies[min(len(self.calls)-1,len(self.bodies)-1)] if self.bodies else response_body([row()])
        return SimpleNamespace(status=self.status,body=json.dumps(body).encode())

class DiscoveryTests(unittest.TestCase):
    def test_current_schema_dedup_subject_missing_and_counts(self):
        parsed=parse_search(response_body([row('1'),row(),row()]),SUBJECT,'https://www.airbnb.com/search')
        self.assertEqual(len(parsed['candidates']),1)
        candidate=parsed['candidates'][0]
        self.assertEqual(candidate['listing_id'],'2')
        self.assertEqual([candidate[k] for k in ('bedrooms','beds','bathrooms','review_count')],[1,2,1.5,1234])
        self.assertIsNone(candidate['host_listing_count']);self.assertIsNone(candidate['person_capacity'])
        self.assertIsNone(candidate['room_type']);self.assertIsNone(candidate['amenities'])
        self.assertLess(candidate['distance_km'],0.1)

    def test_map_rows_preserved_outside_circle_before_comparison(self):
        body=response_body([row('2'),row('3',25.25,55.3)])
        parsed=parse_search(body,SUBJECT,'source')
        self.assertEqual(len(parsed['candidates']),2)
        self.assertGreater(parsed['candidates'][1]['distance_km'],2)

    def test_null_rating_labels_and_formatted_display_stay_auditable(self):
        first=row();first['avgRatingLocalized']='4.92 (1,234)'
        parsed=parse_search(response_body([first]),SUBJECT,'source')['candidates'][0]
        self.assertEqual(parsed['rating'],4.92)
        self.assertEqual(parsed['search_rating_display'],'4.92 (1,234)')
        first['avgRatingA11yLabel']=None;first['avgRatingLocalized']=None
        parsed=parse_search(response_body([first]),SUBJECT,'source')['candidates'][0]
        self.assertIsNone(parsed['rating']);self.assertIsNone(parsed['review_count'])

    def test_final_response_candidates_are_all_retained_at_candidate_threshold(self):
        session=FakeSession([response_body([row('2'),row('3'),row('4')])])
        result=replay_tiles(template(),SUBJECT,session,bounds=circle_bounds(25,55,1),max_candidates=2)
        self.assertEqual(len(session.calls),1)
        self.assertEqual(len(result['candidates']),3)
        self.assertEqual(result['report']['stop_reason'],'candidate_cap_reached')

    def test_arbitrary_templates_are_rejected_before_any_http(self):
        session=FakeSession();bad=template();bad['url']='https://example.com/api/v3/StaysSearch/current'
        with self.assertRaises(ValueError):
            replay_tiles(bad,SUBJECT,session,bounds=circle_bounds(25,55,1))
        self.assertEqual(session.calls,[])

    def test_distance_and_id_are_bounded_numeric(self):
        self.assertEqual(distance_km(25,55,25,55),0)
        self.assertIsNone(distance_km(None,55,25,55))
        self.assertIsNone(listing_identifier('not-base64'))
        self.assertIsNone(listing_identifier(base64.b64encode(b'Host:123').decode()))

    def test_query_allowlist_rejects_mutations_other_hosts_and_operations(self):
        t=template();self.assertTrue(search_operation(t['url'],t['method'],t['body']))
        for url in (t['url'].replace('airbnb.co.in','airbnb.co.in.evil.com'),t['url'].replace('https:','http:'),
                    t['url'].replace('StaysSearch','CreateReservation'),t['url']+'&query=mutation'):
            self.assertFalse(search_operation(url,'POST',t['body']))
        self.assertFalse(search_operation(t['url'],'POST',dict(t['body'],query='mutation Booking{}')))

    def test_bounds_tiles_cover_original_circle_bbox(self):
        b=circle_bounds(25.1929,55.2716,2);cells=split_bounds(b)
        self.assertEqual(len(cells),4)
        self.assertEqual(min(c['swLat'] for c in cells),b['swLat'])
        self.assertEqual(max(c['neLng'] for c in cells),b['neLng'])

    def test_observed_body_hash_preserved_cursor_changed_without_secrets_saved(self):
        t=template();b=circle_bounds(25,55,1)
        _,body,filters=tile_request(t,b,'next-observed')
        self.assertEqual(body['extensions'],t['body']['extensions'])
        self.assertEqual(body['variables']['staysSearchRequest']['cursor'],'next-observed')
        self.assertEqual(body['variables']['staysSearchRequest']['skipHydrationListingIds'],[])
        self.assertEqual(t['body']['variables']['staysSearchRequest']['cursor'],'observed-page-two')
        self.assertEqual(set(filters),set(b))
        self.assertNotIn('private-cookie',json.dumps(filters))

    def test_budget_capped_subdivision_cursor_and_dedup(self):
        bodies=[response_body([row()],['first','next','third','fourth'])]
        session=FakeSession(bodies)
        result=replay_tiles(template(),SUBJECT,session,bounds=circle_bounds(25,55,2),max_requests=5,pages_per_cell=2)
        self.assertEqual(len(session.calls),5)
        self.assertEqual(len(result['candidates']),1)
        self.assertFalse(result['report']['complete_for_requested_cells'])
        self.assertTrue(result['report']['unresolved_cells'])
        self.assertTrue(any(c['status']=='subdivided' for c in result['report']['cells']))
        self.assertEqual(session.calls[1][1]['json']['variables']['staysSearchRequest']['cursor'],'next')
        self.assertNotIn('private-cookie',json.dumps(result))
        self.assertNotIn('next',json.dumps(result['report']['requests']))

    def test_exhausted_cells_only_claim_requested_cell_pages(self):
        result=replay_tiles(template(),SUBJECT,FakeSession(),bounds=circle_bounds(25,55,1))
        self.assertEqual(result['report']['http_requests'],4)
        self.assertTrue(result['report']['complete_for_requested_cells'])
        self.assertEqual(result['report']['unresolved_cells'],[])

    def test_access_failure_stops_no_fabricated_candidates(self):
        for status in (403,429):
            session=FakeSession(status=status)
            result=replay_tiles(template(),SUBJECT,session,bounds=circle_bounds(25,55,1))
            self.assertEqual(len(session.calls),1)
            self.assertEqual(result['candidates'],[])
            self.assertEqual(result['report']['stop_reason'],f'access_or_rate_limit_{status}')
            self.assertFalse(result['report']['complete_for_requested_cells'])

    def test_error_coverage_never_becomes_inventory(self):
        session=FakeSession(error=RuntimeError('private-cookie request-url'))
        result=replay_tiles(template(),SUBJECT,session,bounds=circle_bounds(25,55,1),max_requests=1)
        self.assertEqual(result['candidates'],[])
        self.assertNotIn('private-cookie',json.dumps(result))
        self.assertFalse(result['report']['complete_for_requested_cells'])

if __name__=='__main__':unittest.main()
