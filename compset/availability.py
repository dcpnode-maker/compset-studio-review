"""Conservative exact-stay decisions from typed public calendar responses."""
from __future__ import annotations

from datetime import date

from .normalize import CALENDAR, _get, _integer, _listing_id, _roots, _valid_date, normalize

CONTEXT_FIELDS = ("listing_id", "checkin", "checkout", "adults", "children", "infants", "pets", "currency", "locale")
RULE_FIELDS = ("available", "availableForCheckin", "availableForCheckout", "minNights", "maxNights")


def calendar_preflight(payloads: list[dict], context: dict) -> dict:
    """Skip only a stay disproved by matched typed evidence; never claim booked.

    Sleeping nights use [checkin, checkout). Checkout permission applies on the
    departure date, whose overnight availability cannot disqualify this stay.
    No positive preflight certifies availability; unknowns still need a quote.
    """
    result = {"decision": "proceed_quote", "result": "unknown", "reason": "calendar_not_observed",
              "context": {key: context.get(key) for key in CONTEXT_FIELDS}, "evidence": [],
              "retryable": None}

    def unknown(reason):
        result["reason"] = reason
        return result

    checkin, checkout = _valid_date(context.get("checkin")), _valid_date(context.get("checkout"))
    identifier = _listing_id(context.get("listing_id"))
    if not identifier or not checkin or not checkout or checkin >= checkout:
        return unknown("invalid_stay_context")
    nights = (date.fromisoformat(checkout) - date.fromisoformat(checkin)).days
    # Include the departure action even when it equals the requested calendar
    # export boundary. This changes parser clipping only, never a request.
    parse_context = dict(context, start_date=None, end_date=None)
    normalized = normalize(payloads, parse_context)
    signatures, request_sources = {}, {}
    recognized = False
    for envelope in payloads:
        if not isinstance(envelope, dict):
            return unknown("calendar_schema_unknown")
        for root, _ in _roots(envelope.get("body")):
            months = _get(root, CALENDAR)
            if months is None:
                continue
            recognized = True
            if envelope.get("status") != 200 or root.get("errors"):
                return unknown("calendar_request_failed")
            captured = envelope.get("request_context")
            if not isinstance(captured, dict) or _listing_id(captured.get("listing_id")) != identifier:
                return unknown("calendar_request_context_unverified")
            for field in CONTEXT_FIELDS[1:]:
                if field in captured and captured[field] != context.get(field):
                    return unknown("calendar_request_context_conflict")
            for path in ("variables.id", "data.node.id"):
                body_id = _get(root, path)
                if body_id is not None and _listing_id(body_id) != identifier:
                    return unknown("calendar_listing_conflict")
            year, month, count = (captured.get(key) for key in ("calendar_year", "calendar_month", "calendar_month_count"))
            month_range = None
            if all(type(value) is int for value in (year, month, count)) and 1 <= year <= 9998 and 1 <= month <= 12 and 1 <= count <= 13:
                start_month = year * 12 + month - 1
                month_range = (start_month, start_month + count)
            elif captured.get("checkin") != checkin or captured.get("checkout") != checkout:
                return unknown("calendar_request_range_unverified")
            if not isinstance(months, list):
                return unknown("calendar_schema_unknown")
            for calendar_month in months:
                if not isinstance(calendar_month, dict):
                    return unknown("calendar_schema_unknown")
                month_id = calendar_month.get("listingId")
                if month_id is not None and _listing_id(month_id) != identifier:
                    return unknown("calendar_listing_conflict")
                days = calendar_month.get("days", calendar_month.get("calendarDays"))
                if not isinstance(days, list):
                    return unknown("calendar_schema_unknown")
                for day in days:
                    if not isinstance(day, dict) or not _valid_date(day.get("calendarDate")):
                        return unknown("calendar_schema_unknown")
                    day_date = day["calendarDate"]
                    if not checkin <= day_date <= checkout:
                        continue
                    if month_range:
                        value = date.fromisoformat(day_date)
                        index = value.year * 12 + value.month - 1
                        if not month_range[0] <= index < month_range[1]:
                            return unknown("calendar_request_range_conflict")
                    signature = tuple(day.get(field) if type(day.get(field)) is bool else None
                                      for field in RULE_FIELDS[:3]) + tuple(_integer(day.get(field)) for field in RULE_FIELDS[3:])
                    if day_date in signatures and signatures[day_date] != signature:
                        return unknown("calendar_observations_conflict")
                    signatures[day_date] = signature
                    request_sources[day_date] = dict(captured)
    if not recognized or not signatures:
        return unknown("calendar_not_observed")
    rows = {row["date"]: row for row in normalized["calendar"] if row.get("listing_id") == identifier}
    start = rows.get(checkin, {})
    minimum, maximum = start.get("min_nights"), start.get("max_nights")
    if type(minimum) is int and type(maximum) is int and maximum > 0 and minimum > maximum:
        return unknown("calendar_observations_conflict")

    def blocked(row, field, reason, classification):
        evidence = {key: row.get(key) for key in ("listing_id", "date", "source_url", "source_path", "http_status", "observed_at")}
        source_field = {"available_for_checkin": "availableForCheckin", "available_for_checkout": "availableForCheckout",
                        "min_nights": "minNights", "max_nights": "maxNights"}.get(field, field)
        evidence["source_path"] += "." + source_field
        evidence.update(field=field, value=row[field], request_context=request_sources[row["date"]])
        result.update(decision="skip_quote", result=classification, reason=reason, retryable=False, evidence=[evidence])
        return result

    for day in sorted(rows):
        if checkin <= day < checkout and rows[day].get("available") is False and day in signatures:
            return blocked(rows[day], "available", "sleeping_night_unavailable", "unavailable_for_context")
    if start.get("available_for_checkin") is False and checkin in signatures:
        return blocked(start, "available_for_checkin", "checkin_not_allowed", "constraint_not_met")
    end = rows.get(checkout, {})
    if end.get("available_for_checkout") is False and checkout in signatures:
        return blocked(end, "available_for_checkout", "checkout_not_allowed", "constraint_not_met")
    if type(minimum) is int and nights < minimum and checkin in signatures:
        return blocked(start, "min_nights", "minimum_stay_not_met", "constraint_not_met")
    if type(maximum) is int and maximum > 0 and nights > maximum and checkin in signatures:
        return blocked(start, "max_nights", "maximum_stay_exceeded", "constraint_not_met")
    return unknown("no_proven_calendar_block")
