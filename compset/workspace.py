"""Read-only, public-field projection of saved rate evidence for the local workspace.

This module does not collect, repair, persist or infer missing rates. A generated
timestamp describes this projection; observation timestamps always come from evidence.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

from .hotel_contracts import SOURCES, SEED

SOURCE_LABELS = {'google_hotels': 'Google Hotels', 'makemytrip': 'MakeMyTrip',
                 'booking': 'Booking.com', 'expedia': 'Expedia', 'agoda': 'Agoda'}
PARTY = ('adults', 'children', 'infants', 'pets')
CONTEXT_FIELDS = ('hotel_id', 'listing_id', 'start_date', 'end_date', 'days',
                  'stay_nights', 'checkin', 'checkout', 'rooms', *PARTY, 'currency',
                  'timezone', 'locale', 'observed_at', 'amount_kind')
STATES = ('quoted', 'indicative', 'unavailable', 'restricted', 'unknown')


def _dict(value):
    return value if isinstance(value, dict) else {}


def _rows(value):
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _text(value):
    if not isinstance(value, str):
        return None
    return ''.join(c for c in value[:4000] if c in '\n\t' or ord(c) >= 32)


def _number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def _public(value):
    """Keep small public scalar values, never arbitrary nested source objects."""
    if value is None or type(value) is bool:
        return value
    return _text(value) if isinstance(value, str) else _number(value)


def _pick(value, fields):
    value = _dict(value)
    return {k: _public(value[k]) for k in fields if k in value}


def _strings(value):
    return [v for item in value if (v := _text(item)) is not None] if isinstance(value, list) else []


def _stamp(value):
    try:
        stamp = datetime.fromisoformat(value)
        return value if stamp.tzinfo else None
    except (TypeError, ValueError):
        return None


def _time_key(value):
    stamp = _stamp(value)
    return datetime.fromisoformat(stamp).astimezone(timezone.utc) if stamp else datetime.min.replace(tzinfo=timezone.utc)


def _latest(values):
    return max((s for s in values if _stamp(s)), key=_time_key, default=None)


def _date(value):
    try:
        return str(date.fromisoformat(value))
    except (ValueError, TypeError):
        return None


def _money(value):
    if value is None or type(value) is bool:
        return None
    try:
        amount = Decimal(str(value))
        return format(amount, 'f') if amount.is_finite() and amount > 0 else None
    except (ValueError, TypeError, InvalidOperation):
        return None


def _currency(value):
    return value if isinstance(value, str) and re.fullmatch('[A-Z]{3}', value) else None


def public_property_url(value):
    """Only recognized public property paths; drop tracking and session query strings."""
    if not isinstance(value, str) or '\\' in value or any(ord(c) < 32 for c in value):
        return None
    try:
        parts = urlsplit(value)
        host = (parts.hostname or '').lower()
        if parts.scheme not in {'http', 'https'} or parts.username or parts.password or parts.port:
            return None
        path = parts.path
        permitted = (
            host in {'airbnb.com', 'www.airbnb.com', 'www.airbnb.co.in', 'www.airbnb.ae'} and bool(re.fullmatch(r'/rooms/\d{1,25}/?', path))
            or host in {'bnbmehomes.com', 'www.bnbmehomes.com'} and path.startswith('/property/')
            or host == 'www.google.com' and path.startswith('/travel/hotels/entity/')
            or host == 'www.agoda.com' and '/hotel/' in path
            or host in {'www.booking.com', 'booking.com'} and path.startswith('/hotel/')
            or host in {'www.makemytrip.com', 'www.goibibo.com'} and path.startswith('/hotels/')
            or host in {'www.expedia.co.in', 'www.expedia.com', 'www.expedia.co.kr'} and 'Hotel-Information' in path
            or host in {'hotels.com', 'www.hotels.com', 'in.hotels.com'} and bool(re.match(r'/ho\d+/', path))
        )
        return urlunsplit((parts.scheme, host, path, '', '')) if permitted else None
    except ValueError:
        return None


def _airbnb_url(listing_id):
    return f'https://www.airbnb.com/rooms/{listing_id}' if re.fullmatch(r'\d{1,25}', str(listing_id)) else None


def _read(root, name, warnings):
    try:
        value = json.loads((root / name).read_text(encoding='utf-8-sig'))
        if not isinstance(value, dict):
            raise ValueError('expected object')
        return value
    except FileNotFoundError:
        warnings.append(f'{name}: no saved evidence.')
    except (OSError, UnicodeError, ValueError, RecursionError):
        warnings.append(f'{name}: saved evidence could not be read; data remains unknown.')
    return {}


def _window(context):
    start = _date(context.get('start_date'))
    if not start:
        return []
    if 'days' in context:
        days = context.get('days')
    else:
        end = _date(context.get('end_date'))
        days = (date.fromisoformat(end) - date.fromisoformat(start)).days if end else 0
    if type(days) is not int or not 1 <= days <= 366:
        return []
    return [str(date.fromisoformat(start) + timedelta(days=n)) for n in range(days)]


def _match(actual, expected, fields):
    return all(k in actual and k in expected and actual[k] == expected[k]
               and type(actual[k]) is type(expected[k]) for k in fields)


def _stay(row):
    arrival, departure = _date(row.get('checkin')), _date(row.get('checkout'))
    return (arrival, departure) if arrival and departure and date.fromisoformat(departure) - date.fromisoformat(arrival) == timedelta(days=1) else (None, None)


def _terms(value):
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, list):
        return [_terms(item) for item in value if isinstance(item, (str, dict))]
    if isinstance(value, dict):
        result = _pick(value, ('text', 'name', 'type', 'textDescription', 'description'))
        if isinstance(value.get('descriptions'), list):
            result['descriptions'] = _strings(value['descriptions'])
        return result
    return None


def _offer(row, *, source, basis, stamp, context):
    result = _pick(row, ('room_id', 'room_name', 'rate_plan_id', 'rate_plan_name',
                        'product_variant_id', 'channel', 'provider', 'provider_id',
                        'taxes_included', 'fees_included', 'membership_required',
                        'direct_supplier_quote', 'context_verified', 'party_basis',
                        'room_count_verified'))
    result.update(source=source, checkin=row.get('checkin'), checkout=row.get('checkout'),
                  amount=_money(row.get('amount')), currency=row.get('currency'),
                  precision=_text(row.get('precision')) or 'exact', amount_basis=basis,
                  source_amount_basis=_text(row.get('source_amount_basis')),
                  display_amount=_text(row.get('display_amount') or row.get('amount_display')),
                  approximate_amount=_money(row.get('approximate_amount')),
                  observed_at=stamp, observed_context=_pick(context, CONTEXT_FIELDS))
    if result['precision'] == 'abbreviated':
        result['amount'] = None
    result['rate_plan_name'] = _text(row.get('rate_plan_name') or row.get('rate_plan'))
    result['source_url'] = public_property_url(row.get('source_url') or _dict(row.get('provenance')).get('source_url'))
    for key in ('meals', 'cancellation', 'cancellation_terms', 'conditions', 'discount_conditions', 'payment', 'benefits'):
        result[key] = _terms(row.get(key))
    for key in ('taxes', 'fees', 'base_amount', 'taxes_amount', 'cleaning_fee_amount'):
        result[key] = _money(row.get(key))
    result['rate_options'] = []
    for option in _rows(row.get('rate_options')):
        sources = _rows(option.get('sources'))
        if (option.get('status') != 'quoted' or option.get('amount_kind') != basis
                or option.get('currency') != row.get('currency') or not _money(option.get('amount'))
                or type(option.get('is_selected')) is not bool
                or not any(_match(_dict(s.get('observed_request_context')), context,
                                  ('listing_id', 'checkin', 'checkout', *PARTY, 'currency')) for s in sources)):
            continue
        result['rate_options'].append({
            **_pick(option, ('rate_plan_id', 'is_selected', 'taxes_included', 'fees_included')),
            'rate_plan_name': _text(option.get('rate_plan')), 'amount': _money(option['amount']),
            'currency': option['currency'], 'amount_basis': basis,
            'cancellation_terms': _terms(option.get('cancellation_terms')),
            'observed_at': _latest(s.get('observed_at') for s in sources)})
    return result


def _empty_cell(entity_id, day, currency, reason='not_observed'):
    return {'entity_id': entity_id, 'date': day,
            'checkout': str(date.fromisoformat(day) + timedelta(days=1)), 'state': 'unknown',
            'amount': None, 'display_amount': None, 'currency': currency, 'precision': None,
            'amount_basis': None, 'observed_at': None, 'reason': reason, 'offers': []}


def _price_cell(cell, offers):
    cell['offers'] = offers
    selectable = offers
    if cell['entity_id'] == 'google_hotels':
        calendar = [o for o in offers if o['amount_basis'] == 'google_calendar_minimum']
        if calendar:
            selectable = calendar
            cell['selection_note'] = 'Observed Google calendar display; partner offers are separate evidence in the detail.'
    groups = {(o['currency'], o['amount_basis'], o.get('source_amount_basis'),
               tuple((k, _dict(o.get('observed_context')).get(k)) for k in ('rooms', *PARTY)),
               o.get('taxes_included'), o.get('fees_included')) for o in selectable}
    cell['state'] = 'quoted' if all(o.get('direct_supplier_quote') is True and o['precision'] in {'exact', 'source_exact'} for o in selectable) else 'indicative'
    cell['observed_at'] = _latest(o['observed_at'] for o in offers)
    if len(groups) != 1:
        cell.update(reason='different_price_bases_or_terms', selection_note='Different rate bases or tax contexts; open every offer. No comparable minimum calculated.')
        return
    priced = [o for o in selectable if o['amount'] is not None]
    chosen = min(priced, key=lambda o: Decimal(o['amount'])) if priced else selectable[0]
    for key in ('amount', 'display_amount', 'currency', 'precision', 'amount_basis', 'observed_at'):
        cell[key] = chosen[key]
    cell['reason'] = None
    cell.setdefault('selection_note', 'Lowest observed offer for this source, stay and party; room and rate conditions differ. This is not a like-for-like parity comparison.')


def _summary(cells):
    return {'date_cells': len(cells), **{f'{state}_cells': sum(c['state'] == state for c in cells) for state in STATES},
            'rate_rows': sum(len(c['offers']) for c in cells)}


def _base(dataset_id, label, kind, context):
    return {'id': dataset_id, 'label': label, 'kind': kind, 'currency': _currency(context.get('currency')),
            'context': _pick(context, CONTEXT_FIELDS), 'observed_at': None, 'dates': _window(context),
            'entities': [], 'cells': [], 'summary': _summary([]), 'source_states': [],
            'profiles': [], 'candidates': [], 'warnings': [], 'comparison_note': ''}


def _hotel(report, audit):
    context = _dict(report.get('context'))
    result = _base('aketa', 'Hotel Aketa · Dehradun', 'hotel', context)
    result['comparison_note'] = ('No like-for-like parity or market rank is calculated. Google displays, OTA prices before taxes, membership offers and exact totals have different bases; room, meal and cancellation terms are not fully aligned. No hotel competitor set has been collected.')
    hotel = _dict(report.get('hotel'))
    mappings = _dict(hotel.get('sources'))
    result['entities'] = [{'id': source, 'label': SOURCE_LABELS[source], 'source': source,
                           'role': 'channel', 'source_url': public_property_url(_dict(mappings.get(source)).get('url'))}
                          for source in SOURCES]
    for row in _rows(report.get('source_states')):
        if row.get('source') in SOURCES:
            state = _pick(row, ('source', 'status', 'reason', 'rate_count', 'last_stay'))
            state.update(observed_at=_stamp(row.get('observed_at')), url=public_property_url(row.get('url')))
            result['source_states'].append(state)
    result['warnings'].extend(_strings(report.get('limitations')))
    valid_context = (context.get('hotel_id') == hotel.get('id') == 'aketa-dehradun'
                     and type(context.get('stay_nights')) is int and context['stay_nights'] == 1
                     and all(type(context.get(k)) is int for k in ('rooms', 'adults', 'children'))
                     and isinstance(context.get('currency'), str) and bool(re.fullmatch('[A-Z]{3}', context['currency'])))
    buckets = defaultdict(list)
    rejected = 0
    for row in _rows(report.get('rates')):
        source = row.get('source')
        arrival, departure = _stay(row)
        actual = _dict(row.get('observed_context'))
        basis = row.get('amount_type')
        stamp = _stamp(row.get('observed_at') or _dict(row.get('provenance')).get('observed_at'))
        expected = {**context, 'checkin': arrival, 'checkout': departure}
        valid = (valid_context and source in SOURCES and row.get('hotel_id') == context['hotel_id']
                 and arrival in result['dates'] and row.get('currency') == context['currency'] and stamp is not None)
        if source == 'google_hotels':
            valid = (valid and isinstance(basis, str) and basis in {'google_calendar_minimum', 'google_partner_nightly_total'}
                     and row.get('precision') in ('displayed_integer', 'displayed_decimal', 'abbreviated')
                     and _match(actual, expected, ('adults', 'children', 'currency')))
        else:
            valid = (valid and isinstance(basis, str) and _match(actual, expected, ('hotel_id', 'checkin', 'checkout', 'rooms', 'adults', 'children', 'currency'))
                     and row.get('context_verified') is True and row.get('channel', source) == source
                     and (basis in {'one_night_stay_total', 'nightly_room_rate'} and row.get('direct_supplier_quote') is True
                          and row.get('precision') in ('exact', 'source_exact')
                          or basis == 'ota_display_price' and row.get('direct_supplier_quote') is False
                          and row.get('source_amount_basis') in ('one_night_stay_total', 'nightly_room_rate')
                          and row.get('precision') in ('displayed_integer', 'displayed_decimal', 'abbreviated')))
        for key in ('rooms', 'adults', 'children'):
            if key in row and row[key] is not None and (row[key] != context.get(key) or type(row[key]) is not type(context.get(key))):
                valid = False
        if actual.get('hotel_id', context.get('hotel_id')) != context.get('hotel_id'):
            valid = False
        if source in SOURCES:
            provider_id = SEED['hotels'][0]['sources'][source]['provider_id']
            for evidence in (row, actual):
                for key in ('provider_id', 'provider_hotel_id'):
                    if evidence.get(key) is not None and evidence[key] != provider_id:
                        valid = False
        if not valid or (_money(row.get('amount')) is None and _money(row.get('approximate_amount')) is None):
            rejected += 1
            continue
        offer = _offer(row, source=source, basis=basis, stamp=stamp, context=actual)
        if source == 'google_hotels':
            offer.update(direct_supplier_quote=False, context_verified=False)
        buckets[(source, arrival)].append(offer)
    coverage = {(r.get('source'), r.get('checkin')): r for r in _rows(report.get('coverage'))
                if r.get('hotel_id') == context.get('hotel_id') and r.get('source') in SOURCES and _date(r.get('checkin'))}
    negatives = {}
    for obs in _rows(report.get('observations')):
        actual, requested = _dict(obs.get('observed_context')), _dict(obs.get('requested_context'))
        arrival, departure = _stay(requested)
        expected = {**context, 'checkin': arrival, 'checkout': departure}
        source = obs.get('source')
        provider_matches = source in SOURCES
        if provider_matches:
            provider_id = SEED['hotels'][0]['sources'][source]['provider_id']
            provider_matches = all(evidence.get(key) is None or evidence[key] == provider_id
                                   for evidence in (obs, requested, actual)
                                   for key in ('provider_id', 'provider_hotel_id'))
        if (valid_context and obs.get('source') in SOURCES and obs.get('source') != 'google_hotels'
                and provider_matches
                and obs.get('hotel_id') == context.get('hotel_id') and obs.get('status') == 'unavailable'
                and obs.get('unavailability_verified') is True and not obs.get('rates')
                and _match(actual, expected, ('hotel_id', 'checkin', 'checkout', 'rooms', 'adults', 'children', 'currency'))
                and _match(requested, context, ('hotel_id', 'start_date', 'days', 'rooms', 'adults', 'children', 'currency'))
                and _stamp(obs.get('observed_at'))):
            negatives[(obs['source'], arrival)] = obs
    for entity in result['entities']:
        for day in result['dates']:
            key = (entity['id'], day)
            prior = coverage.get(key, {})
            cell = _empty_cell(entity['id'], day, _currency(context.get('currency')), _text(prior.get('reason')) or 'not_observed')
            offers = buckets.get(key, [])
            if offers and key in negatives:
                cell.update(reason='conflicting_price_and_unavailability_evidence', offers=offers)
            elif offers:
                _price_cell(cell, offers)
            elif key in negatives:
                cell.update(state='unavailable', observed_at=_stamp(negatives[key].get('observed_at')), reason='source_unavailable_for_requested_stay')
            elif prior.get('state') in ('quoted', 'indicative', 'unavailable'):
                cell['reason'] = 'missing_or_unverified_supporting_evidence'
            result['cells'].append(cell)
    if rejected:
        result['warnings'].append(f'{rejected} saved rate rows failed identity, context or price checks and were excluded.')
    if report and not valid_context:
        result['warnings'].append('Hotel request context is invalid; price evidence remains unknown.')
    if not result['dates']:
        result['warnings'].append('No valid saved hotel date window is available.')
    if audit.get('hotel_id') == 'aketa-dehradun':
        for row in _rows(audit.get('profiles')):
            profile = _pick(row, ('source', 'provider_id', 'name', 'sale_status', 'branding'))
            profile.update(url=public_property_url(row.get('url')), observed_at=_stamp(row.get('observed_at')),
                           audit_completed_at=_stamp(audit.get('audit_completed_at')),
                           requested_context=_pick(audit.get('requested_context'), CONTEXT_FIELDS),
                           inventory_mirror=_pick(row.get('inventory_mirror'), ('source', 'provider_id')) or None)
            current = _dict(audit.get('current_offer'))
            if current.get('source') == row.get('source') and current.get('provider_id') == row.get('provider_id'):
                profile['observed_at'] = _stamp(current.get('observed_at'))
            result['profiles'].append(profile)
    result['summary'] = _summary(result['cells'])
    result['observed_at'] = _latest(c['observed_at'] for c in result['cells'])
    return result


def _candidate(row, selected):
    result = _pick(row, ('listing_id', 'title', 'eligibility', 'latitude', 'longitude', 'location_name',
                         'circle_distance_km', 'inside_circle', 'bedrooms', 'beds', 'bathrooms', 'person_capacity',
                         'floor_area_sqm', 'building_name', 'property_type', 'room_type', 'quality_tier', 'rating',
                         'review_count', 'host_id', 'host_name', 'host_listing_count', 'operator_size',
                         'operator_size_basis', 'evidence_coverage', 'similarity_score'))
    listing_id = str(row.get('listing_id', ''))
    result.update(id=listing_id, selected=listing_id in selected, source_url=_airbnb_url(listing_id),
                  observed_at=_stamp(row.get('details_observed_at') or row.get('observed_at')),
                  rejection_reasons=_strings(row.get('rejection_reasons')), missing_fields=_strings(row.get('missing_fields')),
                  amenities=[_pick(a, ('title', 'available')) for a in _rows(row.get('amenities'))])
    return result


def _preflight_state(record, expected):
    preflight = _dict(record.get('preflight'))
    fields = ('listing_id', 'checkin', 'checkout', *PARTY, 'currency')
    if preflight.get('decision') != 'skip_quote' or not _match(_dict(preflight.get('context')), expected, fields):
        return None
    reason = preflight.get('reason')
    rules = {'sleeping_night_unavailable': ('available', 'checkin', 'unavailable'),
             'minimum_stay_not_met': ('min_nights', 'checkin', 'restricted'),
             'checkin_not_allowed': ('available_for_checkin', 'checkin', 'restricted'),
             'checkout_not_allowed': ('available_for_checkout', 'checkout', 'restricted')}
    if not isinstance(reason, str) or reason not in rules:
        return None
    field, day_key, state = rules[reason]
    for evidence in _rows(preflight.get('evidence')):
        if (evidence.get('listing_id') == expected['listing_id'] and evidence.get('date') == expected[day_key]
                and evidence.get('field') == field and evidence.get('http_status') == 200
                and (type(evidence.get('value')) is int and evidence['value'] > 1 if field == 'min_nights' else evidence.get('value') is False)):
            return state, reason
    return None


def _airbnb(compset, nightly):
    context = _dict(nightly.get('context')) or _dict(compset.get('context'))
    result = _base('airbnb-compset', 'Dubai Airbnb comp set', 'airbnb', context)
    result['context']['amount_kind'] = _text(nightly.get('amount_kind'))
    result['comparison_note'] = ('Exact one-night totals are shown only for the recorded guest context. Missing quotes, minimum-stay and arrival/departure restrictions are separate states. Unavailable does not identify a booking. Sparse observations and unknown taxes/cancellation prevent reliable market rank, demand, occupancy or like-for-like parity.')
    result['warnings'].extend(_strings(nightly.get('warnings')))
    discovery_context = _dict(compset.get('candidate_discovery_context'))
    result['discovery_context'] = _pick(discovery_context, CONTEXT_FIELDS)
    if discovery_context and any(discovery_context.get(k) != context.get(k) for k in ('adults', 'children', 'checkin', 'checkout')):
        result['warnings'].append('Candidate discovery used its separately shown stay and guest context; the rate grid uses the saved one-night request context.')
    subject = _dict(compset.get('subject'))
    subject_id = str(subject.get('listing_id') or context.get('listing_id') or '')
    selected_rows = _rows(compset.get('selected'))
    selected = {str(r.get('listing_id')) for r in selected_rows if _airbnb_url(r.get('listing_id'))}
    entities = {str(subject.get('listing_id')): subject} if _airbnb_url(subject.get('listing_id')) else {}
    entities.update({str(r['listing_id']): r for r in selected_rows if _airbnb_url(r.get('listing_id'))})
    planned = nightly.get('listing_ids') if isinstance(nightly.get('listing_ids'), list) else []
    for listing_id in planned:
        if _airbnb_url(listing_id):
            entities.setdefault(str(listing_id), {})
    if _airbnb_url(subject_id):
        entities.setdefault(subject_id, subject)
    for listing_id, row in entities.items():
        result['entities'].append({'id': listing_id, 'label': _text(row.get('title')) or listing_id,
                                   'source': 'airbnb', 'role': 'subject' if listing_id == subject_id else 'competitor',
                                   'source_url': _airbnb_url(listing_id)})
    result['candidates'] = [_candidate(r, selected) for r in _rows(compset.get('candidates')) if _airbnb_url(r.get('listing_id'))]
    valid_context = (str(context.get('listing_id')) == subject_id
                     and all(type(context.get(k)) is int for k in PARTY)
                     and nightly.get('amount_kind') == 'one_night_stay_total'
                     and isinstance(context.get('currency'), str) and bool(re.fullmatch('[A-Z]{3}', context['currency']))
                     and type(context.get('stay_nights')) is int and context['stay_nights'] == 1)
    linked = nightly.get('compset_run_id') == compset.get('run_id') and bool(compset.get('run_id'))
    if nightly and not linked:
        result['warnings'].append('Saved prices reference a different or missing comp-set run; membership may have changed. The grid retains the saved planned cohort as well as current selected listings.')
    records = {}
    rejected = 0
    for record in _rows(nightly.get('records')):
        actual = _dict(record.get('context'))
        listing_id = actual.get('listing_id')
        arrival, departure = _stay(actual)
        expected = {**context, 'listing_id': listing_id, 'checkin': arrival, 'checkout': departure}
        if (not valid_context or not isinstance(listing_id, str) or listing_id not in entities or arrival not in result['dates']
                or not _match(actual, expected, ('listing_id', 'checkin', 'checkout', *PARTY, 'currency'))):
            rejected += 1
            continue
        key = listing_id, arrival
        # Most recent source observation wins, never report update time.
        prior = records.get(key)
        if prior is None or _time_key(record.get('observed_at')) > _time_key(prior.get('observed_at')):
            records[key] = record
    for entity in result['entities']:
        for day in result['dates']:
            cell = _empty_cell(entity['id'], day, _currency(context.get('currency')))
            record = records.get((entity['id'], day), {})
            expected = {**context, 'listing_id': entity['id'], 'checkin': day, 'checkout': cell['checkout']}
            offers = []
            for quote in _rows(record.get('quotes')):
                if (record.get('status') != 'quoted' or quote.get('status') != 'quoted'
                        or quote.get('guest_context_verified') is not True
                        or not _match(quote, expected, ('listing_id', 'checkin', 'checkout', *PARTY, 'currency'))
                        or quote.get('amount_kind') != 'one_night_stay_total' or _money(quote.get('amount')) is None
                        or quote.get('precision') not in (None, 'exact', 'source_exact')
                        or not _stamp(quote.get('observed_at'))):
                    rejected += 1
                    continue
                offer = _offer({**quote, 'direct_supplier_quote': True, 'precision': 'exact'}, source='airbnb',
                               basis='one_night_stay_total', stamp=_stamp(quote['observed_at']), context=quote)
                offer['source_url'] = entity['source_url']
                offers.append(offer)
            negative = _preflight_state(record, expected) if record.get('status') == 'calendar_skipped' else None
            if offers:
                _price_cell(cell, offers)
            elif negative and _stamp(record.get('calendar_observed_at') or record.get('observed_at')):
                cell.update(state=negative[0], reason=negative[1], observed_at=_stamp(record.get('calendar_observed_at') or record.get('observed_at')),
                            amount_basis='one_night_stay_total')
            elif record:
                cell.update(reason='quote_not_observed' if record.get('status') == 'unknown' else 'missing_or_unverified_supporting_evidence',
                            observed_at=_stamp(record.get('observed_at')))
            result['cells'].append(cell)
    if rejected:
        result['warnings'].append(f'{rejected} saved rows failed listing, stay, guest or price checks and were excluded.')
    if not nightly:
        result['warnings'].append('No saved one-night evidence is available.')
    elif not valid_context:
        result['warnings'].append('Saved one-night request context is invalid; prices remain unknown.')
    result['source_states'] = [{'source': 'airbnb', 'status': _text(nightly.get('state')) or 'unknown',
                                'reason': _text(nightly.get('stop_reason')), 'observed_at': None}]
    result['summary'] = _summary(result['cells'])
    result['observed_at'] = _latest(c['observed_at'] for c in result['cells'])
    result['source_states'][0]['observed_at'] = result['observed_at']
    return result


def _portfolio(report):
    properties = []
    for row in _rows(report.get('properties')):
        value = _pick(row, ('title', 'city', 'country', 'currency', 'bedrooms', 'bathrooms',
                            'person_capacity', 'operator_name', 'publication_status', 'link_status'))
        value.update(id=_public(row.get('property_id')), source_url=public_property_url(row.get('public_property_url')),
                     observed_at=_stamp(row.get('details_observed_at') or row.get('observed_at')))
        properties.append(value)
    summary = _dict(report.get('summary'))
    safe_summary = _pick(summary, ('property_count', 'airbnb_listing_count', 'airbnb_linked_count', 'host_count',
                                  'quoted_count', 'display_price_count', 'active_property_count', 'stay_price_count',
                                  'calendar_property_count', 'calendar_record_count', 'calendar_unknown_count', 'active_inventory_complete'))
    for field in ('city_counts', 'currency_counts'):
        safe_summary[field] = {_text(k): _number(v) for k, v in _dict(summary.get(field)).items() if _text(k)}
    safe_summary['coverage_notes'] = _strings(summary.get('coverage_notes'))
    return {'observed_at': _stamp(report.get('observed_at')), 'properties': properties, 'summary': safe_summary}


def build_workspace(data_root):
    """Project saved data, without creating directories or touching source bytes."""
    root = Path(data_root)
    warnings = []
    hotel = _read(root, 'hotel-pipelines/latest.json', warnings)
    audit = _read(root, 'hotels/aketa/profile-audit/profiles.json', warnings)
    compset = _read(root, 'compset-latest.json', warnings)
    nightly = _read(root, 'one-night-latest.json', warnings)
    portfolio = _read(root, 'portfolio-latest.json', warnings)
    return {'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'datasets': [_hotel(hotel, audit), _airbnb(compset, nightly)],
            'portfolio': _portfolio(portfolio), 'warnings': warnings}
