"""Small, lazy read projections for the STR and hotel workspaces.

All reads are local. Cached decoded source objects are private and never mutated.
Price semantics are inherited from observed source evidence, not comparison ranks.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from . import workspace as rate
from .portfolio_compsets import _safe_url, _public_evidence

SCHEMA = 'intelligence-v1'
NAMESPACES = ('bnbme_direct', 'airbnb')
PROFILE = ('title', 'city', 'country', 'area', 'location_name', 'currency', 'currency_basis', 'bedrooms',
           'beds', 'bathrooms', 'person_capacity', 'latitude', 'longitude', 'room_type', 'floor_area_sqm',
           'property_type', 'building_name', 'quality_tier', 'rating', 'review_count', 'host_id', 'host_name',
           'host_listing_count', 'host_is_professional', 'operator_name', 'observed_at')
DECISIONS = ('candidate_id', 'eligibility', 'selected', 'distance_km', 'inside_circle', 'similarity_score',
             'base_similarity_score', 'secondary_similarity_score', 'operator_size', 'operator_size_basis',
             'observed_host_listing_count', 'provisional_physical_match', 'operator_relation')


@lru_cache(maxsize=12)
def _decoded(path, signature):
    value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('Saved evidence must be an object')
    return value


def _read(root, name, warnings):
    path = Path(root) / name
    try:
        stat = path.stat()
        return _decoded(str(path.resolve()), (stat.st_mtime_ns, stat.st_size))
    except FileNotFoundError:
        warnings.append(f'{name}: no saved evidence.')
    except (OSError, UnicodeError, ValueError, RecursionError):
        warnings.append(f'{name}: unreadable saved evidence; unknown values retained.')
    return {}


def _revision(root):
    parts = []
    for name in ('portfolio-latest.json', 'portfolio-compsets/latest.json', 'one-night-latest.json',
                 'hotel-pipelines/latest.json', 'hotel-compsets/aketa/latest.json', 'hotel-portfolio/latest.json',
                 'hotel-portfolio/configured-compset-labels.json'):
        try:
            stat = (Path(root) / name).stat()
            parts.append((name, stat.st_mtime_ns, stat.st_size))
        except OSError:
            parts.append((name, None))
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:20]


def _valid_id(value):
    return isinstance(value, str) and re.fullmatch(r'(?:bnbme_direct|airbnb):\d{1,25}', value) is not None


def _profile(row, identity=None, *, amenities=True):
    result = rate._pick(row, PROFILE)
    result['id'] = identity or rate._text(row.get('id'))
    result['subject_id'] = result['id']
    result['namespace'] = result['id'].split(':')[0] if _valid_id(result['id']) else None
    result['source'] = result['namespace']
    result['label'] = result.get('title') or result['id']
    result['source_url'] = rate.public_property_url(row.get('public_property_url') or row.get('source_url'))
    if result['namespace'] == 'airbnb':
        result['source_url'] = rate._airbnb_url(result['id'].split(':')[1])
    result['observed_at'] = rate._stamp(row.get('details_observed_at') or row.get('observed_at'))
    if amenities:
        result['amenities'] = [rate._pick(a, ('title', 'available', 'category')) if isinstance(a, dict) else rate._text(a)
                               for a in row.get('amenities', [])] if isinstance(row.get('amenities'), list) else []
    return result


def _headers(root, warnings):
    portfolio = _read(root, 'portfolio-latest.json', warnings)
    index = _read(root, 'portfolio-compsets/latest.json', warnings)
    compared = {r['subject_id']: r for r in rate._rows(index.get('subjects')) if _valid_id(r.get('subject_id'))}
    properties = []
    for namespace, key, id_key in (('bnbme_direct', 'properties', 'property_id'), ('airbnb', 'airbnb_listings', 'listing_id')):
        for source in rate._rows(portfolio.get(key)):
            identity = f'{namespace}:{source.get(id_key)}'
            if not _valid_id(identity):
                continue
            row = _profile(source, identity, amenities=False)
            match = compared.get(identity, {})
            row.update(rate._pick(match, ('state', 'selected_count', 'provisional_physical_match_count')))
            row['missing_core_fields'] = rate._strings(match.get('missing_core_fields'))
            row['currency'] = rate._currency(source.get('currency') or match.get('currency'))
            row['city'] = rate._text(source.get('city') or match.get('city')) or 'Unknown'
            row['compset_available'] = bool(match)
            properties.append(row)
    # No silent duplicate identities in the UI denominator.
    unique = {r['id']: r for r in properties}
    if len(unique) != len(properties):
        warnings.append('Duplicate saved subject identities were collapsed in the display.')
    return list(unique.values()), portfolio, index


@lru_cache(maxsize=4)
def _bounds(path, signature):
    portfolio = _decoded(path, signature)
    days = sorted({r['date'] for p in rate._rows(portfolio.get('properties')) for r in rate._rows(p.get('calendar'))
                   if rate._date(r.get('date'))})
    return (days[0], days[-1]) if days else (None, None)


def summary(data_root):
    warnings = []
    properties, portfolio, index = _headers(data_root, warnings)
    hotel_saved = _read(data_root, 'hotel-compsets/aketa/latest.json', warnings)
    hotel_portfolio = _hotel_portfolio(data_root)
    counts = Counter(r['city'] for r in properties)
    try:
        path = (Path(data_root) / 'portfolio-latest.json').resolve()
        stat = path.stat()
        first, last = _bounds(str(path), (stat.st_mtime_ns, stat.st_size))
    except (OSError, ValueError, UnicodeError):
        first, last = None, None
    today = str(datetime.now(timezone.utc).date())
    default_start = min(max(today, first), last) if first else today
    headers = [rate._pick(r, ('id', 'subject_id', 'namespace', 'title', 'city', 'area', 'currency', 'bedrooms', 'bathrooms',
                             'person_capacity', 'latitude', 'longitude', 'observed_at', 'source_url', 'state', 'selected_count',
                             'provisional_physical_match_count', 'compset_available')) for r in properties]
    return {'schema_version': SCHEMA, 'revision': _revision(data_root),
            'observed_at': rate._latest(r.get('observed_at') for r in properties),
            'str': {'properties': headers, 'subjects': [rate._pick(r, ('subject_id', 'namespace',
                     'state', 'selected_count', 'provisional_physical_match_count')) for r in properties],
                    'summary': {'official_subject_count': sum(r['namespace'] == 'bnbme_direct' for r in properties),
                                'airbnb_subject_count': sum(r['namespace'] == 'airbnb' for r in properties),
                                'city_counts': dict(counts), 'unique_candidates': rate._number(rate._dict(index.get('summary')).get('unique_candidates')),
                                'city_namespace_counts': {city: {n: sum(r['city'] == city and r['namespace'] == n for r in properties) for n in NAMESPACES} for city in counts},
                                'corporate_inventory_complete': False, 'cross_platform_identity_links_created': 0},
                    'default_start': default_start, 'calendar_bounds': {'start': first,
                         'end': str(date.fromisoformat(last) + timedelta(days=1)) if last else None},
                    'max_days': 31, 'max_limit': 25},
            'hotel': {'label': 'Hotel Aketa, Dehradun', 'summary': _scalar_map(hotel_saved.get('summary')),
                      'portfolio': {'schema_version': hotel_portfolio.get('schema_version'), 'observed_at': hotel_portfolio.get('observed_at'),
                                    'profiles': [{**rate._pick(r, ('id', 'title', 'city', 'country', 'room_count', 'source_url', 'observed_at')),
                                                  'roles': rate._strings(r.get('roles')), 'rate_coverage': _scalar_map(r.get('rate_coverage')),
                                                  **_configured_label_summary(hotel_portfolio['configured_labels'], r.get('id'))}
                                                 for r in rate._rows(hotel_portfolio.get('profiles'))],
                                    'coverage': deepcopy(hotel_portfolio.get('coverage', {})),
                                    'warnings': rate._strings(hotel_portfolio.get('warnings'))}},
            'warnings': warnings + rate._strings(rate._dict(portfolio.get('summary')).get('coverage_notes'))}


def _scalar_map(value):
    return {k: rate._public(v) for k, v in rate._dict(value).items() if isinstance(k, str) and not isinstance(v, (dict, list))}


def _configured_label_summary(labels, identity):
    for group in labels.get('groups', []):
        if group['subject_id'] == identity:
            return {'configured_label_count': len(group['competitor_labels']), 'configured_label_status': 'observed_name_only'}
    return {'configured_label_count': None,
            'configured_label_status': 'read_error' if labels.get('status') == 'read_error' else 'not_observed'}


def _comparison_summary(value):
    result = _scalar_map(value)
    source = rate._dict(value)
    for key in ('active_filters', 'circle', 'rejection_counts', 'tolerances', 'score_weights',
                'candidate_counts_within_km', 'selected_operator_concentration', 'eligibility_counts'):
        if isinstance(source.get(key), dict):
            result[key] = _scalar_map(source[key])
    if isinstance(source.get('filter_counts'), dict):
        result['filter_counts'] = {k: _scalar_map(v) for k, v in source['filter_counts'].items()}
    return result


def _integer(value, field, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f'{field} must be an integer from {lower} to {upper}')
    return value


def _request(start, days, city, currency, offset, limit, query, bedrooms, namespace):
    if not isinstance(start, str) or re.fullmatch(r'\d{4}-\d{2}-\d{2}', start) is None or rate._date(start) != start:
        raise ValueError('start must be a valid YYYY-MM-DD date')
    days = _integer(days, 'days', 1, 31)
    limit = _integer(limit, 'limit', 1, 25)
    offset = _integer(offset, 'offset', 0, 100000)
    if city not in (None, 'Dubai', 'Riyadh', 'London', 'Unknown'):
        raise ValueError('Unknown city filter')
    if currency is not None and rate._currency(currency) is None:
        raise ValueError('currency must be an uppercase three-letter source currency')
    if namespace not in (*NAMESPACES, None):
        raise ValueError('Unknown identity namespace')
    if bedrooms is not None:
        _integer(bedrooms, 'bedrooms', 0, 50)
    if query is not None and (not isinstance(query, str) or len(query) > 120 or any(ord(c) < 32 for c in query)):
        raise ValueError('query must be at most 120 printable characters')
    query = ' '.join((query or '').split())
    try:
        date.fromisoformat(start) + timedelta(days=days)
    except OverflowError:
        raise ValueError('Date window exceeds supported calendar') from None
    return {'start': start, 'days': days, 'city': city, 'currency': currency, 'offset': offset, 'limit': limit,
            'query': query, 'bedrooms': bedrooms, 'namespace': namespace}


def _unknown(identity, day, currency):
    return {'entity_id': identity, 'date': day, 'checkin': day, 'checkout': str(date.fromisoformat(day) + timedelta(days=1)),
            'state': 'unknown', 'availability': 'unknown', 'amount': None, 'currency': currency,
            'amount_basis': None, 'observed_at': None, 'reason': 'not_observed', 'offers': []}


def _direct_cell(identity, day, source, currency):
    cell = _unknown(identity, day, currency)
    if not source:
        return cell
    stamp = rate._stamp(source.get('observed_at'))
    count = source.get('available_room')
    availability = source.get('availability')
    valid = (stamp is not None and rate._currency(source.get('currency')) == currency
             and source.get('price_basis') == 'website_calendar_rate'
             and source.get('date') == day)
    if not valid:
        cell['reason'] = 'unverified_calendar_context'
        return cell
    cell.update(observed_at=stamp, amount_basis='website_calendar_rate',
                reason=rate._text(source.get('reason')), source_url=_safe_url(source.get('source_url')))
    if type(count) is int and count >= 0 and availability == ('available' if count else 'unavailable'):
        cell['availability'] = availability
    for field, label in (('non_refundable_price', 'Non-refundable'), ('refundable_price', 'Refundable')):
        amount = rate._money(source.get(field))
        if amount is not None:
            cell['offers'].append({'source': 'bnbme_direct', 'amount': amount, 'currency': currency,
                                   'amount_basis': 'website_calendar_rate', 'rate_plan_name': label,
                                   'status': 'indicative', 'observed_at': stamp})
    if cell['availability'] == 'unavailable':
        cell['state'] = 'unavailable'
    elif cell['availability'] == 'available' and cell['offers']:
        # The first named plan is the display plan; alternatives stay distinct.
        cell.update(state='indicative', amount=cell['offers'][0]['amount'])
    elif cell['availability'] == 'available':
        cell['reason'] = 'available_without_calendar_price'
    return cell


def str_calendar(data_root, *, start, days=14, city=None, currency=None, offset=0, limit=25,
                 query=None, bedrooms=None, namespace='bnbme_direct'):
    request = _request(start, days, city, currency, offset, limit, query, bedrooms, namespace)
    warnings = []
    properties, portfolio, index = _headers(data_root, warnings)
    filtered = [r for r in properties if (namespace is None or r['namespace'] == namespace)
                and (city is None or r['city'] == city) and (currency is None or r['currency'] == currency)
                and (bedrooms is None or type(r.get('bedrooms')) in (int, float) and r['bedrooms'] == bedrooms)
                and (not request['query'] or request['query'].casefold() in ' '.join(str(r.get(k) or '') for k in ('title', 'city', 'area', 'id')).casefold())]
    entities = filtered[offset:offset + limit]
    dates = [str(date.fromisoformat(start) + timedelta(days=i)) for i in range(days)]
    direct = {f"bnbme_direct:{r.get('property_id')}": r for r in rate._rows(portfolio.get('properties'))}
    cells = []
    airbnb = None
    if any(r['namespace'] == 'airbnb' for r in entities):
        nightly = _read(data_root, 'one-night-latest.json', warnings)
        compset = _read(data_root, 'compset-latest.json', warnings)
        airbnb = rate._airbnb(compset, nightly)
        warnings.extend(airbnb['warnings'])
    airbnb_cells = {(f"airbnb:{r['entity_id']}", r['date']): r for r in airbnb['cells']} if airbnb else {}
    for entity in entities:
        if entity['namespace'] == 'bnbme_direct':
            rows = {}
            for row in rate._rows(direct.get(entity['id'], {}).get('calendar')):
                day = row.get('date')
                if day in dates and (day not in rows or rate._time_key(row.get('observed_at')) > rate._time_key(rows[day].get('observed_at'))):
                    rows[day] = row
            cells.extend(_direct_cell(entity['id'], day, rows.get(day), entity['currency']) for day in dates)
        else:
            for day in dates:
                row = airbnb_cells.get((entity['id'], day))
                if row and row.get('currency') == entity['currency']:
                    cell = deepcopy(row)
                    cell['entity_id'] = entity['id']
                    cell['availability'] = 'unavailable' if cell['state'] == 'unavailable' else 'unknown'
                    cells.append(cell)
                else:
                    cells.append(_unknown(entity['id'], day, entity['currency']))
    return {'schema_version': SCHEMA, 'revision': _revision(data_root), 'request': request,
            'total': len(filtered), 'dates': dates, 'entities': entities, 'cells': cells,
            'summary': dict(Counter(c['state'] for c in cells)),
            'source_context': {'bnbme_direct': {'amount_basis': 'website_calendar_rate', 'adults': None, 'rooms': None,
                                              'taxes_included': None, 'fees_included': None},
                               'airbnb': deepcopy(airbnb['context']) if airbnb else None},
            'warnings': warnings + ['Official calendar rates are indicative; guest, tax and fee terms are unknown. Unavailable does not mean booked. Direct and Airbnb identities remain unlinked.']}


def _artifact(root, relative, warnings):
    if not isinstance(relative, str):
        warnings.append('Comparison artifact is missing.')
        return {}
    base = (Path(root) / 'portfolio-compsets').resolve()
    path = (base / relative).resolve()
    if not path.is_relative_to(base) or path.suffix != '.json':
        warnings.append('Invalid comparison artifact path; evidence remains unknown.')
        return {}
    return _read(base, str(path.relative_to(base)), warnings)


def str_compset(data_root, subject_id, *, offset=0, limit=50, decision=None, candidate_id=None):
    if not _valid_id(subject_id):
        raise ValueError('subject_id must use bnbme_direct:<numeric-id> or airbnb:<numeric-id>')
    _integer(offset, 'offset', 0, 100000)
    _integer(limit, 'limit', 1, 100)
    if decision not in (None, 'selected', 'eligible', 'provisional', 'excluded'):
        raise ValueError('Unknown comparison decision filter')
    if candidate_id is not None and (not _valid_id(candidate_id) or not candidate_id.startswith('airbnb:')):
        raise ValueError('candidate_id must be an explicit Airbnb identity')
    warnings = []
    index = _read(data_root, 'portfolio-compsets/latest.json', warnings)
    header = next((r for r in rate._rows(index.get('subjects')) if r.get('subject_id') == subject_id), None)
    if header is None:
        raise KeyError('No saved comparison for this subject')
    record = _artifact(data_root, header.get('artifact'), warnings)
    if record.get('subject_id') != subject_id:
        record = {}
        warnings.append('Comparison subject identity mismatch; no candidates displayed.')
    pool = _artifact(data_root, index.get('candidate_pool_artifact'), warnings)
    if record.get('candidate_pool_id') != pool.get('pool_id') or not pool.get('pool_id'):
        pool = {}
        warnings.append('Comparison pool identity mismatch; candidate attributes remain unknown.')
    profiles = {r.get('id'): r for r in rate._rows(pool.get('profiles'))}
    candidates, map_points = [], []
    decisions = [r for r in rate._rows(record.get('candidates')) if _valid_id(r.get('candidate_id'))]
    for item in decisions:
        identity = item['candidate_id']
        profile = profiles.get(identity, {})
        map_points.append({'id': identity, 'candidate_id': identity,
                           **rate._pick(profile, ('title', 'latitude', 'longitude', 'observed_at')),
                           'source_url': rate._airbnb_url(identity.split(':')[1]),
                           **rate._pick(item, ('eligibility', 'selected', 'provisional_physical_match', 'distance_km', 'inside_circle'))})
    def matches(item):
        if candidate_id is not None and item['candidate_id'] != candidate_id:
            return False
        if decision == 'selected':
            return item.get('selected') is True
        return decision is None or item.get('eligibility') == decision
    filtered = [r for r in decisions if matches(r)]
    for item in filtered[offset:offset + limit]:
        identity = item.get('candidate_id')
        if not _valid_id(identity):
            continue
        profile = profiles.get(identity, {})
        row = _profile(profile, identity)
        row.update(rate._pick(item, DECISIONS))
        row['rejection_reasons'] = rate._strings(item.get('rejection_reasons'))
        row['missing_fields'] = rate._strings(item.get('missing_fields'))
        for key in ('score_components', 'comparison_components'):
            row[key] = {k: _scalar_map(v) for k, v in rate._dict(item.get(key)).items()}
        row['adaptive_history'] = [_history(s) for s in rate._rows(item.get('adaptive_history'))]
        row['field_sources'] = {k: _public_evidence(v) for k, v in rate._dict(profile.get('field_sources')).items() if k in PROFILE}
        row['freshness'] = _scalar_map(profile.get('freshness'))
        candidates.append(row)
    adaptive = rate._dict(record.get('adaptive'))
    steps = []
    for step in rate._rows(adaptive.get('steps')):
        row = rate._pick(step, ('stage', 'kind', 'eligible_count_before', 'discovery_performed', 'error_type'))
        row.update(criteria=_scalar_map(step.get('criteria')), counts=_scalar_map(step.get('counts')),
                   changes={k: _scalar_map(v) for k, v in rate._dict(step.get('changes')).items()})
        steps.append(row)
    subject = _profile(rate._dict(record.get('subject')), subject_id)
    subject['field_sources'] = {k: _public_evidence(v) for k, v in rate._dict(rate._dict(record.get('subject')).get('field_sources')).items() if k in PROFILE}
    return {'schema_version': SCHEMA, 'revision': _revision(data_root), 'request': {'subject_id': subject_id, 'offset': offset, 'limit': limit,
                                                                               'decision': decision, 'candidate_id': candidate_id},
            'subject': subject, 'subject_freshness': _scalar_map(record.get('subject_freshness')),
            'criteria': _scalar_map(record.get('criteria')), 'summary': _comparison_summary(record.get('summary')),
            'adaptive': {**rate._pick(adaptive, ('stop_reason', 'automatic_radius_changes', 'policy_revision')),
                         'subject_core_unknown_fields': rate._strings(adaptive.get('subject_core_unknown_fields')), 'steps': steps},
            'candidate_total': len(filtered), 'all_candidate_total': len(decisions), 'map_points': map_points,
            'candidates': candidates, 'warnings': warnings + rate._strings(record.get('warnings'))}


def _history(value):
    return {**rate._pick(value, ('stage', 'eligibility', 'selected')),
            'rejection_reasons': rate._strings(value.get('rejection_reasons')), 'missing_fields': rate._strings(value.get('missing_fields'))}


def _hotel_candidate(value):
    row = rate._pick(value, ('id', 'title', 'property_type', 'address', 'latitude', 'longitude', 'distance_km', 'distance_band',
                            'radius_verified', 'location_precision', 'selected', 'eligibility', 'classification_conflict',
                            'observed_at', 'rate_status', 'availability_status'))
    row['source_url'] = _safe_url(value.get('source_url'))
    for key in ('reasons', 'missing_fields', 'identity_notes', 'evidence'):
        row[key] = rate._strings(value.get(key))
    row['amenities'] = _scalar_map(value.get('amenities'))
    row['similarity_score'] = _scalar_map(value.get('similarity_score'))
    product = rate._dict(value.get('product'))
    row['product'] = rate._pick(product, ('segment', 'room_count'))
    for key in ('room_types', 'room_areas_sqm', 'service_notes'):
        row['product'][key] = [rate._public(v) for v in product.get(key, [])] if isinstance(product.get(key), list) else []
    for key in ('classification_evidence', 'review_evidence', 'location_evidence'):
        row[key] = [_scalar_map(r) for r in rate._rows(value.get(key))]
        for evidence in row[key]:
            if 'source_url' in evidence:
                evidence['source_url'] = _safe_url(evidence['source_url'])
    row['field_sources'] = {k: rate._strings(v) for k, v in rate._dict(value.get('field_sources')).items()}
    return row


def _hotel_portfolio(data_root):
    from .hotel_portfolio import load_hotel_portfolio
    from .hotel_memberships import load_configured_labels
    try:
        result = load_hotel_portfolio(data_root)
        result['configured_labels'] = load_configured_labels(data_root, result.get('profiles', []))
        return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError):
        return {'schema_version': 'hotel-portfolio.v1', 'observed_at': None, 'profiles': [], 'relations': [],
                'coverage': {'status': 'read_error', 'subject_list_complete': False, 'rates_collected_count': 0},
                'configured_labels': {'status': 'read_error', 'groups': []},
                'warnings': ['Saved Lighthouse portfolio could not be validated; no inventory or rates inferred.']}


def hotel(data_root):
    warnings = []
    report = _read(data_root, 'hotel-pipelines/latest.json', warnings)
    audit = _read(data_root, 'hotels/aketa/profile-audit/profiles.json', warnings)
    research = _read(data_root, 'hotel-compsets/aketa/latest.json', warnings)
    sources = {}
    for identity, value in rate._dict(research.get('sources')).items():
        if isinstance(value, dict):
            sources[identity] = {**rate._pick(value, ('observed_at', 'kind', 'capture_method', 'capture_status', 'notes')),
                                 'url': _safe_url(value.get('url'))}
    return {'schema_version': SCHEMA, 'revision': _revision(data_root), 'dataset': rate._hotel(report, audit),
            'portfolio': _hotel_portfolio(data_root),
            'compset': {'subject': _hotel_candidate(rate._dict(research.get('subject'))),
                        'summary': _comparison_summary(research.get('summary')), 'candidates': [_hotel_candidate(r) for r in rate._rows(research.get('candidates'))],
                        'warnings': rate._strings(research.get('warnings')), 'search': _scalar_map(research.get('search')),
                        'sources': sources, 'relaxation': [_scalar_map(r) for r in rate._rows(research.get('relaxation'))]}, 'warnings': warnings}
