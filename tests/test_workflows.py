import unittest
from compset.workflows import criteria_from

class CriteriaTests(unittest.TestCase):
    def test_circle_and_budget_validation(self):
        for value in ({"center_lat": float("nan")}, {"center_lng": 181}, {"radius_km": 0}, {"radius_km": True}, {"budget": 41}, {"target": 101}, {"target": 2.5}):
            with self.assertRaises(ValueError):
                criteria_from(value)
        self.assertEqual(criteria_from({})["radius_km"], 2)
        self.assertEqual(criteria_from({"radius_km": 1.5})["radius_km"], 1.5)
