"""Append-only source and parser history; no changes to the Airbnb database."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from .pipeline import canonical


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def connect(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / 'evidence.sqlite3', timeout=15)
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS hotel_captures(
            capture_id TEXT PRIMARY KEY, hotel_id TEXT NOT NULL, source TEXT NOT NULL,
            observed_at TEXT NOT NULL, context_key TEXT NOT NULL, raw_json TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS hotel_capture_lookup ON hotel_captures(hotel_id,source,context_key,observed_at);
        CREATE TABLE IF NOT EXISTS hotel_interpretations(
            interpretation_id TEXT PRIMARY KEY, capture_id TEXT NOT NULL REFERENCES hotel_captures(capture_id),
            parser_hash TEXT NOT NULL, context_json TEXT NOT NULL, observation_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS hotel_jobs(
            job_id TEXT PRIMARY KEY, saved_at TEXT NOT NULL, report_json TEXT NOT NULL);
    ''')
    return db


def record(root, raw, observation, context, parser_hash):
    hotel_id, source = observation['hotel_id'], observation['source']
    identity = {'hotel_id': hotel_id, 'source': source, 'context': context, 'raw': raw}
    capture_id = digest(identity)
    interpretation_id = digest({'capture_id': capture_id, 'parser_hash': parser_hash, 'observation': observation})
    with closing(connect(root)) as db, db:
        db.execute('INSERT OR IGNORE INTO hotel_captures VALUES(?,?,?,?,?,?)',
                   (capture_id, hotel_id, source, observation['observed_at'], digest(context), canonical(raw)))
        db.execute('INSERT OR IGNORE INTO hotel_interpretations VALUES(?,?,?,?,?)',
                   (interpretation_id, capture_id, parser_hash, canonical(context), canonical(observation)))
    return {'capture_id': capture_id, 'interpretation_id': interpretation_id, 'parser_hash': parser_hash}


def cached(root, hotel_id, source, context, *, now=None, max_age_seconds=21600):
    now = now or datetime.now(timezone.utc)
    with closing(connect(root)) as db:
        rows = db.execute('SELECT capture_id,observed_at,raw_json FROM hotel_captures WHERE hotel_id=? AND source=? AND context_key=? ORDER BY observed_at DESC',
                          (hotel_id, source, digest(context))).fetchall()
    for capture_id, stamp, raw in rows:
        try:
            age = (now - datetime.fromisoformat(stamp)).total_seconds()
            if 0 <= age <= max_age_seconds:
                return {'capture_id': capture_id, 'raw': json.loads(raw), 'observed_at': stamp}
        except (ValueError, TypeError):
            continue
    return None


def save_job(root, report):
    job_id = digest(report)
    with closing(connect(root)) as db, db:
        db.execute('INSERT OR IGNORE INTO hotel_jobs VALUES(?,?,?)',
                   (job_id, report['updated_at'], canonical(report)))
    return job_id
