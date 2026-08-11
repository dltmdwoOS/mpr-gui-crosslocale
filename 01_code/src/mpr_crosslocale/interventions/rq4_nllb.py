from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from mpr_crosslocale.data.input_specs import build_mismatch_inputs
from mpr_crosslocale.data.options import OPTION_RE, parse_question_options
from mpr_crosslocale.data.schema import LABELS, LANGUAGES
from mpr_crosslocale.inference.answer_parser import parse_label

EXPECTED_REL_ITEMS = 366
EXPECTED_DIRECTIONS = len(LANGUAGES) * (len(LANGUAGES) - 1)
EXPECTED_INTERVENTION_ROWS = EXPECTED_REL_ITEMS * EXPECTED_DIRECTIONS
EXPECTED_TARGET_UNITS = EXPECTED_REL_ITEMS * len(LANGUAGES)
DEPENDENCY_LEVELS = {"dependent", "independent"}

NLLB_MODEL_ID = "facebook/nllb-200-distilled-600M"
NLLB_REVISION = "f8d333a098d19b4fd9a8b18f94170487ad3f821d"
NLLB_LANGUAGE_CODES = {
    "en": "eng_Latn",
    "zh": "zho_Hans",
    "fr": "fra_Latn",
    "ru": "rus_Cyrl",
    "ja": "jpn_Jpan",
    "th": "tha_Thai",
}

TRANSLATABLE_FIELDS = ("question_stem", "A", "B", "C", "D")

# The intervention input is built from an original-control input. Any top-level
# difference not listed here is a construction error.
ALLOWED_INPUT_DIFF_FIELDS = {
    "condition",
    "effective_question_language",
    "input_id",
    "language_aligned_after_intervention",
    "options",
    "question_language",
    "question_raw",
    "question_stem",
    "translation_generation_config",
    "translation_status",
    "translation_retry_events",
    "translation_failed_fields",
    "translation_analysis_eligible",
    "translation_id",
    "translator_model_id",
    "translator_revision",
    "translator_src_code",
    "translator_tgt_code",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl_atomic(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def write_csv_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("Cannot write an empty CSV audit.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_text_sha256(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest()


def pair_id(parallel_id: str, source_language: str, gui_language: str) -> str:
    return f"{parallel_id}::source={source_language}::gui={gui_language}"


def translation_id(parallel_id: str, source_language: str, gui_language: str) -> str:
    return f"{pair_id(parallel_id, source_language, gui_language)}::nllb"


def source_matched_endpoint_id(parallel_id: str, source_language: str) -> str:
    return f"{parallel_id}::{source_language}"


def target_human_parallel_endpoint_id(parallel_id: str, target_language: str) -> str:
    return f"{parallel_id}::{target_language}"


def _preserve_outer_whitespace(segment: str, replacement: str) -> str:
    leading_length = len(segment) - len(segment.lstrip())
    trailing_length = len(segment) - len(segment.rstrip())
    leading = segment[:leading_length]
    trailing = segment[len(segment) - trailing_length :] if trailing_length else ""
    return f"{leading}{replacement}{trailing}"


def render_with_source_layout(
    source_question_raw: str,
    replacement_stem: str,
    replacement_options: dict[str, str],
) -> str:
    """Replace semantic fields while preserving source A-D delimiters and whitespace."""

    matches = list(OPTION_RE.finditer(source_question_raw))
    labels = [match.group(1) for match in matches]
    if labels != list(LABELS):
        raise ValueError(f"Expected ordered A-D delimiters, found {labels!r}.")
    if set(replacement_options) != set(LABELS):
        raise ValueError("Replacement options must contain exactly A, B, C, and D.")

    pieces = [
        _preserve_outer_whitespace(source_question_raw[: matches[0].start()], replacement_stem)
    ]
    for index, match in enumerate(matches):
        pieces.append(source_question_raw[match.start() : match.end()])
        segment_end = matches[index + 1].start() if index + 1 < len(matches) else len(
            source_question_raw
        )
        source_option_segment = source_question_raw[match.end() : segment_end]
        pieces.append(
            _preserve_outer_whitespace(source_option_segment, replacement_options[match.group(1)])
        )
    return "".join(pieces)


def load_rel_source_rows(
    annotation_manifest_path: Path,
    qas_dir: Path,
    canonical_image_root: str = "data/raw/mpr_gui_bench/images",
) -> list[dict[str, Any]]:
    """Load the frozen, dependency-blind REL source universe."""

    manifest = json.loads(annotation_manifest_path.read_text(encoding="utf-8"))
    items = manifest.get("items", [])
    if len(items) != EXPECTED_REL_ITEMS:
        raise ValueError(
            f"REL annotation manifest must contain {EXPECTED_REL_ITEMS} items; found {len(items)}."
        )

    qas_cache: dict[str, list[dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda value: str(value["parallel_id"])):
        parallel_id_value = str(item["parallel_id"])
        if not parallel_id_value.startswith("rel::"):
            raise ValueError(f"Non-REL item in manifest: {parallel_id_value}")
        locales = item.get("locales", {})
        if set(locales) != set(LANGUAGES):
            raise ValueError(f"{parallel_id_value} does not contain all six locales.")

        item_rows: list[dict[str, Any]] = []
        for language in LANGUAGES:
            locale = locales[language]
            source_file = str(locale["source_file"])
            if source_file not in qas_cache:
                source_path = qas_dir / source_file
                if not source_path.exists():
                    raise FileNotFoundError(f"Missing frozen QAS source: {source_path}")
                qas_cache[source_file] = read_jsonl(source_path)
            source_line = int(locale["source_line"])
            if source_line < 1 or source_line > len(qas_cache[source_file]):
                raise ValueError(f"Invalid source line for {parallel_id_value}/{language}: {source_line}")
            qas_row = qas_cache[source_file][source_line - 1]
            question_raw = str(qas_row.get("question", ""))
            parsed = parse_question_options(question_raw)
            if parsed.option_parse_status != "ok":
                raise ValueError(
                    f"Option parsing failed for {parallel_id_value}/{language}: "
                    f"{parsed.option_parse_status}"
                )
            expected_options = {key: str(value) for key, value in locale["options"].items()}
            if parsed.question_stem != str(locale["question_stem"]):
                raise ValueError(f"Question stem differs from frozen manifest: {parallel_id_value}/{language}")
            if parsed.options != expected_options:
                raise ValueError(f"Options differ from frozen manifest: {parallel_id_value}/{language}")
            if parsed.option_order != list(locale["option_order"]):
                raise ValueError(f"Option order differs from frozen manifest: {parallel_id_value}/{language}")

            # Round-trip with source fields must preserve every source byte.
            round_trip = render_with_source_layout(question_raw, parsed.question_stem, parsed.options)
            if round_trip != question_raw:
                raise ValueError(f"Source layout round-trip failed: {parallel_id_value}/{language}")

            gold_label = parse_label(str(qas_row.get("answer", "")))
            if gold_label not in LABELS:
                raise ValueError(f"Invalid gold label for {parallel_id_value}/{language}: {gold_label}")
            asset = str(locale["asset"])
            item_rows.append(
                {
                    "parallel_id": parallel_id_value,
                    "dimension": "rel",
                    "language": language,
                    "sample_id": f"{parallel_id_value}::{language}",
                    "question_raw": question_raw,
                    "question_stem": parsed.question_stem,
                    "options": parsed.options,
                    "option_order": parsed.option_order,
                    "gold_label": gold_label,
                    "answer_raw": str(qas_row.get("answer", "")),
                    "asset": asset,
                    "image_paths": [f"{canonical_image_root.rstrip('/')}/{asset}"],
                    "num_images": 1,
                    "frame_order": "single_image",
                    "source_file": source_file,
                    "source_line": source_line,
                }
            )
        if len({row["gold_label"] for row in item_rows}) != 1:
            raise ValueError(f"Cross-locale gold labels differ for {parallel_id_value}.")
        rows.extend(item_rows)

    if len(rows) != EXPECTED_REL_ITEMS * len(LANGUAGES):
        raise AssertionError("Unexpected REL locale-row count.")
    return rows


def build_translation_plan(source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Pair construction is delegated to the repository's canonical mismatch
    # builder. RQ4 only enriches those frozen pairs with translation metadata.
    mismatch_rows = build_mismatch_inputs(source_rows)
    by_sample_id = {str(row["sample_id"]): row for row in source_rows}
    plan: list[dict[str, Any]] = []
    for mismatch in mismatch_rows:
        source = by_sample_id[str(mismatch["question_sample_id"])]
        target = by_sample_id[str(mismatch["gui_sample_id"])]
        source_language = str(mismatch["question_language"])
        target_language = str(mismatch["gui_language"])
        parallel_id_value = str(mismatch["parallel_id"])
        row = {
            "translation_id": translation_id(
                parallel_id_value, source_language, target_language
            ),
            "pair_id": pair_id(parallel_id_value, source_language, target_language),
            "source_input_id": mismatch["input_id"],
            "parallel_id": parallel_id_value,
            "dimension": "rel",
            "source_language": source_language,
            "target_language": target_language,
            "source_question_sample_id": mismatch["question_sample_id"],
            "gui_sample_id": mismatch["gui_sample_id"],
            "source_qas_file": source["source_file"],
            "source_qas_line": source["source_line"],
            "source_matched_endpoint_id": mismatch["source_matched_endpoint_id"],
            "target_human_parallel_endpoint_id": mismatch[
                "target_human_parallel_endpoint_id"
            ],
            "source_question_raw": source["question_raw"],
            "source_question_stem": source["question_stem"],
            "source_options": source["options"],
            "option_order": source["option_order"],
            "gold_label": mismatch["gold_label"],
            "answer_raw": mismatch["answer_raw"],
            "image_paths": mismatch["image_paths"],
            "num_images": mismatch["num_images"],
            "frame_order": mismatch["frame_order"],
        }
        if source["gold_label"] != target["gold_label"]:
            raise ValueError(f"Gold mismatch while constructing {row['pair_id']}")
        plan.append(row)
    validate_plan_rows(plan)
    return plan


def validate_plan_rows(rows: list[dict[str, Any]]) -> None:
    if len(rows) != EXPECTED_INTERVENTION_ROWS:
        raise ValueError(
            f"Translation plan must contain {EXPECTED_INTERVENTION_ROWS} rows; found {len(rows)}."
        )
    ids = [str(row["translation_id"]) for row in rows]
    pairs = [str(row["pair_id"]) for row in rows]
    if len(ids) != len(set(ids)) or len(pairs) != len(set(pairs)):
        raise ValueError("Translation IDs and pair IDs must both be unique.")
    if any(row["source_language"] == row["target_language"] for row in rows):
        raise ValueError("Translation plan contains a matched language direction.")
    if any(row.get("text_dependency") is not None for row in rows):
        raise ValueError("Translation generation plan must be blind to text_dependency.")
    counts = Counter((row["source_language"], row["target_language"]) for row in rows)
    if len(counts) != EXPECTED_DIRECTIONS or set(counts.values()) != {EXPECTED_REL_ITEMS}:
        raise ValueError("Every directed language pair must contain exactly 366 REL items.")


def validate_translation_rows(rows: list[dict[str, Any]], allow_partial: bool = False) -> None:
    if not allow_partial and len(rows) != EXPECTED_INTERVENTION_ROWS:
        raise ValueError(
            f"Translation artifact must contain {EXPECTED_INTERVENTION_ROWS} rows; found {len(rows)}."
        )
    if len({str(row["translation_id"]) for row in rows}) != len(rows):
        raise ValueError("Duplicate translation_id in translation artifact.")
    required = {
        "translation_id",
        "pair_id",
        "parallel_id",
        "source_language",
        "target_language",
        "source_question_stem",
        "translated_question_stem",
        "source_options",
        "translated_options",
        "translated_question_raw",
        "option_order",
        "gold_label",
        "image_paths",
        "translator_model_id",
        "translator_revision",
        "translator_src_code",
        "translator_tgt_code",
        "translation_generation_config",
        "translation_status",
        "translation_retry_events",
        "translation_failed_fields",
        "translation_analysis_eligible",
    }
    for row in rows:
        missing = required - set(row)
        if missing:
            raise ValueError(f"{row.get('translation_id')} is missing fields: {sorted(missing)}")
        if row["source_language"] == row["target_language"]:
            raise ValueError(f"Matched direction in translation artifact: {row['translation_id']}")
        if str(row["translator_model_id"]) != NLLB_MODEL_ID:
            raise ValueError(f"Unexpected translator model: {row['translator_model_id']}")
        if str(row["translator_revision"]) != NLLB_REVISION:
            raise ValueError(f"Unexpected translator revision: {row['translator_revision']}")
        if str(row["translator_src_code"]) != NLLB_LANGUAGE_CODES[row["source_language"]]:
            raise ValueError(f"Source NLLB code mismatch: {row['translation_id']}")
        if str(row["translator_tgt_code"]) != NLLB_LANGUAGE_CODES[row["target_language"]]:
            raise ValueError(f"Target NLLB code mismatch: {row['translation_id']}")
        if list(row["option_order"]) != list(LABELS):
            raise ValueError(f"Option order changed: {row['translation_id']}")
        if set(row["translated_options"]) != set(LABELS):
            raise ValueError(f"Translated options are not exactly A-D: {row['translation_id']}")
        status = str(row["translation_status"])
        retry_events = row["translation_retry_events"]
        failed_fields = list(row["translation_failed_fields"])
        eligible = bool(row["translation_analysis_eligible"])
        if status not in {
            "ok",
            "recovered_after_empty_retry",
            "failed_empty_after_retry",
        }:
            raise ValueError(f"Invalid translation status: {row['translation_id']}={status}")
        if not isinstance(retry_events, list) or not isinstance(
            row["translation_failed_fields"], list
        ):
            raise ValueError(f"Invalid retry audit metadata: {row['translation_id']}")
        field_values = {
            "question_stem": row["translated_question_stem"],
            **row["translated_options"],
        }
        actual_empty_fields = sorted(
            field for field, value in field_values.items() if not str(value).strip()
        )
        if sorted(failed_fields) != actual_empty_fields:
            raise ValueError(
                f"Failed-field metadata mismatch: {row['translation_id']} "
                f"metadata={sorted(failed_fields)}, actual={actual_empty_fields}"
            )
        if status == "ok" and (retry_events or failed_fields or not eligible):
            raise ValueError(f"Inconsistent ok translation metadata: {row['translation_id']}")
        if status == "recovered_after_empty_retry" and (
            not retry_events or failed_fields or not eligible
        ):
            raise ValueError(f"Inconsistent recovered translation metadata: {row['translation_id']}")
        if status == "failed_empty_after_retry" and (
            not retry_events or not failed_fields or eligible
        ):
            raise ValueError(f"Inconsistent failed translation metadata: {row['translation_id']}")
        for event in retry_events:
            if event.get("translation_id") != row["translation_id"]:
                raise ValueError(f"Retry event ID mismatch: {row['translation_id']}")
            if event.get("field_name") not in TRANSLATABLE_FIELDS:
                raise ValueError(f"Retry event field mismatch: {row['translation_id']}")
            if event.get("retry_status") not in {
                "recovered_after_empty_retry",
                "failed_empty_after_retry",
            }:
                raise ValueError(f"Retry event status mismatch: {row['translation_id']}")
            if event.get("source_fallback_used") is not False:
                raise ValueError(f"Source fallback detected: {row['translation_id']}")
        expected_raw = render_with_source_layout(
            str(row["source_question_raw"]),
            str(row["translated_question_stem"]),
            {key: str(value) for key, value in row["translated_options"].items()},
        )
        if expected_raw != row["translated_question_raw"]:
            raise ValueError(f"Translated raw rendering mismatch: {row['translation_id']}")
        if "text_dependency" in row:
            raise ValueError("Translation artifact must not contain text_dependency.")


def top_level_diff(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    keys = sorted(set(left) | set(right))
    return [key for key in keys if left.get(key) != right.get(key)]


def normalized_image_assets(paths: Iterable[str]) -> list[str]:
    normalized = []
    for raw_path in paths:
        value = str(raw_path).replace("\\", "/")
        marker = "/images/"
        if marker in value:
            value = value.split(marker, 1)[1]
        normalized.append(value.lstrip("/"))
    return normalized
