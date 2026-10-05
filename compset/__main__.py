from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .pipeline import context_from, run


def main():
    parser = argparse.ArgumentParser(description="CompSet Studio: local Airbnb evidence pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("run", help="Collect one listing using Scrapling")
    collect.add_argument("--listing", default="1567889913136387224")
    collect.add_argument("--checkin")
    collect.add_argument("--checkout")
    collect.add_argument("--start-date")
    collect.add_argument("--days", type=int, default=30)
    collect.add_argument("--adults", type=int, default=1)
    collect.add_argument("--currency", default="AED")
    replay = sub.add_parser("reparse", help="Reparse saved public evidence without network requests")
    replay.add_argument("source", type=Path)
    serve = sub.add_parser("serve", help="Start the local browser dashboard")
    serve.add_argument("--port", type=int, default=8765)
    discovery = sub.add_parser("discover", help="Discover and audit nearby competitors")
    discovery.add_argument("--request", type=Path, required=True)
    sub.add_parser("monitor", help="Refresh the saved selected competitor set")
    inventory = sub.add_parser("inventory", help="Import observed BnBMe catalogue and detail evidence into SQLite")
    inventory.add_argument("--source", type=Path, default=Path("data/bnbme-catalog-source.json"))
    refresh = sub.add_parser("inventory-refresh", help="Start or resume slow official inventory reads")
    refresh.add_argument("--request", type=Path, required=True)
    nightly = sub.add_parser("nightly", help="Export verified one-adult 30-day evidence from a saved capture")
    nightly.add_argument("--source", type=Path, required=True)
    nightly_monitor = sub.add_parser("nightly-monitor", help="Slowly collect next-30-day calendars for the saved selected set")
    nightly_monitor.add_argument("--request", type=Path)
    nightly_monitor.add_argument("--max-listings", type=int, default=100)
    nightly_monitor.add_argument("--request-budget", type=int, default=100)
    nightly_monitor.add_argument("--interval-seconds", type=float, default=3.0)
    single = sub.add_parser("one-night-monitor", help="Collect exact one-night totals after calendar restriction preflight")
    single.add_argument("--request-budget", type=int, default=100)
    single.add_argument("--interval-seconds", type=float, default=3.0)
    sub.add_parser("hotels-init", help="Initialize the verified Aketa OTA registry without network requests")
    hotels = sub.add_parser("hotel-run", help="Plan/resume Aketa source pipelines; default is cached evidence only")
    hotels.add_argument("--sources", default="google_hotels,makemytrip,booking,expedia,agoda")
    hotels.add_argument("--start-date")
    hotels.add_argument("--live", action="store_true")
    hotels.add_argument("--request-budget", type=int, default=5)
    hotels.add_argument("--interval-seconds", type=float, default=3)
    hotels.add_argument("--dashboard", action="store_true", help="Publish saved source health/rates in the existing Aketa view")
    hotel_import = sub.add_parser("hotel-import", help="Parse and store observed OTA evidence without network requests")
    hotel_import.add_argument("--source", required=True, choices=["google_hotels", "makemytrip", "booking", "expedia", "agoda"])
    hotel_import.add_argument("--file", type=Path, required=True)
    hotel_import.add_argument("--start-date", required=True)
    hotel_import.add_argument("--checkin")
    sub.add_parser("hotel-status", help="Read saved hotel source/date coverage")
    workspace_worker = sub.add_parser('workspace-worker', help='Run one dashboard-reserved finite collection job')
    workspace_worker.add_argument('--job-id', required=True)
    workspace_worker.add_argument('--data-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'workspace-worker':
            from .workspace_jobs import run_worker
            result = run_worker(args.data_dir, args.job_id)
            print(json.dumps(result, ensure_ascii=True))
            return
        if args.command == "hotels-init":
            from .hotel_jobs import init_registry
            print(str(init_registry()))
            return
        if args.command == "hotel-run":
            from .hotel_jobs import run_pipeline
            result = run_pipeline(sources=tuple(args.sources.split(',')), start_date=args.start_date,
                request_budget=args.request_budget, interval_seconds=args.interval_seconds,
                live=args.live, dashboard=args.dashboard)
            print(json.dumps({k: result[k] for k in ('job_id', 'state', 'summary', 'source_states', 'capture_calls_this_run')}, indent=2))
            return
        if args.command == "hotel-import":
            from .hotel_jobs import import_source
            result = import_source(args.source, args.file, start_date=args.start_date, checkin=args.checkin)
            print(json.dumps({k: result.get(k) for k in ('source', 'status', 'reason', 'capture_id', 'interpretation_id')}, indent=2))
            return
        if args.command == "hotel-status":
            from .hotel_jobs import DEFAULT_ROOT
            result = json.loads((DEFAULT_ROOT / 'latest.json').read_text(encoding='utf-8'))
            print(json.dumps({k: result[k] for k in ('job_id', 'state', 'summary', 'source_states')}, indent=2))
            return
        if args.command == "serve":
            from .server import serve
            serve(args.port)
            return
        if args.command == "nightly":
            from .nightly import export_source
            result = export_source(args.source)
            print(json.dumps({"run_id": result["run_id"], "context": result["context"], "coverage": result["coverage"]}, indent=2))
            return
        if args.command == "nightly-monitor":
            from .nightly import collect_selected
            values = json.loads(args.request.read_text(encoding="utf-8")) if args.request else {}
            result = collect_selected(values, max_listings=args.max_listings,
                                      request_budget=args.request_budget, interval_seconds=args.interval_seconds)
            print(json.dumps({key: result.get(key) for key in ("state", "context", "processed", "total", "direct_requests_this_run", "stop_reason")}, indent=2))
            return
        if args.command == "one-night-monitor":
            from .one_night import collect_one_night
            result = collect_one_night(request_budget=args.request_budget, interval_seconds=args.interval_seconds)
            print(json.dumps({key: result.get(key) for key in ("state", "total_date_cells", "quoted_date_cells", "calendar_skipped_date_cells", "unknown_date_cells", "direct_requests_this_run", "stop_reason")}, indent=2))
            return
        if args.command == "discover":
            from .workflows import discover_compset
            result = discover_compset(json.loads(args.request.read_text(encoding="utf-8")))
            print(json.dumps({"run_id": result["run_id"], "summary": result["summary"]}, indent=2))
            return
        if args.command == "monitor":
            from .batch import monitor_compset
            result = monitor_compset()
            print(json.dumps({"state": result["state"], "processed": result["processed"], "total": result["total"]}))
            return
        if args.command == "inventory":
            from .inventory import import_inventory
            result = import_inventory(args.source)
            print(json.dumps({"snapshot_id": result["snapshot_id"], "summary": result["summary"]}, indent=2))
            return
        if args.command == "inventory-refresh":
            from .refresh import refresh_inventory
            print(json.dumps(refresh_inventory(json.loads(args.request.read_text(encoding="utf-8"))), indent=2))
            return
        if args.command == "reparse":
            source = json.loads(args.source.read_text(encoding="utf-8"))
            context = source.pop("context")
            result = run(context, capture=source)
        else:
            result = run(context_from(vars(args)))
        print(json.dumps({"run_id": result["run_id"], "coverage": result["coverage"], "report": result["report"], "warnings": result["warnings"]}, indent=2))
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Collection failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
