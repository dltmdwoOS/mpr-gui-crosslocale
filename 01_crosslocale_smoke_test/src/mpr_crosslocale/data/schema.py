from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

LANGUAGES = ("en", "zh", "fr", "ru", "ja", "th")
LABELS = ("A", "B", "C", "D")


@dataclass(frozen=True)
class Sample:
    sample_id: str
    dimension: str
    language: str
    question: str
    answer: str
    image_paths: tuple[Path, ...]


@dataclass(frozen=True)
class ParallelKey:
    dimension: str
    state_key: str

    def as_id(self) -> str:
        return f"{self.dimension}::{self.state_key}"
