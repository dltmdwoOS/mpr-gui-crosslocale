from __future__ import annotations

import math
from dataclasses import dataclass

from mpr_crosslocale.inference.constrained_choice import LABELS
from mpr_crosslocale.inference.option_scoring import entropy


@dataclass(frozen=True)
class LabelScoreSummary:
    label_logprobs: dict[str, float]
    label_probabilities: dict[str, float]
    scored_predicted_label: str
    gold_probability: float
    gold_rank: int
    top1_top2_margin: float
    gold_vs_best_wrong_margin: float
    entropy: float
    scoring_method: str
    label_token_ids: dict[str, list[int]]


def summarize_label_logprobs(
    label_logprobs: dict[str, float],
    gold_label: str,
    scoring_method: str,
    label_token_ids: dict[str, list[int]] | None = None,
) -> LabelScoreSummary:
    complete = {label: float(label_logprobs.get(label, float("-inf"))) for label in LABELS}
    probs = _softmax_logprobs(complete)
    ranked = sorted(LABELS, key=lambda label: probs[label], reverse=True)
    scored = ranked[0]
    best_wrong = next(label for label in ranked if label != gold_label)
    return LabelScoreSummary(
        label_logprobs=complete,
        label_probabilities=probs,
        scored_predicted_label=scored,
        gold_probability=probs.get(gold_label, 0.0),
        gold_rank=ranked.index(gold_label) + 1 if gold_label in ranked else len(LABELS) + 1,
        top1_top2_margin=probs[ranked[0]] - probs[ranked[1]],
        gold_vs_best_wrong_margin=probs.get(gold_label, 0.0) - probs[best_wrong],
        entropy=entropy(probs),
        scoring_method=scoring_method,
        label_token_ids=label_token_ids or {},
    )


def uniform_label_score(gold_label: str, scoring_method: str = "unavailable") -> LabelScoreSummary:
    return summarize_label_logprobs(
        {label: math.log(0.25) for label in LABELS},
        gold_label=gold_label,
        scoring_method=scoring_method,
        label_token_ids={},
    )


def deterministic_mock_label_score(gold_label: str, predicted_label: str) -> LabelScoreSummary:
    return summarize_label_logprobs(
        {label: (-0.1 if label == predicted_label else -2.5) for label in LABELS},
        gold_label=gold_label,
        scoring_method="mock_fixed_margin",
        label_token_ids={label: [ord(label)] for label in LABELS},
    )


def _softmax_logprobs(logprobs: dict[str, float]) -> dict[str, float]:
    finite = [value for value in logprobs.values() if math.isfinite(value)]
    if not finite:
        return {label: 1.0 / len(LABELS) for label in LABELS}
    max_logprob = max(finite)
    exps = {
        label: (math.exp(value - max_logprob) if math.isfinite(value) else 0.0)
        for label, value in logprobs.items()
    }
    total = sum(exps.values())
    if total == 0:
        return {label: 1.0 / len(LABELS) for label in LABELS}
    return {label: value / total for label, value in exps.items()}
