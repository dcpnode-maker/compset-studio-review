"""Observed public MakeMyTrip and Agoda evidence for Hotel Aketa.

The MakeMyTrip contract is presently unavailable: its dated document returned
only ``200-OK``. A source failure is never an unavailable hotel night. Agoda
capture uses ordinary Scrapling/Playwright form controls, never guessed RPCs.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
MMT_URL = 'https://www.makemytrip.com/hotels/hotel_aketa_rajpur_road_dehradun-details-dehradun.html'
AGODA_URL = 'https://www.agoda.com/hotel-aketa/hotel/dehradun-in.html'
MMT_ID = '202108231240265962'
AGODA_ID = '110205'
MMT_PRIOR = ROOT / 'data/hotels/aketa/canary-2026-09-28-v2.json'
ROOM_GRID = 'https://www.agoda.com/api/v1/property/room-grid'
BLOCK = re.compile(r'captcha|access denied|unusual traffic|verify (?:that )?you(?: are|.re) human', re.I)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safe_url(url):
    item = urlsplit(url)
    return urlunsplit((item.scheme, item.hostname or '', item.path, '', ''))


def _validate(source, hotel, context):
    if source not in {'makemytrip', 'agoda'}:
        raise ValueError('Unsupported direct source')
    if hotel.get('id') != 'aketa-dehradun' or hotel.get('name') != 'Hotel Aketa' or hotel.get('city') != 'Dehradun':
        raise ValueError('This adapter is verified for Aketa, Dehradun only')
    mapping = hotel.get('sources', {}).get(source, {})
    expected = MMT_URL if source == 'makemytrip' else AGODA_URL
    if mapping.get('url') != expected:
        raise ValueError('Property source differs from the observed mapping')
    if mapping.get('provider_id') not in {None, MMT_ID if source == 'makemytrip' else AGODA_ID}:
        raise ValueError('Provider ID differs from observed Aketa identity')
    if context.get('hotel_id', hotel['id']) != hotel['id']:
        raise ValueError('Requested hotel context mismatch')
    for key, value in {'rooms': 1, 'adults': 1, 'children': 0, 'stay_nights': 1}.items():
        if type(context.get(key)) is not int or context[key] != value:
            raise ValueError('One adult, zero children, one room and one night required')
    if context.get('currency') != 'INR':
        raise ValueError('INR is the observed source currency')
    start = date.fromisoformat(context['checkin'])
    end = date.fromisoformat(context['checkout'])
    if end - start != timedelta(days=1):
        raise ValueError('Exactly one night is required')


def _save(evidence, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    name = evidence['source'] + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json'
    path = output_dir / name
    evidence['source_artifact'] = str(path.resolve())
    path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding='utf-8')
    return evidence


def _mmt_capture(hotel, context):
    result = {'source': 'makemytrip', 'hotel_id': hotel['id'], 'captured_at': _now(),
              'observed_at': None, 'source_url': MMT_URL, 'browser_navigations': 0,
              'direct_requests': 0, 'capture_mode': 'cached_source_diagnostic',
              'stop_reason': 'source_contract_unavailable', 'requested_context': deepcopy(context),
              'prior_evidence_available': False}
    try:
        raw = MMT_PRIOR.read_bytes()
        prior = json.loads(raw)
    except (OSError, ValueError):
        result['stop_reason'] = 'prior_source_diagnostic_missing'
        return result
    # Reproject only the exact public diagnostic. Recommendation prices, opaque
    # endpoints and old default-party rates have no place in this observation.
    finals = [s for s in prior.get('snapshots', []) if s.get('stage') == 'after one-adult APPLY navigation']
    wanted = {'checkin', 'checkout', 'hotelId', 'roomStayQualifier', 'rsc', '_uCurrency'}
    fields = [deepcopy(f) for f in prior.get('returned_url_public_fields', [])
              if isinstance(f, dict) and f.get('path', '').removeprefix('$.query.') in wanted]
    if (prior.get('source_url') != MMT_URL or len(finals) != 1
            or finals[0].get('visible_text') != '200-OK'):
        result['stop_reason'] = 'prior_source_diagnostic_changed'
        return result
    result.update(observed_at=prior.get('observed_at'), prior_evidence_available=True,
                  prior_artifact=str(MMT_PRIOR), prior_sha256=hashlib.sha256(raw).hexdigest(),
                  browser_status=prior.get('report', {}).get('browser_status'),
                  response_text='200-OK', request_public_fields=fields)
    return result


def _mmt_observed(evidence):
    fields = evidence.get('request_public_fields', [])
    values = {}
    for item in fields:
        if not isinstance(item, dict):
            return {}
        key = item.get('path', '').removeprefix('$.query.')
        if key in values and values[key] != item.get('value'):
            return {}
        values[key] = item.get('value')
    if (values.get('hotelId') != MMT_ID or values.get('roomStayQualifier') != '1e0e'
            or values.get('rsc') != '1e1e0e' or values.get('_uCurrency') != 'INR'):
        return {}
    try:
        dates = {key: datetime.strptime(values[key], '%m%d%Y').date().isoformat()
                 for key in ('checkin', 'checkout')}
    except (ValueError, TypeError, KeyError):
        return {}
    return {'hotel_id': 'aketa-dehradun', 'provider_id': MMT_ID,
            **dates, 'rooms': 1, 'adults': 1, 'children': 0, 'currency': 'INR',
            'basis': 'observed_public_request_only'}


def _pick(value, keys):
    def public_leaf(item):
        if isinstance(item, str):
            if re.search(r'https?://|Bearer\s|[\w.+-]+@[\w.-]+', item, re.I):
                return '[omitted]'
            return item[:4000]
        if item is None or type(item) in (int, float, bool):
            return item
        if isinstance(item, list):
            return [public_leaf(x) for x in item[:100] if x is None or type(x) in (str, int, float, bool)]
        return None
    return {key: public_leaf(value[key]) for key in keys if isinstance(value, dict) and key in value}


def _project_grid(value):
    """An explicit public schema projection, excluding booking tokens and URLs."""
    result = _pick(value, ('propertyName', 'propertyId', 'cityId', 'countryId',
                           'searchCriteriaDescription', 'isSoldOut'))
    if not isinstance(value.get('rooms'), list):
        result['rooms'] = None  # Missing schema must never become an empty inventory list.
        return result
    result['rooms'] = []
    for room in value.get('rooms', [])[:100]:
        if not isinstance(room, dict):
            continue
        item = _pick(room, ('typeId', 'name', 'isSoldOut', 'roomSize'))
        item['offers'] = []
        for offer in room.get('offers', [])[:100]:
            if not isinstance(offer, dict):
                continue
            row = _pick(offer, ('typeId', 'name', 'isFit', 'isClosestOffering'))
            price = offer.get('price', {})
            row['price'] = _pick(price, ('priceInfo',))
            row['price']['final'] = _pick(price.get('final', {}), ('amount', 'amountNumber', 'currency', 'text'))
            row['occupancyItems'] = [_pick(x, ('text', 'occupancyTags')) for x in offer.get('occupancyItems', [])]
            row['benefits'] = [_pick(x, ('text', 'type')) for x in offer.get('benefits', [])]
            row['policies'] = [_pick(x, ('name', 'descriptions')) for x in offer.get('policies', [])]
            row['conditions'] = [_pick(x, ('type', 'text', 'textDescription'))
                                 for x in offer.get('conditions', offer.get('cxpRgRewardsAndDiscounts', []))]
            row['bookingDetails'] = _pick(offer.get('bookingDetails', {}),
                                          ('isBreakfastIncluded', 'isFreeCancellation', 'isInclusive'))
            item['offers'].append(row)
        result['rooms'].append(item)
    return result


def project_agoda_capture(raw, hotel, context):
    """Reproject saved research without any network or inferred request fields."""
    _validate('agoda', hotel, context)
    result = {'source': 'agoda', 'hotel_id': hotel['id'], 'source_url': AGODA_URL,
              'observed_at': raw.get('observed_at'), 'captured_at': _now(),
              'requested_context': deepcopy(context), 'browser_status': raw.get('browser_status'),
              'stop_reason': raw.get('stop_reason'), 'capture_mode': 'observed_browser_json',
              'browser_navigations': raw.get('browser_navigations', 1),
              'direct_requests': 0, 'snapshots': [], 'network': []}
    for snapshot in raw.get('snapshots', []):
        result['snapshots'].append({
            'stage': snapshot.get('stage'), 'url': _safe_url(snapshot.get('url', '')),
            'headings': [x for x in snapshot.get('headings', []) if 'Aketa' in x],
            'controls': [_pick(x, ('id', 'text', 'aria_label', 'value')) for x in snapshot.get('controls', [])
                         if x.get('id') in {'check-in-box', 'check-out-box', 'occupancy-box', 'textInput'}
                         or x.get('aria_label') == 'Price display in India Rupee']})
    for event in raw.get('network', []):
        if event.get('url') != ROOM_GRID:
            continue
        request = event.get('request', {})
        response = event.get('response', {})
        item = {'url': ROOM_GRID, **_pick(event, ('status', 'method'))}
        item['request'] = _pick(request, ('propertyId',))
        item['request']['searchCriteria'] = _pick(request.get('searchCriteria', {}) if isinstance(request, dict) else {},
                                                  ('adults', 'checkIn', 'checkOut', 'childrenAges', 'durationType', 'rooms'))
        item['response'] = _project_grid(response) if isinstance(response, dict) else None
        if event.get('response_error') or (isinstance(response, dict) and any(response.get(k) for k in ('error', 'errors'))):
            item['response_error'] = True
        result['network'].append(item)
    return result


AGODA_SNAPSHOT = r'''() => {
 const visible=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const selector=e=>{if(e.id)return '#'+CSS.escape(e.id);const p=[];while(e&&e!==document.body){
 const s=Array.from(e.parentElement?.children||[]).filter(x=>x.tagName===e.tagName);
 p.unshift(e.tagName.toLowerCase()+':nth-of-type('+(s.indexOf(e)+1)+')');e=e.parentElement;}return 'body > '+p.join(' > ');};
 return {title:document.title,headings:Array.from(document.querySelectorAll('h1')).map(e=>e.innerText),
 challenge_text:(document.body.innerText||'').slice(0,1600),
 controls:Array.from(document.querySelectorAll('#check-in-box,#check-out-box,#occupancy-box,input,button,[role="button"]'))
 .filter(visible).slice(0,180).map(e=>({selector:selector(e),id:e.id,text:(e.innerText||'').slice(0,160),
 aria_label:e.getAttribute('aria-label'),value:e.value||''}))};}'''


AGODA_SUBMITTED_READY = r'''expected => {
 const visible=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const challenge=(document.body?.innerText||'').slice(0,1600);
 if (/captcha|access denied|unusual traffic|verify (?:that )?you(?: are|.re) human/i.test(challenge)) return 'challenge';
 const label=id=>{const es=Array.from(document.querySelectorAll('#'+id)).filter(visible);
 return es.length===1?es[0].getAttribute('aria-label'):null;};
 const hotel=Array.from(document.querySelectorAll('h1')).some(e=>visible(e)&&e.innerText.includes('Hotel Aketa Rajpur Road Dehradun'));
 const currency=Array.from(document.querySelectorAll('[aria-label]')).some(e=>visible(e)&&e.getAttribute('aria-label')==='Price display in India Rupee');
 const party=(label('occupancy-box')||'').replace(/\s+/g,' ').trim();
 return hotel&&currency&&label('check-in-box')===expected.checkin&&label('check-out-box')===expected.checkout
 &&party==='Guests and rooms 1 adult 1 room'?'ready':false;
}'''


def _matching_agoda_response(raw, context):
    """Readiness only: parsing independently validates the complete response."""
    for event in raw.get('network', []):
        request = event.get('request')
        if not isinstance(request, dict):
            continue
        search = request.get('searchCriteria')
        if not isinstance(search, dict):
            continue
        if (event.get('url') == ROOM_GRID and event.get('method') == 'POST'
                and str(request.get('propertyId')) == AGODA_ID
                and search.get('checkIn') == context['checkin']
                and search.get('checkOut') == context['checkout']
                and type(search.get('adults')) is int and search['adults'] == 1
                and type(search.get('rooms')) is int and search['rooms'] == 1
                and search.get('childrenAges') == [] and search.get('durationType') == 'nightly'
                and 'response' in event):
            return True
    return False


def _wait_for_agoda_result(page, raw, context, *, timeout_ms=30000, clock=time.monotonic):
    """Wait through navigation for this stay's form and paired room-grid response.

    The waits service Playwright response callbacks and never issue another
    search or HTTP request. Short bounded slices observe source stops promptly.
    A previous page's controls cannot satisfy the final parser snapshot.
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    labels = {}
    for key, prefix in [('checkin', 'Check-in'), ('checkout', 'Check-out')]:
        day = date.fromisoformat(context[key])
        labels[key] = prefix + ' ' + str(day.day) + day.strftime(' %b %Y %A')
    deadline = clock() + timeout_ms / 1000
    while clock() < deadline:
        if raw.get('stop_reason'):
            return False
        remaining = max(1, int((deadline - clock()) * 1000))
        try:
            handle = page.wait_for_function(AGODA_SUBMITTED_READY, arg=labels,
                                            timeout=min(1000, remaining))
            state = handle.json_value()
            handle.dispose()
        except PlaywrightTimeoutError:
            continue
        if raw.get('stop_reason'):
            return False
        if state == 'challenge':
            raw['stop_reason'] = 'challenge_detected'
            return False
        if state == 'ready' and _matching_agoda_response(raw, context):
            return True
        page.wait_for_timeout(min(200, max(1, int((deadline - clock()) * 1000))))
    raw['stop_reason'] = raw.get('stop_reason') or 'submitted_result_timeout'
    return False


def _agoda_capture(hotel, context):
    from scrapling.fetchers import DynamicSession
    from .collect import _quiet_scrapling

    raw = {'source': 'agoda', 'observed_at': _now(), 'snapshots': [], 'network': [],
           'browser_navigations': 1, 'stop_reason': None}

    def snapshot(page, stage):
        value = page.evaluate(AGODA_SNAPSHOT)
        value.update(stage=stage, url=_safe_url(page.url))
        challenge = value.pop('challenge_text', '')
        if BLOCK.search(challenge):
            raw['stop_reason'] = 'challenge_detected'
        raw['snapshots'].append(value)
        return value

    def setup(page):
        def observed(request):
            parsed = urlsplit(request.url)
            if parsed.hostname != 'www.agoda.com' or request.resource_type not in {'document', 'xhr', 'fetch'}:
                return
            response = request.response()
            if response.status in {401, 403, 429}:
                raw['stop_reason'] = f'access_or_rate_limit_{response.status}'
            if _safe_url(request.url) != ROOM_GRID:
                return
            item = {'url': ROOM_GRID, 'status': response.status, 'method': request.method}
            try:
                body = request.post_data_json
                item['request'] = {'propertyId': body.get('propertyId'),
                                   'searchCriteria': _pick(body.get('searchCriteria', {}),
                                     ('adults', 'checkIn', 'checkOut', 'childrenAges', 'durationType', 'rooms'))}
                payload = response.json()
                item['response'] = _project_grid(payload)
                item['response_error'] = bool(payload.get('errors') or payload.get('error'))
            except Exception:
                item['response'] = None
            raw['network'].append(item)
        page.on('requestfinished', observed)

    def click(page, current, predicate):
        if raw['stop_reason']:
            raise RuntimeError('Source stopped')
        choices = [x for x in current['controls'] if predicate(x)]
        if len(choices) != 1:
            raise ValueError('Observed form control changed or ambiguous')
        control = page.locator(choices[0]['selector'])
        if control.count() != 1 or not control.is_visible() or not control.is_enabled():
            raise ValueError('Observed control is not actionable')
        control.click(timeout=5000)
        page.wait_for_timeout(500)

    def action(page):
        try:
            page.wait_for_timeout(5000)
            current = snapshot(page, 'initial')
            if not any('Hotel Aketa Rajpur Road Dehradun' in h for h in current['headings']):
                raw['stop_reason'] = 'property_identity_not_verified'
                return
            for key in ('checkin', 'checkout'):
                day = date.fromisoformat(context[key])
                label = day.strftime('%a %b %d %Y')
                if not any(x.get('aria_label') == label for x in current['controls']):
                    click(page, current, lambda x: x.get('id') == 'check-in-box')
                    current = snapshot(page, 'calendar open')
                # At most two observed Next Month actions within the frozen 30-day scope.
                for _ in range(2):
                    if any(x.get('aria_label') == label for x in current['controls']):
                        break
                    click(page, current, lambda x: x.get('aria_label') == 'Next Month')
                    current = snapshot(page, 'next month')
                click(page, current, lambda x: x.get('aria_label') == label)
                current = snapshot(page, 'selected ' + key)
            if not any(x.get('aria_label') == 'Subtract Adults' for x in current['controls']):
                click(page, current, lambda x: x.get('id') == 'occupancy-box')
                current = snapshot(page, 'occupancy open')
            occupancy = [x for x in current['controls'] if x.get('id') == 'occupancy-box']
            if len(occupancy) != 1 or '2 adults 1 room' not in ' '.join(occupancy[0].get('aria_label', '').split()):
                raw['stop_reason'] = 'initial_party_controls_changed'
                return
            click(page, current, lambda x: x.get('aria_label') == 'Subtract Adults')
            current = snapshot(page, 'one adult selected')
            click(page, current, lambda x: x.get('text') == 'SEARCH')
            _wait_for_agoda_result(page, raw, context)
            snapshot(page, 'after search')
        except Exception as exc:
            raw['stop_reason'] = raw['stop_reason'] or 'observed_form_contract_changed'
            raw['error_type'] = type(exc).__name__

    try:
        with _quiet_scrapling(), DynamicSession(headless=True,
                executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                retries=1, timeout=35000, google_search=False, locale='en-IN', timezone_id='Asia/Kolkata') as browser:
            response = browser.fetch(AGODA_URL, page_setup=setup, page_action=action, network_idle=False, wait=500)
            raw['browser_status'] = response.status
            if response.status in {401, 403, 429}:
                raw['stop_reason'] = f'access_or_rate_limit_{response.status}'
    except Exception as exc:
        raw['stop_reason'] = raw['stop_reason'] or 'browser_error'
        raw['error_type'] = type(exc).__name__
    return project_agoda_capture(raw, hotel, context)


def _agoda_rates(evidence, hotel, context):
    if evidence.get('stop_reason'):
        return {}, [], evidence['stop_reason']
    if evidence.get('browser_status') != 200:
        return {}, [], 'source_http_status_unknown'
    snapshots = [s for s in evidence.get('snapshots', []) if s.get('stage') == 'after search']
    if len(snapshots) != 1:
        return {}, [], 'submitted_form_not_observed'
    snapshot = snapshots[0]
    if snapshot.get('url') not in {AGODA_URL, AGODA_URL.replace('/hotel-aketa/', '/en-in/hotel-aketa/')}:
        return {}, [], 'returned_property_url_mismatch'
    controls = snapshot.get('controls', [])
    if not any(x.get('aria_label') == 'Price display in India Rupee' for x in controls):
        return {}, [], 'currency_not_verified'
    if not any('Hotel Aketa Rajpur Road Dehradun' in h for h in snapshot.get('headings', [])):
        return {}, [], 'property_identity_not_verified'
    for key, ident, prefix in [('checkin', 'check-in-box', 'Check-in'), ('checkout', 'check-out-box', 'Check-out')]:
        day = date.fromisoformat(context[key])
        label = prefix + ' ' + str(day.day) + day.strftime(' %b %Y %A')
        matching = [x for x in controls if x.get('id') == ident]
        if len(matching) != 1 or matching[0].get('aria_label') != label:
            return {}, [], 'returned_dates_mismatch'
    occupancy = [x for x in controls if x.get('id') == 'occupancy-box']
    if len(occupancy) != 1 or ' '.join(occupancy[0].get('aria_label', '').split()) != 'Guests and rooms 1 adult 1 room':
        return {}, [], 'returned_party_mismatch'
    matching = []
    for index, event in enumerate(evidence.get('network', [])):
        if event.get('status') in {401, 403, 429}:
            return {}, [], 'access_or_rate_limit_' + str(event['status'])
        request = event.get('request', {})
        search = request.get('searchCriteria', {})
        if search.get('checkIn') != context['checkin'] or search.get('checkOut') != context['checkout']:
            continue
        if (str(request.get('propertyId')) != AGODA_ID
                or type(search.get('adults')) is not int or search['adults'] != 1
                or type(search.get('rooms')) is not int or search['rooms'] != 1
                or search.get('childrenAges') != [] or search.get('durationType') != 'nightly'):
            continue  # Initial/default or alternative-party responses are not the submitted stay.
        if (event.get('url') != ROOM_GRID or event.get('method') != 'POST' or event.get('status') != 200
                or event.get('response_error')):
            return {}, [], 'returned_request_contract_mismatch'
        response = event.get('response')
        if not isinstance(response, dict):
            return {}, [], 'source_contract_unavailable'
        checkin, checkout = (date.fromisoformat(context[k]) for k in ('checkin', 'checkout'))
        echo = f'{checkin:%b} {checkin.day} - {checkout:%b} {checkout.day}, 1 guest'
        if (str(response.get('propertyId')) != AGODA_ID
                or response.get('propertyName', '').strip() != 'Hotel Aketa Rajpur Road Dehradun, Dehradun'
                or response.get('searchCriteriaDescription') != echo):
            return {}, [], 'returned_property_or_stay_mismatch'
        if response.get('isSoldOut') is True:
            if response.get('rooms') != []:
                return {}, [], 'property_availability_contract_unverified'
        elif response.get('isSoldOut') is not False:
            return {}, [], 'property_availability_contract_unverified'
        matching.append((index, response))
    if not matching:
        return {}, [], 'dated_room_grid_not_observed'
    observed = {'hotel_id': hotel['id'], 'provider_id': AGODA_ID,
                **{k: context[k] for k in ('checkin', 'checkout', 'rooms', 'adults', 'children', 'currency')}}
    sold_out = [response['isSoldOut'] for _, response in matching]
    if any(sold_out):
        if not all(sold_out):
            return observed, [], 'conflicting_stay_availability'
        return observed, [], 'source_unavailable_for_requested_stay'
    rates = {}
    for index, response in matching:
        for ri, room in enumerate(response.get('rooms', [])):
            for oi, offer in enumerate(room.get('offers', [])):
                price = offer.get('price', {})
                final = price.get('final', {})
                occupancy_items = offer.get('occupancyItems', [])
                # A second informational item may advertise that a child can
                # stay free. Actual requested children remain verified from
                # childrenAges=[]; only the explicit adult/room deal is matched.
                adult_items = [x for x in occupancy_items if re.fullmatch(r'\d+ adults?', x.get('text', ''))]
                price_info = price.get('priceInfo')
                if (price_info not in (['Per night before taxes'], ['Per night before taxes & fees'])
                        or final.get('currency') != '₹'
                        or type(final.get('amountNumber')) not in (float, int)
                        or room.get('isSoldOut') is not False or offer.get('isFit') is False
                        or offer.get('isClosestOffering') is True
                        or len(adult_items) != 1 or adult_items[0].get('text') != '1 adult'
                        or adult_items[0].get('occupancyTags') != ['1 room']):
                    continue
                try:
                    amount = Decimal(str(final['amountNumber']))
                    displayed = Decimal(final['amount'].replace(',', ''))
                except (InvalidOperation, ValueError, TypeError, KeyError, AttributeError):
                    continue
                if not amount.is_finite() or amount <= 0 or amount != displayed:
                    continue
                product = {k: offer.get(k) for k in ('benefits', 'policies', 'conditions', 'occupancyItems')}
                variant = hashlib.sha256(json.dumps(product, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
                key = (str(room.get('typeId')), str(offer.get('typeId')), variant)
                policies = offer.get('policies', [])
                row = {'source': 'agoda', 'channel': 'agoda', 'hotel_id': hotel['id'],
                       'provider_id': AGODA_ID, 'checkin': context['checkin'], 'checkout': context['checkout'],
                       'amount': format(amount, 'f'), 'approximate_amount': None, 'currency': 'INR',
                       'amount_type': 'ota_display_price', 'source_amount_basis': 'nightly_room_rate',
                       'precision': 'displayed_integer',
                       'display_amount': final.get('text'), 'direct_supplier_quote': False,
                       'context_verified': True, 'observed_context': deepcopy(observed),
                       'room_id': key[0], 'room_name': room.get('name'), 'rate_plan_id': key[1],
                       'product_variant_id': variant, 'product_variant_basis': 'hash_of_observed_public_terms',
                       'offer_occupancy': deepcopy(occupancy_items),
                       'rate_plan_name': offer.get('name') or None, 'taxes_included': False,
                       'fees_included': False if price_info == ['Per night before taxes & fees'] else None,
                       'taxes': None, 'fees': None,
                       'meals': [b.get('text') for b in offer.get('benefits', [])
                                 if b.get('text') in {'Breakfast Included', 'Lunch included', 'Dinner included'}] or None,
                       'benefits': deepcopy(offer.get('benefits', [])),
                       'cancellation': [p for p in policies if p.get('name') == 'Cancellation policy'] or None,
                       'conditions': deepcopy(offer.get('conditions', offer.get('cxpRgRewardsAndDiscounts', []))),
                       'payment': [p for p in policies if p.get('name') == 'Payment'] or None,
                       'provenance': {'source_url': AGODA_URL, 'observed_at': evidence.get('observed_at'),
                                      'source_artifact': evidence.get('source_artifact'),
                                      'source_path': f'network[{index}].response.rooms[{ri}].offers[{oi}]',
                                      'method': 'observed_browser_json'}}
                row['membership_required'] = any('MEMBERS ONLY' in c.get('text', '') for c in row['conditions'])
                row['discount_conditions'] = [c for c in row['conditions'] if c.get('type') == 'AUTO_APPLY_COUPON']
                row['discount_conditions'].extend(b for b in row['benefits'] if b.get('text', '').startswith('AGODA_SPONSORED - '))
                if key in rates and {k: v for k, v in rates[key].items() if k != 'provenance'} != {k: v for k, v in row.items() if k != 'provenance'}:
                    return observed, [], 'conflicting_duplicate_offer'
                rates[key] = row
    return observed, list(rates.values()), None if rates else 'no_verified_offer_prices'


def capture(source, hotel, context, *, output_dir):
    """Capture one exact stay, or preserve the cached MMT diagnostic without IO."""
    _validate(source, hotel, context)
    result = _mmt_capture(hotel, context) if source == 'makemytrip' else _agoda_capture(hotel, context)
    return _save(result, output_dir)


def parse(evidence, hotel, context):
    """Normalize only verified observed contracts; missing/changed stays remain unknown."""
    source = evidence.get('source')
    _validate(source, hotel, context)
    observed = _mmt_observed(evidence) if source == 'makemytrip' else {}
    result = {'hotel_id': hotel['id'], 'source': source,
              'observed_at': evidence.get('observed_at'),
              'requested_context': deepcopy(context), 'observed_context': observed,
              'status': 'unknown', 'reason': evidence.get('stop_reason') or 'source_contract_unavailable',
              'rates': [], 'browser_navigations': evidence.get('browser_navigations', 0),
              'direct_requests': evidence.get('direct_requests', 0),
              'provenance': {'source_url': evidence.get('source_url'),
                             'source_artifact': evidence.get('source_artifact'),
                             'capture_mode': evidence.get('capture_mode'),
                             'prior_artifact': evidence.get('prior_artifact'),
                             'prior_sha256': evidence.get('prior_sha256')}}
    if evidence.get('hotel_id') != hotel['id']:
        result['reason'] = 'capture_property_mismatch'
    elif source == 'agoda':
        try:
            observed, rates, reason = _agoda_rates(evidence, hotel, context)
        except (TypeError, ValueError, AttributeError, KeyError):
            observed, rates, reason = {}, [], 'source_schema_changed'
        result.update(observed_context=observed, rates=rates, reason=reason,
                      status='indicative' if rates else 'unknown')
        if reason == 'source_unavailable_for_requested_stay':
            result.update(status='unavailable', unavailability_verified=True)
    return result
