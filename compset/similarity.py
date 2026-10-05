"""Pure, explainable STR comparison. The user's circle is a firm boundary.

Scores are analytical comparability measures, never official hotel star ratings.
Missing evidence earns no points; it is not treated as an observed mismatch.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from .profile import enrich_subject_profile

RULE_REVISION = "guest-filters-major-amenities-profile-v2"

WEIGHTS = {"room_type": 20, "bedrooms": 20, "bathrooms": 15,
           "person_capacity": 10, "beds": 10, "amenities": 15, "rating": 10}
FIELDS = ("listing_id", "title", "latitude", "longitude", "bedrooms", "beds",
          "bathrooms", "person_capacity", "room_type", "amenities", "rating",
          "review_count", "host_id", "host_name", "host_listing_count")


def _number(value, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= minimum else None
    except (ValueError, OverflowError):
        return None


def _identifier(value):
    if type(value) is int or isinstance(value, str):
        return str(value).strip() or None
    return None


def _tokens(value):
    if not isinstance(value, str):
        return ""
    return " ".join(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", value).casefold()))


def _room_type(value):
    token = _tokens(value)
    entire = {"entire home apt", "entire home", "entire home apartment", "entire place",
              "entire rental unit", "entire apartment", "entire condominium condo",
              "entire condo", "entire serviced apartment", "entire villa",
              "entire townhouse", "entire house", "entire cottage", "entire cabin"}
    if token in entire:
        return "entire_home"
    return {"private room": "private_room", "shared room": "shared_room",
            "hotel room": "hotel_room"}.get(token)


def _amenities(value):
    if not isinstance(value, list):
        return None
    available, observed = set(), not value
    icons = {"SYSTEM_POOL": "pool", "SYSTEM_GYM": "gym", "SYSTEM_SNOWFLAKE": "air_conditioning",
             "SYSTEM_WI_FI": "wifi", "SYSTEM_COOKING_BASICS": "kitchen", "SYSTEM_MAPS_CAR_RENTAL": "parking"}
    patterns = {"pool": r"\b(?:swimming pool|pool)\b", "gym": r"\b(?:gym|fitness cent(?:er|re)|exercise equipment)\b",
                "air_conditioning": r"\b(?:air conditioning|air conditioner|a c|ac)\b", "wifi": r"\b(?:wifi|wi fi|wireless internet)\b",
                "kitchen": r"\b(?:kitchen|kitchenette)\b", "parking": r"\b(?:parking|car park|garage)\b"}
    for item in value:
        icon = None
        if isinstance(item, str):
            title, present = _tokens(item), True
        elif isinstance(item, dict):
            title, present = _tokens(item.get("title")), item.get("available")
            icon = item.get("icon")
        else:
            continue
        category = icons.get(icon) or next((key for key, pattern in patterns.items() if re.search(pattern, title)), None)
        if category == "pool" and "pool table" in title:
            category = None
        if category and type(present) is bool:
            observed = True
            if present and not re.search(r"\b(?:no|without|unavailable)\b", title):
                available.add(category)
    return available if observed else None


def _secondary_comparisons(subject, candidate):
    """Observed size/type/building evidence influences ranking, never hard gates."""
    comparisons = {}
    for field in ("floor_area_sqm", "property_type", "building_name", "quality_tier"):
        left, right = subject.get(field), candidate.get(field)
        score = None
        if field == "floor_area_sqm":
            left, right = _number(left), _number(right)
            if left is not None and right is not None and max(left, right) > 0:
                score = min(left, right) / max(left, right)
        elif field == "quality_tier":
            if left not in (None, "unknown") and right not in (None, "unknown"):
                score = float(left == right)
        else:
            left, right = _tokens(left), _tokens(right)
            if left and right:
                score = float(left == right)
        comparisons[field] = {"subject_value": subject.get(field), "candidate_value": candidate.get(field),
                              "score": round(100 * score, 4) if score is not None else None,
                              "evidence": "observed" if score is not None else "missing"}
    observed = [item["score"] for item in comparisons.values() if item["score"] is not None]
    return (sum(observed) / len(observed) if observed else None), comparisons


def _coordinates(row):
    lat, lng = _number(row.get("latitude"), -90), _number(row.get("longitude"), -180)
    return (lat, lng) if lat is not None and lng is not None and lat <= 90 and lng <= 180 else None


def _distance(center, point):
    lat1, lng1, lat2, lng2 = map(math.radians, (*center, *point))
    value = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, value))))


def _operator_size(value, threshold):
    count = _number(value)
    if count is None or not count.is_integer():
        return "unknown"
    return "large" if count >= threshold else "small"


def _score(subject, candidate, missing):
    components, total, coverage = {}, 0.0, 0
    for field, weight in WEIGHTS.items():
        left, right, similarity = subject.get(field), candidate.get(field), None
        if field == "room_type":
            left, right = _room_type(left), _room_type(right)
            if left is not None and right is not None:
                similarity = float(left == right)
        elif field == "amenities":
            left, right = _amenities(left), _amenities(right)
            if left is not None and right is not None:
                union = left | right
                similarity = len(left & right) / len(union) if union else 1.0
        else:
            left, right = _number(left), _number(right)
            if field == "rating":
                for row, prefix in ((subject, "subject."), (candidate, "")):
                    reviews = _number(row.get("review_count"))
                    if reviews is None or reviews <= 0:
                        missing.add(prefix + "review_count")
                if (_number(subject.get("review_count")) or 0) <= 0:
                    left = None
                if (_number(candidate.get("review_count")) or 0) <= 0:
                    right = None
                if left is not None and left > 5:
                    left = None
                if right is not None and right > 5:
                    right = None
            if left is not None and right is not None:
                scale = 5.0 if field == "rating" else max(left, 1.0)
                similarity = max(0.0, 1.0 - abs(left - right) / scale)
        if left is None:
            missing.add("subject." + field)
        if right is None:
            missing.add(field)
        earned = weight * similarity if similarity is not None else None
        components[field] = {"weight": weight, "score": round(100 * similarity, 4) if similarity is not None else None,
                             "earned_points": round(earned, 4) if earned is not None else None,
                             "evidence": "observed" if similarity is not None else "missing"}
        if earned is not None:
            total += earned
            coverage += weight
    return (round(total, 4) if coverage else None), coverage, components


def rank_candidates(subject: dict, candidates: list[dict], criteria: dict) -> dict:
    """Retain the full unique discovery audit and select at most 100 eligible rows.

    Hard rules: exact chosen circle, room type, bedroom/bathroom/capacity tolerances.
    Missing hard-rule fields are provisional. IDs deduplicate only exact public IDs.
    Ties sort by score, distance, then listing ID; input objects are never mutated.
    """
    subject = enrich_subject_profile(subject)
    center = _coordinates({"latitude": criteria.get("center_lat", subject.get("latitude")),
                           "longitude": criteria.get("center_lng", subject.get("longitude"))})
    radius = _number(criteria.get("radius_km"))
    target = _number(criteria.get("target", 100))
    threshold = _number(criteria.get("large_operator_threshold", 10), 1)
    raw_tolerances = {"bedrooms": criteria.get("bedroom_tolerance", 0),
                      "bathrooms": criteria.get("bathroom_tolerance", 0.5),
                      "person_capacity": criteria.get("capacity_tolerance", 2)}
    tolerances = {field: _number(value) if value is not None else None for field, value in raw_tolerances.items()}
    minimum_guests = _number(criteria.get("min_guest_capacity"), 1) if criteria.get("min_guest_capacity") is not None else None
    if center is None or radius is None:
        raise ValueError("Valid center coordinates and a nonnegative radius_km are required")
    if (target is None or not target.is_integer() or threshold is None or not threshold.is_integer()
            or tolerances["bedrooms"] is None
            or any(raw_tolerances[field] is not None and value is None for field, value in tolerances.items())
            or criteria.get("min_guest_capacity") is not None and (minimum_guests is None or not minimum_guests.is_integer())):
        raise ValueError("Target/large operator threshold must be integers and tolerances nonnegative")
    target = min(int(target), 100)
    threshold = int(threshold)
    subject_id, seen, audited = _identifier(subject.get("listing_id")), set(), []
    subject_exclusions, duplicates = 0, 0
    active_filters = {"circle": True, "room_type": True, **{field: value is not None for field, value in tolerances.items()},
                      "min_guest_capacity": minimum_guests is not None}
    filters = {key: {"passed": 0, "excluded": 0, "unknown": 0, "disabled": 0} for key in active_filters}
    for source in candidates:
        row = enrich_subject_profile(source)
        for field in FIELDS:
            row.setdefault(field, None)
        listing_id = _identifier(row.get("listing_id"))
        if subject_id is not None and listing_id == subject_id:
            subject_exclusions += 1
            continue
        if listing_id is not None and listing_id in seen:
            duplicates += 1
            continue
        if listing_id is not None:
            seen.add(listing_id)
        missing, reasons, unresolved = set(), [], False
        if listing_id is None:
            missing.add("listing_id")
            unresolved = True
        point = _coordinates(row)
        distance = _distance(center, point) if point is not None else None
        inside = distance <= radius if distance is not None else None
        if inside is None:
            for field in ("latitude", "longitude"):
                if _coordinates({"latitude": row.get("latitude") if field == "latitude" else 0,
                                 "longitude": row.get("longitude") if field == "longitude" else 0}) is None:
                    missing.add(field)
            unresolved = True
        elif not inside:
            reasons.append("outside_circle")
        filters["circle"]["unknown" if inside is None else "passed" if inside else "excluded"] += 1
        for field in ("room_type", *tolerances):
            if not active_filters[field]:
                filters[field]["disabled"] += 1
                continue
            normalize = _room_type if field == "room_type" else _number
            left, right = normalize(subject.get(field)), normalize(row.get(field))
            if left is None or right is None:
                if left is None:
                    missing.add("subject." + field)
                if right is None:
                    missing.add(field)
                unresolved = True
                filters[field]["unknown"] += 1
            else:
                match = left == right if field == "room_type" else abs(left - right) <= tolerances[field]
                filters[field]["passed" if match else "excluded"] += 1
                if not match:
                    reasons.append("capacity_mismatch" if field == "person_capacity" else field + "_mismatch")
        if minimum_guests is not None:
            capacity = _number(row.get("person_capacity"))
            if capacity is None:
                missing.add("person_capacity")
                unresolved = True
                filters["min_guest_capacity"]["unknown"] += 1
            else:
                enough = capacity >= minimum_guests
                filters["min_guest_capacity"]["passed" if enough else "excluded"] += 1
                if not enough:
                    reasons.append("insufficient_guest_capacity")
        else:
            filters["min_guest_capacity"]["disabled"] += 1
        score, coverage, components = _score(subject, row, missing)
        secondary_score, comparisons = _secondary_comparisons(subject, row)
        base_score = score
        if score is not None and secondary_score is not None:
            score = round(score * 0.85 + secondary_score * 0.15, 4)
        row.update(distance_km=round(distance, 6) if distance is not None else None,
                   inside_circle=inside, eligibility="excluded" if reasons else "provisional" if unresolved else "eligible",
                   rejection_reasons=reasons, missing_fields=sorted(missing), similarity_score=score,
                   score_components=components, evidence_coverage=coverage,
                   base_similarity_score=base_score, comparison_components=comparisons,
                   secondary_similarity_score=round(secondary_score, 4) if secondary_score is not None else None,
                   operator_size=_operator_size(row.get("host_listing_count"), threshold), selected=False)
        audited.append(row)
    eligible = sorted((row for row in audited if row["eligibility"] == "eligible"),
                      key=lambda row: (-(row["similarity_score"] or 0), row["distance_km"], _identifier(row["listing_id"]) or ""))
    selected = eligible[:target]
    for row in selected:
        row["selected"] = True
    groups = {}
    for row in audited:
        host_id = _identifier(row.get("host_id"))
        if host_id is None:
            continue
        group = groups.setdefault(host_id, {"host_id": host_id, "host_names": [], "listing_ids": [],
                                           "observed_competitor_count": 0, "selected_count": 0,
                                           "disclosed_listing_counts": [], "operator_size": "unknown"})
        if row.get("host_name") and row["host_name"] not in group["host_names"]:
            group["host_names"].append(row["host_name"])
        if _identifier(row["listing_id"]) is not None:
            group["listing_ids"].append(row["listing_id"])
            group["observed_competitor_count"] += 1
        group["selected_count"] += int(row["selected"])
        count = _number(row.get("host_listing_count"))
        if count is not None and count.is_integer() and int(count) not in group["disclosed_listing_counts"]:
            group["disclosed_listing_counts"].append(int(count))
        if group["disclosed_listing_counts"]:
            group["operator_size"] = _operator_size(max(group["disclosed_listing_counts"]), threshold)
    for row in audited:
        group = groups.get(_identifier(row.get("host_id")))
        if group and group["observed_competitor_count"] >= threshold:
            row["operator_size"] = "large"
            row["operator_size_basis"] = "observed_listings_for_same_public_host_id"
            row["observed_host_listing_count"] = group["observed_competitor_count"]
            group["operator_size"] = "large"
            group["operator_size_basis"] = "observed_listings_for_same_public_host_id"
        elif row.get("host_listing_count") is not None:
            row["operator_size_basis"] = "publicly_disclosed_listing_count"
        else:
            row["operator_size_basis"] = "unknown"
    statuses = Counter(row["eligibility"] for row in audited)
    sizes = Counter(row["operator_size"] for row in selected)
    maximum = max((group["selected_count"] for group in groups.values()), default=0)
    summary = {"rule_revision": RULE_REVISION, "active_filters": active_filters,
               "profile_stage": criteria.get("profile_stage", "canonical_profile"),
               "relaxation_stage": criteria.get("relaxation_stage", "strict"),
               "min_guest_capacity": minimum_guests,
               "secondary_comparison_weight": 0.15,
               "amenity_comparison_categories": ["pool", "gym", "air_conditioning", "wifi", "kitchen", "parking"],
               "review_threshold": None,
               "returned_count": len(candidates), "candidate_count": len(audited),
               "subject_excluded_count": subject_exclusions, "duplicate_count": duplicates,
               "eligible_count": statuses["eligible"], "excluded_count": statuses["excluded"],
               "provisional_count": statuses["provisional"], "selected_count": len(selected),
               "target": target, "target_met": len(selected) >= target,
               "circle": {"center_lat": center[0], "center_lng": center[1], "radius_km": radius,
                          "automatic_expansion": False}, "filter_counts": filters,
               "rejection_counts": dict(Counter(reason for row in audited for reason in row["rejection_reasons"])),
               "tolerances": tolerances, "score_weights": dict(WEIGHTS),
               "large_operator_threshold": threshold, "host_groups": list(groups.values()),
               "selected_operator_concentration": {"known_host_count": sum(group["selected_count"] > 0 for group in groups.values()),
                   "unknown_host_listing_count": sum(_identifier(row.get("host_id")) is None for row in selected),
                   "largest_host_selected_count": maximum,
                   "largest_host_share_percent": round(100 * maximum / len(selected), 4) if selected else None,
                   "large": sizes["large"], "small": sizes["small"], "unknown": sizes["unknown"]}}
    return {"candidates": audited, "selected": selected, "summary": summary}
