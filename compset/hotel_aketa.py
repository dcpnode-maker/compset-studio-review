"""Hotel Aketa public Google Hotels calendar evidence.

Calendar minimums and Google partner offers are indicative displays, not direct
supplier checkout quotes. Missing prices are always unknown. No credentials,
opaque RPC requests, outbound booking links, or personal reviews are exported.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

# India currently uses UTC+05:30 without daylight saving; this collector only
# requests present/future dates. A fixed offset avoids missing Windows tzdata.
INDIA = timezone(timedelta(hours=5, minutes=30), 'Asia/Kolkata')
HOTEL_NAME = 'Hotel Aketa'
ENTITY = 'ChgI98PmmYGh5fJgGgwvZy8xMmNueDRyN3IQAQ'
SOURCE_URL = 'https://www.google.com/travel/hotels/entity/' + ENTITY
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / 'data' / 'hotels' / 'aketa'
MONTHS = 'January February March April May June July August September October November December'.split()
MONTH_PATTERN = re.compile(r'^(' + '|'.join(MONTHS) + r')(?: (20\d\d))?$')
PRICE = re.compile(r'^₹\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)(K)?$')
TRAVELERS = 'Number of travelers. Current number of travelers is 1.'
PARTNERS = {'Booking.com', 'Agoda', 'MakeMyTrip.com', 'EaseMyTrip.com', HOTEL_NAME,
            'Expedia', 'Hotels.com', 'Goibibo.com', 'Cleartrip.com', 'Trip.com'}


def requested_context(start_date=None, days=30):
    if type(days) is not int or days != 30:
        raise ValueError('Hotel evidence requires exactly 30 consecutive dates')
    start = date.fromisoformat(start_date) if start_date else datetime.now(INDIA).date()
    return {'hotel_name': HOTEL_NAME, 'provider_hotel_id': ENTITY, 'source': 'google_hotels',
            'timezone': 'Asia/Kolkata', 'start_date': start.isoformat(), 'days': days,
            'rooms': 1, 'adults': 1, 'children': 0, 'currency': 'INR', 'stay_nights': 1}


def price_value(label):
    """Never turn Google's abbreviated K labels into exact amounts."""
    match = PRICE.fullmatch(label.strip()) if isinstance(label, str) else None
    if not match:
        return None
    try:
        value = Decimal(match[1].replace(',', ''))
    except InvalidOperation:
        return None
    if not value.is_finite() or value <= 0:
        return None
    abbreviated = bool(match[2])
    return {'amount': None if abbreviated else float(value),
            'approximate_amount': float(value * 1000) if abbreviated else None,
            'display_amount': label.strip(),
            'precision': 'abbreviated' if abbreviated else 'displayed_integer'}


def one_traveler(snapshot):
    controls = snapshot.get('controls', [])
    travelers = [c.get('aria_label') for c in controls
                 if str(c.get('aria_label') or '').startswith('Number of travelers.')]
    return travelers == [TRAVELERS]


def source_identity(snapshot):
    return (snapshot.get('title') == 'Hotel Aketa - Google hotels' and snapshot.get('url') == SOURCE_URL
            and any(re.sub(r'[\s\u200b]', '', c.get('text', '')) == 'CurrencyINR'
                    for c in snapshot.get('controls', [])))


def _base_row(context, checkin, observed_at, kind, source_path):
    return {'hotel_name': HOTEL_NAME, 'provider_hotel_id': ENTITY, 'source': 'google_hotels',
            'checkin': checkin.isoformat(), 'checkout': (checkin + timedelta(days=1)).isoformat(),
            'rooms': None, 'requested_rooms': 1, 'adults': 1, 'children': 0, 'currency': 'INR',
            'room_count_verified': False, 'party_basis': 'one adult selected; Google offer may omit room count',
            'room_id': None, 'room_name': None, 'rate_plan_id': None, 'rate_plan_name': None,
            'amount_type': kind, 'taxes_and_fees': None, 'taxes_included': None,
            'fees_included': None, 'meals': None, 'cancellation': None,
            'availability': 'price_displayed', 'direct_supplier_quote': False,
            'provenance': {'source_url': SOURCE_URL, 'observed_at': observed_at,
                           'source_path': source_path, 'method': 'rendered_public_google_hotels'}}


def calendar_rows(snapshot, context, observed_at):
    """Parse the displayed month/date/price sequence with an explicit year anchor."""
    if not source_identity(snapshot) or not one_traveler(snapshot):
        return []
    text = snapshot.get('visible_text', '')
    if 'Best prices for 1-night stay' not in text or '\nNightly total\n' not in text:
        return []
    controls = snapshot.get('controls', [])
    if not any(c.get('aria_label') == 'Price displayedNightly total' for c in controls):
        return []
    lines = text.splitlines()
    headers = [(i, MONTHS.index(m[1]) + 1, int(m[2]) if m[2] else None)
               for i, line in enumerate(lines) if (m := MONTH_PATTERN.fullmatch(line.strip()))]
    anchor = next((j for j, (_, _, year) in enumerate(headers) if year is not None), None)
    if anchor is None:
        return []
    years = {anchor: headers[anchor][2]}
    for j in range(anchor - 1, -1, -1):
        years[j] = years[j + 1] - (headers[j][1] > headers[j + 1][1])
    for j in range(anchor + 1, len(headers)):
        years[j] = headers[j][2] or years[j - 1] + (headers[j][1] < headers[j - 1][1])
    start = date.fromisoformat(context['start_date'])
    end = start + timedelta(days=context['days'])
    rows = {}
    conflicts = set()
    for j, (index, month, explicit_year) in enumerate(headers):
        year = years[j]
        if explicit_year is not None and explicit_year != year:
            return []
        stop = headers[j + 1][0] if j + 1 < len(headers) else len(lines)
        for n in range(index + 1, stop - 1):
            if not re.fullmatch(r'[0-9]{1,2}', lines[n].strip()):
                continue
            price = price_value(lines[n + 1])
            if price is None:
                continue
            try:
                day = date(year, month, int(lines[n]))
            except ValueError:
                continue
            if not start <= day < end:
                continue
            row = _base_row(context, day, observed_at, 'google_calendar_minimum',
                            f"snapshots.{snapshot.get('stage')}.visible_text.lines[{n}:{n+2}]")
            row.update(price, provider=None, calendar_caption='Best prices for 1-night stay')
            if day in rows and rows[day]['display_amount'] != row['display_amount']:
                conflicts.add(day)
            else:
                rows[day] = row
    return [rows[day] for day in sorted(rows) if day not in conflicts]


def selected_dates(snapshot, context):
    start = date.fromisoformat(context['start_date'])
    result = []
    for label in ('Check-in', 'Check-out'):
        inputs = [e.get('value') for e in snapshot.get('controls', []) if e.get('aria_label') == label]
        if len(inputs) != 1:
            return None
        value = inputs[0]
        found = []
        for offset in range(context['days'] + 1):
            day = start + timedelta(days=offset)
            if value == day.strftime('%a, %b ') + str(day.day):
                found.append(day)
        if len(found) != 1:
            return None
        result.append(found[0])
    return result if result[1] - result[0] == timedelta(days=1) else None


def partner_rows(snapshot, context, observed_at):
    if not source_identity(snapshot) or not one_traveler(snapshot):
        return []
    dates = selected_dates(snapshot, context)
    if dates is None or '\nNightly total\n' not in snapshot.get('visible_text', ''):
        return []
    text = snapshot['visible_text']
    marker = 'Sponsored·Featured options' if 'Sponsored·Featured options' in text else 'All options'
    if marker not in text:
        return []
    lines = [x.strip() for x in text.split(marker, 1)[1].splitlines() if x.strip() not in {'', ','}]
    provider = None
    start = 0
    rows, seen = [], set()
    for index, line in enumerate(lines):
        if line in PARTNERS:
            provider, start = line, index + 1
            continue
        price = price_value(line)
        if index == start and not price and line not in {'Visit site', 'All options'}:
            description = (re.search(r'\bRoom\b', line) or re.match(
                r'^(?:Free\b|Official Site$|[0-9]+ guests?\b|Breakfast\b|Non-refundable\b)', line))
            if not description:
                provider = None  # A newly encountered supplier must not inherit the previous one.
        if not price or provider is None:
            if line in {'Visit site', 'All options'}:
                start = index + 1
            continue
        descriptions = lines[start:index]
        combined = ' · '.join(descriptions)
        guest_counts = {int(m) for m in re.findall(r'\b([0-9]+) guests?\b', combined)}
        if guest_counts != {1}:
            start = index + 1
            continue
        room = next((x for x in descriptions if re.search(r'\bRoom\b', x)
                     and not re.search(r'guest|bed|breakfast', x, re.I)), None)
        key = (provider, room, price['display_amount'], combined)
        if key in seen:
            continue
        seen.add(key)
        row = _base_row(context, dates[0], observed_at, 'google_partner_nightly_total',
                        f"snapshots.{snapshot.get('stage')}.visible_text.partner_lines[{start}:{index+1}]")
        row.update(price, provider=provider, room_name=room, source_description=combined,
                   meals='breakfast' if (any(part.strip().lower() in {'breakfast', 'free breakfast'}
                                             for part in combined.split('·'))
                                           and not re.search(r'breakfast not included|no breakfast|without breakfast|excluding breakfast', combined, re.I)) else None,
                   cancellation=next((x for x in descriptions if 'cancellation' in x.lower()), None))
        rows.append(row)
        start = index + 1
    return rows


def build_report(capture, context=None):
    context = requested_context() if context is None else context
    expected = requested_context(context.get('start_date'), context.get('days'))
    if any(context.get(key) != expected[key] or type(context.get(key)) is not type(expected[key])
           for key in expected):
        raise ValueError('Hotel context must be one adult, zero children, INR, one night, 30 dates')
    observed_at = capture.get('observed_at')
    observed_time = datetime.fromisoformat(observed_at)
    if observed_time.tzinfo is None:
        raise ValueError('Observation time must include its timezone')
    snapshots = capture.get('snapshots', [])
    # Only a source-proven adult decrement with zero children binds the traveler
    # control to an adult. An arbitrary one-traveler label is insufficient.
    party_proofs = [i for i, s in enumerate(snapshots) if source_identity(s) and any(c.get('aria_label') == 'Remove adult' and c.get('disabled') is True
                         for c in s.get('controls', [])) and
                      any(c.get('aria_label') == 'Remove child' and c.get('disabled') is True
                          for c in s.get('controls', []))]
    status_good = type(capture.get('browser_status')) is int and capture['browser_status'] == 200
    calendar, partners = [], []
    calendar_values, calendar_conflicts = {}, set()
    if party_proofs and status_good and not capture.get('stop_reason'):
        for i, s in enumerate(snapshots):
            if not any(index < i for index in party_proofs):
                continue
            parsed = calendar_rows(s, context, observed_at)
            for row in parsed:
                day = row['checkin']
                if day in calendar_values and calendar_values[day]['display_amount'] != row['display_amount']:
                    calendar_conflicts.add(day)
                else:
                    calendar_values[day] = row
            parsed = partner_rows(s, context, observed_at)
            if parsed:
                partners = parsed
    calendar = [calendar_values[day] for day in sorted(calendar_values) if day not in calendar_conflicts]
    rates = calendar + partners
    start = date.fromisoformat(context['start_date'])
    dates = []
    for i in range(context['days']):
        day = start + timedelta(days=i)
        rows = [r for r in rates if r['checkin'] == day.isoformat()]
        dates.append({'checkin': day.isoformat(), 'checkout': (day + timedelta(days=1)).isoformat(),
                      'state': 'indicative_price' if rows else 'unknown',
                      'reason': None if rows else 'source_did_not_return_verified_price', 'rate_count': len(rows)})
    priced = sum(row['state'] == 'indicative_price' for row in dates)
    return {'state': 'complete_indicative_calendar' if len(calendar) == context['days'] else 'partial',
            'requested_context': context,
            'context': {**context, 'rooms': None, 'requested_rooms': 1, 'room_count_verified': False},
            'observed_at': observed_at, 'dates': dates, 'rates': rates,
            'summary': {'date_count': context['days'], 'indicative_dates': priced, 'calendar_price_rows': len(calendar),
                        'partner_offer_dates': len({r['checkin'] for r in partners}),
                        'partner_offer_rows': len(partners), 'quoted_dates': 0, 'unavailable_dates': 0,
                        'unknown_dates': context['days'] - priced, 'rate_rows': len(rates),
                        'abbreviated_calendar_rows': sum(r['precision'] == 'abbreviated' for r in calendar)},
            'stop_reason': capture.get('stop_reason'),
            'limitations': ['Google-displayed indicative prices; direct supplier checkout quotes are not verified.',
                           'Room count, tax inclusion and fee inclusion are not explicitly verified by this page.',
                           'Calendar minimums omit supplier, room, meal and cancellation details.',
                           'Abbreviated K prices have no exact amount; unknown cells never mean unavailable.']}


def export_capture(source: Path, output: Path = DEFAULT_OUTPUT, *, start_date=None):
    capture = json.loads(source.read_text(encoding='utf-8-sig'))
    report = build_report(capture, requested_context(start_date))
    report['source_artifact'] = str(source.resolve())
    output.mkdir(parents=True, exist_ok=True)
    (output / 'latest.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    fields = ['checkin', 'checkout', 'provider', 'room_name', 'amount_type', 'amount', 'approximate_amount',
              'display_amount', 'precision', 'currency', 'requested_rooms', 'rooms', 'adults', 'children',
              'meals', 'cancellation', 'taxes_and_fees', 'taxes_included', 'fees_included', 'source_description',
              'direct_supplier_quote', 'room_count_verified', 'source_url', 'observed_at', 'source_path']
    with (output / 'rates.csv').open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows({**row, **row['provenance']} for row in report['rates'])
    with (output / 'calendar.csv').open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=['checkin', 'checkout', 'state', 'reason', 'rate_count'])
        writer.writeheader()
        writer.writerows(report['dates'])
    return report


# Actual selectors and labels observed in the September 28 canary. The current
# DOM must still expose each control uniquely before it is used.
GOOGLE_SNAPSHOT_JS = r"""() => {const vis=e=>!!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';const selector=e=>{if(e.id)return '#'+CSS.escape(e.id);const ps=[];while(e&&e!==document.body){const ss=Array.from(e.parentElement?.children||[]).filter(n=>n.tagName===e.tagName);ps.unshift(e.tagName.toLowerCase()+':nth-of-type('+(ss.indexOf(e)+1)+')');e=e.parentElement;}return 'body > '+ps.join(' > ');};const raw=document.body.innerText||'';return {title:document.title,visible_text:raw.split('8 top things to know')[0].slice(0,8000),controls:Array.from(document.querySelectorAll('button,input,[role="button"],[role="combobox"],[role="gridcell"],[role="spinbutton"]')).filter(vis).slice(0,900).map(e=>({selector:selector(e),tag:e.tagName,id:e.id,text:(e.innerText||'').slice(0,180),aria_label:e.getAttribute('aria-label'),aria_disabled:e.getAttribute('aria-disabled'),disabled:!!e.disabled,role:e.getAttribute('role'),value:e.value||'',type:e.type||''}))}}"""

def capture_google(*, output: Path = DEFAULT_OUTPUT):
    """One browser/session: select one adult, read the displayed 1-night calendar.

    No endpoint replay, proxy changes or supplier navigation. Four bounded form
    actions expose an entire calendar; source drift ends the read with unknowns.
    """
    from scrapling.fetchers import DynamicSession
    from urllib.parse import urlsplit, urlunsplit
    from .collect import _quiet_scrapling

    capture = {'source': 'google_hotels', 'source_url': SOURCE_URL,
               'observed_at': datetime.now(timezone.utc).isoformat(),
               'stop_reason': None, 'snapshots': [], 'actions': [],
               'browser_navigations': 1, 'direct_replays': 0}

    def snapshot(page, stage):
        item = page.evaluate(GOOGLE_SNAPSHOT_JS)
        parsed = urlsplit(page.url)
        item.update(stage=stage, url=urlunsplit((parsed.scheme, parsed.hostname or '', parsed.path, '', '')))
        capture['snapshots'].append(item)
        if re.search(r'captcha|unusual traffic|verify (?:that )?you(?: are|.re) human|access denied',
                     item.get('visible_text', '')[:2000], re.I):
            capture['stop_reason'] = 'challenge_detected'
        if not source_identity(item):
            capture['stop_reason'] = capture['stop_reason'] or 'hotel_or_currency_not_verified'
        return item

    def setup(page):
        def observed(response):
            parsed = urlsplit(response.url)
            if parsed.hostname == 'www.google.com' and response.request.resource_type in {'document', 'xhr', 'fetch'}:
                if response.status in {401, 403, 429}:
                    capture['stop_reason'] = f'access_or_rate_limit_{response.status}'
        page.on('response', observed)

    def action(page):
        try:
            page.wait_for_timeout(5000)
            current = snapshot(page, 'initial')
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
                control.click(timeout=5000)
                capture['actions'].append({'action': 'click', 'label': selected.get('aria_label') or selected.get('text')})
                page.wait_for_timeout(2500)
                current = snapshot(page, f'action {step+1}')
        except Exception as exc:
            capture['stop_reason'] = 'browser_action_error'
            capture['error_type'] = type(exc).__name__

    with _quiet_scrapling():
        try:
            with DynamicSession(headless=True, executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                                retries=1, timeout=45000, google_search=False,
                                locale='en-IN', timezone_id='Asia/Kolkata') as browser:
                response = browser.fetch(SOURCE_URL, page_setup=setup, page_action=action, network_idle=False, wait=500)
                capture['browser_status'] = response.status
                if response.status in {401, 403, 429}:
                    capture['stop_reason'] = f'access_or_rate_limit_{response.status}'
        except Exception as exc:
            capture['stop_reason'] = 'browser_error'
            capture['error_type'] = type(exc).__name__
    output.mkdir(parents=True, exist_ok=True)
    name = 'google-calendar-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json'
    source = output / name
    source.write_text(json.dumps(capture, indent=2, ensure_ascii=False), encoding='utf-8')
    return source


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--source', type=Path, help='Saved observed Google hotel form capture')
    mode.add_argument('--live', action='store_true', help='One bounded browser calendar read using observed controls')
    parser.add_argument('--start-date', required=True, help='Frozen local window start YYYY-MM-DD')
    args = parser.parse_args()
    if args.live and args.start_date != requested_context()['start_date']:
        parser.error('A live capture must freeze the current hotel-local date')
    source = capture_google() if args.live else args.source
    result = export_capture(source, start_date=args.start_date)
    print(json.dumps({'state': result['state'], 'summary': result['summary']}, indent=2))
