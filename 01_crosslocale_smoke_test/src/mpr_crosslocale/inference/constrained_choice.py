from __future__ import annotations

LABELS = ("A", "B", "C", "D")


def normalize_label_scores(scores: dict[str, float]) -> dict[str, float]:
    total = sum(max(scores.get(label, 0.0), 0.0) for label in LABELS)
    if total == 0:
        return {label: 0.25 for label in LABELS}
    return {label: max(scores.get(label, 0.0), 0.0) / total for label in LABELS}
