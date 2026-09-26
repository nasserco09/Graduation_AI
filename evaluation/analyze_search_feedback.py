"""Export an inspectable summary of real search feedback."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from backend.search_observability import SearchObservability


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE = ROOT / "data" / "search_observability.db"
DEFAULT_JSON = ROOT / "evaluation" / "results" / "search_feedback_analysis.json"
DEFAULT_CSV = ROOT / "evaluation" / "results" / "search_feedback_failures.csv"


def run(database: Path, json_output: Path, csv_output: Path) -> dict:
    store = SearchObservability(database)
    failures = store.failure_cases(limit=1000)
    report = {
        "analysis_type": "real_search_feedback",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": store.summary(),
        "failure_count": len(failures),
        "failures": failures,
    }

    json_output.parent.mkdir(parents=True, exist_ok=True)
    with json_output.open("w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)

    columns = [
        "search_id",
        "created_at_utc",
        "search_mode",
        "requested_category",
        "predicted_category",
        "applied_category",
        "category_confidence",
        "verdict",
        "corrected_category",
        "top_product_id",
        "top_similarity",
        "latency_ms",
        "result_product_ids",
        "notes",
    ]
    with csv_output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for failure in failures:
            row = dict(failure)
            row["result_product_ids"] = " | ".join(row.get("result_product_ids", []))
            writer.writerow(row)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()

    report = run(
        args.database.resolve(),
        args.json_output.resolve(),
        args.csv_output.resolve(),
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Failure cases: {report['failure_count']}")
    print(f"JSON report: {args.json_output.resolve()}")
    print(f"CSV failures: {args.csv_output.resolve()}")


if __name__ == "__main__":
    main()
