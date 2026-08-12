from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image, ImageOps

from mpr_crosslocale.inference.runtime import load_yaml, read_jsonl, resolve_paths
from mpr_crosslocale.models.qwen25vl import Qwen25VLAdapter


def image_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_info(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        width, height = image.size
    return {
        "path": path.as_posix(),
        "width": width,
        "height": height,
        "sha256": image_sha256(path),
    }


def percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1)))
    return ordered[index]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = ["num_images", "text_tokens", "total_sequence_length", "visual_grid_tokens"]
    summary: dict[str, Any] = {"rows": len(rows)}
    for field in fields:
        values = [int(row[field]) for row in rows if row.get(field) is not None]
        summary[field] = {
            "min": min(values) if values else None,
            "p50": int(median(values)) if values else None,
            "p90": percentile(values, 90),
            "p95": percentile(values, 95),
            "p99": percentile(values, 99),
            "max": max(values) if values else None,
        }
    by_dimension: dict[str, int] = defaultdict(int)
    by_language: dict[str, int] = defaultdict(int)
    for row in rows:
        by_dimension[row["dimension"]] += 1
        by_language[row["language"]] += 1
    summary["rows_by_dimension"] = dict(sorted(by_dimension.items()))
    summary["rows_by_language"] = dict(sorted(by_language.items()))
    return summary


def run_preflight(args: argparse.Namespace) -> dict[str, Any]:
    from transformers import AutoProcessor
    from qwen_vl_utils import process_vision_info

    repo_root = Path(args.repo_root).resolve()
    model_config = load_yaml(args.model_config)
    processor_kwargs = {
        key: model_config[key]
        for key in ("use_fast", "min_pixels", "max_pixels")
        if model_config.get(key) is not None
    }
    processor = AutoProcessor.from_pretrained(
        model_config["model_id"],
        revision=model_config.get("revision"),
        **processor_kwargs,
    )
    rows = read_jsonl(args.inputs)
    if args.limit is not None:
        rows = rows[: args.limit]
    rows = resolve_paths(rows, repo_root)

    records: list[dict[str, Any]] = []
    prompt_profile = args.prompt_profile or model_config.get("prompt_profile", "mpr_minimal_v1")
    for row in rows:
        messages = Qwen25VLAdapter.build_messages(row, prompt_profile)
        rendered_prompt = processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = processor(
            text=[rendered_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        image_grid = inputs.get("image_grid_thw")
        visual_grid_tokens = None
        if image_grid is not None:
            visual_grid_tokens = int(image_grid.prod(dim=1).sum().item())
        text_tokens = len(processor.tokenizer(rendered_prompt).input_ids)
        image_records = [image_info(Path(path)) for path in row["image_paths"]]
        records.append(
            {
                "input_id": row["input_id"],
                "sample_id": row["sample_id"],
                "parallel_id": row["parallel_id"],
                "language": row["question_language"],
                "dimension": row["dimension"],
                "num_images": row["num_images"],
                "image_info": image_records,
                "text_tokens": text_tokens,
                "total_sequence_length": int(inputs.input_ids.shape[1]),
                "visual_grid_tokens": visual_grid_tokens,
                "prompt_profile": prompt_profile,
                "processor_profile": model_config.get("processor_profile", "qwen_default"),
                "processor_use_fast": model_config.get("use_fast"),
            }
        )
    return {"summary": summarize(records), "records": records}


def format_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = ["# Processor Preflight", ""]
    lines.append("This file is generated before canonical inference to estimate context and image load.")
    lines.append("")
    lines.append(f"- Rows: `{summary['rows']}`")
    lines.append(f"- Rows by dimension: `{summary['rows_by_dimension']}`")
    lines.append(f"- Rows by language: `{summary['rows_by_language']}`")
    lines.append("")
    lines.append("| Field | min | p50 | p90 | p95 | p99 | max |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for field in ["num_images", "text_tokens", "total_sequence_length", "visual_grid_tokens"]:
        stats = summary[field]
        lines.append(
            f"| {field} | {stats['min']} | {stats['p50']} | {stats['p90']} | "
            f"{stats['p95']} | {stats['p99']} | {stats['max']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run Qwen processor preflight over canonical inputs.")
    parser.add_argument("--inputs", type=Path, default=Path("data/manifests/canonical_inputs.jsonl"))
    parser.add_argument("--model-config", type=Path, default=Path("configs/models/qwen2_5_vl_7b.yaml"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--json-out", type=Path, default=Path("data/manifests/processor_preflight.json"))
    parser.add_argument("--markdown-out", type=Path, default=Path("docs/PROCESSOR_PREFLIGHT.md"))
    parser.add_argument("--prompt-profile", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    report = run_preflight(args)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text(format_markdown(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
