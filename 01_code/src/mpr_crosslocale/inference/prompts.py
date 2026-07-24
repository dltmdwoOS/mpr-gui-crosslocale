from __future__ import annotations

MPR_LABEL_ONLY_V1_SUFFIX = "Respond with exactly one label: A, B, C, or D."


def build_prompt_text(question: str, prompt_profile: str) -> str:
    if prompt_profile == "mpr_minimal_v1":
        return question
    if prompt_profile == "mpr_label_only_v1":
        return f"{question}\n\n{MPR_LABEL_ONLY_V1_SUFFIX}"
    if prompt_profile == "mpr_direct_v1":
        return (
            "You are given a GUI screenshot and a multiple-choice question. "
            "Select the single best answer.\n\n"
            f"{question}\n\n{MPR_LABEL_ONLY_V1_SUFFIX}"
        )
    raise ValueError(f"Unknown prompt profile: {prompt_profile}")
