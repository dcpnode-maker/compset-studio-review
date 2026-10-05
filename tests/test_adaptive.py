import copy
import math
import unittest
from unittest.mock import Mock

from compset.adaptive import build_adaptive_plan, run_adaptive_comparison


class AdaptiveTests(unittest.TestCase):
    def setUp(self):
        self.subject = {"listing_id": "subject", "latitude": 0, "longitude": 0,
                        "bedrooms": 1, "bathrooms": 1, "beds": 1, "person_capacity": 2,
                        "room_type": "Entire home/apt", "amenities": ["Wifi", "Kitchen"],
                        "rating": 4.8, "review_count": 20}
        self.criteria = {"radius_km": 1, "target": 100, "min_guest_capacity": 1}

    def row(self, identifier, **values):
        return {**self.subject, "listing_id": identifier, "title": "Observed apartment", **values}

    def run_plan(self, rows, **values):
        return run_adaptive_comparison(self.subject, rows, self.criteria, **values)

    def test_more_than_ten_stays_strict_despite_target_shortfall(self):
        for count in (11, 67):
            callback = Mock()
            result = self.run_plan([self.row(str(index)) for index in range(count)], discovery_callback=callback)
            self.assertEqual(len(result["adaptive"]["steps"]), 1)
            self.assertEqual(result["summary"]["eligible_count"], count)
            self.assertEqual(result["summary"]["shortfall"], 100 - count)
            self.assertEqual(result["criteria"]["bathroom_tolerance"], 0.5)
            self.assertEqual(result["criteria"]["radius_km"], 1)
            self.assertFalse(result["summary"]["circle"]["automatic_expansion"])
            callback.assert_not_called()

    def test_ten_boundary_relaxes_bathrooms_then_stops_at_eleven(self):
        rows = [self.row(str(index)) for index in range(10)] + [self.row("secondary", bathrooms=2)]
        callback = Mock()
        result = self.run_plan(rows, discovery_callback=callback)
        steps = result["adaptive"]["steps"]
        self.assertEqual([step["stage"] for step in steps], ["strict", "secondary_bathrooms"])
        self.assertEqual([step["counts"]["eligible_count"] for step in steps], [10, 11])
        self.assertEqual(steps[1]["eligible_count_before"], 10)
        self.assertEqual(steps[1]["changes"]["bathroom_tolerance"], {"before": 0.5, "after": 1.0})
        self.assertEqual(result["criteria"]["bedroom_tolerance"], 0)
        callback.assert_not_called()

    def test_capacity_ceiling_relaxation_preserves_actual_guest_floor(self):
        rows = [self.row(str(index)) for index in range(10)] + [self.row("large", person_capacity=7),
               self.row("small", person_capacity=1), self.row("unknown", person_capacity=None)]
        criteria = {**self.criteria, "min_guest_capacity": 2}
        result = run_adaptive_comparison(self.subject, rows, criteria)
        mapped = {row["listing_id"]: row for row in result["candidates"]}
        self.assertIsNone(result["criteria"]["capacity_tolerance"])
        self.assertTrue(mapped["large"]["selected"])
        self.assertIn("insufficient_guest_capacity", mapped["small"]["rejection_reasons"])
        self.assertEqual(mapped["unknown"]["eligibility"], "provisional")
        self.assertFalse(mapped["unknown"]["selected"])
        self.assertEqual(result["criteria"]["min_guest_capacity"], 2)

    def test_known_outside_candidates_reconsidered_with_explicit_coverage_gap(self):
        longitude = math.degrees(1.5 / 6371.0088)
        rows = [self.row(str(index)) for index in range(10)] + [self.row("outside", longitude=longitude)]
        result = self.run_plan(rows)
        last = result["adaptive"]["steps"][-1]
        self.assertEqual(last["kind"], "radius")
        self.assertEqual(last["criteria"]["radius_km"], 2)
        self.assertFalse(last["discovery_performed"])
        self.assertFalse(last["discovery_coverage"]["complete_for_requested_cells"])
        self.assertTrue(result["summary"]["circle"]["automatic_expansion"])
        outside = next(row for row in result["candidates"] if row["listing_id"] == "outside")
        self.assertIn("outside_circle", outside["adaptive_history"][0]["rejection_reasons"])
        self.assertTrue(outside["selected"])

    def test_missing_evidence_remains_provisional_without_free_points(self):
        rows = [self.row("known")]
        for field in ("bedrooms", "room_type", "person_capacity", "bathrooms", "latitude", "listing_id"):
            rows.append(self.row("missing-" + field, **{field: None}))
        result = self.run_plan(rows, policy={"max_radius_steps": 0})
        for row in result["candidates"][1:]:
            self.assertEqual(row["eligibility"], "provisional")
            self.assertFalse(row["selected"])
            self.assertLessEqual(row["similarity_score"], result["candidates"][0]["similarity_score"])
            for field in ("bedrooms", "bathrooms", "person_capacity", "room_type"):
                if field in row["missing_fields"]:
                    self.assertIsNone(row["score_components"][field]["earned_points"])
        self.assertEqual(result["summary"]["eligible_count"], 1)

    def test_room_type_bedrooms_and_major_scoring_are_never_rewritten(self):
        result = self.run_plan([self.row("room", room_type="Private room"), self.row("beds", bedrooms=2),
                                self.row("bath", bathrooms=4), self.row("major", amenities=[])])
        mapped = {row["listing_id"]: row for row in result["candidates"]}
        for identifier, reason in (("room", "room_type_mismatch"), ("beds", "bedrooms_mismatch"), ("bath", "bathrooms_mismatch")):
            self.assertFalse(mapped[identifier]["selected"])
            self.assertTrue(all(reason in step["rejection_reasons"] for step in mapped[identifier]["adaptive_history"]))
        self.assertEqual(result["summary"]["score_weights"]["amenities"], 15)
        self.assertEqual(result["summary"]["secondary_comparison_weight"], 0.15)
        self.assertEqual(mapped["major"]["amenities"], [])
        self.assertEqual(result["criteria"]["bathroom_tolerance"], 1)

    def test_callback_deduplicates_stable_ids_and_preserves_all_raw_variants(self):
        original = self.row(1, title="First evidence")
        observed = [self.row("1", title="Another observation")] + [self.row(str(index)) for index in range(2, 13)]
        report = {"complete_for_requested_cells": False, "unresolved_cells": ["cell"]}
        callback = Mock(return_value={"candidates": observed, "report": report})
        rows = [original]
        snapshot = copy.deepcopy((rows, observed, report, self.subject, self.criteria))
        result = self.run_plan(rows, discovery_callback=callback)
        self.assertEqual(len(result["selected"]), 12)
        self.assertEqual(len(result["candidate_observations"]), 13)
        self.assertEqual(result["summary"]["duplicate_observation_count"], 1)
        self.assertEqual(result["candidates"][0]["title"], "First evidence")
        self.assertEqual((rows, observed, report, self.subject, self.criteria), snapshot)
        callback.assert_called_once()
        self.assertEqual(callback.call_args.args[1]["radius_km"], 2)
        self.assertEqual(result["adaptive"]["steps"][-1]["discovery_coverage"], report)

    def test_subject_duplicates_are_audited_raw_without_entering_selection(self):
        rows = [self.row("subject"), self.row(1), self.row("1"), self.row(None), self.row(None)]
        result = self.run_plan(rows, policy={"max_radius_steps": 0})
        self.assertEqual(len(result["candidate_observations"]), 5)
        self.assertEqual(len(result["candidates"]), 3)
        self.assertEqual(result["summary"]["subject_excluded_count"], 1)
        self.assertEqual(result["summary"]["duplicate_observation_count"], 1)
        self.assertEqual(len(result["selected"]), 1)

    def test_radius_and_transition_count_caps_are_explicit(self):
        callback = Mock(return_value={"candidates": [], "report": {"complete_for_requested_cells": False}})
        result = self.run_plan([], policy={"max_radius_km": 3, "max_radius_steps": 8}, discovery_callback=callback)
        radii = [step["criteria"]["radius_km"] for step in result["adaptive"]["steps"] if step["kind"] == "radius"]
        self.assertEqual(radii, [2, 3])
        self.assertEqual(callback.call_count, 2)
        self.assertEqual(result["adaptive"]["stop_reason"], "bounded_plan_exhausted")
        result = self.run_plan([], policy={"max_radius_steps": 1})
        self.assertEqual(result["criteria"]["radius_km"], 2)
        self.assertEqual(result["adaptive"]["automatic_radius_changes"], 1)

    def test_access_stop_retains_partial_rows_and_never_requests_another_radius(self):
        callback = Mock(return_value={"candidates": [self.row("new")], "report": {
            "stop_reason": "access_or_rate_limit_429", "complete_for_requested_cells": False}})
        result = self.run_plan([], discovery_callback=callback)
        callback.assert_called_once()
        self.assertEqual(result["adaptive"]["stop_reason"], "discovery_stopped")
        self.assertEqual(len(result["candidate_observations"]), 1)
        self.assertEqual(result["adaptive"]["steps"][-1]["discovery_coverage"]["stop_reason"], "access_or_rate_limit_429")
        initial = self.run_plan([], discovery_callback=callback, discovery_coverage={"stop_reason": "access_or_rate_limit_403"})
        self.assertEqual(len(initial["adaptive"]["steps"]), 1)
        self.assertEqual(callback.call_count, 1)

    def test_callback_failure_preserves_evidence_without_saving_exception_secrets(self):
        callback = Mock(side_effect=RuntimeError("token=private-value"))
        result = self.run_plan([self.row("known")], discovery_callback=callback)
        callback.assert_called_once()
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["adaptive"]["steps"][-1]["error_type"], "RuntimeError")
        self.assertNotIn("private-value", str(result))

    def test_unknown_subject_core_blocks_adaptation_and_unverified_grade_is_unknown(self):
        subject = {**self.subject, "room_type": "Unknown product", "quality_tier": "luxury"}
        callback = Mock()
        result = run_adaptive_comparison(subject, [self.row("candidate")], self.criteria, discovery_callback=callback)
        self.assertEqual(result["subject"]["quality_tier"], "unknown")
        self.assertEqual(result["adaptive"]["subject_core_unknown_fields"], ["room_type"])
        self.assertEqual(result["adaptive"]["stop_reason"], "subject_core_fields_unknown")
        self.assertFalse(result["selected"])
        callback.assert_not_called()

    def test_plan_validates_caps_guests_core_and_does_not_mutate_inputs(self):
        original = copy.deepcopy((self.subject, self.criteria))
        plan = build_adaptive_plan(self.subject, self.criteria)
        self.assertEqual((self.subject, self.criteria), original)
        self.assertFalse(plan["score_weights_changed"])
        for criteria in ({"bedroom_tolerance": 1}, {"bathroom_tolerance": None}, {"min_guest_capacity": True},
                         {"adults": 2, "min_guest_capacity": 1}, {"radius_km": 11}, {"target": 1.5}):
            with self.subTest(criteria=criteria), self.assertRaises(ValueError):
                build_adaptive_plan(self.subject, {**self.criteria, **criteria})
        for policy in ({"max_radius_km": 11}, {"bathroom_tolerance_cap": 3}, {"max_radius_steps": 9},
                       {"radius_multiplier": float("nan")}, {"unsupported": True}, []):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                build_adaptive_plan(self.subject, self.criteria, policy)


if __name__ == "__main__":
    unittest.main()
