"""Offline regressions for the single observed persisted Sections POST read."""
import base64
from copy import deepcopy
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from compset.batch import retarget_template
from compset.collect import collect, read_operation, replay_observed, request_context
from tests.test_collect import context


HASH = "6" * 64  # Synthetic observed fixture; production never supplies a hash.


def sections_template():
    return {
        "url": f"https://www.airbnb.co.in/api/v3/StaysPdpSections/{HASH}?" +
               urlencode({"currency": "AED", "locale": "en-IN"}),
        "method": "POST", "headers": {"x-airbnb-api-key": "MEMORY-ONLY-SECRET"},
        "body": {
            "operationName": "StaysPdpSections",
            "extensions": {"persistedQuery": {"version": 1, "sha256Hash": HASH}},
            "variables": {
                "id": base64.b64encode(b"StayListing:123456").decode(),
                "pdpSectionsRequest": {"adults": "2", "children": "0", "infants": "0", "pets": 0,
                                       "checkIn": "2026-10-12", "checkOut": "2026-10-15"},
                "dateRange": {"startDate": "2026-10-12", "endDate": "2026-10-15"},
                "guestCounts": {"numberOfAdults": 2, "numberOfChildren": 0,
                                "numberOfInfants": 0, "numberOfPets": 0},
                "numberOfChildren": 0, "numberOfInfants": 0, "numberOfPets": 0,
                "flags": {"observedFlag": False}, "hostId": "123456",
                "priceHeatmapDateRange": {"startDate": "2026-09-28", "endDate": "2026-12-27"},
            },
        },
    }


class PostSession:
    def __init__(self, status=200, error=None, body=b'{"data":{"public":true}}', **kwargs):
        self.calls, self.status, self.error, self.body = [], status, error, body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return SimpleNamespace(status=self.status, body=self.body)


class SectionsTransportTests(unittest.TestCase):
    def test_only_exact_observed_sections_post_shape_qualifies(self):
        t = sections_template()
        self.assertEqual(read_operation(t["url"], "POST", t["body"]), "StaysPdpSections")
        for body in (None, [], {}, {**t["body"], "query": "mutation Booking"},
                     {**t["body"], "operationName": "CreateReservation"},
                     {**t["body"], "variables": []}, {**t["body"], "extensions": []},
                     {**t["body"], "extensions": {"persistedQuery": None}},
                     {**t["body"], "extensions": {"persistedQuery": {"sha256Hash": "7" * 64}}}):
            with self.subTest(body=body):
                self.assertIsNone(read_operation(t["url"], "POST", body))
        for url in (t["url"].replace("StaysPdpSections", "StaysPdpBookItQuery"),
                    t["url"].replace("airbnb.co.in", "airbnb.co.in.example.com"),
                    t["url"].replace(HASH, "guessed"), t["url"] + "&query=query%20PublicRead",
                    t["url"] + "&operationName=CreateReservation", t["url"] + "&variables=%7B%7D"):
            self.assertIsNone(read_operation(url, "POST", t["body"]))
        # Unspecified extension structure is kept observed, not fabricated.
        self.assertEqual(read_operation(t["url"], "POST", {**t["body"], "extensions": {}}), "StaysPdpSections")

    def test_context_extracts_only_public_values_and_both_encoded_id_types(self):
        t = sections_template()
        expected = {key: context()[key] for key in
                    ("listing_id", "checkin", "checkout", "adults", "children", "infants", "pets", "currency")}
        expected.update(method="POST", locale="en-IN")
        for prefix in ("StayListing", "DemandStayListing"):
            t["body"]["variables"]["id"] = base64.b64encode(f"{prefix}:123456".encode()).decode()
            actual = request_context(t["url"], "POST", t["body"])
            self.assertEqual(actual, expected)
            self.assertNotIn(HASH, json.dumps(actual))

    def test_duplicate_fields_conflict_instead_of_last_value_winning(self):
        changes = [
            ("checkin", lambda v: v["dateRange"].update(startDate="2026-10-13")),
            ("checkout", lambda v: v["dateRange"].update(endDate="2026-10-16")),
            ("adults", lambda v: v["guestCounts"].update(numberOfAdults=1)),
            ("children", lambda v: v.update(numberOfChildren=True)),
            ("listing_id", lambda v: v.update(listingId="999999")),
            ("pets", lambda v: v["pdpSectionsRequest"].update(pets="unknown")),
        ]
        for key, mutate in changes:
            t = sections_template()
            mutate(t["body"]["variables"])
            observed = request_context(t["url"], "POST", t["body"])
            with self.subTest(key=key):
                self.assertIn(key, observed["conflicts"])
                self.assertNotIn(key, observed)
                with self.assertRaises(ValueError):
                    retarget_template(t, "123456", context())
        t = sections_template()
        observed = request_context(t["url"] + "&currency=USD&locale=en", "POST", t["body"])
        self.assertEqual(observed["conflicts"], ["currency", "locale"])
        self.assertNotIn("currency", observed)

    def test_retarget_preserves_observed_hash_flags_guests_and_original(self):
        t = sections_template()
        original = deepcopy(t)
        target = context(listing_id="987654", checkin="2026-10-17", checkout="2026-10-18")
        updated = retarget_template(t, "123456", target)
        observed = request_context(updated["url"], updated["method"], updated["body"])
        for key in ("listing_id", "checkin", "checkout", "adults", "children", "infants", "pets", "currency"):
            self.assertEqual(observed[key], target[key])
        self.assertEqual(updated["body"]["extensions"], original["body"]["extensions"])
        for key in ("guestCounts", "flags", "hostId", "priceHeatmapDateRange"):
            self.assertEqual(updated["body"]["variables"][key], original["body"]["variables"][key])
        self.assertEqual(t, original)
        updated["body"]["variables"]["guestCounts"]["numberOfAdults"] = 8
        updated["headers"]["x-airbnb-api-key"] = "changed"
        self.assertEqual(t, original)

    def test_retarget_requires_existing_full_party_currency_dates_and_source(self):
        t = sections_template()
        for changes in ({"adults": 1}, {"children": 1}, {"infants": 1}, {"pets": 1}, {"currency": "USD"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                retarget_template(t, "123456", context(**changes))
        with self.assertRaises(ValueError):
            retarget_template(t, "000000", context())
        missing = deepcopy(t)
        missing["url"] = missing["url"].split("?")[0]
        with self.assertRaises(ValueError):
            retarget_template(missing, "123456", context())
        missing = deepcopy(t)
        del missing["body"]["variables"]["dateRange"]
        del missing["body"]["variables"]["pdpSectionsRequest"]["checkIn"]
        with self.assertRaises(ValueError):
            retarget_template(missing, "123456", context())

    def test_replay_deduplicates_exact_body_but_not_different_date_bodies(self):
        t = sections_template()
        second = retarget_template(t, "123456", context(checkin="2026-10-17", checkout="2026-10-18"))
        session = PostSession()
        result = replay_observed([t, deepcopy(t), second], context(), session)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[0][1]["json"], t["body"])
        self.assertEqual([p["request_context"]["checkin"] for p in result["payloads"]],
                         ["2026-10-12", "2026-10-17"])
        self.assertTrue(all(p["request_context"]["method"] == "POST" for p in result["payloads"]))
        self.assertNotIn("MEMORY-ONLY-SECRET", json.dumps(result))
        self.assertNotIn("persistedQuery", json.dumps(result))
        self.assertNotIn("?", result["requests"][0]["source_url"])
        self.assertEqual(session.calls[0][1]["retries"], 1)
        self.assertFalse(session.calls[0][1]["follow_redirects"])

    def test_replay_is_bounded_and_stops_on_access_limits_and_transport_errors(self):
        t = sections_template()
        templates = [retarget_template(t, "123456", context(checkin=f"2026-10-{n:02}", checkout=f"2026-10-{n+1:02}"))
                     for n in range(1, 12)]
        session = PostSession()
        result = replay_observed(templates, context(), session, limit=1000)
        self.assertEqual(len(session.calls), 8)
        for status in (401, 403, 429):
            session = PostSession(status=status)
            result = replay_observed(templates, context(), session)
            self.assertEqual(len(session.calls), 1)
            self.assertEqual(result["payloads"], [])
            self.assertEqual(result["stop_reason"], f"access_or_rate_limit_{status}")
        session = PostSession(error=RuntimeError("MEMORY-ONLY-SECRET"))
        result = replay_observed(templates, context(), session)
        self.assertEqual(result["stop_reason"], "direct_request_error")
        self.assertEqual(len(session.calls), 1)
        self.assertNotIn("MEMORY-ONLY-SECRET", json.dumps(result))

    def test_nonjson_and_graphql_error_outcomes_remain_visible(self):
        for body, error in ((b"not-json", "not_json"), (b'{"errors":[{"message":"unavailable"}]}', None)):
            result = replay_observed([sections_template()], context(), PostSession(body=body))
            if error:
                self.assertEqual(result["requests"][0]["error"], error)
            else:
                self.assertTrue(result["requests"][0]["graphql_errors"])

    def test_explicit_challenges_stop_before_next_request_without_saving_body(self):
        first = sections_template()
        second = retarget_template(first, "123456", context(checkin="2026-10-17", checkout="2026-10-18"))
        for body in (b'<html><title>Verify you are human</title>MEMORY-ONLY-SECRET</html>',
                     b'{"errors":[{"message":"CAPTCHA required MEMORY-ONLY-SECRET"}]}'):
            session = PostSession(body=body)
            result = replay_observed([first, second], context(), session)
            self.assertEqual(result["stop_reason"], "challenge_detected")
            self.assertEqual(len(session.calls), 1)
            self.assertEqual(result["payloads"], [])
            self.assertNotIn("MEMORY-ONLY-SECRET", json.dumps(result))
        session = PostSession(body=b'{"data":{"captchaLabel":"Public description"}}')
        self.assertIsNone(replay_observed([first], context(), session)["stop_reason"])

    def test_browser_response_is_bound_to_exact_request_when_completion_order_reverses(self):
        first = sections_template()
        second = retarget_template(first, "123456", context(checkin="2026-10-17", checkout="2026-10-18"))

        class Browser:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def fetch(self, url, **kwargs):
                handlers = {}
                kwargs["page_setup"](SimpleNamespace(on=lambda event, callback: handlers.update({event: callback})))
                requests = []
                for marker, template in (("first", first), ("second", second)):
                    request = SimpleNamespace(url=template["url"], method="POST", post_data_json=template["body"],
                                              all_headers=lambda: first["headers"])
                    response = SimpleNamespace(status=200, url=request.url, request=request,
                                               body=lambda marker=marker: json.dumps({"marker": marker}).encode())
                    request.response = lambda response=response: response
                    handlers["request"](request)
                    requests.append(request)
                for request in reversed(requests):
                    handlers["response"](request.response())
                    handlers["requestfinished"](request)
                return SimpleNamespace(status=200, url=url, captured_xhr=[],
                    css=lambda selector: SimpleNamespace(get=lambda: "Fixture") if selector == "title::text" else [])

        with patch.dict(sys.modules, {"scrapling.fetchers": SimpleNamespace(DynamicSession=Browser, FetcherSession=PostSession)}):
            sink = []
            result = collect(context(), template_sink=sink)
        markers = {p["body"]["marker"]: p["request_context"]["checkin"]
                   for p in result["payloads"] if "marker" in p["body"]}
        self.assertEqual(markers, {"first": "2026-10-12", "second": "2026-10-17"})
        self.assertEqual(len(sink), 2)
        self.assertEqual(sink[0]["body"], first["body"])
        self.assertEqual(result["report"]["captured_operations"], ["StaysPdpSections"])
        self.assertNotIn("MEMORY-ONLY-SECRET", json.dumps(result))
        self.assertNotIn("persistedQuery", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
