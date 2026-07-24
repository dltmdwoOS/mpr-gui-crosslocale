import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))

import run_demo


def test_demo_fixture_schema_and_balance():
    rows = run_demo.fixture_rows()

    assert len(rows) == 24
    assert {"en", "ja"} == {row["language"] for row in rows}
    assert {row["dimension"] for row in rows} == set(run_demo.DIMENSIONS)
    assert all("parallel_id" in row and "gold_label" in row for row in rows)
    for dimension in run_demo.DIMENSIONS:
        ids = {row["parallel_id"] for row in rows if row["dimension"] == dimension}
        assert len(ids) == 2


def test_demo_plan_has_two_directions_and_shared_items():
    plan = run_demo.build_cross_locale_plan(
        manifest_rows=run_demo.fixture_rows(),
        language_pairs=list(run_demo.LANGUAGE_PAIRS),
        dimensions=set(run_demo.DIMENSIONS),
        sample_size=12,
        sample_unit="semantic_items",
        seed=42,
    )
    by_pair = {}
    for row in plan.rows:
        by_pair.setdefault((row["question_language"], row["gui_language"]), set()).add(row["parallel_id"])

    assert set(by_pair) == {("en", "ja"), ("ja", "en")}
    assert by_pair[("en", "ja")] == by_pair[("ja", "en")]
    assert plan.n_semantic_items == 12
    assert plan.n_evaluations == 24


def test_demo_mock_is_deterministic_and_scored():
    plan = run_demo.build_cross_locale_plan(
        run_demo.fixture_rows(), list(run_demo.LANGUAGE_PAIRS), set(run_demo.DIMENSIONS), 12, "semantic_items", 42
    )
    row = plan.rows[0]
    first = run_demo._mock_result_row(row, 42, "english_fixed")
    second = run_demo._mock_result_row(row, 42, "english_fixed")
    other = run_demo._mock_result_row(row, 43, "english_fixed")

    assert first["mock_raw_label_logprobs"] == second["mock_raw_label_logprobs"]
    assert first["mock_raw_label_logprobs"] != other["mock_raw_label_logprobs"]
    assert abs(sum(first["label_probabilities"].values()) - 1.0) < 1e-9
    assert 1 <= first["gold_rank"] <= 4


def test_demo_end_to_end_outputs_and_resume(tmp_path, monkeypatch):
    output_dir = tmp_path / "outputs"
    monkeypatch.setattr(run_demo, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(run_demo, "IMAGES_DIR", output_dir / "images")
    monkeypatch.setattr(run_demo, "FIXTURE_MANIFEST", output_dir / "demo_fixture_manifest.jsonl")
    monkeypatch.setattr(run_demo, "RESULTS_PATH", output_dir / "demo_results.jsonl")
    monkeypatch.setattr(run_demo, "SUMMARY_PATH", output_dir / "demo_summary.json")
    monkeypatch.setattr(run_demo, "MATRIX_PATH", output_dir / "demo_matrix.csv")
    monkeypatch.setattr(run_demo, "REPORT_PATH", output_dir / "demo_validation_report.txt")

    args = run_demo.argparse.Namespace(
        seed=42,
        system_prompt_mode="english_fixed",
        resume=False,
        run_resume_check=True,
        clean_demo_output=True,
    )
    result = run_demo.run_demo(args)
    rows = [json.loads(line) for line in run_demo.RESULTS_PATH.read_text(encoding="utf-8").splitlines()]

    assert len(rows) == 24
    assert all(passed for _, passed, _ in result["validation"])
    assert result["summary"]["counts"]["resume_skipped"] == 24
    assert all(row["image_paths"] == [row["image_path"]] for row in rows)
    assert all(f"/images/{row['gui_language']}/" in row["image_path"] for row in rows)
    assert run_demo.SUMMARY_PATH.exists()
    assert run_demo.MATRIX_PATH.exists()
    assert run_demo.REPORT_PATH.exists()
