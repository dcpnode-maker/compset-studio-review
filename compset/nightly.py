"""Thirty-day, one-adult evidence jobs; calendar rates and stay quotes stay separate."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from .pipeline import DATA, ROOT, _write_json, build_result, canonical, context_from, export_csv, persist

DUBAI = timezone(timedelta(hours=4), "Asia/Dubai")


def window_context(values=None, *, now=None):
    values = dict(values or {})
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("An aware execution time is required")
    today = now.astimezone(DUBAI).date()
    if type(values.get("adults", 1)) is not int or values.get("adults", 1) != 1 or type(values.get("days", 30)) is not int or values.get("days", 30) != 30:
        raise ValueError("This job observes thirty days for one adult")
    if any(type(values.get(key, 0)) is not int or values.get(key, 0) != 0 for key in ("children", "infants", "pets")):
        raise ValueError("This job has one adult, no children, infants or pets")
    if values.get("start_date") not in (None, str(today)):
        raise ValueError("The thirty-day window starts today in Asia/Dubai")
    return context_from({**values, "adults": 1, "days": 30, "start_date": str(today)})


def save_window(capture, result, *, data_dir=DATA):
    from .nightly_rows import build_nightly_rows
    evidence = build_nightly_rows(capture, result)
    evidence.update(run_id=result["run_id"], source_sha256=result["source_sha256"],
                    window_timezone="Asia/Dubai", subject=result["listing"],
                    report=result.get("report", {}))
    folder = Path(data_dir) / "nightly" / result["run_id"]
    folder.mkdir(parents=True, exist_ok=True)
    _write_json(folder / "nightly.json", evidence)
    export_csv(folder / "nightly.csv", evidence["rows"],
               ["listing_id", "date", "availability", "nightly_amount_for_requested_party", "calendar_display_amount", "currency"])
    export_csv(folder / "stay-quotes.csv", evidence["stay_quotes"],
               ["listing_id", "checkin", "checkout", "adults", "price_basis", "total_amount", "currency"])
    # Existing append-only run/observation tables preserve the source and the
    # derived party-verification fields without replacing historical records.
    with closing(sqlite3.connect(Path(data_dir) / "compset.sqlite3")) as db, db:
        db.executemany("INSERT OR IGNORE INTO observations VALUES(?,?,?,?)",
                       [(result["run_id"], "nightly_context", index, canonical(row))
                        for index, row in enumerate(evidence["rows"])])
    return evidence


def export_source(source_path, *, data_dir=DATA):
    """Reprocess a saved one-adult capture; never relabel historical parties."""
    capture = json.loads(Path(source_path).read_text(encoding="utf-8"))
    context = capture.pop("context")
    from .nightly_rows import build_nightly_rows
    result = build_result(capture, context)
    build_nightly_rows(capture, result)  # Validate before writing any artifacts.
    persist(capture, result, Path(data_dir), update_latest=False)
    evidence = save_window(capture, result, data_dir=data_dir)
    _write_json(Path(data_dir) / "nightly-latest.json", evidence)
    return evidence


def collect_selected(values=None, *, data_dir=DATA, max_listings=100, request_budget=100,
                     interval_seconds=3.0, headless=True, fresh=False, snapshot=None,
                     context_override=None, progress_fn=None, stop_requested=None, job_id=None):
    """One bootstrap, one reusable HTTP session, serial calendar-only reads.

    The request budget counts direct competitor calendar reads. The separately
    reported bootstrap uses one browser visit and at most eight read replays.
    Fresh completed observations are reused; source failures stay incomplete.
    """
    from scrapling.fetchers import FetcherSession
    from .batch import retarget_template
    from .collect import collect, read_operation, replay_observed, _quiet_scrapling
    from .nightly_rows import _positive

    if type(max_listings) is not int or not 1 <= max_listings <= 100:
        raise ValueError("Choose 1–100 selected competitors")
    if type(request_budget) is not int or not 0 <= request_budget <= 100:
        raise ValueError("Choose a finite calendar request budget of 0–100")
    interval_seconds = max(3.0, float(interval_seconds))
    if not interval_seconds < 60:
        raise ValueError("Choose an interval below sixty seconds")
    data_dir = Path(data_dir)
    workspace_collection = job_id is not None or context_override is not None or fresh
    snapshot = snapshot or json.loads((data_dir / "compset-latest.json").read_text(encoding="utf-8"))
    context = dict(context_override) if context_override is not None else window_context({"listing": snapshot["context"]["listing_id"], **(values or {})})
    if context["listing_id"] != snapshot["context"]["listing_id"]:
        raise ValueError("The selected comparison set belongs to a different subject")
    selected, seen = [], set()
    for row in snapshot.get("selected", []):
        identifier = str(row.get("listing_id", ""))
        if identifier.isdigit() and 1 <= len(identifier) <= 25 and identifier not in seen and identifier != context["listing_id"]:
            seen.add(identifier)
            selected.append({**row, "listing_id": identifier})
    selected = selected[:max_listings]
    fingerprint = hashlib.sha256((ROOT / "compset/nightly_rows.py").read_bytes() +
                                 (ROOT / "compset/normalize.py").read_bytes()).hexdigest()
    key = {k: context[k] for k in ("listing_id", "start_date", "end_date", "adults", "children", "infants", "pets", "currency", "locale")}
    signature = hashlib.sha256(canonical({"context": key, "compset": snapshot["run_id"],
                                          "ids": [r["listing_id"] for r in selected], "parser": fingerprint}).encode()).hexdigest()
    output = data_dir / "nightly-monitoring-latest.json"
    report = {"state": "running", "signature": signature, "context": context, "window_timezone": "Asia/Dubai",
              "workspace_job_id": job_id,
              "compset_run_id": snapshot["run_id"], "selection_observed_at": snapshot.get("observed_at"),
              "selection_criteria": snapshot.get("criteria"), "discovery_coverage": snapshot.get("discovery"),
              "total": len(selected), "records": [], "direct_requests_this_run": 0,
              "bootstrap_browser_visits": 0, "interval_seconds": interval_seconds, "route": "direct",
              "warnings": ["Comparison membership uses the saved attribute audit; nightly reads do not establish complete market coverage."]}
    if output.exists() and not fresh:
        try:
            previous = json.loads(output.read_text(encoding="utf-8"))
            if isinstance(previous, dict) and previous.get("signature") == signature and isinstance(previous.get("records"), list):
                try:
                    subject_record = previous.get('subject_record', {})
                    run_id = subject_record.get('run_id', '')
                    if not isinstance(run_id, str) or len(run_id) != 24 or any(c not in '0123456789abcdef' for c in run_id):
                        raise ValueError('No reusable subject')
                    source = json.loads((data_dir / 'runs' / run_id / 'source.json').read_text(encoding='utf-8'))
                    actual = source['context']
                    age = (datetime.now(timezone.utc) - datetime.fromisoformat(actual['observed_at'])).total_seconds()
                    if not 0 <= age <= 21600 or any(actual.get(k) != v or type(actual.get(k)) is not type(v) for k, v in key.items()):
                        raise ValueError('Subject context expired or changed')
                    parsed = build_result(source, actual)
                    if parsed['coverage']['observed_days'] != 30 or parsed['coverage']['unknown_days'] != 0:
                        raise ValueError('Subject calendar incomplete')
                    report['subject_record'] = dict(subject_record)
                except (OSError, ValueError, TypeError, KeyError):
                    pass
                reused = set()
                for record in previous.get("records", []):
                    try:
                        identifier = str(record["listing_id"])
                        run_id = record["run_id"]
                        if not isinstance(run_id, str) or len(run_id) != 24 or any(ch not in "0123456789abcdef" for ch in run_id):
                            continue
                        age = (datetime.now(timezone.utc) - datetime.fromisoformat(record["observed_at"])).total_seconds()
                        if identifier not in {row["listing_id"] for row in selected} or identifier in reused or record.get("collection_status") != "observed" or not 0 <= age <= 6 * 3600:
                            continue
                        artifact = json.loads((data_dir / "nightly" / run_id / "nightly.json").read_text(encoding="utf-8"))
                        expected = {**key, "listing_id": identifier}
                        if not isinstance(artifact, dict) or any(artifact.get("context", {}).get(field) != value for field, value in expected.items()):
                            continue
                        source_age = (datetime.now(timezone.utc) - datetime.fromisoformat(artifact["context"]["observed_at"])).total_seconds()
                        if artifact.get("run_id") != run_id or not 0 <= source_age <= 6 * 3600:
                            continue
                        rows = artifact.get("rows")
                        first_day = datetime.fromisoformat(context["start_date"]).date()
                        dates = {str(first_day + timedelta(days=offset)) for offset in range(30)}
                        if not isinstance(rows, list) or len(rows) != 30 or any(not isinstance(row, dict) or str(row.get("listing_id")) != identifier or type(row.get("available")) is not bool for row in rows) or {row.get("date") for row in rows} != dates:
                            continue
                        coverage = {
                            "requested_days": 30,
                            "observed_calendar_days": sum(bool(row.get("source_evidence")) for row in rows),
                            "available_days": sum(row["available"] is True for row in rows),
                            "unavailable_days": sum(row["available"] is False for row in rows),
                            "unknown_days": 0,
                            "calendar_display_price_days": sum(_positive(row.get("calendar_display_amount")) is not None for row in rows),
                            "verified_nightly_price_days": sum(row.get("guest_context_verified") is True and bool(row.get("source_evidence")) and _positive(row.get("nightly_amount_for_requested_party")) is not None for row in rows),
                            "verified_one_adult_stay_quotes": sum(isinstance(quote, dict) and quote.get("guest_context_verified") is True for quote in artifact.get("stay_quotes", [])),
                        }
                        if coverage["observed_calendar_days"] != 30:
                            continue
                        reused.add(identifier)
                        report["records"].append({**record, "listing_id": identifier, "coverage": coverage})
                    except (ValueError, TypeError, KeyError, AttributeError, OSError):
                        continue
        except (ValueError, TypeError, KeyError, OSError):
            pass
    done = {row["listing_id"] for row in report["records"]}
    pending = [row for row in selected if row["listing_id"] not in done]
    pause = data_dir / "pause-nightly.flag"

    def checkpoint():
        report["processed"] = len(report["records"])
        report["requested_calendar_rows"] = 30 * len(selected)
        report["verified_nightly_price_rows"] = sum(record.get("coverage", {}).get("verified_nightly_price_days", 0) for record in report["records"])
        report["requested_party_prices_complete"] = bool(selected) and report["verified_nightly_price_rows"] == report["requested_calendar_rows"]
        report["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(output, report)
        if progress_fn:
            progress_fn(report)

    def requested_stop():
        return (stop_requested() if stop_requested else None) or ('pause_requested' if pause.exists() else None)

    checkpoint()
    stopping = requested_stop()
    if (not pending and (report.get('subject_record') or not workspace_collection)) or request_budget == 0 or stopping:
        report["state"] = ("paused" if stopping == 'pause_requested' else "stopped") if stopping else "complete" if not pending else "budget_reached"
        if stopping:
            report['stop_reason'] = stopping
        checkpoint()
        return report
    templates = []
    # Frozen resume context fixes dates and guests, not the observation clock.
    # Only an actual source start receives a fresh timestamp; cache-only paths
    # above retain their original source timestamps.
    context['observed_at'] = datetime.now(timezone.utc).isoformat()
    capture = collect(context, headless=headless, template_sink=templates)
    report["bootstrap_browser_visits"] = capture["report"].get("browser_navigations", 0)
    report["bootstrap_report"] = capture["report"]
    subject = build_result(capture, context)
    persist(capture, subject, data_dir, update_latest=False)
    save_window(capture, subject, data_dir=data_dir)
    report['subject_record'] = {'listing_id': context['listing_id'], 'run_id': subject['run_id'],
                                'observed_at': context['observed_at'], 'coverage': subject['coverage']}
    stop_reason = capture["report"].get("stop_reason")
    calendar_template = next((t for t in templates if "Calendar" in (read_operation(t.get("url", ""), t.get("method", "")) or "")), None)
    try:
        if stop_reason or calendar_template is None:
            report.update(state="stopped", stop_reason=stop_reason or "calendar_template_not_observed")
            return report
        with _quiet_scrapling(), FetcherSession(retries=1, timeout=20, stealthy_headers=False,
                                               impersonate=None, follow_redirects=False) as session:
            previous_start = time.monotonic() if workspace_collection else None
            for candidate in pending:
                stopping = requested_stop()
                if stopping:
                    report.update(state='paused' if stopping == 'pause_requested' else 'stopped', stop_reason=stopping)
                    break
                if report["direct_requests_this_run"] >= request_budget:
                    report["state"] = "budget_reached"
                    break
                if previous_start is not None:
                    time.sleep(max(0, interval_seconds - (time.monotonic() - previous_start)))
                stopping = requested_stop()
                if stopping:
                    report.update(state='paused' if stopping == 'pause_requested' else 'stopped', stop_reason=stopping)
                    break
                target = {**context, "listing_id": str(candidate["listing_id"]), "observed_at": datetime.now(timezone.utc).isoformat()}
                template = retarget_template(calendar_template, context["listing_id"], target)
                previous_start = time.monotonic()
                replay = replay_observed([template], target, session, limit=1)
                report["direct_requests_this_run"] += len(replay["requests"])
                child_capture = {"payloads": replay.pop("payloads"), "report": {"direct_replay": replay, "stop_reason": replay.get("stop_reason"), "route": "direct"}}
                child = build_result(child_capture, target)
                child["listing"] = {**candidate, **{k: v for k, v in child["listing"].items() if v is not None and v != {}}}
                persist(child_capture, child, data_dir, update_latest=False)
                evidence = save_window(child_capture, child, data_dir=data_dir)
                observed = child["coverage"]["observed_days"] == 30 and child["coverage"]["unknown_days"] == 0 and not replay.get("stop_reason") and all(
                    req.get("status") == 200 and req.get("json_captured") and not req.get("graphql_errors") for req in replay["requests"])
                report["records"] = [r for r in report["records"] if r["listing_id"] != target["listing_id"]]
                report["records"].append({"listing_id": target["listing_id"], "run_id": child["run_id"],
                    "observed_at": target["observed_at"], "coverage": evidence["coverage"],
                    "collection_status": "observed" if observed else "incomplete", "price_coverage": "reported_separately"})
                checkpoint()
                # Unknown schema/transport outcomes stop this finite session;
                # never repeat the same broken contract across all candidates.
                if not observed:
                    report.update(state="stopped", stop_reason=replay.get("stop_reason") or "calendar_coverage_or_contract_gap")
                    break
            else:
                report["state"] = "complete"
    finally:
        templates.clear()
        checkpoint()
    return report
