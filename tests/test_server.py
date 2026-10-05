import json
import threading
import tempfile
from pathlib import Path
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from compset.server import Handler, STATE


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.data_directory = tempfile.TemporaryDirectory()
        self.data_patch = patch("compset.server.DATA", Path(self.data_directory.name))
        self.data_patch.start()
        STATE.clear()
        STATE.update(state="idle", message="Test")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.data_patch.stop()
        self.data_directory.cleanup()

    def request(self, method, path, headers=None, data=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request(method, path, body=json.dumps(data or {}), headers=headers or {})
        response = connection.getresponse()
        status = response.status
        response.read()
        connection.close()
        return status

    def test_cross_origin_and_rebinding_are_rejected(self):
        self.assertEqual(self.request("GET", "/api/status", {"Host": "evil.example"}), 403)
        self.assertEqual(self.request("POST", "/api/run", {"Origin": "https://evil.example", "X-CompSet-Request": "dashboard-v1"}), 403)
        self.assertEqual(self.request("POST", "/api/run", {}), 403)
        self.assertEqual(self.request("GET", "/../.venv/pyvenv.cfg"), 404)

    def test_run_validates_before_worker_and_only_one_runs(self):
        headers = {"Content-Type": "application/json", "X-CompSet-Request": "dashboard-v1"}
        with patch("compset.server.collect_job") as job:
            self.assertEqual(self.request("POST", "/api/run", headers, {"listing": "https://localhost/rooms/123"}), 400)
            job.assert_not_called()
            self.assertEqual(self.request("POST", "/api/run", headers, {"listing": "123"}), 202)
            self.assertEqual(self.request("POST", "/api/run", headers, {"listing": "123"}), 409)

    def test_inventory_controls_validate_and_pause_without_deleting_evidence(self):
        headers = {"Content-Type": "application/json", "X-CompSet-Request": "dashboard-v1"}
        with tempfile.TemporaryDirectory() as directory, patch("compset.server.DATA", Path(directory)), patch("compset.server.collect_job"):
            saved = Path(directory) / "portfolio-latest.json"
            saved.write_text('{"properties": []}', encoding="utf-8")
            self.assertEqual(self.request("POST", "/api/inventory-refresh", headers, {"adults": True}), 400)
            self.assertEqual(self.request("POST", "/api/inventory-refresh", headers, {"adults": 2}), 202)
            self.assertEqual(self.request("POST", "/api/inventory-refresh", headers), 409)
            self.assertEqual(self.request("POST", "/api/inventory-pause", headers), 202)
            self.assertTrue((Path(directory) / "pause-inventory.flag").exists())
            self.assertEqual(saved.read_text(encoding="utf-8"), '{"properties": []}')
