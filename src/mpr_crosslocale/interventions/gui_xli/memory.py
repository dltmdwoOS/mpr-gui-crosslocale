from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryEntry:
    sample_id: str
    language: str
    layer: int
    key: tuple[float, ...]
    vector: tuple[float, ...]
