import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from tools.preview_safe_catalog_crops import (
    SAFE_CROP_BATCH_VERSION,
    crop_from_bbox,
    load_checkpoint,
    make_safe_tile,
    save_contact_sheet,
    write_json_atomic,
)


class SafeCropPreviewTests(unittest.TestCase):
    def test_checkpoint_round_trip(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            payload = {
                "crop_version": SAFE_CROP_BATCH_VERSION,
                "items": [{"image": "shoes/example.jpg", "value": 1}],
            }
            write_json_atomic(path, payload)

            loaded = load_checkpoint(path)

            self.assertEqual(loaded["shoes/example.jpg"]["value"], 1)
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_checkpoint_from_another_version_is_ignored(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            path.write_text(
                json.dumps(
                    {
                        "crop_version": "old-version",
                        "items": [{"image": "dress/example.jpg"}],
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(load_checkpoint(path), {})

    def test_crop_uses_requested_original_pixels(self):
        image = Image.new("RGB", (100, 80), "blue")

        cropped = crop_from_bbox(
            image,
            {"x": 10, "y": 15, "width": 40, "height": 30},
        )

        self.assertEqual(cropped.size, (40, 30))
        self.assertEqual(cropped.getpixel((0, 0)), (0, 0, 255))

    def test_contact_sheet_uses_compact_five_column_grid(self):
        image = Image.new("RGB", (100, 80), "blue")
        tiles = [
            make_safe_tile(
                image,
                image,
                label=f"item-{index}",
                fallback_used=False,
            )
            for index in range(6)
        ]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sheet.jpg"
            save_contact_sheet(tiles, path)
            with Image.open(path) as sheet:
                self.assertEqual(sheet.size, (2800, 536))


if __name__ == "__main__":
    unittest.main()
