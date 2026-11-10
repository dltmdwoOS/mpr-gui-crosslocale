"""Pre-registered analysis of the R_stem / R_opts run (see ANALYSIS_PLAN_KO.md).

Usage: python analyze_rstem.py <predictions.jsonl[.gz]> <reference_OR.jsonl[.gz]> <out_dir>
Writes contrasts.csv, by_gui.csv, glmm_rows.csv, summary.json (including reproducibility).
"""
from __future__ import annotations

import csv
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

CONDS = ("O", "R_stem", "R_opts", "R")
SEED, B = 20261109, 10_000


def read_text(path: Path) -> str:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return stream.read()


def load(path: Path) -> list[dict]:
    rows = {}
    for line in read_text(path).splitlines():
        if line.strip():
            r = json.loads(line)
            rows[r["input_id"]] = r
    return [r for r in rows.values() if r.get("split", "main") == "main"]


def contrasts(m: np.ndarray) -> dict:
    """m: items x 4 matrix of item-mean accuracy in CONDS order."""
    o, s, p, r = (m[:, k] for k in range(4))
    return {
        "R_minus_O": r - o,
        "Rstem_minus_O": s - o,
        "Ropts_minus_O": p - o,
        "stem_effect_S": ((s - o) + (r - p)) / 2,
        "option_effect_P": ((p - o) + (r - s)) / 2,
        "interaction_I": r - s - p + o,
        "S_minus_P": ((s - o) + (r - p)) / 2 - ((p - o) + (r - s)) / 2,
    }


def item_matrix(rows: list[dict], outcome: str, subset=None):
    acc = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["status"] != "success" or (subset and not subset(r)):
            continue
        acc[r["parallel_id"]][r["condition"]].append(float(bool(r[outcome])))
    items = sorted(acc)
    for i in items:
        if set(acc[i]) != set(CONDS):
            raise ValueError(f"Item {i} lacks a condition")
    return items, np.array([[np.mean(acc[i][c]) for c in CONDS] for i in items])


def bootstrap(m: np.ndarray) -> dict:
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(m), size=(B, len(m)))
    point = {k: v.mean() for k, v in contrasts(m).items()}
    draws = {k: np.empty(B) for k in point}
    for b in range(B):
        for k, v in contrasts(m[idx[b]]).items():
            draws[k][b] = v.mean()
    out = {}
    for k, d in draws.items():
        d = np.round(d, 12)  # remove float noise around exact zeros
        p_two = 2 * min((d <= 0).mean(), (d >= 0).mean())
        out[k] = {"pp": 100 * point[k], "lo": 100 * np.percentile(d, 2.5),
                  "hi": 100 * np.percentile(d, 97.5), "p_boot": min(1.0, p_two)}
    primary = ["stem_effect_S", "option_effect_P", "interaction_I"]
    order = sorted(primary, key=lambda k: out[k]["p_boot"])
    running = 0.0
    for rank, k in enumerate(order):
        running = max(running, min(1.0, (len(order) - rank) * out[k]["p_boot"]))
        out[k]["p_holm"] = running
    return out


def reproducibility(rows: list[dict], ref_path: Path) -> dict:
    ref = {}
    for line in read_text(ref_path).splitlines():
        x = json.loads(line)
        ref[(x["pair_id"], x["condition"])] = x
    res = {}
    for c in ("O", "R"):
        new = [r for r in rows if r["condition"] == c and r["status"] == "success"]
        same = sum(r["parsed_generated_label"] == ref[(r["pair_id"], c)]["parsed_generated_label"] for r in new)
        res[c] = {"n": len(new), "label_agreement": same / len(new),
                  "acc_new": np.mean([bool(r["generation_correct"]) for r in new]),
                  "acc_reference": np.mean([bool(ref[(r["pair_id"], c)]["generation_correct"]) for r in new])}
    res["R_minus_O_pp_new"] = 100 * (res["R"]["acc_new"] - res["O"]["acc_new"])
    res["R_minus_O_pp_reference"] = 100 * (res["R"]["acc_reference"] - res["O"]["acc_reference"])
    return res


def main() -> None:
    pred, ref, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    rows = load(pred)
    ok = defaultdict(set)
    for r in rows:
        if r["status"] == "success":
            ok[r["pair_id"]].add(r["condition"])
    complete_pairs = {p for p, c in ok.items() if c == set(CONDS)}
    dropped = len({r["pair_id"] for r in rows}) - len(complete_pairs)
    if dropped:
        print(f"WARNING: dropping {dropped} incomplete pairs", file=sys.stderr)
    rows = [r for r in rows if r["pair_id"] in complete_pairs]
    if len(rows) != 7584 or any(r["status"] != "success" for r in rows):
        print(f"WARNING: {len(rows)} main rows, not all successful", file=sys.stderr)
    summary = {}
    with (out / "contrasts.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["outcome", "contrast", "pp", "ci95_lo", "ci95_hi", "p_boot", "p_holm_primary3", "items"])
        for outcome in ("generation_correct", "scoring_correct"):
            items, m = item_matrix(rows, outcome)
            res = bootstrap(m)
            summary[outcome] = {"items": len(items),
                                "accuracy_pct": {c: 100 * m[:, k].mean() for k, c in enumerate(CONDS)},
                                "contrasts": res}
            for k, v in res.items():
                w.writerow([outcome, k, round(v["pp"], 3), round(v["lo"], 3), round(v["hi"], 3),
                            round(v["p_boot"], 5), round(v["p_holm"], 5) if "p_holm" in v else "", len(items)])
    with (out / "by_gui.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["gui_language", "contrast", "pp", "ci95_lo", "ci95_hi", "items"])
        for g in ("en", "zh", "th", "ru"):
            items, m = item_matrix(rows, "generation_correct", lambda r, g=g: r["gui_language"] == g)
            boot = bootstrap(m)
            for k in ("stem_effect_S", "option_effect_P", "interaction_I", "R_minus_O"):
                v = boot[k]
                w.writerow([g, k, round(v["pp"], 3), round(v["lo"], 3), round(v["hi"], 3), len(items)])
    summary["reproducibility"] = reproducibility(rows, ref)
    with (out / "glmm_rows.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["correct", "scoring_correct", "condition", "stem_gui", "opts_gui",
                    "item", "pair", "query_language", "gui_language"])
        for r in rows:
            w.writerow([int(bool(r["generation_correct"])), int(bool(r["scoring_correct"])), r["condition"],
                        int(r["condition"] in ("R_stem", "R")), int(r["condition"] in ("R_opts", "R")),
                        r["parallel_id"], r["pair_id"], r["query_language"], r["gui_language"]])
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    print(json.dumps({k: summary["generation_correct"]["contrasts"][k] for k in
                      ("stem_effect_S", "option_effect_P", "interaction_I", "S_minus_P")}, indent=1, default=float))
    print(json.dumps(summary["reproducibility"], indent=1, default=float))


if __name__ == "__main__":
    main()
