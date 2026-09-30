"""Measure Qwen REL batches on a fixed sample plus conservative memory stress inputs."""

from __future__ import annotations

import argparse
import gc
import json
import math
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from mpr_crosslocale.data.rel_followup import BUNDLE_MANIFEST, digest, validate_dataset, verify_bundle, write_json
from mpr_crosslocale.inference.answer_parser import parse_label
from mpr_crosslocale.inference.prompts import build_prompt_text
from mpr_crosslocale.inference.run_rel_followup import code_identity, cuda_memory_error_kind, inference_plan, input_id, stable_hash
from mpr_crosslocale.inference.runtime import load_yaml, software_versions
from mpr_crosslocale.inference.system_prompts import build_system_prompt


def adapter_row(row: dict, root: Path) -> dict:
    return {
        "question_raw": row["question"], "gold_label": row["gold_answer"],
        "image_paths": [str((root / row["image_path"]).resolve())],
    }


def stress_input(adapter, rows: list[dict], root: Path, config: dict) -> tuple[dict, dict]:
    """Combine maximum actual text length and largest processed screenshot for an upper bound."""
    import qwen_vl_utils.vision_process as vp

    tokenizer = adapter.processor.tokenizer
    longest, longest_tokens = rows[0], -1
    for offset in range(0, len(rows), 128):
        group = rows[offset:offset + 128]
        encoded = tokenizer(
            [build_prompt_text(r["question"], config["prompt_profile"]) for r in group],
            add_special_tokens=False, return_attention_mask=False,
        )["input_ids"]
        for row, ids in zip(group, encoded, strict=True):
            if len(ids) > longest_tokens:
                longest, longest_tokens = row, len(ids)
    factor = 14 * vp.SPATIAL_MERGE_SIZE
    sizes = []
    for name in sorted({row["image_path"] for row in rows}):
        with Image.open(root / name) as image:
            width, height = image.size
        height, width = vp.smart_resize(
            height, width, factor,
            min_pixels=vp.IMAGE_MIN_TOKEN_NUM * factor**2,
            max_pixels=vp.IMAGE_MAX_TOKEN_NUM * factor**2,
        )
        height, width = vp.smart_resize(
            height, width, factor,
            min_pixels=config["min_pixels"], max_pixels=config["max_pixels"],
        )
        sizes.append((height * width, name))
    candidates = sorted(sizes, reverse=True)[:4]
    processed = []
    for _, name in candidates:
        image = vp.fetch_image({"image": str((root / name).resolve())})
        inputs = adapter.processor.image_processor(images=[image], return_tensors="pt")
        grid = inputs["image_grid_thw"][0].tolist()
        processed.append((math.prod(grid) // vp.SPATIAL_MERGE_SIZE**2, name, grid))
    visual_tokens, name, grid = max(processed)
    row = adapter_row(longest, root)
    row["image_paths"] = [str((root / name).resolve())]
    return row, {
        "scope": "Synthetic memory-only combination; not an experimental prediction.",
        "text_source_input_id": input_id(longest), "text_tokens": longest_tokens,
        "image_path": name, "image_grid_thw": grid, "visual_tokens": visual_tokens,
    }


def measure(adapter, inputs: list[dict], batch_size: int, config: dict, system_prompt: str) -> dict:
    import torch

    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()
    started = time.perf_counter()
    labels, scored = [], []
    for offset in range(0, len(inputs), batch_size):
        group = inputs[offset:offset + batch_size]
        outputs = adapter.generate_batch(
            group, config["prompt_profile"], config["generation"],
            system_prompt=system_prompt, score_labels=True,
        )
        if len(outputs) != len(group) or any(o.label_summary is None for o in outputs):
            raise RuntimeError("Batch lost an output or its first-token label scores")
        labels.extend(parse_label(output.raw_output) for output in outputs)
        scored.extend(output.label_summary.scored_predicted_label for output in outputs)
    torch.cuda.synchronize()
    seconds = time.perf_counter() - started
    return {
        "inputs": len(inputs), "seconds": round(seconds, 4),
        "inputs_per_second": round(len(inputs) / seconds, 4),
        "peak_allocated_GiB": round(torch.cuda.max_memory_allocated() / 2**30, 3),
        "peak_reserved_GiB": round(torch.cuda.max_memory_reserved() / 2**30, 3),
        "labels": labels, "scored_labels": scored,
        "parse_failures": sum(label is None for label in labels),
    }


def run(args) -> dict:
    import torch

    from mpr_crosslocale.inference.run_cross_locale import _build_model_adapter

    root = args.data_root.resolve()
    rows, audit = validate_dataset(root, images=True)
    verify_bundle(root, images=True)
    canonical, _ = inference_plan(rows)
    rows = list(canonical.values())
    config = load_yaml(args.model_config)
    if config["model_family"] != "qwen2_5_vl":
        raise ValueError("This batch experiment supports Qwen2.5-VL only")
    rng = random.Random(args.seed)
    sample = rng.sample(rows, min(args.samples, len(rows)))
    identity = {
        "dataset_sha256": audit["conditions_sha256"], "model_config": config,
        "bundle_manifest_sha256": digest(root / BUNDLE_MANIFEST),
        "code_sha256": {**code_identity(), "benchmark_rel_batch.py": digest(Path(__file__))},
        "software_versions": software_versions(), "seed": args.seed,
        "sample_input_ids": [input_id(row) for row in sample],
        "max_batch_size": args.max_batch_size, "memory_fraction": args.memory_fraction,
    }
    fingerprint = stable_hash(identity)
    path = args.output_dir / "summary.json"
    if path.exists():
        report = json.loads(path.read_text())
        if report["experiment_fingerprint"] != fingerprint:
            raise ValueError("Benchmark directory belongs to different code/data/settings")
        if report["status"] == "complete":
            return report
    else:
        report = {
            **identity, "experiment_fingerprint": fingerprint, "status": "running",
            "created_at": datetime.now(timezone.utc).isoformat(), "trials": [],
        }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(path, report)
    if not torch.cuda.is_available():
        raise RuntimeError("Batch benchmark requires CUDA")
    adapter = _build_model_adapter(SimpleNamespace(attn_implementation=None, device_map="cuda:0"), config)
    report["gpu_total_GiB"] = round(torch.cuda.get_device_properties(0).total_memory / 2**30, 3)
    stress, stress_metadata = stress_input(adapter, rows, root, config)
    report["memory_stress"] = stress_metadata
    print("Memory stress:", json.dumps(stress_metadata, ensure_ascii=False), flush=True)
    inputs = [adapter_row(row, root) for row in sample]
    system_prompt, _, _ = build_system_prompt("english_fixed", "en")
    # One warmup excludes first-call CUDA initialization from the comparisons.
    adapter.generate_batch(inputs[:1], config["prompt_profile"], config["generation"], system_prompt, True)
    baseline = next((trial.get("throughput") for trial in report["trials"] if trial["batch_size"] == 1), None)
    completed = {trial["batch_size"] for trial in report["trials"]}
    batch_size = 1
    while batch_size <= args.max_batch_size:
        # An interrupted run may already have persisted the terminal unsafe trial.
        if any(not trial["safe"] for trial in report["trials"]):
            break
        if batch_size in completed:
            batch_size *= 2
            continue
        trial = {"batch_size": batch_size}
        try:
            trial["stress"] = measure(adapter, [stress] * batch_size, batch_size, config, system_prompt)
            count = max(len(inputs), batch_size)
            workload = [inputs[index % len(inputs)] for index in range(count)]
            trial["throughput"] = measure(adapter, workload, batch_size, config, system_prompt)
            peak = max(trial["stress"]["peak_reserved_GiB"], trial["throughput"]["peak_reserved_GiB"])
            trial["safe"] = peak <= report["gpu_total_GiB"] * args.memory_fraction
            trial["status"] = "success" if trial["safe"] else "memory_headroom_exceeded"
            if baseline is None:
                baseline = trial["throughput"]
            trial["generation_label_changes_vs_batch1"] = sum(
                label != baseline["labels"][index % len(baseline["labels"])]
                for index, label in enumerate(trial["throughput"]["labels"])
            )
            trial["scored_label_changes_vs_batch1"] = sum(
                label != baseline["scored_labels"][index % len(baseline["scored_labels"])]
                for index, label in enumerate(trial["throughput"]["scored_labels"])
            )
        except Exception as exc:
            kind = cuda_memory_error_kind(exc)
            if kind is None:
                raise
            trial.update(status=kind, safe=False, error_type=type(exc).__name__, error=str(exc))
        report["trials"].append(trial)
        write_json(path, report)
        print("Batch trial:", json.dumps({
            "batch_size": batch_size, "status": trial["status"],
            "inputs_per_second": trial.get("throughput", {}).get("inputs_per_second"),
            "stress_peak_reserved_GiB": trial.get("stress", {}).get("peak_reserved_GiB"),
        }), flush=True)
        if not trial["safe"]:
            gc.collect()
            torch.cuda.empty_cache()
            break
        batch_size *= 2
    safe = [trial for trial in report["trials"] if trial.get("safe")]
    if not safe:
        raise RuntimeError("No batch size passed the memory headroom check")
    best = max(safe, key=lambda trial: trial["throughput"]["inputs_per_second"])
    report.update(
        status="complete", recommended_batch_size=best["batch_size"],
        largest_safe_batch_size=max(trial["batch_size"] for trial in safe),
        speedup_vs_batch1=round(best["throughput"]["inputs_per_second"] / baseline["inputs_per_second"], 3),
        completed_at=datetime.now(timezone.utc).isoformat(),
    )
    write_json(path, report)
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("followup_rel_4lang"))
    parser.add_argument("--model-config", type=Path, default=Path("01_code/configs/models/qwen2_5_vl_7b.yaml"))
    parser.add_argument("--output-dir", type=Path, default=Path("followup_rel_4lang/results/batch_benchmark/qwen2_5_vl_7b"))
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--max-batch-size", type=int, default=128)
    parser.add_argument("--memory-fraction", type=float, default=0.90)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    if args.samples < 1 or args.max_batch_size < 1 or not 0 < args.memory_fraction < 1:
        parser.error("Use positive sample/batch sizes and a memory fraction between 0 and 1")
    result = run(args)
    print(json.dumps({key: result[key] for key in ["status", "recommended_batch_size", "largest_safe_batch_size", "speedup_vs_batch1"]}, indent=2))


if __name__ == "__main__":
    main()
