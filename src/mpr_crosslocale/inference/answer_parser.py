from __future__ import annotations

import re

VALID_LABELS = {"A", "B", "C", "D"}
LABEL_RE = re.compile(
    r"^\s*(?:answer\s*[:：]\s*)?[\(\[]?\s*([ABCD])\s*[\)\].:：]?\s*(?:$|\s)",
    re.IGNORECASE,
)


def parse_label(text: str) -> str | None:
    """Parse a conservative A/B/C/D answer label from model or gold text."""
    stripped = text.strip()
    if stripped.upper() in VALID_LABELS:
        return stripped.upper()
    match = LABEL_RE.match(stripped)
    if match:
        return match.group(1).upper()
    return None
