import copy
import unittest

from flask import Flask

from planner import DEFAULT_PLANNER
from planner_api import create_planner_blueprint
from test_preparation import isolated_backend


class PlannerApiTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "settings": {"weekdayHours": 5, "weekendHours": 10, "preparation": {"mcqAccuracy": 80}},
            "subjects": [
                {"id": "economy", "name": "Economy", "topics": [{"id": "gs", "status": "not-started"}]},
                {"id": "sociology", "name": "Sociology Paper I", "topics": [{"id": "opt", "status": "not-started"}]},
            ],
            "completedRevisions": {"old_R1": {"completedAt": 123}},
            "studyLogs": [{"topicId": "old", "hours": 2}],
        }
        self.saved = []
        app = Flask(__name__)
        app.register_blueprint(create_planner_blueprint(lambda: self.data, self.saved.append, lambda: "2026-10-21"))
        self.client = app.test_client()

    def test_default_policy_has_both_streams_and_2028_attempt(self):
        response = self.client.get("/api/planner")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["config"]["attemptYear"], 2028)
        self.assertEqual(response.json["weeklyStudyHours"], 45)
        self.assertEqual({subject["stream"] for subject in response.json["subjects"]}, {"gs", "optional"})

    def test_save_preserves_progress_and_training_targets(self):
        before = copy.deepcopy(self.data)
        response = self.client.put("/api/planner", json={"config": DEFAULT_PLANNER})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.data, before)
        self.assertEqual(self.saved[0]["studyLogs"], before["studyLogs"])
        self.assertEqual(self.saved[0]["completedRevisions"], before["completedRevisions"])
        self.assertEqual(self.saved[0]["settings"]["preparation"], {"mcqAccuracy": 80})

    def test_invalid_percentage_does_not_write(self):
        config = copy.deepcopy(DEFAULT_PLANNER)
        config["allocations"]["integrated"]["gs"] = 90
        self.assertEqual(self.client.put("/api/planner", json={"config": config}).status_code, 400)
        self.assertFalse(self.saved)

    def test_stream_reassignment_cannot_create_two_active_learners(self):
        for subject in self.data["subjects"]:
            subject["topics"][0]["status"] = "learning"
        response = self.client.put("/api/planner", json={"config": DEFAULT_PLANNER, "subjectStreams": {"economy": "optional"}})
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.saved)

    def test_invalid_structure_returns_validation_error(self):
        self.assertEqual(self.client.put("/api/planner", json=[]).status_code, 400)
        self.assertEqual(self.client.put("/api/planner", json={"config": {"allocations": []}}).status_code, 400)
        self.assertEqual(self.client.put("/api/planner", json={"config": {"allocations": {"integrated": {"unknownPool": 1}}}}).status_code, 400)


class PlannerApplicationTests(unittest.TestCase):
    def setUp(self):
        self.backend = isolated_backend()
        self.app = Flask(__name__)
        self.data = self.backend["default_data"]()
        self.data["settings"].update(weekdayHours=6, weekendHours=6, examBufferDays=0,
                                     examDates={"prelims": "2026-11-15", "mains": "2030-08-20"})
        self.data["subjects"] = [
            {"id": "gs", "name": "Economy", "color": "#fff", "topics": [self.topic("gs-first"), self.topic("gs-second")]},
            {"id": "opt", "name": "Sociology Paper I", "color": "#fff", "topics": [self.topic("optional", "mains", 100)]},
        ]
        self.backend["load_data"] = lambda: self.data
        self.backend["save_data"] = lambda data: None

    def topic(self, topic_id, exam_type="both", hours=1):
        return {"id": topic_id, "name": topic_id, "status": "not-started", "estimatedHours": hours,
                "roi": "medium", "examType": exam_type, "activeStages": ["R1"], "completionDate": None}

    def test_start_allows_optional_alongside_gs_but_not_second_gs(self):
        self.data["subjects"][0]["topics"][0].update(status="learning", startDate="2026-10-21")
        with self.app.test_request_context(method="POST", json={}):
            response = self.backend["api_start_topic"]("opt", "optional")
            blocked, status = self.backend["api_start_topic"]("gs", "gs-second")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(status, 409)
        self.assertTrue(blocked.get_json()["streamBusy"])

    def test_prelims_warning_excludes_late_optional_pipeline(self):
        with self.app.test_request_context():
            response = self.backend["api_dashboard"]().get_json()
        warnings = response["examInfo"]["feasibility"]["warnings"]
        self.assertFalse(any(entry.get("exam") == "prelims" for entry in warnings))
        self.assertEqual(response["stats"]["totalSubjects"], 2)

    def test_daily_and_calendar_learning_are_identical(self):
        with self.app.test_request_context():
            today = self.backend["api_today"]().get_json()
            calendar = self.backend["api_calendar_day"]("2026-10-21").get_json()
        self.assertEqual(today["learningPlan"], calendar["learningPlan"])
        self.assertEqual({entry["stream"] for entry in today["learningPlan"]}, {"gs", "optional"})

    def test_unknown_schedule_never_reports_on_track(self):
        self.data["settings"].update(weekdayHours=0, weekendHours=0)
        with self.app.test_request_context():
            response = self.backend["api_dashboard"]().get_json()
        self.assertEqual(response["examInfo"]["feasibility"]["status"], "unknown")

    def test_stage_logs_are_validated_and_do_not_change_learning_hours(self):
        topic = self.data["subjects"][0]["topics"][0]
        topic.update(status="completed", completionDate="2026-10-20")
        with self.app.test_request_context(method="POST", json={"topicId": topic["id"], "hours": 0.25, "stage": "R1"}):
            response = self.backend["api_add_study_log"]()
        self.assertEqual(response.get_json()["hours"], 0.25)
        self.assertEqual(self.backend["get_actual_hours"](self.data, topic["id"]), 0)
        with self.app.test_request_context(method="POST", json={"topicId": topic["id"], "hours": -1}):
            response, status = self.backend["api_add_study_log"]()
        self.assertEqual(status, 400)

    def test_unplaceable_topic_details_do_not_compare_null_dates(self):
        topic = self.data["subjects"][0]["topics"][0]
        topic.update(status="completed", completionDate="2026-10-20")
        self.data["settings"].update(weekdayHours=0, weekendHours=0)
        with self.app.test_request_context():
            response = self.backend["api_topic_detail"]("gs", topic["id"])
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()["schedule"]["r1"]["date"])


if __name__ == "__main__":
    unittest.main()