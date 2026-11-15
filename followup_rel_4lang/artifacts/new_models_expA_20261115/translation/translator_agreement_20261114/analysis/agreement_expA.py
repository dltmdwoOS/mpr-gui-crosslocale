"""Exploratory: T-O, R-T, R-O on the translator-agreed pair set vs its complement (and by screen language).
Usage: python agreement_expA.py <model> <predictions> <out_dir> [agreed_pairs.json]
Imports the pre-registered helpers (analysis/analyze_expA.py) unmodified; only the bootstrap seed is set to 20261114 (B=10,000 from the module)."""
import csv, json, sys
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "analysis"))
import analyze_expA as A  # noqa
A.SEED = 20261114

def main():
    model, pred, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    ap = Path(sys.argv[4]) if len(sys.argv) > 4 else HERE.parent / "work/agreed_pairs.json"
    out.mkdir(parents=True, exist_ok=True)
    d = json.loads(ap.read_text())
    agreed, allm = set(d["agreed"]), set(d["all_main"])
    rows = A.load_predictions(pred)
    ok = defaultdict(set)
    for r in rows:
        if r["status"] == "success":
            ok[r["pair_id"]].add(r["condition"])
    complete = {p for p, c in ok.items() if c == set(A.CONDS)}
    rows = [r for r in rows if r["pair_id"] in complete]
    gui = {r["pair_id"]: r["gui_language"] for r in rows}
    base = allm & complete
    sets = {"all_pairs": base, "agreed": agreed & base, "not_agreed": base - agreed}
    for g in ("en", "zh", "th", "ru"):
        sets[f"agreed|screen_{g}"] = {p for p in agreed & base if gui[p] == g}
        sets[f"not_agreed|screen_{g}"] = {p for p in base - agreed if gui[p] == g}
    res = {"model": model, "predictions": str(pred), "label": "EXPLORATORY (not pre-registered)", "seed": A.SEED, "B": A.B, "sets": {}}
    with (out / "agreement_contrasts.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "set", "pairs", "items", "acc_O", "acc_T", "acc_R", "contrast", "pp", "ci_lo", "ci_hi"])
        for name, P in sets.items():
            items, m = A.item_matrix(rows, "generation_correct", P)
            if len(items) < 10:
                continue
            b = A.bootstrap(m)
            acc = 100 * m.mean(axis=0)
            res["sets"][name] = {"pairs": len(P), "items": len(items), "acc": dict(zip(A.CONDS, acc.tolist())),
                                 **{k: b[k] for k in ("T_minus_O", "R_minus_T", "R_minus_O")}}
            for k in ("T_minus_O", "R_minus_T", "R_minus_O"):
                w.writerow([model, name, len(P), len(items), *[round(a, 2) for a in acc], k, round(b[k]["pp"], 3), round(b[k]["lo"], 3), round(b[k]["hi"], 3)])
    (out / "agreement_summary.json").write_text(json.dumps(res, indent=1, default=float))
    print(open(out / "agreement_contrasts.csv").read())

if __name__ == "__main__":
    main()
