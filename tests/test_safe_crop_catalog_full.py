import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from tools.build_safe_catalog_crops import (
    FULL_CROP_VERSION,
    crop_from_bbox,
    load_reusable_record,
    save_png_atomic,
    sha256_file,
    write_json_atomic,
)


class FullSafeCropCatalogTests(unittest.TestCase):
    def test_reusable_record_requires_matching_source_and_output_hashes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jpg"
            output = root / "safe_crops" / "dress" / "item.png"
            record_path = root / "record.json"
            Image.new("RGB", (20, 10), "blue").save(source)
            save_png_atomic(Image.new("RGB", (10, 10), "red"), output)
            record = {
                "schema_version": "1.0",
                "crop_version": FULL_CROP_VERSION,
                "image": "dress/item.jpg",
                "source_sha256": sha256_file(source),
                "output_sha256": sha256_file(output),
                "content_crop": {"path": "safe_crops/dress/item.png"},
            }
            write_json_atomic(record_path, record)

            loaded = load_reusable_record(
                record_path,
                root,
                image_key="dress/item.jpg",
                source_sha256=sha256_file(source),
            )
            self.assertEqual(loaded["image"], "dress/item.jpg")

            Image.new("RGB", (10, 10), "green").save(output)
            self.assertIsNone(load_reusable_record(
                record_path,
                root,
                image_key="dress/item.jpg",
                source_sha256=sha256_file(source),
            ))

    def test_crop_rejects_out_of_bounds_bbox(self):
        image = Image.new("RGB", (100, 80), "white")
        with self.assertRaises(ValueError):
            crop_from_bbox(image, {"x": 90, "y": 10, "width": 20, "height": 20})

    def test_atomic_json_is_valid(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "record.json"
            write_json_atomic(path, {"value": "تمام"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["value"], "تمام")


if __name__ == "__main__":
    unittest.main()
