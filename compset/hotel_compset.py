"""Offline, evidence-backed hotel inventory and product comparison builder.

This module makes no network requests and never produces prices or availability.
The input is a complete saved OSM response plus a reviewed research manifest.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import csv
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlsplit


SCHEMA_VERSION = "hotel-compset.v1"
AMENITIES = ("restaurant", "wifi", "room_service", "air_conditioning", "parking",
             "fitness_center", "meeting_space", "pool", "spa", "private_bathroom")
CORE_SERVICES = ("restaurant", "wifi", "room_service")
INNER_KM = 5.0
OUTER_KM = 10.0


def coordinate(value, limit):
    """Reject booleans, non-finite numbers and out-of-range coordinates."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and abs(value) <= limit else None


def haversine_km(lat1, lon1, lat2, lon2):
    values = [coordinate(lat1, 90), coordinate(lon1, 180),
              coordinate(lat2, 90), coordinate(lon2, 180)]
    if any(v is None for v in values):
        return None
    a, b, c, d = map(math.radians, values)
    term = math.sin((c-a)/2)**2 + math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, term))))


def public_url(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        return value if parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username and not parsed.password else None
    except ValueError:
        return None


def _stars(value):
    # A 4.6 guest score is never converted into a four-star classification.
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and value in ("1", "2", "3", "4", "5"):
        return int(value)
    return value if isinstance(value, int) and 1 <= value <= 5 else None


def _blank_row(identity, title):
    return {"id": identity, "title": title, "latitude": None, "longitude": None,
            "location_evidence": [], "location_status": "unknown", "address": None,
            "property_type": None, "product": {"segment": None, "room_count": None,
            "room_types": [], "room_areas_sqm": [], "service_notes": []},
            "amenities": dict.fromkeys(AMENITIES), "classification_evidence": [],
            "review_evidence": [], "field_sources": {}, "source_url": None,
            "identity_notes": [], "evidence": [], "observed_at": None}


def osm_rows(payload, source):
    """Keep every source feature; do not merge names or buildings speculatively."""
    if payload.get("remark"):
        raise ValueError("OSM response has a remark; partial/error snapshots cannot be declared complete")
    elements = payload.get("elements")
    if not isinstance(elements, list):
        raise ValueError("OSM elements must be a list")
    rows, seen = [], set()
    for element in elements:
        kind, number = element.get("type"), element.get("id")
        if kind not in ("node", "way", "relation") or isinstance(number, bool) or not isinstance(number, int):
            raise ValueError("Unsupported OSM feature identity")
        identity = f"osm:{kind}:{number}"
        if identity in seen:
            raise ValueError("Duplicate OSM feature identity")
        seen.add(identity)
        tags = element.get("tags", {})
        row = _blank_row(identity, tags.get("name"))
        loc = element if kind == "node" else element.get("center", {})
        lat, lon = coordinate(loc.get("lat"), 90), coordinate(loc.get("lon"), 180)
        url = f"https://www.openstreetmap.org/{kind}/{number}"
        if lat is not None and lon is not None:
            row.update(latitude=lat, longitude=lon, location_status="observed")
            row["location_evidence"] = [{"source_id": "osm", "url": url, "latitude": lat,
                "longitude": lon, "method": "map_node" if kind == "node" else "geometry_bbox_center",
                "accepted": True, "selected_for_distance": True, "observed_at": source["observed_at"]}]
        row.update(property_type=tags.get("tourism"), source_url=public_url(tags.get("website")) or url,
                   observed_at=source["observed_at"], osm_feature={"type": kind, "id": number,
                   "tags": deepcopy(tags)}, evidence=["osm"])
        row["field_sources"] = {"property_type": ["osm"], "title": ["osm"]}
        row["address"] = ", ".join(str(tags[k]) for k in ("addr:housenumber", "addr:street", "addr:city") if tags.get(k)) or None
        grade = _stars(tags.get("stars"))
        if grade:
            row["classification_evidence"].append({"stars": grade, "source_id": "osm",
                "basis": "community map tag; not government certification", "currentness": "unverified"})
        if tags.get("internet_access") in ("yes", "wlan"):
            row["amenities"]["wifi"] = True if tags.get("internet_access") == "wlan" else None
            # internet_access=yes does not establish wireless access specifically.
            if row["amenities"]["wifi"]:
                row["field_sources"]["amenities.wifi"] = ["osm"]
        if tags.get("air_conditioning") in ("yes", "no"):
            row["amenities"]["air_conditioning"] = tags["air_conditioning"] == "yes"
            row["field_sources"]["amenities.air_conditioning"] = ["osm"]
        if tags.get("rooms", "").isdigit():
            row["product"]["room_count"] = int(tags["rooms"])
            row["field_sources"]["product.room_count"] = ["osm"]
        if not row["title"]:
            row["identity_notes"].append("Unnamed map feature; may duplicate a named hotel building or node")
        rows.append(row)
    return rows


def _source_ids(value, sources):
    if not isinstance(value, list) or not value:
        raise ValueError("Every researched field needs source IDs")
    for source_id in value:
        if source_id not in sources or sources[source_id].get("capture_status") in ("blocked", "failed"):
            raise ValueError(f"Missing or failed evidence source: {source_id}")
    return value


def enrich(row, research, sources):
    row = deepcopy(row)
    bindings = research.get("field_sources", {})
    fields = ("title", "address", "property_type", "source_url")
    for field in fields:
        if field in research:
            _source_ids(bindings.get(field), sources)
            row[field] = research[field]
    for group in ("amenities", "product"):
        for field, value in research.get(group, {}).items():
            _source_ids(bindings.get(f"{group}.{field}"), sources)
            if group == "amenities" and (field not in AMENITIES or value is not None and not isinstance(value, bool)):
                raise ValueError("Amenities must use known tri-state fields")
            row[group][field] = deepcopy(value)
    row["field_sources"].update(deepcopy(bindings))
    for item in research.get("classification_evidence", []):
        _source_ids([item.get("source_id")], sources)
        if _stars(item.get("stars")) is None:
            raise ValueError("Invalid star classification; reviews are a different field")
        row["classification_evidence"].append(deepcopy(item))
    for item in research.get("review_evidence", []):
        _source_ids([item.get("source_id")], sources)
        row["review_evidence"].append(deepcopy(item))
    extra_locations = research.get("location_evidence", [])
    for item in extra_locations:
        _source_ids([item.get("source_id")], sources)
        if coordinate(item.get("latitude"), 90) is None or coordinate(item.get("longitude"), 180) is None:
            raise ValueError("Invalid evidenced coordinates")
        row["location_evidence"].append(deepcopy(item))
    accepted = [item for item in extra_locations if item.get("accepted") is True]
    if len(accepted) > 1:
        raise ValueError("Select at most one reviewed coordinate per research record")
    if accepted:
        row.update(latitude=accepted[0]["latitude"], longitude=accepted[0]["longitude"], location_status="observed")
        for item in row["location_evidence"]:
            item["selected_for_distance"] = (item.get("source_id") == accepted[0]["source_id"]
                and item.get("latitude") == accepted[0]["latitude"]
                and item.get("longitude") == accepted[0]["longitude"] and item.get("accepted") is True)
    if research.get("location_status") == "conflicted":
        row.update(latitude=None, longitude=None, location_status="conflicted")
        for item in row["location_evidence"]:
            item["selected_for_distance"] = False
    row["identity_notes"].extend(research.get("identity_notes", []))
    refs = set(row["evidence"])
    for values in bindings.values():
        refs.update(_source_ids(values, sources))
    refs.update(item["source_id"] for item in extra_locations)
    refs.update(item["source_id"] for item in row["classification_evidence"] + row["review_evidence"])
    row["evidence"] = sorted(refs)
    row["source_url"] = public_url(row["source_url"])
    return row


def classify(row, subject, radius_km, require_business_service=True):
    """Apply a small, explicit product policy. Missing evidence earns no match."""
    reasons, missing = [], []
    if row["id"] == subject["id"]:
        return "subject", ["Subject property"], []
    if row.get("property_type") not in ("hotel", "motel", "resort"):
        return "excluded_non_hotel", ["Accommodation type is not a comparable hotel"], []
    if not row.get("title"):
        return "unresolved_identity", ["Unnamed map feature requires property identity verification"], ["title"]
    if row.get("distance_km") is None:
        return "unverified_location", ["No accepted, source-backed coordinate"], ["location"]
    if row["distance_km"] > OUTER_KM:
        return "outside_radius", ["Outside the 10 km discovery circle"], []
    if row["distance_km"] > radius_km:
        return "outside_current_radius", [f"Outside current {radius_km:g} km selection radius"], []
    segment = row["product"].get("segment")
    if segment in ("wellness_retreat", "luxury_full_service", "homestay"):
        return "different_product", [f"Product segment {segment} differs from Aketa's city-hotel offer"], []
    current_grades = {x["stars"] for x in row["classification_evidence"] if x.get("currentness") != "historical"}
    if current_grades and not current_grades.issubset({3, 4}):
        return "different_product", ["Published star classification outside the subject's observed 3–4-star range"], []
    if not current_grades and segment not in ("midscale", "upper_midscale"):
        missing.append("classification_or_segment")
    for service in CORE_SERVICES:
        value = row["amenities"].get(service)
        if value is None:
            missing.append(service)
        elif value is False:
            reasons.append(f"Core guest service absent: {service}")
    if reasons:
        return "different_service", reasons, missing
    if missing:
        return "insufficient_evidence", ["Core product/service evidence is incomplete"], missing
    if require_business_service and not any(row["amenities"].get(k) is True for k in ("fitness_center", "meeting_space")):
        return "optional_service_unmatched", ["Fitness or meeting service is not evidenced"], []
    return "eligible", ["City-hotel classification/segment and restaurant, Wi-Fi and room service evidenced"], []


def score_candidate(row, subject):
    """Documented 100-point evidence score; not an observed market quality grade."""
    components = {}
    components["hotel_product"] = 5 if row.get("property_type") in ("hotel", "motel", "resort") else 0
    grades = {x["stars"] for x in row["classification_evidence"] if x.get("currentness") != "historical"}
    components["classification_or_segment"] = 25 if (grades and grades.issubset({3, 4}) or row["product"].get("segment") in ("midscale", "upper_midscale")) else 0
    for name, weight in (("restaurant", 15), ("wifi", 10), ("room_service", 15),
                         ("air_conditioning", 5), ("parking", 5), ("fitness_center", 5), ("meeting_space", 5)):
        components[name] = weight if row["amenities"].get(name) is True else 0
    distance = row.get("distance_km")
    components["proximity"] = round(max(0, 10-distance), 2) if distance is not None else 0
    # Reviews have no minimum: they are separately visible secondary evidence.
    components["reviews"] = 0
    subject_areas = subject["product"].get("room_areas_sqm", [])
    components["room_area"] = 0  # No comparable subject room-area evidence in this snapshot.
    return {"total": round(sum(components.values()), 2), "components": components,
            "room_area_comparable": bool(subject_areas and row["product"].get("room_areas_sqm"))}


def build_inventory(osm_payload, manifest):
    """Return deterministic inventory, selection audit and source coverage."""
    sources = deepcopy(manifest["sources"])
    rows = osm_rows(osm_payload, sources["osm"])
    discovery = manifest["discovery"]
    if discovery.get("response_complete") is False:
        raise ValueError("Discovery response is marked incomplete")
    if "returned_features" in discovery and discovery["returned_features"] != len(rows):
        raise ValueError("Discovery denominator does not match the saved response")
    indexed = {row["id"]: row for row in rows}
    enriched_ids = set()
    for research in manifest.get("properties", []):
        identity = research["id"]
        if identity in enriched_ids:
            raise ValueError("Duplicate research identity; reconcile evidence explicitly")
        enriched_ids.add(identity)
        if identity not in indexed:
            indexed[identity] = _blank_row(identity, None)
        indexed[identity] = enrich(indexed[identity], research, sources)
    subject = indexed.get(manifest["subject_id"])
    if not subject or subject.get("latitude") is None or not subject["location_evidence"]:
        raise ValueError("Subject must have an observed coordinate")
    rows = list(indexed.values())
    for row in rows:
        row["distance_km"] = haversine_km(subject["latitude"], subject["longitude"], row["latitude"], row["longitude"]) if row["location_evidence"] else None
        d = row["distance_km"]
        row["distance_band"] = "unknown" if d is None else "0–5 km" if d <= INNER_KM else "5–10 km" if d <= OUTER_KM else "outside 10 km"
        row["radius_verified"] = d is not None and d <= OUTER_KM
        row["location_precision"] = "published map point; not a survey; straight-line distance"
        row["observed_at"] = max((sources[x]["observed_at"] for x in row["evidence"]), default=None)
        row["classification_conflict"] = len({x["stars"] for x in row["classification_evidence"]}) > 1
        row["rate_status"] = "not_collected"
        row["availability_status"] = "not_collected"
    stages = []
    radius, optional = INNER_KM, True
    for stage, radius, optional in (("initial", INNER_KM, True), ("expand_radius", OUTER_KM, True), ("relax_optional_services", OUTER_KM, False)):
        statuses = {row["id"]: classify(row, subject, radius, optional) for row in rows}
        selected = [identity for identity, status in statuses.items() if status[0] == "eligible"]
        stages.append({"stage": stage, "radius_km": radius, "require_fitness_or_meetings": optional,
                       "selected_count": len(selected), "selected_ids": selected,
                       "trigger": "initial policy" if stage == "initial" else "previous stage had ten or fewer eligible hotels"})
        if len(selected) > 10:
            break
    for row in rows:
        eligibility, reasons, missing = statuses[row["id"]]
        row.update(selected=eligibility == "eligible", eligibility=eligibility, reasons=reasons,
                   missing_fields=missing, similarity_score=score_candidate(row, subject))
        row["distance_km"] = round(row["distance_km"], 4) if row["distance_km"] is not None else None
    rows.sort(key=lambda row: (not row["selected"], -row["similarity_score"]["total"], row["id"]))
    statuses = Counter(row["eligibility"] for row in rows)
    hotel_rows = [r for r in rows if r["property_type"] in ("hotel", "motel", "resort") and r["id"] != subject["id"]]
    return {"schema_version": SCHEMA_VERSION, "observed_at": manifest["observed_at"],
            "subject": deepcopy(subject), "search": {"center": {"latitude": subject["latitude"], "longitude": subject["longitude"]},
            "inner_radius_km": INNER_KM, "outer_radius_km": OUTER_KM,
            "distance_method": "haversine straight-line; Earth radius 6371.0088 km",
            "source_scope": manifest["discovery"], "exhaustive": False}, "candidates": rows,
            "selected_ids": [r["id"] for r in rows if r["selected"]], "summary": {
                "osm_features_returned": len(osm_payload["elements"]), "retained_candidate_features": len(rows),
                "supplemental_properties": len(rows)-len(osm_payload["elements"]),
                "named_hotel_candidates_within_5_km": sum(bool(r["title"]) and r["distance_km"] is not None and r["distance_km"] <= 5 for r in hotel_rows),
                "named_hotel_candidates_5_to_10_km": sum(bool(r["title"]) and r["distance_km"] is not None and 5 < r["distance_km"] <= 10 for r in hotel_rows),
                "hotel_candidates_unverified_location": sum(r["distance_km"] is None for r in hotel_rows),
                "selected_count": statuses["eligible"], "eligibility_counts": dict(sorted(statuses.items())),
                "unique_real_hotel_count": None, "live_rate_count": 0, "active_inventory_complete": False},
            "relaxation": stages, "sources": sources, "warnings": manifest["warnings"]}


def csv_safe(value):
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        text = "'" + text
    return text


def export_inventory(artifact, output):
    """Content-addressed history keeps prior evidence; latest is a projection."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    body = json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    history = output / "history" / f"{digest}.json"
    history.parent.mkdir(parents=True, exist_ok=True)
    if not history.exists():
        history.write_text(body, encoding="utf-8")
    (output / "latest.json").write_text(body, encoding="utf-8")
    columns = ["id", "title", "property_type", "address", "latitude", "longitude", "distance_km",
               "distance_band", "radius_verified", "selected", "eligibility", "reasons", "missing_fields",
               "classification_evidence", "classification_conflict", "product", "amenities", "location_evidence",
               "identity_notes", "review_evidence", "similarity_score", "source_url", "evidence", "field_sources",
               "observed_at", "rate_status", "availability_status"]
    with (output / "candidates.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for row in artifact["candidates"]:
            writer.writerow({key: csv_safe(json.dumps(row[key], ensure_ascii=False) if isinstance(row.get(key), (dict, list)) else row.get(key)) for key in columns})
    return {"latest": str(output / "latest.json"), "history": str(history), "sha256": digest,
            "summary": artifact["summary"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/hotel-compsets/aketa/research.json"))
    parser.add_argument("--osm", type=Path, default=Path("data/hotel-compsets/aketa/raw/osm-accommodation-bbox.json"))
    parser.add_argument("--output", type=Path, default=Path("data/hotel-compsets/aketa"))
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    raw_osm = args.osm.read_bytes()
    expected = manifest["sources"]["osm"].get("sha256")
    if expected and hashlib.sha256(raw_osm).hexdigest() != expected:
        raise ValueError("Saved OSM response hash differs from research provenance")
    osm = json.loads(raw_osm.decode("utf-8"))
    print(json.dumps(export_inventory(build_inventory(osm, manifest), args.output), indent=2))


if __name__ == "__main__":
    main()
