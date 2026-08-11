from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from mpr_crosslocale.data.schema import LABELS
from mpr_crosslocale.interventions.rq4_contextual import (
    EXPECTED_SMOKE_ROWS,
    human_reference_map_from_original_controls,
    read_jsonl,
    validate_contextual_translation_rows,
)
from mpr_crosslocale.interventions.rq4_nllb import (
    load_rel_source_rows,
    write_csv_atomic,
)


def log_step(message: str) -> None:
    print(f"[{datetime.now().astimezone():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


def _flatten_options(prefix: str, options: dict[str, str]) -> dict[str, str]:
    return {f"{prefix}_option_{label}": str(options[label]) for label in LABELS}


def build_review_rows(
    translations: list[dict[str, Any]], by_endpoint: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    review_rows = []
    for index, translation in enumerate(
        sorted(
            translations,
            key=lambda row: (
                row["source_language"],
                row["target_language"],
                row["parallel_id"],
            ),
        ),
        start=1,
    ):
        human_id = str(translation["target_human_parallel_endpoint_id"])
        if human_id not in by_endpoint:
            raise ValueError(f"Missing human target endpoint: {human_id}")
        human = by_endpoint[human_id]
        review_rows.append(
            {
                "review_order": index,
                "translation_id": translation["translation_id"],
                "pair_id": translation["pair_id"],
                "parallel_id": translation["parallel_id"],
                "source_language": translation["source_language"],
                "target_language": translation["target_language"],
                "source_question_stem": translation["source_question_stem"],
                **_flatten_options("source", translation["source_options"]),
                "translated_question_stem": translation["translated_question_stem"],
                **_flatten_options("translated", translation["translated_options"]),
                "human_parallel_question_stem_reference_only": human["question_stem"],
                **_flatten_options("human_parallel_reference_only", human["options"]),
                "translation_status": translation["translation_status"],
                "translation_attempt_count": len(translation["translation_attempts"]),
                "hard_repair_attempted": int(translation["hard_repair_attempted"]),
                "semantic_repair_attempted": int(
                    translation["semantic_repair_attempted"]
                ),
                "semantic_repair_accepted": int(
                    translation["semantic_repair_accepted"]
                ),
                "initial_semantic_repair_reasons": json.dumps(
                    translation["initial_semantic_repair_reasons"],
                    ensure_ascii=False,
                ),
                "initial_semantic_repair_score": translation[
                    "initial_semantic_repair_score"
                ],
                "final_semantic_repair_reasons": json.dumps(
                    translation["final_semantic_repair_reasons"],
                    ensure_ascii=False,
                ),
                "final_semantic_repair_score": translation[
                    "final_semantic_repair_score"
                ],
                "hard_validation_errors": json.dumps(
                    translation["hard_validation_errors"], ensure_ascii=False
                ),
                "semantic_diagnostic_flags": json.dumps(
                    translation["semantic_diagnostic_flags"], ensure_ascii=False
                ),
                "manual_structure_pass_0_or_1": "",
                "manual_correct_target_language_0_or_1": "",
                "manual_spatial_relation_preserved_0_or_1": "",
                "manual_gross_semantic_corruption_0_or_1": "",
                "manual_overall_pass_0_or_1": "",
                "manual_note": "",
            }
        )
    return review_rows


def validate_review_rows(rows: list[dict[str, Any]]) -> None:
    if len(rows) != EXPECTED_SMOKE_ROWS:
        raise ValueError(f"Smoke review must contain exactly {EXPECTED_SMOKE_ROWS} rows.")
    counts = Counter((row["source_language"], row["target_language"]) for row in rows)
    if len(counts) != 30 or set(counts.values()) != {2}:
        raise ValueError(f"Smoke review must contain two rows per direction; counts={counts}")
    if len({row["translation_id"] for row in rows}) != len(rows):
        raise ValueError("Smoke review translation IDs must be unique.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Build the 60-row human smoke-review sheet after contextual generation."
    )
    parser.add_argument(
        "--translations",
        type=Path,
        default=Path(
            "data/derived/interventions/rel_qwen3_contextual_smoke_v4_60.jsonl"
        ),
    )
    parser.add_argument(
        "--source-mode",
        choices=["original-controls", "raw-qas"],
        default="original-controls",
    )
    parser.add_argument(
        "--source-controls",
        type=Path,
        default=Path(
            "data/derived/interventions/rel_nllb_original_controls.jsonl"
        ),
    )
    parser.add_argument(
        "--annotation-manifest",
        type=Path,
        default=Path("../annotation/rel_text_dependency/data/pilot_manifest.json"),
    )
    parser.add_argument(
        "--qas-dir", type=Path, default=Path("data/raw/mpr_gui_bench/qas")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/derived/interventions/rel_qwen3_contextual_smoke_review_v4_60.csv"
        ),
    )
    args = parser.parse_args(argv)

    log_step(f"STEP 1/3 validating smoke translations: {args.translations}")
    translations = read_jsonl(args.translations)
    validate_contextual_translation_rows(
        translations, expected_count=EXPECTED_SMOKE_ROWS
    )
    log_step(
        "STEP 2/3 joining human-parallel text for review only: "
        f"source_mode={args.source_mode}"
    )
    if args.source_mode == "original-controls":
        if not args.source_controls.is_file():
            raise FileNotFoundError(
                f"Missing frozen original controls: {args.source_controls}. "
                "Run `git lfs pull` from the repository root."
            )
        with args.source_controls.open("rb") as handle:
            source_prefix = handle.read(80)
        if source_prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise RuntimeError(
                f"{args.source_controls} is still a Git LFS pointer. Run `git lfs pull`."
            )
        controls = read_jsonl(args.source_controls)
        by_endpoint = human_reference_map_from_original_controls(controls)
    else:
        source_rows = load_rel_source_rows(args.annotation_manifest, args.qas_dir)
        by_endpoint = {str(row["sample_id"]): row for row in source_rows}
    review_rows = build_review_rows(translations, by_endpoint)
    validate_review_rows(review_rows)
    log_step(f"STEP 3/3 writing UTF-8 review CSV: {args.output}")
    write_csv_atomic(args.output, review_rows)
    print(
        json.dumps(
            {
                "status": "complete",
                "rows": len(review_rows),
                "directions": 30,
                "rows_per_direction": 2,
                "hard_failure_rows": sum(
                    not row["translation_analysis_eligible"] for row in translations
                ),
                "semantic_diagnostic_flag_rows": sum(
                    bool(row["semantic_diagnostic_flags"]) for row in translations
                ),
                "output": args.output.as_posix(),
                "note": (
                    "Human-parallel text is joined only after translation generation and is "
                    "for smoke review, never translator input or correction."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
