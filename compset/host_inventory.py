"""Slow, cached, resumable hydration of a verified public host listing set."""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
from .pipeline import DATA, context_from, _write_json


def collect_host_inventory(manifest_path: Path, *, data_dir: Path = DATA, values=None):
    from .collect import _quiet_scrapling
    from .profile import enrich_subject_profile
    from .workflows import listing_detail
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ids = list(dict.fromkeys(str(identifier) for identifier in manifest["listing_ids"]))
    if len(ids) > 150 or any(not identifier.isdigit() for identifier in ids):
        raise ValueError("A bounded manifest of at most 150 public listing IDs is required")
    context = context_from(values or {})
    output = data_dir / "host-listings-source.json"
    result = {"profile": manifest, "context": context, "listings": [],
              "report": {"state": "running", "requested": len(ids), "processed": 0,
                         "workers": 1, "minimum_interval_seconds": 1, "stop_reason": None}}
    stop = threading.Event()
    next_start = time.monotonic()
    for identifier in ids:
        pause = data_dir / "pause-inventory.flag"
        if pause.exists():
            result["report"].update(state="paused", stop_reason="user_pause_requested")
            break
        time.sleep(max(0, next_start - time.monotonic()))
        next_start = time.monotonic() + 1
        with _quiet_scrapling():
            row = listing_detail(identifier, context, stop)
        row["listing_id"] = identifier
        row["profile_membership_evidence"] = {"profile_url": manifest["profile_url"],
                                              "observed_at": manifest["observed_at"]}
        if str(row.get("host_id")) == str(manifest.get("host_id")):
            row["host_profile_url"] = manifest["profile_url"]
            row["host_listing_count"] = manifest.get("declared_listing_count")
        result["listings"].append(enrich_subject_profile(row))
        result["report"]["processed"] = len(result["listings"])
        result["observed_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(output, result)
        if stop.is_set():
            result["report"].update(state="stopped", stop_reason="access_or_rate_limit")
            break
    if result["report"]["state"] == "running":
        result["report"]["state"] = "complete"
    _write_json(output, result)
    return result
