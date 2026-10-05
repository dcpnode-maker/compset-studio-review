"""Explicit property mappings and price evidence contracts for the Aketa rollout."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

SOURCES = ('google_hotels', 'makemytrip', 'booking', 'expedia', 'agoda')
INDIA = timezone(timedelta(hours=5, minutes=30), 'Asia/Kolkata')
HOSTS = {
    'google_hotels': {'www.google.com'},
    'makemytrip': {'www.makemytrip.com'},
    'booking': {'www.booking.com'},
    'expedia': {'www.expedia.co.in', 'www.expedia.com'},
    'agoda': {'www.agoda.com'},
}
SEED = {'schema_version': 1, 'hotels': [{
    'id': 'aketa-dehradun', 'name': 'Hotel Aketa', 'city': 'Dehradun',
    'timezone': 'Asia/Kolkata', 'currency': 'INR',
    'sources': {
        'google_hotels': {'url': 'https://www.google.com/travel/hotels/entity/ChgI98PmmYGh5fJgGgwvZy8xMmNueDRyN3IQAQ', 'provider_id': 'ChgI98PmmYGh5fJgGgwvZy8xMmNueDRyN3IQAQ', 'verified': True},
        'makemytrip': {'url': 'https://www.makemytrip.com/hotels/hotel_aketa_rajpur_road_dehradun-details-dehradun.html', 'provider_id': '202108231240265962', 'verified': True},
        'booking': {'url': 'https://www.booking.com/hotel/in/aketa.en-gb.html', 'provider_id': None, 'verified': False},
        'expedia': {'url': 'https://www.expedia.co.in/Dehradun-Hotels-Hotel-Aketa-Dehradun.h92850456.Hotel-Information', 'provider_id': '92850456', 'verified': True},
        'agoda': {'url': 'https://www.agoda.com/hotel-aketa/hotel/dehradun-in.html', 'provider_id': '110205', 'verified': True},
    },
}]}


def validate_registry(value):
    if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value.get('schema_version') != 1 or not isinstance(value.get('hotels'), list):
        raise ValueError('Expected hotel registry schema_version 1 and hotels array')
    ids = set()
    for hotel in value['hotels']:
        if not isinstance(hotel, dict) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', str(hotel.get('id', ''))):
            raise ValueError('Hotel IDs must be short lowercase slugs')
        if hotel['id'] in ids:
            raise ValueError('Duplicate hotel ID')
        ids.add(hotel['id'])
        if hotel['id'] != 'aketa-dehradun' or hotel.get('name') != 'Hotel Aketa' or hotel.get('city') != 'Dehradun':
            raise ValueError('This rollout is verified for Hotel Aketa, Dehradun only')
        if hotel.get('timezone') != 'Asia/Kolkata' or hotel.get('currency') != 'INR':
            raise ValueError('Aketa requires Asia/Kolkata and INR')
        if not isinstance(hotel.get('sources'), dict) or not set(hotel['sources']) <= set(SOURCES):
            raise ValueError('Unrecognized hotel source')
        for source, mapping in hotel['sources'].items():
            if not isinstance(mapping, dict) or type(mapping.get('verified')) is not bool:
                raise ValueError('Source mappings require explicit verification state')
            url = urlsplit(mapping.get('url', ''))
            if (url.scheme != 'https' or url.hostname not in HOSTS[source] or url.username or url.password
                    or url.port is not None or url.query or url.fragment):
                raise ValueError('Use a canonical HTTPS property URL on the matching OTA')
            expected = SEED['hotels'][0]['sources'][source]
            if url.path != urlsplit(expected['url']).path or mapping.get('provider_id') != expected['provider_id']:
                raise ValueError('Property mapping differs from the identified Aketa source')
    if not ids:
        raise ValueError('Registry must include a hotel')
    return value


def load_registry(path):
    return validate_registry(json.loads(Path(path).read_text(encoding='utf-8-sig')))


def context_for(hotel, *, start_date=None, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Use an aware execution time')
    today = now.astimezone(INDIA).date()
    start = date.fromisoformat(start_date) if start_date else today
    return {'hotel_id': hotel['id'], 'start_date': str(start), 'days': 30,
            'stay_nights': 1, 'rooms': 1, 'adults': 1, 'children': 0,
            'currency': hotel['currency'], 'timezone': hotel['timezone'], 'locale': 'en-IN'}


def stay_context(context, offset=0):
    checkin = date.fromisoformat(context['start_date']) + timedelta(days=offset)
    return {**context, 'checkin': str(checkin), 'checkout': str(checkin + timedelta(days=1))}


def money(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result <= 0:
            return None
        return format(result, 'f')
    except (InvalidOperation, ValueError, TypeError):
        return None


def normalize_observation(observation, hotel, source, context):
    """Only verified actual context can authorize an exact direct supplier quote."""
    if not isinstance(observation, dict):
        raise ValueError('Source adapter must return an observation object')
    if observation.get('hotel_id') != hotel['id'] or observation.get('source') != source:
        raise ValueError('Source observation identity mismatch')
    requested = observation.get('requested_context')
    if not isinstance(requested, dict) or requested != context or any(type(requested.get(k)) is not type(v) for k, v in context.items()):
        raise ValueError('Source request context differs from the planned request')
    stamp = datetime.fromisoformat(observation['observed_at'])
    if stamp.tzinfo is None:
        raise ValueError('Source observation time must have a timezone')
    result = {**observation, 'requested_context': dict(context), 'rates': [], 'rejected_rates': []}
    if observation.get('status') == 'unavailable':
        actual = observation.get('observed_context') or {}
        fields = ('hotel_id', 'checkin', 'checkout', 'rooms', 'adults', 'children', 'currency')
        verified = (source != 'google_hotels' and observation.get('unavailability_verified') is True
                    and not observation.get('rates') and all(k in context and actual.get(k) == context[k]
                    and type(actual.get(k)) is type(context[k]) for k in fields))
        if not verified:
            result.update(status='unknown', reason='unavailability_context_not_verified', unavailability_verified=False)
        return result
    if observation.get('status') not in {'quoted', 'observed', 'complete', 'indicative', 'success', 'partial'}:
        if observation.get('rates'):
            result['rejected_rates'].append({'reason': 'failed_source_cannot_supply_prices'})
        return result
    start = date.fromisoformat(context['start_date'])
    end = start + timedelta(days=context['days'])
    for original in observation.get('rates', []):
        reason = None
        try:
            row = dict(original)
            arrival, departure = date.fromisoformat(row['checkin']), date.fromisoformat(row['checkout'])
            if row.get('hotel_id', hotel['id']) != hotel['id'] or row.get('source', source) != source:
                reason = 'rate_identity_mismatch'
            elif source != 'google_hotels' and row.get('channel', source) != source:
                reason = 'direct_rate_channel_mismatch'
            elif not start <= arrival < end or departure - arrival != timedelta(days=1):
                reason = 'rate_outside_requested_stay_window'
            elif row.get('currency') != context['currency']:
                reason = 'currency_not_verified'
            elif source != 'google_hotels':
                actual = row.get('observed_context') or observation.get('observed_context') or {}
                expected = {**context, 'checkin': row['checkin'], 'checkout': row['checkout']}
                fields = ('hotel_id', 'checkin', 'checkout', 'rooms', 'adults', 'children', 'currency')
                if not all(actual.get(k) == expected[k] and type(actual.get(k)) is type(expected[k]) for k in fields):
                    reason = 'returned_stay_context_not_verified'
                elif row.get('context_verified') is not True:
                    reason = 'direct_quote_context_not_verified'
                elif row.get('direct_supplier_quote') is True:
                    if row.get('amount_type') not in {'one_night_stay_total', 'nightly_room_rate'}:
                        reason = 'direct_amount_basis_not_verified'
                elif not (row.get('direct_supplier_quote') is False and row.get('amount_type') == 'ota_display_price'
                          and row.get('source_amount_basis') in {'one_night_stay_total', 'nightly_room_rate'}
                          and row.get('precision') in {'displayed_integer', 'displayed_decimal', 'abbreviated'}):
                    reason = 'direct_display_semantics_not_verified'
            amount = money(row.get('amount'))
            approximate = money(row.get('approximate_amount'))
            if source != 'google_hotels' and row.get('direct_supplier_quote') is True and (amount is None or row.get('precision') not in {'exact', 'source_exact'}):
                reason = reason or 'exact_direct_amount_not_observed'
            if row.get('precision') == 'abbreviated':
                amount = None
            if source == 'google_hotels':
                if row.get('amount_type') not in {'google_calendar_minimum', 'google_partner_nightly_total'}:
                    reason = 'google_price_basis_not_verified'
                row['direct_supplier_quote'] = False
                row['context_verified'] = False  # Explicit room count is unobserved on Google.
                if row.get('precision') == 'abbreviated':
                    amount = None
            if amount is None and approximate is None:
                reason = reason or 'positive_price_not_observed'
            if reason:
                result['rejected_rates'].append({'checkin': row.get('checkin'), 'reason': reason})
                continue
            row.update(hotel_id=hotel['id'], source=source, amount=amount, approximate_amount=approximate)
            row.setdefault('channel', source if source != 'google_hotels' else None)
            row.setdefault('taxes_included', None)
            row.setdefault('fees_included', None)
            result['rates'].append(row)
        except (ValueError, KeyError, TypeError):
            result['rejected_rates'].append({'reason': 'malformed_rate'})
    if result['rejected_rates'] and not result['rates']:
        result.update(status='unknown', reason='price_contract_mismatch')
    return result
