"""Category-aware routing for visual catalog search."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np


CATEGORY_LABELS = {
    "dress": "فساتين",
    "hat": "قبعات",
    "longsleeve": "ملابس بأكمام طويلة",
    "outwear": "جاكيتات وملابس خارجية",
    "pants": "بناطيل",
    "shirt": "قمصان",
    "shoes": "أحذية",
    "shorts": "سراويل قصيرة",
    "skirt": "تنانير",
    "t-shirt": "تيشيرتات",
}

CATEGORY_ALIASES = {
    "outerwear": "outwear",
    "shoe": "shoes",
}


def normalize_category(value: str | None) -> str:
    normalized = (value or "auto").strip().lower()
    normalized = CATEGORY_ALIASES.get(normalized, normalized)
    allowed = {"auto", "all", *CATEGORY_LABELS}
    if normalized not in allowed:
        raise ValueError(f"Unsupported category: {value}")
    return normalized


def category_from_path(image_path: str) -> str | None:
    """Read the category prefix used by the current catalog filenames."""

    filename = Path(image_path).name.lower()
    prefix = filename.split("_", 1)[0]
    prefix = CATEGORY_ALIASES.get(prefix, prefix)
    return prefix if prefix in CATEGORY_LABELS else None


def predict_category(
    query_vector: np.ndarray,
    catalog_vectors: np.ndarray,
    image_paths: list[str],
    category_keys: list[str | None] | None = None,
) -> dict:
    """Classify a query against normalized category centroids.

    This uses only the indexed catalog embeddings, so it does not introduce a
    second model or require internet access. The confidence is a probability
    over the categories present in the current catalog, not a universal claim.
    """

    if len(catalog_vectors) != len(image_paths):
        raise ValueError("Catalog vectors and image paths have different sizes.")
    if category_keys is not None and len(category_keys) != len(image_paths):
        raise ValueError("Category keys and image paths have different sizes.")

    grouped: dict[str, list[np.ndarray]] = defaultdict(list)
    for position, (vector, image_path) in enumerate(zip(catalog_vectors, image_paths)):
        category = (
            category_keys[position]
            if category_keys is not None
            else category_from_path(image_path)
        )
        if category:
            grouped[category].append(vector)

    if not grouped:
        return {
            "category": None,
            "label": None,
            "confidence": 0.0,
            "margin": 0.0,
            "scores": {},
        }

    query = np.asarray(query_vector, dtype="float32").reshape(-1)
    query_norm = np.linalg.norm(query)
    if query_norm == 0:
        raise ValueError("Query embedding cannot be a zero vector.")
    query = query / query_norm

    categories = sorted(grouped)
    cosine_scores = []
    for category in categories:
        centroid = np.mean(np.vstack(grouped[category]), axis=0)
        centroid_norm = np.linalg.norm(centroid)
        if centroid_norm == 0:
            cosine_scores.append(-1.0)
        else:
            cosine_scores.append(float(np.dot(query, centroid / centroid_norm)))

    scores_array = np.asarray(cosine_scores, dtype="float64")
    logits = (scores_array - scores_array.max()) / 0.07
    probabilities = np.exp(logits)
    probabilities /= probabilities.sum()

    order = np.argsort(probabilities)[::-1]
    best_index = int(order[0])
    second_probability = float(probabilities[order[1]]) if len(order) > 1 else 0.0
    best_category = categories[best_index]

    return {
        "category": best_category,
        "label": CATEGORY_LABELS[best_category],
        "confidence": round(float(probabilities[best_index]), 6),
        "margin": round(float(probabilities[best_index]) - second_probability, 6),
        "scores": {
            category: round(float(probability), 6)
            for category, probability in zip(categories, probabilities)
        },
    }
