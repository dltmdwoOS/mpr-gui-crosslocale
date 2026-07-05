import json
from pathlib import Path
from types import SimpleNamespace

from mpr_crosslocale.inference.run_canonical import filter_rows
from mpr_crosslocale.inference.runtime import existing_success_ids


def test_filter_rows_by_language_dimension_and_limit():
    rows = [
        {"question_language": "en", "dimension": "wf"},
        {"question_language": "ja", "dimension": "wf"},
        {"question_language": "en", "dimension": "ri"},
    ]

    selected = filter_rows(rows, {"en"}, {"wf", "ri"}, 1)

    assert selected == [{"question_language": "en", "dimension": "wf"}]


def test_existing_success_ids(tmp_path: Path):
    path = tmp_path / "results.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"input_id": "a", "status": "success"}),
                json.dumps({"input_id": "b", "status": "failed"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert existing_success_ids(path) == {"a"}
