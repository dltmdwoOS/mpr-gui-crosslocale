from __future__ import annotations

import argparse
import importlib.metadata
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mpr_crosslocale.inference.runtime import (
    git_commit,
    hardware_metadata,
    load_yaml,
    software_versions,
)
from mpr_crosslocale.interventions.build_rel_qwen3_contextual_translations import (
    _read_frozen_original_controls,
)
from mpr_crosslocale.interventions.rq4_contextual import (
    build_contextual_plan_from_original_controls,
    canonical_json_sha256,
    select_smoke_rows,
    write_jsonl_atomic,
)
from mpr_crosslocale.interventions.rq4_gui_lexical import (
    EXPECTED_INVENTORIES,
    EXTRACTOR_MODEL_ID,
    EXTRACTOR_REVISION,
    INVENTORY_METHOD,
    INVENTORY_PROMPT_VERSION,
    INVENTORY_SYSTEM_PROMPT,
    INVENTORY_USER_PROMPT,
    build_inventory_plan,
    parse_visible_string_output,
    validate_inventory_rows,
    validate_lexical_config,
)


def log_step(message: str) -> None:
    print(f"[{datetime.now().astimezone():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


def _scope_inventory_plan(
    full_inventory_plan: list[dict[str, Any]],
    controls: list[dict[str, Any]],
    scope: str,
) -> list[dict[str, Any]]:
    if scope == "full":
        return full_inventory_plan
    smoke_pairs = select_smoke_rows(build_contextual_plan_from_original_controls(controls))
    endpoint_ids = {
        str(row["target_human_parallel_endpoint_id"]) for row in smoke_pairs
    }
    selected = [
        row
        for row in full_inventory_plan
        if row["target_human_parallel_endpoint_id"] in endpoint_ids
    ]
    if len(selected) != len(endpoint_ids):
        raise ValueError("Smoke inventory endpoint selection is incomplete.")
    return selected


class VisibleStringExtractor:
    def __init__(self, config: dict[str, Any], device_map: str) -> None:
        import torch

        actual_transformers = importlib.metadata.version("transformers")
        expected_transformers = str(config["extractor"]["transformers_version"])
        if actual_transformers != expected_transformers:
            raise RuntimeError(
                "Visible-string extraction requires "
                f"transformers=={expected_transformers}; found {actual_transformers}."
            )
        if not torch.cuda.is_available():
            raise RuntimeError("Visible-string extraction requires CUDA; use --dry-run locally.")
        properties = torch.cuda.get_device_properties(0)
        if properties.total_memory < int(config["runtime"]["min_gpu_memory_gib"]) * 1024**3:
            raise RuntimeError(
                "Frozen bf16 visible-string extraction requires a >=20 GiB GPU."
            )
        torch.manual_seed(int(config["extractor"]["seed"]))
        torch.cuda.manual_seed_all(int(config["extractor"]["seed"]))
        from mpr_crosslocale.models.qwen25vl import Qwen25VLAdapter

        extractor = config["extractor"]
        self.adapter = Qwen25VLAdapter(
            model_id=EXTRACTOR_MODEL_ID,
            revision=EXTRACTOR_REVISION,
            dtype=str(extractor["dtype"]),
            attn_implementation=str(extractor["attn_implementation"]),
            device_map=device_map,
            processor_kwargs={
                "min_pixels": int(extractor["min_pixels"]),
                "max_pixels": int(extractor["max_pixels"]),
            },
            model_family=str(extractor["model_family"]),
        )
        loaded_revision = getattr(self.adapter.model.config, "_commit_hash", None)
        if loaded_revision and loaded_revision != EXTRACTOR_REVISION:
            raise RuntimeError(
                f"Loaded extractor revision {loaded_revision} != {EXTRACTOR_REVISION}"
            )
        self.generation = dict(extractor["generation"])

    def generate(self, image_path: str, repair: bool = False):
        prompt = INVENTORY_USER_PROMPT
        if repair:
            prompt += (
                " The prior response was invalid. Return the exact JSON shape only; "
                "do not change the visible transcription for any other reason."
            )
        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": INVENTORY_SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": Path(image_path).as_posix()},
                    {"type": "text", "text": prompt},
                ],
            },
        ]
        return self.adapter.generate_messages(messages, self.generation)


def _mock_inventory(row: dict[str, Any]) -> tuple[list[str], str]:
    value = f"MOCK_VISIBLE_STRING_{row['target_language']}"
    return [value], json.dumps({"visible_strings": [value]})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Extract query-blind target-GUI visible-string inventories for RQ4."
    )
    parser.add_argument(
        "--source-controls",
        type=Path,
        default=Path("data/derived/interventions/rel_nllb_original_controls.jsonl"),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/interventions/rel_gui_lexical_localization.yaml"),
    )
    parser.add_argument("--scope", choices=["smoke", "full"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--device-map", default="auto")
    parser.add_argument("--log-every", type=int, default=10)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock-model", action="store_true")
    args = parser.parse_args(argv)

    config = load_yaml(args.config)
    log_step("STEP 1/6 validating frozen two-step lexical configuration")
    validate_lexical_config(config)

    log_step("STEP 2/6 building 2,196 query-blind target endpoint plan")
    controls = _read_frozen_original_controls(args.source_controls)
    full_plan = build_inventory_plan(controls)
    selected = _scope_inventory_plan(full_plan, controls, args.scope)
    print(
        json.dumps(
            {
                "scope": args.scope,
                "selected_inventory_rows": len(selected),
                "full_inventory_rows": len(full_plan),
                "query_fields_exposed": [],
                "translator_fields_exposed_later": ["visible_strings"],
            },
            indent=2,
        )
    )
    if args.dry_run:
        log_step("DRY RUN COMPLETE: no extractor loaded")
        return

    repo_root = args.repo_root.resolve()
    for row in selected:
        resolved = (repo_root / row["image_paths"][0]).resolve()
        if not args.mock_model and not resolved.is_file():
            raise FileNotFoundError(f"Missing target GUI image: {resolved}")
        row["resolved_image_path"] = str(resolved)

    existing_rows = (
        [json.loads(line) for line in args.output.open(encoding="utf-8") if line.strip()]
        if args.resume and args.output.exists()
        else []
    )
    existing = {str(row["inventory_id"]): row for row in existing_rows}
    selected_ids = {str(row["inventory_id"]) for row in selected}
    if set(existing) - selected_ids:
        raise ValueError("Resume inventory contains rows outside the selected scope.")
    if existing:
        validate_inventory_rows(list(existing.values()), expected_count=len(existing))

    log_step(
        f"STEP 3/6 loading query-blind extractor: completed={len(existing)}, "
        f"pending={len(selected) - len(existing)}, mock={args.mock_model}"
    )
    extractor = None if args.mock_model else VisibleStringExtractor(config, args.device_map)
    completed = dict(existing)
    provenance = {
        "extractor_model_id": EXTRACTOR_MODEL_ID,
        "extractor_revision": EXTRACTOR_REVISION,
        "extraction_method": INVENTORY_METHOD,
        "prompt_template_version": INVENTORY_PROMPT_VERSION,
        "system_prompt_sha256": canonical_json_sha256(INVENTORY_SYSTEM_PROMPT),
        "query_content_exposed": False,
        "code_commit": git_commit(),
        "software_versions": software_versions(),
        "hardware": hardware_metadata(),
    }
    pending = [row for row in selected if row["inventory_id"] not in completed]
    log_step("STEP 4/6 extracting visible strings; per-endpoint checkpoints enabled")
    for index, row in enumerate(pending, start=1):
        started = time.perf_counter()
        if args.mock_model:
            strings, raw_output = _mock_inventory(row)
            rendered_prompt = "mock"
            prompt_tokens = output_tokens = None
            attempts = 1
        else:
            assert extractor is not None
            output = extractor.generate(row["resolved_image_path"])
            strings, errors = parse_visible_string_output(output.raw_output)
            attempts = 1
            if errors:
                log_step(f"STEP 4/6 STRUCTURE REPAIR {row['inventory_id']}: {errors}")
                output = extractor.generate(row["resolved_image_path"], repair=True)
                strings, errors = parse_visible_string_output(output.raw_output)
                attempts = 2
            if errors or strings is None:
                raise RuntimeError(
                    f"Visible-string extraction failed for {row['inventory_id']}: {errors}"
                )
            raw_output = output.raw_output
            rendered_prompt = output.rendered_prompt
            prompt_tokens = output.prompt_token_count
            output_tokens = output.output_token_count
        artifact = {
            **{key: value for key, value in row.items() if key != "resolved_image_path"},
            "visible_strings": strings,
            "visible_string_count": len(strings),
            "inventory_status": "success",
            "raw_extractor_output": raw_output,
            "rendered_extractor_prompt": rendered_prompt,
            "prompt_token_count": prompt_tokens,
            "output_token_count": output_tokens,
            "attempt_count": attempts,
            "runtime_ms": int((time.perf_counter() - started) * 1000),
            **provenance,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        completed[row["inventory_id"]] = artifact
        if index == 1 or index == len(pending) or index % args.log_every == 0:
            ordered = sorted(completed.values(), key=lambda value: value["inventory_id"])
            validate_inventory_rows(ordered, expected_count=len(ordered))
            write_jsonl_atomic(args.output, ordered)
            log_step(
                f"STEP 4/6 CHECKPOINT {len(completed)}/{len(selected)}: {args.output}"
            )

    log_step("STEP 5/6 validating frozen inventory artifact")
    result = sorted(completed.values(), key=lambda row: row["inventory_id"])
    validate_inventory_rows(result, expected_count=len(selected))
    if args.scope == "full" and len(result) != EXPECTED_INVENTORIES:
        raise AssertionError("Full inventory artifact is incomplete.")
    log_step("STEP 6/6 complete")
    print(
        json.dumps(
            {
                "status": "complete",
                "scope": args.scope,
                "rows": len(result),
                "nonempty_inventory_rows": sum(bool(row["visible_strings"]) for row in result),
                "repair_rows": sum(int(row["attempt_count"]) > 1 for row in result),
                "output": args.output.as_posix(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
