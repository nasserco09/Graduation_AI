from pathlib import Path
from collections import defaultdict
import base64
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
    save_embeddings,
    calculate_metrics,
)


ROOT = Path(__file__).resolve().parent.parent

CACHE_ROOT = ROOT / "evaluation" / "cache"
RESULTS_ROOT = ROOT / "evaluation" / "results"

SIGLIP_TRAIN_CACHE = (
    CACHE_ROOT
    / "siglip2"
    / "train.npz"
)

SIGLIP_TEST_CACHE = (
    CACHE_ROOT
    / "siglip2"
    / "test.npz"
)

FINAL_CACHE = (
    CACHE_ROOT
    / "final_test"
)

COMPOSITE_ROOT = (
    FINAL_CACHE
    / "composites"
)

CUTOUT_ROOT = (
    FINAL_CACHE
    / "cutouts"
)

SAMPLES_PER_CLASS = 10
RANDOM_SEED = 42


def retrieve(
    query_vectors,
    query_labels,
    index,
    gallery_labels
):
    scores, ids = index.search(
        query_vectors,
        10
    )

    retrieved_labels = []

    for row in ids:
        retrieved_labels.append(
            [
                gallery_labels[int(i)]
                for i in row
                if i >= 0
            ]
        )

    metrics = calculate_metrics(
        query_labels,
        retrieved_labels,
        gallery_labels
    )

    predictions = [
        row[0] if row else ""
        for row in retrieved_labels
    ]

    return (
        metrics,
        predictions,
        scores,
        ids,
    )


def prepare_panel(
    image,
    size=512
):
    image = image.convert("RGB")

    panel = Image.new(
        "RGB",
        (size, size),
        "white"
    )

    fitted = ImageOps.contain(
        image,
        (
            size - 40,
            size - 40
        )
    )

    x = (
        size
        - fitted.width
    ) // 2

    y = (
        size
        - fitted.height
    ) // 2

    panel.paste(
        fitted,
        (x, y)
    )

    return panel


def build_multi_product_queries(
    test_paths,
    test_labels
):
    grouped = defaultdict(list)

    for path, label in zip(
        test_paths,
        test_labels
    ):
        grouped[label].append(
            path
        )

    rng = random.Random(
        RANDOM_SEED
    )

    classes = sorted(
        grouped.keys()
    )

    COMPOSITE_ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    records = []

    query_index = 0

    for target_class in classes:

        candidates = (
            grouped[target_class][:]
        )

        rng.shuffle(
            candidates
        )

        selected = candidates[
            :SAMPLES_PER_CLASS
        ]

        for target_path in selected:

            distractor_classes = [
                item
                for item in classes
                if item != target_class
            ]

            distractor_class = (
                rng.choice(
                    distractor_classes
                )
            )

            distractor_path = (
                rng.choice(
                    grouped[
                        distractor_class
                    ]
                )
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

            distractor_panel = (
                prepare_panel(
                    distractor_image
                )
            )

            composite = Image.new(
                "RGB",
                (1024, 512),
                "white"
            )

            target_left = rng.choice(
                [True, False]
            )

            if target_left:

                composite.paste(
                    target_panel,
                    (0, 0)
                )

                composite.paste(
                    distractor_panel,
                    (512, 0)
                )

                prompt = [
                    256,
                    256
                ]

            else:

                composite.paste(
                    distractor_panel,
                    (0, 0)
                )

                composite.paste(
                    target_panel,
                    (512, 0)
                )

                prompt = [
                    768,
                    256
                ]

            output_path = (
                COMPOSITE_ROOT
                / (
                    f"{query_index:03d}_"
                    f"{target_class}.jpg"
                )
            )

            composite.save(
                output_path,
                quality=95
            )

            records.append(
                {
                    "index":
                        query_index,

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
                        prompt,
                }
            )

            query_index += 1

    return records


def run_sam2(
    records
):
    CUTOUT_ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    print()
    print("=" * 70)
    print("SAM2 FINAL TEST")
    print("=" * 70)

    segmenter = Segmenter()

    successful = []

    for number, record in enumerate(
        records,
        start=1
    ):

        cutout_path = (
            CUTOUT_ROOT
            / (
                f"{record['index']:03d}_"
                f"{record['target_class']}.png"
            )
        )

        if cutout_path.exists():

            record[
                "cutout_path"
            ] = cutout_path

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
                record[
                    "composite_path"
                ]
            ).convert("RGB")

            x, y = record[
                "prompt"
            ]

            result = (
                segmenter.segment(
                    image=image,
                    points=[
                        [x, y]
                    ],
                    labels=[1]
                )
            )

            decoded = (
                base64.b64decode(
                    result["cutout"]
                )
            )

            cutout_path.write_bytes(
                decoded
            )

            record[
                "cutout_path"
            ] = cutout_path

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

    return successful


def main():

    if not SIGLIP_TRAIN_CACHE.exists():

        raise FileNotFoundError(
            "SigLIP2 train cache "
            "was not found."
        )

    RESULTS_ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    # ==========================================
    # Gallery
    # ==========================================

    (
        train_vectors,
        train_paths,
        train_labels
    ) = load_embeddings(
        SIGLIP_TRAIN_CACHE
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

    # ==========================================
    # Test split
    # ==========================================

    test_paths, test_labels = (
        discover_split(
            "test"
        )
    )

    print()
    print("=" * 70)
    print("FINAL TEST SET")
    print("=" * 70)

    print(
        f"Gallery: "
        f"{len(train_vectors)}"
    )

    print(
        f"Test queries: "
        f"{len(test_paths)}"
    )

    # ==========================================
    # Load SigLIP2 once
    # ==========================================

    adapter = create_adapter(
        "siglip2"
    )

    # ==========================================
    # Normal Test Images
    # ==========================================

    if SIGLIP_TEST_CACHE.exists():

        print(
            "Loading cached "
            "SigLIP2 test embeddings..."
        )

        (
            test_vectors,
            _,
            cached_test_labels
        ) = load_embeddings(
            SIGLIP_TEST_CACHE
        )

        test_labels = (
            cached_test_labels
        )

    else:

        print(
            "Encoding all Test images..."
        )

        test_vectors = (
            adapter.encode_paths(
                test_paths,
                batch_size=8
            )
        )

        save_embeddings(
            SIGLIP_TEST_CACHE,
            test_vectors,
            test_paths,
            test_labels
        )

    (
        clean_metrics,
        clean_predictions,
        _,
        _
    ) = retrieve(
        test_vectors,
        test_labels,
        index,
        train_labels
    )

    # ==========================================
    # Multi-product Test
    # ==========================================

    records = (
        build_multi_product_queries(
            test_paths,
            test_labels
        )
    )

    print()
    print(
        f"Multi-product queries: "
        f"{len(records)}"
    )

    records = run_sam2(
        records
    )

    composite_paths = [
        record[
            "composite_path"
        ]
        for record in records
    ]

    cutout_paths = [
        record[
            "cutout_path"
        ]
        for record in records
    ]

    multi_labels = [
        record[
            "target_class"
        ]
        for record in records
    ]

    print()
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

    (
        full_metrics,
        full_predictions,
        _,
        _
    ) = retrieve(
        full_vectors,
        multi_labels,
        index,
        train_labels
    )

    (
        selected_metrics,
        selected_predictions,
        _,
        _
    ) = retrieve(
        selected_vectors,
        multi_labels,
        index,
        train_labels
    )

    improved = 0
    worsened = 0
    unchanged = 0

    for true_class, full_pred, selected_pred in zip(
        multi_labels,
        full_predictions,
        selected_predictions
    ):

        full_correct = (
            full_pred == true_class
        )

        selected_correct = (
            selected_pred == true_class
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

    p1_delta = (
        selected_metrics[
            "precision_at_1"
        ]
        -
        full_metrics[
            "precision_at_1"
        ]
    )

    # ==========================================
    # Save final result
    # ==========================================

    result = {
        "protocol": {
            "gallery_split":
                "train",

            "final_query_split":
                "test",

            "gallery_count":
                len(train_vectors),

            "test_query_count":
                len(test_paths),

            "multi_product_query_count":
                len(records),

            "model":
                "SigLIP2",

            "segmentation_model":
                "SAM2.1 Hiera Base Plus",
        },

        "clean_test": {
            "precision_at_1":
                clean_metrics[
                    "precision_at_1"
                ],

            "precision_at_5":
                clean_metrics[
                    "precision_at_5"
                ],

            "precision_at_10":
                clean_metrics[
                    "precision_at_10"
                ],

            "map_at_10":
                clean_metrics[
                    "map_at_10"
                ],

            "mrr_at_10":
                clean_metrics[
                    "mrr_at_10"
                ],
        },

        "multi_product_full_image": {
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

        "multi_product_sam2": {
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

        "sam2_effect": {
            "improved_queries":
                improved,

            "worsened_queries":
                worsened,

            "unchanged_queries":
                unchanged,

            "precision_at_1_delta":
                p1_delta,
        },
    }

    output_path = (
        RESULTS_ROOT
        / "FINAL_TEST_RESULTS.json"
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            indent=2
        )

    # ==========================================
    # PRINT
    # ==========================================

    print()
    print("=" * 70)
    print("FINAL TEST RESULTS")
    print("=" * 70)

    print()
    print(
        f"CLEAN TEST IMAGES "
        f"({len(test_paths)} queries)"
    )

    print(
        f"P@1:    "
        f"{clean_metrics['precision_at_1']:.4f}"
    )

    print(
        f"P@5:    "
        f"{clean_metrics['precision_at_5']:.4f}"
    )

    print(
        f"P@10:   "
        f"{clean_metrics['precision_at_10']:.4f}"
    )

    print(
        f"mAP@10: "
        f"{clean_metrics['map_at_10']:.4f}"
    )

    print(
        f"MRR@10: "
        f"{clean_metrics['mrr_at_10']:.4f}"
    )

    print()
    print("MULTI-PRODUCT — FULL IMAGE")

    print(
        f"P@1:    "
        f"{full_metrics['precision_at_1']:.4f}"
    )

    print(
        f"P@5:    "
        f"{full_metrics['precision_at_5']:.4f}"
    )

    print(
        f"mAP@10: "
        f"{full_metrics['map_at_10']:.4f}"
    )

    print()
    print(
        "MULTI-PRODUCT — "
        "SAM2 SELECTED PRODUCT"
    )

    print(
        f"P@1:    "
        f"{selected_metrics['precision_at_1']:.4f}"
    )

    print(
        f"P@5:    "
        f"{selected_metrics['precision_at_5']:.4f}"
    )

    print(
        f"mAP@10: "
        f"{selected_metrics['map_at_10']:.4f}"
    )

    print()
    print(
        f"Improved: "
        f"{improved}"
    )

    print(
        f"Worsened: "
        f"{worsened}"
    )

    print(
        f"Unchanged: "
        f"{unchanged}"
    )

    print(
        f"P@1 change: "
        f"{p1_delta * 100:+.2f} "
        f"percentage points"
    )

    print()
    print(
        f"Saved:"
        f"\n{output_path}"
    )


if __name__ == "__main__":
    main()