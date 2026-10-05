"""Observe public StaysSearch reads, then replay bounded circle bounding-box tiles.

Every discovered ID is retained before comparison. Request headers, cookie values,
persisted query templates and opaque cursors live only in memory.
"""
from __future__ import annotations

import base64
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import re
import time
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from .collect import AIRBNB_HOSTS, STOP_STATUSES, safe_source, _quiet_scrapling, _challenge_response

MAX_REQUESTS = 40
MAX_CANDIDATES = 2000
MIN_REQUEST_INTERVAL = 3.0
# Conservative validation envelopes, not claims about municipal boundaries.
SEARCH_REGIONS = {
    'Dubai': (24.8, 25.45, 54.8, 55.65, 'Dubai--United-Arab-Emirates', 'AED'),
    'Riyadh': (24.4, 25.1, 46.3, 47.0, 'Riyadh--Saudi-Arabia', 'SAR'),
    'London': (51.28, 51.7, -0.52, 0.34, 'London--United-Kingdom', 'GBP'),
}
FIELDS = ('title', 'latitude', 'longitude', 'distance_km', 'bedrooms', 'beds',
          'bathrooms', 'person_capacity', 'room_type', 'amenities', 'rating',
          'review_count', 'host_id', 'host_name', 'host_listing_count')
PUBLIC_FILTERS = frozenset({'neLat','neLng','swLat','swLng','query','refinementPaths',
    'searchByMap','searchMode','zoomLevel','itemsPerGrid','adults','children','infants',
    'pets','checkin','checkout','checkIn','checkOut','currency','locale','roomTypes',
    'minBedrooms','maxBedrooms','minBathrooms','minBeds','amenities','flexibleTripLengths',
    'monthlyStartDate','monthlyEndDate','monthlyLength','priceFilterInputType',
    'priceFilterNumNights','placeId','screenSize','tabId','version','channel','cdnCacheSafe'})


def search_operation(url: str, method: str, body=None) -> bool:
    """Allow exactly the observed persisted StaysSearch query on Airbnb HTTPS."""
    try:
        parts = urlsplit(url)
        path = parts.path.split('/')
        query = dict(parse_qsl(parts.query))
        if (parts.scheme != 'https' or parts.hostname not in AIRBNB_HOSTS
                or parts.port not in (None,443) or parts.username or parts.password
                or len(path) != 5 or path[1:4] != ['api','v3','StaysSearch']
                or query.get('operationName','StaysSearch') != 'StaysSearch'
                or 'query' in query or method not in {'GET','POST'}):
            return False
        if method == 'POST':
            return (isinstance(body,dict) and body.get('operationName') == 'StaysSearch'
                    and 'query' not in body and isinstance(body.get('variables'),dict)
                    and isinstance(body.get('extensions',{}).get('persistedQuery'),dict))
        return 'variables' in query
    except (ValueError,TypeError):
        return False


def _number(value):
    if isinstance(value,bool): return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError,TypeError): return None


def _city(value):
    text = unquote(str(value or '')).casefold()
    names = [name for name in SEARCH_REGIONS if re.search(r'\b' + name.casefold() + r'\b', text)]
    return names[0] if len(names) == 1 else None


def _within_region(city, lat, lng):
    south, north, west, east, *_ = SEARCH_REGIONS[city]
    return lat is not None and lng is not None and south <= lat <= north and west <= lng <= east


def search_location(subject, context, lat, lng):
    """Resolve only a supported explicit city, with legacy Dubai coordinate fallback."""
    explicit = [value for value in (context.get('city'), subject.get('city')) if value]
    cities = [_city(value) for value in explicit]
    if explicit and (None in cities or len(set(cities)) != 1):
        raise ValueError('search_city_unrecognized_or_conflicting')
    city = cities[0] if cities else 'Dubai' if _within_region('Dubai', lat, lng) else None
    if city is None:
        raise ValueError('explicit_supported_search_city_required')
    if not _within_region(city, lat, lng):
        raise ValueError('search_city_coordinate_mismatch')
    raw_url = context.get('search_url')
    if raw_url:
        parts = urlsplit(raw_url)
        segments = parts.path.strip('/').split('/')
        if (parts.scheme != 'https' or parts.hostname not in AIRBNB_HOSTS
                or parts.port not in (None, 443) or parts.username or parts.password
                or len(segments) != 3 or segments[0] != 's' or segments[2] != 'homes'
                or _city(segments[1]) != city):
            raise ValueError('search_url_city_mismatch')
        base = urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))
    else:
        base = 'https://www.airbnb.com/s/' + SEARCH_REGIONS[city][4] + '/homes'
    return {'city': city, 'url': base, 'currency': context.get('currency') or SEARCH_REGIONS[city][5],
            'url_basis': 'supplied_search_url' if raw_url else 'public_city_path_pending_live_validation'}


def observed_geography(template, location, bounds):
    """An observed template must still describe the requested city and map area."""
    filters = observed_filters(request_variables(template))
    query = filters.get('query')
    if query and (not isinstance(query, list) or any(_city(value) != location['city'] for value in query)):
        raise ValueError('observed_search_city_mismatch')
    values = {}
    for key in ('neLat', 'neLng', 'swLat', 'swLng'):
        field = filters.get(key)
        value = _number(field[0]) if isinstance(field, list) and len(field) == 1 else None
        if value is None:
            raise ValueError('observed_search_bbox_contract_missing')
        values[key] = value
    if (values['swLat'] >= values['neLat'] or values['swLng'] >= values['neLng']
            or not _within_region(location['city'], (values['swLat'] + values['neLat']) / 2,
                                  (values['swLng'] + values['neLng']) / 2)
            or values['swLat'] > bounds['neLat'] or values['neLat'] < bounds['swLat']
            or values['swLng'] > bounds['neLng'] or values['neLng'] < bounds['swLng']):
        raise ValueError('observed_search_geography_mismatch')
    currency = filters.get('currency')
    if currency and currency != [location['currency']]:
        raise ValueError('observed_search_currency_mismatch')


def _search_result(payload):
    if not isinstance(payload, dict) or any(node.get('errors') for node in _walk(payload)):
        raise ValueError('unknown_or_error_schema')
    results = [node for node in _walk(payload) if 'searchResults' in node]
    if len(results) != 1 or not isinstance(results[0]['searchResults'], list):
        raise ValueError('search_results_schema_missing')
    result = results[0]
    if any(not isinstance(row, dict) for row in result['searchResults']):
        raise ValueError('search_results_schema_changed')
    if result['searchResults'] and not any(
            isinstance(node.get('demandStayListing') or node.get('listing'), dict)
            and listing_identifier((node.get('demandStayListing') or node.get('listing')).get('id'))
            for node in _walk(result['searchResults'])):
        raise ValueError('search_results_schema_changed')
    info = result.get('paginationInfo')
    if not isinstance(info, dict) or not any(key in info for key in ('pageCursors', 'nextPageCursor')):
        raise ValueError('pagination_schema_missing')
    if ('pageCursors' in info and (not isinstance(info['pageCursors'], list)
            or any(not isinstance(cursor, str) or not cursor for cursor in info['pageCursors']))) or (
            info.get('nextPageCursor') is not None and not isinstance(info['nextPageCursor'], str)):
        raise ValueError('pagination_schema_changed')
    return result


def _pace(last_request_started):
    if last_request_started is not None:
        remaining = MIN_REQUEST_INTERVAL - (time.monotonic() - last_request_started)
        while remaining > 0:
            time.sleep(remaining)
            remaining = MIN_REQUEST_INTERVAL - (time.monotonic() - last_request_started)
    return time.monotonic()


def listing_identifier(value):
    value = str(value or '')
    if re.fullmatch(r'\d{1,25}',value): return value
    try:
        decoded = base64.b64decode(value,validate=True).decode('ascii')
        match = re.fullmatch(r'(?:DemandStayListing|StayListing|Listing):(\d{1,25})',decoded)
        return match[1] if match else None
    except (ValueError,UnicodeError): return None


def distance_km(lat1,lng1,lat2,lng2):
    values = [_number(x) for x in (lat1,lng1,lat2,lng2)]
    if any(x is None for x in values): return None
    a,b,c,d = map(math.radians,values)
    v = math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return round(6371.0088*2*math.asin(math.sqrt(min(1,max(0,v)))),4)


def _walk(value):
    if isinstance(value,dict):
        yield value
        for child in value.values(): yield from _walk(child)
    elif isinstance(value,list):
        for child in value: yield from _walk(child)


def parse_search(body: dict, subject: dict, source: str) -> dict:
    """Parse observed current schema and legacy listing nodes; no absent inference."""
    candidates,seen,cursors,overrides = [],set(),[],[]
    pagination_seen = False
    for node in _walk(body):
        if isinstance(node.get('paginationInfo'),dict):
            pagination_seen = True
            info = node['paginationInfo']
            for cursor in info.get('pageCursors',[]):
                if isinstance(cursor,str) and cursor not in cursors: cursors.append(cursor)
            if isinstance(info.get('nextPageCursor'),str):
                if info['nextPageCursor'] not in cursors: cursors.append(info['nextPageCursor'])
        listing = node.get('demandStayListing') or node.get('listing')
        if not isinstance(listing,dict): continue
        identifier = listing_identifier(listing.get('id'))
        if not identifier or identifier in seen or identifier == str(subject.get('listing_id')): continue
        seen.add(identifier)
        row = dict.fromkeys(FIELDS)
        row.update(listing_id=identifier,source_url=f'https://www.airbnb.com/rooms/{identifier}',
                   field_sources={'listing_id':source+'#demandStayListing.id'})
        def put(key,value,path):
            if value is not None:
                row[key] = value; row['field_sources'][key] = source+'#'+path
        location = listing.get('location') or {}
        coord = location.get('coordinate') or {}
        put('latitude',_number(coord.get('latitude',listing.get('lat'))),'demandStayListing.location.coordinate.latitude')
        put('longitude',_number(coord.get('longitude',listing.get('lng'))),'demandStayListing.location.coordinate.longitude')
        put('title',node.get('subtitle') or listing.get('name') or node.get('title'),'searchResult.subtitle')
        for key,old in [('bedrooms','bedrooms'),('beds','beds'),('bathrooms','bathrooms'),('person_capacity','personCapacity')]:
            put(key,_number(listing.get(old)),'listing.'+old)
        put('room_type',listing.get('roomTypeCategory') or listing.get('roomType'),'listing.roomTypeCategory')
        put('amenities',listing.get('amenities'),'listing.amenities')
        host = listing.get('primaryHost') or listing.get('host') or {}
        put('host_id',str(host['id']) if host.get('id') else None,'listing.primaryHost.id')
        put('host_name',host.get('name'),'listing.primaryHost.name')
        put('host_listing_count',_number(host.get('listingsCount')),'listing.primaryHost.listingsCount')
        texts = []
        for message in _walk(node.get('structuredContent',{})):
            if isinstance(message.get('body'),str): texts.append(message['body'])
        for text in texts:
            for key,pattern in [('bedrooms',r'(\d+(?:\.\d+)?)\s+bedrooms?\b'),
                ('beds',r'(\d+(?:\.\d+)?)\s+(?:(?:king|queen|double|single|sofa)\s+)?beds?\b'),
                ('bathrooms',r'(\d+(?:\.\d+)?)\s+(?:shared\s+)?bath(?:room)?s?\b'),
                ('person_capacity',r'(\d+)\s+guests?\b')]:
                match = re.search(pattern,text,re.I)
                if match: put(key,_number(match[1]),'structuredContent.body')
        rating = _number(node.get('avgRatingLocalized',listing.get('avgRating')))
        if rating is not None and 0 <= rating <= 5: put('rating',rating,'avgRatingLocalized')
        label = node.get('avgRatingA11yLabel') or ''
        row['search_rating_label'] = label if isinstance(label,str) else None
        row['search_rating_display'] = node.get('avgRatingLocalized')
        if rating is None and isinstance(label,str):
            rated = re.search(r'([0-5](?:[.,]\d{1,3})?)\s+(?:out of 5|average)',label,re.I)
            if rated:
                observed_rating = float(rated[1].replace(',','.'))
                if observed_rating <= 5: put('rating',observed_rating,'avgRatingA11yLabel')
        match = re.search(r'(\d[\d,]*)\s+reviews?\b',label,re.I) if isinstance(label,str) else None
        count = _number(listing.get('reviewsCount'))
        if match: count=int(match[1].replace(',',''))
        put('review_count',count,'avgRatingA11yLabel')
        center_lat=subject.get('latitude');center_lng=subject.get('longitude')
        put('distance_km',distance_km(center_lat,center_lng,row['latitude'],row['longitude']),'computed_haversine_from_public_coordinates')
        override = node.get('listingParamOverrides')
        if isinstance(override,dict):
            row['search_stay_context'] = {k:override.get(k) for k in ('checkin','checkout','adults','children','infants','pets')}
            if row['search_stay_context'] not in overrides: overrides.append(row['search_stay_context'])
        row['missing_fields'] = [key for key in FIELDS if row[key] is None]
        candidates.append(row)
    return {'candidates':candidates,'cursors':cursors,'pagination_seen':pagination_seen,
            'suggested_stay_contexts':overrides}


def circle_bounds(lat,lng,radius):
    delta_lat=radius/111.195
    delta_lng=radius/(111.195*math.cos(math.radians(lat)))
    return {'neLat':lat+delta_lat,'neLng':lng+delta_lng,'swLat':lat-delta_lat,'swLng':lng-delta_lng}


def split_bounds(bounds):
    midlat=(bounds['neLat']+bounds['swLat'])/2
    midlng=(bounds['neLng']+bounds['swLng'])/2
    return [{'swLat':s,'neLat':n,'swLng':w,'neLng':e}
            for s,n in ((bounds['swLat'],midlat),(midlat,bounds['neLat']))
            for w,e in ((bounds['swLng'],midlng),(midlng,bounds['neLng']))]


def request_variables(template):
    if template['method']=='POST': return deepcopy(template['body']['variables'])
    return json.loads(dict(parse_qsl(urlsplit(template['url']).query))['variables'])


def observed_filters(variables):
    result={}
    for node in _walk(variables):
        if node.get('filterName') in PUBLIC_FILTERS:
            result[node['filterName']]=node.get('filterValues')
    return result


def tile_request(template,bounds,cursor=None):
    """Keep the observed query/hash; adjust map coordinates and observed cursor key."""
    variables=request_variables(template)
    adjusted=set();cursor_adjusted=False
    for node in _walk(variables):
        name=node.get('filterName')
        if name in bounds:
            node['filterValues']=[str(bounds[name])];adjusted.add(name)
        if name == 'cursor':
            node['filterValues']=[cursor] if cursor else [];cursor_adjusted=True
        if 'cursor' in node and 'filterName' not in node:
            node['cursor']=cursor;cursor_adjusted=True
        # Hydration and preferred-map IDs refer to the browser's previous bbox.
        # Clearing observed lists prevents them suppressing full listing objects.
        for key in ('skipHydrationListingIds','preferredStayListings'):
            if key in node: node[key]=[]
    if adjusted != set(bounds): raise ValueError('observed_bbox_contract_missing')
    if cursor and not cursor_adjusted: raise ValueError('observed_cursor_contract_missing')
    if template['method']=='POST':
        body=deepcopy(template['body']);body['variables']=variables
        return template['url'],body,observed_filters(variables)
    parts=urlsplit(template['url']);pairs=parse_qsl(parts.query,keep_blank_values=True)
    pairs=[(k,json.dumps(variables,separators=(',',':')) if k=='variables' else v) for k,v in pairs]
    return urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(pairs),'')),None,observed_filters(variables)


def replay_tiles(template,subject,session,*,bounds,max_requests=18,pages_per_cell=3,max_depth=2,max_candidates=MAX_CANDIDATES,last_request_started=None):
    """BFS tile traversal; dense tiles subdivide and unresolved leaves stay explicit."""
    if not search_operation(template.get('url',''),template.get('method',''),template.get('body')):
        raise ValueError('Only observed public StaysSearch reads can be replayed')
    max_requests=min(MAX_REQUESTS,max(1,int(max_requests)))
    max_candidates=min(MAX_CANDIDATES,max(1,int(max_candidates)))
    queue=deque((b,1) for b in split_bounds(bounds))
    candidates={}; cells=[];requests=[];stop=None;suggested=[]
    while queue and len(requests)<max_requests and len(candidates)<max_candidates and stop is None:
        cell_bounds,depth=queue.popleft()
        cell={'bounds':cell_bounds,'depth':depth,'status':'capped','returned_count':0,'pages':0,'cursor_count':0}
        cells.append(cell);cursor=None;seen_cursors=set();remaining=True
        for page_index in range(pages_per_cell):
            if len(requests)>=max_requests: break
            try: url,body,filters=tile_request(template,cell_bounds,cursor)
            except (ValueError, TypeError, KeyError) as exc:
                stop='observed_request_contract_changed';cell['status']='error';cell['error']=type(exc).__name__;break
            evidence={'method':template['method'],'source_url':safe_source(url),'filters':filters,
                      'cell_index':len(cells)-1,'page':page_index+1,'cursor_used':cursor is not None,'status':None}
            requests.append(evidence)
            try:
                last_request_started=_pace(last_request_started)
                kwargs={'headers':template.get('headers',{}),'timeout':20,'retries':1,'follow_redirects':False}
                response=session.post(url,json=body,**kwargs) if body is not None else session.get(url,**kwargs)
                evidence['status']=response.status
                if response.status in STOP_STATUSES:
                    stop=f'access_or_rate_limit_{response.status}';cell['status']='error';break
                if response.status!=200:
                    stop='non_success_response';cell['status']='error';cell['error']=stop;break
                if _challenge_response(response):
                    stop='challenge_response';cell['status']='error';cell['error']=stop;break
                payload=json.loads(response.body)
                try: result_node=_search_result(payload)
                except ValueError as exc:
                    stop=str(exc);cell['status']='error';cell['error']=stop;break
                parsed=parse_search(result_node,subject,safe_source(url))
            except Exception as exc:
                stop='source_or_parser_error';cell['status']='error';cell['error']=type(exc).__name__;break
            cell['pages']+=1;cell['returned_count']+=len(parsed['candidates'])
            for row in parsed['candidates']:
                if row['listing_id'] not in candidates:
                    candidates[row['listing_id']]=row
            for ctx in parsed['suggested_stay_contexts']:
                if ctx not in suggested: suggested.append(ctx)
            cursors=parsed['cursors'];cell['cursor_count']=max(cell['cursor_count'],len(cursors))
            # pageCursors includes the current/first page; use actual next value.
            info=result_node['paginationInfo']
            next_cursor=info.get('nextPageCursor') or (cursors[page_index+1] if page_index+1<len(cursors) else None)
            remaining=next_cursor is not None
            if not remaining:
                cell['status']='exhausted' if parsed['pagination_seen'] else 'error'
                if not parsed['pagination_seen']: stop='pagination_schema_missing';cell['error']=stop
                break
            if next_cursor in seen_cursors:
                stop='cursor_cycle';cell['status']='error';cell['error']=stop;break
            seen_cursors.add(next_cursor);cursor=next_cursor
        if cell['status']=='capped' and remaining and depth<max_depth and stop is None:
            cell['status']='subdivided'
            queue.extend((b,depth+1) for b in split_bounds(cell_bounds))
    for b,d in queue: cells.append({'bounds':b,'depth':d,'status':'unvisited','returned_count':0,'pages':0,'cursor_count':0})
    unresolved=[i for i,c in enumerate(cells) if c['status'] not in {'exhausted','subdivided'}]
    if stop is None and len(requests)>=max_requests: stop='request_budget_reached'
    if stop is None and len(candidates)>=max_candidates: stop='candidate_cap_reached'
    return {'candidates':list(candidates.values()),'report':{'cells':cells,'requests':requests,
        'http_requests':len(requests),'unresolved_cells':unresolved,'stop_reason':stop,
        'complete_for_requested_cells':not unresolved and not queue and stop is None,
        'minimum_request_interval_seconds':MIN_REQUEST_INTERVAL,
        'suggested_stay_contexts':suggested,'request_budget':max_requests,'candidate_cap':max_candidates}}


def discover(subject: dict,context: dict,target: int=100) -> dict:
    lat=_number(context.get('center_lat',subject.get('latitude')))
    lng=_number(context.get('center_lng',subject.get('longitude')))
    radius=_number(context.get('radius_km',2))
    if lat is None or lng is None or not -80<=lat<=80 or not -180<=lng<=180 or radius is None or not 0.1<=radius<=10:
        raise ValueError('Circle center and radius0.1..10km are required')
    location=search_location(subject,context,lat,lng)
    bounds=circle_bounds(lat,lng,radius)
    search_budget=min(MAX_REQUESTS,max(1,int(context.get('max_requests',context.get('budget',18)))))
    report={'transport':'scrapling_observed_stays_search','observed_at':datetime.now(timezone.utc).isoformat(),
        'target':target,'circle':{'center_lat':lat,'center_lng':lng,'radius_km':radius},'initial_bounds':bounds,
        'search_location':location,'browser_navigations':0,'browser_search_requests':0,'browser_status':None,'warnings':[],
        'complete_for_requested_cells':False,'stop_reason':None,'cells':[],'unresolved_cells':[],
        'requested_dates':None,'upstream_similarity_filters':False,'candidates_filtered_for_similarity':False,
        'search_request_budget':search_budget,'minimum_request_interval_seconds':MIN_REQUEST_INTERVAL}
    templates=[];payloads=[];observed_methods=[];last_request_started=None
    query={'ne_lat':bounds['neLat'],'ne_lng':bounds['neLng'],'sw_lat':bounds['swLat'],'sw_lng':bounds['swLng'],
           'search_by_map':'true','zoom_level':14,'currency':location['currency'],'locale':context.get('locale','en')}
    url=location['url']+'?'+urlencode(query)
    try:
        from scrapling.fetchers import DynamicSession,FetcherSession
    except ImportError:
        report['stop_reason']='scrapling_dependency_missing';return {'candidates':[],'report':report}

    def stop(reason, error=None):
        if report['stop_reason'] is None:
            report['stop_reason']=reason
            if error:report['error']=type(error).__name__

    def accept_payload(body,source):
        try:
            node=_search_result(body)
            parsed=parse_search(node,subject,source)
        except ValueError as exc:
            # Contract error messages originate from our bounded validators.
            reason=str(exc) if str(exc) in {'unknown_or_error_schema','search_results_schema_missing',
                'search_results_schema_changed','pagination_schema_missing','pagination_schema_changed'} else 'search_parser_error'
            stop(reason,exc);return
        except Exception as exc:
            stop('search_parser_error',exc);return
        payloads.append(parsed)

    def setup(page):
        def request_seen(request):
            nonlocal last_request_started
            if '/api/v3/StaysSearch/' not in request.url:return
            last_request_started=time.monotonic()
            report['browser_search_requests']+=1
            if request.method not in observed_methods:observed_methods.append(request.method)
            if report['stop_reason'] is not None:return
            try:
                body=request.post_data_json if request.method=='POST' else None
                if not search_operation(request.url,request.method,body):
                    stop('observed_request_contract_changed');return
                template={'url':request.url,'method':request.method,'body':body}
                observed_geography(template,location,bounds)
                headers={k:v for k,v in request.headers.items() if k.lower() not in {'host','content-length','accept-encoding'}}
                if len(templates)<8:templates.append({**template,'headers':headers})
            except ValueError as exc:
                stop(str(exc) if str(exc).startswith('observed_search_') else 'observed_request_contract_changed',exc)
            except Exception as exc:stop('observed_request_contract_changed',exc)

        def response_seen(response):
            search='/api/v3/StaysSearch/' in response.url
            document=urlsplit(response.url).path.startswith('/s/')
            if not search and not document:return
            if report['stop_reason'] is not None:return
            if response.status in STOP_STATUSES:
                stop(f'access_or_rate_limit_{response.status}');return
            if response.status!=200:
                stop('non_success_response');return
            try:
                if _challenge_response(response):stop('challenge_response');return
                if search:accept_payload(response.json(),safe_source(response.url))
            except Exception as exc:stop('source_or_parser_error',exc)

        def request_failed(request):
            if '/api/v3/StaysSearch/' in request.url or urlsplit(request.url).path.startswith('/s/'):
                stop('browser_request_failed')
        page.on('request',request_seen);page.on('response',response_seen);page.on('requestfailed',request_failed)

    def action(page):
        nonlocal last_request_started
        if report['stop_reason'] is not None:return
        page.wait_for_timeout(7000)
        if report['stop_reason'] is not None:return
        # Browser controls are read-only, and never run after a recorded failure.
        try:
            if report['browser_search_requests']>=search_budget:return
            control=page.locator('a[aria-label="Next"]')
            if control.count():
                last_request_started=_pace(last_request_started)
                if report['stop_reason'] is not None:return
                control.first.click(timeout=4000);page.wait_for_timeout(3000)
            if report['stop_reason'] is not None:return
            if not templates and report['browser_search_requests']<search_budget:
                control=page.locator('[aria-label="Zoom in"]')
                if control.count():
                    last_request_started=_pace(last_request_started)
                    if report['stop_reason'] is not None:return
                    control.first.click(timeout=5000);page.wait_for_timeout(3500)
        except Exception as exc:stop('browser_action_error',exc)

    candidates={}
    with _quiet_scrapling():
        try:
            opts={};chrome=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            if chrome.exists():opts['executable_path']=str(chrome)
            with DynamicSession(headless=True,capture_xhr=r'https://(?:www\.)?airbnb\.(?:com|co\.in)/api/v3/',
                    retries=1,timeout=45000,google_search=False,**opts) as browser:
                report['browser_navigations']=1
                response=browser.fetch(url,page_setup=setup,page_action=action,network_idle=False,wait=500)
                report['browser_status']=response.status
                if response.status in STOP_STATUSES:stop(f'access_or_rate_limit_{response.status}')
                elif response.status!=200:stop('non_success_response')
                elif _challenge_response(response):stop('challenge_response')
                if report['stop_reason'] is None:
                    # A redirect to another city cannot license replay of its template.
                    search_location(subject,{**context,'city':location['city'],'search_url':response.url},lat,lng)
                    if not payloads:
                        for script in response.css('script[type="application/json"]'):
                            try:node=json.loads(script.text)
                            except (ValueError,TypeError):continue
                            if isinstance(node,dict) and 'niobeClientData' in node:
                                accept_payload(node,safe_source(response.url)+'#bootstrap')
                                if report['stop_reason'] is not None:break
        except Exception as exc:stop('browser_error',exc)
        for parsed in payloads:
            for row in parsed['candidates']:candidates.setdefault(row['listing_id'],row)
        if report['stop_reason'] is None and templates and report['browser_search_requests'] < search_budget:
            template=next((t for t in reversed(templates) if any('cursor' in n or n.get('filterName')=='cursor'
                        for n in _walk(request_variables(t)))),templates[-1])
            report['observed_method']=template['method']
            report['observed_filters']=observed_filters(request_variables(template))
            try:
                with FetcherSession(retries=1,timeout=20,stealthy_headers=False,impersonate=None,follow_redirects=False) as session:
                    result=replay_tiles(template,subject,session,bounds=bounds,
                        max_requests=search_budget-report['browser_search_requests'],
                        pages_per_cell=min(5,max(1,int(context.get('pages_per_cell',3)))),
                        max_depth=min(3,max(1,int(context.get('max_depth',2)))),
                        max_candidates=context.get('max_candidates',MAX_CANDIDATES),
                        last_request_started=last_request_started)
                report.update(result['report'])
                for row in result['candidates']:candidates.setdefault(row['listing_id'],row)
            except Exception as exc:stop('direct_session_error',exc)
        elif report['stop_reason'] is None:
            stop('request_budget_reached' if templates else 'no_observed_stays_search_template')
    report['observed_methods']=observed_methods
    report['total_search_requests']=report['browser_search_requests']+report.get('http_requests',0)
    report['unique_candidates']=len(candidates)
    for row in candidates.values():
        row['circle_distance_km'] = distance_km(lat,lng,row['latitude'],row['longitude'])
        row['inside_circle'] = None if row['circle_distance_km'] is None else row['circle_distance_km']<=radius
        row['field_sources']['circle_distance_km'] = 'computed_haversine_from_circle_center_and_public_coordinates'
    report['inside_circle_candidates']=sum(r['inside_circle'] is True for r in candidates.values())
    report['outside_circle_candidates']=sum(r['inside_circle'] is False for r in candidates.values())
    report['unknown_location_candidates']=sum(r['inside_circle'] is None for r in candidates.values())
    report['warnings'].append('Search results are ranked public observations; exhausted pages do not prove all Airbnb inventory. Suggested stay dates can affect results.')
    if not report['complete_for_requested_cells']:report['warnings'].append('Requested cell traversal is incomplete; inspect unresolved_cells and budgets.')
    return {'candidates':list(candidates.values()),'report':report}
