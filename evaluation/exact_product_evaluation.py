"""Evaluate retrieval by exact product identity instead of category only."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

from PIL import Image

from backend.catalog_config import CATALOG_DIR, CATALOG_METADATA_FILE, ROOT
from backend.catalog_metadata import CatalogMetadata
from backend.category_routing import normalize_category


DEFAULT_MANIFEST = ROOT / "evaluation" / "exact_product_manifest.json"
DEFAULT_OUTPUT = ROOT / "evaluation" / "results" / "exact_product_results.json"


def calculate_exact_product_metrics(records: list[dict]) -> dict:
    if not records:
        raise ValueError("At least one evaluated query is required.")

    reciprocal_ranks = []
    hits_at_1 = 0
    hits_at_5 = 0
    hits_at_10 = 0
    category_checks = 0
    category_hits = 0

    for record in records:
        expected_id = record["expected_product_id"]
        retrieved_ids = record["retrieved_product_ids"]
        rank = next(
            (position for position, product_id in enumerate(retrieved_ids, start=1)
             if product_id == expected_id),
            None,
        )
        reciprocal_ranks.append(0.0 if rank is None else 1.0 / rank)
        hits_at_1 += int(rank is not None and rank <= 1)
        hits_at_5 += int(rank is not None and rank <= 5)
        hits_at_10 += int(rank is not None and rank <= 10)

        expected_category = record.get("expected_category")
        predicted_category = record.get("predicted_category")
        if expected_category:
            category_checks += 1
            category_hits += int(predicted_category == expected_category)

    count = len(records)
    return {
        "query_count": count,
        "exact_top1": round(hits_at_1 / count, 6),
        "exact_top5": round(hits_at_5 / count, 6),
        "exact_top10": round(hits_at_10 / count, 6),
        "exact_mrr": round(sum(reciprocal_ranks) / count, 6),
        "category_accuracy": (
            round(category_hits / category_checks, 6)
            if category_checks
            else None
        ),
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(
    manifest_path: Path,
    metadata: CatalogMetadata,
    *,
    catalog_dir: Path | None = None,
) -> list[dict]:
    with manifest_path.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)

    if manifest.get("schema_version") != "1.0":
        raise ValueError("Unsupported exact-product manifest schema version.")

    queries = manifest.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError(
            "The exact-product manifest has no queries. Add real query photos "
            "before claiming exact-product accuracy."
        )

    product_categories: dict[str, str] = {}
    for item in metadata.items.values():
        product_id = item["product_id"]
        category = item["category_key"]
        previous = product_categories.setdefault(product_id, category)
        if previous != category:
            raise ValueError(
                f"Product {product_id} is assigned to more than one category."
            )
    catalog_dir = (catalog_dir or CATALOG_DIR).resolve()
    # A copied catalog file outside the catalog directory is still leakage.
    catalog_hashes = set()
    for image_key in metadata.items:
        path = catalog_dir / image_key
        if not path.is_file():
            raise FileNotFoundError(f"Catalog image required for leakage validation is missing: {path}")
        catalog_hashes.add(file_sha256(path))
    query_hashes = set()
    validated = []
    for position, query in enumerate(queries, start=1):
        image_value = str(query.get("image", "")).strip()
        product_id = str(query.get("product_id", "")).strip()
        if not image_value or not product_id:
            raise ValueError(f"Query {position} requires image and product_id.")
        if product_id not in product_categories:
            raise ValueError(f"Query {position} uses unknown product_id: {product_id}")

        expected_category = query.get("category") or product_categories[product_id]
        if expected_category != product_categories[product_id]:
            raise ValueError(
                f"Query {position} category does not match product metadata: "
                f"{expected_category} != {product_categories[product_id]}"
            )

        image_path = (ROOT / image_value).resolve()
        if not image_path.is_file():
            raise FileNotFoundError(f"Query image not found: {image_path}")
        if image_path.is_relative_to(catalog_dir):
            raise ValueError(
                f"Query {position} points to a catalog image. Use a different "
                "photo of the same product to avoid a trivial identity test."
            )

        image_hash = file_sha256(image_path)
        if image_hash in catalog_hashes:
            raise ValueError(
                f"Query {position} is a byte-identical copy of a catalog image. "
                "Use a different photo of the same product."
            )
        if image_hash in query_hashes:
            raise ValueError(f"Query {position} duplicates another query image.")
        query_hashes.add(image_hash)
        validated.append({
            "image": image_path,
            "relative_image": image_value.replace("\\", "/"),
            "product_id": product_id,
            "category": expected_category,
            "search_category": normalize_category(query.get("search_category", "auto")),
            "sha256": image_hash,
        })
    return validated


def run(manifest_path: Path, output_path: Path) -> dict:
    metadata = CatalogMetadata(CATALOG_METADATA_FILE)
    queries = load_manifest(manifest_path, metadata)

    # Heavy model imports happen only after the manifest is proven usable.
    from backend.search_engine import SearchEngine

    engine = SearchEngine()
    records = []
    for query in queries:
        started = time.perf_counter()
        with Image.open(query["image"]) as image:
            results, routing = engine.search(
                image.copy(),
                top_k=10,
                category=query["search_category"],
                return_metadata=True,
            )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        records.append({
            "query_image": query["relative_image"],
            "query_sha256": query["sha256"],
            "expected_product_id": query["product_id"],
            "expected_category": query["category"],
            "predicted_category": routing["predicted_category"],
            "applied_category": routing["applied_category"],
            "latency_ms": elapsed_ms,
            "retrieved_product_ids": [item["product_id"] for item in results],
            "results": results,
        })

    report = {
        "evaluation_type": "exact_product_identity",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest": _display_path(manifest_path),
        "metrics": calculate_exact_product_metrics(records),
        "average_latency_ms": round(
            sum(record["latency_ms"] for record in records) / len(records),
            3,
        ),
        "queries": records,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    return report


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    try:
        report = run(args.manifest.resolve(), args.output.resolve())
    except (ValueError, FileNotFoundError, KeyError) as error:
        print(f"Evaluation cannot start: {error}", file=sys.stderr)
        raise SystemExit(2) from error
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    print(f"Saved report: {args.output.resolve()}")


if __name__ == "__main__":
    main()
