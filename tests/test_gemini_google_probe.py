import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from compset.gemini_google_probe import BoundedFetcher, ProbeStopped


class FakeTransport:
    def __init__(self, status=200, body=b'[]'):
        self.status, self.body, self.calls = status, body, []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return SimpleNamespace(status=self.status, body=self.body, text='wrong element text')


class GeminiProbeTests(unittest.TestCase):
    def test_uses_raw_body_and_disables_hidden_retries_redirects(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = FakeTransport(body=b'[["2026-10-01",3600]]')
            fetcher = BoundedFetcher(tmp, transport, interval=0)
            response = fetcher.get('https://www.google.com/travel/hotels')
            self.assertEqual(response.text, '[["2026-10-01",3600]]')
            self.assertEqual(transport.calls[0][1]['retries'], 1)
            self.assertIs(transport.calls[0][1]['follow_redirects'], False)
            self.assertEqual(Path(fetcher.records[0]['body_artifact']).read_bytes(), transport.body)

    def test_rate_limit_stops_without_becoming_a_price_or_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = FakeTransport(status=429)
            fetcher = BoundedFetcher(tmp, transport, interval=0)
            with self.assertRaises(ProbeStopped):
                fetcher.get('https://www.google.com/travel/hotels')
            self.assertEqual(fetcher.stop_reason, 'access_or_rate_limit_429')
            self.assertEqual(len(transport.calls), 1)

    def test_budget_prevents_recursive_network_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = FakeTransport()
            fetcher = BoundedFetcher(tmp, transport, max_requests=1, interval=0)
            fetcher.get('https://www.google.com/travel/hotels')
            with self.assertRaises(ProbeStopped):
                fetcher.get('https://www.google.com/travel/hotels')
            self.assertEqual(len(transport.calls), 1)

    def test_challenge_stops_original_broad_exception_handler(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = FakeTransport(body=b'<h1>Our systems have detected unusual traffic</h1>')
            fetcher = BoundedFetcher(tmp, transport, interval=0)
            with self.assertRaises(ProbeStopped):
                fetcher.get('https://www.google.com/travel/hotels')
            self.assertEqual(fetcher.stop_reason, 'challenge_detected')

    def test_same_origin_redirects_count_against_budget(self):
        class RedirectTransport(FakeTransport):
            def get(self, url, **kwargs):
                result = super().get(url, **kwargs)
                result.status = 302
                result.headers = {'Location': '/travel/search?q=aketa'}
                return result
        with tempfile.TemporaryDirectory() as tmp:
            transport = RedirectTransport()
            fetcher = BoundedFetcher(tmp, transport, max_requests=2, interval=0)
            with self.assertRaises(ProbeStopped):
                fetcher.get('https://www.google.com/travel/hotels')
            self.assertEqual(len(transport.calls), 2)
            self.assertEqual(fetcher.stop_reason, 'request_budget_exhausted')


if __name__ == '__main__':
    unittest.main()
