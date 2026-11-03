"""Model-native spatial outputs mapped to a common original-image point score."""

from __future__ import annotations

import json
import re


INT_STRING = re.compile(r"[0-9]+\Z")
INTERNVL_BOX = re.compile(
    r"\s*(?:<ref>[^<>]*</ref>\s*)?<box>\s*\[\[\s*"
    r"([0-9]{1,4})\s*,\s*([0-9]{1,4})\s*,\s*([0-9]{1,4})\s*,\s*([0-9]{1,4})"
    r"\s*\]\]\s*</box>\s*\Z"
)


def _coordinate(value: object) -> int | None:
    if type(value) is int:
        return value
    if isinstance(value, str) and INT_STRING.fullmatch(value):
        return int(value)
    return None


def qwen_image_size_from_grid(grid: tuple[int, int, int] | list[int]) -> tuple[int, int]:
    """Qwen2.5-VL image_grid_thw is in 14-pixel vision patches."""
    if len(grid) != 3 or grid[0] != 1 or grid[1] <= 0 or grid[2] <= 0:
        raise ValueError("Expected one Qwen2.5-VL image with a positive patch grid")
    return grid[2] * 14, grid[1] * 14


def _decode_qwen_point(
    raw_output: str, model_width: int, model_height: int,
) -> tuple[tuple[int, int] | None, bool]:
    """Read one point; distinguish pixel validity from exact requested JSON shape."""
    if model_width <= 0 or model_height <= 0:
        raise ValueError("Model image dimensions must be positive")
    try:
        output = json.loads(raw_output)
    except (json.JSONDecodeError, TypeError):
        return None, False
    one_element_array = isinstance(output, list) and len(output) == 1
    item = output[0] if one_element_array else output
    if not isinstance(item, dict) or "point_2d" not in item or not set(item) <= {"point_2d", "label"}:
        return None, False
    if "label" in item and not isinstance(item["label"], str):
        return None, False
    values = item["point_2d"]
    if not isinstance(values, list) or len(values) != 2:
        return None, False
    x, y = (_coordinate(value) for value in values)
    if x is None or y is None or not (0 <= x <= model_width and 0 <= y <= model_height):
        return None, False
    adherent = (one_element_array and set(item) == {"point_2d"} and
                all(type(value) is int for value in values))
    return (x, y), adherent


def parse_qwen_point(raw_output: str, model_width: int, model_height: int) -> tuple[int, int] | None:
    """Read one unambiguous JSON point in actual, resized Qwen image pixels."""
    return _decode_qwen_point(raw_output, model_width, model_height)[0]


def parse_internvl_box(raw_output: str) -> tuple[int, int, int, int] | None:
    """Read one full-image InternVL box on its documented 0–1000 grid."""
    match = INTERNVL_BOX.fullmatch(raw_output)
    if match is None:
        return None
    x1, y1, x2, y2 = map(int, match.groups())
    if not (0 <= x1 < x2 <= 1000 and 0 <= y1 < y2 <= 1000):
        return None
    return x1, y1, x2, y2


def point_in_box(point: tuple[float, float], box: list[float]) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def box_iou(first: tuple[float, float, float, float], second: list[float]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def score_qwen_point(
    raw_output: str, gt_box: list[float], original_width: int, original_height: int,
    model_width: int, model_height: int,
) -> dict:
    point, requested_format_adherent = _decode_qwen_point(raw_output, model_width, model_height)
    original = (
        point[0] * original_width / model_width,
        point[1] * original_height / model_height,
    ) if point is not None else None
    return {
        "parsed_point_model_pixels": list(point) if point is not None else None,
        "point_original_pixels": list(original) if original is not None else None,
        "valid_output": point is not None,
        "requested_format_adherent": requested_format_adherent,
        "point_in_gt_box": point_in_box(original, gt_box) if original is not None else False,
    }


def score_internvl_box(
    raw_output: str, gt_box: list[float], original_width: int, original_height: int,
) -> dict:
    box = parse_internvl_box(raw_output)
    original_box = (
        box[0] * original_width / 1000,
        box[1] * original_height / 1000,
        box[2] * original_width / 1000,
        box[3] * original_height / 1000,
    ) if box is not None else None
    original_point = (
        (box[0] + box[2]) * original_width / 2000,
        (box[1] + box[3]) * original_height / 2000,
    ) if box is not None else None
    return {
        "parsed_box_1000": list(box) if box is not None else None,
        "box_original_pixels": list(original_box) if original_box is not None else None,
        "point_original_pixels": list(original_point) if original_point is not None else None,
        "valid_output": box is not None,
        "point_in_gt_box": point_in_box(original_point, gt_box) if original_point is not None else False,
        "bbox_iou": box_iou(original_box, gt_box) if original_box is not None else None,
    }
