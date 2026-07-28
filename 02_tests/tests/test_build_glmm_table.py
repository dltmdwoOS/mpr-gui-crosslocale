from __future__ import annotations

import itertools

import pytest

from mpr_crosslocale.analysis.build_glmm_table import (
    LANGUAGES,
    build_table,
)


def _rows():
    for question_language, gui_language in itertools.product(LANGUAGES, LANGUAGES):
        yield {
            "input_id": f"item-1::{question_language}::{gui_language}",
            "parallel_id": "item-1",
            "status": "success",
            "question_language": question_language,
            "gui_language": gui_language,
            "dimension": "wf",
            "matched": question_language == gui_language,
            "gold_label": "A",
            "parsed_generated_label": "A" if question_language == "en" else "B",
            "scored_predicted_label": "A",
            "label_logprobs": {"A": -0.1, "B": -0.1, "C": -2.0, "D": -3.0},
            "label_token_ids": {"A": [20], "B": [10], "C": [30], "D": [40]},
            "parse_success": True,
            "generation_scoring_disagreement": question_language != "en",
            "correct": True,
            "model_id": "test/model",
        }


def test_build_table_derives_both_outcomes_and_validates_grid():
    table, summary = build_table(_rows(), expected_items=1)

    assert len(table) == 36
    assert sum(row["generation_correct"] for row in table) == 6
    assert sum(row["scoring_correct"] for row in table) == 36
    assert sum(row["scoring_correct_token_tiebreak"] for row in table) == 0
    assert all(row["scored_predicted_label_token_tiebreak"] == "B" for row in table)
    assert summary["top_label_ties"] == 36
    assert summary["generation_scoring_disagreements"] == 30
    assert summary["stored_correct_vs_scoring_mismatches"] == 0
    assert summary["configuration_values"]["model_id"] == ["test/model"]


def test_build_table_rejects_failed_rows_instead_of_silently_dropping():
    rows = list(_rows())
    rows[0]["status"] = "failed"

    with pytest.raises(ValueError, match="non-success"):
        build_table(rows, expected_items=1)


def test_build_table_rejects_inconsistent_stored_correct():
    rows = list(_rows())
    rows[0]["correct"] = False

    _, summary = build_table(rows, expected_items=1)
    assert summary["stored_correct_vs_scoring_mismatches"] == 1
