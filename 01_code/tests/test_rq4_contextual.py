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
    build_contextual_plan_from_original_controls,
    build_semantic_repair_prompt,
    build_user_prompt,
    select_smoke_rows,
    semantic_diagnostic_flags,
    semantic_repair_reasons,
    semantic_repair_score,
    should_accept_semantic_repair,
    translation_payload,
    validate_contextual_translation_rows,
    validate_structured_output,
)
from mpr_crosslocale.interventions.rq4_nllb import load_rel_source_rows, read_jsonl

ANNOTATION_MANIFEST = Path("../annotation/rel_text_dependency/data/pilot_manifest.json")
# This checkout retains a legacy local QAS mirror only for equivalence testing.
# Production/default execution uses the Git-LFS original controls instead.
QAS_DIR = Path("data/raw/mpr_gui_bench_qas/qas")
ORIGINAL_CONTROLS = Path(
    "data/derived/interventions/rel_nllb_original_controls.jsonl"
)


def _plan() -> list[dict]:
    return [
        {
            **row,
            "translation_source_kind": "frozen_original_controls",
            "translation_source_path": ORIGINAL_CONTROLS.as_posix(),
            "translation_source_sha256": "test-source-sha256",
        }
        for row in build_contextual_plan_from_original_controls(
            read_jsonl(ORIGINAL_CONTROLS)
        )
    ]


def test_frozen_controls_reconstruct_the_same_translation_content_as_raw_qas() -> None:
    controls_plan = _plan()
    qas_plan = build_contextual_plan(
        load_rel_source_rows(ANNOTATION_MANIFEST, QAS_DIR)
    )
    content_fields = (
        "pair_id",
        "parallel_id",
        "source_language",
        "target_language",
        "source_question_sample_id",
        "gui_sample_id",
        "source_question_raw",
        "source_question_stem",
        "source_options",
        "option_order",
        "gold_label",
        "image_paths",
    )
    by_pair = {row["pair_id"]: row for row in qas_plan}
    assert set(by_pair) == {row["pair_id"] for row in controls_plan}
    for control_row in controls_plan:
        qas_row = by_pair[control_row["pair_id"]]
        assert {key: control_row[key] for key in content_fields} == {
            key: qas_row[key] for key in content_fields
        }


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
    flags = semantic_diagnostic_flags(row, parsed)
    reasons = semantic_repair_reasons(row, parsed, flags)
    score = semantic_repair_score(reasons)
    primary_attempt = {
        "attempt": 0,
        "attempt_kind": "primary",
        "raw_output": _valid_raw(row),
        "parsed_output": parsed,
        "hard_validation_errors": [],
        "runtime_ms_approx": 0,
        "selected_as_final": True,
    }
    rejected_attempt = {
        **primary_attempt,
        "attempt": 1,
        "attempt_kind": "semantic_repair",
        "semantic_diagnostic_flags": flags,
        "semantic_repair_reasons": reasons,
        "semantic_repair_score": score,
        "semantic_repair_accepted": False,
        "selected_as_final": False,
    }
    return {
        **row,
        "translated_question_stem": parsed["question_stem"],
        "translated_options": parsed["options"],
        "translated_question_raw": row["source_question_raw"],
        "translator_model_id": "Qwen/Qwen3-8B",
        "translator_revision": "47719a242beab8f9aecc40ce3928b034dd5dd559",
        "translation_method": "full_mcq_contextual_structured_json",
        "prompt_template_version": "rq4_contextual_translation_v4",
        "translation_generation_config": {
            "do_sample": False,
            "num_beams": 1,
            "max_new_tokens": 512,
        },
        "translation_status": "eligible_after_rejected_semantic_repair",
        "translation_attempts": [primary_attempt, rejected_attempt],
        "hard_validation_errors": [],
        "semantic_diagnostic_flags": flags,
        "hard_repair_attempted": False,
        "semantic_repair_attempted": True,
        "semantic_repair_accepted": False,
        "initial_semantic_repair_reasons": reasons,
        "initial_semantic_repair_score": score,
        "final_semantic_repair_reasons": reasons,
        "final_semantic_repair_score": score,
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


def test_numeric_validator_handles_cjk_boundaries_and_named_months() -> None:
    row = _plan()[0]
    phone_row = dict(row)
    phone_row["source_question_stem"] = "+86 162 6746 0018の下にある項目は何ですか？"
    translated_phone = {
        "question_stem": "What item is below +86 162 6746 0018?",
        "options": phone_row["source_options"],
    }
    _, errors = validate_structured_output(
        json.dumps(translated_phone, ensure_ascii=False), phone_row
    )
    assert errors == []

    date_row = dict(row)
    date_row["source_question_stem"] = "日付「2025年6月11日水曜日」の下は何ですか？"
    translated_date = {
        "question_stem": 'What is below the date "Wednesday, June 11, 2025"?',
        "options": date_row["source_options"],
    }
    _, errors = validate_structured_output(
        json.dumps(translated_date, ensure_ascii=False), date_row
    )
    assert errors == []

    missing_number = {
        "question_stem": "What item is below this number?",
        "options": date_row["source_options"],
    }
    standalone_row = dict(row)
    standalone_row["source_question_stem"] = "What item is below 10?"
    _, errors = validate_structured_output(json.dumps(missing_number), standalone_row)
    assert any(error.startswith("number_tokens_changed") for error in errors)

    hourly_row = dict(row)
    hourly_row["source_options"] = {
        "A": "1時間ごとの天気予報",
        "B": "Map",
        "C": "10日間天気予報",
        "D": "Search",
    }
    hourly_translation = {
        "question_stem": hourly_row["source_question_stem"],
        "options": {
            "A": "每小时天气预报",
            "B": "Map",
            "C": "10日天气预报",
            "D": "Search",
        },
    }
    _, errors = validate_structured_output(
        json.dumps(hourly_translation, ensure_ascii=False), hourly_row
    )
    assert errors == []


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


def test_semantic_checks_flag_opposition_and_untranslated_options() -> None:
    row = dict(_plan()[0])
    row["source_language"] = "en"
    row["target_language"] = "th"
    row["source_question_stem"] = "Which item is directly above the button?"
    row["source_options"] = {
        "A": "Delete",
        "B": "Select",
        "C": "Insert",
        "D": "Join",
    }
    translated = {
        "question_stem": "รายการใดอยู่ตรงข้ามกับปุ่ม?",
        "options": row["source_options"],
    }
    flags = semantic_diagnostic_flags(row, translated)
    assert "spatial_opposition_introduced" in flags
    assert "multiple_options_unchanged:4" in flags
    reasons = semantic_repair_reasons(row, translated, flags)
    assert "spatial_opposition_introduced" in reasons
    assert any(reason.startswith("translatable_options_unchanged") for reason in reasons)
    assert semantic_repair_score(reasons) > 0
    repair_prompt = build_semantic_repair_prompt(
        row, json.dumps(translated, ensure_ascii=False), reasons
    )
    assert "Source relation categories detected for preservation: above, direct" in repair_prompt

    corrected = {
        "question_stem": "รายการใดอยู่เหนือปุ่มโดยตรง?",
        "options": {"A": "ลบ", "B": "เลือก", "C": "แทรก", "D": "รวม"},
    }
    corrected_reasons = semantic_repair_reasons(row, corrected)
    assert should_accept_semantic_repair(reasons, [], corrected_reasons)
    assert not should_accept_semantic_repair(
        reasons, ["number_tokens_changed:A:['1']->[]"], []
    )


def test_mock_full_artifact_builds_exact_pair_audit() -> None:
    translated = [_mock_translated_row(row) for row in _plan()]
    validate_contextual_translation_rows(
        translated, expected_count=EXPECTED_INTERVENTION_ROWS
    )
    originals, interventions, audits = build_inputs(translated)
    assert len(originals) == len(interventions) == len(audits) == 10_980
    assert all(row["audit_pass"] == 1 for row in audits)
    assert all(row["condition"] == "contextual_query_aligned" for row in interventions)
