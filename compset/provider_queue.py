"""Durable bounded research tasks, independent from legacy Aketa-only jobs.

Unknown requests after interruption are not automatically replayed. Access stops
survive restarts and new dates; an operator must inspect them before clearing.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time
import re

from .rate_policy import canonical, digest, freshness


class Queue:
    def __init__(self, root):
        self.path = Path(root) / 'queue.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS provider_tasks (
                task_id TEXT PRIMARY KEY, scope TEXT NOT NULL, task_json TEXT NOT NULL,
                state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, capture_json TEXT,
                interpretation_json TEXT, parser_version TEXT, reason TEXT, updated_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS provider_stops (
                scope TEXT PRIMARY KEY, reason TEXT NOT NULL, stopped_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS provider_capture_history (
                capture_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, captured_json TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS provider_interpretation_history (
                interpretation_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, parser_version TEXT NOT NULL,
                parsed_at TEXT NOT NULL, interpretation_json TEXT NOT NULL);
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def scope(task):
        return canonical({k: task[k] for k in ('provider', 'vertical')})

    def plan(self, task):
        required = ('provider', 'vertical', 'method', 'hotel_id', 'provider_id', 'start_date',
                    'end_date', 'currency', 'party', 'mode', 'identity_verified')
        if not isinstance(task, dict) or any(k not in task for k in required):
            raise ValueError('Task must contain its full reviewed identity/context')
        from datetime import date
        from .ota_tool_adapters import party, reviewed_binding
        providers={'google_hotels','google_vacation_rentals','booking','expedia','vrbo','agoda','makemytrip','goibibo','airbnb','vio','wyndham'}
        if (not isinstance(task['provider'],str) or task['provider'] not in providers
                or task['vertical'] not in {'hotel','str'} or type(task['identity_verified']) is not bool
                or not isinstance(task['hotel_id'],str) or not re.fullmatch(r'[A-Za-z0-9:_-]{1,128}',task['hotel_id'])
                or not isinstance(task['provider_id'],str) or not re.fullmatch(r'[A-Za-z0-9:_-]{1,128}',task['provider_id'])
                or not isinstance(task['currency'],str) or not re.fullmatch(r'[A-Z]{3}',task['currency'])
                or not isinstance(task['method'],str) or not re.fullmatch(r'[a-z_]{1,64}',task['method'])
                or task['mode'] not in {'calendar','detailed'}):
            raise ValueError('Malformed typed task identity')
        validated_party=party(task['party'])
        if len(validated_party)>4 or any(room['adults']>16 for room in validated_party):
            raise ValueError('Party exceeds collection bounds')
        if not isinstance(task['start_date'],str) or not isinstance(task['end_date'],str):
            raise ValueError('Dates must be ISO strings')
        start, end = date.fromisoformat(task['start_date']), date.fromisoformat(task['end_date'])
        if end < start or (end-start).days > 365:
            raise ValueError('Invalid task range')
        # Task IDs exclude execution time and enclosing UI windows.
        target = {k: task[k] for k in required}
        target['party']=validated_party
        task_id, now = digest(target), datetime.now(timezone.utc).isoformat()
        state = 'planned' if task['identity_verified'] is True else 'unsupported'
        supported={('vio','connector_calendar','calendar'),('vio','connector_offers','detailed'),
                   ('expedia','connector_display','detailed')}
        if (task['provider'],task['method'],task['mode']) not in supported or not reviewed_binding(task):
            state='unsupported'
        with closing(self.connect()) as db, db:
            db.execute('INSERT OR IGNORE INTO provider_tasks(task_id,scope,task_json,state,updated_at) VALUES(?,?,?,?,?)',
                       (task_id, self.scope(target), canonical(target), state, now))
            db.execute('UPDATE provider_tasks SET scope=? WHERE task_id=?',(self.scope(target),task_id))
        return task_id

    def get(self, task_id):
        with closing(self.connect()) as db:
            row = db.execute('SELECT * FROM provider_tasks WHERE task_id=?', (task_id,)).fetchone()
        return dict(row) if row else None

    def claim(self, task_id):
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM provider_tasks WHERE task_id=?', (task_id,)).fetchone()
            if row is None or row['state'] != 'planned':
                return False
            if db.execute('SELECT 1 FROM provider_stops WHERE scope=?', (row['scope'],)).fetchone():
                return False
            db.execute("UPDATE provider_tasks SET state='claimed',attempts=attempts+1,updated_at=? WHERE task_id=?",
                       (datetime.now(timezone.utc).isoformat(), task_id))
        return True

    def stop(self, task_id, reason):
        row = self.get(task_id)
        with closing(self.connect()) as db, db:
            db.execute('INSERT OR IGNORE INTO provider_stops VALUES(?,?,?)',
                       (row['scope'], reason, datetime.now(timezone.utc).isoformat()))
            db.execute("UPDATE provider_tasks SET state='blocked',reason=? WHERE task_id=?", (reason, task_id))

    def capture(self, task_id, sanitized_capture):
        # This boundary accepts reviewed adapter projections only, never raw HTTP headers/body.
        from .ota_tool_adapters import sanitize_capture
        row=self.get(task_id)
        if not row or row['state']!='claimed': raise ValueError('Capture requires a claimed task')
        sanitized_capture=sanitize_capture(sanitized_capture,json.loads(row['task_json']))
        text = canonical(sanitized_capture)
        forbidden = {'cookie', 'cookies', 'authorization', 'access_token', 'csrf', 'headers', '_meta'}
        def inspect(node):
            if isinstance(node, dict):
                if any(str(k).lower() in forbidden for k in node):
                    raise ValueError('Private transport fields cannot be persisted')
                for child in node.values(): inspect(child)
            elif isinstance(node, list):
                for child in node: inspect(child)
        inspect(sanitized_capture)
        with closing(self.connect()) as db, db:
            changed = db.execute("UPDATE provider_tasks SET state='captured',capture_json=? WHERE task_id=? AND state='claimed'",
                                 (text, task_id)).rowcount
            if changed == 1:
                db.execute('INSERT OR IGNORE INTO provider_capture_history VALUES(?,?,?)',
                           (digest({'task_id':task_id,'capture':sanitized_capture}),task_id,text))
        if changed != 1:
            raise ValueError('Capture requires a claimed task')

    def interpret(self, task_id, normalize, parser_version):
        row = self.get(task_id)
        if row is None or row['capture_json'] is None or row['state'] not in {'captured', 'completed'}:
            raise ValueError('No durable capture to interpret')
        result = normalize(json.loads(row['capture_json']), json.loads(row['task_json']))
        with closing(self.connect()) as db, db:
            db.execute("UPDATE provider_tasks SET state='completed',interpretation_json=?,parser_version=?,updated_at=? WHERE task_id=?",
                       (canonical(result), parser_version, datetime.now(timezone.utc).isoformat(), task_id))
            db.execute('INSERT OR IGNORE INTO provider_interpretation_history VALUES(?,?,?,?,?)',
                       (digest({'task_id':task_id,'capture':row['capture_json'],'version':parser_version,'result':result}),
                        task_id,parser_version,datetime.now(timezone.utc).isoformat(),canonical(result)))
        return result

    def refresh(self, task_id, *, force=False, now=None, max_age_seconds=21600):
        row=self.get(task_id)
        if not row or row['state']!='completed': return False
        raw=json.loads(row['capture_json'])
        if not force and freshness(raw['observed_at'],now=now,max_age_seconds=max_age_seconds)['capture_recent']:
            return False
        with closing(self.connect()) as db, db:
            return db.execute("UPDATE provider_tasks SET state='planned',reason=NULL WHERE task_id=? AND state='completed'",
                              (task_id,)).rowcount==1

    def interrupted(self):
        with closing(self.connect()) as db, db:
            return db.execute("UPDATE provider_tasks SET state='uncertain',reason='interrupted_request_requires_review' WHERE state='claimed'").rowcount

    def fail(self,task_id,reason):
        row=self.get(task_id)
        with closing(self.connect()) as db, db:
            db.execute('INSERT OR IGNORE INTO provider_stops VALUES(?,?,?)',
                       (row['scope'],reason,datetime.now(timezone.utc).isoformat()))
            db.execute("UPDATE provider_tasks SET state=CASE WHEN state='claimed' THEN 'uncertain' ELSE state END,reason=? WHERE task_id=?",(reason,task_id))

    def run(self, task_ids, fetch, normalize, *, budget, parser_version, interval_seconds=3,
            cancelled=lambda: False, fresh=False, max_age_seconds=21600):
        if type(budget) is not int or budget < 0 or not 2 <= interval_seconds <= 15:
            raise ValueError('Require a finite budget and 2-15-second spacing')
        calls, results, failures = 0, [], []
        last = None
        for task_id in task_ids:
            if cancelled(): break
            row = self.get(task_id)
            if row and row['state']=='completed' and self.refresh(task_id,force=fresh,max_age_seconds=max_age_seconds):
                row=self.get(task_id)
            if row and row['state'] in {'captured', 'completed'}:
                try:
                    results.append(self.interpret(task_id, normalize, parser_version))
                except Exception as exc:
                    self.fail(task_id,'parser_error_requires_review:'+type(exc).__name__)
                    failures.append({'task_id':task_id,'reason':'parser_error_requires_review'})
                continue
            if calls >= budget: break
            if last is not None:
                time.sleep(max(0, interval_seconds - (time.monotonic()-last)))
            if cancelled() or not self.claim(task_id): continue
            if cancelled():
                with closing(self.connect()) as db, db:
                    db.execute("UPDATE provider_tasks SET state='planned',attempts=attempts-1 WHERE task_id=? AND state='claimed'",(task_id,))
                break
            calls += 1
            last = time.monotonic()
            try:
                captured = fetch(json.loads(row['task_json']))
                status = captured.get('http_status')
                if status in {401, 403, 429} or captured.get('challenge_detected') is True:
                    self.stop(task_id, f'access_or_rate_limit_{status}' if status in {401,403,429} else 'challenge_detected')
                    continue
                self.capture(task_id, captured)
                results.append(self.interpret(task_id, normalize, parser_version))
            except Exception as exc:
                # Failure could follow a successful remote request: preserve uncertainty.
                self.fail(task_id,'capture_or_parse_failure_requires_review:'+type(exc).__name__)
                failures.append({'task_id':task_id,'reason':'capture_or_parse_failure_requires_review'})
        return {'capture_calls': calls, 'results': results, 'failures':failures}
