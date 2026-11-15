"""Sensitivity of the existing R_stem/R_opts results to the mapping audit.

Re-runs the pre-registered item bootstrap (same functions, seed and B as analyze_rstem.py) after
dropping pairs touched by refs judged mapping_error (and, second variant, also uncertain).
Items stay in the analysis as long as at least one of their pairs remains.
"""
import gzip
import importlib.util
import json
import sys
from pathlib import Path

BASE = Path("/Users/baegihyeon/Desktop/CUAI/CUAI_하계 컨퍼런스")
spec = importlib.util.spec_from_file_location("ar", BASE / "rstem_ropts_qwen3_20261109/analysis/analyze_rstem.py")
ar = importlib.util.module_from_spec(spec); spec.loader.exec_module(ar)
PRED = {"qwen3": BASE / "rstem_ropts_qwen3_20261109/results_20261109/raw_from_github_324654c/full/predictions.jsonl.gz",
        "internvl35": BASE / "rstem_ropts_internvl35_20261110/results_20261110/extracted/internvl35_rstem_ropts/full/predictions.jsonl"}
aff = json.load(open(Path(__file__).resolve().parents[1] / "work/mapping_audit_affected_pairs.json"))
variants = {"all": set(), "drop_error": set(aff["mapping_error"]), "drop_error_uncertain": set(aff["mapping_error"]) | set(aff["uncertain"])}
out = {}
for model, p in PRED.items():
    txt = gzip.open(p, "rt", encoding="utf-8").read() if p.suffix == ".gz" else p.read_text(encoding="utf-8")
    rows = {}
    for line in txt.splitlines():
        if line.strip():
            r = json.loads(line); rows[r["input_id"]] = r
    rows = [r for r in rows.values() if r.get("split", "main") == "main" and r["status"] == "success"]
    for v, drop in variants.items():
        sub = [r for r in rows if r["pair_id"] not in drop]
        items, m = ar.item_matrix(sub, "generation_correct")
        res = ar.bootstrap(m)
        out[(model, v)] = {"pairs": len({r["pair_id"] for r in sub}), "items": len(items),
                           **{k: [round(res[k][x], 2) for x in ("pp", "lo", "hi")] for k in ("R_minus_O", "stem_effect_S", "option_effect_P", "interaction_I")}}
        print(model, v, json.dumps(out[(model, v)]), flush=True)
json.dump({f"{a}|{b}": v for (a, b), v in out.items()}, open(Path(__file__).with_suffix(".json"), "w"), indent=1)
