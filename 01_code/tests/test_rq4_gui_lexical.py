from __future__ import annotations

import json

from mpr_crosslocale.interventions.rq4_gui_lexical import (
    INVENTORY_SCHEMA_VERSION,
    build_lexical_user_prompt,
    canonicalize_visible_strings,
    parse_visible_string_output,
    validate_inventory_plan,
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
