from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mpr_crosslocale.inference.runtime import git_commit, load_yaml, software_versions
from mpr_crosslocale.interventions.rq4_nllb import (
    EXPECTED_INTERVENTION_ROWS,
    NLLB_LANGUAGE_CODES,
    NLLB_MODEL_ID,
    NLLB_REVISION,
    TRANSLATABLE_FIELDS,
    build_translation_plan,
    canonical_text_sha256,
    load_rel_source_rows,
    read_jsonl,
    render_with_source_layout,
    validate_plan_rows,
    validate_translation_rows,
    write_jsonl_atomic,
)


def log_step(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def _normalize_translation_audit_metadata(row: dict[str, Any]) -> dict[str, Any]:
    """Upgrade pre-amendment checkpoints without changing translated content."""

    normalized = dict(row)
    normalized.setdefault("translation_status", "ok")
    normalized.setdefault("translation_retry_events", [])
    normalized.setdefault("translation_failed_fields", [])
    normalized.setdefault("translation_analysis_eligible", True)
    return normalized


def runtime_preflight(config: dict[str, Any], device: str):
    import torch

    actual_transformers = importlib.metadata.version("transformers")
    expected_transformers = str(config["translator"]["transformers_version"])
    if actual_transformers != expected_transformers:
        raise RuntimeError(
            f"RQ4 requires transformers=={expected_transformers}; "
            f"found {actual_transformers}."
        )
    requested_device = torch.device(device)
    log_step(
        "STEP 3/6 runtime preflight: "
        f"torch={torch.__version__}, cuda_build={torch.version.cuda}, "
        f"cuda_available={torch.cuda.is_available()}, requested_device={device}"
    )
    if requested_device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA was requested, but this Conda environment has a CPU-only PyTorch build "
            f"(torch={torch.__version__}, torch.version.cuda={torch.version.cuda}). "
            "Install a CUDA-enabled PyTorch wheel in 'mpr-rq4-nllb' before rerunning. "
            "For this machine, the verified project baseline is torch==2.8.0 with cu128."
        )
    if requested_device.type == "cuda":
        device_index = requested_device.index or 0
        properties = torch.cuda.get_device_properties(device_index)
        log_step(
            "STEP 3/6 GPU ready: "
            f"{properties.name}, VRAM={properties.total_memory / 1024**3:.1f} GiB"
        )
    return torch, requested_device


def _validate_config(config: dict[str, Any]) -> None:
    translator = config.get("translator", {})
    if translator.get("model_id") != NLLB_MODEL_ID:
        raise ValueError(f"RQ4 translator must be {NLLB_MODEL_ID}.")
    if translator.get("revision") != NLLB_REVISION:
        raise ValueError(f"RQ4 translator revision must be {NLLB_REVISION}.")
    if translator.get("dtype") != "float32":
        raise ValueError("RQ4 translator dtype must be float32.")
    if translator.get("transformers_version") != "4.57.6":
        raise ValueError("RQ4 Transformers version must be frozen to 4.57.6.")
    if translator.get("language_codes") != NLLB_LANGUAGE_CODES:
        raise ValueError("RQ4 NLLB language-code mapping differs from the frozen mapping.")
    expected_generation = {
        "do_sample": False,
        "num_beams": 4,
        "length_penalty": 1.0,
        "early_stopping": True,
        "max_new_tokens": 256,
    }
    if config.get("generation") != expected_generation:
        raise ValueError("NLLB generation config differs from the frozen RQ4 protocol.")
    expected_retry = {
        "enabled": True,
        "trigger": "decoded_output_empty_after_strip",
        "batch_size": 1,
        "max_attempts": 1,
        "generation_overrides": {"repetition_penalty": 1.1},
        "retain_failed_row": True,
    }
    if config.get("protocol", {}).get("empty_translation_retry") != expected_retry:
        raise ValueError("Empty-translation retry policy differs from the frozen RQ4 amendment.")


class NllbTranslator:
    def __init__(
        self,
        config: dict[str, Any],
        device: str,
        batch_size: int,
        log_every_batches: int,
        local_files_only: bool,
    ) -> None:
        self.config = config
        self.batch_size = batch_size
        self.log_every_batches = log_every_batches
        self.local_files_only = local_files_only
        self.generation = dict(config["generation"])

        self.torch, self.device = runtime_preflight(config, device)
        torch = self.torch

        if not local_files_only:
            from huggingface_hub import HfApi

            log_step("STEP 4/6 resolving pinned Hugging Face revision")
            resolved = HfApi().model_info(NLLB_MODEL_ID, revision=NLLB_REVISION).sha
            if resolved != NLLB_REVISION:
                raise RuntimeError(
                    f"Hugging Face revision resolution changed: expected {NLLB_REVISION}, got {resolved}"
                )

        torch.manual_seed(int(config["translator"]["seed"]))
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(int(config["translator"]["seed"]))
        log_step(
            "STEP 4/6 loading NLLB model: "
            f"model={NLLB_MODEL_ID}, revision={NLLB_REVISION}, dtype=float32"
        )
        from transformers import AutoModelForSeq2SeqLM

        started = time.perf_counter()
        self.model = AutoModelForSeq2SeqLM.from_pretrained(
            NLLB_MODEL_ID,
            revision=NLLB_REVISION,
            dtype=torch.float32,
            local_files_only=local_files_only,
        ).to(self.device)
        self.model.eval()
        log_step(f"STEP 4/6 model ready in {(time.perf_counter() - started):.1f}s")
        loaded_revision = getattr(self.model.config, "_commit_hash", None)
        if loaded_revision and loaded_revision != NLLB_REVISION:
            raise RuntimeError(
                f"Loaded NLLB commit {loaded_revision} does not match frozen {NLLB_REVISION}."
            )

    def translate_direction(
        self,
        values: list[str],
        source_language: str,
        target_language: str,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(
            NLLB_MODEL_ID,
            revision=NLLB_REVISION,
            src_lang=NLLB_LANGUAGE_CODES[source_language],
            tgt_lang=NLLB_LANGUAGE_CODES[target_language],
            local_files_only=self.local_files_only,
        )
        forced_bos_token_id = tokenizer.convert_tokens_to_ids(
            NLLB_LANGUAGE_CODES[target_language]
        )
        if forced_bos_token_id in {None, tokenizer.unk_token_id}:
            raise RuntimeError(f"Unknown target language token for {target_language}.")

        translated: list[str] = []
        retry_events: list[dict[str, Any]] = []
        total_batches = (len(values) + self.batch_size - 1) // self.batch_size
        for start in range(0, len(values), self.batch_size):
            batch = values[start : start + self.batch_size]
            batch_number = start // self.batch_size + 1
            if (
                batch_number == 1
                or batch_number == total_batches
                or batch_number % self.log_every_batches == 0
            ):
                log_step(
                    "STEP 5/6 batch "
                    f"{source_language}->{target_language} "
                    f"{batch_number}/{total_batches} "
                    f"fields={start + 1}-{start + len(batch)}/{len(values)}"
                )
            encoded = tokenizer(batch, padding=True, truncation=False, return_tensors="pt")
            if int(encoded["input_ids"].shape[1]) > 512:
                raise ValueError(
                    f"NLLB source batch exceeds the frozen 512-token limit: "
                    f"{encoded['input_ids'].shape[1]}"
                )
            encoded = {key: value.to(self.device) for key, value in encoded.items()}
            try:
                with self.torch.inference_mode():
                    output_ids = self.model.generate(
                        **encoded,
                        forced_bos_token_id=forced_bos_token_id,
                        **self.generation,
                    )
            except Exception as error:
                raise RuntimeError(
                    "NLLB generation failed at "
                    f"direction={source_language}->{target_language}, "
                    f"batch={batch_number}/{total_batches}, "
                    f"field_range={start + 1}-{start + len(batch)}."
                ) from error
            batch_output = tokenizer.batch_decode(output_ids, skip_special_tokens=True)
            if len(batch_output) != len(batch):
                raise RuntimeError(
                    "NLLB returned a different number of translations than inputs at "
                    f"direction={source_language}->{target_language}, "
                    f"batch={batch_number}/{total_batches}, "
                    f"field_range={start + 1}-{start + len(batch)}: "
                    f"inputs={len(batch)}, outputs={len(batch_output)}."
                )
            empty_indices = [
                index for index, value in enumerate(batch_output) if not value.strip()
            ]
            if empty_indices:
                retry_policy = self.config["protocol"]["empty_translation_retry"]
                retry_generation = {
                    **self.generation,
                    **retry_policy["generation_overrides"],
                }
                for index in empty_indices:
                    field_index = start + index + 1
                    source_value = batch[index]
                    primary_token_ids = output_ids[index].detach().cpu().tolist()
                    log_step(
                        "STEP 5/6 EMPTY RETRY "
                        f"direction={source_language}->{target_language}, "
                        f"field={field_index}/{len(values)}, source={source_value!r}, "
                        f"overrides={retry_policy['generation_overrides']}"
                    )
                    retry_status = "failed_empty_after_retry"
                    retry_decoded = ""
                    retry_token_ids: list[int] = []
                    retry_error: str | None = None
                    try:
                        retry_encoded = tokenizer(
                            [source_value], padding=True, truncation=False, return_tensors="pt"
                        )
                        retry_encoded = {
                            key: value.to(self.device) for key, value in retry_encoded.items()
                        }
                        with self.torch.inference_mode():
                            retry_output_ids = self.model.generate(
                                **retry_encoded,
                                forced_bos_token_id=forced_bos_token_id,
                                **retry_generation,
                            )
                        retry_token_ids = retry_output_ids[0].detach().cpu().tolist()
                        retry_decoded = tokenizer.batch_decode(
                            retry_output_ids, skip_special_tokens=True
                        )[0].strip()
                        if retry_decoded:
                            retry_status = "recovered_after_empty_retry"
                            batch_output[index] = retry_decoded
                    except Exception as error:
                        retry_error = f"{type(error).__name__}: {error}"

                    event = {
                        "field_index": field_index,
                        "batch_number": batch_number,
                        "batch_offset": index,
                        "source": source_value,
                        "primary_decoded": batch_output[index]
                        if retry_status == "failed_empty_after_retry"
                        else "",
                        "primary_token_ids": primary_token_ids,
                        "retry_status": retry_status,
                        "retry_generation_overrides": retry_policy[
                            "generation_overrides"
                        ],
                        "retry_decoded": retry_decoded,
                        "retry_token_ids": retry_token_ids,
                        "retry_error": retry_error,
                        "source_fallback_used": False,
                    }
                    retry_events.append(event)
                    log_step(
                        "STEP 5/6 EMPTY RETRY RESULT "
                        f"direction={source_language}->{target_language}, "
                        f"field={field_index}/{len(values)}, status={retry_status}, "
                        f"decoded={retry_decoded!r}"
                    )
            translated.extend(value.strip() for value in batch_output)
        return translated, retry_events


def _translate_rows(
    plan: list[dict[str, Any]],
    translator: NllbTranslator,
    config: dict[str, Any],
    existing: dict[str, dict[str, Any]],
    output_path: Path,
    provenance: dict[str, Any],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in plan:
        grouped[(row["source_language"], row["target_language"])].append(row)

    completed = dict(existing)
    for source_language, target_language in sorted(grouped):
        direction_rows = sorted(grouped[(source_language, target_language)], key=lambda row: row["pair_id"])
        pending = [row for row in direction_rows if row["translation_id"] not in completed]
        if not pending:
            log_step(f"STEP 5/6 SKIP {source_language}->{target_language}: already complete")
            continue
        log_step(
            f"STEP 5/6 direction {source_language}->{target_language}: "
            f"{len(pending)} MCQs, {len(pending) * 5} fields"
        )
        field_values: list[str] = []
        for row in pending:
            field_values.extend(
                [row["source_question_stem"]]
                + [row["source_options"][label] for label in ("A", "B", "C", "D")]
            )
        translated_values, retry_events = translator.translate_direction(
            field_values, source_language, target_language
        )
        if len(translated_values) != len(pending) * len(TRANSLATABLE_FIELDS):
            raise RuntimeError("Unexpected translated field count.")

        retry_events_by_row: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for event in retry_events:
            zero_based_field = int(event["field_index"]) - 1
            row_index, field_offset = divmod(zero_based_field, len(TRANSLATABLE_FIELDS))
            event = {
                **event,
                "translation_id": pending[row_index]["translation_id"],
                "pair_id": pending[row_index]["pair_id"],
                "field_name": TRANSLATABLE_FIELDS[field_offset],
            }
            retry_events_by_row[row_index].append(event)

        for index, row in enumerate(pending):
            values = translated_values[
                index * len(TRANSLATABLE_FIELDS) : (index + 1) * len(TRANSLATABLE_FIELDS)
            ]
            translated_options = dict(zip(("A", "B", "C", "D"), values[1:], strict=True))
            row_retry_events = retry_events_by_row.get(index, [])
            failed_fields = [
                event["field_name"]
                for event in row_retry_events
                if event["retry_status"] == "failed_empty_after_retry"
            ]
            if failed_fields:
                translation_status = "failed_empty_after_retry"
            elif row_retry_events:
                translation_status = "recovered_after_empty_retry"
            else:
                translation_status = "ok"
            translated_row = {
                **row,
                "translated_question_stem": values[0],
                "translated_options": translated_options,
                "translated_question_raw": render_with_source_layout(
                    row["source_question_raw"], values[0], translated_options
                ),
                "translator_model_id": NLLB_MODEL_ID,
                "translator_revision": NLLB_REVISION,
                "translator_src_code": NLLB_LANGUAGE_CODES[source_language],
                "translator_tgt_code": NLLB_LANGUAGE_CODES[target_language],
                "translation_generation_config": config["generation"],
                "translation_status": translation_status,
                "translation_retry_events": row_retry_events,
                "translation_failed_fields": failed_fields,
                "translation_analysis_eligible": not failed_fields,
                **provenance,
            }
            completed[translated_row["translation_id"]] = translated_row

        checkpoint_rows = sorted(completed.values(), key=lambda row: row["translation_id"])
        validate_translation_rows(checkpoint_rows, allow_partial=True)
        write_jsonl_atomic(output_path, checkpoint_rows)
        log_step(
            f"STEP 5/6 CHECKPOINT {len(checkpoint_rows)}/{EXPECTED_INTERVENTION_ROWS}: "
            f"{output_path}"
        )
    return sorted(completed.values(), key=lambda row: row["translation_id"])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build the frozen RQ4 REL NLLB translation artifact.")
    parser.add_argument(
        "--annotation-manifest",
        type=Path,
        default=Path("../annotation/rel_text_dependency/data/pilot_manifest.json"),
    )
    parser.add_argument(
        "--qas-dir",
        type=Path,
        default=Path("data/raw/mpr_gui_bench_qas/qas"),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/interventions/rel_nllb_query_alignment.yaml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived/interventions/rel_nllb_translations.jsonl"),
    )
    parser.add_argument(
        "--issue-audit-out",
        type=Path,
        default=Path(
            "data/derived/interventions/rel_nllb_translation_issue_audit.jsonl"
        ),
    )
    parser.add_argument("--plan-out", type=Path, default=None)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--log-every-batches", type=int, default=10)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.batch_size < 1:
        raise ValueError("--batch-size must be positive.")
    if args.log_every_batches < 1:
        raise ValueError("--log-every-batches must be positive.")
    log_step(f"STEP 1/6 validating frozen config: {args.config}")
    config = load_yaml(args.config)
    _validate_config(config)
    log_step("STEP 2/6 reading frozen REL source and constructing canonical mismatch pairs")
    source_rows = load_rel_source_rows(args.annotation_manifest, args.qas_dir)
    plan = build_translation_plan(source_rows)
    validate_plan_rows(plan)
    if args.plan_out is not None:
        write_jsonl_atomic(args.plan_out, plan)

    log_step(
        "STEP 2/6 plan validated: "
        f"rows={len(plan)}, directions=30, translated_fields={len(plan) * 5}, "
        "dependency_blind=true"
    )
    print(
        json.dumps(
            {
                "status": "validated_plan",
                "rows": len(plan),
                "directions": 30,
                "fields_per_row": 5,
                "translated_fields": len(plan) * 5,
                "dependency_blind": True,
            },
            indent=2,
        )
    )
    if args.dry_run:
        runtime_preflight(config, args.device)
        log_step("DRY RUN COMPLETE: no model loaded and no translations generated")
        return

    log_step(
        "STEP 3/6 checking resume artifact: "
        f"resume={args.resume}, output_exists={args.output.exists()}"
    )
    existing_rows = (
        [
            _normalize_translation_audit_metadata(row)
            for row in read_jsonl(args.output)
        ]
        if args.resume and args.output.exists()
        else []
    )
    if existing_rows:
        validate_translation_rows(existing_rows, allow_partial=True)
    existing = {row["translation_id"]: row for row in existing_rows}
    created_at = datetime.now(timezone.utc).isoformat()
    provenance = {
        "schema_version": str(config["schema_version"]),
        "source_manifest_sha256": canonical_text_sha256(args.annotation_manifest),
        "source_qas_directory": args.qas_dir.as_posix(),
        "source_qas_sha256": {
            language: canonical_text_sha256(args.qas_dir / f"rel_el_{language}.jsonl")
            for language in NLLB_LANGUAGE_CODES
        },
        "code_commit": git_commit(),
        "created_at": created_at,
        "runtime": {
            "platform": platform.platform(),
            "device": args.device,
            "batch_size": args.batch_size,
            "software_versions": software_versions(),
        },
    }
    translator = NllbTranslator(
        config=config,
        device=args.device,
        batch_size=args.batch_size,
        log_every_batches=args.log_every_batches,
        local_files_only=args.local_files_only,
    )
    log_step(
        f"STEP 5/6 translation start: completed={len(existing)}, "
        f"pending={EXPECTED_INTERVENTION_ROWS - len(existing)}"
    )
    result = _translate_rows(plan, translator, config, existing, args.output, provenance)
    log_step("STEP 6/6 validating complete translation artifact")
    validate_translation_rows(result)
    write_jsonl_atomic(args.output, result)
    issue_rows = [
        {
            "translation_id": row["translation_id"],
            "pair_id": row["pair_id"],
            "parallel_id": row["parallel_id"],
            "source_language": row["source_language"],
            "target_language": row["target_language"],
            "translation_status": row["translation_status"],
            "translation_failed_fields": row["translation_failed_fields"],
            "translation_analysis_eligible": row["translation_analysis_eligible"],
            "translation_retry_events": row["translation_retry_events"],
        }
        for row in result
        if row["translation_status"] != "ok"
    ]
    write_jsonl_atomic(args.issue_audit_out, issue_rows)
    recovered_rows = sum(
        row["translation_status"] == "recovered_after_empty_retry" for row in result
    )
    failed_rows = sum(
        row["translation_status"] == "failed_empty_after_retry" for row in result
    )
    log_step(
        f"COMPLETE: {len(result)} validated translations -> {args.output}; "
        f"retry_recovered_rows={recovered_rows}, failed_rows={failed_rows}, "
        f"issue_audit={args.issue_audit_out}"
    )


if __name__ == "__main__":
    main()
