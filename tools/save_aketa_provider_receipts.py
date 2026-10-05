"""Export reviewed public provider receipts; never persist connector/session metadata."""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import io
import json
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

BOOKING = {
    449888: 'osm:node:11740798982', 1150796: 'osm:node:6123644590',
    1797978: 'osm:node:6121571816', 15233569: 'osm:way:331779423',
    7473131: 'official:sterling-marbella-dehradun', 6895522: 'official:spree-kriday-dehradun',
    13253926: 'official:clarks-inn-niranjanpur', 1123641: 'official:hyatt-centric-rajpur-road',
    7986048: 'official:fairfield-dehradun',
}
PROFILE_FIELDS = ('id', 'name', 'rating', 'facilities', 'location')
START, END = date(2026, 9, 30), date(2026, 10, 30)


def public_url(raw):
    parts = urlsplit(raw or '')
    allowed = ('aid', 'checkin', 'checkout', 'no_rooms', 'group_adults', 'group_children',
               'selected_currency', 'brand_id', 'children', 'adults', 'rooms', 'checkInDate', 'checkOutDate')
    query = parse_qs(parts.query)
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                      urlencode([(k, v) for k in allowed for v in query.get(k, [])]), ''))


def export_receipts(log, baseline, root):
    evidence = json.loads(baseline.read_text(encoding='utf-8-sig'))
    candidates = {r['id']: r for r in evidence['candidates']}
    candidates[evidence['subject']['id']] = evidence['subject']
    roster = []
    for research in evidence['researched_properties']:
        candidate = candidates.get(research['id'], {})
        roster.append({'id': research['id'], 'name': candidate.get('title', 'Hotel Aketa'),
                       'source_url': research.get('source_url') or candidate.get('source_url'),
                       'selected_in_saved_compset': research['id'] in evidence['selected_ids']})
    rates, profiles, rejected, direct, attempts = {}, {}, {}, [], []
    for line in log.open(encoding='utf-8'):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = record.get('payload', {})
        item = payload.get('item', {})
        if record.get('type') != 'event_msg' or payload.get('type') != 'item_completed':
            continue
        if item.get('status') != 'completed' or item.get('server') != 'codex_apps':
            continue
        args = item.get('arguments', {})
        result = item.get('result', {})
        content = result.get('structuredContent', {})
        stamp = record['timestamp']
        if item.get('tool') == 'booking_com.accommodations_search_v2':
            arrival, departure = args.get('checkin_date'), args.get('checkout_date')
            try:
                checkin = date.fromisoformat(arrival)
                checkout = date.fromisoformat(departure)
            except (ValueError, TypeError):
                continue
            if not (START <= checkin <= END and checkout - checkin == timedelta(days=1)
                    and args.get('currency') == 'INR' and args.get('number_of_adults') == 1
                    and args.get('number_of_rooms') == 1):
                continue
            attempts.append({'checkin': arrival, 'checkout': departure, 'observed_at': stamp,
                             'source': 'booking.com', 'issues': content.get('issues', [])})
            for hotel in content.get('accommodations', []):
                provider_id = hotel.get('id')
                identity = BOOKING.get(provider_id)
                if not identity or hotel.get('location', {}).get('city_name') != 'Dehradun':
                    rejected[str(provider_id)] = {'provider_id': provider_id, 'name': hotel.get('name'),
                                                  'city': hotel.get('location', {}).get('city_name'),
                                                  'reason': 'unreviewed_or_wrong_city_provider_identity'}
                    continue
                price = hotel.get('price', {})
                url = public_url(hotel.get('url'))
                query = parse_qs(urlsplit(url).query)
                expected = {'checkin': arrival, 'checkout': departure, 'no_rooms': '1',
                            'group_adults': '1', 'selected_currency': 'INR'}
                if any(query.get(k) != [v] for k, v in expected.items()):
                    raise ValueError('Returned provider URL does not match the requested stay')
                if price.get('currency') != 'INR' or not isinstance(price.get('book'), (int, float)) or price['book'] <= 0:
                    continue
                profiles[identity] = {k: hotel.get(k) for k in PROFILE_FIELDS}
                profiles[identity].update(source='booking.com', source_url=url, observed_at=stamp)
                rates[(identity, arrival)] = {
                    'hotel_id': identity, 'provider_id': str(provider_id), 'checkin': arrival, 'checkout': departure,
                    'adults': 1, 'rooms': 1, 'currency': 'INR', 'amount': price['book'],
                    'amount_type': 'booking_display_stay_total', 'source': 'booking.com', 'source_url': url,
                    'observed_at': stamp, 'room_type': None, 'meal_plan': None, 'cancellation': None,
                    'taxes_fees': 'legally_required_display_charges_included_additional_charges_may_apply',
                }
        elif item.get('tool') == 'wyndham_hotels_resorts.search-wyndham-hotels':
            for hotel in content.get('Hotels', []):
                if hotel.get('propertyId') != '51110' or content.get('AdultCount') != 1 or content.get('NumRooms') != 1:
                    continue
                for rate in hotel.get('bestAvailableRates', []):
                    if rate.get('type') != 'cash' or rate.get('currency') != 'INR':
                        continue
                    direct.append({'hotel_id': 'osm:node:6147612906', 'provider_id': '51110',
                                   'checkin': datetime.strptime(content['CheckinDate'], '%m-%d-%Y').date().isoformat(),
                                   'checkout': datetime.strptime(content['CheckoutDate'], '%m-%d-%Y').date().isoformat(),
                                   'adults': 1, 'children': content.get('ChildCount'), 'rooms': 1,
                                   'currency': 'INR', 'amount': rate['pricePerNight'],
                                   'amount_type': 'direct_best_available_per_night', 'source': 'wyndham_direct',
                                   'source_url': public_url(hotel['detail']['uniqueUrl']), 'observed_at': stamp,
                                   'taxes_fees': rate.get('feesLabel'), 'room_type': None,
                                   'meal_plan': None, 'cancellation': None})
        elif item.get('tool') == 'wyndham_hotels_resorts.get-wyndham-hotel-details':
            for hotel in content.get('Hotels', []):
                if hotel.get('propertyId') == '51110':
                    profiles['osm:node:6147612906'] = {'source': 'wyndham_direct', 'observed_at': stamp,
                        'provider_id': '51110', 'detail': hotel.get('detail'),
                        'description': hotel.get('enrich', {}).get('propertyIntro', {})}
    google_file = root / 'data/probes/google-api-final-20260930/api-calendar.json'
    raw_google = json.loads(google_file.read_text(encoding='utf-8-sig')) if google_file.exists() else {}
    google = {k: raw_google.get(k) for k in ('state', 'source_url', 'observed_at', 'requested_context', 'observed_context', 'rates')}
    artifact = {
        'schema_version': 'hotel-provider-receipts.v1', 'assembled_at': datetime.now(timezone.utc).isoformat(),
        'start_date': START.isoformat(), 'detailed_end_date': END.isoformat(),
        'annual_end_date': (START + timedelta(days=364)).isoformat(), 'currency': 'INR',
        'party': {'adults': 1, 'rooms': 1, 'stay_nights': 1}, 'roster': roster,
        'research': evidence['researched_properties'], 'research_observed_at': evidence['compset_observed_at'],
        'profiles': profiles, 'rates': sorted(rates.values(), key=lambda r: (r['checkin'], r['hotel_id'])),
        'direct_rates': direct, 'google_saved': google, 'attempts': attempts,
        'rejected_matches': list(rejected.values()),
        'coverage': {'roster_count': len(roster), 'booking_hotel_count': len(BOOKING),
                     'booking_observations': len(rates), 'dated_hotels': len({r['hotel_id'] for r in [*rates.values(), *direct]}),
                     'annual_complete': False, 'all_ota_lowest_verified': False},
        'limitations': ['Missing dates are unknown, not proven sold out.',
                       'Display offers do not establish comparable room/meal/cancellation plans or the lowest price across all OTAs.',
                       'Historical research attributes retain their original source dates and conflicts.',
                       'Google indicative calendar prices remain separate from provider display offers.',
                       'Collected roster membership does not assign a quality tier or change the saved selected compset.'],
    }
    if len(roster) != 17 or len(rates) < 230:
        raise ValueError('Expected the reviewed 17-property roster and at least 230 accepted Booking receipts')
    output = root / 'data/provider-receipts/20260930'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'aketa-provider-receipts.json').write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding='utf-8')
    body = io.StringIO(newline='')
    columns = ('hotel_id', 'source', 'checkin', 'checkout', 'currency', 'amount', 'amount_type', 'observed_at', 'source_url')
    writer = csv.DictWriter(body, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    writer.writerows([*artifact['rates'], *direct])
    (output / 'aketa-provider-rates.csv').write_text(body.getvalue(), encoding='utf-8')
    return artifact, output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    artifact, output = export_receipts(args.log, args.baseline, args.root)
    print(json.dumps({'output': str(output), **artifact['coverage']}))
