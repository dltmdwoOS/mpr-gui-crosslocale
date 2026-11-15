"""Gates for the Experiment A run (O, T, R).

  python check_T_gate.py <qwen3|internvl35> smoke    <out_dir>
  python check_T_gate.py <qwen3|internvl35> complete <out_dir>

smoke    : stop unless the 3-item run is complete, parses, batches are as planned, and the
           re-run O/R answers agree with the earlier run of the same model
complete : stop unless all 5,688 main rows succeeded; report anchor agreement
Also reported (not a gate): answer agreement of T and R on pairs where the T question equals
the R question (same input in the same run; differences would be batch-level numerical noise).
Exit 0 = pass, 1 = fail. Result in gate_<mode>.json.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REL = Path(__file__).resolve().parent.parent
RULES = {
    "qwen3": {"reference": "rstem_ropts_inputs/reference_qwen3_20261107_OR.jsonl", "smoke_min_anchor_agreement": 0.90},
    "internvl35": {"reference": "rstem_ropts_inputs/reference_internvl35_20261109_OR.jsonl", "smoke_min_anchor_agreement": 0.97},
}
COMMON = {"smoke_max_parse_failures": 2, "complete_rows": 5688, "complete_max_parse_failures": 20}


def load(out: Path) -> list[dict]:
    rows = {}
    for line in (out / "predictions.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["input_id"]] = row
    return list(rows.values())


def anchor_agreement(rows: list[dict], ref_path: Path) -> dict:
    ref = {}
    for line in ref_path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        ref[(r["pair_id"], r["condition"])] = r
    same = total = 0
    by_condition = Counter()
    for row in rows:
        if row["condition"] not in ("O", "R") or row.get("status") != "success":
            continue
        old = ref[(row["pair_id"], row["condition"])]
        if row["rendered_prompt"].find(old["question"]) < 0:
            raise ValueError(f"Anchor question text differs from the earlier run: {row['input_id']}")
        total += 1
        agree = row["parsed_generated_label"] == old["parsed_generated_label"]
        same += agree
        by_condition[(row["condition"], agree)] += 1
    return {"anchor_rows": total, "label_agreement": round(same / total, 4) if total else None,
            "by_condition": {f"{c}/{'same' if a else 'diff'}": n for (c, a), n in sorted(by_condition.items())}}


def t_equals_r_agreement(rows: list[dict]) -> dict:
    by_pair = {}
    for r in rows:
        if r.get("status") == "success":
            by_pair.setdefault(r["pair_id"], {})[r["condition"]] = r
    n = same = 0
    for c in by_pair.values():
        if "T" in c and "R" in c and c["T"]["rendered_prompt"] == c["R"]["rendered_prompt"]:
            n += 1
            same += c["T"]["parsed_generated_label"] == c["R"]["parsed_generated_label"]
    return {"pairs_T_equals_R": n, "same_answer": same}


def software_vs_earlier(out: Path, model: str) -> dict:
    """Report (not a gate) package versions of this run against the earlier run contract of the model."""
    contract = {"qwen3": "rstem_ropts_inputs/run_contract_qwen3_rel_20261107.json",
                "internvl35": "rstem_ropts_inputs/run_contract_internvl35_rel_20261109.json"}[model]
    old = json.loads((REL / contract).read_text(encoding="utf-8"))["software_versions"]
    now = json.loads((out / "run_contract.json").read_text(encoding="utf-8"))["software_versions"]
    diff = {k: [old.get(k), now.get(k)] for k in sorted(set(old) | set(now)) if k != "platform" and old.get(k) != now.get(k)}
    return {"differences_except_platform": diff}


def main() -> None:
    model, mode, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    rule = RULES[model]
    rows = load(out)
    statuses = Counter(r.get("status") for r in rows)
    parse_failures = sum(1 for r in rows if r.get("status") == "success" and not r["parse_success"])
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    agreement = anchor_agreement(rows, REL / rule["reference"])
    problems = []
    batches = {}
    for r in rows:
        if r.get("status") == "success":
            batches.setdefault(r["batch_id"], []).append((r["pair_id"], r["condition"]))
    if model == "qwen3":
        misaligned = sum(1 for b in batches.values()
                         if len({p for p, _ in b}) != 1 or sorted(c for _, c in b) != ["O", "R", "T"])
        if misaligned:
            problems.append(f"{misaligned} batches are not exactly one pair's O, T, R")
    else:
        misaligned = sum(1 for b in batches.values() if len(b) != 1)
        if misaligned:
            problems.append(f"{misaligned} batches hold more than one input (expected batch size 1)")
    if not summary.get("complete"):
        problems.append(f"incomplete: {summary.get('statuses')}")
    if mode == "smoke":
        if parse_failures > COMMON["smoke_max_parse_failures"]:
            problems.append(f"parse failures {parse_failures}")
        if (agreement["label_agreement"] or 0) < rule["smoke_min_anchor_agreement"]:
            problems.append(f"anchor agreement {agreement['label_agreement']} below threshold")
    elif mode == "complete":
        if len(rows) != COMMON["complete_rows"]:
            problems.append(f"rows {len(rows)} != {COMMON['complete_rows']}")
        if parse_failures > COMMON["complete_max_parse_failures"]:
            problems.append(f"parse failures {parse_failures}")
    else:
        raise SystemExit("Use smoke or complete")
    result = {"model": model, "rules": {**rule, **COMMON}, "rows": len(rows), "statuses": dict(statuses),
              "parse_failures": parse_failures, "misaligned_batches": misaligned,
              "accuracy": summary.get("accuracy"), "anchor_vs_earlier_run": agreement,
              "T_equals_R_same_input_check": t_equals_r_agreement(rows),
              "software_versions_vs_earlier_run": software_vs_earlier(out, model),
              "note_anchor_below_0_99": (agreement["label_agreement"] or 0) < 0.99,
              "problems": problems, "status": "passed" if not problems else "failed"}
    (out / f"gate_{mode}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
