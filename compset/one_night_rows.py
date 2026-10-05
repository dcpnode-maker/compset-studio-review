"""Pure exact one-night totals from guest-verified public Sections responses.

A one-night stay total is not a base nightly rate. Rounded primary display
prices are deliberately excluded, and no amount is computed from line items.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
import re
from urllib.parse import urlsplit

from .normalize import PDP, _get, _listing_id, _money, _roots, _source, _valid_date

PARTY = {"adults": 1, "children": 0, "infants": 0, "pets": 0}
CONTEXT_FIELDS = ("listing_id", "checkin", "checkout", *PARTY, "currency")
HOSTS = {"airbnb.com", "www.airbnb.com", "airbnb.co.in", "www.airbnb.co.in"}


def _context(context):
    if not isinstance(context, dict):
        raise ValueError("A one-night quote context is required")
    start, end = _valid_date(context.get("checkin")), _valid_date(context.get("checkout"))
    if not start or not end or (date.fromisoformat(end) - date.fromisoformat(start)).days != 1:
        raise ValueError("Only an exact one-night interval is supported")
    identifier = _listing_id(context.get("listing_id"))
    if not identifier or not re.fullmatch(r"[A-Z]{3}", str(context.get("currency", ""))):
        raise ValueError("Listing identity and currency are required")
    if any(type(context.get(key)) is not int or context[key] != value for key, value in PARTY.items()):
        raise ValueError("Exactly one adult and zero other guests are required")
    return {**context, "listing_id": identifier}


def _verified(envelope, context):
    observed = envelope.get("request_context")
    if (not isinstance(observed, dict) or observed.get("conflicts")
            or envelope.get("request_context_conflicts")):
        return False
    if (_listing_id(observed.get("listing_id")) != context["listing_id"]
            or any(observed.get(key) != context[key] for key in ("checkin", "checkout", "currency"))):
        return False
    if any(type(observed.get(key)) is not int or observed[key] != value for key, value in PARTY.items()):
        return False
    # Amount punctuation and the observed explanation labels are currently English.
    if not re.fullmatch(r"en(?:-[A-Z]{2})?", str(observed.get("locale", ""))):
        return False
    try:
        url = urlsplit(envelope.get("source_url", ""))
        parts = url.path.split("/")
        return (url.scheme == "https" and url.hostname in HOSTS and url.port in (None, 443)
                and not url.username and not url.password and len(parts) in (4, 5)
                and parts[1:3] == ["api", "v3"] and parts[3] in {"StaysPdpSections", "PdpSections"})
    except (ValueError, TypeError):
        return False


def _positive(display, currency, locale):
    amount = _money(display, currency, locale)
    return amount if amount is not None and Decimal(amount) > 0 else None


def _total(item, currency, locale):
    """Return (exact amount, tax flag, inconsistency) for a semantic total line."""
    if not isinstance(item, dict):
        return None
    label = item.get("accessibilityLabel")
    label = label.strip() if isinstance(label, str) else ""
    explicit = re.fullmatch(r"(.+?)\s+total(?:\s+(before taxes))?", label, re.I)
    description = item.get("description")
    semantic = (item.get("__typename") == "HighlightExplanationLineItem"
                and isinstance(description, str)
                and re.fullmatch(r"(?:price after discount|total(?: before taxes)?)", description.strip(), re.I))
    if not explicit and not semantic:
        return None
    amount = _positive(item.get("priceString"), currency, locale)
    if amount is None:
        return None
    before_tax = bool(explicit and explicit[2]) or bool(
        semantic and re.fullmatch(r"total before taxes", description.strip(), re.I))
    conflict = False
    if explicit:
        accessible_amount = _positive(explicit[1], currency, locale)
        conflict = accessible_amount is None or Decimal(accessible_amount) != Decimal(amount)
    return amount, False if before_tax else None, conflict


def _option_id(value):
    return str(value) if type(value) in (str, int) and 0 < len(str(value)) <= 128 else None


def _rate_options(product, path, source, currency, locale):
    """Validate a declared selected plan without comparing different plans' prices."""
    selected_id = _option_id(product.get("selectedGuestOptionId"))
    raw = product.get("guestOptions")
    if not isinstance(raw, list) or not raw:
        return [], None, "rate_options_missing"
    options, invalid = [], False
    for index, option in enumerate(raw):
        if not isinstance(option, dict) or option.get("__typename") != "GuestOption":
            invalid = True
            continue
        identifier = _option_id(option.get("guestOptionId"))
        selected = option.get("isSelected") if type(option.get("isSelected")) is bool else None
        display = option.get("priceString")
        total = re.fullmatch(r"(.+?)\s+total", display.strip(), re.I) if isinstance(display, str) else None
        amount = _positive(total[1], currency, locale) if total else None
        title, subtitle = option.get("title"), option.get("subtitle")
        evidence = {**source, "source_path": f"{path}.guestOptions[{index}].priceString"}
        options.append({"rate_plan_id": identifier, "rate_plan": title if isinstance(title, str) and title else None,
                        "is_selected": selected, "amount": amount, "currency": currency,
                        "amount_kind": "one_night_stay_total", "status": "quoted" if amount else "unknown",
                        "cancellation_terms": subtitle if isinstance(subtitle, str) and subtitle else None,
                        "taxes_included": None, "fees_included": None, "source_url": evidence["source_url"],
                        "source_path": evidence["source_path"], "sources": [evidence],
                        "raw_options": [deepcopy(option)]})
        invalid = invalid or identifier is None or selected is None
    ids = [option["rate_plan_id"] for option in options]
    selected = [option for option in options if option["is_selected"] is True]
    if (invalid or not selected_id or len(ids) != len(set(ids)) or len(selected) != 1
            or selected[0]["rate_plan_id"] != selected_id):
        return options, None, "selected_rate_identity_conflict"
    if selected[0]["amount"] is None:
        return options, None, "selected_rate_amount_missing"
    return options, selected[0], None


def _merge_rate_options(observations):
    merged, conflicts = {}, False
    for option in observations:
        key = option["rate_plan_id"] or (option["sources"][0]["payload_index"], option["source_path"])
        if key not in merged:
            merged[key] = deepcopy(option)
            continue
        current = merged[key]
        different = any(current[field] != option[field] for field in
                        ("rate_plan", "is_selected", "cancellation_terms"))
        if current["amount"] is not None and option["amount"] is not None:
            different = different or Decimal(current["amount"]) != Decimal(option["amount"])
        if different:
            conflicts = True
            current.update(amount=None, status="unknown", reason="rate_option_conflict")
        elif current["amount"] is None and not current.get("reason"):
            current.update(amount=option["amount"], status=option["status"])
        current["sources"].extend(option["sources"])
        current["raw_options"].extend(option["raw_options"])
    return list(merged.values()), conflicts


def extract_one_night_quotes(payloads: list[dict], context: dict) -> list[dict]:
    """Extract exact totals, or one explicit unknown row if evidence conflicts.

    Missing prices, failed responses and unverified actual request context yield
    no quote. Input objects are never modified. Repeated matching totals retain
    all source evidence; a conflicting total is never silently selected.
    """
    context = _context(context)
    observations, problems, rate_observations, selected_plans = [], [], [], []
    for index, envelope in enumerate(payloads if isinstance(payloads, list) else []):
        if (not isinstance(envelope, dict) or type(envelope.get("status")) is not int
                or envelope["status"] != 200 or not _verified(envelope, context)):
            continue
        body = envelope.get("body")
        if not isinstance(body, dict) or body.get("errors"):
            continue
        observed = envelope["request_context"]
        for root, prefix in _roots(body):
            if root.get("errors"):
                continue
            if any(_get(root, key) is not None and _listing_id(_get(root, key)) != context["listing_id"]
                   for key in ("variables.id", "data.node.id")):
                continue
            for pdp_path in (PDP, "stayProductDetailPage.sections"):
                pdp = _get(root, pdp_path)
                if not isinstance(pdp, dict):
                    continue
                identifier = _get(pdp, "metadata.loggingContext.eventDataLogging.listingId")
                if identifier is not None and _listing_id(identifier) != context["listing_id"]:
                    continue
                wrappers = pdp.get("sections")
                for section_index, wrapper in enumerate(wrappers if isinstance(wrappers, list) else []):
                    if not isinstance(wrapper, dict) or wrapper.get("sectionId") != "BOOK_IT_SIDEBAR":
                        continue
                    section = wrapper.get("section")
                    if not isinstance(section, dict):
                        continue
                    section_path = f"{prefix}.{pdp_path}.sections[{section_index}].section"
                    display, product = section.get("structuredDisplayPrice"), section.get("productItemDetail")
                    containers = []
                    if isinstance(display, dict):
                        containers.append((display, section_path + ".structuredDisplayPrice"))
                    # Both observed product families carry an explicit selected
                    # total even when the display has only a unit-price line.
                    product_type = product.get("__typename") if isinstance(product, dict) else None
                    if product_type in {"BasicPriceDetail", "OptionalityPriceDetail"}:
                        containers.append((product, section_path + ".productItemDetail"))
                    if not containers:
                        continue
                    source = {**_source(envelope, section_path, context), "payload_index": index,
                              "observed_request_context": {key: observed[key] for key in (*CONTEXT_FIELDS, "locale")}}
                    qualifier = _get(display, "primaryLine.qualifier")
                    if isinstance(qualifier, dict):
                        qualifier = qualifier.get("text")
                    duration = re.fullmatch(r"(?:for )?(\d+) nights?", qualifier.strip(), re.I) if isinstance(qualifier, str) else None
                    if section.get("available") is False or duration and int(duration[1]) != 1:
                        problems.append({"reason": "source_unavailable" if section.get("available") is False else "response_stay_length_conflict",
                                         "source": source})
                        continue
                    observation_start = len(observations)
                    for container, path in containers:
                        groups = _get(container, "explanationData.priceDetails")
                        if not isinstance(groups, list):
                            continue
                        for group_index, group in enumerate(groups):
                            items = group.get("items") if isinstance(group, dict) else None
                            for item_index, item in enumerate(items if isinstance(items, list) else []):
                                parsed = _total(item, context["currency"], observed["locale"])
                                if parsed is None:
                                    continue
                                amount, taxes, conflict = parsed
                                evidence = {**source, "source_path": f"{path}.explanationData.priceDetails[{group_index}].items[{item_index}].priceString"}
                                observations.append({"amount": amount, "taxes_included": taxes, "source": evidence,
                                                     "raw_line_items": deepcopy(groups), "amount_display": item["priceString"]})
                                if conflict:
                                    problems.append({"reason": "exact_total_label_conflict", "source": evidence})
                    if product_type == "OptionalityPriceDetail":
                        options, selected_option, option_problem = _rate_options(
                            product, section_path + ".productItemDetail", source, context["currency"], observed["locale"])
                        rate_observations.extend(options)
                        if option_problem:
                            problems.append({"reason": option_problem, "source": source})
                        if selected_option:
                            selected_plans.append(selected_option)
                            semantic = observations[observation_start:]
                            if not semantic:
                                problems.append({"reason": "selected_rate_semantic_total_missing", "source": source})
                            elif any(Decimal(item["amount"]) != Decimal(selected_option["amount"]) for item in semantic):
                                problems.append({"reason": "selected_rate_total_conflict", "source": source})
                            # Only the selected option corroborates the main
                            # total. Other cancellation prices remain separate.
                            observations.append({"amount": selected_option["amount"], "taxes_included": None,
                                "source": selected_option["sources"][0],
                                "raw_line_items": deepcopy(_get(product, "explanationData.priceDetails") or []),
                                "amount_display": selected_option["raw_options"][0]["priceString"]})
    if not observations and not problems:
        return []
    amounts = {Decimal(item["amount"]) for item in observations}
    if len(amounts) > 1:
        problems.append({"reason": "conflicting_exact_totals"})
    rate_options, option_conflict = _merge_rate_options(rate_observations)
    if option_conflict:
        problems.append({"reason": "rate_option_conflict"})
    if len({option["rate_plan_id"] for option in selected_plans}) > 1:
        problems.append({"reason": "selected_rate_identity_conflict"})
    sources = [item["source"] for item in observations]
    sources += [item["source"] for item in problems if "source" in item and item["source"] not in sources]
    selected = observations[0] if observations else None
    selected_plan = selected_plans[0] if selected_plans and not problems else None
    reason = "conflicting_exact_totals" if len(amounts) > 1 else problems[0]["reason"] if problems else None
    row = {key: context[key] for key in CONTEXT_FIELDS}
    row.update(amount=None if problems else selected["amount"], amount_kind="one_night_stay_total",
               status="unknown" if problems else "quoted", reason=reason, guest_context_verified=True,
               taxes_included=None if problems else next((item["taxes_included"] for item in observations
                                                         if item["taxes_included"] is not None), None),
               fees_included=None, cancellation_terms=selected_plan["cancellation_terms"] if selected_plan else None,
               rate_plan_id=selected_plan["rate_plan_id"] if selected_plan else None,
               rate_plan=selected_plan["rate_plan"] if selected_plan else None, rate_options=rate_options,
               base_amount=None, taxes_amount=None,
               cleaning_fee_amount=None, source_label="Airbnb observed Sections response",
               source_url=sources[0]["source_url"], source_path=None if problems else selected["source"]["source_path"],
               observed_at=context.get("observed_at"), http_status=200, sources=sources,
               raw_line_items=[] if problems else selected["raw_line_items"],
               price_observations=observations, warnings=sorted({item["reason"] for item in problems}))
    return [row]
