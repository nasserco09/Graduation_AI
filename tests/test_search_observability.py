import tempfile
import unittest
from pathlib import Path

from backend.search_observability import SearchObservability


class SearchObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = SearchObservability(Path(self.temporary.name) / "events.db")

    def record_search(self):
        return self.store.record_search(
            query_sha256="a" * 64,
            search_mode="ai",
            routing={
                "requested_category": "auto",
                "predicted_category": "shoes",
                "applied_category": "shoes",
                "confidence": 0.9,
            },
            top_k=5,
            results=[{"product_id": "P-1", "similarity": 0.88}],
            latency_ms=25.5,
            model_name="SigLIP2",
            preprocessing_version="v1",
        )

    def test_search_and_correct_feedback_are_summarized(self):
        search_id = self.record_search()
        self.store.record_feedback(
            search_id=search_id,
            verdict="correct",
            selected_product_id="P-1",
        )

        summary = self.store.summary()

        self.assertEqual(summary["total_searches"], 1)
        self.assertEqual(summary["feedback_count"], 1)
        self.assertEqual(summary["correct_match_rate"], 1.0)
        self.assertFalse(summary["privacy"]["raw_query_images_stored"])

    def test_feedback_for_unknown_search_is_rejected(self):
        with self.assertRaises(KeyError):
            self.store.record_feedback(search_id="missing", verdict="no_match")

    def test_wrong_category_requires_a_supported_correction(self):
        search_id = self.record_search()
        with self.assertRaises(ValueError):
            self.store.record_feedback(
                search_id=search_id,
                verdict="wrong_category",
                corrected_category="cars",
            )

    def test_correct_feedback_must_reference_a_returned_product(self):
        search_id = self.record_search()
        with self.assertRaises(ValueError):
            self.store.record_feedback(
                search_id=search_id,
                verdict="correct",
                selected_product_id="NOT-RETURNED",
            )

    def test_failure_case_does_not_expose_query_hash(self):
        search_id = self.record_search()
        self.store.record_feedback(search_id=search_id, verdict="no_match")

        cases = self.store.failure_cases()

        self.assertEqual(len(cases), 1)
        self.assertNotIn("query_sha256", cases[0])
        self.assertEqual(cases[0]["result_product_ids"], ["P-1"])


if __name__ == "__main__":
    unittest.main()
