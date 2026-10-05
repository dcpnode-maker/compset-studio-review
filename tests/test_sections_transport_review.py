"""Independent offline proof of the new observed Sections POST transport."""
import base64
from copy import deepcopy
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from compset.batch import retarget_template
from compset.collect import collect, read_operation, replay_observed, request_context

HASH = "a" * 64
URL = f"https://www.airbnb.com/api/v3/StaysPdpSections/{HASH}?locale=en-IN&currency=AED"


def context(**changes):
    return {"listing_id": "123456", "checkin": "2030-09-30", "checkout": "2030-10-01",
            "adults": 1, "children": 0, "infants": 0, "pets": 0, "currency": "AED", "locale": "en",
            "start_date": "2030-09-28", "end_date": "2030-10-28", **changes}


def template(*, adults=1):
    return {"method": "POST", "url": URL, "headers": {"Cookie": "memory-only-credential"}, "body": {
        "operationName": "StaysPdpSections", "variables": {
            "id": base64.b64encode(b"StayListing:123456").decode(),
            "pdpSectionsRequest": {"adults": str(adults), "children": "0", "infants": "0", "pets": 0,
                                   "checkIn": "2030-09-30", "checkOut": "2030-10-01"},
            "dateRange": {"startDate": "2030-09-30", "endDate": "2030-10-01"},
            "guestCounts": {"numberOfAdults": adults, "numberOfChildren": 0, "numberOfInfants": 0, "numberOfPets": 0},
            "numberOfChildren": 0, "numberOfInfants": 0, "numberOfPets": 0,
            "priceHeatmapDateRange": {"startDate": "2030-09-28", "endDate": "2030-10-28"},
            "hostId": "123456", "observedFlag": True},
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": HASH}}}}


class SectionsTransportReviewTests(unittest.TestCase):
    def test_post_rejects_mutations_extra_documents_and_conflicting_hashes(self):
        valid = template()
        self.assertEqual(read_operation(URL, "POST", valid["body"]), "StaysPdpSections")
        cases = []
        bad = deepcopy(valid); bad["body"]["query"] = "mutation { createReservation }"; cases.append(bad)
        bad = deepcopy(valid); bad["body"]["operationName"] = "CreateReservation"; cases.append(bad)
        bad = deepcopy(valid); bad["body"]["extensions"]["persistedQuery"]["sha256Hash"] = "b" * 64; cases.append(bad)
        bad = deepcopy(valid); bad["url"] += "&operationName=StaysPdpSections&operationName=CreateReservation"; cases.append(bad)
        bad = deepcopy(valid); bad["url"] += "&variables=%7B%7D"; cases.append(bad)
        bad = deepcopy(valid); bad["url"] = URL.replace("www.airbnb.com", "evil.example"); cases.append(bad)
        for case in cases:
            self.assertIsNone(read_operation(case["url"], case["method"], case["body"]))

    def test_duplicate_disagreement_and_invalid_aliases_remove_disputed_fields(self):
        for field, change in (("adults", {"numberOfAdults": 2}), ("children", {"numberOfChildren": True}),
                              ("infants", {"numberOfInfants": -1}), ("pets", {"numberOfPets": None})):
            observed = template(); observed["body"]["variables"]["guestCounts"].update(change)
            actual = request_context(URL, "POST", observed["body"])
            self.assertNotIn(field, actual)
            self.assertIn(field, actual["conflicts"])
        observed = template(); observed["body"]["variables"]["dateRange"]["endDate"] = "2030-10-02"
        actual = request_context(URL + "&currency=USD", "POST", observed["body"])
        self.assertEqual(set(actual["conflicts"]), {"checkout", "currency"})
        self.assertNotIn("checkout", actual); self.assertNotIn("currency", actual)
        self.assertEqual(actual["checkin"], "2030-09-30")
        self.assertNotIn("memory-only", json.dumps(actual))

    def test_distinct_bodies_are_not_deduplicated_or_mutated(self):
        first, second = template(), template(adults=2)
        before = deepcopy([first, second]); calls = []
        class HTTP:
            def post(self, url, **kwargs):
                calls.append(deepcopy(kwargs))
                kwargs["json"]["variables"]["guestCounts"]["numberOfAdults"] = 15
                kwargs["headers"]["Cookie"] = "client-mutated"
                return SimpleNamespace(status=200, body=b'{"data":{"ok":true}}')
        result = replay_observed([first, second, deepcopy(first)], context(), HTTP())
        self.assertEqual(len(calls), 2)
        self.assertEqual([p["request_context"]["adults"] for p in result["payloads"]], [1, 2])
        self.assertEqual([first, second], before)
        self.assertNotIn("memory-only-credential", json.dumps(result))

    def test_html_challenge_stops_before_a_second_post(self):
        calls = []
        class HTTP:
            def post(self, url, **kwargs):
                calls.append(url)
                return SimpleNamespace(status=200, body=b'<html>CAPTCHA: verify you are human</html>')
        result = replay_observed([template(), template(adults=2)], context(), HTTP())
        self.assertEqual(len(calls), 1)
        self.assertTrue(result["stop_reason"])
        self.assertEqual(result["payloads"], [])

    def test_post_access_block_has_no_followup_and_no_error_body(self):
        for status in (401, 403, 429):
            calls = []
            class HTTP:
                def post(self, url, **kwargs):
                    calls.append(url)
                    return SimpleNamespace(status=status, body=b'private diagnostic')
            result = replay_observed([template(), template(adults=2)], context(), HTTP())
            self.assertEqual(len(calls), 1)
            self.assertEqual(result["payloads"], [])
            self.assertEqual(result["stop_reason"], f"access_or_rate_limit_{status}")

    def test_browser_post_challenge_blocks_actions_replay_and_template_export(self):
        observed = template(); calls = []
        request = SimpleNamespace(url=URL, method="POST", post_data_json=observed["body"],
                                  all_headers=lambda: observed["headers"])
        response = SimpleNamespace(status=200, url=URL, request=request,
                                   body=lambda: b"<html>Verify you are human: CAPTCHA</html>")
        request.response = lambda: response
        class Browser:
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def fetch(self, url, **kwargs):
                handlers = {}
                page = SimpleNamespace(on=lambda name, handler: handlers.__setitem__(name, handler),
                    wait_for_timeout=lambda milliseconds: None,
                    locator=lambda selector: (calls.append("date-control-search") or SimpleNamespace(all=lambda: [])))
                kwargs["page_setup"](page)
                handlers["request"](request)
                handlers["response"](response)
                handlers["requestfinished"](request)
                kwargs["page_action"](page)
                return SimpleNamespace(status=200, url=url,
                    css=lambda selector: SimpleNamespace(get=lambda: "Public title") if selector == "title::text" else [])
        class HTTP:
            def __init__(self, **kwargs):
                calls.append("http-client-created")
                raise AssertionError("No replay allowed after a browser challenge")
        sink = []
        with patch.dict(sys.modules, {"scrapling.fetchers": SimpleNamespace(DynamicSession=Browser, FetcherSession=HTTP)}):
            result = collect(context(), template_sink=sink)
        self.assertEqual(calls, [])
        self.assertEqual(sink, [])
        self.assertIn("challenge", result["report"]["stop_reason"])
        self.assertEqual(result["payloads"], [])

    def test_same_url_out_of_order_responses_keep_their_own_post_context(self):
        first, second = template(), template(adults=2)
        requests = []
        for observed, marker in ((first, "one-adult-response"), (second, "two-adult-response")):
            request = SimpleNamespace(url=observed["url"], method="POST", post_data_json=observed["body"],
                                      all_headers=lambda: {"Cookie": "memory-only-credential"})
            response = SimpleNamespace(status=200, url=request.url, request=request,
                                       body=lambda marker=marker: json.dumps({"data": {"marker": marker}}).encode())
            request.response = lambda response=response: response
            requests.append(request)
        class Browser:
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def fetch(self, url, **kwargs):
                handlers = {}
                kwargs["page_setup"](SimpleNamespace(on=lambda name, handler: handlers.__setitem__(name, handler)))
                for request in requests: handlers["request"](request)
                for request in reversed(requests):
                    handlers["response"](request.response())
                    handlers["requestfinished"](request)
                return SimpleNamespace(status=200, url=url, captured_xhr=[],
                    css=lambda selector: SimpleNamespace(get=lambda: "Public title") if selector == "title::text" else [])
        class HTTP:
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def post(self, url, **kwargs):
                return SimpleNamespace(status=200, body=b'{"data":{"marker":"replay"}}')
        with patch.dict(sys.modules, {"scrapling.fetchers": SimpleNamespace(DynamicSession=Browser, FetcherSession=HTTP)}):
            result = collect(context())
        matched = {p["body"]["data"]["marker"]: p["request_context"]["adults"] for p in result["payloads"]
                   if p["body"]["data"].get("marker") != "replay"}
        self.assertEqual(matched, {"one-adult-response": 1, "two-adult-response": 2})
        self.assertNotIn("memory-only-credential", json.dumps(result))

    def test_post_retarget_preserves_source_hash_types_and_unrelated_context(self):
        original = template(); before = deepcopy(original)
        updated = retarget_template(original, "123456", context(listing_id="654321", checkin="2030-10-02", checkout="2030-10-03"))
        actual = request_context(updated["url"], updated["method"], updated["body"])
        self.assertEqual(actual["listing_id"], "654321")
        self.assertEqual(actual["checkin"], "2030-10-02")
        self.assertEqual(actual["checkout"], "2030-10-03")
        self.assertEqual(actual["adults"], 1)
        self.assertNotIn("conflicts", actual)
        self.assertEqual(updated["body"]["extensions"], before["body"]["extensions"])
        self.assertEqual(updated["body"]["variables"]["hostId"], "123456")
        self.assertEqual(updated["body"]["variables"]["priceHeatmapDateRange"], before["body"]["variables"]["priceHeatmapDateRange"])
        self.assertEqual(base64.b64decode(updated["body"]["variables"]["id"]).decode(), "StayListing:654321")
        self.assertEqual(original, before)

    def test_post_retarget_refuses_conflicting_original_guest_dates_and_id(self):
        for mutate in (
            lambda v: v["guestCounts"].update(numberOfAdults=2),
            lambda v: v["dateRange"].update(endDate="2030-10-02"),
            lambda v: v.update(listingId="654321"),
        ):
            original = template(); mutate(original["body"]["variables"])
            with self.assertRaises(ValueError):
                retarget_template(original, "123456", context(listing_id="654321"))


if __name__ == "__main__":
    unittest.main()
