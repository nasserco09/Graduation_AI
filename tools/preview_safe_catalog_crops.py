"""Build a resumable content-preserving catalog-crop preview.

SAM2 is used only to locate the product.  The saved image is always cropped
from the untouched source pixels, so segmentation holes can never damage the
garment.  This command never changes the active catalog or FAISS index.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from backend.catalog_config import CATALOG_DIR, DATA_DIR
from backend.catalog_isolation import (
    assess_catalog_isolation,
    build_catalog_prompts,
    build_shoe_recovery_prompts,
    choose_content_crop_box,
    merge_isolation_results,
    select_compatible_shoe_results,
)
from tools.preview_catalog_isolation import load_balanced_sample


PREVIEW_DIR = DATA_DIR / "catalog_safe_crop_preview"
CHECKPOINT_NAME = "checkpoint.json"
SAFE_CROP_BATCH_VERSION = "content-preserving-crop-batch-v6"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preview safe catalog crops on a balanced sample without changing "
            "the active search index."
        )
    )
    parser.add_argument(
        "--per-category",
        type=int,
        default=10,
        help="Deterministic sample count per category (default: 10).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PREVIEW_DIR,
        help="Directory used for safe crops, checkpoint, manifest, and sheet.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Reprocess existing checkpointed images instead of resuming.",
    )
    return parser.parse_args()


def write_json_atomic(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def load_checkpoint(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if data.get("crop_version") != SAFE_CROP_BATCH_VERSION:
        return {}
    return {
        str(record["image"]): record
        for record in data.get("items", [])
        if record.get("image")
    }


def make_safe_tile(
    original: Image.Image,
    safe_crop: Image.Image,
    *,
    label: str,
    fallback_used: bool,
) -> Image.Image:
    panel_width = 280
    image_height = 220
    label_height = 48
    tile_width = panel_width * 2

    def fit(image: Image.Image) -> Image.Image:
        contained = ImageOps.contain(
            image.convert("RGB"),
            (panel_width - 12, image_height - 12),
        )
        canvas = Image.new("RGB", (panel_width, image_height), "white")
        canvas.paste(
            contained,
            (
                (panel_width - contained.width) // 2,
                (image_height - contained.height) // 2,
            ),
        )
        return canvas

    tile = Image.new("RGB", (tile_width, image_height + label_height), "white")
    tile.paste(fit(original), (0, 0))
    tile.paste(fit(safe_crop), (panel_width, 0))
    draw = ImageDraw.Draw(tile)
    draw.line(
        (panel_width, 0, panel_width, image_height),
        fill=(180, 180, 180),
        width=2,
    )
    draw.rectangle(
        (0, image_height, tile_width, image_height + label_height),
        fill=(255, 247, 219) if fallback_used else (235, 247, 238),
    )
    draw.text((8, image_height + 5), label, fill=(20, 20, 20))
    draw.text((8, image_height + 25), "original", fill=(70, 70, 70))
    draw.text(
        (panel_width + 8, image_height + 25),
        "safe crop",
        fill=(70, 70, 70),
    )
    return tile


def save_contact_sheet(
    tiles: list[Image.Image],
    output_path: Path,
    *,
    columns: int = 5,
) -> None:
    if not tiles:
        raise ValueError("No preview tiles were generated.")
    tile_width = max(tile.width for tile in tiles)
    tile_height = max(tile.height for tile in tiles)
    rows = math.ceil(len(tiles) / columns)
    sheet = Image.new(
        "RGB",
        (tile_width * columns, tile_height * rows),
        "white",
    )
    for index, tile in enumerate(tiles):
        x = (index % columns) * tile_width
        y = (index // columns) * tile_height
        sheet.paste(tile, (x, y))
    sheet.save(output_path, quality=92, optimize=True)


def crop_from_bbox(image: Image.Image, bbox: dict) -> Image.Image:
    x1 = int(bbox["x"])
    y1 = int(bbox["y"])
    x2 = x1 + int(bbox["width"])
    y2 = y1 + int(bbox["height"])
    return image.crop((x1, y1, x2, y2))


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    safe_crop_dir = output_dir / "safe_crops"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_crop_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / CHECKPOINT_NAME

    from backend.segmenter import Segmenter

    sample = load_balanced_sample(args.per_category)
    cached_records = {} if args.overwrite else load_checkpoint(checkpoint_path)
    segmenter = None
    records = []
    tiles = []
    processed_count = 0
    reused_count = 0

    for position, item in enumerate(sample, start=1):
        relative_path = Path(str(item["image"]))
        image_key = relative_path.as_posix()
        source_path = CATALOG_DIR / relative_path
        safe_output_path = (safe_crop_dir / relative_path).with_suffix(".png")
        safe_output_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(source_path) as source_image:
            original = source_image.convert("RGB")

        cached = cached_records.get(image_key)
        if cached and safe_output_path.is_file():
            with Image.open(safe_output_path) as cached_crop:
                safe_crop = cached_crop.convert("RGB")
            record = dict(cached)
            record["reused_from_checkpoint"] = True
            reused_count += 1
        else:
            if segmenter is None:
                segmenter = Segmenter()

            category_key = str(item.get("category_key", ""))
            prompt_runs = build_catalog_prompts(
                category_key,
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
                category_key.strip().lower() == "shoes"
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
                recovery_candidates = (
                    len(compatible_results) - len(primary_results)
                )

            assessment = assess_catalog_isolation(result)
            crop_bbox, crop_strategy = choose_content_crop_box(
                category_key,
                result,
                original.width,
                original.height,
            )
            safe_crop = crop_from_bbox(original, crop_bbox)
            safe_crop.save(safe_output_path, format="PNG", optimize=True)
            record = {
                "image": image_key,
                "product_id": item.get("product_id"),
                "category_key": item.get("category_key"),
                "source_size": {
                    "width": original.width,
                    "height": original.height,
                },
                "prompt_runs": len(prompt_runs),
                "isolation_components": result.get("isolation_components", 1),
                "isolation_strategy": result.get(
                    "isolation_strategy",
                    "single_prompt",
                ),
                "recovery_used": recovery_used,
                "recovery_candidates": recovery_candidates,
                "locator_assessment": assessment.as_dict(),
                "content_crop": {
                    "bbox": crop_bbox,
                    "strategy": crop_strategy,
                    "preserves_original_pixels": True,
                    "path": safe_output_path.relative_to(output_dir).as_posix(),
                },
                "reused_from_checkpoint": False,
            }
            cached_records[image_key] = record
            processed_count += 1
            write_json_atomic(
                checkpoint_path,
                {
                    "schema_version": "1.0",
                    "crop_version": SAFE_CROP_BATCH_VERSION,
                    "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "items": list(cached_records.values()),
                },
            )

        crop_strategy = str(record["content_crop"]["strategy"])
        fallback_used = crop_strategy.startswith("full_image_")
        label = (
            f"{position:03d} {item.get('category_key', 'unknown')} | "
            f"{crop_strategy}"
        )
        tiles.append(
            make_safe_tile(
                original,
                safe_crop,
                label=label,
                fallback_used=fallback_used,
            )
        )
        records.append(record)
        print(f"[{position}/{len(sample)}] {label}")

    fallback_count = sum(
        1
        for record in records
        if str(record["content_crop"]["strategy"]).startswith("full_image_")
    )
    review_count = sum(
        1
        for record in records
        if record["locator_assessment"]["review_required"]
    )
    manifest = {
        "schema_version": "1.0",
        "crop_version": SAFE_CROP_BATCH_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "catalog_source": str(CATALOG_DIR),
        "sample_count": len(records),
        "safe_crop_count": len(records),
        "fallback_count": fallback_count,
        "locator_review_count": review_count,
        "processed_this_run": processed_count,
        "reused_from_checkpoint": reused_count,
        "active_index_changed": False,
        "selected_preview_strategy": "content_preserving_crop",
        "items": records,
    }
    write_json_atomic(output_dir / "manifest.json", manifest)
    save_contact_sheet(tiles, output_dir / "contact_sheet.jpg")

    print()
    print(f"Safe crops: {len(records)}/{len(records)}")
    print(f"Full-image fallbacks: {fallback_count}/{len(records)}")
    print(f"Processed this run: {processed_count}")
    print(f"Reused from checkpoint: {reused_count}")
    print(f"Manifest: {output_dir / 'manifest.json'}")
    print(f"Contact sheet: {output_dir / 'contact_sheet.jpg'}")
    print("The active catalog and FAISS index were not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
