from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from compset.one_night import plan_quotes, collect_one_night
from compset.pipeline import build_result, context_from, persist
from tests.test_one_night_rows import fixture


def quote_bootstrap(context, headless=True, template_sink=None):
    body = {"operationName": "StaysPdpSections", "extensions": {}, "variables": {
        "id": context["listing_id"], "pdpSectionsRequest": {key: context[key] for key in
            ("adults", "children", "infants", "pets")},
        "dateRange": {"startDate": context["checkin"], "endDate": context["checkout"]}}}
    url = "https://www.airbnb.co.in/api/v3/StaysPdpSections/" + "a" * 64 + "?" + urlencode({"currency": "AED", "locale": "en-IN"})
    template_sink.append({"method": "POST", "url": url, "body": body, "headers": {}})
    payload = fixture(request={**context, "locale": "en-IN", "method": "POST"})
    payload["source_url"] = url.split("?")[0]
    return {"payloads": [payload], "report": {"browser_navigations": 1, "stop_reason": None}}


def setup_sources(root, *, stale=False):
    context = context_from({"listing": "101"})
    if stale:
        context["observed_at"] = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    records = []
    start = date.fromisoformat(context["start_date"])
    for identifier in ("101", "102"):
        target = {**context, "listing_id": identifier}
        days = [{"calendarDate": str(start + timedelta(days=i)), "available": i == 0,
                 "availableForCheckin": True, "availableForCheckout": True,
                 "minNights": 1 if identifier == "101" else 3, "maxNights": 365}
                for i in range(31)]
        payload = {"source_url": "https://www.airbnb.co.in/api/v3/PdpAvailabilityCalendar/hash",
                   "status": 200, "request_context": {"listing_id": identifier, "currency": "AED", "locale": "en-IN",
                       "calendar_year": start.year, "calendar_month": start.month, "calendar_month_count": 2},
                   "body": {"data": {"merlin": {"pdpAvailabilityCalendar": {"calendarMonths": [
                       {"listingId": identifier, "days": days}]}}}}}
        capture = {"payloads": [payload], "report": {}}
        result = build_result(capture, target)
        persist(capture, result, root, update_latest=identifier == "101")
        records.append({"listing_id": identifier, "run_id": result["run_id"]})
    (root / "compset-latest.json").write_text(json.dumps({"run_id": "audit", "context": context,
        "selected": [{"listing_id": "102"}]}), encoding="utf-8")
    (root / "nightly-monitoring-latest.json").write_text(json.dumps({"context": context, "records": records}), encoding="utf-8")
    return context


class OneNightJobTests(unittest.TestCase):
    def test_plan_uses_departure_permission_not_departure_overnight(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            setup_sources(root)
            _, _, plan = plan_quotes(root)
            self.assertEqual(len(plan), 60)
            self.assertEqual(plan[0]["preflight"]["decision"], "proceed_quote")
            self.assertEqual(plan[1]["preflight"]["reason"], "sleeping_night_unavailable")
            self.assertEqual(plan[30]["preflight"]["reason"], "minimum_stay_not_met")
            self.assertEqual(plan[0]["context"]["locale"], "en-IN")
            self.assertTrue(plan[30]["preflight"]["evidence"])

    def test_stale_calendar_cannot_skip_any_quote(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            setup_sources(root, stale=True)
            _, _, plan = plan_quotes(root)
            self.assertTrue(all(row["preflight"]["decision"] == "proceed_quote" for row in plan))
            self.assertTrue(all(row["calendar_run_id"] is None for row in plan))

    def test_zero_budget_retains_full_grid_and_never_bootstraps(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            setup_sources(root)
            with patch("compset.collect.collect") as browser:
                result = collect_one_night(data_dir=root, request_budget=0)
                browser.assert_not_called()
            self.assertEqual(result["state"], "budget_reached")
            self.assertEqual(result["calendar_skipped_date_cells"], 59)
            self.assertEqual(result["unknown_date_cells"], 1)
            with (root / "one-night-prices.csv").open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 60)
            self.assertEqual(sum(row["status"] == "not_requested" for row in rows), 1)

    def test_access_denial_stops_and_keeps_amount_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            setup_sources(root)
            capture = {"payloads": [], "report": {"browser_navigations": 1, "stop_reason": "access_or_rate_limit_403"}}
            with patch("compset.collect.collect", return_value=capture) as browser, patch("scrapling.fetchers.FetcherSession") as session:
                result = collect_one_night(data_dir=root)
                browser.assert_called_once()
                session.assert_not_called()
            self.assertEqual(result["state"], "stopped")
            self.assertEqual(result["stop_reason"], "access_or_rate_limit_403")
            self.assertEqual(result["quoted_date_cells"], 0)
            self.assertEqual(result["unknown_date_cells"], 1)
            self.assertEqual(result["records"][-1]["quotes"], [])

    def test_resume_reparses_source_and_does_not_trust_checkpoint_amount(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            setup_sources(root)
            with patch("compset.collect.collect", side_effect=quote_bootstrap), patch("scrapling.fetchers.FetcherSession"):
                result = collect_one_night(data_dir=root)
            self.assertEqual(result["state"], "complete")
            self.assertEqual(result["quoted_date_cells"], 1)
            self.assertEqual(result["unknown_date_cells"], 0)
            quoted = next(r for r in result["records"] if r["status"] == "quoted")
            quoted["quotes"][0]["amount"] = "999999.00"
            (root / "one-night-latest.json").write_text(json.dumps(result), encoding="utf-8")
            with patch("compset.collect.collect") as browser:
                cached = collect_one_night(data_dir=root)
                browser.assert_not_called()
            self.assertEqual(next(r for r in cached["records"] if r["status"] == "quoted")["quotes"][0]["amount"], "377.04")
            self.assertEqual(cached["direct_requests_this_run"], 0)
            import sqlite3
            with closing(sqlite3.connect(root / "compset.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM observations WHERE kind='one_night_quote'").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
