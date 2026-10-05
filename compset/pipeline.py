"""Bounded collection, provenance, append-only observations and local exports."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def context_from(values: dict) -> dict:
    listing = str(values.get("listing", "1567889913136387224")).strip()
    if listing.startswith("https://"):
        url = urlsplit(listing)
        if url.hostname not in {"www.airbnb.com", "airbnb.com", "www.airbnb.co.in", "www.airbnb.ae"} or url.username or url.password or url.port:
            raise ValueError("Use an Airbnb listing URL or numeric listing ID.")
        match = re.fullmatch(r"/rooms/(\d{1,25})/?", url.path)
        if not match:
            raise ValueError("The listing URL must contain /rooms/<listing ID>.")
        listing = match[1]
    if not re.fullmatch(r"\d{1,25}", listing):
        raise ValueError("Listing ID must contain only digits.")
    today = datetime.now(timezone(timedelta(hours=4))).date()
    checkin = date.fromisoformat(values.get("checkin") or str(today + timedelta(days=14)))
    checkout = date.fromisoformat(values.get("checkout") or str(checkin + timedelta(days=3)))
    start = date.fromisoformat(values.get("start_date") or str(today))
    def bounded_integer(key, default):
        value = values.get(key, default)
        if type(value) is int:
            return value
        if isinstance(value, str) and re.fullmatch(r"\d{1,3}", value):
            return int(value)
        raise ValueError(f"{key} must be a whole number.")
    days = bounded_integer("days", 30)
    adults = bounded_integer("adults", 1)
    if not 1 <= days <= 366 or not 1 <= adults <= 16:
        raise ValueError("Choose 1–366 calendar days and 1–16 adults.")
    if not 1 <= (checkout - checkin).days <= 90:
        raise ValueError("The stay must last 1–90 nights.")
    if checkin < today or start < today:
        raise ValueError("Use today or a future date; past availability cannot be reconstructed.")
    currency = str(values.get("currency", "AED")).upper()
    if currency not in {"AED", "SAR", "USD", "EUR", "GBP", "INR"}:
        raise ValueError("Choose AED, SAR, USD, EUR, GBP or INR.")
    return {"listing_id": listing, "checkin": str(checkin), "checkout": str(checkout),
            "start_date": str(start), "end_date": str(start + timedelta(days=days)),
            "adults": adults, "children": 0, "infants": 0, "pets": 0,
            "currency": currency, "locale": "en", "observed_at": datetime.now(timezone.utc).isoformat()}


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def build_result(capture: dict, context: dict) -> dict:
    from .normalize import normalize
    normalized = normalize(capture.get("payloads", []), context)
    start, end = date.fromisoformat(context["start_date"]), date.fromisoformat(context["end_date"])
    observed = {row["date"]: row for row in normalized["calendar"] if str(start) <= row["date"] < str(end)}
    rows = []
    for offset in range((end - start).days):
        day = str(start + timedelta(days=offset))
        rows.append(observed.get(day) or {"date": day, "availability": "unknown", "available": None,
                     "price_amount": None, "price_display": None, "currency": context["currency"],
                     "observed_at": None, "source_url": None, "source_path": None,
                     "reason": "not_observed", "listing_id": context["listing_id"]})
    coverage = {"requested_days": len(rows), "observed_days": len(observed), "missing_days": len(rows) - len(observed),
                "available_days": sum(r.get("availability") == "available" for r in rows),
                "unavailable_days": sum(r.get("availability") == "unavailable" for r in rows),
                "unknown_days": sum(r.get("availability") == "unknown" for r in rows),
                "priced_days": sum(r.get("price_amount") is not None for r in rows)}
    parser_hash = hashlib.sha256((ROOT / "compset" / "normalize.py").read_bytes()).hexdigest()
    identity = canonical({"version": VERSION, "parser_sha256": parser_hash, "context": context, "capture": capture})
    run_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
    warnings = list(normalized["warnings"])
    if coverage["missing_days"]:
        warnings.append(f'{coverage["missing_days"]} requested calendar dates were not observed.')
    if not coverage["priced_days"]:
        warnings.append("No numeric nightly calendar prices were returned; dated stay quotes are separate.")
    return {"run_id": run_id, "parser_version": VERSION, "parser_sha256": parser_hash, "context": context,
            "listing": normalized["listing"], "calendar": rows, "quotes": normalized["quotes"],
            "warnings": warnings, "report": capture.get("report", {}), "coverage": coverage,
            "source_sha256": hashlib.sha256(canonical(capture).encode()).hexdigest()}


def _write_json(path: Path, value) -> None:
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    for attempt in range(6):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))


def _csv_value(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = canonical(value)
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_csv(path: Path, rows: list[dict], base_fields: list[str]) -> None:
    fields = list(dict.fromkeys(base_fields + sorted({key for row in rows for key in row})))
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(value) for key, value in row.items()})


def persist(capture: dict, result: dict, data_dir: Path = DATA, *, update_latest=True) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    output = data_dir / "runs" / result["run_id"]
    output.mkdir(parents=True, exist_ok=True)
    from .health import airbnb_health
    _write_json(output / "contract-health.json", airbnb_health(capture, result, data_dir))
    _write_json(output / "source.json", {"context": result["context"], **capture})
    _write_json(output / "result.json", result)
    export_csv(output / "calendar.csv", result["calendar"], ["date", "availability", "price_amount", "currency"])
    export_csv(output / "quotes.csv", result["quotes"], ["checkin", "checkout", "price_basis", "total_amount", "currency"])
    with closing(sqlite3.connect(data_dir / "compset.sqlite3")) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, observed_at TEXT NOT NULL, listing_id TEXT NOT NULL, result_json TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS observations(run_id TEXT NOT NULL REFERENCES runs(run_id), kind TEXT NOT NULL, ordinal INTEGER NOT NULL, record_json TEXT NOT NULL, PRIMARY KEY(run_id,kind,ordinal))")
        db.execute("INSERT OR IGNORE INTO runs VALUES(?,?,?,?)", (result["run_id"], result["context"]["observed_at"], result["context"]["listing_id"], canonical(result)))
        for kind, rows in (("listing", [result["listing"]]), ("calendar", result["calendar"]), ("quote", result["quotes"])):
            db.executemany("INSERT OR IGNORE INTO observations VALUES(?,?,?,?)", [(result["run_id"], kind, i, canonical(row)) for i, row in enumerate(rows)])
    if update_latest:
        _write_json(data_dir / "latest.json", result)
    return output


def run(context: dict, *, data_dir: Path = DATA, capture: dict | None = None) -> dict:
    if capture is None:
        from .collect import collect
        capture = collect(context)
    result = build_result(capture, context)
    persist(capture, result, data_dir)
    return result
