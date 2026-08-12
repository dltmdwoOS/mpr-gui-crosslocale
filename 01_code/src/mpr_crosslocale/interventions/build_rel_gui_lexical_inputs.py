from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mpr_crosslocale.data.schema import LABELS
from mpr_crosslocale.interventions.rq4_contextual import (
    CONTEXTUAL_MODEL_ID,
    CONTEXTUAL_REVISION,
    EXPECTED_INTERVENTION_ROWS,
    read_jsonl,
    write_jsonl_atomic,
)
from mpr_crosslocale.interventions.rq4_gui_lexical import (
    LEXICAL_CONDITION,
    lexical_input_id,
    validate_lexical_translation_rows,
)
from mpr_crosslocale.interventions.rq4_nllb import top_level_diff, write_csv_atomic

ALLOWED_DIFFS = {
    "condition",
    "effective_question_language",
    "input_id",
    "language_aligned_after_intervention",
    "options",
    "question_language",
    "question_raw",
    "question_stem",
    "translation_id",
    "translator_model_id",
    "translator_revision",
    "translation_method",
    "prompt_template_version",
    "translation_generation_config",
    "translation_status",
    "translation_attempt_count",
    "translation_analysis_eligible",
    "semantic_diagnostic_flags",
    "token_invariant_diagnostic_flags",
    "visible_string_inventory_id",
    "visible_string_inventory_sha256",
    "visible_string_count",
    "inventory_extractor_model_id",
    "inventory_extractor_revision",
}


def build_inputs(
    translations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    validate_lexical_translation_rows(translations, EXPECTED_INTERVENTION_ROWS)
    originals = []
    interventions = []
    audits = []
    for row in sorted(translations, key=lambda value: value["pair_id"]):
        source_language = str(row["source_language"])
        target_language = str(row["target_language"])
        common = {
            "pair_id": row["pair_id"],
            "parallel_id": row["parallel_id"],
            "semantic_item_id": row["parallel_id"],
            "dimension": "rel",
            "source_question_language": source_language,
            "gui_language": target_language,
            "question_sample_id": row["source_question_sample_id"],
            "gui_sample_id": row["gui_sample_id"],
            "source_qas_file": row["source_qas_file"],
            "source_qas_line": row["source_qas_line"],
            "source_matched_endpoint_id": row["source_matched_endpoint_id"],
            "target_human_parallel_endpoint_id": row[
                "target_human_parallel_endpoint_id"
            ],
            "original_matched": False,
            "matched": False,
            "option_order": list(row["option_order"]),
            "answer_raw": row["answer_raw"],
            "gold_label": row["gold_label"],
            "image_paths": list(row["image_paths"]),
            "num_images": int(row["num_images"]),
            "frame_order": row["frame_order"],
        }
        original = {
            **common,
            "input_id": f"rq4_original::{row['pair_id']}",
            "condition": "original_mismatch",
            "question_language": source_language,
            "effective_question_language": source_language,
            "language_aligned_after_intervention": False,
            "question_raw": row["source_question_raw"],
            "question_stem": row["source_question_stem"],
            "options": row["source_options"],
        }
        intervention = {
            **common,
            "input_id": lexical_input_id(str(row["pair_id"])),
            "condition": LEXICAL_CONDITION,
            "question_language": target_language,
            "effective_question_language": target_language,
            "language_aligned_after_intervention": True,
            "question_raw": row["translated_question_raw"],
            "question_stem": row["translated_question_stem"],
            "options": row["translated_options"],
            "translation_id": row["translation_id"],
            "translator_model_id": CONTEXTUAL_MODEL_ID,
            "translator_revision": CONTEXTUAL_REVISION,
            "translation_method": row["translation_method"],
            "prompt_template_version": row["prompt_template_version"],
            "translation_generation_config": row["translation_generation_config"],
            "translation_status": row["translation_status"],
            "translation_attempt_count": len(row["translation_attempts"]),
            "translation_analysis_eligible": True,
            "semantic_diagnostic_flags": row["semantic_diagnostic_flags"],
            "token_invariant_diagnostic_flags": row[
                "token_invariant_diagnostic_flags"
            ],
            "visible_string_inventory_id": row["visible_string_inventory_id"],
            "visible_string_inventory_sha256": row[
                "visible_string_inventory_sha256"
            ],
            "visible_string_count": len(row["visible_strings"]),
            "inventory_extractor_model_id": row["inventory_extractor_model_id"],
            "inventory_extractor_revision": row["inventory_extractor_revision"],
        }
        changed = top_level_diff(original, intervention)
        unexpected = sorted(set(changed) - ALLOWED_DIFFS)
        invariants = {
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
        if unexpected or not all(invariants.values()):
            raise ValueError(
                f"GUI lexical pair metadata audit failed: {row['pair_id']}, "
                f"unexpected={unexpected}, invariants={invariants}"
            )
        if list(intervention["options"]) != list(LABELS):
            raise ValueError(f"Option keys/order changed: {row['pair_id']}")
        originals.append(original)
        interventions.append(intervention)
        audits.append(
            {
                "pair_id": row["pair_id"],
                "parallel_id": row["parallel_id"],
                "source_language": source_language,
                "gui_language": target_language,
                "changed_fields": json.dumps(changed, ensure_ascii=False),
                "unexpected_changed_fields": json.dumps(unexpected),
                **{name: int(value) for name, value in invariants.items()},
                "audit_pass": 1,
            }
        )
    return originals, interventions, audits


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Build strict paired downstream inputs for GUI lexical localization."
    )
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--inputs-out", type=Path, required=True)
    parser.add_argument("--original-controls-out", type=Path, required=True)
    parser.add_argument("--pair-diff-audit-out", type=Path, required=True)
    args = parser.parse_args(argv)

    print(f"STEP 1/4 reading lexical translations: {args.translations}", flush=True)
    rows = read_jsonl(args.translations)
    print(f"STEP 2/4 validating {len(rows)} frozen translations", flush=True)
    originals, interventions, audits = build_inputs(rows)
    print("STEP 3/4 exact pair metadata diff audit passed", flush=True)
    write_jsonl_atomic(args.original_controls_out, originals)
    write_jsonl_atomic(args.inputs_out, interventions)
    write_csv_atomic(args.pair_diff_audit_out, audits)
    print("STEP 4/4 complete", flush=True)
    print(
        json.dumps(
            {
                "status": "complete",
                "rows": len(interventions),
                "pair_metadata_diff_failures": 0,
                "inputs": args.inputs_out.as_posix(),
                "original_controls": args.original_controls_out.as_posix(),
                "pair_diff_audit": args.pair_diff_audit_out.as_posix(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
