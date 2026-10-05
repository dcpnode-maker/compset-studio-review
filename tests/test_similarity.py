import copy
import math
import unittest

from compset.similarity import rank_candidates


class SimilarityTests(unittest.TestCase):
    def setUp(self):
        self.subject = {"listing_id": "subject", "latitude": 0, "longitude": 0,
                        "bedrooms": 1, "bathrooms": 1, "beds": 1, "person_capacity": 2,
                        "room_type": "Entire home/apt", "amenities": ["Wifi", "Kitchen"],
                        "rating": 4.8, "review_count": 20}
        self.criteria = {"center_lat": 0, "center_lng": 0, "radius_km": 1}

    def candidate(self, listing_id="a", **changes):
        row = {**self.subject, "listing_id": listing_id, "title": "Observed title",
               "host_id": "host1", "host_name": "Display name", "host_listing_count": 10,
               "field_sources": {"bedrooms": {"source_path": "$.observed"}}}
        row.update(changes)
        return row

    def rank(self, *rows, **criteria):
        return rank_candidates(self.subject, list(rows), {**self.criteria, **criteria})

    def test_exact_match_preserves_evidence_and_does_not_mutate_input(self):
        row = self.candidate()
        before = copy.deepcopy(row)
        result = self.rank(row)
        observed = result["candidates"][0]
        self.assertEqual(row, before)
        self.assertEqual(observed["field_sources"], row["field_sources"])
        self.assertEqual((observed["similarity_score"], observed["evidence_coverage"]), (100, 100))
        self.assertEqual(observed["operator_size"], "large")
        self.assertTrue(observed["selected"])
        self.assertNotIn("official_stars", observed)

    def test_circle_exact_boundary_and_outside_are_retained(self):
        boundary = math.degrees(1 / 6371.0088)
        inside = self.candidate("inside", longitude=boundary)
        outside = self.candidate("outside", longitude=boundary + 1e-9)
        result = self.rank(inside, outside)
        rows = {row["listing_id"]: row for row in result["candidates"]}
        self.assertTrue(rows["inside"]["inside_circle"])
        self.assertEqual(rows["outside"]["eligibility"], "excluded")
        self.assertIn("outside_circle", rows["outside"]["rejection_reasons"])
        self.assertEqual(result["summary"]["circle"]["radius_km"], 1)
        self.assertFalse(result["summary"]["circle"]["automatic_expansion"])
        self.assertEqual(result["summary"]["filter_counts"]["circle"]["excluded"], 1)

    def test_critical_missing_evidence_is_provisional(self):
        for field in ("latitude", "longitude", "bedrooms", "bathrooms", "room_type", "person_capacity", "listing_id"):
            with self.subTest(field=field):
                row = self.rank(self.candidate(**{field: None}))["candidates"][0]
                self.assertEqual(row["eligibility"], "provisional")
                self.assertIn(field, row["missing_fields"])
                self.assertFalse(row["selected"])
        row = self.rank(self.candidate(latitude=float("nan")))["candidates"][0]
        self.assertIsNone(row["inside_circle"])

    def test_tolerances_and_dissimilar_reason_counts(self):
        accepted = self.candidate("edge", bathrooms=1.5, person_capacity=4)
        rejected = self.candidate("bad", bedrooms=2, bathrooms=1.50001, person_capacity=5, room_type="Private room")
        result = self.rank(accepted, rejected)
        self.assertTrue(result["candidates"][0]["selected"])
        self.assertEqual(set(result["candidates"][1]["rejection_reasons"]),
                         {"bedrooms_mismatch", "bathrooms_mismatch", "capacity_mismatch", "room_type_mismatch"})
        self.assertEqual(result["summary"]["rejection_counts"]["bedrooms_mismatch"], 1)
        self.assertEqual(self.rank(self.candidate(bedrooms=2), bedroom_tolerance=1)["selected"][0]["bedrooms"], 2)

    def test_known_whole_home_aliases_and_unknown_room_type(self):
        for room_type in ("entire_home", "Entire rental unit", "ENTIRE HOME/APT"):
            self.assertTrue(self.rank(self.candidate(room_type=room_type))["selected"])
        row = self.rank(self.candidate(room_type="Entire spaceship"))["candidates"][0]
        self.assertEqual(row["eligibility"], "provisional")
        self.assertIn("room_type", row["missing_fields"])

    def test_missing_optional_data_cannot_inflate_score(self):
        row = self.rank(self.candidate(beds=None, amenities=None, rating=None))["candidates"][0]
        self.assertEqual((row["similarity_score"], row["evidence_coverage"]), (65, 65))
        self.assertIsNone(row["score_components"]["rating"]["score"])
        self.assertTrue(row["selected"])

    def test_unreviewed_subject_rating_is_missing_evidence(self):
        self.subject.update(rating=0, review_count=0)
        row = self.rank(self.candidate(rating=4.9, review_count=200))["candidates"][0]
        self.assertEqual(row["evidence_coverage"], 90)
        self.assertEqual(row["similarity_score"], 90)
        self.assertIsNone(row["score_components"]["rating"]["earned_points"])
        self.assertIn("subject.rating", row["missing_fields"])

    def test_amenity_titles_casefold_unicode_and_available_booleans(self):
        self.subject["amenities"] = ["ＷＩＦＩ", "Kitchen", "Ｓｔｒａße"]
        row = self.rank(self.candidate(amenities=[{"title": "wifi", "available": True},
                                                 {"title": "KITCHEN", "available": True},
                                                 {"title": "STRASSE", "available": True},
                                                 {"title": "Pool", "available": False},
                                                 {"title": "Gym", "available": None},
                                                 {"id": "wifi", "available": True}]))["candidates"][0]
        self.assertEqual(row["score_components"]["amenities"]["score"], 100)
        row = self.rank(self.candidate(amenities=[{"title": "Kitchen", "available": None}]))["candidates"][0]
        self.assertIsNone(row["score_components"]["amenities"]["score"])

    def test_subject_and_duplicate_ids_removed_unknown_ids_retained(self):
        result = self.rank(self.candidate("subject"), self.candidate(123), self.candidate("123"),
                           self.candidate(None), self.candidate(None))
        self.assertEqual(result["summary"]["returned_count"], 5)
        self.assertEqual(result["summary"]["subject_excluded_count"], 1)
        self.assertEqual(result["summary"]["duplicate_count"], 1)
        self.assertEqual(len(result["candidates"]), 3)

    def test_operator_size_uses_disclosed_count_or_evidenced_host_footprint_not_name(self):
        rows = [self.candidate(str(index), host_name="BnBME", host_listing_count=None) for index in range(12)]
        rows.extend([self.candidate("small", host_id="host2", host_name="BnBME", host_listing_count=9),
                     self.candidate("unknown", host_id=None, host_name="BnBME", host_listing_count=None)])
        result = self.rank(*rows)
        groups = result["summary"]["host_groups"]
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["observed_competitor_count"], 12)
        self.assertEqual(groups[0]["operator_size"], "large")
        self.assertEqual(groups[0]["operator_size_basis"], "observed_listings_for_same_public_host_id")
        self.assertEqual(result["candidates"][-2]["operator_size"], "small")
        self.assertEqual(result["candidates"][-1]["operator_size"], "unknown")
        concentration = result["summary"]["selected_operator_concentration"]
        self.assertEqual(concentration["known_host_count"], 2)
        self.assertEqual(concentration["unknown_host_listing_count"], 1)
        self.assertAlmostEqual(concentration["largest_host_share_percent"], 100 * 12 / 14, places=4)

    def test_target_ceiling_ranking_and_large_operators_retained(self):
        result = self.rank(*(self.candidate(str(index)) for index in range(102)), target=1000)
        self.assertEqual(len(result["candidates"]), 102)
        self.assertEqual(len(result["selected"]), 100)
        self.assertEqual(result["summary"]["selected_operator_concentration"]["large"], 100)
        result = self.rank(self.candidate("weak", beds=2), self.candidate("strong"), target=1)
        self.assertEqual(result["selected"][0]["listing_id"], "strong")
        self.assertEqual(len(result["candidates"]), 2)

    def test_criteria_and_nonfinite_values_are_validated(self):
        for changes in ({"radius_km": -1}, {"center_lat": 91}, {"center_lng": float("inf")},
                        {"target": True}, {"target": 1.5}, {"large_operator_threshold": 0},
                        {"bathroom_tolerance": -1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.rank(self.candidate(), **changes)

    def test_secondary_hard_filters_can_relax_but_room_and_bedrooms_remain(self):
        row = self.candidate("relaxed", bathrooms=None, person_capacity=6)
        result = self.rank(row, bathroom_tolerance=None, capacity_tolerance=None, relaxation_stage="secondary_relaxed")
        self.assertTrue(result["selected"])
        self.assertFalse(result["summary"]["active_filters"]["bathrooms"])
        self.assertFalse(result["summary"]["active_filters"]["person_capacity"])
        self.assertEqual(result["summary"]["filter_counts"]["bathrooms"]["disabled"], 1)
        self.assertEqual(result["summary"]["relaxation_stage"], "secondary_relaxed")
        self.assertIn("bathrooms", result["selected"][0]["missing_fields"])
        self.assertFalse(self.rank(self.candidate(bedrooms=2), bathroom_tolerance=None, capacity_tolerance=None)["selected"])
        self.assertFalse(self.rank(self.candidate(room_type="Private room"), bathroom_tolerance=None, capacity_tolerance=None)["selected"])
        with self.assertRaises(ValueError):
            self.rank(self.candidate(), bedroom_tolerance=None)

    def test_guest_count_floor_survives_capacity_tolerance_relaxation(self):
        result = self.rank(self.candidate("small", person_capacity=1), self.candidate("unknown", person_capacity=None),
                           self.candidate("enough", person_capacity=4), capacity_tolerance=None, min_guest_capacity=2)
        rows = {row["listing_id"]: row for row in result["candidates"]}
        self.assertIn("insufficient_guest_capacity", rows["small"]["rejection_reasons"])
        self.assertEqual(rows["unknown"]["eligibility"], "provisional")
        self.assertTrue(rows["enough"]["selected"])
        self.assertTrue(result["summary"]["active_filters"]["min_guest_capacity"])
        for invalid in (0, -1, 2.5, True):
            with self.assertRaises(ValueError):
                self.rank(self.candidate(), min_guest_capacity=invalid)

    def test_main_amenities_match_variants_without_small_amenity_hard_filters(self):
        self.subject["amenities"] = ["Shared outdoor pool available all year", "Shared gym in building", "Central air conditioning",
                                     "Wifi", "Kitchen", "Free multistorey car park on premises", "Shampoo", "Wine glasses"]
        candidate = self.candidate(amenities=["Swimming pool", "Fitness centre", "AC", "Wireless internet", "Kitchenette", "Free parking"])
        result = self.rank(candidate)
        self.assertEqual(result["selected"][0]["score_components"]["amenities"]["score"], 100)
        self.assertTrue(self.rank(self.candidate(amenities=[]))["selected"])
        self.assertNotIn("amenities", result["summary"]["active_filters"])
        self.assertIsNone(result["summary"]["review_threshold"])
        self.subject["amenities"] = ["Swimming pool"]
        row = self.rank(self.candidate(amenities=["Pool table", "Shampoo"]))["selected"][0]
        self.assertIsNone(row["score_components"]["amenities"]["score"])

    def test_observed_size_and_type_affect_ranking_without_excluding_candidates(self):
        self.subject.update(floor_area_sqm=100, property_type="Entire apartment", building_name="Example Tower")
        close = self.candidate("close", floor_area_sqm=98)
        small = self.candidate("small", floor_area_sqm=40)
        result = self.rank(small, close)
        self.assertEqual(result["selected"][0]["listing_id"], "close")
        self.assertEqual(result["summary"]["eligible_count"], 2)
        self.assertLess(result["candidates"][0]["similarity_score"], result["candidates"][1]["similarity_score"])
        self.assertIn("rule_revision", result["summary"])

    def test_unverified_quality_marketing_does_not_influence_ranking(self):
        self.subject.update(quality_tier="luxury", title="Luxury apartment")
        result = self.rank(self.candidate("different", quality_tier="standard"))
        row = result["selected"][0]
        self.assertIsNone(row["comparison_components"]["quality_tier"]["score"])
        self.assertEqual(row["quality_tier"], "unknown")


if __name__ == "__main__":
    unittest.main()
