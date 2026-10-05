"""Conservative Airbnb response normalization; no network access.

Schema references: johnbalvin/pyairbnb calendarinfo.py, models/calendar.py,
standardize.py and price.py (inspected 2026-09-28). This implementation is
independent: retain unknowns and evidence instead of guessing changed contracts.
"""
from __future__ import annotations

import base64
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit

CALENDAR = "data.merlin.pdpAvailabilityCalendar.calendarMonths"
PDP = "data.presentation.stayProductDetailPage.sections"
CONTEXT = ("listing_id", "checkin", "checkout", "adults", "children", "infants",
           "pets", "currency", "locale", "observed_at")


def _get(obj, path, default=None):
    for key in path.split("."):
        if not isinstance(obj, dict) or key not in obj:
            return default
        obj = obj[key]
    return obj


def _items(value):
    return value if isinstance(value, list) else []


def _text(value):
    return value if isinstance(value, str) else None


def _boolean(value):
    return value if type(value) is bool else None


def _integer(value):
    return value if type(value) is int and value >= 0 else None


def _valid_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _money(value, currency, locale):
    """Parse a single amount in a known locale; reject ambiguous/mixed currencies."""
    if not isinstance(value, str) or not currency:
        return None
    value = unicodedata.normalize("NFKC", value)
    if "د.إ" in value:
        if currency != "AED":
            return None
        value = value.replace("د.إ", "AED")
    codes = re.findall(r"\b[A-Z]{3}\b", value)
    if any(code != currency for code in codes):
        return None
    symbols = {"€": {"EUR"}, "£": {"GBP"}, "₹": {"INR"}, "¥": {"JPY", "CNY"},
               "$": {"USD", "CAD", "AUD", "NZD", "HKD", "SGD", "MXN", "ARS", "CLP", "COP", "TWD"}}
    if any(symbol in value and currency not in allowed for symbol, allowed in symbols.items()):
        return None
    number = re.sub(r"[A-Z]{3}|[$€£¥₹]|[\s\u00a0\u202f]", "", value)
    lang = str(locale or "").split("-")[0].lower()
    comma_decimal = lang in {"de", "es", "fr", "it", "pt", "nl"}
    if comma_decimal:
        pattern = r"-?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,3})?"
        number = number.replace(".", "").replace(",", ".") if re.fullmatch(pattern, number) else ""
    elif lang == "en":
        pattern = r"-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,3})?"
        number = number.replace(",", "") if re.fullmatch(pattern, number) else ""
    else:
        return None
    try:
        result = Decimal(number)
        return format(result, "f") if result.is_finite() else None
    except InvalidOperation:
        return None


def _source(envelope, path, context):
    # Query strings can contain opaque session identifiers; preserve URL path only.
    try:
        url = urlsplit(str(envelope.get("source_url", "")))
        source_url = urlunsplit((url.scheme, url.hostname or "", url.path, "", ""))
    except ValueError:
        source_url = ""
    return {"source_url": source_url,
            "source_path": path, "http_status": envelope.get("status"),
            "observed_at": context.get("observed_at")}


def _roots(body):
    """Known hydration wrapper, including all responses rather than just index 0."""
    if not isinstance(body, dict):
        return
    yield body, "$"
    for index, entry in enumerate(_items(body.get("niobeClientData"))):
        if isinstance(entry, list) and len(entry) > 1 and isinstance(entry[1], dict):
            yield entry[1], f"$.niobeClientData[{index}][1]"


def _listing_id(value):
    if value is None or type(value) is bool:
        return None
    text = str(value)
    if text.isdigit():
        return text
    try:
        decoded = base64.b64decode(text, validate=True).decode()
        if re.fullmatch(r"(?:StayListing|DemandStayListing):\d+", decoded):
            return decoded.split(":")[1]
    except (ValueError, UnicodeError):
        pass
    return None


def _parse_calendar(root, prefix, envelope, context, rows, warnings):
    months = _get(root, CALENDAR)
    if months is None:
        return
    if not isinstance(months, list):
        warnings.append(f"{prefix}.{CALENDAR}: expected calendar month list")
        return
    for mi, month in enumerate(months):
        if not isinstance(month, dict):
            continue
        month_id = _listing_id(month.get("listingId"))
        if month_id is not None and month_id != str(context.get("listing_id")):
            warnings.append(f"Calendar listing mismatch: {month_id}")
            continue
        day_key = "days" if "days" in month else "calendarDays"
        for di, day in enumerate(_items(month.get(day_key))):
            if not isinstance(day, dict):
                continue
            path = f"{prefix}.{CALENDAR}[{mi}].{day_key}[{di}]"
            day_date = _valid_date(day.get("calendarDate"))
            if day_date is None:
                warnings.append(f"{path}: missing or invalid calendarDate")
                continue
            if context.get("start_date") and day_date < context["start_date"]:
                continue
            if context.get("end_date") and day_date >= context["end_date"]:
                continue
            available = _boolean(day.get("available"))
            if available is None:
                warnings.append(f"{path}.available: missing or non-boolean; unknown")
            display = _text(_get(day, "price.localPriceFormatted"))
            row = {"listing_id": str(context.get("listing_id")), "date": day_date,
                   "available": available, "availability": "unknown" if available is None else
                   ("available" if available else "unavailable"),
                   "price_display": display, "price_amount": _money(display, context.get("currency"), context.get("locale")),
                   "currency": context.get("currency"), **_source(envelope, path, context)}
            for source, target in (("availableForCheckin", "available_for_checkin"),
                                   ("availableForCheckout", "available_for_checkout"), ("bookable", "bookable")):
                row[target] = _boolean(day.get(source))
            row.update(min_nights=_integer(day.get("minNights")), max_nights=_integer(day.get("maxNights")))
            old = rows.get(day_date)
            if old and old["available"] is not None and available is not None and old["available"] != available:
                warnings.append(f"Conflicting calendar observations for {day_date}; retained last observed response")
            # A malformed duplicate must not erase a typed availability observation.
            if not old or available is not None or old["available"] is None:
                rows[day_date] = row


def _parse_listing(pdp, prefix, envelope, context, listing):
    def set_value(key, value, path):
        if value is not None and value != "" and value != []:
            listing[key] = value
            listing["field_sources"][key] = _source(envelope, path, context)

    event_path = "metadata.loggingContext.eventDataLogging"
    event = _get(pdp, event_path, {})
    fields = {"roomType": "room_type", "personCapacity": "person_capacity",
              "listingLat": "latitude", "listingLng": "longitude",
              "guestSatisfactionOverall": "rating", "visibleReviewCount": "review_count",
              "bedrooms": "bedrooms", "beds": "beds", "bathrooms": "bathrooms"}
    for raw, key in fields.items():
        value = event.get(raw) if isinstance(event, dict) else None
        if isinstance(value, (str, int, float)) and type(value) is not bool:
            set_value(key, value, f"{prefix}.{event_path}.{raw}")
    # Current bootstrap responses contain public details in metadata while their
    # title/overview sections are placeholders. These paths were observed live.
    sharing = _get(pdp, "metadata.sharingConfig", {})
    if isinstance(sharing, dict):
        set_value("property_type", _text(sharing.get("propertyType")), f"{prefix}.metadata.sharingConfig.propertyType")
        if "person_capacity" not in listing:
            set_value("person_capacity", _integer(sharing.get("personCapacity")), f"{prefix}.metadata.sharingConfig.personCapacity")
        summary = _text(sharing.get("title"))
        set_value("property_summary", summary, f"{prefix}.metadata.sharingConfig.title")
        if summary and str(context.get("locale", "")).startswith("en"):
            for unit, key in (("bedroom", "bedrooms"), ("bed", "beds"), ("bathroom", "bathrooms")):
                match = re.search(r"\b(\d+(?:\.\d+)?) " + unit + r"s?\b", summary, re.I)
                if match and key not in listing:
                    value = Decimal(match[1])
                    set_value(key, int(value) if value == value.to_integral_value() else float(value),
                              f"{prefix}.metadata.sharingConfig.title")
    if "title" not in listing:
        set_value("title", _text(_get(pdp, "metadata.seoFeatures.ogTags.ogDescription")),
                  f"{prefix}.metadata.seoFeatures.ogTags.ogDescription")
    sections = [(item, f"{prefix}.sections[{index}].section")
                for index, item in enumerate(_items(pdp.get("sections")))]
    sections += [(item, f"{prefix}.sbuiData.sectionConfiguration.root.sections[{index}].sectionData")
                 for index, item in enumerate(_items(_get(pdp, "sbuiData.sectionConfiguration.root.sections")))]
    for wrapper, path in sections:
        if not isinstance(wrapper, dict):
            continue
        data = wrapper.get("section", wrapper.get("sectionData", {}))
        if not isinstance(data, dict):
            continue
        kind = data.get("__typename")
        if kind == "PdpTitleSection":
            set_value("title", _text(data.get("title")), path + ".title")
        elif kind == "PdpOverviewV2Section":
            set_value("property_summary", _text(data.get("title")), path + ".title")
            set_value("overview", [_text(item.get("title")) for item in _items(data.get("overviewItems"))
                                   if isinstance(item, dict) and _text(item.get("title"))], path + ".overviewItems")
        elif kind == "AmenitiesSection":
            amenities = []
            for group in _items(data.get("seeAllAmenitiesGroups")):
                for item in _items(group.get("amenities")) if isinstance(group, dict) else []:
                    if isinstance(item, dict) and isinstance(item.get("title"), str):
                        amenities.append({"title": item["title"], "available": _boolean(item.get("available"))})
            set_value("amenities", amenities, path + ".seeAllAmenitiesGroups")


def _parse_amenities(root, prefix, envelope, context, listing):
    path = "data.node.pdpPresentation.amenities.seeAllAmenitiesGroups"
    groups = _get(root, path)
    if not isinstance(groups, list):
        return
    values = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        for item in _items(group.get("amenities")):
            if isinstance(item, dict) and isinstance(item.get("title"), str):
                amenity = {"title": item["title"], "available": _boolean(item.get("available"))}
                if isinstance(item.get("icon"), str):
                    amenity["icon"] = item["icon"]
                if isinstance(item.get("id"), str):
                    # This is listing-scoped evidence, not a global search filter ID.
                    amenity["source_id"] = item["id"]
                values.append(amenity)
    if values:
        listing["amenities"] = values
        listing["field_sources"]["amenities"] = _source(envelope, f"{prefix}.{path}", context)


def _parse_modern_listing(root, prefix, envelope, context, listing):
    """Public presentation attributes observed in the current HTTP bootstrap.

    Host identifiers/display names are authorized by Order003. Never copy host
    biographies, contact fields or infer shared operators from a display name.
    """
    path = "data.node.pdpPresentation"
    data = _get(root, path)
    if not isinstance(data, dict):
        return

    def put(key, value, suffix):
        if value is not None and value != "" and value != []:
            listing[key] = value
            listing["field_sources"][key] = _source(envelope, f"{prefix}.{path}.{suffix}", context)

    def count(value):
        if type(value) is int and value >= 0:
            return value
        if isinstance(value, str) and re.fullmatch(r"\d+", value):
            return int(value)
        return None

    def number(value, low, high):
        if type(value) not in (int, float):
            return None
        return value if low <= value <= high else None

    put("title", _text(_get(data, "title.content.localizedStringWithTranslationPreference")),
        "title.content.localizedStringWithTranslationPreference")
    put("person_capacity", _integer(data.get("personCapacity")), "personCapacity")
    put("property_type", _text(_get(data, "sharingConfig.propertyType")), "sharingConfig.propertyType")
    put("latitude", number(_get(data, "location.latitude"), -90, 90), "location.latitude")
    put("longitude", number(_get(data, "location.longitude"), -180, 180), "location.longitude")
    put("location_is_exact", _boolean(_get(data, "location.isExactLocation")), "location.isExactLocation")
    put("location_name", _text(data.get("localizedLocation")), "localizedLocation")
    summary_path = "sharingConfig.ugcTitle.content.localizedStringWithTranslationPreference"
    put("property_summary", _text(_get(data, summary_path)), summary_path)
    overview = [item for item in _items(_get(data, "overview.items")) if isinstance(item, str)]
    put("overview", overview, "overview.items")
    if str(context.get("locale", "")).startswith("en"):
        for index, item in enumerate(overview):
            match = re.fullmatch(r"(\d+(?:\.\d+)?) (bedrooms?|beds?|bathrooms?|guests?)", item, re.I)
            if match:
                unit = match[2].lower().rstrip("s")
                key = {"bedroom": "bedrooms", "bed": "beds", "bathroom": "bathrooms", "guest": "person_capacity"}[unit]
                # personCapacity is typed and takes priority over a translated label.
                if key == "person_capacity" and _integer(data.get("personCapacity")) is not None:
                    continue
                value = Decimal(match[1])
                put(key, int(value) if value == value.to_integral_value() else float(value), f"overview.items[{index}]")
    rating_path = "quality.listingRatingStats.overallRatingStats"
    review_count = count(_get(data, rating_path + ".ratingCount"))
    put("review_count", review_count, rating_path + ".ratingCount")
    rating = number(_get(data, rating_path + ".ratingAverage"), 0, 5)
    # A zero count and zero rating are an unrated listing, not a zero-star review.
    if review_count == 0:
        listing.pop("rating", None)
        listing["field_sources"].pop("rating", None)
        put("rating_status", "unrated", rating_path + ".ratingCount")
    elif rating is not None and rating > 0:
        put("rating", rating, rating_path + ".ratingAverage")
        put("rating_status", "rated", rating_path + ".ratingAverage")
    host = data.get("hostInfo")
    if not isinstance(host, dict):
        return
    passport = host.get("passportData")
    passport = passport if isinstance(passport, dict) else {}
    user_id = passport.get("userId")
    if isinstance(user_id, str):
        try:
            decoded = user_id if user_id.isdigit() else base64.b64decode(user_id, validate=True).decode("ascii")
            match = re.fullmatch(r"(?:(?:DemandUser|User):)?(\d+)", decoded)
            put("host_id", match[1] if match else None, "hostInfo.passportData.userId")
        except (ValueError, UnicodeError):
            pass
    put("host_name", _text(passport.get("name")), "hostInfo.passportData.name")
    listing.setdefault("host_listing_count", None)
    listing.setdefault("host_is_professional", None)
    # These must be explicitly disclosed. Reviews, years hosting and isVerified
    # are deliberately excluded; none measures a host's portfolio or profession.
    for suffix in ("hostInfo.listingCount", "hostInfo.passportData.listingCount"):
        put("host_listing_count", count(_get(data, suffix)), suffix)
    for index, stat in enumerate(_items(passport.get("stats"))):
        if isinstance(stat, dict) and stat.get("type") == "LISTING_COUNT":
            put("host_listing_count", count(stat.get("value")), f"hostInfo.passportData.stats[{index}].value")
    put("host_is_professional", _boolean(host.get("isProfessionalHost")), "hostInfo.isProfessionalHost")
    if str(context.get("locale", "")).startswith("en") and listing["host_is_professional"] is None:
        for index, item in enumerate(_items(_get(host, "overview.items"))):
            if isinstance(item, dict) and item.get("text") == "Professional host":
                put("host_is_professional", True, f"hostInfo.overview.items[{index}].text")


def _parse_quotes(pdp, prefix, envelope, context, quotes):
    if not _valid_date(context.get("checkin")) or not _valid_date(context.get("checkout")):
        return
    if context["checkout"] <= context["checkin"]:
        return
    for index, wrapper in enumerate(_items(pdp.get("sections"))):
        if not isinstance(wrapper, dict) or wrapper.get("sectionId") != "BOOK_IT_SIDEBAR":
            continue
        data = wrapper.get("section", {})
        if not isinstance(data, dict):
            continue
        price = data.get("structuredDisplayPrice")
        path = f"{prefix}.sections[{index}].section"
        _parse_price_options(data.get("productItemDetail"), path + ".productItemDetail", envelope, context, quotes)
        available = _boolean(data.get("available"))
        message = _text(data.get("localizedUnavailabilityMessage"))
        if not isinstance(price, dict):
            if available is not None or message:
                row = {key: context.get(key) for key in CONTEXT}
                row.update(status="unavailable" if available is False else "no_price",
                           quote_kind="stay_availability",
                           available=available, unavailability_message=message,
                           display_amount=None, total_amount=None, price_display=None,
                           price_basis="unknown", qualifier=None, taxes_included=None,
                           fees_included=None, line_items=[], **_source(envelope, path, context))
                quotes.append(row)
            continue
        primary = price.get("primaryLine", {})
        if not isinstance(primary, dict):
            continue
        display = next((_text(primary.get(key)) for key in ("discountedPrice", "price", "originalPrice")
                        if _text(primary.get(key))), None)
        qualifier = primary.get("qualifier")
        qualifier = qualifier.get("text") if isinstance(qualifier, dict) else qualifier
        qualifier = _text(qualifier)
        basis = "unknown"
        if qualifier and str(context.get("locale", "")).startswith("en"):
            duration = re.fullmatch(r"(?:for )?(\d+) nights?", qualifier.strip(), re.I)
            nights = (date.fromisoformat(context["checkout"]) - date.fromisoformat(context["checkin"])).days
            if ((duration and int(duration[1]) == nights) or
                    re.fullmatch(r"total(?: before taxes)?", qualifier.strip(), re.I)):
                basis = "stay_total"
            elif re.fullmatch(r"(?:per |a |/\s*)?night", qualifier.strip(), re.I):
                basis = "nightly_display"
        amount = _money(display, context.get("currency"), context.get("locale"))
        row = {key: context.get(key) for key in CONTEXT}
        row.update(display_amount=amount, price_display=display, qualifier=qualifier, price_basis=basis,
                   quote_kind="display_price", amount_precision="display",
                   status="unavailable" if available is False else ("quoted" if amount is not None else "no_price"),
                   available=available, unavailability_message=message,
                   total_amount=None, display_total_amount=amount if basis == "stay_total" else None,
                   taxes_included=False if qualifier and "before taxes" in qualifier.lower() else None,
                   fees_included=None, line_items=[], **_source(envelope, path + ".structuredDisplayPrice", context))
        for detail in _items(_get(price, "explanationData.priceDetails")):
            for item in _items(detail.get("items")) if isinstance(detail, dict) else []:
                if isinstance(item, dict):
                    text = _text(item.get("priceString"))
                    row["line_items"].append({"description": _text(item.get("description")),
                                              "price_display": text, "amount": _money(text, context.get("currency"), context.get("locale"))})
        quotes.append(row)


def _parse_price_options(item, path, envelope, context, quotes):
    """Rate-plan totals are independent of the rounded marketing display line."""
    if not isinstance(item, dict) or item.get("__typename") != "OptionalityPriceDetail":
        return
    if not _valid_date(context.get("checkin")) or not _valid_date(context.get("checkout")):
        return
    if context["checkout"] <= context["checkin"]:
        return
    for index, option in enumerate(_items(item.get("guestOptions"))):
        if not isinstance(option, dict) or option.get("__typename") != "GuestOption":
            continue
        display = _text(option.get("priceString"))
        amount = None
        if display and str(context.get("locale", "")).startswith("en"):
            total = re.fullmatch(r"(.+?)\s+total", display, re.I)
            if total:
                amount = _money(total[1], context.get("currency"), context.get("locale"))
        row = {key: context.get(key) for key in CONTEXT}
        row.update(quote_kind="rate_plan_total", status="quoted" if amount is not None else "no_price",
                   rate_plan=_text(option.get("title")), rate_plan_id=_text(option.get("guestOptionId")),
                   is_selected=_boolean(option.get("isSelected")),
                   selected_rate_plan_id=_text(item.get("selectedGuestOptionId")),
                   cancellation_summary=_text(option.get("subtitle")),
                   total_amount=amount, display_amount=None, price_display=display,
                   amount_precision="source_amount", price_basis="stay_total" if amount is not None else "unknown",
                   taxes_included=None, fees_included=None, line_items=[],
                   **_source(envelope, f"{path}.guestOptions[{index}].priceString", context))
        # Replay and sidebar often repeat the same option; retain all provenance.
        evidence_keys = {"source_url", "source_path", "http_status", "sources"}
        comparable = {key: value for key, value in row.items() if key not in evidence_keys}
        match = next((existing for existing in quotes if
                      {key: value for key, value in existing.items() if key not in evidence_keys} == comparable), None)
        if match is None:
            quotes.append(row)
        else:
            source = _source(envelope, f"{path}.guestOptions[{index}].priceString", context)
            sources = match.setdefault("sources", [{key: match[key] for key in source}])
            if source not in sources:
                sources.append(source)


def normalize(payloads: list[dict], context: dict) -> dict:
    """Return public descriptors, observed days and stay quotes with provenance.

    Calendar context is [start_date, end_date). Missing dates remain absent;
    callers must report coverage. A response's observed request_context overrides
    run defaults (legacy context is accepted when request_context is absent).
    """
    listing = {"listing_id": str(context.get("listing_id")), "field_sources": {}}
    calendar, quotes, warnings = {}, [], []
    for envelope in payloads:
        if not isinstance(envelope, dict):
            continue
        status = envelope.get("status")
        if type(status) is not int or not 200 <= status < 300:
            warnings.append(f"Ignored response with HTTP status {status!r}")
            continue
        request_context = dict(context)
        supplied_context = envelope.get("request_context")
        if not isinstance(supplied_context, dict):
            supplied_context = envelope.get("context")
        if isinstance(supplied_context, dict):
            request_context.update({k: v for k, v in supplied_context.items() if k in CONTEXT})
        if str(request_context.get("listing_id")) != str(context.get("listing_id")):
            warnings.append("Ignored response for a different listing")
            continue
        for root, prefix in _roots(envelope.get("body")):
            if root.get("errors"):
                warnings.append(f"{prefix}: GraphQL errors; response not normalized")
                continue
            root_id = _listing_id(_get(root, "variables.id")) or _listing_id(_get(root, "data.node.id"))
            if root_id is not None and root_id != str(context.get("listing_id")):
                warnings.append(f"{prefix}: response body listing mismatch: {root_id}")
                continue
            _parse_calendar(root, prefix, envelope, request_context, calendar, warnings)
            _parse_amenities(root, prefix, envelope, request_context, listing)
            options_path = "data.node.pdpPresentation.bookIt.productItemDetail"
            _parse_price_options(_get(root, options_path), f"{prefix}.{options_path}", envelope, request_context, quotes)
            for pdp_path in (PDP, "stayProductDetailPage.sections"):
                pdp = _get(root, pdp_path)
                if isinstance(pdp, dict):
                    metadata_id = _listing_id(_get(pdp, "metadata.loggingContext.eventDataLogging.listingId"))
                    if metadata_id is not None and metadata_id != str(context.get("listing_id")):
                        warnings.append(f"{prefix}.{pdp_path}: metadata listing mismatch: {metadata_id}")
                        continue
                    _parse_listing(pdp, f"{prefix}.{pdp_path}", envelope, request_context, listing)
                    _parse_quotes(pdp, f"{prefix}.{pdp_path}", envelope, request_context, quotes)
            _parse_modern_listing(root, prefix, envelope, request_context, listing)
    if not calendar:
        warnings.append("No recognized calendar observations; availability coverage is unknown")
    else:
        priced = sum(row.get("price_amount") is not None for row in calendar.values())
        if priced < len(calendar):
            warnings.append(f"Calendar nightly prices recognized for {priced}/{len(calendar)} observed dates; remaining nightly prices are unknown")
    if not quotes:
        warnings.append("No recognized dated stay quote")
    quotes.sort(key=lambda row: (0 if row.get("quote_kind") == "rate_plan_total" and row.get("is_selected") is True
                                else 1 if row.get("quote_kind") == "rate_plan_total" else 2))
    return {"listing": listing, "calendar": [calendar[key] for key in sorted(calendar)], "quotes": quotes, "warnings": warnings}
