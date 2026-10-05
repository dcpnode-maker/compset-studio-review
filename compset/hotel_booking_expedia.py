"""Bounded direct Booking.com / Expedia evidence, with honest source health.

The September 2026 canaries encountered access challenges before an exact
one-adult quote could be verified. Consequently this adapter deliberately does
not promote teaser/default-date prices to stay quotes. The next successful
capture is retained for explicit contract discovery, rather than inventing an
endpoint or treating an access failure as sold out.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

SOURCES = {'booking', 'expedia'}
HOSTS = {'booking': {'www.booking.com'}, 'expedia': {'www.expedia.co.in', 'www.expedia.com'}}
STOP_STATUSES = {401, 403, 429}
CHALLENGE = re.compile(r"verify.{0,40}(?:not a robot|human)|show us your human side|"
                       r"can't tell if you're a human|captcha|access denied|unusual traffic", re.I)
CONTEXT_FIELDS = ('checkin', 'checkout', 'rooms', 'adults', 'children', 'currency', 'stay_nights')

# Public visible material only. No cookies, storage, request headers, request
# bodies, inline application state, hidden inputs, or traveller names are saved.
SNAPSHOT_JS = r"""() => {
 const vis=e=>!!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
 const text=(document.body?.innerText||'');
 const cutoff=['Popular amenities','Guest reviews','Traveller reviews','See availability'].map(x=>text.indexOf(x)).filter(x=>x>0);
 return {title:document.title,headings:Array.from(document.querySelectorAll('h1')).filter(vis).map(e=>e.innerText.slice(0,200)),
 visible_text:text.slice(0,Math.min(5000,...cutoff)),
 controls:Array.from(document.querySelectorAll('button,input,[role="button"]')).filter(vis)
 .map(e=>({text:(e.innerText||'').slice(0,160),aria_label:e.getAttribute('aria-label'),name:e.name||'',type:e.type||'',value:e.value||''}))
 .filter(e=> /date|check.?in|check.?out|traveller|traveler|adult|children|room|search/i.test([e.text,e.aria_label,e.name].join(' ')))
 .filter(e=>! /password|email|cookie|token|session|secret|login|sign in/i.test([e.name,e.type,e.aria_label].join(' ')))
 .slice(0,80)};
}"""


def _canonical_url(value):
    parts = urlsplit(value)
    return urlunsplit((parts.scheme, parts.hostname or '', parts.path, '', ''))


def _validate(source, hotel, context):
    if source not in SOURCES:
        raise ValueError('Unsupported direct source')
    mapping = hotel.get('sources', {}).get(source, {})
    value = mapping.get('url', '')
    parts = urlsplit(value)
    if (parts.scheme != 'https' or parts.hostname not in HOSTS[source]
            or parts.port is not None or parts.username or parts.password or parts.query or parts.fragment):
        raise ValueError('Expected canonical HTTPS property URL on the source host')
    if source == 'booking' and not re.fullmatch(r'/hotel/[a-z]{2}/[a-z0-9.-]+\.html', parts.path):
        raise ValueError('Expected Booking.com property URL')
    if source == 'expedia' and not re.fullmatch(r'/[^/]+\.h[0-9]+\.Hotel-Information', parts.path):
        raise ValueError('Expected Expedia property URL')
    if source == 'expedia' and mapping.get('provider_id') != re.search(r'\.h([0-9]+)\.', parts.path)[1]:
        raise ValueError('Expedia property ID does not match mapping')
    if not hotel.get('id') or not hotel.get('name') or not hotel.get('city'):
        raise ValueError('Hotel identity required')
    checkin, checkout = date.fromisoformat(context['checkin']), date.fromisoformat(context['checkout'])
    if (checkout - checkin).days != context.get('stay_nights') or context.get('stay_nights') != 1:
        raise ValueError('This adapter requires an explicit one-night stay')
    if any(type(context.get(k)) is not int or context[k] != v
           for k, v in [('rooms', 1), ('adults', 1), ('children', 0)]):
        raise ValueError('This adapter supports one room, one adult, no children')
    if context.get('currency') != 'INR':
        raise ValueError('This rollout requires INR')
    return value


def _sanitize_snapshot(snapshot, url):
    controls = []
    for item in snapshot.get('controls', [])[:80]:
        if not isinstance(item, dict):
            continue
        if re.search(r'password|email|cookie|token|session|secret|login|sign in',
                     ' '.join(str(item.get(k, '')) for k in ('name', 'type', 'aria_label')), re.I):
            continue
        controls.append({k: str(item.get(k) or '')[:160]
                         for k in ('text', 'aria_label', 'name', 'type', 'value')})
    result = {'url': _canonical_url(url), 'title': str(snapshot.get('title') or '')[:250],
              'headings': [str(x)[:200] for x in snapshot.get('headings', [])][:5],
              'visible_text': str(snapshot.get('visible_text') or '')[:5000],
              'controls': controls}
    if CHALLENGE.search(result['visible_text'][:3000]) or CHALLENGE.search(result['title']):
        # Challenge identifiers/fingerprints are neither property nor rate data.
        result.update(visible_text='Access challenge detected; no property rate evidence.', controls=[], headings=[],
                      challenge_detected=True)
    return result


def _write_capture(value, output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode('utf-8')
    digest = hashlib.sha256(raw).hexdigest()
    path = output / (value['source'] + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + digest[:10] + '.json')
    path.write_bytes(raw)
    return {**value, 'artifact_path': str(path.resolve()), 'artifact_sha256': digest}


def capture(source, hotel, context, *, output_dir: Path):
    """One ordinary public browser navigation; no direct replay or access retry.

    Dates/party in the requested envelope describe the job, not the source's
    returned context. Successful undated content remains unverified until a
    supported, observed exact-stay contract is available.
    """
    url = _validate(source, hotel, context)
    result = {'source': source, 'hotel_id': hotel['id'], 'source_url': url,
              'observed_at': datetime.now(timezone.utc).isoformat(),
              'requested_context': deepcopy(context), 'snapshots': [], 'responses': [],
              'stop_reason': None, 'browser_status': None, 'browser_navigations': 0,
              'direct_requests': 0, 'method': 'scrapling_dynamic_public_page',
              'exact_stay_form_supported': False}
    from scrapling.fetchers import DynamicSession
    from .collect import _quiet_scrapling

    def setup(page):
        def request_seen(request):
            if request.is_navigation_request() and request.frame == page.main_frame:
                result['browser_navigations'] += 1

        def response_seen(response):
            parts = urlsplit(response.url)
            if parts.hostname not in HOSTS[source] or response.request.resource_type not in {'document', 'xhr', 'fetch'}:
                return
            if response.request.is_navigation_request() and response.request.frame == page.main_frame:
                result['browser_status'] = response.status
            if response.status in STOP_STATUSES:
                result['stop_reason'] = result['stop_reason'] or f'access_or_rate_limit_{response.status}'
            # URLs and HTTP status only; no analytics payloads or query tokens.
            if response.request.resource_type == 'document' or response.status in STOP_STATUSES:
                result['responses'].append({'url': _canonical_url(response.url), 'status': response.status})
        page.on('request', request_seen)
        page.on('response', response_seen)

    def action(page):
        if not result['stop_reason']:
            page.wait_for_timeout(2500)
        snapshot = _sanitize_snapshot(page.evaluate(SNAPSHOT_JS), page.url)
        result['snapshots'].append(snapshot)
        if snapshot.get('challenge_detected'):
            result['stop_reason'] = result['stop_reason'] or 'challenge_detected'
        if not result['stop_reason']:
            result['stop_reason'] = 'exact_stay_contract_not_discovered'

    with _quiet_scrapling():
        try:
            with DynamicSession(headless=True, executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                                retries=1, timeout=30000, google_search=False, locale='en-IN', timezone_id=hotel['timezone']) as browser:
                response = browser.fetch(url, page_setup=setup, page_action=action, network_idle=False, wait=250)
                if result['browser_status'] is None:
                    result['browser_status'] = response.status
                if response.status in STOP_STATUSES:
                    result['stop_reason'] = f'access_or_rate_limit_{response.status}'
        except Exception as exc:
            result['stop_reason'] = result['stop_reason'] or 'browser_error'
            result['error_type'] = type(exc).__name__
    return _write_capture(result, output_dir)


def parse(capture, hotel, context):
    """Only actual source evidence counts; caller-provided quote objects do not."""
    source = capture.get('source')
    url = _validate(source, hotel, context)
    result = {'hotel_id': hotel['id'], 'source': source, 'observed_at': capture.get('observed_at'),
              'requested_context': deepcopy(context), 'observed_context': {}, 'status': 'unknown',
              'reason': None, 'rates': [], 'provenance': {'source_url': url,
              'artifact_path': capture.get('artifact_path'), 'artifact_sha256': capture.get('artifact_sha256'),
              'method': capture.get('method'), 'browser_status': capture.get('browser_status'),
              'browser_navigations': capture.get('browser_navigations', 0),
              'direct_requests': capture.get('direct_requests', 0)}}
    original = capture.get('requested_context', {})
    if (capture.get('hotel_id') != hotel['id'] or capture.get('source_url') != url
            or not isinstance(original, dict) or any(original.get(k) != context.get(k) for k in CONTEXT_FIELDS)):
        result['reason'] = 'capture_context_mismatch'
        return result
    stop = str(capture.get('stop_reason') or '')
    snapshots = [s for s in capture.get('snapshots', []) if isinstance(s, dict)]
    statuses = [capture.get('browser_status')] + [r.get('status') for r in capture.get('responses', []) if isinstance(r, dict)]
    challenge = any(s.get('challenge_detected') or CHALLENGE.search(str(s.get('visible_text', ''))[:3000]) for s in snapshots)
    blocked = next((s for s in statuses if s in STOP_STATUSES), None)
    if blocked or challenge or stop.startswith('access_or_rate_limit_') or stop == 'challenge_detected':
        result.update(status='blocked', reason=f'access_or_rate_limit_{blocked}' if blocked else stop or 'challenge_detected')
        return result
    if stop in {'browser_error', 'browser_action_error'}:
        result.update(status='source_error', reason=stop)
        return result
    if capture.get('browser_status') != 200:
        result.update(status='source_error', reason='source_response_not_successful')
        return result
    # A property name on a search/recommendation page cannot establish identity.
    identities = [s for s in snapshots if s.get('url') == url and
                  any(hotel['name'].casefold() in str(t).casefold() and hotel['city'].casefold() in str(t).casefold()
                      for t in [s.get('title', '')] + s.get('headings', []))]
    if not identities:
        result['reason'] = 'property_identity_not_verified'
        return result
    result['observed_context'] = {'property_id': hotel['sources'][source].get('provider_id'),
                                  'property_identity_verified': True}
    result['reason'] = 'exact_stay_contract_not_discovered'
    # Expedia's default-date teaser is real money for a different/unknown party.
    # Booking has not returned a usable public exact-stay response. Neither is
    # evidence of a quote, inventory shortage, or a zero price for this request.
    return result
