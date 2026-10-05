"""Small loopback-only dashboard. The collector runs in a bounded subprocess."""
from __future__ import annotations
import json
import mimetypes
import subprocess
import sys
import threading
import re
import base64
import hashlib
import gzip
import hmac
import sqlite3
from http.cookies import SimpleCookie
from functools import lru_cache
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from .pipeline import ROOT, DATA, context_from, _write_json
from . import workspace_jobs

STATE = {"state": "idle", "message": "Saved evidence ready. No collection is running."}
LOCK = threading.Lock()

INTELLIGENCE_ROUTES = {
    '/api/intelligence': set(),
    '/api/intelligence/str/calendar': {'start', 'days', 'city', 'currency', 'offset', 'limit', 'query', 'bedrooms', 'namespace'},
    '/api/intelligence/str/compset': {'subject_id', 'offset', 'limit', 'decision', 'candidate_id'},
    '/api/intelligence/hotel': set(),
    '/api/intelligence/hotel/provider-receipts': set(),
}


def intelligence_response(data_root, request_url):
    """Fixed read projections, with bounded query values and no file arguments."""
    from . import intelligence
    parts = urlsplit(request_url)
    if len(parts.query) > 2048:
        raise ValueError('Query is too long')
    values = parse_qs(parts.query, keep_blank_values=True, max_num_fields=16)
    if parts.path not in INTELLIGENCE_ROUTES or set(values) - INTELLIGENCE_ROUTES[parts.path]:
        raise ValueError('Unsupported saved-data query')
    if any(len(value) != 1 for value in values.values()):
        raise ValueError('Repeated query fields are not supported')
    values = {key: value[0] for key, value in values.items()}
    if parts.path == '/api/intelligence/hotel/provider-receipts':
        from .provider_receipts import load_provider_receipts
        return load_provider_receipts(data_root)
    if values.get('namespace') == 'all':
        values['namespace'] = None
    for key in ('days', 'offset', 'limit', 'bedrooms'):
        if key in values:
            if not re.fullmatch(r'[0-9]{1,6}', values[key]):
                raise ValueError(f'{key} must be a nonnegative integer')
            values[key] = int(values[key])
    if parts.path.endswith('/calendar'):
        if 'start' not in values:
            raise ValueError('start is required')
        return intelligence.str_calendar(data_root, **values)
    if parts.path.endswith('/compset'):
        if not values.get('subject_id'):
            raise ValueError('subject_id is required')
        return intelligence.str_compset(data_root, **values)
    if parts.path.endswith('/hotel'):
        return intelligence.hotel(data_root)
    return intelligence.summary(data_root)

WORKSPACE_INPUTS = (
    "hotel-pipelines/latest.json", "hotels/aketa/latest.json",
    "hotels/aketa/profile-audit/profiles.json", "compset-latest.json",
    "one-night-latest.json", "portfolio-latest.json",
)


@lru_cache(maxsize=2)
def workspace_response(data_root, revisions):
    """Reuse only the read projection; changed source files invalidate it."""
    from .workspace import build_workspace
    return json.dumps(build_workspace(data_root), ensure_ascii=False,
                      allow_nan=False, separators=(",", ":")).encode("utf-8")


def workspace_revisions(data_root):
    from pathlib import Path
    values = []
    for name in WORKSPACE_INPUTS:
        try:
            stat = (Path(data_root) / name).stat()
            values.append((name, stat.st_mtime_ns, stat.st_size))
        except FileNotFoundError:
            values.append((name, None, None))
    return tuple(values)

# These saved-evidence routes never accept a filename or start a collector.
SAVED_PRICE_FILES = {
    "/api/one-night": ("one-night-latest.json", "application/json; charset=utf-8"),
    "/api/hotels/aketa": ("hotels/aketa/latest.json", "application/json; charset=utf-8"),
    "/exports/one-night.json": ("one-night-latest.json", "application/json; charset=utf-8"),
    "/exports/one-night-prices.csv": ("one-night-prices.csv", "text/csv; charset=utf-8"),
    "/exports/hotel-aketa.json": ("hotels/aketa/latest.json", "application/json; charset=utf-8"),
    "/exports/hotel-aketa-rates.csv": ("hotels/aketa/rates.csv", "text/csv; charset=utf-8"),
    "/aketa-calendar": ("provider-receipts/20260930/aketa-compset-live-preview.html", "text/html; charset=utf-8"),
    "/exports/aketa-provider-receipts.json": ("provider-receipts/20260930/aketa-provider-receipts.json", "application/json; charset=utf-8"),
    "/exports/aketa-provider-rates.csv": ("provider-receipts/20260930/aketa-provider-rates.csv", "text/csv; charset=utf-8"),
}


@lru_cache(maxsize=2)
def portfolio_response(path, modified_ns):
    """Parse/project a saved inventory once per file revision for fast UI reads."""
    from pathlib import Path
    result = json.loads(Path(path).read_text(encoding="utf-8"))
    for row in result["properties"]:
        for key in ("calendar", "detail_observations", "profile"):
            row.pop(key, None)
    for row in result.get("airbnb_listings", []):
        row.pop("profile", None)
    return json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def latest():
    path = DATA / "latest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def collector_command(context):
    kind = context.get("_command", "run")
    command = [sys.executable, "-m", "compset", "run", "--listing", context["listing_id"],
               "--checkin", context["checkin"], "--checkout", context["checkout"],
               "--start-date", context["start_date"], "--days",
               str((date.fromisoformat(context["end_date"]) - date.fromisoformat(context["start_date"])).days),
               "--adults", str(context["adults"]), "--currency", context["currency"]]
    if kind == "discover":
        request = DATA / "discovery-request.json"
        _write_json(request, context["_values"])
        command = [sys.executable, "-m", "compset", "discover", "--request", str(request)]
    elif kind == "monitor":
        command = [sys.executable, "-m", "compset", "monitor"]
    elif kind == "inventory":
        request = DATA / "inventory-request.json"
        _write_json(request, context["_values"])
        command = [sys.executable, "-m", "compset", "inventory-refresh", "--request", str(request)]
    return command


def collect_job(context):
    kind = context.get("_command", "run")
    try:
        command = collector_command(context)
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600 if kind == "inventory" else 900 if kind != "run" else 240,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            message = "Collector failed. Previous observations remain available; inspect data/last-error.txt."
            DATA.mkdir(exist_ok=True)
            (DATA / "last-error.txt").write_text((result.stdout + result.stderr)[-12000:], encoding="utf-8")
            state = "failed"
        elif kind == "run":
            data = latest()
            state = "complete"
            coverage = data["coverage"]
            message = f'Collection finished: {coverage["observed_days"]}/{coverage["requested_days"]} calendar dates observed. Review gaps and warnings.'
        else:
            state = "complete"
            progress = DATA / "progress.json"
            message = json.loads(progress.read_text(encoding="utf-8")).get("message", "Job complete; review coverage.") if progress.exists() else "Job complete; review coverage."
            if kind == "inventory" and progress.exists():
                state = json.loads(progress.read_text(encoding="utf-8")).get("state", "complete")
    except subprocess.TimeoutExpired:
        state, message = "failed", "Collection exceeded its time budget and the worker was stopped. Saved checkpoints are retained."
    except Exception:
        state, message = "failed", "The local collection worker could not finish. Previous results are retained."
    try:
        if context.get("_lease_id"):
            workspace_jobs.finish_legacy(DATA, context["_lease_id"], state, message)
    finally:
        with LOCK:
            STATE.update(state=state, message=message)


def workspace_job_status():
    """Read durable workspace ownership without confusing it with legacy progress."""
    status = workspace_jobs.read_job(DATA)
    with LOCK:
        legacy = dict(STATE)
    if legacy.get("state") == "running" and legacy.get("command") != "workspace":
        status = {"job_id": None, "dataset_id": None, "state": "running", "legacy": True,
                  "busy": True, "pause_supported": False, "command": legacy.get("command"),
                  "phase": "legacy collection", "message": legacy.get("message"),
                  "context": status.get("context", {}), "progress": {}}
    return status


def launch_workspace_job(job_id):
    try:
        workspace_jobs.launch_worker(DATA, job_id)
    finally:
        status = workspace_jobs.read_job(DATA)
        with LOCK:
            if STATE.get("job_id") == job_id:
                STATE.update(state=status.get("state", "failed"),
                             message=status.get("message", "Review the saved collection results."))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def allowed_host(self):
        hosts={f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        origin=self.public_origin()
        if origin:hosts.add(urlsplit(origin).netloc)
        return self.headers.get("Host") in hosts

    def public_origin(self):
        from .collection_control import read
        config=read(DATA/'collection-control/config.json',{})
        origin=config.get('public_origin')
        if isinstance(origin,str) and urlsplit(origin).scheme=='https' and urlsplit(origin).path in {'','/'}:
            return origin.rstrip('/')
        return None

    def allowed_origin(self, origin):
        return origin is None or origin in {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}',self.public_origin()}

    def owner_access(self):
        from .collection_control import read
        config=read(DATA/'collection-control/config.json',{})
        if not config.get('public_origin'):return True
        expected=config.get('control_token_sha256','')
        try:
            cookies=SimpleCookie();cookies.load(self.headers.get('Cookie',''))
            token=cookies['compset_control'].value
            return bool(expected) and hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),expected)
        except (KeyError,ValueError):return False

    def send_data(self, status, body, content_type="application/json; charset=utf-8", script_hashes=(), extra_headers=()):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        compressed=False
        encodings={item.split(';')[0].strip():item for item in self.headers.get('Accept-Encoding','').lower().split(',')}
        if len(body)>1024 and 'gzip' in encodings and not re.search(r';\s*q=0(?:\.0*)?\s*$',encodings['gzip']):
            body=gzip.compress(body,compresslevel=5);compressed=True
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header('Vary','Accept-Encoding')
        if compressed:self.send_header('Content-Encoding','gzip')
        self.send_header("X-Content-Type-Options", "nosniff")
        for key,value in extra_headers:self.send_header(key,value)
        scripts = " ".join(("'self'", *script_hashes))
        self.send_header("Content-Security-Policy", f"default-src 'self'; script-src {scripts}; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.allowed_host():
            return self.send_data(403, {"error": "Local host only."})
        path = urlsplit(self.path).path
        if path=='/api/collection/session':
            return self.send_data(200,{'owner':self.owner_access()})
        if path=='/exports/collection-columns.csv':
            file=DATA/'collection-control/data-columns.csv'
            if not file.is_file():return self.send_data(404,{'error':'Column catalogue is not available.'})
            return self.send_data(200,file.read_bytes(),'text/csv; charset=utf-8')
        if path in {'/api/collection/status','/api/collection/listings','/api/collection/map','/api/collection/profile','/api/collection/calendar','/api/collection/hotels'}:
            if not self.allowed_origin(self.headers.get('Origin')):
                return self.send_data(403,{'error':'Use the CompSet dashboard origin.'})
            from . import collection_control,live_collection_data
            try:
                config=collection_control.load_config(DATA)
                values=parse_qs(urlsplit(self.path).query,keep_blank_values=True,max_num_fields=12)
                if any(len(v)!=1 for v in values.values()):raise ValueError('Repeated query fields are not supported.')
                values={k:v[0] for k,v in values.items()}
                action=path.rsplit('/',1)[1]
                body=getattr(live_collection_data,action)(config,values) if action!='status' else live_collection_data.status(config)
                return self.send_data(200,body)
            except ValueError as exc:return self.send_data(400,{'error':str(exc)})
            except (OSError,KeyError,TypeError,sqlite3.Error):return self.send_data(503,{'error':'Collection data is temporarily unreadable. Saved observations are retained.'})
        if path in INTELLIGENCE_ROUTES:
            origin = self.headers.get('Origin')
            if not self.allowed_origin(origin):
                return self.send_data(403, {'error': 'Request must come from the local dashboard.'})
            try:
                body = intelligence_response(DATA, self.path)
                encoded = json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
            except ValueError as exc:
                return self.send_data(400, {'error': str(exc)})
            except (OSError, TypeError, KeyError):
                return self.send_data(503, {'error': 'Saved intelligence could not be read. Existing observations are retained.', 'state': 'read_error'})
            return self.send_data(200, encoded)
        if path == "/api/workspace/job":
            origin = self.headers.get("Origin")
            if not self.allowed_origin(origin):
                return self.send_data(403, {"error": "Request must come from the local dashboard."})
            return self.send_data(200, workspace_job_status())
        if path == "/api/workspace":
            origin = self.headers.get("Origin")
            if not self.allowed_origin(origin):
                return self.send_data(403, {"error": "Request must come from the local dashboard."})
            try:
                body = workspace_response(str(DATA), workspace_revisions(DATA))
            except (OSError, ValueError, TypeError):
                return self.send_data(503, {"error": "Saved rate evidence could not be read. Existing observations are retained.", "state": "read_error"})
            return self.send_data(200, body)
        if path in SAVED_PRICE_FILES:
            origin = self.headers.get("Origin")
            if not self.allowed_origin(origin):
                return self.send_data(403, {"error": "Request must come from the local dashboard."})
            relative, content_type = SAVED_PRICE_FILES[path]
            try:
                file = (DATA / relative).resolve()
                if not file.is_relative_to(DATA.resolve()):
                    return self.send_data(403, {"error": "Saved evidence must stay inside the data directory."})
                body = file.read_bytes()
                if file.suffix == ".json":
                    # A partial write is a read error, never an empty successful dataset.
                    result = json.loads(body)
                    if not isinstance(result, dict):
                        raise ValueError("Expected a saved report object.")
            except FileNotFoundError:
                return self.send_data(404, {"error": "No saved evidence for this dataset yet.", "state": "not_collected"})
            except (OSError, ValueError, UnicodeError):
                return self.send_data(503, {"error": "Saved evidence is temporarily unreadable. Refresh to try again.", "state": "read_error"})
            # Only this fixed, generated HTML page needs inline scripts. Bind their
            # permissions to the exact response bytes; never enable unsafe-inline.
            script_hashes = ()
            if path == "/aketa-calendar":
                script_hashes = tuple("'sha256-" + base64.b64encode(hashlib.sha256(script).digest()).decode("ascii") + "'"
                                      for script in re.findall(br"<script\b[^>]*>(.*?)</script\s*>", body, re.DOTALL | re.IGNORECASE))
            return self.send_data(200, body, content_type, script_hashes=script_hashes)
        if path == "/api/status":
            with LOCK:
                status = dict(STATE)
            job = workspace_jobs.read_job(DATA)
            if status.get("command") == "workspace" or (job.get("state") == "running" and not job.get("legacy")):
                return self.send_data(200, {**job, "command": "workspace"})
            progress = DATA / "progress.json"
            if status["state"] == "running" and progress.exists():
                status["message"] = json.loads(progress.read_text(encoding="utf-8")).get("message", status["message"])
            details = DATA / "bnbme-details-source.json"
            if status["state"] == "running" and status.get("command") == "inventory" and details.exists():
                report = json.loads(details.read_text(encoding="utf-8"))["report"]
                status["message"] = f'Slow inventory refresh: {report.get("observed_count", 0)}/{report.get("catalog_count", 0)} properties checkpointed.'
            return self.send_data(200, status)
        if path == "/api/compset":
            saved = DATA / "compset-latest.json"
            if not saved.exists():
                return self.send_data(404, {"error": "No competitor set collected yet."})
            result = json.loads(saved.read_text(encoding="utf-8"))
            monitoring = DATA / "monitoring-latest.json"
            if monitoring.exists():
                data = json.loads(monitoring.read_text(encoding="utf-8"))
                if data.get("compset_run_id") == result["run_id"]:
                    result["monitoring"] = data
            return self.send_data(200, result)
        if path == "/api/portfolio":
            saved = DATA / "portfolio-latest.json"
            if not saved.exists():
                return self.send_data(404, {"error": "No BnBMe inventory imported yet."})
            return self.send_data(200, portfolio_response(str(saved), saved.stat().st_mtime_ns))
        if path == "/api/health":
            saved = DATA / "schema-health.json"
            return self.send_data(200, json.loads(saved.read_text(encoding="utf-8")) if saved.exists() else {"state": "not_observed", "changes": [], "semantic_alerts": []})
        if path in {"/exports/portfolio.json", "/exports/portfolio.csv", "/exports/hosts.csv", "/exports/prices.csv", "/exports/inventory-calendar.csv"}:
            saved = DATA / "portfolio-latest.json"
            if not saved.exists():
                return self.send_data(404, {"error": "No BnBMe inventory imported yet."})
            result = json.loads(saved.read_text(encoding="utf-8"))
            file = DATA / "inventory" / result["snapshot_id"] / path.rsplit("/", 1)[1]
            return self.send_data(200, file.read_bytes(), "application/json" if file.suffix == ".json" else "text/csv; charset=utf-8")
        if path in {"/exports/candidates.csv", "/exports/compset.json"}:
            saved = DATA / "compset-latest.json"
            if not saved.exists():
                return self.send_data(404, {"error": "No competitor set yet."})
            result = json.loads(saved.read_text(encoding="utf-8"))
            file = DATA / "compsets" / result["run_id"] / path.rsplit("/", 1)[1]
            return self.send_data(200, file.read_bytes(), "application/json" if file.suffix == ".json" else "text/csv; charset=utf-8")
        if path == "/api/latest":
            data = latest()
            return self.send_data(200 if data else 404, data or {"error": "No observations yet."})
        if path in {"/exports/calendar.csv", "/exports/quotes.csv", "/exports/result.json"}:
            data = latest()
            if not data:
                return self.send_data(404, {"error": "No observations yet."})
            file = DATA / "runs" / data["run_id"] / path.rsplit("/", 1)[1]
            return self.send_data(200, file.read_bytes(), "application/json" if file.suffix == ".json" else "text/csv; charset=utf-8")
        files = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css",
                 "/collection-studio.js":"collection-studio.js","/collection-studio.css":"collection-studio.css",
                 "/rates-workspace.js": "rates-workspace.js", "/rates-workspace.css": "rates-workspace.css",
                 "/dual-workspace.js": "dual-workspace.js", "/dual-workspace.css": "dual-workspace.css"}
        for asset in ("leaflet.js", "leaflet.css", "images/marker-icon.png", "images/marker-icon-2x.png", "images/marker-shadow.png", "images/layers.png", "images/layers-2x.png"):
            files["/vendor/" + asset] = "vendor/" + asset
        if path not in files:
            return self.send_data(404, {"error": "Not found."})
        file = ROOT / "compset" / "static" / files[path]
        if not file.exists():
            return self.send_data(503, {"error": "Dashboard files are not installed."})
        return self.send_data(200, file.read_bytes(), (mimetypes.guess_type(file.name)[0] or "text/plain") + "; charset=utf-8")

    def do_POST(self):
        origin = self.headers.get("Origin")
        if not self.allowed_host() or not self.allowed_origin(origin) or self.headers.get("X-CompSet-Request") != "dashboard-v1":
            return self.send_data(403, {"error": "Request must come from the local dashboard."})
        if self.path not in {"/api/collection/session","/api/collection/refresh","/api/run", "/api/discover", "/api/monitor", "/api/inventory-refresh", "/api/inventory-pause", "/api/workspace/collect", "/api/workspace/pause"}:
            return self.send_data(404, {"error": "Not found."})
        if self.path!='/api/collection/session' and not self.owner_access():
            return self.send_data(401,{'error':'Open your owner link to control collection. Viewing the data is free.'})
        if self.headers.get_content_type() != "application/json":
            return self.send_data(415, {"error": "Use application/json."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                raise ValueError("Invalid request size.")
            values = json.loads(self.rfile.read(length))
            if not isinstance(values, dict):
                raise ValueError("Expected an object.")
            if self.path=='/api/collection/session':
                from .collection_control import load_config
                config=load_config(DATA);token=values.get('token')
                if set(values)!={'token'} or not isinstance(token,str) or not re.fullmatch('[A-Za-z0-9_-]{40,100}',token):
                    return self.send_data(401,{'error':'Invalid owner link.'})
                expected=config.get('control_token_sha256','')
                if not expected or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),expected):
                    return self.send_data(401,{'error':'Invalid owner link.'})
                cookie=f'compset_control={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800'
                if self.public_origin():cookie+='; Secure'
                return self.send_data(200,{'state':'owner_session_ready'},extra_headers=(('Set-Cookie',cookie),))
            if self.path=='/api/collection/refresh':
                from .collection_control import load_config,request_refresh
                return self.send_data(202,request_refresh(load_config(DATA),values))
            if (DATA/'collection-control/config.json').exists():
                return self.send_data(409,{'error':'Use On-demand refresh in the live collection panel. The shared collector prevents parallel jobs.','state':'shared_collector_required'})
            if self.path == "/api/workspace/pause":
                if set(values) != {"job_id"}:
                    raise ValueError("Use only the active job_id to pause collection.")
                return self.send_data(202, workspace_jobs.request_pause(DATA, values["job_id"]))
            if self.path == "/api/workspace/collect":
                with LOCK:
                    if STATE["state"] == "running":
                        raise workspace_jobs.BusyError("A collection is already running.")
                    job = workspace_jobs.reserve_job(DATA, values)
                    STATE.update(state="running", command="workspace", job_id=job["job_id"], message=job["message"])
                try:
                    threading.Thread(target=launch_workspace_job, args=(job["job_id"],), daemon=True).start()
                except Exception:
                    workspace_jobs.fail_start(DATA, job["job_id"])
                    with LOCK:
                        STATE.update(state="failed", message="The collection worker could not start. Saved evidence is retained.")
                    return self.send_data(503, {"error": STATE["message"]})
                return self.send_data(202, job)
            if self.path == "/api/inventory-pause":
                DATA.mkdir(exist_ok=True)
                (DATA / "pause-inventory.flag").write_text("User requested a cooperative pause.\n", encoding="utf-8")
                return self.send_data(202, {"state": "pause_requested"})
            context = context_from(values)
            if self.path == "/api/discover":
                from .workflows import criteria_from
                criteria_from(values)
                context.update(_command="discover", _values=values)
            elif self.path == "/api/monitor":
                saved = DATA / "compset-latest.json"
                if not saved.exists() or not json.loads(saved.read_text(encoding="utf-8")).get("selected"):
                    raise ValueError("Discover an eligible competitor set first.")
                context["_command"] = "monitor"
            elif self.path == "/api/inventory-refresh":
                context.update(_command="inventory", _values=values)
        except workspace_jobs.BusyError as exc:
            return self.send_data(409, {"error": str(exc)})
        except (ValueError, TypeError, OverflowError) as exc:
            return self.send_data(400, {"error": str(exc)})
        except OSError:
            return self.send_data(503, {"error": "Local collection state could not be saved. Previous observations are retained."})
        with LOCK:
            if STATE["state"] == "running":
                return self.send_data(409, {"error": "A collection is already running."})
            try:
                context["_lease_id"] = workspace_jobs.reserve_legacy(DATA, context)
                if context.get("_command") == "inventory":
                    (DATA / "pause-inventory.flag").unlink(missing_ok=True)
                DATA.mkdir(exist_ok=True)
                _write_json(DATA / "progress.json", {"message": "Preparing collection…"})
            except workspace_jobs.BusyError as exc:
                return self.send_data(409, {"error": str(exc)})
            except OSError:
                if context.get("_lease_id"):
                    workspace_jobs.finish_legacy(DATA, context["_lease_id"])
                return self.send_data(503, {"error": "Collection preparation could not be saved."})
            STATE.update(state="running", command=context.get("_command", "run"), message="Collecting public listing and calendar responses…")
        try:
            threading.Thread(target=collect_job, args=(context,), daemon=True).start()
        except Exception:
            workspace_jobs.finish_legacy(DATA, context["_lease_id"])
            with LOCK:
                STATE.update(state="failed", message="The collection worker could not start.")
            return self.send_data(503, {"error": "The collection worker could not start."})
        return self.send_data(202, {"state": "running"})


def serve(port=8765):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"CompSet Studio: http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
