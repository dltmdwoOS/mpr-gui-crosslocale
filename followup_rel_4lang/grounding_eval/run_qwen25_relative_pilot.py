"""Run Qwen2.5-VL on the eight saved controls with the Qwen3 relative-point prompt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from qwen_vl_utils import process_vision_info

from run_qwen3_prompt_pilot import CONTROL_IDS, PROMPT, _inputs, _score
from run_qwen_pilot import (
    MODEL_ID, PERSONAL_CACHE, REVISION, _load_processor, _read_jsonl,
)


REPO = Path(__file__).resolve().parents[2]
OUTPUT = REPO / "followup_rel_4lang/results/grounding_pilot_qwen25_relative_controls"
ARMS = ("query_informed", "element_only")
SCHEMA = "qwen25-vl-7b-relative-two-prompt-controls-v1"


def _screens() -> list[dict]:
    selected = _inputs()[:8]
    assert len(selected) == 8 and {row["parallel_id"] for row in selected} == set(CONTROL_IDS)
    locked = _read_jsonl(REPO / "followup_rel_4lang/results/grounding_protocol_inputs_v3/positive_controls.jsonl")
    by_key = {(row["parallel_id"], row["gui_language"]): row for row in locked}
    assert len(by_key) == 8
    for screen in selected:
        row = by_key[screen["parallel_id"], screen["gui_language"]]
        assert screen["query_informed_text"] == row["question"]
        assert screen["image_sha256"] == row["image_sha256"]
        assert screen["image_path"].relative_to(REPO).as_posix() == row["image_path"]
    return selected


def _load_existing(path: Path, screens: list[dict]) -> dict[str, dict]:
    if not path.exists():
        return {}
    rows = _read_jsonl(path)
    by_id = {row["trial_id"]: row for row in rows}
    assert len(by_id) == len(rows)
    expected = {f"{screen['screen_id']}::{arm}" for screen in screens for arm in ARMS}
    assert set(by_id) <= expected
    by_screen = {screen["screen_id"]: screen for screen in screens}
    prompt_hash = hashlib.sha256(PROMPT.encode()).hexdigest()
    for row in rows:
        screen = by_screen[row["screen_id"]]
        assert row["schema"] == SCHEMA and row["model_id"] == MODEL_ID
        assert row["revision"] == REVISION and row["prompt_template_sha256"] == prompt_hash
        assert row["image_sha256"] == screen["image_sha256"]
        assert row["marked_text"] == screen[f"{row['arm']}_text"]
        assert row["gt_bbox"] == screen["gt_bbox"] and row["image_size"] == screen["image_size"]
        assert row["attn_implementation"] == "sdpa"
    return by_id


def _summary(rows: list[dict]) -> dict:
    return {
        "schema": SCHEMA, "model_id": MODEL_ID, "revision": REVISION,
        "prompt_template_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "arms": {arm: {
            "count": sum(row["arm"] == arm for row in rows),
            "valid": sum(row["valid_output"] for row in rows if row["arm"] == arm),
            "hit": sum(row["point_in_gt_box"] for row in rows if row["arm"] == arm),
            "addCriterion": sum("addCriterion" in row["raw_output"] for row in rows if row["arm"] == arm),
            "eos_stop": sum(row["stop_reason"] == "eos" for row in rows if row["arm"] == arm),
        } for arm in ARMS},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--limit-screens", type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.limit_screens <= 8:
        parser.error("--limit-screens must be 1..8")
    os.environ.update({
        "XDG_CACHE_HOME": str(PERSONAL_CACHE),
        "HF_HOME": str(PERSONAL_CACHE / "huggingface"),
        "TORCH_HOME": str(PERSONAL_CACHE / "torch"),
        "PIP_CACHE_DIR": str(PERSONAL_CACHE / "pip"),
        "OMP_NUM_THREADS": "3", "MKL_NUM_THREADS": "3",
        "OPENBLAS_NUM_THREADS": "3", "TOKENIZERS_PARALLELISM": "false",
    })
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
    import torch
    from transformers import Qwen2_5_VLForConditionalGeneration

    all_screens = _screens()
    screens = all_screens[:args.limit_screens]
    processor, snapshot, min_pixels, max_pixels = _load_processor()
    print(json.dumps({"screens": len(screens), "trials": len(screens) * 2,
                      "model_id": MODEL_ID, "revision": REVISION,
                      "relative_coordinates": True, "min_pixels": min_pixels,
                      "max_pixels": max_pixels}, indent=2), flush=True)
    if args.preflight_only:
        screen = screens[0]
        messages = [{"role": "user", "content": [
            {"type": "image", "image": screen["image_path"].as_posix()},
            {"type": "text", "text": PROMPT.format(text=screen["element_only_text"])},
        ]}]
        rendered = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        images, videos = process_vision_info(messages)
        inputs = processor(text=[rendered], images=images, videos=videos, return_tensors="pt")
        assert inputs.input_ids.shape[0] == 1 and len(images) == 1 and not videos
        print(f"Preflight image grid {inputs['image_grid_thw'][0].tolist()}", flush=True)
        return

    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "predictions.jsonl"
    existing = _load_existing(path, all_screens)
    if all(f"{screen['screen_id']}::{arm}" in existing for screen in screens for arm in ARMS):
        summary = _summary(list(existing.values()))
        (OUTPUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        return

    torch.set_num_threads(3)
    assert torch.cuda.is_available()
    free_bytes, _ = torch.cuda.mem_get_info()
    assert free_bytes >= 24 * 2**30, "Insufficient free GPU memory for Qwen2.5-VL 7B"
    index = json.loads((snapshot / "model.safetensors.index.json").read_text())
    shards = set(index["weight_map"].values())
    assert len(shards) == 5 and all((snapshot / shard).is_file() for shard in shards), (
        "Five complete model shards must be cached before inference"
    )
    started = time.perf_counter()
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        snapshot, local_files_only=True, dtype=torch.bfloat16,
        attn_implementation="sdpa", device_map={"": "cuda:0"}, low_cpu_mem_usage=True,
    )
    load_s = time.perf_counter() - started
    assert model.config._attn_implementation == "sdpa"
    assert all(parameter.device.type == "cuda" for parameter in model.parameters())
    model.eval()
    eos = model.generation_config.eos_token_id
    eos_ids = {eos} if isinstance(eos, int) else set(eos or [])
    print(f"Model loaded in {load_s:.1f}s", flush=True)

    for screen in screens:
        for arm in ARMS:
            trial_id = f"{screen['screen_id']}::{arm}"
            if trial_id in existing:
                continue
            marked_text = screen[f"{arm}_text"]
            messages = [{"role": "user", "content": [
                {"type": "image", "image": screen["image_path"].as_posix()},
                {"type": "text", "text": PROMPT.format(text=marked_text)},
            ]}]
            rendered = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            images, videos = process_vision_info(messages)
            inputs = processor(text=[rendered], images=images, videos=videos, return_tensors="pt")
            assert inputs.input_ids.shape[0] == 1 and len(images) == 1 and not videos
            grid = inputs["image_grid_thw"][0].tolist()
            inputs = inputs.to(model.device)
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
            start_generate = time.perf_counter()
            with torch.inference_mode():
                generated = model.generate(**inputs, do_sample=False, num_beams=1, max_new_tokens=64)
            torch.cuda.synchronize()
            generate_s = time.perf_counter() - start_generate
            suffix = generated[0, inputs.input_ids.shape[1]:].detach().cpu().tolist()
            stop = next((i for i, token in enumerate(suffix) if token in eos_ids), None)
            tokens = suffix[:stop + 1] if stop is not None else suffix
            raw = processor.decode(tokens, skip_special_tokens=True,
                                   clean_up_tokenization_spaces=False).strip()
            record = {
                "schema": SCHEMA, "trial_id": trial_id, "screen_id": screen["screen_id"],
                "parallel_id": screen["parallel_id"], "query_language": screen["gui_language"],
                "gui_language": screen["gui_language"], "arm": arm,
                "model_id": MODEL_ID, "revision": REVISION,
                "prompt_template_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
                "attn_implementation": "sdpa", "dtype": "bfloat16",
                "model_loading": "from_pretrained",
                "do_sample": False, "num_beams": 1, "max_new_tokens": 64,
                "min_pixels": min_pixels, "max_pixels": max_pixels,
                "model_load_s": round(load_s, 3), "generate_s": round(generate_s, 3),
                "peak_gpu_gib": round(torch.cuda.max_memory_allocated() / 2**30, 3),
                "image_path": screen["image_path"].relative_to(REPO).as_posix(),
                "image_sha256": screen["image_sha256"], "image_size": screen["image_size"],
                "image_grid_thw": grid, "gt_bbox": screen["gt_bbox"],
                "marked_text": marked_text, "rendered_prompt": rendered,
                "raw_output": raw, "generated_token_ids": tokens,
                "output_tokens": len(tokens), "stop_reason": "eos" if stop is not None else "length",
                **_score(raw, screen),
            }
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            existing[trial_id] = record
            print(f"{trial_id}: raw={raw!r} valid={record['valid_output']} "
                  f"hit={record['point_in_gt_box']} stop={record['stop_reason']} "
                  f"generate={generate_s:.1f}s", flush=True)
            (OUTPUT / "summary.json").write_text(
                json.dumps(_summary(list(existing.values())), ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(_summary(list(existing.values())), ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
