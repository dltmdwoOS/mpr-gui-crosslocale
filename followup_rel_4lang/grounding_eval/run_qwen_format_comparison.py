"""Bounded Qwen grounding format diagnostic on locked pilot items only.

Runs four prompt arms on eight existing positive controls, then the plain
coordinate arm on 96 existing phrase O/R pilot inputs. These results are
exploratory and do not replace the locked v3 protocol or its gate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from qwen_vl_utils import process_vision_info

from build_protocol_inputs import REPO, render_qwen_user_prompt
from point_format import point_in_box, score_qwen_point
from run_qwen_pilot import (
    DEFAULT_OUTPUT,
    GT_PATH,
    MODEL_ID,
    PERSONAL_CACHE,
    PHRASE_OUTPUT,
    REVISION,
    _load_inputs,
    _load_model_streamed,
    _load_phrase_descriptors,
    _load_processor,
    _preflight_image,
    _read_jsonl,
    _trials,
)


OUTPUT_DIR = REPO / "followup_rel_4lang/results/grounding_format_comparison_v1"
JSON_SUFFIX = 'Return only this JSON array: [{"point_2d": [x, y]}]. No explanation or code fence.'
TUPLE_SUFFIX = 'Return only one coordinate as (x, y). No explanation or code fence.'
TUPLE_POINT = re.compile(r"\(\s*([0-9]+)\s*,\s*([0-9]+)\s*\)\Z")
ARMS = ("full_json", "full_tuple", "phrase_json", "phrase_tuple")


def _tuple_prompt(json_prompt: str) -> str:
    assert json_prompt.count(JSON_SUFFIX) == 1
    return json_prompt.replace(JSON_SUFFIX, TUPLE_SUFFIX)


def _score_tuple(
    raw: str, gt_box: list[float], original_size: list[int], model_size: tuple[int, int],
) -> dict:
    match = TUPLE_POINT.fullmatch(raw)
    point = tuple(map(int, match.groups())) if match else None
    width, height = model_size
    if point is not None and not (0 <= point[0] <= width and 0 <= point[1] <= height):
        point = None
    original = (
        point[0] * original_size[0] / width,
        point[1] * original_size[1] / height,
    ) if point is not None else None
    return {
        "parsed_point_model_pixels": list(point) if point is not None else None,
        "point_original_pixels": list(original) if original is not None else None,
        "valid_output": point is not None,
        "requested_format_adherent": point is not None,
        "point_in_gt_box": point_in_box(original, gt_box) if original is not None else False,
    }


def _prepare_trials(controls: list[dict], pilot: list[dict], descriptors: dict) -> tuple[list[dict], list[dict]]:
    full_controls, _ = _trials(controls, pilot)
    phrase_controls, phrase_pilot = _trials(controls, pilot, descriptors)
    assert [trial["trial_id"] for trial in full_controls] == [
        trial["trial_id"] for trial in phrase_controls
    ]
    control_trials = []
    for full, phrase in zip(full_controls, phrase_controls, strict=True):
        for arm in ARMS:
            selected = full if arm.startswith("full") else phrase
            control_trials.append({**selected, "trial_id": f"{selected['trial_id']}::{arm}", "arm": arm})
    pilot_trials = [
        {**trial, "trial_id": f"{trial['trial_id']}::phrase_tuple", "arm": "phrase_tuple"}
        for trial in phrase_pilot
    ]
    assert len(control_trials) == 32 and len(pilot_trials) == 96
    assert len({trial["trial_id"] for trial in control_trials + pilot_trials}) == 128
    return control_trials, pilot_trials


def _prompt(trial: dict, info: dict, phrase_template: str) -> str:
    if trial["arm"].startswith("full"):
        user_prompt = render_qwen_user_prompt(
            trial["marked_stem"], info["model_width"], info["model_height"],
        )
    else:
        user_prompt = phrase_template.format(
            descriptor=trial["marked_stem"],
            model_width=info["model_width"], model_height=info["model_height"],
        )
    assert user_prompt.count(JSON_SUFFIX) == 1
    return _tuple_prompt(user_prompt) if trial["arm"].endswith("tuple") else user_prompt


def _generate_one(
    model, processor, trial: dict, info: dict, gt: dict, lock_hash: str,
    descriptor_hash: str, phrase_template: str, min_pixels: int, max_pixels: int,
) -> dict:
    import torch

    row = trial["row"]
    path = REPO / row["image_path"]
    user_prompt = _prompt(trial, info, phrase_template)
    messages = [{"role": "user", "content": [
        {"type": "image", "image": path.as_posix()},
        {"type": "text", "text": user_prompt},
    ]}]
    rendered = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    images, videos = process_vision_info(messages)
    inputs = processor(text=[rendered], images=images, videos=videos, return_tensors="pt")
    grid = inputs["image_grid_thw"][0].tolist()
    assert grid == info["grid"] and list(images[0].size) == info["intermediate_size"]
    inputs = inputs.to(model.device)
    with torch.inference_mode():
        generated = model.generate(**inputs, do_sample=False, num_beams=1, max_new_tokens=64)
    raw = processor.batch_decode(
        generated[:, inputs.input_ids.shape[1]:],
        skip_special_tokens=True, clean_up_tokenization_spaces=False,
    )[0].strip()
    annotation = gt[row["parallel_id"]][row["gui_language"]]
    model_size = info["model_width"], info["model_height"]
    if trial["arm"].endswith("json"):
        score = score_qwen_point(
            raw, annotation["bbox"], *annotation["image_size"], *model_size,
        )
    else:
        score = _score_tuple(raw, annotation["bbox"], annotation["image_size"], model_size)
    return {
        "schema": "rel-grounding-qwen-format-comparison-v1",
        "trial_id": trial["trial_id"], "phase": trial["phase"], "arm": trial["arm"],
        "pair_id": row.get("pair_id"), "parallel_id": row["parallel_id"],
        "condition": trial["condition"],
        "query_language": row.get("query_language", row["gui_language"]),
        "gui_language": row["gui_language"], "image_path": row["image_path"],
        "image_sha256": row["image_sha256"], "input_lock_sha256": lock_hash,
        "descriptor_sha256": descriptor_hash if trial["arm"].startswith("phrase") else None,
        "model_id": MODEL_ID, "revision": REVISION,
        "min_pixels": min_pixels, "max_pixels": max_pixels,
        "image_grid_thw": grid, "intermediate_image_size": info["intermediate_size"],
        "original_image_size": info["original_size"], "rendered_prompt": rendered,
        "raw_output": raw, "output_tokens": int(generated.shape[1] - inputs.input_ids.shape[1]),
        "max_new_tokens": 64, "do_sample": False, "num_beams": 1,
        **score,
    }


def _existing(
    path: Path, expected: dict[str, dict], info_by_path: dict,
    phrase_template: str, lock_hash: str, descriptor_hash: str,
) -> dict[str, dict]:
    if not path.exists():
        return {}
    rows = _read_jsonl(path)
    records = {row["trial_id"]: row for row in rows}
    assert len(records) == len(rows) and set(records) <= set(expected)
    for row in rows:
        trial = expected[row["trial_id"]]
        info = info_by_path[REPO / trial["row"]["image_path"]]
        assert row["schema"] == "rel-grounding-qwen-format-comparison-v1"
        assert row["revision"] == REVISION and row["input_lock_sha256"] == lock_hash
        assert row["arm"] == trial["arm"] and row["image_sha256"] == trial["row"]["image_sha256"]
        assert row["image_grid_thw"] == info["grid"]
        assert row["descriptor_sha256"] == (descriptor_hash if row["arm"].startswith("phrase") else None)
        assert row["rendered_prompt"].count(_prompt(trial, info, phrase_template)) == 1
    return records


def _write_record(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _summary(controls: dict[str, dict], pilot: dict[str, dict]) -> dict:
    by_arm = {}
    for arm in ARMS:
        rows = [row for row in controls.values() if row["arm"] == arm]
        by_arm[arm] = {
            "count": len(rows), "valid": sum(row["valid_output"] for row in rows),
            "format_adherent": sum(row["requested_format_adherent"] for row in rows),
            "hit": sum(row["point_in_gt_box"] for row in rows),
        }
    pilot_rows = list(pilot.values())
    return {
        "schema": "rel-grounding-qwen-format-comparison-summary-v1",
        "controls": by_arm,
        "pilot_phrase_tuple": {
            "count": len(pilot_rows), "valid": sum(row["valid_output"] for row in pilot_rows),
            "hit_O": sum(row["point_in_gt_box"] for row in pilot_rows if row["condition"] == "O"),
            "hit_R": sum(row["point_in_gt_box"] for row in pilot_rows if row["condition"] == "R"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    os.environ["XDG_CACHE_HOME"] = str(PERSONAL_CACHE)
    os.environ["HF_HOME"] = str(PERSONAL_CACHE / "huggingface")
    os.environ["TORCH_HOME"] = str(PERSONAL_CACHE / "torch")
    os.environ["PIP_CACHE_DIR"] = str(PERSONAL_CACHE / "pip")
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[name] = "3"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)

    controls, pilot, lock_hash = _load_inputs()
    descriptors, phrase_template, descriptor_hash = _load_phrase_descriptors(controls, pilot)
    control_trials, pilot_trials = _prepare_trials(controls, pilot, descriptors)
    gt = json.loads(GT_PATH.read_text(encoding="utf-8"))["annotations"]
    processor, snapshot, min_pixels, max_pixels = _load_processor()
    info_by_path = {}
    for trial in control_trials + pilot_trials:
        row = trial["row"]
        path = REPO / row["image_path"]
        if path not in info_by_path:
            annotation = gt[row["parallel_id"]][row["gui_language"]]
            assert annotation["image_sha256"] == row["image_sha256"]
            info_by_path[path] = _preflight_image(
                processor, path, row["image_sha256"], annotation["image_size"],
            )
    print(json.dumps({"control_trials": len(control_trials), "pilot_trials": len(pilot_trials),
                      "unique_images": len(info_by_path), "input_lock_sha256": lock_hash}, indent=2), flush=True)
    if args.preflight_only:
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    control_path = OUTPUT_DIR / "controls.jsonl"
    pilot_path = OUTPUT_DIR / "pilot_phrase_tuple.jsonl"
    current_controls = _existing(
        control_path, {trial["trial_id"]: trial for trial in control_trials},
        info_by_path, phrase_template, lock_hash, descriptor_hash,
    )
    current_pilot = _existing(
        pilot_path, {trial["trial_id"]: trial for trial in pilot_trials},
        info_by_path, phrase_template, lock_hash, descriptor_hash,
    )
    if len(current_controls) == len(control_trials) and len(current_pilot) == len(pilot_trials):
        print(json.dumps(_summary(current_controls, current_pilot), indent=2), flush=True)
        return
    model = _load_model_streamed(snapshot)
    for path, trials, records in ((control_path, control_trials, current_controls),
                                  (pilot_path, pilot_trials, current_pilot)):
        for trial in trials:
            if trial["trial_id"] in records:
                continue
            record = _generate_one(
                model, processor, trial, info_by_path[REPO / trial["row"]["image_path"]],
                gt, lock_hash, descriptor_hash, phrase_template, min_pixels, max_pixels,
            )
            _write_record(path, record)
            records[trial["trial_id"]] = record
            print(f"{trial['phase']} {len(records)}/{len(trials)} {trial['arm']}: "
                  f"valid={record['valid_output']} hit={record['point_in_gt_box']}", flush=True)
            (OUTPUT_DIR / "summary.json").write_text(
                json.dumps(_summary(current_controls, current_pilot), indent=2) + "\n", encoding="utf-8",
            )
    print(json.dumps(_summary(current_controls, current_pilot), indent=2), flush=True)


if __name__ == "__main__":
    main()
