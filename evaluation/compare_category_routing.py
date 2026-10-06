"""Compare category routing using the application's original FAISS index.

Loads SigLIP2 query encoding from the application, with fresh inference and
the same preprocessing. It never writes/rebuilds the active index or telemetry.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
from PIL import Image

from backend.catalog_config import ROOT
from backend.category_routing import predict_category
from evaluation.audit_evidence import sha256_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation/results/category_routing_comparison.json")
    args = parser.parse_args()
    from backend.search_engine import SearchEngine, INDEX_FILE, PATHS_FILE, MODEL_DIR
    engine = SearchEngine()
    if engine.index is None:
        raise ValueError("A valid original index is required; this command never rebuilds it.")
    gallery_labels = [engine.catalog_metadata.get(path)["category_key"] for path in engine.image_paths]
    labels_array = np.asarray(gallery_labels)
    suites = {}
    for split in ("validation", "test"):
        folder = ROOT / "datasets/clothing_small" / split
        paths = sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in {".jpg", ".png", ".jpeg", ".webp", ".bmp"})
        if not paths:
            raise ValueError(f"Missing query split: {split}")
        records = []
        for start in range(0, len(paths), 8):
            batch = paths[start:start + 8]
            images = []
            for path in batch:
                with Image.open(path) as image:
                    images.append(image.copy())
            vectors = engine._encode_images(images)
            for path, vector in zip(batch, vectors):
                truth = path.parent.name
                prediction = predict_category(vector, engine.catalog_vectors, engine.image_paths, gallery_labels)
                # Same exact inner-product ordering and category filter as SearchEngine.
                scores, ids = engine.index.search(np.asarray(vector, dtype="float32").reshape(1, -1), engine.index.ntotal)
                ranked = [int(i) for i in ids[0] if i >= 0]
                first = ranked[0]
                filtered = next(i for i in ranked if labels_array[i] == prediction["category"])
                records.append({
                    "image": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path),
                    "truth": truth, "unrestricted_prediction": gallery_labels[first],
                    "auto_prediction": gallery_labels[filtered],
                    "confidence": prediction["confidence"], "margin": prediction["margin"],
                    "unrestricted_correct": truth == gallery_labels[first],
                    "auto_correct": truth == gallery_labels[filtered],
                })
            print(f"{split}: {min(start + 8, len(paths))}/{len(paths)}", flush=True)
        from evaluation.compare_safe_crop_catalog import paired_top1_statistics
        unrestricted = np.asarray([r["unrestricted_correct"] for r in records])
        auto = np.asarray([r["auto_correct"] for r in records])
        suites[split] = {
            "query_count": len(records),
            "unrestricted_top1": float(unrestricted.mean()), "auto_top1": float(auto.mean()),
            "auto_vs_unrestricted": paired_top1_statistics(unrestricted, auto),
            "records": records,
        }
    report = {
        "schema_version": "1.0", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_scope": "fresh_category_level_query_inference_against_current_original_index",
        "protocol": {"gallery_count": engine.index.ntotal, "preprocessing": "application_SearchEngine",
                     "threshold_tuned": False, "production_behavior_changed": False},
        "artifacts": {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in [INDEX_FILE, PATHS_FILE, MODEL_DIR / "config.json", MODEL_DIR / "model.safetensors"]},
        "suites": suites,
        "limitations": ["Category correctness does not establish exact product identity.",
                        "The existing catalog vectors are reused; query vectors are freshly encoded.",
                        "Multi-product and real-user photos require a separate evaluation."],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for split, suite in suites.items():
        print(f"{split}: unrestricted={suite['unrestricted_top1']:.4f}, auto={suite['auto_top1']:.4f}")
    print(f"Report: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
