"""Diagnostic analysis for Experiment A (plan: ../DIAGNOSTIC_PLAN_THAI_KO.md, v1).

Usage: python3 -I diag_expA.py <model_name> <predictions.jsonl> <out_dir>

Reuses analyze_expA.py (loaded by path, never modified) for load_predictions, pair_sets (set definitions,
exclusion, sub1/sub2) and the "complete pair" rule. Unit of resampling: item (parallel_id), all pairs of a drawn
item are used. All statistics here are pair-weighted means (plan: "쌍 단위 정답 차를 해당 쌍들에서 평균한 값").
"""
from __future__ import annotations

import csv
import difflib
import hashlib
import importlib.util
import json
import os
import platform
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True

# ----------------------------------------------------------------------------- constants (edit here)
B = int(os.environ.get("DIAG_B", 10_000))      # bootstrap draws (env override only for quick tests)
SEED = 20261114                                # bootstrap seed
ALPHA = 0.05                                   # one-sided, Holm over P1-P3
E2_RATIO_MAX = 0.5                             # AMBIGUOUS in plan v2: "E2 small" operationalised as 90% upper bound of E2/E1 < this
CI_LEVEL_TOST = 90.0                           # E1/E2 90% percentile interval
CI_LEVEL = 95.0                                # exploratory two-sided percentile interval
NEAR_THRESH = 0.5                              # D5 ratio threshold
D6_SEED = 20261114
D6_N = 20
GUIS = ("en", "zh", "th", "ru")
THAI = "th"
HYPOTHESIS_GENERATING_MODELS = {"qwen3", "qwen3-vl-8b"}  # results used to form the hypotheses -> exploratory label
CONFIRMATORY_MODELS = {"internvl35", "internvl35-8b"}  # plan v2: only InternVL3.5-8B is the confirmatory check; all others descriptive
CONDS = ("O", "T", "R")
ROUND = 12                                     # snap float noise at 0 before sign counting (same as analyze_expA)

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
FEATURES = EXP / "diagnostics_inputs_20261114" / "per_pair_features.csv"
SPANS = EXP / "work" / "T_gemma_first_spans.jsonl"
SIM = EXP / "work" / "T_gemma_first_similarity.jsonl"
SPOT_JUDGED = EXP / "spotcheck" / "spotcheck_judged_model.csv"
SPOT_KEY = EXP / "spotcheck" / "spotcheck_key.jsonl"
ANALYZE = HERE / "analyze_expA.py"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_analyze():
    spec = importlib.util.spec_from_file_location("analyze_expA", ANALYZE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ----------------------------------------------------------------------------- bootstrap machinery
class Boot:
    """Item-cluster bootstrap via multinomial item counts; statistics are ratios of per-item sums."""

    def __init__(self, item_idx: np.ndarray, n_items: int, B: int = B, seed: int = SEED):
        self.item_idx, self.n_items, self.B = item_idx, n_items, B
        rng = np.random.default_rng(seed)
        self.W = rng.multinomial(n_items, np.full(n_items, 1.0 / n_items), size=B).astype(float)

    def mean(self, V: np.ndarray, mask: np.ndarray):
        """Pair-weighted mean of columns of V over `mask`. Returns point (k,), draws (B,k)."""
        V = np.asarray(V, float).reshape(len(self.item_idx), -1)
        S = np.zeros((self.n_items, V.shape[1]))
        np.add.at(S, self.item_idx[mask], V[mask])
        c = np.bincount(self.item_idx[mask], minlength=self.n_items).astype(float)
        den = self.W @ c
        with np.errstate(invalid="ignore", divide="ignore"):
            draws = (self.W @ S) / den[:, None]
        point = S.sum(0) / c.sum() if c.sum() else np.full(V.shape[1], np.nan)
        return point, draws

    def reg(self, X: np.ndarray, y: np.ndarray, mask: np.ndarray):
        """OLS (item-weighted bootstrap via per-item X'X, X'y). Returns coef (p,), draws (B,p)."""
        Xm, ym, im = X[mask], y[mask], self.item_idx[mask]
        p = X.shape[1]
        XtX = np.zeros((self.n_items, p, p))
        Xty = np.zeros((self.n_items, p))
        np.add.at(XtX, im, Xm[:, :, None] * Xm[:, None, :])
        np.add.at(Xty, im, Xm * ym[:, None])
        coef = np.linalg.pinv(XtX.sum(0)) @ Xty.sum(0)
        A = np.einsum("bi,ipq->bpq", self.W, XtX)
        c = self.W @ Xty
        draws = np.einsum("bpq,bq->bp", np.linalg.pinv(A), c)
        return coef, draws


def interval(draws, level=CI_LEVEL, scale=1.0):
    d = np.round(draws[~np.isnan(draws)], ROUND) * scale
    a = (100 - level) / 2
    return float(np.percentile(d, a)), float(np.percentile(d, 100 - a)), int(len(d))


def cell_stats(boot: Boot, V: np.ndarray, mask: np.ndarray):
    """V columns = O,T,R outcomes. Returns dict name -> (point, draws) for O,T,R and the three contrasts."""
    pt, dr = boot.mean(V, mask)
    pts = {"O": pt[0], "T": pt[1], "R": pt[2], "T-O": pt[1] - pt[0], "R-T": pt[2] - pt[1], "R-O": pt[2] - pt[0]}
    drs = {"O": dr[:, 0], "T": dr[:, 1], "R": dr[:, 2], "T-O": dr[:, 1] - dr[:, 0], "R-T": dr[:, 2] - dr[:, 1],
           "R-O": dr[:, 2] - dr[:, 0]}
    return {k: (pts[k], drs[k]) for k in pts}


def row_from_cell(cs, **ident):
    out = dict(ident)
    for k in ("O", "T", "R"):
        out[f"acc_{k}"] = round(100 * cs[k][0], 3)
    for k in ("T-O", "R-T", "R-O"):
        lo, hi, nv = interval(cs[k][1], scale=100)
        out[k] = round(100 * cs[k][0], 3)
        out[f"{k}_lo"], out[f"{k}_hi"] = round(lo, 3), round(hi, 3)
    return out


def write_csv(path: Path, rows: list[dict]):
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


# ----------------------------------------------------------------------------- data
def build_pair_table(A, pred_path: Path):
    rows = A.load_predictions(pred_path)
    ok = defaultdict(set)
    for r in rows:
        if r["status"] == "success":
            ok[r["pair_id"]].add(r["condition"])
    complete = {p for p, c in ok.items() if c == set(CONDS)}
    sets = A.pair_sets()
    primary = sets["primary_full"] & complete
    recs = defaultdict(dict)
    for r in rows:
        if r["pair_id"] in primary:
            recs[r["pair_id"]][r["condition"]] = r
    out = []
    for pid, d in recs.items():
        golds = {d[c]["gold_answer"] for c in CONDS}
        assert len(golds) == 1, f"gold differs across conditions in {pid}"
        o = d["O"]
        out.append({"pair_id": pid, "item": o["parallel_id"], "query": o["query_language"], "gui": o["gui_language"],
                    "gold": o["gold_answer"],
                    **{f"c{c}": float(bool(d[c]["generation_correct"])) for c in CONDS},
                    **{f"p{c}": float(d[c]["gold_probability"]) for c in CONDS},
                    **{f"lab{c}": d[c]["parsed_generated_label"] for c in CONDS}})
    df = pd.DataFrame(out).sort_values("pair_id").reset_index(drop=True)
    df["item_idx"] = pd.factorize(df["item"], sort=True)[0]
    feats = pd.read_csv(FEATURES)
    feats["d_exact"] = feats["delta_exact_T_minus_O"]
    feats["d_chrf"] = feats["chrF_T"] - feats["chrF_O"]
    df = df.merge(feats[["pair_id", "d_exact", "d_chrf", "any_lost"]], on="pair_id", how="left", validate="1:1")
    assert df[["d_exact", "d_chrf", "any_lost"]].notna().all().all(), "features missing for some pairs"
    return df, sets, complete


def mk_boot(df, B=B, seed=SEED):
    return Boot(df["item_idx"].to_numpy(), int(df["item_idx"].max()) + 1, B, seed)


# ----------------------------------------------------------------------------- confirmatory
def holm(pvals: dict, alpha=ALPHA):
    order = sorted(pvals, key=lambda k: pvals[k])
    m, run, out = len(order), 0.0, {}
    for i, k in enumerate(order):
        run = max(run, min(1.0, (m - i) * pvals[k]))
        out[k] = {"p_holm": run, "reject": run <= alpha}
    return out


def one_sided_p(draws, direction):
    d = np.round(draws[~np.isnan(draws)], ROUND)
    n = len(d)
    bad = (d <= 0).sum() if direction == ">0" else (d >= 0).sum()
    return float((1 + bad) / (n + 1))


def interpret(res):
    """Plan v2 interpretation rules, literal. 'E2 small / E1 large' is not numerically defined in the plan:
    operationalised with E2_RATIO_MAX / E1 CI below (flagged as ambiguity)."""
    r = {k: res[k]["reject"] for k in ("P1", "P2", "P3")}
    if not r["P1"]:
        return "태국어 패턴은 Qwen3에서만 관찰됐다 (이후 크기 축·UI-TARS·MiniCPM은 같은 코드로 기술만)", "P1_fail"
    if not (r["P2"] and r["P3"]):
        return "방향 차이는 재현되지만 부호 뒤집힘은 재현되지 않았다", "direction_only"
    ratio = res["E2"]["ratio_E2_over_E1"]
    e1_pos = res["E1"]["ci90_lo_pp"] > 0
    small = ratio["ci90_hi"] < E2_RATIO_MAX
    if e1_pos and small:
        return "부호 뒤집힘이 재현됐다. E2가 작고 E1이 커서 뒤집힘이 주로 O 쪽에서 생긴다는 H-A의 형태와 맞는다", "flip_replicated_H-A_consistent"
    return "뒤집힘은 재현, O 쪽 기원은 미결", "flip_replicated_origin_unresolved"


def confirmatory(df, boot, label="confirmatory"):
    V = df[["cO", "cT", "cR"]].to_numpy()
    th = (df["gui"] == THAI).to_numpy()
    rest = ~th
    cth, crest = cell_stats(boot, V, th), cell_stats(boot, V, rest)
    stats = {
        "P1": ("T-O(th) - T-O(rest)", ">0", cth["T-O"][0] - crest["T-O"][0], cth["T-O"][1] - crest["T-O"][1]),
        "P2": ("T-O(th)", ">0", cth["T-O"][0], cth["T-O"][1]),
        "P3": ("T-O(rest)", "<0", crest["T-O"][0], crest["T-O"][1]),
        "E1": ("R-O(th) - R-O(rest)", "estimate", cth["R-O"][0] - crest["R-O"][0], cth["R-O"][1] - crest["R-O"][1]),
        "E2": ("R-T(th) - R-T(rest)", "estimate", cth["R-T"][0] - crest["R-T"][0], cth["R-T"][1] - crest["R-T"][1]),
    }
    res = {}
    for k, (name, dirn, pt, dr) in stats.items():
        lo, hi, nv = interval(dr, scale=100)
        e = {"statistic": name, "direction": dirn, "est_pp": 100 * pt, "ci95_lo_pp": lo, "ci95_hi_pp": hi, "valid_draws": nv}
        if dirn == "estimate":
            l90, h90, _ = interval(dr, CI_LEVEL_TOST, 100)
            e.update({"ci90_lo_pp": l90, "ci90_hi_pp": h90})
        else:
            e["p_one_sided"] = one_sided_p(dr, dirn)
        res[k] = e
    e1d, e2d = stats["E1"][3], stats["E2"][3]
    with np.errstate(invalid="ignore", divide="ignore"):
        rd = e2d / e1d
    l95, h95, nv = interval(rd, CI_LEVEL)
    l90, h90, _ = interval(rd, CI_LEVEL_TOST)
    res["E2"]["ratio_E2_over_E1"] = {"est": float(stats["E2"][2] / stats["E1"][2]) if stats["E1"][2] else None,
                                     "ci95_lo": l95, "ci95_hi": h95, "ci90_lo": l90, "ci90_hi": h90, "valid_draws": nv}
    h = holm({k: res[k]["p_one_sided"] for k in ("P1", "P2", "P3")})
    for k, v in h.items():
        res[k].update(v)
    text, code = interpret(res)
    # secondary metric (descriptive only): gold-probability differences, original scale, in pp
    Vp = df[["pO", "pT", "pR"]].to_numpy()
    pth, prest = cell_stats(boot, Vp, th), cell_stats(boot, Vp, rest)
    sec = {}
    for name, (a, b) in {"P1": (pth["T-O"], prest["T-O"]), "E1": (pth["R-O"], prest["R-O"]), "E2": (pth["R-T"], prest["R-T"])}.items():
        pt, dr = a[0] - b[0], a[1] - b[1]
        lo, hi, _ = interval(dr, scale=100)
        sec[name + "_goldprob_diff"] = {"est_pp": 100 * pt, "ci95_lo_pp": lo, "ci95_hi_pp": hi}
    for name, c in (("T-O(th)", pth["T-O"]), ("T-O(rest)", prest["T-O"])):
        lo, hi, _ = interval(c[1], scale=100)
        sec[name + "_goldprob"] = {"est_pp": 100 * c[0], "ci95_lo_pp": lo, "ci95_hi_pp": hi}
    return {"label": label, "n_pairs_th": int(th.sum()), "n_pairs_rest": int(rest.sum()),
            "n_items": int(boot.n_items), "B": boot.B, "seed": SEED, "alpha_one_sided": ALPHA, "e2_ratio_max": E2_RATIO_MAX, "results": res, "interpretation": text, "interpretation_code": code,
            "secondary_goldprob_descriptive": sec,
            "cells_pp": {"th": {k: 100 * v[0] for k, v in cth.items()}, "rest": {k: 100 * v[0] for k, v in crest.items()}}}


# ----------------------------------------------------------------------------- analysis-specific helpers
def item_mean_contrasts(df, mask):
    """analyze_expA convention (item score = mean over item's pairs, then mean over items) for cross-checking."""
    g = df[mask].groupby("item")[["cO", "cT", "cR"]].mean()
    o, t, r = g["cO"].mean(), g["cT"].mean(), g["cR"].mean()
    return {"O": 100 * o, "T": 100 * t, "R": 100 * r, "T-O": 100 * (t - o), "R-T": 100 * (r - t), "R-O": 100 * (r - o)}


def d1(df, boot):
    V = df[["cO", "cT", "cR"]].to_numpy()
    rows = []
    for q in GUIS:
        for g in GUIS:
            if q == g:
                continue
            m = ((df["query"] == q) & (df["gui"] == g)).to_numpy()
            rows.append(row_from_cell(cell_stats(boot, V, m), table="cell", query=q, gui=g, group="", n_pairs=int(m.sum())))
    for g in GUIS:
        m = (df["gui"] == g).to_numpy()
        rows.append(row_from_cell(cell_stats(boot, V, m), table="gui_marginal", query="*", gui=g, group="", n_pairs=int(m.sum())))
    m = np.ones(len(df), bool)
    rows.append(row_from_cell(cell_stats(boot, V, m), table="overall", query="*", gui="*", group="", n_pairs=int(m.sum())))
    pos = []
    groups = {"all": np.ones(len(df), bool), "th": (df["gui"] == THAI).to_numpy(), "rest": (df["gui"] != THAI).to_numpy()}
    for gname, gm in groups.items():
        for gold in "ABCD":
            m = gm & (df["gold"] == gold).to_numpy()
            if m.sum() == 0:
                continue
            r = row_from_cell(cell_stats(boot, V, m), table="T-O_by_gold_position", group=gname, gold=gold, n_pairs=int(m.sum()),
                              share_of_group=round(float(m.sum() / gm.sum()), 4))
            pos.append(r)
        for c in CONDS:
            vc = df.loc[gm, f"lab{c}"].fillna("none").value_counts()
            for lab in sorted(set(vc.index) | set("ABCD")):
                n = int(vc.get(lab, 0))
                pos.append({"table": "predicted_label_dist", "group": gname, "condition": c, "label": lab, "n": n,
                            "share": round(n / gm.sum(), 4)})
    return rows, pos


def design_gui_query(df, covar):
    gu = [g for g in GUIS[1:]]
    qu = [g for g in GUIS[1:]]
    cols = [np.ones(len(df))] + [(df["gui"] == g).to_numpy().astype(float) for g in gu] + \
           [(df["query"] == q).to_numpy().astype(float) for q in qu] + [df[covar].to_numpy(float)]
    names = ["intercept"] + [f"gui_{g}" for g in gu] + [f"query_{q}" for q in qu] + [covar]
    return np.column_stack(cols), names


def d2(df, boot):
    y = (df["cT"] - df["cO"]).to_numpy()
    rows = []
    for covar in ("d_exact", "d_chrf"):
        X, names = design_gui_query(df, covar)
        coef, dr = boot.reg(X, y, np.ones(len(df), bool))
        for j, n in enumerate(names):
            lo, hi, _ = interval(dr[:, j])
            rows.append({"model": f"pooled_{covar}", "gui": "all", "term": n, "coef": coef[j], "ci_lo": lo, "ci_hi": hi,
                         "n_pairs": len(df), "units": "dCorrect (0-1) per 1 unit of covariate" +
                         (" (d_exact is a 0-1 fraction)" if covar == "d_exact" else " (d_chrf is in chrF points 0-100)")})
        for g in GUIS:
            m = (df["gui"] == g).to_numpy()
            qs = [q for q in GUIS if q != g][1:]
            X = np.column_stack([np.ones(len(df))] + [(df["query"] == q).to_numpy().astype(float) for q in qs] +
                                [df[covar].to_numpy(float)])
            coef, dr = boot.reg(X, y, m)
            lo, hi, _ = interval(dr[:, -1])
            rows.append({"model": f"per_gui_{covar}", "gui": g, "term": covar, "coef": coef[-1], "ci_lo": lo, "ci_hi": hi,
                         "n_pairs": int(m.sum()), "units": "slope, query-language FE only"})
    # descriptive: mean of d_exact/d_chrf by gui
    for g in GUIS:
        m = df["gui"] == g
        rows.append({"model": "descriptive_mean", "gui": g, "term": "d_exact", "coef": df.loc[m, "d_exact"].mean(),
                     "n_pairs": int(m.sum())})
        rows.append({"model": "descriptive_mean", "gui": g, "term": "d_chrf", "coef": df.loc[m, "d_chrf"].mean(),
                     "n_pairs": int(m.sum())})
    return rows


def subset_by_gui(df, boot, mask_set, name, table):
    V = df[["cO", "cT", "cR"]].to_numpy()
    inset = df["pair_id"].isin(mask_set).to_numpy()
    rows = []
    for g in GUIS + ("ALL",):
        gm = np.ones(len(df), bool) if g == "ALL" else (df["gui"] == g).to_numpy()
        m = inset & gm
        if m.sum() == 0:
            continue
        rows.append(row_from_cell(cell_stats(boot, V, m), table=table, set=name, gui=g, n_pairs=int(m.sum()),
                                  n_items=int(df.loc[m, "item"].nunique())))
    # th vs rest difference
    th, rest = inset & (df["gui"] == THAI).to_numpy(), inset & (df["gui"] != THAI).to_numpy()
    if th.sum() and rest.sum():
        a, b = cell_stats(boot, V, th), cell_stats(boot, V, rest)
        for k in ("T-O", "R-O"):
            lo, hi, _ = interval(a[k][1] - b[k][1], scale=100)
            rows.append({"table": table + "_th_minus_rest", "set": name, "contrast": k, "est": 100 * (a[k][0] - b[k][0]),
                         "ci_lo": lo, "ci_hi": hi, "n_pairs_th": int(th.sum()), "n_pairs_rest": int(rest.sum())})
    return rows


def norm_nm(s):
    return unicodedata.normalize("NFKC", s).casefold()


def nearmiss_flags(spans_by_pair):
    out = {}
    for pid, sp in spans_by_pair.items():
        n_nm, per = 0, []
        for i, s in enumerate(sp):
            a = norm_nm(s["translation"])
            own = difflib.SequenceMatcher(None, a, norm_nm(s["screen_text"])).ratio()
            others = [difflib.SequenceMatcher(None, a, norm_nm(t["screen_text"])).ratio() for j, t in enumerate(sp) if j != i]
            mx = max(others) if others else 0.0
            nm = bool(mx >= NEAR_THRESH and mx > own)
            n_nm += nm
            per.append((s["ref_id"], own, mx, nm))
        out[pid] = {"n_spans": len(sp), "n_nearmiss_names": n_nm, "nearmiss_pair": int(n_nm > 0)}
    return out


def load_spans(pairs):
    by = defaultdict(list)
    for l in SPANS.open(encoding="utf-8"):
        s = json.loads(l)
        if s["pair_id"] in pairs:
            by[s["pair_id"]].append(s)
    return by


def d5(df, boot, spans_by):
    fl = nearmiss_flags(spans_by)
    fdf = pd.DataFrame.from_dict(fl, orient="index").rename_axis("pair_id").reset_index()
    fdf = df[["pair_id", "gui", "query"]].merge(fdf, on="pair_id", how="left")
    V = df[["cO", "cT", "cR"]].to_numpy()
    nm = df["pair_id"].map(fdf.set_index("pair_id")["nearmiss_pair"]).to_numpy()
    rows = []
    for g in GUIS + ("ALL",):
        gm = np.ones(len(df), bool) if g == "ALL" else (df["gui"] == g).to_numpy()
        for flag in (1, 0):
            m = gm & (nm == flag)
            if m.sum() == 0:
                continue
            rows.append(row_from_cell(cell_stats(boot, V, m), table="nearmiss", gui=g, nearmiss_pair=flag, n_pairs=int(m.sum()),
                                      n_items=int(df.loc[m, "item"].nunique())))
    return rows, fdf


def d4(df, boot, sets, spans_by):
    rows = subset_by_gui(df, boot, sets["sub2_meaning_preserved"] & set(df["pair_id"]), "sub2_meaning_preserved", "T-O_by_quality")
    rest = set(df["pair_id"]) - sets["sub2_meaning_preserved"]
    rows += subset_by_gui(df, boot, rest, "not_sub2", "T-O_by_quality")
    sim = {}
    for l in SIM.open(encoding="utf-8"):
        r = json.loads(l)
        sim[(r["pair_id"], r["field"], r["ref_id"])] = r["sim_T_screen"]
    gui_of = dict(zip(df["pair_id"], df["gui"]))
    acc, pair_acc = defaultdict(list), defaultdict(lambda: defaultdict(list))
    for pid, sp in spans_by.items():
        for s in sp:
            v = sim[(pid, s["field"], s["ref_id"])]
            acc[gui_of[pid]].append(v)
            pair_acc[gui_of[pid]][pid].append(v)
    for g in GUIS:
        pm = [np.mean(v) for v in pair_acc[g].values()]
        rows.append({"table": "labse_T_vs_screen", "gui": g, "n_spans": len(acc[g]), "span_mean": float(np.mean(acc[g])),
                     "n_pairs": len(pm), "pair_mean": float(np.mean(pm))})
    judged = pd.read_csv(SPOT_JUDGED, encoding="utf-8-sig")
    key = {json.loads(l)["id"]: json.loads(l) for l in SPOT_KEY.open(encoding="utf-8")}
    col = "T_meaning(correct/partly/wrong)"
    for g in GUIS:
        j = judged[judged["gui_language"] == g]
        vc = j[col].value_counts()
        n = len(j)
        rows.append({"table": "spotcheck_model_judged", "gui": g, "n_judged": n,
                     **{f"n_{c}": int(vc.get(c, 0)) for c in ("correct", "partly", "wrong")},
                     **{f"share_{c}": (float(vc.get(c, 0)) / n if n else None) for c in ("partly", "wrong")},
                     "other_values": ";".join(f"{k}={v}" for k, v in vc.items() if k not in ("correct", "partly", "wrong")),
                     "key_gui_mismatch": int(sum(key[i]["gui_language"] != g for i in j["id"] if i in key and "gui_language" in key[i]))})
    return rows


def d7(df, boot):
    V = df[["cO", "cT", "cR"]].to_numpy()
    rows = []
    for flag in (1, 0):
        m = (df["any_lost"] == flag).to_numpy()
        rows.append(row_from_cell(cell_stats(boot, V, m), table="lost", any_lost=flag, n_pairs=int(m.sum()),
                                  n_items=int(df.loc[m, "item"].nunique()),
                                  gui_counts=";".join(f"{g}={int((df.loc[m, 'gui'] == g).sum())}" for g in GUIS),
                                  query_counts=";".join(f"{g}={int((df.loc[m, 'query'] == g).sum())}" for g in GUIS)))
    return rows


def d6(df, spans_by, out_dir: Path):
    d = out_dir / "d6_cases"
    d.mkdir(parents=True, exist_ok=True)
    th = df["gui"] == THAI
    same = df["cO"] == df["cT"]
    groups = {"a_rest_Ocorrect_Twrong": ~th & (df.cO == 1) & (df.cT == 0),
              "b_th_Owrong_Tcorrect": th & (df.cO == 0) & (df.cT == 1),
              "c_rest_same_outcome": ~th & same,
              "d_th_same_outcome": th & same}
    rng = np.random.default_rng(D6_SEED)
    chosen, sizes = [], []
    for gname, m in groups.items():
        cand = sorted(df.loc[m, "pair_id"])
        k = min(D6_N, len(cand))
        pick = [cand[i] for i in sorted(rng.choice(len(cand), size=k, replace=False))]
        sizes.append({"group": gname, "population": len(cand), "sampled": k})
        chosen += [(gname, p) for p in pick]
    perm = rng.permutation(len(chosen))
    ix = df.set_index("pair_id")
    key_rows, sheet = [], []
    for (gname, pid), pi in zip(chosen, perm):
        cid = f"case{pi + 1:03d}"
        r = ix.loc[pid]
        key_rows.append({"case_id": cid, "group": gname, "pair_id": pid, "query_language": r["query"], "gui_language": r["gui"],
                         "gold": r["gold"], **{f"correct_{c}": int(r[f"c{c}"]) for c in CONDS},
                         **{f"label_{c}": r[f"lab{c}"] for c in CONDS}})
        for s in spans_by[pid]:
            sheet.append({"case_id": cid, "ref_id": s["ref_id"], "source_text": s["source_text"], "translation": s["translation"],
                          "screen_text": s["screen_text"], "verdict": "", "note": ""})
    sheet.sort(key=lambda r: (r["case_id"], r["ref_id"]))
    key_rows.sort(key=lambda r: r["case_id"])
    write_csv(d / "judge_sheet_blinded.csv", sheet)
    write_csv(d / "sample_key_UNBLINDED.csv", key_rows)
    write_csv(d / "group_sizes.csv", sizes)
    (d / "judge_categories.txt").write_text(
        "verdict (one per case_id; fill on first row of each case): 번역 오류 / 번역은 맞지만 화면 용어와 다름 / "
        "다른 요소 이름과 비슷함(near-miss) / 화면 글자와 같음 / 판단 불가\n", encoding="utf-8")
    return sizes


# ----------------------------------------------------------------------------- main
def main():
    t0 = time.time()
    model, pred, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    A = load_analyze()
    df, sets, complete = build_pair_table(A, pred)
    boot = mk_boot(df)
    label = ("exploratory (hypotheses were formed from this model's results)" if model.lower() in HYPOTHESIS_GENERATING_MODELS
             else "confirmatory" if model.lower() in CONFIRMATORY_MODELS
             else "descriptive (same code, not part of the confirmatory set; plan v2)")
    conf = confirmatory(df, boot, label)
    conf["model"] = model
    (out / "confirmatory.json").write_text(json.dumps(conf, indent=1, ensure_ascii=False, default=float) + "\n")
    crow = []
    for k, e in conf["results"].items():
        crow.append({"model": model, "label": label, "id": k, **e})
    write_csv(out / "confirmatory.csv", crow)

    cells, pos = d1(df, boot)
    for nm in ("audited_drop_mapping_error", "audited_drop_error_uncertain"):
        cells += subset_by_gui(df, boot, sets[nm] & set(df["pair_id"]), nm, "audited_set")
    write_csv(out / "d1_cells.csv", cells)
    write_csv(out / "d1_answer_position.csv", pos)
    write_csv(out / "d2_dose_response.csv", d2(df, boot))
    write_csv(out / "d3_zero_match.csv", subset_by_gui(df, boot, sets["sub1_zero_screen_match"] & set(df["pair_id"]),
                                                       "sub1_zero_screen_match", "zero_match"))
    spans_by = load_spans(set(df["pair_id"]))
    write_csv(out / "d4_quality.csv", d4(df, boot, sets, spans_by))
    r5, flags = d5(df, boot, spans_by)
    write_csv(out / "d5_nearmiss.csv", r5)
    flags.to_csv(out / "d5_nearmiss_pair_flags.csv", index=False)
    write_csv(out / "d7_lost.csv", d7(df, boot))
    sizes = d6(df, spans_by, out)

    code_hash = sha256(Path(__file__).resolve())
    meta = {"model": model, "timestamp_utc": datetime.now(timezone.utc).isoformat(), "seed": SEED, "B": B, "alpha": ALPHA,
            "e2_ratio_max": E2_RATIO_MAX, "near_thresh": NEAR_THRESH, "d6_seed": D6_SEED, "d6_n": D6_N,
            "n_pairs": len(df), "n_items": int(df["item"].nunique()), "n_complete_pairs_before_exclusion": len(complete),
            "d6_group_sizes": sizes, "label": label,
            "code_sha256": code_hash,
            "input_sha256": {str(p): sha256(p) for p in (pred, FEATURES, SPANS, SIM, SPOT_JUDGED, SPOT_KEY, ANALYZE)},
            "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
            "runtime_seconds": round(time.time() - t0, 1)}
    (out / "run_meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"label": label, "interpretation": conf["interpretation"],
                      "results": {k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()}
                                  for k, v in conf["results"].items()}, "runtime_s": meta["runtime_seconds"]},
                     indent=1, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
