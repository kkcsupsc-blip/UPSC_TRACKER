import copy
import unittest
from datetime import datetime

from flask import Flask

from test_preparation import isolated_backend


class SchedulerUpdatesTests(unittest.TestCase):
    def setUp(self):
        self.backend = isolated_backend()
        self.data = self.backend["default_data"]()
        self.data["settings"].update(weekdayHours=6, weekendHours=6)
        self.data["subjects"] = [{
            "id": "subject", "name": "Subject", "color": "#123456",
            "topics": [],
        }]
        self.data["subjectCycles"] = []
        self.data["cumulativeRevisions"] = {"sectionalBatches": []}
        self.data["studyLogs"] = []
        self.data["completedRevisions"] = {}

    def topic(self, topic_id="topic", **overrides):
        topic = {
            "id": topic_id, "name": topic_id, "status": "completed",
            "estimatedHours": 20, "completionDate": "2026-10-20",
            "startDate": "2026-10-20", "roi": "high", "examType": "both",
            "activeStages": ["R1"],
        }
        topic.update(overrides)
        self.data["subjects"][0]["topics"].append(topic)
        return topic

    def test_large_feasible_course_is_not_truncated_at_400_days(self):
        self.data["settings"].update(weekdayHours=3, weekendHours=3)
        for index in range(40):
            self.topic(f"topic-{index}", status="not-started", estimatedHours=40,
                       startDate=None, completionDate=None)
        result = self.backend["estimate_all_timelines"](self.data)
        self.assertEqual(len(result["estimates"]), 40)
        self.assertTrue(all(item["masteryDate"] for item in result["estimates"].values()))
        self.assertIsNotNone(result["summary"]["overallFinishDate"])
        self.assertEqual(result["summary"]["schedulingErrors"], [])

    def test_zero_study_hours_remain_unscheduled(self):
        self.data["settings"].update(weekdayHours=0, weekendHours=0)
        self.topic(status="not-started", startDate=None, completionDate=None)
        result = self.backend["estimate_all_timelines"](self.data)
        self.assertIsNone(result["summary"]["overallFinishDate"])
        self.assertEqual(result["summary"]["unscheduledTopics"], 1)
        self.assertIn("No study hours configured", result["summary"]["schedulingErrors"][0]["error"])

    def test_forecast_safety_limit_does_not_invent_a_finish_date(self):
        self.topic(status="not-started", startDate=None, completionDate=None, estimatedHours=1000000)
        result = self.backend["estimate_all_timelines"](self.data)
        self.assertEqual(result["summary"]["simulationDays"], 3650)
        self.assertIsNone(result["summary"]["overallFinishDate"])
        self.assertIn("planning horizon", result["summary"]["schedulingErrors"][0]["error"])

    def test_daily_load_and_learning_reserve_scaled_revision_hours(self):
        topic = self.topic()
        self.topic("learner", status="learning", estimatedHours=10,
                   startDate="2026-10-21", completionDate=None)
        schedules = {topic["id"]: {
            "r1": {"date": "2026-10-21", "type": "R1"},
        }}
        hours = self.backend["get_topic_scaled_hours"](
            self.backend["get_activity_hours"](self.data["settings"]), 20,
        )["R1"]
        load = self.backend["compute_daily_load"](
            self.data, "2026-10-21", resolved_schedules=schedules,
        )
        plan = self.backend["_build_preparation_plan"](self.data)
        self.assertEqual(load, plan["days"]["2026-10-21"])
        sessions = plan["schedules"]["topic"]["r1"]["sessions"]
        self.assertAlmostEqual(sum(session["hours"] for session in sessions), hours)
        self.assertLessEqual(load["revisionHours"] + load["learningHours"], 6)
        self.assertTrue(any(item["category"] == "reserve" for item in load["activities"]))

    def test_no_log_learning_does_not_invent_elapsed_progress(self):
        self.topic(status="learning", estimatedHours=10,
                   startDate="2026-10-20", completionDate=None)
        allocations = self.backend["_simulate_learning_for_date"](
            self.data, "2026-10-21", resolved_schedules={},
        )
        self.assertAlmostEqual(allocations["topic"]["hours"], 4.0002)
        self.assertAlmostEqual(allocations["topic"]["remaining"], 5.9998)

    def test_learning_reserves_subject_cycle_and_sectional_capacity(self):
        self.data["settings"].update(weekdayHours=12, weekendHours=12)
        self.topic(status="learning", estimatedHours=20,
                   startDate="2026-10-21", completionDate=None)
        self.data["subjectCycles"] = [{
            "id": "cycle", "subjectId": "subject", "subjectName": "Subject",
            "cycle": "R1", "label": "Recall", "completed": False,
            "startDate": "2026-10-21", "endDate": "2026-10-21",
            "durationDays": 1, "hoursPerDay": 2,
        }]
        self.data["cumulativeRevisions"]["sectionalBatches"] = [{
            "id": "batch", "sessions": [{
                "completed": False, "scheduledDate": "2026-10-21", "round": 1,
            }],
        }]
        per_day = self.backend["get_activity_hours"](
            self.data["settings"],
        )["sectionalBatch"] / 2
        allocations = self.backend["_simulate_learning_for_date"](
            self.data, "2026-10-21", resolved_schedules={},
        )
        load = self.backend["compute_daily_load"](self.data, "2026-10-21")
        self.assertEqual(load["cumulativeHours"], 2 + per_day)
        self.assertEqual(sum(item["hours"] for item in allocations.values()), load["learningHours"])
        self.assertLessEqual(load["totalHours"], 12)
        self.assertLess(load["learningHours"], max(0, 12 - 2 - per_day))

    def test_resolver_and_forecast_share_canonical_stage_placement(self):
        self.topic(activeStages=["R1", "PYQ", "ERA", "R3", "MN", "MCQ",
                                 "MCQA", "R7", "MVA", "MAINS", "R30"])
        resolved, used = self.backend["resolve_all_revision_schedules"](self.data)
        plan = self.backend["_build_preparation_plan"](self.data)
        self.assertEqual(plan["schedules"]["topic"], resolved["topic"])
        forecast = self.backend["estimate_all_timelines"](self.data)["estimates"]["topic"]
        self.assertEqual(forecast["revisionSchedule"], {key: step["date"] for key, step in resolved["topic"].items()})
        for day, hours in used.items():
            self.assertAlmostEqual(hours, plan["days"][day]["revisionHours"])
            self.assertLessEqual(hours, 6)

    def test_future_topics_respect_custom_stages_without_r30(self):
        for status, hours, start in [("learning", 10, "2026-10-01"),
                                     ("learning", 10, "2026-10-21"),
                                     ("not-started", 1, None),
                                     ("not-started", 10, None)]:
            with self.subTest(status=status, hours=hours, start=start):
                self.data["subjects"][0]["topics"] = []
                self.topic(status=status, estimatedHours=hours,
                           startDate=start, completionDate=None, activeStages=["R1"])
                estimate = self.backend["estimate_all_timelines"](self.data)["estimates"]["topic"]
                self.assertEqual(set(estimate["revisionSchedule"]), {"r1"})
                self.assertEqual(estimate["masteryDate"], estimate["revisionSchedule"]["r1"])

    def test_actual_completion_dates_anchor_dependents_without_reservations(self):
        self.topic(activeStages=["R1", "R3", "MN", "MCQ", "MCQA"])
        stamp = int(datetime(2026, 11, 10, 23, tzinfo=self.backend["timezone"].utc).timestamp() * 1000)
        self.data["completedRevisions"] = {
            "topic_R1": {"completedAt": stamp, "confidence": 2},
            "topic_MCQ": stamp,
        }
        resolved, used = self.backend["resolve_all_revision_schedules"](self.data)
        schedule = resolved["topic"]
        self.assertEqual(schedule["r1"]["date"], "2026-11-11")
        self.assertGreater(schedule["r3"]["date"], "2026-11-11")
        self.assertEqual(schedule["mcq"]["date"], "2026-11-11")
        self.assertGreaterEqual(schedule["mcqa"]["date"], "2026-11-11")
        self.assertEqual(schedule["r1"]["sessions"], [])
        self.assertEqual(schedule["mcq"]["sessions"], [])
        self.assertEqual(used["2026-11-11"], 0.5)

    def test_impossible_task_reports_error_without_partial_reservation(self):
        used = {"2026-10-22": 0.2}
        before = dict(used)
        with self.assertRaisesRegex(ValueError, "capacity|budget"):
            self.backend["calculate_revision_schedule_dynamic"](
                "2026-10-21", self.data["settings"]["intervals"],
                self.backend["get_activity_hours"](self.data["settings"]),
                used, 0.25, 0.25,
            )
        self.assertEqual(used, before)

    def test_estimator_reports_infeasible_revision_and_learning(self):
        self.data["settings"].update(weekdayHours=0, weekendHours=0)
        self.topic("done")
        self.topic("learning", status="learning", completionDate=None)
        before = copy.deepcopy(self.data)
        result = self.backend["estimate_all_timelines"](self.data)
        for topic_id in ("done", "learning"):
            estimate = result["estimates"][topic_id]
            self.assertIsNone(estimate["masteryDate"])
            self.assertTrue(estimate["schedulingError"])
        self.assertIsNone(result["estimates"]["learning"]["completionDate"])
        self.assertEqual(self.data, before)

    def cycle(self, cycle="R1", start="2026-10-21", duration=1, hours=2,
              subject_id="subject"):
        entry = {
            "id": f"{subject_id}_{cycle}", "subjectId": subject_id,
            "subjectName": subject_id, "cycle": cycle, "label": "Recall",
            "startDate": start, "endDate": self.backend["add_days"](start, duration - 1),
            "durationDays": duration, "hoursPerDay": hours, "completed": False,
        }
        self.data["subjectCycles"].append(entry)
        return entry

    def test_one_day_cycle_has_one_inclusive_budget_day(self):
        self.backend["load_data"] = lambda: self.data
        self.backend["save_data"] = lambda data: None
        self.backend["gen_id"] = lambda: "cycle"
        app = Flask(__name__)
        with app.test_request_context(method="POST", json={
            "subjectId": "subject", "cycle": "R1", "startDate": "2026-10-21",
            "durationDays": 1, "hoursPerDay": 2,
        }):
            response = self.backend["api_schedule_subject_cycle"]()
        self.assertEqual(response.get_json()["endDate"], "2026-10-21")
        loads = self.backend["_fixed_schedule_loads"](self.data)
        self.assertEqual(loads, {"2026-10-21": 2})

    def subject_cycle_suggestions(self):
        self.backend["load_data"] = lambda: self.data
        app = Flask(__name__)
        with app.test_request_context():
            return self.backend["api_get_subject_cycles"]().get_json()

    def test_cycle_suggestions_advance_past_inclusive_existing_end(self):
        self.data["settings"]["examDates"] = {"prelims": "2027-05-23"}
        self.data["subjects"].append({
            "id": "second", "name": "Z second", "color": "#123456", "topics": [],
        })
        start = self.backend["add_days"]("2027-05-23", -56)
        existing = self.cycle("R3", start, 8)
        result = self.subject_cycle_suggestions()
        suggested = result["subjectStatus"]["second"]["suggestions"]["R3"]
        self.assertEqual(suggested, self.backend["add_days"](existing["endDate"], 1))

    def test_cycle_suggestions_never_overflow_deadlines_or_existing_blocks(self):
        prelims = "2027-05-23"
        self.data["settings"].update(examDates={"prelims": prelims}, examBufferDays=10)
        for index in range(1, 12):
            self.data["subjects"].append({
                "id": f"subject{index}", "name": f"Z{index:02}",
                "color": "#123456", "topics": [],
            })
        start = self.backend["add_days"](prelims, -56)
        existing = self.cycle("R3", start, 8, subject_id="subject11")
        result = self.subject_cycle_suggestions()
        blocks = []
        for status in result["subjectStatus"].values():
            for stage, date in status["suggestions"].items():
                if stage not in ("R3", "R4", "R5"):
                    continue
                duration = self.backend["SUBJECT_CYCLE_CONFIGS"][stage]["durationDays"]
                end = self.backend["add_days"](date, duration - 1)
                deadline = self.backend["add_days"](prelims, -21 if stage == "R3" else -10)
                self.assertLess(end, deadline)
                if stage == "R3":
                    self.assertTrue(end < existing["startDate"] or date > existing["endDate"])
                blocks.append((date, end))
        blocks.sort()
        for previous, following in zip(blocks, blocks[1:]):
            self.assertLess(previous[1], following[0])
        self.assertTrue(result["sequencing"]["r3Overflow"])
        self.assertTrue(result["sequencing"]["r4Overflow"])
        self.assertTrue(result["sequencing"]["r5Overflow"])

    def test_resolver_and_estimator_reserve_fixed_capacity_once(self):
        self.topic(estimatedHours=5)
        self.topic("learner", status="learning", estimatedHours=4,
                   startDate="2026-10-21", completionDate=None)
        self.cycle(hours=2)
        resolved, used = self.backend["resolve_all_revision_schedules"](self.data)
        plan = self.backend["_build_preparation_plan"](self.data)
        self.assertEqual(used["2026-10-21"], plan["days"]["2026-10-21"]["cumulativeHours"]
                 + plan["days"]["2026-10-21"]["revisionHours"])
        for date, hours in used.items():
            self.assertLessEqual(hours, 6)
        estimate = self.backend["estimate_all_timelines"](self.data)["estimates"]["learner"]
        self.assertEqual(estimate["completionDate"], "2026-10-22")
        self.assertEqual(resolved["topic"]["r1"]["originalDate"], "2026-10-21")
        self.assertAlmostEqual(sum(session["hours"] for session in resolved["topic"]["r1"]["sessions"]), 1.5)

    def test_completed_half_cluster_consumes_today_without_repeating_future_work(self):
        self.data["settings"].update(weekdayHours=1, weekendHours=1)
        self.topic(estimatedHours=5, activeStages=["PYQ", "ERA"])
        self.data["completedRevisions"]["topic_PYQ"] = {"completedAt": "2026-10-21"}
        resolved, used = self.backend["resolve_all_revision_schedules"](self.data)
        self.assertEqual(resolved["topic"]["pyq"]["sessions"], [])
        self.assertEqual(resolved["topic"]["era"]["sessions"][0]["date"], "2026-10-22")
        self.assertAlmostEqual(used["2026-10-21"], 1)
        self.assertAlmostEqual(sum(used.values()), 2)
        self.assertTrue(all(hours <= 1 for hours in used.values()))

    def test_final_date_is_latest_active_stage_not_r30(self):
        self.data["settings"]["activityHours"] = {"MAINS": 300}
        self.topic(activeStages=["R1", "R30", "MAINS"])
        self.cycle(start="2026-10-20", duration=60, hours=1)
        estimate = self.backend["estimate_all_timelines"](self.data)["estimates"]["topic"]
        schedule = estimate["revisionSchedule"]
        self.assertGreater(schedule["mains"], schedule["r30"])
        self.assertEqual(estimate["masteryDate"], max(schedule.values()))

    def test_actual_practice_completions_anchor_notes_and_consolidation(self):
        self.topic(activeStages=["R3", "PYQ", "ERA", "MN", "MCQ", "MCQA", "R7"])
        self.data["completedRevisions"] = {
            "topic_R3": {"completedAt": "2026-10-25"},
            "topic_ERA": {"completedAt": "2026-11-10"},
            "topic_MCQA": {"completedAt": "2026-12-01"},
        }
        resolved, _ = self.backend["resolve_all_revision_schedules"](self.data)
        self.assertGreater(resolved["topic"]["mn"]["date"], "2026-11-10")
        self.assertGreaterEqual(resolved["topic"]["r7"]["date"], "2026-12-06")
        self.assertEqual(resolved["topic"]["mcqa"]["date"], "2026-12-01")

    def test_large_stages_split_without_overbooking_or_partial_failure(self):
        self.data["settings"].update(weekdayHours=1.5, weekendHours=1.5)
        self.topic(estimatedHours=5, activeStages=["R1", "PYQ", "ERA"])
        errors = []
        resolved, used = self.backend["resolve_all_revision_schedules"](self.data, errors)
        self.assertTrue(all(step["date"] for step in resolved["topic"].values()))
        self.assertTrue(any(len(step["sessions"]) > 1 for step in resolved["topic"].values()))
        self.assertTrue(all(hours <= 1.5 for hours in used.values()))
        self.assertEqual(errors, [])
        loads = self.backend["build_daily_schedule"](self.data, days_ahead=2)
        self.assertTrue(all(not load["schedulingErrors"] for load in loads))
        self.assertTrue(all(load["totalHours"] <= 1.5 for load in loads))

    def test_placement_does_not_overbook_after_120_full_days(self):
        first_day = "2026-10-22"
        used = {self.backend["add_days"](first_day, offset): 6 for offset in range(121)}
        schedule = self.backend["calculate_revision_schedule_dynamic"](
            "2026-10-21", self.data["settings"]["intervals"],
            self.backend["get_activity_hours"](self.data["settings"]),
            used, 6, 6, active_stages=["R1"],
        )
        self.assertEqual(schedule["r1"]["date"], self.backend["add_days"](first_day, 121))
        self.assertTrue(all(hours <= 6 for hours in used.values()))

    def test_exhausted_search_reports_error_without_committing(self):
        first_day = "2026-10-22"
        used = {self.backend["add_days"](first_day, offset): 6 for offset in range(400)}
        before = dict(used)
        with self.assertRaisesRegex(ValueError, "400 candidate days"):
            self.backend["calculate_revision_schedule_dynamic"](
                "2026-10-21", self.data["settings"]["intervals"],
                self.backend["get_activity_hours"](self.data["settings"]),
                used, 6, 6, active_stages=["R1"],
            )
        self.assertEqual(used, before)

    def test_completed_stages_need_no_capacity_and_keep_dates(self):
        self.data["settings"].update(weekdayHours=0, weekendHours=0)
        self.topic(activeStages=["R1", "MCQ"])
        self.data["completedRevisions"] = {
            "topic_R1": {"completedAt": "2026-11-10"},
            "topic_MCQ": {"completedAt": "2026-11-15"},
        }
        errors = []
        resolved, used = self.backend["resolve_all_revision_schedules"](self.data, errors)
        self.assertEqual(resolved["topic"]["r1"]["date"], "2026-11-10")
        self.assertEqual(resolved["topic"]["mcq"]["date"], "2026-11-15")
        self.assertEqual(used, {})
        self.assertEqual(errors, [])

    def test_future_pipeline_uses_actual_anchor_and_subject_stage_defaults(self):
        self.data["subjects"][0]["defaultStages"] = ["R1", "R3"]
        self.topic(status="learning", estimatedHours=1, activeStages=None,
                   startDate="2026-10-21", completionDate=None)
        self.data["completedRevisions"] = {"topic_R1": {"completedAt": "2026-11-10"}}
        estimate = self.backend["estimate_all_timelines"](self.data)["estimates"]["topic"]
        self.assertEqual(set(estimate["revisionSchedule"]), {"r1", "r3"})
        self.assertEqual(estimate["revisionSchedule"]["r1"], "2026-11-10")
        self.assertGreater(estimate["revisionSchedule"]["r3"], "2026-11-10")


if __name__ == "__main__":
    unittest.main()