import ast
import copy
import math
from pathlib import Path
import time
import unittest
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, request


def isolated_backend():
    source = ast.parse(Path(__file__).with_name("app.py").read_text(encoding="utf-8-sig"))
    namespace = {
        "datetime": datetime, "timedelta": timedelta, "timezone": timezone,
        "math": math, "time": time, "jsonify": jsonify, "request": request,
        "IST": timezone(timedelta(hours=5, minutes=30)),
    }
    nodes = []
    for node in source.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            nodes.append(node)
        elif isinstance(node, ast.Assign):
            try:
                ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            nodes.append(node)
        elif isinstance(node, ast.FunctionDef):
            node.decorator_list = []
            nodes.append(node)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    namespace["send_ntfy"] = lambda *args, **kwargs: None
    namespace["today_str"] = lambda: "2026-10-21"
    return namespace


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.backend = isolated_backend()
        self.app = Flask(__name__)
        self.data = self.backend["default_data"]()
        self.topic = {
            "id": "topic", "name": "Test topic", "status": "learning",
            "roi": "high", "estimatedHours": 5, "startDate": "2026-10-20",
            "completionDate": None, "examType": "both",
        }
        self.data["subjects"] = [{
            "id": "subject", "name": "Test subject", "color": "#123456",
            "roi": "high", "topics": [self.topic],
        }]
        self.backend["load_data"] = lambda: self.data
        self.saved = []
        self.backend["save_data"] = lambda data: self.saved.append(copy.deepcopy(data))

    def test_complete_topic_returns_after_persisting(self):
        with self.app.test_request_context(method="POST", json={}):
            response = self.backend["api_complete_topic"]("subject", "topic")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.topic["status"], "completed")
        self.assertNotIn("ca", response.get_json()["schedule"])
        self.assertTrue(self.saved)

    def test_custom_pipeline_without_final_recall_can_be_estimated(self):
        self.topic.update(status="completed", completionDate="2026-10-20", activeStages=["R1"])
        result = self.backend["estimate_all_timelines"](self.data)
        self.assertIn("topic", result["estimates"])
        self.assertEqual(set(result["estimates"]["topic"]["revisionSchedule"]), {"r1"})

    def test_disabled_stage_is_rejected_without_saving(self):
        self.topic.update(status="completed", completionDate="2026-10-20", activeStages=["R1"])
        with self.app.test_request_context(method="POST", json={"topicId": "topic", "type": "CA"}):
            response, status = self.backend["api_mark_revision"]()
        self.assertEqual(status, 400)
        self.assertFalse(self.data["completedRevisions"])
        self.assertFalse(self.saved)

    def test_unmark_reopens_pipeline_and_removes_pending_eligibility(self):
        self.topic.update(status="pipeline-complete", completionDate="2026-10-20", activeStages=["R1"])
        self.data["completedRevisions"]["topic_R1"] = {"completedAt": 1}
        self.data["cumulativeRevisions"]["pendingTopics"] = [{"topicId": "topic"}]
        with self.app.test_request_context(method="POST", json={"topicId": "topic", "type": "R1"}):
            self.backend["api_unmark_revision"]()
        self.assertEqual(self.topic["status"], "completed")
        self.assertEqual(self.data["cumulativeRevisions"]["pendingTopics"], [])

    def test_unstarted_topic_is_never_pipeline_complete(self):
        self.topic.update(status="not-started", activeStages=["R1"])
        self.data["completedRevisions"]["topic_R1"] = {"completedAt": 1}
        self.assertFalse(self.backend["check_topic_mastery"](self.data, "topic"))

    def test_compact_subject_profile_is_used_without_overriding_custom_stages(self):
        self.data["subjects"][0]["strategy"] = {"stagePreset": "compact"}
        self.assertNotIn("MN", self.backend["get_topic_stages"](self.data, "topic"))
        self.topic["activeStages"] = ["R1", "MN"]
        self.assertEqual(self.backend["get_topic_stages"](self.data, "topic"), ["R1", "MN"])

    def test_prerequisites_block_start_but_not_link_collection(self):
        self.topic.update(status="not-started", prerequisiteIds=["foundation"])
        self.data["subjects"][0]["topics"].append({"id": "foundation", "name": "Foundation", "status": "learning"})
        with self.app.test_request_context(method="POST", json={}):
            response, status = self.backend["api_start_topic"]("subject", "topic")
        self.assertEqual(status, 409)
        self.assertIn("Foundation", response.get_json()["error"])
        self.assertEqual(self.topic["status"], "not-started")

    def test_forecast_respects_prerequisite_before_roi(self):
        self.topic.update(status="not-started", roi="very-high", estimatedHours=3,
                          prerequisiteIds=["foundation"], activeStages=["R1"])
        self.data["subjects"][0]["topics"].append({
            "id": "foundation", "name": "Foundation", "status": "not-started", "roi": "low",
            "estimatedHours": 3, "activeStages": ["R1"],
        })
        estimates = self.backend["estimate_all_timelines"](self.data)["estimates"]
        self.assertGreaterEqual(estimates["topic"]["startDate"], estimates["foundation"]["completionDate"])

    def test_unmark_keeps_an_audit_record(self):
        self.topic.update(status="completed", completionDate="2026-10-20", activeStages=["R1"])
        self.data["completedRevisions"]["topic_R1"] = {"completedAt": 123}
        with self.app.test_request_context(method="POST", json={"topicId": "topic", "type": "R1"}):
            self.backend["api_unmark_revision"]()
        self.assertEqual(self.data["activityHistory"][0]["previous"], {"completedAt": 123})

    def test_load_repair_reopens_incomplete_pipeline(self):
        self.topic.update(status="pipeline-complete", completionDate="2026-10-20", activeStages=["R1"])
        self.backend["_fix_mastery_status"](self.data, persist=False)
        self.assertEqual(self.topic["status"], "completed")

    def test_settings_save_preserves_training_targets(self):
        self.data["settings"]["preparation"] = {"mcqAccuracy": 90}
        with self.app.test_request_context(method="PUT", json={"weekdayHours": 5}):
            self.backend["api_save_settings"]()
        self.assertEqual(self.data["settings"]["preparation"], {"mcqAccuracy": 90})

    def test_old_start_without_logs_does_not_imply_finished_learning(self):
        self.topic.update(startDate="2026-01-01", estimatedHours=20, activeStages=["R1"])
        estimate = self.backend["estimate_all_timelines"](self.data)["estimates"]["topic"]
        self.assertGreater(estimate["completionDate"], "2026-10-21")

    def test_deleting_prerequisite_removes_dependent_links(self):
        self.data["subjects"][0]["topics"].append({
            "id": "dependent", "name": "Dependent", "status": "not-started", "prerequisiteIds": ["topic"],
        })
        with self.app.test_request_context(method="DELETE"):
            self.backend["api_delete_topic"]("subject", "topic")
        self.assertEqual(self.data["subjects"][0]["topics"][0]["prerequisiteIds"], [])

    def test_today_shows_only_open_due_repairs(self):
        self.data["repairItems"] = [
            {"id": "due", "status": "open", "dueDate": "2026-10-20"},
            {"id": "future", "status": "open", "dueDate": "2026-10-23"},
            {"id": "done", "status": "resolved", "dueDate": "2026-10-20"},
        ]
        with self.app.test_request_context():
            result = self.backend["api_today"]().get_json()
        self.assertEqual([entry["id"] for entry in result["repairTasks"]], ["due"])


if __name__ == "__main__":
    unittest.main()