"""Self-contained bounded free HTTP-proxy batch validator; no server required.

Run on Kaggle with internet enabled after installing aiohttp, or run locally.
HTTPS certificate validation is always enabled. Results prove only that the
specific HTTPS /ip probe succeeded at the recorded time, not Airbnb access.
"""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
import ipaddress
import hashlib
import json
from pathlib import Path
import re
import time

SOURCES = (
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http",
)
TEST_URL = "https://httpbin.org/ip"
MAX_SOURCE_BYTES = 2_000_000


def normalize_proxy(line: str) -> str | None:
    if not isinstance(line, str):
        return None
    match = re.fullmatch(r"(?:http://)?(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})", line.strip())
    if not match:
        return None
    try:
        address = ipaddress.ip_address(match[1])
    except ValueError:
        return None
    port = int(match[2])
    if not address.is_global or address.is_multicast or not 1 <= port <= 65535:
        return None
    return f"{address}:{port}"


def operator_candidates(input_file: str) -> tuple[dict, dict, int]:
    """Explicit user file; export a content digest, never its local path/name."""
    with Path(input_file).open("rb") as stream:
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    if not raw or len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("operator input must contain 1..2000000 bytes")
    lines = raw.decode("utf-8", errors="replace").splitlines()
    candidates = {endpoint: set() for line in lines if (endpoint := normalize_proxy(line))}
    provenance = {"source_type": "operator_supplied", "source_file": {
        "label": "operator-input", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}
    return candidates, provenance, len(lines)


def valid_origin(value) -> bool:
    if not isinstance(value, str) or len(value) > 200:
        return False
    try:
        return all(ipaddress.ip_address(part.strip()).is_global and
                   not ipaddress.ip_address(part.strip()).is_multicast for part in value.split(","))
    except ValueError:
        return False


async def read_bounded(content, maximum: int) -> bytes:
    """StreamReader.read(n) may return a partial chunk; read to EOF or the cap."""
    chunks, size = [], 0
    while True:
        chunk = await content.read(min(65536, maximum + 1 - size))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        size += len(chunk)
        if size > maximum:
            raise ValueError("body exceeds byte budget")


async def validate_one(session, endpoint: str, *, attempts=2) -> dict:
    """At most two probes of the same route; never follows redirects."""
    if normalize_proxy(endpoint) != endpoint:
        raise ValueError("proxy must be a globally routable IPv4:port")
    started = time.monotonic()
    result = {"endpoint": endpoint, "alive": False, "category": "unknown",
              "protocol": "http_connect", "tls_verified": False,
              "validation_url": TEST_URL, "validated_at": datetime.now(timezone.utc).isoformat()}
    for attempt in range(min(2, max(1, attempts))):
        try:
            async with session.get(TEST_URL, proxy=f"http://{endpoint}", ssl=True,
                                   allow_redirects=False) as response:
                result["status"] = response.status
                if response.status != 200:
                    result["error"] = "probe_http_status"
                    break
                body = await read_bounded(response.content, 8192)
                origin = json.loads(body).get("origin")
                if not valid_origin(origin):
                    result["error"] = "invalid_origin"
                    break
                result.update(alive=True, tls_verified=True, origin=origin,
                              latency_ms=round((time.monotonic() - started) * 1000, 2))
                result.pop("error", None)
                break
        except (TimeoutError, OSError, ValueError) as exc:
            result["error"] = type(exc).__name__
        except Exception as exc:
            # aiohttp's errors often embed proxy URLs; retain type, not text.
            result["error"] = type(exc).__name__
        if attempt == 0:
            await asyncio.sleep(0.25)
    return result


async def run(*, concurrency=8, max_candidates=200, output="working_proxies.txt", deadline=900, input_file=None) -> dict:
    if (any(type(value) is not int for value in (concurrency, max_candidates, deadline)) or
            not 1 <= concurrency <= 32 or not 1 <= max_candidates <= 2000 or not 1 <= deadline <= 3600):
        raise ValueError("limits: concurrency 1..32, candidates 1..2000, deadline 1..3600 seconds")
    import aiohttp
    started = time.monotonic()
    candidates, source_results, total_fetched = {}, [], 0
    supplied = None
    if input_file is not None:
        candidates, supplied, total_fetched = operator_candidates(input_file)
        source_results.append({**supplied, "lines": total_fetched})
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8),
                                     connector=aiohttp.TCPConnector(limit=concurrency, ssl=True),
                                     trust_env=False) as session:
        for source in (() if supplied else SOURCES):
            try:
                async with session.get(source, ssl=True, allow_redirects=False) as response:
                    if response.status != 200:
                        source_results.append({"source": source, "status": response.status})
                        continue
                    body = await read_bounded(response.content, MAX_SOURCE_BYTES)
                    lines = body.decode("utf-8", errors="replace").splitlines()
                    total_fetched += len(lines)
                    for line in lines:
                        endpoint = normalize_proxy(line)
                        if endpoint:
                            candidates.setdefault(endpoint, set()).add(source)
                    source_results.append({"source": source, "status": 200, "lines": len(lines)})
            except Exception as exc:
                source_results.append({"source": source, "error": type(exc).__name__})
        # Select deterministically; finite budget is explicit.
        selected = sorted(candidates)[:max_candidates]
        semaphore = asyncio.Semaphore(concurrency)
        results = []

        async def check(endpoint):
            async with semaphore:
                value = await validate_one(session, endpoint)
                value["source_urls"] = sorted(candidates[endpoint])
                if supplied:
                    value.update(supplied)
                results.append(value)

        timed_out = False
        try:
            await asyncio.wait_for(asyncio.gather(*(check(p) for p in selected)), timeout=deadline)
        except TimeoutError:
            timed_out = True
    alive = sorted((value for value in results if value["alive"]), key=lambda item: item["latency_ms"])
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(value["endpoint"] + "\n" for value in alive), encoding="utf-8")
    summary = {"schema_version": 1, "total_fetched": total_fetched, "deduped": len(candidates),
               "selected": len(selected), "completed": len(results), "alive": len(alive),
               "elapsed_seconds": round(time.monotonic() - started, 2), "deadline_reached": timed_out,
               "source_results": source_results, "proxies": alive,
               "validation_scope": "HTTPS httpbin.org/ip only; target usability unknown"}
    output_path.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key not in {"proxies", "source_results"}}))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--max-candidates", type=int, default=200)
    parser.add_argument("--deadline", type=int, default=900)
    parser.add_argument("--output", default="working_proxies.txt")
    parser.add_argument("--input", dest="input_file", help="Validate only this operator-supplied IPv4:port file; no public source fetches")
    asyncio.run(run(**vars(parser.parse_args())))
