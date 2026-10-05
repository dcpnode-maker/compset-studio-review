"""Evidence-preserving BnBMe catalogue and channel inventory snapshots."""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3

from .pipeline import DATA, canonical, export_csv, _write_json

SCHEMA_VERSION = "bnbme-inventory-1"


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _amount(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        amount = Decimal(str(value))
        return format(amount, "f") if amount.is_finite() and amount > 0 else None
    except InvalidOperation:
        return None


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return str(date.fromisoformat(value))
    except (TypeError, ValueError):
        return None


def _amenities(groups):
    result = []
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            continue
        for item in group.get("amenities", []):
            if isinstance(item, dict) and item.get("name"):
                result.append({"title": item["name"], "code": item.get("code"),
                               "category": item.get("category", group.get("category")),
                               "available": True, "source": "official_catalogue"})
    return result


def normalize_property(raw, source):
    """Keep every source attribute; search prices are explicitly non-final."""
    from .profile import enrich_subject_profile
    identifier = str(raw.get("id", ""))
    if not identifier or identifier == "None":
        raise ValueError("Official property is missing its public identifier")
    location, detail = raw.get("location") or {}, raw.get("details") or {}
    full, half = _number(detail.get("bathroom_full")), _number(detail.get("bathroom_half"))
    # The source's available_bathrooms counts rooms, not fractional equivalents.
    bathrooms = full + half / 2 if full is not None and half is not None else _number(detail.get("available_bathrooms"))
    quotes = []
    for field, rate in (("non_refundable_price", "non_refundable"), ("refundable_price", "refundable")):
        amount = _amount(raw.get(field))
        if amount is None:
            continue
        quotes.append({"quote_kind": "search_display", "price_basis": "unspecified_search_price",
                       "display_amount": amount, "total_amount": None, "currency": raw.get("currency"),
                       "checkin": _date(raw.get("from_date")), "checkout": _date(raw.get("to_date")),
                       "adults": None, "rate_plan": rate, "status": "display_only",
                       "taxes_and_fees_included": None, "observed_at": source["observed_at"],
                       "source_url": source["source_url"], "source_path": f"data[id={identifier}].{field}"})
    row = {"property_id": identifier, "property_uuid": raw.get("property_details_uuid"),
           "platform": "bnbme_direct", "title": raw.get("title"),
           "property_code": raw.get("property_details_name"), "slug": raw.get("slug"),
           "source_url": source["source_url"], "city": location.get("city"),
           "country": location.get("country"), "area": location.get("area"),
           "latitude": _number(location.get("latitude")), "longitude": _number(location.get("longitude")),
           "bedrooms": _number(detail.get("bedrooms")), "beds": _number(detail.get("available_beds")),
           "bathrooms": bathrooms, "bathrooms_source_count": _number(detail.get("available_bathrooms")),
           "person_capacity": _number(detail.get("guests")), "currency": raw.get("currency"),
           "rating": _number(detail.get("rating")), "rating_source": "official_site",
           "review_count": None, "amenities": _amenities(raw.get("amenities")),
           "description": raw.get("description"), "attributes": deepcopy(raw),
           "operator_name": "bnbme homes", "operator_source_url": "https://bnbmehomes.com/",
           "publication_status": "published_in_public_catalogue", "bookability": "not_verified",
           "airbnb_listing_id": None, "host_id": None, "host_name": None, "host_profile_url": None,
           "link_status": "unresolved", "quotes": quotes, "observed_at": source["observed_at"],
           "field_sources": {key: {"source_url": source["source_url"], "observed_at": source["observed_at"],
                                  "source_path": f"data[id={identifier}].{key}"} for key in raw}}
    return enrich_subject_profile(row)


def normalize_detail_observation(item):
    """Normalize only the observed official website calendar/charge contracts."""
    result = deepcopy(item)
    result["raw_quotes"] = deepcopy(item.get("quotes", []))
    result["quotes"], result["calendar"] = [], []
    context = item.get("context") or {}
    for quote in item.get("quotes", []):
        if quote.get("quote_kind"):
            result["quotes"].append(deepcopy(quote))
            continue
        body = quote.get("body") or {}
        quote_context = quote.get("context") or context
        if (isinstance(body, dict) and body.get("message") == "SOLD_OUT"
                and _date(quote_context.get("checkin")) and _date(quote_context.get("checkout"))):
            result["quotes"].append({"quote_kind": "website_stay_unavailable", "price_basis": "stay_total",
                "status": "unavailable", "total_amount": None, "currency": quote_context.get("currency"),
                "checkin": quote_context["checkin"], "checkout": quote_context["checkout"],
                "adults": quote_context.get("adults"), "price_endpoint_guest_parameter": False,
                "source_message": "SOLD_OUT", "source_url": quote.get("source_url"), "source_path": "message",
                "observed_at": quote.get("observed_at", item.get("observed_at")),
                "meaning": "The source declined this complete stay; no individual night is inferred."})
            continue
        data = body.get("data") or {} if isinstance(body, dict) else {}
        final = data.get("after_discount") if isinstance(data, dict) else None
        if not isinstance(final, dict) or not _amount(final.get("total")):
            continue
        source_url = quote.get("source_url")
        if (not _date(quote_context.get("checkin")) or not _date(quote_context.get("checkout"))
                or not source_url or not quote.get("observed_at", item.get("observed_at"))):
            continue
        nights = (date.fromisoformat(quote_context["checkout"]) - date.fromisoformat(quote_context["checkin"])).days
        if type(final.get("total_nights")) not in (int, float) or final["total_nights"] != nights or nights <= 0:
            continue
        result["quotes"].append({"quote_kind": "website_stay_total", "price_basis": "stay_total",
            "status": "price_returned_availability_separate", "total_amount": _amount(final["total"]),
            "currency": quote_context.get("currency", context.get("currency")),
            "checkin": quote_context["checkin"], "checkout": quote_context["checkout"],
            "adults": quote_context.get("adults"), "price_endpoint_guest_parameter": False,
            "rate_plan": "non_refundable", "breakdown": deepcopy(final),
            "observed_at": quote.get("observed_at", item.get("observed_at")), "source_url": source_url,
            "source_path": "data.after_discount.total", "taxes_and_fees_included": True})
    inventory = item.get("inventory") or {}
    days = (inventory.get("body") or {}).get("data") or {}
    expected_uuid = (item.get("attributes") or {}).get("property_details_uuid")
    inventory_context = inventory.get("context") or {}
    for day, values in days.items() if isinstance(days, dict) else []:
        if not _date(day) or not isinstance(values, list):
            continue
        for record in values:
            if (not isinstance(record, dict) or record.get("property_id") is not None and str(record["property_id"]) != str(item.get("property_id"))
                    or record.get("calendar_date") != day
                    or expected_uuid is not None and record.get("property_details_uuid") != expected_uuid
                    or record.get("property_id") is None and (expected_uuid is None or record.get("property_details_uuid") != expected_uuid)):
                continue
            placeholder = "inventory_uuid" in record and record["inventory_uuid"] is None
            count = None if placeholder else _number(record.get("available_room"))
            count = count if count is not None and count >= 0 and count.is_integer() else None
            availability = "unknown" if count is None else "available" if count > 0 else "unavailable"
            result["calendar"].append({"date": day, "room_id": record.get("room_id"),
                "availability": availability, "available_room": int(count) if count is not None else None,
                "non_refundable_price": _amount(record.get("non_refundable_price")),
                "refundable_price": _amount(record.get("refundable_price")),
                "currency": inventory_context.get("currency", context.get("currency")),
                "price_basis": "website_calendar_rate", "status": record.get("status"),
                "observed_at": inventory.get("observed_at"), "source_url": inventory.get("source_url"),
                "source_path": f"data.{day}[room_id={record.get('room_id')}]",
                "reason": "inventory_record_missing" if placeholder else "public_inventory_count" if count is not None else "inventory_count_unknown"})
    return result


def build_inventory(catalog, *, airbnb_listings=None, hosts=None, links=None, supplements=None):
    if not isinstance(catalog.get("properties"), list):
        raise ValueError("Expected a properties array from the official catalogue")
    properties = [normalize_property(row, catalog) for row in catalog["properties"]]
    ids = [row["property_id"] for row in properties]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate official property identifiers must be resolved before ingestion")
    airbnb_listings, hosts = deepcopy(airbnb_listings or []), deepcopy(hosts or [])
    channel_ids = [str(row.get("listing_id", "")) for row in airbnb_listings]
    if any(not identifier or identifier == "None" for identifier in channel_ids) or len(channel_ids) != len(set(channel_ids)):
        raise ValueError("Airbnb listing identifiers must be present and unique")
    channels = {str(row["listing_id"]): row for row in airbnb_listings}
    verified_links = []
    by_id = {row["property_id"]: row for row in properties}
    for link in links or []:
        # Only an explicit source cross-reference qualifies. Similar names do not.
        if link.get("status") != "verified" or not link.get("evidence_url") or not link.get("source_path"):
            continue
        row = by_id.get(str(link.get("property_id")))
        channel = channels.get(str(link.get("airbnb_listing_id")))
        if row is None or channel is None:
            continue
        row.update(airbnb_listing_id=str(channel["listing_id"]), host_id=channel.get("host_id"),
                   host_name=channel.get("host_name"), host_profile_url=channel.get("host_profile_url"), link_status="verified")
        verified_links.append(deepcopy(link))
    # Detail/price supplements retain their original response and context. Only
    # already-normalized, explicit verified quotes may set dated bookability.
    for item in supplements or []:
        row = by_id.get(str(item.get("property_id")))
        if row is None:
            continue
        row.setdefault("detail_observations", []).append(deepcopy(item))
        raw_attributes = item.get("attributes") or {}
        if (raw_attributes.get("id") is not None and str(raw_attributes["id"]) != row["property_id"]
                or raw_attributes.get("property_details_uuid") is not None
                and raw_attributes["property_details_uuid"] != row["property_uuid"]):
            row.setdefault("observation_warnings", []).append("Detail identity did not match the catalogue; derived fields were not imported.")
            continue
        item = normalize_detail_observation(item)
        attributes = item.get("attributes") or {}
        if str(attributes.get("id")) == row["property_id"] and attributes.get("property_details_uuid") == row["property_uuid"]:
            observed = normalize_property(attributes, item)
            mapped_fields = set()
            for key in ("title", "description", "latitude", "longitude", "bedrooms", "beds", "bathrooms",
                        "bathrooms_source_count", "person_capacity", "rating", "amenities", "city", "country", "area"):
                if key == "amenities" and not isinstance(attributes.get("amenities"), list):
                    continue
                if observed.get(key) is not None and observed.get(key) != "":
                    row[key] = observed[key]
                    mapped_fields.add(key)
            row["detail_attributes"] = deepcopy(attributes)
            row["public_property_url"] = item.get("source_url")
            if attributes.get("status") in {"ACTIVE", "INACTIVE"}:
                row["publication_status"] = attributes["status"].lower() + "_in_public_details"
                mapped_fields.add("publication_status")
            row["details_observed_at"] = item.get("observed_at")
            details = attributes.get("details") or {}
            bathroom_path = "details.bathroom_full+details.bathroom_half/2" if _number(details.get("bathroom_full")) is not None and _number(details.get("bathroom_half")) is not None else "details.available_bathrooms"
            for field, path in (("title", "title"), ("latitude", "location.latitude"), ("longitude", "location.longitude"),
                                ("city", "location.city"), ("country", "location.country"), ("area", "location.area"),
                                ("rating", "details.rating"), ("bathrooms_source_count", "details.available_bathrooms"),
                                ("bedrooms", "details.bedrooms"), ("beds", "details.available_beds"),
                                ("bathrooms", bathroom_path),
                                ("person_capacity", "details.guests"), ("amenities", "amenities"),
                                ("description", "description"), ("publication_status", "status")):
                if field in mapped_fields:
                    row["field_sources"][field] = {"source_url": item.get("source_url"), "source_path": "singleHotelDetails." + path,
                                                   "observed_at": item.get("observed_at")}
        row["calendar"] = item["calendar"]
        row["calendar_coverage"] = {"observed_days": len({r["date"] for r in row["calendar"]}),
            "available_days": len({r["date"] for r in row["calendar"] if r["availability"] == "available"}),
            "unavailable_days": len({r["date"] for r in row["calendar"] if r["availability"] == "unavailable"}),
            "unknown_days": len({r["date"] for r in row["calendar"] if r["availability"] == "unknown"}),
            "priced_days": len({r["date"] for r in row["calendar"] if r["non_refundable_price"] or r["refundable_price"]})}
        for quote in item.get("quotes", []):
            if not isinstance(quote, dict):
                continue
            row["quotes"].append(deepcopy(quote))
            if (quote.get("status") == "available" and quote.get("quote_kind") == "verified_stay_total"
                    and _amount(quote.get("total_amount")) and _date(quote.get("checkin"))
                    and _date(quote.get("checkout")) and quote.get("currency")
                    and quote["checkout"] > quote["checkin"]
                    and quote.get("source_url") and quote.get("source_path") and quote.get("observed_at")
                    and type(quote.get("adults")) is int and quote["adults"] > 0):
                row["bookability"] = "quoted_available_for_observed_stay"
    from .profile import enrich_subject_profile
    properties = [enrich_subject_profile(row) for row in properties]
    report = deepcopy(catalog.get("report", {}))
    notes = list(report.get("warnings", []))
    notes.extend(["Published catalogue entries are not a guarantee of bookability or complete corporate inventory.",
                  "Airbnb host accounts and direct-site properties remain separate until an explicit cross-reference verifies a link.",
                  "Search display amounts are not verified final stay totals; missing guest and fee context remains unknown."])
    summary = {"property_count": len(properties), "city_counts": dict(Counter(row["city"] for row in properties)),
               "currency_counts": dict(Counter(row["currency"] for row in properties)),
               "airbnb_listing_count": len(airbnb_listings), "airbnb_linked_count": len(verified_links),
               "host_count": len(hosts), "quoted_count": sum(row["bookability"] != "not_verified" for row in properties),
               "display_price_count": sum(any(q.get("quote_kind") == "search_display" for q in row["quotes"]) for row in properties),
               "active_property_count": sum(row["publication_status"] == "active_in_public_details" for row in properties),
               "stay_price_count": sum(any(q.get("price_basis") == "stay_total" and q.get("total_amount") for q in row["quotes"]) for row in properties),
               "calendar_property_count": sum(bool(row.get("calendar")) for row in properties),
               "calendar_record_count": sum(len(row.get("calendar", [])) for row in properties),
               "calendar_unknown_count": sum(record["availability"] == "unknown" for row in properties for record in row.get("calendar", [])),
               "coverage_notes": notes, "active_inventory_complete": report.get("active_inventory_complete") is True}
    result = {"schema_version": SCHEMA_VERSION, "observed_at": catalog["observed_at"],
              "source_url": catalog["source_url"], "source_sha256": hashlib.sha256(canonical(catalog).encode()).hexdigest(),
              "properties": properties, "airbnb_listings": airbnb_listings, "hosts": hosts,
              "links": verified_links, "summary": summary, "report": report}
    result["snapshot_id"] = hashlib.sha256(canonical(result).encode()).hexdigest()[:24]
    return result


def persist_inventory(result, data_dir: Path = DATA):
    """Atomic database snapshot with append-only observations and portable exports."""
    data_dir.mkdir(parents=True, exist_ok=True)
    snapshot_id = result["snapshot_id"]
    folder = data_dir / "inventory" / snapshot_id
    folder.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(data_dir / "compset.sqlite3")) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("CREATE TABLE IF NOT EXISTS portfolio_snapshots(snapshot_id TEXT PRIMARY KEY, observed_at TEXT NOT NULL, source_sha256 TEXT NOT NULL, summary_json TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS portfolio_properties(snapshot_id TEXT NOT NULL REFERENCES portfolio_snapshots(snapshot_id), property_id TEXT NOT NULL, city TEXT, currency TEXT, publication_status TEXT NOT NULL, bookability TEXT NOT NULL, record_json TEXT NOT NULL, PRIMARY KEY(snapshot_id,property_id))")
        db.execute("CREATE TABLE IF NOT EXISTS portfolio_hosts(snapshot_id TEXT NOT NULL REFERENCES portfolio_snapshots(snapshot_id), ordinal INTEGER NOT NULL, record_json TEXT NOT NULL, PRIMARY KEY(snapshot_id,ordinal))")
        db.execute("CREATE TABLE IF NOT EXISTS portfolio_channel_listings(snapshot_id TEXT NOT NULL REFERENCES portfolio_snapshots(snapshot_id), platform TEXT NOT NULL, listing_id TEXT NOT NULL, record_json TEXT NOT NULL, PRIMARY KEY(snapshot_id,platform,listing_id))")
        db.execute("CREATE TABLE IF NOT EXISTS portfolio_prices(snapshot_id TEXT NOT NULL REFERENCES portfolio_snapshots(snapshot_id), property_id TEXT NOT NULL, ordinal INTEGER NOT NULL, currency TEXT, checkin TEXT, checkout TEXT, record_json TEXT NOT NULL, PRIMARY KEY(snapshot_id,property_id,ordinal))")
        db.execute("CREATE TABLE IF NOT EXISTS portfolio_links(snapshot_id TEXT NOT NULL REFERENCES portfolio_snapshots(snapshot_id), ordinal INTEGER NOT NULL, record_json TEXT NOT NULL, PRIMARY KEY(snapshot_id,ordinal))")
        db.execute("CREATE TABLE IF NOT EXISTS portfolio_calendar(snapshot_id TEXT NOT NULL REFERENCES portfolio_snapshots(snapshot_id), property_id TEXT NOT NULL, ordinal INTEGER NOT NULL, date TEXT NOT NULL, availability TEXT NOT NULL, record_json TEXT NOT NULL, PRIMARY KEY(snapshot_id,property_id,ordinal))")
        db.execute("INSERT OR IGNORE INTO portfolio_snapshots VALUES(?,?,?,?)", (snapshot_id, result["observed_at"], result["source_sha256"], canonical(result["summary"])))
        db.executemany("INSERT OR IGNORE INTO portfolio_properties VALUES(?,?,?,?,?,?,?)", [(snapshot_id, r["property_id"], r["city"], r["currency"], r["publication_status"], r["bookability"], canonical(r)) for r in result["properties"]])
        db.executemany("INSERT OR IGNORE INTO portfolio_hosts VALUES(?,?,?)", [(snapshot_id, i, canonical(row)) for i, row in enumerate(result["hosts"])])
        db.executemany("INSERT OR IGNORE INTO portfolio_channel_listings VALUES(?,?,?,?)", [(snapshot_id, "airbnb", str(row["listing_id"]), canonical(row)) for row in result["airbnb_listings"]])
        db.executemany("INSERT OR IGNORE INTO portfolio_prices VALUES(?,?,?,?,?,?,?)", [(snapshot_id, row["property_id"], i, quote.get("currency"), quote.get("checkin"), quote.get("checkout"), canonical(quote)) for row in result["properties"] for i, quote in enumerate(row["quotes"])])
        db.executemany("INSERT OR IGNORE INTO portfolio_links VALUES(?,?,?)", [(snapshot_id, i, canonical(row)) for i, row in enumerate(result["links"])])
        db.executemany("INSERT OR IGNORE INTO portfolio_calendar VALUES(?,?,?,?,?,?)", [(snapshot_id, row["property_id"], i, record["date"], record["availability"], canonical(record)) for row in result["properties"] for i, record in enumerate(row.get("calendar", []))])
    _write_json(folder / "portfolio.json", result)
    csv_rows = [{key: value for key, value in row.items() if key not in {"calendar", "detail_observations", "profile"}} for row in result["properties"]]
    export_csv(folder / "portfolio.csv", csv_rows, ["property_id", "title", "city", "area", "currency", "bedrooms", "bathrooms", "person_capacity", "publication_status", "bookability", "airbnb_listing_id"])
    export_csv(folder / "hosts.csv", result["hosts"], ["host_id", "host_name", "profile_url"])
    export_csv(folder / "prices.csv", [{"property_id": row["property_id"], **quote} for row in result["properties"] for quote in row["quotes"]], ["property_id", "quote_kind", "price_basis", "display_amount", "total_amount", "currency", "checkin", "checkout", "adults"])
    export_csv(folder / "inventory-calendar.csv", [{"property_id": row["property_id"], **record} for row in result["properties"] for record in row.get("calendar", [])], ["property_id", "date", "availability", "non_refundable_price", "refundable_price", "currency"])
    _write_json(data_dir / "portfolio-latest.json", result)
    return folder


def import_inventory(source_path: Path, *, data_dir: Path = DATA):
    catalog = json.loads(source_path.read_text(encoding="utf-8"))
    extra = {}
    supplement = data_dir / "inventory-supplements.json"
    if supplement.exists():
        extra = json.loads(supplement.read_text(encoding="utf-8"))
    detail_file = data_dir / "bnbme-details-source.json"
    if detail_file.exists():
        detail_source = json.loads(detail_file.read_text(encoding="utf-8"))
        extra["supplements"] = detail_source.get("observations", [])
        from .health import inventory_health
        inventory_health(detail_source, data_dir)
    hosts_file = data_dir / "host-listings-source.json"
    if hosts_file.exists():
        host_data = json.loads(hosts_file.read_text(encoding="utf-8"))
        extra["airbnb_listings"] = host_data.get("listings", [])
        profile = host_data["profile"]
        extra["hosts"] = [{"host_id": profile["host_id"], "host_name": profile["host_name"],
            "profile_url": profile["profile_url"], "contextual_profile_id": profile["profile_id"],
            "declared_listing_count": profile["declared_listing_count"],
            "observed_listing_count": len(profile["listing_ids"]), "profile_evidence": profile,
            "company_affiliation": "bnbme homes", "affiliation_basis": "public_host_business_self_description",
            "market": "Dubai", "platform": "airbnb"}]
    result = build_inventory(catalog, **{key: extra[key] for key in ("airbnb_listings", "hosts", "links", "supplements") if key in extra})
    persist_inventory(result, data_dir)
    return result
