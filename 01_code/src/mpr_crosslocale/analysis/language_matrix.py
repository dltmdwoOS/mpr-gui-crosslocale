from __future__ import annotations


def matrix_key(question_language: str, gui_language: str) -> str:
    return f"{question_language}->{gui_language}"
