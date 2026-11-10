from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
import traceback
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tqdm

from mpr_crosslocale.data.cross_locale_sampling import (
    build_cross_locale_plan,
    build_language_pairs,
    parse_language_pairs,
)
from mpr_crosslocale.inference.answer_parser import parse_label
from mpr_crosslocale.inference.label_scoring import (
    deterministic_mock_label_score,
    uniform_label_score,
)
from mpr_crosslocale.inference.prompts import build_prompt_text
from mpr_crosslocale.inference.runtime import (
    append_jsonl,
    existing_model_ids,
    existing_success_ids,
    git_commit,
    hardware_metadata,
    load_yaml,
    read_jsonl,
    resolve_paths,
    select_item_shard,
    software_versions,
)
from mpr_crosslocale.inference.system_prompts import build_system_prompt
from mpr_crosslocale.models.internvl25 import InternVL25Adapter
from mpr_crosslocale.models.qwen25vl import Qwen25VLAdapter

INTERNVL_FAMILIES = frozenset({"internvl2_5", "internvl3_5"})


def run(args: argparse.Namespace) -> None:
    batch_size = getattr(args, "batch_size", 1)
    if batch_size < 1:
        raise ValueError("batch-size must be positive")
    repo_root = Path(args.repo_root).resolve()
    manifest_rows = read_jsonl(args.manifest)
    dimensions = set(args.dimensions) if args.dimensions else None
    language_pairs = (
        parse_language_pairs(args.language_pairs)
        if args.language_pairs
        else build_language_pairs(
            args.question_languages,
            args.gui_languages,
            include_matched=not args.mismatch_only,
            include_mismatch=not args.matched_only,
        )
    )
    plan = build_cross_locale_plan(
        manifest_rows=manifest_rows,
        language_pairs=language_pairs,
        dimensions=dimensions,
        sample_size=args.sample_size,
        sample_unit=args.sample_unit,
        seed=args.seed,
    )
    num_shards = getattr(args, "num_shards", 1)
    shard_index = getattr(args, "shard_index", 0)
    selected = select_item_shard(plan.rows, num_shards, shard_index)
    plan = replace(plan, rows=selected, n_evaluations=len(selected),
                   n_semantic_items=len({r["parallel_id"] for r in selected}),
                   missing=select_item_shard(plan.missing, num_shards, shard_index))
    rows = resolve_paths(plan.rows, repo_root)
    model_config = load_yaml(args.model_config)
    if batch_size > 1 and model_config.get("model_family") not in {"qwen2_5_vl", "qwen3_vl"}:
        raise ValueError("Batched cross-locale inference supports Qwen VL only")
    _reject_mixed_model_output(args.output, model_config["model_id"])
    _reject_mixed_model_output(args.failures_out, model_config["model_id"])
    prompt_profile = args.prompt_profile or model_config.get("prompt_profile", "mpr_label_only_v1")
    generation_config = dict(model_config.get("generation", {}))
    generation_config.setdefault("do_sample", False)
    if args.max_new_tokens is not None:
        generation_config["max_new_tokens"] = args.max_new_tokens
    attn_implementation = args.attn_implementation or model_config.get("attn_implementation")
    effective_use_flash_attn = model_config.get("use_flash_attn")
    if model_config.get("model_family") in INTERNVL_FAMILIES and args.attn_implementation:
        effective_use_flash_attn = args.attn_implementation == "flash_attention_2"
    contract = {
        "schema": "cross-locale-run-contract-v1", "model_config": model_config,
        "batch_size": batch_size,
        "manifest_sha256": hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(),
        "input_ids": [r["input_id"] for r in rows], "num_shards": num_shards,
        "shard_index": shard_index, "prompt_profile": prompt_profile,
        "generation": generation_config, "system_prompt_mode": args.system_prompt_mode,
        "attn_implementation": attn_implementation, "score_labels": args.score_labels,
        "execution_mode": "dry_run" if args.dry_run else "mock" if args.mock_model else "gpu",
        "seed": args.seed,
        "code_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            Path(__file__), Path(__file__).with_name("runtime.py"),
            Path(__file__).with_name("prompts.py"), Path(__file__).with_name("system_prompts.py"),
            Path(__file__).parents[1] / "models/qwen25vl.py",
            Path(__file__).parents[1] / "models/qwen3_memory.py")},
    }
    contract_path = args.output.with_suffix(args.output.suffix + ".contract.json")
    if contract_path.exists():
        if json.loads(contract_path.read_text(encoding="utf-8")) != contract:
            raise ValueError("Output belongs to a different experiment contract")
    else:
        if args.output.exists() and args.output.stat().st_size:
            raise ValueError("Existing output has no experiment contract; use a fresh output path")
        contract_path.parent.mkdir(parents=True, exist_ok=True)
        contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    run_metadata = {
        "code_commit": git_commit(),
        "software_versions": software_versions(),
        "hardware": hardware_metadata(),
        "attn_implementation": attn_implementation,
        "use_flash_attn": effective_use_flash_attn,
    }

    write_sample_manifest(args.sample_manifest_out, plan, args)
    if plan.missing:
        append_jsonl(args.missing_out, plan.missing)

    if args.dry_run:
        dry_rows = [
            {
                **_result_base(row, args, model_config, prompt_profile, run_metadata),
                "status": "dry_run",
                "rendered_prompt": _render_plain_prompt(row, args.system_prompt_mode, prompt_profile),
            }
            for row in rows
        ]
        append_jsonl(args.output, dry_rows)
        print_plan(plan, args)
        return

    done = existing_success_ids(args.output) if args.resume else set()
    pending = [row for row in rows if row["input_id"] not in done]
    adapter = None
    if not args.mock_model and pending:
        adapter = _build_model_adapter(args, model_config)

    retry_counts: dict[str, int] = {}
    for row, output, batch_error, elapsed, actual_batch in batch_outputs(
            pending, adapter, args, prompt_profile, generation_config):
        base = _result_base(row, args, model_config, prompt_profile, run_metadata)
        try:
            started = time.perf_counter()
            if args.mock_model:
                generated_text, label_summary = _mock_inference(row, args.seed)
                rendered_prompt = _render_plain_prompt(row, args.system_prompt_mode, prompt_profile)
                prompt_token_count = None
                output_token_count = None
                num_patches_list = None
                visual_token_count = None
            else:
                assert adapter is not None
                if batch_error is not None:
                    raise batch_error
                generated_text = output.raw_output
                rendered_prompt = output.rendered_prompt
                prompt_token_count = output.prompt_token_count
                output_token_count = output.output_token_count
                num_patches_list = getattr(output, "num_patches_list", None)
                visual_token_count = getattr(output, "visual_token_count", None)
                if args.score_labels:
                    if output.label_summary is None:
                        raise RuntimeError("Label scoring was requested but generation returned no scores")
                    label_summary = output.label_summary
                else:
                    label_summary = uniform_label_score(
                        row["gold_label"],
                        scoring_method="not_requested",
                    )
            runtime_ms = int(elapsed * 1000 / actual_batch)
            parsed = parse_label(generated_text)
            scored = label_summary.scored_predicted_label
            result = {
                **base,
                "rendered_prompt": rendered_prompt,
                "prompt_token_count": prompt_token_count,
                "output_token_count": output_token_count,
                "num_patches_list": num_patches_list,
                "visual_token_count": visual_token_count,
                "generated_text": generated_text,
                "parsed_generated_label": parsed,
                "scored_predicted_label": scored,
                "label_logprobs": label_summary.label_logprobs,
                "label_probabilities": label_summary.label_probabilities,
                "gold_probability": label_summary.gold_probability,
                "gold_rank": label_summary.gold_rank,
                "top1_top2_margin": label_summary.top1_top2_margin,
                "gold_vs_best_wrong_margin": label_summary.gold_vs_best_wrong_margin,
                "entropy": label_summary.entropy,
                "label_scoring_method": label_summary.scoring_method,
                "label_token_ids": label_summary.label_token_ids,
                "generation_scoring_disagreement": parsed is not None and parsed != scored,
                "correct": scored == row["gold_label"],
                "parse_success": parsed is not None,
                "inference_status": "success",
                "status": "success",
                "runtime_ms": runtime_ms,
                "batch_size": actual_batch, "batch_runtime_ms": elapsed * 1000,
                "timestamp": _utc_now(),
            }
        except Exception as exc:
            retry_counts[row["input_id"]] = retry_counts.get(row["input_id"], 0) + 1
            result = {
                **base,
                "inference_status": "failed",
                "status": "failed",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "error_traceback": traceback.format_exc(),
                "retry_count": retry_counts[row["input_id"]],
                "runtime_ms": int(elapsed * 1000 / actual_batch),
                "timestamp": _utc_now(),
            }
            append_jsonl(args.failures_out, [result])
        append_jsonl(args.output, [result])
    print_plan(plan, args)
    remaining = {r["input_id"] for r in rows} - existing_success_ids(args.output)
    if remaining:
        raise SystemExit(f"Incomplete inference: {len(remaining)} inputs remain; rerun with --resume")


def batch_outputs(rows, adapter, args, prompt_profile, generation_config):
    """Run real batches and preserve row order, including failures for resume."""
    offset = 0
    while offset < len(rows):
        prompt = build_system_prompt(args.system_prompt_mode, rows[offset]["question_language"])[0]
        count = min(getattr(args, "batch_size", 1), len(rows) - offset)
        for i in range(1, count):
            if build_system_prompt(args.system_prompt_mode, rows[offset+i]["question_language"])[0] != prompt:
                count = i
                break
        chunk = rows[offset:offset+count]
        started = time.perf_counter()
        error, outputs = None, [None] * count
        try:
            if not args.mock_model:
                if count == 1:
                    outputs = [adapter.generate_one(chunk[0], prompt_profile, generation_config,
                               system_prompt=prompt, score_labels=args.score_labels)]
                else:
                    outputs = adapter.generate_batch(chunk, prompt_profile, generation_config,
                              system_prompt=prompt, score_labels=args.score_labels)
                if len(outputs) != count:
                    raise RuntimeError("Batch lost output rows")
        except Exception as exc:
            from mpr_crosslocale.inference.run_rel_followup import cuda_memory_error_kind
            if cuda_memory_error_kind(exc) is not None:
                raise
            error = exc
            outputs = [None] * count
        elapsed = time.perf_counter() - started
        for row, output in zip(chunk, outputs, strict=True):
            yield row, output, error, elapsed, count
        offset += count


def write_sample_manifest(path: Path | None, plan, args: argparse.Namespace) -> None:
    if path is None:
        return
    payload = {
        "run_id": args.run_id,
        "seed": args.seed,
        "sample_unit": args.sample_unit,
        "sample_size": args.sample_size,
        "language_pairs": [f"{q}:{g}" for q, g in plan.language_pairs],
        "n_semantic_items": plan.n_semantic_items,
        "n_evaluations": plan.n_evaluations,
        "input_ids": [row["input_id"] for row in plan.rows],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def print_plan(plan, args: argparse.Namespace) -> None:
    print(
        json.dumps(
            {
                "run_id": args.run_id,
                "language_pairs": [f"{q}:{g}" for q, g in plan.language_pairs],
                "n_semantic_items": plan.n_semantic_items,
                "n_evaluations": plan.n_evaluations,
                "missing": len(plan.missing),
                "sample_unit": args.sample_unit,
                "sample_size": args.sample_size,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _result_base(
    row: dict[str, Any],
    args: argparse.Namespace,
    model_config: dict[str, Any],
    prompt_profile: str,
    run_metadata: dict[str, Any],
) -> dict[str, Any]:
    system_prompt, system_language, template_version = build_system_prompt(
        args.system_prompt_mode, row["question_language"]
    )
    return {
        "run_id": args.run_id,
        "code_commit": run_metadata["code_commit"],
        "input_id": row["input_id"],
        "parallel_id": row["parallel_id"],
        "semantic_item_id": row["semantic_item_id"],
        "source_question_id": row["question_sample_id"],
        "question_language": row["question_language"],
        "gui_language": row["gui_language"],
        "matched": row["matched"],
        "condition": row["condition"],
        "dimension": row["dimension"],
        "image_paths": row["image_paths"],
        "image_path": row["image_paths"][0] if row["image_paths"] else None,
        "num_images": row["num_images"],
        "system_prompt_mode": args.system_prompt_mode,
        "system_prompt_language": system_language,
        "system_prompt": system_prompt,
        "prompt_template_version": template_version,
        "prompt_profile": prompt_profile,
        "model_id": model_config["model_id"],
        "model_family": model_config.get("model_family"),
        "model_revision": model_config.get("revision"),
        "processor_revision": model_config.get("revision"),
        "precision": model_config.get("dtype", "bfloat16"),
        "attn_implementation": run_metadata["attn_implementation"],
        "vision_token_limit": model_config.get("vision_token_limit"),
        "min_pixels": model_config.get("min_pixels"),
        "max_pixels": model_config.get("max_pixels"),
        "patch_embed_memory_format": model_config.get("patch_embed_memory_format", "native"),
        "num_shards": getattr(args, "num_shards", 1),
        "shard_index": getattr(args, "shard_index", 0),
        "processor_profile": model_config.get("processor_profile"),
        "input_size": model_config.get("input_size"),
        "min_num": model_config.get("min_num"),
        "max_num": model_config.get("max_num"),
        "use_thumbnail": model_config.get("use_thumbnail"),
        "trust_remote_code": model_config.get("trust_remote_code", False),
        "use_flash_attn": run_metadata["use_flash_attn"],
        "seed": args.seed,
        "gold_label": row["gold_label"],
        "software_versions": run_metadata["software_versions"],
        "hardware": run_metadata["hardware"],
    }


def _render_plain_prompt(row: dict[str, Any], system_prompt_mode: str, prompt_profile: str) -> str:
    system_prompt, _, _ = build_system_prompt(system_prompt_mode, row["question_language"])
    return f"{system_prompt}\n\n{build_prompt_text(row['question_raw'], prompt_profile)}"


def _mock_inference(row: dict[str, Any], seed: int):
    rng = random.Random(f"{seed}:{row['input_id']}")
    predicted = row["gold_label"] if rng.random() >= 0.25 else rng.choice(["A", "B", "C", "D"])
    return predicted, deterministic_mock_label_score(row["gold_label"], predicted)


def _reject_mixed_model_output(path: Path, model_id: str) -> None:
    existing = existing_model_ids(path)
    if existing and existing != {model_id}:
        raise ValueError(
            f"Refusing to mix model {model_id!r} into {path}; "
            f"existing model IDs: {sorted(existing)!r}"
        )


def _build_model_adapter(args: argparse.Namespace, model_config: dict[str, Any]):
    model_family = model_config.get("model_family", "qwen2_5_vl")
    if model_family in {"qwen2_5_vl", "qwen3_vl"}:
        return _build_qwen_adapter(args, model_config)
    if model_family in INTERNVL_FAMILIES:
        return _build_internvl_adapter(args, model_config)
    raise ValueError(f"Unsupported model_family: {model_family!r}")


def _build_qwen_adapter(args: argparse.Namespace, model_config: dict[str, Any]) -> Qwen25VLAdapter:
    processor_kwargs = {
        key: model_config[key]
        for key in ("min_pixels", "max_pixels")
        if model_config.get(key) is not None
    }
    return Qwen25VLAdapter(
        model_id=model_config["model_id"],
        revision=model_config.get("revision"),
        dtype=model_config.get("dtype", "bfloat16"),
        attn_implementation=args.attn_implementation or model_config.get("attn_implementation"),
        device_map=args.device_map or "auto",
        processor_kwargs=processor_kwargs,
        model_family=model_config.get("model_family", "qwen2_5_vl"),
        patch_embed_memory_format=model_config.get("patch_embed_memory_format", "native"),
    )


def _build_internvl_adapter(
    args: argparse.Namespace,
    model_config: dict[str, Any],
) -> InternVL25Adapter:
    configured_attention = model_config.get("attn_implementation", "eager")
    requested_attention = args.attn_implementation or configured_attention
    if requested_attention not in {"eager", "flash_attention_2"}:
        raise ValueError(
            "InternVL2.5 supports attention modes 'eager' and 'flash_attention_2' "
            f"in this backend, not {requested_attention!r}"
        )
    use_flash_attn = requested_attention == "flash_attention_2"
    if args.attn_implementation is None:
        use_flash_attn = bool(model_config.get("use_flash_attn", use_flash_attn))
    return InternVL25Adapter(
        model_id=model_config["model_id"],
        revision=model_config.get("revision"),
        dtype=model_config.get("dtype", "bfloat16"),
        device_map=args.device_map or model_config.get("device_strategy", "auto"),
        trust_remote_code=bool(model_config.get("trust_remote_code", True)),
        use_flash_attn=use_flash_attn,
        input_size=int(model_config.get("input_size", 448)),
        min_num=int(model_config.get("min_num", 1)),
        max_num=int(model_config.get("max_num", 7)),
        use_thumbnail=bool(model_config.get("use_thumbnail", True)),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run cross-locale MPR-GUI inference.")
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/mpr_gui_manifest.jsonl"))
    parser.add_argument("--model-config", type=Path, default=Path("configs/models/qwen3_vl_4b.yaml"))
    parser.add_argument("--output", type=Path, default=Path("results/raw/cross_locale/qwen3vl4b.jsonl"))
    parser.add_argument("--failures-out", type=Path, default=Path("results/raw/cross_locale/failures.jsonl"))
    parser.add_argument("--missing-out", type=Path, default=Path("results/raw/cross_locale/missing.jsonl"))
    parser.add_argument("--sample-manifest-out", type=Path, default=None)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--run-id", default=f"cross-locale-{uuid.uuid4().hex[:12]}")
    parser.add_argument("--language-pairs", nargs="*", default=None, help="Pairs like en:ja ja:en.")
    parser.add_argument("--question-languages", nargs="*", default=None)
    parser.add_argument("--gui-languages", nargs="*", default=None)
    parser.add_argument("--matched-only", action="store_true")
    parser.add_argument("--mismatch-only", action="store_true")
    parser.add_argument("--dimensions", nargs="*", default=None)
    parser.add_argument("--sample-size", type=int, default=None)
    parser.add_argument(
        "--sample-unit",
        choices=["semantic_items", "evaluations", "per_pair"],
        default="semantic_items",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--system-prompt-mode", choices=["english_fixed", "query_aligned"], default="english_fixed")
    parser.add_argument("--prompt-profile", default=None)
    parser.add_argument("--max-new-tokens", type=int, default=None)
    parser.add_argument("--device-map", default=None)
    parser.add_argument("--attn-implementation", default=None)
    parser.add_argument("--score-labels", action="store_true")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock-model", action="store_true")
    args = parser.parse_args(argv)
    if args.matched_only and args.mismatch_only:
        raise ValueError("--matched-only and --mismatch-only cannot both be set")
    run(args)


if __name__ == "__main__":
    main()
