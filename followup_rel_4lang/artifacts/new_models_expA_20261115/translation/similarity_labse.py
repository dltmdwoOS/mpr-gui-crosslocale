"""Meaning similarity between each T translation and the screen text (official localized label).

LaBSE cosine similarity, computed for every span use, fixed before any GPU run. Used to split
'different' spans into meaning-preserving vs not, so R-T can be read within meaning-preserving
spans. Source-to-screen similarity is also stored as a reference (how close the original-language
name is to the screen label in meaning).
"""
import json
from pathlib import Path

import numpy as np
import sentence_transformers
from huggingface_hub import snapshot_download
from sentence_transformers import SentenceTransformer

MODEL_ID = "sentence-transformers/LaBSE"
HERE = Path(__file__).resolve().parent

rows = [json.loads(l) for l in (HERE / "work/T_gemma_spans.jsonl").open(encoding="utf-8")]
path = snapshot_download(MODEL_ID, ignore_patterns=["*.h5", "*.onnx", "onnx/*", "openvino/*", "tf_model*", "*.msgpack", "pytorch_model.bin"])
model = SentenceTransformer(path, device="cpu")
texts = sorted({t for r in rows for t in (r["translation"], r["screen_text"], r["source_text"])})
emb = model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
idx = {t: i for i, t in enumerate(texts)}
cos = lambda a, b: float(np.dot(emb[idx[a]], emb[idx[b]]))
with (HERE / "work/T_gemma_similarity.jsonl").open("w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps({"pair_id": r["pair_id"], "field": r["field"], "ref_id": r["ref_id"],
                            "sim_T_screen": round(cos(r["translation"], r["screen_text"]), 4),
                            "sim_source_screen": round(cos(r["source_text"], r["screen_text"]), 4)},
                           ensure_ascii=False) + "\n")
meta = {"model_id": MODEL_ID, "revision": Path(path).name, "sentence_transformers": sentence_transformers.__version__,
        "normalize": True, "n_texts": len(texts)}
(HERE / "work/T_gemma_similarity_meta.json").write_text(json.dumps(meta, indent=1))
print(meta)
