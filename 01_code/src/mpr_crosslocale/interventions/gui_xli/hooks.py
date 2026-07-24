from __future__ import annotations


def hook_description(layer: int, location: str = "block_output", positions: str = "last_token") -> str:
    return f"layer={layer}; location={location}; positions={positions}"
