import json
from pathlib import Path

from mpr_crosslocale.data.build_pilot import (
    dataset_relative_image_path,
    huggingface_file_url,
    materialize_pilot,
    select_pilot_rows,
)


def fixture_rows():
    rows = []
    for dimension in ("wf", "wi"):
        for item in ("phone_1.jpg", "phone_2.jpg"):
            for language in ("en", "ja"):
                rows.append(
                    {
                        "sample_id": f"{dimension}::6/{item}::{language}",
                        "parallel_id": f"{dimension}::6/{item}",
                        "dimension": dimension,
                        "language": language,
                        "gold_label": "A",
                        "image_paths": [
                            f"data/raw/mpr_gui_bench/images/6/{language}/"
                            f"{item.removesuffix('.jpg')}_{language}.jpg"
                        ],
                        "num_images": 1,
                    }
                )
    return rows


def test_selects_one_complete_parallel_item_per_dimension():
    rows, parallel_ids = select_pilot_rows(
        fixture_rows(),
        languages=("en", "ja"),
        dimensions=("wf", "wi"),
        items_per_dimension=1,
        seed=42,
    )

    assert len(parallel_ids) == 2
    assert len(rows) == 4
    assert {row["dimension"] for row in rows} == {"wf", "wi"}
    assert all({row["language"] for row in rows if row["parallel_id"] == item} == {"en", "ja"}
               for item in parallel_ids)


def test_dataset_path_and_pinned_download_url():
    path = dataset_relative_image_path(
        "data/raw/mpr_gui_bench/images/6/ja/camera_ja_8.jpg"
    )

    assert path.as_posix() == "6/ja/camera_ja_8.jpg"
    assert huggingface_file_url("owner/repo", "abc123", path).endswith(
        "/abc123/6/ja/camera_ja_8.jpg?download=true"
    )


def test_materialize_rewrites_paths_and_avoids_duplicate_downloads(tmp_path: Path):
    rows = fixture_rows()[:2]
    calls = []

    def fake_download(url: str, destination: Path):
        calls.append((url, destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"image")

    materialized, downloaded = materialize_pilot(
        [rows[0], rows[0], rows[1]],
        tmp_path / "pilot",
        "owner/repo",
        "abc123",
        downloader=fake_download,
    )

    assert len(calls) == 2
    assert len(downloaded) == 2
    assert all(row["asset_exists"] for row in materialized)
    assert json.loads(json.dumps(materialized))[0]["image_paths"][0].startswith(
        (tmp_path / "pilot").as_posix()
    )
