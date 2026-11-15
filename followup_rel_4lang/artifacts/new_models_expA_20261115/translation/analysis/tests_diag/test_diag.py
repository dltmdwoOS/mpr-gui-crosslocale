"""Tests for diag_expA.py, Qwen3 only. Run: python3 -I tests_diag/test_diag.py  (writes nothing outside scratch/tmp dir)."""
import csv, importlib.util, subprocess, sys, tempfile, time, json
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent.parent
EXP = HERE.parent
PRED = EXP.parent / "expA_results_20261114/qwen3/expA_qwen3/full/predictions.jsonl"
CONTRASTS = EXP.parent / "expA_results_20261114/analysis_qwen3/contrasts.csv"
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("diag_expA", HERE / "diag_expA.py")
D = importlib.util.module_from_spec(spec); spec.loader.exec_module(D)
A = D.load_analyze()
df, sets, _ = D.build_pair_table(A, PRED)
fails = []
def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name, info); 
    if not ok: fails.append(name)

# 1. cross-check vs analyze_expA contrasts.csv (item-mean convention)
ref = {}
for r in csv.DictReader(CONTRASTS.open()):
    if r["outcome"] == "generation_correct": ref[(r["set"], r["contrast"])] = float(r["pp"])
chk = {"primary_full": np.ones(len(df), bool), **{f"sub5_gui_{g}": (df.gui == g).to_numpy() for g in D.GUIS}}
mx = 0
for s, m in chk.items():
    est = D.item_mean_contrasts(df, m)
    for k, key in (("T-O", "T_minus_O"), ("R-T", "R_minus_T"), ("R-O", "R_minus_O")):
        mx = max(mx, abs(round(est[k], 3) - ref[(s, key)]))
check("crosscheck vs contrasts.csv (overall + 4 GUI, 3 contrasts)", mx < 1e-3, f"max abs diff pp={mx:.4f}")
# pair-weighted vs item-mean difference (informational)
pw = D.cell_stats(D.mk_boot(df, 10), df[["cO","cT","cR"]].to_numpy(), np.ones(len(df), bool))
print("INFO overall pair-weighted T-O/R-T/R-O:", [round(100*pw[k][0],3) for k in ("T-O","R-T","R-O")])
check("sub1 size 381", len(sets["sub1_zero_screen_match"] & set(df.pair_id)) == 381)

# 2. runtime B=10000 (CLI)
with tempfile.TemporaryDirectory() as td:
    t = time.time()
    subprocess.run([sys.executable, "-I", str(HERE / "diag_expA.py"), "qwen3", str(PRED), td], check=True, capture_output=True)
    el = time.time() - t
    meta = json.load(open(Path(td) / "run_meta.json"))
    check("CLI full run B=10000", meta["B"] == 10000, f"{el:.1f}s wall")
    need = ["confirmatory.json","confirmatory.csv","d1_cells.csv","d1_answer_position.csv","d2_dose_response.csv","d3_zero_match.csv",
            "d4_quality.csv","d5_nearmiss.csv","d5_nearmiss_pair_flags.csv","d7_lost.csv","run_meta.json","d6_cases/judge_sheet_blinded.csv","d6_cases/sample_key_UNBLINDED.csv"]
    check("all outputs exist", all((Path(td)/n).exists() for n in need))
    hdr = open(Path(td)/"d6_cases/judge_sheet_blinded.csv", encoding="utf-8").readline()
    check("blinded sheet has no group/model-answer columns", all(w not in hdr for w in ("group","gold","label","correct","gui","query")), hdr.strip())

# 3. synthetic: shuffle conditions within pair -> P1 ~ 0
Bq = 1000
cover, ests = 0, []
rng = np.random.default_rng(1)
for rep in range(20):
    d2 = df.copy()
    M = d2[["cO","cT","cR"]].to_numpy()
    for i in range(len(M)): M[i] = M[i][rng.permutation(3)]
    d2[["cO","cT","cR"]] = M
    r = D.confirmatory(d2, D.mk_boot(d2, Bq, 100 + rep))["results"]["P1"]
    ests.append(r["est_pp"]); cover += r["ci95_lo_pp"] <= 0 <= r["ci95_hi_pp"]
check("shuffled conditions: P1 near 0", abs(np.mean(ests)) < 2 and cover >= 17, f"mean est={np.mean(ests):.2f}pp sd={np.std(ests):.2f}, CI covers 0 in {cover}/20")
# planted effect
d3 = df.copy(); th = (d3.gui == "th").to_numpy()
r3 = np.random.default_rng(2)
d3["cO"] = (r3.random(len(d3)) < 0.6).astype(float)
d3["cT"] = np.where(th, (r3.random(len(d3)) < 0.8), (r3.random(len(d3)) < 0.5)).astype(float)
d3["cR"] = d3["cT"]
c = D.confirmatory(d3, D.mk_boot(d3, 2000))
check("planted effect: P1-P3 rejected", all(c["results"][k]["reject"] for k in ("P1","P2","P3")), c["interpretation_code"])
# D2 slope recovery
d4 = df.copy(); r4 = np.random.default_rng(3)
d4["cO"] = 0.0; d4["cT"] = (r4.random(len(d4)) < 0.2 + 0.6 * d4.d_exact.clip(0,1)).astype(float)
rows = D.d2(d4, D.mk_boot(d4, 500))
sl = [r for r in rows if r["model"] == "pooled_d_exact" and r["term"] == "d_exact"][0]
check("D2 recovers planted slope 0.6", sl["ci_lo"] < 0.6 < sl["ci_hi"], f"coef={sl['coef']:.3f} [{sl['ci_lo']:.3f},{sl['ci_hi']:.3f}]")
print("FAILED:" if fails else "ALL PASSED", fails)
sys.exit(1 if fails else 0)
