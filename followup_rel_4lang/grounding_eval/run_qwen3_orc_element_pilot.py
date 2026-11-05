"""Quick Qwen3-VL O/R/C element-only pilot, defaulting to four language pairs."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from collections import Counter
from pathlib import Path

if __package__:
    from .run_qwen3_prompt_pilot import (
        HERE, MODEL_ID, PERSONAL_CACHE, PROMPT, REPO, REVISION, SNAPSHOT, _score, _sha256,
    )
else:
    from run_qwen3_prompt_pilot import (
        HERE, MODEL_ID, PERSONAL_CACHE, PROMPT, REPO, REVISION, SNAPSHOT, _score, _sha256,
    )


PILOT_PAIRS = (("en", "zh"), ("zh", "th"), ("th", "ru"), ("ru", "en"))
CONDITIONS = ("O", "R", "C")
OUTPUT = REPO / "followup_rel_4lang/results/grounding_pilot_qwen3_8b_orc_element_only"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _pairs(only_pair_id: str | None = None) -> list[dict]:
    gt = json.loads((HERE / "annotations_20261103/grounding_gt_draft_170.json").read_text())
    phrases = json.loads((HERE / "pilot_referent_phrases.json").read_text())["descriptors"]
    data = REPO / "followup_rel_4lang/data/rel_all_366"
    rows = _read_jsonl(data / "conditions_4lang.jsonl")
    mappings = {row["parallel_id"]: row for row in _read_jsonl(data / "reference_mappings.jsonl")}
    ids = sorted(gt["gt_assembly"]["pilot_item_ids"])
    assert len(ids) == 12 and set(ids) == set(phrases)
    by_key = {(row["parallel_id"], row["query_language"], row["gui_language"], row["condition"]): row
              for row in rows if row["parallel_id"] in ids}
    pairs = []
    for index, pid in enumerate(ids):
        source, gui = PILOT_PAIRS[index % 4]
        pair_id = f"{pid}::{source}::{gui}"
        if only_pair_id is not None and pair_id != only_pair_id:
            continue
        subset = {condition: by_key[pid, source, gui, condition] for condition in CONDITIONS}
        assert len({row["image_path"] for row in subset.values()}) == 1
        mapping = mappings[pid]["spans"]
        source_span = mapping[source]["question_stem"]
        gui_span = mapping[gui]["question_stem"]
        assert len(source_span) == len(gui_span) == 1
        assert source_span[0]["ref_id"] == gui_span[0]["ref_id"]
        source_ref, gui_ref = source_span[0]["text"], gui_span[0]["text"]
        descriptors = {
            "O": phrases[pid][source].format(ref=f"<ref>{source_ref}</ref>"),
            "R": phrases[pid][source].format(ref=f"<ref>{gui_ref}</ref>"),
            "C": phrases[pid][gui].format(ref=f"<ref>{source_ref}</ref>"),
        }
        for condition in CONDITIONS:
            plain = descriptors[condition].replace("<ref>", "").replace("</ref>", "")
            assert plain in subset[condition]["question_stem"], (pid, source, gui, condition)
        image_path = REPO / "followup_rel_4lang" / subset["O"]["image_path"]
        annotation = gt["annotations"][pid][gui]
        assert image_path.is_file() and _sha256(image_path) == annotation["image_sha256"]
        pairs.append({
            "pair_id": pair_id, "parallel_id": pid,
            "source_language": source, "gui_language": gui,
            "image_path": image_path, "image_sha256": annotation["image_sha256"],
            "image_size": annotation["image_size"], "gt_bbox": annotation["bbox"],
            "descriptors": descriptors,
            "questions": {condition: subset[condition]["question_stem"] for condition in CONDITIONS},
        })
    assert len(pairs) == (1 if only_pair_id is not None else 12)
    assert len({pair["pair_id"] for pair in pairs}) == len(pairs)
    if only_pair_id is None:
        assert Counter(pair["gui_language"] for pair in pairs) == {x: 3 for x in ("en", "zh", "th", "ru")}
    return pairs


def _existing(path: Path, pairs: list[dict]) -> dict[str, dict]:
    if not path.exists():
        return {}
    rows = _read_jsonl(path)
    by_id = {row["trial_id"]: row for row in rows}
    expected = {f"{pair['pair_id']}::{condition}" for pair in pairs for condition in CONDITIONS}
    assert len(rows) == len(by_id) and set(by_id) <= expected
    by_pair = {pair["pair_id"]: pair for pair in pairs}
    for row in rows:
        pair = by_pair[row["pair_id"]]
        assert row["model_id"] == MODEL_ID and row["revision"] == REVISION
        assert row["image_sha256"] == pair["image_sha256"]
        assert row["gt_bbox"] == pair["gt_bbox"] and row["image_size"] == pair["image_size"]
        assert row["marked_text"] == pair["descriptors"][row["condition"]]
        assert row["batch_size"] == 3 and row["attn_implementation"] == "sdpa"
    return by_id


def _summary(rows: list[dict]) -> dict:
    by_condition = {}
    for condition in CONDITIONS:
        subset = [row for row in rows if row["condition"] == condition]
        by_condition[condition] = {
            "count": len(subset), "valid": sum(row["valid_output"] for row in subset),
            "hit": sum(row["point_in_gt_box"] for row in subset),
            "addCriterion": sum("addCriterion" in row["raw_output"] for row in subset),
            "eos_stop": sum(row["stop_reason"] == "eos" for row in subset),
        }
    by_pair = {}
    for row in rows:
        by_pair.setdefault(row["pair_id"], {})[row["condition"]] = row
    complete = [group for group in by_pair.values() if set(group) == set(CONDITIONS)]
    durations = [group["O"]["generate_s"] for group in complete]
    preprocessing = [group["O"]["preprocess_s"] for group in complete]
    profiled = [group["O"] for group in complete if "prefill_forward_s" in group["O"]]
    return {
        "schema": "qwen3-vl-8b-orc-element-only-quick-pilot-v1",
        "model_id": MODEL_ID, "revision": REVISION,
        "selected_pairs": len(by_pair), "complete_pairs": len(complete),
        "conditions": by_condition,
        "generate_s_median_per_batch": statistics.median(durations) if durations else None,
        "preprocess_s_median_per_batch": statistics.median(preprocessing) if preprocessing else None,
        "profiled_batch_count": len(profiled),
        "prefill_s_median": statistics.median(row["prefill_forward_s"] for row in profiled)
        if profiled else None,
        "decode_s_median": statistics.median(row["decode_forward_s"] for row in profiled)
        if profiled else None,
        "prefill_share_median": statistics.median(
            row["prefill_forward_s"] / row["generate_s"] for row in profiled
        ) if profiled else None,
        "max_peak_gpu_gib": max((row["peak_gpu_gib"] for row in rows), default=None),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--limit-pairs", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.limit_pairs <= 12:
        parser.error("--limit-pairs must be 1..12")
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

    pairs = _pairs()
    selected = pairs[:args.limit_pairs]
    index = json.loads((SNAPSHOT / "model.safetensors.index.json").read_text())
    assert len(set(index["weight_map"].values())) == 4
    assert all((SNAPSHOT / shard).is_file() for shard in set(index["weight_map"].values()))
    processor = AutoProcessor.from_pretrained(
        SNAPSHOT, local_files_only=True, min_pixels=262144, max_pixels=2097152,
    )
    processor.tokenizer.padding_side = "left"
    assert int(processor.image_processor.patch_size) == 16
    print(json.dumps({"pairs": len(selected), "trials": len(selected) * 3,
                      "revision": REVISION, "transformers": transformers.__version__,
                      "torch": torch.__version__}, indent=2), flush=True)
    if args.preflight_only:
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "predictions.jsonl"
    existing = _existing(path, pairs)
    if all(f"{pair['pair_id']}::{condition}" in existing
           for pair in selected for condition in CONDITIONS):
        summary = _summary(list(existing.values()))
        (OUTPUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        return

    torch.set_num_threads(3)
    t_load = time.perf_counter()
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        SNAPSHOT, local_files_only=True, dtype=torch.bfloat16,
        attn_implementation="sdpa", device_map={"": "cuda:0"}, low_cpu_mem_usage=True,
    )
    load_s = time.perf_counter() - t_load
    assert all(param.device.type == "cuda" for param in model.parameters())
    assert model.config._attn_implementation == "sdpa"
    model.eval()
    eos = model.generation_config.eos_token_id
    eos_ids = {eos} if isinstance(eos, int) else set(eos or [])
    print(f"Model loaded in {load_s:.1f}s", flush=True)

    for pair in selected:
        if all(f"{pair['pair_id']}::{condition}" in existing for condition in CONDITIONS):
            continue
        t_start = time.perf_counter()
        conversations = [[{"role": "user", "content": [
            {"type": "image", "image": pair["image_path"].as_posix()},
            {"type": "text", "text": PROMPT.format(text=pair["descriptors"][condition])},
        ]}] for condition in CONDITIONS]
        rendered = [processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                    for messages in conversations]
        images, videos = process_vision_info(conversations, image_patch_size=16)
        inputs = processor(text=rendered, images=images, videos=videos,
                           padding=True, return_tensors="pt")
        assert inputs.input_ids.shape[0] == 3 and inputs["image_grid_thw"].shape[0] == 3
        grids = inputs["image_grid_thw"].tolist()
        assert grids[0] == grids[1] == grids[2]
        prompt_lengths = inputs.attention_mask.sum(dim=1).tolist()
        inputs = inputs.to(model.device)
        preprocess_s = time.perf_counter() - t_start
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        starts: list[float] = []
        forward_s: list[float] = []

        def before_forward(_module, _inputs):
            torch.cuda.synchronize()
            starts.append(time.perf_counter())

        def after_forward(_module, _inputs, _output):
            torch.cuda.synchronize()
            forward_s.append(time.perf_counter() - starts.pop())

        before_hook = model.register_forward_pre_hook(before_forward)
        after_hook = model.register_forward_hook(after_forward)
        t_generate = time.perf_counter()
        try:
            with torch.inference_mode():
                generated = model.generate(**inputs, do_sample=False, num_beams=1, max_new_tokens=64)
        finally:
            before_hook.remove()
            after_hook.remove()
        torch.cuda.synchronize()
        generate_s = time.perf_counter() - t_generate
        assert forward_s and not starts
        prefill_s, decode_s = forward_s[0], sum(forward_s[1:])
        peak_gpu_gib = torch.cuda.max_memory_allocated() / 2**30
        padded_prompt_len = inputs.input_ids.shape[1]
        for row_index, condition in enumerate(CONDITIONS):
            suffix = generated[row_index, padded_prompt_len:].detach().cpu().tolist()
            stop = next((i for i, token in enumerate(suffix) if token in eos_ids), None)
            tokens = suffix[:stop + 1] if stop is not None else suffix
            raw = processor.decode(tokens, skip_special_tokens=True,
                                   clean_up_tokenization_spaces=False).strip()
            record = {
                "schema": "qwen3-vl-8b-orc-element-only-quick-pilot-v1",
                "trial_id": f"{pair['pair_id']}::{condition}", "pair_id": pair["pair_id"],
                "parallel_id": pair["parallel_id"], "source_language": pair["source_language"],
                "gui_language": pair["gui_language"], "condition": condition,
                "model_id": MODEL_ID, "revision": REVISION,
                "transformers_version": transformers.__version__, "torch_version": torch.__version__,
                "dtype": "bfloat16", "attn_implementation": "sdpa", "batch_size": 3,
                "min_pixels": 262144, "max_pixels": 2097152,
                "do_sample": False, "num_beams": 1, "max_new_tokens": 64,
                "eos_token_ids": sorted(eos_ids), "model_load_s": load_s,
                "preprocess_s": round(preprocess_s, 3),
                "generate_s": round(generate_s, 3), "peak_gpu_gib": round(peak_gpu_gib, 3),
                "prefill_forward_s": round(prefill_s, 3),
                "decode_forward_s": round(decode_s, 3), "forward_calls": len(forward_s),
                "image_path": pair["image_path"].relative_to(REPO).as_posix(),
                "image_sha256": pair["image_sha256"], "image_size": pair["image_size"],
                "image_grid_thw": grids[row_index], "gt_bbox": pair["gt_bbox"],
                "question_stem": pair["questions"][condition],
                "marked_text": pair["descriptors"][condition],
                "rendered_prompt": rendered[row_index], "prompt_tokens": prompt_lengths[row_index],
                "raw_output": raw, "generated_token_ids": tokens, "output_tokens": len(tokens),
                "stop_reason": "eos" if stop is not None else "length",
                **_score(raw, pair),
            }
            trial_id = record["trial_id"]
            if trial_id not in existing:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                existing[trial_id] = record
            print(f"{trial_id} valid={record['valid_output']} hit={record['point_in_gt_box']} "
                  f"add={raw.count('addCriterion')} stop={record['stop_reason']}", flush=True)
        print(f"batch generate={generate_s:.1f}s preprocess={preprocess_s:.1f}s "
              f"prefill={prefill_s:.1f}s decode={decode_s:.1f}s "
              f"peak_gpu={peak_gpu_gib:.1f}GiB", flush=True)
        summary = _summary(list(existing.values()))
        (OUTPUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(_summary(list(existing.values())), ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
