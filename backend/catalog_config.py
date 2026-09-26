"""Resolve the application catalog without mixing it with evaluation splits."""

from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LEGACY_CATALOG_DIR = ROOT / "catalog"
TRAIN_CATALOG_DIR = ROOT / "datasets" / "clothing_small" / "train"
LEGACY_METADATA_FILE = DATA_DIR / "catalog_metadata.json"
TRAIN_METADATA_FILE = DATA_DIR / "catalog_metadata_train.json"


def _resolve_catalog() -> tuple[Path, Path, str]:
    custom_catalog = os.getenv("GRADUATION_AI_CATALOG_DIR")
    custom_metadata = os.getenv("GRADUATION_AI_CATALOG_METADATA")

    if custom_catalog:
        catalog_dir = Path(custom_catalog).expanduser().resolve()
        metadata_file = (
            Path(custom_metadata).expanduser().resolve()
            if custom_metadata
            else TRAIN_METADATA_FILE
        )
        return catalog_dir, metadata_file, "custom"

    if TRAIN_CATALOG_DIR.is_dir() and TRAIN_METADATA_FILE.is_file():
        return TRAIN_CATALOG_DIR, TRAIN_METADATA_FILE, "clothing_small_train"

    return LEGACY_CATALOG_DIR, LEGACY_METADATA_FILE, "demo_30_images"


CATALOG_DIR, CATALOG_METADATA_FILE, CATALOG_SOURCE = _resolve_catalog()
