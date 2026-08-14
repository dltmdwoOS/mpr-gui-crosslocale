"""Build an exact-pair table for a direct RQ4 method comparison.

The existing RQ4 GLMM script expects a baseline named ``original``. This
builder extracts one validated intervention condition from each of two paired
tables, verifies that their pair universes and immutable metadata match, and
maps the requested baseline to that reserved analysis level. The original
condition names remain available in ``comparison_source_condition``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


EXPECTED_PAIRS = 10_980
INVARIANT_FIELDS = (
    "pair_id",
    "parallel_id",
    "source_question_language",
    "gui_language",
    "text_dependency",
    "gold_label",
    "model_id",
    "model_revision",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_condition(path: Path, condition: str) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["intervention"] == condition]
    selected = {row["pair_id"]: row for row in rows}
    if len(rows) != EXPECTED_PAIRS or len(selected) != EXPECTED_PAIRS:
        raise ValueError(
            f"{path}: expected {EXPECTED_PAIRS} unique {condition!r} rows; "
            f"found rows={len(rows)}, pairs={len(selected)}"
        )
    return selected


def build(
    baseline_path: Path,
    baseline_condition: str,
    treatment_path: Path,
    treatment_condition: str,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], dict[str, Any]]:
    baseline = read_condition(baseline_path, baseline_condition)
    treatment = read_condition(treatment_path, treatment_condition)
    if set(baseline) != set(treatment):
        raise ValueError("Baseline and treatment pair universes differ.")

    combined: list[dict[str, str]] = []
    dependency_items: dict[str, set[str]] = {
        "dependent": set(),
        "independent": set(),
    }
    for pair_id in sorted(baseline):
        left = baseline[pair_id]
        right = treatment[pair_id]
        differences = [field for field in INVARIANT_FIELDS if left[field] != right[field]]
        if differences:
            raise ValueError(f"Immutable metadata differs for {pair_id}: {differences}")
        dependency_items[left["text_dependency"]].add(left["parallel_id"])

        baseline_row = dict(left)
        baseline_row["intervention"] = "original"
        baseline_row["comparison_source_condition"] = baseline_condition
        treatment_row = dict(right)
        treatment_row["intervention"] = treatment_condition
        treatment_row["comparison_source_condition"] = treatment_condition
        combined.extend((baseline_row, treatment_row))

    condition_counts = Counter(row["intervention"] for row in combined)
    if condition_counts != Counter({"original": EXPECTED_PAIRS, treatment_condition: EXPECTED_PAIRS}):
        raise AssertionError(f"Unexpected output conditions: {condition_counts}")
    dependency_counts = {key: len(value) for key, value in dependency_items.items()}
    if dependency_counts != {"dependent": 302, "independent": 64}:
        raise ValueError(f"Unexpected annotation universe: {dependency_counts}")

    transitions: list[dict[str, Any]] = []
    for dependency in ("independent", "dependent"):
        counts = Counter()
        for pair_id in sorted(baseline):
            left = baseline[pair_id]
            right = treatment[pair_id]
            if left["text_dependency"] != dependency:
                continue
            before = int(left["generation_correct"])
            after = int(right["generation_correct"])
            label = (
                "both_correct" if before and after else
                "recovered_0_to_1" if not before and after else
                "harmed_1_to_0" if before and not after else
                "both_wrong"
            )
            counts[label] += 1
        transitions.append({
            "text_dependency": dependency,
            "both_wrong": counts["both_wrong"],
            "recovered_0_to_1": counts["recovered_0_to_1"],
            "harmed_1_to_0": counts["harmed_1_to_0"],
            "both_correct": counts["both_correct"],
            "net_recovered": counts["recovered_0_to_1"] - counts["harmed_1_to_0"],
        })

    audit = {
        "status": "pass",
        "estimand": f"{treatment_condition}-minus-{baseline_condition}",
        "analysis_baseline_level": "original",
        "analysis_treatment_level": treatment_condition,
        "baseline_source_condition": baseline_condition,
        "treatment_source_condition": treatment_condition,
        "pairs": EXPECTED_PAIRS,
        "rows": len(combined),
        "pair_metadata_diff_failures": 0,
        "dependency_item_counts": dependency_counts,
        "baseline_input": baseline_path.as_posix(),
        "baseline_input_sha256": file_sha256(baseline_path),
        "treatment_input": treatment_path.as_posix(),
        "treatment_input_sha256": file_sha256(treatment_path),
    }
    return combined, transitions, audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-paired", type=Path, required=True)
    parser.add_argument("--baseline-condition", required=True)
    parser.add_argument("--treatment-paired", type=Path, required=True)
    parser.add_argument("--treatment-condition", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-out", type=Path, required=True)
    parser.add_argument("--transition-out", type=Path)
    args = parser.parse_args()

    rows, transitions, audit = build(
        args.baseline_paired,
        args.baseline_condition,
        args.treatment_paired,
        args.treatment_condition,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    audit["output"] = args.output.as_posix()
    audit["output_sha256"] = file_sha256(args.output)
    args.audit_out.parent.mkdir(parents=True, exist_ok=True)
    args.audit_out.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.transition_out is not None:
        args.transition_out.parent.mkdir(parents=True, exist_ok=True)
        with args.transition_out.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(transitions[0]))
            writer.writeheader()
            writer.writerows(transitions)
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
