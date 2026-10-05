"""The saved calendar is a fixed loopback read path with exact-script CSP."""
import base64
import hashlib
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from compset.server import Handler, intelligence_response


class ProviderReceiptRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.batch = self.root / 'provider-receipts' / '20260930'
        self.batch.mkdir(parents=True)
        self.data_patch = patch('compset.server.DATA', self.root)
        self.data_patch.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.data_patch.stop()
        self.temp.cleanup()

    def get(self, path, headers=None):
        connection = HTTPConnection('127.0.0.1', self.server.server_port)
        connection.request('GET', path, headers=headers or {})
        response = connection.getresponse()
        value = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return value

    def test_html_csp_permits_only_exact_scripts_and_exports_original_bytes(self):
        code = b'console.log("fixture");'
        html = b'<script>' + code + b'</script>'
        (self.batch / 'aketa-compset-live-preview.html').write_bytes(html)
        status, headers, body = self.get('/aketa-calendar')
        self.assertEqual((status, body), (200, html))
        digest = base64.b64encode(hashlib.sha256(code).digest()).decode('ascii')
        script_policy = headers['Content-Security-Policy'].split(';')[1]
        self.assertIn("'sha256-" + digest + "'", script_policy)
        self.assertNotIn('unsafe-inline', script_policy)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(self.get('/aketa-calendar', {'Origin': 'https://example.com'})[0], 403)
        self.assertEqual(self.get('/aketa-calendar', {'Host': 'evil.example'})[0], 403)

    def test_missing_and_partial_reports_are_not_successful_empty_data(self):
        self.assertEqual(self.get('/exports/aketa-provider-receipts.json')[0], 404)
        saved = self.batch / 'aketa-provider-receipts.json'
        saved.write_text('{"incomplete":', encoding='utf-8')
        self.assertEqual(self.get('/exports/aketa-provider-receipts.json')[0], 503)
        saved.write_text('{"schema_version":"fixture"}', encoding='utf-8')
        self.assertEqual(json.loads(self.get('/exports/aketa-provider-receipts.json')[2]), {'schema_version': 'fixture'})
        self.assertEqual(self.get('/exports/../../secret.json')[0], 404)

    def test_projection_route_accepts_no_file_or_context_override(self):
        projection = {'schema_version': 'fixture', 'roster_count': 17}
        module = SimpleNamespace(load_provider_receipts=lambda root: projection)
        with patch.dict('sys.modules', {'compset.provider_receipts': module}):
            self.assertEqual(intelligence_response(self.root, '/api/intelligence/hotel/provider-receipts'), projection)
            for query in ('file=secret.json', 'hotel_id=other', 'adults=2', 'currency=USD'):
                with self.assertRaises(ValueError):
                    intelligence_response(self.root, '/api/intelligence/hotel/provider-receipts?' + query)


if __name__ == '__main__':
    unittest.main()
