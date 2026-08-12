from __future__ import annotations

import hashlib

from mpr_crosslocale.analysis.rq4_translation_correspondence import (
    build_diagnostics,
    character_ngram_fscore,
    correspondence_metrics,
    extract_quoted_spans,
    normalize_correspondence_text,
    translations_from_inference_rows,
)


def test_reconstructs_translation_from_sha_verified_qwen_prompt() -> None:
    question_raw = (
        'Which item is below "Settings"? '
        "A: Find B: Rename C: Duplicate D: Hide grid"
    )
    row = {
        "translation_id": "t1",
        "pair_id": "p1",
        "parallel_id": "rel::x",
        "source_question_language": "en",
        "gui_language": "fr",
        "target_human_parallel_endpoint_id": "rel::x::fr",
        "gold_label": "B",
        "question_raw_sha256": hashlib.sha256(question_raw.encode()).hexdigest(),
        "rendered_prompt": (
            "prefix<|vision_end|>"
            + question_raw
            + "\n\nRespond with exactly one label: A, B, C, or D.<|im_end|>"
        ),
        "translation_status": "ok",
        "translation_analysis_eligible": True,
        "translation_semantic_diagnostic_flags": [],
    }
    reconstructed = translations_from_inference_rows([row])
    assert reconstructed[0]["translated_question_stem"] == (
        'Which item is below "Settings"?'
    )
    assert reconstructed[0]["translated_options"]["D"] == "Hide grid"


def test_quoted_span_extraction_handles_gui_quote_systems_and_apostrophes() -> None:
    text = (
        "L'interface montre 'Settings', “Favorite”, « Rename », "
        "「複製」 et 『グリッド』."
    )
    assert extract_quoted_spans(text) == [
        "Settings",
        "Favorite",
        "Rename",
        "複製",
        "グリッド",
    ]


def test_correspondence_metrics_preserve_option_identity() -> None:
    metrics, alignments = correspondence_metrics(
        'Which item is below "Settings"?',
        {"A": "Find", "B": "Rename", "C": "Duplicate", "D": "Hide grid"},
        'Which item is below “Settings”?',
        {"A": "Find", "B": "Rename", "C": "Copy", "D": "Hide grid"},
    )
    assert metrics["quoted_exact_recall"] == 1.0
    assert metrics["quoted_aligned_edit_similarity"] == 1.0
    assert metrics["exact_option_match_count"] == 3
    assert metrics["option_C_normalized_exact_match"] == 0
    assert metrics["option_A_edit_similarity"] == 1.0
    assert len(alignments) == 1


def test_missing_and_extra_quotes_are_penalized_without_inflating_empty_rows() -> None:
    missing, _ = correspondence_metrics(
        "Target is below Settings",
        {label: label for label in "ABCD"},
        'Target is below "Settings"',
        {label: label for label in "ABCD"},
    )
    assert missing["human_quoted_span_count"] == 1
    assert missing["translated_quoted_span_count"] == 0
    assert missing["quoted_exact_recall"] == 0.0
    assert missing["quoted_exact_precision"] is None
    assert missing["quoted_exact_f1"] == 0.0
    assert missing["quoted_aligned_edit_similarity"] == 0.0

    empty, _ = correspondence_metrics(
        "No quoted label",
        {label: label for label in "ABCD"},
        "No quoted label",
        {label: label for label in "ABCD"},
    )
    assert empty["quoted_exact_f1"] is None
    assert empty["quoted_aligned_edit_similarity"] is None


def test_character_ngram_score_and_nfkc_normalization() -> None:
    assert normalize_correspondence_text("  ＳＥＴＴＩＮＧＳ  ") == "settings"
    assert character_ngram_fscore("Settings", "Settings") == 1.0
    assert 0.0 < character_ngram_fscore("Rename", "Renaming") < 1.0
    assert character_ngram_fscore("Left", "Right") < 0.5


def test_build_diagnostics_joins_human_only_after_translation() -> None:
    translation = {
        "translation_id": "t1",
        "pair_id": "p1",
        "parallel_id": "rel::x",
        "source_language": "en",
        "target_language": "ja",
        "target_human_parallel_endpoint_id": "rel::x::ja",
        "gold_label": "B",
        "translated_question_stem": '「設定」の下は何ですか？',
        "translated_options": {"A": "検索", "B": "名前変更", "C": "複製", "D": "非表示"},
        "translation_status": "ok",
        "translation_analysis_eligible": True,
        "semantic_diagnostic_flags": [],
    }
    human = {
        "rel::x::ja": {
            "question_stem": '「設定」の下は何ですか？',
            "options": {"A": "検索", "B": "名前変更", "C": "複製", "D": "非表示"},
        }
    }
    rows, alignments = build_diagnostics(
        [translation], human, {"rel::x": "dependent"}, {}
    )
    assert len(rows) == 1
    assert rows[0]["quoted_exact_f1"] == 1.0
    assert rows[0]["mean_option_char_ngram_fscore"] == 1.0
    assert rows[0]["gold_minus_wrong_option_char_ngram_fscore"] == 0.0
    assert rows[0]["text_dependency"] == "dependent"
    assert len(alignments) == 1
