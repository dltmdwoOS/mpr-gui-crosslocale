"""Trace R-to-F answer changes by language using completed REL 4-language runs.

Reads the published full result JSONL (plain or gzip) without invoking a model.
Only complete, successful, unflagged mismatch quartets enter the main analysis.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import random
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_DIRS = {
    "Qwen": "qwen2_5_vl_7b_batch32",
    "InternVL": "internvl2_5_8b",
}
LANGUAGES = ("en", "zh", "th", "ru")
CONDITIONS = {"O", "R", "C", "F"}


def read_jsonl(result_dir: Path):
    plain = result_dir / "results.jsonl"
    packed = result_dir / "results.jsonl.gz"
    path = plain if plain.is_file() else packed
    if not path.is_file():
        raise FileNotFoundError(f"Missing result JSONL in {result_dir}")
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def load_model(result_dir: Path):
    summary = json.loads((result_dir / "summary.json").read_text(encoding="utf-8"))
    quartets = defaultdict(dict)
    matched = {}
    for row in read_jsonl(result_dir):
        assert row["status"] == "success", (result_dir, row["pair_id"])
        if row["matched"] and row["condition"] == "O":
            matched[(row["parallel_id"], row["query_language"])] = row
        if row["primary_analysis_eligible"]:
            pair = quartets[row["pair_id"]]
            assert row["condition"] not in pair, row["pair_id"]
            pair[row["condition"]] = row
    assert all(set(pair) == CONDITIONS for pair in quartets.values())
    for dependency in ("dependent", "independent"):
        expected = summary["primary_descriptive_summary"][dependency][
            "complete_unflagged_mismatch_quartets"
        ]
        actual = sum(q["R"]["text_dependency"] == dependency for q in quartets.values())
        assert actual == expected, (result_dir, dependency, actual, expected)
    return dict(quartets), matched, summary


def validate_pair(pair):
    r, f = pair["R"], pair["F"]
    assert r["pair_id"] == f["pair_id"]
    assert r["query_language"] == f["query_language"]
    assert r["gui_language"] == f["gui_language"]
    assert r["context_language"] == r["query_language"]
    assert f["context_language"] == f["gui_language"]
    assert r["reference_language"] == f["reference_language"] == r["gui_language"]
    assert r["gold_answer"] == f["gold_answer"]
    assert r["option_order"] == f["option_order"]
    assert r["image_path"] == f["image_path"]
    assert not r["matched"] and r["primary_analysis_eligible"]


def metrics(quartets):
    n = len(quartets)
    assert n
    r_correct = sum(q["R"]["generation_correct"] for q in quartets)
    f_correct = sum(q["F"]["generation_correct"] for q in quartets)
    gain = sum(not q["R"]["generation_correct"] and q["F"]["generation_correct"] for q in quartets)
    loss = sum(q["R"]["generation_correct"] and not q["F"]["generation_correct"] for q in quartets)
    oc_gain = sum(not q["O"]["generation_correct"] and q["C"]["generation_correct"] for q in quartets)
    oc_loss = sum(q["O"]["generation_correct"] and not q["C"]["generation_correct"] for q in quartets)
    assert f_correct - r_correct == gain - loss
    return {
        "n": n,
        "r_correct": r_correct,
        "f_correct": f_correct,
        "r_accuracy_pct": 100 * r_correct / n,
        "f_accuracy_pct": 100 * f_correct / n,
        "incorrect_to_correct": gain,
        "correct_to_incorrect": loss,
        "net": gain - loss,
        "rf_delta_pp": 100 * (gain - loss) / n,
        "loss_among_r_correct_pct": 100 * loss / r_correct if r_correct else None,
        "gain_among_r_incorrect_pct": 100 * gain / (n - r_correct) if n > r_correct else None,
        "oc_gain": oc_gain,
        "oc_loss": oc_loss,
        "oc_delta_pp": 100 * (oc_gain - oc_loss) / n,
    }


def write_csv(path: Path, rows: list[dict]):
    assert rows
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def case_row(model: str, pair: dict):
    r, f = pair["R"], pair["F"]
    gained = not r["generation_correct"] and f["generation_correct"]
    return {
        "model": model,
        "text_dependency": r["text_dependency"],
        "source_language": r["query_language"],
        "target_language": r["gui_language"],
        "direction": "incorrect_to_correct" if gained else "correct_to_incorrect",
        "pair_id": r["pair_id"],
        "parallel_id": r["parallel_id"],
        "gold_answer": r["gold_answer"],
        "r_generated_label": r["parsed_generated_label"],
        "f_generated_label": f["parsed_generated_label"],
        "r_input_id": r["input_id"],
        "f_input_id": f["input_id"],
        "r_question": r["question"],
        "f_question": f["question"],
        "r_options_json": json.dumps(r["options"], ensure_ascii=False),
        "f_options_json": json.dumps(f["options"], ensure_ascii=False),
    }


def thai_target_contrast(model: str, quartets: dict):
    """Compare Thai with other targets for the same source and semantic item."""
    sources = ("en", "zh", "ru")
    required = {
        (source, target)
        for source in sources
        for target in LANGUAGES
        if source != target
    }
    by_item = defaultdict(dict)
    for pair in quartets.values():
        r, f = pair["R"], pair["F"]
        if r["text_dependency"] != "dependent" or r["query_language"] not in sources:
            continue
        key = (r["query_language"], r["gui_language"])
        by_item[r["parallel_id"]][key] = int(f["generation_correct"]) - int(r["generation_correct"])

    item_rows = []
    for item, pairs in sorted(by_item.items()):
        if not required.issubset(pairs):
            continue
        thai = sum(pairs[source, "th"] for source in sources) / len(sources)
        other = sum(
            pairs[source, target]
            for source in sources
            for target in ("en", "zh", "ru")
            if source != target
        ) / 6
        item_rows.append({
            "model": model,
            "parallel_id": item,
            "thai_target_delta": thai,
            "other_targets_delta": other,
            "thai_minus_other": thai - other,
        })
    assert item_rows
    n = len(item_rows)
    differences = [row["thai_minus_other"] for row in item_rows]
    rng = random.Random(42)
    boot = sorted(
        100 * sum(differences[rng.randrange(n)] for _ in range(n)) / n
        for _ in range(5000)
    )
    return item_rows, {
        "complete_items": n,
        "thai_target_delta_pp": 100 * sum(row["thai_target_delta"] for row in item_rows) / n,
        "other_targets_same_sources_delta_pp": 100 * sum(row["other_targets_delta"] for row in item_rows) / n,
        "thai_minus_other_pp": 100 * sum(differences) / n,
        "item_bootstrap_95_percentile_ci_pp": [boot[int(0.025 * (len(boot) - 1))], boot[int(0.975 * (len(boot) - 1))]],
        "bootstrap_resamples": len(boot),
        "bootstrap_seed": 42,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "followup_rel_4lang/results/analysis/rf_context_switch",
    )
    args = parser.parse_args()
    output = args.output_dir
    by_model = {}
    matched_by_model = {}
    summaries = {}
    for model, dirname in MODEL_DIRS.items():
        result_dir = REPO_ROOT / "followup_rel_4lang/results/full" / dirname
        by_model[model], matched_by_model[model], summaries[model] = load_model(result_dir)
    assert set(by_model["Qwen"]) == set(by_model["InternVL"])

    pair_rows, source_rows, target_rows, case_rows, baseline_rows = [], [], [], [], []
    thai_item_rows, thai_contrasts = [], {}
    totals = {}
    for model, quartets in by_model.items():
        item_rows, thai_contrasts[model] = thai_target_contrast(model, quartets)
        thai_item_rows.extend(item_rows)
        for pair in quartets.values():
            validate_pair(pair)
            if pair["R"]["generation_correct"] != pair["F"]["generation_correct"]:
                case_rows.append(case_row(model, pair))
        for dependency in ("dependent", "independent"):
            selected = [q for q in quartets.values() if q["R"]["text_dependency"] == dependency]
            result = metrics(selected)
            expected = summaries[model]["primary_descriptive_summary"][dependency]["paired_contrasts"]["F-R"]
            assert (result["incorrect_to_correct"], result["correct_to_incorrect"]) == (
                expected["errors_corrected"], expected["errors_introduced"]
            )
            totals[f"{model}/{dependency}"] = result
            for source in LANGUAGES:
                group = [q for q in selected if q["R"]["query_language"] == source]
                source_rows.append({"model": model, "text_dependency": dependency, "source_language": source, **metrics(group)})
                for target in LANGUAGES:
                    if source == target:
                        continue
                    pair_group = [q for q in group if q["R"]["gui_language"] == target]
                    pair_rows.append({"model": model, "text_dependency": dependency, "source_language": source, "target_language": target, **metrics(pair_group)})
            for target in LANGUAGES:
                group = [q for q in selected if q["R"]["gui_language"] == target]
                target_rows.append({"model": model, "text_dependency": dependency, "target_language": target, **metrics(group)})

        dependent_items = {
            q["R"]["parallel_id"] for q in quartets.values() if q["R"]["text_dependency"] == "dependent"
        }
        for language in LANGUAGES:
            same_language = [matched_by_model[model][(item, language)] for item in dependent_items]
            baseline_rows.append({
                "model": model,
                "language": language,
                "items": len(same_language),
                "correct": sum(row["generation_correct"] for row in same_language),
                "accuracy_pct": 100 * sum(row["generation_correct"] for row in same_language) / len(same_language),
            })

    common_loss_ids = {
        pair_id for pair_id in by_model["Qwen"]
        if by_model["Qwen"][pair_id]["R"]["text_dependency"] == "dependent"
        and all(
            by_model[model][pair_id]["R"]["generation_correct"]
            and not by_model[model][pair_id]["F"]["generation_correct"]
            for model in MODEL_DIRS
        )
    }
    common_losses = []
    for pair_id in sorted(common_loss_ids):
        qwen = by_model["Qwen"][pair_id]
        intern = by_model["InternVL"][pair_id]
        assert qwen["R"]["question"] == intern["R"]["question"]
        assert qwen["F"]["question"] == intern["F"]["question"]
        common_losses.append({
            "pair_id": pair_id,
            "parallel_id": qwen["R"]["parallel_id"],
            "source_language": qwen["R"]["query_language"],
            "target_language": qwen["R"]["gui_language"],
            "gold_answer": qwen["R"]["gold_answer"],
            "qwen_r_label": qwen["R"]["parsed_generated_label"],
            "qwen_f_label": qwen["F"]["parsed_generated_label"],
            "internvl_r_label": intern["R"]["parsed_generated_label"],
            "internvl_f_label": intern["F"]["parsed_generated_label"],
            "r_question": qwen["R"]["question"],
            "f_question": qwen["F"]["question"],
            "r_options_json": json.dumps(qwen["R"]["options"], ensure_ascii=False),
            "f_options_json": json.dumps(qwen["F"]["options"], ensure_ascii=False),
        })

    write_csv(output / "rf_by_language_pair.csv", pair_rows)
    write_csv(output / "rf_by_source.csv", source_rows)
    write_csv(output / "rf_by_target.csv", target_rows)
    write_csv(output / "rf_flipped_cases.csv", sorted(case_rows, key=lambda x: (x["model"], x["text_dependency"], x["source_language"], x["target_language"], x["pair_id"])))
    write_csv(output / "rf_common_losses.csv", common_losses)
    write_csv(output / "matched_language_baseline.csv", baseline_rows)
    write_csv(output / "thai_target_within_item.csv", thai_item_rows)
    summary = {
        "method": "Complete successful primary-analysis quartets; generated-answer correctness; R to F changes context from source to GUI language while keeping reference in GUI language.",
        "models": MODEL_DIRS,
        "totals": totals,
        "common_dependent_correct_to_incorrect": len(common_losses),
        "common_dependent_correct_to_incorrect_by_target": dict(Counter(x["target_language"] for x in common_losses)),
        "thai_target_contrast": thai_contrasts,
        "thai_target_contrast_note": "Complete dependent items with all nine pairs from en/zh/ru sources; source and semantic item held fixed, but target GUI and translation still vary. Percentile bootstrap resamples semantic items; exploratory only.",
        "flipped_case_rows": len(case_rows),
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}: {len(pair_rows)} language-pair rows, {len(case_rows)} flipped cases, {len(common_losses)} common losses")


if __name__ == "__main__":
    main()
