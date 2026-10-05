"""Anonymous public host-portfolio observations; no biography/contact persistence."""
from __future__ import annotations
import base64
from contextlib import nullcontext
from datetime import datetime,timezone
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from .collect import AIRBNB_HOSTS,STOP_STATUSES,_quiet_scrapling,safe_source
from .discovery import _walk


def validate_profile_url(url):
    parts=urlsplit(url)
    match=re.fullmatch(r'/users/profile/(\d{1,25})/?',parts.path)
    if (parts.scheme!='https' or parts.hostname not in AIRBNB_HOSTS or parts.port not in (None,443)
            or parts.username or parts.password or not match):
        raise ValueError('An exact public Airbnb /users/profile/numeric-ID HTTPS URL is required')
    return match[1]


def _typed_id(value,namespace):
    try:
        decoded=base64.b64decode(str(value),validate=True).decode('ascii')
        match=re.fullmatch(re.escape(namespace)+r':(\d{1,25})',decoded)
        return match[1] if match else None
    except (ValueError,UnicodeError):return None


def parse_portfolio(payload,profile_id):
    """Only the requested contextual user's supplied-listing connection qualifies."""
    ids=[];counts=[];names=[];page_info=[]
    for node in _walk(payload):
        if node.get('__typename')!='ContextualUser' or _typed_id(node.get('id'),'ContextualUser')!=profile_id:continue
        for key in ('displayName','firstName','name'):
            if isinstance(node.get(key),str) and node[key].strip():names.append(node[key].strip())
        # Connection data on this exact identity, not unrelated review counts.
        listings=node.get('staySupplyListings')
        if not isinstance(listings,dict):continue
        info=listings.get('pageInfo') or {}
        count=info.get('totalCount')
        if type(count) is int and count>=0:counts.append(count)
        page_info.append({k:info[k] for k in ('hasNextPage','hasPreviousPage','totalCount') if k in info})
        for item in _walk(listings.get('edges',[])):
            if item.get('__typename')=='StaySupplyListing':
                identifier=_typed_id(item.get('id'),'StaySupplyListing')
                if identifier and identifier not in ids:ids.append(identifier)
    return {'listing_ids':ids,'declared_listing_count':max(counts) if counts else None,
            'host_name':names[0] if names else None,'page_info':page_info}


def subject_profile_identity(subject_payload,profile_id):
    """A single public host passport explicitly links both identifier namespaces."""
    for node in _walk(subject_payload):
        passport=node.get('passportData')
        if not isinstance(passport,dict):continue
        contextual_id=_typed_id(passport.get('contextualUserId'),'ContextualUser')
        legacy_id=_typed_id(passport.get('userId'),'DemandUser')
        if contextual_id==profile_id and legacy_id:
            return {'profile_id':contextual_id,'host_id':legacy_id,'host_name':passport.get('name'),
                    'source_fields':['hostInfo.passportData.userId','hostInfo.passportData.contextualUserId']}
    return None


def inspect_profile(profile_url,*,subject_host_id=None,subject_payload=None,max_replays=3):
    """One browser capture including the visible public listings control.

    This observer does not synthesize pagination variables or replay unknown
    profile operations. A partial sample remains partial.
    """
    profile_id=validate_profile_url(profile_url)
    result={'profile_url':safe_source(profile_url),'profile_id':profile_id,'host_name':None,
            'host_id':None,'listing_ids':[],'declared_listing_count':None,'coverage':'unknown',
            'report':{'observed_at':datetime.now(timezone.utc).isoformat(),'browser_navigations':0,
                'browser_status':None,'observed_operations':[],'direct_replays':0,
                'max_replays':min(3,max(0,int(max_replays))),'stop_reason':None,
                'identity_namespace':'ContextualUser','subject_legacy_host_id':subject_host_id,
                'legacy_host_id_mapping':'unresolved','corporate_inventory_proven':False,
                'complete_public_profile_listing_sample':False,'warnings':[]}}
    records=[];blocked=[];labels=[];links=[]
    try:
        from scrapling.fetchers import DynamicSession
    except ImportError:
        result['report']['stop_reason']='scrapling_dependency_missing';return result
    def setup(page):
        def response_seen(response):
            parts=urlsplit(response.url);segments=parts.path.split('/')
            if parts.hostname not in AIRBNB_HOSTS or len(segments)<4 or segments[1:3]!=['api','v3']:return
            operation=segments[3]
            if operation not in result['report']['observed_operations']:result['report']['observed_operations'].append(operation)
            if not re.search(r'PublicProfile|ProfileListings|UserProfile',operation):return
            if response.status in STOP_STATUSES:blocked.append(response.status)
            elif response.status==200:
                try:records.append(response.json())
                except Exception:pass
        page.on('response',response_seen)
    def action(page):
        page.wait_for_timeout(8000)
        for control in page.locator('button').all():
            label=(control.get_attribute('aria-label') or control.inner_text()).strip()
            if re.fullmatch(r'View all \d+ listings',label):
                labels.append(label)
                if not blocked:
                    try:control.click(timeout=3000);page.wait_for_timeout(2500)
                    except Exception:pass
                break
        for control in page.locator('button').all():
            label=(control.get_attribute('aria-label') or control.inner_text()).strip()
            match=re.fullmatch(r'Learn more about (.+?)[\u2019\']s identity verification status',label)
            if match:result['host_name']=match[1]
        for link in page.locator('a[href*="/rooms/"]').all():
            match=re.match(r'/rooms/(\d{1,25})(?:\?|$)',link.get_attribute('href') or '')
            if match and match[1] not in links:links.append(match[1])
    with _quiet_scrapling():
        try:
            options={};chrome=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
            if chrome.exists():options['executable_path']=str(chrome)
            with DynamicSession(headless=True,retries=1,timeout=45000,google_search=False,**options) as browser:
                result['report']['browser_navigations']=1
                response=browser.fetch(profile_url,page_setup=setup,page_action=action,network_idle=False,wait=500)
                result['report']['browser_status']=response.status
                if response.status in STOP_STATUSES:blocked.append(response.status)
                if response.status==200:
                    for script in response.css('script[type="application/json"]'):
                        try:node=json.loads(script.text)
                        except (ValueError,TypeError):continue
                        if isinstance(node,dict) and 'niobeClientData' in node:records.append(node)
        except Exception as exc:
            result['report']['stop_reason']='browser_error';result['report']['error']=type(exc).__name__
    for record in records:
        parsed=parse_portfolio(record,profile_id)
        for identifier in parsed['listing_ids']:
            if identifier not in result['listing_ids']:result['listing_ids'].append(identifier)
        if parsed['declared_listing_count'] is not None:
            result['declared_listing_count']=max(result['declared_listing_count'] or 0,parsed['declared_listing_count'])
        if parsed['host_name']:result['host_name']=parsed['host_name']
    # Listing URLs on the exact public profile are independent public evidence.
    for identifier in links:
        if identifier not in result['listing_ids']:result['listing_ids'].append(identifier)
    for label in labels:
        declared=int(re.search(r'\d+',label)[0])
        if result['declared_listing_count'] is None:result['declared_listing_count']=declared
    count=result['declared_listing_count'];found=len(result['listing_ids'])
    mapping=subject_profile_identity(subject_payload,profile_id) if subject_payload is not None else None
    if mapping:
        result['host_id']=mapping['host_id']
        result['report']['legacy_host_id_mapping']='verified_same_public_host_passport'
        result['report']['identity_mapping_evidence']=mapping
    result['coverage']='complete_declared_profile_sample' if count is not None and found>=count else 'partial_profile_sample' if found else 'no_public_listings_observed'
    result['report']['complete_public_profile_listing_sample']=count is not None and found>=count
    result['report']['observed_listing_count']=found
    if blocked:result['report']['stop_reason']=f'access_or_rate_limit_{blocked[0]}'
    result['report']['warnings'].append('This is the supplied public profile portfolio, not proof of complete corporate ownership. A legacy host ID mapping requires the explicit public listing host passport.')
    return result

CATALOG_URL='https://api.bnbmehomes.com/api/v1/property/search-property-v2'
_CONTACT_KEYS=re.compile(r'email|phone|whatsapp|contact|password|secret|token|authorization|cookie|created_by|modified_by',re.I)

def redact_catalog(value):
    """Keep full public rental attributes; omit contact/session material."""
    if isinstance(value,dict):
        return {k:redact_catalog(v) for k,v in value.items() if not _CONTACT_KEYS.search(k)}
    if isinstance(value,list):return [redact_catalog(v) for v in value]
    if isinstance(value,str):
        if value.startswith(('https://','http://')) and re.search(r'(?:Signature|AWSAccessKeyId|X-Amz|token|secret|authorization)=',value,re.I):
            value=safe_source(value)
        value=re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b','[contact redacted]',value)
        value=re.sub(r'\+(?:971|966|44|91)[\d\s().-]{7,18}','[contact redacted]',value)
    return value


def collect_catalog():
    """One anonymous public search read, preserving every returned property."""
    from scrapling.fetchers import FetcherSession
    result={'properties':[],'observed_at':datetime.now(timezone.utc).isoformat(),'source_url':CATALOG_URL,
        'report':{'method':'GET','status':None,'requests':1,'pagination_contract_observed':False,
            'active_inventory_complete':False,'stop_reason':None,
            'warnings':['Returned public search rows are not proof of complete active inventory. No pagination contract or active status was observed in the search response.']}}
    with _quiet_scrapling():
        try:
            with FetcherSession(timeout=20,retries=1,follow_redirects=False) as session:
                response=session.get(CATALOG_URL)
            result['report']['status']=response.status
            if response.status in STOP_STATUSES:
                result['report']['stop_reason']=f'access_or_rate_limit_{response.status}';return result
            if response.status!=200:
                result['report']['stop_reason']='non_success_response';return result
            body=json.loads(response.body)
            result['report']['root_keys']=list(body) if isinstance(body,dict) else []
            if not isinstance(body,dict) or not isinstance(body.get('data'),list):
                result['report']['stop_reason']='unknown_catalog_schema';return result
            result['properties']=redact_catalog(body['data'])
            result['report']['returned_count']=len(result['properties'])
            result['report']['city_counts']={}
            result['report']['active_status_counts']={}
            for row in result['properties']:
                city=(row.get('location') or {}).get('city') or 'unknown'
                result['report']['city_counts'][city]=result['report']['city_counts'].get(city,0)+1
                status=str(row.get('status','unknown'))
                result['report']['active_status_counts'][status]=result['report']['active_status_counts'].get(status,0)+1
            result['report']['airbnb_external_listing_urls']=sorted(set(re.findall(r'https://(?:www\.)?airbnb\.(?:com|co\.in)/rooms/\d+',json.dumps(result['properties']))))
        except Exception as exc:
            result['report']['stop_reason']='catalog_request_error';result['report']['error']=type(exc).__name__
    return result

def collect_property_details(property_record,context,*,session=None):
    """One public dated website GET, retaining exact server attributes and query.

    Missing prices remain null. Field names alone do not establish per-night or
    total price semantics, even when the request contains a complete stay.
    """
    from urllib.parse import urlencode
    from scrapling.fetchers import FetcherSession
    slug=property_record.get('slug','')
    if not isinstance(slug,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,249}',slug):
        raise ValueError('A public catalog slug is required')
    checkin=context.get('checkin',context.get('startDate'))
    checkout=context.get('checkout',context.get('endDate'))
    from datetime import date
    nights=(date.fromisoformat(checkout)-date.fromisoformat(checkin)).days
    adults=context.get('adults',2)
    if not 1<=nights<=365 or type(adults) is not int or not 1<=adults<=16:raise ValueError('Invalid dated guest context')
    params={'startDate':checkin,'endDate':checkout,'adults':adults}
    source='https://bnbmehomes.com/property/'+slug
    result={'property':None,'observed_at':datetime.now(timezone.utc).isoformat(),'source_url':source,
        'request_context':{'checkin':checkin,'checkout':checkout,'adults':adults,'requested_currency':context.get('currency')},
        'observed_query':None,'price_fields':None,'report':{'method':'GET','status':None,'requests':1,'stop_reason':None}}
    with _quiet_scrapling():
        try:
            with (nullcontext(session) if session is not None else FetcherSession(timeout=20,retries=1,follow_redirects=False)) as transport:
                response=transport.get(source+'?'+urlencode(params))
            result['report']['status']=response.status
            if response.status in STOP_STATUSES:
                result['report']['stop_reason']=f'access_or_rate_limit_{response.status}';return result
            if response.status!=200:
                result['report']['stop_reason']='non_success_response';return result
            for script in response.css('script#__NEXT_DATA__'):
                body=json.loads(script.text)
                props=body.get('props',{}).get('pageProps',{})
                if isinstance(props.get('singleHotelDetails'),dict):
                    result['property']=redact_catalog(props['singleHotelDetails'])
                    query=props.get('query') or {}
                    result['observed_query']={k:query.get(k) for k in ('startDate','endDate','adults','kids','infants','pets') if k in query}
                    p=result['property']
                    result['price_fields']={'currency':p.get('currency'),'non_refundable_price':p.get('non_refundable_price'),
                        'refundable_price':p.get('refundable_price'),'value_semantics':'unverified_website_price_fields',
                        'dated_context_matches':query.get('startDate')==checkin and query.get('endDate')==checkout and str(query.get('adults'))==str(adults)}
                    result['report']['active_status']=p.get('status')
                    result['report']['price_values_observed']=any(p.get(k) is not None for k in ('non_refundable_price','refundable_price'))
                    break
            if result['property'] is None:result['report']['stop_reason']='property_detail_schema_missing'
        except Exception as exc:
            result['report']['stop_reason']='property_detail_error';result['report']['error']=type(exc).__name__
    return result

def collect_catalog_details(catalog,context,output_path,*,pause_seconds=1.0,max_requests=None,session=None):
    """One worker, one public page per property, atomic checkpoints and resume."""
    if session is None:
        from scrapling.fetchers import FetcherSession
        with _quiet_scrapling(),FetcherSession(timeout=20,retries=1,follow_redirects=False) as reusable_session:
            return collect_catalog_details(catalog,context,output_path,pause_seconds=pause_seconds,
                                           max_requests=max_requests,session=reusable_session)
    import time
    output_path=Path(output_path)
    properties=catalog.get('properties',[])
    context=dict(context)
    state={'observations':[],'requested_context':context,'report':{'started_at':datetime.now(timezone.utc).isoformat(),
        'source_url':catalog.get('source_url'),'catalog_count':len(properties),'requests_this_run':0,
        'worker_count':1,'minimum_start_interval_seconds':max(1.0,float(pause_seconds)),
        'stop_reason':None,'complete_for_catalog_rows':False,'warnings':[]}}
    if output_path.exists():
        previous=json.loads(output_path.read_text(encoding='utf-8'))
        if previous.get('requested_context')==context:
            state['observations']=previous.get('observations',[])
            if str(previous.get('report',{}).get('stop_reason','')).startswith('access_or_rate_limit_'):
                return previous
    def fresh(observation):
        try:
            stamp=datetime.fromisoformat(observation['observed_at'])
            if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
            return -60 <= (datetime.now(timezone.utc)-stamp).total_seconds() <= 6*3600
        except (KeyError,ValueError,TypeError):return False
    state['report']['cache_max_age_seconds']=6*3600
    completed={str(o['property_id']) for o in state['observations'] if o.get('attributes') is not None and o.get('price_attempts_complete') and fresh(o)}
    by_id={str(o['property_id']):o for o in state['observations']}
    budget=len(properties)*3 if max_requests is None else min(len(properties)*3,max(0,int(max_requests)))
    last_start=None
    pause_flag=output_path.parent/'pause-inventory.flag'
    def pace():
        nonlocal last_start
        if last_start is not None:
            remaining=state['report']['minimum_start_interval_seconds']-(time.monotonic()-last_start)
            if remaining>0:time.sleep(remaining)
        last_start=time.monotonic()
    def checkpoint():
        state['observations']=list(by_id.values())
        state['report']['observed_count']=len(state['observations'])
        state['report']['attributes_count']=sum(x.get('attributes') is not None for x in state['observations'])
        state['report']['unresolved_property_ids']=[str(p['id']) for p in properties if str(p['id']) not in completed]
        state['report']['complete_for_catalog_rows']=not state['report']['unresolved_property_ids']
        state['report']['updated_at']=datetime.now(timezone.utc).isoformat()
        output_path.parent.mkdir(parents=True,exist_ok=True)
        _atomic_checkpoint(output_path,state)
    def paused():
        if pause_flag.exists():
            state['report']['stop_reason']='manual_pause'
            checkpoint()
            return True
        return False
    checkpoint()
    for property_record in properties:
        if paused():return state
        property_id=str(property_record['id'])
        if property_id in completed:continue
        if state['report']['requests_this_run']>=budget:
            state['report']['stop_reason']='request_budget_reached';break
        pace()
        if paused():return state
        property_context=dict(context,currency=property_record.get('currency') or context.get('currency'))
        result=collect_property_details(property_record,property_context,session=session)
        state['report']['requests_this_run']+=1
        quotes=[]
        if result['report'].get('price_values_observed'):
            quotes.append({'kind':'unclassified_public_website_price_fields','context':result['request_context'],
                'observed_query':result['observed_query'],'values':result['price_fields'],
                'source_url':result['source_url'],'observed_at':result['observed_at']})
        observation={'property_id':property_id,'source_url':result['source_url'],'observed_at':result['observed_at'],
            'context':property_context,'attributes':result['property'],'quotes':quotes,'report':result['report'],
            'observed_query':result['observed_query'],'price_fields':result['price_fields']}
        by_id[property_id]=observation
        access_stop=str(result['report'].get('stop_reason','')).startswith('access_or_rate_limit_')
        if result['property'] is not None and not access_stop:
            observed_property=result['property']
            quote=None;inventory=None
            if state['report']['requests_this_run']<budget:
                pace()
                if paused():return state
                quote=collect_website_quote(observed_property,property_context,session=session)
                state['report']['requests_this_run']+=1
                if quote.get('body') is not None:
                    observation['quotes'].append({'kind':'website_dated_stay_quote',**quote})
                observation['quote_report']=quote['report']
                observation['quote_observation']=quote
                access_stop=str(quote['report'].get('stop_reason','')).startswith('access_or_rate_limit_')
            if not access_stop and state['report']['requests_this_run']<budget:
                pace()
                if paused():return state
                inventory=collect_website_inventory(observed_property,property_context,session=session)
                state['report']['requests_this_run']+=1
                observation['inventory']=inventory
                access_stop=str(inventory['report'].get('stop_reason','')).startswith('access_or_rate_limit_')
            observation['price_attempts_complete']=quote is not None and inventory is not None and not access_stop
            if observation['price_attempts_complete']:completed.add(property_id)
            if access_stop:
                state['report']['stop_reason']=(inventory or quote)['report']['stop_reason']
        checkpoint()
        if access_stop:
            state['report']['stop_reason']=state['report']['stop_reason'] or result['report']['stop_reason'];break
        if state['report']['requests_this_run']%10==0:
            print(f"Public property details: {len(completed)}/{len(properties)} checkpointed",flush=True)
    if state['report']['stop_reason'] is None and len(completed)<len(properties):
        state['report']['stop_reason']='property_detail_coverage_gaps'
    checkpoint()
    return state

QUOTE_URL='https://api.bnbmehomes.com/api/v1/payments/get-charges-breakup'
INVENTORY_URL='https://api.bnbmehomes.com/api/v1/inventory/get-inventory'

def _public_price_read(source,params,*,session=None):
    from urllib.parse import urlencode
    from scrapling.fetchers import FetcherSession
    result={'source_url':source,'observed_at':datetime.now(timezone.utc).isoformat(),
        'request_context':dict(params),'body':None,'report':{'method':'GET','status':None,'stop_reason':None}}
    with _quiet_scrapling():
        try:
            with (nullcontext(session) if session is not None else FetcherSession(timeout=20,retries=1,follow_redirects=False)) as transport:
                response=transport.get(source+'?'+urlencode(params))
            result['report']['status']=response.status
            try:
                body=json.loads(response.body)
                result['body']=redact_catalog(body)
                result['report']['response_root_keys']=list(body) if isinstance(body,dict) else None
            except (ValueError,TypeError):
                result['raw_text']=redact_catalog(response.body.decode('utf-8',errors='replace'))
                body=None
            if response.status in STOP_STATUSES:result['report']['stop_reason']=f'access_or_rate_limit_{response.status}'
            elif response.status!=200:result['report']['stop_reason']='non_success_response'
            else:
                if isinstance(body,dict) and body.get('message')=='SOLD_OUT':
                    result['report']['stay_quote_availability']='SOLD_OUT'
                elif not isinstance(body,dict) or not isinstance(body.get('data'),dict):
                    result['report']['stop_reason']='unknown_price_schema'
        except Exception as exc:
            result['report']['stop_reason']='price_read_error';result['report']['error']=type(exc).__name__
    return result


def _property_uuid(property_record):
    identifier=property_record.get('property_details_uuid','')
    if not re.fullmatch(r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}',identifier):
        raise ValueError('Observed public catalog property UUID is required')
    return identifier


def collect_website_quote(property_record,context,*,session=None):
    """Replay the actually observed anonymous GET fee-breakup read."""
    params={'from_date':context['checkin'],'to_date':context['checkout'],
        'property_details_uuid':_property_uuid(property_record),'voucher_code':'undefined',
        'no_of_pats':str(context.get('pets',0)),'is_refundable':'false'}
    result=_public_price_read(QUOTE_URL,params,session=session)
    result['context']={'checkin':context['checkin'],'checkout':context['checkout'],'adults':context.get('adults',2),
        'pets':context.get('pets',0),'currency':property_record.get('currency')}
    result['report'].update(price_endpoint_guest_parameter=False,currency_basis='public_property_detail.currency',
        bookability_verified=False,refund_policy_parameter='false',pets_parameter_name='no_of_pats')
    body=result.get('body')
    data=(body.get('data') or {}) if isinstance(body,dict) else {}
    if not isinstance(data,dict):data={}
    result['report']['quote_values_observed']=isinstance(data.get('after_discount'),dict) and data['after_discount'].get('total') is not None
    return result


def collect_website_inventory(property_record,context,*,session=None):
    """Replay the observed public dated inventory read; preserve each daily row."""
    from datetime import date
    from datetime import timedelta
    month_start=date.today().replace(day=1)
    start=context.get('calendar_start_date',month_start.isoformat())
    end=context.get('calendar_end_date',(date.fromisoformat(start)+timedelta(days=364)).isoformat())
    requested_end=end
    difference=(date.fromisoformat(end)-date.fromisoformat(start)).days
    if difference < 0:
        raise ValueError('Inventory interval must contain1..365inclusive days')
    if difference >= 365:end=(date.fromisoformat(start)+timedelta(days=364)).isoformat()
    params={'property_details_uuid':_property_uuid(property_record),'from_date':start,'to_date':end}
    result=_public_price_read(INVENTORY_URL,params,session=session)
    result['context']={'start_date':start,'end_date_inclusive':end,'currency':property_record.get('currency')}
    result['report']['calendar_window_clipped_to_365_days']=end!=requested_end
    if end!=requested_end:result['report']['requested_end_date_inclusive']=requested_end
    body=result.get('body')
    data=(body.get('data') or {}) if isinstance(body,dict) else {}
    result['report']['observed_date_count']=sum(bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}',key)) for key in data) if isinstance(data,dict) else 0
    if isinstance(data,dict):
        result['report']['placeholder_date_count']=sum(isinstance(rows,list) and all(
            isinstance(row,dict) and row.get('inventory_uuid') is None and row.get('property_id') is None
            for row in rows) for rows in data.values())
    result['report']['available_room_meaning']='public website inventory count; no booked-status inference'
    return result

def backfill_quote_observations(output_path,*,max_requests=50,pause_seconds=1.0):
    """Repair earlier missing quote evidence without rereading details/calendar."""
    import time
    from scrapling.fetchers import FetcherSession
    output_path=Path(output_path)
    state=json.loads(output_path.read_text(encoding='utf-8'))
    requests=0;last_start=None
    previous_backfill_requests=state['report'].get('quote_evidence_backfill_requests',0)
    with _quiet_scrapling(),FetcherSession(timeout=20,retries=1,follow_redirects=False) as session:
        for observation in state.get('observations',[]):
            if observation.get('quote_observation') is not None or observation.get('attributes') is None:continue
            if requests>=min(50,max(0,int(max_requests))):break
            if (output_path.parent/'pause-inventory.flag').exists():break
            if last_start is not None:
                remaining=max(1.0,pause_seconds)-(time.monotonic()-last_start)
                if remaining>0:time.sleep(remaining)
            if (output_path.parent/'pause-inventory.flag').exists():break
            last_start=time.monotonic()
            quote=collect_website_quote(observation['attributes'],observation['context'],session=session)
            requests+=1
            observation['quote_observation']=quote;observation['quote_report']=quote['report']
            observation['quotes']=[q for q in observation.get('quotes',[]) if q.get('kind')!='website_dated_stay_quote']
            if quote.get('body') is not None:observation['quotes'].append({'kind':'website_dated_stay_quote',**quote})
            state['report']['quote_evidence_backfill_requests']=previous_backfill_requests+requests
            _atomic_checkpoint(output_path,state)
            if str(quote['report'].get('stop_reason','')).startswith('access_or_rate_limit_'):break
    return state

def _atomic_checkpoint(path,state):
    """Atomic replacement tolerates brief Windows readers; no shared temp name."""
    import os,time
    path=Path(path)
    temporary=path.with_name(path.name+'.'+str(os.getpid())+'.tmp')
    temporary.write_text(json.dumps(state,ensure_ascii=True,indent=2),encoding='utf-8')
    for attempt in range(20):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt==19:raise
            time.sleep(0.25)
