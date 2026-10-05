"""Audited, offline comparison sets for explicit official and Airbnb subjects.

Identity namespaces prevent accidental cross-platform joins. Shared candidate
profiles retain original field evidence; per-subject files retain every ranking
decision without copying the source catalogue and calendar history hundreds of times.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

from .adaptive import run_adaptive_comparison
from .pipeline import DATA, canonical, _write_json, export_csv
from .profile import CANONICAL_FIELDS, enrich_subject_profile
from .similarity import _amenities, _coordinates, _distance, _number, _room_type
from .normalize import normalize

VERSION = 'portfolio-compsets-v1'
PROFILE_FIELDS = (*CANONICAL_FIELDS, 'floor_area_sqft', 'description', 'city', 'country', 'area',
                  'location_name', 'location_is_exact', 'property_summary', 'publication_status',
                  'operator_name', 'link_status', 'public_property_url', 'source_url', 'currency', 'currency_basis')
MAJOR_AMENITIES = {'pool': 'Pool', 'gym': 'Gym', 'air_conditioning': 'Air conditioning',
                   'wifi': 'Wifi', 'kitchen': 'Kitchen', 'parking': 'Parking'}
AUDIT_FIELDS = ('eligibility', 'selected', 'distance_km', 'inside_circle', 'rejection_reasons',
                'missing_fields', 'similarity_score', 'score_components', 'evidence_coverage',
                'base_similarity_score', 'comparison_components', 'secondary_similarity_score',
                'operator_size', 'operator_size_basis', 'observed_host_listing_count', 'adaptive_history')


def _load(path):
    value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('Expected a saved snapshot object')
    return value


def _stamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        return value if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def _instant(value):
    return datetime.fromisoformat(value).astimezone(timezone.utc) if _stamp(value) else datetime.min.replace(tzinfo=timezone.utc)


def _latest(values):
    return max((v for v in values if _stamp(v)), key=_instant, default=None)


def _freshness(stamp, now, stale_hours):
    age = (now - _instant(stamp)).total_seconds() if _stamp(stamp) else None
    status = 'unknown' if age is None else 'future_timestamp' if age < 0 else 'stale' if age > stale_hours * 3600 else 'within_age_limit'
    return {'observed_at': stamp, 'age_hours': round(age / 3600, 3) if age is not None else None,
            'status': status, 'stale_after_hours': stale_hours}


def _identifier(value):
    value = str(value) if type(value) is int else value
    return value if isinstance(value, str) and re.fullmatch(r'\d{1,25}', value) else None


def _public_evidence(value):
    if not isinstance(value, dict):
        return None
    keep = ('source_url', 'source_path', 'observed_at', 'http_status', 'verified', 'transformation',
            'source_field', 'matched_quote', 'method')
    result = {k: deepcopy(value[k]) for k in keep if k in value and not isinstance(value[k], (dict, list))}
    if 'source_url' in result:
        result['source_url'] = _safe_url(result['source_url'])
    return result


def _safe_url(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            return None
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', ''))
    except (TypeError, ValueError, AttributeError):
        return None


def _profile(row, namespace, identifier, fallback_stamp=None):
    if not isinstance(row, dict):
        raise ValueError('Every profile must be an object')
    source_fields = row.get('field_sources') if isinstance(row.get('field_sources'), dict) else {}
    values = {k: deepcopy(row[k]) for k in PROFILE_FIELDS if k in row}
    # Keep all public amenity attributes without copying parser-generated profiles.
    values['amenities'] = [{k: deepcopy(a[k]) for k in ('title', 'available', 'icon', 'code', 'category') if k in a}
                           if isinstance(a, dict) else a for a in row.get('amenities', [])] if isinstance(row.get('amenities'), list) else None
    observed = _stamp(row.get('details_observed_at')) or _stamp(row.get('observed_at')) or _stamp(fallback_stamp)
    fields = {}
    for key in values:
        evidence = _public_evidence(source_fields.get(key)) or {}
        evidence.setdefault('observed_at', observed)
        if key != 'source_url' and (row.get('public_property_url') or row.get('source_url')):
            evidence.setdefault('source_url', _safe_url(row.get('public_property_url') or row.get('source_url')))
        fields[key] = evidence
    values.update(id=f'{namespace}:{identifier}', namespace=namespace, public_id=identifier,
                  listing_id=identifier if namespace == 'airbnb' else None,
                  property_id=identifier if namespace == 'bnbme_direct' else None,
                  observed_at=observed, field_sources=fields)
    if namespace == 'airbnb':
        values['source_url'] = f'https://www.airbnb.com/rooms/{identifier}'
    else:
        values['source_url'] = _safe_url(row.get('public_property_url') or row.get('source_url'))
    if 'public_property_url' in values:
        values['public_property_url'] = _safe_url(values['public_property_url'])
    return values


def enrich_official_subject(row, fallback_stamp=None):
    """Resolve only explicit saved fields and unambiguous privacy assertions."""
    identifier = _identifier(row.get('property_id'))
    if identifier is None:
        raise ValueError('Official properties need numeric explicit property_id values')
    result = _profile(row, 'bnbme_direct', identifier, fallback_stamp)
    if result.get('currency'):
        result['currency_basis'] = 'official_property_currency'
    enrichment = []
    for container_name in ('detail_attributes', 'attributes'):
        container = row.get(container_name)
        if not isinstance(container, dict):
            continue
        stamp = _stamp(row.get('details_observed_at') if container_name == 'detail_attributes' else row.get('observed_at')) or _stamp(fallback_stamp)
        url = _safe_url(row.get('public_property_url') if container_name == 'detail_attributes' else row.get('source_url'))
        for key in ('room_type', 'property_type', 'floor_area_sqm', 'floor_area_sqft', 'building_name'):
            if result.get(key) not in (None, '', 'unknown'):
                continue
            for path, candidate in ((key, container.get(key)), ('details.' + key, container.get('details', {}).get(key) if isinstance(container.get('details'), dict) else None)):
                if candidate in (None, '', 'unknown'):
                    continue
                result[key] = deepcopy(candidate)
                evidence = {'source_url': url, 'observed_at': stamp, 'source_path': f'{container_name}.{path}', 'method': 'explicit_saved_attribute'}
                result['field_sources'][key] = evidence
                enrichment.append({'field': key, 'value': deepcopy(candidate), 'evidence': evidence})
                break
        description = container.get('description')
        if _room_type(result.get('room_type')) is not None or not isinstance(description, str):
            continue
        text = html.unescape(re.sub(r'<[^>]*>', ' ', description))
        patterns = (
            r'guests have (?:full )?private access to the entire (?:apartment|home|property|villa|house)',
            r'(?:you have|you will have|you.ll have) (?:the )?entire (?:apartment|home|property|villa|house) to yourself',
            r'exclusive use of (?:the )?(?:entire )?(?:apartment|home|property|villa|house)',
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if not match or re.search(r'\b(?:no|not|without)\b', text[max(0, match.start() - 25):match.start()], re.I):
                continue
            evidence = {'source_url': url, 'source_path': container_name + '.description', 'observed_at': stamp,
                        'matched_quote': match.group(), 'method': 'explicit_privacy_assertion'}
            result['room_type'] = 'Entire home/apt'
            result['field_sources']['room_type'] = evidence
            enrichment.append({'field': 'room_type', 'value': 'Entire home/apt', 'evidence': evidence})
            break
    result['enrichment_evidence'] = enrichment
    return result


def cached_sources(root, identifiers):
    """Reparse exact-ID public cache envelopes; never infer identity from filename."""
    sources, issues = [], []
    cache_dir = Path(root) / 'cache' / 'listings'
    if not cache_dir.exists():
        return sources, issues
    for path in sorted(cache_dir.glob('*.json')):
        identifier = path.name.split('-')[0]
        if identifier not in identifiers:
            continue
        try:
            saved = _load(path)
        except (ValueError, OSError):
            issues.append({'path': str(path.resolve()), 'reason': 'malformed_listing_cache'})
            continue
        stamp = _stamp(saved.get('observed_at'))
        if stamp is None:
            issues.append({'path': str(path.resolve()), 'reason': 'cache_source_time_unknown'})
            continue
        rows = []
        for envelope in saved.get('payloads', []) if isinstance(saved.get('payloads'), list) else []:
            if not isinstance(envelope, dict):
                continue
            request = envelope.get('request_context')
            request = request if isinstance(request, dict) else {}
            try:
                url = urlsplit(envelope.get('source_url', ''))
                public_id = re.fullmatch(r'/rooms/(\d+)/?', url.path)
                trusted_url = bool(url.hostname and re.fullmatch(r'(?:www\.)?airbnb\.(?:com|co\.in|co\.uk)', url.hostname))
            except (ValueError, TypeError):
                public_id, trusted_url = None, False
            request_id = _identifier(request.get('listing_id'))
            if not trusted_url or not public_id or public_id[1] != identifier or (request_id is not None and request_id != identifier):
                continue
            currency = request.get('currency')
            currency = currency if isinstance(currency, str) and re.fullmatch('[A-Z]{3}', currency) else None
            context = {'listing_id': identifier, 'currency': currency, 'checkin': '', 'checkout': '', 'observed_at': stamp}
            row = normalize([envelope], context)['listing']
            if len(row) <= 2:
                continue
            row.update(observed_at=stamp, source_url=_safe_url(envelope.get('source_url')))
            if currency:
                row.update(currency=currency, currency_basis='observed_request_currency')
                row['field_sources']['currency'] = {'source_url': row['source_url'], 'source_path': 'request_context.currency',
                                                    'observed_at': stamp, 'method': 'saved_request_context'}
            rows.append(row)
        if rows:
            sources.append({'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                            'snapshot': {'source_namespace': 'airbnb', 'observed_at': stamp, 'candidates': rows,
                                         'coverage': {'kind': 'exact_id_local_listing_cache', 'discovery_performed': False}}})
    return sources, issues


def candidate_pool(snapshots):
    """Deduplicate exact namespaced IDs and retain all source observations."""
    observations, by_id, errors = [], defaultdict(list), []
    for index, source in enumerate(snapshots):
        snapshot = source['snapshot']
        namespace = snapshot.get('source_namespace', 'airbnb')
        if namespace != 'airbnb':
            raise ValueError('This pool adapter currently supports explicit Airbnb listing IDs only')
        rows = snapshot.get('candidates', snapshot.get('airbnb_listings'))
        if not isinstance(rows, list):
            raise ValueError('A candidate pool needs candidates or airbnb_listings')
        report = snapshot.get('report') if isinstance(snapshot.get('report'), dict) else {}
        observed = _stamp(snapshot.get('observed_at')) or _stamp(report.get('observed_at'))
        for position, row in enumerate(rows):
            if not isinstance(row, dict) or _identifier(row.get('listing_id')) is None:
                errors.append({'pool_index': index, 'row_index': position, 'reason': 'missing_or_invalid_airbnb_listing_id'})
                continue
            profile = _profile(row, namespace, _identifier(row['listing_id']), observed)
            observation_id = hashlib.sha256(canonical({'source_sha256': source['sha256'], 'row_index': position, 'profile': profile}).encode()).hexdigest()[:24]
            item = {'observation_id': observation_id, 'pool_index': index, 'row_index': position, 'profile': profile}
            observations.append(item)
            by_id[profile['id']].append(item)
    merged = []
    for identity, items in sorted(by_id.items()):
        fields, evidence, conflicts = {}, {}, {}
        keys = set().union(*(item['profile'].keys() for item in items)) - {'field_sources', 'observed_at'}
        for key in keys:
            values = [item for item in items if item['profile'].get(key) not in (None, '', 'unknown')]
            if not values:
                fields[key] = None
                continue
            chosen = max(values, key=lambda item: (_instant(item['profile']['field_sources'].get(key, {}).get('observed_at') or item['profile']['observed_at']), item['observation_id']))
            fields[key] = deepcopy(chosen['profile'][key])
            evidence[key] = {**deepcopy(chosen['profile']['field_sources'].get(key, {})), 'observation_id': chosen['observation_id']}
            unique = {canonical(item['profile'][key]) for item in values}
            if len(unique) > 1:
                conflicts[key] = [{'observation_id': item['observation_id'], 'value': deepcopy(item['profile'][key])} for item in values]
        fields.update(id=identity, field_sources=evidence, observed_at=_latest(item['profile']['observed_at'] for item in items),
                      observation_ids=[item['observation_id'] for item in items], field_conflicts=conflicts)
        merged.append(fields)
    return {'schema_version': VERSION, 'profiles': merged, 'observations': observations, 'rejected_rows': errors,
            'observation_count': len(observations), 'unique_candidate_count': len(merged),
            'duplicate_observation_count': len(observations) - len(merged)}


def _ranking_adapter(profile):
    fields = (*CANONICAL_FIELDS, 'floor_area_sqft', 'property_summary')
    row = {k: deepcopy(profile.get(k)) for k in fields}
    row['listing_id'] = profile['id']
    row['host_id'] = f"{profile['namespace']}:{profile['host_id']}" if profile.get('host_id') is not None else None
    categories = _amenities(profile.get('amenities'))
    row['amenities'] = [{'title': MAJOR_AMENITIES[k], 'available': True} for k in sorted(categories)] if categories is not None else None
    row['field_sources'] = {k: deepcopy(v) for k, v in profile.get('field_sources', {}).items() if k in fields}
    return row


def _city(profile):
    if profile.get('city'):
        return profile['city']
    text = profile.get('location_name', '')
    if isinstance(text, str):
        for city in ('Dubai', 'Riyadh', 'London'):
            if re.search(r'\b' + city + r'\b', text, re.I):
                return city
    return 'Unknown'


def compare_subject(subject, pool, *, now=None, stale_hours=168):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Use an aware evaluation time')
    profiles = pool['profiles']
    adapted = _ranking_adapter(subject)
    candidates = [_ranking_adapter(p) for p in profiles]
    point = _coordinates(subject)
    unknown_core = [k for k in ('room_type', 'bedrooms') if (_room_type(subject.get(k)) if k == 'room_type' else _number(subject.get(k))) is None]
    coverage = {'state': 'retained_source_snapshots', 'complete_for_requested_cells': False,
                'collection_performed': False, 'source_snapshot_count': len(pool.get('sources', []))}
    if point is not None:
        comparison = run_adaptive_comparison(adapted, candidates,
            {'center_lat': point[0], 'center_lng': point[1], 'radius_km': 2, 'target': 100,
             'bedroom_tolerance': 0, 'bathroom_tolerance': 0.5, 'capacity_tolerance': 2,
             'min_guest_capacity': 1, 'large_operator_threshold': 10}, discovery_coverage=coverage)
        rows = [{"candidate_id": r['listing_id'], **{k: deepcopy(r.get(k)) for k in AUDIT_FIELDS}}
                for r in comparison['candidates']]
        summary = comparison['summary']
        adaptive = comparison['adaptive']
        criteria = comparison['criteria']
        unknown_core = adaptive['subject_core_unknown_fields']
    else:
        rows = [{'candidate_id': p['id'], 'eligibility': 'provisional', 'selected': False, 'distance_km': None,
                 'inside_circle': None, 'rejection_reasons': [], 'missing_fields': ['subject.latitude', 'subject.longitude'],
                 'similarity_score': None, 'adaptive_history': []} for p in profiles if p['id'] != subject['id']]
        summary = {'candidate_count': len(rows), 'eligible_count': 0, 'selected_count': 0, 'provisional_count': len(rows),
                   'excluded_count': 0, 'target': 100, 'target_met': False, 'shortfall': 100}
        adaptive = {'steps': [], 'stop_reason': 'subject_coordinates_unknown', 'automatic_radius_changes': 0,
                    'subject_core_unknown_fields': unknown_core + ['latitude', 'longitude']}
        criteria = None
    physical_fields = {'bedrooms', 'bathrooms', 'person_capacity', 'latitude', 'longitude'}
    profiles_by_id = {p['id']: p for p in profiles}
    for row in rows:
        missing = set(row.get('missing_fields', []))
        row['provisional_physical_match'] = (row['eligibility'] == 'provisional' and row['inside_circle'] is True
                                            and not row['rejection_reasons']
                                            and not any(k in missing or 'subject.' + k in missing for k in physical_fields))
        candidate = profiles_by_id[row['candidate_id']]
        row['operator_relation'] = ('same_observed_public_host' if subject['namespace'] == candidate['namespace']
                                    and subject.get('host_id') is not None and subject.get('host_id') == candidate.get('host_id') else 'unknown_or_different')
    radius_counts = {str(radius): sum(p['id'] != subject['id'] and _coordinates(p) is not None
                                       and _distance(point, _coordinates(p)) <= radius for p in profiles)
                     for radius in (2, 5, 10)} if point else {'2': 0, '5': 0, '10': 0}
    summary['provisional_physical_match_count'] = sum(r['provisional_physical_match'] for r in rows)
    summary['candidate_counts_within_km'] = radius_counts
    warnings = ['Retained public search observations are not exhaustive market inventory.',
                'No price, booked occupancy, hotel star grade or complete corporate inventory is inferred.']
    if subject['namespace'] == 'bnbme_direct':
        warnings.append('Direct-site and Airbnb identities are not linked. A candidate may be the same physical unit; no identity is guessed from name or coordinates.')
    if unknown_core:
        warnings.append('Unknown subject core fields keep matches provisional and prevent adaptive relaxation: ' + ', '.join(unknown_core) + '.')
    if not radius_counts['10']:
        warnings.append('No retained candidate has observed coordinates within ten kilometres of this subject.')
    source_times = [v.get('observed_at') for v in subject.get('field_sources', {}).values() if isinstance(v, dict)]
    return {'schema_version': VERSION, 'subject_id': subject['id'], 'subject_namespace': subject['namespace'],
            'subject': enrich_subject_profile(subject), 'city': _city(subject), 'currency': subject.get('currency'),
            'comparison_state': 'subject_evidence_incomplete' if unknown_core or point is None else 'audited_partial_market_sample',
            'subject_freshness': _freshness(subject.get('observed_at'), now, stale_hours),
            'subject_field_time_range': {'oldest': min((s for s in source_times if _stamp(s)), key=_instant, default=None),
                                         'newest': _latest(source_times)},
            'criteria': criteria, 'summary': summary, 'adaptive': adaptive, 'candidates': rows,
            'selected_candidate_ids': [r['candidate_id'] for r in rows if r['selected']],
            'provisional_physical_candidate_ids': [r['candidate_id'] for r in rows if r['provisional_physical_match']],
            'source_coverage': coverage, 'warnings': warnings}


def build_portfolio(*, data_root=DATA, pool_paths=(), output_dir=None, stale_hours=168, now=None):
    root = Path(data_root)
    output = Path(output_dir) if output_dir is not None else root / 'portfolio-compsets'
    now = now or datetime.now(timezone.utc)
    if type(stale_hours) not in (int, float) or stale_hours <= 0:
        raise ValueError('stale_hours must be positive')
    portfolio_path = root / 'portfolio-latest.json'
    portfolio = _load(portfolio_path)
    properties = portfolio.get('properties')
    if not isinstance(properties, list) or any(not isinstance(r, dict) for r in properties):
        raise ValueError('The official portfolio needs a properties array')
    subjects = [enrich_official_subject(r, portfolio.get('observed_at')) for r in properties]
    host_rows = portfolio.get('airbnb_listings', [])
    if not isinstance(host_rows, list):
        raise ValueError('Observed Airbnb membership needs an array')
    subjects += [_profile(r, 'airbnb', _identifier(r['listing_id']), portfolio.get('observed_at'))
                 for r in host_rows if isinstance(r, dict) and _identifier(r.get('listing_id'))]
    if len({p['id'] for p in subjects}) != len(subjects):
        raise ValueError('Duplicate explicit subject identities in portfolio')
    paths = [root / 'compset-latest.json', *(Path(p) for p in pool_paths)]
    sources, seen_paths = [], set()
    for path in paths:
        if path.resolve() in seen_paths:
            continue
        seen_paths.add(path.resolve())
        if not path.exists():
            if path == root / 'compset-latest.json':
                continue
            raise ValueError(f'Candidate snapshot is missing: {path.name}')
        source = _load(path)
        sources.append({'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'snapshot': source})
    sources.append({'path': str(portfolio_path.resolve()) + '#airbnb_listings',
                    'sha256': hashlib.sha256(portfolio_path.read_bytes()).hexdigest(),
                    'snapshot': {'source_namespace': 'airbnb', 'observed_at': portfolio.get('observed_at'), 'airbnb_listings': host_rows,
                                 'coverage': {'kind': 'observed_public_host_membership', 'corporate_inventory_complete': False}}})
    subject_source_hash = sources[-1]['sha256']
    identifiers = {_identifier(r.get('listing_id')) for s in sources
                   for r in s['snapshot'].get('candidates', s['snapshot'].get('airbnb_listings', [])) if isinstance(r, dict)}
    cache_sources, cache_issues = cached_sources(root, identifiers)
    sources.extend(cache_sources)
    pool = candidate_pool(sources)
    pool['local_cache_issues'] = cache_issues
    # Subject membership comes only from the explicit portfolio. Attribute enrichment
    # may use matching public Airbnb IDs, never matching titles or coordinates.
    pool_by_id = {p['id']: p for p in pool['profiles']}
    subjects = [deepcopy(pool_by_id[s['id']]) if s['namespace'] == 'airbnb' and s['id'] in pool_by_id else s for s in subjects]
    pool['sources'] = [{k: v for k, v in item.items() if k != 'snapshot'} | {
        'observed_at': item['snapshot'].get('observed_at') or (item['snapshot'].get('report') or {}).get('observed_at') if isinstance(item['snapshot'].get('report', {}), dict) else item['snapshot'].get('observed_at'),
        'discovery_context': item['snapshot'].get('discovery_context', item['snapshot'].get('candidate_discovery_context', item['snapshot'].get('context'))),
        'coverage': item['snapshot'].get('coverage', item['snapshot'].get('discovery', item['snapshot'].get('report', {})))} for item in sources]
    pool_id = hashlib.sha256(canonical(pool).encode()).hexdigest()[:24]
    pool['pool_id'] = pool_id
    for profile in pool['profiles']:
        profile['freshness'] = _freshness(profile.get('observed_at'), now, stale_hours)
    build_id = hashlib.sha256(canonical({'version': VERSION, 'subject_source': subject_source_hash, 'pool_id': pool_id,
                                       'evaluated_at': now.isoformat(), 'stale_hours': stale_hours,
                                       'code': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}).encode()).hexdigest()[:24]
    folder = output / 'builds' / build_id
    folder.mkdir(parents=True, exist_ok=True)
    records_dir = folder / 'subjects'
    records_dir.mkdir(exist_ok=True)
    # Existing immutable build files are never rewritten; latest is an atomic index.
    pool_file = folder / 'candidate-pool.json'
    if not pool_file.exists():
        _write_json(pool_file, pool)
    index_rows = []
    for subject in subjects:
        record = compare_subject(subject, pool, now=now, stale_hours=stale_hours)
        record.update(build_id=build_id, candidate_pool_id=pool_id, candidate_pool_artifact='../candidate-pool.json', generated_at=now.isoformat())
        filename = subject['id'].replace(':', '-') + '.json'
        file = records_dir / filename
        if not file.exists():
            _write_json(file, record)
        index_rows.append({'subject_id': subject['id'], 'namespace': subject['namespace'], 'title': subject.get('title'),
                           'city': record['city'], 'currency': record['currency'], 'state': record['comparison_state'],
                           'selected_count': record['summary']['selected_count'],
                           'provisional_physical_match_count': record['summary']['provisional_physical_match_count'],
                           'candidate_counts_within_km': record['summary']['candidate_counts_within_km'],
                           'missing_core_fields': record['adaptive']['subject_core_unknown_fields'],
                           'observed_at': subject.get('observed_at'), 'artifact': f'builds/{build_id}/subjects/{filename}'})
    cities = {}
    for city in sorted({r['city'] for r in index_rows}):
        values = [r for r in index_rows if r['city'] == city]
        cities[city] = {'subject_count': len(values), 'official_subject_count': sum(r['namespace'] == 'bnbme_direct' for r in values),
                        'airbnb_subject_count': sum(r['namespace'] == 'airbnb' for r in values),
                        'subjects_with_selected_peers': sum(r['selected_count'] > 0 for r in values),
                        'subjects_without_candidates_within_10km': sum(r['candidate_counts_within_km']['10'] == 0 for r in values),
                        'subjects_missing_core_attributes': sum(bool(r['missing_core_fields']) for r in values)}
    index = {'schema_version': VERSION, 'build_id': build_id, 'generated_at': now.isoformat(), 'pool_id': pool_id,
             'candidate_pool_artifact': f'builds/{build_id}/candidate-pool.json', 'subjects': index_rows,
             'summary': {'official_subject_count': len(properties), 'airbnb_subject_count': len(subjects) - len(properties),
                         'total_comparison_records': len(subjects), 'unique_candidates': pool['unique_candidate_count'],
                         'candidate_observations': pool['observation_count'], 'rejected_candidate_rows': len(pool['rejected_rows']),
                         'city_coverage': cities, 'corporate_inventory_complete': False, 'cross_platform_identity_links_created': 0}}
    if not (folder / 'index.json').exists():
        _write_json(folder / 'index.json', index)
    _write_json(output / 'latest.json', index)
    export_csv(output / 'subjects.csv', index_rows, ['subject_id', 'namespace', 'title', 'city', 'currency', 'state', 'selected_count', 'provisional_physical_match_count'])
    return index


def main():
    parser = argparse.ArgumentParser(description='Build offline audited BnBMe comparison sets from saved public profiles')
    parser.add_argument('--data-root', type=Path, default=DATA)
    parser.add_argument('--pool', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--stale-hours', type=float, default=168)
    args = parser.parse_args()
    result = build_portfolio(data_root=args.data_root, pool_paths=args.pool, output_dir=args.output, stale_hours=args.stale_hours)
    print(json.dumps({'build_id': result['build_id'], 'summary': result['summary']}, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
