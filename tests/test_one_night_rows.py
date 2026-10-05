from copy import deepcopy
import unittest

from compset.one_night_rows import extract_one_night_quotes


def context(**changes):
    return {"listing_id": "123456", "checkin": "2030-09-30", "checkout": "2030-10-01",
            "adults": 1, "children": 0, "infants": 0, "pets": 0, "currency": "AED",
            "locale": "en", "observed_at": "2030-09-28T04:00:00+00:00", **changes}


def fixture(*, amount="377.04", label=None, request=None):
    total = {"__typename": "HighlightExplanationLineItem", "description": "Price after discount",
             "priceString": f"\ufea9.\ufe87 {amount}",
             "accessibilityLabel": label if label is not None else f"AED {amount} total before taxes"}
    price = {"__typename": "StructuredDisplayPrice", "displayPriceStyle": "TOTAL_ONLY",
             "primaryLine": {"__typename": "DiscountedDisplayPriceLine", "discountedPrice": "AED 378",
                             "originalPrice": "AED 429", "qualifier": "for 1 night"},
             "explanationData": {"priceDetails": [
                 {"items": [{"__typename": "DefaultExplanationLineItem", "description": "1 night x AED 428.64",
                             "priceString": "AED 428.64"},
                            {"__typename": "DiscountedExplanationLineItem", "description": "Last-minute discount",
                             "priceString": "-AED 51.60", "originalPriceString": None}]},
                 {"items": [total]}]}}
    return {"status": 200, "source_url": "https://www.airbnb.co.in/api/v3/StaysPdpSections/observed-hash?secret=not-for-export",
            "request_context": context(locale="en-IN") if request is None else request,
            "body": {"data": {"presentation": {"stayProductDetailPage": {"sections": {"sections": [
                {"sectionId": "BOOK_IT_SIDEBAR", "section": {"available": True, "structuredDisplayPrice": price}}]}}}}}}


def sidebar(envelope):
    return envelope["body"]["data"]["presentation"]["stayProductDetailPage"]["sections"]["sections"][0]


def display(envelope):
    return sidebar(envelope)["section"]["structuredDisplayPrice"]


def basic_price(amount="650.40"):
    return {"__typename": "BasicPriceDetail", "explanationData": {"priceDetails": [
        {"items": [{"__typename": "DefaultExplanationLineItem", "description": f"1 night x AED {amount}",
                    "priceString": f"AED {amount}"}]},
        {"items": [{"__typename": "HighlightExplanationLineItem", "description": "Price after discount",
                    "priceString": f"\ufea9.\ufe87 {amount}", "accessibilityLabel": None, "originalPriceString": None}]}]}}


def optionality_fixture():
    envelope = fixture(amount="610.36")
    display(envelope)["explanationData"]["priceDetails"].pop()
    product = basic_price("610.36")
    product.update(__typename="OptionalityPriceDetail", selectedGuestOptionId="51", guestOptions=[
        {"__typename": "GuestOption", "guestOptionId": "51", "isSelected": True,
         "priceString": "\ufea9.\ufe87 610.36 total", "title": "Non-refundable", "subtitle": "", "disclosureText": None},
        {"__typename": "GuestOption", "guestOptionId": "3", "isSelected": False,
         "priceString": "\ufea9.\ufe87 650.40 total", "title": "Refundable",
         "subtitle": "Free cancellation before 4:00 pm on 28 September. Afterwards non-refundable."}])
    sidebar(envelope)["section"]["productItemDetail"] = product
    return envelope


def product(envelope):
    return sidebar(envelope)["section"]["productItemDetail"]


class OneNightQuoteTests(unittest.TestCase):
    def test_selected_option_total_and_alternative_prices_remain_separate_plans(self):
        envelope = optionality_fixture(); before = deepcopy(envelope)
        row, = extract_one_night_quotes([envelope], context())
        self.assertEqual(row["amount"], "610.36")
        self.assertEqual(row["status"], "quoted")
        self.assertEqual((row["rate_plan_id"], row["rate_plan"]), ("51", "Non-refundable"))
        self.assertIsNone(row["cancellation_terms"])
        self.assertIsNone(row["taxes_included"])
        self.assertIsNone(row["fees_included"])
        self.assertEqual([(v["rate_plan_id"], v["amount"], v["is_selected"]) for v in row["rate_options"]],
                         [("51", "610.36", True), ("3", "650.40", False)])
        self.assertEqual(row["rate_options"][1]["cancellation_terms"], product(envelope)["guestOptions"][1]["subtitle"])
        self.assertTrue(row["rate_options"][1]["source_path"].endswith("guestOptions[1].priceString"))
        self.assertEqual(row["rate_options"][1]["raw_options"], [product(envelope)["guestOptions"][1]])
        self.assertEqual(envelope, before)

    def test_selected_option_subtitle_is_retained_without_interpreting_deadline(self):
        envelope = optionality_fixture()
        product(envelope)["guestOptions"][0]["subtitle"] = "No refund after booking."
        self.assertEqual(extract_one_night_quotes([envelope], context())[0]["cancellation_terms"], "No refund after booking.")

    def test_option_selection_requires_consistent_id_and_exactly_one_typed_selected_flag(self):
        changes = [lambda p: p.update(selectedGuestOptionId="3"),
                   lambda p: p.update(selectedGuestOptionId=None),
                   lambda p: p["guestOptions"][1].update(isSelected=True),
                   lambda p: p["guestOptions"][0].update(isSelected=False),
                   lambda p: p["guestOptions"][1].update(isSelected=None),
                   lambda p: p["guestOptions"][1].update(guestOptionId="51"),
                   lambda p: p.update(guestOptions=None)]
        for change in changes:
            envelope = optionality_fixture(); change(product(envelope))
            row, = extract_one_night_quotes([envelope], context())
            self.assertEqual(row["status"], "unknown")
            self.assertIsNone(row["amount"])
            self.assertIsNone(row["rate_plan_id"])

    def test_selected_option_amount_must_corroborate_semantic_total(self):
        envelope = optionality_fixture()
        product(envelope)["guestOptions"][0]["priceString"] = "AED 600.00 total"
        row, = extract_one_night_quotes([envelope], context())
        self.assertIsNone(row["amount"])
        self.assertIn("selected_rate_total_conflict", row["warnings"])
        for price in ("AED 0 total", "AED -1 total", None, "unknown"):
            envelope = optionality_fixture(); product(envelope)["guestOptions"][0]["priceString"] = price
            row, = extract_one_night_quotes([envelope], context())
            self.assertIsNone(row["amount"])
            self.assertIn("selected_rate_amount_missing", row["warnings"])

    def test_same_plan_conflicting_source_prices_are_unknown_but_duplicates_merge(self):
        first, second = optionality_fixture(), optionality_fixture()
        row, = extract_one_night_quotes([first, second], context())
        self.assertEqual(row["amount"], "610.36")
        self.assertEqual(len(row["rate_options"]), 2)
        self.assertTrue(all(len(option["sources"]) == 2 for option in row["rate_options"]))
        product(second)["guestOptions"][1]["priceString"] = "AED 651.00 total"
        row, = extract_one_night_quotes([first, second], context())
        self.assertIsNone(row["amount"])
        self.assertIn("rate_option_conflict", row["warnings"])
        self.assertIsNone(row["rate_options"][1]["amount"])
        self.assertEqual(len(row["rate_options"][1]["raw_options"]), 2)

    def test_option_cannot_substitute_for_missing_semantic_total(self):
        envelope = optionality_fixture()
        product(envelope)["explanationData"]["priceDetails"].pop()
        row, = extract_one_night_quotes([envelope], context())
        self.assertIsNone(row["amount"])
        self.assertIn("selected_rate_semantic_total_missing", row["warnings"])
        self.assertEqual(row["rate_options"][0]["amount"], "610.36")

    def test_basic_price_detail_explicit_total_supplies_missing_display_total(self):
        envelope = fixture()
        display(envelope)["explanationData"]["priceDetails"].pop()
        sidebar(envelope)["section"]["productItemDetail"] = basic_price()
        original = deepcopy(envelope)
        row, = extract_one_night_quotes([envelope], context())
        self.assertEqual(row["amount"], "650.40")
        self.assertTrue(row["source_path"].endswith(".productItemDetail.explanationData.priceDetails[1].items[0].priceString"))
        self.assertIsNone(row["taxes_included"])
        self.assertIsNone(row["fees_included"])
        self.assertEqual(row["raw_line_items"], basic_price()["explanationData"]["priceDetails"])
        self.assertEqual(envelope, original)
        sidebar(envelope)["section"]["structuredDisplayPrice"] = None
        self.assertEqual(extract_one_night_quotes([envelope], context())[0]["amount"], "650.40")

    def test_basic_and_structured_totals_disagree_as_unknown_or_merge_matching_evidence(self):
        envelope = fixture()
        sidebar(envelope)["section"]["productItemDetail"] = basic_price()
        row, = extract_one_night_quotes([envelope], context())
        self.assertIsNone(row["amount"])
        self.assertEqual(row["reason"], "conflicting_exact_totals")
        self.assertEqual(len(row["sources"]), 2)
        sidebar(envelope)["section"]["productItemDetail"] = basic_price("377.04")
        row, = extract_one_night_quotes([envelope], context())
        self.assertEqual(row["amount"], "377.04")
        self.assertIs(row["taxes_included"], False)
        self.assertEqual(len(row["sources"]), 2)

    def test_product_detail_is_optional_and_other_product_types_are_not_assumed_basic(self):
        for value in (None, {}, {**basic_price(), "__typename": "UnsupportedPriceDetail"}):
            envelope = fixture()
            sidebar(envelope)["section"]["productItemDetail"] = value
            self.assertEqual(extract_one_night_quotes([envelope], context())[0]["amount"], "377.04")
            display(envelope)["explanationData"]["priceDetails"].pop()
            self.assertEqual(extract_one_night_quotes([envelope], context()), [])

    def test_basic_unit_line_alone_is_not_computed_into_total(self):
        envelope = fixture()
        sidebar(envelope)["section"]["structuredDisplayPrice"] = None
        product = basic_price()
        product["explanationData"]["priceDetails"].pop()
        sidebar(envelope)["section"]["productItemDetail"] = product
        self.assertEqual(extract_one_night_quotes([envelope], context()), [])

    def test_exact_before_tax_total_ignores_rounded_display_and_retains_source(self):
        envelope = fixture()
        original = deepcopy(envelope)
        row, = extract_one_night_quotes([envelope], context())
        self.assertEqual(row["amount"], "377.04")
        self.assertEqual(row["amount_kind"], "one_night_stay_total")
        self.assertEqual(row["status"], "quoted")
        self.assertTrue(row["guest_context_verified"])
        self.assertIs(row["taxes_included"], False)
        for key in ("fees_included", "cancellation_terms", "base_amount", "taxes_amount", "cleaning_fee_amount"):
            self.assertIsNone(row[key])
        self.assertEqual(row["raw_line_items"], display(envelope)["explanationData"]["priceDetails"])
        self.assertTrue(row["source_path"].endswith("priceDetails[1].items[0].priceString"))
        self.assertNotIn("?", row["source_url"])
        self.assertEqual(row["sources"][0]["observed_request_context"]["locale"], "en-IN")
        self.assertEqual(envelope, original)

    def test_actual_request_must_explicitly_verify_every_party_date_identity_currency_field(self):
        for field in ("listing_id", "checkin", "checkout", "adults", "children", "infants", "pets", "currency", "locale"):
            request = context(locale="en-IN")
            request.pop(field)
            self.assertEqual(extract_one_night_quotes([fixture(request=request)], context()), [], field)
        for change in ({"listing_id": "654321"}, {"adults": 2}, {"children": True}, {"pets": 1},
                       {"adults": "1"}, {"currency": "USD"}, {"checkin": "2030-09-29"},
                       {"checkout": "2030-10-02"}, {"conflicts": ["adults"]}):
            self.assertEqual(extract_one_night_quotes([fixture(request=context(**change))], context()), [])

    def test_default_context_or_sections_only_locale_cannot_launder_price(self):
        envelope = fixture(request={"currency": "AED", "locale": "en-IN"})
        envelope["context"] = context()
        self.assertEqual(extract_one_night_quotes([envelope], context()), [])
        envelope = fixture()
        envelope["request_context_conflicts"] = ["adults"]
        self.assertEqual(extract_one_night_quotes([envelope], context()), [])

    def test_zero_negative_missing_nonnumeric_and_other_currency_are_not_quotes(self):
        for amount in ("0", "-1", "NaN", "1,2", "EUR 377.04"):
            self.assertEqual(extract_one_night_quotes([fixture(amount=amount)], context()), [])
        envelope = fixture()
        display(envelope).pop("explanationData")
        self.assertEqual(extract_one_night_quotes([envelope], context()), [])

    def test_never_compute_total_from_night_discount_or_rounded_primary(self):
        envelope = fixture()
        display(envelope)["explanationData"]["priceDetails"].pop()
        self.assertEqual(extract_one_night_quotes([envelope], context()), [])

    def test_unlabeled_tax_inclusion_stays_unknown(self):
        envelope = fixture(label="AED 377.04 total")
        row, = extract_one_night_quotes([envelope], context())
        self.assertEqual(row["amount"], "377.04")
        self.assertIsNone(row["taxes_included"])
        display(envelope)["explanationData"]["priceDetails"][1]["items"][0]["accessibilityLabel"] = None
        row, = extract_one_night_quotes([envelope], context())
        self.assertEqual(row["amount"], "377.04")
        self.assertIsNone(row["taxes_included"])

    def test_failed_graphql_wrong_origin_and_other_sections_are_ignored(self):
        for status in (403, 429, 500, True):
            envelope = fixture(); envelope["status"] = status
            self.assertEqual(extract_one_night_quotes([envelope], context()), [])
        envelope = fixture(); envelope["body"]["errors"] = [{"message": "request failed"}]
        self.assertEqual(extract_one_night_quotes([envelope], context()), [])
        for source in ("https://evil.example/api/v3/StaysPdpSections/hash", "https://www.airbnb.com/api/v3/StaysPdpBookItQuery/hash"):
            envelope = fixture(); envelope["source_url"] = source
            self.assertEqual(extract_one_night_quotes([envelope], context()), [])
        envelope = fixture(); sidebar(envelope)["sectionId"] = "PRICE_OTHER"
        self.assertEqual(extract_one_night_quotes([envelope], context()), [])

    def test_source_body_listing_conflict_is_not_certified(self):
        envelope = fixture(); envelope["body"]["data"]["node"] = {"id": "654321"}
        self.assertEqual(extract_one_night_quotes([envelope], context()), [])

    def test_conflicting_precise_totals_produce_unknown_with_both_sources(self):
        row, = extract_one_night_quotes([fixture(), fixture(amount="400.10")], context())
        self.assertIsNone(row["amount"])
        self.assertEqual(row["status"], "unknown")
        self.assertEqual(row["reason"], "conflicting_exact_totals")
        self.assertEqual(len(row["sources"]), 2)
        self.assertIsNone(row["source_path"])
        self.assertEqual({v["amount"] for v in row["price_observations"]}, {"377.04", "400.10"})

    def test_accessible_total_and_exact_price_disagreement_is_unknown(self):
        row, = extract_one_night_quotes([fixture(label="AED 378 total before taxes")], context())
        self.assertIsNone(row["amount"])
        self.assertEqual(row["reason"], "exact_total_label_conflict")

    def test_duplicate_matching_totals_keep_provenance_without_duplicate_quote(self):
        rows = extract_one_night_quotes([fixture(), fixture(amount="377.040")], context())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["amount"], "377.04")
        self.assertEqual(len(rows[0]["sources"]), 2)

    def test_explicit_unavailability_or_wrong_response_duration_is_unknown(self):
        envelope = fixture(); sidebar(envelope)["section"]["available"] = False
        row, = extract_one_night_quotes([envelope], context())
        self.assertIsNone(row["amount"])
        self.assertEqual(row["reason"], "source_unavailable")
        envelope = fixture(); display(envelope)["primaryLine"]["qualifier"] = "for 3 nights"
        row, = extract_one_night_quotes([envelope], context())
        self.assertIsNone(row["amount"])
        self.assertEqual(row["reason"], "response_stay_length_conflict")

    def test_non_one_night_or_non_one_adult_context_is_rejected(self):
        for change in ({"checkout": "2030-10-02"}, {"checkin": "20300930"}, {"adults": 2}, {"adults": True}, {"children": 1}):
            with self.assertRaises(ValueError):
                extract_one_night_quotes([fixture()], context(**change))


if __name__ == "__main__":
    unittest.main()
