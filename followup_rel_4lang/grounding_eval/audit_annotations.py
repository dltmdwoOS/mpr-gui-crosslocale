"""Independently audit the transferred grounding annotations and their provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PACKAGE = HERE / "annotations_20261103"
LANGUAGES = ("en", "zh", "th", "ru")
SOURCES = ("reviewer_a", "baegihyeon")
CORE_FIELDS = (
    "status", "reference_equivalence", "options_equivalence", "anchor_phrase",
    "element_role", "bbox", "label_bbox", "image_sha256", "image_size",
    "bbox_center", "bbox_normalized",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def iou(first: list[float], second: list[float]) -> float:
    x1, y1 = max(first[0], second[0]), max(first[1], second[1])
    x2, y2 = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    area = sum((box[2] - box[0]) * (box[3] - box[1]) for box in (first, second))
    return intersection / (area - intersection)


def source_flags(raw: dict, reviews: dict) -> dict[str, set[tuple[str, str, str, str]]]:
    flags: dict[str, set[tuple[str, str, str, str]]] = {}
    for source, items in raw.items():
        for pid, locales in items.items():
            for lang, record in locales.items():
                values = {
                    "status": record["status"], "note": record["note"],
                    "reference_equivalence": record["reference_equivalence"],
                    "options_equivalence": record["options_equivalence"],
                }
                for field, value in values.items():
                    flagged = (
                        (field == "status" and value != "valid")
                        or (field == "note" and bool(value.strip()))
                        or (field.endswith("equivalence") and value in {"no", "uncertain"})
                    )
                    if flagged:
                        flags.setdefault(pid, set()).add((source, lang, field, str(value)))
    for key, decision in reviews.items():
        pid, lang = key.rsplit("::", 1)
        status = decision["annotation"]["status"]
        if status != "valid":
            flags.setdefault(pid, set()).add(("consensus", lang, "status", status))
    return flags


def audit() -> dict:
    checksums = read_json(PACKAGE / "checksums.json")
    for name, expected in checksums.items():
        require(sha256(PACKAGE / name) == expected, f"Transferred file changed: {name}")
    manifest_path = REPO / "annotation/rel_grounding/data/full_manifest.json"
    manifest = read_json(manifest_path)
    gt = read_json(PACKAGE / "grounding_gt_draft_170.json")
    review = read_json(PACKAGE / "audit/review_state.json")
    exclusions = read_json(PACKAGE / "excluded_items.json")["excluded_items"]
    raw_files = {name: PACKAGE / "audit" / f"{name}.full.json" for name in SOURCES}
    raw_records = {name: read_json(path) for name, path in raw_files.items()}
    raw = {name: record["annotations"] for name, record in raw_records.items()}
    require(sha256(manifest_path) == gt["manifest_sha256"], "GT/manifest hash differs")
    require(review["manifest_sha256"] == gt["manifest_sha256"], "Review/GT manifest differs")
    by_id = {item["parallel_id"]: item for item in manifest["items"]}
    excluded = {item["parallel_id"]: item for item in exclusions}
    included = gt["annotations"]
    require(len(by_id) == 179 and len(included) == 170 and len(excluded) == 9,
            "Unexpected item counts")
    require(set(by_id) == set(included) | set(excluded) and not set(included) & set(excluded),
            "Included/excluded items do not partition manifest")
    require(set(gt["gt_assembly"]["item_sources"]) == set(included), "Source mapping differs")
    require(set(gt["gt_assembly"]["pilot_item_ids"]) == set(manifest["pilot_item_ids"]),
            "Pilot IDs differ")
    for source in SOURCES:
        record = raw_records[source]
        require(record["annotator_id"] == source and record["manifest_sha256"] == gt["manifest_sha256"],
                f"Raw annotator/manifest mismatch: {source}")
        require(set(record["annotations"]) == set(by_id), f"Incomplete raw annotator: {source}")
        require(sha256(raw_files[source]) == gt["gt_assembly"]["source_hashes"][source],
                f"GT source hash differs: {source}")
    require({source["annotator_id"]: source["sha256"] for source in review["sources"]}
            == gt["gt_assembly"]["source_hashes"], "Review source hashes differ")

    flags = source_flags(raw, review["reviews"])
    recorded_flags = {
        item["parallel_id"]: {
            (flag["source"], flag["language"], flag["field"], str(flag["value"]))
            for flag in item["flags"]
        }
        for item in exclusions
    }
    require(flags == recorded_flags, "Exclusion flags do not match raw annotations/reviews")
    require({item["parallel_id"] for item in gt["gt_assembly"]["excluded_items"]} == set(excluded),
            "GT exclusion list differs")

    counts: Counter[str] = Counter()
    accepted_iou: list[float] = []
    consensus_ids: set[str] = set()
    broad_main_items: set[str] = set()
    pilot_ids = set(gt["gt_assembly"]["pilot_item_ids"])
    for pid, locales in raw[SOURCES[0]].items():
        for lang in LANGUAGES:
            first, second = locales[lang], raw[SOURCES[1]][pid][lang]
            counts["raw_screens"] += 1
            counts["raw_status_agree"] += first["status"] == second["status"]
            counts["raw_role_agree"] += first["element_role"] == second["element_role"]
            counts["raw_phrase_agree"] += first["anchor_phrase"] == second["anchor_phrase"]
            if first["status"] == second["status"] == "valid":
                score = iou(first["bbox"], second["bbox"])
                counts["raw_both_valid"] += 1
                counts["raw_iou_ge_0_5"] += score >= 0.5
                counts["raw_iou_lt_0_1"] += score < 0.1
            if pid not in included:
                continue
            gt_record = included[pid][lang]
            source = gt["gt_assembly"]["item_sources"][pid]
            if source == "consensus":
                consensus_ids.add(pid)
                key = f"{pid}::{lang}"
                require(key in review["reviews"] and review["reviews"][key]["resolution"] == "resolved",
                        f"Missing resolved consensus: {key}")
                chosen = review["reviews"][key]["annotation"]
                counts["consensus_screens"] += 1
            else:
                require(source == "baegihyeon", f"Unknown GT source: {pid}")
                chosen = second
                score = iou(first["bbox"], second["bbox"])
                accepted_iou.append(score)
                require(score >= 0.5, f"Unadjudicated low-overlap box: {pid}/{lang}")
                counts["raw_source_screens"] += 1
            for field in CORE_FIELDS:
                require(gt_record[field] == chosen[field], f"GT source mismatch: {pid}/{lang}/{field}")
            locale = by_id[pid]["locales"][lang]
            width, height = gt_record["image_size"]
            box = gt_record["bbox"]
            center = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]
            normalized = [box[0] / width, box[1] / height, box[2] / width, box[3] / height]
            area_fraction = (box[2] - box[0]) * (box[3] - box[1]) / (width * height)
            require(gt_record["status"] == "valid" and
                    0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height,
                    f"Invalid GT box: {pid}/{lang}")
            require(gt_record["image_sha256"] == locale["image_sha256"] and
                    [width, height] == [locale["width"], locale["height"]],
                    f"GT image mismatch: {pid}/{lang}")
            require(all(abs(a - b) < 1e-9 for a, b in zip(center, gt_record["bbox_center"])) and
                    all(abs(a - b) < 1e-9 for a, b in zip(normalized, gt_record["bbox_normalized"])),
                    f"GT derived coordinates differ: {pid}/{lang}")
            span = locale["stem_span"]["text"]
            start, end = locale["stem_span"]["start"], locale["stem_span"]["end"]
            require(gt_record["anchor_phrase"] == span and
                    locale["question_stem"][start:end] == span,
                    f"Prompt span differs: {pid}/{lang}")
            counts["gt_question_repeats_span"] += locale["question_stem"].count(span) > 1
            counts["gt_screens"] += 1
            if area_fraction > 0.15:
                counts["gt_broad_region_screens_gt_0_15"] += 1
                if pid not in pilot_ids:
                    broad_main_items.add(pid)
            counts["gt_reference_unreviewed"] += gt_record["reference_equivalence"] == "unreviewed"
            counts["gt_options_unreviewed"] += gt_record["options_equivalence"] == "unreviewed"
            counts["gt_bbox_copy_pending"] += (
                gt_record["bbox_provenance"]["review_status"] == "pending"
            )
            counts["gt_selection_independent"] += bool(gt_record["selection_independent"])
    require(counts["raw_screens"] == 716 and counts["gt_screens"] == 680,
            "Incomplete raw or GT screens")
    require(len(consensus_ids) == 52 and counts["consensus_screens"] == 208 and
            counts["raw_source_screens"] == 472, "Unexpected GT source split")
    require(len(review["reviews"]) == 228, "Unexpected review count")
    require(all(entry["resolution"] == "resolved" for entry in review["reviews"].values()),
            "Transferred review contains unresolved entries")
    require(gt["gt_assembly"]["role_alignment_complete"] is False,
            "Role alignment status unexpectedly changed")

    targets = [json.loads(line) for line in (PACKAGE / "targets.jsonl").read_text(encoding="utf-8").splitlines()]
    require(len(targets) == 680, "Target count differs")
    role_pending_items = {target["parallel_id"] for target in targets if target["role_alignment_pending"]}
    require(len(role_pending_items) == gt["gt_assembly"]["role_alignment_required_items"],
            "Role alignment queue differs")
    counts["role_pending_screens"] = sum(target["role_alignment_pending"] for target in targets)
    main_ids = set(included) - pilot_ids
    require(len(pilot_ids) == 12 and len(main_ids) == 158,
            "Unexpected pilot/main partition")

    return {
        "schema": "rel-grounding-annotation-audit-v1",
        "manifest_sha256": gt["manifest_sha256"],
        "gt_sha256": sha256(PACKAGE / "grounding_gt_draft_170.json"),
        "main_items": len(main_ids),
        "pilot_items": len(pilot_ids),
        "excluded_items": len(excluded),
        "main_directed_pairs_per_model": len(main_ids) * 12,
        "source_items": dict(Counter(gt["gt_assembly"]["item_sources"].values())),
        "role_pending_items": len(role_pending_items),
        "main_role_pending_items": len(role_pending_items & main_ids),
        "main_broad_region_items_gt_0_15": sorted(broad_main_items),
        "counts": dict(sorted(counts.items())),
        "raw_source_iou_min": min(accepted_iou),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="also write the summary as JSON")
    args = parser.parse_args()
    summary = audit()
    content = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    print(content, end="")


if __name__ == "__main__":
    main()
