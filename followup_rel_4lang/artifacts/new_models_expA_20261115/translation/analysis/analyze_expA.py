"""Pre-registered analysis of Experiment A (see ../DESIGN_ANALYSIS_PLAN_KO.md). Written before any GPU result.

Usage: python analyze_expA.py <model> <predictions.jsonl[.gz]> <out_dir>
Writes contrasts.csv (every analysis set), summary.json, glmm_rows.csv.
Unit of resampling: item (parallel_id). Item score = mean over its remaining pairs.
"""
from __future__ import annotations

import csv
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
WORK = HERE.parent / "work"
CONDS = ("O", "T", "R")
SEED, B = 20261113, 10_000
EXCLUDED = {"rel::5/forest_9.jpg::zh::ru"}  # T options not distinct (pre-registered)
SIM_MIN = 0.7


def load_predictions(path: Path) -> list[dict]:
    text = gzip.open(path, "rt", encoding="utf-8").read() if path.suffix == ".gz" else path.read_text(encoding="utf-8")
    rows = {}
    for line in text.splitlines():
        if line.strip():
            r = json.loads(line)
            rows[r["input_id"]] = r
    return [r for r in rows.values() if r["split"] == "main"]


def pair_sets() -> dict[str, set]:
    spans = [json.loads(l) for l in (WORK / "T_gemma_first_spans.jsonl").open(encoding="utf-8")]
    sim = {(r["pair_id"], r["field"], r["ref_id"]): r for r in map(json.loads, (WORK / "T_gemma_first_similarity.jsonl").open(encoding="utf-8"))}
    aff = json.loads((WORK / "mapping_audit_affected_pairs.json").read_text())
    artifact_refs = {(r["parallel_id"], r["ref_id"]) for r in csv.DictReader((WORK / "mapping_audit_review.csv").open(encoding="utf-8-sig"))
                     if r["verdict"] == "annotation_artifact"}
    by = defaultdict(list)
    for s in spans:
        if s["split"] == "main":
            by[s["pair_id"]].append(s)
    allp = set(by) - EXCLUDED
    frac = {p: sum(s["match"] != "different" for s in by[p]) / len(by[p]) for p in allp}
    screen_names = {p: {s["screen_text"] for s in by[p]} for p in allp}
    S = {
        "primary_full": allp,
        "audited_drop_mapping_error": allp - set(aff["mapping_error"]),
        "audited_drop_error_uncertain": allp - set(aff["mapping_error"]) - set(aff["uncertain"]),
        "sub1_zero_screen_match": {p for p in allp if frac[p] == 0},
        "sub2_meaning_preserved": {p for p in allp if any(s["match"] == "different" for s in by[p]) and
                                   all(sim[(s["pair_id"], s["field"], s["ref_id"])]["sim_T_screen"] >= SIM_MIN
                                       for s in by[p] if s["match"] == "different")},
        "sub3_stem_name_different": {p for p in allp if any(s["match"] == "different" and s["field"] == "question_stem" for s in by[p])},
        "sub4_frac_0": {p for p in allp if frac[p] == 0},
        "sub4_frac_0_to_half": {p for p in allp if 0 < frac[p] < 0.5},
        "sub4_frac_half_to_1": {p for p in allp if 0.5 <= frac[p] < 1},
        "sub4_frac_1": {p for p in allp if frac[p] == 1},
        "sens_drop_annotation_artifact": {p for p in allp if not any((s["parallel_id"], s["ref_id"]) in artifact_refs for s in by[p])},
        "sens_drop_digit_mismatch": {p for p in allp if all(re.findall(r"\d+", s["source_text"]) == re.findall(r"\d+", s["screen_text"]) for s in by[p])},
        "sens_drop_untranslated": {p for p in allp if not any(s["untranslated"] for s in by[p])},
        "sens_drop_translation_equals_other_screen_name": {p for p in allp if not any(
            s["translation"] in screen_names[p] and s["translation"] != s["screen_text"] for s in by[p])},
    }
    for g in ("en", "zh", "th", "ru"):
        S[f"sub5_gui_{g}"] = {p for p in allp if by[p][0]["gui_language"] == g}
    return S


def item_matrix(rows, outcome, pairs):
    acc = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["pair_id"] in pairs:
            acc[r["parallel_id"]][r["condition"]].append(float(bool(r[outcome])))
    items = sorted(acc)
    return items, np.array([[np.mean(acc[i][c]) for c in CONDS] for i in items])


def contrasts(m):
    o, t, r = m[..., 0], m[..., 1], m[..., 2]
    return {"T_minus_O": t - o, "R_minus_T": r - t, "R_minus_O": r - o, "TO_minus_RT": (t - o) - (r - t)}


def bootstrap(m):
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(m), size=(B, len(m)))
    point = {k: v.mean() for k, v in contrasts(m).items()}
    draws = {k: v.mean(axis=1) for k, v in contrasts(m[idx]).items()}
    out = {}
    for k, d in draws.items():
        d = np.round(d, 12)
        out[k] = {"pp": 100 * point[k], "lo": 100 * np.percentile(d, 2.5), "hi": 100 * np.percentile(d, 97.5),
                  "p_boot": min(1.0, 2 * min((1 + (d <= 0).sum()) / (B + 1), (1 + (d >= 0).sum()) / (B + 1)))}
    order = sorted(("T_minus_O", "R_minus_T"), key=lambda k: out[k]["p_boot"])
    run = 0.0
    for rank, k in enumerate(order):
        run = max(run, min(1.0, (2 - rank) * out[k]["p_boot"]))
        out[k]["p_holm_primary2"] = run
    out["corr_TO_RT_boot"] = float(np.corrcoef(draws["T_minus_O"], draws["R_minus_T"])[0, 1])
    ro = draws["R_minus_O"]
    if out["R_minus_O"]["lo"] > 0:
        ratio = draws["T_minus_O"] / ro
        out["recovery_ratio_TO_over_RO"] = {"est": point["T_minus_O"] / point["R_minus_O"],
                                            "lo": float(np.percentile(ratio, 2.5)), "hi": float(np.percentile(ratio, 97.5))}
    return out


def main():
    model, pred, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    rows = load_predictions(pred)
    ok = defaultdict(set)
    for r in rows:
        if r["status"] == "success":
            ok[r["pair_id"]].add(r["condition"])
    complete = {p for p, c in ok.items() if c == set(CONDS)}
    if len(complete) != 1896:
        print(f"WARNING: {len(complete)} complete main pairs (expected 1896)", file=sys.stderr)
    rows = [r for r in rows if r["pair_id"] in complete]
    sets = pair_sets()
    summary = {"model": model, "predictions": str(pred), "seed": SEED, "B": B, "sets": {}}
    with (out / "contrasts.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "set", "outcome", "pairs", "items", "acc_O", "acc_T", "acc_R", "contrast", "pp", "ci_lo", "ci_hi",
                    "p_boot", "p_holm_primary2"])
        for name, P in sets.items():
            P = P & complete
            for outcome in (("generation_correct", "scoring_correct") if name == "primary_full" else ("generation_correct",)):
                items, m = item_matrix(rows, outcome, P)
                if len(items) < 10:
                    continue
                res = bootstrap(m)
                acc = 100 * m.mean(axis=0)
                summary["sets"][f"{name}|{outcome}"] = {"pairs": len(P), "items": len(items), "acc": dict(zip(CONDS, acc.tolist())), **res}
                for k in ("T_minus_O", "R_minus_T", "R_minus_O", "TO_minus_RT"):
                    v = res[k]
                    w.writerow([model, name, outcome, len(P), len(items), *[round(a, 2) for a in acc], k, round(v["pp"], 3),
                                round(v["lo"], 3), round(v["hi"], 3), round(v["p_boot"], 5),
                                round(v["p_holm_primary2"], 5) if "p_holm_primary2" in v else ""])
    with (out / "glmm_rows.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["correct", "condition", "item", "pair", "query_language", "gui_language"])
        for r in rows:
            if r["pair_id"] in sets["primary_full"]:
                w.writerow([int(bool(r["generation_correct"])), r["condition"], r["parallel_id"], r["pair_id"],
                            r["query_language"], r["gui_language"]])
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=float) + "\n")
    p = summary["sets"]["primary_full|generation_correct"]
    print(json.dumps({k: p[k] for k in ("pairs", "items", "acc", "T_minus_O", "R_minus_T", "R_minus_O", "corr_TO_RT_boot")}, indent=1, default=float))


if __name__ == "__main__":
    main()
