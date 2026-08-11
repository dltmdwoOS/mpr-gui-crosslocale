from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from mpr_crosslocale.data.schema import LABELS
from mpr_crosslocale.interventions.rq4_nllb import (
    ALLOWED_INPUT_DIFF_FIELDS,
    EXPECTED_INTERVENTION_ROWS,
    canonical_json_sha256,
    read_jsonl,
    top_level_diff,
    validate_translation_rows,
    write_csv_atomic,
    write_jsonl_atomic,
)


def log_step(message: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


def build_inputs(
    translations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    original_controls: list[dict[str, Any]] = []
    intervention_inputs: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []

    for translation in sorted(translations, key=lambda row: row["pair_id"]):
        source_language = str(translation["source_language"])
        target_language = str(translation["target_language"])
        common = {
            "pair_id": translation["pair_id"],
            "parallel_id": translation["parallel_id"],
            "semantic_item_id": translation["parallel_id"],
            "dimension": "rel",
            "source_question_language": source_language,
            "gui_language": target_language,
            "question_sample_id": translation["source_question_sample_id"],
            "gui_sample_id": translation["gui_sample_id"],
            "source_qas_file": translation["source_qas_file"],
            "source_qas_line": translation["source_qas_line"],
            "source_matched_endpoint_id": translation["source_matched_endpoint_id"],
            "target_human_parallel_endpoint_id": translation[
                "target_human_parallel_endpoint_id"
            ],
            "original_matched": False,
            "matched": False,
            "option_order": list(translation["option_order"]),
            "answer_raw": translation["answer_raw"],
            "gold_label": translation["gold_label"],
            "image_paths": list(translation["image_paths"]),
            "num_images": int(translation["num_images"]),
            "frame_order": translation["frame_order"],
        }
        original = {
            **common,
            "input_id": f"rq4_original::{translation['pair_id']}",
            "condition": "original_mismatch",
            "question_language": source_language,
            "effective_question_language": source_language,
            "language_aligned_after_intervention": False,
            "question_raw": translation["source_question_raw"],
            "question_stem": translation["source_question_stem"],
            "options": translation["source_options"],
        }
        intervention = {
            **common,
            "input_id": f"rq4_nllb::{translation['pair_id']}",
            "condition": "nllb_query_aligned",
            "question_language": target_language,
            "effective_question_language": target_language,
            "language_aligned_after_intervention": True,
            "question_raw": translation["translated_question_raw"],
            "question_stem": translation["translated_question_stem"],
            "options": translation["translated_options"],
            "translation_id": translation["translation_id"],
            "translator_model_id": translation["translator_model_id"],
            "translator_revision": translation["translator_revision"],
            "translator_src_code": translation["translator_src_code"],
            "translator_tgt_code": translation["translator_tgt_code"],
            "translation_generation_config": translation["translation_generation_config"],
            "translation_status": translation["translation_status"],
            "translation_retry_events": translation["translation_retry_events"],
            "translation_failed_fields": translation["translation_failed_fields"],
            "translation_analysis_eligible": translation[
                "translation_analysis_eligible"
            ],
        }

        changed_fields = top_level_diff(original, intervention)
        unexpected = sorted(set(changed_fields) - ALLOWED_INPUT_DIFF_FIELDS)
        invariant_checks = {
            "image_paths_equal": original["image_paths"] == intervention["image_paths"],
            "gold_label_equal": original["gold_label"] == intervention["gold_label"],
            "parallel_id_equal": original["parallel_id"] == intervention["parallel_id"],
            "source_language_equal": (
                original["source_question_language"]
                == intervention["source_question_language"]
            ),
            "gui_language_equal": original["gui_language"] == intervention["gui_language"],
            "option_order_equal": original["option_order"] == intervention["option_order"],
            "source_question_id_equal": (
                original["question_sample_id"] == intervention["question_sample_id"]
            ),
            "gui_sample_id_equal": original["gui_sample_id"] == intervention["gui_sample_id"],
        }
        if unexpected or not all(invariant_checks.values()):
            raise ValueError(
                f"Pair metadata construction audit failed for {translation['pair_id']}: "
                f"unexpected={unexpected}, invariants={invariant_checks}"
            )
        if set(intervention["options"]) != set(LABELS):
            raise ValueError(f"NLLB input options are not exactly A-D: {translation['pair_id']}")

        original_controls.append(original)
        intervention_inputs.append(intervention)
        audits.append(
            {
                "pair_id": translation["pair_id"],
                "parallel_id": translation["parallel_id"],
                "source_language": source_language,
                "gui_language": target_language,
                "translation_status": translation["translation_status"],
                "translation_failed_fields": json.dumps(
                    translation["translation_failed_fields"], ensure_ascii=False
                ),
                "translation_analysis_eligible": int(
                    translation["translation_analysis_eligible"]
                ),
                "changed_fields": json.dumps(changed_fields, ensure_ascii=False),
                "unexpected_changed_fields": json.dumps(unexpected, ensure_ascii=False),
                **{key: int(value) for key, value in invariant_checks.items()},
                "original_control_sha256": canonical_json_sha256(original),
                "nllb_input_sha256": canonical_json_sha256(intervention),
                "audit_pass": 1,
            }
        )

    validate_built_inputs(original_controls, intervention_inputs, audits)
    return original_controls, intervention_inputs, audits


def validate_built_inputs(
    originals: list[dict[str, Any]],
    interventions: list[dict[str, Any]],
    audits: list[dict[str, Any]],
) -> None:
    if not (
        len(originals) == len(interventions) == len(audits) == EXPECTED_INTERVENTION_ROWS
    ):
        raise ValueError("RQ4 input artifacts must each contain exactly 10,980 rows.")
    for label, rows in (("original", originals), ("nllb", interventions)):
        input_ids = [str(row["input_id"]) for row in rows]
        pair_ids = [str(row["pair_id"]) for row in rows]
        if len(input_ids) != len(set(input_ids)) or len(pair_ids) != len(set(pair_ids)):
            raise ValueError(f"Duplicate ID in {label} input artifact.")
    if {row["pair_id"] for row in originals} != {row["pair_id"] for row in interventions}:
        raise ValueError("Original and NLLB pair universes differ.")
    if any(int(row["audit_pass"]) != 1 for row in audits):
        raise ValueError("At least one pair metadata diff audit failed.")
    if any("text_dependency" in row for row in interventions):
        raise ValueError("Intervention construction must remain blind to text_dependency.")
    if any(
        row["translation_status"] == "failed_empty_after_retry"
        and row["translation_analysis_eligible"] is not False
        for row in interventions
    ):
        raise ValueError("Failed translations must be marked analysis-ineligible.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Build strict original-control and NLLB intervention VLM inputs."
    )
    parser.add_argument(
        "--translations",
        type=Path,
        default=Path("data/derived/interventions/rel_nllb_translations.jsonl"),
    )
    parser.add_argument(
        "--nllb-inputs-out",
        type=Path,
        default=Path("data/derived/interventions/rel_nllb_inputs.jsonl"),
    )
    parser.add_argument(
        "--original-controls-out",
        type=Path,
        default=Path("data/derived/interventions/rel_nllb_original_controls.jsonl"),
    )
    parser.add_argument(
        "--pair-diff-audit-out",
        type=Path,
        default=Path("data/derived/interventions/rel_nllb_pair_metadata_diff.csv"),
    )
    args = parser.parse_args(argv)

    log_step(f"STEP 1/4 reading translation artifact: {args.translations}")
    translations = read_jsonl(args.translations)
    log_step(f"STEP 2/4 validating {len(translations)} translation rows")
    validate_translation_rows(translations)
    log_step("STEP 3/4 building original controls, NLLB inputs, and pair metadata diff")
    originals, interventions, audits = build_inputs(translations)
    log_step("STEP 4/4 writing validated artifacts")
    write_jsonl_atomic(args.original_controls_out, originals)
    write_jsonl_atomic(args.nllb_inputs_out, interventions)
    write_csv_atomic(args.pair_diff_audit_out, audits)
    print(
        json.dumps(
            {
                "status": "complete",
                "rows": len(interventions),
                "pair_metadata_diff_failures": 0,
                "retry_recovered_rows": sum(
                    row["translation_status"] == "recovered_after_empty_retry"
                    for row in interventions
                ),
                "failed_translation_rows": sum(
                    row["translation_status"] == "failed_empty_after_retry"
                    for row in interventions
                ),
                "original_controls": args.original_controls_out.as_posix(),
                "nllb_inputs": args.nllb_inputs_out.as_posix(),
                "pair_diff_audit": args.pair_diff_audit_out.as_posix(),
            },
            indent=2,
        )
    )
    log_step("COMPLETE: pair_metadata_diff_failures=0")


if __name__ == "__main__":
    main()
