import csv
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from compset.pipeline import build_result, context_from, export_csv, persist


class PipelineTests(unittest.TestCase):
    def test_validation_rejects_non_listing_and_bad_intervals(self):
        for listing in ("https://evil.example/rooms/123", "https://www.airbnb.com@evil.example/rooms/123", "abc", "https://www.airbnb.com/users/123"):
            with self.assertRaises(ValueError):
                context_from({"listing": listing})
        for args in ({"days": 0}, {"adults": 0}, {"days": True}, {"adults": 1.9}, {"days": "1.5"}, {"currency": "XXX"}, {"checkin": "2030-01-02", "checkout": "2030-01-01"}):
            with self.assertRaises(ValueError):
                context_from(args)

    def test_missing_calendar_stays_unknown_and_ingestion_is_idempotent(self):
        context = context_from({"days": 3})
        parsed = {"listing": {"title": "Source title"}, "calendar": [{"date": context["start_date"], "availability": "unavailable", "available": False, "price_amount": None}], "quotes": [], "warnings": []}
        with patch("compset.normalize.normalize", return_value=parsed):
            result = build_result({"payloads": [], "report": {}}, context)
        self.assertEqual(result["coverage"]["unavailable_days"], 1)
        self.assertEqual(result["coverage"]["unknown_days"], 2)
        self.assertIsNone(result["calendar"][1]["observed_at"])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            persist({"payloads": []}, result, target)
            persist({"payloads": []}, result, target)
            with closing(sqlite3.connect(target / "compset.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM runs").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT count(*) FROM observations").fetchone()[0], 4)
            self.assertEqual(json.loads((target / "latest.json").read_text())["run_id"], result["run_id"])

    def test_csv_spreadsheet_formula_is_inert(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.csv"
            export_csv(path, [{"title": "=WEBSERVICE(\"https://example.com\")", "amount": "123.45"}], [])
            with path.open(encoding="utf-8-sig", newline="") as stream:
                row = next(csv.DictReader(stream))
            self.assertTrue(row["title"].startswith("'="))
            self.assertEqual(row["amount"], "123.45")
