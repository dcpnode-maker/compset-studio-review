"""Paced, resumable one-night stay quotes with source-proven calendar skips."""
from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

from .availability import calendar_preflight
from .nightly import window_context
from .pipeline import DATA, ROOT, _write_json, build_result, canonical, export_csv, persist

FRESH_SECONDS = 6 * 3600
KEY_FIELDS = ("listing_id", "checkin", "checkout", "adults", "children", "infants", "pets", "currency")


def fresh(stamp, now):
    try:
        return 0 <= (now - datetime.fromisoformat(stamp)).total_seconds() <= FRESH_SECONDS
    except (ValueError, TypeError):
        return False


def plan_quotes(data_dir=DATA, *, now=None, snapshot=None, calendar_report=None, context_override=None):
    """Plan every date for the subject and selected set, retaining negative evidence."""
    root = Path(data_dir)
    now = now or datetime.now(timezone.utc)
    snapshot = snapshot or json.loads((root / "compset-latest.json").read_text(encoding="utf-8"))
    calendar = calendar_report or json.loads((root / "nightly-monitoring-latest.json").read_text(encoding="utf-8"))
    if (not isinstance(snapshot, dict) or not isinstance(snapshot.get("context"), dict)
            or not isinstance(snapshot.get("selected"), list)
            or any(not isinstance(row, dict) for row in snapshot["selected"])
            or not isinstance(calendar, dict) or not isinstance(calendar.get("context"), dict)
            or not isinstance(calendar.get("records"), list)):
        raise ValueError("Saved selection and calendar job must contain typed contexts and rows")
    context = dict(context_override) if context_override is not None else window_context({"listing": snapshot["context"]["listing_id"],
                              "currency": calendar["context"]["currency"]}, now=now)
    identifiers = list(dict.fromkeys([context["listing_id"]] + [str(r["listing_id"]) for r in snapshot["selected"]]))
    if len(identifiers) > 101 or any(not re.fullmatch(r"\d{1,25}", value) for value in identifiers):
        raise ValueError("Expected a numeric subject and at most 100 selected listings")
    records = {str(r.get("listing_id")): r for r in calendar["records"] if isinstance(r, dict)}
    subject_record = calendar.get('subject_record')
    if isinstance(subject_record, dict) and subject_record.get('listing_id') == context['listing_id']:
        records[context['listing_id']] = subject_record
    try:
        subject = json.loads((root / "latest.json").read_text(encoding="utf-8"))
        if (isinstance(subject, dict) and isinstance(subject.get("context"), dict)
                and subject["context"].get("listing_id") == context["listing_id"]
                and context['listing_id'] not in records):
            records[context["listing_id"]] = {"run_id": subject.get("run_id")}
    except (OSError, ValueError):
        pass
    plan = []
    for identifier in identifiers:
        source = None
        run_id = records.get(identifier, {}).get("run_id", "")
        if isinstance(run_id, str) and re.fullmatch(r"[a-f0-9]{24}", run_id):
            try:
                candidate = json.loads((root / "runs" / run_id / "source.json").read_text(encoding="utf-8"))
                if (not isinstance(candidate, dict) or not isinstance(candidate.get("context"), dict)
                        or not isinstance(candidate.get("payloads"), list)
                        or any(not isinstance(p, dict) for p in candidate["payloads"])):
                    raise ValueError("Malformed calendar source")
                actual = candidate["context"]
                expected = {**context, "listing_id": identifier}
                if fresh(actual.get("observed_at"), now) and all(actual.get(k) == expected[k] for k in
                        ("listing_id", "start_date", "end_date", "adults", "children", "infants", "pets", "currency")):
                    source = candidate
            except (OSError, ValueError, KeyError, TypeError):
                pass
        for offset in range(30):
            arrival = date.fromisoformat(context["start_date"]) + timedelta(days=offset)
            target = {**context, "listing_id": identifier, "checkin": str(arrival), "checkout": str(arrival + timedelta(days=1))}
            # Locale is presentation context. Use its actual captured value for
            # calendar preflight; never rewrite source party, identity or dates.
            locales = {p["request_context"].get("locale") for p in (source or {}).get("payloads", [])
                       if isinstance(p.get("request_context"), dict) and "Calendar" in str(p.get("source_url", ""))
                       and isinstance(p["request_context"].get("locale"), str)
                       and re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", p["request_context"]["locale"])}
            if len(locales) == 1 and None not in locales:
                target["locale"] = next(iter(locales))
            preflight = calendar_preflight(source["payloads"], target) if source else {
                "decision": "proceed_quote", "result": "unknown", "reason": "fresh_calendar_not_observed", "evidence": []}
            plan.append({"context": target, "calendar_run_id": run_id if source else None,
                         "calendar_observed_at": source["context"]["observed_at"] if source else None,
                         "preflight": preflight})
    return context, snapshot["run_id"], plan


def _key(context):
    return canonical({k: context[k] for k in KEY_FIELDS})


def _save_quotes(root, run_id, quotes, parser_hash):
    """Append current derived evidence and retain every earlier parser revision."""
    with closing(sqlite3.connect(root / "compset.sqlite3")) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        for kind in ("one_night_quote", "one_night_quote_revision:" + parser_hash):
            db.executemany("INSERT OR IGNORE INTO observations VALUES(?,?,?,?)",
                [(run_id, kind, index, canonical({**quote, "price_parser_sha256": parser_hash}))
                 for index, quote in enumerate(quotes)])


def collect_one_night(*, data_dir=DATA, request_budget=100, interval_seconds=3.0, headless=True,
                      force_fresh=False, snapshot=None, calendar_report=None, context_override=None,
                      progress_fn=None, stop_requested=None, job_id=None, skip_network_reason=None):
    """Use one fresh browser template and serial reads; never retry a broken contract."""
    from scrapling.fetchers import FetcherSession
    from .batch import retarget_template
    from .collect import _quiet_scrapling, collect, read_operation, replay_observed
    from .one_night_rows import extract_one_night_quotes

    if type(request_budget) is not int or not 0 <= request_budget <= 3030:
        raise ValueError("Choose a request budget from 0 to 3030")
    interval_seconds = max(3.0, float(interval_seconds))
    if not interval_seconds < 60:
        raise ValueError("Choose an interval below sixty seconds")
    root = Path(data_dir)
    context, compset_id, plan = plan_quotes(root, snapshot=snapshot, calendar_report=calendar_report,
                                          context_override=context_override)
    price_parser_hash = hashlib.sha256(b"".join(name.encode() + b"\0" + (ROOT / "compset" / name).read_bytes()
        for name in ("one_night_rows.py", "normalize.py"))).hexdigest()
    fingerprint = hashlib.sha256(b"".join((ROOT / "compset" / name).read_bytes() for name in
        ("one_night.py", "one_night_rows.py", "normalize.py", "collect.py", "availability.py", "batch.py"))).hexdigest()
    signature = hashlib.sha256(canonical({"compset": compset_id, "parser": fingerprint,
        "plan": [{"key": _key(row["context"]), "calendar": row["calendar_run_id"]} for row in plan]}).encode()).hexdigest()
    output = root / "one-night-latest.json"
    report = {"state": "running", "signature": signature,
              "workspace_job_id": job_id,
              "context": {**{k: v for k, v in context.items() if k not in {"checkin", "checkout"}}, "stay_nights": 1},
              "compset_run_id": compset_id, "total_date_cells": len(plan), "records": [],
              "listing_ids": list(dict.fromkeys(row["context"]["listing_id"] for row in plan)),
              "price_parser_sha256": price_parser_hash,
              "direct_requests_this_run": 0, "bootstrap_browser_visits": 0,
              "interval_seconds": interval_seconds, "amount_kind": "one_night_stay_total",
              "warnings": ["One-night totals are contextual stay quotes; minimum-stay failures do not mean the night is booked.",
                           "Tax, fee and cancellation terms remain unknown unless the source states them."]}
    cached = {}
    plan_keys = {_key(row["context"]) for row in plan}
    if output.exists() and not force_fresh:
        try:
            previous = json.loads(output.read_text(encoding="utf-8"))
            # Parser revisions may recover an earlier unknown response. Always
            # reparse raw, fresh source evidence; reuse only keys in today's plan.
            # Never trust a checkpoint amount or copy its planning metadata.
            if isinstance(previous, dict) and isinstance(previous.get("records"), list):
                for record in previous["records"]:
                    try:
                        if not isinstance(record, dict) or record.get("status") not in {"quoted", "unknown"} or not fresh(record.get("observed_at"), datetime.now(timezone.utc)):
                            continue
                        key = _key(record["context"])
                        if key not in plan_keys:
                            continue
                        run_id = record.get("run_id", "")
                        if not isinstance(run_id, str) or not re.fullmatch(r"[a-f0-9]{24}", run_id):
                            continue
                        source = json.loads((root / "runs" / run_id / "source.json").read_text(encoding="utf-8"))
                        if _key(source["context"]) != key or not fresh(source["context"].get("observed_at"), datetime.now(timezone.utc)):
                            continue
                        quotes = extract_one_night_quotes(source["payloads"], source["context"])
                        if quotes and all(q.get("status") == "quoted" for q in quotes):
                            _save_quotes(root, run_id, quotes, price_parser_hash)
                            cached[key] = {"run_id": run_id, "quotes": quotes, "status": "quoted",
                                "context": source["context"], "observed_at": source["context"]["observed_at"]}
                    except (OSError, ValueError, KeyError, TypeError, AttributeError, sqlite3.Error):
                        continue
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            cached = {}
    pending = []
    for row in plan:
        if row["preflight"]["decision"] == "skip_quote":
            report["records"].append({**row, "status": "calendar_skipped", "quotes": [],
                                      "observed_at": row["calendar_observed_at"]})
        elif _key(row["context"]) in cached:
            report["records"].append({**row, **cached[_key(row["context"])]})
        else:
            pending.append(row)
    pause = root / "pause-one-night.flag"

    def checkpoint():
        report["updated_at"] = datetime.now(timezone.utc).isoformat()
        report["quoted_date_cells"] = sum(r["status"] == "quoted" for r in report["records"])
        report["calendar_skipped_date_cells"] = sum(r["status"] == "calendar_skipped" for r in report["records"])
        report["unknown_date_cells"] = report["total_date_cells"] - report["quoted_date_cells"] - report["calendar_skipped_date_cells"]
        _write_json(output, report)
        observed_keys = {_key(row["context"]) for row in report["records"]}
        export_rows = report["records"] + [{**row, "status": "not_requested", "quotes": []}
                                          for row in plan if _key(row["context"]) not in observed_keys]
        flattened = [{**{k: row["context"][k] for k in KEY_FIELDS}, "status": row["status"],
                      "reason": row["preflight"]["reason"], "calendar_run_id": row["calendar_run_id"],
                      "run_id": row.get("run_id"), **quote}
                     for row in export_rows for quote in (row["quotes"] or [{}])]
        export_csv(root / "one-night-prices.csv", flattened, ["listing_id", "checkin", "checkout", "status", "amount", "currency"])
        if progress_fn:
            progress_fn(report)

    def requested_stop():
        return (stop_requested() if stop_requested else None) or ('pause_requested' if pause.exists() else None)

    def save_capture(row, capture):
        target = row["context"]
        parsed = build_result(capture, target)
        persist(capture, parsed, root, update_latest=False)
        quotes = extract_one_night_quotes(capture.get("payloads", []), target)
        ok = bool(quotes) and all(q.get("status") == "quoted" for q in quotes)
        _save_quotes(root, parsed["run_id"], quotes, price_parser_hash)
        report["records"].append({**row, "run_id": parsed["run_id"], "quotes": quotes,
                                  "status": "quoted" if ok else "unknown", "observed_at": target["observed_at"]})
        checkpoint()
        return ok

    checkpoint()
    stopping = requested_stop() or skip_network_reason
    if not pending or request_budget == 0 or stopping:
        report["state"] = ("paused" if stopping == 'pause_requested' else "stopped") if stopping else "complete" if not pending else "budget_reached"
        if stopping:
            report['stop_reason'] = stopping
        checkpoint()
        return report
    templates = []
    try:
        first = pending[0]
        first["context"]["observed_at"] = datetime.now(timezone.utc).isoformat()
        capture = collect(first["context"], headless=headless, template_sink=templates)
        report["bootstrap_browser_visits"] = capture["report"].get("browser_navigations", 0)
        report["bootstrap_report"] = capture["report"]
        ok = save_capture(first, capture)
        source_id = first["context"]["listing_id"]
        template = next((t for t in templates if t.get("method") == "POST" and
                         read_operation(t.get("url", ""), "POST", t.get("body")) == "StaysPdpSections"), None)
        if capture["report"].get("stop_reason") or not ok or template is None:
            report.update(state="stopped", stop_reason=capture["report"].get("stop_reason") or "one_night_contract_not_verified")
            return report
        with _quiet_scrapling(), FetcherSession(retries=1, timeout=20, stealthy_headers=False,
                                               impersonate=None, follow_redirects=False) as session:
            previous_start = time.monotonic()
            for row in pending[1:]:
                stopping = requested_stop()
                if stopping:
                    report.update(state='paused' if stopping == 'pause_requested' else 'stopped', stop_reason=stopping)
                    break
                if report["direct_requests_this_run"] >= request_budget:
                    report["state"] = "budget_reached"
                    break
                time.sleep(max(0, interval_seconds - (time.monotonic() - previous_start)))
                stopping = requested_stop()
                if stopping:
                    report.update(state='paused' if stopping == 'pause_requested' else 'stopped', stop_reason=stopping)
                    break
                row["context"]["observed_at"] = datetime.now(timezone.utc).isoformat()
                target = row["context"]
                updated = retarget_template(template, source_id, target)
                previous_start = time.monotonic()
                replay = replay_observed([updated], target, session, limit=1)
                report["direct_requests_this_run"] += len(replay["requests"])
                child = {"payloads": replay.pop("payloads"), "report": {"direct_replay": replay, "stop_reason": replay.get("stop_reason")}}
                ok = save_capture(row, child)
                if replay.get("stop_reason") or not ok:
                    report.update(state="stopped", stop_reason=replay.get("stop_reason") or "one_night_contract_or_quote_gap")
                    break
            else:
                report["state"] = "complete"
    except Exception as exc:
        report.update(state="stopped", stop_reason="job_error", error_type=type(exc).__name__)
        raise
    finally:
        templates.clear()
        checkpoint()
    return report
