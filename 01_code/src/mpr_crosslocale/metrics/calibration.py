from __future__ import annotations


def top_label(probs: dict[str, float]) -> str | None:
    if not probs:
        return None
    return max(probs, key=probs.get)
