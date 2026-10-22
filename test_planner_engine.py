import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import planner
from planner import DEFAULT_PLANNER, build_plan, daily_quotas
from test_preparation import isolated_backend


class PlannerEngineTests(unittest.TestCase):
    def setUp(self):
        self.backend = isolated_backend()
        self.data = self.backend["default_data"]()
        self.data["settings"].update(weekdayHours=6, weekendHours=6, examDates={})
        self.data.update(subjects=[], subjectCycles=[], studyLogs=[], completedRevisions={})
        self.data["cumulativeRevisions"] = {"sectionalBatches": []}

    def subject(self, subject_id, profile, stream="gs"):
        subject = {"id": subject_id, "name": subject_id, "color": "#123456", "topics": [],
                   "studyStream": stream, "strategy": {"profile": profile}}
        self.data["subjects"].append(subject)
        return subject

    def topic(self, subject, topic_id, **overrides):
        topic = {"id": topic_id, "name": topic_id, "estimatedHours": 10,
                 "status": "not-started", "activeStages": ["R1"], "examType": "both"}
        topic.update(overrides)
        subject["topics"].append(topic)
        return topic

    def plan(self, **kwargs):
        return build_plan(self.data, "2026-10-21", kwargs.get("hours", lambda data, topic: {
            stage: 1.8 for stage in self.backend["get_topic_stages"](data, topic["id"])
        }), self.backend["get_topic_stages"], self.backend["get_confidence_multiplier"])

    def assert_budget(self, plan):
        for load in plan["days"].values():
            self.assertLessEqual(load["totalHours"], load["budget"] + 0.00001)
            self.assertAlmostEqual(load["totalHours"], sum(item["hours"] for item in load["activities"]), places=5)

    def test_integrated_weekly_pools_match_two_stream_baseline(self):
        quotas = daily_quotas(45, DEFAULT_PLANNER["allocations"]["integrated"])
        for pool, expected in {"gs": 18, "optional": 12, "recall": 7,
                               "practice": 5, "currentAffairs": 3}.items():
            self.assertAlmostEqual(quotas[pool], expected, delta=0.005)
        self.assertAlmostEqual(sum(quotas.values()), 45)

    def test_both_started_lanes_are_planned_without_mutation_or_progress(self):
        self.topic(self.subject("economy", "economy"), "gs", status="learning", startDate="2026-10-20")
        self.topic(self.subject("soc1", "sociology1", "optional"), "optional", examType="mains",
                   status="learning", startDate="2026-10-20")
        before = copy.deepcopy(self.data)
        plan = self.plan()
        lanes = plan["days"]["2026-10-21"]["streams"]
        self.assertEqual(lanes["gs"]["topicId"], "gs")
        self.assertEqual(lanes["optional"]["topicId"], "optional")
        self.assertFalse(lanes["gs"]["isSuggested"])
        self.assertEqual(lanes["gs"]["remaining"], 10)
        self.assertEqual(self.data, before)
        self.assert_budget(plan)

    def test_default_order_resists_file_reordering_and_config_can_override(self):
        for profile in ("polity", "geography", "economy", "history", "environment"):
            self.topic(self.subject(profile, profile), profile, status="completed", completionDate="2026-10-20")
        first = self.plan()
        self.data["subjects"].reverse()
        second = self.plan()
        self.assertEqual(first["estimates"], second["estimates"])
        self.assertEqual(first["days"]["2026-10-21"]["activities"][0]["topicId"], "economy")
        self.data["settings"]["planner"] = {"gsSubjectOrder": ["polity"]}
        self.assertEqual(self.plan()["days"]["2026-10-21"]["activities"][0]["topicId"], "polity")

    def test_actual_logs_consume_capacity_and_remaining_only_once(self):
        self.topic(self.subject("gs", "economy"), "gs", status="learning", startDate="2026-01-01")
        self.topic(self.subject("optional", "sociology1", "optional"), "optional")
        self.data["studyLogs"] = [{"topicId": "gs", "date": "2026-10-20", "hours": 2},
                                  {"topicId": "gs", "date": "2026-10-21", "hours": 1}]
        plan = self.plan()
        day = plan["days"]["2026-10-21"]
        learning = [item for item in day["activities"] if item.get("topicId") == "gs"]
        self.assertAlmostEqual(sum(item["hours"] for item in learning), 4.0002)
        self.assertAlmostEqual(learning[-1]["remaining"], 7)
        for load in plan["days"].values():
            for item in load["activities"]:
                if item["category"] == "learning" and item["topicId"] == "gs":
                    self.assertEqual(item["remaining"], 7)
        self.assertIsNone(plan["estimates"]["gs"]["completionDate"])
        self.assertEqual(plan["summary"]["remainingLearningHours"], 7)
        self.assert_budget(plan)

    def test_multiple_started_topics_share_priority_capacity_without_completion(self):
        subject = self.subject("gs", "economy")
        for topic_id, roi in (("low", "low"), ("blank", None), ("empty", ""), ("medium", "medium"),
                              ("high", "high"), ("very-high", "very-high")):
            self.topic(subject, topic_id, status="learning", estimatedHours=None,
                       startDate="2026-10-20", roi=roi)
        before = copy.deepcopy(self.data)
        plan = self.plan()
        activities = [item for item in plan["days"]["2026-10-21"]["activities"] if item["category"] == "learning"]
        hours = {item["topicId"]: item["hours"] for item in activities}
        self.assertEqual(set(hours), {"very-high", "high", "medium", "blank", "empty", "low"})
        self.assertEqual(plan["days"]["2026-10-21"]["streams"]["gs"]["topicId"], "very-high")
        self.assertGreater(hours["very-high"], hours["high"])
        self.assertGreater(hours["high"], hours["medium"])
        self.assertEqual(hours["blank"], hours["medium"])
        self.assertEqual(hours["empty"], hours["medium"])
        self.assertGreater(hours["medium"], hours["low"])
        self.assertTrue(all(item["remaining"] is None for item in activities))
        self.assertEqual(plan["summary"]["warnings"], [])
        for estimate in plan["estimates"].values():
            self.assertIsNone(estimate["completionDate"])
            self.assertIsNone(estimate["masteryDate"])
            self.assertTrue(all(value is None for value in estimate["revisionSchedule"].values()))
        self.assertEqual(self.data, before)
        self.assert_budget(plan)

    def test_prerequisites_need_actual_completion_not_learning_reservations(self):
        subject = self.subject("gs", "economy")
        self.topic(subject, "dependent", prerequisiteIds=["foundation"], estimatedHours=1,
                   status="learning", startDate="2026-10-20")
        foundation = self.topic(subject, "foundation", estimatedHours=1,
                                status="learning", startDate="2026-10-20")
        plan = self.plan()
        self.assertFalse(any(item.get("topicId") == "dependent" for load in plan["days"].values()
                             for item in load["activities"]))
        foundation.update(status="completed", completionDate="2026-10-20")
        entries = self.plan()["days"]["2026-10-21"]["activities"]
        self.assertTrue(any(item.get("topicId") == "dependent" for item in entries))

    def test_learning_logs_start_topic_but_revision_or_future_logs_do_not(self):
        subject = self.subject("gs", "economy")
        for topic_id in ("logged", "revision-only", "future", "zero", "invalid", "missing-start"):
            self.topic(subject, topic_id, estimatedHours=None, status="learning", startDate=None)
        subject["topics"][-2]["startDate"] = "invalid-date"
        self.data["studyLogs"] = [
            {"topicId": "logged", "date": "2026-10-20", "hours": 1},
            {"topicId": "revision-only", "date": "2026-10-20", "hours": 1, "stage": "R1"},
            {"topicId": "future", "date": "2026-10-22", "hours": 1},
            {"topicId": "zero", "date": "2026-10-20", "hours": 0},
        ]
        plan = self.plan()
        entries = [item for load in plan["days"].values() for item in load["activities"] if item["category"] == "learning"]
        self.assertEqual({item["topicId"] for item in entries}, {"logged"})
        self.assertEqual(plan["estimates"]["logged"]["startDate"], "2026-10-20")
        self.assertEqual(plan["summary"]["schedulingErrors"], [])

    def test_actual_history_is_visible_without_reserving_capacity(self):
        self.topic(self.subject("gs", "economy"), "done", status="completed", completionDate="2026-10-19")
        self.data["completedRevisions"] = {"done_R1": {"completedAt": "2026-10-20"}}
        self.data["studyLogs"] = [{"topicId": "done", "date": "2026-10-19", "hours": 3}]
        before = copy.deepcopy(self.data)
        tasks = self.backend["get_tasks_for_date"](self.data, "2026-10-20")
        self.assertTrue(tasks[0]["done"])
        self.assertEqual(tasks[0]["hours"], 0)
        historical = self.backend["compute_daily_load"](self.data, "2026-10-19")
        self.assertEqual(historical["learningHours"], 3)
        self.assertEqual(self.data, before)

    def test_partial_stages_split_and_conserve_remaining_hours(self):
        self.data["settings"].update(weekdayHours=0.8, weekendHours=0.8)
        self.topic(self.subject("gs", "economy"), "done", status="completed", completionDate="2026-10-20",
                   stageProgress={"R1": {"hours": 0.4}}, activeStages=["R1", "PYQ", "ERA"])
        plan = self.plan()
        step = plan["schedules"]["done"]["r1"]
        self.assertGreater(len(step["sessions"]), 1)
        self.assertAlmostEqual(sum(session["hours"] for session in step["sessions"]), 1.4, places=5)
        for stage in ("pyq", "era"):
            self.assertEqual(plan["schedules"]["done"][stage]["sessions"], [])
            self.assertFalse(plan["schedules"]["done"][stage]["canMark"])
        self.assertAlmostEqual(plan["summary"]["remainingFollowUpHours"], 1.4)
        self.assertIsNone(plan["estimates"]["done"]["masteryDate"])
        self.assert_budget(plan)

    def test_stage_logs_do_not_inflate_learning_depth_or_double_spend(self):
        self.topic(self.subject("gs", "economy"), "done", status="completed", completionDate="2026-10-20")
        self.data["studyLogs"] = [{"topicId": "done", "date": "2026-10-20", "hours": 5},
                                  {"topicId": "done", "date": "2026-10-21", "hours": 0.4, "type": "r1"}]
        plan = self.backend["_build_preparation_plan"](self.data)
        step = plan["schedules"]["done"]["r1"]
        self.assertEqual(step["hours"], 1.5)
        self.assertAlmostEqual(sum(session["hours"] for session in step["sessions"]), 1.1)
        self.assertAlmostEqual(sum(load["revisionHours"] for load in plan["days"].values()), 1.5)
        self.assertEqual(plan["days"]["2026-10-21"]["learningHours"], 0)
        self.assert_budget(plan)

    def test_dependencies_writing_does_not_gate_r30(self):
        self.topic(self.subject("gs", "economy"), "done", status="completed", completionDate="2026-10-20",
                   activeStages=list(planner.STAGES))
        plan = self.plan(hours=lambda data, topic: {stage: 200 if stage == "MAINS" else 1 for stage in planner.STAGES})
        schedule = plan["schedules"]["done"]
        self.assertIsNotNone(schedule["r1"]["date"])
        for stage in set(schedule) - {"r1"}:
            self.assertIsNone(schedule[stage]["date"])
            self.assertEqual(schedule[stage]["sessions"], [])
            self.assertIsNone(schedule[stage]["dueDate"])
        self.data["completedRevisions"] = {
            f"done_{stage}": {"completedAt": "2026-10-20"}
            for stage in planner.STAGES if stage not in ("R30", "MAINS")
        }
        updated = self.plan(hours=lambda data, topic: {stage: 200 if stage == "MAINS" else 1 for stage in planner.STAGES})
        self.assertIsNotNone(updated["schedules"]["done"]["r30"]["date"])
        self.assertIsNotNone(updated["schedules"]["done"]["mains"]["date"])
        self.assertIsNone(updated["estimates"]["done"]["masteryDate"])
        self.assert_budget(updated)

    def test_unavailable_writing_pool_does_not_block_final_recall(self):
        self.data["settings"]["planner"] = {"weekendConsolidation": False, "allocations": {"integrated": {
            "gs": 40, "optional": 40, "recall": 20, "practice": 0, "currentAffairs": 0}}}
        gs = self.subject("gs", "economy")
        self.topic(gs, "reviewed", status="completed", completionDate="2026-10-20",
                   activeStages=["R1", "R3", "R7", "MAINS", "R30"])
        self.data["completedRevisions"] = {f"reviewed_{stage}": {"completedAt": "2026-10-01"}
                                            for stage in ("R1", "R3", "R7")}
        self.topic(gs, "gs-learning", estimatedHours=None, status="learning", startDate="2026-10-20")
        self.topic(self.subject("optional", "sociology1", "optional"), "optional-learning",
                   estimatedHours=None, status="learning", startDate="2026-10-20")
        schedule = self.plan()["schedules"]["reviewed"]
        self.assertIsNotNone(schedule["r30"]["date"])
        self.assertIsNone(schedule["mains"]["date"])

    def test_due_optional_recall_is_not_starved_by_subject_order(self):
        gs = self.subject("gs", "economy")
        optional = self.subject("optional", "sociology1", "optional")
        for index in range(12):
            self.topic(gs, f"gs-old-{index}", status="completed", completionDate="2026-10-20")
        self.topic(optional, "optional-old", status="completed", completionDate="2026-10-01", examType="mains")
        self.topic(gs, "gs-learning", estimatedHours=1000)
        self.topic(optional, "optional-learning", estimatedHours=1000, examType="mains")
        plan = self.plan()
        first_day = plan["days"]["2026-10-21"]["activities"]
        optional_recall = sum(item["hours"] for item in first_day
                              if item["category"] == "revision" and item["topicId"] == "optional-old")
        self.assertGreater(optional_recall, 0)
        self.assert_budget(plan)

    def test_completed_stage_log_still_consumes_today_capacity(self):
        gs = self.subject("gs", "economy")
        self.topic(gs, "reviewed", status="completed", completionDate="2026-10-20")
        self.topic(gs, "gs-learning", estimatedHours=100)
        self.topic(self.subject("optional", "sociology1", "optional"), "optional-learning", estimatedHours=100)
        self.data["studyLogs"] = [{"topicId": "reviewed", "date": "2026-10-21", "hours": 1.5, "stage": "R1"}]
        before = self.plan()["days"]["2026-10-21"]
        self.data["completedRevisions"]["reviewed_R1"] = {"completedAt": "2026-10-21"}
        after = self.plan()["days"]["2026-10-21"]
        actual = lambda load: sum(item["hours"] for item in load["activities"] if item.get("isActual"))
        self.assertEqual(actual(before), 1.5)
        self.assertEqual(actual(after), 1.5)
        self.assertLessEqual(after["totalHours"], after["budget"])

    def test_consolidation_waits_for_mcq_when_analysis_is_disabled(self):
        self.topic(self.subject("gs", "economy"), "topic", status="completed", completionDate="2026-10-01",
                   activeStages=["MN", "MCQ", "R7"])
        self.data["completedRevisions"] = {"topic_MN": {"completedAt": "2026-10-10"}}
        plan = self.plan(hours=lambda data, topic: {"MN": 1, "MCQ": 100, "R7": 1})
        schedule = plan["schedules"]["topic"]
        self.assertIsNotNone(schedule["mcq"]["date"])
        self.assertIsNone(schedule["r7"]["date"])
        self.assertEqual(schedule["r7"]["sessions"], [])
        self.data["completedRevisions"]["topic_MCQ"] = {"completedAt": "2026-10-20"}
        self.assertGreaterEqual(self.plan()["schedules"]["topic"]["r7"]["date"], "2026-10-25")

    def test_recall_backlog_pauses_only_new_learning_in_that_stream(self):
        gs = self.subject("gs", "economy")
        self.topic(gs, "overdue", status="completed", completionDate="2026-10-01")
        self.topic(gs, "next-gs", estimatedHours=10)
        self.topic(self.subject("optional", "sociology1", "optional"), "optional", estimatedHours=100,
                   status="learning", startDate="2026-10-20")
        plan = self.plan()
        day = plan["days"]["2026-10-21"]
        self.assertIn("gs", day["backlogGuard"])
        self.assertFalse(any(item["category"] == "learning" and item["stream"] == "gs" for item in day["activities"]))
        self.assertGreater(day["streams"]["optional"]["hours"], 0)
        self.assert_budget(plan)

    def test_recall_guard_does_not_interrupt_an_active_learning_topic(self):
        gs = self.subject("gs", "economy")
        self.topic(gs, "overdue", status="completed", completionDate="2026-10-01")
        self.topic(gs, "in-progress", estimatedHours=10, status="learning", startDate="2026-10-20")
        plan = self.plan()
        self.assertGreater(plan["days"]["2026-10-21"]["streams"]["gs"]["hours"], 0)

    def test_second_recall_does_not_wait_for_long_error_analysis(self):
        self.topic(self.subject("gs", "economy"), "topic", status="completed", completionDate="2026-10-20",
                   activeStages=["R1", "ERA", "R3"])
        plan = self.plan(hours=lambda data, topic: {"R1": 1, "ERA": 100, "R3": 1})
        schedule = plan["schedules"]["topic"]
        self.assertIsNone(schedule["r3"]["date"])
        self.data["completedRevisions"]["topic_R1"] = {"completedAt": "2026-10-20"}
        schedule = self.plan(hours=lambda data, topic: {"R1": 1, "ERA": 100, "R3": 1})["schedules"]["topic"]
        self.assertLess(schedule["r3"]["date"], schedule["era"]["date"])

    def test_milestones_separate_coverage_pipeline_and_exam_scope(self):
        self.data["settings"]["examDates"] = {"prelims": "2026-10-25", "mains": "2026-11-01"}
        self.topic(self.subject("gs", "economy"), "gs", estimatedHours=1, activeStages=["R30"])
        self.topic(self.subject("optional", "sociology1", "optional"), "optional", estimatedHours=50, examType="mains")
        plan = self.plan()
        summary = plan["summary"]
        self.assertEqual(summary["milestones"]["prelims"]["finishDate"], plan["estimates"]["gs"]["prelimsFinishDate"])
        self.assertEqual(summary["milestones"]["prelims"]["lateTopics"], [])
        self.assertEqual(summary["milestones"]["prelims"]["unscheduledTopics"], [])
        self.assertIsNone(summary["streams"]["gs"]["coverageDate"])
        self.assertIsNone(summary["streams"]["gs"]["pipelineDate"])
        self.assertEqual(summary["attemptYear"], 2028)

    def test_pre_and_post_prelims_phases_change_daily_pools(self):
        self.data["settings"]["examDates"] = {"prelims": "2026-10-23", "mains": "2026-11-30"}
        self.topic(self.subject("gs", "economy"), "gs", estimatedHours=100,
                   status="learning", startDate="2026-10-20")
        self.topic(self.subject("optional", "sociology1", "optional"), "optional", estimatedHours=100,
                   status="learning", startDate="2026-10-20")
        plan = self.plan()
        first, post = plan["days"]["2026-10-21"], plan["days"]["2026-10-24"]
        self.assertEqual(first["phase"], "prelims")
        self.assertEqual(post["phase"], "mains")
        self.assertAlmostEqual(first["streams"]["optional"]["hours"], 0.3)
        self.assertAlmostEqual(post["streams"]["optional"]["hours"], 0.6)

    def test_zero_budget_missing_dates_and_dependencies_stay_unknown(self):
        self.data["settings"].update(weekdayHours=0, weekendHours=0)
        self.topic(self.subject("gs", "economy"), "blocked", prerequisiteIds=["missing"],
                   status="learning", startDate="2026-10-20")
        plan = self.plan()
        self.assertIsNone(plan["estimates"]["blocked"]["masteryDate"])
        self.assertIsNone(plan["summary"]["milestones"]["prelims"]["finishDate"])
        self.assertEqual(len(plan["summary"]["milestones"]["prelims"]["unscheduledTopics"]), 1)
        self.assertIsNone(plan["summary"]["milestones"]["prelims"]["deadline"])

    def test_impossible_prerequisite_with_positive_budget_stays_unknown(self):
        self.topic(self.subject("gs", "economy"), "blocked", prerequisiteIds=["missing"],
                   status="learning", startDate="2026-10-20")
        plan = self.plan()
        self.assertIsNone(plan["estimates"]["blocked"]["completionDate"])
        self.assertIsNone(plan["summary"]["overallFinishDate"])
        self.assertTrue(plan["summary"]["schedulingErrors"])
        self.assertLessEqual(plan["summary"]["simulationDays"], 3650)

    def test_confidence_adjusts_recall_and_weekend_consolidation_is_configurable(self):
        topic = self.topic(self.subject("gs", "economy"), "done", status="completed",
                           completionDate="2026-10-20", activeStages=["R1", "R3"])
        self.data["completedRevisions"] = {"done_R1": {"completedAt": "2026-10-21", "confidence": 1}}
        hard = self.plan()["schedules"]["done"]["r3"]["date"]
        self.data["completedRevisions"]["done_R1"]["confidence"] = 3
        easy = self.plan()["schedules"]["done"]["r3"]["date"]
        self.assertLess(hard, easy)
        topic["activeStages"] = ["R7"]
        self.data["settings"]["planner"] = {"weekendConsolidation": False}
        weekday = self.plan()["schedules"]["done"]["r7"]["date"]
        self.data["settings"]["planner"]["weekendConsolidation"] = True
        weekend = self.plan()["schedules"]["done"]["r7"]["date"]
        self.assertLess(weekday, weekend)

    def test_completed_stage_without_time_log_is_history_not_synthetic_time(self):
        self.topic(self.subject("gs", "economy"), "done", status="completed", completionDate="2026-10-20")
        self.data["completedRevisions"] = {"done_R1": {"completedAt": "2026-10-21"}}
        plan = self.backend["_build_preparation_plan"](self.data)
        load = self.backend["compute_daily_load"](self.data, "2026-10-21")
        self.assertEqual(plan["days"]["2026-10-21"], load)
        self.assertEqual(load["estimatedSpentHours"], 0)
        self.assertEqual(load["actualHours"], 0)
        self.assertEqual(load["plannedHours"], 0)
        self.assertTrue(load["activities"][0]["done"])
        self.assertTrue(load["activities"][0]["displayOnly"])
        self.assertEqual(plan["estimates"]["done"]["masteryDate"], "2026-10-21")

    def test_exhausted_zero_stage_pool_does_not_fabricate_dates(self):
        self.data["settings"]["planner"] = {"allocations": {"integrated": {
            "gs": 40, "optional": 40, "recall": 0, "practice": 0, "currentAffairs": 20}}}
        self.topic(self.subject("gs", "economy"), "gs", estimatedHours=None, status="learning", startDate="2026-10-20")
        self.topic(self.subject("optional", "sociology1", "optional"), "optional", estimatedHours=None,
                   status="learning", startDate="2026-10-20")
        self.topic(self.data["subjects"][0], "done", status="completed", completionDate="2026-10-20")
        plan = self.plan()
        self.assertIsNone(plan["schedules"]["done"]["r1"]["date"])
        self.assertEqual(plan["summary"]["simulationDays"], 3650)

    def test_overdue_keeps_original_date_and_is_not_charged_twice(self):
        topic = self.topic(self.subject("gs", "economy"), "done", status="completed", completionDate="2026-10-01")
        topic["revisionSchedule"] = {"r1": {"date": "2026-10-02"}}
        overdue = self.backend["get_overdue_tasks"](self.data)
        self.assertEqual(overdue[0]["date"], "2026-10-02")
        plain = self.backend["compute_daily_load"](self.data, "2026-10-21")
        enriched = self.backend["compute_daily_load"](self.data, "2026-10-21", include_overdue=True)
        self.assertEqual(plain["totalHours"], enriched["totalHours"])

    def test_daily_forecast_tasks_and_cache_share_one_build(self):
        self.topic(self.subject("gs", "economy"), "gs", estimatedHours=1,
                   status="learning", startDate="2026-10-20")
        self.topic(self.subject("optional", "sociology1", "optional"), "optional", estimatedHours=1,
                   status="learning", startDate="2026-10-20")
        with patch.object(planner, "build_plan", wraps=planner.build_plan) as engine:
            forecast = self.backend["estimate_all_timelines"](self.data)
            for offset in range(31):
                day = self.backend["add_days"]("2026-10-21", offset)
                load = self.backend["compute_daily_load"](self.data, day)
                tasks = self.backend["get_tasks_for_date"](self.data, day)
                learning = self.backend["_simulate_learning_for_date"](self.data, day)
                self.assertAlmostEqual(sum(item["hours"] for item in tasks), load["revisionHours"])
                self.assertAlmostEqual(sum(item["hours"] for item in learning.values()), load["learningHours"])
                self.assertEqual(tasks, [])
                self.assertGreater(load["learningHours"], 0)
                self.assertEqual(load["actualHours"], 0)
            self.assertEqual(engine.call_count, 1)
            self.data["subjects"][0]["topics"][0]["estimatedHours"] += 1
            self.backend["estimate_all_timelines"](self.data)
            self.assertEqual(engine.call_count, 2)
        self.assertEqual(forecast["summary"]["totalTopics"], 2)

    def test_standard_seed_211_topics_are_catalog_only_without_false_exam_warnings(self):
        self.data = json.loads(Path(__file__).with_name("data").joinpath("upsc_subjects_seed.json").read_text(encoding="utf-8-sig"))
        for subject in self.data["subjects"]:
            for topic in subject["topics"]:
                topic.update(estimatedHours=None, roi=None)
        self.data["settings"]["examDates"] = {"prelims": "2026-10-22", "mains": "2026-10-23"}
        before = copy.deepcopy(self.data)
        plan = self.backend["_build_preparation_plan"](self.data)
        self.assertEqual(len(plan["estimates"]), 211)
        self.assertEqual(plan["summary"]["schedulingErrors"], [])
        self.assertEqual(plan["summary"]["warnings"], [])
        self.assertEqual(plan["summary"]["unscheduledTopics"], 0)
        self.assertEqual(plan["summary"]["notStarted"], 211)
        self.assertEqual(plan["summary"]["totalPlannedHours"], 0)
        self.assertEqual(plan["summary"]["remainingLearningHours"], 0)
        self.assertEqual(plan["summary"]["remainingFollowUpHours"], 0)
        for exam in ("prelims", "mains"):
            self.assertEqual(plan["summary"]["milestones"][exam]["lateTopics"], [])
            self.assertEqual(plan["summary"]["milestones"][exam]["unscheduledTopics"], [])
        for load in plan["days"].values():
            self.assertEqual(load["activities"], [])
            self.assertEqual(load["remaining"], load["budget"])
        for estimate in plan["estimates"].values():
            for field in ("startDate", "completionDate", "masteryDate", "prelimsFinishDate", "mainsFinishDate"):
                self.assertIsNone(estimate[field])
            self.assertTrue(all(day is None for day in estimate["revisionSchedule"].values()))
        self.assertEqual(self.data, before)
        self.assert_budget(plan)


if __name__ == "__main__":
    unittest.main()