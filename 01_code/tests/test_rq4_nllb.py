from __future__ import annotations

import json
from pathlib import Path

import pytest

from mpr_crosslocale.interventions.build_rel_nllb_inputs import build_inputs
from mpr_crosslocale.inference.run_rel_nllb_intervention import (
    validate_intervention_inputs,
)
from mpr_crosslocale.interventions.rq4_nllb import (
    EXPECTED_INTERVENTION_ROWS,
    NLLB_LANGUAGE_CODES,
    NLLB_MODEL_ID,
    NLLB_REVISION,
    build_translation_plan,
    load_rel_source_rows,
    render_with_source_layout,
    validate_translation_rows,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
ANNOTATION_MANIFEST = (
    REPO_ROOT / "annotation" / "rel_text_dependency" / "data" / "pilot_manifest.json"
)
QAS_DIR = REPO_ROOT / "01_code" / "data" / "raw" / "mpr_gui_bench_qas" / "qas"


def test_span_preserving_renderer_round_trip():
    source = "  Question?  A: first   B: second C: third D: fourth  "
    rendered = render_with_source_layout(
        source,
        "Question?",
        {"A": "first", "B": "second", "C": "third", "D": "fourth"},
    )
    assert rendered == source


@pytest.mark.skipif(
    not ANNOTATION_MANIFEST.exists() or not QAS_DIR.exists(),
    reason="Frozen local REL source data are unavailable.",
)
def test_full_translation_plan_and_pair_diff_contract():
    source_rows = load_rel_source_rows(ANNOTATION_MANIFEST, QAS_DIR)
    plan = build_translation_plan(source_rows)
    assert len(plan) == EXPECTED_INTERVENTION_ROWS
    assert all("text_dependency" not in row for row in plan)
    assert all(
        row["target_human_parallel_endpoint_id"].endswith(
            f"::{row['target_language']}"
        )
        for row in plan
    )

    generation = {
        "do_sample": False,
        "num_beams": 4,
        "length_penalty": 1.0,
        "early_stopping": True,
        "max_new_tokens": 256,
    }
    translations = []
    for row in plan:
        translations.append(
            {
                **row,
                "translated_question_stem": row["source_question_stem"],
                "translated_options": row["source_options"],
                "translated_question_raw": row["source_question_raw"],
                "translator_model_id": NLLB_MODEL_ID,
                "translator_revision": NLLB_REVISION,
                "translator_src_code": NLLB_LANGUAGE_CODES[row["source_language"]],
                "translator_tgt_code": NLLB_LANGUAGE_CODES[row["target_language"]],
                "translation_generation_config": generation,
                "translation_status": "ok",
                "translation_retry_events": [],
                "translation_failed_fields": [],
                "translation_analysis_eligible": True,
            }
        )
    validate_translation_rows(translations)
    originals, interventions, audits = build_inputs(translations)
    validate_intervention_inputs(interventions)
    assert len(originals) == len(interventions) == len(audits) == EXPECTED_INTERVENTION_ROWS
    assert all(row["audit_pass"] == 1 for row in audits)
    assert all(json.loads(row["unexpected_changed_fields"]) == [] for row in audits)
    assert all(
        original["image_paths"] == intervention["image_paths"]
        and original["gold_label"] == intervention["gold_label"]
        and original["parallel_id"] == intervention["parallel_id"]
        and original["source_question_language"]
        == intervention["source_question_language"]
        and original["gui_language"] == intervention["gui_language"]
        for original, intervention in zip(originals, interventions, strict=True)
    )
