"""Experiment A: REL multiple-choice inference for O, T and R in the same run.

    O  source-language reference names           (re-run anchor)
    T  names machine-translated into the GUI language without the screenshot (new)
    R  names as written in the GUI-language version of the question (re-run anchor)

T rows come from expA_inputs/T_conditions.jsonl (locked by expA_inputs/expA_lock.json).
Before any inference every T row is checked against the frozen O and R rows of the same
pair: same image, gold answer, option keys and pair list as the R_stem/R_opts inputs, and
the question is stem + options. T may equal R (all names translated exactly as on screen)
or O (every name left untranslated); both counts are written to plan.json.

The three conditions of one pair are queued next to each other. Qwen3 runs with batch 3
(one batch = one pair), InternVL3.5 with batch 1 as in its earlier runs.

Model loading, prompting, batching, parsing, label scoring and the resumable cache are
imported unchanged from run_rel_followup.py. The model config, system prompt and template
must equal the earlier run contract of the chosen model (already in rstem_ropts_inputs/
after the R_stem/R_opts addon of that model is unpacked).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import chain
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REL = HERE.parent  # followup_rel_4lang/
sys.path.insert(0, str(REL.parent / "01_code/src"))

from mpr_crosslocale.data.rel_followup import validate_dataset, write_json  # noqa: E402
from mpr_crosslocale.inference.run_rel_followup import (  # noqa: E402
    append_prediction,
    code_identity,
    predict_chunk,
    read_cache,
    stable_hash,
)
from mpr_crosslocale.inference.runtime import git_commit, load_yaml, software_versions  # noqa: E402
from mpr_crosslocale.inference.system_prompts import build_system_prompt  # noqa: E402

CONDITIONS = ("O", "T", "R")
INPUTS = HERE / "expA_inputs"
T_FILE = INPUTS / "T_conditions.jsonl"
LOCK = INPUTS / "expA_lock.json"
MIXED = REL / "rstem_ropts_inputs" / "mixed_conditions.jsonl"
EXPECTED_DATASET_SHA256 = "e5aa6cd0c426cc648322c8c7702b1b6985fddb09ad895d70a85d86c6a3de38ce"
EXPECTED_PAIRS = {"main": 1896, "pilot": 48}
MODELS = {
    "qwen3": {"contract": REL / "rstem_ropts_inputs/run_contract_qwen3_rel_20261107.json",
              "batch_size": 3, "strict": True},
    "internvl35": {"contract": REL / "rstem_ropts_inputs/run_contract_internvl35_rel_20261109.json",
                   "batch_size": 1, "strict": False},
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(stem: str, options: dict) -> str:
    return stem + " " + " ".join(f"{k}: {options[k]}" for k in "ABCD")


def input_id(pair_id: str, condition: str) -> str:
    return f"rel_expA::{pair_id}::{condition}"


def load_rows(data_root: Path, split: str, max_items: int | None, check_images: bool):
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    if sha256_file(T_FILE) != lock["T_conditions.jsonl"]:
        raise ValueError("T_conditions.jsonl differs from expA_lock.json")
    if sha256_file(MIXED) != lock["source_mixed_conditions.jsonl"]:
        raise ValueError("rstem_ropts_inputs/mixed_conditions.jsonl differs from the one T was built from")
    t_rows = [json.loads(line) for line in T_FILE.read_text(encoding="utf-8").splitlines() if line]
    if dict(Counter(r["split"] for r in t_rows)) != EXPECTED_PAIRS or len({r["pair_id"] for r in t_rows}) != len(t_rows):
        raise ValueError("Unexpected T pair counts or duplicate pair ids")
    mixed_pairs = {}
    for line in MIXED.read_text(encoding="utf-8").splitlines():
        if line:
            m = json.loads(line)
            mixed_pairs[m["pair_id"]] = m
    if set(mixed_pairs) != {r["pair_id"] for r in t_rows}:
        raise ValueError("T pairs differ from the R_stem/R_opts pairs")

    frozen, audit = validate_dataset(data_root, images=check_images)
    if audit["conditions_sha256"] != EXPECTED_DATASET_SHA256:
        raise ValueError("Frozen REL dataset differs from the 2026-11-07/09 runs")
    by_key = {(r["pair_id"], r["condition"]): r for r in frozen}

    pairs = {}
    for t in t_rows:
        if split != "all" and t["split"] != split:
            continue
        pid = t["pair_id"]
        o, r, m = by_key[(pid, "O")], by_key[(pid, "R")], mixed_pairs[pid]
        image = t["image_path"].removeprefix("followup_rel_4lang/")
        if not (image == o["image_path"] == r["image_path"]) or t["image_sha256"] != m["image_sha256"]:
            raise ValueError(f"Image differs from frozen O/R: {pid}")
        if not (t["gold_answer"] == o["gold_answer"] == r["gold_answer"]):
            raise ValueError(f"Gold differs: {pid}")
        if (t["parallel_id"], t["query_language"], t["gui_language"], t["split"]) != \
                (m["parallel_id"], m["query_language"], m["gui_language"], m["split"]):
            raise ValueError(f"Pair metadata differs: {pid}")
        if set(t["options"]) != set("ABCD") or t["question"] != render(t["question_stem"], t["options"]):
            raise ValueError(f"T question is not stem+options: {pid}")
        if o["question"] != render(o["question_stem"], o["options"]) or \
                r["question"] != render(r["question_stem"], r["options"]):
            raise ValueError(f"Frozen question is not stem+options: {pid}")
        if check_images and sha256_file(data_root / image) != t["image_sha256"]:
            raise ValueError(f"Image hash mismatch: {image}")
        base = {"pair_id": pid, "parallel_id": t["parallel_id"], "split": t["split"],
                "query_language": t["query_language"], "gui_language": t["gui_language"],
                "image_path": image, "gold_answer": t["gold_answer"],
                "text_dependency": o["text_dependency"]}
        pairs[pid] = {"O": {**base, "condition": "O", "question": o["question"]},
                      "T": {**base, "condition": "T", "question": t["question"]},
                      "R": {**base, "condition": "R", "question": r["question"]}}

    pair_ids = sorted(pairs)
    if max_items is not None:
        keep = sorted({pairs[p]["O"]["parallel_id"] for p in pair_ids})[:max_items]
        pair_ids = [p for p in pair_ids if pairs[p]["O"]["parallel_id"] in keep]
    rows = [pairs[pid][c] for pid in pair_ids for c in CONDITIONS]
    return rows, audit


def summarize(rows: list[dict], cache: dict) -> dict:
    statuses = Counter()
    acc = defaultdict(lambda: [0, 0])
    parse_fail = 0
    for row in rows:
        pred = cache.get(input_id(row["pair_id"], row["condition"]))
        status = pred["status"] if pred else "pending"
        statuses[status] += 1
        if status == "success":
            parse_fail += not pred["parse_success"]
            cell = acc[(row["split"], row["condition"])]
            cell[0] += bool(pred["generation_correct"])
            cell[1] += 1
    return {
        "rows": len(rows), "statuses": dict(statuses), "parse_failures": parse_fail,
        "accuracy": {f"{s}/{c}": {"correct": a, "n": n, "rate": round(a / n, 4) if n else None}
                     for (s, c), (a, n) in sorted(acc.items())},
        "complete": statuses.get("success", 0) == len(rows),
    }


def run(args) -> dict:
    spec = MODELS[args.model]
    if args.batch_size != spec["batch_size"]:
        raise ValueError(f"Use batch size {spec['batch_size']} for {args.model}")
    data_root = args.data_root.resolve()
    rows, audit = load_rows(data_root, args.split, args.max_items,
                            check_images=not (args.dry_run or args.mock_model))
    config = load_yaml(args.model_config)
    reference = json.loads(spec["contract"].read_text(encoding="utf-8"))
    if config != reference["model_config"]:
        raise ValueError(f"Model config differs from the earlier {args.model} run contract")
    system_prompt, _, template = build_system_prompt("english_fixed", "en")
    if system_prompt != reference["system_prompt"] or template != reference["prompt_template_version"]:
        raise ValueError(f"System prompt differs from the earlier {args.model} run contract")
    mode = "mock" if args.mock_model else "gpu"
    identity = {
        "schema": "rel-expA-T-v1",
        "model": args.model,
        "conditions": list(CONDITIONS),
        "dataset_sha256": audit["conditions_sha256"],
        "T_inputs_sha256": sha256_file(T_FILE),
        "expA_lock_sha256": sha256_file(LOCK),
        "model_config": config, "execution_mode": mode,
        "system_prompt": system_prompt, "prompt_template_version": template,
        "score_labels": True, "batch_size": args.batch_size,
        "strict_batch_size": spec["strict"],
        "queue_order": "pair_id sorted; O, T, R adjacent",
        "split": args.split, "max_items": args.max_items,
        "selected_input_ids_sha256": stable_hash([input_id(r["pair_id"], r["condition"]) for r in rows]),
        "code_sha256": {**code_identity(), "run_rel_T.py": sha256_file(Path(__file__))},
        "software_versions": software_versions(),
    }
    fingerprint = stable_hash(identity)
    plan = {"model": args.model, "pairs": len(rows) // 3, "items": len({r["parallel_id"] for r in rows}),
            "inferences": len(rows), "batch_size": args.batch_size,
            "by_condition": dict(Counter(r["condition"] for r in rows)),
            "T_equals_O_pairs": sum(1 for i in range(0, len(rows), 3) if rows[i + 1]["question"] == rows[i]["question"]),
            "T_equals_R_pairs": sum(1 for i in range(0, len(rows), 3) if rows[i + 1]["question"] == rows[i + 2]["question"]),
            "experiment_fingerprint": fingerprint}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "plan.json", plan)
    if args.dry_run:
        return plan

    contract_path = args.output_dir / "run_contract.json"
    if contract_path.exists():
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        if contract["experiment_fingerprint"] != fingerprint:
            raise ValueError("Output directory belongs to a different input/model/settings")
        if not args.resume:
            raise ValueError("Output already exists; use --resume or a new output directory")
    else:
        if (args.output_dir / "predictions.jsonl").exists():
            raise ValueError("Prediction cache exists without its run contract")
        contract = {**identity, "experiment_fingerprint": fingerprint, "code_commit": git_commit(),
                    "created_at": datetime.now(timezone.utc).isoformat()}
        write_json(contract_path, contract)

    cache_path = args.output_dir / "predictions.jsonl"
    cache = read_cache(cache_path, fingerprint)
    keys = {input_id(r["pair_id"], r["condition"]): r for r in rows}
    if not set(cache) <= set(keys):
        raise ValueError("Unexpected IDs in prediction cache")
    # Keep the three conditions of a pair together across resumes.
    unfinished = {r["pair_id"] for k, r in keys.items() if cache.get(k, {}).get("status") != "success"}
    pending = [(k, r) for k, r in keys.items() if r["pair_id"] in unfinished]

    adapter, hardware = None, {"execution_mode": mode}
    if pending and not args.mock_model:
        import torch
        from mpr_crosslocale.inference.run_cross_locale import _build_model_adapter
        from mpr_crosslocale.inference.runtime import hardware_metadata
        if not torch.cuda.is_available():
            raise RuntimeError("GPU inference requires CUDA; use --dry-run or --mock-model locally")
        hardware = hardware_metadata()
        adapter = _build_model_adapter(SimpleNamespace(attn_implementation=None, device_map="cuda:0"), config)

    chunk_args = SimpleNamespace(mock_model=args.mock_model, no_score_labels=False, seed=args.seed,
                                 data_root=data_root, strict_batch_size=spec["strict"])
    versions, commit, failures = software_versions(), git_commit(), 0
    from tqdm import tqdm
    try:
        progress = tqdm(total=len(pending), desc=f"REL expA O/T/R {args.model} ({mode}, batch={args.batch_size})")
        batches = (predict_chunk(adapter, pending[i:i + args.batch_size], chunk_args, config, system_prompt)
                   for i in range(0, len(pending), args.batch_size))
        for key, row, result in chain.from_iterable(batches):
            prediction = {"input_id": key, "experiment_fingerprint": fingerprint,
                          "attempt": cache.get(key, {}).get("attempt", 0) + 1,
                          "timestamp": datetime.now(timezone.utc).isoformat(),
                          "hardware": hardware, "software_versions": versions, "code_commit": commit,
                          "pair_id": row["pair_id"], "parallel_id": row["parallel_id"],
                          "split": row["split"], "condition": row["condition"],
                          "query_language": row["query_language"], "gui_language": row["gui_language"],
                          "gold_answer": row["gold_answer"], **result}
            failures = 0 if result["status"] == "success" else failures + 1
            append_prediction(cache_path, prediction)
            cache[key] = prediction
            progress.update(1)
            if failures >= 3:
                raise RuntimeError("Stopped after three consecutive failures; inspect predictions.jsonl")
    finally:
        if "progress" in locals():
            progress.close()
        summary = summarize(rows, cache)
        write_json(args.output_dir / "summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", choices=sorted(MODELS), required=True)
    parser.add_argument("--data-root", type=Path, default=Path("followup_rel_4lang"))
    parser.add_argument("--model-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--split", choices=("main", "pilot", "all"), default="main")
    parser.add_argument("--max-items", type=int, help="Keep only the first N items (smoke test)")
    parser.add_argument("--batch-size", type=int, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock-model", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run and args.mock_model:
        parser.error("Choose --dry-run or --mock-model")
    result = run(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.dry_run and not result.get("complete"):
        raise SystemExit("Incomplete inference: rerun the same command with --resume")


if __name__ == "__main__":
    main()
