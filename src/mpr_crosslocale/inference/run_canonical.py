from __future__ import annotations

import argparse
import time
import uuid
from pathlib import Path
from typing import Any

from mpr_crosslocale.inference.answer_parser import parse_label
from mpr_crosslocale.inference.runtime import (
    append_jsonl,
    existing_success_ids,
    git_commit,
    load_yaml,
    read_jsonl,
    resolve_paths,
    software_versions,
)
from mpr_crosslocale.metrics.exact_match import exact_match
from mpr_crosslocale.models.qwen25vl import Qwen25VLAdapter


def filter_rows(
    rows: list[dict[str, Any]],
    languages: set[str] | None,
    dimensions: set[str] | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    selected = []
    for row in rows:
        if languages and row["question_language"] not in languages:
            continue
        if dimensions and row["dimension"] not in dimensions:
            continue
        selected.append(row)
        if limit is not None and len(selected) >= limit:
            break
    return selected


def build_result_base(
    row: dict[str, Any],
    run_id: str,
    model_config: dict[str, Any],
    source_lock: dict[str, Any],
    prompt_profile: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "code_commit": git_commit(),
        "dataset_hf_revision": source_lock.get("huggingface", {}).get("sha"),
        "dataset_github_revision": source_lock.get("github", {}).get("commit"),
        "model_id": model_config["model_id"],
        "model_revision": model_config.get("revision"),
        "processor_revision": model_config.get("revision"),
        "backend": "transformers",
        "software_versions": software_versions(),
        "prompt_profile": prompt_profile,
        "processor_profile": model_config.get("processor_profile", "qwen_default"),
        "input_id": row["input_id"],
        "sample_id": row["sample_id"],
        "parallel_id": row["parallel_id"],
        "language": row["question_language"],
        "dimension": row["dimension"],
        "image_paths": row["image_paths"],
        "num_images": row["num_images"],
        "gold_label": row["gold_label"],
        "gold_raw": row.get("answer_raw", row["gold_label"]),
    }


def run(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).resolve()
    rows = read_jsonl(args.inputs)
    rows = filter_rows(
        rows,
        set(args.languages.split(",")) if args.languages else None,
        set(args.dimensions.split(",")) if args.dimensions else None,
        args.limit,
    )
    rows = resolve_paths(rows, repo_root)
    model_config = load_yaml(args.model_config)
    source_lock = load_yaml(args.source_lock) if args.source_lock.suffix in {".yaml", ".yml"} else {}
    if args.source_lock.suffix == ".json":
        import json

        source_lock = json.loads(args.source_lock.read_text(encoding="utf-8"))

    prompt_profile = args.prompt_profile or model_config.get("prompt_profile", "mpr_minimal_v1")
    generation_config = dict(model_config.get("generation", {}))
    if args.max_new_tokens is not None:
        generation_config["max_new_tokens"] = args.max_new_tokens

    done = existing_success_ids(args.output) if args.resume else set()
    pending = [row for row in rows if row["input_id"] not in done]

    if args.dry_run:
        append_jsonl(
            args.output,
            [
                {
                    "run_id": args.run_id,
                    "status": "dry_run",
                    "planned_rows": len(rows),
                    "pending_rows": len(pending),
                    "prompt_profile": prompt_profile,
                    "model_id": model_config["model_id"],
                }
            ],
        )
        return

    processor_kwargs = {
        key: model_config[key]
        for key in ("min_pixels", "max_pixels")
        if model_config.get(key) is not None
    }
    adapter = Qwen25VLAdapter(
        model_id=model_config["model_id"],
        revision=model_config.get("revision"),
        dtype=model_config.get("dtype", "bfloat16"),
        attn_implementation=args.attn_implementation or model_config.get("attn_implementation"),
        device_map=args.device_map or "auto",
        processor_kwargs=processor_kwargs,
    )

    for row in pending:
        started = time.perf_counter()
        base = build_result_base(row, args.run_id, model_config, source_lock, prompt_profile)
        try:
            output = adapter.generate_one(row, prompt_profile, generation_config)
            parsed_label = parse_label(output.raw_output)
            result = {
                **base,
                "rendered_prompt": output.rendered_prompt,
                "prompt_token_count": output.prompt_token_count,
                "output_token_count": output.output_token_count,
                "raw_output": output.raw_output,
                "parsed_label": parsed_label,
                "parse_success": parsed_label is not None,
                "raw_string_exact": exact_match(output.raw_output, str(row.get("answer_raw", row["gold_label"]))),
                "normalized_correct": parsed_label == row["gold_label"],
                "invalid": parsed_label is None,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "status": "success",
            }
        except Exception as exc:
            result = {
                **base,
                "status": "failed",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        append_jsonl(args.output, [result])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run canonical matched MPR-GUI inference.")
    parser.add_argument("--inputs", type=Path, default=Path("data/manifests/canonical_inputs.jsonl"))
    parser.add_argument("--model-config", type=Path, default=Path("configs/models/qwen2_5_vl_7b.yaml"))
    parser.add_argument("--source-lock", type=Path, default=Path("data/manifests/source_lock.json"))
    parser.add_argument("--output", type=Path, default=Path("results/raw/canonical_reproduction/qwen25vl.jsonl"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--run-id", default=f"canonical-{uuid.uuid4().hex[:12]}")
    parser.add_argument("--prompt-profile", default=None)
    parser.add_argument("--languages", default=None, help="Comma-separated language filter.")
    parser.add_argument("--dimensions", default=None, help="Comma-separated dimension filter.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-new-tokens", type=int, default=None)
    parser.add_argument("--device-map", default=None)
    parser.add_argument("--attn-implementation", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    run(args)


if __name__ == "__main__":
    main()
