from __future__ import annotations

MPR_DIRECT_V1_SYSTEM = (
    "You are given a GUI screenshot and a multiple-choice question. "
    "Select the single best answer."
)
MPR_DIRECT_V1_CONSTRAINT = "Return only one letter: A, B, C, or D."


def build_direct_prompt(question: str) -> str:
    return f"{MPR_DIRECT_V1_SYSTEM}\n\n{question}\n\n{MPR_DIRECT_V1_CONSTRAINT}"
