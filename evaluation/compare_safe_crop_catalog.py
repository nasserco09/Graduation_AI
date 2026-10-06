"""Compare original, safe-crop, and validation-tuned hybrid catalogs.

This is a paired A/B experiment.  The hybrid weight is chosen on the
validation split and frozen before the test split is evaluated.  All files are
written under experimental paths; the application's active index is untouched.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from collections import Counter

import numpy as np

from backend.catalog_config import CATALOG_DIR, CATALOG_METADATA_FILE, DATA_DIR, ROOT
from backend.catalog_metadata import CatalogMetadata
from backend.image_preprocessing import PREPROCESSING_VERSION, preprocess_image
from tools.build_safe_catalog_crops import (
    DEFAULT_OUTPUT_DIR,
    FULL_CROP_VERSION,
    sha256_file,
    write_json_atomic,
)


CACHE_DIR = ROOT / "evaluation" / "cache" / "safe_crop_catalog_ab_v1"
RESULTS_DIR = ROOT / "evaluation" / "results"
EXPERIMENT_INDEX_DIR = DATA_DIR / "experiments" / "safe_crop_catalog_v1"
DEFAULT_RESULT = RESULTS_DIR / "safe_crop_catalog_ab.json"
TOP_K = 10
BOOTSTRAP_SAMPLES = 10_000
RANDOM_SEED = 42
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "manifest.json",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULT)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument(
        "--force-encode",
        action="store_true",
        help="Ignore valid embedding caches and encode every image again.",
    )
    return parser.parse_args()


def content_signature(paths: list[Path], *, prefix: str) -> str:
    digest = hashlib.sha256(prefix.encode("utf-8"))
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(sha256_file(path).encode("ascii"))
    return digest.hexdigest()


def _load_manifest(manifest_path: Path) -> tuple[dict, list[Path], list[Path], list[str]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "1.0":
        raise ValueError("Unsupported safe-crop manifest schema.")
    if manifest.get("crop_version") != FULL_CROP_VERSION:
        raise ValueError("Safe-crop manifest belongs to another algorithm version.")
    if not manifest.get("complete_catalog"):
        raise ValueError("Safe-crop manifest is partial; process all catalog images first.")
    if manifest.get("active_index_changed") is not False:
        raise ValueError("Manifest does not prove that the active index stayed unchanged.")

    metadata = CatalogMetadata(CATALOG_METADATA_FILE)
    if manifest.get("metadata_checksum") != metadata.checksum():
        raise ValueError("Catalog metadata changed after safe crops were generated.")

    item_map = {str(item.get("image")): item for item in manifest.get("items", [])}
    original_paths = sorted(
        path
        for path in CATALOG_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    image_keys = [path.relative_to(CATALOG_DIR).as_posix() for path in original_paths]
    if len(original_paths) != manifest.get("expected_catalog_count"):
        raise ValueError("Current source catalog does not match the complete manifest.")

    safe_paths = []
    labels = []
    manifest_root = manifest_path.parent
    for source_path, image_key in zip(original_paths, image_keys):
        record = item_map[image_key]
        if sha256_file(source_path) != record.get("source_sha256"):
            raise ValueError(f"Source catalog image changed: {image_key}")
        safe_path = manifest_root / record["content_crop"]["path"]
        if not safe_path.is_file():
            raise FileNotFoundError(f"Safe crop is missing: {safe_path}")
        if sha256_file(safe_path) != record.get("output_sha256"):
            raise ValueError(f"Safe-crop checksum failed: {image_key}")
        safe_paths.append(safe_path)
        labels.append(metadata.get(image_key)["category_key"])

    if image_keys != sorted(item_map):
        raise ValueError("Manifest image mapping does not exactly match the catalog.")
    return manifest, original_paths, safe_paths, labels


def _app_transform(image):
    return preprocess_image(image)[0]


def load_or_encode(
    adapter,
    cache_path: Path,
    paths: list[Path],
    labels: list[str],
    *,
    signature: str,
    batch_size: int,
    force: bool,
) -> tuple[np.ndarray, bool]:
    if cache_path.is_file() and not force:
        try:
            data = np.load(cache_path, allow_pickle=False)
            cached_signature = str(data["signature"].item())
            cached_labels = list(data["labels"])
            cached_vectors = data["vectors"].astype("float32")
            if (
                cached_signature == signature
                and cached_labels == labels
                and cached_vectors.ndim == 2
                and cached_vectors.shape[0] == len(paths)
                and np.isfinite(cached_vectors).all()
            ):
                return cached_vectors, True
        except (OSError, ValueError, KeyError):
            pass

    vectors = adapter.encode_paths(
        paths,
        batch_size=batch_size,
        image_transform=_app_transform,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        cache_path,
        vectors=vectors.astype("float32"),
        labels=np.asarray(labels),
        signature=np.asarray(signature),
    )
    return vectors.astype("float32"), False


def rank_score_matrix(
    query_vectors: np.ndarray,
    gallery_vectors: np.ndarray,
    *,
    top_k: int = TOP_K,
) -> tuple[np.ndarray, np.ndarray]:
    scores = np.asarray(query_vectors @ gallery_vectors.T, dtype="float32")
    k = min(top_k, scores.shape[1])
    candidates = np.argpartition(-scores, kth=k - 1, axis=1)[:, :k]
    candidate_scores = np.take_along_axis(scores, candidates, axis=1)
    order = np.argsort(-candidate_scores, axis=1, kind="stable")
    ids = np.take_along_axis(candidates, order, axis=1)
    ranked_scores = np.take_along_axis(scores, ids, axis=1)
    return ranked_scores, ids


def _average_precision_at_k(
    retrieved_labels: list[str],
    query_label: str,
    k: int,
    relevant_in_gallery: int,
) -> float:
    hits = 0
    precision_sum = 0.0
    for rank, label in enumerate(retrieved_labels[:k], start=1):
        if label == query_label:
            hits += 1
            precision_sum += hits / rank
    denominator = min(relevant_in_gallery, k)
    return 0.0 if denominator == 0 else precision_sum / denominator


def calculate_category_metrics(
    query_labels: list[str],
    retrieved_labels: list[list[str]],
    gallery_labels: list[str],
) -> dict:
    """Match the project's existing category-level metric definitions."""

    metrics = {}
    gallery_counts = Counter(gallery_labels)
    for k in (1, 5, 10):
        precisions = []
        hits = []
        for truth, results in zip(query_labels, retrieved_labels):
            relevant = sum(label == truth for label in results[:k])
            precisions.append(relevant / k)
            hits.append(float(relevant > 0))
        metrics[f"precision_at_{k}"] = float(np.mean(precisions))
        metrics[f"hit_at_{k}"] = float(np.mean(hits))

    reciprocal_ranks = []
    average_precisions = []
    for truth, results in zip(query_labels, retrieved_labels):
        rank = next(
            (position for position, label in enumerate(results[:10], start=1) if label == truth),
            None,
        )
        reciprocal_ranks.append(0.0 if rank is None else 1.0 / rank)
        average_precisions.append(
            _average_precision_at_k(results, truth, 10, gallery_counts[truth])
        )
    metrics["mrr_at_10"] = float(np.mean(reciprocal_ranks))
    metrics["map_at_10"] = float(np.mean(average_precisions))
    metrics["query_count"] = len(query_labels)
    return metrics


def evaluate_scores(
    score_matrix: np.ndarray,
    query_labels: list[str],
    gallery_labels: list[str],
) -> dict:
    k = min(TOP_K, score_matrix.shape[1])
    candidates = np.argpartition(-score_matrix, kth=k - 1, axis=1)[:, :k]
    candidate_scores = np.take_along_axis(score_matrix, candidates, axis=1)
    order = np.argsort(-candidate_scores, axis=1, kind="stable")
    ids = np.take_along_axis(candidates, order, axis=1)
    scores = np.take_along_axis(score_matrix, ids, axis=1)
    retrieved_labels = [
        [gallery_labels[int(index)] for index in row]
        for row in ids
    ]
    metrics = calculate_category_metrics(query_labels, retrieved_labels, gallery_labels)
    predictions = [row[0] for row in retrieved_labels]
    correct = np.asarray(
        [prediction == truth for prediction, truth in zip(predictions, query_labels)],
        dtype=bool,
    )
    return {
        "metrics": metrics,
        "predictions": predictions,
        "correct": correct,
        "ids": ids,
        "scores": scores,
    }


def paired_top1_statistics(
    baseline_correct: np.ndarray,
    candidate_correct: np.ndarray,
    *,
    bootstrap_samples: int = BOOTSTRAP_SAMPLES,
    seed: int = RANDOM_SEED,
) -> dict:
    baseline = np.asarray(baseline_correct, dtype=np.int8)
    candidate = np.asarray(candidate_correct, dtype=np.int8)
    if baseline.shape != candidate.shape or baseline.size == 0:
        raise ValueError("Paired correctness arrays must have the same non-zero size.")
    differences = candidate - baseline
    rng = np.random.default_rng(seed)
    sampled = rng.choice(differences, size=(bootstrap_samples, differences.size), replace=True)
    deltas = sampled.mean(axis=1)
    improved = int(np.sum((baseline == 0) & (candidate == 1)))
    worsened = int(np.sum((baseline == 1) & (candidate == 0)))
    discordant = improved + worsened
    if discordant:
        tail = sum(
            math.comb(discordant, value)
            for value in range(0, min(improved, worsened) + 1)
        ) / (2 ** discordant)
        mcnemar_exact_p = min(1.0, 2.0 * tail)
    else:
        mcnemar_exact_p = 1.0
    return {
        "delta_top1": round(float(differences.mean()), 6),
        "bootstrap_95_ci": [
            round(float(np.percentile(deltas, 2.5)), 6),
            round(float(np.percentile(deltas, 97.5)), 6),
        ],
        "improved_queries": improved,
        "worsened_queries": worsened,
        "unchanged_queries": int(differences.size - discordant),
        "mcnemar_exact_p": round(float(mcnemar_exact_p), 6),
    }


def select_hybrid_weight(
    original_scores: np.ndarray,
    safe_scores: np.ndarray,
    query_labels: list[str],
    gallery_labels: list[str],
) -> tuple[float, list[dict]]:
    candidates = []
    for safe_weight in np.linspace(0.0, 1.0, 11):
        combined = ((1.0 - safe_weight) * original_scores) + (safe_weight * safe_scores)
        evaluated = evaluate_scores(combined, query_labels, gallery_labels)
        metrics = evaluated["metrics"]
        candidates.append({
            "safe_weight": round(float(safe_weight), 1),
            "original_weight": round(float(1.0 - safe_weight), 1),
            "precision_at_1": round(float(metrics["precision_at_1"]), 6),
            "map_at_10": round(float(metrics["map_at_10"]), 6),
        })
    # Conservative tie-break: best P@1, then mAP, then more original weight.
    best = max(
        candidates,
        key=lambda row: (
            row["precision_at_1"],
            row["map_at_10"],
            -row["safe_weight"],
        ),
    )
    return float(best["safe_weight"]), candidates


def _metric_subset(metrics: dict) -> dict:
    return {
        key: round(float(metrics[key]), 6)
        for key in (
            "precision_at_1",
            "precision_at_5",
            "precision_at_10",
            "map_at_10",
            "mrr_at_10",
            "hit_at_1",
            "hit_at_5",
            "hit_at_10",
        )
    } | {"query_count": int(metrics["query_count"])}


def _evaluate_suite(
    name: str,
    query_vectors: np.ndarray,
    query_paths: list[Path],
    query_labels: list[str],
    gallery_labels: list[str],
    original_gallery: np.ndarray,
    safe_gallery: np.ndarray,
    safe_weight: float,
    output_dir: Path,
) -> dict:
    original_matrix = query_vectors @ original_gallery.T
    safe_matrix = query_vectors @ safe_gallery.T
    hybrid_matrix = ((1.0 - safe_weight) * original_matrix) + (safe_weight * safe_matrix)
    variants = {
        "original": evaluate_scores(original_matrix, query_labels, gallery_labels),
        "safe_crop": evaluate_scores(safe_matrix, query_labels, gallery_labels),
        "hybrid": evaluate_scores(hybrid_matrix, query_labels, gallery_labels),
    }

    csv_path = output_dir / f"safe_crop_catalog_ab_{name}_queries.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "query",
                "true_category",
                "original_prediction",
                "safe_crop_prediction",
                "hybrid_prediction",
                "original_correct",
                "safe_crop_correct",
                "hybrid_correct",
            ],
        )
        writer.writeheader()
        for index, query_path in enumerate(query_paths):
            writer.writerow({
                "query": str(query_path),
                "true_category": query_labels[index],
                "original_prediction": variants["original"]["predictions"][index],
                "safe_crop_prediction": variants["safe_crop"]["predictions"][index],
                "hybrid_prediction": variants["hybrid"]["predictions"][index],
                "original_correct": bool(variants["original"]["correct"][index]),
                "safe_crop_correct": bool(variants["safe_crop"]["correct"][index]),
                "hybrid_correct": bool(variants["hybrid"]["correct"][index]),
            })

    return {
        "query_count": len(query_paths),
        "original": _metric_subset(variants["original"]["metrics"]),
        "safe_crop": _metric_subset(variants["safe_crop"]["metrics"]),
        "hybrid": _metric_subset(variants["hybrid"]["metrics"]),
        "safe_crop_vs_original": paired_top1_statistics(
            variants["original"]["correct"],
            variants["safe_crop"]["correct"],
        ),
        "hybrid_vs_original": paired_top1_statistics(
            variants["original"]["correct"],
            variants["hybrid"]["correct"],
        ),
        "query_details_csv": str(csv_path.relative_to(ROOT)),
    }


def _optional_final_test_queries(folder_name: str) -> tuple[list[Path], list[str]]:
    root = ROOT / "evaluation" / "cache" / "final_test" / folder_name
    paths = sorted(path for path in root.glob("*") if path.is_file())
    labels = []
    for path in paths:
        stem_parts = path.stem.split("_", 1)
        if len(stem_parts) != 2:
            return [], []
        labels.append(stem_parts[1])
    return paths, labels


def _save_experimental_index(
    vectors: np.ndarray,
    original_paths: list[Path],
    safe_paths: list[Path],
    manifest: dict,
) -> tuple[Path, Path]:
    import faiss

    EXPERIMENT_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    index_path = EXPERIMENT_INDEX_DIR / "catalog_safe_crop_siglip2.faiss"
    mapping_path = EXPERIMENT_INDEX_DIR / "catalog_safe_crop_siglip2_paths.json"
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(np.asarray(vectors, dtype="float32"))
    temporary_index = index_path.with_suffix(index_path.suffix + ".tmp")
    faiss.write_index(index, str(temporary_index))
    temporary_index.replace(index_path)
    write_json_atomic(mapping_path, {
        "schema_version": "1.0",
        "experimental": True,
        "active_index": False,
        "model": "siglip2_base",
        "preprocessing_version": PREPROCESSING_VERSION,
        "crop_version": FULL_CROP_VERSION,
        "image_count": len(original_paths),
        "embedding_dimension": int(vectors.shape[1]),
        "source_catalog_checksum": manifest["source_catalog_checksum"],
        "safe_crop_checksum": manifest["safe_crop_checksum"],
        "paths": [path.relative_to(CATALOG_DIR).as_posix() for path in original_paths],
        "safe_crop_paths": [str(path) for path in safe_paths],
    })
    return index_path, mapping_path


def main() -> int:
    args = parse_args()
    if args.batch_size < 1:
        raise ValueError("--batch-size must be at least 1.")
    from evaluation.benchmark import discover_split
    from evaluation.model_adapters import create_adapter

    manifest_path = args.manifest.resolve()
    manifest, original_paths, safe_paths, gallery_labels = _load_manifest(manifest_path)

    validation_paths, validation_labels = discover_split("validation")
    test_paths, test_labels = discover_split("test")
    adapter = create_adapter("siglip2")

    common_prefix = f"siglip2|{PREPROCESSING_VERSION}|"
    original_signature = (
        common_prefix + "original|" + manifest["source_catalog_checksum"]
    )
    safe_signature = common_prefix + "safe|" + manifest["safe_crop_checksum"]
    original_gallery, original_cached = load_or_encode(
        adapter,
        CACHE_DIR / "gallery_original.npz",
        original_paths,
        gallery_labels,
        signature=original_signature,
        batch_size=args.batch_size,
        force=args.force_encode,
    )
    safe_gallery, safe_cached = load_or_encode(
        adapter,
        CACHE_DIR / "gallery_safe_crop.npz",
        safe_paths,
        gallery_labels,
        signature=safe_signature,
        batch_size=args.batch_size,
        force=args.force_encode,
    )

    def encode_queries(name: str, paths: list[Path], labels: list[str]) -> tuple[np.ndarray, bool]:
        signature = content_signature(paths, prefix=common_prefix + name)
        return load_or_encode(
            adapter,
            CACHE_DIR / f"queries_{name}.npz",
            paths,
            labels,
            signature=signature,
            batch_size=args.batch_size,
            force=args.force_encode,
        )

    validation_vectors, validation_cached = encode_queries(
        "validation", validation_paths, validation_labels
    )
    validation_original_scores = validation_vectors @ original_gallery.T
    validation_safe_scores = validation_vectors @ safe_gallery.T
    safe_weight, weight_search = select_hybrid_weight(
        validation_original_scores,
        validation_safe_scores,
        validation_labels,
        gallery_labels,
    )

    output_path = args.output.resolve()
    suites = {}
    test_vectors, test_cached = encode_queries("clean_test", test_paths, test_labels)
    suites["clean_test"] = _evaluate_suite(
        "clean_test",
        test_vectors,
        test_paths,
        test_labels,
        gallery_labels,
        original_gallery,
        safe_gallery,
        safe_weight,
        output_path.parent,
    )

    optional_cache_status = {}
    for suite_name, folder_name in (
        ("multi_product_full", "composites"),
        ("multi_product_selected", "cutouts"),
    ):
        paths, labels = _optional_final_test_queries(folder_name)
        if not paths:
            continue
        vectors, was_cached = encode_queries(suite_name, paths, labels)
        optional_cache_status[suite_name] = was_cached
        suites[suite_name] = _evaluate_suite(
            suite_name,
            vectors,
            paths,
            labels,
            gallery_labels,
            original_gallery,
            safe_gallery,
            safe_weight,
            output_path.parent,
        )

    adapter.cleanup()
    index_path, mapping_path = _save_experimental_index(
        safe_gallery,
        original_paths,
        safe_paths,
        manifest,
    )

    primary_name = (
        "multi_product_selected"
        if "multi_product_selected" in suites
        else "clean_test"
    )
    primary = suites[primary_name]["hybrid_vs_original"]
    ci_lower = primary["bootstrap_95_ci"][0]
    supported_gain = (
        primary["delta_top1"] > 0
        and ci_lower > 0
        and primary["mcnemar_exact_p"] < 0.05
    )
    report = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "original_vs_safe_crop_vs_validation_tuned_hybrid",
        "evidence_scope": "category_level_retrieval_not_exact_product_identity",
        "protocol": {
            "gallery_count": len(original_paths),
            "validation_split_usage": "hybrid_weight_selection_only",
            "test_split_usage": "final_comparison_only",
            "hybrid_safe_weight": safe_weight,
            "hybrid_original_weight": round(1.0 - safe_weight, 1),
            "hybrid_weight_candidates": weight_search,
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "random_seed": RANDOM_SEED,
            "preprocessing_version": PREPROCESSING_VERSION,
            "crop_version": FULL_CROP_VERSION,
        },
        "cache_reused": {
            "gallery_original": original_cached,
            "gallery_safe_crop": safe_cached,
            "validation_queries": validation_cached,
            "clean_test_queries": test_cached,
            **optional_cache_status,
        },
        "suites": suites,
        "decision": {
            "primary_suite": primary_name,
            "statistically_supported_hybrid_gain": supported_gain,
            "production_switch_authorized": False,
            "recommended_next_action": (
                "collect_exact_product_queries_then_confirm_candidate"
                if supported_gain
                else "keep_original_and_review_paired_failures_before_any_switch"
            ),
            "reason": (
                "Category-level evidence supports the hybrid candidate, but exact-product "
                "identity evidence is still required before changing production."
                if supported_gain
                else "The paired held-out evidence does not yet prove a hybrid improvement."
            ),
        },
        "experimental_index": {
            "active_index_changed": False,
            "faiss": str(index_path.relative_to(ROOT)),
            "mapping": str(mapping_path.relative_to(ROOT)),
        },
    }
    write_json_atomic(output_path, report)

    print()
    print("SAFE-CROP CATALOG A/B COMPLETE")
    print(f"Hybrid weights: original={1.0 - safe_weight:.1f}, safe={safe_weight:.1f}")
    for name, suite in suites.items():
        print(
            f"{name}: original P@1={suite['original']['precision_at_1']:.4f}, "
            f"safe P@1={suite['safe_crop']['precision_at_1']:.4f}, "
            f"hybrid P@1={suite['hybrid']['precision_at_1']:.4f}"
        )
    print(f"Report: {output_path}")
    print(f"Experimental index: {index_path}")
    print("The application active index was not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
