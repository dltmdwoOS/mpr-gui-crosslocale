from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from difflib import SequenceMatcher
from pathlib import Path
from statistics import mean, median
from typing import Any

from mpr_crosslocale.data.options import parse_question_options
from mpr_crosslocale.data.schema import LABELS
from mpr_crosslocale.interventions.rq4_contextual import (
    EXPECTED_INTERVENTION_ROWS,
    human_reference_map_from_original_controls,
    read_jsonl,
)

QUOTE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'"([^"\n]{1,240})"'),
    # A boundary check prevents apostrophes in words such as l'interface from
    # being interpreted as quotation marks.
    re.compile(r"(?<!\w)'([^'\n]{1,240})'(?!\w)"),
    re.compile(r"“([^”\n]{1,240})”"),
    re.compile(r"‘([^’\n]{1,240})’"),
    re.compile(r"«\s*([^»\n]{1,240}?)\s*»"),
    re.compile(r"‹\s*([^›\n]{1,240}?)\s*›"),
    re.compile(r"「([^」\n]{1,240})」"),
    re.compile(r"『([^』\n]{1,240})』"),
)

CORRESPONDENCE_METRICS = (
    "quoted_exact_precision",
    "quoted_exact_recall",
    "quoted_exact_f1",
    "quoted_aligned_edit_similarity",
    "question_edit_similarity",
    "question_char_ngram_fscore",
    "mean_option_edit_similarity",
    "min_option_edit_similarity",
    "mean_option_char_ngram_fscore",
    "min_option_char_ngram_fscore",
    "gold_option_edit_similarity",
    "mean_wrong_option_edit_similarity",
    "gold_minus_wrong_option_edit_similarity",
    "gold_option_char_ngram_fscore",
    "mean_wrong_option_char_ngram_fscore",
    "gold_minus_wrong_option_char_ngram_fscore",
)


def normalize_correspondence_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value))
    normalized = " ".join(normalized.split())
    return normalized.casefold().strip()


def extract_quoted_spans(value: str) -> list[str]:
    candidates: list[tuple[int, int, str]] = []
    for pattern in QUOTE_PATTERNS:
        for match in pattern.finditer(str(value)):
            span = match.group(1).strip()
            if span:
                candidates.append((match.start(), match.end(), span))

    # Prefer the longest match when different quote systems produce an
    # overlapping candidate, then restore source order.
    accepted: list[tuple[int, int, str]] = []
    for candidate in sorted(candidates, key=lambda item: (item[0], -(item[1] - item[0]))):
        start, end, _ = candidate
        if any(start < prior_end and prior_start < end for prior_start, prior_end, _ in accepted):
            continue
        accepted.append(candidate)
    return [span for _, _, span in sorted(accepted)]


def normalized_edit_similarity(left: str, right: str) -> float:
    return SequenceMatcher(
        None,
        normalize_correspondence_text(left),
        normalize_correspondence_text(right),
        autojunk=False,
    ).ratio()


def _ngrams(value: str, order: int) -> Counter[str]:
    if len(value) < order:
        return Counter()
    return Counter(value[index : index + order] for index in range(len(value) - order + 1))


def character_ngram_fscore(
    candidate: str, reference: str, max_order: int = 6, beta: float = 2.0
) -> float:
    """A dependency-free chrF-style character n-gram score in [0, 1].

    This is deliberately named as a chrF-style diagnostic rather than claiming
    bit-for-bit equivalence with sacreBLEU. Whitespace is removed, character
    orders 1..6 are macro-averaged, and recall receives beta=2 weight.
    """

    candidate_norm = "".join(normalize_correspondence_text(candidate).split())
    reference_norm = "".join(normalize_correspondence_text(reference).split())
    if candidate_norm == reference_norm:
        return 1.0
    if not candidate_norm or not reference_norm:
        return 0.0

    precisions: list[float] = []
    recalls: list[float] = []
    for order in range(1, max_order + 1):
        candidate_ngrams = _ngrams(candidate_norm, order)
        reference_ngrams = _ngrams(reference_norm, order)
        if not candidate_ngrams or not reference_ngrams:
            continue
        overlap = sum((candidate_ngrams & reference_ngrams).values())
        precisions.append(overlap / sum(candidate_ngrams.values()))
        recalls.append(overlap / sum(reference_ngrams.values()))
    if not precisions:
        return 0.0
    precision = mean(precisions)
    recall = mean(recalls)
    if precision == 0.0 and recall == 0.0:
        return 0.0
    beta_squared = beta**2
    return (1.0 + beta_squared) * precision * recall / (
        beta_squared * precision + recall
    )


def _field_values(question_stem: str, options: dict[str, str]) -> dict[str, str]:
    return {
        "question_stem": str(question_stem),
        **{label: str(options[label]) for label in LABELS},
    }


def _align_field_spans(
    translated: list[str], human: list[str], field: str
) -> list[dict[str, Any]]:
    candidates = sorted(
        (
            normalized_edit_similarity(translated_value, human_value),
            translated_index,
            human_index,
        )
        for translated_index, translated_value in enumerate(translated)
        for human_index, human_value in enumerate(human)
    )
    candidates.reverse()
    used_translated: set[int] = set()
    used_human: set[int] = set()
    alignments: list[dict[str, Any]] = []
    for similarity, translated_index, human_index in candidates:
        if translated_index in used_translated or human_index in used_human:
            continue
        used_translated.add(translated_index)
        used_human.add(human_index)
        translated_value = translated[translated_index]
        human_value = human[human_index]
        alignments.append(
            {
                "field": field,
                "translated_span_index": translated_index,
                "human_span_index": human_index,
                "translated_span": translated_value,
                "human_span": human_value,
                "translated_span_normalized": normalize_correspondence_text(
                    translated_value
                ),
                "human_span_normalized": normalize_correspondence_text(human_value),
                "normalized_exact_match": int(
                    normalize_correspondence_text(translated_value)
                    == normalize_correspondence_text(human_value)
                ),
                "normalized_edit_similarity": similarity,
                "alignment_status": "paired",
            }
        )
    for translated_index, translated_value in enumerate(translated):
        if translated_index in used_translated:
            continue
        alignments.append(
            {
                "field": field,
                "translated_span_index": translated_index,
                "human_span_index": None,
                "translated_span": translated_value,
                "human_span": "",
                "translated_span_normalized": normalize_correspondence_text(
                    translated_value
                ),
                "human_span_normalized": "",
                "normalized_exact_match": 0,
                "normalized_edit_similarity": 0.0,
                "alignment_status": "translated_only",
            }
        )
    for human_index, human_value in enumerate(human):
        if human_index in used_human:
            continue
        alignments.append(
            {
                "field": field,
                "translated_span_index": None,
                "human_span_index": human_index,
                "translated_span": "",
                "human_span": human_value,
                "translated_span_normalized": "",
                "human_span_normalized": normalize_correspondence_text(human_value),
                "normalized_exact_match": 0,
                "normalized_edit_similarity": 0.0,
                "alignment_status": "human_only",
            }
        )
    return sorted(
        alignments,
        key=lambda row: (
            row["field"],
            row["translated_span_index"] is None,
            row["translated_span_index"] if row["translated_span_index"] is not None else 10_000,
            row["human_span_index"] if row["human_span_index"] is not None else 10_000,
        ),
    )


def correspondence_metrics(
    translated_question_stem: str,
    translated_options: dict[str, str],
    human_question_stem: str,
    human_options: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    translated_fields = _field_values(translated_question_stem, translated_options)
    human_fields = _field_values(human_question_stem, human_options)
    alignments: list[dict[str, Any]] = []
    translated_count = 0
    human_count = 0
    for field in ("question_stem", *LABELS):
        translated_spans = extract_quoted_spans(translated_fields[field])
        human_spans = extract_quoted_spans(human_fields[field])
        translated_count += len(translated_spans)
        human_count += len(human_spans)
        alignments.extend(_align_field_spans(translated_spans, human_spans, field))

    exact_matches = sum(row["normalized_exact_match"] for row in alignments)
    paired_similarity_sum = sum(
        row["normalized_edit_similarity"]
        for row in alignments
        if row["alignment_status"] == "paired"
    )
    quoted_denominator = max(translated_count, human_count)
    quoted_exact_precision = (
        exact_matches / translated_count if translated_count else None
    )
    quoted_exact_recall = exact_matches / human_count if human_count else None
    quoted_exact_f1 = (
        2.0 * exact_matches / (translated_count + human_count)
        if translated_count + human_count
        else None
    )
    quoted_edit = (
        paired_similarity_sum / quoted_denominator if quoted_denominator else None
    )

    option_edit: dict[str, float] = {}
    option_char: dict[str, float] = {}
    option_exact: dict[str, int] = {}
    for label in LABELS:
        option_edit[label] = normalized_edit_similarity(
            translated_options[label], human_options[label]
        )
        option_char[label] = character_ngram_fscore(
            translated_options[label], human_options[label]
        )
        option_exact[label] = int(
            normalize_correspondence_text(translated_options[label])
            == normalize_correspondence_text(human_options[label])
        )

    metrics: dict[str, Any] = {
        "translated_quoted_span_count": translated_count,
        "human_quoted_span_count": human_count,
        "quoted_exact_match_count": exact_matches,
        "quoted_exact_precision": quoted_exact_precision,
        "quoted_exact_recall": quoted_exact_recall,
        "quoted_exact_f1": quoted_exact_f1,
        "quoted_aligned_edit_similarity": quoted_edit,
        "question_edit_similarity": normalized_edit_similarity(
            translated_question_stem, human_question_stem
        ),
        "question_char_ngram_fscore": character_ngram_fscore(
            translated_question_stem, human_question_stem
        ),
        "exact_option_match_count": sum(option_exact.values()),
        "mean_option_edit_similarity": mean(option_edit.values()),
        "min_option_edit_similarity": min(option_edit.values()),
        "mean_option_char_ngram_fscore": mean(option_char.values()),
        "min_option_char_ngram_fscore": min(option_char.values()),
    }
    for label in LABELS:
        metrics[f"option_{label}_normalized_exact_match"] = option_exact[label]
        metrics[f"option_{label}_edit_similarity"] = option_edit[label]
        metrics[f"option_{label}_char_ngram_fscore"] = option_char[label]
    return metrics, alignments


def _read_annotations(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = {str(row["parallel_id"]): str(row["text_dependency"]) for row in rows}
    if len(result) != 366 or set(result.values()) != {"dependent", "independent"}:
        raise ValueError("Expected 366 adjudicated dependent/independent annotations.")
    return result


def _read_inference(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    rows = read_jsonl(path)
    by_translation = {str(row["translation_id"]): row for row in rows}
    if len(by_translation) != len(rows):
        raise ValueError("Duplicate translation_id in downstream inference results.")
    return by_translation


QWEN_VISION_END = "<|vision_end|>"
QWEN_ANSWER_SUFFIX = "\n\nRespond with exactly one label: A, B, C, or D."


def _question_raw_from_qwen_prompt(row: dict[str, Any]) -> str:
    """Recover the exact MCQ supplied to Qwen from a frozen inference row.

    The recovered text is accepted only if its SHA-256 matches the hash written
    by the inference runner. This makes the fallback equivalent to reading the
    missing translation manifest rather than heuristically extracting text.
    """

    rendered = str(row.get("rendered_prompt", ""))
    if QWEN_VISION_END not in rendered or QWEN_ANSWER_SUFFIX not in rendered:
        raise ValueError(
            f"Unsupported rendered prompt for {row.get('translation_id', '<unknown>')}"
        )
    after_image = rendered.split(QWEN_VISION_END, 1)[1]
    question_raw = after_image.split(QWEN_ANSWER_SUFFIX, 1)[0]
    expected_hash = str(row.get("question_raw_sha256", ""))
    actual_hash = hashlib.sha256(question_raw.encode("utf-8")).hexdigest()
    if not expected_hash or actual_hash != expected_hash:
        raise ValueError(
            "Recovered question hash mismatch for "
            f"{row.get('translation_id', '<unknown>')}: "
            f"expected={expected_hash}, actual={actual_hash}"
        )
    return question_raw


def translations_from_inference_rows(
    inference_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reconstruct the frozen translation fields from downstream Qwen prompts."""

    translations: list[dict[str, Any]] = []
    for row in inference_rows:
        question_raw = _question_raw_from_qwen_prompt(row)
        parsed = parse_question_options(question_raw)
        if parsed.option_parse_status != "ok" or parsed.option_order != list(LABELS):
            raise ValueError(
                "Recovered MCQ structure invalid for "
                f"{row.get('translation_id', '<unknown>')}: "
                f"{parsed.option_parse_status}, order={parsed.option_order}"
            )
        translations.append(
            {
                "translation_id": str(row["translation_id"]),
                "pair_id": str(row["pair_id"]),
                "parallel_id": str(row["parallel_id"]),
                "source_language": str(row["source_question_language"]),
                "target_language": str(row["gui_language"]),
                "target_human_parallel_endpoint_id": str(
                    row["target_human_parallel_endpoint_id"]
                ),
                "translated_question_stem": parsed.question_stem,
                "translated_options": parsed.options,
                "gold_label": str(row["gold_label"]),
                "translation_status": str(row.get("translation_status", "unknown")),
                "translation_analysis_eligible": bool(
                    row.get("translation_analysis_eligible", False)
                ),
                "semantic_diagnostic_flags": list(
                    row.get("translation_semantic_diagnostic_flags", [])
                ),
            }
        )
    return translations


def build_diagnostics(
    translations: list[dict[str, Any]],
    human_by_endpoint: dict[str, dict[str, Any]],
    annotations: dict[str, str] | None = None,
    inference_by_translation: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    annotations = annotations or {}
    inference_by_translation = inference_by_translation or {}
    diagnostic_rows: list[dict[str, Any]] = []
    alignment_rows: list[dict[str, Any]] = []
    for translation in sorted(translations, key=lambda row: str(row["translation_id"])):
        endpoint_id = str(translation["target_human_parallel_endpoint_id"])
        if endpoint_id not in human_by_endpoint:
            raise ValueError(f"Missing target human endpoint: {endpoint_id}")
        human = human_by_endpoint[endpoint_id]
        translated_options = {
            label: str(translation["translated_options"][label]) for label in LABELS
        }
        human_options = {label: str(human["options"][label]) for label in LABELS}
        translation_id = str(translation["translation_id"])
        metrics, alignments = correspondence_metrics(
            str(translation["translated_question_stem"]),
            translated_options,
            str(human["question_stem"]),
            human_options,
        )
        gold_label = str(translation["gold_label"])
        if gold_label not in LABELS:
            raise ValueError(f"Invalid gold label: {translation_id}")
        wrong_labels = [label for label in LABELS if label != gold_label]
        gold_edit = float(metrics[f"option_{gold_label}_edit_similarity"])
        wrong_edit = mean(
            float(metrics[f"option_{label}_edit_similarity"])
            for label in wrong_labels
        )
        gold_char = float(metrics[f"option_{gold_label}_char_ngram_fscore"])
        wrong_char = mean(
            float(metrics[f"option_{label}_char_ngram_fscore"])
            for label in wrong_labels
        )
        metrics.update(
            {
                "gold_option_edit_similarity": gold_edit,
                "mean_wrong_option_edit_similarity": wrong_edit,
                "gold_minus_wrong_option_edit_similarity": gold_edit - wrong_edit,
                "gold_option_char_ngram_fscore": gold_char,
                "mean_wrong_option_char_ngram_fscore": wrong_char,
                "gold_minus_wrong_option_char_ngram_fscore": gold_char - wrong_char,
            }
        )
        inference = inference_by_translation.get(translation_id)
        base = {
            "translation_id": translation_id,
            "pair_id": str(translation["pair_id"]),
            "parallel_id": str(translation["parallel_id"]),
            "source_language": str(translation["source_language"]),
            "target_language": str(translation["target_language"]),
            "gold_label": gold_label,
            "text_dependency": annotations.get(str(translation["parallel_id"]), ""),
            "translation_status": str(translation["translation_status"]),
            "translation_analysis_eligible": int(
                bool(translation["translation_analysis_eligible"])
            ),
            "semantic_diagnostic_flag_count": len(
                translation.get("semantic_diagnostic_flags", [])
            ),
            "semantic_diagnostic_flags": json.dumps(
                translation.get("semantic_diagnostic_flags", []), ensure_ascii=False
            ),
            "downstream_generation_correct": (
                int(inference["generation_correct"]) if inference is not None else ""
            ),
            "downstream_parse_success": (
                int(bool(inference["parse_success"])) if inference is not None else ""
            ),
            **metrics,
        }
        diagnostic_rows.append(base)
        for alignment in alignments:
            alignment_rows.append(
                {
                    "translation_id": translation_id,
                    "pair_id": base["pair_id"],
                    "parallel_id": base["parallel_id"],
                    "source_language": base["source_language"],
                    "target_language": base["target_language"],
                    "text_dependency": base["text_dependency"],
                    **alignment,
                }
            )
    if inference_by_translation:
        missing = set(inference_by_translation) - {
            row["translation_id"] for row in diagnostic_rows
        }
        if missing:
            raise ValueError(
                f"Inference contains {len(missing)} translation IDs outside the artifact."
            )
    return diagnostic_rows, alignment_rows


def _finite_values(rows: list[dict[str, Any]], field: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(field)
        if value in (None, ""):
            continue
        numeric = float(value)
        if math.isfinite(numeric):
            values.append(numeric)
    return values


def summarize_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {
        ("overall", "all"): rows
    }
    definitions = {
        "source_language": lambda row: str(row["source_language"]),
        "target_language": lambda row: str(row["target_language"]),
        "direction": lambda row: f"{row['source_language']}->{row['target_language']}",
        "text_dependency": lambda row: str(row["text_dependency"]),
    }
    for group_type, getter in definitions.items():
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            value = getter(row)
            if value:
                buckets[value].append(row)
        for value, members in buckets.items():
            groups[(group_type, value)] = members

    summaries: list[dict[str, Any]] = []
    for (group_type, group_value), members in sorted(groups.items()):
        summary: dict[str, Any] = {
            "group_type": group_type,
            "group_value": group_value,
            "n_rows": len(members),
            "rows_with_human_quoted_spans": sum(
                int(row["human_quoted_span_count"]) > 0 for row in members
            ),
            "rows_with_translated_quoted_spans": sum(
                int(row["translated_quoted_span_count"]) > 0 for row in members
            ),
        }
        for field in CORRESPONDENCE_METRICS:
            values = _finite_values(members, field)
            summary[f"{field}_n"] = len(values)
            summary[f"{field}_mean"] = mean(values) if values else None
            summary[f"{field}_median"] = median(values) if values else None
        outcomes = _finite_values(members, "downstream_generation_correct")
        summary["downstream_accuracy"] = mean(outcomes) if outcomes else None
        summaries.append(summary)
    return summaries


def _write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    values = list(rows)
    if not values:
        raise ValueError(f"Cannot write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(values[0]))
        writer.writeheader()
        writer.writerows(values)
    temporary.replace(path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Measure quoted-span and option-level correspondence between an RQ4 "
            "translation artifact and the target human-parallel endpoint."
        )
    )
    parser.add_argument("--translations", type=Path, default=None)
    parser.add_argument(
        "--source-controls",
        type=Path,
        default=Path("data/derived/interventions/rel_nllb_original_controls.jsonl"),
    )
    parser.add_argument(
        "--annotations",
        type=Path,
        default=Path(
            "../annotation/rel_text_dependency/outputs/"
            "rel_annotations_integrated_366.csv"
        ),
    )
    parser.add_argument("--inference-results", type=Path, default=None)
    parser.add_argument(
        "--expected-rows",
        type=int,
        default=EXPECTED_INTERVENTION_ROWS,
        help="Use 60 for the frozen smoke cohort; defaults to the full 10,980 rows.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.translations is None and args.inference_results is None:
        parser.error("Provide --translations or --inference-results.")

    translation_source_mode = "translation_artifact"
    inference_rows: list[dict[str, Any]] = []
    if args.inference_results is not None:
        inference_rows = read_jsonl(args.inference_results)
    if args.translations is not None:
        print(f"STEP 1/5 reading translations: {args.translations}", flush=True)
        translations = read_jsonl(args.translations)
    else:
        print(
            "STEP 1/5 reconstructing translations from SHA-verified inference prompts: "
            f"{args.inference_results}",
            flush=True,
        )
        translations = translations_from_inference_rows(inference_rows)
        translation_source_mode = "sha256_verified_inference_prompt"
    if len(translations) != args.expected_rows:
        raise ValueError(
            f"Expected {args.expected_rows} translations; found {len(translations)}"
        )
    if len({str(row["translation_id"]) for row in translations}) != len(translations):
        raise ValueError("Duplicate translation_id in translation artifact.")

    print(f"STEP 2/5 reading human endpoints: {args.source_controls}", flush=True)
    controls = read_jsonl(args.source_controls)
    human_by_endpoint = human_reference_map_from_original_controls(controls)
    annotations = _read_annotations(args.annotations)
    inference = (
        {str(row["translation_id"]): row for row in inference_rows}
        if inference_rows
        else {}
    )
    if len(inference) != len(inference_rows):
        raise ValueError("Duplicate translation_id in downstream inference results.")

    print("STEP 3/5 computing correspondence diagnostics", flush=True)
    rows, alignments = build_diagnostics(
        translations, human_by_endpoint, annotations, inference
    )
    summaries = summarize_groups(rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"STEP 4/5 writing row and alignment tables: {args.output_dir}", flush=True)
    _write_csv(args.output_dir / "rq4_correspondence_rows.csv", rows)
    _write_csv(
        args.output_dir / "rq4_quoted_span_alignments.csv", alignments
    )
    _write_csv(
        args.output_dir / "rq4_correspondence_summary_by_group.csv", summaries
    )

    overall = next(
        row
        for row in summaries
        if row["group_type"] == "overall" and row["group_value"] == "all"
    )
    report = {
        "status": "complete",
        "rows": len(rows),
        "quoted_alignment_rows": len(alignments),
        "human_endpoints": len(human_by_endpoint),
        "inference_joined": bool(inference),
        "translation_source_mode": translation_source_mode,
        "metrics_are_diagnostic_not_exclusion_criteria": True,
        "overall": overall,
        "outputs": {
            "rows": str(args.output_dir / "rq4_correspondence_rows.csv"),
            "quoted_alignments": str(
                args.output_dir / "rq4_quoted_span_alignments.csv"
            ),
            "group_summary": str(
                args.output_dir / "rq4_correspondence_summary_by_group.csv"
            ),
        },
    }
    summary_path = args.output_dir / "rq4_correspondence_summary.json"
    summary_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("STEP 5/5 complete", flush=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
