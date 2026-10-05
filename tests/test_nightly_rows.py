from copy import deepcopy
import unittest

from compset.nightly_rows import build_nightly_rows
from compset.normalize import normalize


def context(**changes):
    result = {"listing_id": "123456", "start_date": "2030-10-01", "end_date": "2030-10-31",
              "checkin": "2030-10-03", "checkout": "2030-10-06", "adults": 1,
              "children": 0, "infants": 0, "pets": 0, "currency": "AED", "locale": "en",
              "observed_at": "2030-09-01T10:00:00+00:00"}
    result.update(changes)
    return result


def calendar(*, request=None, display="AED 75.40"):
    return {"status": 200, "source_url": "https://www.airbnb.com/api/v3/PdpAvailabilityCalendar/hash",
            "request_context": request if request is not None else {"listing_id": "123456", "currency": "AED", "locale": "en-IN"},
            "body": {"data": {"merlin": {"pdpAvailabilityCalendar": {"calendarMonths": [{
                "listingId": "123456", "days": [{"calendarDate": "2030-10-01", "available": True,
                "availableForCheckin": False, "availableForCheckout": True, "minNights": 2,
                "price": {"__typename": "MerlinCalendarDayPrice", "localPriceFormatted": display}}]}]}}}}}


def bookit(*, request=None, sections=False):
    item = {"__typename": "OptionalityPriceDetail", "selectedGuestOptionId": "51", "guestOptions": [
        {"__typename": "GuestOption", "guestOptionId": "51", "isSelected": True,
         "priceString": "AED 300.15 total", "title": "Non-refundable"}]}
    if sections:
        item["explanationData"] = {"priceDetails": [{"items": [
            {"description": "3 nights x AED 100.05", "priceString": "AED 300.15", "unknownPublicFee": None},
            {"description": "Price after discount", "priceString": "AED 300.15", "originalPriceString": None}]}]}
        body = {"data": {"presentation": {"stayProductDetailPage": {"sections": {"sections": [
            {"sectionId": "BOOK_IT_SIDEBAR", "section": {"productItemDetail": item}}]}}}}}
    else:
        body = {"data": {"node": {"pdpPresentation": {"bookIt": {"productItemDetail": item}}}}}
    return {"status": 200, "source_url": "https://www.airbnb.com/api/v3/" + ("StaysPdpSections" if sections else "StaysPdpBookItQuery") + "/hash",
            "request_context": request if request is not None else context(locale="en-IN"), "body": body}


def artifact(payloads, ctx=None):
    ctx = ctx or context()
    capture = {"payloads": payloads, "report": {}}
    result = {"context": ctx, **normalize(payloads, ctx)}
    return build_nightly_rows(capture, result)


class NightlyRowsTests(unittest.TestCase):
    def test_calendar_price_without_actual_guest_parameters_is_not_one_adult_price(self):
        result = artifact([calendar()])
        self.assertEqual(len(result["rows"]), 30)
        row = result["rows"][0]
        self.assertEqual(row["calendar_display_amount"], "75.40")
        self.assertIsNone(row["nightly_amount_for_requested_party"])
        self.assertFalse(row["guest_context_verified"])
        self.assertEqual(row["nightly_price_reason"], "guest_context_unverified")
        self.assertFalse(row["available_for_checkin"])
        self.assertTrue(row["available_for_checkout"])
        self.assertEqual(row["min_nights"], 2)
        self.assertEqual(row["source_evidence"][0]["observed_request_context"]["locale"], "en-IN")
        self.assertEqual(result["context"]["locale"], "en")
        self.assertEqual(result["coverage"]["calendar_display_price_days"], 1)
        self.assertEqual(result["coverage"]["verified_nightly_price_days"], 0)
        self.assertEqual(result["coverage"]["unknown_days"], 29)

    def test_explicit_matching_party_verifies_only_returned_daily_amount(self):
        source = calendar(request=context(locale="en-IN"))
        original = deepcopy(source)
        result = artifact([source])
        self.assertEqual(source, original)
        row = result["rows"][0]
        self.assertTrue(row["guest_context_verified"])
        self.assertEqual(row["nightly_amount_for_requested_party"], "75.40")
        self.assertEqual(row["nightly_price_basis"], "calendar_day_display")
        self.assertEqual(result["coverage"]["verified_nightly_price_days"], 1)
        for key in ("base_amount", "taxes_amount", "cleaning_fee_amount", "per_adult_modifier_amount", "taxes_included", "fees_included"):
            self.assertIsNone(row[key])

    def test_missing_guest_fields_wrong_party_and_currency_do_not_verify(self):
        variants = []
        for field in ("listing_id", "adults", "children", "infants", "pets", "currency"):
            request = context()
            request.pop(field)
            variants.append(request)
        variants += [context(adults=2), context(adults=True), context(children=1), context(currency="USD")]
        for request in variants:
            with self.subTest(request=request):
                row = artifact([calendar(request=request)])["rows"][0]
                self.assertFalse(row["guest_context_verified"])
                self.assertIsNone(row["nightly_amount_for_requested_party"])

    def test_zero_negative_missing_or_malformed_prices_are_unknown_not_free(self):
        for display in (None, "AED 0", "AED -1", "unknown", "NaN", 100):
            with self.subTest(display=display):
                row = artifact([calendar(request=context(), display=display)])["rows"][0]
                self.assertIsNone(row["calendar_display_amount"])
                self.assertIsNone(row["nightly_amount_for_requested_party"])
                self.assertIsNone(row["base_amount"])

    def test_historical_party_or_wrong_window_cannot_be_relabelled(self):
        for changed in ({"adults": 2}, {"adults": True}, {"children": 1}, {"end_date": "2030-11-01"},
                        {"end_date": "2030-10-30"}, {"start_date": "20301001"}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                artifact([], context(**changed))

    def test_missing_dates_are_scaffolded_without_stay_total_division(self):
        result = artifact([bookit()])
        self.assertEqual(result["rows"][0]["date"], "2030-10-01")
        self.assertEqual(result["rows"][-1]["date"], "2030-10-30")
        self.assertEqual(result["coverage"]["unknown_days"], 30)
        self.assertEqual(result["coverage"]["verified_one_adult_stay_quotes"], 1)
        self.assertEqual(result["stay_quotes"][0]["total_amount"], "300.15")
        self.assertTrue(result["stay_quotes"][0]["guest_context_verified"])
        self.assertTrue(all(row["nightly_amount_for_requested_party"] is None for row in result["rows"]))
        self.assertTrue(all(row["calendar_display_amount"] is None for row in result["rows"]))

    def test_sections_inherited_guests_are_unverified_but_raw_line_items_survive(self):
        source = bookit(sections=True, request={"currency": "AED", "locale": "en-IN"})
        result = artifact([source])
        quote = result["stay_quotes"][0]
        self.assertEqual(quote["adults"], 1)  # Existing parser inherited the run default.
        self.assertFalse(quote["guest_context_verified"])
        self.assertEqual(quote["total_amount"], "300.15")
        self.assertEqual(quote["raw_line_items"][0]["items"][0]["description"], "3 nights x AED 100.05")
        self.assertIn("unknownPublicFee", quote["raw_line_items"][0]["items"][0])
        self.assertTrue(all(row["nightly_amount_for_requested_party"] is None for row in result["rows"]))

    def test_bookit_must_match_actual_dates_and_party_and_source_amount(self):
        for changes in ({"adults": 2}, {"checkin": "2030-10-04"}, {"currency": "USD"}):
            with self.subTest(changes=changes):
                result = artifact([bookit(request=context(**changes))])
                self.assertFalse(result["stay_quotes"][0]["guest_context_verified"])
        source = bookit()
        capture = {"payloads": [source]}
        result = {"context": context(), **normalize([source], context())}
        result["quotes"][0]["total_amount"] = "999.99"
        self.assertFalse(build_nightly_rows(capture, result)["stay_quotes"][0]["guest_context_verified"])

    def test_deduplicated_bookit_and_sections_sources_keep_verified_quote_and_explanations(self):
        result = artifact([bookit(), bookit(sections=True, request={"currency": "AED", "locale": "en-IN"})])
        self.assertEqual(len(result["stay_quotes"]), 1)
        quote = result["stay_quotes"][0]
        self.assertTrue(quote["guest_context_verified"])
        self.assertEqual(quote["raw_line_items"][0]["items"][0]["priceString"], "AED 300.15")

    def test_conflicting_same_path_prices_do_not_get_arbitrarily_selected(self):
        result = artifact([calendar(request=context()), calendar(request=context(), display="AED 80.20")])
        row = result["rows"][0]
        self.assertIsNone(row["calendar_display_amount"])
        self.assertIsNone(row["nightly_amount_for_requested_party"])
        self.assertEqual(row["nightly_price_reason"], "conflicting_source_prices")

    def test_selected_option_explanations_are_not_assigned_to_other_rate_plan(self):
        source = bookit(sections=True, request={"currency": "AED", "locale": "en-IN"})
        item = source["body"]["data"]["presentation"]["stayProductDetailPage"]["sections"]["sections"][0]["section"]["productItemDetail"]
        item["guestOptions"].append({"__typename": "GuestOption", "guestOptionId": "3", "isSelected": False,
                                    "title": "Refundable", "priceString": "AED 400.50 total"})
        quotes = artifact([source])["stay_quotes"]
        selected = next(quote for quote in quotes if quote["rate_plan_id"] == "51")
        other = next(quote for quote in quotes if quote["rate_plan_id"] == "3")
        self.assertTrue(selected["raw_line_items"])
        self.assertEqual(other["raw_line_items"], [])


if __name__ == "__main__":
    unittest.main()
