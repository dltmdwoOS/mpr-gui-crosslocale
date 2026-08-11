from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from mpr_crosslocale.interventions.rq4_nllb import (
    DEPENDENCY_LEVELS,
    EXPECTED_INTERVENTION_ROWS,
    file_sha256,
    normalized_image_assets,
    pair_id,
    read_jsonl,
    write_jsonl_atomic,
)


def log_step(message: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


INVARIANT_RESULT_FIELDS = (
    "parallel_id",
    "gold_label",
    "gui_language",
    "model_id",
    "model_family",
    "model_revision",
    "processor_revision",
    "prompt_profile",
    "system_prompt_mode",
    "system_prompt_language",
    "system_prompt",
    "prompt_template_version",
    "precision",
    "attn_implementation",
    "vision_token_limit",
    "processor_profile",
    "min_pixels",
    "max_pixels",
    "input_size",
    "min_num",
    "max_num",
    "use_thumbnail",
    "trust_remote_code",
    "use_flash_attn",
    "num_images",
    "seed",
)


def _read_annotations(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 366:
        raise ValueError(f"Final REL annotation must contain 366 rows; found {len(rows)}.")
    labels = {str(row["parallel_id"]): str(row["text_dependency"]).strip().lower() for row in rows}
    if len(labels) != 366 or set(labels.values()) != DEPENDENCY_LEVELS:
        raise ValueError("Final REL annotation IDs or labels are invalid.")
    if Counter(labels.values()) != Counter({"dependent": 302, "independent": 64}):
        raise ValueError("Final REL annotation counts differ from the adjudicated freeze.")
    return labels


def _original_success_rows(path: Path) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        if row.get("dimension") != "rel":
            continue
        source_language = str(row["question_language"])
        gui_language = str(row["gui_language"])
        if source_language == gui_language:
            continue
        if row.get("status") != "success":
            raise ValueError(f"Original canonical run contains a failed REL mismatch: {row['input_id']}")
        key = pair_id(str(row["parallel_id"]), source_language, gui_language)
        if key in selected:
            raise ValueError(f"Duplicate original REL mismatch pair: {key}")
        selected[key] = row
    if len(selected) != EXPECTED_INTERVENTION_ROWS:
        raise ValueError(
            f"Original run must provide {EXPECTED_INTERVENTION_ROWS} REL mismatches; "
            f"found {len(selected)}."
        )
    return selected


def _intervention_success_rows(path: Path) -> tuple[dict[str, dict[str, Any]], int]:
    successes: dict[str, dict[str, Any]] = {}
    failed_attempts = 0
    for row in read_jsonl(path):
        if row.get("status") != "success":
            failed_attempts += 1
            continue
        key = str(row["pair_id"])
        if key in successes:
            raise ValueError(f"Duplicate successful intervention pair: {key}")
        successes[key] = row
    if len(successes) != EXPECTED_INTERVENTION_ROWS:
        raise ValueError(
            f"Intervention result must provide {EXPECTED_INTERVENTION_ROWS} successful pairs; "
            f"found {len(successes)} (failed attempts={failed_attempts})."
        )
    return successes, failed_attempts


def _generation_correct(row: dict[str, Any]) -> int:
    expected = int(row.get("parsed_generated_label") == row.get("gold_label"))
    if "generation_correct" in row and int(row["generation_correct"]) != expected:
        raise ValueError(f"generation_correct is inconsistent for {row.get('input_id')}.")
    return expected


def validate_and_combine(
    original_path: Path,
    intervention_path: Path,
    intervention_inputs_path: Path,
    annotation_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    annotations = _read_annotations(annotation_path)
    originals = _original_success_rows(original_path)
    intervention_rows, failed_attempts = _intervention_success_rows(intervention_path)
    inputs = {row["pair_id"]: row for row in read_jsonl(intervention_inputs_path)}
    if len(inputs) != EXPECTED_INTERVENTION_ROWS:
        raise ValueError("Intervention input artifact must contain 10,980 unique pairs.")
    pair_universe = set(originals)
    if pair_universe != set(intervention_rows) or pair_universe != set(inputs):
        raise ValueError(
            "Original, intervention result, and intervention input pair universes differ."
        )
    conditions = {str(row.get("condition")) for row in inputs.values()}
    if conditions == {"nllb_query_aligned"}:
        intervention_label = "nllb"
    elif conditions == {"contextual_query_aligned"}:
        intervention_label = "contextual"
    else:
        raise ValueError(f"Unexpected intervention condition set: {sorted(conditions)}")

    combined: list[dict[str, Any]] = []
    pair_audits: list[dict[str, Any]] = []
    for key in sorted(pair_universe):
        original = originals[key]
        intervention = intervention_rows[key]
        input_row = inputs[key]
        source_language = str(original["question_language"])
        gui_language = str(original["gui_language"])

        invariant_differences = []
        for field in INVARIANT_RESULT_FIELDS:
            # Older Qwen raw rows did not record every processor field. Compare
            # every invariant that is actually present in the frozen original.
            if field in original and original.get(field) != intervention.get(field):
                invariant_differences.append(field)
        if source_language != intervention.get("source_question_language"):
            invariant_differences.append("source_question_language")
        if original.get("source_question_id") != intervention.get("source_question_id"):
            invariant_differences.append("source_question_id")
        if original.get("image_paths") != intervention.get("image_paths"):
            invariant_differences.append("image_paths")
        if intervention.get("input_id") != input_row.get("input_id"):
            invariant_differences.append("input_id_vs_frozen_input")
        if normalized_image_assets(original["image_paths"]) != normalized_image_assets(
            input_row["image_paths"]
        ):
            invariant_differences.append("input_image_asset")
        if original.get("gold_label") != input_row.get("gold_label"):
            invariant_differences.append("input_gold_label")
        if original.get("parallel_id") != input_row.get("parallel_id"):
            invariant_differences.append("input_parallel_id")
        if source_language != input_row.get("source_question_language"):
            invariant_differences.append("input_source_language")
        if gui_language != input_row.get("gui_language"):
            invariant_differences.append("input_gui_language")
        if invariant_differences:
            raise ValueError(
                f"Forbidden original-intervention metadata difference for {key}: "
                f"{sorted(set(invariant_differences))}"
            )

        dependency = annotations[str(original["parallel_id"])]
        common = {
            "pair_id": key,
            "parallel_id": original["parallel_id"],
            "source_question_language": source_language,
            "gui_language": gui_language,
            "text_dependency": dependency,
            "gold_label": original["gold_label"],
            "model_id": original["model_id"],
            "model_revision": original["model_revision"],
            "translation_status": input_row["translation_status"],
            "translation_failed_fields": json.dumps(
                input_row.get("translation_failed_fields", []), ensure_ascii=False
            ),
            "semantic_diagnostic_flags": json.dumps(
                input_row.get("semantic_diagnostic_flags", []), ensure_ascii=False
            ),
            "translation_analysis_eligible": int(
                input_row["translation_analysis_eligible"]
            ),
        }
        combined.extend(
            [
                {
                    **common,
                    "intervention": "original",
                    "generation_correct": _generation_correct(original),
                    "parse_success": int(bool(original.get("parse_success"))),
                    "input_id": original["input_id"],
                },
                {
                    **common,
                    "intervention": intervention_label,
                    "generation_correct": _generation_correct(intervention),
                    "parse_success": int(bool(intervention.get("parse_success"))),
                    "input_id": intervention["input_id"],
                },
            ]
        )
        pair_audits.append(
            {
                "pair_id": key,
                "parallel_id": original["parallel_id"],
                "source_language": source_language,
                "gui_language": gui_language,
                "image_paths_equal": 1,
                "gold_label_equal": 1,
                "parallel_id_equal": 1,
                "source_language_equal": 1,
                "gui_language_equal": 1,
                "model_protocol_equal": 1,
                "translation_status": input_row["translation_status"],
                "translation_failed_fields": json.dumps(
                    input_row.get("translation_failed_fields", []), ensure_ascii=False
                ),
                "semantic_diagnostic_flags": json.dumps(
                    input_row.get("semantic_diagnostic_flags", []), ensure_ascii=False
                ),
                "translation_analysis_eligible": int(
                    input_row["translation_analysis_eligible"]
                ),
                "forbidden_metadata_differences": "[]",
                "audit_pass": 1,
            }
        )

    if len(combined) != EXPECTED_INTERVENTION_ROWS * 2:
        raise AssertionError("Combined RQ4 table must contain exactly 21,960 rows.")
    pair_counts = Counter(row["pair_id"] for row in combined)
    condition_counts = Counter((row["pair_id"], row["intervention"]) for row in combined)
    if set(pair_counts.values()) != {2} or set(condition_counts.values()) != {1}:
        raise ValueError(
            "Each pair must contain exactly one original and one intervention observation."
        )

    summary = {
        "status": "pass",
        "original_input": original_path.as_posix(),
        "intervention_label": intervention_label,
        "intervention_input": intervention_path.as_posix(),
        "frozen_intervention_inputs": intervention_inputs_path.as_posix(),
        "annotation_input": annotation_path.as_posix(),
        "original_sha256": file_sha256(original_path),
        "intervention_sha256": file_sha256(intervention_path),
        "intervention_inputs_sha256": file_sha256(intervention_inputs_path),
        "annotation_sha256": file_sha256(annotation_path),
        "pair_ids": EXPECTED_INTERVENTION_ROWS,
        "combined_rows": EXPECTED_INTERVENTION_ROWS * 2,
        "failed_intervention_attempts_retained_outside_analysis": failed_attempts,
        "pair_metadata_diff_failures": 0,
        "translation_status_counts": dict(
            Counter(row["translation_status"] for row in inputs.values())
        ),
        "analysis_ineligible_translation_pairs": sum(
            not bool(row["translation_analysis_eligible"])
            for row in inputs.values()
        ),
        "dependency_counts": dict(Counter(annotations.values())),
        "gee_sensitivity": "intentionally_not_implemented_in_current_scope",
    }
    return combined, pair_audits, summary


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate original-intervention pairing and build the 21,960-row RQ4 table."
        )
    )
    parser.add_argument("--original-results", type=Path, required=True)
    parser.add_argument(
        "--intervention-results", "--nllb-results", dest="intervention_results",
        type=Path, required=True
    )
    parser.add_argument(
        "--intervention-inputs", "--nllb-inputs", dest="intervention_inputs",
        type=Path,
        default=Path("data/derived/interventions/rel_nllb_inputs.jsonl"),
    )
    parser.add_argument(
        "--annotations",
        type=Path,
        default=Path("../annotation/rel_text_dependency/outputs/rel_annotations_integrated_366.csv"),
    )
    parser.add_argument("--combined-out", type=Path, required=True)
    parser.add_argument("--pair-audit-out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    args = parser.parse_args(argv)

    log_step("STEP 1/4 reading frozen original, intervention result, inputs, and annotations")
    log_step("STEP 2/4 validating 10,980 exact pairs and immutable metadata")
    combined, pair_audits, summary = validate_and_combine(
        args.original_results,
        args.intervention_results,
        args.intervention_inputs,
        args.annotations,
    )
    log_step("STEP 3/4 building the paired 21,960-row GLMM table")
    _write_csv(args.combined_out, combined)
    write_jsonl_atomic(args.pair_audit_out, pair_audits)
    log_step("STEP 4/4 writing pair audit and validation summary")
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    log_step("COMPLETE: pair_metadata_diff_failures=0")


if __name__ == "__main__":
    main()
