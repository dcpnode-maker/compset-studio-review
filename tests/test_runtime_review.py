"""Independent runtime regressions; no external requests or real checkpoints."""
import copy
import hashlib
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from compset.health import observe_contracts
from compset.pipeline import _write_json
from compset.refresh import refresh_inventory
from compset.server import Handler, STATE, portfolio_response
from compset import workflows


class RuntimeReviewTests(unittest.TestCase):
    inventory = {"snapshot_id": "proof", "summary": {"property_count": 1, "calendar_property_count": 0}}

    def refresh_sources(self, root):
        (root / "bnbme-catalog-source.json").write_text('{"properties": []}', encoding="utf-8")

    def test_pause_accepted_after_start_survives_worker_entry_and_duplicate_start(self):
        old_state = dict(STATE)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.refresh_sources(root)
            flag = root / "pause-inventory.flag"
            flag.write_text("previous job", encoding="utf-8")
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            STATE.clear()
            STATE.update(state="idle", message="Review")
            def request(path):
                connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                connection.request("POST", path, body="{}", headers={
                    "Content-Type": "application/json", "X-CompSet-Request": "dashboard-v1"})
                response = connection.getresponse()
                status = response.status
                response.read()
                connection.close()
                return status
            try:
                with patch("compset.server.DATA", root), patch("compset.server.collect_job"):
                    self.assertEqual(request("/api/inventory-refresh"), 202)
                    self.assertFalse(flag.exists())
                    self.assertEqual(request("/api/inventory-pause"), 202)
                    self.assertTrue(flag.exists())
                    self.assertEqual(request("/api/inventory-refresh"), 409)
                    self.assertTrue(flag.exists())
                observed_flags = []
                def collector(*args, **kwargs):
                    observed_flags.append(flag.exists())
                    return {"report": {"stop_reason": "manual_pause"}}
                with patch("compset.refresh.DATA", root), \
                     patch("compset.portfolio.collect_catalog_details", side_effect=collector), \
                     patch("compset.inventory.import_inventory", return_value=self.inventory), \
                     patch("compset.host_inventory.collect_host_inventory") as host:
                    result = refresh_inventory({})
                self.assertEqual(observed_flags, [True])
                self.assertEqual(result["state"], "paused")
                self.assertTrue(flag.exists())
                host.assert_not_called()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                STATE.clear()
                STATE.update(old_state)

    def test_host_access_stop_propagates_while_evidence_is_imported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.refresh_sources(root)
            (root / "laya-public-listings.json").write_text("{}", encoding="utf-8")
            with patch("compset.refresh.DATA", root), \
                 patch("compset.portfolio.collect_catalog_details", return_value={"report": {"stop_reason": None}}), \
                 patch("compset.host_inventory.collect_host_inventory", return_value={"report": {
                     "state": "stopped", "stop_reason": "access_or_rate_limit"}}), \
                 patch("compset.inventory.import_inventory", return_value=self.inventory) as importer:
                result = refresh_inventory({})
            self.assertEqual(result["state"], "stopped")
            importer.assert_called_once()
            self.assertEqual(json.loads((root / "progress.json").read_text())["state"], "stopped")

    def test_invalid_diagnostic_baseline_shapes_do_not_discard_response(self):
        envelope = {"source_url": "https://api.bnbmehomes.com/api/v1/payments/get-charges-breakup",
                    "status": 200, "body": {"message": "SOLD_OUT"}}
        original = copy.deepcopy(envelope)
        invalid = ([], {"contracts": []}, {"contracts": {
            "api.bnbmehomes.com/get-charges-breakup/sold_out": "invalid entry"}})
        for baseline in invalid:
            with self.subTest(baseline=baseline), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "schema-health.json").write_text(json.dumps(baseline), encoding="utf-8")
                result = observe_contracts([envelope], [], root)
                self.assertEqual(result["state"], "attention_required")
                self.assertTrue(result["semantic_alerts"])
                self.assertIn("api.bnbmehomes.com/get-charges-breakup/sold_out", result["contracts"])
                self.assertFalse(result["automatic_semantic_repair"])
                self.assertEqual(envelope, original)

    def cache_files(self, root, stamp):
        directory = root / "cache" / "listings"
        directory.mkdir(parents=True)
        raw = directory / "123-AED.json"
        raw.write_text(json.dumps({"observed_at": stamp, "payloads": []}), encoding="utf-8")
        parsed = directory / "123-AED.parsed.json"
        wrapper = {"parser_sha256": hashlib.sha256((workflows.ROOT / "compset" / "normalize.py").read_bytes()).hexdigest(),
                   "source_mtime_ns": raw.stat().st_mtime_ns}
        return raw, parsed, wrapper

    def test_new_file_mtime_cannot_make_old_or_invalid_observation_fresh(self):
        for stamp in ("2020-01-01T00:00:00+00:00", "broken", None,
                      (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()):
            with self.subTest(stamp=stamp), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                raw, parsed, wrapper = self.cache_files(root, stamp)
                parsed.write_text(json.dumps({**wrapper, "listing": {
                    "listing_id": "123", "title": "Old cache", "details_observed_at": stamp}}), encoding="utf-8")
                stop = threading.Event()
                with patch("compset.workflows.DATA", root), patch("scrapling.fetchers.Fetcher.get") as fetch:
                    fetch.return_value.status = 429
                    result = workflows.listing_detail("123", {"currency": "AED", "adults": 2}, stop)
                fetch.assert_called_once()
                self.assertEqual(result["detail_status"], "access_limit_429")
                self.assertTrue(stop.is_set())

    def test_invalid_parsed_cache_falls_back_to_fresh_raw_without_network(self):
        stamp = datetime.now(timezone.utc).isoformat()
        for invalid in ("missing", None, [], {"listing_id": "999", "details_observed_at": stamp}, "bad_json"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                raw, parsed, wrapper = self.cache_files(root, stamp)
                if invalid == "bad_json":
                    parsed.write_text("broken JSON", encoding="utf-8")
                else:
                    value = wrapper if invalid == "missing" else {**wrapper, "listing": invalid}
                    parsed.write_text(json.dumps(value), encoding="utf-8")
                with patch("compset.workflows.DATA", root), \
                     patch("compset.normalize.normalize", return_value={"listing": {"listing_id": "123", "title": "Raw evidence"}}) as parser, \
                     patch("scrapling.fetchers.Fetcher.get") as fetch:
                    result = workflows.listing_detail("123", {"currency": "AED", "adults": 2})
                fetch.assert_not_called()
                parser.assert_called_once()
                self.assertEqual(result["title"], "Raw evidence")
                self.assertEqual(result["details_observed_at"], stamp)

    def test_projection_keeps_public_fields_and_invalidates_by_file_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio.json"
            full = {"snapshot_id": "one", "properties": [{"attributes": {"public": "kept"},
                "detail_attributes": {"public": "kept"}, "calendar": [1], "detail_observations": [2],
                "profile": {"large": [3]}, "quotes": [{"total_amount": "2288", "currency": "AED"}]}]}
            _write_json(path, full)
            revision = path.stat().st_mtime_ns
            projected = json.loads(portfolio_response(str(path), revision))
            self.assertEqual(json.loads(path.read_text()), full)
            row = projected["properties"][0]
            for key in ("quotes", "attributes", "detail_attributes"):
                self.assertEqual(row[key], full["properties"][0][key])
            self.assertNotIn("calendar", row)
            self.assertNotIn("profile", row)
            full["snapshot_id"] = "two"
            _write_json(path, full)
            os.utime(path, ns=(revision + 1_000_000_000, revision + 1_000_000_000))
            self.assertNotEqual(path.stat().st_mtime_ns, revision)
            self.assertEqual(json.loads(portfolio_response(str(path), path.stat().st_mtime_ns))["snapshot_id"], "two")

    def test_atomic_writer_retries_without_partial_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            _write_json(path, {"value": "old"})
            real_replace = Path.replace
            attempts = []
            def replace(source, destination):
                attempts.append(source)
                if len(attempts) < 3:
                    self.assertEqual(json.loads(path.read_text()), {"value": "old"})
                    raise PermissionError("simulated read lock")
                return real_replace(source, destination)
            with patch("pathlib.Path.replace", replace):
                _write_json(path, {"value": "new"})
            self.assertEqual(len(attempts), 3)
            self.assertEqual(json.loads(path.read_text()), {"value": "new"})

    def test_discovery_uses_subject_location_and_requested_guest_floor(self):
        subject = {"listing_id": "123", "title": "London subject", "detail_status": "observed",
                   "latitude": 51.5, "longitude": -0.1}
        with tempfile.TemporaryDirectory() as directory, \
             patch("compset.workflows.DATA", Path(directory)), \
             patch("compset.workflows.listing_detail", return_value=subject), \
             patch("compset.discovery.discover", return_value={"candidates": [], "report": {}}) as discovery, \
             patch("compset.adaptive.rank_candidates", return_value={"candidates": [], "selected": [], "summary": {
                 "candidate_count": 0, "eligible_count": 0, "excluded_count": 0,
                 "provisional_count": 0, "selected_count": 0, "circle": {}}}) as rank:
            result = workflows.discover_compset({"listing": "123", "adults": 4})
        context = discovery.call_args.args[1]
        self.assertEqual((context["center_lat"], context["center_lng"]), (51.5, -0.1))
        self.assertEqual(rank.call_args.args[2]["min_guest_capacity"], 4)
        self.assertEqual(result["criteria"]["min_guest_capacity"], 4)


if __name__ == "__main__":
    unittest.main()
