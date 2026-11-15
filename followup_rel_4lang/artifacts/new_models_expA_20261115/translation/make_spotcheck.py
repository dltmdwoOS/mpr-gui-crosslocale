"""Human spot-check sample of T translations: 30 unique (source, translation) per target language, main split.

Checkers see only the source name and the machine translation (not the screen text), so the
judgement is about translation meaning, not about matching the screen. The screen text and match
level go to a separate key file for analysis afterwards. Seed fixed.
"""
import csv
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAMES = {"en": "English", "zh": "Chinese", "th": "Thai", "ru": "Russian"}
rows = [json.loads(l) for l in (HERE / "work/T_gemma_spans.jsonl").open(encoding="utf-8")]
uniq = {}
for r in rows:
    if r["split"] == "main" and not r["source_equals_screen"]:
        uniq.setdefault((r["query_language"], r["gui_language"], r["source_text"], r["translation"]), r)
rng = random.Random(20261113)
out = HERE / "spotcheck"
out.mkdir(exist_ok=True)
key = []
for tgt in NAMES:
    pool = sorted(k for k in uniq if k[1] == tgt)
    pick = rng.sample(pool, 30)
    with (out / f"spotcheck_to_{tgt}.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "from", "source name", f"machine translation ({NAMES[tgt]})",
                    "meaning (correct / partly / wrong)", "natural as an app label? (yes / no)", "note"])
        for i, k in enumerate(pick, 1):
            sid = f"{tgt}-{i:02d}"
            w.writerow([sid, NAMES[k[0]], k[2], k[3], "", "", ""])
            r = uniq[k]
            key.append({"id": sid, "pair_id": r["pair_id"], "query_language": k[0], "gui_language": tgt,
                        "source_text": k[2], "translation": k[3], "screen_text": r["screen_text"], "match": r["match"]})
with (out / "spotcheck_key.jsonl").open("w", encoding="utf-8") as f:
    for k in key:
        f.write(json.dumps(k, ensure_ascii=False) + "\n")
print("pool sizes:", {t: sum(1 for k in uniq if k[1] == t) for t in NAMES}, "written:", len(key))
