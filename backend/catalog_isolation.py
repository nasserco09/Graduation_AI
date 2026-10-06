"""Rules and quality checks for the catalog-isolation experiment.

This module deliberately contains no model loading.  It can be unit-tested
without SAM2 and is used by the preview tool before catalog isolation is ever
allowed to affect the application index.
"""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from io import BytesIO

import numpy as np
from PIL import Image


CATALOG_ISOLATION_VERSION = "sam2-content-preserving-crop-preview-v5"


@dataclass(frozen=True)
class CatalogIsolationAssessment:
    accepted: bool
    reason: str
    review_required: bool
    score: float
    mask_area_ratio: float
    bbox_area_ratio: float

    def as_dict(self) -> dict:
        return asdict(self)


def expand_bounding_box(
    bbox: dict,
    image_width: int,
    image_height: int,
    *,
    padding_ratio: float = 0.10,
) -> dict:
    """Expand and clamp a SAM2 bounding box for a content-preserving crop."""

    if image_width < 2 or image_height < 2:
        raise ValueError("Catalog image dimensions must be at least 2x2.")
    if not 0.0 <= padding_ratio <= 0.50:
        raise ValueError("padding_ratio must be between 0 and 0.50.")

    x = int(bbox.get("x", 0))
    y = int(bbox.get("y", 0))
    width = int(bbox.get("width", 0))
    height = int(bbox.get("height", 0))
    if width <= 0 or height <= 0:
        raise ValueError("Bounding box width and height must be positive.")

    pad_x = max(4, round(width * padding_ratio))
    pad_y = max(4, round(height * padding_ratio))
    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(image_width, x + width + pad_x)
    y2 = min(image_height, y + height + pad_y)
    if x2 <= x1 or y2 <= y1:
        raise ValueError("Expanded bounding box is outside the source image.")
    return {
        "x": x1,
        "y": y1,
        "width": x2 - x1,
        "height": y2 - y1,
    }


def choose_content_crop_box(
    category_key: str,
    result: dict,
    image_width: int,
    image_height: int,
    *,
    padding_ratio: float = 0.10,
) -> tuple[dict, str]:
    """Choose a crop that never deletes pixels from inside the product.

    Footwear with only one detected component falls back to the full original
    image so a second shoe cannot be accidentally discarded.  Rejected masks
    receive the same conservative fallback.
    """

    assessment = assess_catalog_isolation(result)
    normalized_category = str(category_key).strip().lower()
    components = int(result.get("isolation_components", 1))
    if not assessment.accepted:
        return (
            {"x": 0, "y": 0, "width": image_width, "height": image_height},
            "full_image_rejected_mask_fallback",
        )
    if normalized_category == "shoes" and components < 2:
        return (
            {"x": 0, "y": 0, "width": image_width, "height": image_height},
            "full_image_single_shoe_fallback",
        )
    return (
        expand_bounding_box(
            result.get("bbox") or {},
            image_width,
            image_height,
            padding_ratio=padding_ratio,
        ),
        "expanded_product_bbox",
    )


def build_catalog_prompt(
    category_key: str,
    width: int,
    height: int,
) -> tuple[list[list[float]], list[int]]:
    """Return category-aware product points and four negative border points.

    The catalog contains centered, single-product photographs.  This function
    keeps the original single-prompt API.  Pair-aware shoe processing uses
    ``build_catalog_prompts`` below so that each shoe can be segmented in an
    independent SAM2 pass and the two masks can then be combined safely.
    """

    if width < 2 or height < 2:
        raise ValueError("Catalog image dimensions must be at least 2x2.")

    normalized_category = str(category_key).strip().lower()
    positive_ratios = {
        "shoes": [(0.34, 0.55)],
        "pants": [(0.50, 0.20), (0.35, 0.62), (0.65, 0.62)],
        "hat": [(0.50, 0.34), (0.50, 0.66)],
        "t-shirt": [(0.35, 0.45), (0.65, 0.45), (0.50, 0.72)],
    }.get(normalized_category, [(0.50, 0.50)])

    max_x = float(width - 1)
    max_y = float(height - 1)
    edge_x = max(1.0, max_x * 0.03)
    edge_y = max(1.0, max_y * 0.03)

    positive_points = [
        [max_x * x_ratio, max_y * y_ratio]
        for x_ratio, y_ratio in positive_ratios
    ]
    negative_points = [
        [edge_x, edge_y],
        [max_x - edge_x, edge_y],
        [edge_x, max_y - edge_y],
        [max_x - edge_x, max_y - edge_y],
    ]
    points = positive_points + negative_points
    labels = ([1] * len(positive_points)) + ([0] * len(negative_points))
    return points, labels


def build_catalog_prompts(
    category_key: str,
    width: int,
    height: int,
) -> list[tuple[list[list[float]], list[int]]]:
    """Return one or more independent prompts for a catalog product.

    Shoe photographs frequently contain two disconnected objects.  A single
    SAM2 object prompt naturally returns only one shoe, so the left and right
    sides are prompted independently.  Other categories keep one prompt.
    """

    normalized_category = str(category_key).strip().lower()
    if normalized_category != "shoes":
        return [build_catalog_prompt(normalized_category, width, height)]

    if width < 2 or height < 2:
        raise ValueError("Catalog image dimensions must be at least 2x2.")

    max_x = float(width - 1)
    max_y = float(height - 1)
    edge_x = max(1.0, max_x * 0.03)
    edge_y = max(1.0, max_y * 0.03)
    negative_points = [
        [edge_x, edge_y],
        [max_x - edge_x, edge_y],
        [edge_x, max_y - edge_y],
        [max_x - edge_x, max_y - edge_y],
    ]

    prompts = []
    for x_ratio in (0.34, 0.66):
        points = [[max_x * x_ratio, max_y * 0.55], *negative_points]
        prompts.append((points, [1, 0, 0, 0, 0]))
    return prompts


def build_shoe_recovery_prompts(
    width: int,
    height: int,
    excluded_bbox: dict | None = None,
) -> list[tuple[list[list[float]], list[int]]]:
    """Create extra footwear prompts outside an already detected component.

    Recovery runs only when the primary left/right prompts produced fewer than
    two distinct objects.  Points that fall inside the first object's bounding
    box are skipped, and its center is added as a negative point so SAM2 is
    encouraged to find a different shoe rather than repeat the first one.
    """

    if width < 2 or height < 2:
        raise ValueError("Catalog image dimensions must be at least 2x2.")

    max_x = float(width - 1)
    max_y = float(height - 1)
    edge_x = max(1.0, max_x * 0.03)
    edge_y = max(1.0, max_y * 0.03)
    border_negatives = [
        [edge_x, edge_y],
        [max_x - edge_x, edge_y],
        [edge_x, max_y - edge_y],
        [max_x - edge_x, max_y - edge_y],
    ]

    exclusion_center = None
    if excluded_bbox:
        x1 = float(excluded_bbox.get("x", 0.0))
        y1 = float(excluded_bbox.get("y", 0.0))
        x2 = x1 + float(excluded_bbox.get("width", 0.0))
        y2 = y1 + float(excluded_bbox.get("height", 0.0))
        if x2 > x1 and y2 > y1:
            exclusion_center = [(x1 + x2) / 2.0, (y1 + y2) / 2.0]
    else:
        x1 = y1 = x2 = y2 = -1.0

    prompts = []
    for x_ratio, y_ratio in (
        (0.30, 0.32),
        (0.70, 0.32),
        (0.30, 0.72),
        (0.70, 0.72),
    ):
        positive = [max_x * x_ratio, max_y * y_ratio]
        if x1 <= positive[0] <= x2 and y1 <= positive[1] <= y2:
            continue
        negatives = list(border_negatives)
        if exclusion_center is not None:
            negatives.append(exclusion_center)
        prompts.append((
            [positive, *negatives],
            [1] + ([0] * len(negatives)),
        ))
    return prompts


def select_compatible_shoe_results(
    primary_results: list[dict],
    recovery_results: list[dict],
    *,
    minimum_area_factor: float = 0.30,
    maximum_area_factor: float = 3.00,
    maximum_component_bbox_ratio: float = 0.65,
) -> list[dict]:
    """Keep recovery masks whose size is plausible for a matching shoe.

    A second shoe should be in roughly the same size range as the first.  This
    blocks large background masks and tiny fragments from being merged merely
    to force a two-component result.
    """

    accepted_primary = [
        result
        for result in primary_results
        if assess_catalog_isolation(result).accepted
    ]
    if not accepted_primary:
        return list(primary_results) + list(recovery_results)

    reference = max(
        accepted_primary,
        key=lambda item: float(item.get("score", 0.0)),
    )
    reference_area = float(reference.get("mask_area_ratio", 0.0))
    minimum_area = reference_area * minimum_area_factor
    maximum_area = reference_area * maximum_area_factor

    compatible = []
    for result in recovery_results:
        assessment = assess_catalog_isolation(result)
        area = float(result.get("mask_area_ratio", 0.0))
        bbox_area = float(result.get("bbox_area_ratio", 0.0))
        if (
            assessment.accepted
            and minimum_area <= area <= maximum_area
            and bbox_area <= maximum_component_bbox_ratio
        ):
            compatible.append(result)
    return list(primary_results) + compatible


def assess_catalog_isolation(
    result: dict,
    *,
    minimum_score: float = 0.25,
    review_score: float = 0.45,
    minimum_mask_ratio: float = 0.04,
    maximum_mask_ratio: float = 0.90,
    maximum_bbox_ratio: float = 0.96,
) -> CatalogIsolationAssessment:
    """Reject clearly unsafe masks before they are saved or indexed."""

    score = float(result.get("score", 0.0))
    mask_ratio = float(result.get("mask_area_ratio", 0.0))
    bbox_ratio = float(result.get("bbox_area_ratio", 0.0))

    if mask_ratio < minimum_mask_ratio:
        reason = "mask_too_small"
    elif mask_ratio > maximum_mask_ratio:
        reason = "mask_too_large"
    elif bbox_ratio <= 0.0 or bbox_ratio > maximum_bbox_ratio:
        reason = "invalid_bounding_box"
    elif score < minimum_score:
        reason = "low_model_score"
    else:
        review_required = score < review_score
        return CatalogIsolationAssessment(
            accepted=True,
            reason=(
                "accepted_low_confidence"
                if review_required
                else "accepted"
            ),
            review_required=review_required,
            score=score,
            mask_area_ratio=mask_ratio,
            bbox_area_ratio=bbox_ratio,
        )

    return CatalogIsolationAssessment(
        accepted=False,
        reason=reason,
        review_required=False,
        score=score,
        mask_area_ratio=mask_ratio,
        bbox_area_ratio=bbox_ratio,
    )


def _decode_binary_mask(encoded: str, expected_size: tuple[int, int]) -> np.ndarray:
    raw = base64.b64decode(encoded, validate=True)
    with Image.open(BytesIO(raw)) as image:
        mask_image = image.convert("L")
        if mask_image.size != expected_size:
            raise ValueError("SAM2 binary mask size does not match the source image.")
        return np.asarray(mask_image, dtype=np.uint8) > 0


def _encode_png(image: Image.Image) -> str:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def merge_isolation_results(
    image: Image.Image,
    results: list[dict],
    *,
    duplicate_iou: float = 0.65,
) -> dict:
    """Combine distinct accepted masks, primarily for paired footwear.

    Duplicate prompts that identify the same physical object are collapsed.
    If every candidate fails the safety assessment, the highest-scoring raw
    result is returned and remains rejected by the caller's final assessment.
    """

    if not results:
        raise ValueError("At least one isolation result is required.")
    if not 0.0 <= duplicate_iou <= 1.0:
        raise ValueError("duplicate_iou must be between 0 and 1.")

    source = image.convert("RGB")
    accepted_candidates = []
    for result in sorted(
        results,
        key=lambda item: float(item.get("score", 0.0)),
        reverse=True,
    ):
        if not assess_catalog_isolation(result).accepted:
            continue
        encoded_mask = result.get("binary_mask")
        if not encoded_mask:
            raise ValueError("Isolation result is missing binary_mask.")
        accepted_candidates.append(
            (result, _decode_binary_mask(encoded_mask, source.size))
        )

    if not accepted_candidates:
        fallback = dict(
            max(results, key=lambda item: float(item.get("score", 0.0)))
        )
        fallback["isolation_components"] = 0
        fallback["isolation_strategy"] = "best_rejected_candidate"
        return fallback

    selected: list[tuple[dict, np.ndarray]] = []
    for result, candidate_mask in accepted_candidates:
        duplicate = False
        for _, selected_mask in selected:
            intersection = np.logical_and(candidate_mask, selected_mask).sum()
            union = np.logical_or(candidate_mask, selected_mask).sum()
            iou = float(intersection) / float(union) if union else 1.0
            if iou >= duplicate_iou:
                duplicate = True
                break
        if not duplicate:
            selected.append((result, candidate_mask))

    if len(selected) == 1:
        single = dict(selected[0][0])
        single["isolation_components"] = 1
        single["isolation_strategy"] = "single_valid_component"
        return single

    combined_mask = np.logical_or.reduce([mask for _, mask in selected])
    ys, xs = np.where(combined_mask)
    if len(xs) == 0:
        raise RuntimeError("Combined SAM2 mask is empty.")

    x1 = int(xs.min())
    y1 = int(ys.min())
    x2 = int(xs.max()) + 1
    y2 = int(ys.max()) + 1

    image_array = np.asarray(source)
    cropped_image = image_array[y1:y2, x1:x2]
    cropped_mask = combined_mask[y1:y2, x1:x2]
    cutout_array = np.ones_like(cropped_image) * 255
    cutout_array[cropped_mask] = cropped_image[cropped_mask]

    full_mask_image = Image.fromarray(
        (combined_mask.astype(np.uint8) * 255),
        mode="L",
    )
    pixel_count = float(source.width * source.height)
    selected_results = [result for result, _ in selected]
    return {
        "cutout": _encode_png(Image.fromarray(cutout_array)),
        "binary_mask": _encode_png(full_mask_image),
        "bbox": {
            "x": x1,
            "y": y1,
            "width": x2 - x1,
            "height": y2 - y1,
        },
        "score": min(float(result.get("score", 0.0)) for result in selected_results),
        "mask_area_ratio": round(float(combined_mask.sum()) / pixel_count, 6),
        "bbox_area_ratio": round(
            float((x2 - x1) * (y2 - y1)) / pixel_count,
            6,
        ),
        "positive_points": sum(
            int(result.get("positive_points", 0)) for result in selected_results
        ),
        "negative_points": sum(
            int(result.get("negative_points", 0)) for result in selected_results
        ),
        "isolation_components": len(selected),
        "isolation_strategy": "distinct_mask_union",
        "source_scores": [
            float(result.get("score", 0.0)) for result in selected_results
        ],
    }
