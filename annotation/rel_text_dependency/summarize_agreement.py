from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


LABELS = ("dependent", "independent")


def load(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            row["parallel_id"]: row
            for row in csv.DictReader(handle)
            if row.get("text_dependency") in LABELS
        }


def summarize(first_path: Path, second_path: Path):
    first = load(first_path)
    second = load(second_path)
    shared = sorted(set(first) & set(second))
    confusion = Counter(
        (first[item]["text_dependency"], second[item]["text_dependency"])
        for item in shared
    )
    observed = (
        sum(confusion[(label, label)] for label in LABELS) / len(shared)
        if shared
        else 0.0
    )
    first_marginal = Counter(first[item]["text_dependency"] for item in shared)
    second_marginal = Counter(second[item]["text_dependency"] for item in shared)
    expected = (
        sum(
            (first_marginal[label] / len(shared))
            * (second_marginal[label] / len(shared))
            for label in LABELS
        )
        if shared
        else 0.0
    )
    kappa = (observed - expected) / (1 - expected) if expected < 1 else None
    disagreements = [
        {
            "parallel_id": item,
            "annotator_1": first[item]["text_dependency"],
            "annotator_2": second[item]["text_dependency"],
            "review_1": first[item].get("review_flag", ""),
            "review_2": second[item].get("review_flag", ""),
            "note_1": first[item].get("note", ""),
            "note_2": second[item].get("note", ""),
        }
        for item in shared
        if first[item]["text_dependency"] != second[item]["text_dependency"]
    ]
    summary = {
        "annotator_1_file": str(first_path),
        "annotator_2_file": str(second_path),
        "annotator_1_labeled": len(first),
        "annotator_2_labeled": len(second),
        "shared_labeled_items": len(shared),
        "raw_agreement": observed,
        "expected_agreement": expected,
        "cohen_kappa": kappa,
        "disagreement_count": len(disagreements),
        "confusion": {
            f"{left}__{right}": confusion[(left, right)]
            for left in LABELS
            for right in LABELS
        },
    }
    return summary, disagreements


def main():
    parser = argparse.ArgumentParser(description="Summarize two blind REL annotation exports.")
    parser.add_argument("annotator_1", type=Path)
    parser.add_argument("annotator_2", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    summary, disagreements = summarize(args.annotator_1, args.annotator_2)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "agreement_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (args.output_dir / "disagreements.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        fields = [
            "parallel_id",
            "annotator_1",
            "annotator_2",
            "review_1",
            "review_2",
            "note_1",
            "note_2",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(disagreements)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
