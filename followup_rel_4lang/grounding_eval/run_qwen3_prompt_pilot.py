"""Run a bounded, same-language Qwen3-VL grounding prompt diagnostic.

The 12 locked pilot items have four GUI locales each. On every screen, ask for
the marked reference element using either the full relation question or just
its short referring phrase. No O/R condition or cross-language contrast runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path

from PIL import Image

from point_format import point_in_box


REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PERSONAL_CACHE = Path("/home/jovyan/seungjae/.cache")
SNAPSHOT = (PERSONAL_CACHE / "huggingface/hub/models--Qwen--Qwen3-VL-8B-Instruct"
            / "snapshots/0c351dd01ed87e9c1b53cbc748cba10e6187ff3b")
MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"
REVISION = SNAPSHOT.name
OUTPUT = REPO / "followup_rel_4lang/results/grounding_pilot_qwen3_8b_prompts"
CONTROL_IDS = ("rel::1/booking_1.jpg", "rel::5/message_1.jpg")
LOCALES = ("en", "zh", "th", "ru")
ARMS = ("query_informed", "element_only")
POINT = re.compile(r"\(\s*([0-9]{1,4})\s*,\s*([0-9]{1,4})\s*\)\Z")
PROMPT = (
    "Locate the GUI reference element marked by <ref>...</ref> in the text below. "
    "Use surrounding words to identify it. Do not answer a relation question.\n"
    "Text: {text}\n"
    "Return only one point as (x, y), with integer x and y from 0 to 1000 "
    "relative to the full screenshot. (0, 0) is the top-left and (1000, 1000) "
    "is the bottom-right. No explanation or code fence."
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inputs() -> list[dict]:
    manifest = json.loads((REPO / "annotation/rel_grounding/data/full_manifest.json").read_text())
    gt = json.loads((HERE / "annotations_20261103/grounding_gt_draft_170.json").read_text())
    phrases = json.loads((HERE / "pilot_referent_phrases.json").read_text())
    pilot_ids = set(gt["gt_assembly"]["pilot_item_ids"])
    assert len(pilot_ids) == 12 and set(phrases["descriptors"]) == pilot_ids
    items = {item["parallel_id"]: item for item in manifest["items"] if item["parallel_id"] in pilot_ids}
    assert set(items) == pilot_ids
    ordered = list(CONTROL_IDS) + sorted(pilot_ids - set(CONTROL_IDS))
    screens = []
    for pid in ordered:
        for gui in LOCALES:
            locale = items[pid]["locales"][gui]
            span = locale["stem_span"]
            question = locale["question_stem"]
            assert question[span["start"]:span["end"]] == span["text"]
            ref = f"<ref>{span['text']}</ref>"
            marked = question[:span["start"]] + ref + question[span["end"]:]
            descriptor = phrases["descriptors"][pid][gui].format(ref=ref)
            assert descriptor in marked, (pid, gui)
            image_path = REPO / "followup_rel_4lang" / locale["image_path"]
            annotation = gt["annotations"][pid][gui]
            assert image_path.is_file()
            assert _sha256(image_path) == locale["image_sha256"] == annotation["image_sha256"]
            with Image.open(image_path) as image:
                assert list(image.size) == annotation["image_size"]
            screens.append({
                "screen_id": f"{pid}::{gui}", "parallel_id": pid, "gui_language": gui,
                "image_path": image_path, "image_sha256": locale["image_sha256"],
                "image_size": annotation["image_size"], "gt_bbox": annotation["bbox"],
                "query_informed_text": marked, "element_only_text": descriptor,
                "control": pid in CONTROL_IDS,
            })
    assert len(screens) == 48
    return screens


def _existing(path: Path, screens: list[dict]) -> dict[str, dict]:
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    by_id = {row["trial_id"]: row for row in rows}
    expected = {f"{screen['screen_id']}::{arm}" for screen in screens for arm in ARMS}
    assert len(by_id) == len(rows) and set(by_id) <= expected
    by_screen = {screen["screen_id"]: screen for screen in screens}
    for row in rows:
        screen = by_screen[row["screen_id"]]
        assert row["revision"] == REVISION
        assert row["image_sha256"] == screen["image_sha256"]
        assert row["image_size"] == screen["image_size"] and row["gt_bbox"] == screen["gt_bbox"]
        assert row["marked_text"] == screen[f"{row['arm']}_text"]
        assert row["prompt_template_sha256"] == hashlib.sha256(PROMPT.encode()).hexdigest()
    return by_id


def _score(raw: str, screen: dict) -> dict:
    match = POINT.fullmatch(raw)
    point = tuple(map(int, match.groups())) if match else None
    if point is not None and not all(0 <= value <= 1000 for value in point):
        point = None
    width, height = screen["image_size"]
    original = (point[0] * width / 1000, point[1] * height / 1000) if point else None
    return {
        "valid_output": point is not None,
        "point_1000": list(point) if point else None,
        "point_original_pixels": list(original) if original else None,
        "point_in_gt_box": point_in_box(original, screen["gt_bbox"]) if original else False,
    }


def _summary(rows: list[dict]) -> dict:
    result = {"schema": "qwen3-vl-8b-grounding-two-prompt-pilot-v1",
              "model_id": MODEL_ID, "revision": REVISION, "arms": {}}
    for arm in ARMS:
        subset = [row for row in rows if row["arm"] == arm]
        result["arms"][arm] = {
            "count": len(subset),
            "valid": sum(row["valid_output"] for row in subset),
            "hit": sum(row["point_in_gt_box"] for row in subset),
            "addCriterion": sum("addCriterion" in row["raw_output"] for row in subset),
            "eos_stop": sum(row["stop_reason"] == "eos" for row in subset),
            "control_count": sum(row["control"] for row in subset),
            "control_valid": sum(row["valid_output"] for row in subset if row["control"]),
            "control_hit": sum(row["point_in_gt_box"] for row in subset if row["control"]),
            "by_gui": {gui: {
                "count": sum(row["gui_language"] == gui for row in subset),
                "valid": sum(row["valid_output"] for row in subset if row["gui_language"] == gui),
                "hit": sum(row["point_in_gt_box"] for row in subset if row["gui_language"] == gui),
            } for gui in LOCALES},
        }
    paired = {}
    for row in rows:
        paired.setdefault(row["screen_id"], {})[row["arm"]] = row
    complete = [pair for pair in paired.values() if set(pair) == set(ARMS)]
    result["complete_screen_pairs"] = len(complete)
    result["hit_transition"] = dict(Counter(
        f"{int(pair['query_informed']['point_in_gt_box'])}->"
        f"{int(pair['element_only']['point_in_gt_box'])}" for pair in complete
    ))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--limit-screens", type=int, default=48)
    args = parser.parse_args()
    if not 1 <= args.limit_screens <= 48:
        parser.error("--limit-screens must be 1..48")

    os.environ.update({
        "XDG_CACHE_HOME": str(PERSONAL_CACHE),
        "HF_HOME": str(PERSONAL_CACHE / "huggingface"),
        "TORCH_HOME": str(PERSONAL_CACHE / "torch"),
        "PIP_CACHE_DIR": str(PERSONAL_CACHE / "pip"),
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        "OMP_NUM_THREADS": "3", "MKL_NUM_THREADS": "3",
        "OPENBLAS_NUM_THREADS": "3", "TOKENIZERS_PARALLELISM": "false",
    })
    import torch
    import transformers
    from qwen_vl_utils import process_vision_info
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    screens = _inputs()
    selected = screens[:args.limit_screens]
    index = json.loads((SNAPSHOT / "model.safetensors.index.json").read_text())
    shards = set(index["weight_map"].values())
    assert len(shards) == 4 and all((SNAPSHOT / shard).is_file() for shard in shards)
    processor = AutoProcessor.from_pretrained(
        SNAPSHOT, local_files_only=True, min_pixels=262144, max_pixels=2097152,
    )
    processor.tokenizer.padding_side = "left"
    assert int(processor.image_processor.patch_size) == 16
    print(json.dumps({"screens": len(selected), "trials": len(selected) * 2,
                      "revision": REVISION, "transformers": transformers.__version__,
                      "torch": torch.__version__}, indent=2), flush=True)
    if args.preflight_only:
        return

    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "predictions.jsonl"
    existing = _existing(path, screens)
    if all(f"{screen['screen_id']}::{arm}" in existing for screen in selected for arm in ARMS):
        summary = _summary(list(existing.values()))
        (OUTPUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        return
    torch.set_num_threads(3)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        SNAPSHOT, local_files_only=True, dtype=torch.bfloat16,
        attn_implementation="sdpa", device_map={"": "cuda:0"},
        low_cpu_mem_usage=True,
    )
    assert all(param.device.type == "cuda" for param in model.parameters())
    assert model.config._attn_implementation == "sdpa"
    model.eval()
    eos = model.generation_config.eos_token_id
    eos_ids = {eos} if isinstance(eos, int) else set(eos or [])

    for screen in selected:
        for arm in ARMS:
            trial_id = f"{screen['screen_id']}::{arm}"
            if trial_id in existing:
                continue
            user_prompt = PROMPT.format(text=screen[f"{arm}_text"])
            messages = [{"role": "user", "content": [
                {"type": "image", "image": screen["image_path"].as_posix()},
                {"type": "text", "text": user_prompt},
            ]}]
            rendered = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            images, videos = process_vision_info(messages, image_patch_size=16)
            inputs = processor(text=[rendered], images=images, videos=videos, return_tensors="pt")
            grid = inputs["image_grid_thw"][0].tolist()
            inputs = inputs.to(model.device)
            with torch.inference_mode():
                output = model.generate(**inputs, do_sample=False, num_beams=1, max_new_tokens=64)
            tokens = output[0, inputs.input_ids.shape[1]:].detach().cpu().tolist()
            raw = processor.decode(tokens, skip_special_tokens=True,
                                   clean_up_tokenization_spaces=False).strip()
            record = {
                "schema": "qwen3-vl-8b-grounding-two-prompt-pilot-v1",
                "trial_id": trial_id, "screen_id": screen["screen_id"],
                "parallel_id": screen["parallel_id"], "gui_language": screen["gui_language"],
                "query_language": screen["gui_language"], "arm": arm,
                "control": screen["control"], "model_id": MODEL_ID, "revision": REVISION,
                "transformers_version": transformers.__version__, "torch_version": torch.__version__,
                "dtype": "bfloat16", "attn_implementation": "sdpa",
                "min_pixels": 262144, "max_pixels": 2097152,
                "do_sample": False, "num_beams": 1, "max_new_tokens": 64,
                "eos_token_ids": sorted(eos_ids), "image_path": screen["image_path"].relative_to(REPO).as_posix(),
                "image_sha256": screen["image_sha256"], "image_size": screen["image_size"],
                "image_grid_thw": grid, "gt_bbox": screen["gt_bbox"],
                "marked_text": screen[f"{arm}_text"], "prompt_template_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
                "rendered_prompt": rendered, "raw_output": raw,
                "generated_token_ids": tokens, "output_tokens": len(tokens),
                "stop_reason": "eos" if tokens and tokens[-1] in eos_ids else "length",
                **_score(raw, screen),
            }
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            existing[trial_id] = record
            print(f"{len(existing)}/{len(selected)*2} {trial_id} "
                  f"valid={record['valid_output']} hit={record['point_in_gt_box']} "
                  f"add={raw.count('addCriterion')} stop={record['stop_reason']}", flush=True)
    summary = _summary(list(existing.values()))
    (OUTPUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
