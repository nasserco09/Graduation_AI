import unittest

from evaluation.exact_product_evaluation import calculate_exact_product_metrics


class ExactProductMetricTests(unittest.TestCase):
    def test_exact_identity_metrics_use_product_rank(self):
        records = [
            {
                "expected_product_id": "A",
                "retrieved_product_ids": ["A", "B", "C"],
                "expected_category": "shoes",
                "predicted_category": "shoes",
            },
            {
                "expected_product_id": "B",
                "retrieved_product_ids": ["A", "C", "B"],
                "expected_category": "pants",
                "predicted_category": "shoes",
            },
            {
                "expected_product_id": "D",
                "retrieved_product_ids": ["A", "B", "C"],
                "expected_category": "dress",
                "predicted_category": "dress",
            },
        ]

        metrics = calculate_exact_product_metrics(records)

        self.assertEqual(metrics["query_count"], 3)
        self.assertEqual(metrics["exact_top1"], 0.333333)
        self.assertEqual(metrics["exact_top5"], 0.666667)
        self.assertEqual(metrics["exact_mrr"], 0.444444)
        self.assertEqual(metrics["category_accuracy"], 0.666667)


if __name__ == "__main__":
    unittest.main()
