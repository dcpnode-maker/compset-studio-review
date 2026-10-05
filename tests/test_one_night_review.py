"""Independent orchestration proofs; all source/network work uses local fixtures."""
from contextlib import closing
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import csv
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from compset.one_night import collect_one_night, plan_quotes
from compset.pipeline import build_result, persist
from tests.test_one_night_job import quote_bootstrap, setup_sources
from tests.test_one_night_rows import fixture


def replay_quote(templates, context, session, *, limit):
    assert limit == 1
    assert len(templates) == 1
    payload = fixture(request={**context, "locale": "en-IN", "method": "POST"})
    return {"payloads": [payload], "requests": [{"status": 200, "json_captured": True}], "stop_reason": None}


class OneNightReviewTests(unittest.TestCase):
    def source_file(self, root, identifier="101"):
        snapshot = json.loads((root / "nightly-monitoring-latest.json").read_text())
        record = next(r for r in snapshot["records"] if r["listing_id"] == identifier)
        return root / "runs" / record["run_id"] / "source.json"

    def test_malformed_checkpoint_shapes_are_ignored_without_network(self):
        for value in (None, [], {"records": None}, {"records": [None]}):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                setup_sources(root)
                (root / "one-night-latest.json").write_text(json.dumps(value))
                with patch("compset.collect.collect") as browser:
                    result = collect_one_night(data_dir=root, request_budget=0)
                browser.assert_not_called()
                self.assertEqual(result["unknown_date_cells"], 1)
                self.assertEqual(result["calendar_skipped_date_cells"], 59)

    def test_malformed_raw_source_is_unknown_and_never_skips(self):
        for alteration in (None, [], {"context": None}, "null_payload", "mapping_payload"):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                setup_sources(root)
                path = self.source_file(root)
                raw = json.loads(path.read_text())
                if alteration == "null_payload":
                    raw["payloads"] = [None]
                elif alteration == "mapping_payload":
                    raw["payloads"] = {}
                else:
                    raw = alteration
                path.write_text(json.dumps(raw))
                _, _, rows = plan_quotes(root)
                subject = [r for r in rows if r["context"]["listing_id"] == "101"]
                self.assertEqual(len(subject), 30)
                self.assertTrue(all(r["preflight"]["decision"] == "proceed_quote" for r in subject))
                self.assertTrue(all(r["calendar_run_id"] is None for r in subject))

    def test_corrupt_optional_latest_does_not_erase_valid_calendar_proof(self):
        for contents in ("null", "[]", "{", '{"context": null}'):
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                setup_sources(root)
                (root / "latest.json").write_text(contents)
                _, _, rows = plan_quotes(root)
                self.assertEqual(len(rows), 60)
                self.assertEqual(rows[0]["preflight"]["decision"], "proceed_quote")
                self.assertEqual(rows[1]["preflight"]["reason"], "sleeping_night_unavailable")

    def test_malformed_locale_is_unknown_and_cannot_skip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            setup_sources(root)
            path = self.source_file(root)
            raw = json.loads(path.read_text())
            raw["payloads"][0]["request_context"]["locale"] = {"unexpected": 1}
            path.write_text(json.dumps(raw))
            _, _, rows = plan_quotes(root)
            subject = [r for r in rows if r["context"]["listing_id"] == "101"]
            self.assertEqual(len(subject), 30)
            self.assertTrue(all(r["preflight"]["decision"] == "proceed_quote" for r in subject))
            self.assertTrue(all(r["preflight"]["reason"] == "calendar_request_context_conflict" for r in subject))
            self.assertTrue(all(isinstance(r["context"]["locale"], str) for r in subject))

    def test_cache_rebuilds_plan_metadata_instead_of_trusting_cached_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            setup_sources(root)
            with patch("compset.collect.collect", side_effect=quote_bootstrap), patch("scrapling.fetchers.FetcherSession"):
                result = collect_one_night(data_dir=root)
            record = next(r for r in result["records"] if r["status"] == "quoted")
            del record["preflight"]
            record["calendar_run_id"] = "invented"
            record["quotes"][0]["amount"] = "999999.00"
            (root / "one-night-latest.json").write_text(json.dumps(result))
            with patch("compset.collect.collect") as browser:
                resumed = collect_one_night(data_dir=root, request_budget=0)
            browser.assert_not_called()
            restored = next(r for r in resumed["records"] if r["status"] == "quoted")
            self.assertEqual(restored["quotes"][0]["amount"], "377.04")
            self.assertEqual(restored["preflight"]["reason"], "no_proven_calendar_block")
            self.assertNotEqual(restored["calendar_run_id"], "invented")

    def test_missing_stale_or_wrong_party_quote_source_cannot_resume(self):
        for change in ("missing", "stale", "party"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                setup_sources(root)
                with patch("compset.collect.collect", side_effect=quote_bootstrap), patch("scrapling.fetchers.FetcherSession"):
                    result = collect_one_night(data_dir=root)
                quoted = next(r for r in result["records"] if r["status"] == "quoted")
                path = root / "runs" / quoted["run_id"] / "source.json"
                if change == "missing":
                    path.unlink()
                else:
                    raw = json.loads(path.read_text())
                    if change == "stale":
                        raw["context"]["observed_at"] = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
                    else:
                        raw["context"]["adults"] = 2
                    path.write_text(json.dumps(raw))
                with patch("compset.collect.collect") as browser:
                    resumed = collect_one_night(data_dir=root, request_budget=0)
                browser.assert_not_called()
                self.assertEqual(resumed["quoted_date_cells"], 0)
                self.assertEqual(resumed["unknown_date_cells"], 1)

    def test_changed_parser_signature_reparses_amount_without_any_browser(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            setup_sources(root)
            with patch("compset.collect.collect", side_effect=quote_bootstrap), patch("scrapling.fetchers.FetcherSession"):
                result = collect_one_night(data_dir=root)
            result["signature"] = "previous-parser-signature"
            record = next(r for r in result["records"] if r["status"] == "quoted")
            record["quotes"][0]["amount"] = "999999.00"
            (root / "one-night-latest.json").write_text(json.dumps(result))
            with patch("compset.collect.collect") as browser, patch("compset.collect.replay_observed") as replay:
                restored = collect_one_night(data_dir=root, request_budget=0)
            browser.assert_not_called()
            replay.assert_not_called()
            self.assertEqual(restored["quoted_date_cells"], 1)
            self.assertEqual(next(r for r in restored["records"] if r["status"] == "quoted")["quotes"][0]["amount"], "377.04")

    def test_unknown_saved_response_is_recovered_by_current_parser_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            setup_sources(root)
            with patch("compset.collect.collect", side_effect=quote_bootstrap), \
                    patch("compset.one_night_rows.extract_one_night_quotes", return_value=[]):
                old = collect_one_night(data_dir=root)
            self.assertEqual(old["quoted_date_cells"], 0)
            unknown = next(r for r in old["records"] if r["status"] == "unknown")
            raw_path = root / "runs" / unknown["run_id"] / "source.json"
            raw_bytes = raw_path.read_bytes()
            old["signature"] = "previous-unknown-parser-signature"
            (root / "one-night-latest.json").write_text(json.dumps(old))
            with patch("compset.collect.collect") as browser, patch("compset.collect.replay_observed") as replay:
                restored = collect_one_night(data_dir=root, request_budget=0)
            browser.assert_not_called()
            replay.assert_not_called()
            self.assertEqual(restored["quoted_date_cells"], 1)
            self.assertEqual(restored["unknown_date_cells"], 0)
            quote = next(r for r in restored["records"] if r["status"] == "quoted")
            self.assertEqual(quote["quotes"][0]["amount"], "377.04")
            self.assertEqual(raw_path.read_bytes(), raw_bytes)
            self.assertEqual(restored["direct_requests_this_run"], 0)

    def test_outside_plan_party_date_or_listing_cannot_erase_good_cache_or_enter_report(self):
        for field in ("adults", "date", "listing_id"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                setup_sources(root)
                with patch("compset.collect.collect", side_effect=quote_bootstrap), patch("scrapling.fetchers.FetcherSession"):
                    result = collect_one_night(data_dir=root)
                original = next(r for r in result["records"] if r["status"] == "quoted")
                outsider = deepcopy(original)
                outsider["run_id"] = "a" * 24
                target = deepcopy(outsider["context"])
                if field == "date":
                    arrival = date.fromisoformat(target["checkin"]) + timedelta(days=45)
                    target.update(checkin=str(arrival), checkout=str(arrival + timedelta(days=1)))
                else:
                    target[field] = 2 if field == "adults" else "999"
                outsider["context"] = target
                folder_path = root / "runs" / outsider["run_id"]
                folder_path.mkdir()
                (folder_path / "source.json").write_text(json.dumps({"context": target,
                    "payloads": [fixture(request={**target, "locale": "en-IN"})], "report": {}}))
                result["signature"] = "different-parser-signature"
                result["records"].append(outsider)
                (root / "one-night-latest.json").write_text(json.dumps(result))
                with patch("compset.collect.collect") as browser:
                    restored = collect_one_night(data_dir=root, request_budget=0)
                browser.assert_not_called()
                self.assertEqual(restored["quoted_date_cells"], 1)
                quoted = [r for r in restored["records"] if r["status"] == "quoted"]
                self.assertEqual(len(quoted), 1)
                self.assertEqual(quoted[0]["context"]["adults"], 1)
                self.assertEqual(quoted[0]["context"]["listing_id"], "101")
                self.assertEqual(quoted[0]["context"]["checkin"], original["context"]["checkin"])

    def test_recovered_quote_appends_to_database_without_overwriting_unknown_history(self):
        self._assert_recovered_quote_history("one_night_rows.py")

    def test_shared_money_parser_revision_gets_distinct_database_evidence(self):
        self._assert_recovered_quote_history("normalize.py")

    def _assert_recovered_quote_history(self, revised_dependency):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            setup_sources(root)
            from compset.one_night import ROOT
            old_parser_root = root / "old-parser"
            (old_parser_root / "compset").mkdir(parents=True)
            for name in ("one_night.py", "one_night_rows.py", "normalize.py", "collect.py", "availability.py", "batch.py"):
                code = (ROOT / "compset" / name).read_bytes()
                (old_parser_root / "compset" / name).write_bytes(code + (b"\n# Previous parser revision fixture\n" if name == revised_dependency else b""))
            def old_parser(payloads, context):
                return [{**context, "status": "unknown", "amount": None,
                         "amount_kind": "one_night_stay_total", "reason": "previous_price_schema_gap"}]
            with patch("compset.collect.collect", side_effect=quote_bootstrap), \
                    patch("compset.one_night_rows.extract_one_night_quotes", side_effect=old_parser), \
                    patch("compset.one_night.ROOT", old_parser_root):
                old = collect_one_night(data_dir=root)
            record = next(r for r in old["records"] if r["status"] == "unknown")
            source_path = root / "runs" / record["run_id"] / "source.json"
            source_bytes = source_path.read_bytes()
            latest_bytes = (root / "latest.json").read_bytes()
            with closing(sqlite3.connect(root / "compset.sqlite3")) as db:
                old_row = db.execute("SELECT record_json FROM observations WHERE run_id=? AND kind='one_night_quote' AND ordinal=0", (record["run_id"],)).fetchone()[0]
                old_run = db.execute("SELECT result_json FROM runs WHERE run_id=?", (record["run_id"],)).fetchone()[0]
            with patch("compset.collect.collect") as browser, patch("compset.collect.replay_observed") as replay:
                recovered = collect_one_night(data_dir=root, request_budget=0)
            browser.assert_not_called()
            replay.assert_not_called()
            self.assertEqual(recovered["quoted_date_cells"], 1)
            with closing(sqlite3.connect(root / "compset.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT record_json FROM observations WHERE run_id=? AND kind='one_night_quote' AND ordinal=0", (record["run_id"],)).fetchone()[0], old_row)
                self.assertEqual(db.execute("SELECT result_json FROM runs WHERE run_id=?", (record["run_id"],)).fetchone()[0], old_run)
                rows = [json.loads(value) for value, in db.execute("SELECT record_json FROM observations WHERE kind LIKE 'one_night_quote%'")]
                quoted = [value for value in rows if value.get("status") == "quoted"]
                self.assertEqual(len(quoted), 1)
                self.assertEqual(quoted[0]["amount"], "377.04")
                self.assertEqual(quoted[0]["price_parser_sha256"], recovered["price_parser_sha256"])
                self.assertNotEqual(recovered["price_parser_sha256"], old["price_parser_sha256"])
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(source_path.read_bytes(), source_bytes)
            self.assertEqual((root / "latest.json").read_bytes(), latest_bytes)
            with patch("compset.collect.collect") as browser:
                again = collect_one_night(data_dir=root, request_budget=0)
            browser.assert_not_called()
            self.assertEqual(again["quoted_date_cells"], 1)
            with closing(sqlite3.connect(root / "compset.sqlite3")) as db:
                values = [json.loads(value) for value, in db.execute("SELECT record_json FROM observations WHERE kind LIKE 'one_night_quote%'")]
            self.assertEqual(sum(value.get("status") == "quoted" for value in values), 1)

    def test_direct_budget_is_finite_and_complete_csv_keeps_unrequested_dates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            setup_sources(root, stale=True)
            calls = []
            def observed(templates, context, session, *, limit):
                calls.append((context["checkin"], context["checkout"], context["adults"]))
                return replay_quote(templates, context, session, limit=limit)
            with patch("compset.collect.collect", side_effect=quote_bootstrap), patch("scrapling.fetchers.FetcherSession"), \
                    patch("compset.collect.replay_observed", side_effect=observed), patch("compset.one_night.time.sleep") as sleep, \
                    patch("compset.one_night.time.monotonic", return_value=0):
                result = collect_one_night(data_dir=root, request_budget=2, interval_seconds=0)
            self.assertEqual(len(calls), 2)
            self.assertEqual(result["direct_requests_this_run"], 2)
            self.assertEqual(result["bootstrap_browser_visits"], 1)
            self.assertEqual(result["quoted_date_cells"], 3)
            self.assertEqual(result["state"], "budget_reached")
            self.assertEqual(result["interval_seconds"], 3.0)
            for arrival, departure, adults in calls:
                self.assertEqual((date.fromisoformat(departure) - date.fromisoformat(arrival)).days, 1)
                self.assertEqual(adults, 1)
            self.assertEqual(sleep.call_count, 2)
            self.assertTrue(all(call.args[0] == 3 for call in sleep.call_args_list))
            with (root / "one-night-prices.csv").open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 60)
            self.assertEqual(sum(r["status"] == "not_requested" for r in rows), 57)
            self.assertTrue(all(r["amount"] == "" for r in rows if r["status"] == "not_requested"))

    def test_pause_during_spacing_prevents_next_direct_read(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            setup_sources(root, stale=True)
            def pause(_):
                (root / "pause-one-night.flag").write_text("pause")
            with patch("compset.collect.collect", side_effect=quote_bootstrap), patch("scrapling.fetchers.FetcherSession"), \
                    patch("compset.collect.replay_observed") as replay, patch("compset.one_night.time.sleep", side_effect=pause):
                result = collect_one_night(data_dir=root, request_budget=2)
            replay.assert_not_called()
            self.assertEqual(result["state"], "paused")
            self.assertEqual(result["direct_requests_this_run"], 0)
            self.assertTrue((root / "pause-one-night.flag").exists())

    def test_failure_and_quote_gap_stop_before_another_direct_read(self):
        for reason, status in (("access_or_rate_limit_403", 403), ("access_or_rate_limit_429", 429),
                               ("direct_request_error", None), (None, 500), (None, 200)):
            with self.subTest(reason=reason, status=status), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                setup_sources(root, stale=True)
                failure = {"payloads": [], "requests": [{"status": status}], "stop_reason": reason}
                with patch("compset.collect.collect", side_effect=quote_bootstrap), patch("scrapling.fetchers.FetcherSession"), \
                        patch("compset.collect.replay_observed", return_value=failure) as replay, patch("compset.one_night.time.sleep"):
                    result = collect_one_night(data_dir=root, request_budget=4)
                replay.assert_called_once()
                self.assertEqual(result["state"], "stopped")
                self.assertEqual(result["direct_requests_this_run"], 1)
                self.assertEqual(result["quoted_date_cells"], 1)
                self.assertEqual(result["records"][-1]["status"], "unknown")
                self.assertEqual(result["records"][-1]["quotes"], [])

    def test_exact_quotes_append_without_overwriting_historical_database_or_latest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            context = setup_sources(root, stale=True)
            historical = {**context, "adults": 2}
            capture = {"payloads": [], "report": {"historical": True}}
            old = build_result(capture, historical)
            persist(capture, old, root, update_latest=False)
            latest = (root / "latest.json").read_bytes()
            with closing(sqlite3.connect(root / "compset.sqlite3")) as db:
                saved = db.execute("SELECT result_json FROM runs WHERE run_id=?", (old["run_id"],)).fetchone()[0]
                observations = db.execute("SELECT kind,ordinal,record_json FROM observations WHERE run_id=? ORDER BY kind,ordinal", (old["run_id"],)).fetchall()
            with patch("compset.collect.collect", side_effect=quote_bootstrap), patch("scrapling.fetchers.FetcherSession"), \
                    patch("compset.collect.replay_observed", side_effect=replay_quote), patch("compset.one_night.time.sleep"):
                result = collect_one_night(data_dir=root, request_budget=1)
            self.assertEqual(result["quoted_date_cells"], 2)
            self.assertEqual((root / "latest.json").read_bytes(), latest)
            with closing(sqlite3.connect(root / "compset.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT result_json FROM runs WHERE run_id=?", (old["run_id"],)).fetchone()[0], saved)
                self.assertEqual(db.execute("SELECT kind,ordinal,record_json FROM observations WHERE run_id=? ORDER BY kind,ordinal", (old["run_id"],)).fetchall(), observations)
                self.assertEqual(db.execute("SELECT count(*) FROM observations WHERE kind='one_night_quote'").fetchone()[0], 2)
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_cli_forwards_zero_budget_and_reports_one_night_cells(self):
        from compset.__main__ import main
        with patch("sys.argv", ["compset", "one-night-monitor", "--request-budget", "0"]), \
                patch("compset.one_night.collect_one_night", return_value={"state": "budget_reached", "total_date_cells": 60}) as collect, \
                patch("sys.stdout", new_callable=io.StringIO) as output:
            main()
        collect.assert_called_once_with(request_budget=0, interval_seconds=3.0)
        self.assertEqual(json.loads(output.getvalue())["total_date_cells"], 60)


if __name__ == "__main__":
    unittest.main()
