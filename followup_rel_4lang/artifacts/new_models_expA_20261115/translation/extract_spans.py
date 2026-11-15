"""Collect the reference spans to machine-translate for condition T.

For every directed pair (item, query language q, GUI language g) used in the
R_stem / R_opts run, each reference span written in q (question stem and A-D
options) is translated q -> g without the screenshot. This script only lists
the unique (text, q, g) jobs and the pair-level span inventory.
"""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

BASE = Path("/Users/baegihyeon/Desktop/CUAI/CUAI_하계 컨퍼런스")
DATA = BASE / "internvl35_prep/mpr-gui-crosslocale/followup_rel_4lang/data/rel_all_366"
MIXED = BASE / "rstem_ropts_qwen3_20261109/addon/followup_rel_4lang/rstem_ropts_inputs/mixed_conditions.jsonl"
LOCK = BASE / "rstem_ropts_qwen3_20261109/addon/followup_rel_4lang/rstem_ropts_inputs/input_lock.json"
OUT = Path(__file__).resolve().parent / "work"
FIELDS = ("question_stem", "A", "B", "C", "D")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    lock = json.loads(LOCK.read_text())
    mappings_path = DATA / "reference_mappings.jsonl"
    if sha256(mappings_path) != lock["reference_mappings_sha256"]:
        sys.exit("reference_mappings.jsonl differs from the R_stem/R_opts input lock")
    if sha256(DATA / "conditions_4lang.jsonl") != lock["conditions_sha256"]:
        sys.exit("conditions_4lang.jsonl differs from the R_stem/R_opts input lock")

    pairs = {}
    for line in MIXED.open(encoding="utf-8"):
        row = json.loads(line)
        pairs[row["pair_id"]] = (row["parallel_id"], row["query_language"], row["gui_language"], row["split"])
    mappings = {}
    for line in mappings_path.open(encoding="utf-8"):
        row = json.loads(line)
        mappings[row["parallel_id"]] = row

    inventory, jobs = [], {}
    for pair_id, (pid, q, g, split) in sorted(pairs.items()):
        spans = mappings[pid]["spans"]
        for field in FIELDS:
            src, tgt = spans[q].get(field, []), spans[g].get(field, [])
            tgt_by_ref = {s["ref_id"]: s["text"] for s in tgt}
            if {s["ref_id"] for s in src} != set(tgt_by_ref):
                sys.exit(f"ref_id mismatch {pair_id}/{field}")
            for s in src:
                key = f"{q}\t{g}\t{s['text']}"
                jobs.setdefault(key, {"src_lang": q, "tgt_lang": g, "text": s["text"], "uses": 0})
                jobs[key]["uses"] += 1
                inventory.append({
                    "pair_id": pair_id, "parallel_id": pid, "split": split,
                    "query_language": q, "gui_language": g, "field": field,
                    "ref_id": s["ref_id"], "source_text": s["text"],
                    "screen_text": tgt_by_ref[s["ref_id"]],
                })

    OUT.mkdir(exist_ok=True)
    with (OUT / "span_inventory.jsonl").open("w", encoding="utf-8") as f:
        for row in inventory:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (OUT / "translation_jobs.jsonl").open("w", encoding="utf-8") as f:
        for key in sorted(jobs):
            f.write(json.dumps(jobs[key], ensure_ascii=False) + "\n")
    report = {
        "pairs": len(pairs),
        "items": len({p[0] for p in pairs.values()}),
        "span_uses": len(inventory),
        "unique_jobs": len(jobs),
        "jobs_by_direction": dict(Counter(f"{j['src_lang']}->{j['tgt_lang']}" for j in jobs.values())),
        "span_uses_by_field": dict(Counter("stem" if r["field"] == "question_stem" else "option" for r in inventory)),
        "inputs": {"reference_mappings_sha256": lock["reference_mappings_sha256"],
                   "mixed_conditions_sha256": sha256(MIXED)},
    }
    (OUT / "extract_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
