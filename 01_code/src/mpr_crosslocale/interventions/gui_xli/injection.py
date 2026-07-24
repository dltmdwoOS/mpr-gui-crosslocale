from __future__ import annotations

import math


def norm_preserving_add(hidden: tuple[float, ...], vector: tuple[float, ...], alpha: float) -> tuple[float, ...]:
    updated = tuple(h + alpha * v for h, v in zip(hidden, vector))
    old_norm = math.sqrt(sum(h * h for h in hidden))
    new_norm = math.sqrt(sum(u * u for u in updated))
    if new_norm == 0:
        return updated
    scale = old_norm / new_norm
    return tuple(u * scale for u in updated)
