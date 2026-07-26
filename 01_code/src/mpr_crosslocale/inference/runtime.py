from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def existing_success_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done: set[str] = set()
    for row in read_jsonl(path):
        if row.get("status") == "success":
            done.add(str(row.get("input_id") or row.get("sample_id")))
    return done


def existing_model_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        str(row["model_id"])
        for row in read_jsonl(path)
        if row.get("model_id")
    }


def git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def software_versions() -> dict[str, str | None]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "torch": package_version("torch"),
        "transformers": package_version("transformers"),
        "accelerate": package_version("accelerate"),
        "qwen-vl-utils": package_version("qwen-vl-utils"),
        "torchvision": package_version("torchvision"),
        "timm": package_version("timm"),
        "protobuf": package_version("protobuf"),
        "sentencepiece": package_version("sentencepiece"),
        "flash-attn": package_version("flash-attn"),
    }


def hardware_metadata() -> dict[str, Any]:
    try:
        import torch
    except ImportError:
        return {
            "cuda_available": False,
            "cuda_runtime_version": None,
            "gpu_count": 0,
            "gpus": [],
        }

    cuda_available = torch.cuda.is_available()
    gpus = []
    if cuda_available:
        for index in range(torch.cuda.device_count()):
            properties = torch.cuda.get_device_properties(index)
            gpus.append(
                {
                    "index": index,
                    "name": properties.name,
                    "compute_capability": f"{properties.major}.{properties.minor}",
                    "total_memory_bytes": properties.total_memory,
                }
            )
    return {
        "cuda_available": cuda_available,
        "cuda_runtime_version": torch.version.cuda,
        "gpu_count": len(gpus),
        "gpus": gpus,
    }


def load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def resolve_paths(rows: list[dict[str, Any]], repo_root: Path) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for row in rows:
        copied = dict(row)
        copied["image_paths"] = [
            str((repo_root / image_path).resolve()) if not Path(image_path).is_absolute() else image_path
            for image_path in row["image_paths"]
        ]
        resolved.append(copied)
    return resolved
