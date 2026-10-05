"""Independent orchestration proof; all source reads use temporary fixtures."""
from contextlib import closing, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from compset import __main__ as cli
from compset import nightly
from compset import workflows
from compset.pipeline import build_result, context_from, persist
from tests.test_nightly import CalendarSession, bootstrap, setup_snapshot


class NightlyReviewTests(unittest.TestCase):
    def setUp(self):
        CalendarSession.calls = 0
        CalendarSession.status = 200
        CalendarSession.unknown = False

    def collect(self, root, **values):
        with patch("compset.collect.collect", side_effect=bootstrap), \
             patch("scrapling.fetchers.FetcherSession", CalendarSession), \
             patch("compset.nightly.time.sleep"):
            return nightly.collect_selected(data_dir=root, **values)

    def assert_zero_budget_pending(self, root):
        with patch("compset.collect.collect") as collect:
            result = nightly.collect_selected(data_dir=root, request_budget=0)
        collect.assert_not_called()
        self.assertEqual(result["state"], "budget_reached")
        self.assertEqual(result["records"], [])
        self.assertEqual(result["direct_requests_this_run"], 0)
        return result

    def test_strict_party_and_window_scalars_and_explicit_historical_defaults(self):
        for values in ({"adults": True}, {"adults": 1.0}, {"days": 30.0}, {"children": False},
                       {"infants": 0.0}, {"pets": "0"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                nightly.window_context(values)
        current = context_from({})
        historical = context_from({"adults": 2, "days": 90})
        self.assertEqual(current["adults"], 1)
        self.assertEqual((datetime.fromisoformat(current["end_date"]) - datetime.fromisoformat(current["start_date"])).days, 30)
        self.assertEqual(historical["adults"], 2)
        self.assertEqual((datetime.fromisoformat(historical["end_date"]) - datetime.fromisoformat(historical["start_date"])).days, 90)

    def test_malformed_checkpoint_shapes_do_not_start_http(self):
        for value in ([], {"records": []}, "broken JSON"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                setup_snapshot(root, 1)
                path = root / "nightly-monitoring-latest.json"
                path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
                self.assert_zero_budget_pending(root)

    def test_numeric_selected_ids_resume_once_and_duplicate_checkpoint_records_deduplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            setup_snapshot(root, 1)
            path = root / "compset-latest.json"
            snapshot = json.loads(path.read_text())
            snapshot["selected"][0]["listing_id"] = 9000
            snapshot["selected"].append({"listing_id": "9000"})
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            first = self.collect(root, request_budget=1)
            self.assertEqual(first["state"], "complete")
            self.assertEqual(CalendarSession.calls, 1)
            checkpoint = root / "nightly-monitoring-latest.json"
            data = json.loads(checkpoint.read_text())
            data["records"].append(data["records"][0].copy())
            checkpoint.write_text(json.dumps(data), encoding="utf-8")
            with patch("compset.collect.collect") as no_bootstrap:
                cached = nightly.collect_selected(data_dir=root)
            no_bootstrap.assert_not_called()
            self.assertEqual(cached["state"], "complete")
            self.assertEqual((cached["total"], cached["processed"]), (1, 1))
            self.assertEqual(cached["records"][0]["listing_id"], "9000")

    def test_absent_stale_or_incomplete_artifact_cannot_be_reused_as_fresh(self):
        for mutation in ("missing", "stale", "rows_missing", "wrong_run"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                setup_snapshot(root, 1)
                first = self.collect(root, request_budget=1)
                self.assertEqual(first["state"], "complete")
                with patch("compset.collect.collect") as no_bootstrap:
                    positive = nightly.collect_selected(data_dir=root, request_budget=0)
                no_bootstrap.assert_not_called()
                self.assertEqual(positive["state"], "complete")
                record = first["records"][0]
                path = root / "nightly" / record["run_id"] / "nightly.json"
                artifact = json.loads(path.read_text())
                if mutation == "missing":
                    path.unlink()
                else:
                    if mutation == "stale":
                        artifact["context"]["observed_at"] = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
                    elif mutation == "rows_missing":
                        artifact.pop("rows")
                    else:
                        artifact["run_id"] = "0" * 24
                    path.write_text(json.dumps(artifact), encoding="utf-8")
                self.assert_zero_budget_pending(root)

    def test_checkpoint_selected_membership_stale_age_and_parser_hash_are_checked(self):
        for mutation in ("wrong_id", "old_timestamp", "parser"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                setup_snapshot(root, 1)
                self.collect(root, request_budget=1)
                path = root / "nightly-monitoring-latest.json"
                data = json.loads(path.read_text())
                if mutation == "wrong_id":
                    data["records"][0]["listing_id"] = "9999"
                elif mutation == "old_timestamp":
                    data["records"][0]["observed_at"] = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
                path.write_text(json.dumps(data), encoding="utf-8")
                if mutation == "parser":
                    fixture_root = root / "parser"
                    (fixture_root / "compset").mkdir(parents=True)
                    for filename in ("nightly_rows.py", "normalize.py"):
                        (fixture_root / "compset" / filename).write_bytes((nightly.ROOT / "compset" / filename).read_bytes() + b"\n# different revision\n")
                    with patch("compset.nightly.ROOT", fixture_root):
                        self.assert_zero_budget_pending(root)
                else:
                    self.assert_zero_budget_pending(root)

    def test_cached_coverage_cannot_claim_prices_missing_from_saved_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            setup_snapshot(root, 1)
            first = self.collect(root, request_budget=1)
            path = root / "nightly" / first["records"][0]["run_id"] / "nightly.json"
            artifact = json.loads(path.read_text())
            self.assertTrue(all(row["nightly_amount_for_requested_party"] is None for row in artifact["rows"]))
            artifact["coverage"]["verified_nightly_price_days"] = 30
            path.write_text(json.dumps(artifact), encoding="utf-8")
            with patch("compset.collect.collect") as collect:
                result = nightly.collect_selected(data_dir=root, request_budget=0)
            collect.assert_not_called()
            self.assertEqual(result["verified_nightly_price_rows"], 0)
            self.assertFalse(result["requested_party_prices_complete"])

    def test_pause_during_spacing_wait_prevents_next_http_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            setup_snapshot(root, 3)
            flag = root / "pause-nightly.flag"
            def pause_after_first_read(*args):
                flag.touch()
            with patch("compset.collect.collect", side_effect=bootstrap), \
                 patch("scrapling.fetchers.FetcherSession", CalendarSession), \
                 patch("compset.nightly.time.sleep", side_effect=pause_after_first_read):
                result = nightly.collect_selected(data_dir=root)
            self.assertEqual(result["state"], "paused")
            self.assertEqual(CalendarSession.calls, 1)
            self.assertEqual(result["direct_requests_this_run"], 1)
            self.assertTrue(flag.exists())

    def test_http500_and_graphql_error_stop_at_first_competitor(self):
        class ErrorSession(CalendarSession):
            mode = "graphql"
            calls = 0
            def get(self, url, **kwargs):
                type(self).calls += 1
                body = {"errors": [{"message": "public failure"}], "data": None} if self.mode == "graphql" else {}
                return type("Response", (), {"status": 200 if self.mode == "graphql" else 500,
                    "body": json.dumps(body).encode()})()
        for mode in ("graphql", "http500"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                setup_snapshot(root, 3)
                ErrorSession.mode, ErrorSession.calls = mode, 0
                with patch("compset.collect.collect", side_effect=bootstrap), \
                     patch("scrapling.fetchers.FetcherSession", ErrorSession):
                    result = nightly.collect_selected(data_dir=root)
                self.assertEqual(result["state"], "stopped")
                self.assertEqual(ErrorSession.calls, 1)
                self.assertEqual(result["records"][0]["collection_status"], "incomplete")
                self.assertFalse(result["requested_party_prices_complete"])

    def test_one_adult_collection_appends_sqlite_without_replacing_two_adult_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            setup_snapshot(root, 1)
            previous_context = context_from({"adults": 2, "days": 30})
            capture = {"payloads": [], "report": {}}
            previous = build_result(capture, previous_context)
            persist(capture, previous, root)
            original_latest = (root / "latest.json").read_bytes()
            self.collect(root, request_budget=1)
            self.assertEqual((root / "latest.json").read_bytes(), original_latest)
            with closing(sqlite3.connect(root / "compset.sqlite3")) as database:
                old = json.loads(database.execute("SELECT result_json FROM runs WHERE run_id=?", (previous["run_id"],)).fetchone()[0])
                self.assertEqual(old, previous)
                self.assertEqual(old["context"]["adults"], 2)
                self.assertEqual(database.execute("SELECT count(*) FROM observations WHERE run_id=?", (previous["run_id"],)).fetchone()[0], 31)
                self.assertEqual(database.execute("SELECT count(*) FROM observations WHERE kind='nightly_context'").fetchone()[0], 60)
                self.assertEqual(database.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_verified_returned_nightly_prices_are_counted_by_actual_builder_contract(self):
        def replay(templates, target, session, **kwargs):
            start = datetime.fromisoformat(target["start_date"])
            days = [{"calendarDate": (start + timedelta(days=index)).date().isoformat(),
                     "available": True, "price": {"localPriceFormatted": "AED 100"}} for index in range(30)]
            envelope = {"status": 200, "source_url": templates[0]["url"], "request_context": dict(target),
                        "body": {"data": {"merlin": {"pdpAvailabilityCalendar": {"calendarMonths": [{
                            "listingId": target["listing_id"], "days": days}]}}}}}
            return {"requests": [{"status": 200, "json_captured": True, "graphql_errors": False}],
                    "payloads": [envelope], "stop_reason": None}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            setup_snapshot(root, 1)
            with patch("compset.collect.collect", side_effect=bootstrap), \
                 patch("compset.collect.replay_observed", side_effect=replay), \
                 patch("scrapling.fetchers.FetcherSession", CalendarSession):
                result = nightly.collect_selected(data_dir=root, request_budget=1)
            self.assertEqual(result["verified_nightly_price_rows"], 30)
            self.assertTrue(result["requested_party_prices_complete"])
            artifact = json.loads((root / "nightly" / result["records"][0]["run_id"] / "nightly.json").read_text())
            self.assertTrue(all(row["nightly_amount_for_requested_party"] == "100" for row in artifact["rows"]))

    def test_cli_defaults_and_forwarding_do_not_relabel_explicit_party(self):
        returned = {"run_id": "proof", "coverage": {}, "report": {}, "warnings": []}
        for args, expected in ((["compset", "run"], 1), (["compset", "run", "--adults", "2"], 2)):
            with self.subTest(args=args), patch("sys.argv", args), patch("compset.__main__.run", return_value=returned) as run, redirect_stdout(io.StringIO()):
                cli.main()
            self.assertEqual(run.call_args.args[0]["adults"], expected)
        with patch("sys.argv", ["compset", "nightly-monitor", "--request-budget", "0"]), \
             patch("compset.nightly.collect_selected", return_value={"state": "budget_reached"}) as collect, \
             redirect_stdout(io.StringIO()):
            cli.main()
        self.assertEqual(collect.call_args.kwargs["request_budget"], 0)
        self.assertEqual(collect.call_args.kwargs["interval_seconds"], 3.0)


class WorkflowExpansionReviewTests(unittest.TestCase):
    subject = {"listing_id": "123", "title": "Subject", "detail_status": "observed",
               "latitude": 0, "longitude": 0, "room_type": "Entire home/apt",
               "bedrooms": 1, "bathrooms": 1, "person_capacity": 2}

    def exercise(self, root, driver, discovery, detail):
        with patch("compset.workflows.DATA", root), \
             patch("compset.workflows.listing_detail", side_effect=detail), \
             patch("compset.discovery.discover", side_effect=discovery) as reads, \
             patch("compset.adaptive.run_adaptive_comparison", side_effect=driver), \
             patch("compset.workflows.time.sleep"):
            result = workflows.discover_compset({"listing": "123", "budget": 6},
                discovery_result={"candidates": [], "report": {"total_search_requests": 0}})
        return result, reads

    def test_callback_search_budget_is_total_and_never_restarts_after_exhaustion(self):
        reports = []
        def driver(subject, rows, criteria, **kwargs):
            for radius in (4, 8, 10):
                reports.append(kwargs["discovery_callback"](subject, {**criteria, "radius_km": radius})["report"])
            return {"candidates": [], "selected": [], "summary": {}}
        def discovery(subject, context, **kwargs):
            return {"candidates": [], "report": {"total_search_requests": 3}}
        with tempfile.TemporaryDirectory() as directory:
            _, reads = self.exercise(Path(directory), driver, discovery, lambda *args: dict(self.subject))
        self.assertEqual([call.args[1]["budget"] for call in reads.call_args_list], [6, 3])
        self.assertEqual(reports[-1]["stop_reason"], "request_budget_reached")

    def test_new_detail_budget_is_total_across_radius_transitions(self):
        detail_calls, expanded = [], []
        def driver(subject, rows, criteria, **kwargs):
            audit = []
            for radius in (4, 8):
                response = kwargs["discovery_callback"](subject, {**criteria, "radius_km": radius})
                audit.extend(response["candidates"])
                expanded.append(response["report"])
            return {"candidates": audit, "selected": [], "summary": {}}
        def discovery(subject, context, **kwargs):
            offset = 10000 if context["radius_km"] == 4 else 20000
            return {"candidates": [{"listing_id": str(offset + index), "bedrooms": 2} for index in range(201)],
                    "report": {"total_search_requests": 1}}
        def detail(identifier, context, stop=None):
            if identifier == "123":
                return dict(self.subject)
            detail_calls.append(identifier)
            return {**self.subject, "listing_id": identifier, "bedrooms": 2}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result, _ = self.exercise(root, driver, discovery, detail)
            progress = json.loads((root / "progress.json").read_text())
        self.assertEqual(len(detail_calls), 200)
        self.assertEqual(expanded[0]["new_detail_read_budget_remaining"], 0)
        self.assertEqual(expanded[1]["new_detail_read_budget_remaining"], 0)
        self.assertEqual(progress["processed"], len(result["candidates"]))
        self.assertIn("from 402 candidates", progress["message"])

    def test_enrichment_access_limit_prevents_later_detail_and_search_reads(self):
        detail_calls, reports = [], []
        def driver(subject, rows, criteria, **kwargs):
            for radius in (4, 8):
                reports.append(kwargs["discovery_callback"](subject, {**criteria, "radius_km": radius})["report"])
            return {"candidates": [], "selected": [], "summary": {}}
        def detail(identifier, context, stop=None):
            if identifier == "123":
                return dict(self.subject)
            detail_calls.append(identifier)
            stop.set()
            return {"listing_id": identifier, "detail_status": "access_limit_403"}
        def discovery(*args, **kwargs):
            return {"candidates": [{"listing_id": "9000"}, {"listing_id": "9001"}],
                    "report": {"total_search_requests": 1}}
        with tempfile.TemporaryDirectory() as directory:
            result, reads = self.exercise(Path(directory), driver, discovery, detail)
        self.assertEqual(detail_calls, ["9000"])
        self.assertEqual(reads.call_count, 1)
        self.assertEqual(reports[0]["stop_reason"], "enrichment_access_limit")
        self.assertEqual(reports[1]["stop_reason"], "access_limit")
        self.assertTrue(result["summary"]["enrichment_access_limit"])


if __name__ == "__main__":
    unittest.main()
