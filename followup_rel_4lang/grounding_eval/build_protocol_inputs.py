"""Build locked, outcome-blind grounding and mixed REL inputs from the annotated frame."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

if __package__:
    from .audit_annotations import HERE, PACKAGE, REPO, audit, require, sha256
else:
    from audit_annotations import HERE, PACKAGE, REPO, audit, require, sha256


LANGUAGES = ("en", "zh", "th", "ru")
PILOT_PAIRS = (("en", "zh"), ("zh", "th"), ("th", "ru"), ("ru", "en"))
QWEN_USER_PROMPT_TEMPLATE = (
    "Locate the GUI reference element marked with <ref>...</ref> in the question below. "
    "The marked expression may be in a different language from the screenshot. "
    "Use surrounding words to identify the marked element. "
    "Do not locate the element that the question asks for.\n"
    "Question: {marked_stem}\n"
    "The screenshot is {model_width} pixels wide and {model_height} pixels high. "
    "Give one point inside the marked reference element using integer pixel coordinates "
    "on this screenshot, with (0, 0) at the top-left. "
    "Return only this JSON array: [{{\"point_2d\": [x, y]}}]. "
    "No explanation or code fence."
)
INTERNVL_SYSTEM_PROMPT = (
    "Locate one reference element in the full GUI screenshot. "
    "Return exactly one bounding box as <box>[[x1, y1, x2, y2]]</box>. "
    "Use integer coordinates normalized from 0 to 1000 over the full screenshot, "
    "with (0, 0) at the top-left and (1000, 1000) at the bottom-right. "
    "Do not add any other text."
)
INTERNVL_USER_TEMPLATE = (
    "Question: {marked_stem}\n"
    "Locate the reference GUI element described by the marked expression and its surrounding words. "
    "Do not answer the relation question."
)


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def render_question(stem: str, options: dict[str, str]) -> str:
    return stem + " " + " ".join(f"{letter}: {options[letter]}" for letter in "ABCD")


def mark_span(stem: str, start: int, end: int, replacement: str) -> str:
    return stem[:start] + "<ref>" + replacement + "</ref>" + stem[end:]


def render_qwen_user_prompt(marked_stem: str, model_width: int, model_height: int) -> str:
    if model_width <= 0 or model_height <= 0:
        raise ValueError("Qwen model image dimensions must be positive")
    if marked_stem.count("<ref>") != 1 or marked_stem.count("</ref>") != 1:
        raise ValueError("Expected one marked reference expression")
    return QWEN_USER_PROMPT_TEMPLATE.format(
        marked_stem=marked_stem, model_width=model_width, model_height=model_height,
    )


def replace_mapped_spans(text: str, source: list[dict], target: list[dict], key: str) -> str:
    replacements = {span["ref_id"]: span["text"] for span in target}
    require(len(replacements) == len(target) and
            {span["ref_id"] for span in source} == set(replacements),
            f"Option reference mapping differs: {key}")
    result = text
    for span in sorted(source, key=lambda value: value["start"], reverse=True):
        require(result[span["start"]:span["end"]] == span["text"],
                f"Option reference offset differs: {key}")
        result = result[:span["start"]] + replacements[span["ref_id"]] + result[span["end"]:]
    return result


def build() -> tuple[list[dict], list[dict], list[dict], dict]:
    summary = audit()
    gt = json.loads((PACKAGE / "grounding_gt_draft_170.json").read_text(encoding="utf-8"))
    manifest = json.loads((REPO / "annotation/rel_grounding/data/full_manifest.json").read_text(encoding="utf-8"))
    manifest_by_id = {item["parallel_id"]: item for item in manifest["items"]}
    pilot = set(gt["gt_assembly"]["pilot_item_ids"])
    selected = set(gt["annotations"])
    data = REPO / "followup_rel_4lang/data/rel_all_366"
    conditions = data / "conditions_4lang.jsonl"
    mappings = data / "reference_mappings.jsonl"
    by_key = defaultdict(dict)
    for row in read_jsonl(conditions):
        if row["parallel_id"] in selected and row["query_language"] != row["gui_language"]:
            key = (row["parallel_id"], row["query_language"], row["gui_language"])
            require(row["condition"] not in by_key[key], f"Duplicate condition: {key}")
            by_key[key][row["condition"]] = row
    by_mapping = {row["parallel_id"]: row for row in read_jsonl(mappings)}

    grounding: list[dict] = []
    mixed: list[dict] = []
    for pid in sorted(selected):
        source_gui_pairs = PILOT_PAIRS if pid in pilot else tuple(
            (q, g) for q in LANGUAGES for g in LANGUAGES if q != g
        )
        for source, gui in source_gui_pairs:
            pair_id = f"{pid}::{source}::{gui}"
            rows = by_key[pid, source, gui]
            require(set(rows) == {"O", "R", "C", "F"}, f"Incomplete quartet: {pair_id}")
            original, localized = rows["O"], rows["R"]
            require(all(row["source_issue"] is None and row["text_dependency"] == "dependent"
                        for row in rows.values()), f"Ineligible quartet: {pair_id}")
            require(original["image_path"] == localized["image_path"] and
                    original["gold_answer"] == localized["gold_answer"] and
                    original["option_order"] == localized["option_order"] == list("ABCD"),
                    f"Image/gold/order differs: {pair_id}")
            mapping = by_mapping[pid]
            source_span = mapping["spans"][source]["question_stem"]
            gui_span = mapping["spans"][gui]["question_stem"]
            require(len(source_span) == len(gui_span) == 1 and
                    source_span[0]["ref_id"] == gui_span[0]["ref_id"],
                    f"Reference span differs: {pair_id}")
            span = source_span[0]
            stem = original["question_stem"]
            require(stem[span["start"]:span["end"]] == span["text"],
                    f"Source offset differs: {pair_id}")
            replacement = gui_span[0]["text"]
            require(stem[:span["start"]] + replacement + stem[span["end"]:]
                    == localized["question_stem"], f"R stem reconstruction differs: {pair_id}")
            for letter in "ABCD":
                rebuilt = replace_mapped_spans(
                    original["options"][letter], mapping["spans"][source].get(letter, []),
                    mapping["spans"][gui].get(letter, []), f"{pair_id}/{letter}",
                )
                require(rebuilt == localized["options"][letter],
                        f"R option reconstruction differs: {pair_id}/{letter}")
            require(original["question"] == render_question(stem, original["options"]) and
                    localized["question"] == render_question(localized["question_stem"], localized["options"]),
                    f"Original question template differs: {pair_id}")
            image_locale = manifest_by_id[pid]["locales"][gui]
            require(original["image_path"] == image_locale["image_path"],
                    f"Image path differs: {pair_id}")
            marked_original = mark_span(stem, span["start"], span["end"], span["text"])
            marked_localized = mark_span(stem, span["start"], span["end"], replacement)
            split = "pilot" if pid in pilot else "main"
            grounding.append({
                "pair_id": pair_id, "parallel_id": pid, "split": split,
                "query_language": source, "gui_language": gui,
                "image_path": "followup_rel_4lang/" + original["image_path"],
                "image_sha256": image_locale["image_sha256"],
                "question_O": marked_original, "question_R": marked_localized,
                "internvl_user_prompt_O": INTERNVL_USER_TEMPLATE.format(marked_stem=marked_original),
                "internvl_user_prompt_R": INTERNVL_USER_TEMPLATE.format(marked_stem=marked_localized),
            })
            for condition, mixed_stem, mixed_options in (
                ("R_stem", localized["question_stem"], original["options"]),
                ("R_opts", stem, localized["options"]),
            ):
                mixed.append({
                    "pair_id": pair_id, "parallel_id": pid, "split": split,
                    "query_language": source, "gui_language": gui,
                    "condition": condition,
                    "image_path": "followup_rel_4lang/" + original["image_path"],
                    "image_sha256": image_locale["image_sha256"],
                    "gold_answer": original["gold_answer"],
                    "question_stem": mixed_stem, "options": mixed_options,
                    "question": render_question(mixed_stem, mixed_options),
                })
    require(len(grounding) == 1944 and len(mixed) == 3888,
            "Unexpected selected pair/condition counts")

    controls = []
    for gui in LANGUAGES:
        for pid in ("rel::1/booking_1.jpg", "rel::5/message_1.jpg"):
            locale = manifest_by_id[pid]["locales"][gui]
            span = locale["stem_span"]
            marked = mark_span(locale["question_stem"], span["start"], span["end"], span["text"])
            controls.append({
                "parallel_id": pid, "gui_language": gui,
                "image_path": "followup_rel_4lang/" + locale["image_path"],
                "image_sha256": locale["image_sha256"],
                "question": marked,
                "internvl_user_prompt": INTERNVL_USER_TEMPLATE.format(marked_stem=marked),
            })
    provenance = {
        "schema": "rel-grounding-protocol-inputs-v3",
        "annotation_audit": summary,
        "conditions_sha256": sha256(conditions),
        "reference_mappings_sha256": sha256(mappings),
        "qwen_user_prompt_template": QWEN_USER_PROMPT_TEMPLATE,
        "internvl_system_prompt": INTERNVL_SYSTEM_PROMPT,
        "internvl_user_prompt_template": INTERNVL_USER_TEMPLATE,
        "model_output_contracts": {
            "qwen2_5_vl_7b": "one point_2d JSON object (prefer one-element array) in final image_grid_thw * 14 pixel coordinates, no system prompt",
            "internvl2_5_8b": "single <box> with 0-1000 full-image normalized coordinates",
        },
        "pilot_pair_order": list(PILOT_PAIRS),
        "pilot_positive_controls": len(controls),
        "grounding_pair_counts": {"main": 1896, "pilot": 48},
        "mixed_condition_counts": {"main": 3792, "pilot": 96},
    }
    return grounding, mixed, controls, provenance


def write_immutable(path: Path, content: str) -> None:
    if path.exists():
        require(path.read_text(encoding="utf-8") == content,
                f"Existing locked input differs; choose a new output directory: {path}")
        return
    path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=REPO / "followup_rel_4lang/results/grounding_protocol_inputs_v3")
    args = parser.parse_args()
    grounding, mixed, controls, provenance = build()
    paths = {
        "grounding_pairs.jsonl": grounding,
        "mixed_conditions.jsonl": mixed,
        "positive_controls.jsonl": controls,
    }
    contents = {
        name: "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        for name, rows in paths.items()
    }
    provenance["generated_sha256"] = {
        name: hashlib.sha256(content.encode("utf-8")).hexdigest()
        for name, content in contents.items()
    }
    lock_content = json.dumps(provenance, ensure_ascii=False, indent=2) + "\n"
    lock_path = HERE / "input_lock.json"
    require(lock_path.is_file() and lock_path.read_text(encoding="utf-8") == lock_content,
            f"Generated inputs differ from tracked protocol lock: {lock_path}")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name, content in contents.items():
        write_immutable(output / name, content)
    write_immutable(output / "input_lock.json", lock_content)
    print(json.dumps({"output_dir": str(output), "grounding_pairs": len(grounding),
                      "mixed_conditions": len(mixed), "positive_controls": len(controls),
                      "generated_sha256": provenance["generated_sha256"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
