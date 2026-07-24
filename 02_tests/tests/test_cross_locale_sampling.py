from mpr_crosslocale.data.cross_locale_sampling import (
    build_cross_locale_plan,
    build_language_pairs,
    parse_language_pairs,
)


def fixture_manifest():
    rows = []
    for dimension in ("wf", "ri", "si"):
        for item in ("1/foo.jpg", "2/bar.jpg"):
            for language in ("en", "ja"):
                rows.append(
                    {
                        "sample_id": f"{dimension}::{item}::{language}",
                        "parallel_id": f"{dimension}::{item}",
                        "dimension": dimension,
                        "language": language,
                        "question_raw": f"Question {language}? A: one B: two C: three D: four",
                        "question_stem": f"Question {language}?",
                        "options": {"A": "one", "B": "two", "C": "three", "D": "four"},
                        "option_order": ["A", "B", "C", "D"],
                        "answer_raw": "A",
                        "gold_label": "A",
                        "image_paths": [f"data/{language}/{item}"],
                        "num_images": 1,
                        "frame_order": "single_image",
                    }
                )
    return rows


def test_language_pair_generation_and_parsing():
    assert parse_language_pairs(["en:ja", "ja:en"]) == [("en", "ja"), ("ja", "en")]
    assert build_language_pairs(["en"], ["en", "ja"], include_matched=False) == [("en", "ja")]


def test_dimension_filter_keeps_ri_si_available():
    plan = build_cross_locale_plan(
        fixture_manifest(),
        [("en", "ja"), ("ja", "en")],
        {"ri", "si"},
        sample_size=None,
        sample_unit="semantic_items",
        seed=7,
    )

    assert {row["dimension"] for row in plan.rows} == {"ri", "si"}
    assert all(row["matched"] is False for row in plan.rows)


def test_seed_reproducibility_and_shared_semantic_items():
    kwargs = {
        "manifest_rows": fixture_manifest(),
        "language_pairs": [("en", "ja"), ("ja", "en")],
        "dimensions": {"wf", "ri", "si"},
        "sample_size": 2,
        "sample_unit": "semantic_items",
        "seed": 11,
    }
    first = build_cross_locale_plan(**kwargs)
    second = build_cross_locale_plan(**kwargs)

    assert [row["input_id"] for row in first.rows] == [row["input_id"] for row in second.rows]
    assert first.n_semantic_items == 2
    assert first.n_evaluations == 4
    by_parallel = {}
    for row in first.rows:
        by_parallel.setdefault(row["parallel_id"], set()).add(
            (row["question_language"], row["gui_language"])
        )
    assert all(pairs == {("en", "ja"), ("ja", "en")} for pairs in by_parallel.values())
