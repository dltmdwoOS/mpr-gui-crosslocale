"""Report two independent grounding annotators' coverage and disagreements."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent


def intersection_over_union(a: list[float], b: list[float]) -> float:
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return intersection / (area_a + area_b - intersection)


def summarize(manifest_path: Path, first_path: Path, second_path: Path) -> tuple[dict, list[dict]]:
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    first = json.loads(first_path.read_text(encoding="utf-8"))
    second = json.loads(second_path.read_text(encoding="utf-8"))
    for record in (first, second):
        if record.get("schema") != "rel-grounding-annotations-v1" or record.get("manifest_sha256") != manifest_hash:
            raise ValueError("Annotation file does not match the pilot manifest")
    if first["annotator_id"] == second["annotator_id"]:
        raise ValueError("Independent annotation files must use different annotator IDs")
    counters = Counter()
    cases = []
    for item in manifest["items"]:
        pid = item["parallel_id"]
        for language in ("en", "zh", "th", "ru"):
            a = first["annotations"].get(pid, {}).get(language)
            b = second["annotations"].get(pid, {}).get(language)
            counters["screens"] += 1
            counters["first_completed"] += a is not None
            counters["second_completed"] += b is not None
            case = {"parallel_id": pid, "gui_language": language,
                    "first_status": a["status"] if a else "missing",
                    "second_status": b["status"] if b else "missing",
                    "first_bbox": a["bbox"] if a else None,
                    "second_bbox": b["bbox"] if b else None,
                    "bbox_iou": None,
                    "first_note": a["note"] if a else "", "second_note": b["note"] if b else ""}
            if a and b:
                counters["both_completed"] += 1
                for field in ("status", "reference_equivalence", "options_equivalence", "anchor_phrase", "element_role"):
                    counters[f"{field}_agreement"] += a[field] == b[field]
                    case[f"{field}_agreement"] = a[field] == b[field]
                if a["status"] == b["status"] == "valid":
                    iou = intersection_over_union(a["bbox"], b["bbox"])
                    case["bbox_iou"] = round(iou, 6)
                    counters["both_valid"] += 1
                    counters["both_valid_iou_ge_0_5"] += iou >= 0.5
                case["needs_adjudication"] = (
                    any(not case[f"{field}_agreement"] for field in (
                        "status", "reference_equivalence", "options_equivalence", "anchor_phrase", "element_role"
                    )) or (case["bbox_iou"] is not None and case["bbox_iou"] < 0.5)
                )
            else:
                case["needs_adjudication"] = True
            cases.append(case)
    summary = {
        "schema": "rel-grounding-agreement-v1",
        "manifest_sha256": manifest_hash,
        "annotators": [first["annotator_id"], second["annotator_id"]],
        "counts": dict(counters),
        "mean_iou_both_valid": (
            sum(c["bbox_iou"] for c in cases if c["bbox_iou"] is not None) / counters["both_valid"]
            if counters["both_valid"] else None
        ),
        "needs_adjudication": sum(c["needs_adjudication"] for c in cases),
        "note": "IoU is a box-overlap proxy, not a semantic identity adjudication. Inspect flagged cases manually.",
    }
    return summary, cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    parser.add_argument("--manifest", type=Path, default=HERE / "data/pilot_manifest.json")
    parser.add_argument("--output-dir", type=Path, default=HERE / "outputs/agreement")
    args = parser.parse_args()
    summary, cases = summarize(args.manifest, args.first, args.second)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (args.output_dir / "cases.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted({key for row in cases for key in row}))
        writer.writeheader()
        writer.writerows(cases)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
