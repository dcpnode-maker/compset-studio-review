"""Local HTTP/CONNECT forwarder with explicit sticky sessions, never rotation retries.

asyncio streams implement CONNECT; aiohttp implements ordinary HTTP forwarding
and HTTPS route probes. TLS inside CONNECT remains entirely opaque.
"""
from __future__ import annotations
import argparse
import asyncio
import base64
from contextlib import suppress
import ipaddress
import json
import logging
from pathlib import Path
import re
import socket
import time
from urllib.parse import urlsplit

import aiohttp
from .kaggle_fetch_validate import validate_one, normalize_proxy
from .pool import Pool, RouteUnavailable

ALLOWED_HOSTS = frozenset({"httpbin.org", "www.airbnb.com", "airbnb.com", "www.airbnb.co.in", "airbnb.co.in"})
HOP_HEADERS = {"connection", "proxy-connection", "proxy-authorization", "proxy-authenticate",
               "keep-alive", "transfer-encoding", "te", "trailer", "upgrade"}
MAX_HEADERS = 32768


def session_from_headers(headers: dict) -> str:
    value = headers.get("proxy-authorization", "")
    try:
        scheme, encoded = value.split(" ", 1)
        if scheme.lower() != "basic":
            raise ValueError
        decoded = base64.b64decode(encoded, validate=True).decode("ascii")
        session, password = decoded.split(":", 1)
        if password or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session):
            raise ValueError
        return session
    except (ValueError, UnicodeError):
        raise ValueError("explicit_proxy_session_required") from None


async def public_destination(host: str, port: int) -> None:
    records = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not records or any(not ipaddress.ip_address(record[4][0]).is_global or
                          ipaddress.ip_address(record[4][0]).is_multicast for record in records):
        raise ValueError("destination_not_public")


async def read_head(reader):
    raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
    if len(raw) > MAX_HEADERS:
        raise ValueError("headers_too_large")
    lines = raw.decode("iso-8859-1").split("\r\n")
    start = lines[0].split(" ", 2)
    if len(start) != 3:
        raise ValueError("invalid_start_line")
    headers = {}
    for line in lines[1:-2]:
        if ":" not in line or line.startswith((" ", "\t")):
            raise ValueError("invalid_header")
        name, value = line.split(":", 1)
        name = name.lower()
        if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9a-z-]+", name) or name in headers:
            raise ValueError("invalid_or_duplicate_header")
        if any(ord(char) < 32 and char != "\t" for char in value):
            raise ValueError("invalid_header_value")
        headers[name] = value.strip()
    return start, headers


class ForwardProxy:
    def __init__(self, pool: Pool, *, allowed_hosts=ALLOWED_HOSTS, resolve=public_destination,
                 connect=asyncio.open_connection, min_interval=3.0):
        self.pool, self.allowed_hosts, self.resolve, self.connect = pool, set(allowed_hosts), resolve, connect
        self.min_interval = max(0, min_interval)
        self._next_start, self._rate_locks = {}, {}
        self._slots = asyncio.Semaphore(16)
        self.client = None

    async def start(self):
        self.client = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=40, connect=8),
                     auto_decompress=False, cookie_jar=aiohttp.DummyCookieJar(), trust_env=False,
                     connector=aiohttp.TCPConnector(limit=16, ssl=True))
        return self

    async def close(self):
        if self.client:
            await self.client.close()

    async def pace(self, session):
        lock = self._rate_locks.setdefault(session, asyncio.Lock())
        async with lock:
            await asyncio.sleep(max(0, self._next_start.get(session, 0) - time.monotonic()))
            self._next_start[session] = time.monotonic() + self.min_interval

    async def respond(self, writer, status, reason, body=b""):
        writer.write(f"HTTP/1.1 {status} {reason}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
        await writer.drain()

    async def _target(self, method, target):
        if any(ord(char) <= 32 or ord(char) == 127 for char in target):
            raise ValueError("invalid_target")
        if method == "CONNECT":
            match = re.fullmatch(r"([A-Za-z0-9.-]+):443", target)
            if not match:
                raise ValueError("connect_requires_host_port_443")
            host, port = match[1].lower(), 443
        else:
            parsed = urlsplit(target)
            if parsed.scheme != "http" or parsed.username or parsed.password or parsed.fragment or parsed.port not in (None, 80):
                raise ValueError("http_requires_absolute_public_url_port_80")
            host, port = parsed.hostname, 80
        if host not in self.allowed_hosts:
            raise ValueError("host_not_allowlisted")
        await asyncio.wait_for(self.resolve(host, port), 8)
        return host, port

    async def handle(self, reader, writer):
        response_started = False
        try:
            async with self._slots:
                (method, target, version), headers = await read_head(reader)
                if version not in {"HTTP/1.0", "HTTP/1.1"} or "transfer-encoding" in headers:
                    raise ValueError("unsupported_framing")
                if target == "/_route/report" and method == "POST":
                    await self._report(reader, writer, headers)
                    return
                if method not in {"GET", "HEAD", "CONNECT"} or headers.get("content-length", "0") != "0":
                    raise ValueError("read_methods_without_request_body_only")
                session = session_from_headers(headers)
                host, port = await self._target(method, target)
                route = self.pool.choose(session, host)
                await self.pace(session)
                # Recheck after waiting: another request may have reported a block.
                route = self.pool.choose(session, host)
                if method == "CONNECT":
                    response_started = await self._tunnel(reader, writer, route, target)
                else:
                    response_started = await self._http(writer, route, session, host, method, target, headers)
        except RouteUnavailable:
            if not response_started:
                with suppress(Exception):
                    await self.respond(writer, 503, "Route Unavailable")
        except (ValueError, asyncio.LimitOverrunError, asyncio.IncompleteReadError):
            if not response_started:
                with suppress(Exception):
                    await self.respond(writer, 400, "Request Rejected")
        except Exception:
            # Never log exception text, full URLs, headers or local session IDs.
            logging.warning("route_request_failed")
            if not response_started:
                with suppress(Exception):
                    await self.respond(writer, 502, "Route Transport Failure")
        finally:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    async def _tunnel(self, reader, writer, route, target):
        endpoint = route["endpoint"]
        if normalize_proxy(endpoint) != endpoint:
            raise ValueError("invalid_stored_proxy")
        host, port = endpoint.split(":")
        upstream_writer = None
        started = time.monotonic()
        established = False
        try:
            upstream_reader, upstream_writer = await asyncio.wait_for(self.connect(host, int(port), limit=MAX_HEADERS), 8)
            upstream_writer.write(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\nProxy-Connection: keep-alive\r\n\r\n".encode("ascii"))
            await upstream_writer.drain()
            statusline, _ = await read_head(upstream_reader)
            if statusline[0] not in {"HTTP/1.0", "HTTP/1.1"} or statusline[1] != "200":
                self.pool.transport_failure(endpoint, "upstream_connect_denied")
                await self.respond(writer, 502, "Upstream CONNECT Denied")
                return True
            self.pool.transport_ok(endpoint, (time.monotonic() - started) * 1000)
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            established = True

            async def pipe(source, destination):
                transferred = 0
                while chunk := await asyncio.wait_for(source.read(65536), 30):
                    transferred += len(chunk)
                    if transferred > 20 * 1024 * 1024:
                        raise ValueError("tunnel_byte_budget")
                    destination.write(chunk)
                    await destination.drain()
                # A read EOF ends only this direction. Forward FIN while allowing
                # a delayed response to drain from the peer before closing.
                if destination.can_write_eof():
                    destination.write_eof()
                    await destination.drain()

            tasks = [asyncio.create_task(pipe(reader, upstream_writer)), asyncio.create_task(pipe(upstream_reader, writer))]
            try:
                await asyncio.wait_for(asyncio.gather(*tasks), timeout=120)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            return True
        except Exception:
            if not established:
                self.pool.transport_failure(endpoint, "proxy_connect_transport_failure")
                raise
            # Opaque TLS/client timeouts do not establish that the proxy is bad.
            return True
        finally:
            if upstream_writer:
                upstream_writer.close()
                with suppress(Exception):
                    await upstream_writer.wait_closed()

    async def _http(self, writer, route, session, host, method, target, headers):
        endpoint = route["endpoint"]
        if normalize_proxy(endpoint) != endpoint:
            raise ValueError("invalid_stored_proxy")
        connection_tokens = {part.strip().lower() for part in headers.get("connection", "").split(",")}
        forwarded = {key: value for key, value in headers.items() if key not in HOP_HEADERS | connection_tokens | {"host", "content-length"}}
        started = time.monotonic()
        response_started = False
        try:
            async with self.client.request(method, target, headers=forwarded, proxy=f"http://{endpoint}",
                                           allow_redirects=False) as response:
                if response.status == 407:
                    self.pool.transport_failure(endpoint, "upstream_auth_required")
                elif response.status in {401, 403, 429}:
                    self.pool.target_block(session, host, status=response.status)
                else:
                    self.pool.transport_ok(endpoint, (time.monotonic() - started) * 1000)
                writer.write(f"HTTP/1.1 {response.status} Response\r\n".encode())
                response_started = True
                response_tokens = {token.strip().lower() for name, value in response.raw_headers
                    if name.lower() == b"connection" for token in value.decode("iso-8859-1").split(",")}
                for name, value in response.raw_headers:
                    if name.decode("ascii", errors="ignore").lower() not in HOP_HEADERS | response_tokens:
                        writer.write(name + b": " + value + b"\r\n")
                writer.write(b"Connection: close\r\n\r\n")
                await writer.drain()
                count = 0
                async for chunk in response.content.iter_chunked(65536):
                    count += len(chunk)
                    if count > 20 * 1024 * 1024:
                        break
                    writer.write(chunk)
                    await writer.drain()
                return True
        except (aiohttp.ClientProxyConnectionError, aiohttp.ClientHttpProxyError):
            self.pool.transport_failure(endpoint, "proxy_http_transport_failure")
            raise
        except Exception:
            if response_started:
                return True
            raise

    async def _report(self, reader, writer, headers):
        session = session_from_headers(headers)
        # Browser pages cannot forge this endpoint via a form or cross-origin JS.
        if headers.get("origin") or headers.get("content-type") != "application/json":
            raise ValueError("local_json_control_only")
        if not re.fullmatch(r"(?:127\.0\.0\.1|localhost)(?::\d{1,5})?", headers.get("host", "")):
            raise ValueError("local_control_host_required")
        length = int(headers.get("content-length", "0"))
        if not 1 <= length <= 2048:
            raise ValueError("report_size")
        body = json.loads(await asyncio.wait_for(reader.readexactly(length), 5))
        if not isinstance(body, dict):
            raise ValueError("report_requires_json_object")
        host = body.get("host")
        if host not in self.allowed_hosts or type(body.get("status")) is not int:
            raise ValueError("report_target")
        self.pool.target_block(session, host, status=body["status"], cooldown=body.get("cooldown", 900))
        await self.respond(writer, 200, "Reported", b'{"session_halted":true}')


async def health_loop(pool, *, interval=300, batch=32):
    """Finite small batches. Target blocks never trigger alternative routes."""
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8), trust_env=False,
                                     connector=aiohttp.TCPConnector(limit=8, ssl=True)) as session:
        while True:
            await asyncio.sleep(interval)
            candidates = sorted(pool.health(), key=lambda item: item["validated_at"])[:batch]
            semaphore = asyncio.Semaphore(8)

            async def check(route):
                async with semaphore:
                    result = await validate_one(session, route["endpoint"], attempts=1)
                    if result["alive"]:
                        result["source_urls"] = json.loads(route["source_urls"])
                        result.update(json.loads(route["source_provenance"]))
                        pool.import_manifest({"proxies": [result]})
                    else:
                        pool.transport_failure(route["endpoint"], "health_probe_failed")

            await asyncio.gather(*(check(route) for route in candidates))


async def main(args):
    if args.container and not Path("/.dockerenv").exists():
        raise ValueError("container binding is available only inside Docker; local mode binds loopback")
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    pool = Pool(args.db)
    proxy = server = health = None
    try:
        manifest = Path(args.manifest)
        if manifest.exists():
            source_list = Path(args.proxy_list)
            selected = {normalize_proxy(line) for line in source_list.read_text(encoding="utf-8").splitlines()} if source_list.exists() else set()
            evidence = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(evidence, dict) and isinstance(evidence.get("proxies"), list):
                evidence["proxies"] = [item for item in evidence["proxies"] if isinstance(item, dict)
                    and isinstance(item.get("endpoint"), str) and item["endpoint"] in selected]
            imported = pool.import_manifest(evidence)
            logging.info("validated_routes_imported count=%s", imported)
        proxy = ForwardProxy(pool)
        await proxy.start()
        # Container listener must bind its interface; Compose publishes loopback only.
        bind = "0.0.0.0" if args.container else "127.0.0.1"
        server = await asyncio.start_server(proxy.handle, bind, args.port, limit=MAX_HEADERS)
        health = asyncio.create_task(health_loop(pool)) if args.health_checks else None
        logging.info("local_route_server_ready port=%s", args.port)
        async with server:
            await server.serve_forever()
    finally:
        if health:
            health.cancel()
            await asyncio.gather(health, return_exceptions=True)
        if server:
            server.close()
            with suppress(Exception):
                await server.wait_closed()
        if proxy:
            with suppress(Exception):
                await proxy.close()
        pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="routes/data/proxies.db")
    parser.add_argument("--manifest", default="routes/working_proxies.json")
    parser.add_argument("--proxy-list", default="routes/working_proxies.txt")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--container", action="store_true", help="Only with the supplied loopback-published Compose file")
    parser.add_argument("--health-checks", action="store_true", help="Opt in to probes every 5 minutes, 32 routes maximum per cycle")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main(parser.parse_args()))
