"""Verify a transferred, provisional REL grounding annotation package."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
LANGUAGES = {"en", "zh", "th", "ru"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify(check_images: bool = False) -> None:
    checksums = json.loads((HERE / "checksums.json").read_text(encoding="utf-8"))
    for name, expected in checksums.items():
        path = HERE / name
        require(path.is_file() and sha256(path) == expected, f"Package checksum mismatch: {name}")

    gt = json.loads((HERE / "grounding_gt_draft_170.json").read_text(encoding="utf-8"))
    manifest_path = REPO / "annotation/rel_grounding/data/full_manifest.json"
    require(manifest_path.is_file(), f"Missing repository manifest: {manifest_path}")
    require(sha256(manifest_path) == gt["manifest_sha256"], "Repository manifest differs from annotation manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_id = {item["parallel_id"]: item for item in manifest["items"]}
    exclusions = json.loads((HERE / "excluded_items.json").read_text(encoding="utf-8"))
    excluded_ids = {item["parallel_id"] for item in exclusions["excluded_items"]}
    annotations = gt["annotations"]
    sources = gt["gt_assembly"]["item_sources"]
    require(gt["schema"] == "rel-grounding-annotations-v2", "Unknown annotation schema")
    require(len(by_id) == 179 and len(annotations) == 170 and len(excluded_ids) == 9,
            "Unexpected item or exclusion count")
    require(set(by_id) == set(annotations) | excluded_ids and not set(annotations) & excluded_ids,
            "Annotation and exclusion IDs do not partition the manifest")
    require(set(sources) == set(annotations), "Item-source IDs differ from annotations")
    require(Counter(sources.values()) == {"baegihyeon": 118, "consensus": 52},
            "Unexpected adjudication source counts")
    require(gt["gt_assembly"]["role_alignment_complete"] is False,
            "This package is expected to be pre-role-alignment")
    require(gt["gt_assembly"]["role_alignment_required_items"] == 47,
            "Unexpected role-alignment queue size")
    require({x["parallel_id"] for x in gt["gt_assembly"]["excluded_items"]} == excluded_ids,
            "GT exclusions differ from the exclusion list")
    pilot = set(gt["gt_assembly"]["pilot_item_ids"])
    require(len(pilot) == 12 and pilot <= set(annotations) and
            pilot == set(manifest["pilot_item_ids"]), "Pilot item IDs differ")

    targets = [json.loads(line) for line in (HERE / "targets.jsonl").read_text(encoding="utf-8").splitlines()]
    require(len(targets) == 680, "Expected 680 target rows")
    seen = set()
    for target in targets:
        pid, language = target["parallel_id"], target["gui_language"]
        require(pid in annotations and language in LANGUAGES and (pid, language) not in seen,
                f"Invalid or duplicate target: {pid}/{language}")
        seen.add((pid, language))
        record = annotations[pid][language]
        locale = by_id[pid]["locales"][language]
        width, height = int(locale["width"]), int(locale["height"])
        box = record["bbox"]
        require(record["status"] == "valid" and box is not None and record["element_role"],
                f"Invalid annotation: {pid}/{language}")
        require(0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height,
                f"Out-of-bounds box: {pid}/{language}")
        require(record["image_sha256"] == locale["image_sha256"] and
                record["image_size"] == [width, height], f"Image metadata differs: {pid}/{language}")
        require(target["bbox"] == box and target["image_sha256"] == locale["image_sha256"] and
                target["element_role"] == record["element_role"] and
                target["anchor_phrase"] == record["anchor_phrase"] and
                target["annotation_source"] == sources[pid] and
                target["split"] == ("pilot" if pid in pilot else "main"),
                f"Flat target differs from GT: {pid}/{language}")
        image_path = REPO / target["image_path"]
        require(image_path.is_relative_to(REPO) and
                target["image_path"] == "followup_rel_4lang/" + locale["image_path"],
                f"Image path differs: {pid}/{language}")
        if check_images:
            require(image_path.is_file() and sha256(image_path) == locale["image_sha256"],
                    f"Missing or changed image: {image_path}")
    require(len(seen) == 680, "Incomplete four-language targets")

    review = json.loads((HERE / "audit/review_state.json").read_text(encoding="utf-8"))
    require(len(review["reviews"]) == 228, "Unexpected consensus review count")
    source_hashes = gt["gt_assembly"]["source_hashes"]
    for annotator, expected in source_hashes.items():
        path = HERE / f"audit/{annotator}.full.json"
        require(sha256(path) == expected, f"Source annotation changed: {annotator}")
    require({item["annotator_id"]: item["sha256"] for item in review["sources"]} == source_hashes,
            "Consensus review is bound to different source annotations")
    print("OK: 170 items / 680 screens; main 158, pilot 12; excluded 9")
    print("Sources: 52 consensus items, 118 baegihyeon items; element roles provisional (47 pending)")
    print("Images:", "all 680 SHA-256 verified" if check_images else "not checked; use --images")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", action="store_true", help="also verify all 680 local image hashes")
    args = parser.parse_args()
    verify(args.images)
