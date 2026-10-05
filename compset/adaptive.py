"""Pure, bounded comparison policy with explicit transitions and source coverage."""
from __future__ import annotations

from copy import deepcopy
import math

from .profile import enrich_subject_profile
from .similarity import _number, _room_type, rank_candidates

POLICY_REVISION = "adaptive-core-guest-floor-v1"
ELIGIBLE_GATE = 10
HARD_RADIUS_CAP_KM = 10.0
HARD_BATHROOM_TOLERANCE_CAP = 2.0


def _finite(value, name, minimum, maximum):
    if type(value) is bool:
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{name} must be a finite number") from None
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def build_adaptive_plan(subject: dict, criteria: dict, policy: dict | None = None) -> dict:
    """Describe possible transitions; this plan does not assert they will execute."""
    if not isinstance(subject, dict) or not isinstance(criteria, dict):
        raise ValueError("Subject and criteria must be mappings")
    canonical_subject = enrich_subject_profile(subject)
    effective = deepcopy(criteria)
    if effective.get("bedroom_tolerance", 0) != 0 or type(effective.get("bedroom_tolerance", 0)) is bool:
        raise ValueError("Adaptive comparison requires exact bedroom compatibility")
    effective["bedroom_tolerance"] = 0
    effective["target"] = _integer(effective.get("target", 100), "target", 1, 100)
    guests = _integer(effective.get("min_guest_capacity", effective.get("adults", 1)), "min_guest_capacity", 1, 16)
    if "adults" in effective and guests < _integer(effective["adults"], "adults", 1, 16):
        raise ValueError("Minimum guest capacity cannot be below the requested adults")
    effective["min_guest_capacity"] = guests
    effective["center_lat"] = _finite(effective.get("center_lat", canonical_subject.get("latitude")), "center_lat", -90, 90)
    effective["center_lng"] = _finite(effective.get("center_lng", canonical_subject.get("longitude")), "center_lng", -180, 180)
    effective["radius_km"] = _finite(effective.get("radius_km", 2), "radius_km", 0.000001, HARD_RADIUS_CAP_KM)
    effective["bathroom_tolerance"] = _finite(effective.get("bathroom_tolerance", 0.5), "bathroom_tolerance", 0, HARD_BATHROOM_TOLERANCE_CAP)
    if effective.get("capacity_tolerance", 2) is not None:
        effective["capacity_tolerance"] = _finite(effective.get("capacity_tolerance", 2), "capacity_tolerance", 0, 100)
    effective.update(profile_stage="canonical_profile", relaxation_stage="strict")
    if policy is not None and not isinstance(policy, dict):
        raise ValueError("Adaptive policy must be a mapping")
    configured = deepcopy(policy or {})
    allowed = {"max_radius_km", "max_radius_steps", "radius_multiplier", "bathroom_tolerance_cap"}
    if not isinstance(configured, dict) or set(configured) - allowed:
        raise ValueError("Unknown adaptive policy fields")
    configured = {
        "max_radius_km": _finite(configured.get("max_radius_km", 10), "max_radius_km", effective["radius_km"], HARD_RADIUS_CAP_KM),
        "max_radius_steps": _integer(configured.get("max_radius_steps", 6), "max_radius_steps", 0, 8),
        "radius_multiplier": _finite(configured.get("radius_multiplier", 2), "radius_multiplier", 1.01, 3),
        "bathroom_tolerance_cap": _finite(configured.get("bathroom_tolerance_cap", max(1.0, effective["bathroom_tolerance"])),
                                          "bathroom_tolerance_cap", effective["bathroom_tolerance"], HARD_BATHROOM_TOLERANCE_CAP),
    }
    steps = [{"stage": "strict", "kind": "baseline", "criteria": deepcopy(effective), "changes": {}}]
    proposed = deepcopy(effective)
    if proposed["bathroom_tolerance"] < configured["bathroom_tolerance_cap"]:
        previous = proposed["bathroom_tolerance"]
        proposed.update(bathroom_tolerance=configured["bathroom_tolerance_cap"], relaxation_stage="secondary_bathrooms")
        steps.append({"stage": "secondary_bathrooms", "kind": "secondary", "criteria": deepcopy(proposed),
                      "changes": {"bathroom_tolerance": {"before": previous, "after": proposed["bathroom_tolerance"]}}})
    if proposed.get("capacity_tolerance", 2) is not None:
        previous = proposed.get("capacity_tolerance", 2)
        proposed.update(capacity_tolerance=None, relaxation_stage="secondary_capacity")
        steps.append({"stage": "secondary_capacity", "kind": "secondary", "criteria": deepcopy(proposed),
                      "changes": {"capacity_tolerance": {"before": previous, "after": None}}})
    for index in range(configured["max_radius_steps"]):
        previous = proposed["radius_km"]
        if previous >= configured["max_radius_km"]:
            break
        proposed.update(radius_km=min(configured["max_radius_km"], previous * configured["radius_multiplier"]),
                        relaxation_stage=f"radius_{index + 1}")
        steps.append({"stage": f"radius_{index + 1}", "kind": "radius", "criteria": deepcopy(proposed),
                      "changes": {"radius_km": {"before": previous, "after": proposed["radius_km"]}}})
    unknown = []
    if _room_type(canonical_subject.get("room_type")) is None:
        unknown.append("room_type")
    bedrooms = _number(canonical_subject.get("bedrooms"))
    if bedrooms is None or not bedrooms.is_integer():
        unknown.append("bedrooms")
    return {"policy_revision": POLICY_REVISION, "subject": canonical_subject, "initial_criteria": effective,
            "policy": {**configured, "eligible_transition_gate": ELIGIBLE_GATE}, "steps": steps,
            "subject_core_unknown_fields": unknown, "core_rules": {
                "matching_room_type": True, "bedroom_tolerance": 0, "min_guest_capacity": guests},
            "score_weights_changed": False}


def _identity(value):
    if type(value) is int or isinstance(value, str):
        return str(value).strip() or None
    return None


def run_adaptive_comparison(subject: dict, candidates: list[dict], criteria: dict, *,
                            policy: dict | None = None, discovery_callback=None,
                            discovery_coverage: dict | None = None) -> dict:
    """Rank known evidence; optionally request a new bounded discovery via callback.

    Callback: callback(canonical_subject, next_criteria) -> {candidates, report}.
    It owns transport/pacing/access limits; this module never performs HTTP.
    """
    plan = build_adaptive_plan(subject, criteria, policy)
    if not isinstance(candidates, list) or any(not isinstance(row, dict) for row in candidates):
        raise ValueError("Candidates must be a list of mappings")
    if discovery_callback is not None and not callable(discovery_callback):
        raise ValueError("Discovery callback must be callable")
    if discovery_coverage is not None and not isinstance(discovery_coverage, dict):
        raise ValueError("Discovery coverage must be a mapping")
    observations, pool, seen = [], [], set()
    duplicate_observations = 0
    def retain(rows):
        nonlocal duplicate_observations
        for source in rows:
            observations.append(deepcopy(source))
            identifier = _identity(source.get("listing_id"))
            if identifier is not None and identifier in seen:
                duplicate_observations += 1
                continue
            if identifier is not None:
                seen.add(identifier)
            pool.append(deepcopy(source))
    retain(candidates)
    coverage = deepcopy(discovery_coverage) if discovery_coverage is not None else {
        "state": "not_supplied", "complete_for_requested_cells": False}
    records, histories = [], {}
    ranking, active_criteria, stop_reason = None, plan["initial_criteria"], None
    for proposal in plan["steps"]:
        if records:
            if ranking["summary"]["eligible_count"] > ELIGIBLE_GATE:
                stop_reason = "eligible_count_above_transition_gate"
                break
            if plan["subject_core_unknown_fields"]:
                stop_reason = "subject_core_fields_unknown"
                break
            if coverage.get("stop_reason"):
                stop_reason = "discovery_stopped"
                break
        before = ranking["summary"]["eligible_count"] if ranking else None
        active_criteria = deepcopy(proposal["criteria"])
        callback_error = None
        discovery_performed = False
        if proposal["kind"] == "radius":
            if discovery_callback is None:
                coverage = {"state": "retained_candidates_only", "complete_for_requested_cells": False,
                            "requested_circle": {key: active_criteria[key] for key in ("center_lat", "center_lng", "radius_km")}}
            else:
                discovery_performed = True
                try:
                    response = discovery_callback(deepcopy(plan["subject"]), deepcopy(active_criteria))
                    if (not isinstance(response, dict) or not isinstance(response.get("candidates"), list)
                            or any(not isinstance(row, dict) for row in response["candidates"])
                            or not isinstance(response.get("report"), dict)):
                        raise ValueError("Invalid discovery callback response")
                    retain(response["candidates"])
                    coverage = deepcopy(response["report"])
                except Exception as exc:
                    callback_error = type(exc).__name__
                    coverage = {"state": "discovery_error", "complete_for_requested_cells": False,
                                "stop_reason": "discovery_error", "error_type": callback_error}
        ranking = rank_candidates(plan["subject"], pool, active_criteria)
        counts = {key: ranking["summary"][key] for key in (
            "candidate_count", "eligible_count", "excluded_count", "provisional_count", "selected_count")}
        outcomes = []
        for index, row in enumerate(ranking["candidates"]):
            identifier = _identity(row.get("listing_id"))
            key = f"listing:{identifier}" if identifier is not None else f"missing:{index}"
            outcome = {"stage": proposal["stage"], "listing_id": row.get("listing_id"),
                       "eligibility": row["eligibility"], "selected": row["selected"],
                       "rejection_reasons": deepcopy(row["rejection_reasons"]),
                       "missing_fields": deepcopy(row["missing_fields"])}
            histories.setdefault(key, []).append(outcome)
            outcomes.append({"audit_key": key, **outcome})
        records.append({**deepcopy(proposal), "eligible_count_before": before, "counts": counts,
                        "discovery_performed": discovery_performed, "discovery_coverage": deepcopy(coverage),
                        "candidate_outcomes": outcomes, "error_type": callback_error})
        if coverage.get("stop_reason"):
            stop_reason = "discovery_stopped"
            break
    if stop_reason is None:
        if ranking["summary"]["eligible_count"] > ELIGIBLE_GATE:
            stop_reason = "eligible_count_above_transition_gate"
        elif plan["subject_core_unknown_fields"]:
            stop_reason = "subject_core_fields_unknown"
        else:
            stop_reason = "bounded_plan_exhausted"
    for index, row in enumerate(ranking["candidates"]):
        identifier = _identity(row.get("listing_id"))
        key = f"listing:{identifier}" if identifier is not None else f"missing:{index}"
        row["adaptive_history"] = deepcopy(histories[key])
    ranking["summary"].update(shortfall=max(0, active_criteria["target"] - len(ranking["selected"])),
                              adaptive_policy_revision=POLICY_REVISION,
                              raw_candidate_observation_count=len(observations),
                              duplicate_observation_count=duplicate_observations)
    radius_changes = sum(step["kind"] == "radius" for step in records)
    ranking["summary"]["circle"].update(automatic_expansion=radius_changes > 0,
                                        initial_radius_km=plan["initial_criteria"]["radius_km"])
    return {"subject": plan["subject"], "criteria": active_criteria, **ranking,
            "candidate_observations": observations, "adaptive": {
                "policy_revision": POLICY_REVISION, "policy": plan["policy"], "core_rules": plan["core_rules"],
                "subject_core_unknown_fields": plan["subject_core_unknown_fields"],
                "steps": records, "planned_step_count": len(plan["steps"]), "stop_reason": stop_reason,
                "automatic_radius_changes": radius_changes}}
