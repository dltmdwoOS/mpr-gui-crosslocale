from __future__ import annotations


def oracle_condition_name(question_language: str, gui_language: str) -> str:
    if question_language == gui_language:
        return "canonical_matched"
    return "oracle_aligned"
