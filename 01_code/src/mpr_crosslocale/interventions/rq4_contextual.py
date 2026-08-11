from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from mpr_crosslocale.data.schema import LABELS
from mpr_crosslocale.interventions.rq4_nllb import (
    EXPECTED_DIRECTIONS,
    EXPECTED_INTERVENTION_ROWS,
    EXPECTED_REL_ITEMS,
    build_translation_plan,
    render_with_source_layout,
)

CONTEXTUAL_MODEL_ID = "Qwen/Qwen3-8B"
CONTEXTUAL_REVISION = "47719a242beab8f9aecc40ce3928b034dd5dd559"
CONTEXTUAL_CONDITION = "contextual_query_aligned"
PROMPT_TEMPLATE_VERSION = "rq4_contextual_translation_v2"
METHOD_NAME = "full_mcq_contextual_structured_json"
EXPECTED_SMOKE_ROWS = EXPECTED_DIRECTIONS * 2

SYSTEM_PROMPT = """You are a professional translator for multilingual GUI multiple-choice questions.

Translate the complete MCQ from the declared source language to the declared target language.

Rules:
1. Translate the question and all four options faithfully.
2. Do not answer, solve, explain, or improve the question.
3. Preserve the option keys A, B, C, and D exactly and in that order.
4. Do not add, remove, merge, split, normalize, or reorder options.
5. Preserve every spatial relation exactly, including directly, above, below, left, right, inside, and between.
6. Preserve negation exactly.
7. Preserve numbers, percentages, file formats, product names, app names, and proper nouns unless they have an established target-language form.
8. Translate ordinary GUI labels faithfully, but do not invent a label.
9. Do not correct, normalize, or improve the semantic content of any answer option, even if an option appears awkward, implausible, or inconsistent with the question. Translate each option exactly as written.
10. Return only one JSON object with exactly the requested keys. Do not use Markdown fences."""

OUTPUT_SHAPE = {
    "question_stem": "string",
    "options": {"A": "string", "B": "string", "C": "string", "D": "string"},
}

FILE_FORMAT_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:PDF|URL|URI|HTML|JPEG|JPG|PNG|GIF|SVG|MP3|MP4|CSV|JSON|XML|ZIP)(?![A-Za-z0-9])"
)
NUMBER_RE = re.compile(r"(?<!\w)[+-]?\d+(?:[.,]\d+)?%?(?!\w)")
QUOTED_ASCII_RE = re.compile(r"[\"'“”‘’]([A-Za-z][A-Za-z0-9 ._&+%:/-]{1,80})[\"'“”‘’]")

RELATION_PATTERNS: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {
        "above": (r"\babove\b", r"\bover\b", r"on top of"),
        "below": (r"\bbelow\b", r"\bunder\b", r"\bbeneath\b"),
        "left": (r"\bleft\b",),
        "right": (r"\bright\b",),
        "direct": (r"\bdirectly\b", r"\bimmediately\b"),
    },
    "fr": {
        "above": (r"au-dessus", r"\bdessus\b"),
        "below": (r"en dessous", r"au-dessous", r"\bsous\b"),
        "left": (r"à gauche", r"a gauche"),
        "right": (r"à droite", r"a droite"),
        "direct": (r"directement", r"immédiatement", r"immediatement"),
    },
    "ru": {
        "above": (r"\bнад\b", r"сверху", r"выше"),
        "below": (r"\bпод\b", r"снизу", r"ниже"),
        "left": (r"слева", r"лев[а-я]*"),
        "right": (r"справа", r"прав[а-я]*"),
        "direct": (r"непосредственно", r"\bпрямо\b"),
    },
    "zh": {
        "above": (r"上方", r"上面", r"之上", r"上边"),
        "below": (r"下方", r"下面", r"之下", r"下边"),
        "left": (r"左" ,),
        "right": (r"右",),
        "direct": (r"正上", r"正下", r"直接", r"紧邻", r"紧挨"),
    },
    "ja": {
        "above": (r"上方", r"上側", r"上に", r"上の"),
        "below": (r"下方", r"下側", r"下に", r"下の"),
        "left": (r"左",),
        "right": (r"右",),
        "direct": (r"すぐ", r"直接", r"真上", r"真下"),
    },
    "th": {
        "above": (r"ด้านบน", r"ข้างบน", r"เหนือ"),
        "below": (r"ด้านล่าง", r"ข้างล่าง", r"ใต้"),
        "left": (r"ด้านซ้าย", r"ทางซ้าย", r"ซ้าย"),
        "right": (r"ด้านขวา", r"ทางขวา", r"ขวา"),
        "direct": (r"โดยตรง", r"ทันที", r"ติดกับ"),
    },
}

NEGATION_PATTERNS = {
    "en": (r"\bnot\b", r"\bno\b", r"without"),
    "fr": (r"\bne\b", r"\bpas\b", r"sans"),
    "ru": (r"\bне\b", r"\bнет\b", r"без"),
    "zh": (r"不", r"没", r"无"),
    "ja": (r"ない", r"ません", r"ず"),
    "th": (r"ไม่", r"ไม่มี", r"โดยไม่มี"),
}


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def contextual_translation_id(pair_id: str) -> str:
    return f"{pair_id}::qwen3_contextual_v2"


def contextual_input_id(pair_id: str) -> str:
    return f"rq4_contextual::{pair_id}"


def build_contextual_plan(source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan = build_translation_plan(source_rows)
    enriched = []
    for row in plan:
        copied = dict(row)
        copied["translation_id"] = contextual_translation_id(str(row["pair_id"]))
        copied["translation_method"] = METHOD_NAME
        enriched.append(copied)
    validate_contextual_plan(enriched)
    return enriched


def validate_contextual_plan(rows: list[dict[str, Any]]) -> None:
    if len(rows) != EXPECTED_INTERVENTION_ROWS:
        raise ValueError(
            f"Contextual plan must contain {EXPECTED_INTERVENTION_ROWS} rows; found {len(rows)}."
        )
    if len({str(row["translation_id"]) for row in rows}) != len(rows):
        raise ValueError("Contextual translation IDs must be unique.")
    if any(row.get("translation_method") != METHOD_NAME for row in rows):
        raise ValueError("Unexpected contextual translation method.")
    hidden = {"text_dependency", "dependency", "human_target", "model_prediction"}
    if any(hidden & set(row) for row in rows):
        raise ValueError("Contextual generation plan contains a forbidden analysis field.")


def select_smoke_rows(
    rows: list[dict[str, Any]], per_direction: int = 2, seed: int = 20260811
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["source_language"], row["target_language"]), []).append(row)
    selected = []
    for direction, direction_rows in sorted(grouped.items()):
        ranked = sorted(
            direction_rows,
            key=lambda row: hashlib.sha256(
                f"{seed}:{row['translation_id']}".encode("utf-8")
            ).hexdigest(),
        )
        if len(ranked) < per_direction:
            raise ValueError(f"Insufficient rows for smoke direction {direction}.")
        selected.extend(ranked[:per_direction])
    expected = EXPECTED_DIRECTIONS * per_direction
    if len(selected) != expected:
        raise AssertionError(f"Smoke selection must contain {expected} rows.")
    return sorted(selected, key=lambda row: row["translation_id"])


def translation_payload(row: dict[str, Any]) -> dict[str, Any]:
    """The only benchmark content exposed to the translator."""

    return {
        "source_language": row["source_language"],
        "target_language": row["target_language"],
        "question_stem": row["source_question_stem"],
        "options": {label: row["source_options"][label] for label in LABELS},
    }


def build_user_prompt(row: dict[str, Any]) -> str:
    payload = translation_payload(row)
    return (
        "Translate the following complete GUI MCQ. Return only the output JSON object.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\nRequired output shape:\n"
        + json.dumps(OUTPUT_SHAPE, ensure_ascii=False, indent=2)
    )


def build_repair_prompt(
    row: dict[str, Any], previous_output: str, validation_errors: list[str]
) -> str:
    return (
        build_user_prompt(row)
        + "\n\nThe previous output failed validation for:\n- "
        + "\n- ".join(validation_errors)
        + "\n\nPrevious output:\n"
        + previous_output
        + "\n\nReturn a corrected JSON object. Do not revise a field that already satisfies "
        "the requirements unless necessary to restore the failed structure or invariant."
    )


def _tokens_by_field(
    question_stem: str, options: dict[str, str], pattern: re.Pattern[str]
) -> dict[str, list[str]]:
    values = {"question_stem": question_stem, **options}
    return {
        field: [match.group(0).upper() for match in pattern.finditer(str(value))]
        for field, value in values.items()
    }


def validate_structured_output(
    raw_output: str, row: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    try:
        parsed = json.loads(raw_output.strip())
    except json.JSONDecodeError as error:
        return None, [f"invalid_json:{error.msg}"]
    if not isinstance(parsed, dict):
        return None, ["top_level_not_object"]
    if list(parsed) != ["question_stem", "options"]:
        errors.append(f"top_level_keys:{list(parsed)!r}")
    options = parsed.get("options")
    if not isinstance(options, dict):
        errors.append("options_not_object")
        return parsed, errors
    if list(options) != list(LABELS):
        errors.append(f"option_keys_or_order:{list(options)!r}")
    stem = parsed.get("question_stem")
    if not isinstance(stem, str) or not stem.strip():
        errors.append("question_stem_empty_or_non_string")
    for label in LABELS:
        value = options.get(label)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"option_{label}_empty_or_non_string")

    if errors:
        return parsed, errors

    source_options = {label: str(row["source_options"][label]) for label in LABELS}
    translated_options = {label: str(options[label]) for label in LABELS}
    for name, pattern in (("number", NUMBER_RE), ("file_format", FILE_FORMAT_RE)):
        source_tokens = _tokens_by_field(
            str(row["source_question_stem"]), source_options, pattern
        )
        target_tokens = _tokens_by_field(str(stem), translated_options, pattern)
        for field in ("question_stem", *LABELS):
            if Counter(source_tokens[field]) != Counter(target_tokens[field]):
                errors.append(
                    f"{name}_tokens_changed:{field}:"
                    f"{source_tokens[field]!r}->{target_tokens[field]!r}"
                )
    return parsed, errors


def _detected_categories(text: str, language: str) -> set[str]:
    return {
        category
        for category, patterns in RELATION_PATTERNS[language].items()
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)
    }


def semantic_diagnostic_flags(
    row: dict[str, Any], translated: dict[str, Any]
) -> list[str]:
    flags: list[str] = []
    source_language = str(row["source_language"])
    target_language = str(row["target_language"])
    source_text = " ".join(
        [str(row["source_question_stem"])]
        + [str(row["source_options"][label]) for label in LABELS]
    )
    target_text = " ".join(
        [str(translated["question_stem"])]
        + [str(translated["options"][label]) for label in LABELS]
    )
    source_relations = _detected_categories(source_text, source_language)
    target_relations = _detected_categories(target_text, target_language)
    missing_relations = sorted(source_relations - target_relations)
    if missing_relations:
        flags.append("spatial_relation_mismatch:" + ",".join(missing_relations))

    source_negated = any(
        re.search(pattern, source_text, flags=re.IGNORECASE)
        for pattern in NEGATION_PATTERNS[source_language]
    )
    target_negated = any(
        re.search(pattern, target_text, flags=re.IGNORECASE)
        for pattern in NEGATION_PATTERNS[target_language]
    )
    if source_negated != target_negated:
        flags.append(f"negation_mismatch:{source_negated}->{target_negated}")

    quoted_source = {value.casefold() for value in QUOTED_ASCII_RE.findall(source_text)}
    quoted_target = {value.casefold() for value in QUOTED_ASCII_RE.findall(target_text)}
    if quoted_source and not quoted_source.issubset(quoted_target):
        flags.append("quoted_ascii_span_transformation")

    script_patterns = {
        "zh": r"[\u3400-\u9fff]",
        "ja": r"[\u3040-\u30ff]",
        "ru": r"[\u0400-\u04ff]",
        "th": r"[\u0e00-\u0e7f]",
    }
    if target_language in script_patterns and not re.search(
        script_patterns[target_language], target_text
    ):
        flags.append("target_script_mismatch")
    if all(
        str(row["source_options"][label]).strip()
        == str(translated["options"][label]).strip()
        for label in LABELS
    ) and str(row["source_question_stem"]).strip() == str(
        translated["question_stem"]
    ).strip():
        flags.append("all_fields_unchanged")
    return flags


def validate_contextual_translation_rows(
    rows: list[dict[str, Any]], expected_count: int, allow_partial: bool = False
) -> None:
    if not allow_partial and len(rows) != expected_count:
        raise ValueError(
            f"Contextual artifact must contain {expected_count} rows; found {len(rows)}."
        )
    ids = [str(row["translation_id"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate contextual translation_id.")
    required = {
        "translation_id",
        "pair_id",
        "parallel_id",
        "source_language",
        "target_language",
        "source_question_raw",
        "source_question_stem",
        "source_options",
        "translated_question_stem",
        "translated_options",
        "translated_question_raw",
        "option_order",
        "gold_label",
        "image_paths",
        "translator_model_id",
        "translator_revision",
        "translation_method",
        "prompt_template_version",
        "translation_generation_config",
        "translation_status",
        "translation_attempts",
        "hard_validation_errors",
        "semantic_diagnostic_flags",
        "translation_analysis_eligible",
        "translator_runtime_batch_size",
    }
    for row in rows:
        missing = required - set(row)
        if missing:
            raise ValueError(f"{row.get('translation_id')} missing {sorted(missing)}")
        if row["translator_model_id"] != CONTEXTUAL_MODEL_ID:
            raise ValueError("Unexpected contextual translator model.")
        if row["translator_revision"] != CONTEXTUAL_REVISION:
            raise ValueError("Unexpected contextual translator revision.")
        if row["translation_method"] != METHOD_NAME:
            raise ValueError("Unexpected contextual translation method.")
        if row["prompt_template_version"] != PROMPT_TEMPLATE_VERSION:
            raise ValueError("Unexpected contextual prompt template.")
        if list(row["option_order"]) != list(LABELS):
            raise ValueError(f"Option order changed: {row['translation_id']}")
        if list(row["translated_options"]) != list(LABELS):
            raise ValueError(f"Translated option keys/order changed: {row['translation_id']}")
        errors = list(row["hard_validation_errors"])
        eligible = bool(row["translation_analysis_eligible"])
        if eligible == bool(errors):
            raise ValueError(f"Eligibility/error mismatch: {row['translation_id']}")
        if row["translation_status"] not in {
            "ok",
            "recovered_after_structural_repair",
            "failed_after_structural_repair",
        }:
            raise ValueError(f"Invalid contextual status: {row['translation_id']}")
        if row["translation_status"] == "ok" and len(row["translation_attempts"]) != 1:
            raise ValueError(f"Unexpected ok attempts: {row['translation_id']}")
        if row["translation_status"] != "ok" and len(row["translation_attempts"]) != 2:
            raise ValueError(f"Unexpected repair attempts: {row['translation_id']}")
        if eligible:
            expected_raw = render_with_source_layout(
                str(row["source_question_raw"]),
                str(row["translated_question_stem"]),
                {label: str(row["translated_options"][label]) for label in LABELS},
            )
            if expected_raw != row["translated_question_raw"]:
                raise ValueError(f"Rendered question mismatch: {row['translation_id']}")
        if "text_dependency" in row:
            raise ValueError("Contextual translation artifact contains text_dependency.")
        if int(row["translator_runtime_batch_size"]) < 1:
            raise ValueError("Invalid contextual translation runtime batch size.")
    batch_sizes = {int(row["translator_runtime_batch_size"]) for row in rows}
    if len(batch_sizes) > 1:
        raise ValueError(f"Mixed contextual runtime batch sizes: {sorted(batch_sizes)}")


def write_jsonl_atomic(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
