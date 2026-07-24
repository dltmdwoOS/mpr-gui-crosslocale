from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from mpr_crosslocale.data.schema import LABELS, LANGUAGES
from mpr_crosslocale.inference.runtime import read_jsonl


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eval_rows = [row for row in rows if row.get("status") == "success"]
    grouped_pair = _group(eval_rows, ("question_language", "gui_language"))
    grouped_dim_pair = _group(eval_rows, ("dimension", "question_language", "gui_language"))
    matched = [row for row in eval_rows if row.get("matched") is True]
    mismatch = [row for row in eval_rows if row.get("matched") is False]
    predictions = [row.get("scored_predicted_label") or row.get("parsed_generated_label") for row in eval_rows]
    golds = [row.get("gold_label") for row in eval_rows]
    return {
        "counts": {
            "rows": len(rows),
            "success": len(eval_rows),
            "failed": sum(1 for row in rows if row.get("status") == "failed"),
            "dry_run": sum(1 for row in rows if row.get("status") == "dry_run"),
            "semantic_items": len({row.get("parallel_id") for row in eval_rows}),
            "missing_rows": sum(1 for row in rows if row.get("status") == "missing"),
        },
        "overall_accuracy": _accuracy(eval_rows),
        "accuracy_matrix": _matrix(grouped_pair),
        "dimension_accuracy_matrix": _dimension_matrices(grouped_dim_pair),
        "matched_mean": _accuracy(matched),
        "mismatch_mean": _accuracy(mismatch),
        "matched_mismatch_delta": _accuracy(matched) - _accuracy(mismatch),
        "directional_deltas": _directional_deltas(grouped_pair),
        "query_language_mean": _means(_group(eval_rows, ("question_language",))),
        "gui_language_mean": _means(_group(eval_rows, ("gui_language",))),
        "dimension_mean": _means(_group(eval_rows, ("dimension",))),
        "macro_f1": _macro_f1(predictions, golds),
        "balanced_accuracy": _balanced_accuracy(predictions, golds),
        "gold_label_distribution": dict(Counter(golds)),
        "predicted_label_distribution": dict(Counter(predictions)),
        "majority_label_baseline": _majority_label_baseline(golds),
        "mean_gold_probability": _mean_field(eval_rows, "gold_probability"),
        "mean_top1_top2_margin": _mean_field(eval_rows, "top1_top2_margin"),
        "mean_gold_vs_best_wrong_margin": _mean_field(eval_rows, "gold_vs_best_wrong_margin"),
        "mean_entropy": _mean_field(eval_rows, "entropy"),
        "parsing_failure_rate": _rate(eval_rows, lambda row: row.get("parse_success") is False),
        "scoring_generation_disagreement_rate": _rate(
            eval_rows, lambda row: row.get("generation_scoring_disagreement") is True
        ),
    }


def write_csv_summary(summary: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["section", "key", "question_language", "gui_language", "value", "n"],
        )
        writer.writeheader()
        for q_lang, row in summary["accuracy_matrix"].items():
            for g_lang, cell in row.items():
                writer.writerow(
                    {
                        "section": "accuracy_matrix",
                        "key": "",
                        "question_language": q_lang,
                        "gui_language": g_lang,
                        "value": cell["accuracy"],
                        "n": cell["n"],
                    }
                )
        for key in ("overall_accuracy", "matched_mean", "mismatch_mean", "macro_f1", "balanced_accuracy"):
            writer.writerow({"section": "scalar", "key": key, "value": summary[key], "n": ""})


def _group(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(key) for key in keys)].append(row)
    return grouped


def _matrix(grouped: dict[tuple[Any, ...], list[dict[str, Any]]]) -> dict[str, dict[str, dict[str, Any]]]:
    matrix: dict[str, dict[str, dict[str, Any]]] = {}
    for q_lang in LANGUAGES:
        matrix[q_lang] = {}
        for g_lang in LANGUAGES:
            rows = grouped.get((q_lang, g_lang), [])
            matrix[q_lang][g_lang] = {"accuracy": _accuracy(rows), "n": len(rows)}
    return matrix


def _dimension_matrices(
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]]
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    dimensions = sorted({key[0] for key in grouped})
    output = {}
    for dimension in dimensions:
        pair_group = {
            (q_lang, g_lang): rows
            for (dim, q_lang, g_lang), rows in grouped.items()
            if dim == dimension
        }
        output[str(dimension)] = _matrix(pair_group)
    return output


def _means(grouped: dict[tuple[Any, ...], list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    return {str(key[0]): {"accuracy": _accuracy(rows), "n": len(rows)} for key, rows in grouped.items()}


def _directional_deltas(grouped: dict[tuple[Any, ...], list[dict[str, Any]]]) -> dict[str, float]:
    deltas = {}
    for q_lang in LANGUAGES:
        for g_lang in LANGUAGES:
            if q_lang >= g_lang:
                continue
            forward = _accuracy(grouped.get((q_lang, g_lang), []))
            backward = _accuracy(grouped.get((g_lang, q_lang), []))
            deltas[f"{q_lang}->{g_lang}_minus_{g_lang}->{q_lang}"] = forward - backward
    return deltas


def _accuracy(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return sum(row.get("correct") is True for row in rows) / len(rows)


def _macro_f1(predictions: list[Any], golds: list[Any]) -> float:
    if not golds:
        return 0.0
    scores = []
    for label in LABELS:
        tp = sum(pred == label and gold == label for pred, gold in zip(predictions, golds))
        fp = sum(pred == label and gold != label for pred, gold in zip(predictions, golds))
        fn = sum(pred != label and gold == label for pred, gold in zip(predictions, golds))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return sum(scores) / len(scores)


def _balanced_accuracy(predictions: list[Any], golds: list[Any]) -> float:
    recalls = []
    for label in LABELS:
        positives = sum(gold == label for gold in golds)
        if positives:
            recalls.append(sum(pred == label and gold == label for pred, gold in zip(predictions, golds)) / positives)
    return sum(recalls) / len(recalls) if recalls else 0.0


def _majority_label_baseline(golds: list[Any]) -> dict[str, Any]:
    if not golds:
        return {"label": None, "accuracy": 0.0}
    counts = Counter(golds)
    label, count = counts.most_common(1)[0]
    return {"label": label, "accuracy": count / len(golds)}


def _mean_field(rows: list[dict[str, Any]], field: str) -> float:
    values = [float(row[field]) for row in rows if row.get(field) is not None]
    return sum(values) / len(values) if values else 0.0


def _rate(rows: list[dict[str, Any]], predicate) -> float:
    if not rows:
        return 0.0
    return sum(1 for row in rows if predicate(row)) / len(rows)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Summarize cross-locale JSONL results.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--csv-out", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = summarize(read_jsonl(args.input))
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv_summary(summary, args.csv_out)


if __name__ == "__main__":
    main()
