"""Gates for the InternVL3.5 R_stem / R_opts run (batch size 1).

  smoke    <out_dir> : stop unless the smoke run is complete, parses, and its O/R anchors
                       reproduce the 2026-11-09 InternVL3.5 answers closely enough
  complete <out_dir> : stop unless all 7,584 main rows succeeded; report anchor agreement

Thresholds are in RULES and are written into gate_<mode>.json. Exit 0 = pass, 1 = fail.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFERENCE = HERE / "rstem_ropts_inputs/reference_internvl35_20261109_OR.jsonl"
RULES = {
    "smoke_max_parse_failures": 2,
    "smoke_min_anchor_label_agreement": 0.97,  # batch 1, same code: expect ~100%
    "complete_rows": 7584,
    "complete_max_parse_failures": 20,
}


def load(out: Path) -> list[dict]:
    rows = {}
    for line in (out / "predictions.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["input_id"]] = row
    return list(rows.values())


def anchor_agreement(rows: list[dict]) -> dict:
    ref = {}
    for line in REFERENCE.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        ref[(r["pair_id"], r["condition"])] = r
    same = total = 0
    by_condition = Counter()
    changed_correct = Counter()
    for row in rows:
        if row["condition"] not in ("O", "R") or row.get("status") != "success":
            continue
        old = ref[(row["pair_id"], row["condition"])]
        if row["rendered_prompt"].find(old["question"]) < 0:
            raise ValueError(f"Anchor question text differs from 2026-11-09 run: {row['input_id']}")
        total += 1
        agree = row["parsed_generated_label"] == old["parsed_generated_label"]
        same += agree
        by_condition[(row["condition"], agree)] += 1
        if not agree:
            changed_correct[(bool(old["generation_correct"]), bool(row["generation_correct"]))] += 1
    return {"anchor_rows": total, "label_agreement": round(same / total, 4) if total else None,
            "by_condition": {f"{c}/{'same' if a else 'diff'}": n for (c, a), n in sorted(by_condition.items())},
            "disagreements_old_correct_to_new_correct": {f"{o}->{n}": k for (o, n), k in changed_correct.items()}}


def main() -> None:
    mode, out = sys.argv[1], Path(sys.argv[2])
    rows = load(out)
    statuses = Counter(r.get("status") for r in rows)
    parse_failures = sum(1 for r in rows if r.get("status") == "success" and not r["parse_success"])
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    agreement = anchor_agreement(rows)
    problems = []
    batches = {}
    for r in rows:
        if r.get("status") == "success":
            batches.setdefault(r["batch_id"], []).append((r["pair_id"], r["condition"]))
    misaligned = sum(1 for b in batches.values() if len(b) != 1)
    if misaligned:
        problems.append(f"{misaligned} batches hold more than one input (expected batch size 1)")
    if not summary.get("complete"):
        problems.append(f"incomplete: {summary.get('statuses')}")
    if mode == "smoke":
        if parse_failures > RULES["smoke_max_parse_failures"]:
            problems.append(f"parse failures {parse_failures}")
        if (agreement["label_agreement"] or 0) < RULES["smoke_min_anchor_label_agreement"]:
            problems.append(f"anchor agreement {agreement['label_agreement']} below threshold")
    elif mode == "complete":
        if len(rows) != RULES["complete_rows"]:
            problems.append(f"rows {len(rows)} != {RULES['complete_rows']}")
        if parse_failures > RULES["complete_max_parse_failures"]:
            problems.append(f"parse failures {parse_failures}")
    else:
        raise SystemExit("Use smoke or complete")
    result = {"rules": RULES, "rows": len(rows), "statuses": dict(statuses),
              "parse_failures": parse_failures, "misaligned_batches": misaligned,
              "accuracy": summary.get("accuracy"),
              "anchor_vs_20261109": agreement, "problems": problems,
              "status": "passed" if not problems else "failed"}
    (out / f"gate_{mode}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
