import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from compset.batch import _merge_listing, monitor_compset, retarget_template
from compset.collect import request_context
from tests.test_collect import context, template


def quote_template():
    variables = {"id": base64.b64encode(b"DemandStayListing:123456").decode(),
                 "dateRange": {"startDate": "2026-10-12", "endDate": "2026-10-15"},
                 "guestCounts": {"numberOfAdults": 2},
                 "priceHeatmapDateRange": {"startDate": "2026-09-28", "endDate": "2026-12-27"},
                 "flags": {"someObservedFlag": True}, "hostId": "123456"}
    return {"url": "https://www.airbnb.com/api/v3/StaysPdpBookItQuery/current-hash?" + urlencode({
        "variables": json.dumps(variables), "currency": "AED", "locale": "en-IN",
        "extensions": json.dumps({"persistedQuery": {"sha256Hash": "current-hash"}})}),
        "method": "GET", "headers": {"x-airbnb-api-key": "IN-MEMORY-SECRET"}}


def setup_snapshot(directory, count=3):
    snapshot = {"run_id": "compset-test", "context": context(observed_at=datetime.now(timezone.utc).isoformat()),
                "criteria": {}, "subject": {"listing_id": "123456", "title": "Subject"},
                "selected": [{"listing_id": str(9000 + n), "title": f"Competitor {n}"} for n in range(count)]}
    (directory / "compset-latest.json").write_text(json.dumps(snapshot), encoding="utf-8")
    return snapshot


def fake_bootstrap(ctx, **kwargs):
    kwargs["template_sink"].extend([template(), quote_template()])
    return {"payloads": [], "report": {"stop_reason": None}}


class FakeSession:
    calls = []
    block = False
    lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, **kwargs):
        with self.lock:
            self.calls.append((url, kwargs))
        ctx = request_context(url)
        if self.block:
            return type("Response", (), {"status": 429, "body": b""})()
        if "Calendar" in url:
            body = {"data": {"merlin": {"pdpAvailabilityCalendar": {"calendarMonths": [{
                "listingId": ctx["listing_id"], "days": [{"calendarDate": "2026-10-12", "available": True}]}]}}}}
        else:
            body = {"data": {"node": {"pdpPresentation": {"bookIt": {"productItemDetail": {
                "__typename": "OptionalityPriceDetail", "selectedGuestOptionId": "51", "guestOptions": [{
                "__typename": "GuestOption", "guestOptionId": "51", "isSelected": True,
                "priceString": "AED 300.15 total", "title": "Non-refundable"}]}}}}}}
        return type("Response", (), {"status": 200, "body": json.dumps(body).encode()})()


class BatchTests(unittest.TestCase):
    def setUp(self):
        FakeSession.calls = []
        FakeSession.block = False

    def test_cached_details_keep_provenance_and_null_does_not_erase(self):
        previous = {"title": "Known", "host_listing_count": 12, "field_sources": {"title": {"source_path": "$.title"}}}
        combined = _merge_listing(previous, {"host_listing_count": None, "field_sources": {}})
        self.assertEqual(combined["host_listing_count"], 12)
        self.assertEqual(combined["field_sources"], previous["field_sources"])

    def test_selection_is_deduplicated_subject_excluded_and_capped(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            snapshot = setup_snapshot(directory, 120)
            snapshot["selected"].insert(0, {"listing_id": "123456"})
            snapshot["selected"].insert(1, {"listing_id": "9000"})
            (directory / "compset-latest.json").write_text(json.dumps(snapshot), encoding="utf-8")
            with patch("compset.batch.collect", return_value={"payloads": [], "report": {"stop_reason": "access_or_rate_limit_403"}}):
                result = monitor_compset(data_dir=directory)
            self.assertEqual(result["total"], 100)
            self.assertEqual(result["processed"], 0)

    def test_retarget_preserves_hash_id_types_flags_and_unrelated_identifiers(self):
        original = quote_template()
        changed = retarget_template(original, "123456", context(listing_id="987654", checkin="2026-10-17", checkout="2026-10-20"))
        variables = json.loads(parse_qs(urlsplit(changed["url"]).query)["variables"][0])
        self.assertEqual(base64.b64decode(variables["id"]).decode(), "DemandStayListing:987654")
        self.assertEqual(variables["hostId"], "123456")
        self.assertTrue(variables["flags"]["someObservedFlag"])
        self.assertEqual(variables["dateRange"], {"startDate": "2026-10-17", "endDate": "2026-10-20"})
        self.assertEqual(variables["priceHeatmapDateRange"]["startDate"], "2026-09-28")
        self.assertIn("/current-hash?", changed["url"])
        self.assertEqual(request_context(changed["url"])["listing_id"], "987654")
        changed["headers"]["x-airbnb-api-key"] = "changed"
        self.assertEqual(original["headers"]["x-airbnb-api-key"], "IN-MEMORY-SECRET")

    def test_retarget_refuses_wrong_subject_or_unknown_operation(self):
        with self.assertRaises(ValueError):
            retarget_template(quote_template(), "wrong", context(listing_id="987654"))
        bad = quote_template()
        bad["method"] = "POST"
        with self.assertRaises(ValueError):
            retarget_template(bad, "123456", context(listing_id="987654"))

    def test_bulk_single_bootstrap_public_context_persistence_and_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            setup_snapshot(directory)
            with patch("compset.batch.collect", side_effect=fake_bootstrap) as bootstrap, patch("compset.batch._session_factory", FakeSession):
                result = monitor_compset(data_dir=directory)
            self.assertEqual(bootstrap.call_count, 1)
            self.assertEqual((result["processed"], result["total"], result["state"]), (3, 3, "complete"))
            self.assertEqual(len(FakeSession.calls), 6)
            self.assertTrue(all(call[1]["timeout"] == 20 for call in FakeSession.calls))
            self.assertEqual({request_context(url)["listing_id"] for url, _ in FakeSession.calls}, {"9000", "9001", "9002"})
            latest = json.loads((directory / "latest.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["context"]["listing_id"], "123456")
            self.assertTrue(all(row["selected_quote"]["total_amount"] == "300.15" for row in result["records"]))
            for file in directory.rglob("*.json"):
                self.assertNotIn("IN-MEMORY-SECRET", file.read_text(encoding="utf-8"))
                self.assertNotIn("variables=", file.read_text(encoding="utf-8"))
            with patch("compset.batch.collect") as bootstrap:
                resumed = monitor_compset(data_dir=directory)
                bootstrap.assert_not_called()
            self.assertEqual(resumed["processed"], 3)

    def test_rate_limit_stops_further_submission_and_retains_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            setup_snapshot(directory, 10)
            FakeSession.block = True
            with patch("compset.batch.collect", side_effect=fake_bootstrap), patch("compset.batch._session_factory", FakeSession):
                result = monitor_compset(data_dir=directory)
            self.assertEqual(result["state"], "stopped")
            self.assertLessEqual(len(FakeSession.calls), 2)
            self.assertLessEqual(result["processed"], 2)
            self.assertEqual(result["total"], 10)
            self.assertTrue((directory / "monitoring-latest.json").exists())

    def test_missing_templates_does_not_start_competitor_requests(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            setup_snapshot(directory)
            with patch("compset.batch.collect", return_value={"payloads": [], "report": {}}), patch("compset.batch._session_factory") as session:
                result = monitor_compset(data_dir=directory)
                session.assert_not_called()
            self.assertEqual((result["state"], result["processed"]), ("stopped", 0))

    def test_changed_context_does_not_reuse_fresh_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            setup_snapshot(directory, 1)
            with patch("compset.batch.collect", side_effect=fake_bootstrap), patch("compset.batch._session_factory", FakeSession):
                monitor_compset(data_dir=directory)
            snapshot = json.loads((directory / "compset-latest.json").read_text(encoding="utf-8"))
            snapshot["context"].update(checkin="2026-10-17", checkout="2026-10-20")
            (directory / "compset-latest.json").write_text(json.dumps(snapshot), encoding="utf-8")
            with patch("compset.batch.collect", side_effect=fake_bootstrap) as bootstrap, patch("compset.batch._session_factory", FakeSession):
                result = monitor_compset(data_dir=directory)
            self.assertEqual(bootstrap.call_count, 1)
            self.assertEqual(result["records"][0]["selected_quote"]["checkin"], "2026-10-17")


if __name__ == "__main__":
    unittest.main()
