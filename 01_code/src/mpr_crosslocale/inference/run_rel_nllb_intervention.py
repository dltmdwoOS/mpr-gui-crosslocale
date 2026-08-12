from __future__ import annotations

import argparse
import json
import random
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tqdm

from mpr_crosslocale.inference.answer_parser import parse_label
from mpr_crosslocale.inference.label_scoring import (
    deterministic_mock_label_score,
    uniform_label_score,
)
from mpr_crosslocale.inference.prompts import build_prompt_text
from mpr_crosslocale.inference.run_cross_locale import (
    _build_model_adapter,
    _reject_mixed_model_output,
)
from mpr_crosslocale.inference.runtime import (
    append_jsonl,
    existing_success_ids,
    git_commit,
    hardware_metadata,
    load_yaml,
    read_jsonl,
    resolve_paths,
    software_versions,
)
from mpr_crosslocale.inference.system_prompts import build_system_prompt
from mpr_crosslocale.interventions.rq4_contextual import (
    CONTEXTUAL_CONDITION,
    CONTEXTUAL_MODEL_ID,
    CONTEXTUAL_REVISION,
)
from mpr_crosslocale.interventions.rq4_gui_lexical import LEXICAL_CONDITION
from mpr_crosslocale.interventions.rq4_nllb import (
    EXPECTED_INTERVENTION_ROWS,
    NLLB_MODEL_ID,
    NLLB_REVISION,
)


def validate_intervention_inputs(rows: list[dict[str, Any]]) -> None:
    if len(rows) != EXPECTED_INTERVENTION_ROWS:
        raise ValueError(
            f"RQ4 NLLB inference requires {EXPECTED_INTERVENTION_ROWS} rows; found {len(rows)}."
        )
    required = {
        "input_id",
        "pair_id",
        "parallel_id",
        "source_question_language",
        "effective_question_language",
        "question_language",
        "gui_language",
        "condition",
        "source_qas_file",
        "source_qas_line",
        "question_raw",
        "options",
        "option_order",
        "gold_label",
        "image_paths",
        "translator_model_id",
        "translator_revision",
        "translation_status",
        "translation_analysis_eligible",
    }
    input_ids = []
    pair_ids = []
    for row in rows:
        missing = required - set(row)
        if missing:
            raise ValueError(f"Input is missing fields {sorted(missing)}: {row.get('input_id')}")
        input_ids.append(str(row["input_id"]))
        pair_ids.append(str(row["pair_id"]))
        if row["condition"] not in {
            "nllb_query_aligned",
            CONTEXTUAL_CONDITION,
            LEXICAL_CONDITION,
        }:
            raise ValueError(f"Unexpected condition: {row['input_id']}")
        if row["source_question_language"] == row["gui_language"]:
            raise ValueError(f"Source condition is not a mismatch: {row['input_id']}")
        if not (
            row["effective_question_language"]
            == row["question_language"]
            == row["gui_language"]
        ):
            raise ValueError(f"Post-intervention language alignment failed: {row['input_id']}")
        if row["matched"] is not False or row["original_matched"] is not False:
            raise ValueError(f"Original mismatch metadata changed: {row['input_id']}")
        if row["condition"] == "nllb_query_aligned":
            expected_model, expected_revision = NLLB_MODEL_ID, NLLB_REVISION
            for field in ("translation_retry_events", "translation_failed_fields"):
                if field not in row:
                    raise ValueError(f"NLLB input lacks {field}: {row['input_id']}")
        else:
            expected_model, expected_revision = CONTEXTUAL_MODEL_ID, CONTEXTUAL_REVISION
            for field in (
                "translation_method",
                "prompt_template_version",
                "translation_attempt_count",
                "semantic_diagnostic_flags",
            ):
                if field not in row:
                    raise ValueError(f"Contextual input lacks {field}: {row['input_id']}")
            if row["condition"] == LEXICAL_CONDITION:
                for field in (
                    "visible_string_inventory_id",
                    "visible_string_inventory_sha256",
                    "inventory_extractor_model_id",
                    "inventory_extractor_revision",
                ):
                    if field not in row:
                        raise ValueError(
                            f"GUI lexical input lacks {field}: {row['input_id']}"
                        )
        if row["translator_model_id"] != expected_model:
            raise ValueError(f"Unexpected translator: {row['input_id']}")
        if row["translator_revision"] != expected_revision:
            raise ValueError(f"Unexpected translator revision: {row['input_id']}")
        if row["translation_analysis_eligible"] is not True:
            raise ValueError(f"Ineligible translation reached VLM inference: {row['input_id']}")
        if len(row["image_paths"]) != int(row["num_images"]):
            raise ValueError(f"num_images mismatch: {row['input_id']}")
    if len(input_ids) != len(set(input_ids)) or len(pair_ids) != len(set(pair_ids)):
        raise ValueError("RQ4 inference input IDs and pair IDs must be unique.")


def _result_base(
    row: dict[str, Any],
    args: argparse.Namespace,
    model_config: dict[str, Any],
    prompt_profile: str,
    run_metadata: dict[str, Any],
    generation_config: dict[str, Any],
) -> dict[str, Any]:
    system_prompt, system_language, template_version = build_system_prompt(
        args.system_prompt_mode, row["question_language"]
    )
    return {
        "run_id": args.run_id,
        "code_commit": run_metadata["code_commit"],
        "input_id": row["input_id"],
        "pair_id": row["pair_id"],
        "translation_id": row["translation_id"],
        "parallel_id": row["parallel_id"],
        "semantic_item_id": row["parallel_id"],
        "source_question_id": row["question_sample_id"],
        "gui_sample_id": row["gui_sample_id"],
        "source_qas_file": row["source_qas_file"],
        "source_qas_line": row["source_qas_line"],
        "source_matched_endpoint_id": row["source_matched_endpoint_id"],
        "target_human_parallel_endpoint_id": row["target_human_parallel_endpoint_id"],
        "source_question_language": row["source_question_language"],
        "effective_question_language": row["effective_question_language"],
        "question_language": row["question_language"],
        "gui_language": row["gui_language"],
        "matched": False,
        "original_matched": False,
        "language_aligned_after_intervention": True,
        "condition": row["condition"],
        "translation_status": row["translation_status"],
        "translation_retry_events": row.get("translation_retry_events"),
        "translation_failed_fields": row.get("translation_failed_fields"),
        "translation_attempt_count": row.get("translation_attempt_count"),
        "translation_method": row.get("translation_method"),
        "translation_prompt_template_version": row.get("prompt_template_version"),
        "translation_semantic_diagnostic_flags": row.get(
            "semantic_diagnostic_flags", []
        ),
        "translation_analysis_eligible": row["translation_analysis_eligible"],
        "visible_string_inventory_id": row.get("visible_string_inventory_id"),
        "visible_string_inventory_sha256": row.get(
            "visible_string_inventory_sha256"
        ),
        "visible_string_count": row.get("visible_string_count"),
        "inventory_extractor_model_id": row.get("inventory_extractor_model_id"),
        "inventory_extractor_revision": row.get("inventory_extractor_revision"),
        "dimension": "rel",
        "question_raw_sha256": __import__("hashlib").sha256(
            row["question_raw"].encode("utf-8")
        ).hexdigest(),
        "image_paths": row["image_paths"],
        "image_path": row["image_paths"][0] if row["image_paths"] else None,
        "num_images": row["num_images"],
        "frame_order": row["frame_order"],
        "option_order": row["option_order"],
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
        "processor_profile": model_config.get("processor_profile"),
        "input_size": model_config.get("input_size"),
        "min_num": model_config.get("min_num"),
        "max_num": model_config.get("max_num"),
        "use_thumbnail": model_config.get("use_thumbnail"),
        "trust_remote_code": model_config.get("trust_remote_code", False),
        "use_flash_attn": run_metadata["use_flash_attn"],
        "generation_config": generation_config,
        "seed": args.seed,
        "gold_label": row["gold_label"],
        "translator_model_id": row["translator_model_id"],
        "translator_revision": row["translator_revision"],
        "translator_src_code": row.get("translator_src_code"),
        "translator_tgt_code": row.get("translator_tgt_code"),
        "translation_generation_config": row["translation_generation_config"],
        "software_versions": run_metadata["software_versions"],
        "hardware": run_metadata["hardware"],
    }


def _render_plain_prompt(row: dict[str, Any], system_prompt_mode: str, prompt_profile: str) -> str:
    system_prompt, _, _ = build_system_prompt(system_prompt_mode, row["question_language"])
    return f"{system_prompt}\n\n{build_prompt_text(row['question_raw'], prompt_profile)}"


def _mock_inference(row: dict[str, Any], seed: int):
    rng = random.Random(f"rq4:{seed}:{row['input_id']}")
    predicted = row["gold_label"] if rng.random() >= 0.25 else rng.choice(["A", "B", "C", "D"])
    return predicted, deterministic_mock_label_score(row["gold_label"], predicted)


def run(args: argparse.Namespace) -> None:
    def log_step(message: str) -> None:
        print(f"[{datetime.now().astimezone():%Y-%m-%d %H:%M:%S}] {message}", flush=True)

    repo_root = Path(args.repo_root).resolve()
    log_step(f"STEP 1/4 reading and validating intervention inputs: {args.inputs}")
    unresolved_rows = read_jsonl(args.inputs)
    validate_intervention_inputs(unresolved_rows)
    log_step(f"STEP 1/4 validated rows={len(unresolved_rows)}")
    log_step(f"STEP 2/4 resolving image paths under repo root: {repo_root}")
    rows = resolve_paths(unresolved_rows, repo_root)
    if not args.dry_run and not args.mock_model:
        missing_images = [
            path
            for row in rows
            for path in row["image_paths"]
            if not Path(path).exists()
        ]
        if missing_images:
            raise FileNotFoundError(
                f"RQ4 inference has {len(missing_images)} missing image references; "
                f"first={missing_images[0]}"
            )

    model_config = load_yaml(args.model_config)
    _reject_mixed_model_output(args.output, model_config["model_id"])
    _reject_mixed_model_output(args.failures_out, model_config["model_id"])
    prompt_profile = args.prompt_profile or model_config.get("prompt_profile", "mpr_label_only_v1")
    generation_config = dict(model_config.get("generation", {}))
    generation_config.setdefault("do_sample", False)
    if args.max_new_tokens is not None:
        generation_config["max_new_tokens"] = args.max_new_tokens
    attn_implementation = args.attn_implementation or model_config.get("attn_implementation")
    effective_use_flash_attn = model_config.get("use_flash_attn")
    if model_config.get("model_family") == "internvl2_5" and args.attn_implementation:
        effective_use_flash_attn = args.attn_implementation == "flash_attention_2"
    run_metadata = {
        "code_commit": git_commit(),
        "software_versions": software_versions(),
        "hardware": hardware_metadata(),
        "attn_implementation": attn_implementation,
        "use_flash_attn": effective_use_flash_attn,
    }
    log_step(
        "STEP 2/4 protocol ready: "
        f"model={model_config['model_id']}, revision={model_config.get('revision')}, "
        f"prompt={prompt_profile}, system_prompt={args.system_prompt_mode}"
    )

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "rows": len(rows),
                    "model_id": model_config["model_id"],
                    "model_revision": model_config.get("revision"),
                    "prompt_profile": prompt_profile,
                    "system_prompt_mode": args.system_prompt_mode,
                    "generation_config": generation_config,
                },
                indent=2,
            )
        )
        log_step("DRY RUN COMPLETE: no VLM loaded and no inference executed")
        return

    done = existing_success_ids(args.output) if args.resume else set()
    pending = [row for row in rows if row["input_id"] not in done]
    log_step(
        f"STEP 3/4 loading model: completed={len(done)}, pending={len(pending)}, "
        f"resume={args.resume}"
    )
    adapter = None if args.mock_model else _build_model_adapter(args, model_config)
    log_step("STEP 4/4 inference started; per-row progress is shown below")
    for row in tqdm.tqdm(pending, desc="RQ4 query-alignment intervention"):
        started = time.perf_counter()
        base = _result_base(
            row, args, model_config, prompt_profile, run_metadata, generation_config
        )
        try:
            if args.mock_model:
                generated_text, label_summary = _mock_inference(row, args.seed)
                rendered_prompt = _render_plain_prompt(
                    row, args.system_prompt_mode, prompt_profile
                )
                prompt_token_count = None
                output_token_count = None
                num_patches_list = None
                visual_token_count = None
            else:
                assert adapter is not None
                output = adapter.generate_one(
                    row,
                    prompt_profile,
                    generation_config,
                    system_prompt=base["system_prompt"],
                    score_labels=args.score_labels,
                )
                generated_text = output.raw_output
                rendered_prompt = output.rendered_prompt
                prompt_token_count = output.prompt_token_count
                output_token_count = output.output_token_count
                num_patches_list = getattr(output, "num_patches_list", None)
                visual_token_count = getattr(output, "visual_token_count", None)
                label_summary = (
                    output.label_summary
                    if args.score_labels and output.label_summary is not None
                    else uniform_label_score(row["gold_label"], scoring_method="not_requested")
                )
            parsed = parse_label(generated_text)
            result = {
                **base,
                "rendered_prompt": rendered_prompt,
                "prompt_token_count": prompt_token_count,
                "output_token_count": output_token_count,
                "num_patches_list": num_patches_list,
                "visual_token_count": visual_token_count,
                "generated_text": generated_text,
                "parsed_generated_label": parsed,
                "generation_correct": int(parsed == row["gold_label"]),
                "parse_success": parsed is not None,
                "scored_predicted_label": label_summary.scored_predicted_label,
                "label_logprobs": label_summary.label_logprobs,
                "label_probabilities": label_summary.label_probabilities,
                "label_scoring_method": label_summary.scoring_method,
                "inference_status": "success",
                "status": "success",
                "runtime_ms": int((time.perf_counter() - started) * 1000),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:  # noqa: BLE001 - preserve every failed inference row
            result = {
                **base,
                "inference_status": "failed",
                "status": "failed",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "error_traceback": traceback.format_exc(),
                "runtime_ms": int((time.perf_counter() - started) * 1000),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            append_jsonl(args.failures_out, [result])
        append_jsonl(args.output, [result])
    log_step(f"COMPLETE: processed={len(pending)}, output={args.output}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run frozen RQ4 REL query-alignment intervention inputs."
    )
    parser.add_argument(
        "--inputs",
        type=Path,
        default=Path("data/derived/interventions/rel_nllb_inputs.jsonl"),
    )
    parser.add_argument("--model-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--failures-out", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--run-id", default=f"rq4-nllb-{uuid.uuid4().hex[:12]}")
    parser.add_argument("--system-prompt-mode", choices=["english_fixed"], default="english_fixed")
    parser.add_argument("--prompt-profile", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-new-tokens", type=int, default=None)
    parser.add_argument("--device-map", default=None)
    parser.add_argument("--attn-implementation", default=None)
    parser.add_argument("--score-labels", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock-model", action="store_true")
    args = parser.parse_args(argv)
    run(args)


if __name__ == "__main__":
    main()
