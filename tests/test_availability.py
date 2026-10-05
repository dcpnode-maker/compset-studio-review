from copy import deepcopy
import json
from pathlib import Path
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from compset.availability import calendar_preflight
from compset.batch import _fetch_one, monitor_compset
from compset.collect import request_context
from tests.test_batch import FakeSession, fake_bootstrap, quote_template, setup_snapshot
from tests.test_collect import context, template


def payload(days, **changes):
    result = {"status": 200, "source_url": "https://www.airbnb.com/api/v3/StaysPdpAvailabilityCalendar/hash",
              "request_context": {"listing_id": "123456", "calendar_year": 2026,
                                  "calendar_month": 10, "calendar_month_count": 1},
              "body": {"data": {"merlin": {"pdpAvailabilityCalendar": {"calendarMonths": [
                  {"listingId": "123456", "days": days}]}}}}}
    result.update(changes)
    return result


def days():
    return [{"calendarDate": f"2026-10-{number}", "available": True,
             "availableForCheckin": True, "availableForCheckout": True} for number in range(12, 16)]


class CalendarSession(FakeSession):
    calendar_days = [{"calendarDate": "2026-10-12", "available": False}]
    errors = False

    def get(self, url, **kwargs):
        response = super().get(url, **kwargs)
        if "Calendar" not in url or response.status != 200:
            return response
        body = payload(deepcopy(self.calendar_days))["body"]
        body["data"]["merlin"]["pdpAvailabilityCalendar"]["calendarMonths"][0]["listingId"] = request_context(url)["listing_id"]
        if self.errors:
            body["errors"] = [{"message": "Calendar schema failed"}]
        return SimpleNamespace(status=200, body=json.dumps(body).encode())


class AvailabilityTests(unittest.TestCase):
    def test_unavailable_checkout_overnight_is_not_a_sleeping_night(self):
        calendar = days()
        calendar[-1].update(available=False, availableForCheckin=False, availableForCheckout=True)
        result = calendar_preflight([payload(calendar)], context())
        self.assertEqual(result["decision"], "proceed_quote")
        self.assertEqual(result["evidence"], [])

    def test_typed_blocked_sleeping_night_has_context_and_source_evidence(self):
        calendar = days()
        calendar[1]["available"] = False
        source = payload(calendar)
        original = deepcopy(source)
        result = calendar_preflight([source], context(observed_at="2026-09-28T00:00:00+00:00"))
        self.assertEqual(source, original)
        self.assertEqual(result["decision"], "skip_quote")
        self.assertEqual(result["result"], "unavailable_for_context")
        self.assertEqual(result["reason"], "sleeping_night_unavailable")
        self.assertFalse(result["retryable"])
        evidence = result["evidence"][0]
        self.assertEqual(evidence["date"], "2026-10-13")
        self.assertIs(evidence["value"], False)
        self.assertEqual(evidence["request_context"]["listing_id"], "123456")
        self.assertEqual(evidence["http_status"], 200)
        self.assertTrue(evidence["source_path"].endswith("days[1].available"))
        self.assertNotIn("booked", json.dumps(result))

    def test_arrival_and_departure_permissions_are_distinct(self):
        for index, field, reason in ((0, "availableForCheckin", "checkin_not_allowed"),
                                     (-1, "availableForCheckout", "checkout_not_allowed")):
            with self.subTest(field=field):
                calendar = days()
                calendar[index][field] = False
                result = calendar_preflight([payload(calendar)], context())
                self.assertEqual(result["decision"], "skip_quote")
                self.assertEqual(result["reason"], reason)
                self.assertEqual(result["result"], "constraint_not_met")

    def test_minimum_and_maximum_are_checked_on_arrival_only(self):
        for field, value, reason in (("minNights", 4, "minimum_stay_not_met"),
                                     ("maxNights", 2, "maximum_stay_exceeded")):
            with self.subTest(field=field):
                calendar = days()
                calendar[0][field] = value
                result = calendar_preflight([payload(calendar)], context())
                self.assertEqual(result["reason"], reason)
                self.assertEqual(result["decision"], "skip_quote")
                calendar[0].pop(field)
                calendar[1][field] = value
                self.assertEqual(calendar_preflight([payload(calendar)], context())["decision"], "proceed_quote")
        calendar = days()
        calendar[0].update(minNights=3, maxNights=0)
        self.assertEqual(calendar_preflight([payload(calendar)], context())["decision"], "proceed_quote")

    def test_nullable_or_untyped_flags_and_missing_prices_do_not_block(self):
        for value in (None, "false", 0, "true"):
            with self.subTest(value=value):
                calendar = [{"calendarDate": "2026-10-12", "available": value,
                             "availableForCheckin": value, "availableForCheckout": value,
                             "minNights": "9", "maxNights": False, "bookable": False}]
                self.assertEqual(calendar_preflight([payload(calendar)], context())["decision"], "proceed_quote")
        self.assertEqual(calendar_preflight([payload(days())], context())["decision"], "proceed_quote")

    def test_conflicting_duplicates_or_impossible_rule_range_proceed(self):
        for field in ("available", "availableForCheckin", "minNights"):
            with self.subTest(field=field):
                first, second = days(), days()
                first[0][field] = 5 if field == "minNights" else False
                second[0][field] = 1 if field == "minNights" else True
                result = calendar_preflight([payload(first), payload(second)], context())
                self.assertEqual(result["reason"], "calendar_observations_conflict")
                self.assertEqual(result["decision"], "proceed_quote")
        calendar = days()
        calendar[0].update(minNights=5, maxNights=2)
        self.assertEqual(calendar_preflight([payload(calendar)], context())["decision"], "proceed_quote")

    def test_listing_request_party_and_range_must_match(self):
        calendar = [{"calendarDate": "2026-10-12", "available": False}]
        for changed in ({"listing_id": "999"}, {"adults": 8}, {"checkin": "2026-10-13"},
                        {"calendar_month": 11}):
            with self.subTest(changed=changed):
                source = payload(calendar)
                source["request_context"].update(changed)
                self.assertEqual(calendar_preflight([source], context())["decision"], "proceed_quote")
        source = payload(calendar)
        source["body"]["data"]["merlin"]["pdpAvailabilityCalendar"]["calendarMonths"][0]["listingId"] = "999"
        self.assertEqual(calendar_preflight([source], context())["reason"], "calendar_listing_conflict")
        source = payload(calendar, request_context={"listing_id": "123456"})
        self.assertEqual(calendar_preflight([source], context())["reason"], "calendar_request_range_unverified")
        source.pop("request_context")
        self.assertEqual(calendar_preflight([source], context())["decision"], "proceed_quote")

    def test_bad_dates_http_and_graphql_errors_do_not_prove_unavailability(self):
        source = payload([{"calendarDate": "2026-10-12", "available": False}])
        for changed in ({"checkout": "2026-10-12"}, {"checkout": "2026-10-11"}, {"checkin": "20261012"}, {"checkin": None}):
            self.assertEqual(calendar_preflight([source], context(**changed))["reason"], "invalid_stay_context")
        invalid = payload([{"calendarDate": "2026-99-12", "available": False}])
        self.assertEqual(calendar_preflight([invalid], context())["decision"], "proceed_quote")
        invalid = deepcopy(source)
        invalid["status"] = 403
        self.assertEqual(calendar_preflight([invalid], context())["decision"], "proceed_quote")
        invalid = deepcopy(source)
        invalid["body"]["errors"] = [{"message": "failed"}]
        self.assertEqual(calendar_preflight([invalid], context())["decision"], "proceed_quote")

    def test_departure_permission_survives_export_end_boundary(self):
        calendar = days()
        calendar[-1]["availableForCheckout"] = False
        result = calendar_preflight([payload(calendar)], context(end_date="2026-10-15"))
        self.assertEqual(result["reason"], "checkout_not_allowed")


class BatchPreflightTests(unittest.TestCase):
    def setUp(self):
        FakeSession.calls = []
        FakeSession.block = False
        CalendarSession.errors = False
        CalendarSession.calendar_days = [{"calendarDate": "2026-10-12", "available": False}]

    def test_calendar_runs_first_and_proven_negative_skips_quote_without_fabrication(self):
        with patch("compset.batch._session_factory", CalendarSession):
            target, capture = _fetch_one({"listing_id": "9000"}, [quote_template(), template()], "123456", context(), Event())
        self.assertEqual(len(FakeSession.calls), 1)
        self.assertIn("Calendar", FakeSession.calls[0][0])
        self.assertEqual(capture["report"]["calendar_preflight"]["quote_requests_skipped"], 1)
        self.assertEqual(capture["report"]["calendar_preflight"]["evidence"][0]["listing_id"], target["listing_id"])
        self.assertEqual(len(capture["payloads"]), 1)
        self.assertNotIn("total_amount", json.dumps(capture))

    def test_unknown_calendar_and_graphql_errors_allow_the_quote(self):
        for graphql_errors in (False, True):
            with self.subTest(graphql_errors=graphql_errors):
                FakeSession.calls = []
                CalendarSession.errors = graphql_errors
                CalendarSession.calendar_days = [{"calendarDate": "2026-10-12", "available": None if not graphql_errors else False}]
                with patch("compset.batch._session_factory", CalendarSession):
                    _, capture = _fetch_one({"listing_id": "9000"}, [quote_template(), template()], "123456", context(), Event())
                self.assertEqual(len(FakeSession.calls), 2)
                self.assertIn("Calendar", FakeSession.calls[0][0])
                self.assertIn("BookIt", FakeSession.calls[1][0])
                self.assertEqual(capture["report"]["calendar_preflight"]["decision"], "proceed_quote")

    def test_successful_business_negative_completes_and_resumes_from_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            setup_snapshot(target, 1)
            with patch("compset.batch.collect", side_effect=fake_bootstrap), patch("compset.batch._session_factory", CalendarSession):
                result = monitor_compset(data_dir=target)
            self.assertEqual(len(FakeSession.calls), 1)
            record = result["records"][0]
            self.assertEqual(record["status"], "complete")
            self.assertIsNone(record["selected_quote"])
            self.assertEqual(record["calendar_preflight"]["reason"], "sleeping_night_unavailable")
            with patch("compset.batch.collect") as bootstrap, patch("compset.batch._session_factory") as http:
                resumed = monitor_compset(data_dir=target)
            bootstrap.assert_not_called()
            http.assert_not_called()
            self.assertEqual(resumed["records"], result["records"])


if __name__ == "__main__":
    unittest.main()
