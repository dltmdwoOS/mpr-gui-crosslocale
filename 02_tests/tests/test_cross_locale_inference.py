import json
from argparse import Namespace
from pathlib import Path

import pytest
import torch

from mpr_crosslocale.analysis.summarize_cross_locale import summarize
from mpr_crosslocale.inference.label_scoring import summarize_label_logprobs
from mpr_crosslocale.inference import run_cross_locale
from mpr_crosslocale.inference.run_cross_locale import _build_model_adapter, main
from mpr_crosslocale.inference.runtime import existing_success_ids, hardware_metadata
from mpr_crosslocale.inference.system_prompts import build_system_prompt
from mpr_crosslocale.models.internvl25 import (
    InternVL25Adapter,
    _is_usable_tokenizer,
    dynamic_preprocess,
    ensure_generation_mixin,
)
from mpr_crosslocale.models.qwen25vl import Qwen25VLAdapter, _model_class, _vision_process_kwargs


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


def test_internvl_builds_numbered_multi_image_prompt():
    question = InternVL25Adapter.build_question(
        {
            "image_paths": ["one.png", "two.png"],
            "question_raw": "Which option is correct?",
        },
        "mpr_label_only_v1",
    )

    assert question.count("<image>") == 2
    assert question.startswith("Image-1: <image>\nImage-2: <image>\n")
    assert question.endswith("Respond with exactly one label: A, B, C, or D.")


def test_internvl_dynamic_preprocess_respects_visual_budget():
    from PIL import Image

    image = Image.new("RGB", (1792, 448))
    tiles = dynamic_preprocess(image, max_num=7, image_size=448, use_thumbnail=True)

    assert 1 < len(tiles) <= 8
    assert all(tile.size == (448, 448) for tile in tiles)


def test_internvl_generation_compatibility_is_noop_when_generate_exists():
    language_model = type(
        "LanguageModel",
        (),
        {
            "generate": lambda self: None,
            "_supports_default_dynamic_cache": classmethod(lambda cls: True),
        },
    )()
    model = type("Model", (), {"language_model": language_model})()

    assert ensure_generation_mixin(model) is False
    assert model.language_model._supports_default_dynamic_cache() is False


def test_internvl_rejects_boolean_tokenizer_sentinel():
    tokenizer = type(
        "Tokenizer",
        (),
        {
            "__call__": lambda self: None,
            "batch_decode": lambda self: None,
            "convert_tokens_to_ids": lambda self: None,
            "encode": lambda self: None,
        },
    )()

    assert _is_usable_tokenizer(False) is False
    assert _is_usable_tokenizer(tokenizer) is True


def test_model_factory_builds_internvl_with_parallel_settings(monkeypatch):
    captured = {}

    def fake_adapter(**kwargs):
        captured.update(kwargs)
        return "internvl-adapter"

    monkeypatch.setattr(run_cross_locale, "InternVL25Adapter", fake_adapter)
    args = Namespace(attn_implementation=None, device_map=None)
    config = {
        "model_id": "OpenGVLab/InternVL2_5-8B",
        "model_family": "internvl2_5",
        "revision": "pinned",
        "dtype": "bfloat16",
        "device_strategy": "auto",
        "trust_remote_code": True,
        "attn_implementation": "eager",
        "use_flash_attn": False,
        "input_size": 448,
        "min_num": 1,
        "max_num": 7,
        "use_thumbnail": True,
    }

    adapter = _build_model_adapter(args, config)

    assert adapter == "internvl-adapter"
    assert captured["revision"] == "pinned"
    assert captured["max_num"] == 7
    assert captured["use_flash_attn"] is False


def test_internvl_rejects_sdpa_backend():
    args = Namespace(attn_implementation="sdpa", device_map=None)
    config = {
        "model_id": "OpenGVLab/InternVL2_5-8B",
        "model_family": "internvl2_5",
        "revision": "pinned",
    }

    with pytest.raises(ValueError, match="not 'sdpa'"):
        _build_model_adapter(args, config)


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


def test_qwen_label_summary_uses_next_token_logits():
    adapter = object.__new__(Qwen25VLAdapter)
    adapter.processor = type(
        "Processor",
        (),
        {
            "tokenizer": type(
                "Tokenizer",
                (),
                {"encode": lambda self, label, add_special_tokens: [ord(label)]},
            )()
        },
    )()
    logits = torch.full((128,), -10.0)
    logits[ord("C")] = 3.0

    summary = adapter._summarize_label_logits(logits, {"gold_label": "C"})

    assert summary.scored_predicted_label == "C"
    assert summary.label_token_ids == {label: [ord(label)] for label in ("A", "B", "C", "D")}
    assert summary.scoring_method == "next_token_single_label"


def test_hardware_metadata_has_reproducibility_fields():
    metadata = hardware_metadata()

    assert set(metadata) == {
        "cuda_available",
        "cuda_runtime_version",
        "gpu_count",
        "gpus",
    }
    assert metadata["gpu_count"] == len(metadata["gpus"])
    assert all(
        set(gpu) == {
            "index",
            "name",
            "compute_capability",
            "total_memory_bytes",
        }
        for gpu in metadata["gpus"]
    )


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
    assert all(row["attn_implementation"] for row in dry_rows)
    assert all("torch" in row["software_versions"] for row in dry_rows)
    assert all("transformers" in row["software_versions"] for row in dry_rows)
    assert all("cuda_runtime_version" in row["hardware"] for row in dry_rows)
    assert all("gpus" in row["hardware"] for row in dry_rows)
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


def test_runner_rejects_mixed_model_output(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    output = tmp_path / "mixed.jsonl"
    write_manifest(manifest)
    output.write_text(
        json.dumps({"model_id": "another/model", "status": "success"}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Refusing to mix model"):
        main(
            [
                "--manifest",
                str(manifest),
                "--model-config",
                "configs/models/internvl2_5_8b.yaml",
                "--output",
                str(output),
                "--language-pairs",
                "en:ja",
                "--dimensions",
                "wf",
                "--sample-size",
                "1",
                "--dry-run",
            ]
        )


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
