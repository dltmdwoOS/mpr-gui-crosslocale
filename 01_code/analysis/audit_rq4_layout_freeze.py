"""Verify that the frozen RQ4 lexical intervention is query-blind and layout-free."""

from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


EXPECTED_INVENTORIES = 2_196
EXPECTED_TRANSLATIONS = 10_980


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonicalize(values: list[str]) -> list[str]:
    by_key: dict[str, str] = {}
    for value in values:
        cleaned = " ".join(unicodedata.normalize("NFKC", str(value)).split()).strip()
        if cleaned:
            by_key.setdefault(cleaned.casefold(), cleaned)
    return [by_key[key] for key in sorted(by_key)]


def audit(inventory_path: Path, translation_path: Path, downstream_path: Path) -> dict[str, Any]:
    inventories = read_jsonl(inventory_path)
    translations = read_jsonl(translation_path)
    downstream = read_jsonl(downstream_path)
    if len(inventories) != EXPECTED_INVENTORIES:
        raise ValueError(f"Expected {EXPECTED_INVENTORIES} inventories; found {len(inventories)}")
    if len(translations) != EXPECTED_TRANSLATIONS or len(downstream) != EXPECTED_TRANSLATIONS:
        raise ValueError("Expected 10,980 translations and downstream inputs.")

    inventory_by_id = {row["inventory_id"]: row for row in inventories}
    if len(inventory_by_id) != EXPECTED_INVENTORIES:
        raise ValueError("Duplicate inventory IDs detected.")
    forbidden_inventory_fields = {
        "question_raw", "question_stem", "options", "gold_label",
        "text_dependency", "human_question", "model_prediction",
        "bbox", "coordinates", "positions",
    }
    checks = {
        "query_content_exposed_rows": sum(bool(row.get("query_content_exposed")) for row in inventories),
        "inventory_forbidden_field_rows": sum(bool(forbidden_inventory_fields & set(row)) for row in inventories),
        "translation_noncanonical_order_rows": 0,
        "raw_to_stage2_canonical_mismatch_rows": 0,
        "inventory_order_exposed_rows": 0,
        "inventory_duplicate_counts_exposed_rows": 0,
        "translator_layout_exposed_rows": 0,
        "translator_screenshot_exposed_rows": 0,
        "translator_gold_exposed_rows": 0,
        "translator_dependency_exposed_rows": 0,
        "downstream_inventory_payload_rows": sum(
            bool({"visible_strings", "target_gui_visible_strings"} & set(row))
            for row in downstream
        ),
    }
    for row in translations:
        inventory = inventory_by_id[row["visible_string_inventory_id"]]
        checks["translation_noncanonical_order_rows"] += int(
            row["visible_strings"] != canonicalize(row["visible_strings"])
        )
        checks["raw_to_stage2_canonical_mismatch_rows"] += int(
            row["visible_strings"] != canonicalize(inventory["visible_strings"])
        )
        checks["inventory_order_exposed_rows"] += int(
            bool(row.get("inventory_order_exposed_to_translator"))
            or bool(row.get("translator_inventory_order_exposed"))
        )
        checks["inventory_duplicate_counts_exposed_rows"] += int(
            bool(row.get("inventory_duplicate_counts_exposed_to_translator"))
            or bool(row.get("translator_inventory_duplicate_counts_exposed"))
        )
        checks["translator_layout_exposed_rows"] += int(bool(row.get("translator_layout_exposed")))
        checks["translator_screenshot_exposed_rows"] += int(bool(row.get("translator_screenshot_exposed")))
        checks["translator_gold_exposed_rows"] += int(bool(row.get("translator_gold_exposed")))
        checks["translator_dependency_exposed_rows"] += int(bool(row.get("translator_dependency_exposed")))

    failures = {name: value for name, value in checks.items() if value != 0}
    result = {
        "status": "pass" if not failures else "fail",
        "scope": "RQ4 target-GUI lexical intervention layout/query leakage freeze",
        "inventory_rows": len(inventories),
        "translation_rows": len(translations),
        "downstream_input_rows": len(downstream),
        "inventory_status_counts": dict(Counter(row["inventory_status"] for row in inventories)),
        "checks": checks,
        "failures": failures,
        "inventory_sha256": file_sha256(inventory_path),
        "translation_sha256": file_sha256(translation_path),
        "downstream_input_sha256": file_sha256(downstream_path),
        "interpretation": (
            "Raw extractor order is discarded through canonical lexical sorting before "
            "Stage 2; the downstream VLM receives the localized MCQ, not the inventory."
        ),
    }
    if failures:
        raise ValueError(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventories", type=Path, required=True)
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--downstream-inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.inventories, args.translations, args.downstream_inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
