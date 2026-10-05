from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from compset.nightly import collect_selected, export_source, window_context
from compset.pipeline import context_from


def setup_snapshot(directory, count=2):
    context = context_from({})
    snapshot = {"run_id": "subject-audit", "context": context, "subject": {"listing_id": context["listing_id"]},
                "selected": [{"listing_id": str(9000+i), "title": f"Apartment {i}"} for i in range(count)]}
    (Path(directory)/"compset-latest.json").write_text(json.dumps(snapshot), encoding="utf-8")
    return context


def bootstrap(context, headless=True, template_sink=None):
    start = datetime.fromisoformat(context["start_date"])
    variables = {"request": {"listingId": context["listing_id"], "month": start.month, "year": start.year, "count": 2}}
    query = urlencode({"variables": json.dumps(variables), "currency": context["currency"], "locale": context["locale"]})
    template_sink.append({"url": "https://www.airbnb.com/api/v3/PdpAvailabilityCalendar/hash?"+query,
                          "method": "GET", "headers": {}})
    return {"payloads": [], "report": {"browser_navigations": 1, "stop_reason": None}}


class CalendarSession:
    calls = 0
    status = 200
    unknown = False
    def __init__(self, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def get(self, url, **kwargs):
        from compset.collect import request_context
        type(self).calls += 1
        context = window_context({})
        actual = request_context(url)
        start = datetime.fromisoformat(context["start_date"])
        days = [{"calendarDate": (start+timedelta(days=i)).date().isoformat(),
                 "available": None if self.unknown else i % 3 != 0,
                 "price": {"localPriceFormatted": None}} for i in range(30)]
        body = {"data": {"merlin": {"pdpAvailabilityCalendar": {"calendarMonths": [
            {"listingId": actual["listing_id"], "days": days}]}}}}
        return type("Response", (), {"status": self.status, "body": json.dumps(body).encode()})()


class NightlyJobTests(unittest.TestCase):
    def setUp(self):
        CalendarSession.calls=0
        CalendarSession.status=200
        CalendarSession.unknown=False

    def test_context_starts_on_dubai_day_and_defaults_one_adult_thirty_days(self):
        now = datetime.now(timezone.utc).replace(hour=21, minute=30)
        expected = (now+timedelta(hours=4)).date()
        context = window_context(now=now)
        self.assertEqual(context["start_date"], str(expected))
        self.assertEqual(context["end_date"], str(expected+timedelta(days=30)))
        self.assertEqual(context["adults"],1)
        for bad in ({"adults":2},{"children":1},{"days":31},{"start_date":"2000-01-01"}):
            with self.assertRaises(ValueError): window_context(bad)

    def test_export_rejects_two_adults_before_persisting(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"source.json"
            path.write_text(json.dumps({"context":context_from({"adults":2}),"payloads":[],"report":{}}),encoding="utf-8")
            with self.assertRaises(ValueError): export_source(path,data_dir=Path(directory))
            self.assertFalse((Path(directory)/"compset.sqlite3").exists())

    def test_budget_pause_and_cache_prevent_unnecessary_http(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);setup_snapshot(root)
            with patch("compset.collect.collect",side_effect=bootstrap), patch("scrapling.fetchers.FetcherSession",CalendarSession), patch("compset.nightly.time.sleep"):
                first=collect_selected(data_dir=root,request_budget=1)
                self.assertEqual(first["state"],"budget_reached")
                self.assertEqual(CalendarSession.calls,1)
                self.assertFalse(first["requested_party_prices_complete"])
                resumed=collect_selected(data_dir=root,request_budget=1)
                self.assertEqual(resumed["state"],"complete")
                self.assertEqual(CalendarSession.calls,2)
                self.assertEqual(resumed["verified_nightly_price_rows"],0)
                with patch("compset.collect.collect") as no_bootstrap:
                    cached=collect_selected(data_dir=root)
                    no_bootstrap.assert_not_called()
                    self.assertEqual(cached["direct_requests_this_run"],0)
            with closing(sqlite3.connect(root/"compset.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM observations WHERE kind='nightly_context'").fetchone()[0],120)
            (root/"pause-nightly.flag").touch()
            with patch("compset.collect.collect") as no_bootstrap:
                paused=collect_selected(data_dir=root)
                self.assertEqual(paused["state"],"paused")
                no_bootstrap.assert_not_called()

    def test_access_or_unknown_schema_stops_without_next_listing_or_rotation(self):
        for status,unknown in ((403,False),(429,False),(200,True)):
            with self.subTest(status=status,unknown=unknown), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);setup_snapshot(root,3)
                CalendarSession.calls=0;CalendarSession.status=status;CalendarSession.unknown=unknown
                with patch("compset.collect.collect",side_effect=bootstrap), patch("scrapling.fetchers.FetcherSession",CalendarSession):
                    result=collect_selected(data_dir=root)
                self.assertEqual(result["state"],"stopped")
                self.assertEqual(CalendarSession.calls,1)
                self.assertEqual(len(result["records"]),1)
                self.assertEqual(result["records"][0]["collection_status"],"incomplete")

    def test_zero_budget_does_not_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);setup_snapshot(root)
            with patch("compset.collect.collect") as no_bootstrap:
                report=collect_selected(data_dir=root,request_budget=0)
                self.assertEqual(report["state"],"budget_reached")
                no_bootstrap.assert_not_called()


if __name__ == "__main__": unittest.main()
