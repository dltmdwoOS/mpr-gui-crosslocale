from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from mpr_crosslocale.analysis.build_glmm_table import DIMENSIONS, LANGUAGES


OUTCOMES = (
    "generation_correct",
    "scoring_correct",
    "scoring_correct_token_tiebreak",
)
CELL_KEYS = (
    "parallel_id",
    "question_language",
    "gui_language",
    "dimension",
)


def _bootstrap_mean_ci(
    values: np.ndarray,
    *,
    rng: np.random.Generator,
    replicates: int,
) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    draws = rng.choice(values, size=(replicates, len(values)), replace=True).mean(axis=1)
    low, high = np.quantile(draws, (0.025, 0.975))
    return float(low), float(high)


def _item_mean(data: pd.DataFrame, outcome: str) -> pd.Series:
    return data.groupby("parallel_id", observed=True)[outcome].mean()


def _item_matched_delta(data: pd.DataFrame, outcome: str) -> pd.Series:
    means = data.groupby(["parallel_id", "matched"], observed=True)[outcome].mean().unstack()
    if 0 not in means or 1 not in means:
        raise ValueError("Both matched and mismatched cells are required for every item")
    return means[1] - means[0]


def _estimate_row(
    *,
    model: str,
    outcome: str,
    scope: str,
    level: str,
    estimand: str,
    values: pd.Series,
    rng: np.random.Generator,
    replicates: int,
) -> dict[str, Any]:
    low, high = _bootstrap_mean_ci(
        values.to_numpy(), rng=rng, replicates=replicates
    )
    return {
        "model": model,
        "outcome": outcome,
        "scope": scope,
        "level": level,
        "estimand": estimand,
        "estimate": float(values.mean()),
        "conf_low": low,
        "conf_high": high,
        "items": int(values.size),
        "bootstrap_replicates": replicates,
    }


def summarize_table(
    data: pd.DataFrame,
    model: str,
    *,
    replicates: int,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {"model": model, "rows": len(data), "outcomes": {}}

    for outcome in OUTCOMES:
        outcome_detail: dict[str, Any] = {}
        rows.append(
            _estimate_row(
                model=model,
                outcome=outcome,
                scope="overall",
                level="all",
                estimand="accuracy",
                values=_item_mean(data, outcome),
                rng=rng,
                replicates=replicates,
            )
        )
        rows.append(
            _estimate_row(
                model=model,
                outcome=outcome,
                scope="overall",
                level="all",
                estimand="matched_minus_mismatched",
                values=_item_matched_delta(data, outcome),
                rng=rng,
                replicates=replicates,
            )
        )

        for dimension in DIMENSIONS:
            subset = data[data["dimension"] == dimension]
            rows.append(
                _estimate_row(
                    model=model,
                    outcome=outcome,
                    scope="dimension",
                    level=dimension,
                    estimand="accuracy",
                    values=_item_mean(subset, outcome),
                    rng=rng,
                    replicates=replicates,
                )
            )
            rows.append(
                _estimate_row(
                    model=model,
                    outcome=outcome,
                    scope="dimension",
                    level=dimension,
                    estimand="matched_minus_mismatched",
                    values=_item_matched_delta(subset, outcome),
                    rng=rng,
                    replicates=replicates,
                )
            )

        for language in LANGUAGES:
            query_subset = data[data["question_language"] == language]
            gui_subset = data[data["gui_language"] == language]
            rows.append(
                _estimate_row(
                    model=model,
                    outcome=outcome,
                    scope="query_language",
                    level=language,
                    estimand="accuracy",
                    values=_item_mean(query_subset, outcome),
                    rng=rng,
                    replicates=replicates,
                )
            )
            rows.append(
                _estimate_row(
                    model=model,
                    outcome=outcome,
                    scope="gui_language",
                    level=language,
                    estimand="accuracy",
                    values=_item_mean(gui_subset, outcome),
                    rng=rng,
                    replicates=replicates,
                )
            )

        matrix = (
            data.groupby(
                ["question_language", "gui_language"], observed=True
            )[outcome]
            .mean()
            .unstack()
            .reindex(index=LANGUAGES, columns=LANGUAGES)
        )
        outcome_detail["accuracy_matrix"] = {
            query: {gui: float(matrix.loc[query, gui]) for gui in LANGUAGES}
            for query in LANGUAGES
        }
        details["outcomes"][outcome] = outcome_detail

    generated = data["generation_correct"].astype(bool)
    scored = data["scoring_correct"].astype(bool)
    token_tiebreak_scored = data["scoring_correct_token_tiebreak"].astype(bool)
    details["generation_vs_scoring"] = {
        "both_correct": int((generated & scored).sum()),
        "generation_only_correct": int((generated & ~scored).sum()),
        "scoring_only_correct": int((~generated & scored).sum()),
        "both_incorrect": int((~generated & ~scored).sum()),
        "accuracy_difference_generation_minus_scoring": float(
            data["generation_correct"].mean() - data["scoring_correct"].mean()
        ),
        "accuracy_difference_generation_minus_token_tiebreak_scoring": float(
            data["generation_correct"].mean()
            - data["scoring_correct_token_tiebreak"].mean()
        ),
        "generation_vs_token_tiebreak_disagreements": int(
            (generated != token_tiebreak_scored).sum()
        ),
    }
    return rows, details


def compare_tables(
    data_a: pd.DataFrame,
    label_a: str,
    data_b: pd.DataFrame,
    label_b: str,
    *,
    replicates: int,
    seed: int,
) -> list[dict[str, Any]]:
    ordered_a = data_a.sort_values(list(CELL_KEYS)).reset_index(drop=True)
    ordered_b = data_b.sort_values(list(CELL_KEYS)).reset_index(drop=True)
    if not ordered_a[list(CELL_KEYS)].equals(ordered_b[list(CELL_KEYS)]):
        raise ValueError("Model tables do not contain identical experimental cells")

    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    combined = ordered_a[list(CELL_KEYS) + ["matched"]].copy()
    for outcome in OUTCOMES:
        combined["difference"] = ordered_b[outcome] - ordered_a[outcome]
        rows.append(
            _estimate_row(
                model=f"{label_b}_minus_{label_a}",
                outcome=outcome,
                scope="model_comparison",
                level="all",
                estimand="accuracy_difference",
                values=_item_mean(combined, "difference"),
                rng=rng,
                replicates=replicates,
            )
        )
        rows.append(
            _estimate_row(
                model=f"{label_b}_minus_{label_a}",
                outcome=outcome,
                scope="model_comparison",
                level="all",
                estimand="difference_in_matched_advantage",
                values=_item_matched_delta(combined, "difference"),
                rng=rng,
                replicates=replicates,
            )
        )
        for dimension in DIMENSIONS:
            subset = combined[combined["dimension"] == dimension]
            rows.append(
                _estimate_row(
                    model=f"{label_b}_minus_{label_a}",
                    outcome=outcome,
                    scope="model_comparison_dimension",
                    level=dimension,
                    estimand="accuracy_difference",
                    values=_item_mean(subset, "difference"),
                    rng=rng,
                    replicates=replicates,
                )
            )
    return rows


def _parse_table(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Use LABEL=PATH for --table")
    label, path = value.split("=", 1)
    if not label or not path:
        raise argparse.ArgumentTypeError("Use non-empty LABEL=PATH for --table")
    return label, Path(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cluster-bootstrap descriptive summaries for validated GLMM tables."
    )
    parser.add_argument(
        "--table",
        action="append",
        type=_parse_table,
        required=True,
        help="LABEL=PATH; provide one or two tables.",
    )
    parser.add_argument("--csv-out", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--bootstrap-replicates", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if len(args.table) not in (1, 2):
        parser.error("Provide one or two --table arguments")

    loaded = [(label, pd.read_csv(path)) for label, path in args.table]
    summary_rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {"tables": []}
    for index, (label, data) in enumerate(loaded):
        rows, table_details = summarize_table(
            data,
            label,
            replicates=args.bootstrap_replicates,
            seed=args.seed + index,
        )
        summary_rows.extend(rows)
        details["tables"].append(table_details)

    if len(loaded) == 2:
        (label_a, data_a), (label_b, data_b) = loaded
        summary_rows.extend(
            compare_tables(
                data_a,
                label_a,
                data_b,
                label_b,
                replicates=args.bootstrap_replicates,
                seed=args.seed + 100,
            )
        )

    args.csv_out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(summary_rows).to_csv(args.csv_out, index=False)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(details, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
