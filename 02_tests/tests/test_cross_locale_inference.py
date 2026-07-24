import json
from pathlib import Path

import pytest

from mpr_crosslocale.analysis.summarize_cross_locale import summarize
from mpr_crosslocale.inference.label_scoring import summarize_label_logprobs
from mpr_crosslocale.inference.run_cross_locale import main
from mpr_crosslocale.inference.runtime import existing_success_ids
from mpr_crosslocale.inference.system_prompts import build_system_prompt
from mpr_crosslocale.models.qwen25vl import _model_class, _vision_process_kwargs


def write_manifest(path: Path) -> None:
    rows = []
    for dimension in ("wf", "wi", "au", "ap", "ael", "rel", "ri", "si"):
        for language in ("en", "ja"):
            rows.append(
                {
                    "sample_id": f"{dimension}::1/foo.jpg::{language}",
                    "parallel_id": f"{dimension}::1/foo.jpg",
                    "dimension": dimension,
                    "language": language,
                    "question_raw": f"Question {language}? A: one B: two C: three D: four",
                    "question_stem": f"Question {language}?",
                    "options": {"A": "one", "B": "two", "C": "three", "D": "four"},
                    "option_order": ["A", "B", "C", "D"],
                    "answer_raw": "A",
                    "gold_label": "A",
                    "image_paths": [f"data/{language}/foo.jpg"],
                    "num_images": 1,
                    "frame_order": "single_image",
                }
            )
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_system_prompt_modes():
    fixed, fixed_language, version = build_system_prompt("english_fixed", "ja")
    aligned, aligned_language, same_version = build_system_prompt("query_aligned", "ja")

    assert fixed_language == "en"
    assert aligned_language == "ja"
    assert version == same_version
    assert fixed != aligned


def test_qwen_model_family_rejects_unknown_family():
    with pytest.raises(ValueError, match="Unsupported Qwen model_family"):
        _model_class("unknown")


def test_qwen3_uses_vision_patch_size_from_processor():
    image_processor = type("ImageProcessor", (), {"patch_size": 16})()
    processor = type("Processor", (), {"image_processor": image_processor})()

    assert _vision_process_kwargs("qwen3_vl", processor) == {"image_patch_size": 16}
    assert _vision_process_kwargs("qwen2_5_vl", processor) == {}


def test_label_scoring_entropy_and_margins():
    summary = summarize_label_logprobs(
        {"A": -0.1, "B": -2.0, "C": -3.0, "D": -4.0},
        gold_label="A",
        scoring_method="fixture",
    )

    assert summary.scored_predicted_label == "A"
    assert summary.gold_rank == 1
    assert summary.top1_top2_margin > 0
    assert summary.gold_vs_best_wrong_margin > 0
    assert summary.entropy > 0


def test_dry_run_and_mock_runner_without_model(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    dry_output = tmp_path / "dry.jsonl"
    mock_output = tmp_path / "mock.jsonl"
    sample_manifest = tmp_path / "sample.json"
    write_manifest(manifest)

    main(
        [
            "--manifest",
            str(manifest),
            "--output",
            str(dry_output),
            "--language-pairs",
            "en:ja",
            "ja:en",
            "--dimensions",
            "wf",
            "wi",
            "au",
            "ap",
            "ael",
            "rel",
            "ri",
            "si",
            "--sample-size",
            "2",
            "--sample-unit",
            "semantic_items",
            "--sample-manifest-out",
            str(sample_manifest),
            "--dry-run",
        ]
    )
    dry_rows = [json.loads(line) for line in dry_output.read_text(encoding="utf-8").splitlines()]
    assert len(dry_rows) == 4
    assert all(row["status"] == "dry_run" for row in dry_rows)
    assert json.loads(sample_manifest.read_text(encoding="utf-8"))["n_evaluations"] == 4

    main(
        [
            "--manifest",
            str(manifest),
            "--output",
            str(mock_output),
            "--language-pairs",
            "en:ja",
            "ja:en",
            "--dimensions",
            "wf",
            "wi",
            "--sample-size",
            "1",
            "--sample-unit",
            "semantic_items",
            "--mock-model",
            "--resume",
        ]
    )
    assert len(existing_success_ids(mock_output)) == 2


def test_aggregation_6x6_shape():
    rows = []
    for q_lang in ("en", "zh", "fr", "ru", "ja", "th"):
        for g_lang in ("en", "zh", "fr", "ru", "ja", "th"):
            rows.append(
                {
                    "status": "success",
                    "question_language": q_lang,
                    "gui_language": g_lang,
                    "dimension": "wf",
                    "matched": q_lang == g_lang,
                    "gold_label": "A",
                    "scored_predicted_label": "A",
                    "correct": True,
                    "parallel_id": f"wf::{q_lang}:{g_lang}",
                    "parse_success": True,
                    "generation_scoring_disagreement": False,
                    "gold_probability": 0.8,
                    "top1_top2_margin": 0.5,
                    "gold_vs_best_wrong_margin": 0.5,
                    "entropy": 0.7,
                }
            )

    summary = summarize(rows)

    assert summary["accuracy_matrix"]["en"]["ja"]["n"] == 1
    assert summary["matched_mean"] == 1.0
    assert summary["mismatch_mean"] == 1.0
    assert summary["macro_f1"] == 0.25
