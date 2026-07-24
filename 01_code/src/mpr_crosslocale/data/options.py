from __future__ import annotations

import re
from dataclasses import dataclass

OPTION_RE = re.compile(r"(?<![A-Za-z0-9])([ABCD])\s*[:：]\s*")
LABELS = ("A", "B", "C", "D")


@dataclass(frozen=True)
class ParsedOptions:
    question_stem: str
    options: dict[str, str]
    option_order: list[str]
    option_count: int
    option_parse_status: str


def parse_question_options(question: str) -> ParsedOptions:
    matches = list(OPTION_RE.finditer(question))
    labels = [match.group(1) for match in matches]
    if len(labels) != len(set(labels)):
        return ParsedOptions(
            question_stem=question.strip(),
            options={},
            option_order=labels,
            option_count=len(set(labels)),
            option_parse_status="failed_duplicate_label",
        )
    if set(labels) != set(LABELS):
        return ParsedOptions(
            question_stem=question.strip(),
            options={},
            option_order=labels,
            option_count=len(set(labels)),
            option_parse_status="failed_missing_label",
        )

    options: dict[str, str] = {}
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(question)
        options[match.group(1)] = question[start:end].strip()

    if any(not options[label] for label in LABELS):
        return ParsedOptions(
            question_stem=question[: matches[0].start()].strip(),
            options=options,
            option_order=labels,
            option_count=len(options),
            option_parse_status="failed_empty_option",
        )

    return ParsedOptions(
        question_stem=question[: matches[0].start()].strip(),
        options=options,
        option_order=labels,
        option_count=len(options),
        option_parse_status="ok",
    )
