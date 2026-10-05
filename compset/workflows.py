"""Checkpointed candidate discovery and HTTP detail enrichment."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import threading
import time
from urllib.parse import urlencode
from .pipeline import DATA, ROOT, canonical, context_from, export_csv, _write_json


def criteria_from(values: dict, subject: dict | None = None) -> dict:
    subject = subject or {}
    result = {}
    for key, default, lower, upper in (("center_lat", subject.get("latitude", 25.1929), -85, 85),
                                     ("center_lng", subject.get("longitude", 55.2716), -180, 180),
                                     ("radius_km", 2, 0.25, 10)):
        value = values.get(key, default)
        if type(value) is bool:
            raise ValueError(f"Invalid {key}.")
        value = float(value)
        if not math.isfinite(value) or not lower <= value <= upper:
            raise ValueError(f"{key} must be between {lower} and {upper}.")
        result[key] = value
    for key, default, maximum in (("target", 100, 100), ("budget", 18, 40)):
        value = values.get(key, default)
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f"{key} must be an integer from 1 to {maximum}.")
        result[key] = value
    result.update(large_operator_threshold=10, bedroom_tolerance=0, bathroom_tolerance=0.5, capacity_tolerance=2)
    return result


def progress(stage: str, message: str, **fields):
    DATA.mkdir(exist_ok=True)
    _write_json(DATA / "progress.json", {"stage": stage, "message": message, **fields})


def _fresh_observation(value):
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return -60 <= (datetime.now(timezone.utc) - stamp).total_seconds() <= 6 * 3600
    except (TypeError, ValueError):
        return False


def listing_detail(listing_id: str, context: dict, stop: threading.Event | None = None) -> dict:
    from .collect import _script_payloads
    from .normalize import normalize
    from scrapling.fetchers import Fetcher
    if not listing_id.isdigit():
        raise ValueError("Invalid listing ID.")
    cache_dir = DATA / "cache" / "listings"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f'{listing_id}-{context["currency"]}.json'
    parsed_cache = cache_dir / f'{listing_id}-{context["currency"]}.parsed.json'
    parser_sha = hashlib.sha256((ROOT / "compset" / "normalize.py").read_bytes()).hexdigest()
    cached = None
    if cache.exists():
        if parsed_cache.exists():
            try:
                parsed = json.loads(parsed_cache.read_text(encoding="utf-8"))
                if (isinstance(parsed, dict) and parsed.get("parser_sha256") == parser_sha
                        and parsed.get("source_mtime_ns") == cache.stat().st_mtime_ns
                        and isinstance(parsed.get("listing"), dict)
                        and str(parsed["listing"].get("listing_id")) == listing_id
                        and _fresh_observation(parsed["listing"].get("details_observed_at"))):
                    return parsed["listing"]
            except (ValueError, OSError):
                pass
        try:
            candidate = json.loads(cache.read_text(encoding="utf-8"))
            if isinstance(candidate, dict) and _fresh_observation(candidate.get("observed_at")):
                cached = candidate
        except (ValueError, OSError):
            pass
    if cached is None:
        if stop and stop.is_set():
            return {"listing_id": listing_id, "detail_status": "deferred_after_access_limit"}
        url = f'https://www.airbnb.co.in/rooms/{listing_id}?' + urlencode({"currency": context["currency"], "adults": context["adults"]})
        try:
            response = Fetcher.get(url, timeout=20, retries=1)
            if response.status in {401, 403, 429}:
                if stop:
                    stop.set()
                return {"listing_id": listing_id, "detail_status": f"access_limit_{response.status}"}
            if response.status != 200:
                return {"listing_id": listing_id, "detail_status": f"http_{response.status}"}
            cached = {"observed_at": datetime.now(timezone.utc).isoformat(), "payloads": _script_payloads(response, url)}
            _write_json(cache, cached)
        except Exception as exc:
            return {"listing_id": listing_id, "detail_status": "request_error", "error_type": type(exc).__name__}
    detail_context = {**context, "listing_id": listing_id, "observed_at": cached["observed_at"]}
    listing = normalize(cached["payloads"], detail_context)["listing"]
    result = {**listing, "detail_status": "observed" if listing.get("title") else "schema_unrecognized", "details_observed_at": cached["observed_at"]}
    _write_json(parsed_cache, {"parser_sha256": parser_sha, "source_mtime_ns": cache.stat().st_mtime_ns, "listing": result})
    return result


def discover_compset(values: dict, *, discovery_result: dict | None = None) -> dict:
    from .collect import _quiet_scrapling
    from .discovery import discover
    from .adaptive import run_adaptive_comparison
    context = context_from(values)
    criteria = criteria_from(values)
    progress("subject", "Reading the subject property's public attributes…")
    with _quiet_scrapling():
        subject = listing_detail(context["listing_id"], context)
    if subject.get("detail_status") != "observed":
        raise ValueError("The subject listing could not be read. Check its public URL and try again.")
    criteria = criteria_from(values, subject)
    criteria["min_guest_capacity"] = context["adults"]
    progress("discovery", "Discovering nearby Airbnb candidates by search cell…")
    discovery = discovery_result or discover(subject, {**context, **criteria}, target=criteria["target"])
    candidates = discovery["candidates"]
    progress("enrichment", f"Reading full attributes for {len(candidates)} discovered candidates…", processed=0, total=len(candidates))
    stop = threading.Event()
    source_stop = discovery["report"].get("stop_reason")
    if source_stop in (None, "request_budget_reached", "candidate_cap_reached"):
        source_stop = None
    if source_stop:
        stop.set()
    enriched = [dict(candidate) for candidate in candidates]
    with _quiet_scrapling(), ThreadPoolExecutor(max_workers=2) as pool:
        tasks = {pool.submit(listing_detail, str(candidate["listing_id"]), context, stop): index for index, candidate in enumerate(candidates)}
        completed = 0
        for task in as_completed(tasks):
            index = tasks[task]
            detail = task.result()
            old_sources = enriched[index].get("field_sources", {})
            enriched[index].update({k: v for k, v in detail.items() if v is not None and v != [] and k != "field_sources"})
            enriched[index]["field_sources"] = {**old_sources, **detail.get("field_sources", {})}
            completed += 1
            progress("enrichment", f"Read {completed}/{len(candidates)} candidates; cached details are reused.", processed=completed, total=len(candidates))
            if completed % 10 == 0:
                _write_json(DATA / "discovery-checkpoint.json", {"context": context, "criteria": criteria, "subject": subject, "candidates": enriched, "discovery": discovery["report"]})
    known_details = {str(row["listing_id"]): row for row in enriched}
    search_remaining = max(0, criteria["budget"] - discovery["report"].get("total_search_requests", criteria["budget"]))
    new_detail_remaining = 200
    initial_coverage = dict(discovery["report"])
    if stop.is_set() and not source_stop:
        initial_coverage["stop_reason"] = "enrichment_access_limit"

    def expand(canonical_subject, next_criteria):
        nonlocal search_remaining, new_detail_remaining, source_stop
        if search_remaining < 1 or stop.is_set():
            return {"candidates": [], "report": {"complete_for_requested_cells": False,
                    "stop_reason": source_stop or ("access_limit" if stop.is_set() else "request_budget_reached")}}
        progress("discovery", f'Expanding the comparison radius to {next_criteria["radius_km"]} km after ten or fewer matches.')
        additional = discover(canonical_subject, {**context, **next_criteria, "budget": search_remaining}, target=criteria["target"])
        reason = additional["report"].get("stop_reason")
        if reason not in (None, "request_budget_reached", "candidate_cap_reached"):
            source_stop = reason
            stop.set()
        search_remaining = max(0, search_remaining - additional["report"].get("total_search_requests", search_remaining))
        rows = []
        # New detail reads are serial and separately bounded. Any excess stays
        # provisional; missing attributes cannot become exact matches.
        for candidate in additional["candidates"]:
            identifier = str(candidate["listing_id"])
            detail = known_details.get(identifier)
            if detail is None and new_detail_remaining > 0 and not stop.is_set():
                with _quiet_scrapling():
                    detail = listing_detail(identifier, context, stop)
                known_details[identifier] = detail
                new_detail_remaining -= 1
                time.sleep(1)
            merged = dict(candidate)
            if detail:
                merged.update({key: value for key, value in detail.items() if value is not None and value != [] and key != "field_sources"})
                merged["field_sources"] = {**candidate.get("field_sources", {}), **detail.get("field_sources", {})}
            rows.append(merged)
        if stop.is_set() and not source_stop:
            additional["report"]["stop_reason"] = "enrichment_access_limit"
        additional["report"]["new_detail_read_budget_remaining"] = new_detail_remaining
        return {"candidates": rows, "report": additional["report"]}

    ranked = run_adaptive_comparison(subject, enriched, criteria,
        policy={"max_radius_km": values.get("max_radius_km", 10)},
        discovery_callback=expand, discovery_coverage=initial_coverage)
    result = {"context": context, "criteria": criteria, "subject": subject,
              "observed_at": datetime.now(timezone.utc).isoformat(), **ranked, "discovery": discovery["report"]}
    result["summary"]["shortfall"] = max(0, criteria["target"] - len(ranked["selected"]))
    result["summary"]["enrichment_access_limit"] = stop.is_set() and source_stop is None
    result["summary"]["source_stop_reason"] = source_stop
    result["run_id"] = hashlib.sha256(canonical(result).encode()).hexdigest()[:24]
    folder = DATA / "compsets" / result["run_id"]
    folder.mkdir(parents=True, exist_ok=True)
    _write_json(folder / "compset.json", result)
    export_csv(folder / "candidates.csv", ranked["candidates"], ["listing_id", "title", "selected", "eligibility", "distance_km", "bedrooms", "bathrooms", "rating", "similarity_score", "rejection_reasons"])
    _write_json(DATA / "compset-latest.json", result)
    candidate_count = len(ranked["candidates"])
    progress("complete", f'Comp set ready: {len(ranked["selected"])} selected from {candidate_count} candidates.', processed=candidate_count, total=candidate_count)
    return result
