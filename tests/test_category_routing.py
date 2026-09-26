import unittest

import numpy as np

from backend.category_routing import (
    CATEGORY_LABELS,
    category_from_path,
    normalize_category,
    predict_category,
)


class CategoryRoutingTests(unittest.TestCase):
    def test_category_is_read_from_catalog_filename(self):
        self.assertEqual(category_from_path("nested/shoes_123.jpg"), "shoes")
        self.assertEqual(category_from_path("t-shirt_123.jpg"), "t-shirt")
        self.assertIsNone(category_from_path("unknown_123.jpg"))

    def test_category_alias_and_validation(self):
        self.assertEqual(normalize_category("outerwear"), "outwear")
        self.assertEqual(normalize_category(None), "auto")
        with self.assertRaises(ValueError):
            normalize_category("cars")

    def test_query_is_routed_to_nearest_category_centroid(self):
        paths = ["shoes_a.jpg", "shoes_b.jpg", "pants_a.jpg", "pants_b.jpg"]
        vectors = np.asarray(
            [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.1, 0.9]],
            dtype="float32",
        )

        result = predict_category(
            np.asarray([[0.98, 0.02]], dtype="float32"),
            vectors,
            paths,
        )

        self.assertEqual(result["category"], "shoes")
        self.assertEqual(result["label"], CATEGORY_LABELS["shoes"])
        self.assertGreater(result["confidence"], 0.5)

    def test_metadata_categories_override_filename_fallback(self):
        result = predict_category(
            np.asarray([[1.0, 0.0]], dtype="float32"),
            np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype="float32"),
            ["unlabelled-a.jpg", "unlabelled-b.jpg"],
            category_keys=["shoes", "pants"],
        )

        self.assertEqual(result["category"], "shoes")


if __name__ == "__main__":
    unittest.main()
