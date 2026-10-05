import tempfile
from pathlib import Path
import unittest
from compset.health import observe_contracts, field_shape


class HealthTests(unittest.TestCase):
    def test_hash_changes_are_observed_without_semantic_auto_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            def source(hash_value):
                return [{"source_url": "https://www.airbnb.com/api/v3/PdpAvailabilityCalendar/" + hash_value * 64,
                         "status": 200, "body": {"data": {"calendar": []}}}]
            observe_contracts(source("a"), [], target)
            changed = observe_contracts(source("b"), [], target)
            self.assertEqual(changed["changes"][0]["kind"], "fresh_query_hash_observed")
            self.assertFalse(changed["automatic_semantic_repair"])

    def test_sold_out_and_fee_breakdown_are_distinct_expected_contracts(self):
        with tempfile.TemporaryDirectory() as directory:
            responses = [{"source_url": "https://api.bnbmehomes.com/api/v1/payments/get-charges-breakup", "status": 200, "body": body}
                         for body in ({"message": "SOLD_OUT"}, {"message": "Charges breakup", "data": {"after_discount": {"total": 125}}})]
            observe_contracts(responses, [], Path(directory))
            repeated = observe_contracts(responses, [], Path(directory))
            self.assertEqual(repeated["changes"], [])

    def test_shape_contains_paths_not_personal_values_or_amounts(self):
        paths = field_shape({"2026-10-17": [{"title": "Private value", "amount": "1234.55"}]})
        self.assertIn("$.<date>[].amount", paths)
        self.assertNotIn("Private value", str(paths))
        self.assertNotIn("1234.55", str(paths))

    def test_broken_local_diagnostic_does_not_discard_source_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "schema-health.json").write_text("broken", encoding="utf-8")
            result = observe_contracts([], [], target)
            self.assertEqual(result["state"], "attention_required")
