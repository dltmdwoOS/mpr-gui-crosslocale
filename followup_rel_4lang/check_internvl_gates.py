"""Automatic gates for the unattended InternVL run: ETA, smoke pass/fail, completion.

  eta        <out>  : estimate full-run hours from preflight.json timings
  smoke      <out>  : pass only if smoke outputs are complete and well-formed
  complete   <out>  : pass only if all three full runs are complete

Thresholds are written in SMOKE_RULES and recorded in the gate output so the
decision is visible later. Exit code 0 = pass, 1 = fail.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

FULL = {"six_by_six": 79020, "rel_inferences": 18432, "rel_rows": 23424, "grounding": 7584}
# Qwen3 pilot for reference: valid O 48/48, R 47/48, C 47/48, F 48/48.
SMOKE_RULES = {
    "six_by_six_unique_success": 216,
    "six_by_six_max_parse_failures": 2,
    "rel_condition_rows": 128,
    "rel_max_parse_failures": 2,
    "grounding_responses": 192,
    "grounding_min_valid_rate_per_condition": 0.85,
    "grounding_max_length_stops": 10,
}


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def last_success(rows: list[dict]) -> dict[str, dict]:
    best = {}
    for row in rows:
        if row.get("status") == "success":
            best[row["input_id"]] = row
    return best


def eta(out: Path) -> dict:
    record = json.loads((out / "preflight.json").read_text())
    mc = [m["seconds"] for m in record["measurements"] if m["case"] != "grounding"]
    ground = [m["seconds"] for m in record["measurements"] if m["case"] == "grounding"]
    # Preflight uses the LONGEST inputs, so these are upper-side estimates;
    # the first call also includes warm-up.
    per_mc = statistics.median(mc)
    per_ground = ground[0] if ground else per_mc * 2
    hours = {
        "six_by_six": FULL["six_by_six"] * per_mc / 3600,
        "rel": FULL["rel_inferences"] * per_mc / 3600,
        "grounding": FULL["grounding"] * per_ground / 3600,
    }
    hours["total"] = sum(hours.values())
    return {"seconds_per_mc_response_median_longest_inputs": per_mc,
            "seconds_per_grounding_response_longest_input": per_ground,
            "estimated_hours": {k: round(v, 1) for k, v in hours.items()},
            "note": "Rough upper-side estimate from 7 preflight calls; excludes model loading."}


def smoke(out: Path) -> dict:
    problems = []
    six = last_success(read_jsonl(out / "smoke_6x6.jsonl")) if (out / "smoke_6x6.jsonl").exists() else {}
    six_parse = sum(1 for r in six.values() if not r.get("parse_success"))
    if len(six) != SMOKE_RULES["six_by_six_unique_success"]:
        problems.append(f"6x6 smoke unique successes {len(six)} != 216")
    if six_parse > SMOKE_RULES["six_by_six_max_parse_failures"]:
        problems.append(f"6x6 smoke parse failures {six_parse}")
    rel = json.loads((out / "smoke_rel/summary.json").read_text()) if (out / "smoke_rel/summary.json").exists() else {}
    if rel.get("condition_rows") != SMOKE_RULES["rel_condition_rows"] or set(rel.get("statuses", {})) != {"success"}:
        problems.append(f"REL smoke incomplete: rows={rel.get('condition_rows')} statuses={rel.get('statuses')}")
    if rel.get("parse_failures", 99) > SMOKE_RULES["rel_max_parse_failures"]:
        problems.append(f"REL smoke parse failures {rel.get('parse_failures')}")
    preds = out / "pilot_orcf/predictions.jsonl"
    ground = read_jsonl(preds) if preds.exists() else []
    if len(ground) != SMOKE_RULES["grounding_responses"]:
        problems.append(f"grounding pilot responses {len(ground)} != 192")
    rates = {}
    for condition in ("O", "R", "C", "F"):
        subset = [r for r in ground if r["condition"] == condition]
        rates[condition] = sum(r["valid_output"] for r in subset) / len(subset) if subset else 0.0
        if rates[condition] < SMOKE_RULES["grounding_min_valid_rate_per_condition"]:
            problems.append(f"grounding {condition} valid rate {rates[condition]:.2f}")
    length_stops = sum(1 for r in ground if r.get("stop_reason") == "length")
    if length_stops > SMOKE_RULES["grounding_max_length_stops"]:
        problems.append(f"grounding length stops {length_stops}")
    invalid_examples = [r["raw_output"] for r in ground if not r["valid_output"]][:5]
    return {"rules": SMOKE_RULES, "six_by_six_unique_success": len(six),
            "six_by_six_parse_failures": six_parse, "rel": {k: rel.get(k) for k in
            ("condition_rows", "statuses", "parse_failures")}, "grounding_valid_rate": rates,
            "grounding_length_stops": length_stops, "grounding_invalid_examples": invalid_examples,
            "problems": problems, "status": "passed" if not problems else "failed"}


def complete(out: Path) -> dict:
    problems = []
    six = last_success(read_jsonl(out / "full_6x6.jsonl")) if (out / "full_6x6.jsonl").exists() else {}
    if len(six) != FULL["six_by_six"]:
        problems.append(f"6x6 unique successes {len(six)} != {FULL['six_by_six']}")
    rel = json.loads((out / "full_rel/summary.json").read_text()) if (out / "full_rel/summary.json").exists() else {}
    if rel.get("condition_rows") != FULL["rel_rows"] or rel.get("actual_successful_inferences") != FULL["rel_inferences"]:
        problems.append(f"REL incomplete: {rel.get('condition_rows')} rows, {rel.get('actual_successful_inferences')} inferences")
    ground = json.loads((out / "grounding_main_orcf/summary.json").read_text()) \
        if (out / "grounding_main_orcf/summary.json").exists() else {}
    if not ground.get("complete") or ground.get("response_count") != FULL["grounding"]:
        problems.append(f"grounding incomplete: {ground.get('response_count')}")
    return {"six_by_six_unique_success": len(six), "rel": {k: rel.get(k) for k in
            ("condition_rows", "actual_successful_inferences", "parse_failures")},
            "grounding": {k: ground.get(k) for k in ("complete", "response_count", "conditions")},
            "problems": problems, "status": "passed" if not problems else "failed"}


def main() -> None:
    mode, out = sys.argv[1], Path(sys.argv[2])
    result = {"eta": eta, "smoke": smoke, "complete": complete}[mode](out)
    (out / f"gate_{mode}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    if result.get("status") == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
