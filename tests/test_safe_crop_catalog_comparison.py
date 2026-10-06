import unittest

import numpy as np

from evaluation.compare_safe_crop_catalog import (
    evaluate_scores,
    paired_top1_statistics,
    select_hybrid_weight,
)


class SafeCropCatalogComparisonTests(unittest.TestCase):
    def test_paired_statistics_count_direction_correctly(self):
        baseline = np.asarray([True, True, False, False])
        candidate = np.asarray([True, False, True, True])

        result = paired_top1_statistics(
            baseline,
            candidate,
            bootstrap_samples=500,
            seed=7,
        )

        self.assertEqual(result["improved_queries"], 2)
        self.assertEqual(result["worsened_queries"], 1)
        self.assertEqual(result["unchanged_queries"], 1)
        self.assertEqual(result["delta_top1"], 0.25)

    def test_validation_tuning_can_select_safe_gallery(self):
        query_labels = ["a", "b"]
        gallery_labels = ["a", "b"]
        original_scores = np.asarray([[0.4, 0.6], [0.6, 0.4]], dtype="float32")
        safe_scores = np.asarray([[0.9, 0.1], [0.1, 0.9]], dtype="float32")

        safe_weight, candidates = select_hybrid_weight(
            original_scores,
            safe_scores,
            query_labels,
            gallery_labels,
        )

        self.assertGreaterEqual(safe_weight, 0.3)
        self.assertEqual(len(candidates), 11)

    def test_score_evaluation_uses_ranked_gallery_labels(self):
        scores = np.asarray([[0.9, 0.1], [0.2, 0.8]], dtype="float32")
        result = evaluate_scores(scores, ["a", "b"], ["a", "b"])

        self.assertEqual(result["predictions"], ["a", "b"])
        self.assertEqual(result["metrics"]["precision_at_1"], 1.0)


if __name__ == "__main__":
    unittest.main()
