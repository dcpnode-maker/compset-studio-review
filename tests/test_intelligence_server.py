"""Bounded read route proof using isolated HTTP servers and no collectors."""
import http.client
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from compset import server


class IntelligenceServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data_patch = patch.object(server, 'DATA', self.root)
        self.data_patch.start()
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.worker = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.worker.join()
        self.data_patch.stop()
        self.tmp.cleanup()

    def get(self, path, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.http.server_port, timeout=5)
        connection.request('GET', path, headers=headers or {})
        result = connection.getresponse()
        body = result.read()
        response = (result.status, dict(result.getheaders()), body)
        connection.close()
        return response

    def test_reads_do_not_collect_or_accept_foreign_origin(self):
        with patch.object(server, 'collect_job') as collect, patch.object(server.subprocess, 'run') as run:
            status, headers, body = self.get('/api/intelligence')
            self.assertEqual(status, 200)
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertEqual(json.loads(body)['str']['properties'], [])
            self.assertEqual(self.get('/api/intelligence', {'Origin': 'https://outside.example'})[0], 403)
            self.assertEqual(self.get('/api/intelligence', {'Host': 'outside.example'})[0], 403)
            collect.assert_not_called()
            run.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_query_constraints_and_studio_zero(self):
        for query in ['days=32', 'limit=26', 'offset=-1', 'limit=1.5', 'bedrooms=true', 'namespace=bogus', 'start=2026-10-02', 'file=private.json', 'limit=1&limit=2']:
            with self.subTest(query=query):
                self.assertEqual(self.get('/api/intelligence/str/calendar?start=2026-10-01&' + query)[0], 400)
        status, _, body = self.get('/api/intelligence/str/calendar?start=2026-10-01&bedrooms=0&namespace=all&days=1&limit=1')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['request']['bedrooms'], 0)
        self.assertIsNone(json.loads(body)['request']['namespace'])
        self.assertEqual(self.get('/api/intelligence/str/calendar')[0], 400)
        self.assertEqual(self.get('/api/intelligence/str/compset?limit=101')[0], 400)
        self.assertEqual(self.get('/api/intelligence/hotel?refresh=true')[0], 400)
        self.assertEqual(self.get('/api/intelligence/unknown')[0], 404)

    def test_revision_changes_without_cached_stale_headers(self):
        path = self.root / 'portfolio-latest.json'
        path.write_text(json.dumps({'properties': [{'property_id': '1', 'title': 'Before', 'city': 'Dubai'}]}), encoding='utf-8')
        first = json.loads(self.get('/api/intelligence')[2])
        path.write_text(json.dumps({'properties': [{'property_id': '1', 'title': 'After change', 'city': 'Dubai'}]}), encoding='utf-8')
        second = json.loads(self.get('/api/intelligence')[2])
        self.assertNotEqual(first['revision'], second['revision'])
        self.assertEqual(second['str']['properties'][0]['title'], 'After change')


if __name__ == '__main__':
    unittest.main()
