from __future__ import annotations

import argparse
import json
import random
import tempfile
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from mpr_crosslocale.data.schema import LANGUAGES


DEFAULT_HF_REPO = "chenruihan/MPR-GUI-Bench"
DEFAULT_DIMENSIONS = ("wf", "wi", "au", "ap", "ael", "rel")
DownloadFn = Callable[[str, Path], None]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_source_lock(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def select_pilot_rows(
    rows: list[dict[str, Any]],
    languages: tuple[str, ...],
    dimensions: tuple[str, ...],
    items_per_dimension: int,
    seed: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    if items_per_dimension < 1:
        raise ValueError("items_per_dimension must be at least 1")

    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        if row.get("dimension") not in dimensions:
            continue
        grouped[str(row["parallel_id"])][str(row["language"])] = row

    candidates: dict[str, list[str]] = defaultdict(list)
    for parallel_id, by_language in grouped.items():
        if not all(language in by_language for language in languages):
            continue
        selected_languages = [by_language[language] for language in languages]
        if not all(int(row.get("num_images", 0)) == 1 for row in selected_languages):
            continue
        if len({str(row.get("gold_label")) for row in selected_languages}) != 1:
            continue
        candidates[str(selected_languages[0]["dimension"])].append(parallel_id)

    rng = random.Random(seed)
    selected_ids: list[str] = []
    for dimension in dimensions:
        dimension_ids = sorted(candidates.get(dimension, []))
        if len(dimension_ids) < items_per_dimension:
            raise ValueError(
                f"Dimension {dimension!r} has {len(dimension_ids)} eligible items; "
                f"{items_per_dimension} requested"
            )
        selected_ids.extend(rng.sample(dimension_ids, items_per_dimension))

    output_rows = [
        grouped[parallel_id][language]
        for parallel_id in selected_ids
        for language in languages
    ]
    return output_rows, selected_ids


def dataset_relative_image_path(image_path: str) -> PurePosixPath:
    normalized = image_path.replace("\\", "/")
    marker = "/images/"
    if marker in normalized:
        relative = normalized.split(marker, 1)[1]
    elif normalized.startswith("images/"):
        relative = normalized[len("images/") :]
    else:
        raise ValueError(f"Cannot locate dataset image path in {image_path!r}")

    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe dataset image path: {image_path!r}")
    return path


def huggingface_file_url(repo_id: str, revision: str, relative_path: PurePosixPath) -> str:
    quoted_repo = urllib.parse.quote(repo_id, safe="/")
    quoted_revision = urllib.parse.quote(revision, safe="")
    quoted_path = urllib.parse.quote(relative_path.as_posix(), safe="/")
    return (
        f"https://huggingface.co/datasets/{quoted_repo}/resolve/"
        f"{quoted_revision}/{quoted_path}?download=true"
    )


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "mpr-gui-crosslocale/0.1"})
    with tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.", suffix=".part", dir=destination.parent, delete=False
    ) as handle:
        temporary_path = Path(handle.name)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                while chunk := response.read(1024 * 1024):
                    handle.write(chunk)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
    if temporary_path.stat().st_size == 0:
        temporary_path.unlink(missing_ok=True)
        raise ValueError(f"Downloaded an empty file from {url}")
    temporary_path.replace(destination)


def materialize_pilot(
    rows: list[dict[str, Any]],
    output_root: Path,
    repo_id: str,
    revision: str,
    downloader: DownloadFn = download_file,
) -> tuple[list[dict[str, Any]], list[Path]]:
    materialized: list[dict[str, Any]] = []
    downloaded: list[Path] = []
    seen: set[PurePosixPath] = set()

    for row in rows:
        copied = dict(row)
        local_paths: list[str] = []
        for source_path in row["image_paths"]:
            relative_path = dataset_relative_image_path(str(source_path))
            destination = output_root / "images" / Path(relative_path.as_posix())
            if relative_path not in seen:
                if not destination.exists():
                    downloader(
                        huggingface_file_url(repo_id, revision, relative_path),
                        destination,
                    )
                    downloaded.append(destination)
                seen.add(relative_path)
            local_paths.append(destination.as_posix())

        copied["image_paths"] = local_paths
        copied["asset_path"] = local_paths[0]
        copied["asset_exists"] = all(Path(path).is_file() for path in local_paths)
        materialized.append(copied)

    return materialized, downloaded


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Select a small paired MPR-GUI pilot and download only its images."
    )
    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=Path("data/manifests/mpr_gui_manifest.jsonl"),
    )
    parser.add_argument("--output-root", type=Path, default=Path("data/pilot"))
    parser.add_argument("--languages", nargs="+", default=["en", "ja"])
    parser.add_argument("--dimensions", nargs="+", default=list(DEFAULT_DIMENSIONS))
    parser.add_argument("--items-per-dimension", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--source-lock",
        type=Path,
        default=Path("data/manifests/source_lock.json"),
    )
    parser.add_argument("--hf-repo", default=DEFAULT_HF_REPO)
    parser.add_argument("--hf-revision", default=None)
    args = parser.parse_args(argv)

    unsupported = sorted(set(args.languages) - set(LANGUAGES))
    if unsupported:
        parser.error(f"Unsupported languages: {', '.join(unsupported)}")

    if args.source_lock.exists():
        lock = load_source_lock(args.source_lock)
        args.hf_repo = lock.get("huggingface", {}).get("repo_id", args.hf_repo)
        args.hf_revision = lock.get("huggingface", {}).get("sha", args.hf_revision)
    if not args.hf_revision:
        parser.error("--hf-revision is required when the source lock does not provide one")

    rows = read_jsonl(args.source_manifest)
    selected_rows, selected_ids = select_pilot_rows(
        rows,
        tuple(args.languages),
        tuple(args.dimensions),
        args.items_per_dimension,
        args.seed,
    )
    materialized_rows, downloaded = materialize_pilot(
        selected_rows,
        args.output_root,
        args.hf_repo,
        args.hf_revision,
    )

    manifest_path = args.output_root / "pilot_manifest.jsonl"
    metadata_path = args.output_root / "pilot_selection.json"
    write_jsonl(manifest_path, materialized_rows)
    metadata = {
        "source_manifest": args.source_manifest.as_posix(),
        "repo_id": args.hf_repo,
        "revision": args.hf_revision,
        "languages": args.languages,
        "dimensions": args.dimensions,
        "items_per_dimension": args.items_per_dimension,
        "seed": args.seed,
        "parallel_ids": selected_ids,
        "manifest_rows": len(materialized_rows),
        "downloaded_images": len(downloaded),
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    print(f"Pilot manifest: {manifest_path}")


if __name__ == "__main__":
    main()
