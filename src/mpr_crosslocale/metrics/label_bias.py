from __future__ import annotations

from collections import Counter


def label_distribution(labels: list[str | None]) -> dict[str, int]:
    return dict(Counter(label for label in labels if label is not None))
