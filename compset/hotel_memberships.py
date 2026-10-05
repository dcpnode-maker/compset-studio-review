"""Read-only, label-only account competitor observations; never infer identities."""
from datetime import datetime
import json
from pathlib import Path
import re

from .hotel_portfolio import source_url


def _label(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 250 or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid configured hotel label')
    return value.strip()


def load_configured_labels(data_root, profiles):
    path = Path(data_root) / 'hotel-portfolio' / 'configured-compset-labels.json'
    empty = {'status': 'not_observed', 'groups': [], 'observed_membership_count': 0,
             'verified_competitor_id_count': 0, 'rates_collected_count': 0, 'warnings': []}
    if not path.exists():
        return empty
    try:
        if path.stat().st_size > 500000:
            raise ValueError('Label observation exceeds size limit')
        raw = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(raw, dict) or raw.get('schema_version') != 'lighthouse-configured-labels.v1':
            raise ValueError('Unknown label schema')
        if raw.get('identity_status') != 'name_only_competitors_unresolved_provider_ids':
            raise ValueError('Unknown label identity basis')
        stamp = raw.get('observed_at')
        if not isinstance(stamp, str) or len(stamp) > 60 or datetime.fromisoformat(stamp.replace('Z', '+00:00')).tzinfo is None:
            raise ValueError('Invalid label observation time')
        url = source_url(raw.get('source_url'))
        subjects = raw.get('subjects')
        if not isinstance(subjects, list) or len(subjects) > 100:
            raise ValueError('Invalid subject list')
        known = {p['id'] for p in profiles if isinstance(p, dict) and 'subject' in p.get('roles', [])}
        groups, seen = [], set()
        for row in subjects:
            if not isinstance(row, dict):
                raise ValueError('Invalid label group')
            identity = row.get('subject_id')
            if not isinstance(identity, str) or identity not in known or identity in seen:
                raise ValueError('Unknown or repeated subject identity')
            labels = row.get('competitor_labels')
            if not isinstance(labels, list) or len(labels) > 100:
                raise ValueError('Invalid configured labels')
            labels = [_label(value) for value in labels]
            if len(set(labels)) != len(labels):
                raise ValueError('Repeated competitor label requires reconciliation')
            seen.add(identity)
            groups.append({'subject_id': identity, 'competitor_labels': labels,
                           'identity_status': 'name_only_unresolved', 'observed_at': stamp, 'source_url': url})
        return {'status': 'observed_name_only', 'groups': groups,
                'observed_membership_count': sum(len(g['competitor_labels']) for g in groups),
                'verified_competitor_id_count': 0, 'rates_collected_count': 0,
                'warnings': ['Configured names are not verified OTA identities or independently collected competitor rates.']}
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return {**empty, 'status': 'read_error', 'warnings': ['Configured competitor labels could not be validated.']}
