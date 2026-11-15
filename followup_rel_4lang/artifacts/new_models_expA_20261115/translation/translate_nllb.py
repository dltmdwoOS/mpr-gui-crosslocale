"""Translate reference spans with NLLB-200 (text only, no screenshot).

Usage: .venv/bin/python translate_nllb.py [--limit-per-direction N] [--out FILE]
Deterministic: beam search, no sampling. Model revision is pinned and recorded.
Already-translated jobs in --out are skipped, so a stopped run can resume.
"""
import argparse
import json
import platform
import time
from pathlib import Path

import torch
import transformers
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

MODEL_ID = "facebook/nllb-200-distilled-1.3B"
CODES = {"en": "eng_Latn", "zh": "zho_Hans", "th": "tha_Thai", "ru": "rus_Cyrl"}
GEN = {"num_beams": 4, "do_sample": False, "max_new_tokens": 64}
HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-per-direction", type=int, default=0)
    ap.add_argument("--out", default=str(HERE / "work/translations_nllb.jsonl"))
    ap.add_argument("--revision", default=None)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    jobs = [json.loads(l) for l in (HERE / "work/translation_jobs.jsonl").open(encoding="utf-8")]
    if args.limit_per_direction:
        seen, picked = {}, []
        for j in jobs:
            d = (j["src_lang"], j["tgt_lang"])
            if seen.get(d, 0) < args.limit_per_direction:
                seen[d] = seen.get(d, 0) + 1
                picked.append(j)
        jobs = picked
    out = Path(args.out)
    done = set()
    if out.exists():
        for l in out.open(encoding="utf-8"):
            r = json.loads(l)
            done.add((r["src_lang"], r["tgt_lang"], r["text"]))
    jobs = [j for j in jobs if (j["src_lang"], j["tgt_lang"], j["text"]) not in done]

    from huggingface_hub import snapshot_download
    path = snapshot_download(MODEL_ID, revision=args.revision)
    revision = Path(path).name
    tok = AutoTokenizer.from_pretrained(path)
    model = AutoModelForSeq2SeqLM.from_pretrained(path, torch_dtype=torch.float32).to(args.device).eval()
    meta = {"model_id": MODEL_ID, "revision": revision, "generation": GEN, "torch": torch.__version__,
            "transformers": transformers.__version__, "device": args.device, "platform": platform.platform()}
    (out.parent / (out.stem + "_meta.json")).write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta), flush=True)

    groups = {}
    for j in jobs:
        groups.setdefault((j["src_lang"], j["tgt_lang"]), []).append(j)
    t0, n = time.time(), 0
    with out.open("a", encoding="utf-8") as f:
        for (s, t), items in sorted(groups.items()):
            tok.src_lang = CODES[s]
            bos = tok.convert_tokens_to_ids(CODES[t])
            for i in range(0, len(items), args.batch_size):
                chunk = items[i:i + args.batch_size]
                enc = tok([c["text"] for c in chunk], return_tensors="pt", padding=True).to(args.device)
                with torch.no_grad():
                    gen = model.generate(**enc, forced_bos_token_id=bos, **GEN)
                outs = tok.batch_decode(gen, skip_special_tokens=True)
                for c, o in zip(chunk, outs):
                    f.write(json.dumps({"src_lang": s, "tgt_lang": t, "text": c["text"],
                                        "translation": o.strip(), "model_revision": revision},
                                       ensure_ascii=False) + "\n")
                f.flush()
                n += len(chunk)
                print(f"{s}->{t} {n}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
