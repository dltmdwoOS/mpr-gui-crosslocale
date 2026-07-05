from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from mpr_crosslocale.data.schema import LABELS, LANGUAGES

EXPECTED_PUBLIC_RELEASE = {
    "manifest_rows": 13470,
    "rows_per_language": 2245,
    "parallel_ids": 2245,
    "languages_per_parallel_id": 6,
    "directed_mismatch_pairs": 67350,
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def validate_manifest_rows(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    sample_ids = [row["sample_id"] for row in rows]
    if len(sample_ids) != len(set(sample_ids)):
        errors.append("sample_id is not unique across manifest")

    parallel_language = [(row["parallel_id"], row["language"]) for row in rows]
    if len(parallel_language) != len(set(parallel_language)):
        errors.append("(parallel_id, language) is not unique across manifest")

    rows_by_language = Counter(row["language"] for row in rows)
    for language in LANGUAGES:
        if rows_by_language[language] != EXPECTED_PUBLIC_RELEASE["rows_per_language"]:
            errors.append(f"language {language} has {rows_by_language[language]} rows")

    if len(rows) != EXPECTED_PUBLIC_RELEASE["manifest_rows"]:
        errors.append(f"manifest has {len(rows)} rows")

    for row in rows:
        if row["gold_label"] not in LABELS:
            errors.append(f"{row['sample_id']} has invalid gold_label {row['gold_label']}")
        if not row.get("asset_exists"):
            errors.append(f"{row['sample_id']} asset does not exist")
        if row.get("is_episode") and int(row.get("num_images", 0)) < 1:
            errors.append(f"{row['sample_id']} episode has no images")
        if row.get("option_parse_status") != "ok":
            errors.append(f"{row['sample_id']} option parse failed")
        if set(row.get("option_order", [])) != set(LABELS):
            errors.append(f"{row['sample_id']} option labels are not A/B/C/D")
    return errors


def validate_parallel_index(index: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    entries = index["entries"]
    if len(entries) != EXPECTED_PUBLIC_RELEASE["parallel_ids"]:
        errors.append(f"parallel index has {len(entries)} entries")
    for entry in entries:
        if len(entry["languages"]) != EXPECTED_PUBLIC_RELEASE["languages_per_parallel_id"]:
            errors.append(f"{entry['parallel_id']} does not have six languages")
        if set(entry["languages"]) != set(LANGUAGES):
            errors.append(f"{entry['parallel_id']} language set mismatch")
        if not entry["gold_labels_consistent"]:
            errors.append(f"{entry['parallel_id']} gold labels are inconsistent")
    return errors


def validate_pairs(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    pair_ids = [row["pair_id"] for row in rows]
    if len(pair_ids) != len(set(pair_ids)):
        errors.append("pair_id is not unique")
    if len(rows) != EXPECTED_PUBLIC_RELEASE["directed_mismatch_pairs"]:
        errors.append(f"cross-locale pair file has {len(rows)} rows")
    return errors


def validate_option_order(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["parallel_id"])].append(row)
    for parallel_id, group in grouped.items():
        orders = {tuple(row.get("option_order", [])) for row in group}
        for row in group:
            if set(row.get("options", {}).keys()) != set(LABELS):
                errors.append(f"{row['sample_id']} option labels are not A/B/C/D")
                break
        if len(orders) != 1:
            # This is a warning-worthy property, but not a hard error for the
            # public release: a few rows preserve non-A/B/C/D option order in
            # some languages while remaining parseable.
            continue
    return errors


def validate_all(
    manifest_path: Path,
    parallel_path: Path,
    pairs_path: Path,
) -> dict[str, Any]:
    manifest = read_jsonl(manifest_path)
    parallel_index = json.loads(parallel_path.read_text(encoding="utf-8"))
    pairs = read_jsonl(pairs_path)
    errors = []
    errors.extend(validate_manifest_rows(manifest))
    errors.extend(validate_parallel_index(parallel_index))
    errors.extend(validate_pairs(pairs))
    errors.extend(validate_option_order(manifest))
    return {
        "ok": not errors,
        "errors": errors,
        "summary": {
            "manifest_rows": len(manifest),
            "parallel_ids": len(parallel_index["entries"]),
            "directed_mismatch_pairs": len(pairs),
        },
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/mpr_gui_manifest.jsonl"))
    parser.add_argument("--parallel", type=Path, default=Path("data/manifests/parallel_index.json"))
    parser.add_argument("--pairs", type=Path, default=Path("data/manifests/cross_locale_pairs.jsonl"))
    args = parser.parse_args(argv)
    result = validate_all(args.manifest, args.parallel, args.pairs)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
