"""Bounded multi-source Aketa jobs, with full coverage and independent source stops."""
from __future__ import annotations

from contextlib import contextmanager, closing
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import time

from .hotel_contracts import (INDIA, SEED, SOURCES, context_for, load_registry, money,
                              normalize_observation, stay_context, validate_registry)
from . import hotel_store
from .pipeline import DATA, ROOT, _write_json, canonical, export_csv

DEFAULT_ROOT = DATA / 'hotel-pipelines'
MODULES = {'makemytrip': 'hotel_mmt_agoda', 'agoda': 'hotel_mmt_agoda',
           'booking': 'hotel_booking_expedia', 'expedia': 'hotel_booking_expedia'}
CHANNELS = {'Booking.com': 'booking', 'Agoda': 'agoda', 'MakeMyTrip.com': 'makemytrip',
            'Expedia': 'expedia', 'Hotels.com': 'hotels_com', 'Hotel Aketa': 'hotel_direct'}


def init_registry(root=DEFAULT_ROOT):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'hotels.json'
    if not path.exists():
        _write_json(path, SEED)
    load_registry(path)
    return path


def parser_hash(source):
    files = ['hotel_contracts.py', 'hotel_jobs.py', 'pipeline.py']
    files.append('hotel_aketa.py' if source == 'google_hotels' else MODULES[source] + '.py')
    return hashlib.sha256(b''.join(name.encode() + b'\0' + (ROOT / 'compset' / name).read_bytes() for name in files)).hexdigest()


def parse_source(raw, hotel, source, context):
    if source == 'google_hotels':
        from .hotel_aketa import build_report, requested_context
        report = build_report(raw, requested_context(context['start_date']))
        rates = [{**r, 'channel': CHANNELS.get(r.get('provider')), 'observed_context': report['context']}
                 for r in report['rates']]
        observation = {'hotel_id': hotel['id'], 'source': source, 'observed_at': report['observed_at'],
                       'observed_context': report['context'], 'requested_context': context,
                       'status': 'indicative' if rates else 'unknown', 'reason': report.get('stop_reason'),
                       'rates': rates, 'provenance': {'source_url': hotel['sources'][source]['url']}}
    else:
        adapter = importlib.import_module('.' + MODULES[source], __package__)
        observation = adapter.parse(raw, hotel, context)
    return normalize_observation(observation, hotel, source, context)


def capture_source(source, hotel, context, output_dir):
    if source == 'google_hotels':
        from .hotel_aketa import capture_google
        path = capture_google(output=output_dir)
        return json.loads(path.read_text(encoding='utf-8'))
    adapter = importlib.import_module('.' + MODULES[source], __package__)
    return adapter.capture(source, hotel, context, output_dir=output_dir)


def import_source(source, path, *, root=DEFAULT_ROOT, start_date=None, checkin=None):
    root = Path(root)
    registry = load_registry(init_registry(root))
    hotel = registry['hotels'][0]
    if source not in hotel['sources']:
        raise ValueError('Unknown configured source')
    context = context_for(hotel, start_date=start_date)
    if source != 'google_hotels':
        offset = (date.fromisoformat(checkin or context['start_date']) - date.fromisoformat(context['start_date'])).days
        if not 0 <= offset < context['days']:
            raise ValueError('Imported stay is outside the requested window')
        context = stay_context(context, offset)
    raw = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    save_raw(root, raw)
    observation = parse_source(raw, hotel, source, context)
    evidence = hotel_store.record(root, raw, observation, context, parser_hash(source))
    return {**observation, **evidence}


def save_raw(root, raw):
    folder = Path(root) / 'raw'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (hotel_store.digest(raw) + '.json')
    if not path.exists():
        _write_json(path, raw)
    return path


@contextmanager
def job_lock(root):
    path = root / 'running.lock'
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError('A hotel job is already running; inspect running.lock if a previous process crashed') from exc
    try:
        with os.fdopen(handle, 'w') as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def build_report(hotel, context, observations, *, sources=SOURCES, state='complete', stop_reason=None, requests=0):
    rates, coverage = [], []
    source_states = []
    for source in sources:
        entries = [o for o in observations if o['source'] == source]
        source_rates = [r for o in entries for r in o['rates']]
        rates.extend(source_rates)
        source_states.append({'source': source, 'url': hotel['sources'].get(source, {}).get('url'),
                              'status': entries[-1]['status'] if entries else 'not_requested',
                              'reason': entries[-1].get('reason') if entries else 'not_requested',
                              'rate_count': len(source_rates),
                              'observed_at': entries[-1].get('observed_at') if entries else None,
                              'last_stay': entries[-1].get('requested_context', {}).get('checkin') if entries else None})
        for offset in range(context['days']):
            stay = stay_context(context, offset)
            matches = [r for r in source_rates if r['checkin'] == stay['checkin'] and r['checkout'] == stay['checkout']]
            direct = any(r.get('direct_supplier_quote') is True for r in matches)
            negative = any(o.get('status') == 'unavailable' and o.get('unavailability_verified') is True
                           and o.get('observed_context', {}).get('checkin') == stay['checkin']
                           and o.get('observed_context', {}).get('checkout') == stay['checkout'] for o in entries)
            if direct:
                cell_state, reason = 'quoted', None
            elif matches:
                cell_state, reason = 'indicative', None
            elif negative:
                cell_state, reason = 'unavailable', 'source_unavailable_for_requested_stay'
            else:
                cell_state = 'unknown'
                reason = ('not_requested' if source_states[-1]['status'] == 'unavailable'
                          else source_states[-1]['reason'] or 'price_not_returned')
            coverage.append({'hotel_id': hotel['id'], 'source': source, 'checkin': stay['checkin'],
                             'checkout': stay['checkout'], 'state': cell_state, 'reason': reason, 'rate_count': len(matches)})
    summary = {'source_count': len(sources), 'date_cells': len(coverage),
               'quoted_cells': sum(r['state'] == 'quoted' for r in coverage),
               'indicative_cells': sum(r['state'] == 'indicative' for r in coverage),
               'unavailable_cells': sum(r['state'] == 'unavailable' for r in coverage),
               'unknown_cells': sum(r['state'] == 'unknown' for r in coverage), 'rate_rows': len(rates)}
    return {'schema_version': 1, 'hotel': hotel, 'context': context, 'state': state, 'stop_reason': stop_reason,
            'updated_at': datetime.now(timezone.utc).isoformat(), 'source_states': source_states,
            'observations': observations, 'rates': rates, 'coverage': coverage, 'summary': summary,
            'capture_calls_this_run': requests,
            'limitations': ['Google partner prices are indicative observations from Google, not direct OTA quotes.',
                           'Unknown source/date cells are not sold-out dates. Source failures stop further dates on that source.']}


def export_report(root, report, *, dashboard=False):
    report['job_id'] = hotel_store.save_job(root, report)
    _write_json(root / 'latest.json', report)
    export_csv(root / 'rates.csv', report['rates'], ['hotel_id', 'source', 'channel', 'checkin', 'checkout', 'amount', 'currency', 'amount_type'])
    export_csv(root / 'coverage.csv', report['coverage'], ['hotel_id', 'source', 'checkin', 'checkout', 'state', 'reason'])
    if dashboard:
        # Preserve the original Google report contract and attach source health;
        # do not replace its verified rates with a less complete refresh.
        path = Path(root).parent / 'hotels' / 'aketa' / 'latest.json'
        if path.exists():
            legacy = json.loads(path.read_text(encoding='utf-8'))
            legacy['pipelines'] = {k: report[k] for k in ('job_id', 'state', 'stop_reason', 'context', 'updated_at', 'source_states', 'summary', 'coverage')}
            legacy['pipeline_rates'] = report['rates']
            _write_json(path, legacy)
            export_csv(path.parent / 'rates.csv', report['rates'], ['hotel_id', 'source', 'channel', 'checkin', 'checkout', 'amount', 'currency', 'amount_type'])
    return report


def source_cooldowns(root, hotel_id, *, now=None):
    """Recent source failures survive date-window changes and dashboard restarts."""
    now = now or datetime.now(timezone.utc)
    if not (Path(root) / 'evidence.sqlite3').exists():
        return []
    latest = {}
    with closing(hotel_store.connect(root)) as db:
        rows = db.execute('SELECT rowid,observation_json FROM hotel_interpretations').fetchall()
    for rowid, value in rows:
        try:
            obs = json.loads(value)
            stamp = datetime.fromisoformat(obs['observed_at'])
            if obs.get('hotel_id') != hotel_id or obs.get('source') not in SOURCES or stamp.tzinfo is None:
                continue
            key = (stamp, rowid)
            if obs['source'] not in latest or key > latest[obs['source']][0]:
                latest[obs['source']] = (key, obs)
        except (ValueError, TypeError, KeyError):
            continue
    return [obs for (stamp, _), obs in latest.values()
            if 0 <= (now - stamp).total_seconds() <= 21600
            and obs.get('status') not in ('quoted', 'indicative', 'complete', 'observed', 'success', 'unavailable')]


def run_pipeline(*, root=DEFAULT_ROOT, sources=SOURCES, start_date=None, request_budget=0,
                 interval_seconds=3, live=False, dashboard=False, capture_fn=None,
                 fresh=False, progress_fn=None, stop_requested=None, respect_cooldowns=False):
    root = Path(root)
    registry = load_registry(init_registry(root))
    hotel = registry['hotels'][0]
    if (type(request_budget) is not int or not 0 <= request_budget <= 121 or not sources
            or len(set(sources)) != len(sources) or any(s not in SOURCES for s in sources)):
        raise ValueError('Choose unique configured sources and a capture budget of 0–121')
    interval = float(interval_seconds)
    if not 3 <= interval <= 60:
        raise ValueError('Use 3–60 seconds between source captures')
    context = context_for(hotel, start_date=start_date)
    if live and date.fromisoformat(context['start_date']) < datetime.now(timezone.utc).astimezone(INDIA).date():
        raise ValueError('Live jobs cannot reconstruct past dates')
    observations, requests, last_request = [], 0, None
    state, stop_reason = 'complete', None
    capture_fn = capture_fn or capture_source
    with job_lock(root):
        if respect_cooldowns:
            observations = [o for o in source_cooldowns(root, hotel['id']) if o['source'] in sources]
        stopped = {o['source'] for o in observations}
        # Give every source a canary before spending budget on additional dates.
        tasks = [(source, offset) for offset in range(context['days']) for source in sources
                 if offset == 0 or source != 'google_hotels']
        for source, offset in tasks:
            requested_stop = stop_requested() if stop_requested else None
            if requested_stop or (root / 'pause.flag').exists():
                stop_reason = requested_stop or 'pause_requested'
                state = 'paused' if stop_reason == 'pause_requested' else 'stopped'
                break
            if source not in hotel['sources'] or source in stopped:
                continue
            target = context if source == 'google_hotels' else stay_context(context, offset)
            cached = hotel_store.cached(root, hotel['id'], source, target)
            raw = cached['raw'] if cached else None
            if fresh and cached:
                try:
                    previous = parse_source(raw, hotel, source, target)
                    healthy = bool(previous['rates']) or (previous.get('status') == 'unavailable' and previous.get('unavailability_verified') is True)
                except Exception:
                    healthy = False
                if healthy:
                    cached, raw = None, None
            if raw is None and live and requests < request_budget:
                if last_request is not None:
                    time.sleep(max(0, interval - (time.monotonic() - last_request)))
                requested_stop = stop_requested() if stop_requested else None
                if requested_stop:
                    state = 'paused' if requested_stop == 'pause_requested' else 'stopped'
                    stop_reason = requested_stop
                    break
                requests += 1
                last_request = time.monotonic()
                try:
                    output = root / 'captures' / source
                    output.mkdir(parents=True, exist_ok=True)
                    raw = capture_fn(source, hotel, target, output)
                except Exception as exc:
                    raw = {'source': source, 'hotel_id': hotel['id'], 'observed_at': datetime.now(timezone.utc).isoformat(),
                           'requested_context': target, 'capture_exception': type(exc).__name__}
            if raw is None:
                continue
            raw_path = save_raw(root, raw)
            try:
                observation = parse_source(raw, hotel, source, target)
            except Exception as exc:
                observation = {'hotel_id': hotel['id'], 'source': source,
                               'observed_at': (raw.get('observed_at') if isinstance(raw, dict) else None) or datetime.now(timezone.utc).isoformat(),
                               'requested_context': target, 'observed_context': {}, 'status': 'unknown',
                               'reason': 'parser_error:' + type(exc).__name__, 'rates': []}
            observation.update(hotel_store.record(root, raw, observation, target, parser_hash(source)))
            observation['reused'] = bool(cached)
            observation['source_artifact'] = str(raw_path.resolve())
            observations.append(observation)
            checkpoint = build_report(hotel, context, observations, sources=sources, state='running', requests=requests)
            _write_json(root / 'latest.json', checkpoint)
            if progress_fn:
                progress_fn(checkpoint)
            if not observation['rates'] and not (observation.get('status') == 'unavailable' and observation.get('unavailability_verified') is True):
                stopped.add(source)
        report = build_report(hotel, context, observations, sources=sources, state=state,
                              stop_reason=stop_reason, requests=requests)
        if report['summary']['unknown_cells'] and state == 'complete':
            report['state'] = 'partial'
        result = export_report(root, report, dashboard=dashboard)
        if progress_fn:
            progress_fn(result)
        return result
