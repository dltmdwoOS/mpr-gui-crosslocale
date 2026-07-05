from __future__ import annotations


def normalized_accuracy(predicted_labels: list[str | None], gold_labels: list[str]) -> float:
    if not gold_labels:
        return 0.0
    correct = sum(pred == gold for pred, gold in zip(predicted_labels, gold_labels))
    return correct / len(gold_labels)
