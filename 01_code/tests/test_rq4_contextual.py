from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from mpr_crosslocale.interventions.build_rel_qwen3_contextual_inputs import (
    build_inputs,
)
from mpr_crosslocale.interventions.rq4_contextual import (
    EXPECTED_INTERVENTION_ROWS,
    EXPECTED_SMOKE_ROWS,
    build_contextual_plan,
    build_user_prompt,
    select_smoke_rows,
    semantic_diagnostic_flags,
    translation_payload,
    validate_contextual_translation_rows,
    validate_structured_output,
)
from mpr_crosslocale.interventions.rq4_nllb import load_rel_source_rows


ANNOTATION_MANIFEST = Path("../annotation/rel_text_dependency/data/pilot_manifest.json")
QAS_DIR = Path("data/raw/mpr_gui_bench_qas/qas")


def _plan() -> list[dict]:
    return build_contextual_plan(load_rel_source_rows(ANNOTATION_MANIFEST, QAS_DIR))


def _valid_raw(row: dict) -> str:
    return json.dumps(
        {
            "question_stem": row["source_question_stem"],
            "options": row["source_options"],
        },
        ensure_ascii=False,
    )


def _mock_translated_row(row: dict) -> dict:
    parsed, errors = validate_structured_output(_valid_raw(row), row)
    assert parsed is not None and not errors
    return {
        **row,
        "translated_question_stem": parsed["question_stem"],
        "translated_options": parsed["options"],
        "translated_question_raw": row["source_question_raw"],
        "translator_model_id": "Qwen/Qwen3-8B",
        "translator_revision": "47719a242beab8f9aecc40ce3928b034dd5dd559",
        "translation_method": "full_mcq_contextual_structured_json",
        "prompt_template_version": "rq4_contextual_translation_v2",
        "translation_generation_config": {
            "do_sample": False,
            "num_beams": 1,
            "max_new_tokens": 512,
        },
        "translation_status": "ok",
        "translation_attempts": [
            {
                "attempt": 0,
                "raw_output": _valid_raw(row),
                "parsed_output": parsed,
                "hard_validation_errors": [],
                "runtime_ms_approx": 0,
            }
        ],
        "hard_validation_errors": [],
        "semantic_diagnostic_flags": ["all_fields_unchanged"],
        "translation_analysis_eligible": True,
        "translator_runtime_batch_size": 2,
    }


def test_full_plan_and_smoke_are_balanced_and_dependency_blind() -> None:
    plan = _plan()
    assert len(plan) == EXPECTED_INTERVENTION_ROWS
    assert not any("text_dependency" in row for row in plan)
    smoke = select_smoke_rows(plan)
    assert len(smoke) == EXPECTED_SMOKE_ROWS
    assert set(
        Counter(
            (row["source_language"], row["target_language"]) for row in smoke
        ).values()
    ) == {2}


def test_translator_payload_hides_benchmark_and_analysis_fields() -> None:
    row = _plan()[0]
    payload = translation_payload(row)
    assert list(payload) == [
        "source_language",
        "target_language",
        "question_stem",
        "options",
    ]
    prompt = build_user_prompt(row)
    for hidden_key in (
        "gold_label",
        "image_paths",
        "gui_sample_id",
        "target_human_parallel_endpoint_id",
        "text_dependency",
    ):
        assert hidden_key not in prompt


def test_structured_validator_rejects_structure_and_invariant_breakage() -> None:
    row = _plan()[0]
    parsed, errors = validate_structured_output(_valid_raw(row), row)
    assert parsed is not None and errors == []

    bad_keys = json.dumps(
        {"question_stem": row["source_question_stem"], "options": {"B": "b", "A": "a", "C": "c", "D": "d"}}
    )
    _, errors = validate_structured_output(bad_keys, row)
    assert any(error.startswith("option_keys_or_order") for error in errors)

    numeric_row = dict(row)
    numeric_row["source_question_stem"] = "Which item is 20% above PDF 4?"
    numeric_row["source_options"] = {"A": "1", "B": "2", "C": "3", "D": "4"}
    translated = {
        "question_stem": "Which item is 30% above PDF 4?",
        "options": numeric_row["source_options"],
    }
    _, errors = validate_structured_output(json.dumps(translated), numeric_row)
    assert any(error.startswith("number_tokens_changed") for error in errors)


def test_semantic_checks_are_flags_not_hard_failures() -> None:
    row = _plan()[0]
    parsed = {
        "question_stem": row["source_question_stem"],
        "options": row["source_options"],
    }
    flags = semantic_diagnostic_flags(row, parsed)
    assert isinstance(flags, list)
    _, errors = validate_structured_output(json.dumps(parsed, ensure_ascii=False), row)
    assert errors == []


def test_mock_full_artifact_builds_exact_pair_audit() -> None:
    translated = [_mock_translated_row(row) for row in _plan()]
    validate_contextual_translation_rows(
        translated, expected_count=EXPECTED_INTERVENTION_ROWS
    )
    originals, interventions, audits = build_inputs(translated)
    assert len(originals) == len(interventions) == len(audits) == 10_980
    assert all(row["audit_pass"] == 1 for row in audits)
    assert all(row["condition"] == "contextual_query_aligned" for row in interventions)
