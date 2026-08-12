from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from mpr_crosslocale.interventions.rq4_gui_lexical import read_jsonl


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Build a compact human-review CSV for visible-string inventories."
    )
    parser.add_argument("--inventories", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    rows = read_jsonl(args.inventories)
    review = []
    for index, row in enumerate(
        sorted(rows, key=lambda value: value["inventory_id"]), start=1
    ):
        review.append(
            {
                "review_order": index,
                "inventory_id": row["inventory_id"],
                "parallel_id": row["parallel_id"],
                "target_language": row["target_language"],
                "gui_sample_id": row["gui_sample_id"],
                "image_path": row["image_paths"][0],
                "visible_string_count": len(row["visible_strings"]),
                "visible_strings": json.dumps(
                    row["visible_strings"], ensure_ascii=False
                ),
                "attempt_count": row["attempt_count"],
                "inventory_status": row["inventory_status"],
                "review_label": "",
                "review_note": "",
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(review[0]))
        writer.writeheader()
        writer.writerows(review)
    temporary.replace(args.output)
    print(
        json.dumps(
            {
                "status": "complete",
                "rows": len(review),
                "output": args.output.as_posix(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
