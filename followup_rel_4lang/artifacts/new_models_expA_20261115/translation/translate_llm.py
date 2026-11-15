"""Translate reference spans with a local open LLM (Gemma 3, MLX). Text only, no screenshot.

One call per (item, source language, target language): all reference spans of that
item in the source language are sent together as a JSON list, so labels from the same
screen are translated consistently. Greedy decoding. Raw prompts and outputs are saved.

Usage: .venv/bin/python translate_llm.py [--items N] [--out FILE]
A stopped run resumes: groups already in --out are skipped.
"""
import argparse
import json
import platform
import re
import time
from pathlib import Path

import mlx_lm
from huggingface_hub import snapshot_download
from mlx_lm import generate, load
from mlx_lm.sample_utils import make_sampler

MODEL_ID = "mlx-community/gemma-3-12b-it-4bit"
REVISION = "86cc6a8dedbc456dd0e4af01a9d09f396f77e558"
NAMES = {"en": "English", "zh": "Simplified Chinese", "th": "Thai", "ru": "Russian"}
HERE = Path(__file__).resolve().parent
INSTRUCTION = (
    "You translate names of elements shown in a mobile or desktop app interface from {src} to {tgt}.\n"
    "You cannot see the screen. Translate each name the way it would most naturally appear in a {tgt} app.\n"
    "Rules: keep numbers, times, dates written with digits, symbols, and brand or product names unchanged; "
    "do not add explanations, quotes, or punctuation that is not in the original; "
    "if a name has nothing to translate, return it unchanged.\n"
    "Input is a JSON list of {n} names. Output only a JSON list of exactly {n} strings in the same order.\n\n"
    "{items}"
)


def groups_from_inventory():
    groups = {}
    for line in (HERE / "work/span_inventory.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        key = (r["parallel_id"], r["query_language"], r["gui_language"])
        texts = groups.setdefault(key, [])
        if r["source_text"] not in texts:
            texts.append(r["source_text"])
    return groups


def parse_list(text, n):
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return None
    try:
        val = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(val, list) or len(val) != n or not all(isinstance(v, str) for v in val):
        return None
    return [v.strip() for v in val]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", type=int, default=0, help="limit to the first N items (smoke)")
    ap.add_argument("--out", default=str(HERE / "work/translations_gemma.jsonl"))
    args = ap.parse_args()

    groups = groups_from_inventory()
    keys = sorted(groups)
    if args.items:
        keep = sorted({k[0] for k in keys})[: args.items]
        keys = [k for k in keys if k[0] in keep]
    out = Path(args.out)
    done = set()
    if out.exists():
        for line in out.open(encoding="utf-8"):
            r = json.loads(line)
            done.add((r["parallel_id"], r["src_lang"], r["tgt_lang"]))
    keys = [k for k in keys if k not in done]

    path = snapshot_download(MODEL_ID, revision=REVISION)
    model, tok = load(path)
    sampler = make_sampler(temp=0.0)
    meta = {"model_id": MODEL_ID, "revision": REVISION, "decoding": "greedy (temp 0)", "max_tokens": 512,
            "mlx_lm": mlx_lm.__version__, "platform": platform.platform(), "instruction": INSTRUCTION}
    (out.parent / (out.stem + "_meta.json")).write_text(json.dumps(meta, ensure_ascii=False, indent=1))

    t0 = time.time()
    with out.open("a", encoding="utf-8") as f:
        for i, (pid, s, t) in enumerate(keys, 1):
            texts = groups[(pid, s, t)]
            user = INSTRUCTION.format(src=NAMES[s], tgt=NAMES[t], n=len(texts),
                                      items=json.dumps(texts, ensure_ascii=False))
            prompt = tok.apply_chat_template([{"role": "user", "content": user}],
                                             add_generation_prompt=True, tokenize=False)
            raw = generate(model, tok, prompt=prompt, max_tokens=512, sampler=sampler, verbose=False)
            parsed = parse_list(raw, len(texts))
            f.write(json.dumps({"parallel_id": pid, "src_lang": s, "tgt_lang": t, "inputs": texts,
                                "raw_output": raw, "translations": parsed, "parse_ok": parsed is not None},
                               ensure_ascii=False) + "\n")
            f.flush()
            if i % 10 == 0 or i == len(keys):
                el = time.time() - t0
                print(f"{i}/{len(keys)} groups, {el:.0f}s, eta {el / i * (len(keys) - i) / 60:.0f} min", flush=True)


if __name__ == "__main__":
    main()
