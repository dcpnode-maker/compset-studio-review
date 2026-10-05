"""Shared research policies: collection recency is not upstream price freshness."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from urllib.parse import urlsplit, urlunsplit


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def instant(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Timestamp must include a timezone')
    return stamp.astimezone(timezone.utc)


def freshness(observed_at, *, now=None, provider_updated_at=None, http_age_seconds=None,
              max_age_seconds=21600):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or type(max_age_seconds) is not int or max_age_seconds < 0:
        raise ValueError('Require aware time and nonnegative freshness budget')
    age = (now - instant(observed_at)).total_seconds()
    if age < 0:
        raise ValueError('Observation cannot be in the future')
    upstream_age = None
    if provider_updated_at is not None:
        upstream_age = (now - instant(provider_updated_at)).total_seconds()
        if upstream_age < age:
            raise ValueError('Provider update cannot be later than its capture')
    if http_age_seconds is not None and (type(http_age_seconds) is not int or http_age_seconds < 0):
        raise ValueError('HTTP Age must be a nonnegative integer')
    return {'observed_at': observed_at, 'capture_age_seconds': round(age, 3),
            'capture_recent': age <= max_age_seconds, 'provider_updated_at': provider_updated_at,
            'provider_age_seconds': upstream_age, 'http_age_seconds': http_age_seconds,
            'upstream_freshness': 'timestamp_observed' if upstream_age is not None else 'unknown',
            'uncached_verified': False}


def amount(value, *, allow_zero=False):
    if isinstance(value, bool):
        raise ValueError('Boolean is not money')
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('Invalid money') from exc
    if not value.is_finite() or value < 0 or (not allow_zero and value == 0):
        raise ValueError('Money must be finite and positive')
    return format(value, 'f')


def public_url(value, hosts):
    parts = urlsplit(value)
    if parts.scheme != 'https' or parts.hostname not in hosts or parts.username or parts.password or parts.port:
        raise ValueError('Unexpected provider URL')
    return urlunsplit((parts.scheme, parts.hostname, parts.path, '', ''))


def comparison_key(row):
    """A parity minimum requires verified product/terms, never matching nulls."""
    if row.get('property_identity_verified') is not True or row.get('party_verified') is not True:
        return None
    if row.get('evidence_kind') not in {'direct_quote', 'provider_display'}:
        return None
    fields = ('hotel_id', 'checkin', 'checkout', 'currency', 'amount_basis', 'price_scope', 'evidence_kind', 'party',
              'taxes_included', 'fees_included', 'room_product', 'meals', 'cancellation',
              'payment', 'membership', 'coupon')
    def known(value):
        if value is None or value == '': return False
        if isinstance(value,dict): return bool(value) and all(known(v) for v in value.values())
        if isinstance(value,list): return all(known(v) for v in value)
        return True
    if any(not known(row.get(key)) for key in fields) or row.get('terms_verified') is not True:
        return None
    return digest({key: row[key] for key in fields})


def comparable_minima(rows):
    grouped, excluded = {}, []
    for row in rows:
        key = comparison_key(row)
        if key is None:
            excluded.append(row)
            continue
        if key not in grouped or Decimal(amount(row['amount'])) < Decimal(amount(grouped[key]['amount'])):
            grouped[key] = row
    return {'groups': list(grouped.values()), 'incomparable_count': len(excluded)}


def calendar_windows(start, days=365, chunk_days=31):
    from datetime import date, timedelta
    if type(days) is not int or not 1 <= days <= 366 or type(chunk_days) is not int or not 1 <= chunk_days <= 31:
        raise ValueError('Use 1-366 dates and 1-31-date chunks')
    first = date.fromisoformat(start)
    return [{'start_date': str(first + timedelta(days=offset)),
             'end_date': str(first + timedelta(days=min(offset + chunk_days, days) - 1))}
            for offset in range(0, days, chunk_days)]
