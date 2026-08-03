from __future__ import annotations

import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
TOOL_DIR = HERE.parent
sys.path.insert(0, str(TOOL_DIR))

from annotation_store import AnnotationStore
from app import create_app
from summarize_agreement import summarize


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


def test_manifest_is_blind_and_complete():
    manifest_path = TOOL_DIR / "data" / "pilot_manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["items"]) == 48
    assert [item["display_order"] for item in manifest["items"]] == list(range(1, 49))
    for item in manifest["items"]:
        assert set(item["locales"]) == {"en", "zh", "fr", "ru", "ja", "th"}
        assert "answer" not in json.dumps(item)


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
    assert health.json["items"] == 48
    assert health.json["images"] == 288
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
