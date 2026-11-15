#!/usr/bin/env python3
"""Frozen-rule analysis driver for new models (rules: paper_plan_20261112/분석규칙_v1.md).

Usage: python3 run_frozen_analysis.py <model_key> <unpacked_dir> <out_dir> [--no-context] [--skip-diag]

<unpacked_dir> = the folder holding rel_full/ and expa_full/ (e.g. .../unpacked/sizes_qwen3_vl_4b).
Reuses, never edits:
  - prepare_glmm_qwen3.py (project_row, quartet_table, validate_summary)  -> REL quartet construction/exclusions
  - analyze_expA.py (load_predictions, pair_sets, item_matrix, bootstrap)  -> Exp A primary analysis
  - diag_expA.py (run as a subprocess)                                      -> Exp A diagnostics (label: descriptive)
REL bootstrap/Holm = logic of analysis_plan_followup/scripts/t1_holm.py (that file has hard-coded paths, so the
~10 lines are copied), with the p-value written in the rules (1+count)/(B+1).
GLMM Wald sensitivity needs R (Rscript); if absent it is skipped and said so (no substitute).
"""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True
import csv, hashlib, importlib.util, json, shutil, subprocess, statistics
from collections import defaultdict, Counter
from pathlib import Path
import numpy as np

BASE = Path("/Users/baegihyeon/Desktop/CUAI/CUAI_하계 컨퍼런스")
RULES = BASE / "paper_plan_20261112/분석규칙_v1.md"
RULES_FROZEN = BASE / "paper_plan_20261112/분석규칙_v1.FROZEN.txt"
EXPA_DIR = BASE / "expA_translation_20261112"
ANALYZE = EXPA_DIR / "analysis/analyze_expA.py"
DIAG = EXPA_DIR / "analysis/diag_expA.py"
DIAG_FROZEN = EXPA_DIR / "DIAGNOSTIC_PLAN_THAI_KO.FROZEN.txt"
PREP = BASE / "analysis_qwen3_20261108/rel4/prepare_glmm_qwen3.py"
HOLM_REF = BASE / "analysis_plan_followup/scripts/t1_holm.py"
CONTEXT = {  # 8B reference runs (context only)
    "Qwen3-VL-8B": dict(rel=BASE / "analysis_qwen3_20261108/raw/full_rel_results.jsonl",
                        expa=BASE / "expA_results_20261114/qwen3/expA_qwen3/full/predictions.jsonl"),
    "InternVL3.5-8B": dict(rel=BASE / "internvl35_prep/results_internvl35_20261109/full_rel/results.jsonl",
                           expa=BASE / "expA_results_20261114/internvl35/expA_internvl35/full/predictions.jsonl"),
}
B_REL, SEED_REL = 10_000, 42
REL_CON = ["R_minus_O", "C_minus_O", "F_minus_C", "F_minus_R"]
REF_DIRECTION = {"R_minus_O": ">0", "F_minus_C": ">0", "R_minus_T": ">0"}   # rules sec.4
TWO_SIDED_ONLY = ["C_minus_O", "F_minus_R", "T_minus_O"]
VARIANTS = {  # Thai-exclusion variants (rules do not define "Thai excluded" for REL/Exp A: both recorded)
    "all4": lambda q, g: True,
    "noTH_screen": lambda q, g: g != "th",            # en/zh/ru screens (rules sec.0 wording for Exp A)
    "noTH_both": lambda q, g: q != "th" and g != "th",  # analogue of the 5x5 rule of the 6x6
}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def load_mod(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def jl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def holm(p):
    p = np.array(p, float); o = np.argsort(p); m = len(p); adj = np.empty(m); run = 0.0
    for i, j in enumerate(o):
        run = max(run, (m - i) * p[j]); adj[j] = min(1.0, run)
    return adj


# ---------------------------------------------------------------- REL
def rel_boot(qrows, cols=REL_CON, B=B_REL, seed=SEED_REL):
    ids = sorted({r["parallel_id"] for r in qrows}); ix = {p: i for i, p in enumerate(ids)}; k = len(ids)
    n = np.zeros(k); sums = {c: np.zeros(k) for c in cols}
    for r in qrows:
        i = ix[r["parallel_id"]]; n[i] += 1
        for c in cols:
            sums[c][i] += r[c]
    rng = np.random.default_rng(seed); idx = rng.integers(0, k, size=(B, k))   # t1_holm.py convention
    out = {}
    for c in cols:
        d = 100 * sums[c][idx].sum(1) / n[idx].sum(1); est = 100 * sums[c].sum() / n.sum()
        s = np.sort(d)
        le, ge = int((d <= 0).sum()), int((d >= 0).sum())
        p = min(1.0, 2 * min((1 + le) / (B + 1), (1 + ge) / (B + 1)))
        out[c] = dict(est_pp=est, lo=s[int(0.025 * (B - 1))], hi=s[int(0.975 * (B - 1))], p_raw=p, items=k, quartets=int(n.sum()))
    return out


def rel_analysis(quartets):
    """quartets: list of dicts from prepare_glmm.quartet_table. -> {variant:{stratum:{contrast:stats}}}"""
    res = {}
    for vn, f in VARIANTS.items():
        res[vn] = {}
        sel = [q for q in quartets if f(q["query_language"], q["gui_language"])]
        for st, rows in (("dependent", [q for q in sel if q["text_dependency"] == "dependent"]),
                         ("independent", [q for q in sel if q["text_dependency"] == "independent"]),
                         ("all", sel)):
            if len({r["parallel_id"] for r in rows}) < 5:
                continue
            r = rel_boot(rows)
            if st == "dependent":   # Holm over 4 only in the dependent stratum
                h = holm([r[c]["p_raw"] for c in REL_CON])
                for c, a in zip(REL_CON, h):
                    r[c]["p_holm"] = float(a)
            res[vn][st] = r
    return res


def rel_quartets(prep, model_key, results_path, metric="generation_correct", check_summary=None):
    raw = jl(results_path)
    assert all(r["status"] == "success" for r in raw), "non-success REL rows"
    if metric == "scoring_correct":
        raw2 = []
        for r in raw:
            r = dict(r); r["generation_correct"] = bool(r["scoring_correct"]); r["parse_success"] = True; raw2.append(r)
        raw_use = raw2
    else:
        raw_use = raw
    proj = [prep.project_row(model_key, r) for r in raw_use if r["primary_analysis_eligible"]]
    q = prep.quartet_table(proj)
    if check_summary and metric == "generation_correct":
        prep.validate_summary(q, {model_key: check_summary})
    return raw, q


def pfail_table(rows, exp, cond_key="condition", gui_key="gui_language"):
    c = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        k = (exp, r[cond_key], r[gui_key]); c[k][0] += 1; c[k][1] += (not r["parse_success"]); c[k][2] += (r["status"] != "success")
    return [dict(experiment=k[0], condition=k[1], screen=k[2], n=v[0], parse_fail=v[1], non_success=v[2]) for k, v in sorted(c.items())]


def agreement(rows):
    n = len(rows)
    same_corr = sum(bool(r["generation_correct"]) == bool(r["scoring_correct"]) for r in rows)
    same_lab = sum(r["parsed_generated_label"] == r["scored_predicted_label"] for r in rows)
    return dict(n=n, correctness_agree=same_corr / n, label_agree=same_lab / n, acc_generation=sum(bool(r["generation_correct"]) for r in rows) / n,
                acc_scoring=sum(bool(r["scoring_correct"]) for r in rows) / n)


def thai_indicator(rows):
    """(a) REL R-condition accuracy: Thai screen / English screen (all items, all condition rows)."""
    def acc(sel):
        s = [bool(r["generation_correct"]) for r in sel]; return sum(s) / len(s), len(s)
    out = {}
    for name, f in (("all_rows", lambda r: True), ("eligible_only", lambda r: r.get("primary_analysis_eligible"))):
        R = [r for r in rows if r["condition"] == "R" and f(r)]
        th, nth = acc([r for r in R if r["gui_language"] == "th"]); en, nen = acc([r for r in R if r["gui_language"] == "en"])
        out[name] = dict(acc_th=th, n_th=nth, acc_en=en, n_en=nen, ratio=th / en)
    return out


# ---------------------------------------------------------------- Exp A
def expa_analysis(A, pred_path, B_seed_note=None):
    rows = A.load_predictions(pred_path)
    ok = defaultdict(set)
    for r in rows:
        if r["status"] == "success":
            ok[r["pair_id"]].add(r["condition"])
    complete = {p for p, c in ok.items() if c == set(A.CONDS)}
    rows = [r for r in rows if r["pair_id"] in complete]
    prim = A.pair_sets()["primary_full"] & complete
    res = {}
    for vn, f in VARIANTS.items():
        P = {p for p in prim if f(p.split("::")[-2], p.split("::")[-1])}
        res[vn] = {}
        for outcome in ("generation_correct", "scoring_correct"):
            items, m = A.item_matrix(rows, outcome, P)
            b = A.bootstrap(m)
            res[vn][outcome] = dict(pairs=len(P), items=len(items), acc=dict(zip(A.CONDS, (100 * m.mean(0)).tolist())), **b)
    return res, len(complete)


def fmt_ci(e, d=1):
    return f"{e['est_pp']:+.{d}f} [{e['lo']:+.{d}f}, {e['hi']:+.{d}f}]"


def verdict(contrast, est, p_holm):
    ref = REF_DIRECTION.get(contrast)
    if ref is None:
        return "양측 보고만"
    if est > 0 and p_holm <= 0.05:
        return "재현"
    if est > 0:
        return "부호 일치 (유의 아님)"
    return "부호 반대" if est < 0 else "0"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    model, un, out = args[0], Path(args[1]), Path(args[2])
    out.mkdir(parents=True, exist_ok=True)
    if not (un / "rel_full").exists():
        c = list(un.glob("*/rel_full"))
        assert len(c) == 1, "cannot locate rel_full under unpacked_dir"
        un = c[0].parent
    R = {"model_key": model, "unpacked_dir": str(un)}

    # 0. frozen-file checks
    fr = RULES_FROZEN.read_text()
    rules_sha = sha(RULES); dfz = DIAG_FROZEN.read_text()
    R["provenance"] = dict(
        rules_sha256=rules_sha, rules_frozen_ok=rules_sha in fr,
        diag_sha256=sha(DIAG), diag_frozen_ok=sha(DIAG) in dfz, analyze_expA_sha256=sha(ANALYZE),
        prepare_glmm_sha256=sha(PREP), t1_holm_sha256=sha(HOLM_REF), driver_sha256=sha(Path(__file__).resolve()),
        inputs={str(p.relative_to(un)): sha(p) for p in [un / "rel_full/results.jsonl", un / "rel_full/predictions.jsonl", un / "expa_full/predictions.jsonl"]})
    assert R["provenance"]["rules_frozen_ok"], "rules sha mismatch -> stop"
    assert R["provenance"]["diag_frozen_ok"], "diag sha mismatch -> stop"

    # 1. gates / run contract
    gates = {k: json.loads((un / p).read_text()) for k, p in (("rel", "rel_full/gate_rel_complete.json"), ("expa", "expa_full/gate_expa_complete.json"))}
    contract = json.loads((un / "rel_full/run_contract.json").read_text())
    R["gates"] = {k: dict(status=v.get("status"), rows=v.get("rows"), parse_failures=v.get("parse_failures"), problems=v.get("problems"),
                          warnings=v.get("warnings"), batch_sizes=v.get("batch_sizes")) for k, v in gates.items()}
    R["model_config"] = contract["model_config"]

    prep = load_mod(PREP, "prep_glmm")
    A = load_mod(ANALYZE, "analyze_expA")

    # 2. REL
    rel_summary = json.loads((un / "rel_full/summary.json").read_text())
    raw, quartets = rel_quartets(prep, model, un / "rel_full/results.jsonl", check_summary=rel_summary)
    R["rel_counts"] = dict(condition_rows=len(raw), eligible_quartets=len(quartets), validate_summary_ok=True)
    R["rel"] = {"generation_correct": rel_analysis(quartets)}
    _, qs = rel_quartets(prep, model, un / "rel_full/results.jsonl", metric="scoring_correct")
    R["rel"]["scoring_correct"] = rel_analysis(qs)
    R["rel_glmm"] = "skipped: Rscript not available" if shutil.which("Rscript") is None else "Rscript present but GLMM wrapper not implemented in this driver version (미검증)"

    # 3. Exp A
    pred = un / "expa_full/predictions.jsonl"
    R["expa"], ncomp = expa_analysis(A, pred)
    R["expa_complete_pairs"] = ncomp
    expa_rows = A.load_predictions(pred)
    ea_dir = out / "expA_analyze"
    subprocess.run([sys.executable, "-I", str(ANALYZE), model, str(pred), str(ea_dir)], check=True, capture_output=True)
    primary_summary = json.loads((ea_dir / "summary.json").read_text())["sets"]["primary_full|generation_correct"]
    # cross-check: in-process primary == analyze_expA CLI output
    chk = R["expa"]["all4"]["generation_correct"]
    assert abs(chk["T_minus_O"]["pp"] - primary_summary["T_minus_O"]["pp"]) < 1e-9 and abs(chk["R_minus_T"]["p_holm_primary2"] - primary_summary["R_minus_T"]["p_holm_primary2"]) < 1e-12
    if "--skip-diag" not in flags:
        r = subprocess.run([sys.executable, "-I", str(DIAG), model, str(pred), str(out / "diag_expA")], capture_output=True, text=True)
        R["diag"] = dict(returncode=r.returncode, stderr_tail=r.stderr[-500:])
        if r.returncode == 0:
            R["diag"]["confirmatory"] = json.loads((out / "diag_expA/confirmatory.json").read_text())

    # 4. parse failures, agreement, tokens
    pf = pfail_table(raw, "REL") + pfail_table(expa_rows, "ExpA")
    R["parse_failures"] = pf
    totals = {}
    for e in ("REL", "ExpA"):
        n = sum(x["n"] for x in pf if x["experiment"] == e); f = sum(x["parse_fail"] for x in pf if x["experiment"] == e)
        totals[e] = dict(n=n, parse_fail=f, rate=f / n, over_2pct=f / n > 0.02)
    R["parse_failure_totals"] = totals
    R["agreement"] = {"REL(condition rows)": agreement(raw), "REL(unique inference rows)": agreement(jl(un / "rel_full/predictions.jsonl")), "ExpA": agreement(expa_rows)}
    tok = {}
    for e, rs in (("REL", raw), ("ExpA", expa_rows)):
        v = [r["visual_token_count"] for r in rs if r.get("visual_token_count") is not None]
        p = [r["prompt_token_count"] for r in rs if r.get("prompt_token_count") is not None]
        tok[e] = dict(visual_token_count_available=bool(v), visual=(dict(min=min(v), median=statistics.median(v), max=max(v)) if v else None),
                      prompt=(dict(min=min(p), median=statistics.median(p), max=max(p)) if p else None),
                      batch_sizes=dict(Counter(r["batch_size"] for r in rs)))
    R["tokens"] = tok

    # 5. Thai indicator
    R["thai_indicator_a"] = thai_indicator(raw)
    # Headline definition = eligible_only: it is the one that reproduces the 8B values quoted in the rules (0.95/0.60);
    # the all-rows version is kept for reference (checked on the two 8B runs, see README).
    ti = R["thai_indicator_a"]["eligible_only"]["ratio"]
    R["thai_flag_a"] = dict(ratio_headline=ti, flag_weak_thai_reading=ti < 0.7, ratio_all_rows=R["thai_indicator_a"]["all_rows"]["ratio"],
                            flag_if_all_rows=R["thai_indicator_a"]["all_rows"]["ratio"] < 0.7, indicator_b="6x6 not run (out of scope)")

    # 6. verdicts (model-internal Holm; dependent stratum for REL, all4 variant)
    V = []
    for c in REL_CON:
        e = R["rel"]["generation_correct"]["all4"]["dependent"][c]
        V.append(dict(exp="REL", contrast=c, est_pp=e["est_pp"], p_holm=e["p_holm"], verdict=verdict(c, e["est_pp"], e["p_holm"])))
    for c in ("T_minus_O", "R_minus_T"):
        e = R["expa"]["all4"]["generation_correct"][c]
        V.append(dict(exp="ExpA", contrast=c, est_pp=e["pp"], p_holm=e["p_holm_primary2"], verdict=verdict(c, e["pp"], e["p_holm_primary2"])))
    R["replication"] = V
    # decision changes under Thai exclusion / scoring metric
    chg = []
    for vn in ("noTH_screen", "noTH_both"):
        for c in REL_CON:
            a, b = R["rel"]["generation_correct"]["all4"]["dependent"][c], R["rel"]["generation_correct"][vn]["dependent"][c]
            chg.append(dict(exp="REL", variant=vn, contrast=c, sign_same=(a["est_pp"] > 0) == (b["est_pp"] > 0), sig_all=a["p_holm"] <= .05, sig_var=b["p_holm"] <= .05))
        for c in ("T_minus_O", "R_minus_T"):
            a, b = R["expa"]["all4"]["generation_correct"][c], R["expa"][vn]["generation_correct"][c]
            chg.append(dict(exp="ExpA", variant=vn, contrast=c, sign_same=(a["pp"] > 0) == (b["pp"] > 0), sig_all=a["p_holm_primary2"] <= .05, sig_var=b["p_holm_primary2"] <= .05))
    R["thai_exclusion_changes"] = chg
    sc = []
    for c in REL_CON:
        a, b = R["rel"]["generation_correct"]["all4"]["dependent"][c], R["rel"]["scoring_correct"]["all4"]["dependent"][c]
        sc.append(dict(exp="REL", contrast=c, sign_same=(a["est_pp"] > 0) == (b["est_pp"] > 0), holm_same=(a["p_holm"] <= .05) == (b["p_holm"] <= .05)))
    for c in ("T_minus_O", "R_minus_T"):
        a, b = R["expa"]["all4"]["generation_correct"][c], R["expa"]["all4"]["scoring_correct"][c]
        sc.append(dict(exp="ExpA", contrast=c, sign_same=(a["pp"] > 0) == (b["pp"] > 0), holm_same=(a["p_holm_primary2"] <= .05) == (b["p_holm_primary2"] <= .05)))
    R["scoring_vs_generation_decisions"] = sc

    # 7. 8B context (same code paths; labelled)
    if "--no-context" not in flags:
        ctx = {}
        for name, p in CONTEXT.items():
            try:
                rr, qq = rel_quartets(prep, "ctx", p["rel"])
                ea, nc = expa_analysis(A, p["expa"])
                ctx[name] = dict(rel=rel_analysis(qq), expa=ea, thai_indicator_a=thai_indicator(rr))
            except Exception as ex:  # keep driver usable if a context file is missing
                ctx[name] = dict(error=repr(ex))
        R["context_8b"] = ctx

    (out / "results.json").write_text(json.dumps(R, indent=1, ensure_ascii=False, default=float) + "\n")
    write_tables(R, out)
    print("done:", out)


def write_tables(R, out):
    L = []
    g = R["rel"]["generation_correct"]; e = R["expa"]
    ctx = R.get("context_8b", {})
    L.append("## REL O/R/C/F 의존 문항 층, 생성 답 정오 (문항 bootstrap 10,000회, seed 42, Holm 4개)\n")
    L.append("| 모델 | 언어 범위 | 문항/quartet | 대비 | 차이 %p [95% CI] | 원시 p | Holm p |\n|---|---|---|---|---|---|---|")
    sets = [(R["model_key"] + " (새 모델)", g)] + [(k + " (8B 참고)", v["rel"]) for k, v in ctx.items() if "rel" in v]
    for nm, d in sets:
        for vn in VARIANTS:
            for c in REL_CON:
                s = d[vn]["dependent"][c]
                L.append(f"| {nm} | {vn} | {s['items']}/{s['quartets']} | {c} | {fmt_ci(s)} | {s['p_raw']:.4f} | {s['p_holm']:.4f} |")
    L.append("\n## 실험 A 주 분석 (생성 답 정오, 문항 bootstrap, seed 20261113, Holm 2개)\n")
    L.append("| 모델 | 언어 범위 | 쌍/문항 | O | T | R | T-O [CI] | R-T [CI] | R-O [CI] | Holm p (T-O / R-T) |\n|---|---|---|---|---|---|---|---|---|---|")
    sets = [(R["model_key"] + " (새 모델)", e)] + [(k + " (8B 참고)", v["expa"]) for k, v in ctx.items() if "expa" in v]
    for nm, d in sets:
        for vn in VARIANTS:
            s = d[vn]["generation_correct"]
            f = lambda k: f"{s[k]['pp']:+.1f} [{s[k]['lo']:+.1f}, {s[k]['hi']:+.1f}]"
            L.append(f"| {nm} | {vn} | {s['pairs']}/{s['items']} | {s['acc']['O']:.1f} | {s['acc']['T']:.1f} | {s['acc']['R']:.1f} | {f('T_minus_O')} | {f('R_minus_T')} | {f('R_minus_O')} | {s['T_minus_O']['p_holm_primary2']:.4f} / {s['R_minus_T']['p_holm_primary2']:.4f} |")
    L.append("\n## 파싱 실패 (실험 묶음, 조건, 화면 언어)\n")
    L.append("| 실험 | 조건 | 화면 | 행 수 | 파싱 실패 | 성공 아님 |\n|---|---|---|---|---|---|")
    for x in R["parse_failures"]:
        L.append(f"| {x['experiment']} | {x['condition']} | {x['screen']} | {x['n']} | {x['parse_fail']} | {x['non_success']} |")
    L.append("\n합계: " + "; ".join(f"{k} {v['parse_fail']}/{v['n']} ({100*v['rate']:.2f}%, 2% 초과={v['over_2pct']})" for k, v in R["parse_failure_totals"].items()))
    L.append("\n## 생성 답 vs 레이블 확률 채점 일치\n")
    L.append("| 묶음 | 행 | 정오 일치 | 예측 레이블 일치 | 정확도(생성) | 정확도(채점) |\n|---|---|---|---|---|---|")
    for k, v in R["agreement"].items():
        L.append(f"| {k} | {v['n']} | {100*v['correctness_agree']:.2f}% | {100*v['label_agree']:.2f}% | {100*v['acc_generation']:.2f}% | {100*v['acc_scoring']:.2f}% |")
    L.append("\n## 태국어 읽기 지표 (a): REL R 조건 정답률 태국어 화면 / 영어 화면\n")
    L.append("| 모델 | 정의 | 태국어 | 영어 | 비율 |\n|---|---|---|---|---|")
    rows = [(R["model_key"], R["thai_indicator_a"])] + [(k + " (8B)", v["thai_indicator_a"]) for k, v in ctx.items() if "thai_indicator_a" in v]
    for nm, d in rows:
        for df_, v in d.items():
            L.append(f"| {nm} | {df_} | {100*v['acc_th']:.1f}% (n={v['n_th']}) | {100*v['acc_en']:.1f}% (n={v['n_en']}) | {v['ratio']:.3f} |")
    L.append(f"\n표시(<0.7, 기준 정의=eligible_only): {R['thai_flag_a']['flag_weak_thai_reading']}")
    L.append("\n## 재현 판정 (모델 안 Holm, 8B 기준 방향 대비)\n")
    L.append("| 실험 | 대비 | 추정 %p | Holm p | 판정 |\n|---|---|---|---|---|")
    for v in R["replication"]:
        L.append(f"| {v['exp']} | {v['contrast']} | {v['est_pp']:+.2f} | {v['p_holm']:.4f} | {v['verdict']} |")
    (out / "tables_KO.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
