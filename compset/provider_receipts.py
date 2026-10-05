"""Read-only projection of reviewed Dehradun provider receipts."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlsplit, urlunsplit

INPUT_SCHEMA = 'hotel-provider-receipts.v1'
SCHEMA = 'hotel-provider-receipts-projection.v1'
RECEIPT_PATH = Path('provider-receipts/20260930/aketa-provider-receipts.json')
DAYS = 365
AKETA = 'osm:node:11740798982'
RAMADA = 'osm:node:6147612906'
GOOGLE_ID = 'ChgI98PmmYGh5fJgGgwvZy8xMmNueDRyN3IQAQ'
GOOGLE_URL = 'https://www.google.com/travel/hotels/entity/' + GOOGLE_ID
WYNDHAM_PATH = '/ramada/dehradun-india/ramada-dehradun-chakrata-road/rooms-rates'

# Reviewed bindings, deliberately independent of names supplied by rate rows.
BOOKING = {
    AKETA: ('449888', '/hotel/in/aketa.html',
            'Hotel Aketa Rajpur Road Dehradun, Dehradun'),
    'osm:node:6123644590': ('1150796', '/hotel/in/lemon-tree-dehradun.html',
                           'Lemon Tree Hotel, Dehradun'),
    'osm:node:6121571816': ('1797978', '/hotel/in/central-palace.html',
                           'Hotel Central Palace'),
    'osm:way:331779423': (
        '15233569', '/hotel/in/welcomhotel-by-itc-hotels-madhuban-dehradun.html',
        'Welcomhotel By ITC Hotels, Madhuban Dehradun'),
    'official:fairfield-dehradun': (
        '7986048', '/hotel/in/fairfield-by-marriott-dehradun.html',
        'Fairfield by Marriott Dehradun'),
    'official:hyatt-centric-rajpur-road': (
        '1123641', '/hotel/in/hyatt-centric-rajpur-road-dehradun.html',
        'Hyatt Centric Rajpur Road Dehradun'),
    'official:sterling-marbella-dehradun': (
        '7473131', '/hotel/in/marbella-dehradun-dehradun.html',
        'Sterling Marbella Dehradun'),
    'official:spree-kriday-dehradun': (
        '6895522', '/hotel/in/spree-kriday.html',
        'Spree Hotel Kriday Rajpur Road Dehradun'),
    'official:clarks-inn-niranjanpur': (
        '13253926', '/hotel/in/clarks-inn-dehradun.html', 'Clarks Inn Dehradun'),
}
ROSTER = {
    AKETA: ('Hotel Aketa', GOOGLE_URL),
    'osm:node:6123644590': (
        'Lemon Tree Hotel, Dehradun',
        'https://www.lemontreehotels.com/lemon-tree-hotel/dehradun/hotel-dehradun'),
    RAMADA: (
        'Ramada by Wyndham Dehradun Chakrata Road',
        'https://www.wyndhamhotels.com/ramada/dehradun-india/ramada-dehradun-chakrata-road/overview'),
    'osm:node:6066360185': ('Hotel The Onix', 'https://www.hoteltheonix.com/'),
    'osm:node:10602916733': (
        'Zip by Spree Hotels Grand Legacy Prime',
        'https://www.spreehotels.com/zip-by-spree-hotels-grand-legacy-prime/'),
    'osm:node:4922436521': (
        'Hotel Park View Premium', 'https://hotelparkviewpremium.in/about/'),
    'osm:node:6121571816': (
        'Hotel Central Palace', 'https://www.thehotelcentralpalace.com/'),
    'osm:way:331779423': (
        'Welcomhotel by ITC Hotels, Madhuban Dehradun',
        'https://www.itchotels.com/in/en/welcomhotelmadhuban-dehradun'),
    'osm:node:13520091277': (
        'Six Senses Vana',
        'https://www.sixsenses.com/en/hotels-resorts/asia-the-pacific/india/vana/programs/'),
    'osm:node:11909374517': (
        'Stairway To Heaven', 'https://overpass-api.de/api/interpreter'),
    'official:sarovar-portico-dehradun': (
        'Sarovar Portico Dehradun',
        'https://www.sarovarhotels.com/sarovar-portico-dehradun/facilities/facilities.html'),
    'official:sterling-marbella-dehradun': (
        'Sterling Marbella Dehradun',
        'https://www.sterlingholidays.com/resorts-hotels/marbella-dehradun'),
    'official:manor-house-dehradun': (
        'The Manor House, Dehradun', 'https://www.themanorhousehotels.com/'),
    'official:spree-kriday-dehradun': (
        'Spree Hotel Kriday', 'https://www.spreehotels.com/spree-hotel-kriday/'),
    'official:clarks-inn-niranjanpur': (
        'Clarks Inn Dehradun — Niranjanpur',
        'https://www.theclarkshotels.com/clarks-inn/clarks-inn-dehradun/hotel-overview'),
    'official:hyatt-centric-rajpur-road': (
        'Hyatt Centric Rajpur Road Dehradun',
        'https://www.hyattdiningclub.com/hotel/hoteldetail/en/hyatt-centric-rajpur-road-dehradun'),
    'official:fairfield-dehradun': (
        'Fairfield by Marriott Dehradun',
        'https://www.marriott.com/en-us/hotels/dedfi-fairfield-dehradun/overview/'),
}
SERIES = {
    'booking_display': {
        'source': 'booking.com', 'label': 'Booking.com displayed stay total',
        'semantics': 'provider_display',
        'amount_type': 'booking_display_stay_total'},
    'google_indicative': {
        'source': 'google_hotels', 'label': 'Google indicative calendar',
        'semantics': 'indicative_calendar',
        'amount_type': 'google_calendar_minimum'},
    'wyndham_direct': {
        'source': 'wyndham_direct', 'label': 'Wyndham direct per-night quote',
        'semantics': 'direct_quote',
        'amount_type': 'direct_best_available_per_night'},
}
BOOKING_QUERY = {
    'aid', 'checkin', 'checkout', 'no_rooms', 'group_adults',
    'group_children', 'selected_currency',
}


def _dict(value):
    return value if isinstance(value, dict) else {}


def _text(value):
    if not isinstance(value, str) or not value or len(value) > 500:
        return None
    return value if not re.search(r'[\x00-\x1f<>]', value) else None


def _equal(a, b):
    return type(a) is type(b) and a == b


def _day(value):
    try:
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError()
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError('invalid_date') from None


def _stamp(value):
    try:
        if not isinstance(value, str):
            raise ValueError()
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError()
        return parsed.isoformat()
    except (ValueError, TypeError):
        raise ValueError('invalid_observed_at') from None


def _provider(value):
    if type(value) not in (str, int) or not re.fullmatch(r'[0-9]+', str(value)):
        raise ValueError('provider_identity_mismatch')
    return str(value)


def _amount(value):
    try:
        if type(value) not in (str, int, float) or len(str(value)) > 100:
            raise ValueError()
        amount = Decimal(str(value))
        if not amount.is_finite() or amount <= 0:
            raise ValueError()
        return format(amount, 'f')
    except (ValueError, InvalidOperation):
        raise ValueError('invalid_amount') from None


def _url(value, expected, allowed=()):
    """Validate exact public property identity; return a query-free URL."""
    try:
        if not isinstance(value, str) or len(value) > 4096 or re.search(r'[\s\\]', value):
            raise ValueError()
        actual, target = urlsplit(value), urlsplit(expected)
        if (actual.scheme != 'https' or actual.hostname != target.hostname
                or actual.path != target.path or actual.username or actual.password
                or actual.port is not None or actual.fragment):
            raise ValueError()
        pairs = parse_qsl(actual.query, keep_blank_values=True, strict_parsing=True)
        query = dict(pairs)
        if len(query) != len(pairs) or not set(query) <= set(allowed):
            raise ValueError()
        return urlunsplit(('https', actual.hostname, actual.path, '', '')), query
    except (ValueError, TypeError):
        raise ValueError('invalid_source_url') from None


def _profile(hotel_id, raw):
    if hotel_id in BOOKING:
        provider, path, name = BOOKING[hotel_id]
        location = _dict(raw.get('location'))
        if (_provider(raw.get('id')) != provider or raw.get('source') != 'booking.com'
                or str(raw.get('name', '')).casefold() != name.casefold()):
            raise ValueError('provider_identity_mismatch')
        if (str(location.get('city_name', '')).casefold() != 'dehradun'
                or str(location.get('country_code', '')).lower() != 'in'):
            raise ValueError('provider_city_mismatch')
        url, _ = _url(raw.get('source_url'), 'https://www.booking.com' + path,
                      BOOKING_QUERY)
        return {
            'source': 'booking.com', 'provider_id': provider, 'name': name,
            'city': 'Dehradun', 'source_url': url,
            'observed_at': _stamp(raw.get('observed_at')),
        }
    if hotel_id == RAMADA:
        detail = _dict(raw.get('detail'))
        if (raw.get('source') != 'wyndham_direct'
                or _provider(raw.get('provider_id')) != '51110'
                or detail.get('name') != ROSTER[RAMADA][0]
                or detail.get('uri') != 'uttarakhand/dehradun/ramada-by-wyndham-dehradun-chakrata-road'
                or detail.get('hotelName', detail.get('name')) != detail.get('name')):
            raise ValueError('provider_identity_mismatch')
        if (detail.get('city') != 'Dehradun'
                or detail.get('hotelCity', 'Dehradun') != 'Dehradun'
                or detail.get('countryCode') != 'IN'):
            raise ValueError('provider_city_mismatch')
        return {
            'source': 'wyndham_direct', 'provider_id': '51110',
            'name': detail['name'], 'city': 'Dehradun',
            'observed_at': _stamp(raw.get('observed_at')),
        }
    raise ValueError('unreviewed_provider_identity')


def _offer(row, series, context, start, end, profiles):
    spec = SERIES[series]
    hotel_id = row.get('hotel_id')
    if row.get('source') != spec['source'] or row.get('amount_type') != spec['amount_type']:
        raise ValueError('observation_identity_mismatch')
    if 'city' in row and row['city'] != 'Dehradun':
        raise ValueError('provider_city_mismatch')
    arrival, departure = _day(row.get('checkin')), _day(row.get('checkout'))
    if departure - arrival != timedelta(days=1) or not start <= arrival <= end:
        raise ValueError('stay_date_mismatch')
    if row.get('currency') != context['currency']:
        raise ValueError('currency_mismatch')
    for key in ('adults', 'rooms'):
        if not _equal(row.get(key), context[key]):
            raise ValueError('party_mismatch')
    children = row.get('children')
    if children is not None and (type(children) is not int or children < 0):
        raise ValueError('party_mismatch')
    if context['children'] is not None and not _equal(children, context['children']):
        raise ValueError('party_mismatch')
    actual = _dict(row.get('observed_context'))
    for key in ('hotel_id', 'checkin', 'checkout', 'adults', 'rooms', 'children', 'currency'):
        if key in actual and not _equal(actual[key], row.get(key)):
            raise ValueError('observed_context_mismatch')

    if series == 'booking_display':
        if hotel_id not in BOOKING or hotel_id not in profiles:
            raise ValueError('provider_profile_not_verified')
        provider, path, _ = BOOKING[hotel_id]
        if _provider(row.get('provider_id')) != provider:
            raise ValueError('provider_identity_mismatch')
        url, query = _url(row.get('source_url'), 'https://www.booking.com' + path,
                          BOOKING_QUERY)
        expected = {
            'checkin': str(arrival), 'checkout': str(departure),
            'no_rooms': str(context['rooms']), 'group_adults': str(context['adults']),
            'selected_currency': context['currency'],
        }
        if ('group_children' in query or children is not None):
            expected['group_children'] = str(children)
    elif series == 'wyndham_direct':
        if hotel_id != RAMADA or hotel_id not in profiles or children is None:
            raise ValueError('provider_profile_not_verified')
        provider = '51110'
        if _provider(row.get('provider_id')) != provider:
            raise ValueError('provider_identity_mismatch')
        url, query = _url(
            row.get('source_url'), 'https://www.wyndhamhotels.com' + WYNDHAM_PATH,
            {'brand_id', 'children', 'adults', 'rooms', 'checkInDate', 'checkOutDate'})
        expected = {
            'brand_id': 'RA', 'children': str(children),
            'adults': str(context['adults']), 'rooms': str(context['rooms']),
            'checkInDate': arrival.strftime('%m/%d/%Y'),
            'checkOutDate': departure.strftime('%m/%d/%Y'),
        }
    else:
        if hotel_id != AKETA:
            raise ValueError('provider_identity_mismatch')
        provider = GOOGLE_ID
        url, query = _url(row.get('source_url'), GOOGLE_URL)
        expected = {}
        if (row.get('precision') not in ('displayed_integer', 'displayed_decimal')
                or row.get('direct_supplier_quote') is not False
                or row.get('room_count_verified') is not False):
            raise ValueError('google_semantics_mismatch')
    if any(query.get(key) != value for key, value in expected.items()):
        raise ValueError('url_context_mismatch')

    google, direct = series == 'google_indicative', series == 'wyndham_direct'
    result = {
        'hotel_id': hotel_id, 'provider_id': provider, 'series_id': series,
        **spec, 'checkin': str(arrival), 'checkout': str(departure),
        'stay_nights': 1, 'adults': context['adults'],
        'rooms': None if google else context['rooms'], 'requested_rooms': context['rooms'],
        'children': children, 'currency': context['currency'],
        'amount': _amount(row.get('amount')),
        'state': 'quoted' if direct else 'indicative' if google else 'displayed',
        'precision': row['precision'] if google else 'source_exact' if direct else 'provider_display',
        'direct_supplier_quote': direct, 'stay_context_verified': True,
        'party_context_verified': children is not None and not google,
        'room_count_verified': not google, 'source_url': url,
        'observed_at': _stamp(row.get('observed_at')),
        'like_for_like_verified': False, 'all_ota_lowest_verified': False,
    }
    for key in ('room_type', 'meal_plan', 'cancellation', 'taxes_fees'):
        result[key] = _text(row.get(key))
    for key in ('taxes_included', 'fees_included'):
        result[key] = row.get(key) if type(row.get(key)) is bool else None
    if google:
        result['display_amount'] = _text(row.get('display_amount'))
    return result


def _google(saved, context, start, end):
    requested, actual = _dict(saved.get('requested_context')), _dict(saved.get('observed_context'))
    expected = {
        'hotel_name': ROSTER[AKETA][0], 'provider_hotel_id': GOOGLE_ID,
        'source': 'google_hotels', 'currency': context['currency'],
        'adults': context['adults'], 'stay_nights': 1, 'timezone': 'Asia/Kolkata',
    }
    if any(not _equal(requested.get(k), v) or not _equal(actual.get(k), v)
           for k, v in expected.items()):
        raise ValueError('google_context_mismatch')
    children = requested.get('children')
    if (not _equal(requested.get('rooms'), context['rooms'])
            or actual.get('rooms') is not None
            or not _equal(actual.get('requested_rooms'), context['rooms'])
            or actual.get('room_count_verified') is not False
            or type(children) is not int or children < 0
            or not _equal(actual.get('children'), children)
            or context['children'] is not None and children != context['children']):
        raise ValueError('google_context_mismatch')
    first, days = _day(requested.get('start_date')), requested.get('days')
    if (type(days) is not int or not 1 <= days <= DAYS
            or first < start or first + timedelta(days=days - 1) > end
            or actual.get('start_date') != requested['start_date']
            or not _equal(actual.get('days'), days)):
        raise ValueError('google_date_mismatch')
    _url(saved.get('source_url'), GOOGLE_URL)
    if not isinstance(saved.get('rates'), list):
        raise ValueError('invalid_google_rows')
    return first, first + timedelta(days=days - 1), children


def _coverage(planned, observed):
    return {
        'planned_cells': planned, 'observed_cells': observed,
        'unknown_cells': planned - observed, 'annual_complete': observed == planned,
    }


def build_provider_receipts(receipt):
    """Pure public projection. Bad envelopes raise; bad evidence is quarantined."""
    if not isinstance(receipt, dict) or receipt.get('schema_version') != INPUT_SCHEMA:
        raise ValueError('Expected hotel-provider-receipts.v1')
    start = _day(receipt.get('start_date'))
    end = start + timedelta(days=DAYS - 1)
    if (_day(receipt.get('annual_end_date')) != end
            or not start <= _day(receipt.get('detailed_end_date')) <= end):
        raise ValueError('receipt_window_mismatch')
    assembled_at = _stamp(receipt.get('assembled_at'))
    party = _dict(receipt.get('party'))
    if (receipt.get('currency') != 'INR'
            or any(type(party.get(k)) is not int or party[k] < 1 for k in ('adults', 'rooms'))
            or not _equal(party.get('stay_nights'), 1)
            or party.get('children') is not None
            and (type(party['children']) is not int or party['children'] < 0)):
        raise ValueError('receipt_context_mismatch')
    context = {
        'currency': 'INR', 'adults': party['adults'], 'rooms': party['rooms'],
        'children': party.get('children'), 'stay_nights': 1,
    }
    if (not isinstance(receipt.get('roster'), list) or not receipt['roster']
            or not isinstance(receipt.get('profiles'), dict)):
        raise ValueError('receipt_roster_mismatch')
    hotels, profiles, rejected = {}, {}, []

    def reject(section, index, hotel_id, reason):
        rejected.append({
            'section': section, 'index': index,
            'hotel_id': hotel_id if isinstance(hotel_id, str) and hotel_id in ROSTER else None, 'reason': reason,
        })

    for raw in receipt['roster']:
        row = _dict(raw)
        hotel_id = row.get('id')
        if not isinstance(hotel_id, str) or hotel_id not in ROSTER or hotel_id in hotels:
            raise ValueError('duplicate_or_unreviewed_roster_id')
        name, expected_url = ROSTER[hotel_id]
        if row.get('name') != name or ('city' in row and row['city'] != 'Dehradun'):
            raise ValueError('roster_identity_mismatch')
        url, _ = _url(row.get('source_url'), expected_url)
        hotels[hotel_id] = {
            'id': hotel_id, 'name': name, 'source_url': url, 'profile': None,
            'selected_in_saved_compset': row.get('selected_in_saved_compset') is True,
        }
    for hotel_id, raw in receipt['profiles'].items():
        try:
            if hotel_id not in hotels:
                raise ValueError('hotel_not_in_roster')
            profiles[hotel_id] = _profile(hotel_id, _dict(raw))
            hotels[hotel_id]['profile'] = profiles[hotel_id]
        except ValueError as exc:
            reject('profiles', None, hotel_id, str(exc))

    offers, fingerprints = [], set()
    accepted, duplicates = 0, 0

    def put(raw, series, section, index, first=start, last=end):
        nonlocal accepted, duplicates
        row = _dict(raw)
        hotel_id = row.get('hotel_id')
        try:
            if not isinstance(hotel_id, str) or hotel_id not in hotels:
                raise ValueError('hotel_not_in_roster')
            offer = _offer(row, series, context, first, last, profiles)
            accepted += 1
            fingerprint = json.dumps(offer, sort_keys=True, ensure_ascii=True)
            if fingerprint in fingerprints:
                duplicates += 1
            else:
                fingerprints.add(fingerprint)
                offers.append(offer)
        except ValueError as exc:
            reject(section, index, hotel_id, str(exc))

    for section, series in (('rates', 'booking_display'), ('direct_rates', 'wyndham_direct')):
        rows = receipt.get(section, [])
        if not isinstance(rows, list):
            raise ValueError('receipt_rates_mismatch')
        for index, row in enumerate(rows):
            put(row, series, section, index)

    saved = _dict(receipt.get('google_saved'))
    if saved:
        try:
            first, last, children = _google(saved, context, start, end)
            expected = {
                'hotel_id': AKETA, 'source': 'google_hotels', 'provider_id': GOOGLE_ID,
                'adults': context['adults'], 'children': children,
            }
            for index, raw in enumerate(saved['rates']):
                row = _dict(raw)
                # Reject contradictions before adding context absent from old rows.
                try:
                    if (any(k in row and not _equal(row[k], v) for k, v in expected.items())
                            or 'rooms' in row and row['rooms'] is not None
                            or 'provider_hotel_id' in row and row['provider_hotel_id'] != GOOGLE_ID):
                        raise ValueError('google_context_mismatch')
                    if 'source_url' in row:
                        _url(row['source_url'], GOOGLE_URL)
                    if ('observed_at' in row
                            and datetime.fromisoformat(_stamp(row['observed_at']))
                            != datetime.fromisoformat(_stamp(saved.get('observed_at')))):
                        raise ValueError('google_observed_at_mismatch')
                except ValueError as exc:
                    reject('google_saved', index, AKETA, str(exc))
                    continue
                put({
                    **row, **expected, 'rooms': context['rooms'],
                    'source_url': saved.get('source_url'),
                    'observed_at': saved.get('observed_at'),
                }, 'google_indicative', 'google_saved', index, first, last)
        except ValueError as exc:
            reject('google_saved', None, AKETA, str(exc))

    buckets = defaultdict(list)
    for offer in sorted(offers, key=lambda r: (
            r['hotel_id'], r['checkin'], r['series_id'], r['observed_at'], r['amount'])):
        buckets[offer['hotel_id'], offer['checkin']].append(offer)
    dates = [str(start + timedelta(days=i)) for i in range(DAYS)]
    series_counts = dict.fromkeys(SERIES, 0)
    observed = 0
    for hotel_id, hotel in hotels.items():
        calendar = [{
            'checkin': day, 'checkout': str(_day(day) + timedelta(days=1)),
            'state': 'observed' if buckets[hotel_id, day] else 'unknown',
            'offers': buckets[hotel_id, day],
        } for day in dates]
        hotel['calendar'] = calendar
        count = sum(cell['state'] == 'observed' for cell in calendar)
        observed += count
        hotel['coverage'] = _coverage(DAYS, count)
        hotel['series'] = []
        for series, spec in SERIES.items():
            count = sum(any(o['series_id'] == series for o in cell['offers'])
                        for cell in calendar)
            series_counts[series] += count
            hotel['series'].append({
                'id': series, **spec, 'coverage': _coverage(DAYS, count),
            })
    planned = len(hotels) * DAYS
    revision = hashlib.sha256(
        json.dumps(receipt, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    return {
        'schema_version': SCHEMA, 'revision': revision, 'assembled_at': assembled_at,
        'context': {
            **context, 'start_date': str(start), 'end_date': str(end),
            'days': DAYS, 'timezone': 'Asia/Kolkata', 'city': 'Dehradun',
        },
        'dates': dates, 'hotels': list(hotels.values()), 'rejections': rejected,
        'summary': {
            'roster_count': len(hotels), 'accepted_rows': accepted,
            'duplicate_rows': duplicates, 'unique_offers': len(offers),
            'observed_series_cells': sum(series_counts.values()),
            'coverage': _coverage(planned, observed),
            'series': [{
                'id': key, **SERIES[key], 'coverage': _coverage(planned, value),
            } for key, value in series_counts.items()],
            'rejected_rows': len(rejected), 'all_ota_lowest_verified': False,
        },
        'limitations': [
            'Missing dates are unknown, not proven sold out.',
            'Booking rows omit children unless captured; full party verification remains unknown.',
            'Google indicative prices retain an unverified room count.',
            'Room, meal, cancellation and tax conditions remain unknown unless observed.',
            'No cross-series minimum or like-for-like comparison is computed.',
            'Roster membership does not assign quality tiers or change the saved compset.',
        ],
    }


def load_provider_receipts(data_root):
    """Fixed local-file read; no database access, collection or writes."""
    receipt = json.loads(
        (Path(data_root) / RECEIPT_PATH).read_text(encoding='utf-8-sig'))
    return build_provider_receipts(receipt)
