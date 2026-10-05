"""Local contract diagnostics; never infer observations or auto-approve semantics."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import re
from urllib.parse import urlsplit
from .pipeline import canonical, _write_json


def field_shape(value, path="$", depth=0):
    """Bounded field-path signature without prices, identities or session values."""
    if depth > 12:
        return set()
    paths = set()
    if isinstance(value, dict):
        for key, item in value.items():
            name = "<date>" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(key)) else str(key)
            target = path + "." + name
            paths.add(target)
            paths.update(field_shape(item, target, depth + 1))
    elif isinstance(value, list):
        for item in value[:16]:
            paths.update(field_shape(item, path + "[]", depth + 1))
    return paths


def observe_contracts(envelopes, semantic_alerts, data_dir):
    file = data_dir / "schema-health.json"
    try:
        prior = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}
        if not isinstance(prior, dict) or not isinstance(prior.get("contracts", {}), dict):
            raise ValueError("Invalid diagnostic baseline shape")
    except (ValueError, OSError):
        prior = {}
        semantic_alerts = [*semantic_alerts, {"code": "diagnostic_baseline_unreadable", "effect": "Response evidence is retained; rebuild the local diagnostic baseline."}]
    registry = prior.get("contracts", {})
    changes = []
    for envelope in envelopes:
        if envelope.get("status") != 200 or not isinstance(envelope.get("body"), (dict, list)):
            continue
        parts = urlsplit(envelope.get("source_url") or "")
        path = parts.path.split("/")
        operation = path[-2] if re.fullmatch(r"[a-f0-9]{64}", path[-1]) else path[-1]
        if not operation or operation.isdigit():
            continue
        key = parts.hostname + "/" + operation if parts.hostname else operation
        body = envelope["body"]
        if isinstance(body, dict) and body.get("message") == "SOLD_OUT":
            key += "/sold_out"
        paths = sorted(field_shape(envelope["body"]))
        signature = hashlib.sha256(canonical(paths).encode()).hexdigest()
        observed_hash = path[-1] if re.fullmatch(r"[a-f0-9]{64}", path[-1]) else None
        old = registry.get(key)
        if old is not None and not isinstance(old, dict):
            semantic_alerts = [*semantic_alerts, {"code": "diagnostic_entry_unreadable", "operation": key}]
            old = None
        if old and observed_hash and old.get("query_hash") != observed_hash:
            changes.append({"operation": key, "kind": "fresh_query_hash_observed", "action": "Use only this browser-observed template; validate parser output."})
        if old and old.get("field_signature") != signature:
            changes.append({"operation": key, "kind": "field_shape_changed", "action": "Review saved response and contract tests; a field-shape change alone does not establish a semantic change."})
        registry[key] = {"query_hash": observed_hash, "field_signature": signature, "field_paths": paths,
                         "last_seen_at": datetime.now(timezone.utc).isoformat()}
    # Deduplicate diagnostics from repeated responses within a single session.
    changes = list({canonical(row): row for row in changes}.values())
    result = {"observed_at": datetime.now(timezone.utc).isoformat(), "contracts": registry,
              "changes": changes, "semantic_alerts": semantic_alerts,
              "state": "attention_required" if semantic_alerts else "review_changes" if changes else "observed",
              "automatic_semantic_repair": False,
              "repair_workflow": "Inspect saved source; rediscover a live read request; update the versioned parser and regression fixture; run contract tests; reparse saved evidence; compare one live canary before resuming."}
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_json(file, result)
    return result


def airbnb_health(capture, result, data_dir):
    alerts = []
    urls = [item.get("source_url", "") for item in capture.get("payloads", [])]
    if any("Calendar/" in url for url in urls) and not result["coverage"]["observed_days"]:
        alerts.append({"code": "calendar_contract_unrecognized", "effect": "Requested days remain unknown; inspect source before resuming."})
    if any("BookItQuery/" in url for url in urls) and not result.get("quotes"):
        alerts.append({"code": "quote_contract_unrecognized", "effect": "No price is asserted."})
    return observe_contracts(capture.get("payloads", []), alerts, data_dir)


def inventory_health(source, data_dir):
    envelopes, alerts = [], []
    for row in source.get("observations", []):
        for kind, response in (("quote", row.get("quote_observation")), ("calendar", row.get("inventory"))):
            if not response:
                continue
            report = response.get("report") or {}
            envelopes.append({"source_url": response.get("source_url"), "status": report.get("status"), "body": response.get("body")})
            if report.get("stop_reason") and report.get("stay_quote_availability") != "SOLD_OUT":
                alerts.append({"property_id": row["property_id"], "kind": kind, "code": report["stop_reason"],
                               "effect": "Retain raw evidence; missing values remain unknown."})
    # Different quote variants (e.g. SOLD_OUT versus fee breakdown) are expected.
    # Schema fingerprints are diagnostics, not permission to reinterpret values.
    return observe_contracts(envelopes, alerts, data_dir)
