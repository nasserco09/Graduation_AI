from pathlib import Path
import csv
from collections import Counter, defaultdict


ROOT = Path(__file__).resolve().parent.parent
RESULTS_ROOT = ROOT / "evaluation" / "results"

MODELS = [
    "clip",
    "dinov2",
    "siglip2",
    "resnet50",
    "efficientnet_b3",
]


def analyze_model(model_name):
    input_file = (
        RESULTS_ROOT
        / f"{model_name}_queries.csv"
    )

    if not input_file.exists():
        print(
            f"[SKIP] Missing: {input_file}"
        )
        return None

    confusion = Counter()
    class_totals = Counter()
    class_failures = Counter()

    with open(
        input_file,
        "r",
        encoding="utf-8"
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:

            true_class = row["true_class"]
            predicted_class = (
                row["predicted_class"]
            )

            class_totals[
                true_class
            ] += 1

            if (
                true_class
                != predicted_class
            ):
                class_failures[
                    true_class
                ] += 1

                confusion[
                    (
                        true_class,
                        predicted_class
                    )
                ] += 1

    confusion_file = (
        RESULTS_ROOT
        / f"{model_name}_confusions.csv"
    )

    with open(
        confusion_file,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.writer(file)

        writer.writerow(
            [
                "true_class",
                "predicted_class",
                "count",
            ]
        )

        for (
            true_class,
            predicted_class
        ), count in confusion.most_common():

            writer.writerow(
                [
                    true_class,
                    predicted_class,
                    count,
                ]
            )

    class_summary = []

    for class_name in sorted(
        class_totals
    ):

        total = class_totals[
            class_name
        ]

        failures = class_failures[
            class_name
        ]

        accuracy = (
            (total - failures)
            / total
        )

        class_summary.append(
            {
                "class":
                    class_name,

                "queries":
                    total,

                "failures":
                    failures,

                "top1_accuracy":
                    accuracy,
            }
        )

    return {
        "model":
            model_name,

        "class_summary":
            class_summary,

        "top_confusions":
            confusion.most_common(10),
    }


def main():

    summary_file = (
        RESULTS_ROOT
        / "failure_summary.csv"
    )

    all_rows = []

    for model_name in MODELS:

        result = analyze_model(
            model_name
        )

        if result is None:
            continue

        print()
        print("=" * 60)
        print(
            f"MODEL: {model_name}"
        )
        print("=" * 60)

        print(
            "\nTop confusions:"
        )

        for (
            true_class,
            predicted_class
        ), count in result[
            "top_confusions"
        ]:

            print(
                f"{true_class:12} "
                f"-> "
                f"{predicted_class:12} "
                f": {count}"
            )

        for item in result[
            "class_summary"
        ]:

            all_rows.append(
                {
                    "model":
                        model_name,

                    "class":
                        item["class"],

                    "queries":
                        item["queries"],

                    "failures":
                        item["failures"],

                    "top1_accuracy":
                        round(
                            item[
                                "top1_accuracy"
                            ],
                            6
                        ),
                }
            )

    with open(
        summary_file,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=[
                "model",
                "class",
                "queries",
                "failures",
                "top1_accuracy",
            ]
        )

        writer.writeheader()

        writer.writerows(
            all_rows
        )

    print()
    print(
        f"Saved:"
        f"\n{summary_file}"
    )


if __name__ == "__main__":
    main()