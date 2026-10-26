"""Targeted checks for outcome-blind grounding packet selection and bbox storage."""

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from annotation.rel_grounding.app import create_app, validate_annotation
from annotation.rel_grounding.prepare_pilot import HERE, LANGUAGES, pilot_sample, structural_frame
from annotation.rel_grounding.summarize_agreement import summarize


def test_structural_frame_requires_active_stem_and_options_in_every_pair():
    pid = "rel::1/one.png"
    mappings = {pid: {"spans": {lang: {"question_stem": [{"text": lang}]} for lang in LANGUAGES}}}
    rows = []
    for source in LANGUAGES:
        for gui in LANGUAGES:
            if source == gui:
                continue
            for condition in ("O", "R", "C", "F"):
                rows.append({
                    "parallel_id": pid, "query_language": source, "gui_language": gui,
                    "condition": condition, "text_dependency": "dependent", "source_issue": None,
                    "question_stem": source if condition in ("O", "C") else gui,
                    "options": {"A": source if condition in ("O", "C") else gui},
                })
    assert structural_frame(rows, mappings) == [pid]
    broken = [dict(row) for row in rows]
    for row in broken:
        if (row["query_language"], row["gui_language"], row["condition"]) == ("en", "zh", "R"):
            row["options"] = {"A": "en"}
    assert structural_frame(broken, mappings) == []


def test_pilot_sample_is_group_balanced_and_deterministic():
    frame = [f"rel::{group}/{number}.png" for group in range(1, 7) for number in range(5)]
    first = pilot_sample(frame)
    assert first == pilot_sample(frame)
    assert len(first) == 12
    assert all(sum(pid.startswith(f"rel::{group}/") for pid in first) == 2 for group in range(1, 7))


def locale_record(image_path: str, image_sha256: str):
    return {
        "image_path": image_path, "image_sha256": image_sha256, "width": 100, "height": 50,
        "question_stem": "Where is the 'Search' button?",
        "stem_span": {"start": 14, "end": 20, "text": "Search", "ref_id": "question_stem:0"},
        "options": {letter: letter for letter in "ABCD"},
        "option_spans": {letter: [] for letter in "ABCD"},
    }


def valid_payload():
    return {
        "parallel_id": "rel::1/one.png", "language": "en", "status": "valid",
        "reference_equivalence": "yes", "options_equivalence": "yes",
        "anchor_phrase": "the 'Search' button", "element_role": "button",
        "bbox": [10, 5, 30, 20], "label_bbox": None, "note": "",
    }


def test_annotation_rejects_nonmatching_phrase_and_out_of_image_box():
    locale = locale_record("assets/images/1/en/one.png", "a" * 64)
    assert validate_annotation(valid_payload(), locale)["bbox"] == [10.0, 5.0, 30.0, 20.0]
    without_equivalence = {key: value for key, value in valid_payload().items()
                           if key not in {"reference_equivalence", "options_equivalence"}}
    assert validate_annotation(without_equivalence, locale)["reference_equivalence"] == "yes"
    assert validate_annotation(without_equivalence, locale)["options_equivalence"] == "yes"
    wrong = {**valid_payload(), "anchor_phrase": "Search button"}
    with pytest.raises(ValueError, match="exact stem substring"):
        validate_annotation(wrong, locale)
    outside = {**valid_payload(), "bbox": [10, 5, 101, 20]}
    with pytest.raises(ValueError, match="outside"):
        validate_annotation(outside, locale)


def test_app_serves_only_manifest_images_and_stores_blind_annotation(tmp_path):
    root = tmp_path / "repo"
    relative = "assets/images/1/en/one.png"
    image = root / "followup_rel_4lang" / relative
    image.parent.mkdir(parents=True)
    Image.new("RGB", (100, 50), "white").save(image)
    sha = hashlib.sha256(image.read_bytes()).hexdigest()
    manifest = {
        "schema": "rel-grounding-pilot-v1",
        "items": [{"parallel_id": "rel::1/one.png", "locales": {
            lang: locale_record(relative, sha) for lang in LANGUAGES
        }}],
    }
    manifest_path = tmp_path / "pilot_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    app = create_app(manifest_path, tmp_path / "outputs", "reviewer_a", root)
    client = app.test_client()
    state = client.get("/api/state").json
    assert state["annotator_id"] == "reviewer_a"
    assert state["annotations"] == {}
    assert client.get("/api/image?pid=rel%3A%3A1%2Fone.png&lang=en").status_code == 200
    assert client.get("/api/image?pid=rel%3A%3A1%2Fother.png&lang=en").status_code == 404
    response = client.post("/api/annotation", json=valid_payload())
    assert response.status_code == 200
    saved = json.loads((tmp_path / "outputs/reviewer_a.json").read_text())
    assert saved["annotations"]["rel::1/one.png"]["en"]["bbox"] == [10.0, 5.0, 30.0, 20.0]
    assert "gold_answer" not in json.dumps(client.get("/api/state").json)
    assert "model_output" not in json.dumps(client.get("/api/state").json)


def test_full_manifest_matches_frame_and_keeps_pilot_ids():
    frame = json.loads((HERE / "data/frame.json").read_text(encoding="utf-8"))
    full = json.loads((HERE / "data/full_manifest.json").read_text(encoding="utf-8"))
    pilot = json.loads((HERE / "data/pilot_manifest.json").read_text(encoding="utf-8"))
    full_ids = [item["parallel_id"] for item in full["items"]]
    assert full["schema"] == "rel-grounding-full-v1"
    assert full_ids == frame["item_ids"]
    assert full["pilot_item_ids"] == frame["pilot_item_ids"]
    assert {item["parallel_id"] for item in pilot["items"]} == set(full["pilot_item_ids"])
    assert all(set(item["locales"]) == set(LANGUAGES) for item in full["items"])
    assert full["gold_answer_included"] is False
    assert full["model_outputs_included"] is False


def test_full_item_save_is_atomic_and_uses_separate_output(tmp_path):
    root = tmp_path / "repo"
    relative = "assets/images/1/en/one.png"
    image = root / "followup_rel_4lang" / relative
    image.parent.mkdir(parents=True)
    Image.new("RGB", (100, 50), "white").save(image)
    sha = hashlib.sha256(image.read_bytes()).hexdigest()
    manifest = {"schema": "rel-grounding-full-v1", "items": [{
        "parallel_id": "rel::1/one.png",
        "locales": {lang: locale_record(relative, sha) for lang in LANGUAGES},
    }]}
    manifest_path = tmp_path / "full_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    outputs = tmp_path / "outputs"
    old_pilot = outputs / "reviewer_a.json"
    outputs.mkdir()
    old_pilot.write_text("pilot data", encoding="utf-8")
    client = create_app(manifest_path, outputs, "reviewer_a", root).test_client()
    records = {lang: {key: value for key, value in valid_payload().items()
                      if key not in {"reference_equivalence", "options_equivalence"}}
               for lang in LANGUAGES}
    records["ru"]["bbox"] = [10, 5, 101, 20]
    response = client.post("/api/item", json={"parallel_id": "rel::1/one.png", "annotations": records})
    assert response.status_code == 400
    assert not (outputs / "reviewer_a.full.json").exists()
    records["ru"]["bbox"] = [10, 5, 30, 20]
    response = client.post("/api/item", json={"parallel_id": "rel::1/one.png", "annotations": records})
    assert response.status_code == 200
    assert all(value["options_equivalence"] == "yes" for value in response.json["annotations"].values())
    saved = json.loads((outputs / "reviewer_a.full.json").read_text(encoding="utf-8"))
    assert set(saved["annotations"]["rel::1/one.png"]) == set(LANGUAGES)
    assert old_pilot.read_text(encoding="utf-8") == "pilot data"
    assert "reviewer_a.full.json" in client.get("/api/export").headers["Content-Disposition"]


def test_agreement_flags_different_boxes_for_manual_review(tmp_path):
    manifest = {"schema": "rel-grounding-pilot-v1", "items": [{
        "parallel_id": "rel::1/one.png", "locales": {lang: {} for lang in LANGUAGES}
    }]}
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    annotation = validate_annotation(valid_payload(), locale_record("x", "a" * 64))
    first_path, second_path = tmp_path / "first.json", tmp_path / "second.json"
    for path, annotator, box in ((first_path, "first", [10, 5, 30, 20]),
                                  (second_path, "second", [60, 5, 80, 20])):
        record = {"schema": "rel-grounding-annotations-v1", "manifest_sha256": sha,
                  "annotator_id": annotator, "annotations": {"rel::1/one.png": {"en": {
                      **annotation, "bbox": box, "note": ""
                  }}}}
        path.write_text(json.dumps(record), encoding="utf-8")
    summary, cases = summarize(manifest_path, first_path, second_path)
    assert summary["counts"]["both_completed"] == 1
    assert cases[0]["bbox_iou"] == 0
    assert cases[0]["needs_adjudication"] is True
    assert summary["needs_adjudication"] == 4
    for path in (first_path, second_path):
        record = json.loads(path.read_text(encoding="utf-8"))
        record["annotations"]["rel::1/one.png"]["en"]["reference_equivalence"] = "no"
        path.write_text(json.dumps(record), encoding="utf-8")
    summary, cases = summarize(manifest_path, first_path, second_path)
    assert cases[0]["meaning_review_flagged"] is True
    assert summary["counts"]["meaning_review_flagged"] == 1
