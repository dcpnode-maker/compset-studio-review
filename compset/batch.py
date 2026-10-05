"""Bounded two-worker competitor observations using one browser bootstrap.

Observed request templates exist only in memory. Run artifacts contain sanitized
public responses. All persistence happens on the coordinating thread.
"""
from __future__ import annotations

import base64
import binascii
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from threading import Event
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .availability import calendar_preflight
from .collect import (STOP_STATUSES, _quiet_scrapling, calendar_replay_url, collect,
                      read_operation, replay_observed, request_context, validate_context)
from .pipeline import DATA, _write_json, build_result, canonical, persist

MAX_LISTINGS = 100
WORKERS = 2


def retarget_template(template: dict, source_id: str, context: dict) -> dict:
    """Replace observed listing/date fields only; keep query hash and ID types."""
    context = validate_context(context)
    url = template.get("url", "")
    method = template.get("method", "")
    body = deepcopy(template.get("body")) if method == "POST" else None
    operation = read_operation(url, method, body)
    sections = method == "POST" and operation == "StaysPdpSections"
    if not operation or not ("Calendar" in operation or operation == "StaysPdpBookItQuery" or sections):
        raise ValueError("Only observed public calendar, BookIt GET and Sections POST templates are supported")
    original = request_context(url, method, body)
    if original.get("conflicts"):
        raise ValueError("Observed request context contains conflicting or invalid fields")
    if original.get("listing_id") != source_id:
        raise ValueError("Observed template does not identify the subject listing")
    if sections and any(original.get(key) != context[key]
                        for key in ("adults", "children", "infants", "pets", "currency")):
        raise ValueError("Observed Sections party and currency must already match the requested context")
    parts = urlsplit(url)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    if sections:
        variables = body["variables"]
    else:
        if sum(key == "variables" for key, _ in pairs) != 1:
            raise ValueError("Template must have one variables object")
        try:
            variables = json.loads(dict(pairs)["variables"])
        except (KeyError, ValueError, TypeError):
            raise ValueError("Template variables are invalid") from None
    if not isinstance(variables, dict):
        raise ValueError("Template variables must be an object")
    replaced = 0

    def identifier(value):
        nonlocal replaced
        if type(value) in (str, int) and str(value) == source_id:
            replaced += 1
            return int(context["listing_id"]) if type(value) is int else context["listing_id"]
        if isinstance(value, str):
            try:
                decoded = base64.b64decode(value, validate=True).decode("ascii")
            except (ValueError, binascii.Error, UnicodeError):
                return value
            for prefix in ("DemandStayListing:", "StayListing:"):
                if decoded == prefix + source_id:
                    replaced += 1
                    return base64.b64encode((prefix + context["listing_id"]).encode()).decode()
        return value

    def adjust(node, parent=""):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {"id", "listingId", "demandStayListingId"}:
                    node[key] = identifier(value)
                elif key in {"checkIn", "check_in"} and isinstance(value, str):
                    node[key] = context["checkin"]
                elif key in {"checkOut", "check_out"} and isinstance(value, str):
                    node[key] = context["checkout"]
                elif parent == "dateRange" and key in {"startDate", "endDate"} and isinstance(value, str):
                    node[key] = context["checkin" if key == "startDate" else "checkout"]
                elif isinstance(value, (dict, list)):
                    adjust(value, key)
        elif isinstance(node, list):
            for value in node:
                adjust(value, parent)

    adjust(variables)
    if not replaced:
        raise ValueError("Observed template does not identify the subject listing")
    if sections:
        updated_url = url
    else:
        pairs = [(key, json.dumps(variables, separators=(",", ":")) if key == "variables" else value)
                 for key, value in pairs]
        updated_url = calendar_replay_url(urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), "")), context)
    observed = request_context(updated_url, method, body)
    if observed.get("conflicts") or observed.get("listing_id") != context["listing_id"]:
        raise ValueError("Retargeted template listing identity was not verified")
    if operation == "StaysPdpBookItQuery" and any(observed.get(key) != context[key] for key in ("checkin", "checkout")):
        raise ValueError("Retargeted quote dates were not verified")
    if sections and any(observed.get(key) != context[key] for key in
                        ("checkin", "checkout", "adults", "children", "infants", "pets", "currency")):
        raise ValueError("Retargeted Sections stay, party and currency were not verified")
    result = {"url": updated_url, "method": method, "headers": deepcopy(template.get("headers", {}))}
    if sections:
        result["body"] = body
    return result


def _session_factory():
    from scrapling.fetchers import FetcherSession
    return FetcherSession(retries=1, timeout=20, stealthy_headers=False,
                          impersonate=None, follow_redirects=False)


def _fetch_one(candidate, templates, source_id, context, stopped):
    target = {**context, "listing_id": str(candidate["listing_id"]),
              "observed_at": datetime.now(timezone.utc).isoformat()}
    if stopped.is_set():
        return target, {"payloads": [], "report": {"stop_reason": "batch_stopped"}}
    try:
        requests = [retarget_template(template, source_id, target) for template in templates]
        calendar_requests = [request for request in requests if "Calendar" in read_operation(request["url"])]
        quote_requests = [request for request in requests if request not in calendar_requests]
        with _session_factory() as session:
            class GuardedSession:
                def get(self, url, **kwargs):
                    if stopped.is_set():
                        raise RuntimeError("Batch stopped before request")
                    response = session.get(url, **kwargs)
                    if response.status in STOP_STATUSES:
                        stopped.set()
                    return response

            guarded = GuardedSession()
            replay = replay_observed(calendar_requests, target, guarded, limit=len(calendar_requests))
            preflight = calendar_preflight(replay["payloads"], target)
            if replay.get("stop_reason") or any(
                    request.get("status") != 200 or not request.get("json_captured") or request.get("graphql_errors")
                    for request in replay["requests"]):
                preflight.update(decision="proceed_quote", result="unknown", reason="calendar_request_failed",
                                 retryable=None, evidence=[])
            skipped = len(quote_requests) if preflight["decision"] == "skip_quote" else 0
            if quote_requests and not skipped and not replay.get("stop_reason"):
                quoted = replay_observed(quote_requests, target, guarded, limit=len(quote_requests))
                replay["payloads"].extend(quoted["payloads"])
                replay["requests"].extend(quoted["requests"])
                replay["stop_reason"] = quoted.get("stop_reason")
        payloads = replay.pop("payloads")
        report = {"transport": "scrapling_http_batch", "browser_navigations": 0,
                  "direct_replay": replay, "stop_reason": replay.get("stop_reason"), "warnings": [],
                  "calendar_preflight": {**preflight, "quote_requests_skipped": skipped}}
        return target, {"payloads": payloads, "report": report}
    except Exception as exc:
        return target, {"payloads": [], "report": {"stop_reason": "batch_request_error",
                       "error_type": type(exc).__name__}}


def _selected_quote(result):
    options = [row for row in result.get("quotes", []) if row.get("quote_kind") == "rate_plan_total"
               and row.get("total_amount") is not None]
    selected = next((row for row in options if row.get("is_selected") is True), None)
    if selected is None:
        return None
    return {key: selected.get(key) for key in ("total_amount", "currency", "checkin", "checkout", "rate_plan")}


def _merge_listing(known, observed):
    combined = {**known, **{key: value for key, value in observed.items() if value is not None}}
    combined["field_sources"] = {**known.get("field_sources", {}), **observed.get("field_sources", {})}
    return combined


def monitor_compset(*, data_dir: Path = DATA, headless=True) -> dict:
    """Observe at most 100 selected listings; resume matching fresh completions."""
    data_dir = Path(data_dir)
    snapshot = json.loads((data_dir / "compset-latest.json").read_text(encoding="utf-8"))
    context = validate_context(snapshot["context"])
    source_id = context["listing_id"]
    rows, seen = [], set()
    for candidate in snapshot.get("selected", []):
        if not isinstance(candidate, dict):
            continue
        listing_id = str(candidate.get("listing_id", ""))
        if not re.fullmatch(r"\d{1,25}", listing_id) or listing_id == source_id or listing_id in seen:
            continue
        seen.add(listing_id)
        rows.append({**candidate, "listing_id": listing_id})
        if len(rows) == MAX_LISTINGS:
            break
    signature_context = {key: value for key, value in context.items() if key != "observed_at"}
    signature = hashlib.sha256(canonical({"compset": snapshot.get("run_id"), "context": signature_context,
                                          "selected": [row["listing_id"] for row in rows]}).encode()).hexdigest()
    now = datetime.now(timezone.utc)
    result = {"compset_run_id": snapshot.get("run_id"), "context": signature_context,
              "signature": signature, "state": "running", "processed": 0, "total": len(rows),
              "records": [], "started_at": now.isoformat(), "updated_at": now.isoformat(), "warnings": []}
    checkpoint = data_dir / "monitoring-latest.json"
    if checkpoint.exists():
        try:
            prior = json.loads(checkpoint.read_text(encoding="utf-8"))
            if prior.get("signature") == signature:
                for row in prior.get("records", []):
                    stamp = datetime.fromisoformat(row.get("observed_at", ""))
                    if (row.get("status") == "complete" and row.get("listing_id") in seen
                            and 0 <= (now - stamp).total_seconds() <= 3600):
                        result["records"].append(row)
        except (ValueError, TypeError, KeyError):
            pass
    completed = {row["listing_id"] for row in result["records"]}
    remaining = [row for row in rows if row["listing_id"] not in completed]

    def save(message):
        result["processed"] = len(result["records"])
        result["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(checkpoint, result)
        _write_json(data_dir / "progress.json", {"stage": "monitoring", "message": message,
                    "processed": result["processed"], "total": result["total"], "state": result["state"],
                    "updated_at": result["updated_at"]})

    save("Preparing bounded competitor observations")
    if not remaining:
        result["state"] = "complete"
        save("All selected listings already have fresh observations" if rows else "No selected listings to observe")
        return result
    templates = []
    subject_context = {**context, "observed_at": now.isoformat()}
    subject_capture = collect(subject_context, headless=headless, template_sink=templates)
    subject_result = build_result(subject_capture, subject_context)
    # Preserve previously enriched public subject attributes when this bootstrap
    # omits them; a missing value never erases known discovery evidence.
    subject_result["listing"] = _merge_listing(snapshot.get("subject", {}), subject_result["listing"])
    persist(subject_capture, subject_result, data_dir)
    if subject_capture.get("report", {}).get("stop_reason"):
        result["state"] = "stopped"
        result["warnings"].append("Subject bootstrap stopped: " + subject_capture["report"]["stop_reason"])
        save("Bootstrap stopped; no competitor requests started")
        templates.clear()
        return result
    picked, kinds = [], set()
    for template in templates:
        operation = read_operation(template.get("url", ""), template.get("method", ""))
        kind = "calendar" if operation and "Calendar" in operation else "quote" if operation == "StaysPdpBookItQuery" else None
        if not kind or kind in kinds:
            continue
        try:
            retarget_template(template, source_id, context)
        except ValueError:
            continue
        picked.append(template)
        kinds.add(kind)
    if len(kinds) < 2:
        result["warnings"].append("Observed template coverage: " + (", ".join(sorted(kinds)) or "none"))
    if not picked:
        result["state"] = "stopped"
        save("No verified calendar or quote request template was observed")
        templates.clear()
        return result
    stopped = Event()
    iterator = iter(remaining)
    try:
        with _quiet_scrapling(), ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {}
            for _ in range(min(WORKERS, len(remaining))):
                candidate = next(iterator)
                futures[pool.submit(_fetch_one, candidate, picked, source_id, context, stopped)] = candidate
            while futures:
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    candidate = futures.pop(future)
                    target, capture = future.result()
                    observation = build_result(capture, target)
                    observation["listing"] = _merge_listing(candidate, observation["listing"])
                    persist(capture, observation, data_dir, update_latest=False)
                    report = capture.get("report", {})
                    requests = report.get("direct_replay", {}).get("requests", [])
                    meaningful = (observation["coverage"]["observed_days"] > 0 or
                                  report.get("calendar_preflight", {}).get("decision") == "skip_quote" or
                                  _selected_quote(observation) is not None or
                                  any(row.get("status") == "unavailable" for row in observation.get("quotes", [])))
                    ok = (not report.get("stop_reason") and bool(requests) and
                          meaningful and
                          all(req.get("status") == 200 and req.get("json_captured") and not req.get("graphql_errors") for req in requests))
                    result["records"].append({"listing_id": target["listing_id"], "title": candidate.get("title"),
                        "run_id": observation["run_id"], "coverage": observation["coverage"],
                        "selected_quote": _selected_quote(observation), "warnings": observation["warnings"],
                        "status": "complete" if ok else "partial", "observed_at": target["observed_at"],
                        "stop_reason": report.get("stop_reason"), "calendar_preflight": report.get("calendar_preflight")})
                    save(f'Observed {len(result["records"])} of {len(rows)} selected listings')
                if not stopped.is_set():
                    for _ in range(WORKERS - len(futures)):
                        candidate = next(iterator, None)
                        if candidate is None:
                            break
                        futures[pool.submit(_fetch_one, candidate, picked, source_id, context, stopped)] = candidate
        result["state"] = "stopped" if stopped.is_set() else "complete"
        if stopped.is_set():
            result["warnings"].append("Access or rate limit encountered; no further competitor requests were started")
    except Exception as exc:
        result["state"] = "failed"
        result["warnings"].append("Batch interrupted by " + type(exc).__name__)
        raise
    finally:
        templates.clear()
        picked.clear()
        save("Competitor monitoring " + result["state"])
    return result
