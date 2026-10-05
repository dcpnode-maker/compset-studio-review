"""One bounded sticky-route replay of a fresh browser-observed public read.

No stored API key, speculative StaysSearch variables or alternate-route retry.
The CLI first runs CompSet's ordinary direct observation, then explicitly tests
one observed read through the configured local route. A blocked discovery stops.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import random
import re
import time
from urllib.parse import urlsplit

import requests


def local_proxy_url(proxy_url: str, session_id: str) -> str:
    parsed = urlsplit(proxy_url)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.username or parsed.password or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment or not parsed.port):
        raise ValueError("proxy must be an explicit loopback HTTP host:port")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session_id):
        raise ValueError("invalid explicit session ID")
    return f"http://{session_id}:@{parsed.hostname}:{parsed.port}"


def report_block(session, proxy_url, session_id, host, status, *, cooldown=900):
    credentials = base64.b64encode((session_id + ":").encode("ascii")).decode("ascii")
    response = session.post(proxy_url.rstrip("/") + "/_route/report",
                            headers={"Proxy-Authorization": "Basic " + credentials},
                            json={"host": host, "status": status, "cooldown": cooldown},
                            timeout=(3, 5), allow_redirects=False, proxies={})
    return response.status_code == 200


def execute_observed(template: dict, *, session_id: str, proxy_url="http://127.0.0.1:8080", client=None) -> dict:
    from compset.collect import read_operation, safe_source, public_json, request_context
    url = template.get("url", "")
    if not read_operation(url, template.get("method", "")):
        raise ValueError("only a fresh observed allowlisted GET request may be replayed")
    proxy = local_proxy_url(proxy_url, session_id)
    result = {"route": {"mode": "local_sticky_proxy", "category": "unknown",
                         "session_tag": hashlib.sha256(session_id.encode()).hexdigest()[:12],
                         "tls_verification": True}, "operation": read_operation(url),
              "source_url": safe_source(url), "request_context": request_context(url),
              "status": None, "payload": None, "stop_reason": None}
    owned = client is None
    session = client or requests.Session()
    session.trust_env = False
    try:
        headers = {key: value for key, value in template.get("headers", {}).items()
                   if key.lower() not in {"host", "content-length", "proxy-authorization", "connection", "accept-encoding"}}
        with session.get(url, headers=headers, proxies={"http": proxy, "https": proxy},
                         verify=True, timeout=(8, 30), allow_redirects=False, stream=True) as response:
            result["status"] = response.status_code
            if response.status_code in {401, 403, 429}:
                result["stop_reason"] = "target_access_or_rate_limit"
                try:
                    result["block_reported"] = report_block(session, proxy_url, session_id,
                        urlsplit(url).hostname, response.status_code)
                except requests.RequestException:
                    result["block_reported"] = False
                return result
            if response.status_code != 200:
                result["stop_reason"] = "non_success_response"
                return result
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 8 * 1024 * 1024:
                    result["stop_reason"] = "response_byte_budget"
                    return result
                chunks.append(chunk)
            raw = b"".join(chunks)
            try:
                body = json.loads(raw)
                if not isinstance(body, (dict, list)):
                    raise ValueError
            except (ValueError, UnicodeError):
                result["stop_reason"] = "non_json_or_challenge"
                if re.search(rb"captcha|access denied|verify you are human|security challenge", raw[:100000], re.I):
                    try:
                        result["block_reported"] = report_block(session, proxy_url, session_id, urlsplit(url).hostname, 403)
                    except requests.RequestException:
                        result["block_reported"] = False
                return result
            result["payload"] = {"source_url": safe_source(url), "status": 200,
                                  "request_context": request_context(url), "body": public_json(body)}
    except requests.exceptions.ProxyError:
        result["stop_reason"] = "proxy_transport_failure"
    except requests.exceptions.SSLError:
        result["stop_reason"] = "tls_validation_failure"
    except requests.exceptions.Timeout:
        result["stop_reason"] = "request_timeout"
    except requests.RequestException:
        result["stop_reason"] = "request_transport_failure"
    finally:
        if owned:
            session.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listing", required=True)
    parser.add_argument("--checkin", required=True)
    parser.add_argument("--checkout", required=True)
    parser.add_argument("--adults", type=int, default=1)
    parser.add_argument("--currency", default="AED")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--proxy-url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    local_proxy_url(args.proxy_url, args.session_id)
    from compset.collect import collect
    from compset.pipeline import context_from, build_result
    context = context_from(vars(args))
    templates = []
    capture = collect(context, template_sink=templates)
    if capture["report"].get("stop_reason") or not templates:
        print(json.dumps({"stop_reason": "direct_discovery_stopped_or_no_observed_request",
                          "report": capture["report"]}))
        return 2
    template = next((value for value in templates if "/StaysPdpBookItQuery/" in value["url"]), templates[0])
    time.sleep(random.uniform(3, 7))
    result = execute_observed(template, session_id=args.session_id, proxy_url=args.proxy_url)
    if result["payload"] is not None:
        parsed = build_result({"payloads": [result["payload"]], "report": {}}, context)
        print(json.dumps({"listing_id": context["listing_id"], "listing": parsed["listing"],
                          "quotes": parsed["quotes"], "route": result["route"]}, ensure_ascii=False))
    else:
        print(json.dumps(result))
    return 0 if result["payload"] is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
