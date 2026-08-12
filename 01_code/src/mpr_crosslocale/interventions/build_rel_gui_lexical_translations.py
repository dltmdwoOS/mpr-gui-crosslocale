from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mpr_crosslocale.data.schema import LABELS
from mpr_crosslocale.inference.runtime import (
    git_commit,
    hardware_metadata,
    load_yaml,
    software_versions,
)
from mpr_crosslocale.interventions.build_rel_qwen3_contextual_translations import (
    Qwen3ContextualTranslator,
    _read_frozen_original_controls,
)
from mpr_crosslocale.interventions.rq4_contextual import (
    CONTEXTUAL_MODEL_ID,
    CONTEXTUAL_REVISION,
    EXPECTED_INTERVENTION_ROWS,
    build_contextual_plan_from_original_controls,
    canonical_json_sha256,
    select_smoke_rows,
    semantic_repair_reasons,
    semantic_repair_score,
    should_accept_semantic_repair,
    write_jsonl_atomic,
)
from mpr_crosslocale.interventions.rq4_gui_lexical import (
    LEXICAL_METHOD,
    LEXICAL_PROMPT_VERSION,
    LEXICAL_SYSTEM_PROMPT,
    build_lexical_plan,
    build_lexical_repair_prompt,
    build_lexical_semantic_repair_prompt,
    build_lexical_user_prompt,
    lexical_semantic_flags,
    read_jsonl,
    validate_lexical_config,
    validate_lexical_structured_output,
    validate_lexical_translation_rows,
)
from mpr_crosslocale.interventions.rq4_nllb import render_with_source_layout


def log_step(message: str) -> None:
    print(f"[{datetime.now().astimezone():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


class MockLexicalTranslator:
    batch_size = 2

    @staticmethod
    def generate(prompts: list[str]) -> list[str]:
        outputs = []
        marker = (
            "inventory only as lexical evidence. Return only the output JSON object.\n\n"
        )
        for prompt in prompts:
            payload = json.loads(
                prompt.split(marker, 1)[1].split("\n\nRequired output shape:", 1)[0]
            )
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


def _generate_attempts(
    translator: Qwen3ContextualTranslator | MockLexicalTranslator,
    rows: list[dict[str, Any]],
    prompts: list[str],
    attempt_number: int,
    attempt_kind: str,
) -> list[dict[str, Any]]:
    started = time.perf_counter()
    outputs = translator.generate(prompts)
    elapsed = int((time.perf_counter() - started) * 1000)
    if len(outputs) != len(rows):
        raise RuntimeError("Translator output count differs from input count.")
    attempts = []
    for row, output in zip(rows, outputs, strict=True):
        parsed, hard_errors, token_flags = validate_lexical_structured_output(output, row)
        attempts.append(
            {
                "attempt": attempt_number,
                "attempt_kind": attempt_kind,
                "raw_output": output,
                "parsed_output": parsed,
                "hard_validation_errors": hard_errors,
                "token_invariant_diagnostic_flags": token_flags,
                "runtime_ms_approx": elapsed // max(len(rows), 1),
            }
        )
    return attempts


def translate_rows(
    plan: list[dict[str, Any]],
    translator: Qwen3ContextualTranslator | MockLexicalTranslator,
    config: dict[str, Any],
    output: Path,
    existing: dict[str, dict[str, Any]],
    log_every_batches: int,
) -> list[dict[str, Any]]:
    plan_by_id = {str(row["translation_id"]): row for row in plan}
    if set(existing) - set(plan_by_id):
        raise ValueError("Resume artifact contains translations outside selected scope.")
    for translation_id, prior in existing.items():
        planned = plan_by_id[translation_id]
        for field in (
            "pair_id",
            "parallel_id",
            "source_language",
            "target_language",
            "visible_string_inventory_id",
            "visible_string_inventory_sha256",
        ):
            if prior.get(field) != planned.get(field):
                raise ValueError(f"Resume invariant changed: {translation_id}, field={field}")
    if existing:
        validate_lexical_translation_rows(list(existing.values()), len(existing))

    completed = dict(existing)
    pending = [row for row in plan if row["translation_id"] not in completed]
    batch_size = int(translator.batch_size)
    total_batches = (len(pending) + batch_size - 1) // batch_size
    provenance = {
        "translator_model_id": CONTEXTUAL_MODEL_ID,
        "translator_revision": CONTEXTUAL_REVISION,
        "translation_method": LEXICAL_METHOD,
        "prompt_template_version": LEXICAL_PROMPT_VERSION,
        "system_prompt_sha256": canonical_json_sha256(LEXICAL_SYSTEM_PROMPT),
        "translation_generation_config": config["translation_generation"],
        "translator_code_commit": git_commit(),
        "translator_software_versions": software_versions(),
        "translator_hardware": hardware_metadata(),
        "translator_runtime_batch_size": batch_size,
        "translator_screenshot_exposed": False,
        "translator_layout_exposed": False,
        "translator_visible_strings_exposed": True,
        "translator_inventory_order_exposed": False,
        "translator_inventory_duplicate_counts_exposed": False,
        "translator_gold_exposed": False,
        "translator_dependency_exposed": False,
        "translator_human_parallel_exposed": False,
    }
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        batch_no = start // batch_size + 1
        if batch_no == 1 or batch_no == total_batches or batch_no % log_every_batches == 0:
            global_start = len(completed) + 1
            global_end = len(completed) + len(batch)
            log_step(
                f"STEP 5/7 batch {batch_no}/{total_batches}: "
                f"pending_rows={start + 1}-{start + len(batch)}/{len(pending)}, "
                f"global_rows={global_start}-{global_end}/{len(plan)}"
            )
        prompts = [build_lexical_user_prompt(row) for row in batch]
        primary_attempts = _generate_attempts(
            translator, batch, prompts, 0, "initial"
        )
        batch_repaired = False
        for row, primary in zip(batch, primary_attempts, strict=True):
            attempts = [primary]
            final = primary
            if primary["hard_validation_errors"]:
                batch_repaired = True
                log_step(
                    f"STEP 5/7 STRUCTURE REPAIR {row['translation_id']}: "
                    f"{primary['hard_validation_errors']}"
                )
                repair_prompt = build_lexical_repair_prompt(
                    row, primary["raw_output"], primary["hard_validation_errors"]
                )
                repaired = _generate_attempts(
                    translator,
                    [row],
                    [repair_prompt],
                    len(attempts),
                    "structure_repair",
                )[0]
                attempts.append(repaired)
                final = repaired
            parsed = final["parsed_output"]
            hard_errors = list(final["hard_validation_errors"])
            if parsed is None or hard_errors:
                raise RuntimeError(
                    f"Lexical translation failed after repair: {row['translation_id']}, "
                    f"errors={hard_errors}"
                )
            initial_semantic_flags = lexical_semantic_flags(row, parsed)
            initial_semantic_reasons = semantic_repair_reasons(
                row, parsed, initial_semantic_flags
            )
            initial_semantic_score = semantic_repair_score(initial_semantic_reasons)
            semantic_repair_attempted = False
            semantic_repair_accepted = False
            final_semantic_reasons = list(initial_semantic_reasons)
            final_semantic_score = initial_semantic_score
            if initial_semantic_reasons:
                semantic_repair_attempted = True
                batch_repaired = True
                log_step(
                    f"STEP 5/7 SEMANTIC REPAIR {row['translation_id']}: "
                    f"{initial_semantic_reasons}"
                )
                semantic_prompt = build_lexical_semantic_repair_prompt(
                    row, final["raw_output"], initial_semantic_reasons
                )
                candidate = _generate_attempts(
                    translator,
                    [row],
                    [semantic_prompt],
                    len(attempts),
                    "semantic_repair",
                )[0]
                attempts.append(candidate)
                candidate_parsed = candidate["parsed_output"]
                candidate_reasons = list(initial_semantic_reasons)
                if candidate_parsed is not None:
                    candidate_flags = lexical_semantic_flags(row, candidate_parsed)
                    candidate_reasons = semantic_repair_reasons(
                        row, candidate_parsed, candidate_flags
                    )
                semantic_repair_accepted = should_accept_semantic_repair(
                    initial_semantic_reasons,
                    candidate["hard_validation_errors"],
                    candidate_reasons,
                )
                candidate["semantic_repair_reasons"] = candidate_reasons
                candidate["semantic_repair_score"] = semantic_repair_score(
                    candidate_reasons
                )
                candidate["semantic_repair_accepted"] = semantic_repair_accepted
                if semantic_repair_accepted:
                    final = candidate
                    parsed = candidate_parsed
                    final_semantic_reasons = candidate_reasons
                    final_semantic_score = semantic_repair_score(candidate_reasons)
                    log_step(
                        f"STEP 5/7 SEMANTIC REPAIR ACCEPTED {row['translation_id']}: "
                        f"{initial_semantic_score}->{final_semantic_score}"
                    )
            assert parsed is not None
            translated_stem = str(parsed["question_stem"]).strip()
            translated_options = {
                label: str(parsed["options"][label]).strip() for label in LABELS
            }
            translated_raw = render_with_source_layout(
                str(row["source_question_raw"]), translated_stem, translated_options
            )
            semantic_flags = lexical_semantic_flags(row, parsed)
            if not semantic_repair_accepted:
                final_semantic_reasons = semantic_repair_reasons(
                    row, parsed, semantic_flags
                )
                final_semantic_score = semantic_repair_score(final_semantic_reasons)
            if semantic_repair_accepted:
                status = "recovered_after_semantic_repair"
            elif semantic_repair_attempted:
                status = "eligible_after_rejected_semantic_repair"
            elif any(
                attempt["attempt_kind"] == "structure_repair" for attempt in attempts
            ):
                status = "recovered_after_structure_repair"
            else:
                status = "ok"
            artifact = {
                **row,
                "translated_question_stem": translated_stem,
                "translated_options": translated_options,
                "translated_question_raw": translated_raw,
                "translation_status": status,
                "translation_attempts": attempts,
                "hard_validation_errors": [],
                "token_invariant_diagnostic_flags": final[
                    "token_invariant_diagnostic_flags"
                ],
                "semantic_diagnostic_flags": semantic_flags,
                "semantic_repair_attempted": semantic_repair_attempted,
                "semantic_repair_accepted": semantic_repair_accepted,
                "initial_semantic_repair_reasons": initial_semantic_reasons,
                "initial_semantic_repair_score": initial_semantic_score,
                "final_semantic_repair_reasons": final_semantic_reasons,
                "final_semantic_repair_score": final_semantic_score,
                "translation_analysis_eligible": True,
                "user_prompt_sha256": canonical_json_sha256(
                    build_lexical_user_prompt(row)
                ),
                **provenance,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            completed[str(row["translation_id"])] = artifact
        if (
            batch_no == total_batches
            or batch_no % log_every_batches == 0
            or batch_repaired
        ):
            checkpoint = sorted(completed.values(), key=lambda row: row["translation_id"])
            validate_lexical_translation_rows(checkpoint, len(checkpoint))
            write_jsonl_atomic(output, checkpoint)
            log_step(f"STEP 5/7 CHECKPOINT {len(checkpoint)}/{len(plan)}: {output}")
    return sorted(completed.values(), key=lambda row: row["translation_id"])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Translate REL MCQs using query-blind target-GUI lexical inventories."
    )
    parser.add_argument(
        "--source-controls",
        type=Path,
        default=Path("data/derived/interventions/rel_nllb_original_controls.jsonl"),
    )
    parser.add_argument("--inventories", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/interventions/rel_gui_lexical_localization.yaml"),
    )
    parser.add_argument("--scope", choices=["smoke", "full"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--inventory-failure-audit-out",
        type=Path,
        default=None,
        help="Defaults to <output_stem>_inventory_failures.jsonl.",
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--log-every-batches", type=int, default=10)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock-model", action="store_true")
    args = parser.parse_args(argv)

    log_step("STEP 1/7 validating frozen two-step lexical configuration")
    config = load_yaml(args.config)
    validate_lexical_config(config)

    log_step("STEP 2/7 reading controls and query-blind GUI inventories")
    controls = _read_frozen_original_controls(args.source_controls)
    inventories = read_jsonl(args.inventories)
    if args.scope == "smoke":
        smoke = select_smoke_rows(build_contextual_plan_from_original_controls(controls))
        selected_pair_ids = {str(row["pair_id"]) for row in smoke}
        needed_endpoints = {
            str(row["target_human_parallel_endpoint_id"]) for row in smoke
        }
        inventories = [
            row
            for row in inventories
            if str(row["target_human_parallel_endpoint_id"]) in needed_endpoints
        ]
        expected = 60
    else:
        selected_pair_ids = None
        expected = EXPECTED_INTERVENTION_ROWS
    plan = build_lexical_plan(controls, inventories, selected_pair_ids)
    if len(plan) != expected:
        raise AssertionError(f"Selected lexical plan has {len(plan)} rows, expected {expected}.")
    failed_inventory_ids = {
        row["visible_string_inventory_id"]
        for row in plan
        if row["inventory_failure_included"]
    }
    failure_audit = []
    for inventory_id in sorted(failed_inventory_ids):
        inventory = next(row for row in inventories if row["inventory_id"] == inventory_id)
        affected = [
            row for row in plan if row["visible_string_inventory_id"] == inventory_id
        ]
        failure_audit.append(
            {
                "inventory_id": inventory_id,
                "target_human_parallel_endpoint_id": inventory[
                    "target_human_parallel_endpoint_id"
                ],
                "parallel_id": inventory["parallel_id"],
                "target_language": inventory["target_language"],
                "inventory_status": inventory["inventory_status"],
                "final_validation_errors": inventory.get(
                    "final_validation_errors", []
                ),
                "attempt_count": inventory.get("attempt_count"),
                "raw_extractor_output_preserved_in_inventory_artifact": True,
                "failed_inventory_policy": affected[0]["inventory_failure_policy"],
                "lexical_evidence_available": False,
                "default_translation_and_inference_included": True,
                "sensitivity_exclusion_recommended": True,
                "affected_translation_count": len(affected),
                "affected_translation_ids": [
                    row["translation_id"] for row in affected
                ],
                "affected_pair_ids": [row["pair_id"] for row in affected],
            }
        )
    failure_audit_path = args.inventory_failure_audit_out or args.output.with_name(
        args.output.stem + "_inventory_failures.jsonl"
    )
    write_jsonl_atomic(failure_audit_path, failure_audit)
    print(
        json.dumps(
            {
                "scope": args.scope,
                "translation_rows": len(plan),
                "unique_inventory_rows": len(
                    {row["visible_string_inventory_id"] for row in plan}
                ),
                "translator_has_image_access": False,
                "translator_has_layout_access": False,
                "translator_has_visible_string_access": True,
                "failed_inventory_rows": len(failed_inventory_ids),
                "affected_translation_rows": sum(
                    row["inventory_failure_included"] for row in plan
                ),
                "failed_inventory_default_included": True,
                "inventory_failure_audit": failure_audit_path.as_posix(),
            },
            indent=2,
        )
    )
    default_batch_size = int(config["runtime"]["translation_batch_size"])
    benchmark_batch_sizes = {
        int(value)
        for value in config["runtime"]["benchmark_translation_batch_sizes"]
    }
    if not args.mock_model and args.batch_size not in {
        default_batch_size,
        *benchmark_batch_sizes,
    }:
        raise ValueError("Translation batch size is not an approved runtime size.")
    if args.batch_size != default_batch_size and args.scope != "smoke":
        raise ValueError(
            "Nondefault translation batch sizes are smoke-only until an exact "
            "equivalence audit is passed."
        )
    if args.dry_run:
        log_step("DRY RUN COMPLETE: no Qwen3 model loaded")
        return
    existing_rows = read_jsonl(args.output) if args.resume and args.output.exists() else []
    existing = {str(row["translation_id"]): row for row in existing_rows}
    log_step(
        f"STEP 3/7 preparing no-image Qwen3 translator: completed={len(existing)}, "
        f"pending={len(plan) - len(existing)}, mock={args.mock_model}"
    )
    if args.mock_model:
        translator: Qwen3ContextualTranslator | MockLexicalTranslator = (
            MockLexicalTranslator()
        )
        translator.batch_size = args.batch_size
    else:
        translator_config = {
            "translator": config["translator"],
            "generation": config["translation_generation"],
        }
        translator = Qwen3ContextualTranslator(
            translator_config,
            device=args.device,
            batch_size=args.batch_size,
            local_files_only=args.local_files_only,
            system_prompt=LEXICAL_SYSTEM_PROMPT,
        )
    log_step("STEP 4/7 translator ready; screenshot and layout remain hidden")
    completed = translate_rows(
        plan, translator, config, args.output, existing, args.log_every_batches
    )
    log_step("STEP 6/7 validating completed lexical translation artifact")
    validate_lexical_translation_rows(completed, expected)
    log_step("STEP 7/7 complete")
    print(
        json.dumps(
            {
                "status": "complete",
                "scope": args.scope,
                "rows": len(completed),
                "structure_repair_rows": sum(
                    any(
                        attempt["attempt_kind"] == "structure_repair"
                        for attempt in row["translation_attempts"]
                    )
                    for row in completed
                ),
                "semantic_repair_attempted_rows": sum(
                    row["semantic_repair_attempted"] for row in completed
                ),
                "semantic_repair_accepted_rows": sum(
                    row["semantic_repair_accepted"] for row in completed
                ),
                "token_diagnostic_rows": sum(
                    bool(row["token_invariant_diagnostic_flags"]) for row in completed
                ),
                "semantic_diagnostic_rows": sum(
                    bool(row["semantic_diagnostic_flags"]) for row in completed
                ),
                "output": args.output.as_posix(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
