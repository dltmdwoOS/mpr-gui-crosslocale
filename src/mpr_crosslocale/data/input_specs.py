from __future__ import annotations

from typing import Any

from mpr_crosslocale.data.pair_builder import directed_language_pairs
from mpr_crosslocale.data.schema import LANGUAGES


def build_canonical_inputs(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in manifest:
        rows.append(
            {
                "input_id": f"canonical::{row['sample_id']}",
                "condition": "canonical_matched",
                "sample_id": row["sample_id"],
                "parallel_id": row["parallel_id"],
                "question_language": row["language"],
                "gui_language": row["language"],
                "dimension": row["dimension"],
                "question_raw": row["question_raw"],
                "question_stem": row["question_stem"],
                "options": row["options"],
                "option_order": row["option_order"],
                "answer_raw": row["answer_raw"],
                "gold_label": row["gold_label"],
                "image_paths": row["image_paths"],
                "num_images": row["num_images"],
                "frame_order": row["frame_order"],
            }
        )
    return rows


def build_mismatch_inputs(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_parallel_language = {
        (str(row["parallel_id"]), str(row["language"])): row
        for row in manifest
    }
    languages = [language for language in LANGUAGES if any(row["language"] == language for row in manifest)]
    parallel_ids = sorted({str(row["parallel_id"]) for row in manifest})
    rows: list[dict[str, Any]] = []
    for parallel_id in parallel_ids:
        for question_language, gui_language in directed_language_pairs(languages):
            question_row = by_parallel_language[(parallel_id, question_language)]
            gui_row = by_parallel_language[(parallel_id, gui_language)]
            rows.append(
                {
                    "input_id": f"mismatch::{parallel_id}::q={question_language}::gui={gui_language}",
                    "condition": "raw_mismatch",
                    "parallel_id": parallel_id,
                    "question_sample_id": question_row["sample_id"],
                    "gui_sample_id": gui_row["sample_id"],
                    "oracle_sample_id": question_row["sample_id"],
                    "question_language": question_language,
                    "gui_language": gui_language,
                    "dimension": question_row["dimension"],
                    "question_source": "resolve_from_manifest.question_sample_id",
                    "answer_raw": question_row["answer_raw"],
                    "gold_label": question_row["gold_label"],
                    "image_paths": gui_row["image_paths"],
                    "num_images": gui_row["num_images"],
                    "frame_order": gui_row["frame_order"],
                }
            )
    return rows
