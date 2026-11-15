"""Build condition T (reference names machine-translated without the screen) and a span table.

T is built exactly like R: start from the O question of the pair and replace every mapped
reference span (stem and A-D options) - R puts the screen text there, T puts the machine
translation. Before writing T, the same replacement code with screen text must reproduce
the stored R question character for character for every pair (self-check).

Usage: python3 -I build_T.py --translations work/translations_gemma.jsonl --tag gemma
"""
import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

BASE = Path("/Users/baegihyeon/Desktop/CUAI/CUAI_하계 컨퍼런스")
DATA = BASE / "internvl35_prep/mpr-gui-crosslocale/followup_rel_4lang/data/rel_all_366"
MIXED = BASE / "rstem_ropts_qwen3_20261109/addon/followup_rel_4lang/rstem_ropts_inputs/mixed_conditions.jsonl"
HERE = Path(__file__).resolve().parent
FIELDS = ("question_stem", "A", "B", "C", "D")
SCRIPT = {"en": "LATIN", "ru": "CYRILLIC", "th": "THAI", "zh": "CJK"}


def require(ok, msg):
    if not ok:
        sys.exit("FAILED: " + msg)


def script_of(text):
    counts = Counter()
    for ch in text:
        if ch.isalpha():
            name = unicodedata.name(ch, "")
            for key in ("LATIN", "CYRILLIC", "THAI", "CJK"):
                if name.startswith(key) or (key == "CJK" and "CJK" in name):
                    counts[key] += 1
    return counts.most_common(1)[0][0] if counts else None


def norm(text):
    t = unicodedata.normalize("NFKC", text).casefold().strip()
    t = re.sub(r"[\"'“”«»「」『』‘’]", "", t)
    t = re.sub(r"[\s ]+", " ", t)
    return t.rstrip(".。!！?？ ")


def match_level(translation, screen):
    if translation == screen:
        return "exact"
    if norm(translation) == norm(screen):
        return "normalized"
    return "different"


def replace_spans(text, spans, replacement_by_ref):
    out = text
    for s in sorted(spans, key=lambda v: v["start"], reverse=True):
        require(out[s["start"]:s["end"]] == s["text"], f"offset differs: {s}")
        out = out[:s["start"]] + replacement_by_ref[s["ref_id"]] + out[s["end"]:]
    return out


def render_question(stem, options):
    return stem + " " + " ".join(f"{k}: {options[k]}" for k in "ABCD")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--translations", required=True, nargs="+",
                    help="one or more files; later files override earlier ones (retry pass)")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--allow-missing", action="store_true", help="smoke: skip pairs without translations")
    ap.add_argument("--revert-collisions", default=None,
                    help="translation file whose outputs are reverted to the earlier value when two different "
                         "source names of the same pair would get the same translation (screen-blind rule)")
    args = ap.parse_args()

    trans, earlier = {}, {}
    for path in args.translations:
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            if not r.get("parse_ok", True):
                continue
            for src, tr in zip(r["inputs"], r["translations"]):
                key = (r["parallel_id"], r["src_lang"], r["tgt_lang"], src)
                if args.revert_collisions and path == args.revert_collisions and key in trans:
                    earlier[key] = trans[key]
                trans[key] = tr
    reverted = []
    if args.revert_collisions:
        by_group = {}
        for key, tr in trans.items():
            by_group.setdefault(key[:3], {}).setdefault(tr, []).append(key)
        for grp in by_group.values():
            for tr, keys in grp.items():
                if len(keys) > 1:
                    for key in keys:
                        if key in earlier:
                            trans[key] = earlier[key]
                            reverted.append(list(key) + [tr])

    mappings = {json.loads(l)["parallel_id"]: json.loads(l) for l in open(DATA / "reference_mappings.jsonl", encoding="utf-8")}
    cond = {}
    for line in open(DATA / "conditions_4lang.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r["condition"] in ("O", "R"):
            cond[(r["parallel_id"], r["query_language"], r["gui_language"], r["condition"])] = r
    mixed = {}
    for line in open(MIXED, encoding="utf-8"):
        r = json.loads(line)
        mixed.setdefault(r["pair_id"], r)

    rows, span_rows, skipped, dup_opts = [], [], 0, []
    for pair_id in sorted(mixed):
        m = mixed[pair_id]
        pid, q, g = m["parallel_id"], m["query_language"], m["gui_language"]
        O, R = cond[(pid, q, g, "O")], cond[(pid, q, g, "R")]
        sp = mappings[pid]["spans"]
        screen_by_ref = {s["ref_id"]: s["text"] for f in FIELDS for s in sp[g].get(f, [])}
        # self-check: screen-text replacement reproduces stored R exactly
        r_stem = replace_spans(O["question_stem"], sp[q]["question_stem"], screen_by_ref)
        r_opts = {k: replace_spans(O["options"][k], sp[q].get(k, []), screen_by_ref) for k in "ABCD"}
        require(r_stem == R["question_stem"] and r_opts == R["options"], f"R reconstruction {pair_id}")
        require(m["image_path"].endswith(O["image_path"]) and m["gold_answer"] == O["gold_answer"], f"image/gold {pair_id}")

        src_spans = [(f, s) for f in FIELDS for s in sp[q].get(f, [])]
        if any((pid, q, g, s["text"]) not in trans for _, s in src_spans):
            require(args.allow_missing, f"missing translation {pair_id}")
            skipped += 1
            continue
        t_by_ref = {s["ref_id"]: trans[(pid, q, g, s["text"])] for _, s in src_spans}
        t_stem = replace_spans(O["question_stem"], sp[q]["question_stem"], t_by_ref)
        t_opts = {k: replace_spans(O["options"][k], sp[q].get(k, []), t_by_ref) for k in "ABCD"}
        if len(set(t_opts.values())) < 4 and len(set(O["options"].values())) == 4:
            dup_opts.append(pair_id)
        rows.append({"pair_id": pair_id, "parallel_id": pid, "split": m["split"], "query_language": q,
                     "gui_language": g, "condition": f"T_{args.tag}", "image_path": m["image_path"],
                     "image_sha256": m["image_sha256"], "gold_answer": m["gold_answer"],
                     "question_stem": t_stem, "options": t_opts, "question": render_question(t_stem, t_opts)})
        for f, s in src_spans:
            tr, scr = t_by_ref[s["ref_id"]], screen_by_ref[s["ref_id"]]
            span_rows.append({"pair_id": pair_id, "parallel_id": pid, "split": m["split"], "query_language": q,
                              "gui_language": g, "field": f, "ref_id": s["ref_id"], "source_text": s["text"],
                              "translation": tr, "screen_text": scr, "match": match_level(tr, scr),
                              "source_equals_screen": s["text"] == scr,
                              "untranslated": tr == s["text"] and script_of(s["text"]) not in (None, SCRIPT[g]),
                              "output_script": script_of(tr)})

    out = HERE / "work"
    with (out / f"T_{args.tag}_conditions.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (out / f"T_{args.tag}_spans.jsonl").open("w", encoding="utf-8") as f:
        for r in span_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    main_spans = [r for r in span_rows if r["split"] == "main"]
    stem_main = [r for r in main_spans if r["field"] == "question_stem"]
    rep = {
        "pairs_written": len(rows), "pairs_skipped": skipped, "R_self_check": "all pairs reproduced",
        "main_span_uses": len(main_spans),
        "match_main_all": dict(Counter(r["match"] for r in main_spans)),
        "match_main_stem": dict(Counter(r["match"] for r in stem_main)),
        "untranslated_main": sum(r["untranslated"] for r in main_spans),
        "match_main_by_gui": {gl: dict(Counter(r["match"] for r in main_spans if r["gui_language"] == gl)) for gl in SCRIPT},
        "reverted_collisions": reverted,
        "pairs_T_options_not_distinct_while_O_distinct": dup_opts,
        "translations_sha256": {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in args.translations},
    }
    (out / f"T_{args.tag}_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
