"""Validated product metadata independent from image filenames."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.category_routing import CATEGORY_LABELS


METADATA_SCHEMA_VERSION = "1.0"


class CatalogMetadata:
    def __init__(self, metadata_file: Path):
        self.metadata_file = metadata_file
        self.schema_version = ""
        self.items: dict[str, dict] = {}
        self.reload()

    def reload(self) -> None:
        if not self.metadata_file.is_file():
            raise FileNotFoundError(
                f"Catalog metadata file not found: {self.metadata_file}"
            )

        with self.metadata_file.open("r", encoding="utf-8") as stream:
            data = json.load(stream)

        self.schema_version = str(data.get("schema_version", ""))
        if self.schema_version != METADATA_SCHEMA_VERSION:
            raise ValueError(
                "Unsupported catalog metadata schema version: "
                f"{self.schema_version or 'missing'}"
            )

        raw_items = data.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise ValueError("Catalog metadata must contain a non-empty items list.")

        items: dict[str, dict] = {}
        for position, raw_item in enumerate(raw_items, start=1):
            if not isinstance(raw_item, dict):
                raise ValueError(f"Catalog metadata item {position} must be an object.")

            image = str(raw_item.get("image", "")).strip().replace("\\", "/")
            product_id = str(raw_item.get("product_id", "")).strip()
            category_key = str(raw_item.get("category_key", "")).strip().lower()
            title_ar = str(raw_item.get("title_ar", "")).strip()

            if not image or image.startswith("/") or ".." in Path(image).parts:
                raise ValueError(f"Invalid catalog image path at item {position}.")
            if image in items:
                raise ValueError(f"Duplicate catalog image metadata: {image}")
            if not product_id:
                raise ValueError(f"Missing product_id for catalog image: {image}")
            if category_key not in CATEGORY_LABELS:
                raise ValueError(f"Unsupported category_key for {image}: {category_key}")
            if not title_ar:
                raise ValueError(f"Missing Arabic title for catalog image: {image}")

            item = {
                "image": image,
                "product_id": product_id,
                "category_key": category_key,
                "category": CATEGORY_LABELS[category_key],
                "title_ar": title_ar,
                "source_dataset": str(raw_item.get("source_dataset", "")).strip() or None,
                "active": bool(raw_item.get("active", True)),
            }
            items[image] = item

        self.items = items

    def get(self, image_path: str) -> dict:
        normalized = image_path.replace("\\", "/")
        try:
            return self.items[normalized]
        except KeyError as error:
            raise KeyError(f"No catalog metadata found for: {normalized}") from error

    def validate_catalog_paths(self, image_paths: list[str]) -> dict:
        catalog_set = {path.replace("\\", "/") for path in image_paths}
        metadata_set = set(self.items)
        missing_metadata = sorted(catalog_set - metadata_set)
        missing_images = sorted(metadata_set - catalog_set)
        inactive_images = sorted(
            path for path in catalog_set & metadata_set if not self.items[path]["active"]
        )
        valid = not missing_metadata and not missing_images and not inactive_images
        return {
            "valid": valid,
            "schema_version": self.schema_version,
            "catalog_image_count": len(catalog_set),
            "metadata_item_count": len(metadata_set),
            "missing_metadata": missing_metadata,
            "missing_images": missing_images,
            "inactive_images": inactive_images,
        }

    def require_valid_catalog(self, image_paths: list[str]) -> dict:
        summary = self.validate_catalog_paths(image_paths)
        if not summary["valid"]:
            raise ValueError(
                "Catalog metadata validation failed: "
                f"missing metadata={summary['missing_metadata']}, "
                f"missing images={summary['missing_images']}, "
                f"inactive images={summary['inactive_images']}"
            )
        return summary

    def checksum(self) -> str:
        canonical = json.dumps(
            {
                "schema_version": self.schema_version,
                "items": [self.items[key] for key in sorted(self.items)],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()
