from pathlib import Path
from collections import defaultdict
import base64
import csv
import json
import random

import faiss
import numpy as np
import torch
from PIL import Image, ImageOps

from backend.segmenter import Segmenter
from evaluation.model_adapters import create_adapter
from evaluation.benchmark import (
    discover_split,
    load_embeddings,
    calculate_metrics,
)


ROOT = Path(__file__).resolve().parent.parent

CACHE_ROOT = ROOT / "evaluation" / "cache"
RESULTS_ROOT = ROOT / "evaluation" / "results"

AB_ROOT = CACHE_ROOT / "sam2_ab"
COMPOSITE_ROOT = AB_ROOT / "composites"
CUTOUT_ROOT = AB_ROOT / "cutouts"

SIGLIP_CACHE = (
    CACHE_ROOT
    / "siglip2"
    / "train.npz"
)

SAMPLES_PER_CLASS = 10
RANDOM_SEED = 42


def prepare_panel(image, size=512):
    image = image.convert("RGB")

    panel = Image.new(
        "RGB",
        (size, size),
        "white"
    )

    fitted = ImageOps.contain(
        image,
        (size - 40, size - 40)
    )

    x = (size - fitted.width) // 2
    y = (size - fitted.height) // 2

    panel.paste(
        fitted,
        (x, y)
    )

    return panel


def build_queries():
    validation_paths, validation_labels = (
        discover_split("validation")
    )

    grouped = defaultdict(list)

    for path, label in zip(
        validation_paths,
        validation_labels
    ):
        grouped[label].append(path)

    rng = random.Random(
        RANDOM_SEED
    )

    classes = sorted(
        grouped.keys()
    )

    selected = []

    for class_name in classes:
        candidates = grouped[class_name][:]
        rng.shuffle(candidates)

        for path in candidates[
            :SAMPLES_PER_CLASS
        ]:
            selected.append(
                (path, class_name)
            )

    COMPOSITE_ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    records = []

    for index, (
        target_path,
        target_class
    ) in enumerate(selected):

        distractor_classes = [
            item
            for item in classes
            if item != target_class
        ]

        distractor_class = rng.choice(
            distractor_classes
        )

        distractor_path = rng.choice(
            grouped[distractor_class]
        )

        target_image = Image.open(
            target_path
        ).convert("RGB")

        distractor_image = Image.open(
            distractor_path
        ).convert("RGB")

        target_panel = prepare_panel(
            target_image
        )

        distractor_panel = prepare_panel(
            distractor_image
        )

        target_on_left = rng.choice(
            [True, False]
        )

        composite = Image.new(
            "RGB",
            (1024, 512),
            "white"
        )

        if target_on_left:
            composite.paste(
                target_panel,
                (0, 0)
            )

            composite.paste(
                distractor_panel,
                (512, 0)
            )

            prompt_x = 256
            prompt_y = 256

        else:
            composite.paste(
                distractor_panel,
                (0, 0)
            )

            composite.paste(
                target_panel,
                (512, 0)
            )

            prompt_x = 768
            prompt_y = 256

        output_path = (
            COMPOSITE_ROOT
            / (
                f"{index:03d}_"
                f"{target_class}.jpg"
            )
        )

        composite.save(
            output_path,
            quality=95
        )

        records.append(
            {
                "index": index,
                "target_class":
                    target_class,

                "target_path":
                    target_path,

                "distractor_class":
                    distractor_class,

                "distractor_path":
                    distractor_path,

                "composite_path":
                    output_path,

                "prompt":
                    [
                        prompt_x,
                        prompt_y
                    ],
            }
        )

    return records


def segment_queries(records):
    CUTOUT_ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    print()
    print("=" * 70)
    print("SAM2 SEGMENTATION")
    print("=" * 70)

    segmenter = Segmenter()

    successful = []

    for number, record in enumerate(
        records,
        start=1
    ):
        output_path = (
            CUTOUT_ROOT
            / (
                f"{record['index']:03d}_"
                f"{record['target_class']}.png"
            )
        )

        if output_path.exists():
            record[
                "cutout_path"
            ] = output_path

            successful.append(
                record
            )

            print(
                f"[{number}/{len(records)}] "
                f"Cached"
            )

            continue

        try:
            image = Image.open(
                record["composite_path"]
            ).convert("RGB")

            x, y = record[
                "prompt"
            ]

            result = segmenter.segment(
                image=image,
                points=[[x, y]],
                labels=[1],
            )

            image_bytes = base64.b64decode(
                result["cutout"]
            )

            output_path.write_bytes(
                image_bytes
            )

            record[
                "cutout_path"
            ] = output_path

            successful.append(
                record
            )

            print(
                f"[{number}/{len(records)}] "
                f"OK - "
                f"{record['target_class']}"
            )

        except Exception as error:
            print(
                f"[{number}/{len(records)}] "
                f"FAILED - {error}"
            )

    del segmenter

    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    print()
    print(
        f"SAM2 successful: "
        f"{len(successful)} / "
        f"{len(records)}"
    )

    return successful


def get_retrieved_labels(
    ids,
    gallery_labels
):
    retrieved = []

    for row in ids:
        retrieved.append(
            [
                gallery_labels[
                    int(index)
                ]
                for index in row
                if index >= 0
            ]
        )

    return retrieved


def evaluate(
    vectors,
    labels,
    index,
    gallery_labels
):
    scores, ids = index.search(
        vectors,
        10
    )

    retrieved = get_retrieved_labels(
        ids,
        gallery_labels
    )

    metrics = calculate_metrics(
        labels,
        retrieved,
        gallery_labels
    )

    predictions = [
        row[0]
        if row
        else ""
        for row in retrieved
    ]

    return (
        metrics,
        predictions,
        scores,
        ids,
    )


def main():
    if not SIGLIP_CACHE.exists():
        raise FileNotFoundError(
            "SigLIP2 train cache not found. "
            "Run the SigLIP2 benchmark first."
        )

    RESULTS_ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    print("=" * 70)
    print("BUILDING 100 MULTI-PRODUCT QUERIES")
    print("=" * 70)

    records = build_queries()

    print(
        f"Queries created: "
        f"{len(records)}"
    )

    records = segment_queries(
        records
    )

    if not records:
        raise RuntimeError(
            "SAM2 failed on all queries."
        )

    labels = [
        record["target_class"]
        for record in records
    ]

    composite_paths = [
        record["composite_path"]
        for record in records
    ]

    cutout_paths = [
        record["cutout_path"]
        for record in records
    ]

    print()
    print("=" * 70)
    print("SIGLIP2 EMBEDDINGS")
    print("=" * 70)

    adapter = create_adapter(
        "siglip2"
    )

    print(
        "Encoding full "
        "multi-product images..."
    )

    full_vectors = (
        adapter.encode_paths(
            composite_paths,
            batch_size=8
        )
    )

    print(
        "Encoding SAM2 "
        "selected products..."
    )

    selected_vectors = (
        adapter.encode_paths(
            cutout_paths,
            batch_size=8
        )
    )

    adapter.cleanup()

    train_vectors, _, gallery_labels = (
        load_embeddings(
            SIGLIP_CACHE
        )
    )

    dimension = (
        train_vectors.shape[1]
    )

    index = faiss.IndexFlatIP(
        dimension
    )

    index.add(
        train_vectors
    )

    (
        full_metrics,
        full_predictions,
        full_scores,
        _
    ) = evaluate(
        full_vectors,
        labels,
        index,
        gallery_labels
    )

    (
        selected_metrics,
        selected_predictions,
        selected_scores,
        _
    ) = evaluate(
        selected_vectors,
        labels,
        index,
        gallery_labels
    )

    improved = 0
    worsened = 0
    unchanged = 0

    rows = []

    for i, record in enumerate(
        records
    ):
        true_class = labels[i]

        full_correct = (
            full_predictions[i]
            == true_class
        )

        selected_correct = (
            selected_predictions[i]
            == true_class
        )

        if (
            not full_correct
            and selected_correct
        ):
            improved += 1

        elif (
            full_correct
            and not selected_correct
        ):
            worsened += 1

        else:
            unchanged += 1

        rows.append(
            {
                "query":
                    record[
                        "composite_path"
                    ].name,

                "target_class":
                    true_class,

                "distractor_class":
                    record[
                        "distractor_class"
                    ],

                "full_prediction":
                    full_predictions[i],

                "selected_prediction":
                    selected_predictions[i],

                "full_correct":
                    full_correct,

                "selected_correct":
                    selected_correct,

                "full_top1_score":
                    round(
                        float(
                            full_scores[i][0]
                        ),
                        6
                    ),

                "selected_top1_score":
                    round(
                        float(
                            selected_scores[i][0]
                        ),
                        6
                    ),
            }
        )

    result = {
        "sample_count":
            len(records),

        "sam2_success_count":
            len(records),

        "full_image": {
            "precision_at_1":
                full_metrics[
                    "precision_at_1"
                ],

            "precision_at_5":
                full_metrics[
                    "precision_at_5"
                ],

            "precision_at_10":
                full_metrics[
                    "precision_at_10"
                ],

            "map_at_10":
                full_metrics[
                    "map_at_10"
                ],

            "mrr_at_10":
                full_metrics[
                    "mrr_at_10"
                ],
        },

        "sam2_selected": {
            "precision_at_1":
                selected_metrics[
                    "precision_at_1"
                ],

            "precision_at_5":
                selected_metrics[
                    "precision_at_5"
                ],

            "precision_at_10":
                selected_metrics[
                    "precision_at_10"
                ],

            "map_at_10":
                selected_metrics[
                    "map_at_10"
                ],

            "mrr_at_10":
                selected_metrics[
                    "mrr_at_10"
                ],
        },

        "improved_queries":
            improved,

        "worsened_queries":
            worsened,

        "unchanged_queries":
            unchanged,
    }

    json_path = (
        RESULTS_ROOT
        / "sam2_vs_full.json"
    )

    with open(
        json_path,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            result,
            file,
            indent=2
        )

    csv_path = (
        RESULTS_ROOT
        / "sam2_vs_full_queries.csv"
    )

    with open(
        csv_path,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "query",
                "target_class",
                "distractor_class",
                "full_prediction",
                "selected_prediction",
                "full_correct",
                "selected_correct",
                "full_top1_score",
                "selected_top1_score",
            ]
        )

        writer.writeheader()
        writer.writerows(rows)

    print()
    print("=" * 70)
    print("FINAL A/B RESULT")
    print("=" * 70)

    print()
    print("FULL MULTI-PRODUCT IMAGE")
    print(
        f"P@1:   "
        f"{full_metrics['precision_at_1']:.4f}"
    )
    print(
        f"P@5:   "
        f"{full_metrics['precision_at_5']:.4f}"
    )
    print(
        f"mAP@10:"
        f" {full_metrics['map_at_10']:.4f}"
    )

    print()
    print("SAM2 SELECTED PRODUCT")
    print(
        f"P@1:   "
        f"{selected_metrics['precision_at_1']:.4f}"
    )
    print(
        f"P@5:   "
        f"{selected_metrics['precision_at_5']:.4f}"
    )
    print(
        f"mAP@10:"
        f" {selected_metrics['map_at_10']:.4f}"
    )

    print()
    print(
        f"Improved queries: "
        f"{improved}"
    )

    print(
        f"Worsened queries: "
        f"{worsened}"
    )

    print(
        f"Unchanged queries: "
        f"{unchanged}"
    )

    delta = (
        selected_metrics[
            "precision_at_1"
        ]
        -
        full_metrics[
            "precision_at_1"
        ]
    )

    print()
    print(
        f"P@1 change: "
        f"{delta * 100:+.2f} "
        f"percentage points"
    )

    print()
    print(
        f"Saved:"
        f"\n{json_path}"
        f"\n{csv_path}"
    )


if __name__ == "__main__":
    main()