#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mpr_crosslocale.analysis.summarize_cross_locale import summarize  # noqa: E402
from mpr_crosslocale.data.cross_locale_sampling import build_cross_locale_plan  # noqa: E402
from mpr_crosslocale.inference.label_scoring import summarize_label_logprobs  # noqa: E402
from mpr_crosslocale.inference.prompts import build_prompt_text  # noqa: E402
from mpr_crosslocale.inference.runtime import append_jsonl, read_jsonl, resolve_paths  # noqa: E402
from mpr_crosslocale.inference.system_prompts import build_system_prompt  # noqa: E402

DEMO_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = DEMO_DIR / "outputs"
IMAGES_DIR = OUTPUT_DIR / "images"
FIXTURE_MANIFEST = OUTPUT_DIR / "demo_fixture_manifest.jsonl"
RESULTS_PATH = OUTPUT_DIR / "demo_results.jsonl"
SUMMARY_PATH = OUTPUT_DIR / "demo_summary.json"
MATRIX_PATH = OUTPUT_DIR / "demo_matrix.csv"
REPORT_PATH = OUTPUT_DIR / "demo_validation_report.txt"

DIMENSIONS = ("wf", "wi", "au", "ap", "ael", "rel")
LANGUAGE_PAIRS = (("en", "ja"), ("ja", "en"))
LABELS = ("A", "B", "C", "D")


@dataclass(frozen=True)
class DemoRunStats:
    planned: int
    written: int
    skipped: int


def fixture_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    gold_cycle = ("A", "B", "C", "D")
    for dim_index, dimension in enumerate(DIMENSIONS):
        for item_index in range(2):
            item_name = f"{dimension}_item_{item_index + 1}"
            parallel_id = f"{dimension}::{item_name}"
            gold_label = gold_cycle[(dim_index + item_index) % len(gold_cycle)]
            for language in ("en", "ja"):
                rows.append(
                    {
                        "sample_id": f"{parallel_id}::{language}",
                        "parallel_id": parallel_id,
                        "semantic_item_id": parallel_id,
                        "dimension": dimension,
                        "language": language,
                        "source_question_id": f"{parallel_id}::{language}",
                        "question_raw": _question_text(language, dimension, item_index),
                        "question_stem": _question_stem(language, dimension, item_index),
                        "options": {
                            "A": "Top left",
                            "B": "Top right",
                            "C": "Bottom left",
                            "D": "Bottom right",
                        },
                        "option_order": list(LABELS),
                        "answer_raw": gold_label,
                        "gold_label": gold_label,
                        "image_paths": [str(_placeholder_image_path(language, dimension, item_index))],
                        "num_images": 1,
                        "frame_order": "single_image",
                    }
                )
    return rows


def write_fixture() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    for language in ("en", "ja"):
        for dimension in DIMENSIONS:
            for item_index in range(2):
                path = _placeholder_image_path(language, dimension, item_index)
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    locale_title = "日本語 GUI デモ" if language == "ja" else "English GUI demo"
                    primary_button = "確認" if language == "ja" else "Confirm"
                    secondary_button = "キャンセル" if language == "ja" else "Cancel"
                    path.write_text(
                        "<svg xmlns='http://www.w3.org/2000/svg' width='320' height='180'>"
                        "<rect width='320' height='180' fill='#f2f2f2'/>"
                        f"<text x='20' y='38' font-size='18'>{locale_title}</text>"
                        f"<text x='20' y='68' font-size='14'>{dimension.upper()} item {item_index + 1}</text>"
                        "<rect x='20' y='100' width='125' height='42' rx='4' fill='#ffffff' stroke='#555555'/>"
                        "<rect x='165' y='100' width='125' height='42' rx='4' fill='#ffffff' stroke='#555555'/>"
                        f"<text x='82' y='126' text-anchor='middle' font-size='14'>{primary_button}</text>"
                        f"<text x='227' y='126' text-anchor='middle' font-size='14'>{secondary_button}</text>"
                        "</svg>\n",
                        encoding="utf-8",
                    )
    rows = fixture_rows()
    FIXTURE_MANIFEST.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def run_demo(args: argparse.Namespace) -> dict[str, Any]:
    if args.clean_demo_output and OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    write_fixture()

    manifest_rows = read_jsonl(FIXTURE_MANIFEST)
    plan = build_cross_locale_plan(
        manifest_rows=manifest_rows,
        language_pairs=list(LANGUAGE_PAIRS),
        dimensions=set(DIMENSIONS),
        sample_size=12,
        sample_unit="semantic_items",
        seed=args.seed,
    )
    rows = resolve_paths(plan.rows, REPO_ROOT)
    first_stats = _write_results(rows, args, resume=False)
    resume_stats = None
    if args.run_resume_check or args.resume:
        resume_stats = _write_results(rows, args, resume=True)

    result_rows = read_jsonl(RESULTS_PATH) if RESULTS_PATH.exists() else []
    summary = _demo_summary(result_rows, plan, first_stats, resume_stats)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_matrix_csv(summary)
    validation = validate_demo(result_rows, plan, args, first_stats, resume_stats)
    _write_validation_report(validation, summary)
    print(json.dumps(summary["counts"], ensure_ascii=False, indent=2))
    print(f"Validation report: {REPORT_PATH}")
    return {"summary": summary, "validation": validation}


def validate_demo(
    rows: list[dict[str, Any]],
    plan,
    args: argparse.Namespace,
    first_stats: DemoRunStats,
    resume_stats: DemoRunStats | None,
) -> list[tuple[str, bool, str]]:
    semantic_ids = {row["parallel_id"] for row in rows}
    by_pair = defaultdict(list)
    by_dim_semantic = defaultdict(set)
    by_dim_eval = Counter()
    for row in rows:
        by_pair[(row["question_language"], row["gui_language"])].append(row)
        by_dim_semantic[row["dimension"]].add(row["parallel_id"])
        by_dim_eval[row["dimension"]] += 1

    same_seed_rows = _planned_mock_rows(plan.rows, args.seed, args.system_prompt_mode)
    other_seed_rows = _planned_mock_rows(plan.rows, args.seed + 1, args.system_prompt_mode)
    same_seed_signature = _signature(same_seed_rows)
    current_signature = _signature(rows)
    other_seed_signature = _signature(other_seed_rows)

    checks = [
        ("semantic item count is 12", len(semantic_ids) == 12, str(len(semantic_ids))),
        ("evaluation count is 24", len(rows) == 24, str(len(rows))),
        (
            "both directions share identical semantic item IDs",
            {r["parallel_id"] for r in by_pair[("en", "ja")]}
            == {r["parallel_id"] for r in by_pair[("ja", "en")]}
            == semantic_ids,
            "",
        ),
        ("en->ja count is 12", len(by_pair[("en", "ja")]) == 12, str(len(by_pair[("en", "ja")])),
        ),
        ("ja->en count is 12", len(by_pair[("ja", "en")]) == 12, str(len(by_pair[("ja", "en")])),
        ),
        ("all six dimensions are present", set(by_dim_semantic) == set(DIMENSIONS), str(sorted(by_dim_semantic))),
        (
            "each dimension has 2 semantic items",
            all(len(by_dim_semantic[dimension]) == 2 for dimension in DIMENSIONS),
            str({dimension: len(by_dim_semantic[dimension]) for dimension in DIMENSIONS}),
        ),
        (
            "each dimension has 4 evaluations",
            all(by_dim_eval[dimension] == 4 for dimension in DIMENSIONS),
            str(dict(by_dim_eval)),
        ),
        (
            "en->ja language fields are correct",
            all(row["question_language"] == "en" and row["gui_language"] == "ja" for row in by_pair[("en", "ja")]),
            "",
        ),
        (
            "ja->en language fields are correct",
            all(row["question_language"] == "ja" and row["gui_language"] == "en" for row in by_pair[("ja", "en")]),
            "",
        ),
        (
            "image paths exist and follow GUI language",
            all(
                row["image_paths"]
                and all(Path(path).exists() for path in row["image_paths"])
                and all(f"/images/{row['gui_language']}/" in path for path in row["image_paths"])
                for row in rows
            ),
            "",
        ),
        ("all rows are mismatch", all(row["matched"] is False for row in rows), ""),
        ("all rows use requested system prompt mode", _system_prompt_mode_ok(rows, args.system_prompt_mode), ""),
        (
            "probabilities sum to 1",
            all(abs(sum(row["label_probabilities"].values()) - 1.0) < 1e-9 for row in rows),
            "",
        ),
        ("gold rank is in 1..4", all(1 <= int(row["gold_rank"]) <= 4 for row in rows), ""),
        (
            "entropy and margins are finite",
            all(
                math.isfinite(float(row["entropy"]))
                and math.isfinite(float(row["top1_top2_margin"]))
                and math.isfinite(float(row["gold_vs_best_wrong_margin"]))
                for row in rows
            ),
            "",
        ),
        ("first run wrote 24 rows", first_stats.written == 24, str(first_stats.written)),
        (
            "resume keeps JSONL at 24 rows",
            resume_stats is not None and resume_stats.skipped == 24 and len(rows) == 24,
            "" if resume_stats is not None else "resume check not run",
        ),
        ("same seed reproduces samples and mock scores", current_signature == same_seed_signature, ""),
        (
            "different seed changes mock scores or sample order",
            current_signature != other_seed_signature,
            "",
        ),
        (
            "system prompt includes A/B/C/D-only instruction",
            all(all(label in row["system_prompt"] for label in LABELS) for row in rows),
            "",
        ),
        (
            "system prompt does not include gold labels as answers",
            all("gold" not in row["system_prompt"].lower() and "correct answer" not in row["system_prompt"].lower() for row in rows),
            "",
        ),
    ]
    return checks


def _write_results(rows: list[dict[str, Any]], args: argparse.Namespace, resume: bool) -> DemoRunStats:
    existing_keys = set()
    if resume and RESULTS_PATH.exists():
        existing_keys = {
            row["demo_resume_key"] for row in read_jsonl(RESULTS_PATH) if row.get("inference_status") == "success"
        }
    written = 0
    skipped = 0
    for row in rows:
        result = _mock_result_row(row, args.seed, args.system_prompt_mode)
        if resume and result["demo_resume_key"] in existing_keys:
            skipped += 1
            continue
        append_jsonl(RESULTS_PATH, [result])
        written += 1
    return DemoRunStats(planned=len(rows), written=written, skipped=skipped)


def _system_prompt_mode_ok(rows: list[dict[str, Any]], mode: str) -> bool:
    if mode == "english_fixed":
        return all(row["system_prompt_mode"] == "english_fixed" and row["system_prompt_language"] == "en" for row in rows)
    if mode == "query_aligned":
        return all(
            row["system_prompt_mode"] == "query_aligned"
            and row["system_prompt_language"] == row["question_language"]
            for row in rows
        )
    return False


def _planned_mock_rows(rows: list[dict[str, Any]], seed: int, system_prompt_mode: str) -> list[dict[str, Any]]:
    return [_mock_result_row(row, seed, system_prompt_mode) for row in rows]


def _mock_result_row(row: dict[str, Any], seed: int, system_prompt_mode: str) -> dict[str, Any]:
    system_prompt, system_language, template_version = build_system_prompt(system_prompt_mode, row["question_language"])
    raw_logprobs = _mock_label_logprobs(row["input_id"], seed)
    score = summarize_label_logprobs(raw_logprobs, row["gold_label"], "demo_mock_logprobs")
    rendered_prompt = f"{system_prompt}\n\n{build_prompt_text(row['question_raw'], 'mpr_label_only_v1')}"
    return {
        "input_id": row["input_id"],
        "demo_resume_key": _demo_resume_key(row, seed, system_prompt_mode),
        "parallel_id": row["parallel_id"],
        "semantic_item_id": row["semantic_item_id"],
        "source_question_id": row["question_sample_id"],
        "question_language": row["question_language"],
        "gui_language": row["gui_language"],
        "matched": row["matched"],
        "dimension": row["dimension"],
        "question": row["question_raw"],
        "options": row.get("options", {}),
        "image_paths": list(row["image_paths"]),
        "image_path": row["image_paths"][0] if row["image_paths"] else None,
        "system_prompt_mode": system_prompt_mode,
        "system_prompt_language": system_language,
        "system_prompt": system_prompt,
        "prompt_template_version": template_version,
        "rendered_prompt": rendered_prompt,
        "model_mode": "mock",
        "model_id": "demo-deterministic-mock",
        "seed": seed,
        "gold_label": row["gold_label"],
        "mock_raw_label_logprobs": raw_logprobs,
        "scored_predicted_label": score.scored_predicted_label,
        "label_logprobs": score.label_logprobs,
        "label_probabilities": score.label_probabilities,
        "gold_probability": score.gold_probability,
        "gold_rank": score.gold_rank,
        "top1_top2_margin": score.top1_top2_margin,
        "gold_vs_best_wrong_margin": score.gold_vs_best_wrong_margin,
        "entropy": score.entropy,
        "correct": score.scored_predicted_label == row["gold_label"],
        "parse_success": True,
        "generation_scoring_disagreement": False,
        "inference_status": "success",
        "status": "success",
    }


def _mock_label_logprobs(input_id: str, seed: int) -> dict[str, float]:
    rng = random.Random(f"demo:{seed}:{input_id}")
    logits = {label: rng.uniform(-2.5, 2.5) for label in LABELS}
    max_logit = max(logits.values())
    total = sum(math.exp(value - max_logit) for value in logits.values())
    return {label: value - max_logit - math.log(total) for label, value in logits.items()}


def _demo_resume_key(row: dict[str, Any], seed: int, system_prompt_mode: str) -> str:
    parts = [
        row["parallel_id"],
        row["question_language"],
        row["gui_language"],
        row["dimension"],
        system_prompt_mode,
        "demo-deterministic-mock",
        str(seed),
        "mpr_label_only_v1",
    ]
    return "::".join(parts)


def _demo_summary(
    rows: list[dict[str, Any]],
    plan,
    first_stats: DemoRunStats,
    resume_stats: DemoRunStats | None,
) -> dict[str, Any]:
    base = summarize(rows)
    by_pair = defaultdict(list)
    by_dim_semantic = defaultdict(set)
    by_dim_eval = Counter()
    for row in rows:
        by_pair[f"{row['question_language']}->{row['gui_language']}"].append(row)
        by_dim_semantic[row["dimension"]].add(row["parallel_id"])
        by_dim_eval[row["dimension"]] += 1
    base["counts"].update(
        {
            "n_semantic_items": len({row["parallel_id"] for row in rows}),
            "n_language_pairs": len(LANGUAGE_PAIRS),
            "n_evaluations": len(rows),
            "planned_n_semantic_items": plan.n_semantic_items,
            "planned_n_evaluations": plan.n_evaluations,
            "first_run_written": first_stats.written,
            "resume_skipped": resume_stats.skipped if resume_stats else 0,
        }
    )
    base["demo_direction_counts"] = {pair: len(pair_rows) for pair, pair_rows in by_pair.items()}
    base["demo_dimension_semantic_counts"] = {
        dimension: len(ids) for dimension, ids in sorted(by_dim_semantic.items())
    }
    base["demo_dimension_evaluation_counts"] = dict(sorted(by_dim_eval.items()))
    base["demo_2x2_matrix"] = {
        "en": {"en": None, "ja": _cell(by_pair["en->ja"])},
        "ja": {"en": _cell(by_pair["ja->en"]), "ja": None},
    }
    base["parsing_scoring_failure_count"] = sum(
        1 for row in rows if row.get("parse_success") is False or not row.get("label_probabilities")
    )
    return base


def _cell(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "n": len(rows),
        "accuracy": sum(row["correct"] for row in rows) / len(rows) if rows else None,
    }


def _write_matrix_csv(summary: dict[str, Any]) -> None:
    lines = ["question_language,gui_language,n,accuracy"]
    for q_lang in ("en", "ja"):
        for g_lang in ("en", "ja"):
            cell = summary["demo_2x2_matrix"][q_lang][g_lang]
            if cell is None:
                lines.append(f"{q_lang},{g_lang},0,N/A")
            else:
                lines.append(f"{q_lang},{g_lang},{cell['n']},{cell['accuracy']}")
    MATRIX_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_validation_report(validation: list[tuple[str, bool, str]], summary: dict[str, Any]) -> None:
    lines = ["Cross-Locale Local Demo Validation", ""]
    for name, passed, detail in validation:
        suffix = f" - {detail}" if detail else ""
        lines.append(f"{'PASS' if passed else 'FAIL'}: {name}{suffix}")
    lines.extend(
        [
            "",
            f"n_semantic_items: {summary['counts']['n_semantic_items']}",
            f"n_evaluations: {summary['counts']['n_evaluations']}",
            f"overall_mock_accuracy: {summary['overall_accuracy']}",
            f"resume_skipped: {summary['counts']['resume_skipped']}",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _signature(rows: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return [
        (
            row["input_id"],
            row["scored_predicted_label"],
            tuple(round(row["label_logprobs"][label], 8) for label in LABELS),
        )
        for row in sorted(rows, key=lambda item: item["input_id"])
    ]


def _question_stem(language: str, dimension: str, item_index: int) -> str:
    if language == "ja":
        return f"{dimension.upper()} デモ項目 {item_index + 1} のボタン位置はどこですか?"
    return f"Where is the button for {dimension.upper()} demo item {item_index + 1}?"


def _question_text(language: str, dimension: str, item_index: int) -> str:
    stem = _question_stem(language, dimension, item_index)
    if language == "ja":
        return f"{stem} A: 左上 B: 右上 C: 左下 D: 右下"
    return f"{stem} A: Top left B: Top right C: Bottom left D: Bottom right"


def _placeholder_image_path(language: str, dimension: str, item_index: int) -> Path:
    return IMAGES_DIR / language / f"{dimension}_{item_index + 1}.svg"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run local cross-locale pipeline demo.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--system-prompt-mode",
        choices=["english_fixed", "query_aligned"],
        default="english_fixed",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--run-resume-check", action="store_true")
    parser.add_argument("--clean-demo-output", action="store_true")
    args = parser.parse_args(argv)
    result = run_demo(args)
    failures = [name for name, passed, _ in result["validation"] if not passed]
    if failures:
        raise SystemExit(f"Demo validation failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
