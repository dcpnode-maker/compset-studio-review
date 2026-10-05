"""Saved price reads must preserve unknowns and cannot become collection commands."""
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from compset.server import Handler


class SavedPriceServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)
        self.patch = patch("compset.server.DATA", self.data)
        self.patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.patch.stop()
        self.temp.cleanup()

    def request(self, path, method="GET", headers=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_missing_and_partial_saved_files_are_not_successful_empty_results(self):
        status, _, body = self.request("/api/one-night")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)["state"], "not_collected")
        saved = self.data / "one-night-latest.json"
        for malformed in [b'{"records":', b'[]', b'\xff']:
            saved.write_bytes(malformed)
            status, _, body = self.request("/api/one-night")
            self.assertEqual(status, 503)
            self.assertEqual(json.loads(body)["state"], "read_error")

    def test_exact_evidence_and_unknown_values_survive_api_and_export(self):
        report = {"state": "stopped", "quoted_date_cells": 1, "unknown_date_cells": 29,
                  "context": {"adults": 1, "currency": "AED"},
                  "records": [{"status": "quoted", "quotes": [{"amount": "650.40",
                    "amount_kind": "one_night_stay_total", "taxes_included": None,
                    "fees_included": None, "rate_options": [{"rate_plan": "Refundable"}]}]}]}
        raw = json.dumps(report).encode()
        (self.data / "one-night-latest.json").write_bytes(raw)
        csv = b"listing_id,status,amount\r\n123,quoted,650.40\r\n123,unknown,\r\n"
        (self.data / "one-night-prices.csv").write_bytes(csv)
        for path in ["/api/one-night", "/exports/one-night.json"]:
            status, headers, body = self.request(path)
            self.assertEqual(status, 200)
            self.assertEqual(body, raw)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            self.assertNotIn("Access-Control-Allow-Origin", headers)
        status, headers, body = self.request("/exports/one-night-prices.csv")
        self.assertEqual(status, 200)
        self.assertEqual(body, csv)
        self.assertTrue(headers["Content-Type"].startswith("text/csv"))

    def test_hotel_unknown_is_readable_without_invented_rate(self):
        hotel = self.data / "hotels" / "aketa"
        hotel.mkdir(parents=True)
        report = {"state": "stopped", "context": {"adults": 1, "rooms": 1, "currency": "INR"},
                  "rates": [], "dates": [{"checkin": "2026-09-28", "state": "unknown", "reason": "source_error"}],
                  "summary": {"quoted_dates": 0, "unavailable_dates": 0, "unknown_dates": 30}}
        (hotel / "latest.json").write_text(json.dumps(report), encoding="utf-8")
        (hotel / "rates.csv").write_text("checkin,amount\n", encoding="utf-8")
        for path in ["/api/hotels/aketa", "/exports/hotel-aketa.json"]:
            status, _, body = self.request(path)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), report)
        self.assertEqual(self.request("/exports/hotel-aketa-rates.csv")[0], 200)

    def test_fixed_paths_host_origin_and_read_only_guards(self):
        (self.data / "one-night-latest.json").write_text("{}", encoding="utf-8")
        self.assertEqual(self.request("/api/one-night", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.request("/api/one-night", headers={"Origin": "https://evil.example"})[0], 403)
        origin = f"http://127.0.0.1:{self.server.server_port}"
        self.assertEqual(self.request("/api/one-night", headers={"Origin": origin})[0], 200)
        for path in ["/exports/../one-night-latest.json", "/exports/hotel-aketa-rates.csv/../latest.json", "/api/hotels/other", "/exports/%2e%2e/one-night-latest.json"]:
            self.assertEqual(self.request(path)[0], 404)
        with patch("compset.server.collect_job") as collect:
            headers = {"Origin": origin, "X-CompSet-Request": "dashboard-v1", "Content-Type": "application/json"}
            self.assertEqual(self.request("/api/one-night", "POST", headers)[0], 404)
            self.assertEqual(self.request("/api/hotels/aketa", "POST", headers)[0], 404)
            collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
