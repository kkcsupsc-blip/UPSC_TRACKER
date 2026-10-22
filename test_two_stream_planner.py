import copy
import unittest

from planner import (DEFAULT_PLANNER, STAGES, build_plan, daily_quotas, learning_split,
                     plan_day, preparation_phase, subject_stream, validate_planner)


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


class ProgressDrivenPlannerTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "settings": {"weekdayHours": 6, "weekendHours": 6,
                         "examDates": {"prelims": "2026-10-22", "mains": "2026-10-23"}},
            "subjects": [{"id": "gs", "name": "GS", "studyStream": "gs", "topics": []}],
            "studyLogs": [], "completedRevisions": {}, "subjectCycles": [],
            "cumulativeRevisions": {"sectionalBatches": []},
        }

    def topic(self, topic_id="topic", **overrides):
        topic = {"id": topic_id, "name": topic_id, "status": "not-started",
                 "estimatedHours": None, "roi": None, "activeStages": list(STAGES)}
        topic.update(overrides)
        self.data["subjects"][0]["topics"].append(topic)
        return topic

    def plan(self, today="2026-10-21", durations=None):
        return build_plan(self.data, today, lambda data, topic: durations or {stage: 1 for stage in STAGES},
                          lambda data, topic_id: next(topic["activeStages"] for subject in data["subjects"]
                                                      for topic in subject["topics"] if topic["id"] == topic_id))

    def test_catalog_never_calls_duration_callback_or_creates_work(self):
        self.topic(startDate="2026-10-01", completionDate="2026-10-02")
        def no_duration(data, topic):
            self.fail("Catalog duration callback must not run")
        plan = build_plan(self.data, "2026-10-21", no_duration, lambda data, topic_id: list(STAGES))
        self.assertEqual(plan["days"]["2026-10-21"]["activities"], [])
        self.assertEqual(plan["summary"]["totalPlannedHours"], 0)
        self.assertEqual(plan["summary"]["schedulingErrors"], [])
        self.assertEqual(plan["summary"]["warnings"], [])
        self.assertIsNone(plan["estimates"]["topic"]["queuePosition"])
        for exam in ("prelims", "mains"):
            self.assertEqual(plan["summary"]["milestones"][exam]["unscheduledTopics"], [])
            self.assertEqual(plan["summary"]["milestones"][exam]["lateTopics"], [])

    def test_unknown_duration_is_open_capacity_not_time_or_completion(self):
        self.topic(status="learning", startDate="2026-10-20")
        before = copy.deepcopy(self.data)
        first = self.plan()
        self.assertEqual(first, self.plan())
        for load in first["days"].values():
            self.assertGreater(load["learningHours"], 0)
            self.assertEqual(load["actualHours"], 0)
            self.assertEqual(load["revisionHours"], 0)
            self.assertIsNone(load["streams"]["gs"]["remaining"])
            self.assertLessEqual(load["totalHours"], load["budget"])
            self.assertFalse(any(item["category"] == "reserve" for item in load["activities"]))
        estimate = first["estimates"]["topic"]
        for field in ("completionDate", "masteryDate", "prelimsFinishDate", "mainsFinishDate"):
            self.assertIsNone(estimate[field])
        self.assertEqual(first["summary"]["schedulingErrors"], [])
        self.assertEqual(first["summary"]["milestones"]["prelims"]["unscheduledTopics"], [])
        self.assertEqual(self.data, before)

    def test_known_duration_exceeded_by_actual_logs_still_needs_explicit_completion(self):
        self.topic(status="learning", estimatedHours=1, startDate="2026-10-20")
        self.data["studyLogs"] = [{"topicId": "topic", "date": "2026-10-20", "hours": 2}]
        plan = self.plan()
        self.assertGreater(plan["days"]["2026-10-21"]["learningHours"], 0)
        self.assertEqual(plan["summary"]["remainingLearningHours"], 0)
        self.assertIsNone(plan["estimates"]["topic"]["completionDate"])
        self.assertTrue(all(not step["sessions"] for step in plan["schedules"]["topic"].values()))

    def test_actual_learning_log_starts_catalog_topic_with_unknown_duration(self):
        self.data["settings"]["planner"] = {"phase": "integrated"}
        self.topic()
        self.data["studyLogs"] = [{"topicId": "topic", "date": "2026-10-21", "hours": 2}]
        plan = self.plan()
        load = plan["days"]["2026-10-21"]
        self.assertEqual(load["actualHours"], 2)
        self.assertAlmostEqual(load["learningHours"], 4.0002)
        self.assertTrue(all(item["remaining"] is None for item in load["activities"]))
        self.assertEqual(plan["summary"]["notStarted"], 0)
        self.assertEqual(plan["summary"]["learning"], 1)
        self.assertIsNone(plan["estimates"]["topic"]["completionDate"])

    def test_explicit_completion_releases_first_stage_not_whole_chain(self):
        topic = self.topic(status="learning", startDate="2026-10-20")
        self.assertEqual(self.plan()["days"]["2026-10-21"]["revisionHours"], 0)
        topic.update(status="completed", completionDate="2026-10-20")
        plan = self.plan()
        self.assertTrue(plan["schedules"]["topic"]["r1"]["sessions"])
        for stage in set(plan["schedules"]["topic"]) - {"r1"}:
            self.assertEqual(plan["schedules"]["topic"][stage]["sessions"], [])
            self.assertIsNone(plan["schedules"]["topic"][stage]["originalDate"])
            self.assertFalse(plan["schedules"]["topic"][stage]["canMark"])
        self.assertIsNone(plan["estimates"]["topic"]["masteryDate"])
        self.data["completedRevisions"]["topic_R1"] = {"completedAt": "2026-10-21"}
        updated = self.plan()
        self.assertTrue(updated["schedules"]["topic"]["pyq"]["sessions"])
        self.assertTrue(updated["schedules"]["topic"]["r3"]["sessions"])
        self.assertEqual(updated["schedules"]["topic"]["era"]["sessions"], [])

    def test_fully_logged_stage_does_not_unlock_successor_until_marked_done(self):
        self.topic(status="completed", completionDate="2026-10-20", activeStages=["R1", "PYQ"])
        self.data["studyLogs"] = [{"topicId": "topic", "date": "2026-10-21", "hours": 1, "stage": "R1"}]
        plan = self.plan()
        self.assertFalse(plan["schedules"]["topic"]["r1"]["done"])
        self.assertEqual(plan["schedules"]["topic"]["pyq"]["sessions"], [])
        self.assertIsNone(plan["estimates"]["topic"]["masteryDate"])
        self.assertEqual(plan["days"]["2026-10-21"]["actualHours"], 1)
        self.assertTrue(any(item.get("displayOnly") and item.get("canMark") for item in plan["days"]["2026-10-21"]["activities"]))

    def test_earned_priority_carry_forward_preserves_due_date_and_actual_progress(self):
        for topic_id, roi in (("low", "low"), ("blank", None), ("high", "high")):
            self.topic(topic_id, status="completed", completionDate="2026-10-01", roi=roi,
                       activeStages=["R1", "PYQ"], revisionSchedule={"r1": {"date": "2026-10-02"}})
        self.data["settings"].update(weekdayHours=1, weekendHours=1)
        self.data["settings"]["planner"] = {"phase": "integrated", "allocations": {"integrated": {
            "gs": 40, "optional": 40, "recall": 20, "practice": 0, "currentAffairs": 0}}}
        self.data["subjectCycles"] = [{"id": "manual", "startDate": "2026-10-21", "endDate": "2026-10-21",
                                       "hoursPerDay": 1, "completed": False}]
        plan = self.plan()
        self.assertEqual(plan["days"]["2026-10-21"]["cumulativeHours"], 1)
        self.assertEqual(plan["days"]["2026-10-21"]["revisionHours"], 0)
        next_day = plan["days"]["2026-10-22"]["activities"]
        self.assertEqual(next_day[0]["topicId"], "high")
        self.data["studyLogs"] = [{"topicId": "high", "date": "2026-10-21", "hours": 0.25, "stage": "R1"}]
        carried = self.plan("2026-10-22")
        self.assertEqual(carried["days"]["2026-10-22"]["activities"][0]["topicId"], "high")
        for topic_id, expected in (("high", 0.75), ("blank", 1), ("low", 1)):
            step = carried["schedules"][topic_id]["r1"]
            self.assertEqual(step["originalDate"], "2026-10-02")
            self.assertAlmostEqual(sum(item["hours"] for item in step["sessions"]), expected)
            self.assertEqual(carried["schedules"][topic_id]["pyq"]["sessions"], [])
        for load in carried["days"].values():
            self.assertLessEqual(load["totalHours"], load["budget"])
        self.assertEqual(self.data["completedRevisions"], {})

    def test_all_supported_priorities_order_earned_recall_and_practice(self):
        for stage in ("R1", "PYQ"):
            with self.subTest(stage=stage):
                self.data["subjects"][0]["topics"] = []
                self.data["settings"].update(weekdayHours=1, weekendHours=1)
                self.data["settings"]["planner"] = {"phase": "integrated"}
                for topic_id, roi in (("low", "low"), ("blank", None), ("empty", ""),
                                      ("medium", "medium"), ("high", "high"), ("very-high", "very-high")):
                    self.topic(topic_id, status="completed", completionDate="2026-10-01", roi=roi,
                               activeStages=[stage])
                plan = self.plan()
                ordered = list(dict.fromkeys(
                    item["topicId"] for load in plan["days"].values() for item in load["activities"]
                    if item["category"] == "revision"))
                self.assertEqual(ordered, ["very-high", "high", "blank", "empty", "medium", "low"])
                for load in plan["days"].values():
                    self.assertLessEqual(load["totalHours"], load["budget"])

    def test_actual_logs_for_disabled_stages_still_consume_capacity(self):
        self.data["settings"]["planner"] = {"phase": "integrated"}
        self.topic(status="learning", startDate="2026-10-20", activeStages=["R1"])
        self.data["studyLogs"] = [{"topicId": "topic", "date": "2026-10-21", "hours": 2, "stage": "MCQ"}]
        plan = self.plan()
        load = plan["days"]["2026-10-21"]
        self.assertEqual(load["actualHours"], 2)
        self.assertEqual(load["revisionHours"], 2)
        self.assertLessEqual(load["totalHours"], load["budget"])
        self.assertNotIn("mcq", plan["schedules"]["topic"])
        self.assertIsNone(plan["estimates"]["topic"]["completionDate"])

    def test_actual_history_with_unknown_duration_and_manual_work_survives(self):
        self.topic(status="completed", completionDate="2026-10-19", activeStages=["R1"])
        self.data["studyLogs"] = [{"topicId": "topic", "date": "2026-10-19", "hours": 3}]
        self.data["completedRevisions"] = {"topic_R1": {"completedAt": "2026-10-20"}}
        self.data["subjectCycles"] = [{"id": "cycle", "startDate": "2026-10-21", "endDate": "2026-10-21",
                                       "hoursPerDay": 2, "completed": False}]
        self.data["cumulativeRevisions"]["sectionalBatches"] = [{"id": "batch", "sessions": [
            {"round": 1, "scheduledDate": "2026-10-22", "completed": False}]}]
        plan = self.plan()
        self.assertEqual(plan_day(plan, self.data, "2026-10-19")["actualHours"], 3)
        self.assertTrue(plan_day(plan, self.data, "2026-10-20")["activities"][0]["done"])
        self.assertEqual(plan["estimates"]["topic"]["masteryDate"], "2026-10-20")
        self.assertEqual(plan["days"]["2026-10-21"]["cumulativeHours"], 2)
        self.assertEqual(plan["days"]["2026-10-22"]["cumulativeHours"], 6)
        self.assertEqual(plan["days"]["2026-10-23"]["cumulativeHours"], 6)


if __name__ == "__main__":
    unittest.main()