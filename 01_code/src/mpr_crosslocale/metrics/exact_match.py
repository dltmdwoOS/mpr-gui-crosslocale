from __future__ import annotations


def exact_match(prediction: str, gold: str) -> bool:
    return prediction.strip() == gold.strip()
