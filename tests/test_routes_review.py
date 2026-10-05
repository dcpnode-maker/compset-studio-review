"""Independent offline regressions for order 005 route boundaries."""
import asyncio
import base64
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from routes import proxy_server
from routes.airbnb_scraper import execute_observed
from routes.pool import Pool
from routes.proxy_server import ForwardProxy, public_destination
from tests import test_routes as baseline


class MemoryWriter:
    def __init__(self):
        self.data = bytearray()
        self.closed = False
        self.eof = False

    def write(self, value):
        self.data.extend(value)

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass

    def can_write_eof(self):
        return True

    def write_eof(self):
        self.eof = True


class ManifestReviewTests(unittest.TestCase):
    def setUp(self):
        self.pool = Pool(":memory:")

    def tearDown(self):
        self.pool.close()

    def test_manifest_requires_boolean_success_and_known_source_provenance(self):
        for changed in ({"alive": "false"}, {"alive": 1}, {"source_urls": []},
                        {"source_urls": ["https://unknown.example/proxies"]}):
            with self.subTest(changed=changed):
                item = baseline.manifest("8.8.8.8:8080")
                item["proxies"][0].update(changed)
                self.assertEqual(self.pool.import_manifest(item), 0)

    def test_empty_shipped_pool_and_host_only_compose_binding(self):
        root = Path(__file__).resolve().parents[1] / "routes"
        self.assertEqual(json.loads((root / "working_proxies.json").read_text())["proxies"], [])
        self.assertEqual((root / "working_proxies.txt").read_text().strip(), "")
        compose = (root / "docker-compose.yml").read_text()
        self.assertIn('"127.0.0.1:8080:8080"', compose)
        self.assertNotIn('"8080:8080"', compose)

    def test_malformed_manifest_rows_are_rejected_without_hiding_valid_rows(self):
        valid = baseline.manifest("8.8.8.8:8080")["proxies"][0]
        self.assertEqual(self.pool.import_manifest({"proxies": [None, [], {"endpoint": None}, valid]}), 1)
        self.assertEqual(len(self.pool.health()), 1)

    def test_operator_provenance_rejects_incomplete_or_ambiguous_evidence(self):
        valid_evidence = {"label": "operator-input", "sha256": "a" * 64, "bytes": 20}
        for change in ({"bytes": True}, {"bytes": 0}, {"bytes": 2_000_001},
                       {"sha256": "not-a-digest"}, {"label": "private-filename.txt"}):
            item = baseline.manifest("8.8.8.8:8080")["proxies"][0]
            item.update(source_type="operator_supplied", source_urls=[], source_file={**valid_evidence, **change})
            self.assertEqual(self.pool.import_manifest({"proxies": [item]}), 0)
        item["source_file"] = valid_evidence
        item["source_urls"] = [baseline.SOURCES[0]]
        self.assertEqual(self.pool.import_manifest({"proxies": [item]}), 0)

    def test_additive_database_upgrade_preserves_sticky_and_halted_state(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "old-routes.sqlite3"
            original = sqlite3.connect(database)
            try:
                original.executescript("""
                    CREATE TABLE proxies(endpoint TEXT PRIMARY KEY, source_urls TEXT NOT NULL,
                        category TEXT NOT NULL DEFAULT 'unknown', protocol TEXT NOT NULL,
                        tls_verified INTEGER NOT NULL, validated_at REAL NOT NULL,
                        origin TEXT, last_ok REAL, fail_count INTEGER NOT NULL DEFAULT 0,
                        avg_latency_ms REAL, last_error TEXT);
                    CREATE TABLE sessions(session_id TEXT PRIMARY KEY, endpoint TEXT NOT NULL,
                        created_at REAL NOT NULL, halted_reason TEXT);
                    CREATE TABLE target_cooldowns(host TEXT PRIMARY KEY, until_at REAL NOT NULL);
                """)
                original.execute("INSERT INTO proxies VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    ("8.8.8.8:8080", json.dumps([baseline.SOURCES[0]]), "unknown", "http_connect", 1,
                     1_700_000_000, "8.8.8.8", 1_700_000_000, 2, 42.5, "health_probe_failed"))
                original.execute("INSERT INTO sessions VALUES('keep','8.8.8.8:8080',1700000000,'target_429')")
                original.execute("INSERT INTO target_cooldowns VALUES('www.airbnb.com',2000000000)")
                original.commit()
                before = original.execute("SELECT * FROM proxies").fetchone()
            finally:
                original.close()
            for _ in range(2):
                upgraded = Pool(database)
                try:
                    self.assertEqual(tuple(upgraded.db.execute("SELECT * FROM proxies").fetchone())[:-1], before)
                    self.assertEqual(upgraded.db.execute("SELECT halted_reason FROM sessions WHERE session_id='keep'").fetchone()[0], "target_429")
                    self.assertEqual(upgraded.db.execute("SELECT until_at FROM target_cooldowns").fetchone()[0], 2_000_000_000)
                    self.assertEqual(json.loads(upgraded.health()[0]["source_provenance"]), {})
                    self.assertEqual(upgraded.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                finally:
                    upgraded.close()


class ProtocolReviewTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = baseline.ProxyServerTests.asyncSetUp
    asyncTearDown = baseline.ProxyServerTests.asyncTearDown
    exchange = baseline.ProxyServerTests.exchange

    async def test_report_rejects_remote_host_origin_bad_auth_and_unknown_session(self):
        self.pool.choose("sticky-test", "www.airbnb.com")
        body = json.dumps({"host": "www.airbnb.com", "status": 429}).encode()
        variants = [
            (b"Host: attacker.example\r\n", self.auth),
            (b"Host: localhost:8080\r\nOrigin: https://attacker.example\r\n", self.auth),
            (b"Host: localhost:8080\r\n", b""),
            (b"Host: localhost:8080\r\n", b"Proxy-Authorization: Basic " + base64.b64encode(b"missing:") + b"\r\n"),
        ]
        for headers, auth in variants:
            response = await self.exchange(b"POST /_route/report HTTP/1.1\r\n" + headers + auth +
                b"Content-Type: application/json\r\n" + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
            self.assertTrue(response.startswith(b"HTTP/1.1 400"), response)
        self.assertEqual(self.pool.db.execute("SELECT COUNT(*) FROM target_cooldowns").fetchone()[0], 0)
        self.assertEqual(self.upstream_requests, [])

    async def test_report_non_object_json_is_a_client_error(self):
        self.pool.choose("sticky-test", "www.airbnb.com")
        body = b"[]"
        response = await self.exchange(b"POST /_route/report HTTP/1.1\r\nHost: localhost:8080\r\n" + self.auth +
            b"Content-Type: application/json\r\nContent-Length: 2\r\n\r\n" + body)
        self.assertTrue(response.startswith(b"HTTP/1.1 400"), response)
        self.assertEqual(self.pool.db.execute("SELECT COUNT(*) FROM target_cooldowns").fetchone()[0], 0)

    async def test_duplicate_headers_and_oversized_headers_close_without_upstream(self):
        requests = [
            b"GET http://httpbin.org/ip HTTP/1.1\r\n" + self.auth + b"Content-Length: 0\r\nContent-Length: 0\r\n\r\n",
            b"GET http://httpbin.org/ip HTTP/1.1\r\n" + self.auth + b" X-Fold: secret\r\n\r\n",
            b"GET http://httpbin.org/ip HTTP/1.1\r\n" + self.auth + b"X-Large: " + b"x" * 33000 + b"\r\n\r\n",
        ]
        for request in requests:
            self.assertTrue((await self.exchange(request)).startswith(b"HTTP/1.1 400"))
        self.assertEqual(self.upstream_requests, [])

    async def test_mixed_public_private_dns_and_non_allowlisted_names_fail(self):
        loop = asyncio.get_running_loop()
        records = [(None, None, None, None, ("8.8.8.8", 443)),
                   (None, None, None, None, ("::1", 443))]
        with patch.object(loop, "getaddrinfo", return_value=records):
            with self.assertRaisesRegex(ValueError, "not_public"):
                await public_destination("www.airbnb.com", 443)
        for target in ("http://www.airbnb.com.evil.example/", "http://www.airbnb.com@127.0.0.1/",
                       "http://www.airbnb.com:81/", "http://www.airbnb.com/#fragment"):
            with self.assertRaises(ValueError):
                await self.proxy._target("GET", target)


class TransportLifecycleReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_strips_response_connection_nominated_headers(self):
        class Response:
            status = 200
            raw_headers = [(b"Connection", b"X-Route-Internal"), (b"X-Route-Internal", b"hop-only"),
                           (b"Content-Length", b"2")]
            def __init__(self): self.content = self
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def iter_chunked(self, size): yield b"ok"
        class Client:
            def request(self, *args, **kwargs): return Response()
        pool = Pool(":memory:")
        pool.import_manifest(baseline.manifest("8.8.8.8:8080"))
        writer = MemoryWriter()
        try:
            proxy = ForwardProxy(pool, min_interval=0)
            proxy.client = Client()
            await proxy._http(writer, pool.choose("headers", "httpbin.org"), "headers", "httpbin.org", "GET",
                              "http://httpbin.org/ip", {})
            self.assertNotIn(b"X-Route-Internal", writer.data)
            self.assertTrue(writer.data.endswith(b"ok"))
        finally:
            pool.close()

    async def test_connect_half_close_does_not_discard_late_upstream_response(self):
        pool = Pool(":memory:")
        pool.import_manifest(baseline.manifest("8.8.8.8:8080"))
        client_reader, upstream_reader = asyncio.StreamReader(), asyncio.StreamReader()
        client_writer, upstream_writer = MemoryWriter(), MemoryWriter()
        client_reader.feed_data(b"opaque request")
        client_reader.feed_eof()
        upstream_reader.feed_data(b"HTTP/1.1 200 Established\r\n\r\n")

        async def connect(*args, **kwargs):
            return upstream_reader, upstream_writer

        async def delayed_response():
            await asyncio.sleep(0.02)
            upstream_reader.feed_data(b"opaque delayed response")
            upstream_reader.feed_eof()

        task = asyncio.create_task(delayed_response())
        try:
            proxy = ForwardProxy(pool, connect=connect, min_interval=0)
            await proxy._tunnel(client_reader, client_writer, pool.choose("half-close", "www.airbnb.com"), "www.airbnb.com:443")
            await task
            self.assertIn(b"opaque delayed response", client_writer.data)
            self.assertTrue(upstream_writer.closed)
        finally:
            await task
            pool.close()

    async def test_main_bind_failure_closes_client_and_database(self):
        fake_pool = SimpleNamespace(close=unittest.mock.Mock(), import_manifest=unittest.mock.Mock(return_value=0))
        fake_proxy = SimpleNamespace(handle=AsyncMock(), close=AsyncMock())
        fake_proxy.start = AsyncMock(return_value=fake_proxy)
        args = SimpleNamespace(container=False, db="unused.db", manifest="unused.json", proxy_list="unused.txt",
                               port=8080, health_checks=False)
        with patch.object(proxy_server, "Pool", return_value=fake_pool), \
             patch.object(proxy_server, "ForwardProxy", return_value=fake_proxy), \
             patch.object(proxy_server.Path, "mkdir"), \
             patch.object(proxy_server.Path, "exists", return_value=False), \
             patch.object(proxy_server.asyncio, "start_server", side_effect=OSError("address already in use")) as bind:
            with self.assertRaises(OSError):
                await proxy_server.main(args)
        self.assertEqual(bind.call_args.args[1], "127.0.0.1")
        fake_proxy.close.assert_awaited_once()
        fake_pool.close.assert_called_once()

    async def test_container_switch_cannot_enable_public_local_bind_outside_docker(self):
        args = SimpleNamespace(container=True)
        with patch.object(proxy_server.Path, "exists", return_value=False), \
             patch.object(proxy_server, "Pool") as pool, \
             patch.object(proxy_server.asyncio, "start_server") as bind:
            with self.assertRaisesRegex(ValueError, "only inside Docker"):
                await proxy_server.main(args)
        pool.assert_not_called()
        bind.assert_not_called()


class WrapperReviewTests(unittest.TestCase):
    def test_html_challenge_reports_once_without_payload_or_retry(self):
        class Response:
            status_code = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def iter_content(self, size): yield b"<html>Verify you are human</html>"
        class Client:
            calls = []
            def get(self, url, **kwargs):
                self.calls.append(("get", kwargs))
                return Response()
            def post(self, url, **kwargs):
                self.calls.append(("post", kwargs))
                return SimpleNamespace(status_code=200)
        client = Client()
        result = execute_observed({"method": "GET", "url": "https://www.airbnb.com/api/v3/StaysPdpBookItQuery/hash?secret=not-logged",
                                   "headers": {"Cookie": "not-logged"}}, session_id="review", client=client)
        self.assertEqual([method for method, _ in client.calls], ["get", "post"])
        self.assertEqual(result["stop_reason"], "non_json_or_challenge")
        self.assertTrue(result["block_reported"])
        self.assertIsNone(result["payload"])
        self.assertNotIn("not-logged", json.dumps(result))
        self.assertTrue(client.calls[0][1]["verify"])


if __name__ == "__main__":
    unittest.main()
