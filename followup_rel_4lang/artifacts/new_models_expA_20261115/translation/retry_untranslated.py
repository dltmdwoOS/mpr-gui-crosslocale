"""Second-pass translation, two separate outputs (rules fixed before any GPU run; screen text never read).

--mode parsefail     : names of first-pass groups whose output could not be parsed, one name per call.
                       Needed for every T variant (otherwise those pairs have no translation).
--mode untranslated  : names the first pass returned unchanged although the source script differs
                       from the GUI-language script. v2 guards (v1 overwrote brands/abbreviations):
                         * skip names with 2 or fewer letters (D, 1x, Y ...)
                         * prompt asks for a text label, never uses the word "name"
                         * build step reverts a retry output if two different source names of the
                           same pair would get the same translation (build_T.py --revert-collisions)
                       Used only for the sensitivity variant T_retry.
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
    "The following text is a label shown in a mobile or desktop app interface, written in {src}. "
    "Translate it into {tgt} as it would appear in a {tgt} version of the app. You cannot see the screen. "
    "If the text is a brand, product or app name, keep it exactly as it is. Keep digits and symbols unchanged. "
    "Output only a JSON list containing one string.\n\n{items}"
)


def parse_one(text):
    """parse_list for one item; if the JSON is broken by unescaped inner quotes, take the text
    between the first '["' and the last '"]' (single-item lists only)."""
    v = parse_list(text, 1)
    if v is None and '["' in text and '"]' in text:
        inner = text[text.index('["') + 2: text.rindex('"]')]
        if inner.strip():
            v = [inner.strip()]
    return v


def letters(text):
    return sum(ch.isalpha() for ch in text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="gemma")
    ap.add_argument("--mode", required=True, choices=["parsefail", "untranslated"])
    args = ap.parse_args()
    todo, skipped = {}, 0
    if args.mode == "parsefail":
        for line in (HERE / f"work/translations_{args.tag}.jsonl").open(encoding="utf-8"):
            r = json.loads(line)
            if not r["parse_ok"]:
                for text in r["inputs"]:
                    todo[(r["parallel_id"], r["src_lang"], r["tgt_lang"], text)] = True
    else:
        for line in (HERE / f"work/T_{args.tag}_first_spans.jsonl").open(encoding="utf-8"):
            r = json.loads(line)
            if r["untranslated"]:
                if letters(r["source_text"]) <= 2:
                    skipped += 1
                    continue
                todo[(r["parallel_id"], r["query_language"], r["gui_language"], r["source_text"])] = True
    print(args.mode, "names to retry:", len(todo), "span uses skipped (<=2 letters):", skipped, flush=True)
    model, tok = load(snapshot_download(MODEL_ID, revision=REVISION))
    sampler = make_sampler(temp=0.0)
    out = HERE / f"work/translations_{args.tag}_{args.mode}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for pid, s, t, text in sorted(todo):
            user = PROMPT.format(src=NAMES[s], tgt=NAMES[t], items=json.dumps([text], ensure_ascii=False))
            prompt = tok.apply_chat_template([{"role": "user", "content": user}], add_generation_prompt=True, tokenize=False)
            raw = generate(model, tok, prompt=prompt, max_tokens=128, sampler=sampler, verbose=False)
            parsed = parse_one(raw)
            f.write(json.dumps({"parallel_id": pid, "src_lang": s, "tgt_lang": t, "inputs": [text], "raw_output": raw,
                                "translations": parsed, "parse_ok": parsed is not None, "pass": args.mode,
                                "prompt": PROMPT}, ensure_ascii=False) + "\n")
    print("written", out)


if __name__ == "__main__":
    main()
