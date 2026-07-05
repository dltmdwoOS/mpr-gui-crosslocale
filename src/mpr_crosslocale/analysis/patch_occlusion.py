from __future__ import annotations


def probability_drop(original: float, occluded: float) -> float:
    return original - occluded
