from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

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
CONTEXTUAL_SCHEMA_VERSION = "rq4-rel-contextual-v4"
PROMPT_TEMPLATE_VERSION = "rq4_contextual_translation_v4"
METHOD_NAME = "full_mcq_contextual_structured_json"
EXPECTED_SMOKE_ROWS = EXPECTED_DIRECTIONS * 2
# Freeze the original 60-row smoke cohort even when prompt/artifact versions
# change, so revisions are compared on exactly the same pair_ids.
SMOKE_COHORT_TRANSLATION_SUFFIX = "qwen3_contextual_v2"

SYSTEM_PROMPT = """You are a professional translator for multilingual GUI multiple-choice questions.

Translate the complete MCQ from the declared source language to the declared target language.

Rules:
1. Translate EVERY translatable natural-language expression in the question and in all four options into the target language.
2. Do not answer, solve, explain, or improve the question.
3. Preserve the option keys A, B, C, and D exactly and in that order.
4. Do not add, remove, merge, split, normalize, or reorder options.
5. Translate ordinary GUI labels, tab names, button names, menu items, mode names, and one-word answer options. Quotation marks, capitalization, or brevity are NOT reasons to leave a translatable label in the source language.
6. Leave text unchanged only when it is genuinely language-neutral or normally retained in the target language, such as a trademark, product/app name, personal/place name, acronym, URL, or file format. Do not treat an ordinary interface label as a proper noun merely because it is quoted.
7. Use the complete MCQ only to disambiguate short fields. Do not use context to answer the MCQ or alter the meaning of any option.
8. Preserve the exact spatial axis and direction: above must remain above, below must remain below, left must remain left, and right must remain right. Never replace a directional relation with opposite, across from, near, or beside. In Thai, ตรงข้าม means opposite and MUST NOT be used to translate directly/immediately.
9. Preserve adjacency/intensity modifiers such as directly, immediately, and nearest whenever they are present. Do not introduce such a modifier when it is absent.
10. Preserve negation exactly.
11. Preserve every Arabic digit value, sign, percentage, telephone number, decimal value, and file-format token. Do not spell Arabic digits out or convert them to another numeral system. A numeric calendar month may be rendered as the corresponding target-language month name, but the date value must not change.
12. Do not correct, normalize, or improve the semantic content of any answer option, even if an option appears awkward, implausible, or inconsistent with the question. Translate each option as written.
13. Before responding, silently verify that all five fields are in the target language where translatable, every spatial relation has the same direction, and A/B/C/D remain unchanged as keys.
14. Return only one JSON object with exactly the requested keys. Do not use Markdown fences."""

OUTPUT_SHAPE = {
    "question_stem": "string",
    "options": {"A": "string", "B": "string", "C": "string", "D": "string"},
}

FILE_FORMAT_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:PDF|URL|URI|HTML|JPEG|JPG|PNG|GIF|SVG|MP3|MP4|CSV|JSON|XML|ZIP)(?![A-Za-z0-9])"
)
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])[+-]?\d+(?:[.,]\d+)?%?(?![A-Za-z0-9])")
QUOTED_ASCII_RE = re.compile(r"[\"'“”‘’]([A-Za-z][A-Za-z0-9 ._&+%:/-]{1,80})[\"'“”‘’]")
QUOTED_SPAN_RE = re.compile(
    r"\"[^\"]*\"|'[^']*'|“[^”]*”|‘[^’]*’|「[^」]*」|『[^』]*』|«[^»]*»"
)

# Month names add a canonical numeric month token so that natural date
# localization such as `2025年6月11日` -> `June 11, 2025` does not fail the
# hard numeric invariant. Numeric months already contribute their digit through
# NUMBER_RE and therefore need no separate pattern here.
MONTH_NAME_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, flags=re.IGNORECASE), str(month))
    for month, patterns in {
        1: (r"(?<![A-Za-z])jan(?:uary)?(?![A-Za-z])", r"\bjanvier\b", r"\bянвар[\w]*\b", r"มกราคม", r"一月"),
        2: (r"(?<![A-Za-z])feb(?:ruary)?(?![A-Za-z])", r"\bfévrier\b|\bfevrier\b", r"\bфеврал[\w]*\b", r"กุมภาพันธ์", r"二月"),
        3: (r"(?<![A-Za-z])mar(?:ch)?(?![A-Za-z])", r"\bmars\b", r"\bмарт[\w]*\b", r"มีนาคม", r"三月"),
        4: (r"(?<![A-Za-z])apr(?:il)?(?![A-Za-z])", r"\bavril\b", r"\bапрел[\w]*\b", r"เมษายน", r"四月"),
        5: (r"(?<![A-Za-z])may(?![A-Za-z])", r"\bmai\b", r"\bма[\w]*\b", r"พฤษภาคม", r"五月"),
        6: (r"(?<![A-Za-z])jun(?:e)?(?![A-Za-z])", r"\bjuin\b", r"\bиюн[\w]*\b", r"มิถุนายน", r"六月"),
        7: (r"(?<![A-Za-z])jul(?:y)?(?![A-Za-z])", r"\bjuillet\b", r"\bиюл[\w]*\b", r"กรกฎาคม", r"七月"),
        8: (r"(?<![A-Za-z])aug(?:ust)?(?![A-Za-z])", r"\baoût\b|\baout\b", r"\bавгуст[\w]*\b", r"สิงหาคม", r"八月"),
        9: (r"(?<![A-Za-z])sep(?:t(?:ember)?)?(?![A-Za-z])", r"\bseptembre\b", r"\bсентябр[\w]*\b", r"กันยายน", r"九月"),
        10: (r"(?<![A-Za-z])oct(?:ober)?(?![A-Za-z])", r"\boctobre\b", r"\bоктябр[\w]*\b", r"ตุลาคม", r"十月"),
        11: (r"(?<![A-Za-z])nov(?:ember)?(?![A-Za-z])", r"\bnovembre\b", r"\bноябр[\w]*\b", r"พฤศจิกายน", r"十一月"),
        12: (r"(?<![A-Za-z])dec(?:ember)?(?![A-Za-z])", r"\bdécembre\b|\bdecembre\b", r"\bдекабр[\w]*\b", r"ธันวาคม", r"十二月"),
    }.items()
    for pattern in patterns
)

OPPOSITE_PATTERNS: dict[str, tuple[str, ...]] = {
    "en": (r"\bopposite\b", r"\bacross from\b"),
    "fr": (r"\ben face de\b", r"\bopposé[\w]*\b"),
    "ru": (r"\bнапротив\b", r"\bпротивополож[\w]*\b"),
    "zh": (r"对面",),
    "ja": (r"向かい", r"反対側"),
    "th": (r"ตรงข้าม", r"ฝั่งตรงข้าม"),
}

UNIT_RATE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, flags=re.IGNORECASE)
    for pattern in (
        r"\b(?:hourly|daily|weekly|monthly|yearly)\b",
        r"\bper\s+(?:hour|day|week|month|year)\b",
        r"\b(?:horaire|quotidien(?:ne)?|hebdomadaire|mensuel(?:le)?|annuel(?:le)?)\b",
        r"\bpar\s+(?:heure|jour|semaine|mois|an)\b",
        r"\b(?:ежечас[\w]*|ежеднев[\w]*|еженедел[\w]*|ежемесяч[\w]*|ежегод[\w]*)\b",
        r"每(?:小时|时|分钟|日|天|周|月|年)",
        r"(?:毎時|毎日|毎週|毎月|毎年)",
        r"(?:ราย|ทุก)(?:ชั่วโมง|วัน|สัปดาห์|เดือน|ปี)",
    )
)

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
        "below": (r"下方", r"下側", r"下に", r"(?<!以)下の"),
        "left": (r"左",),
        "right": (r"右",),
        "direct": (r"すぐ", r"直接", r"直ちに", r"真上", r"真下", r"直[上下左右]"),
    },
    "th": {
        "above": (r"ด้านบน", r"ข้างบน", r"เหนือ"),
        "below": (r"ด้านล่าง", r"ข้างล่าง", r"ใต้"),
        "left": (r"ด้านซ้าย", r"ทางซ้าย", r"ซ้าย"),
        "right": (r"ด้านขวา", r"ทางขวา", r"ขวา"),
        "direct": (r"โดยตรง", r"ทันที", r"ติดกับ", r"ตรง(?!ข้าม)"),
    },
}

NEGATION_PATTERNS = {
    "en": (r"\bnot\b", r"\bno\b", r"without"),
    "fr": (r"\bne\b", r"\bpas\b", r"sans"),
    "ru": (r"\bне\b", r"\bнет\b", r"\bбез\b"),
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
    return f"{pair_id}::qwen3_contextual_v4"


def contextual_input_id(pair_id: str) -> str:
    return f"rq4_contextual_v4::{pair_id}"


def build_contextual_plan(source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan = build_translation_plan(source_rows)
    enriched = []
    for row in plan:
        copied = dict(row)
        copied["schema_version"] = CONTEXTUAL_SCHEMA_VERSION
        copied["translation_id"] = contextual_translation_id(str(row["pair_id"]))
        copied["translation_method"] = METHOD_NAME
        enriched.append(copied)
    validate_contextual_plan(enriched)
    return enriched


def build_contextual_plan_from_original_controls(
    controls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build v4 directly from the frozen, Git-LFS-shared original controls.

    This is the deployment-safe path: raw MPR-GUI QAS files are intentionally not
    tracked in Git, while the original-control artifact contains the exact 10,980
    source-query/target-GUI pairs previously integrity-audited for RQ4.
    """

    if len(controls) != EXPECTED_INTERVENTION_ROWS:
        raise ValueError(
            "Frozen original controls must contain exactly "
            f"{EXPECTED_INTERVENTION_ROWS} rows; found {len(controls)}."
        )
    plans: list[dict[str, Any]] = []
    seen_pairs: set[str] = set()
    source_versions: dict[tuple[str, str], tuple[Any, ...]] = {}
    for control in controls:
        required = {
            "input_id",
            "pair_id",
            "parallel_id",
            "dimension",
            "source_question_language",
            "gui_language",
            "question_sample_id",
            "gui_sample_id",
            "source_qas_file",
            "source_qas_line",
            "source_matched_endpoint_id",
            "target_human_parallel_endpoint_id",
            "question_raw",
            "question_stem",
            "options",
            "option_order",
            "gold_label",
            "answer_raw",
            "image_paths",
            "num_images",
            "frame_order",
            "condition",
            "matched",
            "original_matched",
        }
        missing = required - set(control)
        if missing:
            raise ValueError(
                f"Frozen original control lacks {sorted(missing)}: "
                f"{control.get('pair_id')}"
            )
        pair_id = str(control["pair_id"])
        if pair_id in seen_pairs:
            raise ValueError(f"Duplicate frozen original-control pair: {pair_id}")
        seen_pairs.add(pair_id)
        source_language = str(control["source_question_language"])
        target_language = str(control["gui_language"])
        if source_language == target_language:
            raise ValueError(f"Original control is not a mismatch: {pair_id}")
        if control["dimension"] != "rel" or control["condition"] != "original_mismatch":
            raise ValueError(f"Unexpected original-control condition: {pair_id}")
        if control["matched"] is not False or control["original_matched"] is not False:
            raise ValueError(f"Original-control match metadata changed: {pair_id}")
        if list(control["option_order"]) != list(LABELS):
            raise ValueError(f"Original-control option order changed: {pair_id}")
        if list(control["options"]) != list(LABELS):
            raise ValueError(f"Original-control option keys/order changed: {pair_id}")
        if len(control["image_paths"]) != int(control["num_images"]):
            raise ValueError(f"Original-control image count mismatch: {pair_id}")

        source_key = (str(control["parallel_id"]), source_language)
        source_signature = (
            control["question_raw"],
            control["question_stem"],
            json.dumps(control["options"], ensure_ascii=False, sort_keys=True),
            tuple(control["option_order"]),
            control["gold_label"],
            control["question_sample_id"],
        )
        previous = source_versions.setdefault(source_key, source_signature)
        if previous != source_signature:
            raise ValueError(
                "Source query differs across target-GUI controls for "
                f"{source_key}."
            )

        plans.append(
            {
                "schema_version": CONTEXTUAL_SCHEMA_VERSION,
                "translation_id": contextual_translation_id(pair_id),
                "pair_id": pair_id,
                "source_input_id": control["input_id"],
                "parallel_id": control["parallel_id"],
                "dimension": "rel",
                "source_language": source_language,
                "target_language": target_language,
                "source_question_sample_id": control["question_sample_id"],
                "gui_sample_id": control["gui_sample_id"],
                "source_qas_file": control["source_qas_file"],
                "source_qas_line": control["source_qas_line"],
                "source_matched_endpoint_id": control["source_matched_endpoint_id"],
                "target_human_parallel_endpoint_id": control[
                    "target_human_parallel_endpoint_id"
                ],
                "source_question_raw": control["question_raw"],
                "source_question_stem": control["question_stem"],
                "source_options": control["options"],
                "option_order": list(control["option_order"]),
                "gold_label": control["gold_label"],
                "answer_raw": control["answer_raw"],
                "image_paths": list(control["image_paths"]),
                "num_images": int(control["num_images"]),
                "frame_order": control["frame_order"],
                "translation_method": METHOD_NAME,
            }
        )
    validate_contextual_plan(plans)
    return sorted(plans, key=lambda row: row["translation_id"])


def human_reference_map_from_original_controls(
    controls: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Recover each human Q_language endpoint without reading raw QAS files."""

    references: dict[str, dict[str, Any]] = {}
    for control in controls:
        endpoint_id = str(control["source_matched_endpoint_id"])
        candidate = {
            "sample_id": endpoint_id,
            "question_stem": str(control["question_stem"]),
            "options": {label: str(control["options"][label]) for label in LABELS},
        }
        previous = references.setdefault(endpoint_id, candidate)
        if previous != candidate:
            raise ValueError(
                f"Human endpoint differs across frozen controls: {endpoint_id}"
            )
    expected_endpoints = EXPECTED_REL_ITEMS * 6
    if len(references) != expected_endpoints:
        raise ValueError(
            f"Expected {expected_endpoints} human endpoints; found {len(references)}."
        )
    return references


def validate_contextual_plan(rows: list[dict[str, Any]]) -> None:
    if len(rows) != EXPECTED_INTERVENTION_ROWS:
        raise ValueError(
            f"Contextual plan must contain {EXPECTED_INTERVENTION_ROWS} rows; found {len(rows)}."
        )
    if len({str(row["translation_id"]) for row in rows}) != len(rows):
        raise ValueError("Contextual translation IDs must be unique.")
    if any(row.get("translation_method") != METHOD_NAME for row in rows):
        raise ValueError("Unexpected contextual translation method.")
    if any(row.get("schema_version") != CONTEXTUAL_SCHEMA_VERSION for row in rows):
        raise ValueError("Unexpected contextual plan schema version.")
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
                (
                    f"{seed}:{row['pair_id']}::"
                    f"{SMOKE_COHORT_TRANSLATION_SUFFIX}"
                ).encode()
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
        "the requirements unless necessary to restore the failed structure or invariant. "
        "Re-check that every ordinary GUI label and answer option is translated, that "
        "left/right/above/below are not replaced by an opposite/across relation, and that "
        "Arabic digit values and signs remain unchanged."
    )


def build_semantic_repair_prompt(
    row: dict[str, Any], previous_output: str, repair_reasons: list[str]
) -> str:
    reason_text = "\n- ".join(repair_reasons)
    source_relations = sorted(
        _detected_categories(
            str(row["source_question_stem"]), str(row["source_language"])
        )
    )
    relation_text = ", ".join(source_relations) if source_relations else "none detected"
    return (
        build_user_prompt(row)
        + "\n\nThe previous JSON was structurally valid, but automated checks found "
        "the following likely semantic translation problems:\n- "
        + reason_text
        + "\n\nPrevious output:\n"
        + previous_output
        + "\n\nSource relation categories detected for preservation: "
        + relation_text
        + "\n\nReturn a corrected JSON object. Correct only the identified translation "
        "problems and preserve every unaffected field. The source spatial direction "
        "must remain unchanged. In particular, never use a word meaning opposite or "
        "across from for directly/immediately. Translate ordinary quoted GUI labels "
        "and natural-language answer options, but retain genuine brands, names, phone "
        "numbers, identifiers, and language-neutral tokens. Return JSON only."
    )


def _normalize_unicode_digits(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text))
    converted: list[str] = []
    for character in normalized:
        try:
            converted.append(str(unicodedata.digit(character)))
        except (TypeError, ValueError):
            converted.append(character)
    return "".join(converted)


def _normalized_number_tokens(text: str) -> list[str]:
    normalized = _normalize_unicode_digits(text)
    tokens: list[str] = []
    for match in NUMBER_RE.finditer(normalized):
        token = match.group(0)
        # Treat locale decimal commas and decimal points as the same value.
        if token.count(",") == 1 and "." not in token:
            token = token.replace(",", ".")
        tokens.append(token.upper())
    # Named months carry the same semantic numeric value as digit months.
    for pattern, month in MONTH_NAME_PATTERNS:
        if pattern.search(normalized):
            tokens.append(month)
    # `1 hour` may be localized idiomatically as `hourly`/`每小时`. Add the
    # canonical implicit one only when no explicit 1 is already present.
    if "1" not in tokens and any(pattern.search(normalized) for pattern in UNIT_RATE_PATTERNS):
        tokens.append("1")
    return tokens


def _tokens_by_field(
    question_stem: str, options: dict[str, str], pattern: re.Pattern[str]
) -> dict[str, list[str]]:
    values = {"question_stem": question_stem, **options}
    if pattern is NUMBER_RE:
        return {
            field: _normalized_number_tokens(str(value))
            for field, value in values.items()
        }
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
    source_stem = str(row["source_question_stem"])
    target_stem = str(translated["question_stem"])
    source_text = " ".join(
        [source_stem] + [str(row["source_options"][label]) for label in LABELS]
    )
    target_text = " ".join(
        [target_stem] + [str(translated["options"][label]) for label in LABELS]
    )
    # REL directions are expressed by the question stem. Restricting this check
    # to the stem avoids mistaking positional words inside answer labels for the
    # relation being asked about.
    source_relations = _detected_categories(source_stem, source_language)
    target_relations = _detected_categories(target_stem, target_language)
    missing_relations = sorted(source_relations - target_relations)
    if missing_relations:
        flags.append("spatial_relation_mismatch:" + ",".join(missing_relations))

    for first, second in (("above", "below"), ("left", "right")):
        source_only_first = first in source_relations and second not in source_relations
        source_only_second = second in source_relations and first not in source_relations
        target_only_first = first in target_relations and second not in target_relations
        target_only_second = second in target_relations and first not in target_relations
        if source_only_first and target_only_second:
            flags.append(f"spatial_direction_conflict:{first}->{second}")
        if source_only_second and target_only_first:
            flags.append(f"spatial_direction_conflict:{second}->{first}")

    source_opposed = any(
        re.search(pattern, source_stem, flags=re.IGNORECASE)
        for pattern in OPPOSITE_PATTERNS[source_language]
    )
    target_opposed = any(
        re.search(pattern, target_stem, flags=re.IGNORECASE)
        for pattern in OPPOSITE_PATTERNS[target_language]
    )
    if target_opposed and not source_opposed:
        flags.append("spatial_opposition_introduced")

    # Negation inside a quoted GUI label (for example, "Do Not Disturb") is
    # lexical content, not question-level logical negation.
    source_unquoted = QUOTED_SPAN_RE.sub(" ", source_stem)
    target_unquoted = QUOTED_SPAN_RE.sub(" ", target_stem)
    source_negated = any(
        re.search(pattern, source_unquoted, flags=re.IGNORECASE)
        for pattern in NEGATION_PATTERNS[source_language]
    )
    target_negated = any(
        re.search(pattern, target_unquoted, flags=re.IGNORECASE)
        for pattern in NEGATION_PATTERNS[target_language]
    )
    if source_negated != target_negated:
        flags.append(f"negation_mismatch:{source_negated}->{target_negated}")

    quoted_source = {value.casefold() for value in QUOTED_ASCII_RE.findall(source_text)}
    quoted_target = {value.casefold() for value in QUOTED_ASCII_RE.findall(target_text)}
    unchanged_quoted = sorted(quoted_source & quoted_target)
    if source_language != target_language and unchanged_quoted:
        flags.append(
            "quoted_ascii_span_unchanged:" + "|".join(unchanged_quoted)
        )

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
    unchanged_options = sum(
        str(row["source_options"][label]).strip()
        == str(translated["options"][label]).strip()
        for label in LABELS
    )
    if source_language != target_language and unchanged_options >= 2:
        flags.append(f"multiple_options_unchanged:{unchanged_options}")
    return flags


def semantic_repair_reasons(
    row: dict[str, Any],
    translated: dict[str, Any],
    flags: list[str] | None = None,
) -> list[str]:
    """Return only high-confidence or high-impact issues worth one MT retry.

    Broad lexical diagnostics remain report-only. In particular, loss of the
    optional `direct` modifier alone does not trigger regeneration because human
    parallel questions also omit it in some locales.
    """

    flags = semantic_diagnostic_flags(row, translated) if flags is None else flags
    reasons: list[str] = []
    for flag in flags:
        prefix, _, detail = flag.partition(":")
        if prefix in {
            "spatial_opposition_introduced",
            "spatial_direction_conflict",
            "negation_mismatch",
            "target_script_mismatch",
            "all_fields_unchanged",
        }:
            reasons.append(flag)
        elif prefix == "spatial_relation_mismatch":
            missing = sorted(
                {value for value in detail.split(",") if value}
                & {"above", "below", "left", "right"}
            )
            if missing:
                reasons.append("spatial_core_relation_missing:" + ",".join(missing))

    source_language = str(row["source_language"])
    target_language = str(row["target_language"])
    if source_language != target_language and target_language != "en":
        unchanged_quoted = sorted(
            {
                value.casefold()
                for value in QUOTED_ASCII_RE.findall(str(row["source_question_stem"]))
            }
            & {
                value.casefold()
                for value in QUOTED_ASCII_RE.findall(str(translated["question_stem"]))
            }
        )
        if unchanged_quoted:
            reasons.append(
                "quoted_gui_label_may_be_untranslated:" + "|".join(unchanged_quoted)
            )

        unchanged_translatable_options = [
            label
            for label in LABELS
            if str(row["source_options"][label]).strip()
            == str(translated["options"][label]).strip()
            and any(character.isalpha() for character in str(row["source_options"][label]))
        ]
        if len(unchanged_translatable_options) >= 2:
            reasons.append(
                "translatable_options_unchanged:"
                + ",".join(unchanged_translatable_options)
            )
    return list(dict.fromkeys(reasons))


def semantic_repair_score(reasons: list[str]) -> int:
    weights = {
        "spatial_opposition_introduced": 120,
        "spatial_direction_conflict": 120,
        "spatial_core_relation_missing": 100,
        "negation_mismatch": 100,
        "target_script_mismatch": 120,
        "all_fields_unchanged": 120,
        "translatable_options_unchanged": 40,
        "quoted_gui_label_may_be_untranslated": 20,
    }
    return sum(weights.get(reason.split(":", 1)[0], 0) for reason in reasons)


def should_accept_semantic_repair(
    baseline_reasons: list[str],
    candidate_hard_errors: list[str],
    candidate_reasons: list[str],
) -> bool:
    if candidate_hard_errors:
        return False
    return semantic_repair_score(candidate_reasons) < semantic_repair_score(
        baseline_reasons
    )


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
        "schema_version",
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
        "hard_repair_attempted",
        "semantic_repair_attempted",
        "semantic_repair_accepted",
        "initial_semantic_repair_reasons",
        "initial_semantic_repair_score",
        "final_semantic_repair_reasons",
        "final_semantic_repair_score",
        "translation_analysis_eligible",
        "translator_runtime_batch_size",
        "translation_source_kind",
        "translation_source_path",
        "translation_source_sha256",
    }
    for row in rows:
        missing = required - set(row)
        if missing:
            raise ValueError(f"{row.get('translation_id')} missing {sorted(missing)}")
        if row["translator_model_id"] != CONTEXTUAL_MODEL_ID:
            raise ValueError("Unexpected contextual translator model.")
        if row["schema_version"] != CONTEXTUAL_SCHEMA_VERSION:
            raise ValueError("Unexpected contextual artifact schema version.")
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
            "recovered_after_hard_repair",
            "recovered_after_semantic_repair",
            "eligible_after_rejected_semantic_repair",
            "failed_after_repair",
        }:
            raise ValueError(f"Invalid contextual status: {row['translation_id']}")
        attempts = list(row["translation_attempts"])
        if not 1 <= len(attempts) <= 3:
            raise ValueError(f"Unexpected repair attempts: {row['translation_id']}")
        if [int(attempt["attempt"]) for attempt in attempts] != list(range(len(attempts))):
            raise ValueError(f"Non-sequential attempt numbers: {row['translation_id']}")
        attempt_kinds = [str(attempt.get("attempt_kind")) for attempt in attempts]
        if attempt_kinds[0] != "primary":
            raise ValueError(f"Missing primary attempt marker: {row['translation_id']}")
        hard_attempted = bool(row["hard_repair_attempted"])
        semantic_attempted = bool(row["semantic_repair_attempted"])
        semantic_accepted = bool(row["semantic_repair_accepted"])
        if hard_attempted != ("hard_repair" in attempt_kinds):
            raise ValueError(f"Hard repair metadata mismatch: {row['translation_id']}")
        if semantic_attempted != ("semantic_repair" in attempt_kinds):
            raise ValueError(f"Semantic repair metadata mismatch: {row['translation_id']}")
        if semantic_accepted and not semantic_attempted:
            raise ValueError(f"Accepted semantic repair was not attempted: {row['translation_id']}")
        if sum(bool(attempt.get("selected_as_final")) for attempt in attempts) != 1:
            raise ValueError(f"Final attempt selection mismatch: {row['translation_id']}")
        if (
            semantic_accepted
            and row["final_semantic_repair_score"]
            >= row["initial_semantic_repair_score"]
        ):
            raise ValueError(
                f"Accepted semantic repair did not improve: {row['translation_id']}"
            )
        if row["translation_status"] == "ok" and len(attempts) != 1:
            raise ValueError(f"Unexpected ok attempts: {row['translation_id']}")
        if eligible:
            expected_raw = render_with_source_layout(
                str(row["source_question_raw"]),
                str(row["translated_question_stem"]),
                {label: str(row["translated_options"][label]) for label in LABELS},
            )
            if expected_raw != row["translated_question_raw"]:
                raise ValueError(f"Rendered question mismatch: {row['translation_id']}")
            final_parsed = {
                "question_stem": str(row["translated_question_stem"]),
                "options": {
                    label: str(row["translated_options"][label]) for label in LABELS
                },
            }
            expected_flags = semantic_diagnostic_flags(row, final_parsed)
            if list(row["semantic_diagnostic_flags"]) != expected_flags:
                raise ValueError(f"Final semantic flags mismatch: {row['translation_id']}")
            expected_reasons = semantic_repair_reasons(
                row, final_parsed, expected_flags
            )
            if list(row["final_semantic_repair_reasons"]) != expected_reasons:
                raise ValueError(f"Final semantic reasons mismatch: {row['translation_id']}")
            if row["final_semantic_repair_score"] != semantic_repair_score(
                expected_reasons
            ):
                raise ValueError(f"Final semantic score mismatch: {row['translation_id']}")
        if "text_dependency" in row:
            raise ValueError("Contextual translation artifact contains text_dependency.")
        if int(row["translator_runtime_batch_size"]) < 1:
            raise ValueError("Invalid contextual translation runtime batch size.")
    batch_sizes = {int(row["translator_runtime_batch_size"]) for row in rows}
    if len(batch_sizes) > 1:
        raise ValueError(f"Mixed contextual runtime batch sizes: {sorted(batch_sizes)}")
    source_kinds = {str(row["translation_source_kind"]) for row in rows}
    source_hashes = {row["translation_source_sha256"] for row in rows}
    if len(source_kinds) != 1 or len(source_hashes) != 1:
        raise ValueError("Mixed contextual translation source provenance.")
    if not source_kinds <= {"frozen_original_controls", "raw_qas_reconstruction"}:
        raise ValueError(f"Unexpected translation source kind: {source_kinds}")


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
