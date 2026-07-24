from __future__ import annotations


def visual_reliance_score(matched_prob: float, occluded_prob: float) -> float:
    return max(matched_prob - occluded_prob, 0.0)
