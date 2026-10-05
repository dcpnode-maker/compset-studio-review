"""SQLite health, provenance and explicit sticky-session assignments."""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import re
import sqlite3
import time

from .kaggle_fetch_validate import normalize_proxy, valid_origin, TEST_URL, SOURCES


class RouteUnavailable(RuntimeError):
    pass


def source_provenance(item: dict) -> dict | None:
    sources = item.get("source_urls")
    if not isinstance(sources, list):
        return None
    if item.get("source_type", "public_list") == "public_list":
        if sources and all(isinstance(source, str) and source in SOURCES for source in sources):
            return {"source_type": "public_list", "source_urls": sources}
    elif item.get("source_type") == "operator_supplied" and sources == []:
        evidence = item.get("source_file")
        if (isinstance(evidence, dict) and evidence.get("label") == "operator-input"
                and isinstance(evidence.get("sha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}", evidence["sha256"])
                and type(evidence.get("bytes")) is int and 1 <= evidence["bytes"] <= 2_000_000):
            return {"source_type": "operator_supplied", "source_urls": [], "source_file": {
                "label": "operator-input", "sha256": evidence["sha256"], "bytes": evidence["bytes"]}}
    return None


class Pool:
    def __init__(self, path: str | Path):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS proxies (
            endpoint TEXT PRIMARY KEY, source_urls TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'unknown',
            protocol TEXT NOT NULL, tls_verified INTEGER NOT NULL, validated_at REAL NOT NULL,
            origin TEXT, last_ok REAL, fail_count INTEGER NOT NULL DEFAULT 0, avg_latency_ms REAL,
            last_error TEXT, source_provenance TEXT NOT NULL DEFAULT '{}');
          CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY, endpoint TEXT NOT NULL, created_at REAL NOT NULL,
            halted_reason TEXT, FOREIGN KEY(endpoint) REFERENCES proxies(endpoint));
          CREATE TABLE IF NOT EXISTS target_cooldowns (host TEXT PRIMARY KEY, until_at REAL NOT NULL);
        """)
        if "source_provenance" not in {row[1] for row in self.db.execute("PRAGMA table_info(proxies)")}:
            self.db.execute("ALTER TABLE proxies ADD COLUMN source_provenance TEXT NOT NULL DEFAULT '{}'")
            self.db.commit()

    def close(self):
        self.db.close()

    def import_manifest(self, manifest: dict) -> int:
        if not isinstance(manifest, dict) or not isinstance(manifest.get("proxies"), list):
            return 0
        count = 0
        for item in manifest.get("proxies", []):
            if not isinstance(item, dict):
                continue
            endpoint = item.get("endpoint", "")
            if (not isinstance(endpoint, str) or normalize_proxy(endpoint) != endpoint
                    or item.get("alive") is not True or item.get("tls_verified") is not True):
                continue
            provenance = source_provenance(item)
            if provenance is None:
                continue
            if item.get("protocol") != "http_connect" or item.get("validation_url") != TEST_URL:
                continue
            try:
                parsed_stamp = datetime.fromisoformat(item["validated_at"])
                if parsed_stamp.tzinfo is None or not valid_origin(item.get("origin")):
                    continue
                stamp = parsed_stamp.timestamp()
                latency = float(item["latency_ms"])
                if not 0 <= time.time() - stamp <= 86400 or not 0 < latency < 120000:
                    continue
            except (ValueError, KeyError, TypeError):
                continue
            sources = provenance["source_urls"]
            self.db.execute("""INSERT INTO proxies(endpoint,source_urls,category,protocol,tls_verified,
                validated_at,origin,last_ok,fail_count,avg_latency_ms,source_provenance) VALUES(?,?,'unknown','http_connect',1,?,?,?,0,?,?)
                ON CONFLICT(endpoint) DO UPDATE SET source_urls=excluded.source_urls,
                validated_at=excluded.validated_at,origin=excluded.origin,last_ok=excluded.last_ok,
                fail_count=0,avg_latency_ms=excluded.avg_latency_ms,tls_verified=1,last_error=NULL,
                source_provenance=excluded.source_provenance""",
                (endpoint, json.dumps(sources), stamp, item.get("origin"), stamp, latency, json.dumps(provenance)))
            count += 1
        self.db.commit()
        return count

    def choose(self, session_id: str, host: str) -> dict:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session_id):
            raise ValueError("explicit session ID required: 1..64 letters, digits, underscores or hyphens")
        block = self.db.execute("SELECT until_at FROM target_cooldowns WHERE host=?", (host,)).fetchone()
        if block and block["until_at"] > time.time():
            raise RouteUnavailable("target_cooldown")
        sticky = self.db.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if sticky:
            if sticky["halted_reason"]:
                raise RouteUnavailable("session_halted_requires_manual_reset")
            route = self.db.execute("SELECT * FROM proxies WHERE endpoint=?", (sticky["endpoint"],)).fetchone()
            if not self._healthy(route):
                raise RouteUnavailable("sticky_route_unhealthy_no_fallback")
            return dict(route)
        eligible = [row for row in self.db.execute("SELECT * FROM proxies") if self._healthy(row)]
        if not eligible:
            raise RouteUnavailable("no_recently_validated_routes")
        route = random.choices(eligible, weights=[1 / max(row["avg_latency_ms"] or 1000, 100) for row in eligible], k=1)[0]
        self.db.execute("INSERT INTO sessions VALUES(?,?,?,NULL)", (session_id, route["endpoint"], time.time()))
        self.db.commit()
        return dict(route)

    @staticmethod
    def _healthy(row) -> bool:
        return bool(row and row["tls_verified"] and row["fail_count"] < 3 and time.time() - row["validated_at"] <= 86400)

    def transport_failure(self, endpoint: str, reason: str):
        # Call sites supply fixed reason codes, never exception messages/URLs.
        if not re.fullmatch(r"[a-z_]{1,60}", reason):
            raise ValueError("fixed error code required")
        self.db.execute("UPDATE proxies SET fail_count=fail_count+1,last_error=? WHERE endpoint=?", (reason, endpoint))
        self.db.commit()

    def transport_ok(self, endpoint: str, latency_ms: float):
        self.db.execute("""UPDATE proxies SET last_ok=?,avg_latency_ms=CASE WHEN avg_latency_ms IS NULL
                         THEN ? ELSE (avg_latency_ms*0.8+?*0.2) END WHERE endpoint=?""",
                        (time.time(), latency_ms, latency_ms, endpoint))
        self.db.commit()

    def target_block(self, session_id: str, host: str, *, status=403, cooldown=900):
        if type(status) is not int or status not in {401, 403, 429}:
            raise ValueError("only access/rate-limit statuses may halt a session")
        if type(cooldown) is not int or not 60 <= cooldown <= 86400:
            raise ValueError("cooldown must be an integer between 60 and 86400 seconds")
        if not self.db.execute("SELECT 1 FROM sessions WHERE session_id=?", (session_id,)).fetchone():
            raise ValueError("unknown_session")
        self.db.execute("UPDATE sessions SET halted_reason=? WHERE session_id=?", (f"target_{status}", session_id))
        self.db.execute("INSERT INTO target_cooldowns VALUES(?,?) ON CONFLICT(host) DO UPDATE SET until_at=MAX(until_at,excluded.until_at)",
                        (host, time.time() + cooldown))
        self.db.commit()

    def reset_session(self, session_id: str):
        # Keep its original route. A manual reset never secretly rotates it.
        self.db.execute("UPDATE sessions SET halted_reason=NULL WHERE session_id=?", (session_id,))
        self.db.commit()

    def health(self) -> list[dict]:
        return [dict(row) for row in self.db.execute("SELECT * FROM proxies ORDER BY endpoint")]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="routes/data/proxies.db")
    parser.add_argument("--reset-session", help="Explicitly resume this same route after its target cooldown expires")
    args = parser.parse_args()
    pool = Pool(args.db)
    if args.reset_session:
        pool.reset_session(args.reset_session)
    print(json.dumps(pool.health(), indent=2))
    pool.close()
