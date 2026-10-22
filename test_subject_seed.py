import unittest
from pathlib import Path

from subject_seed import DOCUMENTS, build_seed, clean_text, extract_all, validate_seed
from test_preparation import isolated_backend


class SubjectSeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).parent
        cls.subjects = extract_all(cls.root)
        cls.backend = isolated_backend()

    def test_all_documents_match_main_topic_counts(self):
        subjects = self.subjects
        self.assertEqual(len(subjects), 7)
        self.assertEqual(sum(len(subject["topics"]) for subject in subjects), 211)
        for subject, specification in zip(subjects, DOCUMENTS):
            self.assertEqual(len(subject["topics"]), specification[3])
            for topic in subject["topics"]:
                self.assertRegex(topic["code"], r"^\d+\.\d+$")
                self.assertNotIn("Sub-topics", topic["name"])
                self.assertNotIn("Pre-requisites", topic["name"])

    def test_normalization_keeps_topic_words(self):
        self.assertEqual(clean_text("  State\u2013Society\u2019s   Links  "), "State-Society's Links")

    def test_page_break_headings_remain_main_topics(self):
        economy = {topic["code"]: topic["name"] for topic in self.subjects[0]["topics"]}
        sociology = {topic["code"]: topic["name"] for topic in self.subjects[-1]["topics"]}
        self.assertEqual(economy["2.5"], "Financial Inclusion & Digital Finance")
        self.assertEqual(economy["6.3"], "Investment Models & PPP Framework")
        self.assertEqual(sociology["4.2"], "Agrarian Social Structure - Land Reforms, Green Revolution & Agrarian Relations")

    def test_numbered_coverage_text_is_not_a_topic(self):
        geography = self.subjects[2]["topics"]
        self.assertNotIn("3.8", [topic["code"] for topic in geography])
        self.assertFalse(any("billion+ years" in topic["name"] for topic in geography))

    def seed(self):
        return build_seed(self.root, self.backend["default_data"](), self.subjects, "2026-10-21")

    def test_seed_is_topic_only_and_clears_all_progress(self):
        seed = self.seed()
        self.assertEqual(validate_seed(seed), seed)
        self.assertEqual(seed["seedMetadata"]["topicCount"], 211)
        self.assertTrue(all("subtopics" not in topic for subject in seed["subjects"] for topic in subject["topics"]))

    def test_profiles_and_syllabus_mappings_are_ready_but_not_officially_verified(self):
        for subject in self.seed()["subjects"]:
            self.assertEqual(len(subject["strategy"]["syllabus"]), len(subject["topics"]))
            self.assertFalse(subject["strategy"]["syllabusVerified"])
            self.assertEqual(subject["strategy"]["stagePreset"], "standard")

    def test_seed_can_be_used_by_the_real_scheduler(self):
        seed = self.seed()
        self.backend["_migrate_data"](seed)
        result = self.backend["estimate_all_timelines"](seed)
        self.assertEqual(len(result["estimates"]), 211)
        self.assertEqual(result["summary"]["totalTopics"], 211)
        self.assertEqual(result["summary"]["schedulingErrors"], [])
        self.assertTrue(all(estimate["masteryDate"] is None for estimate in result["estimates"].values()))
        self.assertTrue(all(topic["estimatedHours"] is None and topic["roi"] is None
                            for subject in seed["subjects"] for topic in subject["topics"]))
        self.assertEqual(self.backend["compute_daily_load"](seed, "2026-10-21")["activities"], [])

    def test_optional_papers_only_use_mains_activities(self):
        seed = self.seed()
        for subject in seed["subjects"][-2:]:
            for topic in subject["topics"]:
                self.assertEqual(topic["examType"], "mains")
                stages = self.backend["get_topic_stages"](seed, topic["id"])
                self.assertNotIn("MCQ", stages)
                self.assertIn("MAINS", stages)

    def test_validator_rejects_accidental_subtopic_or_progress(self):
        seed = self.seed()
        seed["subjects"][0]["topics"][0]["source"]["code"] = "1.1.1"
        with self.assertRaises(ValueError):
            validate_seed(seed)


if __name__ == "__main__":
    unittest.main()