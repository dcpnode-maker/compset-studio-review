import json
import base64
import logging
import sys
from io import StringIO
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode, urlsplit, parse_qs

from compset.collect import (MAX_REPLAYS, calendar_replay_url, collect,
    public_json, read_operation, replay_observed, safe_source, validate_context,
    _quiet_scrapling, _script_payloads, observed_operation_name, is_date_control, request_context)


def context(**changes):
    result = dict(listing_id="123456", checkin="2026-10-12", checkout="2026-10-15",
        start_date="2026-09-28", end_date="2026-12-27", adults=2, children=0,
        infants=0, pets=0, currency="AED", locale="en")
    result.update(changes)
    return result


def template(index=0, operation="StaysPdpAvailabilityCalendar"):
    query = urlencode({"operationName": operation, "variables": json.dumps({
        "request": {"listingId": "123456", "month": 10, "year": 2026, "count": 2}}),
        "extensions": json.dumps({"persistedQuery": {"sha256Hash": "abc"}}), "index": index})
    return {"url": f"https://www.airbnb.com/api/v3/{operation}/abc?{query}",
            "method": "GET", "headers": {"x-airbnb-api-key": "in-memory-only"}}


class FakeSession:
    def __init__(self, status=200, body=None, error=None):
        self.calls = []
        self.status = status
        self.body = body if body is not None else b'{"data":{"calendarMonths":[]}}'
        self.error = error

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return SimpleNamespace(status=self.status, body=self.body)


class CollectionTests(unittest.TestCase):
    def test_template_sink_is_ephemeral_and_not_returned_or_filled_after_block(self):
        observed = template()
        class Browser:
            status = 200
            def __init__(self, **kwargs):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def fetch(self, url, **kwargs):
                def on(event, handler):
                    if event == "request":
                        handler(SimpleNamespace(url=observed["url"], method="GET",
                                                all_headers=lambda: observed["headers"]))
                kwargs["page_setup"](SimpleNamespace(on=on))
                return SimpleNamespace(status=self.status, url=url, captured_xhr=[],
                    css=lambda selector: SimpleNamespace(get=lambda: "Public title") if selector == "title::text" else [])
        class HTTP(FakeSession):
            def __init__(self, **kwargs):
                super().__init__()
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        fake = SimpleNamespace(DynamicSession=Browser, FetcherSession=HTTP)
        with patch.dict(sys.modules, {"scrapling.fetchers": fake}):
            sink = []
            result = collect(context(), template_sink=sink)
            self.assertEqual(len(sink), 1)
            self.assertEqual(sink[0]["headers"]["x-airbnb-api-key"], "in-memory-only")
            self.assertNotIn("in-memory-only", json.dumps(result))
            sink[0]["headers"]["x-airbnb-api-key"] = "changed"
            self.assertEqual(observed["headers"]["x-airbnb-api-key"], "in-memory-only")
            Browser.status = 403
            blocked_sink = []
            blocked = collect(context(), template_sink=blocked_sink)
            self.assertEqual(blocked_sink, [])
            self.assertEqual(blocked["report"]["stop_reason"], "access_or_rate_limit_403")

    def test_context_rejects_bad_dates_ids_guests_and_large_range(self):
        for patch in ({"listing_id": "../../etc"}, {"checkout": "2026-10-12"},
                      {"adults": True}, {"adults": 0}, {"currency": "aed"},
                      {"end_date": "2028-10-01"}, {"checkin": "2026-02-30"}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validate_context(context(**patch))

    def test_url_allowlist_rejects_nonpublic_targets_and_mutations(self):
        good = template()["url"]
        self.assertEqual(read_operation(good), "StaysPdpAvailabilityCalendar")
        self.assertEqual(read_operation(good.replace("airbnb.com", "airbnb.co.in")),
                         "StaysPdpAvailabilityCalendar")
        for url in (good.replace("www.airbnb.com", "www.airbnb.com.evil.com"),
                    good.replace("https://", "http://"),
                    good.replace("www.airbnb.com", "user@www.airbnb.com"),
                    good.replace("StaysPdpAvailabilityCalendar", "CreateReservation"),
                    good + "&query=mutation%20Booking", good.replace("/api/v3/", "/api/v2/")):
            self.assertIsNone(read_operation(url))
        self.assertIsNone(read_operation(good, "POST"))

    def test_calendar_updates_observed_variables_and_preserves_hash(self):
        original = template()["url"]
        updated = calendar_replay_url(original, context())
        query = parse_qs(urlsplit(updated).query)
        request = json.loads(query["variables"][0])["request"]
        self.assertEqual(request, dict(listingId="123456", month=9, year=2026, count=4))
        self.assertEqual(query["extensions"], parse_qs(urlsplit(original).query)["extensions"])
        no_calendar = template(operation="StaysPdpSections")["url"]
        self.assertEqual(calendar_replay_url(no_calendar, context()), no_calendar)

    def test_replay_limit_and_no_secret_diagnostics(self):
        session = FakeSession()
        result = replay_observed([template(n) for n in range(30)], context(), session, limit=1000)
        self.assertEqual(len(session.calls), MAX_REPLAYS)
        self.assertEqual(len(result["payloads"]), MAX_REPLAYS)
        self.assertNotIn("in-memory-only", json.dumps(result))
        self.assertNotIn("variables=", json.dumps(result))
        self.assertEqual(session.calls[0][1]["retries"], 1)
        self.assertFalse(session.calls[0][1]["follow_redirects"])

    def test_access_limits_stop_without_retry_or_error_body(self):
        for status in (401, 403, 429):
            session = FakeSession(status=status)
            result = replay_observed([template(0), template(1)], context(), session)
            self.assertEqual(len(session.calls), 1)
            self.assertEqual(result["payloads"], [])
            self.assertEqual(result["stop_reason"], f"access_or_rate_limit_{status}")

    def test_exception_does_not_expose_request_secrets(self):
        session = FakeSession(error=RuntimeError("https://example.com?secret=password"))
        result = replay_observed([template()], context(), session)
        self.assertEqual(result["requests"][0]["error"], "RuntimeError")
        self.assertNotIn("password", json.dumps(result))

    def test_non_json_is_unknown_not_success(self):
        result = replay_observed([template()], context(), FakeSession(body=b'<html>blocked</html>'))
        self.assertEqual(result["payloads"], [])
        self.assertEqual(result["requests"][0]["error"], "not_json")

    def test_redacts_bootstrap_secrets_and_api_query_strings(self):
        result = public_json({"title": "Public listing", "accessToken": "secret",
                              "nested": [{"cookie": "secret", "price": 100}],
                              "endpoint": "https://www.airbnb.com/api/v3/PdpSections?token=secret"})
        self.assertEqual(result["nested"], [{"price": 100}])
        self.assertNotIn("secret", json.dumps(result))
        self.assertEqual(safe_source(template()["url"]),
                         "https://www.airbnb.com/api/v3/StaysPdpAvailabilityCalendar/abc")

    def test_duplicate_and_non_read_requests_are_not_replayed(self):
        session = FakeSession()
        invalid = template()
        invalid["method"] = "POST"
        result = replay_observed([invalid, template(), template()], context(), session)
        self.assertEqual(len(result["requests"]), 1)

    def test_bootstrap_extraction_keeps_public_subtree_not_config(self):
        scripts = [SimpleNamespace(
            text=json.dumps({"config": {"apiKey": "private"}, "bootstrap": [
                {"data": {"presentation": {"stayProductDetailPage": {
                    "title": "Public apartment", "sessionToken": "private"}}}}]}),
            attrib={"type": "application/json"})]
        response = SimpleNamespace(status=200, css=lambda selector: scripts)
        result = _script_payloads(response, "https://www.airbnb.com/rooms/123?secret=private")
        self.assertEqual(result[0]["body"], {"data": {"presentation": {
            "stayProductDetailPage": {"title": "Public apartment"}}}})
        self.assertNotIn("private", json.dumps(result))

    def test_book_it_read_keeps_observed_flags_and_dates(self):
        original = template(operation="StaysPdpBookItQuery")
        session = FakeSession()
        result = replay_observed([original], context(), session)
        self.assertEqual(len(result["requests"]), 1)
        self.assertEqual(session.calls[0][0], original["url"])

    def test_unknown_operations_are_named_but_never_replayed(self):
        url = "https://www.airbnb.co.in/api/v3/NewCalendarRead/hash?deviceId=secret"
        self.assertEqual(observed_operation_name(url, "GET"), "NewCalendarRead")
        self.assertIsNone(read_operation(url))
        self.assertIsNone(observed_operation_name(url, "POST"))
        self.assertIsNone(observed_operation_name(url.replace("airbnb.co.in", "evil.com"), "GET"))

    def test_observed_date_label_is_strict_and_dates_are_valid(self):
        self.assertTrue(is_date_control("change dates; check-in: 2026-10-17; checkout: 2026-10-20"))
        self.assertFalse(is_date_control("change dates; check-in: 2026-02-30; checkout: 2026-10-20"))
        self.assertFalse(is_date_control("reserve; change dates; check-in: 2026-10-17; checkout: 2026-10-20"))

    def test_request_context_records_actual_locale_dates_guests_without_secrets(self):
        variables = {"id": base64.b64encode(b"DemandStayListing:123456").decode(),
                     "dateRange": {"startDate": "2026-10-17", "endDate": "2026-10-20"},
                     "guestCounts": {"numberOfAdults": 2, "numberOfChildren": 1, "numberOfInfants": 0, "numberOfPets": 0},
                     "priceHeatmapDateRange": {"startDate": "2026-09-28", "endDate": "2026-12-27"},
                     "accessToken": "secret"}
        url = "https://www.airbnb.co.in/api/v3/StaysPdpBookItQuery/hash?" + urlencode({
            "locale": "en-IN", "currency": "AED", "variables": json.dumps(variables), "key": "secret"})
        self.assertEqual(request_context(url), {"locale": "en-IN", "currency": "AED", "listing_id": "123456",
            "checkin": "2026-10-17", "checkout": "2026-10-20", "adults": 2, "children": 1, "infants": 0, "pets": 0})

    def test_library_and_child_logger_messages_are_suppressed_then_restored(self):
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("scrapling.test_secret")
        previous_level = logger.level
        previous_disable = logging.root.manager.disable
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        try:
            with _quiet_scrapling():
                logger.info("https://example.com?session=secret")
                logger.error("headers contain cookie=secret")
            self.assertEqual(stream.getvalue(), "")
            self.assertEqual(logging.root.manager.disable, previous_disable)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)


if __name__ == "__main__":
    unittest.main()
