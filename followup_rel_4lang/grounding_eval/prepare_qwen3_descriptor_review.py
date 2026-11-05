"""Draft source-substring descriptors for review, without using model predictions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OPENING = "'\"“「«"
CLOSING = "'\"”」»"


def candidate(stem: str, span: dict, language: str) -> tuple[str, dict]:
    start, end = span["start"], span["end"]
    if stem[start:end] != span["text"]:
        raise ValueError("Reference offsets disagree with source")
    left, right = start, end
    while left > 0 and stem[left - 1] in OPENING:
        left -= 1
    while right < len(stem) and stem[right] in CLOSING:
        right += 1
    prefix = stem[:left]
    if language == "en":
        matches = list(re.finditer(r"\b(?:of|from|as|with|than|to|under|above|below|beside|near|around|behind)\s+(?:the\s+)?", prefix, re.IGNORECASE))
        left = matches[-1].end() if matches else left
        suffix = stem[right:]
        stop = re.search(r"[,?;]|\b(?:which|what|where)\b", suffix, re.IGNORECASE)
        right += stop.start() if stop else len(suffix)
    elif language == "zh":
        suffix = stem[right:]
        stop = re.search(r"的?(?:正上方|正下方|上方|下方|左侧|右侧|左边|右边|上面|下面)|相比|相对|[，,？?；;]", suffix)
        right += stop.start() if stop else len(suffix)
    elif language == "th":
        matches = list(re.finditer(r"ปุ่ม|แท็บ|ไอคอน|ส่วน|ข้อความ|คำว่า|ชื่อ|เมนู|ตัวเลือก|หัวข้อ|สวิตช์|ป้ายกำกับ|ช่อง|รายการ|โหมด|คอลัมน์|การตั้งค่า|องค์ประกอบ|การสลับ|การ์ด|แอป|ลิงก์", prefix))
        if matches and left - matches[-1].start() < 90:
            possible = matches[-1].start()
            # A nearby noun can name the question's answer instead of its reference.
            if "ใด" not in stem[possible:left]:
                left = possible
    elif language == "ru":
        matches = list(re.finditer(r"\b(?:кнопк\w*|значк\w*|вкладк\w*|раздел\w*|пункт\w*|метк\w*|текст\w*|переключател\w*|списк\w*|заголов\w*|меню|пол[ея]\w*|слов\w*|икон\w*|опци\w*)", prefix, re.IGNORECASE))
        if matches and left - matches[-1].start() < 90:
            left = matches[-1].start()
        suffix = stem[right:]
        stop = re.search(r"[,?;]|\b(?:какой|какая|какое|какие|что|где)\b", suffix, re.IGNORECASE)
        right += stop.start() if stop else len(suffix)
    while left < start and stem[left].isspace():
        left += 1
    while right > end and stem[right - 1].isspace():
        right -= 1
    template = stem[left:start] + "{ref}" + stem[end:right]
    if template.format(ref=span["text"]) != stem[left:right]:
        raise ValueError("Candidate is not an exact source substring")
    query_words = re.search(r"\b(?:which|what|where|какой|какая|какое|какие)\b|哪个|什么|ใด", template, re.IGNORECASE)
    flags = ["source_language_review_needed"]
    if query_words:
        flags.append("possible_relation_question_remaining")
    if template.strip("'\"“”「」«» ") == "{ref}":
        flags.append("reference_only_context_missing")
    return template, {"source_start": left, "source_end": right, "flags": flags}


def build() -> dict:
    manifest_path = REPO / "annotation/rel_grounding/data/full_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    gt = json.loads((HERE / "annotations_20261103/grounding_gt_draft_170.json").read_text())
    ids = set(gt["annotations"]) - set(gt["gt_assembly"]["pilot_item_ids"])
    descriptors, review = {}, []
    for item in manifest["items"]:
        pid = item["parallel_id"]
        if pid not in ids:
            continue
        descriptors[pid] = {}
        for language in ("en", "zh", "th", "ru"):
            locale = item["locales"][language]
            template, details = candidate(locale["question_stem"], locale["stem_span"], language)
            descriptors[pid][language] = template
            review.append({"parallel_id": pid, "language": language,
                           "question_stem": locale["question_stem"], "reference_span": locale["stem_span"],
                           "candidate_template": template, "reviewed": False, **details})
    assert len(descriptors) == 158 and len(review) == 632
    return {"schema": "qwen3-main-descriptor-review-draft-v1", "reviewed": False,
            "note": "Machine-extracted source substrings. Not finalized main-experiment descriptions; no model predictions used.",
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "descriptors": descriptors, "review": review}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a fresh review output path")
    result = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"items": len(result["descriptors"]), "review_rows": len(result["review"]),
                      "possible_question_remaining": sum("possible_relation_question_remaining" in r["flags"]
                                                         for r in result["review"]),
                      "reference_only": sum("reference_only_context_missing" in r["flags"]
                                            for r in result["review"])}, indent=2))


if __name__ == "__main__":
    main()
