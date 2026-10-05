"""Canonical public listing profile without inventing missing attributes."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import re

SCHEMA_REVISION = "public-listing-profile-v1"
QUALITY_TIERS = {"luxury", "mid_luxury", "deluxe", "standard", "unknown"}
CANONICAL_FIELDS = (
    "listing_id", "title", "room_type", "bedrooms", "beds", "bathrooms", "person_capacity",
    "latitude", "longitude", "amenities", "rating", "review_count", "floor_area_sqm",
    "property_type", "building_name", "quality_tier", "host_id", "host_name",
    "host_listing_count", "host_is_professional",
)


def _area(value):
    if type(value) is bool or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number > 0 else None
    except InvalidOperation:
        return None


def enrich_subject_profile(listing: dict) -> dict:
    """Return a copy retaining input fields and adding canonical unknowns/evidence.

    A quality tier requires explicit verified field evidence. Marketing language
    remains a reported claim, never a verified property/building classification.
    This function performs no network requests and is also suitable for candidates.
    """
    result = deepcopy(listing)
    old_profile = result.pop("profile", {})
    sources = deepcopy(result.get("field_sources") or {})
    original = {key: deepcopy(value) for key, value in listing.items()
                if key in CANONICAL_FIELDS and key != "profile"}
    if isinstance(old_profile, dict):
        prior_original = old_profile.get("original_values", {})
        prior_attributes = old_profile.get("attributes", {})
        original = {key: deepcopy(prior_original.get(key, value))
                    if key in prior_attributes and prior_attributes[key].get("value") == value else value
                    for key, value in original.items()}
    for field in CANONICAL_FIELDS:
        result.setdefault(field, "unknown" if field == "quality_tier" else None)
    for field in ("property_type", "building_name"):
        value = result.get(field)
        result[field] = value.strip() or None if isinstance(value, str) else None
    square_metres = _area(result.get("floor_area_sqm"))
    if square_metres is not None:
        result["floor_area_sqm"] = float(square_metres)
    else:
        square_feet = _area(result.get("floor_area_sqft"))
        result["floor_area_sqm"] = (float((square_feet * Decimal("0.09290304")).quantize(Decimal("0.01")))
                                    if square_feet is not None else None)
        if square_feet is not None:
            sources["floor_area_sqm"] = {"source_field": "floor_area_sqft",
                                        "source_evidence": deepcopy(sources.get("floor_area_sqft")),
                                        "transformation": "square_feet_to_square_metres"}
    claims = deepcopy(old_profile.get("quality_marketing_claims", [])) if isinstance(old_profile, dict) else []
    reported_tier = listing.get("quality_tier")
    tier_source = sources.get("quality_tier")
    verified = isinstance(tier_source, dict) and tier_source.get("verified") is True
    if not isinstance(reported_tier, str) or reported_tier not in QUALITY_TIERS or not verified:
        result["quality_tier"] = "unknown"
        if reported_tier and reported_tier != "unknown":
            claim = {"source_field": "quality_tier", "reported_value": reported_tier,
                     "status": "unverified_claim", "evidence": deepcopy(tier_source)}
            if claim not in claims:
                claims.append(claim)
    # Literal mentions are retained as claims, without interpreting stars,
    # superhost badges, nightly price or amenity counts as property quality.
    for field in ("title", "description", "property_summary", "building_description"):
        value = listing.get(field)
        if not isinstance(value, str):
            continue
        for match in re.finditer(r"\b(?:mid[ -]luxury|luxury|deluxe|standard)\b", value, re.I):
            claim = {"source_field": field, "reported_value": match.group(), "status": "marketing_mention",
                     "evidence": deepcopy(sources.get(field))}
            if claim not in claims:
                claims.append(claim)
    attributes = {}
    source_containers = {}
    for field, value in result.items():
        if field in {"field_sources", "profile"}:
            continue
        if field in {"attributes", "detail_attributes", "detail_observations", "calendar"}:
            # Keep full evidence once on the listing; the profile references it
            # instead of duplicating thousands of raw/calendar records.
            source_containers[field] = {"source_field": field, "record_count": len(value) if isinstance(value, (dict, list)) else None}
            continue
        evidence = deepcopy(sources.get(field))
        status = ("unknown" if value is None or field == "quality_tier" and value == "unknown"
                  else "verified" if field == "quality_tier" and verified
                  else "derived" if isinstance(evidence, dict) and evidence.get("transformation")
                  else "observed" if evidence else "provided")
        attributes[field] = {"value": deepcopy(value), "status": status, "evidence": evidence}
    result["field_sources"] = sources
    result["profile"] = {"schema_revision": SCHEMA_REVISION, "attributes": attributes,
                         "source_containers": source_containers,
                         "unknown_fields": sorted(field for field, item in attributes.items() if item["status"] == "unknown"),
                         "quality_marketing_claims": claims, "original_values": original}
    return result
