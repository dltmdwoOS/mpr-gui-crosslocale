"""InternVL grounding O/R/C/F with the same inputs, prompt and scoring as the Qwen3 runner.

Differences from run_qwen3_grounding.py are deliberate and recorded in the contract:
- batch size is fixed at 1 (the InternVL adapter has no batched path);
- InternVL's chat template always has a system turn. The Qwen3 runner sends no system
  message, so this runner sends an EMPTY system message instead of the checkpoint's
  default Chinese identity message (which would add Chinese text to every condition);
- images use the InternVL 448px tiling from the model config (max 2,048 visual tokens).
Inputs (build_groups), the user prompt (PROMPT) and hit scoring (_score) are imported
unchanged from the Qwen3 runner.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "01_code/src"))

from benchmark_qwen3_runtime import _ensure_locked_image  # noqa: E402
from run_qwen3_grounding import (  # noqa: E402
    CONDITIONS,
    build_groups,
    digest,
    pack_groups,
    read_jsonl,
    shard_for,
    summarize,
    write_json,
)
from run_qwen3_prompt_pilot import PROMPT, _score  # noqa: E402

SYSTEM_MESSAGE = ""  # see module docstring
GENERATION = {"do_sample": False, "num_beams": 1, "max_new_tokens": 64}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--suite", choices=("controls", "pilot", "main"), default="pilot")
    parser.add_argument("--descriptors", type=Path)
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.shard_index < args.num_shards:
        parser.error("Require 0 <= shard-index < num-shards")

    from mpr_crosslocale.inference.run_cross_locale import INTERNVL_FAMILIES
    from mpr_crosslocale.inference.runtime import load_yaml

    config = load_yaml(args.model_config)
    if config.get("model_family") not in INTERNVL_FAMILIES or not config.get("revision"):
        parser.error("Use a pinned InternVL model configuration")
    if config.get("dtype") != "bfloat16" or config.get("quantization") is not None:
        parser.error("Use unquantized bfloat16")

    groups = [g for g in build_groups(args.suite, args.descriptors)
              if shard_for(g["parallel_id"], args.num_shards) == args.shard_index]
    groups = pack_groups(groups, 1)
    contract = {
        "schema": "internvl-grounding-portable-v1", "batch_size": 1,
        "conditions": list(CONDITIONS), "suite": args.suite,
        "model_id": config["model_id"], "model_family": config["model_family"],
        "revision": config["revision"], "dtype": "bfloat16",
        "attn_implementation": config.get("attn_implementation"),
        "use_flash_attn": bool(config.get("use_flash_attn", False)),
        "tiling": {key: config.get(key) for key in
                   ("input_size", "min_num", "max_num", "use_thumbnail", "vision_token_limit")},
        "system_message": SYSTEM_MESSAGE, "generation": GENERATION,
        "prompt_template": PROMPT, "groups_sha256": digest(groups),
        "model_config_sha256": hashlib.sha256(args.model_config.read_bytes()).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "implementation_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            HERE / "run_qwen3_grounding.py", HERE / "run_qwen3_prompt_pilot.py",
            HERE / "point_format.py", HERE / "benchmark_qwen3_runtime.py",
            REPO / "01_code/src/mpr_crosslocale/models/internvl25.py")},
        "num_shards": args.num_shards, "shard_index": args.shard_index,
        "expected_batches": len(groups), "expected_responses": len(groups),
    }
    if args.dry_run:
        print(json.dumps(contract, ensure_ascii=False, indent=2))
        return

    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[key] = "3"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    import torch
    import transformers

    contract.update(torch_version=torch.__version__, transformers_version=transformers.__version__,
                    gpu=torch.cuda.get_device_name(0),
                    package_versions={p: importlib.metadata.version(p) for p in
                                      ("tokenizers", "numpy", "pillow", "accelerate", "timm", "einops")})
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
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        if lines:
            try:
                json.loads(lines[-1])
            except json.JSONDecodeError:
                # A kill during a write leaves one partial last line; drop only that line.
                print(f"Dropping a partial last line from {path}", flush=True)
                path.write_text("".join(lines[:-1]), encoding="utf-8")
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
        from mpr_crosslocale.models.internvl25 import InternVL25Adapter

        adapter = InternVL25Adapter(
            model_id=config["model_id"], revision=config["revision"], dtype="bfloat16",
            device_map=config.get("device_strategy") or "cuda:0",
            trust_remote_code=bool(config.get("trust_remote_code", True)),
            use_flash_attn=bool(config.get("use_flash_attn", False)),
            input_size=int(config.get("input_size", 448)), min_num=int(config.get("min_num", 1)),
            max_num=int(config.get("max_num", 7)),
            use_thumbnail=bool(config.get("use_thumbnail", True)),
        )
        for group in pending:
            (trial,) = group["trials"]
            image = _ensure_locked_image(trial["pair_id"])
            if hashlib.sha256(image.read_bytes()).hexdigest() != trial["image_sha256"]:
                raise ValueError("Image differs from annotation")
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
            started = time.perf_counter()
            output = adapter.generate_freeform([image.as_posix()],
                                               PROMPT.format(text=trial["marked_text"]),
                                               GENERATION, SYSTEM_MESSAGE)
            torch.cuda.synchronize()
            elapsed = time.perf_counter() - started
            if output["visual_token_count"] > int(config.get("vision_token_limit", 2048)):
                raise ValueError("Visual tokens exceed the configured cap")
            result = {**trial, **output, **_score(output["raw_output"], trial)}
            batch = {"group_id": group["group_id"], "contract_sha256": digest(contract),
                     "batch_size": 1, "generate_s": round(elapsed, 6),
                     "peak_reserved_gib": torch.cuda.max_memory_reserved() / 2**30,
                     "results": [result]}
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(batch, ensure_ascii=False) + "\n")
                handle.flush()
            batches.append(batch)
            if len(batches) % 50 == 0 or len(batches) == len(groups):
                write_json(args.output_dir / "summary.json", summarize(batches, len(groups)))
            print(f"{len(batches)}/{len(groups)} {trial['trial_id']} {elapsed:.3f}s "
                  f"hit={int(result['point_in_gt_box'])} raw={output['raw_output']!r}", flush=True)
    write_json(args.output_dir / "summary.json", summarize(batches, len(groups)))
    predictions = args.output_dir / "predictions.jsonl"
    temporary = predictions.with_suffix(".jsonl.tmp")
    temporary.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                 for b in batches for r in b["results"]), encoding="utf-8")
    temporary.replace(predictions)
    print(json.dumps(summarize(batches, len(groups)), ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
