"""Audit of cross-language reference mappings (no GPU, fixed before any T run).

The mapping pairs quoted reference names across the four language versions of a question by
order within each field (ref_id = field:index); it was not checked against screenshots.
For each ref, LaBSE similarity is computed for all 6 language pairs. Two automatic flags:
  swap  - within a field with 2+ refs, a different-index name in another language matches
          better than the paired one (order of quotes differs between languages)
  low   - minimum pairwise similarity of the ref below 0.5
Flagged refs are then reviewed by hand (review file written separately).
"""
import itertools
import json
from pathlib import Path

import numpy as np
from huggingface_hub import snapshot_download
from sentence_transformers import SentenceTransformer

DATA = Path("/Users/baegihyeon/Desktop/CUAI/CUAI_하계 컨퍼런스/internvl35_prep/mpr-gui-crosslocale/followup_rel_4lang/data/rel_all_366")
HERE = Path(__file__).resolve().parent
LANGS = ("en", "zh", "th", "ru")
pids = {json.loads(l)["parallel_id"] for l in (HERE / "work/span_inventory.jsonl").open(encoding="utf-8")}
refs = {}
for line in (DATA / "reference_mappings.jsonl").open(encoding="utf-8"):
    m = json.loads(line)
    if m["parallel_id"] not in pids:
        continue
    for lang in LANGS:
        for field, ss in m["spans"][lang].items():
            for s in ss:
                refs.setdefault((m["parallel_id"], s["ref_id"]), {"field": field})[lang] = s["text"]
path = snapshot_download("sentence-transformers/LaBSE", ignore_patterns=["*.h5", "*.onnx", "onnx/*", "openvino/*", "tf_model*", "*.msgpack", "pytorch_model.bin"])
model = SentenceTransformer(path, device="cpu")
texts = sorted({v[l] for v in refs.values() for l in LANGS})
E = model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
ix = {t: i for i, t in enumerate(texts)}
sim = lambda a, b: float(E[ix[a]] @ E[ix[b]])
by_field = {}
for (pid, rid), v in refs.items():
    by_field.setdefault((pid, v["field"]), []).append(rid)
out = []
for (pid, rid), v in sorted(refs.items()):
    pair_sims = {f"{a}-{b}": round(sim(v[a], v[b]), 3) for a, b in itertools.combinations(LANGS, 2)}
    swap = []
    for other in by_field[(pid, v["field"])]:
        if other == rid:
            continue
        o = refs[(pid, other)]
        for a, b in itertools.permutations(LANGS, 2):
            if sim(v[a], o[b]) > sim(v[a], v[b]) + 0.05:
                swap.append(f"{a}:{rid}~{b}:{other}")
    out.append({"parallel_id": pid, "ref_id": rid, "field": v["field"], **{l: v[l] for l in LANGS},
                "min_sim": min(pair_sims.values()), "pair_sims": pair_sims, "swap_hits": swap,
                "flag_swap": bool(swap), "flag_low": min(pair_sims.values()) < 0.5})
with (HERE / "work/mapping_audit_auto.jsonl").open("w", encoding="utf-8") as f:
    for r in out:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("refs", len(out), "flag_swap", sum(r["flag_swap"] for r in out), "flag_low", sum(r["flag_low"] for r in out),
      "either", sum(r["flag_swap"] or r["flag_low"] for r in out))
