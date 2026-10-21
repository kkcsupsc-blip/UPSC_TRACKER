import unittest

from planner import DEFAULT_PLANNER, daily_quotas, learning_split, preparation_phase, subject_stream, validate_planner


class TwoStreamContractTests(unittest.TestCase):
    def test_optional_is_not_inferred_from_mains_exam_type(self):
        self.assertEqual(subject_stream({"name": "Sociology Paper I"}), "optional")
        self.assertEqual(subject_stream({"name": "Essay", "topics": [{"examType": "mains"}]}), "gs")

    def test_both_streams_receive_capacity_on_the_same_day(self):
        result = learning_split(6, {"gs": 12, "optional": 12}, {"gs": 60, "optional": 40})
        self.assertAlmostEqual(result["gs"], 3.6)
        self.assertAlmostEqual(result["optional"], 2.4)

    def test_unused_optional_learning_capacity_can_move_to_gs(self):
        result = learning_split(6, {"gs": 12, "optional": 1}, {"gs": 60, "optional": 40})
        self.assertAlmostEqual(result["gs"], 5)
        self.assertAlmostEqual(result["optional"], 1)

    def test_fixed_work_consumes_existing_pools_not_extra_capacity(self):
        quotas = daily_quotas(10, DEFAULT_PLANNER["allocations"]["integrated"], fixed_hours=3)
        self.assertAlmostEqual(sum(quotas.values()), 7)

    def test_allocation_totals_are_validated(self):
        with self.assertRaises(ValueError):
            validate_planner({"allocations": {"integrated": {"gs": 90}}}, [])

    def test_auto_phase_uses_exam_dates(self):
        settings = {"examDates": {"prelims": "2028-05-20", "mains": "2028-08-20"}}
        self.assertEqual(preparation_phase("2026-10-21", settings, DEFAULT_PLANNER), "integrated")
        self.assertEqual(preparation_phase("2028-04-01", settings, DEFAULT_PLANNER), "prelims")
        self.assertEqual(preparation_phase("2028-06-01", settings, DEFAULT_PLANNER), "mains")


if __name__ == "__main__":
    unittest.main()