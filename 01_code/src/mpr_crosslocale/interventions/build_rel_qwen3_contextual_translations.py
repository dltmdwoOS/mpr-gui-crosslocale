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
from mpr_crosslocale.interventions.rq4_contextual import (
    CONTEXTUAL_MODEL_ID,
    CONTEXTUAL_REVISION,
    EXPECTED_INTERVENTION_ROWS,
    EXPECTED_SMOKE_ROWS,
    METHOD_NAME,
    PROMPT_TEMPLATE_VERSION,
    SYSTEM_PROMPT,
    build_contextual_plan,
    build_contextual_plan_from_original_controls,
    build_repair_prompt,
    build_user_prompt,
    canonical_json_sha256,
    read_jsonl,
    select_smoke_rows,
    semantic_diagnostic_flags,
    validate_contextual_translation_rows,
    validate_structured_output,
    write_jsonl_atomic,
)
from mpr_crosslocale.interventions.rq4_nllb import (
    canonical_text_sha256,
    load_rel_source_rows,
    render_with_source_layout,
)


def log_step(message: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


def _read_frozen_original_controls(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing Git-LFS-shared frozen original controls: {path}. "
            "From the repository root run `git lfs pull`, then retry."
        )
    with path.open("rb") as handle:
        prefix = handle.read(80)
    if prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise RuntimeError(
            f"{path} is still a Git LFS pointer. Run `git lfs pull` from the "
            "repository root before translation."
        )
    return read_jsonl(path)


def _validate_config(config: dict[str, Any]) -> None:
    translator = config.get("translator", {})
    expected_translator = {
        "model_id": CONTEXTUAL_MODEL_ID,
        "revision": CONTEXTUAL_REVISION,
        "transformers_version": "4.57.6",
        "dtype": "bfloat16",
        "attn_implementation": "sdpa",
        "seed": 42,
        "enable_thinking": False,
    }
    if translator != expected_translator:
        raise ValueError(
            "Qwen3 contextual translator config differs from the frozen protocol: "
            f"expected={expected_translator!r}, actual={translator!r}"
        )
    expected_generation = {
        "do_sample": False,
        "num_beams": 1,
        "max_new_tokens": 512,
    }
    if config.get("generation") != expected_generation:
        raise ValueError("Contextual generation config differs from the frozen protocol.")
    if config.get("runtime") != {
        "device": "cuda",
        "min_gpu_memory_gib": 20,
        "batch_size": 2,
    }:
        raise ValueError("Contextual runtime config differs from the frozen protocol.")
    protocol = config.get("protocol", {})
    if protocol.get("method") != METHOD_NAME:
        raise ValueError("Unexpected contextual translation method.")
    if protocol.get("prompt_template_version") != PROMPT_TEMPLATE_VERSION:
        raise ValueError("Unexpected contextual prompt template version.")
    hidden_checks = {
        "dependency_blind_generation": True,
        "screenshot_hidden": True,
        "gold_hidden": True,
        "human_parallel_hidden": True,
        "prior_translation_hidden": True,
    }
    for key, expected in hidden_checks.items():
        if protocol.get(key) is not expected:
            raise ValueError(f"Frozen hidden-input rule changed: {key}")
    if protocol.get("repair") != {
        "enabled": True,
        "max_attempts": 1,
        "batch_size": 1,
        "retain_all_attempts": True,
    }:
        raise ValueError("Contextual repair policy differs from the frozen protocol.")
    if config.get("smoke") != {
        "per_direction": 2,
        "seed": 20260811,
        "expected_rows": 60,
    }:
        raise ValueError("Contextual smoke protocol differs from the frozen protocol.")


def runtime_preflight(config: dict[str, Any], device: str):
    import torch

    actual_transformers = importlib.metadata.version("transformers")
    expected_transformers = str(config["translator"]["transformers_version"])
    if actual_transformers != expected_transformers:
        raise RuntimeError(
            f"RQ4 contextual translation requires transformers=={expected_transformers}; "
            f"found {actual_transformers}."
        )
    if not device.startswith("cuda"):
        raise RuntimeError(
            "The frozen Qwen3 contextual translation run requires CUDA. "
            "Use --dry-run or --mock-model on a CPU-only machine."
        )
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false.")
    index = int(device.split(":", 1)[1]) if ":" in device else 0
    properties = torch.cuda.get_device_properties(index)
    log_step(
        "STEP 3/7 GPU ready: "
        f"torch={torch.__version__}, cuda={torch.version.cuda}, "
        f"gpu={properties.name}, vram={properties.total_memory / 1024**3:.1f} GiB"
    )
    if properties.total_memory < 20 * 1024**3:
        raise RuntimeError(
            "Frozen bf16 Qwen3-8B translation requires a >=20 GiB GPU. "
            "The local RTX 3060 is intentionally unsupported."
        )
    return torch


class Qwen3ContextualTranslator:
    def __init__(
        self,
        config: dict[str, Any],
        device: str,
        batch_size: int,
        local_files_only: bool,
    ) -> None:
        self.config = config
        self.batch_size = batch_size
        self.generation = dict(config["generation"])
        self.local_files_only = local_files_only
        self.mock = False
        self.torch = runtime_preflight(config, device)

        if not local_files_only:
            from huggingface_hub import HfApi

            log_step("STEP 4/7 resolving pinned Qwen3 revision")
            resolved = HfApi().model_info(
                CONTEXTUAL_MODEL_ID, revision=CONTEXTUAL_REVISION
            ).sha
            if resolved != CONTEXTUAL_REVISION:
                raise RuntimeError(
                    f"Qwen3 revision resolution changed: {resolved} != {CONTEXTUAL_REVISION}"
                )

        self.torch.manual_seed(int(config["translator"]["seed"]))
        self.torch.cuda.manual_seed_all(int(config["translator"]["seed"]))
        log_step(
            "STEP 4/7 loading translator: "
            f"model={CONTEXTUAL_MODEL_ID}, revision={CONTEXTUAL_REVISION}, "
            "dtype=bfloat16, attention=sdpa"
        )
        from transformers import AutoModelForCausalLM, AutoTokenizer

        started = time.perf_counter()
        self.tokenizer = AutoTokenizer.from_pretrained(
            CONTEXTUAL_MODEL_ID,
            revision=CONTEXTUAL_REVISION,
            local_files_only=local_files_only,
        )
        self.tokenizer.padding_side = "left"
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
        self.model = AutoModelForCausalLM.from_pretrained(
            CONTEXTUAL_MODEL_ID,
            revision=CONTEXTUAL_REVISION,
            dtype=self.torch.bfloat16,
            attn_implementation="sdpa",
            device_map="auto",
            local_files_only=local_files_only,
        )
        self.model.eval()
        loaded_revision = getattr(self.model.config, "_commit_hash", None)
        if loaded_revision and loaded_revision != CONTEXTUAL_REVISION:
            raise RuntimeError(
                f"Loaded Qwen3 commit {loaded_revision} != {CONTEXTUAL_REVISION}"
            )
        log_step(f"STEP 4/7 model ready in {time.perf_counter() - started:.1f}s")

    def _render_chat(self, user_prompts: list[str]) -> list[str]:
        rendered = []
        for user_prompt in user_prompts:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
            rendered.append(
                self.tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=False,
                )
            )
        return rendered

    def generate(self, user_prompts: list[str]) -> list[str]:
        rendered = self._render_chat(user_prompts)
        encoded = self.tokenizer(
            rendered,
            padding=True,
            truncation=False,
            return_tensors="pt",
        )
        input_length = int(encoded["input_ids"].shape[1])
        max_context = int(getattr(self.model.config, "max_position_embeddings", 32768))
        if input_length + int(self.generation["max_new_tokens"]) > max_context:
            raise ValueError(
                f"Contextual prompt exceeds context: input={input_length}, "
                f"new={self.generation['max_new_tokens']}, max={max_context}"
            )
        encoded = {key: value.to(self.model.device) for key, value in encoded.items()}
        with self.torch.inference_mode():
            generated = self.model.generate(**encoded, **self.generation)
        suffix = generated[:, input_length:]
        return [
            value.strip()
            for value in self.tokenizer.batch_decode(
                suffix,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
        ]


class MockContextualTranslator:
    mock = True

    @staticmethod
    def generate(user_prompts: list[str]) -> list[str]:
        outputs = []
        for prompt in user_prompts:
            marker = "Translate the following complete GUI MCQ. Return only the output JSON object.\n\n"
            payload_text = prompt.split(marker, 1)[1].split("\n\nRequired output shape:", 1)[0]
            payload = json.loads(payload_text)
            outputs.append(
                json.dumps(
                    {
                        "question_stem": payload["question_stem"],
                        "options": payload["options"],
                    },
                    ensure_ascii=False,
                )
            )
        return outputs


def _attempt(
    translator: Qwen3ContextualTranslator | MockContextualTranslator,
    rows: list[dict[str, Any]],
    prompts: list[str],
    attempt_number: int,
) -> list[dict[str, Any]]:
    started = time.perf_counter()
    raw_outputs = translator.generate(prompts)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if len(raw_outputs) != len(rows):
        raise RuntimeError("Qwen3 returned a different output count from the input count.")
    attempts = []
    per_row_runtime = elapsed_ms // max(len(rows), 1)
    for row, raw_output in zip(rows, raw_outputs, strict=True):
        parsed, errors = validate_structured_output(raw_output, row)
        attempts.append(
            {
                "attempt": attempt_number,
                "raw_output": raw_output,
                "parsed_output": parsed,
                "hard_validation_errors": errors,
                "runtime_ms_approx": per_row_runtime,
            }
        )
    return attempts


def translate_rows(
    selected_plan: list[dict[str, Any]],
    translator: Qwen3ContextualTranslator | MockContextualTranslator,
    config: dict[str, Any],
    output_path: Path,
    existing: dict[str, dict[str, Any]],
    log_every_batches: int,
) -> list[dict[str, Any]]:
    run_provenance = {
        "translator_code_commit": git_commit(),
        "translator_software_versions": software_versions(),
        "translator_hardware": hardware_metadata(),
        "translator_runtime_batch_size": translator.batch_size,
    }
    system_prompt_sha256 = canonical_json_sha256(SYSTEM_PROMPT)
    selected_ids = {str(row["translation_id"]) for row in selected_plan}
    extra_existing = set(existing) - selected_ids
    if extra_existing:
        raise ValueError(
            f"Resume output contains {len(extra_existing)} rows outside the selected scope."
        )
    if existing:
        validate_contextual_translation_rows(
            list(existing.values()),
            expected_count=len(selected_plan),
            allow_partial=True,
        )
        plan_by_id = {str(row["translation_id"]): row for row in selected_plan}
        resume_invariants = (
            "pair_id",
            "parallel_id",
            "source_language",
            "target_language",
            "source_input_id",
            "source_question_raw",
            "gold_label",
            "image_paths",
            "translation_source_kind",
            "translation_source_sha256",
        )
        for translation_id, prior in existing.items():
            planned = plan_by_id[translation_id]
            changed = [
                field
                for field in resume_invariants
                if prior.get(field) != planned.get(field)
            ]
            if changed:
                raise ValueError(
                    f"Resume source/protocol mismatch for {translation_id}: {changed}"
                )
    completed = dict(existing)
    pending = [row for row in selected_plan if row["translation_id"] not in completed]
    total_batches = (len(pending) + translator.batch_size - 1) // translator.batch_size
    for start in range(0, len(pending), translator.batch_size):
        batch = pending[start : start + translator.batch_size]
        batch_number = start // translator.batch_size + 1
        if batch_number == 1 or batch_number == total_batches or batch_number % log_every_batches == 0:
            log_step(
                f"STEP 5/7 batch {batch_number}/{total_batches}: "
                f"rows={start + 1}-{start + len(batch)}/{len(pending)}"
            )
        prompts = [build_user_prompt(row) for row in batch]
        primary_attempts = _attempt(translator, batch, prompts, 0)
        batch_had_repair = False
        for row, primary in zip(batch, primary_attempts, strict=True):
            attempts = [primary]
            final_attempt = primary
            if primary["hard_validation_errors"]:
                batch_had_repair = True
                log_step(
                    "STEP 5/7 STRUCTURAL REPAIR: "
                    f"{row['translation_id']} errors={primary['hard_validation_errors']}"
                )
                repair_prompt = build_repair_prompt(
                    row,
                    primary["raw_output"],
                    primary["hard_validation_errors"],
                )
                repaired = _attempt(translator, [row], [repair_prompt], 1)[0]
                attempts.append(repaired)
                final_attempt = repaired

            parsed = final_attempt["parsed_output"]
            errors = list(final_attempt["hard_validation_errors"])
            eligible = parsed is not None and not errors
            if eligible:
                translated_stem = str(parsed["question_stem"]).strip()
                translated_options = {
                    label: str(parsed["options"][label]).strip()
                    for label in ("A", "B", "C", "D")
                }
                translated_raw = render_with_source_layout(
                    str(row["source_question_raw"]), translated_stem, translated_options
                )
                diagnostic_flags = semantic_diagnostic_flags(row, parsed)
            else:
                translated_stem = ""
                translated_options = {label: "" for label in ("A", "B", "C", "D")}
                translated_raw = ""
                diagnostic_flags = []

            if eligible and len(attempts) == 1:
                status = "ok"
            elif eligible:
                status = "recovered_after_structural_repair"
            else:
                status = "failed_after_structural_repair"
            user_prompt = build_user_prompt(row)
            translated_row = {
                **row,
                "translated_question_stem": translated_stem,
                "translated_options": translated_options,
                "translated_question_raw": translated_raw,
                "translator_model_id": CONTEXTUAL_MODEL_ID,
                "translator_revision": CONTEXTUAL_REVISION,
                "translator_source_language": row["source_language"],
                "translator_target_language": row["target_language"],
                "translation_method": METHOD_NAME,
                "prompt_template_version": PROMPT_TEMPLATE_VERSION,
                "system_prompt_sha256": system_prompt_sha256,
                "user_prompt_sha256": canonical_json_sha256(user_prompt),
                "translation_generation_config": config["generation"],
                "translation_status": status,
                "translation_attempts": attempts,
                "hard_validation_errors": errors,
                "semantic_diagnostic_flags": diagnostic_flags,
                "translation_analysis_eligible": eligible,
                **run_provenance,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            completed[str(row["translation_id"])] = translated_row

        should_checkpoint = (
            batch_number == total_batches
            or batch_number % log_every_batches == 0
            or batch_had_repair
        )
        if should_checkpoint:
            checkpoint = sorted(
                completed.values(), key=lambda row: row["translation_id"]
            )
            validate_contextual_translation_rows(
                checkpoint, expected_count=len(selected_plan), allow_partial=True
            )
            write_jsonl_atomic(output_path, checkpoint)
            log_step(
                f"STEP 5/7 CHECKPOINT {len(checkpoint)}/{len(selected_plan)}: "
                f"{output_path}"
            )
    return sorted(completed.values(), key=lambda row: row["translation_id"])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Build RQ4 Qwen3 full-MCQ contextual translations."
    )
    parser.add_argument(
        "--source-mode",
        choices=["original-controls", "raw-qas"],
        default="original-controls",
        help=(
            "Use the Git-LFS-shared 10,980-row frozen original controls by default. "
            "raw-qas is a local reconstruction/audit path only."
        ),
    )
    parser.add_argument(
        "--source-controls",
        type=Path,
        default=Path(
            "data/derived/interventions/rel_nllb_original_controls.jsonl"
        ),
    )
    parser.add_argument(
        "--annotation-manifest",
        type=Path,
        default=Path("../annotation/rel_text_dependency/data/pilot_manifest.json"),
    )
    parser.add_argument(
        "--qas-dir", type=Path, default=Path("data/raw/mpr_gui_bench/qas")
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/interventions/rel_qwen3_contextual_translation.yaml"),
    )
    parser.add_argument("--scope", choices=["smoke", "full"], required=True)
    parser.add_argument("--plan-out", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--issue-audit-out", type=Path, default=None)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--log-every-batches", type=int, default=10)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock-model", action="store_true")
    args = parser.parse_args(argv)

    if args.batch_size < 1 or args.log_every_batches < 1:
        raise ValueError("Batch and log intervals must be positive.")
    config = load_yaml(args.config)
    log_step(f"STEP 1/7 validating frozen contextual config: {args.config}")
    _validate_config(config)
    if not args.dry_run and not args.mock_model:
        if args.device != config["runtime"]["device"]:
            raise ValueError("Actual translator device differs from the frozen runtime config.")
        if args.batch_size != int(config["runtime"]["batch_size"]):
            raise ValueError("Actual translator batch size differs from the frozen runtime config.")
    log_step(
        "STEP 2/7 building dependency-blind full REL translation plan: "
        f"source_mode={args.source_mode}"
    )
    if args.source_mode == "original-controls":
        controls = _read_frozen_original_controls(args.source_controls)
        full_plan = build_contextual_plan_from_original_controls(controls)
        source_provenance = {
            "translation_source_kind": "frozen_original_controls",
            "translation_source_path": args.source_controls.as_posix(),
            "translation_source_sha256": canonical_text_sha256(args.source_controls),
        }
    else:
        source_rows = load_rel_source_rows(args.annotation_manifest, args.qas_dir)
        full_plan = build_contextual_plan(source_rows)
        source_provenance = {
            "translation_source_kind": "raw_qas_reconstruction",
            "translation_source_path": args.qas_dir.as_posix(),
            "translation_source_sha256": None,
        }
    full_plan = [{**row, **source_provenance} for row in full_plan]
    if args.scope == "smoke":
        smoke = config["smoke"]
        selected_plan = select_smoke_rows(
            full_plan,
            per_direction=int(smoke["per_direction"]),
            seed=int(smoke["seed"]),
        )
        expected_count = EXPECTED_SMOKE_ROWS
        default_output = Path(
            "data/derived/interventions/rel_qwen3_contextual_smoke_60.jsonl"
        )
    else:
        selected_plan = full_plan
        expected_count = EXPECTED_INTERVENTION_ROWS
        default_output = Path(
            "data/derived/interventions/rel_qwen3_contextual_translations_v2.jsonl"
        )
    if len(selected_plan) != expected_count:
        raise AssertionError(f"Selected scope count mismatch: {len(selected_plan)}")
    if args.plan_out:
        write_jsonl_atomic(args.plan_out, selected_plan)
    output_path = args.output or default_output
    log_step(
        f"STEP 2/7 scope={args.scope}, rows={len(selected_plan)}, "
        f"directions=30, output={output_path}"
    )

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "validated_plan",
                    "scope": args.scope,
                    "rows": len(selected_plan),
                    "directions": 30,
                    "translator_model_id": CONTEXTUAL_MODEL_ID,
                    "translator_revision": CONTEXTUAL_REVISION,
                    "prompt_template_version": PROMPT_TEMPLATE_VERSION,
                    **source_provenance,
                    "config_sha256": canonical_text_sha256(args.config),
                    "translator_hidden_fields": [
                        "image",
                        "gold",
                        "dependency",
                        "model_predictions",
                        "human_parallel",
                        "nllb_output",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        log_step("DRY RUN COMPLETE: no translator loaded")
        return

    existing_rows = read_jsonl(output_path) if args.resume and output_path.exists() else []
    existing = {str(row["translation_id"]): row for row in existing_rows}
    log_step(
        f"STEP 3/7 preparing translator: completed={len(existing)}, "
        f"pending={len(selected_plan) - len(existing)}, mock={args.mock_model}"
    )
    translator: Qwen3ContextualTranslator | MockContextualTranslator
    if args.mock_model:
        translator = MockContextualTranslator()
        translator.batch_size = args.batch_size
    else:
        translator = Qwen3ContextualTranslator(
            config,
            device=args.device,
            batch_size=args.batch_size,
            local_files_only=args.local_files_only,
        )
    completed = translate_rows(
        selected_plan,
        translator,
        config,
        output_path,
        existing,
        args.log_every_batches,
    )
    log_step("STEP 6/7 validating completed contextual artifact")
    validate_contextual_translation_rows(completed, expected_count=expected_count)
    issue_rows = [
        {
            "translation_id": row["translation_id"],
            "pair_id": row["pair_id"],
            "source_language": row["source_language"],
            "target_language": row["target_language"],
            "translation_status": row["translation_status"],
            "hard_validation_errors": row["hard_validation_errors"],
            "semantic_diagnostic_flags": row["semantic_diagnostic_flags"],
            "translation_analysis_eligible": row["translation_analysis_eligible"],
            "translation_attempts": row["translation_attempts"],
        }
        for row in completed
        if row["translation_status"] != "ok" or row["semantic_diagnostic_flags"]
    ]
    issue_path = args.issue_audit_out or output_path.with_name(
        output_path.stem + "_issues.jsonl"
    )
    write_jsonl_atomic(issue_path, issue_rows)
    log_step("STEP 7/7 complete")
    print(
        json.dumps(
            {
                "status": "complete",
                "scope": args.scope,
                "rows": len(completed),
                "eligible": sum(row["translation_analysis_eligible"] for row in completed),
                "repair_rows": sum(len(row["translation_attempts"]) == 2 for row in completed),
                "hard_failure_rows": sum(
                    not row["translation_analysis_eligible"] for row in completed
                ),
                "diagnostic_flag_rows": sum(
                    bool(row["semantic_diagnostic_flags"]) for row in completed
                ),
                "output": output_path.as_posix(),
                "issue_audit": issue_path.as_posix(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
