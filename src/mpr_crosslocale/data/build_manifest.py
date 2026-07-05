from __future__ import annotations

import argparse
import json
from pathlib import Path

from mpr_crosslocale.data.parallel_index import canonical_state_key
from mpr_crosslocale.data.pair_builder import build_cross_locale_pair_rows
from mpr_crosslocale.data.validate_release import DIMENSION_FILES, LANGUAGES, iter_jsonl, resolve_asset_path, row_asset
from mpr_crosslocale.inference.answer_parser import parse_label


def build_manifest(root: Path) -> list[dict[str, object]]:
    images_dir = root / "images"
    qas_dir = root / "qas"
    rows: list[dict[str, object]] = []
    for qas_path in sorted(qas_dir.glob("*.jsonl")):
        stem = qas_path.stem
        language = stem.rsplit("_", 1)[-1]
        dimension = next(
            (dim for dim, prefix in DIMENSION_FILES.items() if stem == f"{prefix}_{language}"),
            "unknown",
        )
        for line_no, row in iter_jsonl(qas_path):
            asset, is_episode = row_asset(row)
            state_key = canonical_state_key(asset)
            rows.append(
                {
                    "sample_id": f"{dimension}::{state_key}::{language}",
                    "parallel_id": f"{dimension}::{state_key}",
                    "state_key": state_key,
                    "dimension": dimension,
                    "language": language,
                    "qas_file": qas_path.name,
                    "qas_line": line_no,
                    "question": row.get("question", ""),
                    "answer_raw": row.get("answer", ""),
                    "gold_label": parse_label(str(row.get("answer", ""))),
                    "asset": asset,
                    "asset_path": resolve_asset_path(images_dir, asset).as_posix() if asset else "",
                    "is_episode": is_episode,
                    "asset_exists": resolve_asset_path(images_dir, asset).exists() if asset else False,
                }
            )
    return rows


def build_parallel_index(manifest: list[dict[str, object]]) -> dict[str, object]:
    grouped: dict[str, dict[str, dict[str, object]]] = {}
    for row in manifest:
        parallel_id = str(row["parallel_id"])
        language = str(row["language"])
        grouped.setdefault(parallel_id, {})[language] = {
            "sample_id": row["sample_id"],
            "qas_file": row["qas_file"],
            "qas_line": row["qas_line"],
            "asset": row["asset"],
            "gold_label": row["gold_label"],
            "asset_exists": row["asset_exists"],
        }
    entries = []
    for parallel_id, by_lang in sorted(grouped.items()):
        labels = {lang: meta["gold_label"] for lang, meta in by_lang.items()}
        entries.append(
            {
                "parallel_id": parallel_id,
                "languages": sorted(by_lang),
                "complete": set(by_lang) == set(LANGUAGES),
                "gold_labels": labels,
                "gold_labels_consistent": len(set(labels.values())) == 1,
                "samples": by_lang,
            }
        )
    return {
        "languages": list(LANGUAGES),
        "entries": entries,
        "summary": {
            "parallel_ids": len(entries),
            "complete_parallel_ids": sum(1 for entry in entries if entry["complete"]),
            "gold_label_inconsistent_ids": sum(
                1 for entry in entries if not entry["gold_labels_consistent"]
            ),
        },
    }


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data/raw/mpr_gui_bench"))
    parser.add_argument("--out", type=Path, default=Path("data/manifests/mpr_gui_manifest.jsonl"))
    parser.add_argument("--parallel-out", type=Path, default=Path("data/manifests/parallel_index.json"))
    parser.add_argument("--pairs-out", type=Path, default=Path("data/manifests/cross_locale_pairs.jsonl"))
    args, _ = parser.parse_known_args(argv)
    manifest = build_manifest(args.root)
    write_jsonl(args.out, manifest)
    parallel_index = build_parallel_index(manifest)
    args.parallel_out.parent.mkdir(parents=True, exist_ok=True)
    args.parallel_out.write_text(
        json.dumps(parallel_index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    pair_rows = build_cross_locale_pair_rows(parallel_index)
    write_jsonl(args.pairs_out, pair_rows)
    print(f"Wrote {len(manifest)} manifest rows to {args.out}")
    print(f"Wrote parallel index to {args.parallel_out}")
    print(f"Wrote {len(pair_rows)} cross-locale pair rows to {args.pairs_out}")


if __name__ == "__main__":
    main()
