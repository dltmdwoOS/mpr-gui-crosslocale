"""REL R_stem / R_opts multiple-choice inference, with same-run O and R anchors.

The 2x2 design separates the referent string in the question stem from the
referent strings in the A-D options:

    O       source stem + source options     (re-run anchor)
    R_stem  GUI stem    + source options     (new)
    R_opts  source stem + GUI options        (new)
    R       GUI stem    + GUI options        (re-run anchor)

Inputs come from the locked generator (grounding_eval/build_protocol_inputs.py,
schema rel-grounding-protocol-inputs-v3). Before any inference this script checks
that every mixed row is an exact recombination of the frozen O and R rows of the
same pair (same image, gold answer and option order), so only the referent strings
differ between conditions.

The four conditions of one pair are queued next to each other, so with batch size 4
each model batch holds exactly one pair: same screenshot, same batch companions.

Model loading, prompting, batching, parsing, label scoring and the resumable cache
are imported unchanged from run_rel_followup.py, so the prompt and decoding match
the 2026-11-07 Qwen3 O/R/C/F run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import chain
from pathlib import Path
from types import SimpleNamespace
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "01_code/src"))

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

CONDITIONS = ("O", "R_stem", "R_opts", "R")
INPUT_DIR = HERE / "rstem_ropts_inputs"
LOCK = INPUT_DIR / "input_lock.json"  # copy of grounding_eval/input_lock.json (schema v3)
EXPECTED_DATASET_SHA256 = "e5aa6cd0c426cc648322c8c7702b1b6985fddb09ad895d70a85d86c6a3de38ce"
EXPECTED_ROWS = {"main": 3792, "pilot": 96}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(stem: str, options: dict) -> str:
    return stem + " " + " ".join(f"{k}: {options[k]}" for k in "ABCD")


def input_id(pair_id: str, condition: str) -> str:
    return f"rel_mix::{pair_id}::{condition}"


def load_rows(data_root: Path, split: str, max_items: int | None, check_images: bool):
    mixed_path = INPUT_DIR / "mixed_conditions.jsonl"
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    if sha256_file(mixed_path) != lock["generated_sha256"]["mixed_conditions.jsonl"]:
        raise ValueError("mixed_conditions.jsonl differs from the tracked input lock")
    mixed = [json.loads(line) for line in mixed_path.read_text(encoding="utf-8").splitlines() if line]
    counts = Counter(r["split"] for r in mixed)
    if dict(counts) != EXPECTED_ROWS:
        raise ValueError(f"Unexpected mixed row counts {dict(counts)}")

    frozen, audit = validate_dataset(data_root, images=check_images)
    if audit["conditions_sha256"] != EXPECTED_DATASET_SHA256:
        raise ValueError("Frozen REL dataset differs from the 2026-11-07 Qwen3 run")
    by_key = {(r["pair_id"], r["condition"]): r for r in frozen}

    pairs = defaultdict(dict)
    for m in mixed:
        if split != "all" and m["split"] != split:
            continue
        o, r = by_key[(m["pair_id"], "O")], by_key[(m["pair_id"], "R")]
        image = m["image_path"].removeprefix("followup_rel_4lang/")
        if image != o["image_path"] or image != r["image_path"]:
            raise ValueError(f"Image differs from frozen O/R: {m['pair_id']}")
        if not (m["gold_answer"] == o["gold_answer"] == r["gold_answer"]):
            raise ValueError(f"Gold differs: {m['pair_id']}")
        if o["question"] != render(o["question_stem"], o["options"]) or \
                r["question"] != render(r["question_stem"], r["options"]):
            raise ValueError(f"Frozen question is not stem+options: {m['pair_id']}")
        want = ((r["question_stem"], o["options"]) if m["condition"] == "R_stem"
                else (o["question_stem"], r["options"]))
        if (m["question_stem"], m["options"]) != want or m["question"] != render(*want):
            raise ValueError(f"Not an exact O/R recombination: {m['pair_id']} {m['condition']}")
        if m["question"] in (o["question"], r["question"]):
            raise ValueError(f"Mixed question equals O or R: {m['pair_id']} {m['condition']}")
        if check_images and sha256_file(data_root / image) != m["image_sha256"]:
            raise ValueError(f"Image hash mismatch: {image}")
        base = {"pair_id": m["pair_id"], "parallel_id": m["parallel_id"], "split": m["split"],
                "query_language": m["query_language"], "gui_language": m["gui_language"],
                "image_path": image, "gold_answer": m["gold_answer"],
                "text_dependency": o["text_dependency"]}
        pairs[m["pair_id"]][m["condition"]] = {**base, "condition": m["condition"],
                                               "question": m["question"]}
        pairs[m["pair_id"]]["O"] = {**base, "condition": "O", "question": o["question"]}
        pairs[m["pair_id"]]["R"] = {**base, "condition": "R", "question": r["question"]}

    pair_ids = sorted(pairs)
    if max_items is not None:
        keep = sorted({pairs[p]["O"]["parallel_id"] for p in pair_ids})[:max_items]
        pair_ids = [p for p in pair_ids if pairs[p]["O"]["parallel_id"] in keep]
    rows = []
    for pid in pair_ids:
        if set(pairs[pid]) != set(CONDITIONS):
            raise ValueError(f"Pair lacks a condition: {pid}")
        rows.extend(pairs[pid][c] for c in CONDITIONS)
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
    data_root = args.data_root.resolve()
    rows, audit = load_rows(data_root, args.split, args.max_items,
                            check_images=not (args.dry_run or args.mock_model))
    config = load_yaml(args.model_config)
    if config.get("model_family") != "qwen3_vl" or config.get("prompt_profile") != "mpr_label_only_v1":
        raise ValueError("Use the pinned Qwen3-VL config with mpr_label_only_v1")
    gen = config["generation"]
    if config.get("dtype") != "bfloat16" or config.get("quantization") is not None or \
            gen.get("do_sample") is not False or gen.get("num_beams") != 1 or gen.get("max_new_tokens") != 2:
        raise ValueError("Use unquantized bfloat16 greedy decoding with max_new_tokens=2")
    system_prompt, _, template = build_system_prompt("english_fixed", "en")
    mode = "mock" if args.mock_model else "gpu"
    identity = {
        "schema": "rel-rstem-ropts-v1",
        "conditions": list(CONDITIONS),
        "dataset_sha256": audit["conditions_sha256"],
        "mixed_inputs_sha256": sha256_file(INPUT_DIR / "mixed_conditions.jsonl"),
        "model_config": config, "execution_mode": mode,
        "system_prompt": system_prompt, "prompt_template_version": template,
        "score_labels": True, "batch_size": args.batch_size,
        "strict_batch_size": args.strict_batch_size,
        "queue_order": "pair_id sorted; O, R_stem, R_opts, R adjacent",
        "split": args.split, "max_items": args.max_items,
        "selected_input_ids_sha256": stable_hash([input_id(r["pair_id"], r["condition"]) for r in rows]),
        "code_sha256": {**code_identity(), "run_rel_mixed.py": sha256_file(Path(__file__))},
        "software_versions": software_versions(),
    }
    fingerprint = stable_hash(identity)
    plan = {"pairs": len(rows) // 4, "items": len({r["parallel_id"] for r in rows}),
            "inferences": len(rows), "batch_size": args.batch_size,
            "by_condition": dict(Counter(r["condition"] for r in rows)),
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
    # Keep "one batch = one pair" across resumes: if any condition of a pair is not yet
    # successful, re-run all four conditions of that pair together.
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
                                 data_root=data_root, strict_batch_size=args.strict_batch_size)
    versions, commit, failures = software_versions(), git_commit(), 0
    from tqdm import tqdm
    try:
        progress = tqdm(total=len(pending), desc=f"REL R_stem/R_opts ({mode}, batch={args.batch_size})")
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
    parser.add_argument("--data-root", type=Path, default=Path("followup_rel_4lang"))
    parser.add_argument("--model-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--split", choices=("main", "pilot", "all"), default="main")
    parser.add_argument("--max-items", type=int, help="Keep only the first N items (smoke test)")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--strict-batch-size", action="store_true")
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
