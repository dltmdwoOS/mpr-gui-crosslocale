import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from mpr_crosslocale.data.rel_followup import (
    CONDITIONS,
    DATA_DIR,
    LANGUAGES,
    TRANSFER_FILES,
    pack,
    safe_path,
    unpack,
    validate_dataset,
    verify_bundle,
)
from mpr_crosslocale.inference import run_rel_followup as runner


def dataset(root: Path) -> list[dict]:
    folder = root / DATA_DIR
    folder.mkdir(parents=True)
    fields = {l: {"question_stem": f"Where is {l}?", **{c: c for c in "ABCD"}} for l in LANGUAGES}
    mapping = {
        "parallel_id": "rel::one.png",
        "fields": fields,
        "spans": {l: {f: [] for f in fields[l]} for l in LANGUAGES},
        "methods": {f: "visual_or_generic_description_not_label" for f in fields["en"]},
    }
    rows = []
    for q in LANGUAGES:
        for g in LANGUAGES:
            image_path = f"assets/images/{g}/one.png"
            path = root / image_path
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (4, 4), "white").save(path)
            seen = {}
            for c, context, refs in (("O", q, q), ("R", q, g), ("C", g, q), ("F", g, g)):
                question = (
                    fields[context]["question_stem"]
                    + " "
                    + " ".join(f"{option}: {option}" for option in "ABCD")
                )
                first = seen.setdefault(question, c)
                rows.append(
                    {
                        "parallel_id": mapping["parallel_id"],
                        "pair_id": f"rel::one.png::{q}::{g}",
                        "state_key": "one.png",
                        "query_language": q,
                        "gui_language": g,
                        "condition": c,
                        "matched": q == g,
                        "primary_analysis": q != g,
                        "dimension": "rel",
                        "text_dependency": "dependent",
                        "image_path": image_path,
                        "gold_answer": "A",
                        "option_order": list("ABCD"),
                        "options": {c: c for c in "ABCD"},
                        "question_stem": fields[context]["question_stem"],
                        "question": question,
                        "context_language": context,
                        "reference_language": refs,
                        "eligible_without_source_adjudication": True,
                        "source_issue": None,
                        "equivalent_to_condition": first,
                        "human_reviewed": False,
                        "screenshot_verified": False,
                    }
                )
    (folder / "conditions_4lang.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    (folder / "reference_mappings.jsonl").write_text(json.dumps(mapping) + "\n", encoding="utf-8")
    for name in TRANSFER_FILES:
        path = folder / name
        if not path.exists():
            path.write_text("{}", encoding="utf-8")
    (folder / "generation_report.json").write_text(
        json.dumps({"source": {"hf_repo": "chenruihan/MPR-GUI-Bench", "hf_revision": "a" * 40}}),
        encoding="utf-8",
    )
    return rows


def args(root: Path, output: Path) -> Namespace:
    config = Path(__file__).resolve().parents[2] / "01_code/configs/models/qwen2_5_vl_7b.yaml"
    return Namespace(
        data_root=root,
        output_dir=output,
        model_config=config,
        max_items=None,
        population="all",
        seed=42,
        dry_run=False,
        mock_model=True,
        resume=True,
        no_score_labels=False,
    )


def test_mock_preserves_quartets_and_reuses_only_within_pair(tmp_path):
    root = tmp_path / "data"
    dataset(root)
    summary = runner.run(args(root, tmp_path / "out"))
    results = [json.loads(s) for s in (tmp_path / "out/results.jsonl").read_text().splitlines()]
    assert summary["statuses"] == {"success": 64}
    assert summary["actual_successful_inferences"] == 28
    assert len({r["input_id"] for r in results}) == 64
    assert {r["condition"] for r in results} == set(CONDITIONS)
    assert all(r["correct"] == r["generation_correct"] for r in results)
    assert all(
        r["prediction_source_input_id"].split("::")[:-1] == r["input_id"].split("::")[:-1]
        for r in results
    )
    runner.run(args(root, tmp_path / "out"))
    assert len((tmp_path / "out/predictions.jsonl").read_text().splitlines()) == 28


def test_generation_outcome_is_distinct_from_label_scoring(tmp_path, monkeypatch):
    root = tmp_path / "data"
    dataset(root)
    original = runner.predict

    def disagree(*arguments):
        result = original(*arguments)
        result.update(generation_correct=True, correct=True, scoring_correct=False)
        return result

    monkeypatch.setattr(runner, "predict", disagree)
    runner.run(args(root, tmp_path / "out"))
    row = json.loads((tmp_path / "out/results.jsonl").read_text().splitlines()[0])
    assert row["correct"] and row["generation_correct"] and not row["scoring_correct"]


def test_adapter_receives_frozen_prompt_image_and_gold(tmp_path):
    root = tmp_path / "data"
    row = dataset(root)[0]
    options = args(root, tmp_path / "out")
    options.mock_model = False
    config = runner.load_yaml(options.model_config)

    class FakeAdapter:
        def generate_one(self, supplied, profile, generation, **kwargs):
            assert supplied["question_raw"] == row["question"]
            assert supplied["gold_label"] == "A"
            assert supplied["image_paths"] == [str((root / row["image_path"]).resolve())]
            assert profile == "mpr_label_only_v1" and generation["max_new_tokens"] == 2
            assert kwargs == {"system_prompt": "fixed", "score_labels": True}
            return SimpleNamespace(
                raw_output="B",
                rendered_prompt="test",
                prompt_token_count=10,
                output_token_count=1,
                label_summary=runner.deterministic_mock_label_score("A", "A"),
            )

    result = runner.predict(FakeAdapter(), row, options, config, "fixed")
    assert result["parse_success"] and result["scoring_correct"]
    assert not result["generation_correct"] and not result["correct"]
    assert result["generation_scoring_disagreement"]


def test_resume_rejects_model_or_prompt_configuration_change(tmp_path):
    root = tmp_path / "data"
    dataset(root)
    options = args(root, tmp_path / "out")
    runner.run(options)
    options.no_score_labels = True
    with pytest.raises(ValueError, match="different dataset/model/settings/subset"):
        runner.run(options)


def test_failed_predictions_remain_null_and_are_retried(tmp_path, monkeypatch):
    root = tmp_path / "data"
    dataset(root)
    original = runner.predict
    calls = 0

    def fail_once(*arguments):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("simulated OOM")
        return original(*arguments)

    monkeypatch.setattr(runner, "predict", fail_once)
    first = runner.run(args(root, tmp_path / "out"))
    assert first["statuses"]["failed"] == 4  # matched O/R/C/F share one failed call
    row = json.loads((tmp_path / "out/results.jsonl").read_text().splitlines()[0])
    assert row["generation_correct"] is None
    second = runner.run(args(root, tmp_path / "out"))
    assert second["statuses"] == {"success": 64}
    assert calls == 29


def test_known_issue_is_inferred_but_excluded_as_a_complete_quartet(tmp_path):
    root = tmp_path / "data"
    rows = dataset(root)
    for row in rows:
        if (row["query_language"], row["gui_language"]) == ("en", "zh"):
            row.update(
                source_issue={"reason": "parallel translation mismatch"},
                eligible_without_source_adjudication=False,
            )
    (root / DATA_DIR / "conditions_4lang.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    result = runner.run(args(root, tmp_path / "out"))
    assert result["statuses"] == {"success": 64}
    assert result["source_issue_rows"] == 4
    assert (
        result["primary_descriptive_summary"]["dependent"]["complete_unflagged_mismatch_quartets"]
        == 11
    )


def test_bundle_roundtrip_verifies_images_and_refuses_corruption(tmp_path):
    root = tmp_path / "source"
    dataset(root)
    archive, lock = tmp_path / "data.tar.gz", tmp_path / "lock.json"
    pack(root, archive, lock, include_images=True)
    dest = tmp_path / "dest"
    unpack(archive, dest, lock)
    unpack(archive, dest, lock)  # safe replay
    verify_bundle(dest, images=True)
    image = dest / "assets/images/en/one.png"
    image.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_bundle(dest, images=True)
    with pytest.raises(ValueError, match="Refusing to overwrite different"):
        unpack(archive, dest, lock)


@pytest.mark.parametrize("name", ["../escape", "/escape", "C:/escape", "..\\escape"])
def test_transfer_rejects_paths_outside_data_root(tmp_path, name):
    with pytest.raises(ValueError, match="Unsafe relative path"):
        safe_path(tmp_path, name)


def test_partial_cache_tail_is_recovered_without_repeating_successes(tmp_path):
    path = tmp_path / "predictions.jsonl"
    path.write_bytes(b'{"input_id":"one","experiment_fingerprint":"f","status":"success"}\n{"inp')
    cache = runner.read_cache(path, "f")
    assert cache["one"]["status"] == "success"
    assert path.read_bytes().endswith(b"\n")


def test_cache_cannot_mix_mock_predictions_with_real_inference(tmp_path):
    root = tmp_path / "data"
    dataset(root)
    options = args(root, tmp_path / "out")
    runner.run(options)
    # The execution mode is part of the contract, even when all other settings match.
    options.mock_model = False
    (root / "bundle_manifest.json").write_text(
        json.dumps({"schema": "rel-followup-bundle-v1", "files": [], "images": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="different dataset/model/settings/subset"):
        runner.run(options)


def test_resume_detects_changed_image_manifest(tmp_path):
    root = tmp_path / "data"
    dataset(root)
    manifest_path = root / "bundle_manifest.json"
    manifest_path.write_text(
        json.dumps({"schema": "rel-followup-bundle-v1", "files": [], "images": []}),
        encoding="utf-8",
    )
    options = args(root, tmp_path / "out")
    runner.run(options)
    manifest_path.write_text(
        json.dumps({"schema": "rel-followup-bundle-v1", "files": [], "images": [], "new": True}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="different dataset/model/settings/subset"):
        runner.run(options)


def test_structural_audit_rejects_missing_quartet_and_modified_context(tmp_path):
    root = tmp_path / "source"
    rows = dataset(root)
    path = root / DATA_DIR / "conditions_4lang.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows[:-1]), encoding="utf-8")
    with pytest.raises(ValueError, match="Incomplete quartet"):
        validate_dataset(root)
    rows[0]["question_stem"] = "unintended change"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    with pytest.raises(ValueError, match="reconstruction failed"):
        validate_dataset(root)
