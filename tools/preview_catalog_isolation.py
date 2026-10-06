"""Create a reversible SAM2 catalog-isolation preview.

The command processes a balanced sample only and never changes the active
catalog, FAISS index, metadata, or application settings.
"""

from __future__ import annotations

import argparse
import base64
from collections import defaultdict
from datetime import datetime, timezone
from io import BytesIO
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from backend.catalog_config import CATALOG_DIR, CATALOG_METADATA_FILE, DATA_DIR
from backend.catalog_isolation import (
    CATALOG_ISOLATION_VERSION,
    assess_catalog_isolation,
    build_catalog_prompts,
    build_shoe_recovery_prompts,
    choose_content_crop_box,
    merge_isolation_results,
    select_compatible_shoe_results,
)


PREVIEW_DIR = DATA_DIR / "catalog_isolation_preview"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preview SAM2 product isolation on a balanced catalog sample "
            "without modifying the active search index."
        )
    )
    parser.add_argument(
        "--per-category",
        type=int,
        default=3,
        help="Number of deterministic sample images per category (default: 3).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PREVIEW_DIR,
        help="Directory used for cutouts, manifest, and contact sheet.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Reprocess images whose preview cutouts already exist.",
    )
    return parser.parse_args()


def load_balanced_sample(per_category: int) -> list[dict]:
    if per_category < 1:
        raise ValueError("--per-category must be at least 1.")

    data = json.loads(CATALOG_METADATA_FILE.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict]] = defaultdict(list)

    for item in data.get("items", []):
        if not item.get("active", True):
            continue
        relative_path = Path(str(item.get("image", "")))
        source_path = CATALOG_DIR / relative_path
        if (
            source_path.is_file()
            and source_path.suffix.lower() in SUPPORTED_EXTENSIONS
        ):
            grouped[str(item.get("category_key", "unknown"))].append(item)

    selected = []
    for category_key in sorted(grouped):
        category_items = sorted(
            grouped[category_key],
            key=lambda item: str(item["image"]),
        )
        if len(category_items) < per_category:
            raise ValueError(
                f"Category '{category_key}' has only {len(category_items)} "
                f"available images; requested {per_category}."
            )

        # Spread samples across the sorted category instead of taking only the
        # first adjacent files.
        if per_category == 1:
            indices = [len(category_items) // 2]
        else:
            last = len(category_items) - 1
            indices = [round(i * last / (per_category - 1)) for i in range(per_category)]
        selected.extend(category_items[index] for index in indices)

    if not selected:
        raise ValueError("No active catalog images were found in metadata.")
    return selected


def decode_png(encoded: str) -> Image.Image:
    raw = base64.b64decode(encoded, validate=True)
    with Image.open(BytesIO(raw)) as image:
        return image.convert("RGB")


def make_tile(
    original: Image.Image,
    point_cutout: Image.Image | None,
    box_cutout: Image.Image | None,
    safe_crop: Image.Image,
    *,
    label: str,
    accepted: bool,
    review_required: bool = False,
) -> Image.Image:
    panel_width = 320
    panel_names = ("original", "point mask", "box mask", "safe crop")
    panels = (original, point_cutout or original, box_cutout or original, safe_crop)
    tile_width = panel_width * len(panels)
    image_height = 300
    label_height = 58

    def fit(image: Image.Image) -> Image.Image:
        contained = ImageOps.contain(
            image.convert("RGB"),
            (panel_width - 16, image_height - 16),
        )
        canvas = Image.new("RGB", (panel_width, image_height), "white")
        x = (panel_width - contained.width) // 2
        y = (image_height - contained.height) // 2
        canvas.paste(contained, (x, y))
        return canvas

    tile = Image.new("RGB", (tile_width, image_height + label_height), "white")
    for index, panel in enumerate(panels):
        tile.paste(fit(panel), (index * panel_width, 0))

    draw = ImageDraw.Draw(tile)
    for index in range(1, len(panels)):
        x = index * panel_width
        draw.line((x, 0, x, image_height), fill=(180, 180, 180), width=2)
    draw.rectangle(
        (0, image_height, tile_width, image_height + label_height),
        fill=(
            (255, 247, 219)
            if review_required
            else ((235, 247, 238) if accepted else (253, 235, 235))
        ),
    )
    draw.text((12, image_height + 8), label, fill=(20, 20, 20))
    for index, panel_name in enumerate(panel_names):
        draw.text(
            (index * panel_width + 12, image_height + 33),
            panel_name,
            fill=(70, 70, 70),
        )
    return tile


def save_contact_sheet(
    tiles: list[Image.Image],
    output_path: Path,
    *,
    columns: int = 2,
) -> None:
    if not tiles:
        raise ValueError("No preview tiles were generated.")
    if columns < 1:
        raise ValueError("Contact-sheet columns must be at least 1.")
    tile_width = max(tile.width for tile in tiles)
    tile_height = max(tile.height for tile in tiles)
    rows = math.ceil(len(tiles) / columns)
    width = tile_width * columns
    height = tile_height * rows
    sheet = Image.new("RGB", (width, height), "white")
    for index, tile in enumerate(tiles):
        x = (index % columns) * tile_width
        y = (index // columns) * tile_height
        sheet.paste(tile, (x, y))
    sheet.save(output_path, quality=92, optimize=True)


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    cutout_dir = output_dir / "cutouts"
    box_cutout_dir = output_dir / "box_cutouts"
    safe_crop_dir = output_dir / "safe_crops"
    output_dir.mkdir(parents=True, exist_ok=True)
    cutout_dir.mkdir(parents=True, exist_ok=True)
    box_cutout_dir.mkdir(parents=True, exist_ok=True)
    safe_crop_dir.mkdir(parents=True, exist_ok=True)

    # Importing here avoids loading the heavy model when this module is merely
    # inspected or unit-tested.
    from backend.segmenter import Segmenter

    sample = load_balanced_sample(args.per_category)
    segmenter = Segmenter()
    records = []
    tiles = []

    for position, item in enumerate(sample, start=1):
        relative_path = Path(str(item["image"]))
        source_path = CATALOG_DIR / relative_path
        output_path = (cutout_dir / relative_path).with_suffix(".png")
        box_output_path = (box_cutout_dir / relative_path).with_suffix(".png")
        safe_output_path = (safe_crop_dir / relative_path).with_suffix(".png")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        box_output_path.parent.mkdir(parents=True, exist_ok=True)
        safe_output_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(source_path) as source_image:
            original = source_image.convert("RGB")

        prompt_runs = build_catalog_prompts(
            str(item.get("category_key", "")),
            original.width,
            original.height,
        )

        primary_results = [
            segmenter.segment(
                original,
                points,
                labels,
                include_binary_mask=len(prompt_runs) > 1,
            )
            for points, labels in prompt_runs
        ]
        result = (
            merge_isolation_results(original, primary_results)
            if len(primary_results) > 1
            else primary_results[0]
        )
        recovery_used = False
        recovery_candidates = 0
        if (
            str(item.get("category_key", "")).strip().lower() == "shoes"
            and int(result.get("isolation_components", 1)) < 2
        ):
            recovery_prompts = build_shoe_recovery_prompts(
                original.width,
                original.height,
                result.get("bbox"),
            )
            recovery_results = [
                segmenter.segment(
                    original,
                    points,
                    labels,
                    include_binary_mask=True,
                )
                for points, labels in recovery_prompts
            ]
            compatible_results = select_compatible_shoe_results(
                primary_results,
                recovery_results,
            )
            result = merge_isolation_results(original, compatible_results)
            prompt_runs.extend(recovery_prompts)
            recovery_used = True
            recovery_candidates = len(compatible_results) - len(primary_results)

        assessment = assess_catalog_isolation(result)
        cutout = decode_png(result["cutout"])

        safe_bbox, safe_strategy = choose_content_crop_box(
            str(item.get("category_key", "")),
            result,
            original.width,
            original.height,
        )
        safe_x1 = int(safe_bbox["x"])
        safe_y1 = int(safe_bbox["y"])
        safe_x2 = safe_x1 + int(safe_bbox["width"])
        safe_y2 = safe_y1 + int(safe_bbox["height"])
        safe_crop = original.crop((safe_x1, safe_y1, safe_x2, safe_y2))

        box_prompt = [
            float(safe_x1),
            float(safe_y1),
            float(max(safe_x1 + 1, safe_x2 - 1)),
            float(max(safe_y1 + 1, safe_y2 - 1)),
        ]
        box_result = None
        box_assessment = None
        box_cutout = None
        box_error = None
        try:
            box_result = segmenter.segment(
                original,
                box=box_prompt,
                include_binary_mask=False,
            )
            box_assessment = assess_catalog_isolation(box_result)
            box_cutout = decode_png(box_result["cutout"])
        except (RuntimeError, ValueError, TypeError) as exc:
            box_error = f"{type(exc).__name__}: {exc}"

        if assessment.accepted and (args.overwrite or not output_path.exists()):
            cutout.save(output_path, format="PNG", optimize=True)
        if box_cutout is not None and (args.overwrite or not box_output_path.exists()):
            box_cutout.save(box_output_path, format="PNG", optimize=True)
        if args.overwrite or not safe_output_path.exists():
            safe_crop.save(safe_output_path, format="PNG", optimize=True)

        label = (
            f"{position:02d} {item.get('category_key', 'unknown')} | "
            f"point={assessment.score:.3f} | "
            f"box={(f'{box_assessment.score:.3f}' if box_assessment else 'error')} | "
            f"parts={result.get('isolation_components', 1)} | "
            f"crop={safe_strategy}"
        )
        tiles.append(
            make_tile(
                original,
                cutout,
                box_cutout,
                safe_crop,
                label=label,
                accepted=assessment.accepted,
                review_required=assessment.review_required,
            )
        )
        first_points, first_labels = prompt_runs[0]
        records.append(
            {
                "image": relative_path.as_posix(),
                "product_id": item.get("product_id"),
                "category_key": item.get("category_key"),
                "points": first_points,
                "labels": first_labels,
                "prompt_runs": [
                    {"points": points, "labels": labels}
                    for points, labels in prompt_runs
                ],
                "bbox": result.get("bbox"),
                "isolation_components": result.get("isolation_components", 1),
                "isolation_strategy": result.get(
                    "isolation_strategy",
                    "single_prompt",
                ),
                "recovery_used": recovery_used,
                "recovery_candidates": recovery_candidates,
                "assessment": assessment.as_dict(),
                "point_assessment": assessment.as_dict(),
                "box_prompt": box_prompt,
                "box_bbox": box_result.get("bbox") if box_result else None,
                "box_assessment": (
                    box_assessment.as_dict() if box_assessment else None
                ),
                "box_error": box_error,
                "content_crop": {
                    "bbox": safe_bbox,
                    "strategy": safe_strategy,
                    "preserves_original_pixels": True,
                    "path": safe_output_path.relative_to(output_dir).as_posix(),
                },
                "selected_preview_strategy": "content_preserving_crop",
                "cutout": (
                    output_path.relative_to(output_dir).as_posix()
                    if assessment.accepted
                    else None
                ),
                "box_cutout": (
                    box_output_path.relative_to(output_dir).as_posix()
                    if box_cutout is not None
                    else None
                ),
            }
        )
        print(f"[{position}/{len(sample)}] {label}")

    accepted_count = sum(
        1 for record in records if record["assessment"]["accepted"]
    )
    review_count = sum(
        1 for record in records if record["assessment"]["review_required"]
    )
    box_accepted_count = sum(
        1
        for record in records
        if record["box_assessment"] and record["box_assessment"]["accepted"]
    )
    box_review_count = sum(
        1
        for record in records
        if record["box_assessment"]
        and record["box_assessment"]["review_required"]
    )
    manifest = {
        "schema_version": "2.0",
        "isolation_version": CATALOG_ISOLATION_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "catalog_source": str(CATALOG_DIR),
        "sample_count": len(records),
        "accepted_count": accepted_count,
        "review_count": review_count,
        "rejected_count": len(records) - accepted_count,
        "point_accepted_count": accepted_count,
        "point_review_count": review_count,
        "box_accepted_count": box_accepted_count,
        "box_review_count": box_review_count,
        "safe_crop_count": len(records),
        "active_index_changed": False,
        "adaptive_shoe_recovery": True,
        "content_preserving_crop": True,
        "selected_preview_strategy": "content_preserving_crop",
        "items": records,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    save_contact_sheet(tiles, output_dir / "contact_sheet.jpg")

    print()
    print(f"Accepted: {accepted_count}/{len(records)}")
    print(f"Needs visual review: {review_count}/{len(records)}")
    print(f"Box prompts accepted: {box_accepted_count}/{len(records)}")
    print(f"Box prompts needing review: {box_review_count}/{len(records)}")
    print(f"Manifest: {output_dir / 'manifest.json'}")
    print(f"Contact sheet: {output_dir / 'contact_sheet.jpg'}")
    print("The active catalog and FAISS index were not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
