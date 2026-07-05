from __future__ import annotations


def resource_gap(canonical_accuracy: float, question_only_accuracy: float) -> float:
    return canonical_accuracy - question_only_accuracy
