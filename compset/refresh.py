"""Manually started/resumed inventory jobs. No background schedule is installed."""
from __future__ import annotations
from datetime import date
import json
from .pipeline import DATA, context_from, _write_json


def refresh_inventory(values):
    from .host_inventory import collect_host_inventory
    from .inventory import import_inventory
    from .portfolio import collect_catalog, collect_catalog_details
    context = context_from(values)
    pause = DATA / "pause-inventory.flag"
    catalog_file = DATA / "bnbme-catalog-source.json"
    # Resume the same captured catalogue until the user requests a new catalogue.
    if catalog_file.exists() and not values.get("refresh_catalog", False):
        catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
    else:
        catalog = collect_catalog()
        if catalog["report"].get("stop_reason"):
            raise RuntimeError("Catalogue read stopped: " + catalog["report"]["stop_reason"])
        _write_json(catalog_file, catalog)
    start = date.fromisoformat(context["start_date"]).replace(day=1)
    from datetime import timedelta
    end = start + timedelta(days=365)
    request = {"checkin": context["checkin"], "checkout": context["checkout"], "adults": context["adults"],
               "pets": 0, "calendar_start_date": str(start), "calendar_end_date": str(end - timedelta(days=1))}
    result = collect_catalog_details(catalog, request, DATA / "bnbme-details-source.json", pause_seconds=1.0)
    host_result = None
    if not result["report"].get("stop_reason") and not pause.exists():
        manifest = DATA / "laya-public-listings.json"
        if manifest.exists():
            host_result = collect_host_inventory(manifest, values=values)
    inventory = import_inventory(catalog_file)
    host_stop = host_result and host_result.get("report", {}).get("stop_reason")
    state = "paused" if pause.exists() else "stopped" if result["report"].get("stop_reason") or host_stop else "complete"
    _write_json(DATA / "progress.json", {"stage": "inventory", "state": state,
        "message": f'Inventory {state}: {inventory["summary"]["property_count"]} catalogue properties; '
                   f'{inventory["summary"]["calendar_property_count"]} with observed calendars.'})
    return {"state": state, "snapshot_id": inventory["snapshot_id"], "summary": inventory["summary"]}
