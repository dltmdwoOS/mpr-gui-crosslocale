"""Checks for the frozen grounding response format and actual locked inputs."""

import json
from pathlib import Path

from followup_rel_4lang.grounding_eval.build_protocol_inputs import build, render_qwen_user_prompt
from followup_rel_4lang.grounding_eval.point_format import (
    parse_internvl_box, parse_qwen_point, qwen_image_size_from_grid,
    score_internvl_box, score_qwen_point,
)
from followup_rel_4lang.grounding_eval.run_qwen_pilot import _load_phrase_descriptors, _trials


def test_qwen_point_uses_actual_model_pixels_and_original_image_for_scoring():
    box = [100, 50, 300, 150]
    assert qwen_image_size_from_grid([1, 152, 70]) == (980, 2128)
    result = score_qwen_point('[{"point_2d": [490, 1064]}]',
                              box, 400, 200, 980, 2128)
    assert result == {
        "parsed_point_model_pixels": [490, 1064],
        "point_original_pixels": [200.0, 100.0],
        "valid_output": True,
        "requested_format_adherent": True,
        "point_in_gt_box": True,
    }
    assert parse_qwen_point('{"point_2d": ["490", "1064"]}', 980, 2128) == (490, 1064)
    assert score_qwen_point('{"point_2d": ["490", "1064"]}', box, 400, 200,
                            980, 2128)["requested_format_adherent"] is False
    rendered = render_qwen_user_prompt('Find <ref>Search</ref> button.', 980, 2128)
    assert '980 pixels wide and 2128 pixels high' in rendered
    assert '[{"point_2d": [x, y]}]' in rendered
    assert 'Do not locate the element that the question asks for.' in rendered
    for invalid in (
        '(490, 1064)', '{"point_2d": [981, 1064]}',
        '{"point_2d": [490.5, 1064]}', '{"point_2d": [true, 1064]}',
        '{"point_2d": [-1, 1064]}', '{"point_2d": ["４９０", 1064]}',
        '{"point_2d": [490, 1064], "label": 5}',
        '[{"point_2d": [490, 1064]}, {"point_2d": [490, 1064]}]',
        '{"point_2d": [490, 1064], "bbox_2d": [1, 2, 3, 4]}',
        'answer: {"point_2d": [490, 1064]}',
    ):
        assert parse_qwen_point(invalid, 980, 2128) is None
        assert score_qwen_point(invalid, box, 400, 200, 980, 2128)["point_in_gt_box"] is False


def test_internvl_box_uses_documented_normalized_coordinates():
    box = [100, 50, 300, 150]
    result = score_internvl_box('<ref>the target</ref><box>[[250, 250, 750, 750]]</box>', box, 400, 200)
    assert result == {
        "parsed_box_1000": [250, 250, 750, 750],
        "box_original_pixels": [100.0, 50.0, 300.0, 150.0],
        "point_original_pixels": [200.0, 100.0],
        "valid_output": True,
        "point_in_gt_box": True,
        "bbox_iou": 1.0,
    }
    for invalid in (
        '(500, 500)', '<box>[[1001, 250, 750, 750]]</box>',
        '<box>[[750, 250, 250, 750]]</box>',
        'answer: <box>[[250, 250, 750, 750]]</box>',
        '<box>[[250, 250, 750, 750], [100, 100, 200, 200]]</box>',
    ):
        assert parse_internvl_box(invalid) is None
        assert score_internvl_box(invalid, box, 400, 200)["point_in_gt_box"] is False


def test_grounding_inputs_keep_annotation_and_gold_out_of_prompts():
    grounding, mixed, controls, lock = build()
    assert len(grounding) == 1944
    assert len(mixed) == 3888
    assert len(controls) == 8
    assert lock["schema"] == "rel-grounding-protocol-inputs-v3"
    assert sum(row["split"] == "main" for row in grounding) == 1896
    assert sum(row["split"] == "main" for row in mixed) == 3792
    assert all("bbox" not in row and "gold_answer" not in row for row in grounding)
    assert all(row["question_O"].count("<ref>") == row["question_R"].count("<ref>") == 1
               for row in grounding)
    assert lock["grounding_pair_counts"] == {"main": 1896, "pilot": 48}
    # This question repeats its reference word; the immutable span offset picks one occurrence.
    manifest = json.loads(Path("annotation/rel_grounding/data/full_manifest.json").read_text())
    repeated = next(
        (item["parallel_id"], lang)
        for item in manifest["items"] for lang, locale in item["locales"].items()
        if locale["question_stem"].count(locale["stem_span"]["text"]) > 1
    )
    relevant = [row for row in grounding if row["parallel_id"] == repeated[0]
                and row["query_language"] == repeated[1]]
    assert relevant and all(row["question_O"].count("<ref>") == 1 for row in relevant)


def test_pilot_only_referring_phrases_are_locked_source_question_substrings():
    grounding, _, controls, _ = build()
    pilot = [row for row in grounding if row["split"] == "pilot"]
    descriptors, template, descriptor_hash = _load_phrase_descriptors(controls, pilot)
    control_trials, pilot_trials = _trials(controls, pilot, descriptors)
    assert len(control_trials) == 8 and len(pilot_trials) == 96
    assert len(descriptor_hash) == 64
    assert '[{"point_2d": [x, y]}]' in template.format(
        descriptor="<ref>Search</ref>", model_width=980, model_height=2128,
    )
    assert all("Question:" not in trial["marked_stem"] for trial in pilot_trials)
