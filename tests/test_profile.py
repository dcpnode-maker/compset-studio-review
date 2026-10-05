import copy
import unittest

from compset.profile import CANONICAL_FIELDS, SCHEMA_REVISION, enrich_subject_profile


class ProfileTests(unittest.TestCase):
    def test_unknown_defaults_preserve_arbitrary_public_attributes_and_input(self):
        listing = {"listing_id": "123", "title": "Public apartment", "custom_public_attribute": {"view": "city"}}
        original = copy.deepcopy(listing)
        result = enrich_subject_profile(listing)
        self.assertEqual(listing, original)
        self.assertEqual(result["custom_public_attribute"], {"view": "city"})
        self.assertTrue(set(CANONICAL_FIELDS).issubset(result))
        self.assertIsNone(result["floor_area_sqm"])
        self.assertIsNone(result["building_name"])
        self.assertEqual(result["quality_tier"], "unknown")
        self.assertEqual(result["profile"]["schema_revision"], SCHEMA_REVISION)
        self.assertIn("floor_area_sqm", result["profile"]["unknown_fields"])

    def test_literal_luxury_marketing_is_claim_not_verified_tier(self):
        listing = {"title": "Luxury Deluxe apartment", "quality_tier": "luxury", "rating": 4.99,
                   "host_is_superhost": True, "field_sources": {"title": {"source_path": "$.title"}}}
        result = enrich_subject_profile(listing)
        self.assertEqual(result["quality_tier"], "unknown")
        claims = result["profile"]["quality_marketing_claims"]
        self.assertEqual(len(claims), 3)
        self.assertEqual(result["profile"]["original_values"]["quality_tier"], "luxury")
        self.assertEqual(result["rating"], 4.99)
        self.assertEqual(enrich_subject_profile(result)["profile"]["original_values"]["quality_tier"], "luxury")

    def test_verified_existing_tier_retained_with_evidence(self):
        source = {"verified": True, "source_path": "$.classification", "source_url": "https://example.invalid/classification"}
        result = enrich_subject_profile({"quality_tier": "mid_luxury", "field_sources": {"quality_tier": source}})
        self.assertEqual(result["quality_tier"], "mid_luxury")
        self.assertEqual(result["profile"]["attributes"]["quality_tier"]["status"], "verified")
        self.assertEqual(result["profile"]["attributes"]["quality_tier"]["evidence"], source)

    def test_floor_area_conversion_is_documented_and_invalid_sizes_unknown(self):
        result = enrich_subject_profile({"floor_area_sqft": 1000, "field_sources": {"floor_area_sqft": {"source_path": "$.area"}}})
        self.assertEqual(result["floor_area_sqm"], 92.9)
        self.assertEqual(result["floor_area_sqft"], 1000)
        self.assertEqual(result["profile"]["attributes"]["floor_area_sqm"]["status"], "derived")
        self.assertEqual(result["field_sources"]["floor_area_sqm"]["source_field"], "floor_area_sqft")
        for value in (-1, True, "spacious", float("inf")):
            self.assertIsNone(enrich_subject_profile({"floor_area_sqm": value})["floor_area_sqm"])

    def test_quality_tier_unknown_on_unrecognized_or_malformed_value(self):
        for value in ({"label": "luxury"}, ["luxury"], "five_star"):
            self.assertEqual(enrich_subject_profile({"quality_tier": value})["quality_tier"], "unknown")

    def test_large_evidence_containers_are_retained_once_and_referenced(self):
        rows = [{"date": "2030-10-17", "availability": "unknown"}]
        result = enrich_subject_profile({"calendar": rows, "attributes": {"all_public_fields": True}})
        self.assertEqual(result["calendar"], rows)
        self.assertEqual(result["attributes"], {"all_public_fields": True})
        self.assertNotIn("calendar", result["profile"]["attributes"])
        self.assertEqual(result["profile"]["source_containers"]["calendar"]["record_count"], 1)


if __name__ == "__main__":
    unittest.main()
