import unittest

from preparation import evidence_summary
from test_strategy import StrategyTests


class AssessmentTests(StrategyTests):
    def record(self, **updates):
        payload = {"kind": "mcq", "topicId": "second", "date": "2026-10-21", "minutes": 30,
                   "correct": 15, "wrong": 5, "unattempted": 0, "setType": "unseen"}
        payload.update(updates)
        return self.client.post("/api/subjects/subject/attempts", json=payload)

    def test_negative_marking_and_history(self):
        first = self.record()
        self.assertEqual(first.status_code, 201)
        self.assertAlmostEqual(first.json["netMarks"], 26.67)
        self.assertEqual(first.json["accuracy"], 75)
        self.record(correct=10, wrong=10)
        self.assertEqual(len(self.data["assessmentAttempts"]), 2)
        self.assertEqual(self.subject["topics"][1]["status"], "completed")

    def test_invalid_and_future_attempts_do_not_save(self):
        for updates in ({"correct": -1}, {"correct": 1.5}, {"date": "2026-10-22"}, {"minutes": "nan"}):
            self.assertEqual(self.record(**updates).status_code, 400)
        self.assertFalse(self.saved)

    def test_repeated_questions_do_not_prove_readiness(self):
        self.record(setType="repeated")
        summary = evidence_summary(self.data, self.subject["topics"][1], "2026-10-21")
        self.assertEqual(summary["dimensions"]["mcq"]["status"], "diagnostic-only")

    def test_skipped_questions_do_not_satisfy_mcq_sample_size(self):
        self.record(correct=1, wrong=0, unattempted=19)
        summary = evidence_summary(self.data, self.subject["topics"][1], "2026-10-21")
        self.assertEqual(summary["dimensions"]["mcq"]["status"], "small-sample")

    def test_unattempted_items_count_against_recall(self):
        self.subject["topics"][1]["completionDate"] = "2026-10-01"
        self.record(kind="recall", correct=1, wrong=0, unattempted=9)
        summary = evidence_summary(self.data, self.subject["topics"][1], "2026-10-21")
        self.assertEqual(summary["dimensions"]["recall"]["status"], "needs-practice")

    def test_external_writing_and_staleness_are_distinct(self):
        self.record(kind="writing", score=6, maxMarks=10, reviewer="self")
        topic = self.subject["topics"][1]
        self.assertEqual(evidence_summary(self.data, topic, "2026-10-21")["dimensions"]["writing"]["status"], "self-assessed")
        self.record(kind="writing", score=6, maxMarks=10, reviewer="external")
        self.assertEqual(evidence_summary(self.data, topic, "2026-10-21")["dimensions"]["writing"]["status"], "on-target")
        self.assertEqual(evidence_summary(self.data, topic, "2026-11-21")["dimensions"]["writing"]["status"], "stale")

    def test_error_creates_repair_and_requires_resolution(self):
        self.record(errors=["concept"])
        repair = self.data["repairItems"][0]
        self.assertEqual(repair["dueDate"], "2026-10-23")
        endpoint = f'/api/preparation/repairs/{repair["id"]}'
        self.assertEqual(self.client.put(endpoint, json={}).status_code, 400)
        self.assertEqual(self.client.put(endpoint, json={"resolution": "Corrected mechanism and retested"}).status_code, 200)

    def test_void_preserves_history_but_removes_evidence(self):
        attempt = self.record(errors=["fact"]).json
        self.assertEqual(self.client.delete(f'/api/preparation/attempts/{attempt["id"]}').status_code, 200)
        self.assertEqual(len(self.data["assessmentAttempts"]), 1)
        self.assertEqual(self.data["repairItems"][0]["status"], "cancelled")
        self.assertEqual(evidence_summary(self.data, self.subject["topics"][1], "2026-10-21")["attempts"], 0)


if __name__ == "__main__":
    unittest.main()