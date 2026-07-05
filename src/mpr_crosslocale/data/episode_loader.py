from __future__ import annotations

import re
from pathlib import Path


def natural_sort_key(path: str | Path) -> tuple[object, ...]:
    text = Path(path).name
    return tuple(int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text))


def sorted_episode_frames(folder: Path) -> list[Path]:
    return sorted((p for p in folder.iterdir() if p.is_file()), key=natural_sort_key)
