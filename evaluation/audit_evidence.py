"""Audit saved evaluation evidence without loading models or rewriting results.

This verifies artifact consistency and byte-level split overlap. It does not
rerun inference or certify the provenance of unsigned historical caches.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "evaluation/results"
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def paired_csv_summary(rows: list[dict], baseline: str, candidate: str) -> dict:
    if not rows:
        raise ValueError("Paired query CSV is empty.")
    def boolean(value):
        if value not in {"True", "False"}:
            raise ValueError(f"Invalid correctness value: {value}")
        return value == "True"
    pairs = [(boolean(row[baseline]), boolean(row[candidate])) for row in rows]
    return {
        "query_count": len(pairs),
        "baseline_top1": sum(a for a, _ in pairs) / len(pairs),
        "candidate_top1": sum(b for _, b in pairs) / len(pairs),
        "improved": sum(not a and b for a, b in pairs),
        "worsened": sum(a and not b for a, b in pairs),
        "unchanged": sum(a == b for a, b in pairs),
    }


def run() -> dict:
    checks, artifacts, issues = [], [], []
    def read_json(path):
        artifacts.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path)})
        return json.loads(path.read_text(encoding="utf-8"))
    def check(name, actual, expected, tolerance=1e-6):
        valid = abs(actual - expected) <= tolerance
        checks.append({"name": name, "passed": valid, "actual": actual, "expected": expected})
        if not valid:
            issues.append(name)

    baseline = read_json(ROOT / "data/baseline_metrics.json")
    final = read_json(RESULTS / "FINAL_TEST_RESULTS.json")
    validation = read_json(RESULTS / "sam2_vs_full.json")
    safe = read_json(RESULTS / "safe_crop_catalog_ab.json")
    for key in ("p_at_1", "p_at_5", "p_at_10", "map_at_10", "mrr_at_10"):
        source_key = key.replace("p_at_", "precision_at_") if key.startswith("p_at_") else key
        check(f"baseline_clean_{key}", baseline["clean_test"][key], final["clean_test"][source_key])
    multi = baseline["multi_product_synthetic"]
    check("baseline_full_top1", multi["full_image_p_at_1"], final["multi_product_full_image"]["precision_at_1"])
    check("baseline_sam2_top1", multi["sam2_p_at_1"], final["multi_product_sam2"]["precision_at_1"])
    check("baseline_multi_count", multi["queries"], final["protocol"]["multi_product_query_count"])
    for key in ("improved", "worsened", "unchanged"):
        check(f"baseline_{key}", multi[key], final["sam2_effect"][f"{key}_queries"])

    csv_path = RESULTS / "sam2_vs_full_queries.csv"
    artifacts.append({"path": csv_path.relative_to(ROOT).as_posix(), "sha256": sha256_file(csv_path)})
    with csv_path.open(encoding="utf-8", newline="") as stream:
        pairs = paired_csv_summary(list(csv.DictReader(stream)), "full_correct", "selected_correct")
    check("validation_count", pairs["query_count"], validation["sam2_success_count"])
    check("validation_full_top1", pairs["baseline_top1"], validation["full_image"]["precision_at_1"])
    check("validation_sam2_top1", pairs["candidate_top1"], validation["sam2_selected"]["precision_at_1"])
    for key in ("improved", "worsened", "unchanged"):
        check(f"validation_{key}", pairs[key], validation[f"{key}_queries"])
    for name, suite in safe["suites"].items():
        path = ROOT / suite["query_details_csv"]
        artifacts.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path)})
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        for variant in ("safe_crop", "hybrid"):
            summary = paired_csv_summary(rows, "original_correct", f"{variant}_correct")
            check(f"{name}_{variant}_count", summary["query_count"], suite["query_count"])
            check(f"{name}_{variant}_original", summary["baseline_top1"], suite["original"]["precision_at_1"])
            check(f"{name}_{variant}_top1", summary["candidate_top1"], suite[variant]["precision_at_1"])
            for key in ("improved", "worsened", "unchanged"):
                check(f"{name}_{variant}_{key}", summary[key], suite[f"{variant}_vs_original"][f"{key}_queries"])

    split_hashes, splits = {}, {}
    for split in ("train", "validation", "test"):
        folder = ROOT / "datasets/clothing_small" / split
        paths = sorted(p for p in folder.rglob("*") if p.suffix.lower() in EXTENSIONS and p.is_file())
        if not folder.is_dir() or not paths:
            issues.append(f"Missing dataset split: {split}")
        split_hashes[split] = {}
        for path in paths:
            split_hashes[split].setdefault(sha256_file(path), []).append(path.relative_to(ROOT).as_posix())
        splits[split] = {"image_count": len(paths), "unique_byte_hashes": len(split_hashes[split])}
    for split, expected in (("train", final["protocol"]["gallery_count"]), ("test", final["protocol"]["test_query_count"])):
        check(f"{split}_count", splits[split]["image_count"], expected)
    overlaps = []
    for first, second in (("train", "validation"), ("train", "test"), ("validation", "test")):
        shared = sorted(split_hashes[first].keys() & split_hashes[second].keys())
        overlaps.append({"splits": [first, second], "shared_byte_hash_count": len(shared), "examples": [
            {first: split_hashes[first][key], second: split_hashes[second][key]} for key in shared[:10]
        ]})
        if shared:
            issues.append(f"Byte-identical images across {first}/{second}")
    return {
        "schema_version": "1.0",
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "saved_artifact_consistency_and_current_byte_level_split_audit_not_fresh_inference",
        "passed": not issues,
        "checks": checks,
        "issues": issues,
        "dataset_splits": splits,
        "cross_split_overlap": overlaps,
        "artifacts": artifacts,
        "limitations": [
            "Historical final/validation results have no model, code, or input-content fingerprints from their original runs.",
            "Legacy final_test.py/compare_sam2.py reuse caches by existence and do not explicitly apply application square preprocessing.",
            "Safe-crop results use application preprocessing; different results must not be presented as one run.",
            "Byte hashing does not detect resized/re-encoded duplicates or the same product in different photos.",
            "Metrics measure category relevance, not exact product identity; no new inference was run by this audit.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RESULTS / "evidence_audit.json")
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Evidence audit: {'PASS' if report['passed'] else 'FAIL'}; checks={len(report['checks'])}")
    print(f"Report: {args.output.resolve()}")
    for issue in report["issues"]:
        print(f"Issue: {issue}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
