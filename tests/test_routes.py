import asyncio
import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from routes.kaggle_fetch_validate import normalize_proxy, valid_origin, validate_one, run, read_bounded, operator_candidates, SOURCES, TEST_URL
from routes.pool import Pool, RouteUnavailable
from routes.proxy_server import ForwardProxy, public_destination, session_from_headers
from routes.airbnb_scraper import execute_observed, local_proxy_url


def manifest(*endpoints):
    return {"proxies": [{"endpoint": endpoint, "alive": True, "tls_verified": True,
            "protocol": "http_connect", "category": "residential", "validation_url": TEST_URL,
            "validated_at": datetime.now(timezone.utc).isoformat(), "latency_ms": 50,
            "origin": "8.8.8.8", "source_urls": [SOURCES[0]]} for endpoint in endpoints]}


class RoutePoolTests(unittest.TestCase):
    def setUp(self):
        self.pool = Pool(":memory:")

    def tearDown(self):
        self.pool.close()

    def test_normalization_rejects_private_reserved_multicast_garbage_and_credentials(self):
        for value in ("127.0.0.1:80", "10.0.0.1:8080", "169.254.169.254:80", "192.168.1.1:80",
                      "0.0.0.0:80", "224.0.0.1:80", "203.0.113.5:80", "8.8.8.8:0",
                      "8.8.8.8:65536", "999.1.1.1:80", "user:secret@8.8.8.8:80", "example.com:80",
                      "https://8.8.8.8:80", "8.8.8.8:80/path", "[::1]:80"):
            self.assertIsNone(normalize_proxy(value), value)
        self.assertEqual(normalize_proxy(" http://8.8.8.8:8080 "), "8.8.8.8:8080")
        self.assertTrue(valid_origin("8.8.8.8, 1.1.1.1"))
        self.assertFalse(valid_origin("8.8.8.8, 127.0.0.1"))

    def test_only_recent_verified_manifest_entries_import_and_category_stays_unknown(self):
        valid = manifest("8.8.8.8:8080")
        self.assertEqual(self.pool.import_manifest(valid), 1)
        self.assertEqual(self.pool.health()[0]["category"], "unknown")
        for change in ({"tls_verified": False}, {"protocol": "socks5"}, {"endpoint": "127.0.0.1:1"},
                       {"validated_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()},
                       {"validation_url": "http://httpbin.org/ip"}, {"origin": "private"}):
            item = manifest("1.1.1.1:8888")["proxies"][0]
            item.update(change)
            self.assertEqual(self.pool.import_manifest({"proxies": [item]}), 0)

    def test_sticky_failure_never_chooses_another_healthy_route(self):
        self.pool.import_manifest(manifest("8.8.8.8:8080", "1.1.1.1:8888"))
        route = self.pool.choose("same", "httpbin.org")
        for _ in range(3):
            self.assertEqual(self.pool.choose("same", "httpbin.org")["endpoint"], route["endpoint"])
            self.pool.transport_failure(route["endpoint"], "proxy_connect_transport_failure")
        with self.assertRaisesRegex(RouteUnavailable, "no_fallback"):
            self.pool.choose("same", "httpbin.org")
        self.assertNotEqual(self.pool.choose("explicit_new", "httpbin.org")["endpoint"], route["endpoint"])

    def test_target_block_does_not_damage_transport_health_and_requires_manual_reset(self):
        self.pool.import_manifest(manifest("8.8.8.8:8080"))
        route = self.pool.choose("same", "www.airbnb.com")
        self.pool.target_block("same", "www.airbnb.com", status=429, cooldown=60)
        self.assertEqual(self.pool.health()[0]["fail_count"], 0)
        with self.assertRaisesRegex(RouteUnavailable, "target_cooldown"):
            self.pool.choose("new", "www.airbnb.com")
        self.pool.db.execute("UPDATE target_cooldowns SET until_at=0")
        with self.assertRaisesRegex(RouteUnavailable, "manual_reset"):
            self.pool.choose("same", "www.airbnb.com")
        self.pool.reset_session("same")
        self.assertEqual(self.pool.choose("same", "www.airbnb.com")["endpoint"], route["endpoint"])

    def test_local_proxy_configuration_and_session_auth_are_strict(self):
        self.assertEqual(local_proxy_url("http://127.0.0.1:8080", "test-1"), "http://test-1:@127.0.0.1:8080")
        for url in ("http://0.0.0.0:8080", "http://example.com:8080", "http://secret@127.0.0.1:8080", "https://localhost:8080"):
            with self.assertRaises(ValueError):
                local_proxy_url(url, "test")
        header = "Basic " + base64.b64encode(b"abc:").decode()
        self.assertEqual(session_from_headers({"proxy-authorization": header}), "abc")
        with self.assertRaises(ValueError):
            session_from_headers({"proxy-authorization": "Basic " + base64.b64encode(b"abc:secret").decode()})

    def test_operator_provenance_is_explicit_and_does_not_accept_unknown_sources(self):
        item = manifest("8.8.8.8:8080")["proxies"][0]
        item.update(source_type="operator_supplied", source_urls=[],
                    source_file={"label": "operator-input", "sha256": "a" * 64, "bytes": 20})
        self.assertEqual(self.pool.import_manifest({"proxies": [item]}), 1)
        self.assertEqual(json.loads(self.pool.health()[0]["source_provenance"])["source_type"], "operator_supplied")
        for evidence in ({}, {"label": "operator-input", "sha256": "bad", "bytes": 20},
                         {"label": "other", "sha256": "a" * 64, "bytes": 20}):
            item["source_file"] = evidence
            self.assertEqual(self.pool.import_manifest({"proxies": [item]}), 0)

    def test_operator_file_filters_garbage_and_exports_digest_without_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sensitive-operator-name.txt"
            path.write_text("8.8.8.8:8080\n127.0.0.1:80\n8.8.8.8:8080\ninvalid\n", encoding="utf-8")
            candidates, provenance, count = operator_candidates(str(path))
            self.assertEqual(list(candidates), ["8.8.8.8:8080"])
            self.assertEqual(count, 4)
            self.assertNotIn(str(path), json.dumps(provenance))
            self.assertNotIn(path.name, json.dumps(provenance))
            self.assertEqual(len(provenance["source_file"]["sha256"]), 64)


class ProbeResponse:
    def __init__(self, status=200, body=b'{"origin":"8.8.8.8"}'):
        self.status, self.body, self.content = status, body, self
        self.position = 0
    async def read(self, size):
        data = self.body[self.position:self.position + size]
        self.position += len(data)
        return data
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass


class ProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_operator_run_has_no_source_fetch_and_same_verified_probe_budget(self):
        calls = []
        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            def get(self, url, **kwargs):
                calls.append((url, kwargs))
                return ProbeResponse()
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "private-name.txt", Path(directory) / "working.txt"
            source.write_text("8.8.8.8:8080\n1.1.1.1:8080\n9.9.9.9:8080\n", encoding="utf-8")
            with patch("aiohttp.ClientSession", return_value=Client()), patch("aiohttp.TCPConnector"), patch("builtins.print"):
                result = await run(input_file=str(source), output=str(output), max_candidates=2, concurrency=1)
            self.assertEqual(len(calls), 2)
            self.assertTrue(all(url == TEST_URL and kwargs["ssl"] for url, kwargs in calls))
            self.assertEqual(result["alive"], 2)
            self.assertNotIn(str(source), output.with_suffix(".json").read_text())
            pool = Pool(":memory:")
            try:
                self.assertEqual(pool.import_manifest(result), 2)
            finally:
                pool.close()

    async def test_partial_chunks_are_read_to_eof_with_a_hard_byte_cap(self):
        class Partial:
            chunks = iter([b"abc", b"def", b""])
            async def read(self, size):
                return next(self.chunks)
        self.assertEqual(await read_bounded(Partial(), 8), b"abcdef")
        with self.assertRaises(ValueError):
            await read_bounded(ProbeResponse(body=b"a" * 9), 8)

    async def test_verified_https_probe_records_public_provenance(self):
        calls = []
        class Client:
            def get(self, url, **kwargs):
                calls.append((url, kwargs))
                return ProbeResponse()
        result = await validate_one(Client(), "8.8.8.8:8080")
        self.assertTrue(result["alive"])
        self.assertTrue(result["tls_verified"])
        self.assertEqual(result["category"], "unknown")
        self.assertEqual(calls[0][0], "https://httpbin.org/ip")
        self.assertTrue(calls[0][1]["ssl"])
        self.assertFalse(calls[0][1]["allow_redirects"])

    async def test_probe_denial_has_no_alternate_or_status_retry(self):
        calls = []
        class Client:
            def get(self, url, **kwargs):
                calls.append(kwargs["proxy"])
                return ProbeResponse(status=429)
        result = await validate_one(Client(), "8.8.8.8:8080")
        self.assertFalse(result["alive"])
        self.assertEqual(calls, ["http://8.8.8.8:8080"])

    async def test_budgets_reject_before_any_network(self):
        for kwargs in ({"concurrency": 500}, {"max_candidates": 100000}, {"deadline": 0}):
            with self.assertRaises(ValueError):
                await run(**kwargs)

    async def test_private_resolved_destination_is_rejected(self):
        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 443))]):
            with self.assertRaisesRegex(ValueError, "not_public"):
                await public_destination("www.airbnb.com", 443)


class ProxyServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pool = Pool(":memory:")
        self.pool.import_manifest(manifest("8.8.8.8:8080"))
        self.upstream_requests = []
        self.upstream_status = 200
        async def upstream(reader, writer):
            try:
                head = await reader.readuntil(b"\r\n\r\n")
                self.upstream_requests.append(head)
                if head.startswith(b"CONNECT"):
                    if self.upstream_status != 200:
                        writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                    else:
                        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                        await writer.drain()
                        data = await reader.readexactly(8)
                        writer.write(data)
                else:
                    writer.write(f"HTTP/1.1 {self.upstream_status} Response\r\nContent-Length: 7\r\nConnection: close\r\n\r\n".encode() + b"payload")
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
        self.upstream = await asyncio.start_server(upstream, "127.0.0.1", 0)
        upstream_port = self.upstream.sockets[0].getsockname()[1]
        async def local_test_connector(host, port, **kwargs):
            self.assertEqual((host, port), ("8.8.8.8", 8080))
            return await asyncio.open_connection("127.0.0.1", upstream_port, **kwargs)
        async def test_resolve(host, port):
            self.assertIn(host, {"httpbin.org", "www.airbnb.com"})
        self.proxy = await ForwardProxy(self.pool, resolve=test_resolve, connect=local_test_connector, min_interval=0).start()
        original = self.proxy.client
        class LocalTestHTTP:
            def request(self, method, target, **kwargs):
                self_endpoint = kwargs.pop("proxy")
                assert self_endpoint == "http://8.8.8.8:8080"
                return original.request(method, target, proxy=f"http://127.0.0.1:{upstream_port}", **kwargs)
            async def close(self):
                await original.close()
        self.proxy.client = LocalTestHTTP()
        self.server = await asyncio.start_server(self.proxy.handle, "127.0.0.1", 0, limit=32768)
        self.port = self.server.sockets[0].getsockname()[1]
        self.auth = b"Proxy-Authorization: Basic " + base64.b64encode(b"sticky-test:") + b"\r\n"

    async def asyncTearDown(self):
        self.server.close()
        self.upstream.close()
        await self.server.wait_closed()
        await self.upstream.wait_closed()
        await self.proxy.close()
        self.pool.close()

    async def exchange(self, request):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(request)
        await writer.drain()
        value = await asyncio.wait_for(reader.read(), 3)
        writer.close()
        await writer.wait_closed()
        return value

    async def test_http_forwards_stream_and_consumes_proxy_credentials_hop_headers(self):
        request = b"GET http://httpbin.org/ip HTTP/1.1\r\nHost: httpbin.org\r\n" + self.auth + b"Connection: X-Remove\r\nX-Remove: secret\r\n\r\n"
        response = await self.exchange(request)
        self.assertTrue(response.startswith(b"HTTP/1.1 200"))
        self.assertTrue(response.endswith(b"payload"))
        self.assertNotIn(b"secret", self.upstream_requests[0])
        self.assertNotIn(b"sticky-test", self.upstream_requests[0])
        self.assertNotIn(b"Proxy-Authorization", self.upstream_requests[0])

    async def test_connect_keeps_tunnel_bytes_opaque_and_sticky(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(b"CONNECT www.airbnb.com:443 HTTP/1.1\r\nHost: www.airbnb.com:443\r\n" + self.auth + b"\r\n")
        await writer.drain()
        self.assertIn(b"200 Connection Established", await reader.readuntil(b"\r\n\r\n"))
        opaque = b"\x16\x03\x01\x00test"
        writer.write(opaque)
        await writer.drain()
        self.assertEqual(await reader.readexactly(8), opaque)
        writer.close()
        await writer.wait_closed()
        self.assertEqual(len(self.upstream_requests), 1)
        self.assertNotIn(b"Proxy-Authorization", self.upstream_requests[0])

    async def test_unsafe_destination_port_missing_auth_and_ambiguous_framing_rejected(self):
        for target in (b"127.0.0.1:443", b"www.airbnb.com:22", b"evil.example:443"):
            response = await self.exchange(b"CONNECT " + target + b" HTTP/1.1\r\n" + self.auth + b"\r\n")
            self.assertTrue(response.startswith(b"HTTP/1.1 400"))
        response = await self.exchange(b"GET http://httpbin.org/ip HTTP/1.1\r\nTransfer-Encoding: chunked\r\n" + self.auth + b"\r\n")
        self.assertTrue(response.startswith(b"HTTP/1.1 400"))
        self.assertEqual(self.upstream_requests, [])

    async def test_http_block_halts_session_without_proxy_failure_or_retry(self):
        self.upstream_status = 429
        request = b"GET http://httpbin.org/ip HTTP/1.1\r\nHost: httpbin.org\r\n" + self.auth + b"\r\n"
        self.assertTrue((await self.exchange(request)).startswith(b"HTTP/1.1 429"))
        self.assertTrue((await self.exchange(request)).startswith(b"HTTP/1.1 503"))
        self.assertEqual(len(self.upstream_requests), 1)
        self.assertEqual(self.pool.health()[0]["fail_count"], 0)

    async def test_connect_denial_is_transport_failure_and_never_retries(self):
        self.upstream_status = 403
        request = b"CONNECT www.airbnb.com:443 HTTP/1.1\r\n" + self.auth + b"\r\n"
        self.assertTrue((await self.exchange(request)).startswith(b"HTTP/1.1 502"))
        self.assertEqual(self.pool.health()[0]["fail_count"], 1)
        self.assertEqual(len(self.upstream_requests), 1)

    async def test_https_caller_report_halts_pinned_route(self):
        self.pool.choose("sticky-test", "www.airbnb.com")
        body = json.dumps({"host": "www.airbnb.com", "status": 403}).encode()
        request = b"POST /_route/report HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nContent-Type: application/json\r\n" + self.auth + f"Content-Length: {len(body)}\r\n\r\n".encode() + body
        response = await self.exchange(request)
        self.assertTrue(response.startswith(b"HTTP/1.1 200"))
        with self.assertRaises(RouteUnavailable):
            self.pool.choose("sticky-test", "www.airbnb.com")
        self.assertEqual(self.pool.health()[0]["fail_count"], 0)


class WrapperTests(unittest.TestCase):
    def test_wrapper_reports_target_block_once_without_retry_or_secret_output(self):
        class Response:
            status_code = 429
            def __enter__(self): return self
            def __exit__(self, *args): pass
        class Client:
            trust_env = True
            calls = []
            def get(self, url, **kwargs):
                self.calls.append(("get", kwargs))
                return Response()
            def post(self, url, **kwargs):
                self.calls.append(("post", kwargs))
                return type("Response", (), {"status_code": 200})()
        client = Client()
        result = execute_observed({"method": "GET", "url": "https://www.airbnb.com/api/v3/StaysPdpBookItQuery/hash?locale=en-IN&secret=private",
                                   "headers": {"Cookie": "private", "X-Airbnb-API-Key": "private"}}, session_id="test", client=client)
        self.assertEqual([item[0] for item in client.calls], ["get", "post"])
        self.assertEqual(result["stop_reason"], "target_access_or_rate_limit")
        self.assertTrue(result["block_reported"])
        self.assertTrue(client.calls[0][1]["verify"])
        self.assertFalse(client.calls[0][1]["allow_redirects"])
        self.assertNotIn("private", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
