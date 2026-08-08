from __future__ import annotations

import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
TOOL_DIR = HERE.parent
sys.path.insert(0, str(TOOL_DIR))

from annotation_store import AnnotationStore
from app import canonical_text_sha256, create_app
from prepare_pilot import LANGUAGES, load_items, preserve_existing_prefix, stratified_sample
from summarize_agreement import summarize


def test_manifest_hash_is_newline_portable(tmp_path):
    lf_path = tmp_path / "manifest_lf.json"
    crlf_path = tmp_path / "manifest_crlf.json"
    content = '{\n  "items": []\n}\n'
    lf_path.write_bytes(content.encode("utf-8"))
    crlf_path.write_bytes(content.replace("\n", "\r\n").encode("utf-8"))

    assert canonical_text_sha256(lf_path) == canonical_text_sha256(crlf_path)


def test_store_roundtrip_and_export(tmp_path):
    store = AnnotationStore(tmp_path / "annotations.sqlite3")
    saved = store.upsert(
        annotator_id="검수자_A",
        parallel_id="rel::demo.jpg",
        display_order=1,
        label="dependent",
        review_flag=True,
        note="target label 확인 필요",
        current_locale="ja",
        annotation_seconds=12.5,
        guideline_version="pilot-v1",
        manifest_sha256="abc",
    )
    assert saved["label"] == "dependent"
    assert saved["review_flag"] is True
    assert store.progress("검수자_A", 48)["labeled"] == 1
    exported = store.export_csv("검수자_A")
    assert "text_dependency" in exported
    assert "dependent" in exported

    changed = store.reconcile_manifest(
        [{"parallel_id": "rel::demo.jpg", "display_order": 7}],
        guideline_version="pilot-v1",
        manifest_sha256="new-manifest",
    )
    migrated = store.get("검수자_A", "rel::demo.jpg")
    assert changed == 1
    assert migrated["label"] == "dependent"
    assert migrated["review_flag"] is True
    assert migrated["note"] == "target label 확인 필요"
    assert migrated["annotation_seconds"] == 12.5
    assert migrated["display_order"] == 7
    assert migrated["manifest_sha256"] == "new-manifest"


def test_full_census_and_existing_prefix(tmp_path):
    items = [
        {"parallel_id": f"rel::{index}", "stratum": stratum}
        for index, stratum in enumerate(["1", "1", "2", "2", "2", "3"], start=1)
    ]
    selected, allocation, population = stratified_sample(items, len(items), seed=42)
    assert len(selected) == len(items)
    assert allocation == population == {"1": 2, "2": 3, "3": 1}

    manifest = {
        "items": [
            {"parallel_id": "rel::2", "display_order": 1},
            {"parallel_id": "rel::5", "display_order": 2},
        ]
    }
    manifest_path = tmp_path / "pilot_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    expanded = preserve_existing_prefix(selected, manifest_path)
    assert [item["parallel_id"] for item in expanded[:2]] == ["rel::2", "rel::5"]
    assert [item["display_order"] for item in expanded] == list(range(1, 7))

    census_items = [
        {"parallel_id": f"rel::{stratum}-{index}", "stratum": str(stratum)}
        for stratum in range(1, 7)
        for index in range(10)
    ]
    expected_pilot, _, _ = stratified_sample(census_items, 48, seed=20260803)
    full_census, _, _ = stratified_sample(census_items, 60, seed=20260803)
    assert [item["parallel_id"] for item in full_census[:48]] == [
        item["parallel_id"] for item in expected_pilot
    ]


def test_manifest_is_blind_and_complete():
    manifest_path = TOOL_DIR / "data" / "pilot_manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["items"]) in {48, 366}
    assert [item["display_order"] for item in manifest["items"]] == list(
        range(1, len(manifest["items"]) + 1)
    )
    for item in manifest["items"]:
        assert set(item["locales"]) == {"en", "zh", "fr", "ru", "ja", "th"}
        assert not ({"answer", "correct_answer", "gold", "gold_label"} & set(item))
        for locale in item["locales"].values():
            assert not ({"answer", "correct_answer", "gold", "gold_label"} & set(locale))


def test_actual_full_census_preserves_current_manifest_prefix():
    data_dir = TOOL_DIR / "data"
    manifest_path = data_dir / "pilot_manifest.json"
    qas_paths = {language: data_dir / "qas" / f"rel_el_{language}.jsonl" for language in LANGUAGES}
    if not manifest_path.exists() or not all(path.exists() for path in qas_paths.values()):
        return
    existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    existing_ids = [item["parallel_id"] for item in existing["items"]]
    full, allocation, population = stratified_sample(
        load_items(qas_paths), 366, seed=20260803
    )
    full = preserve_existing_prefix(full, manifest_path)
    assert len(full) == 366
    assert allocation == population
    assert [item["parallel_id"] for item in full[: len(existing_ids)]] == existing_ids


def test_real_app_health_annotation_export_and_image(tmp_path):
    data_dir = TOOL_DIR / "data"
    if not (data_dir / "pilot_manifest.json").exists():
        return
    app = create_app(data_dir=data_dir, output_dir=tmp_path / "outputs")
    app.testing = True
    client = app.test_client()

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json["status"] == "ok"
    assert health.json["items"] in {48, 366}
    assert health.json["images"] == health.json["items"] * 6
    assert health.json["gold_in_manifest"] is False
    assert health.json["gold_in_ui"] is True

    item_response = client.get("/api/item/1?annotator=tester")
    assert item_response.status_code == 200
    item = item_response.json["item"]
    assert all("answer" not in locale for locale in item["locales"].values())
    assert item["locales"]["en"]["correct_answer"] in {"A", "B", "C", "D"}
    first_image = item["locales"]["en"]["image_url"]
    assert client.get(first_image).status_code == 200

    save = client.post(
        "/api/annotate",
        json={
            "annotator_id": "tester",
            "parallel_id": item["parallel_id"],
            "label": "independent",
            "review_flag": False,
            "note": "API integration test",
            "current_locale": "en",
            "annotation_seconds": 4.2,
        },
    )
    assert save.status_code == 200
    assert save.json["progress"]["labeled"] == 1

    exported = client.get("/api/export?annotator=tester")
    assert exported.status_code == 200
    assert b"independent" in exported.data


def test_agreement_summary(tmp_path):
    header = "parallel_id,annotator_id,display_order,text_dependency,review_flag,note\n"
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_text(
        header
        + "rel::a,A,1,dependent,0,\n"
        + "rel::b,A,2,independent,0,\n"
        + "rel::c,A,3,dependent,1,check\n",
        encoding="utf-8",
    )
    second.write_text(
        header
        + "rel::a,B,1,dependent,0,\n"
        + "rel::b,B,2,independent,0,\n"
        + "rel::c,B,3,independent,1,check\n",
        encoding="utf-8",
    )
    summary, disagreements = summarize(first, second)
    assert summary["shared_labeled_items"] == 3
    assert summary["raw_agreement"] == 2 / 3
    assert summary["disagreement_count"] == 1
    assert disagreements[0]["parallel_id"] == "rel::c"
