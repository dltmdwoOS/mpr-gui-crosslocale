"""Check the paired Qwen JSON/tuple diagnostic against archived pilot records."""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from run_qwen_format_comparison import JSON_SUFFIX, OUTPUT_DIR, TUPLE_SUFFIX
from run_qwen_pilot import DEFAULT_OUTPUT, PHRASE_OUTPUT, REVISION, _read_jsonl


def _by_id(path: Path) -> dict[str, dict]:
    rows = _read_jsonl(path)
    by_id = {row["trial_id"]: row for row in rows}
    assert len(by_id) == len(rows), path
    return by_id


def _counts(rows: list[dict]) -> dict:
    return {
        "n": len(rows), "valid": sum(row["valid_output"] for row in rows),
        "hit": sum(row["point_in_gt_box"] for row in rows),
    }


def _paired(old: dict[str, dict], new: dict[str, dict], field: str) -> dict:
    assert set(old) == set(new)
    counts = Counter((int(old[key][field]), int(new[key][field])) for key in old)
    return {f"{a}->{b}": counts[a, b] for a in (0, 1) for b in (0, 1)}


def _cluster_ci(old: dict[str, dict], new: dict[str, dict], field: str) -> list[float]:
    grouped = defaultdict(list)
    for key, row in old.items():
        grouped[row["parallel_id"]].append(key)
    assert len(grouped) == 12 and all(len(keys) == 8 for keys in grouped.values())
    ids = sorted(grouped)
    rng = random.Random(20261104)
    values = []
    for _ in range(10000):
        picked = (rng.choice(ids) for _ in ids)
        values.append(sum(
            sum(int(new[key][field]) - int(old[key][field]) for key in grouped[item])
            for item in picked
        ) / 96)
    values.sort()
    return [values[250], values[9750]]


def main() -> None:
    controls = _read_jsonl(OUTPUT_DIR / "controls.jsonl")
    assert len(controls) == 32 and len({row["trial_id"] for row in controls}) == 32
    by_arm = {
        arm: {row["trial_id"].rsplit("::", 1)[0]: row for row in controls if row["arm"] == arm}
        for arm in ("full_json", "full_tuple", "phrase_json", "phrase_tuple")
    }
    assert all(len(rows) == 8 for rows in by_arm.values())
    for prefix in ("full", "phrase"):
        for key, json_row in by_arm[prefix + "_json"].items():
            tuple_row = by_arm[prefix + "_tuple"][key]
            assert json_row["rendered_prompt"].replace(JSON_SUFFIX, TUPLE_SUFFIX) == tuple_row["rendered_prompt"]
            assert json_row["image_sha256"] == tuple_row["image_sha256"]
            assert json_row["image_grid_thw"] == tuple_row["image_grid_thw"]

    old_full_controls = _by_id(DEFAULT_OUTPUT / "controls.jsonl")
    old_phrase_controls = _by_id(PHRASE_OUTPUT / "controls.jsonl")
    repeats = {
        "full_json": sum(row["raw_output"] == old_full_controls[key]["raw_output"]
                         for key, row in by_arm["full_json"].items()),
        "phrase_json": sum(row["raw_output"] == old_phrase_controls[key]["raw_output"]
                           for key, row in by_arm["phrase_json"].items()),
    }

    old_pilot = _by_id(PHRASE_OUTPUT / "pilot.jsonl")
    new_pilot = {row["trial_id"].rsplit("::", 1)[0]: row
                 for row in _read_jsonl(OUTPUT_DIR / "pilot_phrase_tuple.jsonl")}
    assert len(old_pilot) == len(new_pilot) == 96 and set(old_pilot) == set(new_pilot)
    for key, old in old_pilot.items():
        new = new_pilot[key]
        assert old["rendered_prompt"].replace(JSON_SUFFIX, TUPLE_SUFFIX) == new["rendered_prompt"]
        assert old["image_sha256"] == new["image_sha256"]
        assert old["image_grid_thw"] == new["image_grid_thw"]
        assert old["revision"] == new["revision"] == REVISION
        assert old["input_lock_sha256"] == new["input_lock_sha256"]

    by_gui = defaultdict(list)
    for key, row in old_pilot.items():
        by_gui[row["gui_language"]].append(key)
    language = {
        gui: {
            "n": len(keys),
            "json_valid": sum(old_pilot[key]["valid_output"] for key in keys),
            "tuple_valid": sum(new_pilot[key]["valid_output"] for key in keys),
            "json_hit": sum(old_pilot[key]["point_in_gt_box"] for key in keys),
            "tuple_hit": sum(new_pilot[key]["point_in_gt_box"] for key in keys),
        }
        for gui, keys in sorted(by_gui.items())
    }
    invalid = [row for row in new_pilot.values() if not row["valid_output"]]
    errors = {
        "addCriterion": sum("addCriterion" in row["raw_output"] for row in invalid),
        "at_64_token_cap": sum(row["output_tokens"] == 64 for row in invalid),
        "complete_parenthesized_pair_anywhere": sum(
            re.search(r"\([0-9]+\s*,\s*[0-9]+\)", row["raw_output"]) is not None
            for row in invalid
        ),
    }
    report = {
        "schema": "rel-grounding-qwen-format-comparison-analysis-v1",
        "controls": {arm: _counts(list(rows.values())) for arm, rows in by_arm.items()},
        "repeated_json_controls_identical_to_archive": repeats,
        "control_format_pairs": {
            prefix: {
                field: _paired(by_arm[prefix + "_json"], by_arm[prefix + "_tuple"], field)
                for field in ("valid_output", "point_in_gt_box")
            }
            for prefix in ("full", "phrase")
        },
        "pilot_phrase": {
            "json": _counts(list(old_pilot.values())),
            "tuple": _counts(list(new_pilot.values())),
            "valid_transitions": _paired(old_pilot, new_pilot, "valid_output"),
            "hit_transitions": _paired(old_pilot, new_pilot, "point_in_gt_box"),
            "valid_delta_95pct_item_bootstrap": _cluster_ci(old_pilot, new_pilot, "valid_output"),
            "hit_delta_95pct_item_bootstrap": _cluster_ci(old_pilot, new_pilot, "point_in_gt_box"),
            "by_gui_language": language,
            "tuple_invalid_output": errors,
        },
    }
    (OUTPUT_DIR / "analysis.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
