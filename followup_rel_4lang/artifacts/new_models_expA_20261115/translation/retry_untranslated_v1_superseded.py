"""Second pass for spans the first pass left in the source language (rule fixed before any GPU run).

Selects spans flagged `untranslated` in work/T_<tag>_spans.jsonl (output identical to the source
and the source script differs from the GUI-language script), asks the same model once more with a
stricter one-name prompt, and writes records in the first-pass format so build_T.py can take them
as a later --translations file. If the model again returns the source unchanged, it stays as is
(e.g. brand names) and is reported.
"""
import argparse
import json
from pathlib import Path

from huggingface_hub import snapshot_download
from mlx_lm import generate, load
from mlx_lm.sample_utils import make_sampler

from translate_llm import MODEL_ID, NAMES, REVISION, parse_list

HERE = Path(__file__).resolve().parent
PROMPT = (
    "Translate this name of an element in a mobile or desktop app interface from {src} into {tgt}. "
    "You cannot see the screen. The answer must be written in {tgt}; keep it unchanged only if it is a "
    "brand or product name. Keep digits and symbols unchanged. Output only a JSON list with one string.\n\n{items}"
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="gemma")
    args = ap.parse_args()
    todo = {}
    for line in (HERE / f"work/T_{args.tag}_spans.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if r["untranslated"]:
            todo[(r["parallel_id"], r["query_language"], r["gui_language"], r["source_text"])] = True
    n_untr = len(todo)
    # groups whose first-pass output could not be parsed: retry each name on its own
    for line in (HERE / f"work/translations_{args.tag}.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if not r["parse_ok"]:
            for text in r["inputs"]:
                todo[(r["parallel_id"], r["src_lang"], r["tgt_lang"], text)] = True
    print("spans to retry:", len(todo), "(untranslated", n_untr, "+ parse-failed", len(todo) - n_untr, ")", flush=True)
    model, tok = load(snapshot_download(MODEL_ID, revision=REVISION))
    sampler = make_sampler(temp=0.0)
    out = HERE / f"work/translations_{args.tag}_retry.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for pid, s, t, text in sorted(todo):
            user = PROMPT.format(src=NAMES[s], tgt=NAMES[t], items=json.dumps([text], ensure_ascii=False))
            prompt = tok.apply_chat_template([{"role": "user", "content": user}], add_generation_prompt=True, tokenize=False)
            raw = generate(model, tok, prompt=prompt, max_tokens=128, sampler=sampler, verbose=False)
            parsed = parse_list(raw, 1)
            f.write(json.dumps({"parallel_id": pid, "src_lang": s, "tgt_lang": t, "inputs": [text], "raw_output": raw,
                                "translations": parsed, "parse_ok": parsed is not None, "pass": "retry"},
                               ensure_ascii=False) + "\n")
    print("written", out)


if __name__ == "__main__":
    main()
