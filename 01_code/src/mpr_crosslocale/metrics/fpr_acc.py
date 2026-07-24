from __future__ import annotations

WEIGHTS = {
    "wf": 1.0,
    "wi": 1.0,
    "au": 1.0,
    "ap": 1.0,
    "ael": 1.0,
    "rel": 1.0,
    "ri": 1.5,
    "si": 2.0,
}


def fpr_acc(dimension_accuracies: dict[str, float], weights: dict[str, float] | None = None) -> float:
    active_weights = weights or WEIGHTS
    numerator = 0.0
    denominator = 0.0
    for dimension, accuracy in dimension_accuracies.items():
        weight = active_weights[dimension]
        numerator += weight * accuracy
        denominator += weight
    return numerator / denominator if denominator else 0.0
