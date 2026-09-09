from pathlib import Path
import argparse
import csv
import json
import time

import faiss
import numpy as np
import torch
from collections import Counter, defaultdict

from evaluation.model_adapters import (
    create_adapter,
    normalize_numpy,
)


ROOT = Path(__file__).resolve().parent.parent

DATASET_ROOT = (
    ROOT
    / "datasets"
    / "clothing_small"
)

CACHE_ROOT = (
    ROOT
    / "evaluation"
    / "cache"
)

RESULTS_ROOT = (
    ROOT
    / "evaluation"
    / "results"
)


SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
}


ALL_MODELS = [
    "clip",
    "dinov2",
    "siglip2",
    "resnet50",
    "efficientnet_b3",
]


def discover_split(
    split_name: str
):

    split_root = (
        DATASET_ROOT
        / split_name
    )

    if not split_root.exists():

        raise FileNotFoundError(
            f"Dataset split not found: "
            f"{split_root}"
        )

    paths = []
    labels = []

    class_dirs = sorted(
        [
            path
            for path
            in split_root.iterdir()
            if path.is_dir()
        ]
    )

    for class_dir in class_dirs:

        label = class_dir.name

        images = sorted(
            [
                path
                for path
                in class_dir.rglob("*")
                if (
                    path.is_file()
                    and
                    path.suffix.lower()
                    in SUPPORTED_EXTENSIONS
                )
            ]
        )

        paths.extend(images)

        labels.extend(
            [label] * len(images)
        )

    return paths, labels


def save_embeddings(
    path: Path,
    vectors: np.ndarray,
    image_paths,
    labels
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    np.savez_compressed(
        path,
        vectors=vectors,
        paths=np.array(
            [
                str(item)
                for item in image_paths
            ]
        ),
        labels=np.array(labels)
    )


def load_embeddings(
    path: Path
):

    data = np.load(
        path,
        allow_pickle=False
    )

    return (
        data["vectors"]
        .astype("float32"),

        list(data["paths"]),

        list(data["labels"]),
    )


def get_embeddings(
    adapter,
    model_name,
    split_name,
    paths,
    labels,
    force=False
):

    cache_file = (
        CACHE_ROOT
        / model_name
        / f"{split_name}.npz"
    )

    if (
        cache_file.exists()
        and not force
    ):

        print(
            f"[{model_name}] "
            f"Loading cached "
            f"{split_name} embeddings"
        )

        vectors, _, cached_labels = (
            load_embeddings(
                cache_file
            )
        )

        return (
            vectors,
            cached_labels,
            0.0,
            True
        )

    print(
        f"[{model_name}] "
        f"Encoding {split_name}: "
        f"{len(paths)} images"
    )

    if torch.cuda.is_available():
        torch.cuda.synchronize()

    started = time.perf_counter()

    vectors = adapter.encode_paths(
        paths
    )

    if torch.cuda.is_available():
        torch.cuda.synchronize()

    elapsed = (
        time.perf_counter()
        - started
    )

    vectors = normalize_numpy(
        vectors
    )

    save_embeddings(
        cache_file,
        vectors,
        paths,
        labels
    )

    return (
        vectors,
        labels,
        elapsed,
        False
    )


def average_precision_at_k(
    retrieved_labels,
    query_label,
    k,
    relevant_in_gallery
):
    hits = 0
    precision_sum = 0.0

    for rank, label in enumerate(
        retrieved_labels[:k],
        start=1
    ):
        if label == query_label:
            hits += 1
            precision_sum += hits / rank

    denominator = min(
        relevant_in_gallery,
        k
    )

    if denominator == 0:
        return 0.0

    return precision_sum / denominator


def calculate_metrics(
    query_labels,
    retrieved_labels,
    gallery_labels
):
    ks = [1, 5, 10]

    metrics = {}

    gallery_counts = Counter(
        gallery_labels
    )

    # ----------------------------
    # Overall Precision / Hit@K
    # ----------------------------

    for k in ks:

        precisions = []
        hits = []

        for query_label, results in zip(
            query_labels,
            retrieved_labels
        ):
            top_k = results[:k]

            relevant_count = sum(
                1
                for label in top_k
                if label == query_label
            )

            precisions.append(
                relevant_count / k
            )

            hits.append(
                1.0
                if relevant_count > 0
                else 0.0
            )

        metrics[
            f"precision_at_{k}"
        ] = float(
            np.mean(precisions)
        )

        metrics[
            f"hit_at_{k}"
        ] = float(
            np.mean(hits)
        )

    # ----------------------------
    # MRR@10 + Correct mAP@10
    # ----------------------------

    reciprocal_ranks = []
    ap10_scores = []

    for query_label, results in zip(
        query_labels,
        retrieved_labels
    ):
        reciprocal_rank = 0.0

        for rank, label in enumerate(
            results[:10],
            start=1
        ):
            if label == query_label:
                reciprocal_rank = (
                    1.0 / rank
                )
                break

        reciprocal_ranks.append(
            reciprocal_rank
        )

        ap10_scores.append(
            average_precision_at_k(
                results,
                query_label,
                10,
                gallery_counts[
                    query_label
                ]
            )
        )

    metrics["mrr_at_10"] = float(
        np.mean(
            reciprocal_ranks
        )
    )

    metrics["map_at_10"] = float(
        np.mean(
            ap10_scores
        )
    )

    metrics["query_count"] = len(
        query_labels
    )

    # ----------------------------
    # Per-Class Evaluation
    # ----------------------------

    grouped = defaultdict(list)

    for index, label in enumerate(
        query_labels
    ):
        grouped[label].append(
            index
        )

    per_class = {}

    for class_name, indices in sorted(
        grouped.items()
    ):
        class_results = {}

        for k in ks:

            precisions = []
            hits = []

            for index in indices:

                results = (
                    retrieved_labels[
                        index
                    ][:k]
                )

                correct = sum(
                    1
                    for label in results
                    if label == class_name
                )

                precisions.append(
                    correct / k
                )

                hits.append(
                    1.0
                    if correct > 0
                    else 0.0
                )

            class_results[
                f"precision_at_{k}"
            ] = float(
                np.mean(
                    precisions
                )
            )

            class_results[
                f"hit_at_{k}"
            ] = float(
                np.mean(
                    hits
                )
            )

        class_results[
            "query_count"
        ] = len(indices)

        per_class[
            class_name
        ] = class_results

    metrics[
        "per_class"
    ] = per_class

    return metrics

def save_query_analysis(
    model_name,
    query_paths,
    query_labels,
    gallery_paths,
    gallery_labels,
    scores,
    ids,
):
    RESULTS_ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    all_results_path = (
        RESULTS_ROOT
        / f"{model_name}_queries.csv"
    )

    failures_path = (
        RESULTS_ROOT
        / f"{model_name}_failures.csv"
    )

    def relative_path(path):
        path = Path(path)

        try:
            return path.resolve().relative_to(
                ROOT.resolve()
            ).as_posix()

        except ValueError:
            return str(path)

    rows = []
    failure_rows = []

    for query_index in range(
        len(query_paths)
    ):
        query_path = query_paths[
            query_index
        ]

        true_class = query_labels[
            query_index
        ]

        result_ids = ids[
            query_index
        ]

        result_scores = scores[
            query_index
        ]

        row = {
            "query_path":
                relative_path(
                    query_path
                ),

            "true_class":
                true_class,
        }

        valid_results = []

        for rank, (
            gallery_index,
            similarity
        ) in enumerate(
            zip(
                result_ids,
                result_scores
            ),
            start=1
        ):
            if gallery_index < 0:
                continue

            gallery_index = int(
                gallery_index
            )

            predicted_class = (
                gallery_labels[
                    gallery_index
                ]
            )

            predicted_path = (
                gallery_paths[
                    gallery_index
                ]
            )

            similarity = float(
                similarity
            )

            valid_results.append(
                {
                    "rank": rank,
                    "class":
                        predicted_class,
                    "score":
                        similarity,
                    "path":
                        relative_path(
                            predicted_path
                        ),
                }
            )

            row[
                f"rank_{rank}_class"
            ] = predicted_class

            row[
                f"rank_{rank}_score"
            ] = round(
                similarity,
                6
            )

            row[
                f"rank_{rank}_path"
            ] = relative_path(
                predicted_path
            )

        if valid_results:

            top1 = valid_results[0]

            predicted_class = (
                top1["class"]
            )

            top1_score = (
                top1["score"]
            )

        else:

            predicted_class = ""
            top1_score = 0.0

        top1_correct = (
            predicted_class
            == true_class
        )

        row[
            "predicted_class"
        ] = predicted_class

        row[
            "top1_score"
        ] = round(
            top1_score,
            6
        )

        row[
            "top1_correct"
        ] = top1_correct

        rows.append(
            row
        )

        if not top1_correct:
            failure_rows.append(
                row.copy()
            )

    fieldnames = [
        "query_path",
        "true_class",
        "predicted_class",
        "top1_score",
        "top1_correct",
    ]

    for rank in range(
        1,
        11
    ):
        fieldnames.extend(
            [
                f"rank_{rank}_class",
                f"rank_{rank}_score",
                f"rank_{rank}_path",
            ]
        )

    with open(
        all_results_path,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()

        writer.writerows(
            rows
        )

    with open(
        failures_path,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()

        writer.writerows(
            failure_rows
        )

    print(
        f"Query analysis saved: "
        f"{all_results_path.name}"
    )

    print(
        f"Top-1 failures: "
        f"{len(failure_rows)} "
        f"/ {len(rows)}"
    )

    return {
        "query_count":
            len(rows),

        "failure_count":
            len(failure_rows),

        "success_count":
            len(rows)
            - len(failure_rows),
    }

def benchmark_model(
    model_name,
    force=False
):

    print()
    print("=" * 70)
    print(
        f"MODEL: {model_name}"
    )
    print("=" * 70)

    train_paths, train_labels = (
        discover_split(
            "train"
        )
    )

    validation_paths, validation_labels = (
        discover_split(
            "validation"
        )
    )

    print(
        f"Train gallery: "
        f"{len(train_paths)} images"
    )

    print(
        f"Validation queries: "
        f"{len(validation_paths)} images"
    )

    adapter = create_adapter(
        model_name
    )

    try:

        (
            train_vectors,
            train_labels,
            train_embedding_seconds,
            train_cached
        ) = get_embeddings(
            adapter,
            model_name,
            "train",
            train_paths,
            train_labels,
            force
        )

        (
            query_vectors,
            validation_labels,
            query_embedding_seconds,
            validation_cached
        ) = get_embeddings(
            adapter,
            model_name,
            "validation",
            validation_paths,
            validation_labels,
            force
        )

        dimension = (
            train_vectors.shape[1]
        )

        print(
            f"Embedding dimension: "
            f"{dimension}"
        )

        # ---------------------------------------------
        # FAISS INDEX
        # ---------------------------------------------

        index_started = (
            time.perf_counter()
        )

        index = faiss.IndexFlatIP(
            dimension
        )

        index.add(
            train_vectors
        )

        index_seconds = (
            time.perf_counter()
            - index_started
        )

        # ---------------------------------------------
        # SEARCH
        # ---------------------------------------------

        search_started = (
            time.perf_counter()
        )

        scores, ids = index.search(
            query_vectors,
            10
        )

        search_seconds = (
            time.perf_counter()
            - search_started
        )

        # ---------------------------------------------
        # LABEL RESULTS
        # ---------------------------------------------

        retrieved_labels = []

        for row in ids:
            retrieved_labels.append(
                [
                    train_labels[index_id]
                    for index_id in row
                    if index_id >= 0
                ]
            )

        analysis_info = save_query_analysis(
            model_name=model_name,
            query_paths=validation_paths,
            query_labels=validation_labels,
            gallery_paths=train_paths,
            gallery_labels=train_labels,
            scores=scores,
            ids=ids,
        )

        metrics = calculate_metrics(
            validation_labels,
            retrieved_labels,
            train_labels
        )

        metrics["top1_failure_count"] = (
            analysis_info["failure_count"]
        )

        query_count = len(
            validation_paths
        )

        metrics.update(
            {
                "model":
                    model_name,

                "embedding_dimension":
                    int(dimension),

                "gallery_count":
                    len(train_paths),

                "validation_count":
                    query_count,

                "gallery_embedding_seconds":
                    float(
                        train_embedding_seconds
                    ),

                "validation_embedding_seconds":
                    float(
                        query_embedding_seconds
                    ),

                "avg_query_embedding_ms":
                    float(
                        (
                            query_embedding_seconds
                            / query_count
                            * 1000
                        )
                        if query_embedding_seconds
                        else 0.0
                    ),

                "faiss_index_seconds":
                    float(index_seconds),

                "search_seconds":
                    float(search_seconds),

                "avg_search_ms":
                    float(
                        search_seconds
                        / query_count
                        * 1000
                    ),

                "gallery_cache_used":
                    train_cached,

                "validation_cache_used":
                    validation_cached,

                "device":
                    adapter.device,
            }
        )

        # ---------------------------------------------
        # DETAIL FILE
        # ---------------------------------------------

        RESULTS_ROOT.mkdir(
            parents=True,
            exist_ok=True
        )

        detail_path = (
            RESULTS_ROOT
            / f"{model_name}.json"
        )

        with open(
            detail_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                metrics,
                file,
                indent=2
            )

        print()
        print(
            f"Precision@1: "
            f"{metrics['precision_at_1']:.4f}"
        )

        print(
            f"Precision@5: "
            f"{metrics['precision_at_5']:.4f}"
        )

        print(
            f"Precision@10: "
            f"{metrics['precision_at_10']:.4f}"
        )

        print(
            f"Hit@5: "
            f"{metrics['hit_at_5']:.4f}"
        )

        print(
            f"mAP@10: "
            f"{metrics['map_at_10']:.4f}"
        )

        print(
            f"MRR@10: "
            f"{metrics['mrr_at_10']:.4f}"
        )

        print(
            f"Average search: "
            f"{metrics['avg_search_ms']:.3f} ms/query"
        )

        return metrics

    finally:

        adapter.cleanup()


def save_summary(
    results
):

    RESULTS_ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path = (
        RESULTS_ROOT
        / "summary.csv"
    )

    fields = [
        "model",
        "embedding_dimension",
        "gallery_count",
        "validation_count",
        "precision_at_1",
        "precision_at_5",
        "precision_at_10",
        "hit_at_1",
        "hit_at_5",
        "hit_at_10",
        "map_at_10",
        "mrr_at_10",
        "gallery_embedding_seconds",
        "validation_embedding_seconds",
        "avg_query_embedding_ms",
        "faiss_index_seconds",
        "search_seconds",
        "avg_search_ms",
        "device",
    ]

    with open(
        output_path,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fields
        )

        writer.writeheader()

        for result in results:

            writer.writerow(
                {
                    key:
                        result.get(key)
                    for key in fields
                }
            )

    print()
    print(
        f"Summary saved to:"
        f"\n{output_path}"
    )


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--model",
        default="clip",
        choices=ALL_MODELS + ["all"]
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Rebuild cached embeddings."
        )
    )

    args = parser.parse_args()

    if args.model == "all":

        models = ALL_MODELS

    else:

        models = [
            args.model
        ]

    results = []

    for model_name in models:

        try:

            result = benchmark_model(
                model_name,
                force=args.force
            )

            results.append(
                result
            )

        except Exception as error:

            print()
            print(
                f"[ERROR] {model_name}: "
                f"{error}"
            )

    if results:

        save_summary(
            results
        )


if __name__ == "__main__":

    main()