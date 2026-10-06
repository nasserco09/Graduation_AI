"""Build a verified, resumable safe-crop copy of the complete catalog.

The generated files are experimental.  They never replace the source catalog
or the application's active FAISS index.  SAM2 is used only as a locator; the
saved crop always comes from the source RGB pixels.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageOps

from backend.catalog_config import CATALOG_DIR, CATALOG_METADATA_FILE, DATA_DIR
from backend.catalog_isolation import (
    assess_catalog_isolation,
    build_catalog_prompts,
    build_shoe_recovery_prompts,
    choose_content_crop_box,
    merge_isolation_results,
    select_compatible_shoe_results,
)
from backend.catalog_metadata import CatalogMetadata


DEFAULT_OUTPUT_DIR = DATA_DIR / "catalog_safe_crops_v1"
FULL_CROP_VERSION = "content-preserving-crop-full-v1"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Experimental output directory (default: data/catalog_safe_crops_v1).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Reprocess every image instead of reusing verified item records.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Developer smoke-test limit. Omit it for the complete catalog.",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def save_png_atomic(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    image.save(temporary, format="PNG", optimize=True)
    temporary.replace(path)


def crop_from_bbox(image: Image.Image, bbox: dict) -> Image.Image:
    x1 = int(bbox["x"])
    y1 = int(bbox["y"])
    x2 = x1 + int(bbox["width"])
    y2 = y1 + int(bbox["height"])
    if not (0 <= x1 < x2 <= image.width and 0 <= y1 < y2 <= image.height):
        raise ValueError("Safe-crop bounding box is outside the source image.")
    return image.crop((x1, y1, x2, y2))


def _record_path(records_dir: Path, relative_path: Path) -> Path:
    return records_dir / relative_path.with_suffix(relative_path.suffix + ".json")


def load_reusable_record(
    record_path: Path,
    output_dir: Path,
    *,
    image_key: str,
    source_sha256: str,
) -> dict | None:
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if (
        record.get("schema_version") != "1.0"
        or record.get("crop_version") != FULL_CROP_VERSION
        or record.get("image") != image_key
        or record.get("source_sha256") != source_sha256
    ):
        return None

    relative_output = record.get("content_crop", {}).get("path")
    expected_hash = record.get("output_sha256")
    if not isinstance(relative_output, str) or not isinstance(expected_hash, str):
        return None
    output_path = output_dir / relative_output
    if not output_path.is_file() or sha256_file(output_path) != expected_hash:
        return None
    try:
        with Image.open(output_path) as image:
            image.verify()
    except (OSError, ValueError):
        return None
    return record


def _catalog_paths() -> list[Path]:
    return sorted(
        path
        for path in CATALOG_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def _aggregate_checksum(records: list[dict], field: str) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(record["image"].encode("utf-8"))
        digest.update(str(record[field]).encode("ascii"))
    return digest.hexdigest()


def _locate_and_crop(segmenter, original: Image.Image, category_key: str) -> tuple:
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
    if category_key == "shoes" and int(result.get("isolation_components", 1)) < 2:
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
        compatible = select_compatible_shoe_results(
            primary_results,
            recovery_results,
        )
        result = merge_isolation_results(original, compatible)
        prompt_runs.extend(recovery_prompts)
        recovery_used = True
        recovery_candidates = len(compatible) - len(primary_results)

    assessment = assess_catalog_isolation(result)
    crop_bbox, crop_strategy = choose_content_crop_box(
        category_key,
        result,
        original.width,
        original.height,
    )
    return (
        crop_from_bbox(original, crop_bbox),
        crop_bbox,
        crop_strategy,
        result,
        assessment,
        len(prompt_runs),
        recovery_used,
        recovery_candidates,
    )


def main() -> int:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit must be at least 1.")

    output_dir = args.output_dir.resolve()
    safe_crop_dir = output_dir / "safe_crops"
    records_dir = output_dir / "records"
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = CatalogMetadata(CATALOG_METADATA_FILE)
    catalog_paths = _catalog_paths()
    relative_paths = [path.relative_to(CATALOG_DIR).as_posix() for path in catalog_paths]
    metadata.require_valid_catalog(relative_paths)
    selected_paths = catalog_paths[: args.limit] if args.limit else catalog_paths

    # Fail before producing records when the model itself cannot be loaded.
    from backend.segmenter import Segmenter

    segmenter = Segmenter()
    records: list[dict] = []
    processed = 0
    reused = 0

    for position, source_path in enumerate(selected_paths, start=1):
        relative_path = source_path.relative_to(CATALOG_DIR)
        image_key = relative_path.as_posix()
        item = metadata.get(image_key)
        source_sha256 = sha256_file(source_path)
        # Keep the original suffix in the filename so item.jpg and item.png
        # can never collide in the experimental copy.
        safe_output_path = (safe_crop_dir / relative_path).with_suffix(
            relative_path.suffix + ".png"
        )
        record_path = _record_path(records_dir, relative_path)

        record = None if args.overwrite else load_reusable_record(
            record_path,
            output_dir,
            image_key=image_key,
            source_sha256=source_sha256,
        )
        if record is not None:
            reused += 1
            records.append(record)
            print(f"[{position}/{len(selected_paths)}] REUSED {image_key}")
            continue

        with Image.open(source_path) as source:
            original = ImageOps.exif_transpose(source).convert("RGB")

        processing_error = None
        try:
            (
                safe_crop,
                crop_bbox,
                crop_strategy,
                result,
                assessment,
                prompt_count,
                recovery_used,
                recovery_candidates,
            ) = _locate_and_crop(segmenter, original, item["category_key"])
            assessment_payload = assessment.as_dict()
        except Exception as error:  # Preserve content and expose the failure in evidence.
            safe_crop = original.copy()
            crop_bbox = {
                "x": 0,
                "y": 0,
                "width": original.width,
                "height": original.height,
            }
            crop_strategy = "full_image_processing_error_fallback"
            result = {"isolation_components": 0, "isolation_strategy": "error"}
            assessment_payload = {
                "accepted": False,
                "reason": "processing_error",
                "review_required": True,
                "score": 0.0,
                "mask_area_ratio": 0.0,
                "bbox_area_ratio": 1.0,
            }
            prompt_count = 0
            recovery_used = False
            recovery_candidates = 0
            processing_error = f"{type(error).__name__}: {error}"

        save_png_atomic(safe_crop, safe_output_path)
        record = {
            "schema_version": "1.0",
            "crop_version": FULL_CROP_VERSION,
            "image": image_key,
            "product_id": item["product_id"],
            "category_key": item["category_key"],
            "source_sha256": source_sha256,
            "source_size_bytes": source_path.stat().st_size,
            "source_dimensions": {
                "width": original.width,
                "height": original.height,
            },
            "prompt_runs": prompt_count,
            "isolation_components": int(result.get("isolation_components", 1)),
            "isolation_strategy": result.get("isolation_strategy", "single_prompt"),
            "recovery_used": recovery_used,
            "recovery_candidates": recovery_candidates,
            "locator_assessment": assessment_payload,
            "content_crop": {
                "bbox": crop_bbox,
                "strategy": crop_strategy,
                "preserves_original_pixels": True,
                "path": safe_output_path.relative_to(output_dir).as_posix(),
                "width": safe_crop.width,
                "height": safe_crop.height,
            },
            "output_sha256": sha256_file(safe_output_path),
            "processing_error": processing_error,
        }
        write_json_atomic(record_path, record)
        records.append(record)
        processed += 1
        marker = "FALLBACK" if crop_strategy.startswith("full_image_") else "CROP"
        print(f"[{position}/{len(selected_paths)}] {marker} {image_key}")

    del segmenter
    category_counts = Counter(record["category_key"] for record in records)
    strategy_counts = Counter(
        record["content_crop"]["strategy"] for record in records
    )
    missing = sorted(set(relative_paths) - {record["image"] for record in records})
    unexpected = sorted({record["image"] for record in records} - set(relative_paths))
    complete_catalog = not missing and not unexpected and len(records) == len(catalog_paths)
    manifest = {
        "schema_version": "1.0",
        "crop_version": FULL_CROP_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "catalog_source": str(CATALOG_DIR),
        "catalog_metadata": str(CATALOG_METADATA_FILE),
        "metadata_checksum": metadata.checksum(),
        "expected_catalog_count": len(catalog_paths),
        "safe_crop_count": len(records),
        "complete_catalog": complete_catalog,
        "missing_images": missing,
        "unexpected_images": unexpected,
        "category_counts": dict(sorted(category_counts.items())),
        "strategy_counts": dict(sorted(strategy_counts.items())),
        "fallback_count": sum(
            count
            for strategy, count in strategy_counts.items()
            if strategy.startswith("full_image_")
        ),
        "processing_error_count": sum(
            1 for record in records if record.get("processing_error")
        ),
        "locator_review_count": sum(
            1
            for record in records
            if record["locator_assessment"].get("review_required")
        ),
        "processed_this_run": processed,
        "reused_verified_records": reused,
        "source_catalog_checksum": _aggregate_checksum(records, "source_sha256"),
        "safe_crop_checksum": _aggregate_checksum(records, "output_sha256"),
        "active_catalog_changed": False,
        "active_index_changed": False,
        "items": records,
    }
    manifest_path = output_dir / "manifest.json"
    write_json_atomic(manifest_path, manifest)

    print()
    print(f"Safe crops: {len(records)}/{len(catalog_paths)}")
    print(f"Complete catalog: {complete_catalog}")
    print(f"Processed this run: {processed}")
    print(f"Reused verified records: {reused}")
    print(f"Full-image fallbacks: {manifest['fallback_count']}")
    print(f"Processing errors: {manifest['processing_error_count']}")
    print(f"Manifest: {manifest_path}")
    print("The active catalog and active FAISS index were not changed.")
    return 0 if complete_catalog else 2


if __name__ == "__main__":
    raise SystemExit(main())
