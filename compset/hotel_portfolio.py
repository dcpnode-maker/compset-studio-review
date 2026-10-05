"""Import observed Lighthouse identities without inventing OTA mappings.

Pure validation/projection plus atomic local JSON/CSV persistence. No network,
credentials, browser access, database migrations or rate collection.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import unquote, urlsplit, urlunsplit


INPUT_SCHEMA = "lighthouse-portfolio-observation.v1"
SCHEMA_VERSION = "hotel-portfolio.v1"
ROLES = {"subject", "competitor"}
PROFILE_FIELDS = ("title", "city", "country", "address", "latitude", "longitude",
                  "room_count", "star_classification", "currency", "timezone")
SOURCE_HOSTS = {"mylighthouse.com", "otainsight.com"}


def _text(value, name, *, required=False, limit=500):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be a non-empty string of at most {limit} characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{name} contains control characters")
    return value.strip()


def _provider_id(value):
    # Treat IDs as opaque strings; never cast through integer/float and lose digits.
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError("provider_id must be an exact string of letters, digits, hyphens or underscores")
    return value


def _stamp(value):
    value = _text(value, "observed_at", required=True, limit=60)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observed_at must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("observed_at requires a timezone")
    return value


def source_url(value):
    """Lighthouse evidence links only; omit queries/fragments that may hold secrets."""
    value = _text(value, "source_url", required=True, limit=3000)
    try:
        url = urlsplit(value)
        valid_host = any(url.hostname == base or (url.hostname or "").endswith("." + base) for base in SOURCE_HOSTS)
        if url.scheme != "https" or not valid_host or url.username or url.password or url.port is not None:
            raise ValueError("source_url must be an HTTPS Lighthouse page without credentials or a port")
        if re.search(r"(?:token|secret|password|api[_-]?key|sessionid)[=/]", unquote(url.path), re.I):
            raise ValueError("Credential-like data is not allowed in a source path")
        return urlunsplit(("https", url.hostname, url.path or "/", "", ""))
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid Lighthouse source_url") from exc


def _keys(value, allowed, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    if set(value) - set(allowed):
        # Never echo unknown input values, which might accidentally contain credentials.
        raise ValueError(f"Unsupported fields in {label}; provide only hotel inventory observations")


def _integer(value, name, *, minimum=0, maximum=100000):
    if value is None:
        return None
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return value


def _coordinate(value, limit):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > limit:
        raise ValueError("Coordinates must be finite numbers within geographic bounds")
    return value


def _profile_fields(raw):
    values = {"title": _text(raw.get("title", raw.get("name")), "title", required=True, limit=250)}
    for field in ("city", "country", "address", "timezone"):
        values[field] = _text(raw.get(field), field)
    values["currency"] = _text(raw.get("currency"), "currency", limit=3)
    if values["currency"] is not None and not re.fullmatch(r"[A-Z]{3}", values["currency"]):
        raise ValueError("Currency must be an observed uppercase three-letter code")
    values["room_count"] = _integer(raw.get("room_count"), "room_count", minimum=1)
    values["star_classification"] = _integer(raw.get("star_classification"), "star_classification", minimum=1, maximum=5)
    values["latitude"] = _coordinate(raw.get("latitude"), 90)
    values["longitude"] = _coordinate(raw.get("longitude"), 180)
    if (values["latitude"] is None) != (values["longitude"] is None):
        raise ValueError("Supply both observed coordinates, or leave both unknown")
    return values


def _field_value(field, value):
    """Validate nested public values too; an allowlisted key is not enough."""
    if field == "title":
        return _text(value, field, required=True, limit=250)
    if field in ("city", "country", "address", "timezone"):
        return _text(value, field)
    if field == "currency":
        if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[A-Z]{3}", value)):
            raise ValueError("Invalid saved currency")
        return value
    if field == "room_count":
        return _integer(value, field, minimum=1)
    if field == "star_classification":
        return _integer(value, field, minimum=1, maximum=5)
    if field in ("latitude", "longitude"):
        return _coordinate(value, 90 if field == "latitude" else 180)
    raise ValueError("Unsupported public profile field")


def _evidence(raw, top, *, role=None):
    result = {"source": "lighthouse", "source_url": source_url(raw.get("source_url", top["source_url"])),
              "observed_at": _stamp(raw.get("observed_at", top["observed_at"])),
              "observation_method": "authenticated visible account UI"}
    if role is not None:
        if role not in ROLES:
            raise ValueError("Unknown evidence role")
        result["role"] = role
    return result


def build_hotel_portfolio(observation):
    """Validate an account-list snapshot; retain exact IDs and directional relations."""
    _keys(observation, ("schema_version", "observed_at", "source_url", "coverage", "hotels", "relations"), "observation")
    if observation.get("schema_version") != INPUT_SCHEMA:
        raise ValueError(f"Expected {INPUT_SCHEMA}")
    top = {"observed_at": _stamp(observation.get("observed_at")), "source_url": source_url(observation.get("source_url"))}
    raw_coverage = observation.get("coverage")
    _keys(raw_coverage, ("account_subject_count", "subject_list_complete", "competitor_membership_complete", "notes"), "coverage")
    count = _integer(raw_coverage.get("account_subject_count"), "account_subject_count")
    for field in ("subject_list_complete", "competitor_membership_complete"):
        if type(raw_coverage.get(field)) is not bool:
            raise ValueError(f"{field} requires an explicit boolean")
    notes = raw_coverage.get("notes", [])
    if not isinstance(notes, list) or len(notes) > 100:
        raise ValueError("coverage.notes must be a bounded list")
    notes = [_text(note, "coverage note", required=True, limit=2000) for note in notes]
    hotels, relations = observation.get("hotels"), observation.get("relations", [])
    if not isinstance(hotels, list) or not isinstance(relations, list) or len(hotels) > 100000 or len(relations) > 500000:
        raise ValueError("hotels and relations must be bounded arrays")
    profiles = {}
    for raw in hotels:
        _keys(raw, ("provider_id", "name", "title", "role", "roles", "source_url", "observed_at", *PROFILE_FIELDS), "hotel")
        provider_id = _provider_id(raw.get("provider_id"))
        identity = "lighthouse:" + provider_id
        roles = raw.get("roles", [raw.get("role")])
        if not isinstance(roles, list) or not roles or any(role not in ROLES for role in roles):
            raise ValueError("A hotel must have explicit subject/competitor role(s)")
        if "role" in raw and "roles" in raw and raw["role"] not in roles:
            raise ValueError("role and roles disagree")
        values = _profile_fields(raw)
        evidence = [_evidence(raw, top, role=role) for role in sorted(set(roles))]
        if identity not in profiles:
            profiles[identity] = {"id": identity, "provider": "lighthouse", "provider_id": provider_id,
                **values, "roles": [], "aliases": [], "evidence": [], "attribute_conflicts": {},
                "field_evidence": {}, "source_url": evidence[0]["source_url"], "observed_at": evidence[0]["observed_at"],
                "rate_coverage": {"status": "not_collected", "collection_supported": False,
                    "reason": "No independently verified OTA identity or supported collection adapter is linked"},
                "ota_mappings": []}
        profile = profiles[identity]
        profile["roles"] = sorted(set(profile["roles"]) | set(roles))
        profile["aliases"] = sorted(set(profile["aliases"]) | {values["title"]})
        for item in evidence:
            if item not in profile["evidence"]:
                profile["evidence"].append(item)
        for field, value in values.items():
            if value is None:
                continue
            item = {"value": value, "source_url": evidence[0]["source_url"], "observed_at": evidence[0]["observed_at"]}
            observations = profile["field_evidence"].setdefault(field, [])
            if item not in observations:
                observations.append(item)
            distinct = []
            for seen in observations:
                if seen["value"] not in distinct:
                    distinct.append(seen["value"])
            if len(distinct) > 1:
                profile["attribute_conflicts"][field] = distinct
                # Preserve a display alias for a known exact ID; other conflicts stay unknown.
                profile[field] = distinct[0] if field == "title" else None
            else:
                profile[field] = distinct[0]
        latest = max(profile["evidence"], key=lambda item: datetime.fromisoformat(item["observed_at"].replace("Z", "+00:00")))
        profile["source_url"], profile["observed_at"] = latest["source_url"], latest["observed_at"]
    observed_subject_ids = sorted(key for key, profile in profiles.items() if "subject" in profile["roles"])
    if count is not None and len(observed_subject_ids) > count:
        raise ValueError("Observed subjects exceed the visible account subject count")
    if raw_coverage["subject_list_complete"] and (count is None or count != len(observed_subject_ids)):
        raise ValueError("A complete subject list requires an exact account-count reconciliation")
    normalized_relations = {}
    for raw in relations:
        _keys(raw, ("subject_provider_id", "competitor_provider_id", "source_url", "observed_at"), "relation")
        subject_id, competitor_id = ("lighthouse:" + _provider_id(raw.get(key)) for key in ("subject_provider_id", "competitor_provider_id"))
        if subject_id == competitor_id:
            raise ValueError("A hotel cannot be its own configured competitor")
        if subject_id not in profiles or "subject" not in profiles[subject_id]["roles"]:
            raise ValueError("Relation subject must be an observed subject profile")
        if competitor_id not in profiles or "competitor" not in profiles[competitor_id]["roles"]:
            raise ValueError("Relation competitor must be an observed competitor profile")
        key = (subject_id, competitor_id)
        relation = normalized_relations.setdefault(key, {"subject_id": subject_id, "competitor_id": competitor_id,
            "relationship": "configured_lighthouse_competitor", "evidence": []})
        evidence = _evidence(raw, top)
        if evidence not in relation["evidence"]:
            relation["evidence"].append(evidence)
    for profile in profiles.values():
        if "latitude" in profile["attribute_conflicts"] or "longitude" in profile["attribute_conflicts"]:
            profile["latitude"] = profile["longitude"] = None
    result_profiles = sorted(profiles.values(), key=lambda profile: ("subject" not in profile["roles"], profile["title"].casefold(), profile["id"]))
    coverage = {"status": "complete_subject_list" if raw_coverage["subject_list_complete"] else "partial_subject_list",
        "account_subject_count": count, "observed_subject_count": len(observed_subject_ids),
        "observed_subject_ids": observed_subject_ids, "subject_list_complete": raw_coverage["subject_list_complete"],
        "competitor_membership_complete": raw_coverage["competitor_membership_complete"],
        "profile_count": len(profiles), "competitor_profile_count": sum("competitor" in p["roles"] for p in profiles.values()),
        "configured_relation_count": len(normalized_relations), "rates_collected_count": 0,
        "notes": notes}
    return {"schema_version": SCHEMA_VERSION, "provider": "lighthouse", **top, "profiles": result_profiles,
        "relations": [normalized_relations[key] for key in sorted(normalized_relations)], "coverage": coverage,
        "warnings": ["Imported account configuration is Lighthouse evidence, not independently collected OTA inventory or rates.",
                     "Names do not establish OTA identity. The existing Aketa collection dataset remains separate.",
                     "Source URL queries and fragments are omitted to avoid retaining session or account secrets."]}


def _atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name + ".", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _csv(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for row in rows:
        output = {}
        for field in fields:
            value = row.get(field)
            text = "" if value is None else json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
            if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
                text = "'" + text
            output[field] = text
        writer.writerow(output)
    return stream.getvalue().encode("utf-8-sig")


def import_hotel_portfolio(observation, data_root):
    """Publish one explicitly scoped snapshot; prior snapshots stay in history."""
    artifact = build_hotel_portfolio(observation)
    body = (json.dumps(artifact, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    directory = Path(data_root) / "hotel-portfolio"
    history = directory / "history" / (digest + ".json")
    if not history.exists():
        _atomic_write(history, body)
    _atomic_write(directory / "profiles.csv", _csv(artifact["profiles"], ["id", "provider_id", *PROFILE_FIELDS, "roles", "aliases", "attribute_conflicts", "rate_coverage", "source_url", "observed_at", "evidence"]))
    _atomic_write(directory / "relations.csv", _csv(artifact["relations"], ["subject_id", "competitor_id", "relationship", "evidence"]))
    _atomic_write(directory / "latest.json", body)
    return {"path": str(directory / "latest.json"), "history_path": str(history), "sha256": digest,
            "coverage": artifact["coverage"]}


def load_hotel_portfolio(data_root):
    """Read-only allowlisted projection for API callers, with no secret/raw fields."""
    path = Path(data_root) / "hotel-portfolio" / "latest.json"
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "provider": "lighthouse", "observed_at": None,
                "profiles": [], "relations": [], "coverage": {"status": "not_imported", "subject_list_complete": False,
                "competitor_membership_complete": False, "account_subject_count": None, "observed_subject_count": 0,
                "profile_count": 0, "rates_collected_count": 0}, "warnings": ["Lighthouse account inventory has not been imported."]}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported saved hotel portfolio schema")
    if not isinstance(raw.get("profiles"), list) or not isinstance(raw.get("relations"), list) or not isinstance(raw.get("coverage"), dict):
        raise ValueError("Malformed saved hotel portfolio structure")
    # Revalidate through the observation contract; persisted collection support cannot be escalated.
    hotels = []
    for profile in raw.get("profiles", []):
        if not isinstance(profile, dict):
            raise ValueError("Malformed saved hotel profile")
        provider_id = _provider_id(profile.get("provider_id"))
        if profile.get("id") != "lighthouse:" + provider_id:
            raise ValueError("Saved portfolio identity mismatch")
        hotels.append({"provider_id": provider_id, **{field: profile.get(field) for field in PROFILE_FIELDS},
            "roles": profile.get("roles"), "source_url": profile.get("source_url"), "observed_at": profile.get("observed_at")})
    for item in raw["relations"]:
        if (not isinstance(item, dict) or not isinstance(item.get("subject_id"), str)
                or not isinstance(item.get("competitor_id"), str)
                or not item["subject_id"].startswith("lighthouse:")
                or not item["competitor_id"].startswith("lighthouse:")
                or not isinstance(item.get("evidence"), list) or not item["evidence"]):
            raise ValueError("Malformed saved hotel relation")
    relations = [{"subject_provider_id": item["subject_id"].removeprefix("lighthouse:"),
                  "competitor_provider_id": item["competitor_id"].removeprefix("lighthouse:"),
                  "source_url": item.get("evidence", [{}])[0].get("source_url", raw.get("source_url")),
                  "observed_at": item.get("evidence", [{}])[0].get("observed_at", raw.get("observed_at"))} for item in raw.get("relations", [])]
    coverage = {field: raw.get("coverage", {}).get(field) for field in
                ("account_subject_count", "subject_list_complete", "competitor_membership_complete", "notes")}
    result = build_hotel_portfolio({"schema_version": INPUT_SCHEMA, "observed_at": raw.get("observed_at"),
        "source_url": raw.get("source_url"), "coverage": coverage, "hotels": hotels, "relations": relations})
    # Preserve safe original field-level evidence/conflicts, while never returning arbitrary JSON.
    original = {profile["id"]: profile for profile in raw["profiles"]}
    for profile in result["profiles"]:
        source = original[profile["id"]]
        if (not isinstance(source.get("aliases"), list) or not isinstance(source.get("evidence"), list)
                or not isinstance(source.get("attribute_conflicts"), dict) or not isinstance(source.get("field_evidence"), dict)):
            raise ValueError("Malformed saved profile evidence")
        profile["aliases"] = [_text(alias, "alias", required=True, limit=250) for alias in source.get("aliases", [])]
        profile["evidence"] = [_evidence(item, result, role=item.get("role")) for item in source.get("evidence", [])]
        profile["attribute_conflicts"] = {field: [_field_value(field, value) for value in values] for field, values in source.get("attribute_conflicts", {}).items() if field in PROFILE_FIELDS}
        profile["field_evidence"] = {field: [{"value": _field_value(field, item.get("value")),
            "source_url": source_url(item["source_url"]), "observed_at": _stamp(item["observed_at"])} for item in items]
            for field, items in source.get("field_evidence", {}).items() if field in PROFILE_FIELDS}
    original_relations = {(item["subject_id"], item["competitor_id"]): item for item in raw.get("relations", [])}
    for relation in result["relations"]:
        original = original_relations[(relation["subject_id"], relation["competitor_id"])]
        relation["evidence"] = [_evidence(item, result) for item in original.get("evidence", [])]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Observed account inventory JSON")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    args = parser.parse_args(argv)
    observation = json.loads(args.input.read_text(encoding="utf-8-sig"))
    print(json.dumps(import_hotel_portfolio(observation, args.data_root), indent=2))


if __name__ == "__main__":
    main()
