"""Pure 30-day artifacts that never use requested guests as pricing evidence."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import re
from urllib.parse import urlsplit, urlunsplit

from .collect import read_operation
from .normalize import _listing_id, _money, _roots, _valid_date

PARTY = {"adults": 1, "children": 0, "infants": 0, "pets": 0}
PUBLIC_CONTEXT = ("listing_id", "checkin", "checkout", *PARTY, "currency", "locale",
                  "calendar_year", "calendar_month", "calendar_month_count")


def _positive(value):
    if type(value) is bool or value is None:
        return None
    try:
        amount = Decimal(str(value))
        return format(amount, "f") if amount.is_finite() and amount > 0 else None
    except (InvalidOperation, ValueError):
        return None


def _url(value):
    try:
        parsed = urlsplit(str(value or ""))
        return urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path, "", ""))
    except ValueError:
        return ""


def _tokens(path):
    if not isinstance(path, str) or not path.startswith("$"):
        return None
    matches = list(re.finditer(r"\.([A-Za-z_][A-Za-z_0-9]*)|\[([0-9]+)\]", path[1:]))
    if "$" + "".join(item.group() for item in matches) != path:
        return None
    return [item[1] if item[1] is not None else int(item[2]) for item in matches]


def _lookup(body, path):
    tokens = _tokens(path)
    if tokens is None:
        return None
    for token in tokens:
        if isinstance(token, int) and isinstance(body, list) and token < len(body):
            body = body[token]
        elif isinstance(token, str) and isinstance(body, dict) and token in body:
            body = body[token]
        else:
            return None
    return body


def _source_matches(capture, source):
    path, url = source.get("source_path"), _url(source.get("source_url"))
    if not path or not url:
        return []
    matches = []
    for index, envelope in enumerate(capture.get("payloads", [])):
        if not isinstance(envelope, dict) or type(envelope.get("status")) is not int or envelope["status"] != 200:
            continue
        if _url(envelope.get("source_url")) != url:
            continue
        if any(root.get("errors") for root, prefix in _roots(envelope.get("body")) if path.startswith(prefix + ".")):
            continue
        value = _lookup(envelope.get("body"), path)
        if value is not None:
            matches.append((index, envelope, value, path))
    return matches


def _captured(envelope):
    context = envelope.get("request_context")
    return {key: context[key] for key in PUBLIC_CONTEXT if key in context} if isinstance(context, dict) else {}


def _verified(envelope, requested, *, stay=False):
    observed = _captured(envelope)
    if (_listing_id(observed.get("listing_id")) != requested["listing_id"]
            or observed.get("currency") != requested["currency"]):
        return False
    if any(type(observed.get(key)) is not int or observed[key] != value for key, value in PARTY.items()):
        return False
    return not stay or all(observed.get(key) == requested.get(key) for key in ("checkin", "checkout"))


def _evidence(match):
    index, envelope, _, path = match
    return {"payload_index": index, "source_url": _url(envelope.get("source_url")),
            "source_path": path, "http_status": envelope["status"],
            "observed_request_context": _captured(envelope)}


def _calendar_matches(capture, row, context):
    matches = []
    for match in _source_matches(capture, row):
        _, envelope, day, path = match
        if not isinstance(day, dict) or day.get("calendarDate") != row["date"]:
            continue
        month_path = re.split(r"\.(?:days|calendarDays)\[", path)[0]
        month = _lookup(envelope.get("body"), month_path)
        month_id = _listing_id(month.get("listingId")) if isinstance(month, dict) else None
        request_id = _listing_id(_captured(envelope).get("listing_id"))
        if (isinstance(month, dict) and month.get("listingId") is not None and month_id is None
                or not (month_id or request_id) or month_id is not None and month_id != context["listing_id"]
                or request_id is not None and request_id != context["listing_id"]):
            continue
        matches.append(match)
    return matches


def _explanation_groups(envelope, path, rate_plan_id=None):
    """Keep returned explanation groups, including unknown fee/modifier fields."""
    tokens = _tokens(path) or []
    while tokens:
        current = "$" + "".join(f"[{token}]" if isinstance(token, int) else "." + token for token in tokens)
        node = _lookup(envelope.get("body"), current)
        explanation = node.get("explanationData") if isinstance(node, dict) else None
        groups = explanation.get("priceDetails") if isinstance(explanation, dict) else None
        if isinstance(groups, list):
            # Product-level explanations describe its selected cancellation
            # option, not every refundable/non-refundable option in the product.
            if (rate_plan_id is not None and isinstance(node.get("guestOptions"), list)
                    and node.get("selectedGuestOptionId") != rate_plan_id):
                return []
            return deepcopy(groups)
        tokens.pop()
    return []


def build_nightly_rows(capture: dict, result: dict) -> dict:
    """Build one-adult rows without dividing totals or relabeling old captures."""
    context = deepcopy(result.get("context") or {})
    if any(type(context.get(key)) is not int or context[key] != value for key, value in PARTY.items()):
        raise ValueError("Nightly artifact requires exactly one adult and zero children, infants and pets")
    start, end = _valid_date(context.get("start_date")), _valid_date(context.get("end_date"))
    if not start or not end or (date.fromisoformat(end) - date.fromisoformat(start)).days != 30:
        raise ValueError("Nightly artifact requires an exclusive 30-day calendar interval")
    identifier = _listing_id(context.get("listing_id"))
    if not identifier or not re.fullmatch(r"[A-Z]{3}", str(context.get("currency", ""))):
        raise ValueError("Nightly artifact requires listing identity and currency")
    context["listing_id"] = identifier
    supplied = {}
    for row in result.get("calendar", []):
        if isinstance(row, dict) and _valid_date(row.get("date")) and start <= row["date"] < end:
            if row["date"] in supplied:
                raise ValueError("Conflicting duplicate dates must be resolved before building nightly rows")
            supplied[row["date"]] = row
    rows, warnings = [], list(result.get("warnings", []))
    for offset in range(30):
        day = str(date.fromisoformat(start) + timedelta(days=offset))
        row = deepcopy(supplied.get(day) or {"date": day, "listing_id": identifier,
            "available": None, "availability": "unknown", "available_for_checkin": None,
            "available_for_checkout": None, "min_nights": None, "max_nights": None,
            "currency": context["currency"], "source_url": None, "source_path": None,
            "observed_at": None, "reason": "not_observed"})
        row.update(calendar_display_amount=None, nightly_amount_for_requested_party=None,
                   guest_context_verified=False, base_amount=None, taxes_amount=None,
                   cleaning_fee_amount=None, per_adult_modifier_amount=None,
                   taxes_included=None, fees_included=None, raw_price=None,
                   calendar_price_precision="display", source_evidence=[])
        matches = _calendar_matches(capture, row, context) if str(row.get("listing_id")) == identifier else []
        observations = []
        for match in matches:
            _, envelope, raw_day, _ = match
            price = raw_day.get("price")
            price = price if isinstance(price, dict) else {}
            observed = _captured(envelope)
            currency = observed.get("currency", row.get("currency", context["currency"]))
            display = price.get("localPriceFormatted")
            amount = _positive(_money(display, currency, observed.get("locale", context.get("locale"))))
            observations.append((amount, currency, display, deepcopy(price)))
            row["source_evidence"].append(_evidence(match))
        if observations and all(item == observations[0] for item in observations):
            amount, currency, display, raw_price = observations[0]
            row.update(calendar_display_amount=amount, currency=currency, price_display=display, raw_price=raw_price)
            row["guest_context_verified"] = all(_verified(match[1], context) for match in matches)
            if row["guest_context_verified"]:
                row["nightly_amount_for_requested_party"] = amount
            row["nightly_price_reason"] = ("nightly_price_not_returned" if amount is None else
                                            "verified_calendar_display" if row["guest_context_verified"] else
                                            "guest_context_unverified")
        else:
            row["nightly_price_reason"] = "conflicting_source_prices" if observations else "price_source_not_verified"
        row["calendar_price_basis"] = "calendar_day_display" if row["calendar_display_amount"] is not None else "unknown"
        row["nightly_price_basis"] = "calendar_day_display" if row["nightly_amount_for_requested_party"] is not None else "unknown"
        # Do not leave the normalizer's generic amount as an ambiguous alternative
        # to the two deliberately separated price columns.
        row.pop("price_amount", None)
        rows.append(row)
    quotes = []
    for original in result.get("quotes", []):
        quote = deepcopy(original)
        candidates, seen, raw_groups = [], set(), []
        sources = [original, *original.get("sources", [])]
        for source in sources:
            for match in _source_matches(capture, source):
                index, envelope, value, path = match
                if (index, path) in seen:
                    continue
                seen.add((index, path))
                for group in _explanation_groups(envelope, path, original.get("rate_plan_id")):
                    if group not in raw_groups:
                        raw_groups.append(group)
                if (read_operation(envelope.get("source_url", "")) == "StaysPdpBookItQuery"
                        and original.get("quote_kind") == "rate_plan_total" and isinstance(value, str)
                        and value == original.get("price_display")):
                    total = re.fullmatch(r"(.+?)\s+total", value, re.I)
                    observed = _captured(envelope)
                    amount = _positive(_money(total[1], observed.get("currency"), observed.get("locale"))) if total else None
                    if amount is not None and amount == _positive(original.get("total_amount")):
                        candidates.append(match)
        quote["guest_context_verified"] = bool(candidates) and all(
            _verified(match[1], context, stay=True) for match in candidates) and all(
            original.get(key) == context.get(key) for key in ("listing_id", "checkin", "checkout", "currency", *PARTY))
        quote["source_evidence"] = [_evidence(match) for match in candidates]
        quote["raw_line_items"] = raw_groups
        quote["guest_context_reason"] = "observed_bookit_request" if quote["guest_context_verified"] else "guest_context_unverified"
        quotes.append(quote)
    coverage = {"requested_days": 30, "observed_calendar_days": sum(bool(row["source_evidence"]) for row in rows),
        "available_days": sum(row.get("available") is True for row in rows),
        "unavailable_days": sum(row.get("available") is False for row in rows),
        "unknown_days": sum(type(row.get("available")) is not bool for row in rows),
        "calendar_display_price_days": sum(row["calendar_display_amount"] is not None for row in rows),
        "verified_nightly_price_days": sum(row["nightly_amount_for_requested_party"] is not None for row in rows),
        "verified_one_adult_stay_quotes": sum(quote["guest_context_verified"] for quote in quotes)}
    if coverage["verified_nightly_price_days"] < 30:
        warnings.append("Missing verified one-adult nightly amounts remain unknown; stay totals are not allocated to dates.")
    return {"context": context, "rows": rows, "stay_quotes": quotes, "coverage": coverage, "warnings": warnings}
