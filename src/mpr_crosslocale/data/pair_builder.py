from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CrossLocalePair:
    sample_id: str
    question_language: str
    gui_language: str
    condition: str


def directed_language_pairs(languages: list[str]) -> list[tuple[str, str]]:
    return [(lq, lg) for lq in languages for lg in languages if lq != lg]


def build_cross_locale_pair_rows(parallel_index: dict[str, Any]) -> list[dict[str, Any]]:
    languages = list(parallel_index["languages"])
    rows: list[dict[str, Any]] = []
    for entry in parallel_index["entries"]:
        if not entry["complete"]:
            continue
        samples = entry["samples"]
        for question_language, gui_language in directed_language_pairs(languages):
            question_sample = samples[question_language]
            mismatch_gui_sample = samples[gui_language]
            oracle_gui_sample = samples[question_language]
            rows.append(
                {
                    "pair_id": (
                        f"{entry['parallel_id']}::q={question_language}::"
                        f"gui={gui_language}"
                    ),
                    "parallel_id": entry["parallel_id"],
                    "question_language": question_language,
                    "gui_language": gui_language,
                    "condition": "raw_mismatch",
                    "question_sample_id": question_sample["sample_id"],
                    "mismatch_gui_sample_id": mismatch_gui_sample["sample_id"],
                    "oracle_gui_sample_id": oracle_gui_sample["sample_id"],
                    "gold_label": question_sample["gold_label"],
                    "gold_label_consistent": entry["gold_labels_consistent"],
                    "question_asset": question_sample["asset"],
                    "mismatch_gui_asset": mismatch_gui_sample["asset"],
                    "oracle_gui_asset": oracle_gui_sample["asset"],
                }
            )
    return rows
