"""Run frozen REL O/R/C/F inputs through the existing model adapters."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from mpr_crosslocale.data.rel_followup import (
    BUNDLE_MANIFEST,
    CONDITIONS,
    digest,
    validate_dataset,
    verify_bundle,
    write_json,
)
from mpr_crosslocale.inference.answer_parser import parse_label
from mpr_crosslocale.inference.label_scoring import deterministic_mock_label_score
from mpr_crosslocale.inference.prompts import build_prompt_text
from mpr_crosslocale.inference.runtime import git_commit, load_yaml, software_versions
from mpr_crosslocale.inference.system_prompts import build_system_prompt


def stable_hash(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def input_id(row: dict) -> str:
    return f"rel_orcf::{row['pair_id']}::{row['condition']}"


def select_rows(rows: list[dict], population: str, max_items: int | None, seed: int) -> list[dict]:
    if max_items is not None and max_items < 1:
        raise ValueError("--max-items must be positive")
    if max_items is not None:
        by_dependency = defaultdict(set)
        for row in rows:
            by_dependency[row["text_dependency"]].add(row["parallel_id"])
        rng = random.Random(seed)
        pools = []
        for name in sorted(by_dependency):
            pool = sorted(by_dependency[name])
            rng.shuffle(pool)
            pools.append(pool)
        selected = []
        while any(pools) and len(selected) < max_items:
            for pool in pools:
                if pool and len(selected) < max_items:
                    selected.append(pool.pop())
        rows = [r for r in rows if r["parallel_id"] in set(selected)]
    if population == "mismatch":
        rows = [r for r in rows if not r["matched"]]
    elif population == "matched":
        rows = [r for r in rows if r["matched"]]
    return sorted(
        rows,
        key=lambda r: (
            r["parallel_id"],
            r["query_language"],
            r["gui_language"],
            CONDITIONS.index(r["condition"]),
        ),
    )


def inference_plan(rows: list[dict]) -> tuple[dict, dict]:
    """Reuse only exact prompts with the same image/gold inside the same language pair."""
    canonical, aliases, seen = {}, {}, {}
    for row in rows:
        key = (row["pair_id"], row["image_path"], row["question"], row["gold_answer"])
        identity = input_id(row)
        first = seen.setdefault(key, identity)
        aliases[identity] = first
        if first == identity:
            canonical[first] = row
    return canonical, aliases


def read_cache(path: Path, fingerprint: str) -> dict:
    """Recover a torn final append; reject interior corruption or a different experiment."""
    cached = {}
    if not path.exists():
        return cached
    with path.open("rb+") as handle:
        while True:
            start = handle.tell()
            line = handle.readline()
            if not line:
                break
            try:
                row = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                if handle.read(1):
                    raise ValueError("Corrupt prediction cache before its final line") from None
                handle.truncate(start)
                break
            if row.get("experiment_fingerprint") != fingerprint:
                raise ValueError("Refusing to reuse predictions from a different experiment")
            if not line.endswith(b"\n"):
                handle.seek(0, 2)
                handle.write(b"\n")
            cached[row["input_id"]] = row
    return cached


def append_prediction(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()


def code_identity() -> dict:
    package = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        package / "models/qwen25vl.py",
        package / "models/internvl25.py",
        package / "inference/prompts.py",
        package / "inference/system_prompts.py",
        package / "inference/run_cross_locale.py",
        package / "inference/answer_parser.py",
        package / "inference/label_scoring.py",
        package / "inference/option_scoring.py",
        package / "inference/runtime.py",
        package / "data/rel_followup.py",
    )
    return {p.name: digest(p) for p in paths}


def predict(adapter, row: dict, args, config: dict, system_prompt: str) -> dict:
    if args.mock_model:
        # Seed by actual canonical input, never by a reused condition or gold answer.
        rng = random.Random(f"{args.seed}:{input_id(row)}")
        generated = rng.choice(list("ABCD"))
        scores = deterministic_mock_label_score(row["gold_answer"], generated)
        prompt = (
            system_prompt + "\n\n" + build_prompt_text(row["question"], config["prompt_profile"])
        )
        output = SimpleNamespace(
            raw_output=generated,
            label_summary=scores,
            rendered_prompt=prompt,
            prompt_token_count=None,
            output_token_count=1,
        )
    else:
        adapter_row = {
            "question_raw": row["question"],
            "gold_label": row["gold_answer"],
            "image_paths": [str((args.data_root / row["image_path"]).resolve())],
        }
        output = adapter.generate_one(
            adapter_row,
            config["prompt_profile"],
            config["generation"],
            system_prompt=system_prompt,
            score_labels=not args.no_score_labels,
        )
    label = parse_label(output.raw_output)
    result = {
        "generated_text": output.raw_output,
        "parsed_generated_label": label,
        "parse_success": label is not None,
        "generation_correct": label == row["gold_answer"],
        "correct": label == row["gold_answer"],
        "rendered_prompt": output.rendered_prompt,
        "prompt_token_count": output.prompt_token_count,
        "output_token_count": output.output_token_count,
        "visual_token_count": getattr(output, "visual_token_count", None),
        "num_patches_list": getattr(output, "num_patches_list", None),
    }
    scores = output.label_summary if not args.no_score_labels else None
    if not args.no_score_labels and scores is None:
        raise RuntimeError("Requested first-token label scores were not returned")
    result.update(
        scored_predicted_label=scores.scored_predicted_label if scores else None,
        scoring_correct=(scores.scored_predicted_label == row["gold_answer"]) if scores else None,
        label_logprobs=scores.label_logprobs if scores else None,
        label_probabilities=scores.label_probabilities if scores else None,
        gold_probability=scores.gold_probability if scores else None,
        gold_rank=scores.gold_rank if scores else None,
        gold_vs_best_wrong_margin=scores.gold_vs_best_wrong_margin if scores else None,
        top1_top2_margin=scores.top1_top2_margin if scores else None,
        entropy=scores.entropy if scores else None,
        label_token_ids=scores.label_token_ids if scores else None,
        label_scoring_method=scores.scoring_method if scores else "not_requested",
        generation_scoring_disagreement=(
            label is not None and label != scores.scored_predicted_label
        )
        if scores
        else None,
    )
    return result


def export_results(
    rows: list[dict], aliases: dict, cache: dict, output: Path, contract: dict
) -> dict:
    temporary = output / "results.jsonl.tmp"
    statuses, complete = Counter(), defaultdict(dict)
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            identity = input_id(row)
            prediction = cache.get(aliases[identity], {"status": "pending"})
            status = prediction["status"]
            statuses[status] += 1
            result = {
                **row,
                **prediction,
                "input_id": identity,
                "model_id": contract["model_config"]["model_id"],
                "model_revision": contract["model_config"]["revision"],
                "experiment_fingerprint": contract["experiment_fingerprint"],
                "prediction_source_input_id": aliases[identity],
                "reused_prediction": identity != aliases[identity],
                "runtime_ms": prediction.get("inference_runtime_ms", 0)
                if identity == aliases[identity]
                else 0,
                "primary_analysis_eligible": row["primary_analysis"]
                and row["eligible_without_source_adjudication"],
            }
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            if result["primary_analysis_eligible"]:
                complete[row["pair_id"]][row["condition"]] = result
    temporary.replace(output / "results.jsonl")
    summaries = {}
    eligible = [
        quartet
        for quartet in complete.values()
        if set(quartet) == set(CONDITIONS)
        and all(r["status"] == "success" for r in quartet.values())
    ]
    for dependency in ("dependent", "independent"):
        quartets = [q for q in eligible if q["O"]["text_dependency"] == dependency]
        count = len(quartets)
        accuracy = {
            c: sum(q[c]["generation_correct"] for q in quartets) / count if count else None
            for c in CONDITIONS
        }
        contrasts = {}
        for later, earlier in (("R", "O"), ("F", "C"), ("C", "O"), ("F", "R")):
            corrected = sum(
                q[later]["generation_correct"] and not q[earlier]["generation_correct"]
                for q in quartets
            )
            introduced = sum(
                not q[later]["generation_correct"] and q[earlier]["generation_correct"]
                for q in quartets
            )
            contrasts[f"{later}-{earlier}"] = {
                "difference_pp": 100 * (corrected - introduced) / count if count else None,
                "errors_corrected": corrected,
                "errors_introduced": introduced,
            }
        summaries[dependency] = {
            "complete_unflagged_mismatch_quartets": count,
            "items": len({q["O"]["parallel_id"] for q in quartets}),
            "generation_accuracy": accuracy,
            "paired_contrasts": contrasts,
            "interaction_pp": 100
            * ((accuracy["F"] - accuracy["C"]) - (accuracy["R"] - accuracy["O"]))
            if count
            else None,
        }
    summary = {
        "outcome": "generation_correct",
        "execution_mode": contract["execution_mode"],
        "condition_rows": len(rows),
        "statuses": dict(statuses),
        "actual_successful_inferences": sum(r["status"] == "success" for r in cache.values()),
        "source_issue_rows": sum(not r["eligible_without_source_adjudication"] for r in rows),
        "parse_failures": sum(not q[c]["parse_success"] for q in eligible for c in CONDITIONS),
        "primary_descriptive_summary": summaries,
        "note": "Unadjusted descriptive estimates; no independent-sample inference or CI. "
        "Failures exclude the entire quartet; unparseable generated labels count as wrong.",
    }
    write_json(output / "summary.json", summary)
    return summary


def run(args) -> dict:
    args.data_root = args.data_root.resolve()
    rows, audit = validate_dataset(args.data_root, images=True)
    if (args.data_root / BUNDLE_MANIFEST).exists():
        verify_bundle(args.data_root, images=True)
    elif not args.dry_run and not args.mock_model:
        raise ValueError("Unpack a checksummed data bundle before GPU inference")
    rows = select_rows(rows, args.population, args.max_items, args.seed)
    canonical, aliases = inference_plan(rows)
    config = load_yaml(args.model_config)
    if config.get("model_family") not in ("qwen2_5_vl", "internvl2_5") or not config.get(
        "revision"
    ):
        raise ValueError("Use a pinned Qwen2.5-VL or InternVL2.5 model configuration")
    if config.get("prompt_profile") != "mpr_label_only_v1":
        raise ValueError("This experiment uses mpr_label_only_v1")
    if config.get("dtype") != "bfloat16" or config.get("quantization") is not None:
        raise ValueError("This experiment uses unquantized bfloat16")
    if (
        config["generation"].get("do_sample") is not False
        or config["generation"].get("num_beams") != 1
        or config["generation"].get("max_new_tokens") != 2
    ):
        raise ValueError("This experiment uses greedy generation with max_new_tokens=2")
    system_prompt, _, template = build_system_prompt("english_fixed", "en")
    mode = "mock" if args.mock_model else "gpu"
    identity = {
        "dataset_sha256": audit["conditions_sha256"],
        "bundle_manifest_sha256": digest(args.data_root / BUNDLE_MANIFEST)
        if (args.data_root / BUNDLE_MANIFEST).exists()
        else None,
        "model_config": config,
        "execution_mode": mode,
        "system_prompt": system_prompt,
        "prompt_template_version": template,
        "score_labels": not args.no_score_labels,
        "seed": args.seed,
        "population": args.population,
        "selected_input_ids_sha256": stable_hash([input_id(r) for r in rows]),
        "code_sha256": code_identity(),
        "software_versions": software_versions(),
    }
    fingerprint = stable_hash(identity)
    plan = {
        "items": len({r["parallel_id"] for r in rows}),
        "condition_rows": len(rows),
        "actual_inferences": len(canonical),
        "reused_condition_rows": len(rows) - len(canonical),
        "source_issue_rows": sum(not r["eligible_without_source_adjudication"] for r in rows),
        "items_by_dependency": dict(
            Counter({r["parallel_id"]: r["text_dependency"] for r in rows}.values())
        ),
        "experiment_fingerprint": fingerprint,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        write_json(args.output_dir / "dry_run_plan.json", plan)
        write_json(args.output_dir / "data_audit.json", audit)
        return plan
    contract_path = args.output_dir / "run_contract.json"
    if contract_path.exists():
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        if contract["experiment_fingerprint"] != fingerprint:
            raise ValueError(
                "Output directory belongs to a different dataset/model/settings/subset"
            )
        if not args.resume:
            raise ValueError("Output already exists; use --resume or a fresh output directory")
    else:
        if (args.output_dir / "predictions.jsonl").exists():
            raise ValueError("Prediction cache exists without its run contract")
        contract = {
            **identity,
            "experiment_fingerprint": fingerprint,
            "code_commit": git_commit(),
            "software_versions": software_versions(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_issue_policy": audit["source_issue_policy"],
            "deduplication_scope": "same parallel_id/query_language/gui_language only",
        }
        write_json(contract_path, contract)
    write_json(args.output_dir / "plan.json", plan)
    write_json(args.output_dir / "data_audit.json", audit)
    cache_path = args.output_dir / "predictions.jsonl"
    cache = read_cache(cache_path, fingerprint)
    if not set(cache).issubset(canonical):
        raise ValueError("Unexpected canonical IDs in prediction cache")
    pending = [
        (key, row)
        for key, row in canonical.items()
        if cache.get(key, {}).get("status") != "success"
    ]
    adapter = None
    if pending and not args.mock_model:
        import torch

        from mpr_crosslocale.inference.run_cross_locale import _build_model_adapter
        from mpr_crosslocale.inference.runtime import hardware_metadata

        if not torch.cuda.is_available():
            raise RuntimeError("GPU inference requires CUDA; use --dry-run or --mock-model locally")
        hardware = hardware_metadata()
        adapter = _build_model_adapter(
            SimpleNamespace(attn_implementation=None, device_map="cuda:0"), config
        )
    else:
        hardware = {"execution_mode": mode}
    versions = software_versions()
    commit = git_commit()
    consecutive_failures = 0
    from tqdm import tqdm

    try:
        for key, row in tqdm(pending, desc=f"REL O/R/C/F ({mode})"):
            started = time.perf_counter()
            prediction = {
                "input_id": key,
                "experiment_fingerprint": fingerprint,
                "attempt": cache.get(key, {}).get("attempt", 0) + 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "hardware": hardware,
                "software_versions": versions,
                "code_commit": commit,
            }
            try:
                prediction.update(
                    predict(adapter, row, args, config, system_prompt), status="success"
                )
                consecutive_failures = 0
            except Exception as exc:  # noqa: BLE001 -- Persist arbitrary backend failures for resume.
                consecutive_failures += 1
                prediction.update(
                    status="failed",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    error_traceback=traceback.format_exc(),
                    generation_correct=None,
                    scoring_correct=None,
                    correct=None,
                    parse_success=None,
                )
            prediction["inference_runtime_ms"] = round((time.perf_counter() - started) * 1000)
            append_prediction(cache_path, prediction)
            cache[key] = prediction
            if consecutive_failures >= 3:
                raise RuntimeError(
                    "Stopped after three consecutive failures; inspect predictions.jsonl"
                )
    finally:
        summary = export_results(rows, aliases, cache, args.output_dir, contract)
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("followup_rel_4lang"))
    parser.add_argument("--model-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--population", choices=("all", "mismatch", "matched"), default="all")
    parser.add_argument("--max-items", type=int, help="Stratified item limit for a smoke test")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock-model", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-score-labels", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run and args.mock_model:
        parser.error("Choose --dry-run or --mock-model")
    result = run(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("statuses", {}).get("failed", 0) or result.get("statuses", {}).get("pending", 0):
        raise SystemExit("Incomplete inference: rerun the same command with --resume")


if __name__ == "__main__":
    main()
