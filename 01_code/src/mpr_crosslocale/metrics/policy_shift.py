from __future__ import annotations

import math


def js_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    labels = sorted(set(p) | set(q))
    m = {label: 0.5 * (p.get(label, 0.0) + q.get(label, 0.0)) for label in labels}
    return 0.5 * _kl(p, m, labels) + 0.5 * _kl(q, m, labels)


def _kl(p: dict[str, float], q: dict[str, float], labels: list[str]) -> float:
    total = 0.0
    for label in labels:
        pv = p.get(label, 0.0)
        qv = q.get(label, 0.0)
        if pv > 0 and qv > 0:
            total += pv * math.log(pv / qv)
    return total
