import json
import tempfile
import unittest
from pathlib import Path

from backend.catalog_metadata import CatalogMetadata


class CatalogMetadataTests(unittest.TestCase):
    def make_store(self, items):
        temporary = tempfile.TemporaryDirectory()
        metadata_file = Path(temporary.name) / "catalog_metadata.json"
        metadata_file.write_text(
            json.dumps({"schema_version": "1.0", "items": items}),
            encoding="utf-8",
        )
        return temporary, CatalogMetadata(metadata_file)

    def test_valid_metadata_matches_catalog(self):
        temporary, store = self.make_store([
            {
                "image": "shoes_a.jpg",
                "product_id": "P-1",
                "category_key": "shoes",
                "title_ar": "حذاء تجريبي",
            }
        ])
        self.addCleanup(temporary.cleanup)

        summary = store.require_valid_catalog(["shoes_a.jpg"])

        self.assertTrue(summary["valid"])
        self.assertEqual(store.get("shoes_a.jpg")["category"], "أحذية")

    def test_missing_metadata_is_reported(self):
        temporary, store = self.make_store([
            {
                "image": "shoes_a.jpg",
                "product_id": "P-1",
                "category_key": "shoes",
                "title_ar": "حذاء تجريبي",
            }
        ])
        self.addCleanup(temporary.cleanup)

        summary = store.validate_catalog_paths(["shoes_a.jpg", "pants_b.jpg"])

        self.assertFalse(summary["valid"])
        self.assertEqual(summary["missing_metadata"], ["pants_b.jpg"])

    def test_same_product_can_have_multiple_catalog_images(self):
        items = [
            {"image": "a.jpg", "product_id": "P-1", "category_key": "shoes", "title_ar": "أ"},
            {"image": "b.jpg", "product_id": "P-1", "category_key": "shoes", "title_ar": "أ"},
        ]

        with tempfile.TemporaryDirectory() as directory:
            metadata_file = Path(directory) / "catalog_metadata.json"
            metadata_file.write_text(
                json.dumps({"schema_version": "1.0", "items": items}),
                encoding="utf-8",
            )
            store = CatalogMetadata(metadata_file)

        self.assertEqual(store.get("a.jpg")["product_id"], "P-1")
        self.assertEqual(store.get("b.jpg")["product_id"], "P-1")

    def test_catalog_path_traversal_is_rejected(self):
        items = [{
            "image": "../outside.jpg",
            "product_id": "P-1",
            "category_key": "shoes",
            "title_ar": "حذاء",
        }]

        with tempfile.TemporaryDirectory() as directory:
            metadata_file = Path(directory) / "catalog_metadata.json"
            metadata_file.write_text(
                json.dumps({"schema_version": "1.0", "items": items}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Invalid catalog image path"):
                CatalogMetadata(metadata_file)

    def test_checked_in_metadata_covers_the_current_catalog(self):
        root = Path(__file__).resolve().parent.parent
        store = CatalogMetadata(root / "data" / "catalog_metadata.json")
        catalog_paths = sorted(
            path.name
            for path in (root / "catalog").iterdir()
            if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
        )

        summary = store.require_valid_catalog(catalog_paths)

        self.assertEqual(summary["catalog_image_count"], 30)
        self.assertEqual(summary["metadata_item_count"], 30)

    def test_train_metadata_covers_the_expanded_catalog(self):
        root = Path(__file__).resolve().parent.parent
        catalog_dir = root / "datasets" / "clothing_small" / "train"
        store = CatalogMetadata(root / "data" / "catalog_metadata_train.json")
        catalog_paths = sorted(
            path.relative_to(catalog_dir).as_posix()
            for path in catalog_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
        )

        summary = store.require_valid_catalog(catalog_paths)

        self.assertEqual(summary["catalog_image_count"], 3068)
        self.assertEqual(summary["metadata_item_count"], 3068)
        self.assertTrue(all("/" in path for path in store.items))


if __name__ == "__main__":
    unittest.main()
