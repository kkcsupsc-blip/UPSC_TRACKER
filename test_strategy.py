import copy
import unittest

from flask import Flask

from preparation import create_preparation_blueprint, strategy_stages, validate_prerequisites, validate_strategy


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.subject = {"id": "subject", "name": "Geography", "topics": [
            {"id": "first", "name": "First", "status": "not-started"},
            {"id": "second", "name": "Second", "status": "completed"},
        ]}
        self.data = {"subjects": [self.subject]}
        self.saved = []
        app = Flask(__name__)
        app.register_blueprint(create_preparation_blueprint(
            lambda: self.data, lambda data: self.saved.append(copy.deepcopy(data)),
            lambda: "2026-10-21", lambda data, topic: None,
        ))
        self.client = app.test_client()

    def test_unconfigured_strategy_preserves_pipeline(self):
        stages = ["R1", "MN", "R7", "MVA", "MAINS", "R30"]
        self.assertEqual(strategy_stages(self.subject, {}, stages), stages)

    def test_compact_retains_writing_and_delayed_recall(self):
        stages = ["R1", "MN", "R7", "MVA", "MAINS", "R30"]
        self.assertEqual(strategy_stages(self.subject, {"studyScope": "compact"}, stages), ["R1", "MAINS", "R30"])

    def test_depth_reading_requires_a_specific_gap(self):
        with self.assertRaises(ValueError):
            validate_strategy({"resources": [{"tier": "depth", "title": "Book", "scope": "Chapter 1"}]}, self.subject)

    def test_cyclic_prerequisites_are_rejected(self):
        self.subject["topics"][0]["prerequisiteIds"] = ["second"]
        with self.assertRaises(ValueError):
            validate_prerequisites(self.data, "second", ["first"])

    def test_coverage_requires_learning_and_mapping(self):
        response = self.client.put("/api/subjects/subject/strategy", json={
            "profile": "geography", "stagePreset": "compact", "syllabus": [
                {"title": "Mapped", "topicIds": ["second"]},
                {"title": "Unmapped", "topicIds": []},
            ],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["coverage"], {"total": 2, "covered": 1, "verified": False})

    def test_invalid_strategy_never_saves(self):
        response = self.client.put("/api/subjects/subject/strategy", json={"profile": "unknown"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.saved)


if __name__ == "__main__":
    unittest.main()