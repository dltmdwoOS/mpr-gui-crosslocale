from __future__ import annotations

import re
from pathlib import Path

LANG_RE = re.compile(r"(^|[_/-])(en|zh|fr|ru|ja|th)(?=[_./-]|$)")


def canonical_state_key(path: str | Path) -> str:
    """Build a language-agnostic key from an MPR-GUI image or episode path."""
    normalized = normalize_asset_reference(path)
    parts = [part for part in normalized.split("/") if part not in {"images", "qas"}]
    without_lang_parts = [part for part in parts if part not in {"en", "zh", "fr", "ru", "ja", "th"}]
    key = "/".join(without_lang_parts)
    key = LANG_RE.sub(lambda match: match.group(1), key)
    key = re.sub(r"__+", "_", key).strip("_")
    return key


def parallel_sample_id(dimension: str, path: str | Path) -> str:
    return f"{dimension}::{canonical_state_key(path)}"


def normalize_asset_reference(path: str | Path) -> str:
    normalized = Path(path).as_posix()
    while normalized.startswith("../"):
        normalized = normalized[3:]
    normalized = normalized.removeprefix("./")
    normalized = normalized.removeprefix("images/")
    return normalized
