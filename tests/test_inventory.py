"""Independent inventory ingestion and persistence regression tests."""
from contextlib import closing
from copy import deepcopy
import csv
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from compset.inventory import build_inventory, import_inventory, normalize_detail_observation, persist_inventory


def property_record(identifier="101", currency="AED", city="Dubai", **changes):
    row = {
        "id": identifier, "property_details_uuid": "uuid-" + identifier,
        "title": "Public apartment", "property_details_name": "Public code",
        "slug": "public-apartment-" + identifier, "currency": currency,
        "description": "A full description", "images": [{"paths": ["photos/a.jpg"]}],
        "floor_plan": ["plans/first.pdf"], "yt_walkthrough_video": "public-video",
        "location": {"city": city, "country": "country", "area": "area",
                     "latitude": "25.123456789", "longitude": "55.123456789"},
        "details": {"bedrooms": "2", "available_beds": 3, "bathroom_full": 1,
                    "bathroom_half": 1, "available_bathrooms": 2, "guests": 4,
                    "rating": 4.9},
        "amenities": [{"category": "Shared", "amenities": [{"name": "Pool", "code": "POOL"}]}],
        "non_refundable_price": "1234.5600", "refundable_price": "1400.01",
        "from_date": "2030-10-17", "to_date": "2030-10-20",
        "future_public_attribute": {"nested": [False, None, {"public": "retained"}]},
    }
    row.update(changes)
    return row


def catalogue(*properties):
    return {"properties": list(properties) or [property_record()],
            "observed_at": "2030-09-01T10:00:00+00:00",
            "source_url": "https://api.bnbmehomes.com/api/v1/property/search-property-v2",
            "report": {"status": 200, "pagination_contract_observed": False,
                       "active_inventory_complete": False, "warnings": []}}


def verified_quote(**changes):
    row = {"quote_kind": "verified_stay_total", "price_basis": "stay_total",
           "status": "available", "total_amount": "1234.56", "currency": "AED",
           "checkin": "2030-10-17", "checkout": "2030-10-20", "adults": 2,
           "rate_plan": "non_refundable", "observed_at": "2030-09-01T10:01:00+00:00",
           "source_url": "https://bnbmehomes.com/property/public-apartment-101",
           "source_path": "data.verifiedQuote"}
    row.update(changes)
    return row


def detail_observation():
    attributes = property_record(status="ACTIVE", description="Fresh detail description")
    day = "2030-10-17"
    return {"property_id": "101", "attributes": attributes,
            "context": {"checkin": day, "checkout": "2030-10-20", "adults": 2, "currency": "AED"},
            "source_url": "https://bnbmehomes.com/property/public-apartment-101",
            "observed_at": "2030-09-01T10:01:00+00:00", "report": {"status": 200},
            "quotes": [{"body": {"data": {"after_discount": {"total": "1234.56789", "total_nights": 3,
                                                                    "public_charge_breakdown": {"tax": "4.50"}}}},
                        "source_url": "https://api.bnbmehomes.com/observed-price",
                        "observed_at": "2030-09-01T10:02:00+00:00"}],
            "inventory": {"body": {"data": {day: [{"property_id": 101, "property_details_uuid": "uuid-101",
                          "room_id": 909, "calendar_date": day, "available_room": 0,
                          "non_refundable_price": "99.9901", "refundable_price": 0, "status": "ACTIVE"}]}},
                          "source_url": "https://api.bnbmehomes.com/observed-inventory",
                          "observed_at": "2030-09-01T10:03:00+00:00",
                          "context": {"currency": "AED"}, "report": {"status": 200}}}


class InventoryTests(unittest.TestCase):
    def test_full_public_source_is_retained_and_input_is_not_mutated(self):
        source = catalogue()
        original = deepcopy(source)
        row = build_inventory(source)["properties"][0]
        self.assertEqual(row["attributes"], original["properties"][0])
        self.assertEqual(source, original)
        row["attributes"]["images"][0]["paths"].append("changed")
        self.assertEqual(source, original)
        for field in original["properties"][0]:
            self.assertEqual(row["field_sources"][field]["source_url"], source["source_url"])
            self.assertIn(field, row["field_sources"][field]["source_path"])
        self.assertEqual(row["bathrooms"], 1.5)
        self.assertEqual(row["bathrooms_source_count"], 2)
        self.assertIsNone(row["review_count"])

    def test_search_prices_preserve_precision_and_never_claim_bookability(self):
        row = build_inventory(catalogue(property_record(non_refundable_price="9007199254740993.123456789")))["properties"][0]
        self.assertEqual(row["quotes"][0]["display_amount"], "9007199254740993.123456789")
        self.assertEqual(row["quotes"][1]["display_amount"], "1400.01")
        self.assertEqual(row["bookability"], "not_verified")
        for quote in row["quotes"]:
            self.assertEqual(quote["quote_kind"], "search_display")
            self.assertEqual(quote["status"], "display_only")
            self.assertIsNone(quote["total_amount"])
            self.assertIsNone(quote["adults"])
            self.assertIsNone(quote["taxes_and_fees_included"])
            self.assertEqual(quote["checkin"], "2030-10-17")

    def test_zero_missing_and_nonfinite_prices_are_not_free_quotes(self):
        for value in (0, "0.00", None, False, -1, "-0.1", "NaN", "Infinity", "bad"):
            with self.subTest(value=value):
                row = build_inventory(catalogue(property_record(non_refundable_price=value, refundable_price=value)))["properties"][0]
                self.assertEqual(row["quotes"], [])
                self.assertEqual(row["bookability"], "not_verified")
                self.assertEqual(row["attributes"]["non_refundable_price"], value)

    def test_cities_and_currencies_are_not_converted_or_combined(self):
        result = build_inventory(catalogue(property_record(), property_record("102", "SAR", "Riyadh"), property_record("103", "GBP", "London")))
        self.assertEqual(result["summary"]["currency_counts"], {"AED": 1, "SAR": 1, "GBP": 1})
        self.assertEqual(result["summary"]["city_counts"], {"Dubai": 1, "Riyadh": 1, "London": 1})
        for row in result["properties"]:
            self.assertTrue(all(q["currency"] == row["currency"] for q in row["quotes"]))
        self.assertFalse(result["summary"]["active_inventory_complete"])
        self.assertEqual(result["summary"]["quoted_count"], 0)

    def test_missing_dates_and_attributes_stay_unknown(self):
        result = build_inventory(catalogue({"id": "minimal", "currency": "GBP", "non_refundable_price": "5.99"}))
        row = result["properties"][0]
        for key in ("bedrooms", "bathrooms", "person_capacity", "review_count", "host_id"):
            self.assertIsNone(row[key])
        self.assertIsNone(row["quotes"][0]["checkin"])
        self.assertIsNone(row["quotes"][0]["checkout"])
        self.assertEqual(row["bookability"], "not_verified")

    def test_duplicate_official_identifiers_are_rejected(self):
        with self.assertRaises(ValueError):
            build_inventory(catalogue(property_record(), property_record()))

    def test_host_names_are_not_identity_or_cross_channel_evidence(self):
        hosts = [{"host_id": "h1", "host_name": "bnbme", "review_count": 999},
                 {"host_id": "h2", "host_name": "bnbme", "review_count": 999}]
        channels = [{"listing_id": "a1", "host_id": "h1", "host_name": "bnbme"},
                    {"listing_id": "a2", "host_id": "h2", "host_name": "bnbme"}]
        links = [{"property_id": "101", "airbnb_listing_id": "a1", "status": "probable",
                  "evidence_url": "https://example.com", "source_path": "title_match"},
                 {"property_id": "101", "airbnb_listing_id": "a2", "status": "verified"}]
        result = build_inventory(catalogue(), hosts=hosts, airbnb_listings=channels, links=links)
        self.assertEqual(result["hosts"], hosts)
        self.assertEqual(result["airbnb_listings"], channels)
        self.assertEqual(result["links"], [])
        self.assertEqual(result["summary"]["host_count"], 2)
        self.assertIsNone(result["properties"][0]["host_id"])
        self.assertIsNone(result["properties"][0]["host_listing_count"])

    def test_explicit_cross_reference_links_only_the_matching_property(self):
        channels = [{"listing_id": "a1", "host_id": "h1", "host_name": "Operator"}]
        link = {"property_id": "101", "airbnb_listing_id": "a1", "status": "verified",
                "evidence_url": "https://bnbmehomes.com/property/public-apartment-101", "source_path": "data.airbnb_url"}
        result = build_inventory(catalogue(property_record(), property_record("102")), airbnb_listings=channels, links=[link])
        self.assertEqual(result["properties"][0]["host_id"], "h1")
        self.assertEqual(result["properties"][0]["airbnb_listing_id"], "a1")
        self.assertIsNone(result["properties"][1]["host_id"])
        self.assertEqual(result["links"], [link])

    def test_duplicate_channel_identity_cannot_silently_lose_attributes(self):
        channels = [{"listing_id": "a1", "host_id": "h1"}, {"listing_id": "a1", "host_id": "h2"}]
        with self.assertRaises(ValueError):
            build_inventory(catalogue(), airbnb_listings=channels)

    def test_verified_dated_quote_sets_only_contextual_bookability(self):
        quote = verified_quote()
        supplement = {"property_id": "101", "quotes": [quote], "attributes": {"public": "retained"}}
        original = deepcopy(supplement)
        result = build_inventory(catalogue(), supplements=[supplement])
        row = result["properties"][0]
        self.assertEqual(row["bookability"], "quoted_available_for_observed_stay")
        self.assertEqual(row["quotes"][-1], quote)
        self.assertEqual(row["detail_observations"][0], supplement)
        self.assertEqual(supplement, original)
        self.assertFalse(result["summary"]["active_inventory_complete"])

    def test_quote_label_cannot_override_missing_or_invalid_stay_context(self):
        invalid = ({"total_amount": "0"}, {"adults": True}, {"adults": 0}, {"adults": None},
                   {"currency": None}, {"checkin": None}, {"checkout": "bad"},
                   {"checkout": "2030-10-17"}, {"checkout": "2030-10-16"},
                   {"checkout": "20301016"}, {"checkout": "2030-W41-1"},
                   {"source_url": None}, {"source_path": None}, {"observed_at": None},
                   {"status": "unknown"}, {"quote_kind": "search_display"})
        for changes in invalid:
            with self.subTest(changes=changes):
                quote = verified_quote(**changes)
                row = build_inventory(catalogue(), supplements=[{"property_id": "101", "quotes": [quote]}])["properties"][0]
                self.assertEqual(row["bookability"], "not_verified")
                self.assertEqual(row["quotes"][-1], quote)

    def test_detail_status_calendar_and_precise_total_remain_distinct(self):
        detail = detail_observation()
        original = deepcopy(detail)
        result = build_inventory(catalogue(), supplements=[detail])
        row = result["properties"][0]
        self.assertEqual(detail, original)
        self.assertEqual(row["detail_attributes"], detail["attributes"])
        self.assertEqual(row["description"], "Fresh detail description")
        self.assertEqual(row["publication_status"], "active_in_public_details")
        self.assertEqual(row["bookability"], "not_verified")
        quote = row["quotes"][-1]
        self.assertEqual(quote["quote_kind"], "website_stay_total")
        self.assertEqual(quote["total_amount"], "1234.56789")
        self.assertEqual(quote["status"], "price_returned_availability_separate")
        self.assertFalse(quote["price_endpoint_guest_parameter"])
        self.assertEqual(quote["breakdown"], detail["quotes"][0]["body"]["data"]["after_discount"])
        record = row["calendar"][0]
        self.assertEqual(record["availability"], "unavailable")
        self.assertEqual(record["reason"], "public_inventory_count")
        self.assertNotIn("booked", json.dumps(record).lower())
        self.assertEqual(record["non_refundable_price"], "99.9901")
        self.assertIsNone(record["refundable_price"])
        self.assertEqual(row["detail_observations"][0]["inventory"], detail["inventory"])

    def test_unknown_inventory_counts_are_not_unavailable(self):
        for count in (None, True, False, -1, 0.5, "NaN", "bad"):
            with self.subTest(count=count):
                detail = detail_observation()
                detail["inventory"]["body"]["data"]["2030-10-17"][0]["available_room"] = count
                record = normalize_detail_observation(detail)["calendar"][0]
                self.assertEqual(record["availability"], "unknown")
                self.assertIsNone(record["available_room"])
        detail = detail_observation()
        detail["inventory"]["body"]["data"]["2030-10-17"][0]["available_room"] = 2
        self.assertEqual(normalize_detail_observation(detail)["calendar"][0]["availability"], "available")

    def test_calendar_rejects_wrong_identity_and_date(self):
        for change in ({"property_id": 102}, {"property_details_uuid": "different"}, {"calendar_date": "2030-10-18"}):
            with self.subTest(change=change):
                detail = detail_observation()
                detail["inventory"]["body"]["data"]["2030-10-17"][0].update(change)
                self.assertEqual(normalize_detail_observation(detail)["calendar"], [])

    def test_missing_inventory_record_is_unknown_even_when_zero_count_is_returned(self):
        detail = detail_observation()
        record = detail["inventory"]["body"]["data"]["2030-10-17"][0]
        record.pop("property_id")
        record.pop("room_id")
        record.update(inventory_uuid=None, available_room=0, non_refundable_price=0, refundable_price=0)
        calendar = normalize_detail_observation(detail)["calendar"]
        self.assertEqual(len(calendar), 1)
        self.assertEqual(calendar[0]["availability"], "unknown")
        self.assertEqual(calendar[0]["reason"], "inventory_record_missing")
        for field in ("available_room", "non_refundable_price", "refundable_price"):
            self.assertIsNone(calendar[0][field])
        record["property_details_uuid"] = "different"
        self.assertEqual(normalize_detail_observation(detail)["calendar"], [])
        record["property_details_uuid"] = "uuid-101"
        record["property_id"] = 999
        self.assertEqual(normalize_detail_observation(detail)["calendar"], [])

    def test_raw_quote_missing_or_malformed_context_is_ignored(self):
        for context in ({}, {"checkin": "bad", "checkout": "2030-10-20"},
                        {"checkin": "2030-10-17", "checkout": None},
                        {"checkin": "2030-10-20", "checkout": "2030-10-17"}):
            with self.subTest(context=context):
                detail = detail_observation()
                detail["context"] = context
                result = normalize_detail_observation(detail)
                self.assertEqual(result["quotes"], [])
                self.assertEqual(result["raw_quotes"], detail["quotes"])

    def test_wrong_detail_uuid_cannot_enrich_a_catalogue_property(self):
        detail = detail_observation()
        detail["attributes"]["property_details_uuid"] = "different"
        detail["inventory"]["body"]["data"]["2030-10-17"][0]["property_details_uuid"] = "different"
        row = build_inventory(catalogue(), supplements=[detail])["properties"][0]
        self.assertEqual(row["publication_status"], "published_in_public_catalogue")
        self.assertEqual(row.get("calendar", []), [])
        self.assertFalse(any(q.get("quote_kind") == "website_stay_total" for q in row["quotes"]))

    def test_latest_detail_fields_and_profile_agree_without_losing_source(self):
        detail = detail_observation()
        detail["attributes"]["details"].update(guests=6, bedrooms=3, available_beds=4, bathroom_full=2, bathroom_half=0)
        detail["attributes"]["title"] = "New title"
        detail["attributes"]["amenities"] = [{"category": "Internet", "amenities": [{"name": "Wifi", "code": "WIFI"}]}]
        row = build_inventory(catalogue(), supplements=[detail])["properties"][0]
        self.assertEqual(row["person_capacity"], 6)
        self.assertEqual(row["bedrooms"], 3)
        self.assertEqual(row["beds"], 4)
        self.assertEqual(row["bathrooms"], 2)
        self.assertEqual(row["amenities"][0]["title"], "Wifi")
        for key in ("description", "person_capacity", "bedrooms", "beds", "bathrooms", "amenities", "publication_status"):
            self.assertEqual(row["profile"]["attributes"][key]["value"], row[key])
        for field in ("title", "person_capacity", "latitude", "longitude", "rating", "city", "country", "area", "bathrooms_source_count"):
            self.assertEqual(row["field_sources"][field]["source_url"], detail["source_url"])
        self.assertEqual(row["attributes"], property_record())
        self.assertEqual(row["detail_attributes"], detail["attributes"])

    def test_partial_detail_preserves_known_values_and_does_not_relabel_their_evidence(self):
        detail = detail_observation()
        detail["attributes"] = {"id": "101", "property_details_uuid": "uuid-101", "status": "ACTIVE",
                                "description": None, "details": {"guests": None}}
        row = build_inventory(catalogue(), supplements=[detail])["properties"][0]
        self.assertEqual(row["person_capacity"], 4)
        self.assertEqual(row["description"], "A full description")
        self.assertEqual(row["amenities"][0]["title"], "Pool")
        self.assertNotEqual(row["field_sources"].get("person_capacity", {}).get("source_url"), detail["source_url"])
        self.assertNotEqual(row["field_sources"]["amenities"]["source_url"], detail["source_url"])

    def test_bathroom_fallback_points_to_the_observed_count(self):
        detail = detail_observation()
        detail["attributes"]["details"] = {"available_bathrooms": 3}
        row = build_inventory(catalogue(), supplements=[detail])["properties"][0]
        self.assertEqual(row["bathrooms"], 3)
        self.assertEqual(row["field_sources"]["bathrooms"]["source_path"], "singleHotelDetails.details.available_bathrooms")

    def test_calendar_round_trip_preserves_dates_count_precision_and_currency(self):
        result = build_inventory(catalogue(), supplements=[detail_observation()])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            folder = persist_inventory(result, target)
            persist_inventory(result, target)
            with closing(sqlite3.connect(target / "compset.sqlite3")) as db:
                persisted = [json.loads(row[0]) for row in db.execute("SELECT record_json FROM portfolio_calendar")]
            self.assertEqual(persisted, result["properties"][0]["calendar"])
            with (folder / "inventory-calendar.csv").open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["date"], "2030-10-17")
            self.assertEqual(rows[0]["non_refundable_price"], "99.9901")
            self.assertEqual(rows[0]["currency"], "AED")

    def test_sqlite_round_trip_is_idempotent_and_new_observations_append(self):
        source = catalogue(property_record(), property_record("102", "SAR", "Riyadh"), property_record("103", "GBP", "London"))
        hosts = [{"host_id": "h1", "host_name": "Same"}, {"host_id": "h2", "host_name": "Same"}]
        channels = [{"listing_id": "a1", "host_id": "h1"}, {"listing_id": "a2", "host_id": "h2"}]
        result = build_inventory(source, hosts=hosts, airbnb_listings=channels)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            folder = persist_inventory(result, target)
            persist_inventory(result, target)
            with closing(sqlite3.connect(target / "compset.sqlite3")) as db:
                for table, expected in (("portfolio_snapshots", 1), ("portfolio_properties", 3),
                                        ("portfolio_hosts", 2), ("portfolio_channel_listings", 2), ("portfolio_prices", 6)):
                    self.assertEqual(db.execute(f"SELECT count(*) FROM {table}").fetchone()[0], expected)
                persisted = {row[0]: json.loads(row[1]) for row in db.execute("SELECT property_id,record_json FROM portfolio_properties")}
            self.assertEqual(persisted, {row["property_id"]: row for row in result["properties"]})
            self.assertEqual(json.loads((folder / "portfolio.json").read_text(encoding="utf-8")), result)
            with (folder / "prices.csv").open(encoding="utf-8-sig", newline="") as stream:
                prices = list(csv.DictReader(stream))
            self.assertEqual(prices[0]["display_amount"], "1234.5600")
            self.assertEqual({row["currency"] for row in prices}, {"AED", "SAR", "GBP"})
            source["observed_at"] = "2030-09-02T10:00:00+00:00"
            changed = build_inventory(source)
            self.assertNotEqual(changed["snapshot_id"], result["snapshot_id"])
            persist_inventory(changed, target)
            with closing(sqlite3.connect(target / "compset.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM portfolio_snapshots").fetchone()[0], 2)
                self.assertEqual(db.execute("SELECT count(*) FROM portfolio_properties").fetchone()[0], 6)
            self.assertEqual(json.loads((target / "portfolio-latest.json").read_text(encoding="utf-8")), changed)
            self.assertEqual(json.loads((folder / "portfolio.json").read_text(encoding="utf-8")), result)

    def test_import_uses_optional_supplements_and_keeps_host_records(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            source = target / "source.json"
            source.write_text(json.dumps(catalogue()), encoding="utf-8")
            extra = {"hosts": [{"host_id": "h1", "host_name": "Public business"}], "ignored": "not a function argument"}
            (target / "inventory-supplements.json").write_text(json.dumps(extra), encoding="utf-8")
            result = import_inventory(source, data_dir=target)
            self.assertEqual(result["hosts"], extra["hosts"])
            self.assertTrue((target / "portfolio-latest.json").exists())


if __name__ == "__main__":
    unittest.main()
