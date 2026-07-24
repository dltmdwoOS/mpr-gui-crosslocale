from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ModelResponse:
    raw_output: str
    parsed_label: str | None


class MultipleChoiceModel(Protocol):
    model_id: str

    def answer(self, prompt: str, image_paths: list[Path]) -> ModelResponse:
        ...
