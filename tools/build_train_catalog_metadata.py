"""Generate deterministic product metadata for the clothing_small train split."""

from __future__ import annotations

import json
from pathlib import Path

from backend.catalog_config import ROOT, TRAIN_CATALOG_DIR, TRAIN_METADATA_FILE
from backend.category_routing import CATEGORY_LABELS


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SINGULAR_ARABIC = {
    "dress": "فستان",
    "hat": "قبعة",
    "longsleeve": "قطعة بأكمام طويلة",
    "outwear": "جاكيت",
    "pants": "بنطال",
    "shirt": "قميص",
    "shoes": "حذاء",
    "shorts": "سروال قصير",
    "skirt": "تنورة",
    "t-shirt": "تيشيرت",
}


def build_metadata(catalog_dir: Path = TRAIN_CATALOG_DIR) -> dict:
    if not catalog_dir.is_dir():
        raise FileNotFoundError(f"Train catalog folder not found: {catalog_dir}")

    items = []
    product_ids = set()
    category_counts = {}

    for category_key in sorted(CATEGORY_LABELS):
        category_dir = catalog_dir / category_key
        if not category_dir.is_dir():
            raise FileNotFoundError(f"Category folder not found: {category_dir}")

        category_paths = sorted(
            path
            for path in category_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        category_counts[category_key] = len(category_paths)

        for number, path in enumerate(category_paths, start=1):
            product_id = path.stem
            if product_id in product_ids:
                raise ValueError(f"Duplicate product ID in train catalog: {product_id}")
            product_ids.add(product_id)

            items.append({
                "image": path.relative_to(catalog_dir).as_posix(),
                "product_id": product_id,
                "category_key": category_key,
                "title_ar": f"{SINGULAR_ARABIC[category_key]} رقم {number}",
                "source_dataset": "clothing_small/train",
                "active": True,
            })

    if not items:
        raise ValueError("The train catalog contains no supported images.")

    return {
        "schema_version": "1.0",
        "description": (
            "Generated metadata for the application catalog based only on the "
            "clothing_small train split. Test and validation remain excluded."
        ),
        "catalog_source": "datasets/clothing_small/train",
        "image_count": len(items),
        "category_counts": category_counts,
        "items": items,
    }


def main() -> None:
    metadata = build_metadata()
    TRAIN_METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRAIN_METADATA_FILE.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Saved {len(metadata['items'])} items to {TRAIN_METADATA_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
