"""Offline appearance reranking probe; never changes the app or its index.

This is a qualitative probe, not an accuracy benchmark. Catalog backgrounds
are not segmented, and gradient histograms are only a coarse texture proxy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
import requests

from backend.catalog_config import CATALOG_DIR, ROOT


def appearance(path: Path) -> tuple[np.ndarray, np.ndarray, int]:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
        image.thumbnail((192, 192))
        rgba = np.asarray(image)
        rgb = rgba[..., :3].astype(float) / 255
        # Reject transparent and almost-white pixels; other backgrounds remain.
        valid = (rgba[..., 3] > 128) & ~(rgba[..., :3].min(axis=2) > 245)
        if valid.sum() < 16:
            raise ValueError(f"Insufficient visible pixels: {path}")
        hsv = np.asarray(image.convert("RGB").convert("HSV"), dtype=float) / 256
        color = np.histogramdd(hsv[valid], bins=(12, 4, 4), range=((0, 1),) * 3)[0].ravel()
        gray = rgb @ np.array([.299, .587, .114])
        dy, dx = np.gradient(gray)
        magnitude = np.hypot(dx, dy)
        # Exclude silhouette/alpha boundaries so they do not dominate texture.
        interior = valid.copy()
        interior[1:-1, 1:-1] &= (valid[:-2, 1:-1] & valid[2:, 1:-1]
                                & valid[1:-1, :-2] & valid[1:-1, 2:])
        interior[[0, -1], :] = False
        interior[:, [0, -1]] = False
        orientation = np.arctan2(dy, dx) % np.pi
        directions = np.histogram(orientation[interior], bins=8, range=(0, np.pi),
                                  weights=magnitude[interior])[0]
        strengths = np.histogram(magnitude[interior], bins=[0, .01, .03, .06, .12, .25, 2])[0]
        def unit_hist(values):
            return np.sqrt(values / max(float(values.sum()), 1))
        texture = np.concatenate([unit_hist(directions), unit_hist(strengths)]) / np.sqrt(2)
        return unit_hist(color), texture, int(valid.sum())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation/cache/appearance_probe/report.json")
    parser.add_argument("--url", default="http://127.0.0.1:8001", help="Local development API")
    args = parser.parse_args()
    from urllib.parse import urlparse
    if urlparse(args.url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Only a local development server is supported")
    query = args.query.resolve()
    query_bytes = query.read_bytes()
    # API uses the current model/preprocessing. This request creates ordinary
    # search telemetry but does not submit feedback or change the browser.
    response = requests.post(args.url.rstrip("/") + "/api/search", params={"top_k": 50},
                             data={"category": "auto", "search_mode": "ai"},
                             files={"image": (query.name, query_bytes, "image/png")}, timeout=90)
    response.raise_for_status()
    payload = response.json()
    results = payload["results"]
    qc, qt, count = appearance(query)
    rows = []
    for rank, item in enumerate(results, 1):
        path = (CATALOG_DIR / item["image"]).resolve()
        if not path.is_relative_to(CATALOG_DIR.resolve()):
            raise ValueError("Candidate escaped catalog directory")
        color, texture, _ = appearance(path)
        rows.append({"baseline_rank": rank, "title": item["title"], "image": item["image"],
                     "semantic": float(item["score"]), "color": float(qc @ color),
                     "texture_proxy": float(qt @ texture)})
    trials = []
    # Declared exploratory weights, no automatic tuning or production selection.
    for wc, wt in [(0, 0), (.1, 0), (.2, 0), (.1, .1), (.2, .1)]:
        ranked = sorted(rows, key=lambda row: (1-wc-wt)*row["semantic"] + wc*row["color"]
                        + wt*row["texture_proxy"], reverse=True)
        trials.append({"color_weight": wc, "texture_weight": wt,
                       "ranking": [dict(row, rank=i) for i, row in enumerate(ranked, 1)]})
    report = {"scope": "single_user_selected_query_qualitative_probe",
              "query": str(query), "query_sha256": hashlib.sha256(query_bytes).hexdigest(),
              "visible_pixels": count, "candidate_count": len(rows),
              "production_behavior_changed": False, "api_query": payload.get("query"),
              "limitations": ["No human relevance labels or aggregate accuracy measured.",
                              "Catalog backgrounds can dominate color histograms.",
                              "Gradient histograms do not identify clothing patterns.",
                              "Only the original top 50 candidates can be reordered.",
                              "Weights are exploratory and must not be tuned on held-out test examples."],
              "trials": trials}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for trial in trials:
        print(trial["color_weight"], trial["texture_weight"],
              [(r["title"], r["rank"]) for r in trial["ranking"][:8]])
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
