"""Finite dashboard collection jobs with durable identity and a shared local lease."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

from .pipeline import DATA, ROOT, _write_json

DATASETS = ('aketa', 'airbnb-compset')
JOB_PATTERN = re.compile(r'[a-f0-9]{32}')
TERMINAL = ('paused', 'partial', 'complete', 'stopped', 'failed', 'interrupted')


class BusyError(RuntimeError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(path, default=None):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        return value if isinstance(value, dict) else default
    except (OSError, ValueError, UnicodeError):
        return default


def _job_path(root, job_id):
    if not isinstance(job_id, str) or not JOB_PATTERN.fullmatch(job_id):
        raise ValueError('Invalid job identity.')
    return Path(root) / 'workspace-jobs' / job_id


def _alive(pid):
    if type(pid) is not int or pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # Query denied: never assume it is dead.
        code = wintypes.DWORD()
        try:
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextmanager
def _control(root):
    """Kernel-released file lock serializes lease changes across app processes."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'collection-control.lock').open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise BusyError('Another collector is changing job state.') from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def _safe_context(context):
    fields = ('hotel_id', 'listing_id', 'start_date', 'end_date', 'days', 'checkin', 'checkout',
              'stay_nights', 'rooms', 'adults', 'children', 'infants', 'pets', 'currency', 'timezone', 'locale', 'selection_count')
    return {k: v for k, v in context.items() if k in fields and (v is None or type(v) in (str, int, bool))}


def _public(job):
    result = {k: job.get(k) for k in ('job_id', 'dataset_id', 'mode', 'state', 'phase', 'message',
                                     'started_at', 'updated_at', 'finished_at', 'pause_requested', 'context', 'progress')}
    result.update(busy=job.get('state') == 'running', pause_supported=job.get('state') == 'running')
    return result


def _save(root, job):
    job['updated_at'] = _now()
    _write_json(_job_path(root, job['job_id']) / 'job.json', job)


def _lease(root):
    return _json(Path(root) / 'collection-lease.json', {})


def _claim(root, job_id, kind, context):
    """Caller holds _control. Dead owners are reclaimed; live owners are never stopped."""
    path = Path(root) / 'collection-lease.json'
    existing = _lease(root)
    if path.exists() and not existing:
        raise BusyError('The saved collection lease is unreadable; no new worker was started.')
    if existing:
        if _alive(existing.get('pid')):
            raise BusyError('A collection is already running.')
        if existing.get('kind') == 'workspace':
            old = _json(_job_path(root, existing['job_id']) / 'job.json')
            if old and old.get('state') == 'running':
                old.update(state='interrupted', phase='finished', finished_at=_now(),
                           message='The previous worker ended without finalizing; saved checkpoints are retained.')
                _save(root, old)
    _write_json(path, {'job_id': job_id, 'kind': kind, 'pid': os.getpid(), 'context': _safe_context(context), 'started_at': _now()})


def _release(root, job_id):
    for attempt in range(40):
        try:
            with _control(root):
                if _lease(root).get('job_id') == job_id:
                    (Path(root) / 'collection-lease.json').unlink(missing_ok=True)
            return
        except BusyError:
            if attempt == 39:
                raise
            time.sleep(0.05)


def _plan(root, dataset_id):
    if dataset_id == 'aketa':
        from .hotel_contracts import SEED, context_for
        context = context_for(SEED['hotels'][0])
        context['end_date'] = str(datetime.fromisoformat(context['start_date']).date() + timedelta(days=30))
        return context, None
    from .nightly import DUBAI, window_context
    snapshot = _json(Path(root) / 'compset-latest.json')
    if not snapshot or not isinstance(snapshot.get('selected'), list) or not isinstance(snapshot.get('context'), dict):
        raise ValueError('Save an Airbnb subject and selected competitor set first.')
    identifier = snapshot['context'].get('listing_id')
    subject_row = snapshot.get('subject')
    subject = subject_row.get('listing_id') if isinstance(subject_row, dict) else None
    if not isinstance(identifier, str) or not re.fullmatch(r'\d{1,25}', identifier) or subject != identifier:
        raise ValueError('The saved Airbnb subject identity is not verified.')
    currency = snapshot['context'].get('currency')
    if currency not in ('AED', 'SAR', 'USD', 'EUR', 'GBP', 'INR'):
        raise ValueError('The saved dataset needs an explicit supported currency.')
    if not isinstance(snapshot.get('run_id'), str) or not snapshot['run_id']:
        raise ValueError('The saved selected set has no run identity.')
    ids = [str(r.get('listing_id', '')) for r in snapshot['selected'] if isinstance(r, dict)]
    if not ids or len(ids) != len(snapshot['selected']) or len(ids) > 100 or identifier in ids or any(not re.fullmatch(r'\d{1,25}', i) for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Expected one to one hundred unique selected Airbnb listings.')
    today = datetime.now(timezone.utc).astimezone(DUBAI).date()
    context = window_context({'listing': identifier, 'currency': currency,
                              'checkin': str(today), 'checkout': str(today + timedelta(days=1))})
    context.update(stay_nights=1, days=30, timezone='Asia/Dubai', selection_count=len(ids))
    return context, snapshot


def _resume_plan(root, dataset_id):
    visible = read_job(root)
    if visible.get('dataset_id') != dataset_id or visible.get('state') not in ('paused', 'partial', 'stopped', 'failed', 'interrupted'):
        raise ValueError('There is no resumable job for this dataset. Start a fresh collection.')
    old_id = visible.get('job_id')
    previous = _json(_job_path(root, old_id) / 'job.json', {})
    context = previous.get('collector_context')
    if not isinstance(context, dict):
        raise ValueError('The saved job context is unavailable. Start a fresh collection.')
    from .hotel_contracts import INDIA
    from .nightly import DUBAI
    today = datetime.now(timezone.utc).astimezone(INDIA if dataset_id == 'aketa' else DUBAI).date()
    if context.get('start_date') != str(today):
        raise ValueError('The previous date window has expired. Start a fresh collection for the next thirty dates.')
    snapshot = _json(_job_path(root, old_id) / 'selection.json') if dataset_id == 'airbnb-compset' else None
    if dataset_id == 'airbnb-compset' and not snapshot:
        raise ValueError('The saved selection is unavailable. Start a fresh collection.')
    return dict(context), snapshot, old_id


def reserve_job(data_root, values):
    if not isinstance(values, dict) or set(values) - {'dataset_id', 'mode'}:
        raise ValueError('Use only dataset_id and mode.')
    dataset, mode = values.get('dataset_id'), values.get('mode', 'fresh')
    if dataset not in DATASETS or mode not in ('fresh', 'resume'):
        raise ValueError('Choose a supported dataset and fresh or resume mode.')
    root = Path(data_root)
    job_id = uuid.uuid4().hex
    with _control(root):
        active = _lease(root)
        if active and _alive(active.get('pid')):
            raise BusyError('A collection is already running.')
        resume_of = None
        if mode == 'resume':
            context, snapshot, resume_of = _resume_plan(root, dataset)
        else:
            context, snapshot = _plan(root, dataset)
        _claim(root, job_id, 'workspace', context)
        try:
            folder = _job_path(root, job_id)
            folder.mkdir(parents=True)
            job = {'job_id': job_id, 'dataset_id': dataset, 'mode': mode, 'state': 'running', 'phase': 'planning',
                   'message': 'Preparing a finite collection using the recorded dataset membership.',
                   'started_at': _now(), 'updated_at': _now(), 'finished_at': None, 'pause_requested': False,
                   'context': _safe_context(context), 'progress': {'capture_budget': 8} if dataset == 'aketa' else
                   {'calendar_request_budget': 100, 'quote_request_budget': 100, 'planned_listings': len(snapshot['selected']) + 1},
                   'collector_context': context, 'resume_of': resume_of}
            if snapshot:
                _write_json(folder / 'selection.json', snapshot)
            _save(root, job)
            _write_json(root / 'workspace-jobs' / 'latest.json', {'job_id': job_id})
        except Exception:
            (root / 'collection-lease.json').unlink(missing_ok=True)
            raise
    return _public(job)


def read_job(data_root):
    root = Path(data_root)
    lease = _lease(root)
    if lease.get('kind') == 'legacy' and _alive(lease.get('pid')):
        return {'job_id': None, 'dataset_id': None, 'mode': None, 'state': 'running', 'phase': 'legacy collection',
                'message': 'Another dashboard collection is running. Its controls remain in the collection view.',
                'started_at': lease.get('started_at'), 'updated_at': lease.get('started_at'), 'finished_at': None,
                'pause_requested': False, 'context': lease.get('context', {}), 'progress': {},
                'busy': True, 'pause_supported': False, 'legacy': True}
    pointer = _json(root / 'workspace-jobs' / 'latest.json', {})
    if not isinstance(pointer.get('job_id'), str) or not JOB_PATTERN.fullmatch(pointer['job_id']):
        return {'state': 'idle', 'job_id': None, 'busy': bool(lease and _alive(lease.get('pid'))), 'pause_supported': False}
    folder = _job_path(root, pointer['job_id'])
    job = _json(folder / 'job.json')
    if not job:
        return {'state': 'failed', 'job_id': pointer['job_id'], 'busy': False, 'pause_supported': False,
                'message': 'Saved job status could not be read. Existing observations are retained.'}
    job['pause_requested'] = (folder / 'pause.flag').exists() or job.get('pause_requested', False)
    if job.get('state') == 'running' and (lease.get('job_id') != job['job_id'] or not _alive(lease.get('pid'))):
        job.update(state='interrupted', phase='finished', message='The worker is no longer running; checkpoints are retained.')
    return _public(job)


def request_pause(data_root, job_id):
    root = Path(data_root)
    with _control(root):
        job = read_job(root)
        if not isinstance(job_id, str) or job.get('job_id') != job_id or job.get('state') != 'running' or not job.get('pause_supported'):
            raise BusyError('That job is not the active workspace collector.')
        (_job_path(root, job_id) / 'pause.flag').write_text('Pause requested by the local dashboard.\n', encoding='utf-8')
    return read_job(root)


def reserve_legacy(data_root, context):
    job_id = uuid.uuid4().hex
    with _control(data_root):
        _claim(data_root, job_id, 'legacy', context)
    return job_id


def finish_legacy(data_root, lease_id, state=None, message=None):
    _release(data_root, lease_id)


def _finish(root, job_id, state, message):
    job = _json(_job_path(root, job_id) / 'job.json')
    if job:
        job.update(state=state, phase='finished', message=message, finished_at=_now())
        _save(root, job)
    _release(root, job_id)
    return _public(job) if job else {'state': state, 'job_id': job_id}


def fail_start(data_root, job_id):
    return _finish(Path(data_root), job_id, 'failed', 'The local collection thread could not start. Previous observations are retained.')


def launch_worker(data_root, job_id):
    """Run only the fixed local worker; the API cannot provide commands or paths."""
    root = Path(data_root)
    try:
        result = subprocess.run([sys.executable, '-m', 'compset', 'workspace-worker', '--job-id', job_id,
                                 '--data-dir', str(root.resolve())], cwd=ROOT, capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=3600,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        job = _json(_job_path(root, job_id) / 'job.json', {})
        if result.returncode or job.get('state') == 'running':
            _finish(root, job_id, 'failed', 'The collection worker could not finish. Saved checkpoints and earlier evidence are retained.')
    except subprocess.TimeoutExpired:
        _finish(root, job_id, 'stopped', 'The one-hour worker budget ended. Saved checkpoints are available for an explicit resume.')
    except Exception:
        _finish(root, job_id, 'failed', 'The local worker could not start. Previous observations are retained.')


def _recent_stop(root):
    """A recent Airbnb transport/contract stop is a source cooldown, not inventory."""
    for name in ('nightly-monitoring-latest.json', 'one-night-latest.json'):
        report = _json(Path(root) / name, {})
        try:
            stamp = datetime.fromisoformat(report.get('updated_at') or report['context']['observed_at'])
            age = (datetime.now(timezone.utc) - stamp).total_seconds()
            reason = report.get('stop_reason')
            if report.get('state') == 'stopped' and reason not in (None, 'pause_requested', 'time_budget_reached', 'calendar_budget_reached') and 0 <= age <= 21600:
                return reason
        except (ValueError, TypeError, KeyError):
            continue
    return None


def run_worker(data_root, job_id):
    root = Path(data_root)
    folder = _job_path(root, job_id)
    with _control(root):
        job = _json(folder / 'job.json')
        lease = _lease(root)
        if not job or job.get('state') != 'running' or lease.get('job_id') != job_id or lease.get('kind') != 'workspace':
            raise BusyError('The requested job does not own collection.')
        try:
            handle = os.open(folder / 'worker.started', os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(handle)
        except FileExistsError as exc:
            raise BusyError('This job already started a worker.') from exc
        lease['pid'] = os.getpid()
        _write_json(root / 'collection-lease.json', lease)
    deadline = time.monotonic() + 3540

    def stopping():
        if (folder / 'pause.flag').exists():
            return 'pause_requested'
        if time.monotonic() >= deadline:
            return 'time_budget_reached'
        return None

    def progress(phase, report):
        current = _json(folder / 'job.json', job)
        current.update(phase=phase, pause_requested=(folder / 'pause.flag').exists(),
                       message=f'{phase.capitalize()} collection is running; coverage remains explicit.')
        for field in ('capture_calls_this_run', 'processed', 'total', 'direct_requests_this_run',
                      'bootstrap_browser_visits', 'quoted_date_cells', 'calendar_skipped_date_cells',
                      'unknown_date_cells', 'total_date_cells'):
            if type(report.get(field)) is int:
                current['progress'][phase + '_' + field] = report[field]
        bootstrap_report = report.get('bootstrap_report')
        bootstrap_report = bootstrap_report if isinstance(bootstrap_report, dict) else {}
        replay = bootstrap_report.get('direct_replay')
        bootstrap = replay.get('requests', []) if isinstance(replay, dict) else []
        if isinstance(bootstrap, list):
            current['progress'][phase + '_bootstrap_direct_requests'] = len(bootstrap)
        if isinstance(report.get('summary'), dict):
            current['progress']['coverage'] = {k: v for k, v in report['summary'].items() if type(v) is int}
        _save(root, current)

    try:
        backups = folder / 'before'
        backups.mkdir()
        for name in ('hotel-pipelines/latest.json', 'nightly-monitoring-latest.json', 'one-night-latest.json', 'one-night-prices.csv'):
            source = root / name
            if source.exists():
                shutil.copyfile(source, backups / name.replace('/', '-'))
        context = job['collector_context']
        if job['dataset_id'] == 'aketa':
            from .hotel_jobs import run_pipeline
            (root / 'hotel-pipelines' / 'pause.flag').unlink(missing_ok=True)
            result = run_pipeline(root=root / 'hotel-pipelines', start_date=context['start_date'], request_budget=8,
                                  interval_seconds=3, live=True, dashboard=True, fresh=job['mode'] == 'fresh',
                                  respect_cooldowns=True, progress_fn=lambda r: progress('prices', r), stop_requested=stopping)
            state = result.get('state', 'partial')
            if state not in TERMINAL:
                state = 'partial'
            unknown = result.get('summary', {}).get('unknown_cells', 0)
            if state == 'complete' and unknown:
                state = 'partial'
            return _finish(root, job_id, state, f'Hotel collection ended with {unknown} unknown source/date cells. No missing price is treated as unavailable.')
        from .nightly import collect_selected
        from .one_night import collect_one_night
        snapshot = _json(folder / 'selection.json')
        cooldown = _recent_stop(root)
        if cooldown:
            return _finish(root, job_id, 'stopped', 'Airbnb is in a six-hour source cooldown after a transport, access or schema stop. Previous evidence keeps its original dates and timestamps.')
        for name in ('pause-nightly.flag', 'pause-one-night.flag'):
            (root / name).unlink(missing_ok=True)
        calendar = collect_selected(data_dir=root, max_listings=100, request_budget=100, interval_seconds=3,
                                    fresh=job['mode'] == 'fresh', snapshot=snapshot, context_override=context,
                                    progress_fn=lambda r: progress('calendars', r), stop_requested=stopping, job_id=job_id)
        reason = stopping()
        if calendar.get('state') != 'complete':
            reason = reason or calendar.get('stop_reason') or 'calendar_budget_reached'
        if not reason:
            # The next collector has its own bootstrap; preserve pacing across
            # phase boundaries as well as inside each reusable session.
            time.sleep(3)
            reason = stopping()
        # A no-network checkpoint publishes the current planned grid after a
        # calendar stop, preserving any reusable quote's original timestamp.
        result = collect_one_night(data_dir=root, request_budget=0 if reason else 100, interval_seconds=3,
                                   force_fresh=job['mode'] == 'fresh' and not reason, snapshot=snapshot,
                                   calendar_report=calendar, context_override=context,
                                   progress_fn=lambda r: progress('prices', r), stop_requested=stopping,
                                   job_id=job_id, skip_network_reason=reason)
        state = result.get('state', 'partial')
        if state == 'budget_reached':
            state = 'partial'
        if state not in TERMINAL:
            state = 'partial'
        if state == 'complete' and result.get('unknown_date_cells', 0):
            state = 'partial'
        return _finish(root, job_id, state,
                       f'Airbnb collection ended: {result.get("quoted_date_cells", 0)} quoted cells; {result.get("unknown_date_cells", 0)} unknown. Restrictions remain separate from unavailability.')
    except Exception:
        _finish(root, job_id, 'failed', 'Collection stopped on a local or source error. Partial checkpoints and earlier evidence are retained.')
        raise
