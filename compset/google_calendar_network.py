"""One public Aketa calendar capture with sanitized request-contract discovery."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlsplit, urlunsplit

from .hotel_aketa import (SOURCE_URL, GOOGLE_SNAPSHOT_JS, build_report,
                          export_capture, price_value, requested_context, source_identity)

NETWORK_SNAPSHOT_JS = GOOGLE_SNAPSHOT_JS.replace('[role="spinbutton"]',
                       '[role="spinbutton"],[role="radio"],[role="option"]')


def decode_rpc(text):
    """Read XSSI-prefixed, optionally length-framed JSON without executing it."""
    if text.startswith(")]}'"):
        text = text.split('\n', 1)[-1]
    decoder, cursor, values = json.JSONDecoder(), 0, []
    while cursor < len(text):
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor == len(text):
            break
        try:
            value, end = decoder.raw_decode(text, cursor)
        except ValueError:
            break
        cursor = end
        if isinstance(value, list):
            values.extend(value)
    decoded = []
    for row in values:
        if isinstance(row, list) and len(row) > 2 and row[0] == 'wrb.fr':
            try:
                payload = json.loads(row[2]) if isinstance(row[2], str) else row[2]
            except ValueError:
                payload = None
            decoded.append({'rpc_id': row[1], 'payload': payload})
    return decoded


def shape(value, depth=0):
    if depth >= 5:
        return {'kind': type(value).__name__, 'length': len(value) if isinstance(value, (list, dict, str)) else None}
    if isinstance(value, list):
        return [shape(x, depth + 1) for x in value[:8]] + ([{'omitted': len(value)-8}] if len(value) > 8 else [])
    if isinstance(value, dict):
        return {str(k): shape(v, depth + 1) for k, v in list(value.items())[:12]}
    return type(value).__name__


def safe_leaf(value, depth=0):
    if depth > 6:
        return '<depth>'
    if isinstance(value, list):
        return [safe_leaf(v, depth+1) for v in value[:20]]
    if isinstance(value, dict):
        return {k: safe_leaf(v, depth+1) for k, v in list(value.items())[:20]}
    if isinstance(value, str):
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}|INR|USD|AED|₹[\d,.K]+', value):
            return value
        return f'<string:{len(value)}>'
    return value


def date_structures(value):
    found = []
    def walk(node, path, parent=None, parent_path=None):
        if len(found) >= 12:
            return
        is_date = isinstance(node, list) and len(node) == 3 and all(type(v) is int for v in node)
        if is_date and 2025 <= node[0] <= 2030 and 1 <= node[1] <= 12 and 1 <= node[2] <= 31:
            found.append({'date_path': path, 'date': node, 'parent_path': parent_path,
                          'parent': safe_leaf(parent)})
            return
        if isinstance(node, str) and re.fullmatch(r'202[5-9]-\d{2}-\d{2}', node):
            found.append({'date_path': path, 'date': node, 'parent_path': parent_path,
                          'parent': safe_leaf(parent)})
        elif isinstance(node, list):
            for i, child in enumerate(node):
                walk(child, f'{path}[{i}]', node, path)
        elif isinstance(node, dict):
            for k, child in node.items():
                walk(child, f'{path}.{k}', node, path)
    walk(value, '$')
    return found


def project_calendar(payload):
    """Project only the observed dated price records; never infer unavailability."""
    if not isinstance(payload, list) or len(payload) != 2 or not isinstance(payload[1], list):
        return []
    rows = []
    for item in payload[1]:
        if not isinstance(item, list) or len(item) <= 15 or item[15] != 'INR':
            continue
        money, stay = item[1], item[8]
        if not isinstance(money, list) or len(money) < 5:
            continue
        display = price_value(money[0])
        if not display or display.get('amount') is None or type(money[4]) is not int \
                or money[4] <= 0 or display['amount'] != money[4]:
            continue
        if not isinstance(stay, list) or len(stay) < 2:
            continue
        try:
            if not all(isinstance(d, list) and len(d) == 3 and all(type(n) is int for n in d)
                       for d in stay[:2]):
                continue
            checkin, checkout = date(*stay[0]), date(*stay[1])
            if (checkout-checkin).days != 1:
                continue
        except (ValueError, TypeError):
            continue
        rows.append({'checkin': checkin.isoformat(), 'checkout': checkout.isoformat(),
                     'currency': 'INR', 'observed_money_fields': safe_leaf(money),
                     'amount': money[4], 'display_amount': money[0],
                     'precision': 'displayed_integer', 'amount_type': 'google_calendar_minimum',
                     'taxes_included': None, 'fees_included': None,
                     'direct_supplier_quote': False, 'room_count_verified': False})
    unique, conflicts = {}, set()
    for row in rows:
        day = row['checkin']
        if day in unique and unique[day]['amount'] != row['amount']:
            conflicts.add(day)
        unique[day] = row
    return [row for day, row in sorted(unique.items()) if day not in conflicts]


def compare_calendar(rows, report):
    displayed = {r['checkin']: r['amount'] for r in report['rates']
                 if r['amount_type'] == 'google_calendar_minimum' and r.get('amount') is not None}
    by_date = {r['checkin']: r for r in rows}
    matches = []
    for field in (4, 2):
        for rounding, convert in [('exact', lambda x:x), ('ceil', math.ceil), ('round', round)]:
            count = 0
            for day, price in displayed.items():
                money = by_date.get(day, {}).get('observed_money_fields', [])
                if len(money) > field and type(money[field]) in {int, float} and math.isfinite(money[field]):
                    count += convert(money[field]) == price
            matches.append({'money_index': field, 'display_rounding': rounding, 'matched_dates': count})
    exact_matches = sum(type(by_date.get(day, {}).get('amount')) is int
                        and by_date[day]['amount'] == price
                        for day, price in displayed.items())
    return {'matched_dates': exact_matches, 'displayed_dates': len(displayed),
            'all_displayed_dates_match': bool(displayed) and exact_matches == len(displayed),
            'rounding_diagnostics': matches}


def verified_replay_frame(replay, selected):
    if replay.get('status') != 200 or selected.get('request_contains_known_hotel_entity') is not True:
        return None
    matched = [frame for frame in replay.get('frames', [])
               if frame.get('display_comparison', {}).get('all_displayed_dates_match') is True]
    return matched[0] if len(matched) == 1 else None


def observation_for_index(observations, index):
    matches = [item for item in observations
               if type(item.get('index')) is int and item['index'] == index]
    return matches[0] if len(matches) == 1 else {}


def write_replay(path, replay):
    status = replay.get('status')
    if status in {401, 403, 429}:
        replay['stop_reason'] = f'access_or_rate_limit_{status}'
    Path(path).write_text(json.dumps(replay, indent=2), encoding='utf-8')


def currency_option(snapshot):
    """Choose only a unique currently observed INR/Rupee option."""
    choices = [c for c in snapshot.get('controls', [])
               if re.search(r'\bINR\b', str(c.get('text', ''))+' '+str(c.get('aria_label','')))
               and re.search(r'Indian Rupee', str(c.get('text', ''))+' '+str(c.get('aria_label','')), re.I)]
    return choices[0] if len(choices) == 1 else None


def discover(output, *, hold_seconds=0):
    from scrapling.fetchers import DynamicSession
    from .collect import _quiet_scrapling

    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    total_started = time.monotonic()
    context = requested_context()
    capture = {'source': 'google_hotels', 'source_url': SOURCE_URL,
               'observed_at': datetime.now(timezone.utc).isoformat(), 'stop_reason': None,
               'snapshots': [], 'actions': [], 'browser_navigations': 1, 'direct_replays': 0}
    observed, private = [], []
    phase = {'value': 'navigation'}
    counts = {'browser_requests': 0, 'google_requests': 0, 'rpc_responses': 0, 'replay_requests': 0}

    def snapshot(page, stage, *, verify_currency=True):
        item = page.evaluate(NETWORK_SNAPSHOT_JS)
        parsed = urlsplit(page.url)
        item.update(stage=stage, url=urlunsplit((parsed.scheme, parsed.hostname or '', parsed.path, '', '')))
        capture['snapshots'].append(item)
        if re.search(r'captcha|unusual traffic|verify (?:that )?you(?: are|.re) human|access denied',
                     item.get('visible_text', '')[:2000], re.I):
            capture['stop_reason'] = 'challenge_detected'
        hotel_identity = item.get('title') == 'Hotel Aketa - Google hotels' and item.get('url') == SOURCE_URL
        if not hotel_identity or (verify_currency and not source_identity(item)):
            capture['stop_reason'] = capture['stop_reason'] or 'hotel_or_currency_not_verified'
        return item

    def setup(page):
        def requested(request):
            counts['browser_requests'] += 1
            if urlsplit(request.url).hostname == 'www.google.com':
                counts['google_requests'] += 1
        def response_ready(response):
            parsed = urlsplit(response.url)
            if parsed.hostname != 'www.google.com':
                return
            if response.status in {401, 403, 429}:
                if phase['value'] != 'replay':
                    capture['stop_reason'] = f'access_or_rate_limit_{response.status}'
                return
            if 'batchexecute' not in parsed.path:
                return
            counts['rpc_responses'] += 1
            try:
                text = response.text()
                request = response.request
                fields = parse_qs(request.post_data or '')
                f_req = json.loads(fields.get('f.req', ['null'])[0])
                decoded = decode_rpc(text)
                index = len(private)
                private.append({'url': request.url, 'post_data': request.post_data,
                                'headers': request.all_headers(), 'frames': decoded})
                observed.append({'index': index, 'phase': phase['value'], 'status': response.status,
                    'method': request.method, 'endpoint': parsed.scheme+'://'+parsed.hostname+parsed.path,
                    'request_rpc_ids': parse_qs(parsed.query).get('rpcids', []),
                    'request_contains_known_hotel_entity': SOURCE_URL.rsplit('/',1)[-1] in (request.post_data or '')
                        or '/g/12cnx4r7r' in json.dumps(f_req),
                    'request_shape': shape(f_req), 'body_bytes': len(text.encode()),
                    'body_sha256': hashlib.sha256(text.encode()).hexdigest(),
                    'response_frames': [{'rpc_id': f['rpc_id'], 'shape': shape(f['payload']),
                                         'dated_structures': date_structures(f['payload'])} for f in decoded]})
            except Exception as exc:
                observed.append({'index': None, 'phase': phase['value'], 'status': response.status,
                                 'parse_error': type(exc).__name__})
        page.on('request', requested)
        page.on('response', response_ready)

    def write_discovery():
        report = build_report(capture, context)
        for item in observed:
            if item.get('index') is not None:
                frames = private[item['index']]['frames']
                for source, saved in zip(frames, item['response_frames']):
                    rows = project_calendar(source['payload'])
                    if rows:
                        saved['calendar_rows'] = rows
                        saved['display_comparison'] = compare_calendar(rows, report)
        evidence = {'observed_at': capture['observed_at'], 'stop_reason': capture['stop_reason'],
            'summary': report['summary'], 'requests': counts, 'rpc_observations': observed}
        (output / 'discovery.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        return report

    def action(page):
        try:
            page.wait_for_timeout(5000)
            current = snapshot(page, 'initial', verify_currency=False)
            if not capture['stop_reason'] and not source_identity(current):
                controls = [c for c in current.get('controls', [])
                            if re.fullmatch(r'Currency[A-Z]{3}', re.sub(r'[\s\u200b]', '', c.get('text', '')))]
                if len(controls) != 1:
                    capture['stop_reason'] = 'currency_control_not_unique'
                    return
                control = page.locator(controls[0]['selector'])
                if control.count() != 1 or not control.is_visible() or not control.is_enabled():
                    capture['stop_reason'] = 'currency_control_not_actionable'
                    return
                control.click(timeout=5000)
                page.wait_for_timeout(500)
                current = snapshot(page, 'currency_menu', verify_currency=False)
                choice = currency_option(current)
                if choice is None or capture['stop_reason']:
                    capture['stop_reason'] = capture['stop_reason'] or 'currency_option_not_unique'
                    return
                control = page.locator(choice['selector'])
                if control.count() != 1 or not control.is_visible() or not control.is_enabled():
                    capture['stop_reason'] = 'currency_option_not_actionable'
                    return
                control.click(timeout=5000)
                capture['actions'].append({'action':'click','label':'observed INR Indian Rupee option'})
                page.wait_for_timeout(1000)
                current = snapshot(page, 'currency_selected', verify_currency=False)
                if not source_identity(current):
                    confirm = [c for c in current.get('controls',[]) if c.get('text') in {'Done','Apply','Save'}]
                    if len(confirm)==1:
                        control=page.locator(confirm[0]['selector'])
                        if control.count()==1 and control.is_visible() and control.is_enabled():
                            control.click(timeout=5000)
                            page.wait_for_timeout(1000)
                current=snapshot(page,'currency_verified')
            for step in range(4):
                if capture['stop_reason']:
                    return
                controls = current.get('controls', [])
                if step == 0:
                    choices = [c for c in controls if c.get('aria_label') ==
                        'Number of travelers. Current number of travelers is 2.']
                elif step == 1:
                    choices = [c for c in controls if c.get('aria_label') == 'Remove adult']
                elif step == 2:
                    choices = [c for c in controls if c.get('text') == 'Done']
                else:
                    choices = [c for c in controls if c.get('aria_label') == 'Check-in']
                if len(choices) != 1:
                    capture['stop_reason'] = f'observed_control_not_unique_{step}'
                    return
                selected = choices[0]
                control = page.locator(selected['selector'])
                if control.count() != 1 or not control.is_visible() or not control.is_enabled():
                    capture['stop_reason'] = 'observed_control_not_actionable'
                    return
                phase['value'] = f'action_{step+1}'
                control.click(timeout=5000)
                capture['actions'].append({'action': 'click', 'label': selected.get('aria_label') or selected.get('text')})
                page.wait_for_timeout(2500)
                current = snapshot(page, f'action {step+1}')
            capture['browser_status'] = 200
            capture['browser_calendar_seconds'] = round(time.monotonic()-total_started, 3)
            report = write_discovery()
            # Optional network verification must not erase an already successful calendar.
            (output/'rendered-before-replay.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps({'discovery_ready': str(output/'discovery.json'),
                              'summary': report['summary'], 'rpc_count': len(observed)}), flush=True)
            candidates = [(item['index'], n) for item in observed if item.get('phase') == 'action_4'
                          and item.get('request_contains_known_hotel_entity') is True
                          for n, frame in enumerate(item.get('response_frames', []))
                          if frame.get('display_comparison', {}).get('all_displayed_dates_match')]
            if len(candidates) == 1:
                (output/'replay-command.json').write_text(json.dumps(
                    {'action':'replay', 'index': candidates[0][0], 'frame': candidates[0][1]}), encoding='utf-8')
                hold_seconds_effective = max(hold_seconds, 1)
            else:
                hold_seconds_effective = hold_seconds
            deadline = time.monotonic() + hold_seconds_effective
            while hold_seconds_effective and not capture['stop_reason'] and time.monotonic() < deadline:
                command = output / 'replay-command.json'
                if command.exists():
                    value = json.loads(command.read_text(encoding='utf-8'))
                    if value.get('action') == 'finish':
                        break
                    if value.get('action') != 'replay' or type(value.get('index')) is not int:
                        raise ValueError('invalid replay command')
                    template = private[value['index']]
                    headers = {k: v for k, v in template['headers'].items()
                               if not k.startswith(':') and not k.lower().startswith('sec-')
                               and k.lower() not in {'cookie', 'host', 'content-length', 'connection',
                                   'accept-encoding', 'origin', 'referer', 'user-agent'}}
                    # Same browser context, identical observed URL and POST body, once only.
                    counts['replay_requests'] = 1
                    replay_started = time.monotonic()
                    phase['value'] = 'replay'
                    try:
                        result = page.evaluate('''async ({url, body, headers}) => {
                          const controller = new AbortController();
                          const timer = setTimeout(() => controller.abort(), 20000);
                          try { const response = await fetch(url, {method:'POST', body, headers,
                            credentials:'same-origin', redirect:'error', signal:controller.signal});
                            return {status:response.status, text:await response.text()};
                          } finally {clearTimeout(timer);}
                        }''', {'url': template['url'], 'body': template['post_data'], 'headers': headers})
                    except Exception as exc:
                        message = re.sub(r'https?://[^\s]+', '<url>', str(exc).splitlines()[0])[:240]
                        (output/'replay.json').write_text(json.dumps({'index':value['index'],
                            'status':None, 'error_type':type(exc).__name__, 'error':message,
                            'elapsed_seconds':round(time.monotonic()-replay_started,3)}), encoding='utf-8')
                        break
                    frames = decode_rpc(result['text']) if result['status'] == 200 else []
                    replay = {'index': value['index'], 'status': result['status'],
                        'elapsed_seconds': round(time.monotonic()-replay_started, 3),
                        'frames': [{'rpc_id': f['rpc_id'], 'shape': shape(f['payload']),
                                    'dated_structures': date_structures(f['payload']),
                                    'calendar_rows':project_calendar(f['payload']),
                                    'display_comparison':compare_calendar(project_calendar(f['payload']),report)}
                                   for f in frames]}
                    # Preserve only a reviewed date/price subtree, chosen from sanitized discovery.
                    if 'payload_path' in value and frames:
                        path = value['payload_path']
                        if not isinstance(path, list) or not all(type(x) is int and x >= 0 for x in path):
                            raise ValueError('payload_path must contain array indexes')
                        selected_payload = frames[value.get('frame', 0)]['payload']
                        for index in path:
                            selected_payload = selected_payload[index]
                        replay['selected_payload'] = safe_leaf(selected_payload)
                    write_replay(output/'replay.json', replay)
                    selected = observation_for_index(observed, value['index'])
                    frame = verified_replay_frame(replay, selected)
                    if frame is not None:
                        dates = {r['checkin'] for r in report['dates']}
                        rates = [r for r in frame['calendar_rows'] if r['checkin'] in dates]
                        api_report = {'state':'complete_indicative_calendar' if len(rates)==context['days'] else 'partial',
                            'method':'observed_same_session_google_calendar_rpc', 'rpc_id':frame['rpc_id'],
                            'source_url':SOURCE_URL, 'hotel_name':'Hotel Aketa',
                            'observed_at':datetime.now(timezone.utc).isoformat(),
                            'requested_context':context, 'observed_context':report['context'],
                            'rates':rates, 'summary':{'requested_dates':context['days'], 'api_price_rows':len(rates),
                                'response_date_rows':len(frame['calendar_rows']),
                                'matching_displayed_dates':frame['display_comparison']['matched_dates'],
                                'unknown_dates':context['days']-len(rates), 'unavailable_dates':0},
                            'provenance':{'request_index':value['index'], 'same_observed_url_and_body':True,
                                'request_contains_known_hotel_entity':selected['request_contains_known_hotel_entity'],
                                'identity_basis':'known hotel page identity, observed one-adult form, identical request, full date-price display comparison',
                                'rpc_fixture':str(output/'replay.json'), 'browser_capture':str(output/'calendar-capture.json')},
                            'timings':{'browser_calendar_seconds':capture['browser_calendar_seconds'],
                                       'same_session_replay_seconds':replay['elapsed_seconds']},
                            'limitations':['Indicative displayed calendar minimums, not final supplier checkout quotes.',
                                'Room count, taxes, fees, supplier and cancellation inclusions remain unverified.',
                                'Current Aketa one-adult session only; no multi-property batch or long-lived token claim.']}
                        (output/'api-calendar.json').write_text(json.dumps(api_report,indent=2), encoding='utf-8')
                    capture['direct_replays'] = 1
                    print(json.dumps({'replay_status': result['status'], 'artifact': str(output/'replay.json')}), flush=True)
                    break
                page.wait_for_timeout(500)
        except Exception as exc:
            capture['stop_reason'] = capture['stop_reason'] or 'browser_action_error'
            capture['error_type'] = type(exc).__name__

    with _quiet_scrapling():
        try:
            with DynamicSession(headless=True, executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                                retries=1, timeout=45000, google_search=False,
                                locale='en-IN', timezone_id='Asia/Kolkata') as browser:
                response = browser.fetch(SOURCE_URL, page_setup=setup, page_action=action, network_idle=False, wait=500)
                capture['browser_status'] = response.status
        except Exception as exc:
            capture['stop_reason'] = capture['stop_reason'] or 'browser_error'
            capture['error_type'] = type(exc).__name__
    source = output/'calendar-capture.json'
    source.write_text(json.dumps(capture, indent=2, ensure_ascii=False), encoding='utf-8')
    report = export_capture(source, output, start_date=context['start_date'])
    write_discovery()
    private.clear()
    return {'state': report['state'], 'summary': report['summary'], 'counts': counts,
            'stop_reason': capture['stop_reason'], 'total_seconds':round(time.monotonic()-total_started,3),
            'api_calendar_created':(output/'api-calendar.json').exists(), 'output': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--hold-seconds', type=int, default=0)
    args = parser.parse_args()
    if not 0 <= args.hold_seconds <= 240:
        parser.error('--hold-seconds must be 0..240')
    print(json.dumps(discover(args.output, hold_seconds=args.hold_seconds), indent=2), flush=True)
