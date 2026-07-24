from __future__ import annotations

from math import log

from mpr_crosslocale.inference.constrained_choice import LABELS


def entropy(probs: dict[str, float]) -> float:
    return -sum(p * log(p) for label in LABELS if (p := probs.get(label, 0.0)) > 0)
