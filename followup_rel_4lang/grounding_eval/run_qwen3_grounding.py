"""Portable Qwen3 grounding controls, pilot and locked main-input execution."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import statistics
import time
from collections import defaultdict
from pathlib import Path

if __package__:
    from .benchmark_qwen3_runtime import _ensure_locked_image
    from .run_qwen3_prompt_pilot import HERE, MODEL_ID, PROMPT, REPO, REVISION, _score
else:
    from benchmark_qwen3_runtime import _ensure_locked_image
    from run_qwen3_prompt_pilot import HERE, MODEL_ID, PROMPT, REPO, REVISION, _score


LOCALES = ("en", "zh", "th", "ru")
CYCLE = (("en", "zh"), ("zh", "th"), ("th", "ru"), ("ru", "en"))
CONDITIONS = ("O", "R", "C", "F")


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def write_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def shard_for(parallel_id: str, num_shards: int) -> int:
    if num_shards < 1:
        raise ValueError("num_shards must be positive")
    return int(hashlib.sha256(parallel_id.encode()).hexdigest(), 16) % num_shards


def build_groups(suite: str, descriptors_path: Path | None = None) -> list[dict]:
    """Build prompts without looking at predictions or exposing GT in messages."""
    gt = json.loads((HERE / "annotations_20261103/grounding_gt_draft_170.json").read_text())
    descriptor_file = descriptors_path or HERE / "pilot_referent_phrases.json"
    descriptor_record = json.loads(descriptor_file.read_text(encoding="utf-8"))
    descriptors = descriptor_record["descriptors"]
    pilot = set(gt["gt_assembly"]["pilot_item_ids"])
    if suite == "main":
        ids = sorted(set(gt["annotations"]) - pilot)
        if descriptors_path is None or set(descriptors) != set(ids):
            raise ValueError("Main execution requires descriptors for exactly the 158 main items")
    elif suite == "controls":
        ids = ["rel::1/booking_1.jpg", "rel::5/message_1.jpg"]
    elif suite == "pilot":
        ids = sorted(pilot)
    else:
        raise ValueError(f"Unknown suite: {suite}")
    data = REPO / "followup_rel_4lang/data/rel_all_366"
    rows = read_jsonl(data / "conditions_4lang.jsonl")
    by_key = {(r["parallel_id"], r["query_language"], r["gui_language"], r["condition"]): r
              for r in rows if r["parallel_id"] in ids}
    mappings = {r["parallel_id"]: r for r in read_jsonl(data / "reference_mappings.jsonl")}
    groups = []
    for pid in ids:
        if set(descriptors[pid]) != set(LOCALES):
            raise ValueError(f"Missing descriptor languages: {pid}")
        pairs = ([(g, g) for g in LOCALES] if suite == "controls" else
                 [(q, g) for q in LOCALES for g in LOCALES if q != g]
                 if suite == "main" else CYCLE)
        for source, gui in pairs:
            pair_id = f"{pid}::{source}::{gui}"
            mapping = mappings[pid]["spans"]
            spans = {lang: mapping[lang]["question_stem"] for lang in LOCALES}
            if any(len(value) != 1 for value in spans.values()):
                raise ValueError(f"Expected exactly one reference span per language: {pid}")
            if len({value[0]["ref_id"] for value in spans.values()}) != 1:
                raise ValueError(f"Reference identities disagree: {pid}")
            annotation = gt["annotations"][pid][gui]
            common = {
                "pair_id": pair_id, "parallel_id": pid, "query_language": source,
                "gui_language": gui, "image_sha256": annotation["image_sha256"],
                "image_size": annotation["image_size"], "gt_bbox": annotation["bbox"],
            }
            trials = []
            for condition in (("O",) if suite == "controls" else CONDITIONS):
                context, ref_language = {"O": (source, source), "R": (source, gui),
                                         "C": (gui, source), "F": (gui, gui)}[condition]
                template = descriptors[pid][context]
                if template.count("{ref}") != 1:
                    raise ValueError(f"Expected one descriptor placeholder: {pid}/{context}")
                text = template.format(ref=f"<ref>{spans[ref_language][0]['text']}</ref>")
                original = by_key[pid, source, gui, condition]
                plain = text.replace("<ref>", "").replace("</ref>", "")
                if plain not in original["question_stem"]:
                    raise ValueError(f"Descriptor is not an exact source substring: {pair_id}/{condition}")
                base = {**common, "image_path": original["image_path"]}
                if suite == "controls":
                    span = spans[source][0]
                    stem = original["question_stem"]
                    if stem[span["start"]:span["end"]] != span["text"]:
                        raise ValueError(f"Reference span offsets disagree: {pair_id}")
                    full = stem[:span["start"]] + "<ref>" + span["text"] + "</ref>" + stem[span["end"]:]
                    for arm, marked in (("query_informed", full), ("element_only", text)):
                        trial = {**base, "condition": arm, "marked_text": marked,
                                 "trial_id": f"{pair_id}::{arm}"}
                        groups.append({"group_id": trial["trial_id"], "parallel_id": pid,
                                       "trials": [trial]})
                else:
                    trials.append({**base, "condition": condition, "marked_text": text,
                                   "trial_id": f"{pair_id}::{condition}"})
            if trials:
                groups.append({"group_id": pair_id, "parallel_id": pid, "trials": trials})
    return groups


def pack_groups(groups: list[dict], batch_size: int) -> list[dict]:
    """Pack all trials in stable order; retain each trial ID for paired analysis."""
    if batch_size not in (1, 3, 4):
        raise ValueError("batch_size must be 1, 3 or 4")
    trials = [r for g in groups for r in g["trials"]]
    return [{"group_id": "batch::" + digest([r["trial_id"] for r in trials[i:i + batch_size]]),
             "trials": trials[i:i + batch_size]}
            for i in range(0, len(trials), batch_size)]


def measure(model, inputs, torch) -> tuple[object, dict]:
    times, starts = defaultdict(list), defaultdict(list)
    hooks = []
    for module, name in ((model, "whole"), (model.model.visual, "vision"),
                         (model.model.language_model, "language")):
        def before(_module, _args, key=name):
            torch.cuda.synchronize()
            starts[key].append(time.perf_counter())

        def after(_module, _args, _output, key=name):
            torch.cuda.synchronize()
            times[key].append(time.perf_counter() - starts[key].pop())

        hooks.extend([module.register_forward_pre_hook(before), module.register_forward_hook(after)])
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    try:
        with torch.inference_mode():
            generated = model.generate(**inputs, do_sample=False, num_beams=1, max_new_tokens=64)
        torch.cuda.synchronize()
    finally:
        for hook in hooks:
            hook.remove()
    return generated, {
        "generate_s": round(time.perf_counter() - started, 6),
        "prefill_forward_s": round(times["whole"][0], 6),
        "decode_forward_s": round(sum(times["whole"][1:]), 6),
        "vision_forward_s": round(sum(times["vision"]), 6),
        "language_prefill_s": round(times["language"][0], 6),
        "language_decode_s": round(sum(times["language"][1:]), 6),
        "peak_allocated_gib": round(torch.cuda.max_memory_allocated() / 2**30, 6),
        "peak_reserved_gib": round(torch.cuda.max_memory_reserved() / 2**30, 6),
    }


def summarize(batches: list[dict], expected: int) -> dict:
    rows = [row for batch in batches for row in batch["results"]]
    conditions = {}
    for condition in sorted({row["condition"] for row in rows}):
        subset = [row for row in rows if row["condition"] == condition]
        conditions[condition] = {"count": len(subset), "valid": sum(r["valid_output"] for r in subset),
                                 "hit": sum(r["point_in_gt_box"] for r in subset)}
    return {
        "expected_batches": expected, "completed_batches": len(batches),
        "complete": len(batches) == expected, "response_count": len(rows), "conditions": conditions,
        "by_gui": {gui: {c: {"count": len(s := [r for r in rows if r["gui_language"] == gui
                                                               and r["condition"] == c]),
                              "valid": sum(r["valid_output"] for r in s),
                              "hit": sum(r["point_in_gt_box"] for r in s)}
                         for c in conditions} for gui in LOCALES},
        "generate_s_median_per_batch": statistics.median(b["generate_s"] for b in batches)
        if batches else None,
        "generate_s_total": sum(b["generate_s"] for b in batches),
        "max_peak_reserved_gib": max((b["peak_reserved_gib"] for b in batches), default=None),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--suite", choices=("controls", "pilot", "main"), default="pilot")
    parser.add_argument("--descriptors", type=Path)
    parser.add_argument("--batch-size", type=int, choices=(1, 3, 4), default=4)
    parser.add_argument("--max-pixels", type=int, choices=(1048576, 2097152), default=2097152)
    parser.add_argument("--patch-embed-memory-format", choices=("native", "channels_last_3d"),
                        default="native")
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.shard_index < args.num_shards:
        parser.error("Require 0 <= shard-index < num-shards")
    snapshot = args.model_path.resolve()
    if snapshot.name != REVISION or not (snapshot / "config.json").is_file():
        parser.error("Expected the pinned Qwen3-VL-8B snapshot")
    groups = [g for g in build_groups(args.suite, args.descriptors)
              if shard_for(g["parallel_id"], args.num_shards) == args.shard_index]
    groups = pack_groups(groups, args.batch_size)
    contract = {
        "schema": "qwen3-grounding-portable-v2", "batch_size": args.batch_size,
        "conditions": list(CONDITIONS), "suite": args.suite,
        "model_id": MODEL_ID, "revision": REVISION, "dtype": "bfloat16",
        "attn_implementation": "sdpa", "min_pixels": 262144, "max_pixels": args.max_pixels,
        "patch_embed_memory_format": args.patch_embed_memory_format,
        "generation": {"do_sample": False, "num_beams": 1, "max_new_tokens": 64},
        "prompt_template": PROMPT, "groups_sha256": digest(groups),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "implementation_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            HERE / "benchmark_qwen3_runtime.py", HERE / "run_qwen3_prompt_pilot.py",
            HERE / "point_format.py", REPO / "01_code/src/mpr_crosslocale/models/qwen3_memory.py")},
        "num_shards": args.num_shards, "shard_index": args.shard_index,
        "expected_batches": len(groups), "expected_responses": sum(len(g["trials"]) for g in groups),
    }
    if args.dry_run:
        print(json.dumps(contract, ensure_ascii=False, indent=2))
        return
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[key] = "3"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    import torch
    import transformers
    from qwen_vl_utils import process_vision_info
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    contract.update(torch_version=torch.__version__, transformers_version=transformers.__version__,
                    gpu=torch.cuda.get_device_name(0),
                    package_versions={p: importlib.metadata.version(p) for p in
                                      ("qwen-vl-utils", "tokenizers", "numpy", "pillow", "accelerate")})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    contract_path = args.output_dir / "run_contract.json"
    if contract_path.exists():
        if json.loads(contract_path.read_text()) != contract:
            raise ValueError("Refusing to mix different experiment contracts")
    else:
        if (args.output_dir / "batches.jsonl").exists():
            raise ValueError("Batch results exist without a run contract")
        write_json(contract_path, contract)
        write_json(args.output_dir / "input_plan.json", groups)
    path = args.output_dir / "batches.jsonl"
    batches = read_jsonl(path) if path.exists() else []
    known = {b["group_id"] for b in batches}
    expected = {g["group_id"]: g for g in groups}
    if len(known) != len(batches) or not known <= set(expected):
        raise ValueError("Duplicate or unexpected completed groups")
    for batch in batches:
        if batch["contract_sha256"] != digest(contract):
            raise ValueError("Batch contract mismatch")
        if [r["trial_id"] for r in batch["results"]] != [r["trial_id"] for r in expected[batch["group_id"]]["trials"]]:
            raise ValueError("Incomplete batch results")
    pending = [g for g in groups if g["group_id"] not in known]
    print(json.dumps({"pending_batches": len(pending), "contract": contract}), flush=True)
    if pending:
        torch.set_num_threads(3)
        processor = AutoProcessor.from_pretrained(snapshot, local_files_only=True,
                                                  min_pixels=262144, max_pixels=args.max_pixels)
        processor.tokenizer.padding_side = "left"
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            snapshot, local_files_only=True, dtype=torch.bfloat16, attn_implementation="sdpa",
            device_map={"": "cuda:0"}, low_cpu_mem_usage=True).eval()
        from mpr_crosslocale.models.qwen3_memory import (
            configure_patch_embed_memory_format,
        )
        configure_patch_embed_memory_format(model, args.patch_embed_memory_format)
        assert all(p.device.type == "cuda" for p in model.parameters())
        eos = model.generation_config.eos_token_id
        eos_ids = {eos} if isinstance(eos, int) else set(eos or [])
        for group in pending:
            trials = group["trials"]
            image_paths = {}
            for trial in trials:
                if trial["pair_id"] not in image_paths:
                    image = _ensure_locked_image(trial["pair_id"])
                    if hashlib.sha256(image.read_bytes()).hexdigest() != trial["image_sha256"]:
                        raise ValueError("Image differs from annotation")
                    image_paths[trial["pair_id"]] = image
            started = time.perf_counter()
            conversations = [[{"role": "user", "content": [
                {"type": "image", "image": image_paths[r["pair_id"]].as_posix()},
                {"type": "text", "text": PROMPT.format(text=r["marked_text"])},
            ]}] for r in trials]
            rendered = [processor.apply_chat_template(c, tokenize=False, add_generation_prompt=True)
                        for c in conversations]
            images, videos = process_vision_info(conversations, image_patch_size=16)
            inputs = processor(text=rendered, images=images, videos=videos, padding=True,
                               return_tensors="pt")
            grids = inputs["image_grid_thw"].tolist()
            lengths = inputs.attention_mask.sum(dim=1).tolist()
            inputs = inputs.to(model.device)
            torch.cuda.synchronize()
            preprocessing = time.perf_counter() - started
            generated, timing = measure(model, inputs, torch)
            results = []
            for index, trial in enumerate(trials):
                tokens = generated[index, inputs.input_ids.shape[1]:].detach().cpu().tolist()
                stop = next((i for i, t in enumerate(tokens) if t in eos_ids), None)
                tokens = tokens[:stop + 1] if stop is not None else tokens
                raw = processor.decode(tokens, skip_special_tokens=True,
                                       clean_up_tokenization_spaces=False).strip()
                results.append({**trial, "rendered_prompt": rendered[index],
                                "prompt_tokens": lengths[index], "image_grid_thw": grids[index],
                                "raw_output": raw, "generated_token_ids": tokens,
                                "output_tokens": len(tokens), "stop_reason": "eos" if stop is not None else "length",
                                **_score(raw, trial)})
            batch = {"group_id": group["group_id"], "contract_sha256": digest(contract),
                     "batch_size": len(trials), "preprocess_s": round(preprocessing, 6),
                     **timing, "results": results}
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(batch, ensure_ascii=False) + "\n")
                handle.flush()
            batches.append(batch)
            write_json(args.output_dir / "summary.json", summarize(batches, len(groups)))
            print(f"{len(batches)}/{len(groups)} {group['group_id']} {timing['generate_s']:.3f}s "
                  + " ".join(f"{r['condition']}={int(r['point_in_gt_box'])}" for r in results), flush=True)
    write_json(args.output_dir / "summary.json", summarize(batches, len(groups)))
    predictions = args.output_dir / "predictions.jsonl"
    temporary = predictions.with_suffix(".jsonl.tmp")
    temporary.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                 for b in batches for r in b["results"]), encoding="utf-8")
    temporary.replace(predictions)
    print(json.dumps(summarize(batches, len(groups)), ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
