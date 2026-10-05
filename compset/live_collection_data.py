"""Read-only projections of the current saved collection evidence.

The dashboard never constructs a collector, changes a ledger, or calls a provider.
Only explicit public normalized fields leave this module.
"""
from datetime import date, datetime, timedelta, timezone
from contextlib import closing
import hashlib
import ipaddress
import json
import lzma
from pathlib import Path
import re
import sqlite3
import time


_STATS_CACHE = {}
_TTL = 3.0
_SCALAR_FIELDS = (
    'title','latitude','longitude','bedrooms','beds','bathrooms','guest_capacity',
    'room_type','property_type','instant_book','studio','area_name',
    'listing_rating_average','listing_review_count','is_superhost',
    'host_verified','pets_allowed','smoking_allowed','parties_allowed',
)
_ERROR_CATEGORIES = {
    'proxy_error','proxy_connection_error','connect_timeout','read_timeout',
    'connection_error','tls_error','provider_rate','provider_auth','challenge',
    'schema','local_failure','unknown',
}


def _config(config):
    if isinstance(config,(str,Path)):
        config=json.loads(Path(config).read_text(encoding='utf-8'))
    if not isinstance(config,dict):raise ValueError('collection_config_required')
    required=('base_root','collector_root','proxy_runtime_root','control_root')
    if any(not isinstance(config.get(key),str) for key in required):
        raise ValueError('collection_roots_required')
    return config


def _path(config,key):return Path(config[key])


def _read_json(path,default=None):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,UnicodeError,ValueError):return default


def _database(path):
    path=Path(path)
    if not path.is_file():raise FileNotFoundError('collection_database_unavailable')
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=2)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')  # Every multi-query projection sees one SQLite snapshot.
    return db


def _revision(path):
    path=Path(path)
    parts=[]
    for name in (path,Path(str(path)+'-wal')):
        try:
            stat=name.stat();parts.append((stat.st_size,stat.st_mtime_ns))
        except FileNotFoundError:parts.append(None)
    return hashlib.sha256(repr(parts).encode()).hexdigest()[:16]


def _counts(config):
    path=_path(config,'base_root')/'market.sqlite';revision=_revision(path)
    cached=_STATS_CACHE.get(str(path))
    if cached and cached[0]==revision and time.monotonic()-cached[1]<_TTL:
        return cached[2],revision
    with closing(_database(path)) as db:
        rows=db.execute('''WITH latest AS (
            SELECT observation_id,listing_id,kind,
              ROW_NUMBER() OVER (PARTITION BY provider,listing_id,kind
                                 ORDER BY captured_at DESC,observation_id DESC) AS rn
            FROM observations WHERE provider='airbnb')
            SELECT
              COUNT(DISTINCT CASE WHEN kind='profile' THEN listing_id END) AS profiles,
              COUNT(DISTINCT CASE WHEN kind='calendar' THEN listing_id END) AS calendars
            FROM latest WHERE rn=1''').fetchone()
        days=db.execute('''WITH latest AS (
            SELECT observation_id,
              ROW_NUMBER() OVER (PARTITION BY provider,listing_id,kind
                                 ORDER BY captured_at DESC,observation_id DESC) AS rn
            FROM observations WHERE provider='airbnb' AND kind='calendar')
            SELECT COUNT(*) AS calendar_rows
            FROM latest o JOIN calendar_days d USING(observation_id) WHERE o.rn=1''').fetchone()
        result={'profiles':rows['profiles'] or 0,'calendars':rows['calendars'] or 0,
                'calendar_rows':days['calendar_rows'] or 0,
                # Calendar availability has no validated, context-complete nightly quote.
                'daily_prices':0}
    _STATS_CACHE[str(path)]=(revision,time.monotonic(),result)
    return result,revision


def _safe_text(value,limit=120):
    if not isinstance(value,str):return None
    return value[:limit]


def _public_summary(value,state):
    if isinstance(value,str) and len(value)<=240 and not re.search(
        r'[/\\]|https?\b|(?:\d{1,3}\.){3}\d{1,3}|(?:token|secret|password|key)\s*[:=]',
        value,re.IGNORECASE):
        return value
    return {'queued':'Repair queued','running':'Repair in progress','proposed':'Repair proposed',
            'testing':'Repair under test','passed':'Repair tests passed','failed':'Repair failed',
            'rejected':'Repair rejected','applied':'Repair applied','fixed':'Repair verified',
            'waiting':'Repair is waiting for its required condition',
            'needs_attention':'Repair needs further attention'}.get(state,'Repair status unknown')


def _process_alive(receipt):
    if not isinstance(receipt,dict):return False
    try:
        from .collection_control import process_matches
        return bool(process_matches(receipt))
    except (ImportError,OSError,ValueError,TypeError,AttributeError):
        return False


def _proxy_pool(config):
    saved=_read_json(_path(config,'proxy_runtime_root')/'working_proxies.json',{})
    if not isinstance(saved,dict) or saved.get('global_stop') is not None:
        return {'healthy':0,'distinct_ipv4':0}
    now=datetime.now(timezone.utc);healthy=[];ips=set()
    for item in saved.get('proxies',[]):
        if not isinstance(item,dict) or item.get('alive') is not True or item.get('tls_verified') is not True:
            continue
        try:
            until=datetime.fromisoformat(item['valid_until'].replace('Z','+00:00'))
            ip=ipaddress.ip_address(item['origin'])
            if until<=now or not isinstance(ip,ipaddress.IPv4Address) or not ip.is_global:continue
        except (ValueError,KeyError,TypeError):continue
        healthy.append(item);ips.add(str(ip))
    return {'healthy':len(healthy),'distinct_ipv4':len(ips)}


def _provider_proxy_quality(collector):
    saved=_read_json(collector/'provider-route-quality.json',{})
    result={'fresh':False,'validated_ipv4':None,'updated_at':None}
    if not isinstance(saved,dict) or saved.get('schema')!='compset.airbnb-route-quality.v1':return result
    try:
        updated=datetime.fromisoformat(saved['updated_at'].replace('Z','+00:00'))
        if updated.tzinfo is None:return result
        age=(datetime.now(timezone.utc)-updated).total_seconds()
        count=saved['fresh_neutral_and_recent_airbnb_validated_ipv4']
        if type(count) is not int or not 0<=count<=100000:return result
        result['updated_at']=updated.isoformat()
        if 0<=age<=120:result.update(fresh=True,validated_ipv4=count)
    except (ValueError,TypeError,KeyError):pass
    return result


def _errors(collector_root):
    queue=_read_json(collector_root/'failure-queue.json',{})
    if not isinstance(queue,dict):return []
    result=[]
    for item in queue.get('immutable_records',[])[-50:]:
        if not isinstance(item,dict):continue
        rel=item.get('path','')
        if not re.fullmatch(r'failures/[0-9a-f]{32}\.json',rel):continue
        envelope=_read_json(collector_root/'failure-queue'/rel,{})
        record=envelope.get('record',{}) if isinstance(envelope,dict) else {}
        attempt=record.get('attempt',{}) if isinstance(record,dict) else {}
        diag=attempt.get('diagnostic',{}) if isinstance(attempt,dict) else {}
        category=diag.get('category') if isinstance(diag,dict) else None
        if category not in _ERROR_CATEGORIES:category='unknown'
        state=attempt.get('state')
        result.append({'id':_safe_text(record.get('parent_token'),32),
                       'at':_safe_text(attempt.get('admitted_at'),35),
                       'listing_id':_safe_text(attempt.get('listing_id'),30),
                       'kind':attempt.get('kind') if attempt.get('kind') in ('profile','calendar') else None,
                       'category':category,
                       'state':state if state in ('stopped','quarantined','pending','retrying','resolved') else 'unknown'})
    saved=_read_json(collector_root/'STATUS.json',{})
    if saved.get('state') in {'stopped','failed','interrupted'}:
        attempt=saved.get('current_attempt') or {}
        raw=saved.get('reason') or saved.get('error') or saved.get('error_type')
        reason=raw if isinstance(raw,str) and re.fullmatch(r'[A-Za-z0-9 _:.\-]{1,180}',raw) else 'Collection stopped; review the recorded incident.'
        result.append({'id':_safe_text(attempt.get('token'),32),'at':_safe_text(saved.get('updated_at'),40),
                       'listing_id':_safe_text(attempt.get('listing_id'),30),'kind':_safe_text(attempt.get('kind'),20),
                       'category':'local_failure' if reason=='route_changed_after_preflight_no_failover' else 'unknown',
                       'state':saved['state'],'reason':reason})
    return result


def _repairs(control_root):
    root=control_root/'repairs'
    if not root.is_dir():return []
    result=[]
    for path in sorted(root.glob('*.json'))[-30:]:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}\.json',path.name):continue
        row=_read_json(path,{})
        if not isinstance(row,dict):continue
        state=row.get('state')
        if state not in ('queued','running','proposed','testing','passed','failed','rejected','applied',
                         'fixed','waiting','needs_attention'):
            state='unknown'
        model=row.get('model')
        if not isinstance(model,str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,60}',model):model=None
        result.append({'id':path.stem,
                       'state':state,'model':model,
                       'summary':_public_summary(row.get('summary'),state),
                       'started_at':_safe_text(row.get('started_at'),40),
                       'finished_at':_safe_text(row.get('finished_at'),40)})
    return result


def status(config):
    """Return saved market counts plus independently verified process/pool health."""
    config=_config(config);base=_path(config,'base_root');collector=_path(config,'collector_root')
    saved=_read_json(collector/'STATUS.json',{})
    receipt=_read_json(collector/'PROCESS.json',{})
    if not isinstance(saved,dict):saved={}
    alive=_process_alive(receipt)
    try:counts,revision=_counts(config)
    except (OSError,sqlite3.Error):
        counts={'profiles':None,'calendars':None,'calendar_rows':None,'daily_prices':None}
        revision=None
    progress={'completed':int(saved.get('new_completed_tasks') or 0),
              'total':int(saved.get('selected_tasks') or 0),
              'quarantined':int(saved.get('new_quarantined_tasks') or 0)}
    admission=saved.get('admission',{}) if isinstance(saved.get('admission'),dict) else {}
    effective=admission.get('effective_pacing',{}) if isinstance(admission.get('effective_pacing'),dict) else {}
    try:
        with closing(_database(base/'market.sqlite')) as db:
            since=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
            recent=db.execute("SELECT COUNT(*) FROM observations WHERE provider='airbnb' AND captured_at>=?",(since,)).fetchone()[0]
    except (OSError,sqlite3.Error):recent=None
    active_states={'starting','running','waiting','waiting_pool','cooling_down','waiting_discovery'}
    known_states=active_states|{'stopped','completed','paused','budget_exhausted','failed','interrupted'}
    state=saved.get('state') if saved.get('state') in known_states else 'unavailable'
    if alive and not saved:state='starting'
    if state in active_states and not alive:state='unavailable'
    pool=_proxy_pool(config)
    provider_quality=_provider_proxy_quality(collector)
    sources=[{'name':'Airbnb public observations','state':'unavailable' if revision is None else 'available' if counts['profiles'] else 'empty',
              'note':'Saved profile and availability evidence; daily prices remain unknown without observed dated amounts.'},
             {'name':'Proxy pool','state':'healthy' if pool['healthy'] else 'unavailable',
              'note':'Neutral HTTPS checks and recent validated Airbnb payloads are counted separately. Residential status is unknown.'}]
    hotel_root=config.get('hotel_root')
    if hotel_root:
        coverage=_read_json(Path(hotel_root)/'coverage.json',{})
        sources.append({'name':'Hotel saved research','state':'available' if coverage.get('hotels') else 'unavailable',
                        'note':'Saved 17 hotel research; indicative or approximate calendar evidence is not an all-in quote.'})
    refresh={'state':'running' if alive and state in active_states else 'idle',
             'message':('Collection is active.' if state in {'running','starting'} else
                        'Collection is waiting under its saved pacing or pool rule.')
                       if alive and state in active_states else 'No active collection verified.'}
    if alive and state=='waiting_discovery':
        refresh={'state':'waiting','message':'The current search plan is exhausted. Further market coverage needs a validated discovery plan.'}
    demand=_read_json(_path(config,'control_root')/'refresh.json',{})
    if not alive and demand.get('collector_root')==str(collector) and demand.get('state') in {'review_requested','paused'}:
        refresh={'state':demand['state'],'message':_safe_text(demand.get('message'),180)}
    return {'state':state,'updated_at':_safe_text(saved.get('updated_at'),40),
            'revision':revision,
            'process_alive':alive,'counts':counts,'progress':progress,'proxy_pool':pool,
            'provider_proxy_quality':provider_quality,
            'discovery':{'state':_safe_text(saved.get('discovery_state'),100),
                         'pages':saved.get('discovery_pages',0),
                         'unique_ids':saved.get('discovered_listing_ids',0),
                         'new_in_bounds_ids':saved.get('new_in_bounds_listing_ids',0),
                         'pending_cells':saved.get('pending_search_cells'),
                         'full_market_census':False},
            'rate':{'validated_last_hour':recent,
                    'configured_hourly_limit':effective.get('hour') if isinstance(effective.get('hour'),int) else None,
                    'measured_provider_limit':None},
            'errors':_errors(collector),'repairs':_repairs(_path(config,'control_root')),
            'sources':sources,'refresh':refresh}


def profile(config,query=None):
    config=_config(config);query=query or {}
    listing_id=query.get('listing_id')
    if set(query)!={'listing_id'} or not isinstance(listing_id,str) or not re.fullmatch(r'[0-9]{1,30}',listing_id):
        raise ValueError('valid_listing_id_required')
    with closing(_database(_path(config,'base_root')/'market.sqlite')) as db:
        observation=db.execute('''SELECT observation_id,captured_at,context_json FROM observations
            WHERE provider='airbnb' AND kind='profile' AND listing_id=?
            ORDER BY captured_at DESC,observation_id DESC LIMIT 1''',(listing_id,)).fetchone()
        fields={}
        if observation:
            for row in db.execute('SELECT field_name,status,value_json FROM profile_fields WHERE observation_id=? ORDER BY field_name',(observation['observation_id'],)):
                status=row['status'] if row['status'] in ('observed','missing','null','conflict') else 'unknown'
                value=json.loads(row['value_json']) if status=='observed' else None
                fields[row['field_name']]={'status':status,'value':value}
    raw=json.loads(observation['context_json']) if observation else {}
    context={key:raw.get(key) for key in ('check_in','check_out','adults','children','infants','pets','currency')}
    return {'listing_id':listing_id,'observed_at':observation['captured_at'] if observation else None,
            'context':context,'fields':fields}


def _pagination(query):
    query=query or {}
    if not isinstance(query,dict):raise ValueError('query_object_required')
    if set(query)-{'offset','limit','query','bedrooms'}:raise ValueError('unknown_listing_query_field')
    try:offset=int(query.get('offset',0));limit=int(query.get('limit',50))
    except (TypeError,ValueError):raise ValueError('query_page_out_of_range') from None
    if offset<0 or offset>100000 or limit<1 or limit>100:raise ValueError('query_page_out_of_range')
    text=query.get('query','')
    if not isinstance(text,str) or len(text)>120:raise ValueError('query_too_long')
    bedrooms=query.get('bedrooms')
    if bedrooms not in (None,''):
        try:bedrooms=int(bedrooms)
        except (TypeError,ValueError):raise ValueError('bedrooms_out_of_range') from None
        if bedrooms<0 or bedrooms>100:raise ValueError('bedrooms_out_of_range')
    else:bedrooms=None
    return offset,limit,text.strip().casefold(),bedrooms


def _map_pagination(query):
    query=query or {}
    if not isinstance(query,dict):raise ValueError('query_object_required')
    if set(query)-{'offset','limit','query','bedrooms'}:raise ValueError('unknown_map_query_field')
    try:offset=int(query.get('offset',0));limit=int(query.get('limit',2000))
    except (TypeError,ValueError):raise ValueError('query_page_out_of_range') from None
    if offset<0 or offset>100000 or limit<1 or limit>2000:raise ValueError('query_page_out_of_range')
    text=query.get('query','')
    if not isinstance(text,str) or len(text)>120:raise ValueError('query_too_long')
    bedrooms=query.get('bedrooms')
    if bedrooms not in (None,''):
        try:bedrooms=int(bedrooms)
        except (TypeError,ValueError):raise ValueError('bedrooms_out_of_range') from None
        if bedrooms<0 or bedrooms>100:raise ValueError('bedrooms_out_of_range')
    else:bedrooms=None
    return offset,limit,text.strip().casefold(),bedrooms


def _field_map(db,observation_ids):
    if not observation_ids:return {}
    result={}
    # Keep below SQLite's conservative 999-parameter limit on older runtimes.
    for start in range(0,len(observation_ids),500):
        batch=observation_ids[start:start+500]
        placeholders=','.join('?' for _ in batch)
        rows=db.execute(f'''SELECT observation_id,field_name,status,value_json FROM profile_fields
            WHERE observation_id IN ({placeholders}) AND field_name IN ({','.join('?' for _ in _SCALAR_FIELDS)})''',
            [*batch,*_SCALAR_FIELDS])
        for row in rows:
            try:value=json.loads(row['value_json'])
            except ValueError:value=None
            status=row['status'] if row['status'] in ('observed','missing','null','conflict') else 'unknown'
            if status!='observed':value=None
            if not isinstance(value,(str,int,float,bool,type(None))):value=None
            result.setdefault(row['observation_id'],{})[row['field_name']]={'status':status,'value':value}
    return result


def _latest_profiles(config,needle,bedrooms):
    path=_path(config,'base_root')/'market.sqlite';revision=_revision(path)
    with closing(_database(path)) as db:
        observations=db.execute('''SELECT observation_id,listing_id,captured_at FROM (
          SELECT observation_id,listing_id,captured_at,
            ROW_NUMBER() OVER (PARTITION BY provider,listing_id
                               ORDER BY captured_at DESC,observation_id DESC) AS rn
          FROM observations WHERE provider='airbnb' AND kind='profile')
          WHERE rn=1 ORDER BY listing_id''').fetchall()
        fields=_field_map(db,[row['observation_id'] for row in observations])
    selected=[]
    for row in observations:
        field=fields.get(row['observation_id'],{})
        get=lambda name:field.get(name,{}).get('value')
        if needle and needle not in str(get('title') or '').casefold() and needle not in row['listing_id']:
            continue
        if bedrooms==0:
            if get('bedrooms')!=0 and get('studio') is not True:continue
        elif bedrooms is not None and get('bedrooms')!=bedrooms:continue
        selected.append({'listing_id':row['listing_id'],'title':get('title'),
            'latitude':get('latitude'),'longitude':get('longitude'),
            'bedrooms':get('bedrooms'),'beds':get('beds'),'bathrooms':get('bathrooms'),
            'person_capacity':get('guest_capacity'),'room_type':get('room_type'),
            'property_type':get('property_type'),'instant_book':get('instant_book'),
            'observed_at':row['captured_at'],'fields':field})
    return selected,revision


def listings(config,query=None):
    config=_config(config);offset,limit,needle,bedrooms=_pagination(query)
    selected,revision=_latest_profiles(config,needle,bedrooms)
    return {'total':len(selected),'revision':revision,'listings':selected[offset:offset+limit]}


def _valid_coordinate_pair(latitude,longitude):
    # bool is an int subclass; JSON booleans are not geographic coordinates.
    if isinstance(latitude,bool) or isinstance(longitude,bool):return False
    if not isinstance(latitude,(int,float)) or not isinstance(longitude,(int,float)):return False
    if not (float('-inf')<latitude<float('inf') and float('-inf')<longitude<float('inf')):return False
    return -90<=latitude<=90 and -180<=longitude<=180


def map(config,query=None):
    """Return a paginated, compact map view over all matching latest profiles."""
    config=_config(config);offset,limit,needle,bedrooms=_map_pagination(query)
    selected,revision=_latest_profiles(config,needle,bedrooms)
    points=[];unmapped=0
    for row in selected:
        latitude=row['latitude'];longitude=row['longitude']
        if not _valid_coordinate_pair(latitude,longitude):
            unmapped+=1
            continue
        points.append({key:row[key] for key in (
            'listing_id','title','latitude','longitude','bedrooms','beds','room_type','instant_book')})
        points[-1]['guest_capacity']=row['person_capacity']
    page=points[offset:offset+limit]
    next_offset=offset+len(page) if offset+len(page)<len(points) else None
    return {'total':len(selected),'mapped_total':len(points),'unmapped_total':unmapped,
            'points':page,'next_offset':next_offset,'revision':revision}


def _calendar_value(fields,name):
    item=fields.get(name,{})
    return item.get('value') if isinstance(item,dict) and item.get('status')=='observed' else None


def calendar(config,query):
    config=_config(config)
    if not isinstance(query,dict):raise ValueError('calendar_query_required')
    if set(query)-{'listing_id','start','days'}:raise ValueError('unknown_calendar_query_field')
    listing_id=query.get('listing_id')
    if not isinstance(listing_id,str) or not re.fullmatch(r'[0-9]{1,30}',listing_id):
        raise ValueError('listing_id_required')
    try:
        start=date.fromisoformat(query['start'])
        if start.isoformat()!=query['start']:raise ValueError()
    except (KeyError,TypeError,ValueError):raise ValueError('valid_iso_start_required') from None
    try:days=int(query.get('days',30))
    except (TypeError,ValueError):raise ValueError('calendar_days_out_of_range') from None
    if days<1 or days>366:raise ValueError('calendar_days_out_of_range')
    try:end=start+timedelta(days=days)
    except OverflowError:raise ValueError('calendar_date_out_of_range') from None
    with closing(_database(_path(config,'base_root')/'market.sqlite')) as db:
        observation=db.execute('''SELECT observation_id,captured_at,context_json FROM observations
          WHERE provider='airbnb' AND kind='calendar' AND listing_id=?
          ORDER BY captured_at DESC,observation_id DESC LIMIT 1''',(listing_id,)).fetchone()
        rows={}
        if observation:
            for row in db.execute('''SELECT calendar_date,fields_json FROM calendar_days
              WHERE observation_id=? AND calendar_date>=? AND calendar_date<?''',
              (observation['observation_id'],start.isoformat(),end.isoformat())):
                rows[row['calendar_date']]=json.loads(row['fields_json'])
    result=[]
    for i in range(days):
        day=(start+timedelta(days=i)).isoformat();fields=rows.get(day,{})
        result.append({'date':day,'available':_calendar_value(fields,'available'),
            'available_for_checkin':_calendar_value(fields,'availableForCheckin'),
            'available_for_checkout':_calendar_value(fields,'availableForCheckout'),
            'bookable':_calendar_value(fields,'bookable'),
            'min_nights':_calendar_value(fields,'minNights'),
            'max_nights':_calendar_value(fields,'maxNights'),
            'nightly_price':None})
    raw_context=json.loads(observation['context_json']) if observation else {}
    context={'observed_at':observation['captured_at'] if observation else None,
             'currency':raw_context.get('currency'),
             'source_kind':raw_context.get('source_kind'),
             'party':{'adults':raw_context.get('adults'),'children':raw_context.get('children')},
             'nightly_price_status':'unknown_without_validated_dated_quote',
             'calendar_observed':bool(observation)}
    return {'listing_id':listing_id,'dates':result,'context':context}


def hotels(config,query=None):
    """Saved hotel membership with evidence coverage, never an all-in price claim."""
    config=_config(config);query=query or {}
    if not isinstance(query,dict):raise ValueError('query_object_required')
    if set(query)-{'offset','limit','query','hotel_id','start','days'}:
        raise ValueError('unknown_hotel_query_field')
    try:offset=int(query.get('offset',0));limit=int(query.get('limit',50))
    except (TypeError,ValueError):raise ValueError('hotel_query_out_of_range') from None
    needle=query.get('query','')
    if offset<0 or limit<1 or limit>100 or not isinstance(needle,str) or len(needle)>120:
        raise ValueError('hotel_query_out_of_range')
    root=Path(config.get('hotel_root',''))
    path=root/'market.sqlite3';coverage=_read_json(root/'coverage.json',{})
    if query.get('hotel_id') is None and ({'start','days'} & set(query)):
        raise ValueError('hotel_id_required_for_rates')
    with closing(_database(path)) as db:
        rows=db.execute('''SELECT h.id,h.name,
          (SELECT MAX(o.observed_at) FROM profile_observations o
             JOIN profile_versions v ON v.id=o.version_id WHERE v.hotel_id=h.id) AS last_profile_at,
          (SELECT COUNT(*) FROM rates r WHERE r.hotel_id=h.id) AS saved_rate_observations
          FROM hotels h ORDER BY h.name,h.id''').fetchall()
        rates=[];rate_context=None
        hotel_id=query.get('hotel_id')
        if hotel_id is not None:
            if not isinstance(hotel_id,str) or len(hotel_id)>120 or hotel_id not in {r['id'] for r in rows}:
                raise ValueError('unknown_hotel_id')
            try:
                start=date.fromisoformat(query['start'])
                if start.isoformat()!=query['start']:raise ValueError()
            except (KeyError,TypeError,ValueError):raise ValueError('valid_iso_start_required') from None
            try:days=int(query.get('days',30))
            except (TypeError,ValueError):raise ValueError('hotel_days_out_of_range') from None
            if days<1 or days>366:raise ValueError('hotel_days_out_of_range')
            try:end=start+timedelta(days=days)
            except OverflowError:raise ValueError('hotel_date_out_of_range') from None
            rate_context={'hotel_id':hotel_id,'start':start.isoformat(),'days':days,
                          'adults':1,'rooms':1,'children':0,'currency':'INR'}
            saved=db.execute('''SELECT r.id,r.checkin,r.provider,r.channel,r.observed_at,
                    b.codec,b.bytes,b.payload,b.sha
                FROM rates r JOIN blobs b ON b.sha=r.payload_sha
                WHERE r.hotel_id=? AND r.checkin>=? AND r.checkin<?
                ORDER BY r.observed_at DESC,r.id DESC''',
                (hotel_id,start.isoformat(),end.isoformat())).fetchall()
            latest={}
            for row in saved:
                if row['codec']!='xz' or type(row['bytes']) is not int or not 0<row['bytes']<=2_000_000:continue
                if len(row['payload'])>2_000_000:continue
                try:
                    decoder=lzma.LZMADecompressor()
                    raw=decoder.decompress(row['payload'],max_length=row['bytes']+1)
                    if not decoder.eof or decoder.unused_data:continue
                    if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha']:continue
                    payload=json.loads(raw)
                except (lzma.LZMAError,ValueError,TypeError):continue
                if not isinstance(payload,dict) or payload.get('hotel_id')!=hotel_id or payload.get('checkin')!=row['checkin']:
                    continue
                price_form=('amount' if payload.get('amount') is not None else
                            'approximate' if payload.get('approximate_amount') is not None else 'none')
                identity=(row['checkin'],row['provider'],row['channel'],payload.get('basis'),
                          price_form,
                          payload.get('room_id'),payload.get('provider_room_id'),
                          payload.get('room_name'),payload.get('offer_key'),
                          json.dumps(payload.get('eligibility'),sort_keys=True))
                if identity in latest:continue
                amount=payload.get('amount')
                approx=payload.get('approximate_amount')
                if not isinstance(amount,(str,int,float)) or isinstance(amount,bool):amount=None
                if not isinstance(approx,(str,int,float)) or isinstance(approx,bool):approx=None
                basis=payload.get('basis')
                comparable=(amount is not None and basis=='inclusive_stay_total'
                    and payload.get('source_sold_out') is not True
                    and payload.get('availability') not in ('sold_out','unavailable',
                        'source_reports_sold_out','not_available')
                    and all(payload.get(k) is True for k in ('identity_verified','context_verified',
                        'taxes_included','mandatory_fees_included','public_eligibility_verified')))
                if comparable:price_status='public_all_in'
                elif amount is not None and basis=='indicative_calendar_minimum':price_status='indicative'
                elif approx is not None and basis=='indicative_calendar_minimum':price_status='approximate'
                elif amount is not None:price_status='source_display'
                else:price_status='no_price'
                latest[identity]={'rate_id':row['id'],'checkin':row['checkin'],
                    'checkout':payload.get('checkout'),'provider':row['provider'],'channel':row['channel'],
                    'observed_at':row['observed_at'],'amount':amount,'approximate_amount':approx,
                    'currency':payload.get('currency'),'basis':basis,'precision':payload.get('precision'),
                    'availability':payload.get('availability'),
                    'room_name':_safe_text(payload.get('room_name'),120),
                    **{key:payload.get(key) if type(payload.get(key)) is bool else None
                       for key in ('identity_verified','context_verified','taxes_included',
                                   'mandatory_fees_included','public_eligibility_verified')},
                    'comparable_public_total':comparable,'price_status':price_status}
            rates=sorted(latest.values(),key=lambda r:(r['checkin'],r['provider'],r['channel'],r['rate_id']))
    result=[{'hotel_id':row['id'],'name':row['name'],
             'last_profile_at':row['last_profile_at'],
             'saved_rate_observations':row['saved_rate_observations'],
             'price_status':'unknown_all_in',
             'evidence_note':'Saved observations may be indicative or approximate; context and taxes are not fully verified.'}
            for row in rows if needle.casefold() in row['name'].casefold()]
    response={'total':len(result),'revision':_revision(path),'hotels':result[offset:offset+limit],
            'coverage':{'saved_hotels':coverage.get('hotels',len(rows)),
                        'indicative_cells':coverage.get('annual_indicative_cells',0),
                        'approximate_cells':coverage.get('annual_approximate_calendar_cells',0),
                        'public_all_in_cells':coverage.get('annual_public_inclusive_observed_cells',0)}}
    if rate_context is not None:
        response.update(rate_context=rate_context,rates=rates,rate_count=len(rates))
    return response
