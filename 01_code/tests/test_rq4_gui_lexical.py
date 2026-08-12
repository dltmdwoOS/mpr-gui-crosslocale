from __future__ import annotations

import json

from mpr_crosslocale.interventions.rq4_gui_lexical import (
    FAILED_INVENTORY_POLICY,
    INVENTORY_REPAIR_SUFFIX,
    INVENTORY_REPAIR_SYSTEM_PROMPT,
    INVENTORY_SCHEMA_VERSION,
    LEXICAL_PROMPT_VERSION,
    LEXICAL_SYSTEM_PROMPT,
    build_lexical_semantic_repair_prompt,
    build_lexical_user_prompt,
    canonicalize_visible_strings,
    parse_visible_string_output,
    parse_visible_string_output_detailed,
    recover_truncated_repetition_prefix,
    validate_inventory_plan,
    validate_inventory_rows,
    validate_lexical_plan,
    validate_lexical_structured_output,
)


def test_inventory_plan_forbids_query_and_answer_content() -> None:
    row = {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "inventory_id": "endpoint::visible_strings_v1",
        "target_human_parallel_endpoint_id": "endpoint",
        "parallel_id": "rel::x",
        "target_language": "ja",
        "gui_sample_id": "gui",
        "image_paths": ["image.jpg"],
        "num_images": 1,
        "frame_order": None,
    }
    # The count guard is intentional; use repeated unique rows to exercise the
    # field-level leakage check without weakening the production invariant.
    rows = []
    for index in range(2196):
        copy = dict(row)
        copy["inventory_id"] = f"endpoint-{index}::visible_strings_v1"
        rows.append(copy)
    validate_inventory_plan(rows)
    rows[0]["gold_label"] = "A"
    try:
        validate_inventory_plan(rows)
    except ValueError as error:
        assert "leaked fields" in str(error)
    else:
        raise AssertionError("Gold leakage must fail inventory plan validation.")


def test_visible_string_parser_is_structure_strict_and_allows_empty_gui() -> None:
    parsed, errors = parse_visible_string_output(
        '{"visible_strings": ["設定", "名前を変更"]}'
    )
    assert parsed == ["設定", "名前を変更"]
    assert errors == []
    assert parse_visible_string_output('{"visible_strings": []}') == ([], [])
    assert parse_visible_string_output('{"text": ["設定"]}')[0] is None


def test_visible_string_parser_recovers_empty_null_and_text_objects() -> None:
    parsed, errors, events = parse_visible_string_output_detailed(
        '{"visible_strings": ["Clock", "", null, {"text": "Alarm"}]}'
    )
    assert parsed == ["Clock", "Alarm"]
    assert errors == []
    assert events == [
        "dropped_empty_string:1",
        "dropped_null:2",
        "unwrapped_text_object:3",
    ]


def test_inventory_repair_prevents_duplicate_loops_and_invalid_json_escaping() -> None:
    assert "Duplicates may be retained" not in INVENTORY_REPAIR_SYSTEM_PROMPT
    assert "Return at most 80 strings" in INVENTORY_REPAIR_SYSTEM_PROMPT
    assert "treat cells or keys as atomic strings" in INVENTORY_REPAIR_SYSTEM_PROMPT
    assert "named GUI controls, titles, tabs" in INVENTORY_REPAIR_SYSTEM_PROMPT
    assert "Do not output standalone day-of-month cells 1 through 31" in (
        INVENTORY_REPAIR_SYSTEM_PROMPT
    )
    assert "distinct visible string at most once" in INVENTORY_REPAIR_SUFFIX
    assert "never loop or repeat" in INVENTORY_REPAIR_SUFFIX
    assert "Escape every double quote, backslash" in INVENTORY_REPAIR_SUFFIX
    assert "Do not omit any distinct readable GUI word or label" in INVENTORY_REPAIR_SUFFIX
    assert "begin the array with named controls and tabs" in INVENTORY_REPAIR_SUFFIX


def test_truncated_repetition_recovery_is_narrow_and_deduplicates() -> None:
    raw = '{"visible_strings": ["Settings", ' + ', '.join(['"19"'] * 12) + ', "'
    parsed, events = recover_truncated_repetition_prefix(raw)
    assert parsed == ["Settings", "19"]
    assert events == [
        "closed_truncated_repetition_loop:12",
        "dropped_exact_duplicates:11",
    ]
    assert recover_truncated_repetition_prefix(
        '{"visible_strings": ["Jan", "1", "2", "3", "'
    ) == (None, [])


def test_visible_string_parser_repairs_only_parseable_inner_quote_drift() -> None:
    raw = r'{"visible_strings": ["starting with \"." (dot)", "Recent"]}'
    parsed, errors, events = parse_visible_string_output_detailed(raw)
    assert parsed == ['starting with "." (dot)', "Recent"]
    assert errors == []
    assert events and events[0].startswith("escaped_unquoted_inner_quotes:")


def test_failed_inventory_validation_remains_strict_by_default() -> None:
    failed = {
        "inventory_id": "endpoint::visible_strings_v1",
        "extractor_model_id": "Qwen/Qwen2.5-VL-7B-Instruct",
        "extractor_revision": "cc594898137f460bfe9f0759e9844b3ce807cfb5",
        "processor_use_fast": True,
        "processor_mode_explicit": True,
        "inventory_status": "failed_after_repair",
        "visible_strings": [],
        "query_content_exposed": False,
    }
    validate_inventory_rows([failed], expected_count=1, require_success=False)
    try:
        validate_inventory_rows([failed], expected_count=1)
    except ValueError as error:
        assert "Unsuccessful inventory row" in str(error)
    else:
        raise AssertionError("Stage 2 must reject a failed inventory.")


def test_lexical_plan_explicitly_includes_failed_inventory_without_partial_text() -> None:
    row = {
        "pair_id": "pair",
        "translation_id": "translation",
        "schema_version": "rq4-rel-gui-lexical-v3",
        "translation_method": "target_gui_lexical_evidence_contextual_translation",
        "inventory_status": "failed_after_repair",
        "visible_strings": [],
        "lexical_evidence_available": False,
        "inventory_failure_included": True,
        "inventory_failure_policy": FAILED_INVENTORY_POLICY,
        "inventory_default_analysis_included": True,
    }
    validate_lexical_plan([row], expected_count=1)
    row["visible_strings"] = ["partial unvalidated text"]
    try:
        validate_lexical_plan([row], expected_count=1)
    except ValueError as error:
        assert "Invalid failed-inventory inclusion" in str(error)
    else:
        raise AssertionError("Partial failed inventory must not reach Stage 2.")


def test_translator_inventory_is_deduplicated_and_has_no_reading_order() -> None:
    assert canonicalize_visible_strings(["Zulu", " alpha ", "ＡＬＰＨＡ", "Beta"]) == [
        "alpha",
        "Beta",
        "Zulu",
    ]


def _lexical_row() -> dict:
    return {
        "source_language": "en",
        "target_language": "ja",
        "visible_strings": ["設定", "名前を変更"],
        "source_question_stem": 'Which item is below "Settings"?',
        "source_options": {
            "A": "Find",
            "B": "Rename",
            "C": "Duplicate",
            "D": "Hide grid",
        },
    }


def test_lexical_prompt_exposes_inventory_but_not_image_gold_or_human_endpoint() -> None:
    prompt = build_lexical_user_prompt(_lexical_row())
    payload = json.loads(
        prompt.split("output JSON object.\n\n", 1)[1].split(
            "\n\nRequired output shape:", 1
        )[0]
    )
    assert payload["target_gui_visible_strings"] == ["設定", "名前を変更"]
    assert "image_paths" not in payload
    assert "gold_label" not in payload
    assert "human" not in json.dumps(payload).casefold()


def test_lexical_v3_prompt_explicitly_preserves_spatial_direction() -> None:
    assert LEXICAL_PROMPT_VERSION == "rq4_gui_lexical_translation_v3"
    assert "above must remain above" in LEXICAL_SYSTEM_PROMPT
    assert "ตรงข้าม means opposite" in LEXICAL_SYSTEM_PROMPT
    assert "MUST NOT be used to translate directly/immediately" in LEXICAL_SYSTEM_PROMPT


def test_lexical_semantic_repair_retains_inventory_without_layout() -> None:
    prompt = build_lexical_semantic_repair_prompt(
        _lexical_row(),
        '{"question_stem":"opposite"}',
        ["spatial_opposition_introduced"],
    )
    assert '"target_gui_visible_strings"' in prompt
    assert "spatial_opposition_introduced" in prompt
    assert "provides no layout information" in prompt


def test_lexical_validator_keeps_token_changes_as_diagnostics() -> None:
    raw = json.dumps(
        {
            "question_stem": "設定の下にある項目はどれですか？",
            "options": {
                "A": "検索",
                "B": "名前を変更",
                "C": "複製",
                "D": "グリッドを非表示",
            },
        },
        ensure_ascii=False,
    )
    parsed, hard, diagnostics = validate_lexical_structured_output(raw, _lexical_row())
    assert parsed is not None
    assert hard == []
    assert isinstance(diagnostics, list)
