"""Independent root integration proof; projections are mocked at their boundary."""
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from compset import server


class RootRouteIndependentReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.replace = patch.object(server, 'DATA', self.root)
        self.replace.start()
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=2)
        self.replace.stop()
        self.tmp.cleanup()

    def get(self, path, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.http.server_port, timeout=4)
        connection.request('GET', path, headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_exact_typed_dispatch_preserves_namespace_and_candidate_identity(self):
        with patch('compset.intelligence.str_calendar', return_value={'ok': True}) as calendar:
            status, headers, body = self.get('/api/intelligence/str/calendar?start=2026-10-01&days=3&offset=25&limit=7&bedrooms=0&namespace=all&query=Park%20View&currency=GBP&city=London')
            self.assertEqual(status, 200)
            calendar.assert_called_once_with(self.root, start='2026-10-01', days=3, offset=25, limit=7,
                                             bedrooms=0, namespace=None, query='Park View', currency='GBP', city='London')
            self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        with patch('compset.intelligence.str_compset', return_value={'ok': True}) as compare:
            self.assertEqual(self.get('/api/intelligence/str/compset?subject_id=bnbme_direct%3A8&candidate_id=airbnb%3A9&decision=selected&offset=50&limit=1')[0], 200)
            compare.assert_called_once_with(self.root, subject_id='bnbme_direct:8', candidate_id='airbnb:9', decision='selected', offset=50, limit=1)

    def test_encoded_duplicate_fields_unknown_parameters_and_oversize_queries_stop_before_projection(self):
        invalid = ['/api/intelligence?read=all', '/api/intelligence/hotel?file=secret',
                   '/api/intelligence/str/calendar?start=2026-10-01&limit=1&%6cimit=2',
                   '/api/intelligence/str/calendar?start=2026-10-01&days=+1',
                   '/api/intelligence/str/calendar?start=2026-10-01&offset=1000000',
                   '/api/intelligence/str/calendar?start=2026-10-01&query=' + 'x' * 2050,
                   '/api/intelligence/str/calendar?' + '&'.join('x=1' for _ in range(17))]
        with (patch('compset.intelligence.str_calendar') as calendar, patch('compset.intelligence.summary') as summary,
              patch('compset.intelligence.hotel') as hotel):
            for url in invalid:
                with self.subTest(url=url[:100]):
                    self.assertEqual(self.get(url)[0], 400)
            calendar.assert_not_called()
            summary.assert_not_called()
            hotel.assert_not_called()

    def test_all_new_reads_reject_external_origin_before_any_projection_and_never_launch_collectors(self):
        urls = ['/api/intelligence', '/api/intelligence/str/calendar?start=2026-10-01',
                '/api/intelligence/str/compset?subject_id=airbnb%3A1', '/api/intelligence/hotel']
        with (patch.object(server, 'intelligence_response', return_value={'read': True}) as projection,
              patch.object(server, 'launch_workspace_job') as launch, patch.object(server, 'collect_job') as collect):
            for url in urls:
                self.assertEqual(self.get(url, {'Origin': 'https://unrelated.example'})[0], 403)
                self.assertEqual(self.get(url, {'Origin': 'null'})[0], 403)
                self.assertEqual(self.get(url, {'Host': '127.0.0.1.evil.example'})[0], 403)
            projection.assert_not_called()
            for url in urls:
                self.assertEqual(self.get(url, {'Origin': f'http://127.0.0.1:{self.http.server_port}'})[0], 200)
            self.assertEqual(projection.call_count, 4)
            launch.assert_not_called()
            collect.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_read_errors_are_generic_and_static_files_stay_allowlisted(self):
        with patch.object(server, 'intelligence_response', side_effect=OSError('credential-canary-private-file')):
            status, headers, body = self.get('/api/intelligence')
            self.assertEqual(status, 503)
            self.assertNotIn(b'credential-canary', body)
            self.assertEqual(json.loads(body)['state'], 'read_error')
        for asset in ('/dual-workspace.js', '/dual-workspace.css'):
            self.assertEqual(self.get(asset)[0], 200)
        for rejected in ('/compset/intelligence.py', '/../.venv/pyvenv.cfg', '/dual-workspace.js/../server.py', '/data/portfolio-latest.json'):
            self.assertEqual(self.get(rejected)[0], 404)


if __name__ == '__main__':
    unittest.main()
