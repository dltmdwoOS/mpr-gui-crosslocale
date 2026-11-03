"""Checks for the frozen grounding response format and actual locked inputs."""

import json
from pathlib import Path

from followup_rel_4lang.grounding_eval.build_protocol_inputs import build
from followup_rel_4lang.grounding_eval.point_format import parse_point, score


def test_point_format_is_strict_and_uses_full_image_dimensions():
    box = [100, 50, 300, 150]
    result = score("(500, 500)", box, 400, 200)
    assert result == {
        "parsed_point_1000": [500, 500],
        "point_original_pixels": [200.0, 100.0],
        "valid_output": True,
        "point_in_gt_box": True,
    }
    assert score("(250, 250)", box, 400, 200)["point_in_gt_box"] is True
    for invalid in ("500,500", "(500.5, 500)", "(1001, 500)", "answer: (500, 500)",
                    "(500, 500) (500, 500)", "(-1, 500)"):
        assert parse_point(invalid) is None
        assert score(invalid, box, 400, 200)["point_in_gt_box"] is False


def test_grounding_inputs_keep_annotation_and_gold_out_of_prompts():
    grounding, mixed, controls, lock = build()
    assert len(grounding) == 1944
    assert len(mixed) == 3888
    assert len(controls) == 8
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
