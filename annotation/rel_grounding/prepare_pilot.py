"""Build model-output-blind pilot and full grounding annotation manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image


REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "followup_rel_4lang/data/rel_all_366"
HERE = Path(__file__).resolve().parent
LANGUAGES = ("en", "zh", "th", "ru")
SEED = 20261026


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def structural_frame(rows: list[dict], mappings: dict[str, dict]) -> list[str]:
    """Select complete 12-pair, single-stem-reference, active 2x2 items."""
    by_pair: dict[tuple[str, str, str], dict[str, dict]] = defaultdict(dict)
    for row in rows:
        if (
            row["text_dependency"] == "dependent"
            and row["query_language"] != row["gui_language"]
            and row["source_issue"] is None
        ):
            key = (row["parallel_id"], row["query_language"], row["gui_language"])
            if row["condition"] in by_pair[key]:
                raise ValueError(f"Duplicate condition for {key}")
            by_pair[key][row["condition"]] = row
    selected = []
    for pid, mapping in sorted(mappings.items()):
        if any(len(mapping["spans"][lang]["question_stem"]) != 1 for lang in LANGUAGES):
            continue
        pairs = [
            by_pair.get((pid, source, gui), {})
            for source in LANGUAGES
            for gui in LANGUAGES
            if source != gui
        ]
        if len(pairs) != 12 or any(set(pair) != {"O", "R", "C", "F"} for pair in pairs):
            continue
        if all(
            pair["O"]["question_stem"] != pair["R"]["question_stem"]
            and pair["O"]["options"] != pair["R"]["options"]
            for pair in pairs
        ):
            selected.append(pid)
    return selected


def pilot_sample(frame: list[str], seed: int = SEED) -> list[str]:
    rng = random.Random(seed)
    groups: dict[str, list[str]] = defaultdict(list)
    for pid in frame:
        groups[pid.split("/", 1)[0]].append(pid)
    if len(groups) != 6 or any(len(pool) < 2 for pool in groups.values()):
        raise ValueError("Expected six REL groups with at least two candidates each")
    chosen = []
    for group in sorted(groups):
        chosen.extend(rng.sample(sorted(groups[group]), 2))
    rng.shuffle(chosen)
    return chosen


def item_manifest(pid: str, mapping: dict, rows: list[dict], root: Path) -> dict:
    asset_root = (root / "followup_rel_4lang").resolve()
    by_gui: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["parallel_id"] == pid and row["condition"] == "O":
            by_gui[row["gui_language"]].add(row["image_path"])
    locales = {}
    for lang in LANGUAGES:
        paths = by_gui[lang]
        if len(paths) != 1:
            raise ValueError(f"Expected one image for {pid}/{lang}: {paths}")
        image_path = next(iter(paths))
        image = (asset_root / image_path).resolve()
        if not image.is_relative_to(asset_root) or not image.is_file():
            raise ValueError(f"Unsafe or missing image: {image_path}")
        with Image.open(image) as loaded:
            width, height = loaded.size
            loaded.verify()
        stem_span = mapping["spans"][lang]["question_stem"][0]
        stem = mapping["fields"][lang]["question_stem"]
        if stem[stem_span["start"]:stem_span["end"]] != stem_span["text"]:
            raise ValueError(f"Stem span mismatch: {pid}/{lang}")
        locales[lang] = {
            "image_path": image_path,
            "image_sha256": sha256(image),
            "width": width,
            "height": height,
            "question_stem": stem,
            "stem_span": stem_span,
            "options": {letter: mapping["fields"][lang][letter] for letter in "ABCD"},
            "option_spans": {letter: mapping["spans"][lang][letter] for letter in "ABCD"},
        }
    return {"parallel_id": pid, "group": pid.split("/", 1)[0], "locales": locales}


def build_packet(root: Path = REPO, seed: int = SEED) -> tuple[dict, dict, dict]:
    data = root / "followup_rel_4lang/data/rel_all_366"
    conditions = data / "conditions_4lang.jsonl"
    references = data / "reference_mappings.jsonl"
    rows = read_jsonl(conditions)
    mappings_list = read_jsonl(references)
    mappings = {row["parallel_id"]: row for row in mappings_list}
    if len(mappings) != len(mappings_list):
        raise ValueError("Duplicate reference mappings")
    frame_ids = structural_frame(rows, mappings)
    pilot_ids = pilot_sample(frame_ids, seed)
    provenance = {
        "conditions_sha256": sha256(conditions),
        "reference_mappings_sha256": sha256(references),
        "seed": seed,
        "selection_rule": "dependent, no source issue, 12 complete mismatched quartets, "
        "one stem span in every language, O/R stem and options differ in all 12 pairs",
    }
    frame = {
        "schema": "rel-grounding-frame-v1",
        "provenance": provenance,
        "item_count": len(frame_ids),
        "items_by_group": dict(sorted(Counter(pid.split("/", 1)[0] for pid in frame_ids).items())),
        "item_ids": frame_ids,
        "pilot_item_ids": pilot_ids,
    }
    full_items = [item_manifest(pid, mappings[pid], rows, root) for pid in frame_ids]
    items_by_id = {item["parallel_id"]: item for item in full_items}
    packet = {
        "schema": "rel-grounding-pilot-v1",
        "provenance": provenance,
        "frame_item_ids_sha256": hashlib.sha256(
            json.dumps(frame_ids, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        "pilot_pairs_per_item": [("en", "zh"), ("zh", "th"), ("th", "ru"), ("ru", "en")],
        "items": [items_by_id[pid] for pid in pilot_ids],
        "model_outputs_included": False,
        "gold_answer_included": False,
    }
    full_packet = {
        "schema": "rel-grounding-full-v1",
        "provenance": provenance,
        "frame_item_ids_sha256": packet["frame_item_ids_sha256"],
        "pilot_item_ids": pilot_ids,
        "items": full_items,
        "model_outputs_included": False,
        "gold_answer_included": False,
    }
    return frame, packet, full_packet


def write_immutable(path: Path, value: dict) -> None:
    content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError(f"Existing packet differs; refusing to overwrite {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--output-dir", type=Path, default=HERE / "data")
    args = parser.parse_args()
    frame, packet, full_packet = build_packet(args.root.resolve(), args.seed)
    write_immutable(args.output_dir / "frame.json", frame)
    write_immutable(args.output_dir / "pilot_manifest.json", packet)
    write_immutable(args.output_dir / "full_manifest.json", full_packet)
    print(json.dumps({"full_items": len(full_packet["items"]), "full_images": 4 * len(full_packet["items"]),
                      "pilot_items": len(packet["items"]),
                      "pilot_ids": frame["pilot_item_ids"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
