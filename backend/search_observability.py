"""Privacy-conscious local search logging and user feedback storage."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from backend.category_routing import CATEGORY_LABELS


FEEDBACK_VERDICTS = {
    "correct",
    "no_match",
    "wrong_category",
    "bad_selection",
}


class SearchObservability:
    def __init__(self, database_file: Path):
        self.database_file = database_file
        self.database_file.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.database_file, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self):
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS search_events (
                    search_id TEXT PRIMARY KEY,
                    created_at_utc TEXT NOT NULL,
                    query_sha256 TEXT NOT NULL,
                    search_mode TEXT NOT NULL,
                    requested_category TEXT NOT NULL,
                    predicted_category TEXT,
                    applied_category TEXT,
                    category_confidence REAL NOT NULL,
                    top_k INTEGER NOT NULL,
                    result_count INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    top_product_id TEXT,
                    top_similarity REAL,
                    result_product_ids_json TEXT NOT NULL,
                    result_scores_json TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    preprocessing_version TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS search_feedback (
                    feedback_id TEXT PRIMARY KEY,
                    search_id TEXT NOT NULL UNIQUE,
                    created_at_utc TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    selected_product_id TEXT,
                    corrected_category TEXT,
                    notes TEXT,
                    FOREIGN KEY (search_id) REFERENCES search_events(search_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_search_events_created
                    ON search_events(created_at_utc);
                CREATE INDEX IF NOT EXISTS idx_search_feedback_verdict
                    ON search_feedback(verdict);
                """
            )

    @staticmethod
    def _utc_now():
        return datetime.now(timezone.utc).isoformat()

    def record_search(
        self,
        *,
        query_sha256: str,
        search_mode: str,
        routing: dict,
        top_k: int,
        results: list[dict],
        latency_ms: float,
        model_name: str,
        preprocessing_version: str,
    ) -> str:
        search_id = str(uuid4())
        top_result = results[0] if results else {}
        product_ids = [item.get("product_id") for item in results]
        scores = [round(float(item.get("similarity", 0.0)), 6) for item in results]

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO search_events (
                    search_id, created_at_utc, query_sha256, search_mode,
                    requested_category, predicted_category, applied_category,
                    category_confidence, top_k, result_count, latency_ms,
                    top_product_id, top_similarity, result_product_ids_json,
                    result_scores_json, model_name, preprocessing_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    search_id,
                    self._utc_now(),
                    query_sha256,
                    search_mode,
                    routing.get("requested_category") or "auto",
                    routing.get("predicted_category"),
                    routing.get("applied_category"),
                    float(routing.get("confidence") or 0.0),
                    int(top_k),
                    len(results),
                    round(float(latency_ms), 3),
                    top_result.get("product_id"),
                    float(top_result.get("similarity", 0.0)) if top_result else None,
                    json.dumps(product_ids, ensure_ascii=False),
                    json.dumps(scores),
                    model_name,
                    preprocessing_version,
                ),
            )
        return search_id

    def record_feedback(
        self,
        *,
        search_id: str,
        verdict: str,
        selected_product_id: str | None = None,
        corrected_category: str | None = None,
        notes: str | None = None,
    ) -> dict:
        verdict = (verdict or "").strip().lower()
        if verdict not in FEEDBACK_VERDICTS:
            raise ValueError(f"Unsupported feedback verdict: {verdict}")
        if verdict == "correct" and not selected_product_id:
            raise ValueError("Correct feedback requires selected_product_id.")
        if verdict == "wrong_category" and corrected_category not in CATEGORY_LABELS:
            raise ValueError("Wrong-category feedback requires a valid corrected category.")

        clean_notes = (notes or "").strip() or None
        if clean_notes and len(clean_notes) > 500:
            raise ValueError("Feedback notes cannot exceed 500 characters.")

        with self._connect() as connection:
            search_row = connection.execute(
                "SELECT result_product_ids_json FROM search_events WHERE search_id = ?",
                (search_id,),
            ).fetchone()
            if not search_row:
                raise KeyError("Search ID was not found.")
            returned_product_ids = json.loads(search_row["result_product_ids_json"])
            if verdict == "correct" and selected_product_id not in returned_product_ids:
                raise ValueError(
                    "The selected product was not returned by this search."
                )

            feedback_id = str(uuid4())
            created_at = self._utc_now()
            connection.execute(
                """
                INSERT INTO search_feedback (
                    feedback_id, search_id, created_at_utc, verdict,
                    selected_product_id, corrected_category, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(search_id) DO UPDATE SET
                    created_at_utc = excluded.created_at_utc,
                    verdict = excluded.verdict,
                    selected_product_id = excluded.selected_product_id,
                    corrected_category = excluded.corrected_category,
                    notes = excluded.notes
                """,
                (
                    feedback_id,
                    search_id,
                    created_at,
                    verdict,
                    selected_product_id,
                    corrected_category,
                    clean_notes,
                ),
            )

        return {
            "status": "saved",
            "search_id": search_id,
            "verdict": verdict,
            "selected_product_id": selected_product_id,
            "corrected_category": corrected_category,
        }

    def summary(self) -> dict:
        with self._connect() as connection:
            total_searches = connection.execute(
                "SELECT COUNT(*) AS count FROM search_events"
            ).fetchone()["count"]
            total_feedback = connection.execute(
                "SELECT COUNT(*) AS count FROM search_feedback"
            ).fetchone()["count"]
            verdict_rows = connection.execute(
                "SELECT verdict, COUNT(*) AS count FROM search_feedback GROUP BY verdict"
            ).fetchall()
            average_latency = connection.execute(
                "SELECT AVG(latency_ms) AS value FROM search_events"
            ).fetchone()["value"]
            mode_rows = connection.execute(
                "SELECT search_mode, COUNT(*) AS count FROM search_events GROUP BY search_mode"
            ).fetchall()
            predicted_rows = connection.execute(
                """
                SELECT predicted_category, COUNT(*) AS count
                FROM search_events
                GROUP BY predicted_category
                """
            ).fetchall()

        verdicts = {row["verdict"]: row["count"] for row in verdict_rows}
        correct_count = verdicts.get("correct", 0)
        return {
            "total_searches": total_searches,
            "feedback_count": total_feedback,
            "feedback_coverage": round(total_feedback / total_searches, 6) if total_searches else 0.0,
            "correct_match_rate": round(correct_count / total_feedback, 6) if total_feedback else None,
            "average_latency_ms": round(float(average_latency), 3) if average_latency is not None else None,
            "verdict_counts": verdicts,
            "search_mode_counts": {row["search_mode"]: row["count"] for row in mode_rows},
            "predicted_category_counts": {
                row["predicted_category"] or "unknown": row["count"]
                for row in predicted_rows
            },
            "privacy": {
                "raw_query_images_stored": False,
                "personal_identity_stored": False,
                "query_hash_stored": True,
            },
        }

    def failure_cases(self, limit: int = 100) -> list[dict]:
        safe_limit = max(1, min(int(limit), 1000))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT e.*, f.verdict, f.selected_product_id,
                       f.corrected_category, f.notes, f.created_at_utc AS feedback_at_utc
                FROM search_events e
                JOIN search_feedback f ON f.search_id = e.search_id
                WHERE f.verdict != 'correct'
                ORDER BY f.created_at_utc DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

        cases = []
        for row in rows:
            item = dict(row)
            item["result_product_ids"] = json.loads(item.pop("result_product_ids_json"))
            item["result_scores"] = json.loads(item.pop("result_scores_json"))
            item.pop("query_sha256", None)
            cases.append(item)
        return cases
