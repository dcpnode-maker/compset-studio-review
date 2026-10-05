import copy
import unittest

from compset.normalize import normalize


CONTEXT = {"listing_id": "123", "currency": "AED", "locale": "en", "checkin": "2026-10-12",
           "checkout": "2026-10-15", "adults": 2, "children": 0, "infants": 0, "pets": 0,
           "start_date": "2026-10-01", "end_date": "2026-11-01", "observed_at": "2026-09-28T00:00:00Z"}


def envelope(body, **kwargs):
    return {"source_url": "https://www.airbnb.com/api/v3/example?token=secret", "status": 200, "body": body, **kwargs}


def calendar(days, listing_id="123"):
    return {"data": {"merlin": {"pdpAvailabilityCalendar": {"calendarMonths": [
        {"listingId": listing_id, "days": days}]}}}}


def pdp(sections, metadata=None):
    return {"data": {"presentation": {"stayProductDetailPage": {"sections": {
        "sections": sections, "metadata": metadata or {}}}}}}


def quote(display="AED 1,234.56", qualifier="3 nights"):
    return {"sectionId": "BOOK_IT_SIDEBAR", "section": {"structuredDisplayPrice": {
        "primaryLine": {"price": display, "qualifier": qualifier}}}}


class NormalizeTests(unittest.TestCase):
    def test_calendar_false_is_unavailable_but_not_booked(self):
        result = normalize([envelope(calendar([{"calendarDate": "2026-10-12", "available": False,
                          "availableForCheckin": False, "price": {"localPriceFormatted": None}}]))], CONTEXT)
        row = result["calendar"][0]
        self.assertFalse(row["available"])
        self.assertEqual(row["availability"], "unavailable")
        self.assertNotIn("booked", row)
        self.assertIsNone(row["price_amount"])
        self.assertNotIn("secret", row["source_url"])
        self.assertIn("calendarMonths[0].days[0]", row["source_path"])

    def test_string_and_integer_boolean_are_unknown(self):
        for bad in ("false", 0, 1, None):
            with self.subTest(bad=bad):
                result = normalize([envelope(calendar([{"calendarDate": "2026-10-12", "available": bad}]))], CONTEXT)
                self.assertEqual(result["calendar"][0]["availability"], "unknown")

    def test_errors_do_not_invent_unavailable_dates(self):
        body = calendar([{"calendarDate": "2026-10-12", "available": False}])
        for payload in (envelope(body, status=429), envelope({**body, "errors": [{"message": "failed"}]})):
            self.assertEqual(normalize([payload], CONTEXT)["calendar"], [])

    def test_wrong_listing_invalid_dates_and_exclusive_end_omitted(self):
        days = [{"calendarDate": d, "available": True} for d in ("2026-02-30", "2026-11-01", "2026-09-30")]
        self.assertEqual(normalize([envelope(calendar(days))], CONTEXT)["calendar"], [])
        self.assertEqual(normalize([envelope(calendar([{"calendarDate": "2026-10-12", "available": True}], "999"))], CONTEXT)["calendar"], [])

    def test_typed_value_survives_malformed_duplicate(self):
        first = calendar([{"calendarDate": "2026-10-12", "available": False}])
        second = calendar([{"calendarDate": "2026-10-12", "available": "true"}])
        self.assertFalse(normalize([envelope(first), envelope(second)], CONTEXT)["calendar"][0]["available"])

    def test_calendar_price_keeps_exact_decimal_and_restrictions(self):
        result = normalize([envelope(calendar([{"calendarDate": "2026-10-12", "available": True,
                          "minNights": 3, "bookable": None, "price": {"localPriceFormatted": "AED 987.65"}}]))], CONTEXT)
        self.assertEqual(result["calendar"][0]["price_amount"], "987.65")
        self.assertEqual(result["calendar"][0]["min_nights"], 3)
        self.assertIsNone(result["calendar"][0]["bookable"])

    def test_body_identity_prevents_wrong_listing_details(self):
        body = pdp([{"section": {"__typename": "PdpTitleSection", "title": "Wrong listing"}}])
        body["variables"] = {"id": "U3RheUxpc3Rpbmc6OTk5"}
        self.assertNotIn("title", normalize([envelope(body)], CONTEXT)["listing"])

    def test_separate_amenities_node_preserves_false_without_host_fields(self):
        body = {"data": {"node": {"id": "123", "pdpPresentation": {"amenities": {
            "seeAllAmenitiesGroups": [{"amenities": [{"title": "Pool", "available": False,
                                                        "hostId": "secret"}]}]}}}}}
        listing = normalize([envelope(body)], CONTEXT)["listing"]
        self.assertEqual(listing["amenities"], [{"title": "Pool", "available": False}])
        self.assertNotIn("secret", str(listing))

    def test_money_precise_and_total_requires_qualifier(self):
        total = normalize([envelope(pdp([quote()]))], CONTEXT)["quotes"][0]
        self.assertEqual(total["display_total_amount"], "1234.56")
        self.assertIsNone(total["total_amount"])
        self.assertIsNone(total["taxes_included"])
        nightly = normalize([envelope(pdp([quote(qualifier="night")]))], CONTEXT)["quotes"][0]
        self.assertEqual(nightly["price_basis"], "nightly_display")
        self.assertIsNone(nightly["total_amount"])
        ambiguous = normalize([envelope(pdp([quote(qualifier="")]))], CONTEXT)["quotes"][0]
        self.assertIsNone(ambiguous["total_amount"])

    def test_non_english_decimal_and_currency_mismatch(self):
        ctx = {**CONTEXT, "locale": "de", "currency": "EUR"}
        row = normalize([envelope(pdp([quote("1.234,56 €", "3 Nächte")]))], ctx)["quotes"][0]
        self.assertEqual(row["display_amount"], "1234.56")
        self.assertIsNone(row["total_amount"])
        mismatch = normalize([envelope(pdp([quote("USD 100")]))], CONTEXT)["quotes"][0]
        self.assertIsNone(mismatch["display_amount"])
        mismatch = normalize([envelope(pdp([quote("€100")]))], CONTEXT)["quotes"][0]
        self.assertIsNone(mismatch["display_amount"])

    def test_duration_mismatch_does_not_claim_stay_total(self):
        row = normalize([envelope(pdp([quote(qualifier="4 nights")]))], CONTEXT)["quotes"][0]
        self.assertIsNone(row["total_amount"])

    def test_sbui_is_not_mutated_and_keeps_actual_source_path(self):
        body = pdp([])
        body["data"]["presentation"]["stayProductDetailPage"]["sections"]["sbuiData"] = {
            "sectionConfiguration": {"root": {"sections": [{"sectionData": {
                "__typename": "PdpOverviewV2Section", "overviewItems": [{"title": "4 guests"}]}}]}}}
        original = copy.deepcopy(body)
        listing = normalize([envelope(body)], CONTEXT)["listing"]
        self.assertEqual(listing["overview"], ["4 guests"])
        self.assertIn("sbuiData.sectionConfiguration.root.sections[0].sectionData", listing["field_sources"]["overview"]["source_path"])
        self.assertEqual(body, original)

    def test_hydration_selects_all_entries_and_omits_host(self):
        body = pdp([{"section": {"__typename": "PdpTitleSection", "title": "Public title"}},
                    {"section": {"__typename": "HostProfileSection", "title": "Private host"}}],
                   {"loggingContext": {"eventDataLogging": {"personCapacity": 4, "hostId": "secret"}}})
        wrapped = {"niobeClientData": [["other", {}], ["listing", body]]}
        original = copy.deepcopy(wrapped)
        listing = normalize([envelope(wrapped)], CONTEXT)["listing"]
        self.assertEqual(listing["title"], "Public title")
        self.assertEqual(listing["person_capacity"], 4)
        self.assertNotIn("host", str(listing).lower())
        self.assertIn("niobeClientData[1][1]", listing["field_sources"]["title"]["source_path"])
        self.assertEqual(wrapped, original)

    def test_envelope_context_preserves_quote_currency_and_dates(self):
        result = normalize([envelope(pdp([quote("EUR 200")]), context={"currency": "EUR", "checkin": None})], CONTEXT)
        self.assertEqual(result["quotes"], [])

    def test_sparse_bootstrap_metadata_details_and_capacity_priority(self):
        metadata = {"sharingConfig": {"title": "Apartment in Example City · 1 bedroom · 1 bed · 1.5 bathrooms",
                                      "personCapacity": 1, "propertyType": "Entire apartment"},
                    "loggingContext": {"eventDataLogging": {"listingId": "123", "personCapacity": 2}},
                    "seoFeatures": {"ogTags": {"ogDescription": "Public listing title"}}}
        body = {"stayProductDetailPage": {"sections": {"metadata": metadata, "sections": [
            {"section": {"__typename": "PdpTitleSection"}}]}}}
        listing = normalize([envelope(body)], CONTEXT)["listing"]
        self.assertEqual(listing["person_capacity"], 2)
        self.assertEqual((listing["bedrooms"], listing["beds"], listing["bathrooms"]), (1, 1, 1.5))
        self.assertEqual(listing["title"], "Public listing title")
        self.assertEqual(listing["field_sources"]["bedrooms"]["source_path"],
                         "$.stayProductDetailPage.sections.metadata.sharingConfig.title")

    def test_unavailable_stay_does_not_mark_calendar_nights(self):
        body = pdp([{"sectionId": "BOOK_IT_SIDEBAR", "section": {"available": False,
                    "structuredDisplayPrice": None, "localizedUnavailabilityMessage": "Those dates are not available"}}])
        result = normalize([envelope(body)], CONTEXT)
        self.assertEqual(result["calendar"], [])
        self.assertEqual(result["quotes"][0]["status"], "unavailable")
        self.assertIsNone(result["quotes"][0]["total_amount"])
        self.assertEqual(result["quotes"][0]["checkin"], CONTEXT["checkin"])

    def test_undated_bootstrap_placeholder_does_not_invent_quote(self):
        body = pdp([{"sectionId": "BOOK_IT_SIDEBAR", "section": {"available": None,
                    "structuredDisplayPrice": None, "localizedUnavailabilityMessage": None}}])
        self.assertEqual(normalize([envelope(body)], CONTEXT)["quotes"], [])

    def test_arabic_presentation_aed_marker_and_exact_rate_plan_totals(self):
        detail = {"__typename": "OptionalityPriceDetail", "selectedGuestOptionId": "51", "guestOptions": [
            {"__typename": "GuestOption", "guestOptionId": "51", "isSelected": True,
             "priceString": "\ufea9.\ufe87\u00a02,244.85 total", "title": "Non-refundable", "subtitle": "Cancellation terms"},
            {"__typename": "GuestOption", "guestOptionId": "3", "isSelected": False,
             "priceString": "د.إ 2,466.50 total", "title": "Refundable"}]}
        direct = {"data": {"node": {"pdpPresentation": {"bookIt": {"productItemDetail": detail}}}}}
        display = quote("\ufea9.\ufe87 2,245", "for 3 nights")
        display["section"]["productItemDetail"] = detail
        result = normalize([envelope(direct), envelope(pdp([display])), envelope(direct)], CONTEXT)
        rates = [q for q in result["quotes"] if q["quote_kind"] == "rate_plan_total"]
        self.assertEqual(len(rates), 2)
        self.assertEqual([q["total_amount"] for q in rates], ["2244.85", "2466.50"])
        self.assertTrue(rates[0]["is_selected"])
        self.assertFalse(rates[1]["is_selected"])
        self.assertEqual(len(rates[0]["sources"]), 2)
        shown = next(q for q in result["quotes"] if q["quote_kind"] == "display_price")
        self.assertEqual(shown["display_amount"], "2245")
        self.assertEqual(shown["display_total_amount"], "2245")
        self.assertIsNone(shown["total_amount"])
        self.assertEqual(result["calendar"], [])

    def test_aed_marker_rejected_under_different_currency(self):
        result = normalize([envelope(pdp([quote("د.إ 123.45")]))], {**CONTEXT, "currency": "USD"})
        self.assertIsNone(result["quotes"][0]["display_amount"])

    def test_actual_request_context_wins_and_listing_mismatch_is_rejected(self):
        payload = envelope(pdp([quote("AED 200")]), context={"currency": "USD"},
                           request_context={"currency": "AED", "locale": "en-IN", "adults": 3,
                                            "checkin": "2026-10-17", "checkout": "2026-10-20"})
        row = normalize([payload], CONTEXT)["quotes"][0]
        self.assertEqual((row["currency"], row["locale"], row["adults"]), ("AED", "en-IN", 3))
        self.assertEqual(row["checkin"], "2026-10-17")
        payload["request_context"]["listing_id"] = "999"
        self.assertEqual(normalize([payload], CONTEXT)["quotes"], [])

    def test_selected_rate_plan_sorted_first_even_if_source_option_second(self):
        detail = {"__typename": "OptionalityPriceDetail", "selectedGuestOptionId": "51", "guestOptions": [
            {"__typename": "GuestOption", "guestOptionId": "3", "isSelected": False,
             "priceString": "AED 240 total", "title": "Refundable"},
            {"__typename": "GuestOption", "guestOptionId": "51", "isSelected": True,
             "priceString": "AED 200 total", "title": "Non-refundable"}]}
        body = {"data": {"node": {"pdpPresentation": {"bookIt": {"productItemDetail": detail}}}}}
        row = normalize([envelope(body)], CONTEXT)["quotes"][0]
        self.assertEqual(row["rate_plan_id"], "51")
        self.assertEqual(row["price_basis"], "stay_total")

    def test_modern_presentation_attributes_host_identity_and_unrated_listing(self):
        body = {"data": {"node": {"pdpPresentation": {
            "title": {"content": {"localizedStringWithTranslationPreference": "Public apartment"}},
            "personCapacity": 2, "overview": {"items": ["1 guest", "1 bedroom", "1 bed", "1 bathroom"]},
            "location": {"latitude": 25.19, "longitude": 55.27, "isExactLocation": False},
            "quality": {"listingRatingStats": {"overallRatingStats": {"ratingAverage": 0, "ratingCount": "0"}}},
            "hostInfo": {"passportData": {"name": "Public Host", "userId": "RGVtYW5kVXNlcjoxMjM=",
                "ratingCount": 5311, "ratingAverage": 4.59,
                "stats": [{"type": "REVIEW_COUNT", "value": "5311"}]},
                "about": {"source": "Private biography"}, "email": "private@example.invalid", "isVerified": True},
            "amenities": {"seeAllAmenitiesGroups": [{"amenities": [
                {"title": "Pool", "available": True, "icon": "SYSTEM_POOL", "id": "pdp_parking_7_123-0"},
                {"title": "Heating", "available": False}]}]}}}}}
        listing = normalize([envelope(body)], CONTEXT)["listing"]
        self.assertEqual(listing["person_capacity"], 2)
        self.assertEqual((listing["beds"], listing["bedrooms"], listing["bathrooms"]), (1, 1, 1))
        self.assertEqual((listing["host_id"], listing["host_name"]), ("123", "Public Host"))
        self.assertIsNone(listing["host_listing_count"])
        self.assertIsNone(listing["host_is_professional"])
        self.assertEqual(listing["review_count"], 0)
        self.assertEqual(listing["rating_status"], "unrated")
        self.assertNotIn("rating", listing)
        self.assertNotIn("Private biography", str(listing))
        self.assertNotIn("private@example", str(listing))
        self.assertEqual(listing["amenities"][0]["source_id"], "pdp_parking_7_123-0")
        self.assertNotIn("id", listing["amenities"][0])
        self.assertTrue(listing["field_sources"]["host_id"]["source_path"].endswith("hostInfo.passportData.userId"))
        preceding = pdp([], {"loggingContext": {"eventDataLogging": {"guestSatisfactionOverall": 0}}})
        self.assertNotIn("rating", normalize([envelope(preceding), envelope(body)], CONTEXT)["listing"])

    def test_explicit_host_portfolio_and_professional_flag_only(self):
        body = {"data": {"node": {"pdpPresentation": {"hostInfo": {
            "isProfessionalHost": False, "passportData": {"name": "Same Name", "userId": "123",
            "stats": [{"type": "LISTING_COUNT", "value": "42"}]}},
            "quality": {"listingRatingStats": {"overallRatingStats": {"ratingAverage": 4.8, "ratingCount": "19"}}}}}}}
        listing = normalize([envelope(body)], CONTEXT)["listing"]
        self.assertEqual(listing["host_listing_count"], 42)
        self.assertFalse(listing["host_is_professional"])
        self.assertEqual((listing["rating"], listing["review_count"]), (4.8, 19))
        body["data"]["node"]["pdpPresentation"]["hostInfo"]["isProfessionalHost"] = "true"
        self.assertIsNone(normalize([envelope(body)], CONTEXT)["listing"]["host_is_professional"])


if __name__ == "__main__":
    unittest.main()
