"""Frozen normalized point response contract for REL reference grounding."""

from __future__ import annotations

import re


POINT_RE = re.compile(r"\s*\(\s*(\d{1,4})\s*,\s*(\d{1,4})\s*\)\s*\Z")


def parse_point(raw_output: str) -> tuple[int, int] | None:
    """Accept one integer pair only; out-of-range or extra text is invalid."""
    match = POINT_RE.fullmatch(raw_output)
    if match is None:
        return None
    x, y = (int(part) for part in match.groups())
    return (x, y) if 0 <= x <= 1000 and 0 <= y <= 1000 else None


def to_original_pixels(point: tuple[int, int], width: int, height: int) -> tuple[float, float]:
    if width <= 0 or height <= 0:
        raise ValueError("Original image dimensions must be positive")
    return point[0] * width / 1000, point[1] * height / 1000


def point_in_box(point: tuple[float, float], box: list[float]) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def score(raw_output: str, box: list[float], width: int, height: int) -> dict:
    normalized = parse_point(raw_output)
    pixel = to_original_pixels(normalized, width, height) if normalized is not None else None
    return {
        "parsed_point_1000": list(normalized) if normalized is not None else None,
        "point_original_pixels": list(pixel) if pixel is not None else None,
        "valid_output": normalized is not None,
        "point_in_gt_box": point_in_box(pixel, box) if pixel is not None else False,
    }
