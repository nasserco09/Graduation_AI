import base64
from io import BytesIO
import unittest

import numpy as np
from PIL import Image

from backend.catalog_isolation import (
    assess_catalog_isolation,
    build_catalog_prompt,
    build_catalog_prompts,
    build_shoe_recovery_prompts,
    choose_content_crop_box,
    expand_bounding_box,
    merge_isolation_results,
    select_compatible_shoe_results,
)


class CatalogIsolationTests(unittest.TestCase):
    def test_expanded_bbox_adds_padding_and_clamps_to_image(self):
        expanded = expand_bounding_box(
            {"x": 5, "y": 8, "width": 40, "height": 50},
            100,
            80,
            padding_ratio=0.20,
        )

        self.assertEqual(expanded, {"x": 0, "y": 0, "width": 53, "height": 68})

    def test_content_crop_preserves_full_image_for_single_shoe(self):
        bbox, strategy = choose_content_crop_box(
            "shoes",
            {
                "score": 0.90,
                "mask_area_ratio": 0.20,
                "bbox_area_ratio": 0.30,
                "bbox": {"x": 20, "y": 20, "width": 40, "height": 50},
                "isolation_components": 1,
            },
            100,
            80,
        )

        self.assertEqual(bbox, {"x": 0, "y": 0, "width": 100, "height": 80})
        self.assertEqual(strategy, "full_image_single_shoe_fallback")

    def test_content_crop_uses_pair_bbox_for_two_shoes(self):
        bbox, strategy = choose_content_crop_box(
            "shoes",
            {
                "score": 0.90,
                "mask_area_ratio": 0.20,
                "bbox_area_ratio": 0.30,
                "bbox": {"x": 20, "y": 15, "width": 50, "height": 40},
                "isolation_components": 2,
            },
            100,
            80,
            padding_ratio=0.10,
        )

        self.assertEqual(bbox, {"x": 15, "y": 11, "width": 60, "height": 48})
        self.assertEqual(strategy, "expanded_product_bbox")

    def test_rejected_mask_uses_full_image_crop(self):
        bbox, strategy = choose_content_crop_box(
            "dress",
            {
                "score": 0.10,
                "mask_area_ratio": 0.20,
                "bbox_area_ratio": 0.30,
                "bbox": {"x": 20, "y": 15, "width": 50, "height": 40},
            },
            100,
            80,
        )

        self.assertEqual(bbox, {"x": 0, "y": 0, "width": 100, "height": 80})
        self.assertEqual(strategy, "full_image_rejected_mask_fallback")

    def test_generic_prompt_contains_one_positive_and_four_negative_points(self):
        points, labels = build_catalog_prompt("dress", 100, 80)

        self.assertEqual(len(points), 5)
        self.assertEqual(labels, [1, 0, 0, 0, 0])
        self.assertAlmostEqual(points[0][0], 49.5)
        self.assertAlmostEqual(points[0][1], 39.5)

    def test_shoe_prompt_avoids_empty_center_gap(self):
        points, _ = build_catalog_prompt("shoes", 200, 100)

        self.assertLess(points[0][0], 100)
        self.assertGreater(points[0][1], 49)

    def test_shoe_pair_uses_two_independent_prompts(self):
        prompts = build_catalog_prompts("shoes", 200, 100)

        self.assertEqual(len(prompts), 2)
        left_points, left_labels = prompts[0]
        right_points, right_labels = prompts[1]
        self.assertEqual(left_labels, [1, 0, 0, 0, 0])
        self.assertEqual(right_labels, [1, 0, 0, 0, 0])
        self.assertLess(left_points[0][0], 100)
        self.assertGreater(right_points[0][0], 100)

    def test_non_shoe_category_keeps_one_prompt(self):
        prompts = build_catalog_prompts("dress", 100, 80)

        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0], build_catalog_prompt("dress", 100, 80))

    def test_shoe_recovery_skips_points_inside_detected_component(self):
        prompts = build_shoe_recovery_prompts(
            200,
            100,
            {"x": 40, "y": 20, "width": 40, "height": 60},
        )

        self.assertLess(len(prompts), 4)
        for points, labels in prompts:
            self.assertEqual(labels.count(1), 1)
            self.assertEqual(labels.count(0), 5)
            self.assertFalse(40 <= points[0][0] <= 80 and 20 <= points[0][1] <= 80)

    def test_shoe_recovery_has_four_grid_prompts_without_exclusion(self):
        prompts = build_shoe_recovery_prompts(200, 100)

        self.assertEqual(len(prompts), 4)
        self.assertTrue(all(labels == [1, 0, 0, 0, 0] for _, labels in prompts))

    def test_pants_prompt_targets_waist_and_both_legs(self):
        points, labels = build_catalog_prompt("pants", 200, 300)

        self.assertEqual(labels, [1, 1, 1, 0, 0, 0, 0])
        self.assertLess(points[0][1], points[1][1])
        self.assertLess(points[1][0], points[2][0])

    def test_hat_prompt_targets_crown_and_brim(self):
        points, labels = build_catalog_prompt("hat", 200, 100)

        self.assertEqual(labels, [1, 1, 0, 0, 0, 0])
        self.assertLess(points[0][1], points[1][1])

    def test_tshirt_prompt_spreads_points_across_garment(self):
        points, labels = build_catalog_prompt("t-shirt", 200, 300)

        self.assertEqual(labels, [1, 1, 1, 0, 0, 0, 0])
        self.assertLess(points[0][0], points[1][0])
        self.assertGreater(points[2][1], points[0][1])

    def test_invalid_dimensions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "2x2"):
            build_catalog_prompt("shirt", 1, 100)

    def test_reasonable_mask_is_accepted(self):
        assessment = assess_catalog_isolation(
            {
                "score": 0.91,
                "mask_area_ratio": 0.32,
                "bbox_area_ratio": 0.55,
            }
        )

        self.assertTrue(assessment.accepted)
        self.assertEqual(assessment.reason, "accepted")
        self.assertFalse(assessment.review_required)

    def test_low_score_is_rejected(self):
        assessment = assess_catalog_isolation(
            {
                "score": 0.20,
                "mask_area_ratio": 0.32,
                "bbox_area_ratio": 0.55,
            }
        )

        self.assertFalse(assessment.accepted)
        self.assertEqual(assessment.reason, "low_model_score")

    def test_moderate_score_is_accepted_but_marked_for_review(self):
        assessment = assess_catalog_isolation(
            {
                "score": 0.30,
                "mask_area_ratio": 0.32,
                "bbox_area_ratio": 0.55,
            }
        )

        self.assertTrue(assessment.accepted)
        self.assertEqual(assessment.reason, "accepted_low_confidence")
        self.assertTrue(assessment.review_required)

    def test_tiny_partial_mask_is_rejected_even_with_good_score(self):
        assessment = assess_catalog_isolation(
            {
                "score": 0.90,
                "mask_area_ratio": 0.028,
                "bbox_area_ratio": 0.14,
            }
        )

        self.assertFalse(assessment.accepted)
        self.assertEqual(assessment.reason, "mask_too_small")

    def test_nearly_full_image_mask_is_rejected(self):
        assessment = assess_catalog_isolation(
            {
                "score": 0.95,
                "mask_area_ratio": 0.94,
                "bbox_area_ratio": 0.95,
            }
        )

        self.assertFalse(assessment.accepted)
        self.assertEqual(assessment.reason, "mask_too_large")

    @staticmethod
    def _encoded_mask(mask: np.ndarray) -> str:
        buffer = BytesIO()
        Image.fromarray(mask.astype(np.uint8) * 255, mode="L").save(
            buffer,
            format="PNG",
        )
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _result_for_mask(self, mask: np.ndarray, score: float = 0.90) -> dict:
        ys, xs = np.where(mask)
        x1, x2 = int(xs.min()), int(xs.max()) + 1
        y1, y2 = int(ys.min()), int(ys.max()) + 1
        height, width = mask.shape
        pixel_count = float(width * height)
        placeholder = Image.new("RGB", (x2 - x1, y2 - y1), "white")
        buffer = BytesIO()
        placeholder.save(buffer, format="PNG")
        return {
            "binary_mask": self._encoded_mask(mask),
            "cutout": base64.b64encode(buffer.getvalue()).decode("utf-8"),
            "bbox": {
                "x": x1,
                "y": y1,
                "width": x2 - x1,
                "height": y2 - y1,
            },
            "score": score,
            "mask_area_ratio": float(mask.sum()) / pixel_count,
            "bbox_area_ratio": float((x2 - x1) * (y2 - y1)) / pixel_count,
            "positive_points": 1,
            "negative_points": 4,
        }

    def test_distinct_shoe_masks_are_combined(self):
        image = Image.new("RGB", (100, 80), "gray")
        left = np.zeros((80, 100), dtype=bool)
        right = np.zeros((80, 100), dtype=bool)
        left[20:70, 10:35] = True
        right[20:70, 65:90] = True

        combined = merge_isolation_results(
            image,
            [self._result_for_mask(left), self._result_for_mask(right, 0.85)],
        )

        self.assertEqual(combined["isolation_components"], 2)
        self.assertEqual(combined["isolation_strategy"], "distinct_mask_union")
        self.assertAlmostEqual(combined["mask_area_ratio"], 0.3125)
        self.assertEqual(combined["bbox"]["x"], 10)
        self.assertEqual(combined["bbox"]["width"], 80)

    def test_duplicate_shoe_masks_are_not_counted_twice(self):
        image = Image.new("RGB", (100, 80), "gray")
        shoe = np.zeros((80, 100), dtype=bool)
        shoe[20:70, 20:60] = True

        combined = merge_isolation_results(
            image,
            [self._result_for_mask(shoe), self._result_for_mask(shoe, 0.80)],
        )

        self.assertEqual(combined["isolation_components"], 1)
        self.assertEqual(combined["isolation_strategy"], "single_valid_component")

    def test_shoe_recovery_rejects_background_sized_mask(self):
        primary_mask = np.zeros((80, 100), dtype=bool)
        primary_mask[25:65, 15:40] = True
        plausible_second = np.zeros((80, 100), dtype=bool)
        plausible_second[25:65, 60:88] = True
        background = np.zeros((80, 100), dtype=bool)
        background[5:75, 5:95] = True

        primary = self._result_for_mask(primary_mask)
        plausible = self._result_for_mask(plausible_second, 0.82)
        unsafe = self._result_for_mask(background, 0.95)
        selected = select_compatible_shoe_results(
            [primary],
            [plausible, unsafe],
        )

        self.assertIn(primary, selected)
        self.assertIn(plausible, selected)
        self.assertNotIn(unsafe, selected)


if __name__ == "__main__":
    unittest.main()
