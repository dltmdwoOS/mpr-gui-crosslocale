from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal

from mpr_crosslocale.data.schema import LANGUAGES

LanguagePair = tuple[str, str]
SampleUnit = Literal["semantic_items", "evaluations", "per_pair"]


@dataclass(frozen=True)
class CrossLocalePlan:
    rows: list[dict[str, Any]]
    language_pairs: list[LanguagePair]
    n_semantic_items: int
    n_evaluations: int
    missing: list[dict[str, Any]]


def parse_language_pairs(values: list[str] | None) -> list[LanguagePair]:
    if not values:
        return [(lq, lg) for lq in LANGUAGES for lg in LANGUAGES]
    pairs: list[LanguagePair] = []
    for value in values:
        if ":" not in value:
            raise ValueError(f"Language pair must use q:gui format, got {value!r}")
        question_language, gui_language = value.split(":", 1)
        _validate_language(question_language)
        _validate_language(gui_language)
        pairs.append((question_language, gui_language))
    return pairs


def build_language_pairs(
    question_languages: list[str] | None,
    gui_languages: list[str] | None,
    include_matched: bool = True,
    include_mismatch: bool = True,
) -> list[LanguagePair]:
    q_langs = question_languages or list(LANGUAGES)
    g_langs = gui_languages or list(LANGUAGES)
    for language in [*q_langs, *g_langs]:
        _validate_language(language)
    pairs = []
    for question_language in q_langs:
        for gui_language in g_langs:
            matched = question_language == gui_language
            if matched and not include_matched:
                continue
            if not matched and not include_mismatch:
                continue
            pairs.append((question_language, gui_language))
    return pairs


def build_cross_locale_plan(
    manifest_rows: list[dict[str, Any]],
    language_pairs: list[LanguagePair],
    dimensions: set[str] | None,
    sample_size: int | None,
    sample_unit: SampleUnit,
    seed: int,
) -> CrossLocalePlan:
    by_parallel_language = {
        (str(row["parallel_id"]), str(row["language"])): row
        for row in manifest_rows
        if dimensions is None or str(row["dimension"]) in dimensions
    }
    parallel_ids = sorted({parallel_id for parallel_id, _ in by_parallel_language})
    missing: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for parallel_id in parallel_ids:
        for question_language, gui_language in language_pairs:
            question_row = by_parallel_language.get((parallel_id, question_language))
            gui_row = by_parallel_language.get((parallel_id, gui_language))
            if question_row is None or gui_row is None:
                missing.append(
                    {
                        "parallel_id": parallel_id,
                        "question_language": question_language,
                        "gui_language": gui_language,
                        "missing_question": question_row is None,
                        "missing_gui": gui_row is None,
                    }
                )
                continue
            candidates.append(_build_eval_row(question_row, gui_row))

    if sample_size is None:
        selected = candidates
    elif sample_unit == "evaluations":
        selected = _stable_sample(candidates, sample_size, seed)
    elif sample_unit == "per_pair":
        selected = []
        by_pair = _group_by_pair(candidates)
        for pair in language_pairs:
            selected.extend(_stratified_sample(by_pair.get(pair, []), sample_size, seed + _pair_seed(pair)))
        selected.sort(key=_row_sort_key)
    elif sample_unit == "semantic_items":
        common_ids = _common_parallel_ids(candidates, language_pairs)
        sampled_ids = set(_stratified_parallel_ids(candidates, common_ids, sample_size, seed))
        selected = [row for row in candidates if row["parallel_id"] in sampled_ids]
    else:
        raise ValueError(f"Unknown sample unit: {sample_unit}")

    return CrossLocalePlan(
        rows=selected,
        language_pairs=language_pairs,
        n_semantic_items=len({row["parallel_id"] for row in selected}),
        n_evaluations=len(selected),
        missing=missing,
    )


def _build_eval_row(question_row: dict[str, Any], gui_row: dict[str, Any]) -> dict[str, Any]:
    question_language = str(question_row["language"])
    gui_language = str(gui_row["language"])
    parallel_id = str(question_row["parallel_id"])
    condition = "canonical_matched" if question_language == gui_language else "raw_mismatch"
    return {
        "input_id": f"cross_locale::{parallel_id}::q={question_language}::gui={gui_language}",
        "condition": condition,
        "matched": question_language == gui_language,
        "parallel_id": parallel_id,
        "semantic_item_id": parallel_id,
        "question_sample_id": question_row["sample_id"],
        "gui_sample_id": gui_row["sample_id"],
        "question_language": question_language,
        "gui_language": gui_language,
        "dimension": question_row["dimension"],
        "question_raw": question_row["question_raw"],
        "question_stem": question_row.get("question_stem"),
        "options": question_row.get("options", {}),
        "option_order": question_row.get("option_order", ["A", "B", "C", "D"]),
        "answer_raw": question_row["answer_raw"],
        "gold_label": question_row["gold_label"],
        "image_paths": gui_row["image_paths"],
        "num_images": gui_row["num_images"],
        "frame_order": gui_row["frame_order"],
    }


def _common_parallel_ids(rows: list[dict[str, Any]], pairs: list[LanguagePair]) -> list[str]:
    seen: dict[str, set[LanguagePair]] = defaultdict(set)
    for row in rows:
        seen[row["parallel_id"]].add((row["question_language"], row["gui_language"]))
    required = set(pairs)
    return sorted(parallel_id for parallel_id, present in seen.items() if required.issubset(present))


def _stratified_parallel_ids(
    rows: list[dict[str, Any]], parallel_ids: list[str], sample_size: int, seed: int
) -> list[str]:
    by_parallel = {row["parallel_id"]: row for row in rows if row["parallel_id"] in parallel_ids}
    groups: dict[str, list[str]] = defaultdict(list)
    for parallel_id in parallel_ids:
        groups[str(by_parallel[parallel_id]["dimension"])].append(parallel_id)
    return _round_robin_sample(groups, sample_size, seed)


def _stratified_sample(rows: list[dict[str, Any]], sample_size: int, seed: int) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["dimension"])].append(row)
    sampled_keys = _round_robin_sample(groups, sample_size, seed)
    return sorted(sampled_keys, key=_row_sort_key)


def _round_robin_sample(groups: dict[str, list[Any]], sample_size: int, seed: int) -> list[Any]:
    rng = random.Random(seed)
    shuffled = {key: list(values) for key, values in groups.items()}
    for values in shuffled.values():
        rng.shuffle(values)
    selected: list[Any] = []
    keys = sorted(shuffled)
    while len(selected) < sample_size and any(shuffled.values()):
        for key in keys:
            if shuffled[key] and len(selected) < sample_size:
                selected.append(shuffled[key].pop())
    return selected


def _stable_sample(rows: list[dict[str, Any]], sample_size: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    copied = list(rows)
    rng.shuffle(copied)
    return sorted(copied[:sample_size], key=_row_sort_key)


def _group_by_pair(rows: list[dict[str, Any]]) -> dict[LanguagePair, list[dict[str, Any]]]:
    grouped: dict[LanguagePair, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["question_language"], row["gui_language"])].append(row)
    return grouped


def _row_sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row["parallel_id"]), str(row["question_language"]), str(row["gui_language"]))


def _pair_seed(pair: LanguagePair) -> int:
    return sum(ord(ch) for ch in f"{pair[0]}:{pair[1]}")


def _validate_language(language: str) -> None:
    if language not in LANGUAGES:
        raise ValueError(f"Unsupported language {language!r}; expected one of {', '.join(LANGUAGES)}")
