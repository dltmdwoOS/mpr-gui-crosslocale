"""Translator agreement (Gemma vs NLLB), NLLB screen match, back-translation consistency.
Reuses build_T.norm / match_level exactly. Run: ../.venv/bin/python build_agreement.py
Outputs go to work/ and tables/. Main split only for rates; pair sets exclude the pre-registered excluded pair."""
import csv, hashlib, json, sys, time
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(BASE))
from build_T import norm, match_level  # noqa
EXCLUDED = {"rel::5/forest_9.jpg::zh::ru"}
W, T = HERE / "work", HERE / "tables"
T.mkdir(exist_ok=True)
jl = lambda p: [json.loads(l) for l in open(p, encoding="utf-8")]

spans = jl(BASE / "work/T_gemma_first_spans.jsonl")
fwd = {(r["src_lang"], r["tgt_lang"], r["text"]): r["translation"] for r in jl(W / "translations_nllb_full.jsonl")}
bak = {(r["src_lang"], r["tgt_lang"], r["text"]): r["translation"] for r in jl(W / "backtranslations_nllb_full.jsonl")}

# LaBSE: nllb_back vs source, and nllb vs gemma / screen (extra)
import numpy as np
from huggingface_hub import snapshot_download
from sentence_transformers import SentenceTransformer
path = snapshot_download("sentence-transformers/LaBSE", revision="836121a0533e5664b21c7aacc5d22951f2b8b25b",
                         ignore_patterns=["*.h5", "*.onnx", "onnx/*", "openvino/*", "tf_model*", "*.msgpack", "pytorch_model.bin"])
model = SentenceTransformer(path, device="cpu")

rows = []
for s in spans:
    q, g = s["query_language"], s["gui_language"]
    n = fwd[(q, g, s["source_text"])]
    b = bak[(g, q, s["translation"])]
    rows.append({**s, "nllb": n, "nllb_match_screen": match_level(n, s["screen_text"]),
                 "agree_gemma_nllb": norm(n) == norm(s["translation"]),
                 "agree_exact": n == s["translation"],
                 "gemma_back": b,
                 "back_exact": b == s["source_text"], "back_norm": norm(b) == norm(s["source_text"])})
texts = sorted({t for r in rows for t in (r["gemma_back"], r["source_text"], r["nllb"], r["translation"])})
emb = model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
ix = {t: i for i, t in enumerate(texts)}
cos = lambda a, b: float(np.dot(emb[ix[a]], emb[ix[b]]))
for r in rows:
    r["labse_back_source"] = round(cos(r["gemma_back"], r["source_text"]), 4)
    r["labse_gemma_nllb"] = round(cos(r["translation"], r["nllb"]), 4)
with (W / "agreement_spans.jsonl").open("w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

main = [r for r in rows if r["split"] == "main" and r["pair_id"] not in EXCLUDED]
by = defaultdict(list)
for r in main:
    by[r["pair_id"]].append(r)
agreed = sorted(p for p, v in by.items() if all(x["agree_gemma_nllb"] for x in v))
(W / "agreed_pairs.json").write_text(json.dumps({"agreed": agreed, "all_main": sorted(by)}, indent=0))
meta_pair = {p: (v[0]["query_language"], v[0]["gui_language"]) for p, v in by.items()}
ag = set(agreed)

def pct(a, b): return round(100 * a / b, 2) if b else None
def write(name, header, data):
    with (T / name).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(data)

out = {}
# span-level agreement by screen language, and by cell; pair-level likewise
data = []
for key, sel in [("all", lambda r: True)] + [(g, (lambda g: lambda r: r["gui_language"] == g)(g)) for g in ("en", "zh", "th", "ru")]:
    sp = [r for r in main if sel(r)]
    pr = [p for p in by if sel(by[p][0])]
    data.append([key, len(sp), sum(r["agree_gemma_nllb"] for r in sp), pct(sum(r["agree_gemma_nllb"] for r in sp), len(sp)),
                 sum(r["agree_exact"] for r in sp), len(pr), sum(p in ag for p in pr), pct(sum(p in ag for p in pr), len(pr))])
write("agreement_by_screen_lang.csv", ["screen_lang", "spans", "spans_agree_norm", "span_agree_pct", "spans_agree_exact", "pairs", "pairs_agreed", "pair_agreed_pct"], data)
out["by_screen"] = data
data = []
for q in ("en", "zh", "th", "ru"):
    for g in ("en", "zh", "th", "ru"):
        if q == g: continue
        sp = [r for r in main if r["query_language"] == q and r["gui_language"] == g]
        pr = [p for p in by if meta_pair[p] == (q, g)]
        if not pr: continue
        data.append([q, g, len(sp), pct(sum(r["agree_gemma_nllb"] for r in sp), len(sp)), len(pr), sum(p in ag for p in pr), pct(sum(p in ag for p in pr), len(pr))])
write("agreement_by_cell.csv", ["query_lang", "screen_lang", "spans", "span_agree_pct", "pairs", "pairs_agreed", "pair_agreed_pct"], data)
out["by_cell"] = data
# screen match levels, side by side
data = []
for g in ("all", "en", "zh", "th", "ru"):
    sp = [r for r in main if g == "all" or r["gui_language"] == g]
    for who, key in (("gemma", "match"), ("nllb", "nllb_match_screen")):
        c = {k: sum(r[key] == k for r in sp) for k in ("exact", "normalized", "different")}
        data.append([g, who, len(sp), c["exact"], c["normalized"], c["different"], pct(c["exact"] + c["normalized"], len(sp))])
write("screen_match_gemma_vs_nllb.csv", ["screen_lang", "translator", "spans", "exact", "normalized", "different", "exact_or_norm_pct"], data)
out["match"] = data
# back-translation
data = []
for g in ("all", "en", "zh", "th", "ru"):  # g = screen (translation target) language; back goes to query lang
    sp = [r for r in main if g == "all" or r["gui_language"] == g]
    data.append([g, len(sp), pct(sum(r["back_exact"] for r in sp), len(sp)), pct(sum(r["back_norm"] for r in sp), len(sp)),
                 round(float(np.mean([r["labse_back_source"] for r in sp])), 4), round(float(np.median([r["labse_back_source"] for r in sp])), 4),
                 pct(sum(r["labse_back_source"] >= 0.7 for r in sp), len(sp))])
write("backtranslation_by_screen_lang.csv", ["screen_lang(T target)", "spans", "back_exact_pct", "back_norm_pct", "labse_mean", "labse_median", "labse_ge_0.7_pct"], data)
out["back"] = data
# back-translation split by agree vs not
data = []
for lab, sel in (("agree", True), ("differ", False)):
    sp = [r for r in main if r["agree_gemma_nllb"] == sel]
    data.append([lab, len(sp), pct(sum(r["back_norm"] for r in sp), len(sp)), round(float(np.mean([r["labse_back_source"] for r in sp])), 4)])
write("backtranslation_by_agreement.csv", ["gemma_nllb", "spans", "back_norm_pct", "labse_mean"], data)
out["back_by_agree"] = data
# short-string diagnostic: span agreement by source length bucket
data = []
for lab, lo, hi in (("1-3 chars", 1, 3), ("4-10", 4, 10), (">10", 11, 10**6)):
    sp = [r for r in main if lo <= len(r["source_text"]) <= hi]
    data.append([lab, len(sp), pct(sum(r["agree_gemma_nllb"] for r in sp), len(sp))])
write("agreement_by_source_length.csv", ["source_len", "spans", "span_agree_pct"], data)
out["len"] = data
out["n_main_spans"], out["n_main_pairs"], out["n_agreed_pairs"] = len(main), len(by), len(agreed)
(W / "agreement_summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps(out, ensure_ascii=False, indent=1))
