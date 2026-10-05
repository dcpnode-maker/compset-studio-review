"""Bounded capture and replay of observed public Airbnb read requests.

Request URLs and headers are ephemeral. Returned evidence contains only a URL's
origin/path, public JSON, status and non-sensitive diagnostics.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import base64
import binascii
from datetime import date
import json
import logging
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MAX_REPLAYS = 8
STOP_STATUSES = {401, 403, 429}
READ_OPERATIONS = frozenset({
    "StaysPdpSections", "StaysPdpAvailabilityCalendar", "StaysPdpPricingQuote",
    "PdpSections", "PdpAvailabilityCalendar", "StaysPdpCalendar", "StaysPdpBookItQuery",
})
SECRET_KEYS = re.compile(r"token|cookie|authorization|password|secret|api[_-]?key|csrf|session|tracking|visitor", re.I)
AIRBNB_HOSTS = {"airbnb.com", "www.airbnb.com", "airbnb.co.in", "www.airbnb.co.in"}
CAPTURE_PATTERN = r"https://(?:www\.)?airbnb\.(?:com|co\.in)/api/v3/"
CHALLENGE_PATTERN = re.compile(
    r"captcha|verify (?:that )?you(?: are|'re) human|are you a robot|unusual traffic|"
    r"challenge[-_ ](?:platform|required|detected)|access denied", re.I)


def validate_context(context: dict) -> dict:
    """Validate bounded collection inputs without changing their meaning."""
    result = dict(context)
    if not re.fullmatch(r"[0-9]{1,25}", str(result.get("listing_id", ""))):
        raise ValueError("listing_id must contain only digits")
    result["listing_id"] = str(result["listing_id"])
    dates = {}
    for key in ("checkin", "checkout", "start_date", "end_date"):
        value = result.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError(f"{key} must use YYYY-MM-DD")
        dates[key] = date.fromisoformat(value)
    if not 1 <= (dates["checkout"] - dates["checkin"]).days <= 365:
        raise ValueError("stay must contain between 1 and 365 nights")
    if not 1 <= (dates["end_date"] - dates["start_date"]).days <= 366:
        raise ValueError("calendar range must contain between 1 and 366 days")
    for key in ("adults", "children", "infants", "pets"):
        value = result.get(key, 0)
        if type(value) is not int or not 0 <= value <= 16:
            raise ValueError(f"{key} must be an integer between 0 and 16")
        result[key] = value
    if result["adults"] < 1:
        raise ValueError("at least one adult is required")
    if not re.fullmatch(r"[A-Z]{3}", result.get("currency", "")):
        raise ValueError("currency must be a three-letter uppercase code")
    if not re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", result.get("locale", "")):
        raise ValueError("locale must use en or en-US style")
    return result


def read_operation(url: str, method: str = "GET", body=None) -> str | None:
    """Only known public PDP reads, on Airbnb's exact HTTPS origin, qualify."""
    try:
        parts = urlsplit(url)
        if (method not in {"GET", "POST"} or parts.scheme != "https" or parts.hostname not in
                AIRBNB_HOSTS or parts.port not in (None, 443)
                or parts.username or parts.password):
            return None
        path = parts.path.split("/")
        if len(path) not in (4, 5) or path[1:3] != ["api", "v3"]:
            return None
        operation = path[3]
        if operation not in READ_OPERATIONS:
            return None
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        if any(key == "query" or (key == "operationName" and value != operation)
               for key, value in pairs):
            return None
        if method == "POST":
            # Only the observed persisted Sections read is authorized. No
            # caller-supplied GraphQL document or arbitrary POST can qualify.
            if (operation != "StaysPdpSections" or len(path) != 5
                    or not re.fullmatch(r"[0-9a-f]{64}", path[4])
                    or not isinstance(body, dict)
                    or set(body) != {"operationName", "variables", "extensions"}
                    or body["operationName"] != operation
                    or not isinstance(body["variables"], dict)
                    or not isinstance(body["extensions"], dict)
                    or any(key in {"variables", "extensions"} for key, _ in pairs)):
                return None
            persisted = body["extensions"].get("persistedQuery")
            if "persistedQuery" in body["extensions"] and (not isinstance(persisted, dict)
                    or persisted.get("sha256Hash") != path[4]):
                return None
        return operation
    except (ValueError, TypeError):
        return None


def observed_operation_name(url: str, method: str) -> str | None:
    """Expose operation names for schema discovery, without retaining requests."""
    try:
        parts = urlsplit(url)
        path = parts.path.split("/")
        if (method == "GET" and parts.scheme == "https" and parts.hostname in AIRBNB_HOSTS
                and parts.port in (None, 443) and not parts.username and not parts.password
                and len(path) in (4, 5) and path[1:3] == ["api", "v3"]
                and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,99}", path[3])):
            return path[3]
    except (ValueError, TypeError):
        pass
    return None


def safe_source(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def request_context(url: str, method: str | None = None, body=None) -> dict:
    """Retain only observed public stay parameters, never the request template."""
    result, values, conflicts = {}, {}, set()
    pairs = parse_qsl(urlsplit(url).query, keep_blank_values=True)
    if method is not None:
        result["method"] = method

    def record(key, value):
        if value is None:
            conflicts.add(key)
        elif key in values and values[key] != value:
            conflicts.add(key)
        else:
            values[key] = value
    aliases = {"numberOfAdults": "adults", "numberOfChildren": "children",
               "numberOfInfants": "infants", "numberOfPets": "pets",
               "adults": "adults", "children": "children", "infants": "infants", "pets": "pets"}
    date_aliases = {"checkIn": "checkin", "checkOut": "checkout",
                    "check_in": "checkin", "check_out": "checkout"}

    def extract(node):
        if isinstance(node, list):
            for child in node:
                extract(child)
            return
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            if key in {"currency", "locale"}:
                pattern = r"[A-Z]{3}" if key == "currency" else r"[a-z]{2}(?:-[A-Z]{2})?"
                record(key, value if isinstance(value, str) and re.fullmatch(pattern, value) else None)
            elif key in aliases:
                valid = ((type(value) is int and 0 <= value <= 16) or
                         (isinstance(value, str) and re.fullmatch(r"\d{1,2}", value) and int(value) <= 16))
                record(aliases[key], int(value) if valid else None)
            elif key in date_aliases:
                normalized = None
                try:
                    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                        normalized = date.fromisoformat(value).isoformat()
                except ValueError:
                    pass
                record(date_aliases[key], normalized)
            elif key == "dateRange":
                if isinstance(value, dict):
                    extract({"checkIn": value.get("startDate"), "checkOut": value.get("endDate")})
                else:
                    conflicts.update({"checkin", "checkout"})
            elif key in {"id", "listingId", "demandStayListingId"}:
                identifier = str(value) if type(value) in (str, int) else ""
                if not identifier.isdigit():
                    try:
                        decoded = base64.b64decode(identifier, validate=True).decode("ascii")
                        match = re.fullmatch(r"(?:DemandStayListing|StayListing):(\d{1,25})", decoded)
                        identifier = match[1] if match else ""
                    except (ValueError, binascii.Error, UnicodeError):
                        identifier = ""
                record("listing_id", identifier if re.fullmatch(r"\d{1,25}", identifier) else None)
            elif isinstance(value, (dict, list)) and key != "priceHeatmapDateRange":
                extract(value)
        if all(type(node.get(key)) is int for key in ("month", "year", "count")):
            record("calendar_month", node["month"])
            record("calendar_year", node["year"])
            record("calendar_month_count", node["count"])

    # Process every occurrence: dict(parse_qsl(...)) would hide conflicts.
    for key, value in pairs:
        if key == "variables":
            try:
                parsed = json.loads(value)
                if not isinstance(parsed, dict):
                    raise ValueError("Variables must be an object")
                extract(parsed)
            except (ValueError, TypeError):
                conflicts.add("variables")
        else:
            extract({key: value})
    if isinstance(body, dict):
        if isinstance(body.get("variables"), dict):
            extract(body["variables"])
        else:
            conflicts.add("variables")
    result.update({key: value for key, value in values.items() if key not in conflicts})
    if conflicts:
        result["conflicts"] = sorted(conflicts)
    return result


def is_date_control(label: str, testid: str = "") -> bool:
    if label in {"check-in", "check in", "check-in date", "change dates"} or testid == "change-dates-checkIn":
        return True
    match = re.fullmatch(r"change dates; check-in: (\d{4}-\d{2}-\d{2}); checkout: (\d{4}-\d{2}-\d{2})", label)
    if match:
        try:
            return date.fromisoformat(match[1]) < date.fromisoformat(match[2])
        except ValueError:
            pass
    return False


def public_json(value):
    """Remove bootstrap/session material before any response can be persisted."""
    if isinstance(value, dict):
        return {k: public_json(v) for k, v in value.items() if not SECRET_KEYS.search(k)}
    if isinstance(value, list):
        return [public_json(v) for v in value]
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        # Never persist API request URLs embedded inside bootstrap data.
        if "/api/" in value:
            return safe_source(value)
    return value


def calendar_replay_url(url: str, context: dict) -> str:
    """Change only a calendar template's already-observed month/year/count keys."""
    operation = read_operation(url)
    if not operation or "Calendar" not in operation or request_context(url).get("conflicts"):
        return url
    parts = urlsplit(url)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    try:
        variables = json.loads(dict(pairs)["variables"])
    except (KeyError, ValueError, TypeError):
        return url
    start, end = date.fromisoformat(context["start_date"]), date.fromisoformat(context["end_date"])
    # end_date is exclusive; overfetching one boundary month is harmless and
    # downstream normalization clips to the user's requested interval.
    count = min(13, (end.year - start.year) * 12 + end.month - start.month + 1)
    changed = False

    def adjust(node):
        nonlocal changed
        if isinstance(node, dict):
            if all(type(node.get(k)) is int for k in ("month", "year", "count")):
                node.update(month=start.month, year=start.year, count=count)
                changed = True
            for child in node.values():
                adjust(child)
        elif isinstance(node, list):
            for child in node:
                adjust(child)

    adjust(variables)
    if not changed:
        return url
    pairs = [(key, json.dumps(variables, separators=(",", ":")) if key == "variables" else value)
             for key, value in pairs]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), ""))


def _payload(response, source_url: str, method="GET", request_body=None) -> dict | None:
    try:
        raw = response.body() if callable(response.body) else response.body
        body = json.loads(raw)
    except (ValueError, TypeError, UnicodeError):
        return None
    if not isinstance(body, (dict, list)):
        return None
    return {"source_url": safe_source(source_url), "status": response.status,
            "request_context": request_context(source_url, method, request_body), "body": public_json(body)}


def _challenge_response(response) -> bool:
    """Recognize an explicit challenge without mistaking public data for one."""
    raw = response.body() if callable(response.body) else response.body
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str):
        return False
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        text = raw[:65536]
    else:
        # Public successful data may itself mention captchas. Only GraphQL
        # error text is considered a challenge for JSON responses.
        text = json.dumps(parsed.get("errors", []))[:65536] if isinstance(parsed, dict) else ""
    return bool(CHALLENGE_PATTERN.search(text))


def replay_observed(templates: list[dict], context: dict, session, *, limit=MAX_REPLAYS) -> dict:
    """Replay a finite observed allowlist using a caller-provided HTTP session."""
    payloads, evidence, seen = [], [], set()
    stop_reason = None
    for template in templates:
        if len(evidence) >= min(MAX_REPLAYS, max(0, limit)):
            break
        method, body = template.get("method", ""), template.get("body")
        operation = read_operation(template.get("url", ""), method, body)
        if not operation:
            continue
        url = calendar_replay_url(template["url"], context) if method == "GET" else template["url"]
        try:
            identity = (method, url, json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
                        if method == "POST" else None)
        except (ValueError, TypeError):
            continue
        if identity in seen:
            continue
        seen.add(identity)
        entry = {"operation": operation, "source_url": safe_source(url),
                 "request_context": request_context(url, method, body),
                 "calendar_variables_adjusted": url != template["url"], "status": None}
        evidence.append(entry)
        try:
            options = dict(headers=deepcopy(template.get("headers", {})),
                           timeout=20, retries=1, follow_redirects=False)
            response = (session.post(url, json=deepcopy(body), **options) if method == "POST"
                        else session.get(url, **options))
        except Exception as exc:
            # Exceptions often embed full request URLs; retain the type only.
            entry["error"] = type(exc).__name__
            stop_reason = "direct_request_error"
            break
        entry["status"] = response.status
        if response.status in STOP_STATUSES:
            stop_reason = f"access_or_rate_limit_{response.status}"
            break
        if response.status != 200:
            entry["error"] = "non_success_response"
            continue
        if _challenge_response(response):
            entry["error"] = "challenge_response"
            stop_reason = "challenge_detected"
            break
        payload = _payload(response, url, method, body)
        if payload is None:
            entry["error"] = "not_json"
        else:
            payloads.append(payload)
            entry["json_captured"] = True
            if isinstance(payload["body"], dict) and payload["body"].get("errors"):
                entry["graphql_errors"] = True
    return {"payloads": payloads, "requests": evidence, "stop_reason": stop_reason}


@contextmanager
def _quiet_scrapling():
    # Scrapling's default INFO/error logging contains complete request URLs.
    # Its compiled LoggerProxy forwards reads but assigning proxy.disabled does
    # not update the underlying logger. Disable at Python's logging manager so
    # existing handlers and child loggers cannot leak request/session details.
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous)


def _script_payloads(response, listing_url: str) -> list[dict]:
    result = []
    # Extract public listing data, never whole bootstrap configuration trees.
    def public_subtrees(node):
        if isinstance(node, dict):
            for key, child in node.items():
                if key == "pdpPresentation":
                    yield {"data": {"node": {"pdpPresentation": public_json(child)}}}
                elif key in {"stayProductDetailPage", "pdpListing", "calendarMonths"}:
                    if key == "stayProductDetailPage":
                        yield {"data": {"presentation": {key: public_json(child)}}}
                    else:
                        yield {key: public_json(child)}
                else:
                    yield from public_subtrees(child)
        elif isinstance(node, list):
            for child in node:
                yield from public_subtrees(child)

    for index, script in enumerate(response.css('script[type="application/ld+json"], script[type="application/json"]')):
        try:
            node = json.loads(script.text)
        except (ValueError, TypeError):
            continue
        bodies = [public_json(node)] if script.attrib.get("type") == "application/ld+json" else list(public_subtrees(node))
        for body in bodies:
            result.append({"source_url": safe_source(listing_url) + f"#script-{index}",
                           "status": response.status, "request_context": request_context(listing_url, "GET"), "body": body})
    return result


def collect(context: dict, *, headless=True, template_sink: list | None = None) -> dict:
    """One fresh anonymous browser visit, followed by at most eight public reads."""
    context = validate_context(context)
    report = {"transport": "scrapling", "browser_navigations": 0,
              "browser_status": None, "captured_operations": [],
              "observed_api_operations": [],
              "direct_replay": {"requests": [], "stop_reason": None},
              "warnings": [], "stop_reason": None}
    payloads, templates, blocked, operations, all_operations = [], [], [], set(), set()
    query = {k: context[k] for k in ("adults", "children", "infants", "pets", "currency")}
    query.update(check_in=context["checkin"], check_out=context["checkout"], locale=context["locale"])
    listing_url = f'https://www.airbnb.com/rooms/{context["listing_id"]}?{urlencode(query)}'
    try:
        from scrapling.fetchers import DynamicSession, FetcherSession
    except ImportError:
        report["stop_reason"] = "scrapling_dependency_missing"
        return {"payloads": [], "report": report}

    def setup(page):
        def request_body(request):
            if request.method != "POST":
                return None
            try:
                return request.post_data_json
            except Exception:
                return None

        def request_seen(request):
            observed = observed_operation_name(request.url, request.method)
            if observed:
                all_operations.add(observed)
            body = request_body(request)
            operation = read_operation(request.url, request.method, body)
            if operation:
                operations.add(operation)
                all_operations.add(operation)
                if len(templates) < 30:
                    headers = request.all_headers()
                    # Host/length/compression belong to the HTTP client.
                    headers = {k: v for k, v in headers.items()
                               if k.lower() not in {"host", "content-length", "accept-encoding"}}
                    template = {"url": request.url, "method": request.method, "headers": headers}
                    if request.method == "POST":
                        template["body"] = deepcopy(body)
                    templates.append(template)

        def response_seen(response):
            request = response.request
            if response.status in STOP_STATUSES and (
                    read_operation(request.url, request.method, request_body(request))
                    or urlsplit(response.url).path == urlsplit(listing_url).path):
                blocked.append(response.status)

        def request_finished(request):
            # Request.response() belongs to this exact request. A URL->body map
            # would mislabel concurrent Sections POSTs sharing an endpoint.
            body = request_body(request)
            if not read_operation(request.url, request.method, body):
                return
            try:
                response = request.response()
                if response is not None and response.status == 200:
                    if _challenge_response(response):
                        report["stop_reason"] = "challenge_detected"
                        return
                    payload = _payload(response, request.url, request.method, body)
                    if payload is not None:
                        payloads.append(payload)
            except Exception as exc:
                errors = report.setdefault("capture_errors", [])
                if type(exc).__name__ not in errors:
                    errors.append(type(exc).__name__)

        page.on("request", request_seen)
        page.on("response", response_seen)
        page.on("requestfinished", request_finished)

    def action(page):
        page.wait_for_timeout(4500)
        if blocked or report["stop_reason"] or any("Calendar" in name for name in operations):
            return
        # Only click a date-picker control that is present and identifies itself
        # as check-in. No booking, contact, login or consent actions.
        for button in page.locator("button").all()[:100]:
            label = (button.get_attribute("aria-label") or button.inner_text()).strip().lower()
            testid = button.get_attribute("data-testid") or ""
            if re.search(r"check.?in|check.?out|choose dates|change dates|calendar", label):
                report.setdefault("observed_date_controls", []).append(label[:120])
            if is_date_control(label, testid):
                if button.is_visible() and button.is_enabled():
                    button.click(timeout=2000)
                    page.wait_for_timeout(2500)
                    report["calendar_control_opened"] = True
                    break

    with _quiet_scrapling():
        try:
            browser_options = {}
            system_chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
            if system_chrome.exists():
                browser_options["executable_path"] = str(system_chrome)
            with DynamicSession(headless=headless, capture_xhr=CAPTURE_PATTERN,
                                retries=1, timeout=45000, locale=context["locale"],
                                timezone_id="Asia/Dubai", google_search=False, **browser_options) as browser:
                report["browser_navigations"] = 1
                response = browser.fetch(listing_url, page_setup=setup, page_action=action,
                                         network_idle=False, wait=1000)
                report["browser_status"] = response.status
                report["page_title"] = str(response.css("title::text").get() or "")[:240]
                if response.status in STOP_STATUSES:
                    blocked.append(response.status)
                elif response.status in {404, 410}:
                    report["stop_reason"] = "listing_unavailable"
                elif response.status >= 400:
                    report["stop_reason"] = "browser_http_error"
                if response.status == 200:
                    payloads.extend(_script_payloads(response, response.url))
        except Exception as exc:
            report["browser_error"] = type(exc).__name__
            report["stop_reason"] = "browser_error"
        report["captured_operations"] = sorted(operations)
        report["observed_api_operations"] = sorted(all_operations)
        if blocked:
            report["stop_reason"] = f"access_or_rate_limit_{blocked[0]}"
        elif report["stop_reason"] is None and templates:
            try:
                with FetcherSession(retries=1, timeout=20, stealthy_headers=False,
                                    impersonate=None, follow_redirects=False) as session:
                    replay = replay_observed(templates, context, session)
                payloads.extend(replay.pop("payloads"))
                report["direct_replay"] = replay
                report["stop_reason"] = replay["stop_reason"]
            except Exception as exc:
                report["stop_reason"] = "direct_session_error"
                report["direct_error"] = type(exc).__name__
        elif not templates:
            report["warnings"].append("No replayable public PDP/calendar request was observed.")
    report["payload_count"] = len(payloads)
    differences = []
    for payload in payloads:
        for key, observed in payload.get("request_context", {}).items():
            if key in context and observed != context[key]:
                difference = {"field": key, "requested": context[key], "observed": observed}
                if difference not in differences:
                    differences.append(difference)
    report["request_context_differences"] = differences
    conflicts = sorted({key for payload in payloads
                        for key in payload.get("request_context", {}).get("conflicts", [])})
    if conflicts:
        report["request_context_conflicts"] = conflicts
        report["warnings"].append("Observed request parameters conflict; affected fields are unverified.")
    if differences:
        report["warnings"].append("Observed request parameters differ from requested context; inspect request_context_differences.")
    if template_sink is not None and report.get("stop_reason") is None:
        # Explicit in-process handoff only. Never attach these secrets to the
        # returned capture/report, JSON checkpoints or exception diagnostics.
        template_sink.extend(deepcopy(templates))
    return {"payloads": payloads, "report": report}
