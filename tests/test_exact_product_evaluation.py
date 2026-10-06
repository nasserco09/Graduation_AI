import unittest
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace

from evaluation.exact_product_evaluation import calculate_exact_product_metrics, load_manifest


class ExactProductMetricTests(unittest.TestCase):
    def _load_queries(self, root, queries):
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({"schema_version": "1.0", "queries": queries}), encoding="utf-8")
        metadata = SimpleNamespace(items={"catalog.jpg": {"product_id": "A", "category_key": "shoes"}})
        return load_manifest(manifest, metadata, catalog_dir=root / "catalog")

    def test_copied_catalog_image_outside_catalog_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "catalog").mkdir()
            (root / "catalog/catalog.jpg").write_bytes(b"catalog image bytes")
            copied = root / "renamed.jpg"
            copied.write_bytes(b"catalog image bytes")
            with self.assertRaisesRegex(ValueError, "byte-identical"):
                self._load_queries(root, [{"image": str(copied), "product_id": "A"}])

    def test_repeated_query_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "catalog").mkdir()
            (root / "catalog/catalog.jpg").write_bytes(b"catalog")
            first, second = root / "first.jpg", root / "second.jpg"
            first.write_bytes(b"new photo")
            second.write_bytes(b"new photo")
            with self.assertRaisesRegex(ValueError, "duplicates"):
                self._load_queries(root, [{"image": str(path), "product_id": "A"} for path in [first, second]])

    def test_missing_catalog_image_cannot_bypass_leakage_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            photo = root / "photo.jpg"
            photo.write_bytes(b"new photo")
            with self.assertRaisesRegex(FileNotFoundError, "leakage validation"):
                self._load_queries(root, [{"image": str(photo), "product_id": "A"}])

    def test_distinct_query_is_accepted_and_category_is_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "catalog").mkdir()
            (root / "catalog/catalog.jpg").write_bytes(b"catalog")
            photo = root / "photo.jpg"
            photo.write_bytes(b"new photo")
            query = {"image": str(photo), "product_id": "A", "search_category": "shoe"}
            result = self._load_queries(root, [query])
            self.assertEqual(result[0]["search_category"], "shoes")
            self.assertEqual(len(result[0]["sha256"]), 64)
            query["search_category"] = "cars"
            with self.assertRaisesRegex(ValueError, "Unsupported category"):
                self._load_queries(root, [query])

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
