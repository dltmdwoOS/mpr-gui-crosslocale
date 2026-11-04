"""Append all saved Qwen grounding pilot outputs as Markdown tables, without inference."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "results"
REPORT = HERE / "QWEN_GROUNDING_PILOTS_SUMMARY_KO.md"
GT = HERE / "annotations_20261103/grounding_gt_draft_170.json"
START = "<!-- ALL_RESULTS_START -->"
END = "<!-- ALL_RESULTS_END -->"
GUI_ORDER = ("en", "zh", "th", "ru")
CONTROLS = ("rel::1/booking_1.jpg", "rel::5/message_1.jpg")


def read_rows(relative: str) -> list[dict]:
    path = RESULTS / relative
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def index(rows: list[dict], key) -> dict:
    indexed = {key(row): row for row in rows}
    assert len(indexed) == len(rows)
    return indexed


def code(value: str) -> str:
    assert "|" not in value
    longest = max((len(match.group()) for match in re.finditer(r"`+", value)), default=0)
    delimiter = "`" * max(1, longest + 1)
    return f"{delimiter}{value}{delimiter}"


def result(record: dict) -> str:
    assert record["point_in_gt_box"] is False or record["valid_output"] is True
    status = "✓ 적중" if record["point_in_gt_box"] else (
        "× GT 밖" if record["valid_output"] else "무효")
    assert "⏎" not in record["raw_output"]
    raw = record["raw_output"].replace("\n", "⏎")
    return f"{status} {code(raw)}"


def original_gt(annotations: dict, pid: str, gui: str, records: tuple[dict, ...]) -> str:
    target = annotations[pid][gui]
    for row in records:
        assert row["parallel_id"] == pid and row["gui_language"] == gui
        assert row["image_sha256"] == target["image_sha256"]
        assert row["original_image_size"] == target["image_size"]
    return code(",".join(f"{value:g}" for value in target["bbox"]))


def input_size(records: tuple[dict, ...]) -> str:
    grids = {tuple(row["image_grid_thw"]) for row in records}
    assert len(grids) == 1
    _, height, width = next(iter(grids))
    return f"{width * 14}×{height * 14}"


def relative_gt(record: dict) -> str:
    width, height = record["image_size"]
    x1, y1, x2, y2 = record["gt_bbox"]
    point = (round(1000 * x1 / width), round(1000 * y1 / height),
             round(1000 * x2 / width), round(1000 * y2 / height))
    return code(",".join(map(str, point)))


def verified_count(rows: list[dict], *, count: int, valid: int, hit: int) -> None:
    assert len(rows) == count
    assert sum(row["valid_output"] for row in rows) == valid
    assert sum(row["point_in_gt_box"] for row in rows) == hit


def build_tables() -> tuple[str, int]:
    annotations = json.loads(GT.read_text(encoding="utf-8"))["annotations"]
    controls_original = {
        "full": index(read_rows("grounding_pilot_qwen_v3/controls.jsonl"),
                      lambda row: (row["parallel_id"], row["gui_language"])),
        "phrase": index(read_rows("grounding_pilot_qwen_phrase_v1/controls.jsonl"),
                        lambda row: (row["parallel_id"], row["gui_language"])),
    }
    controls_repeat = index(read_rows("grounding_format_comparison_v1/controls.jsonl"),
                            lambda row: (row["parallel_id"], row["gui_language"], row["arm"]))
    pilot_json = index(read_rows("grounding_pilot_qwen_phrase_v1/pilot.jsonl"),
                       lambda row: (row["parallel_id"], row["gui_language"], row["condition"]))
    pilot_tuple = index(read_rows("grounding_format_comparison_v1/pilot_phrase_tuple.jsonl"),
                        lambda row: (row["parallel_id"], row["gui_language"], row["condition"]))
    qwen25_relative = index(read_rows("grounding_pilot_qwen25_relative_controls/predictions.jsonl"),
                            lambda row: (row["parallel_id"], row["gui_language"], row["arm"]))
    qwen3_prompts = index(read_rows("grounding_pilot_qwen3_8b_prompts/predictions.jsonl"),
                          lambda row: (row["parallel_id"], row["gui_language"], row["arm"]))
    qwen3_orc = index(read_rows("grounding_pilot_qwen3_8b_orc_element_only/predictions.jsonl"),
                      lambda row: (row["pair_id"], row["condition"]))
    assert [len(controls_original[arm]) for arm in ("full", "phrase")] == [8, 8]
    assert (len(controls_repeat), len(pilot_json), len(pilot_tuple),
            len(qwen25_relative), len(qwen3_prompts), len(qwen3_orc)) == (32, 96, 96, 16, 16, 12)
    pilot_ids = sorted({key[0] for key in pilot_json})
    assert len(pilot_ids) == 12

    lines = [
        "## 부록: 실행한 모든 개별 결과", "",
        "아래 표에는 이전에 버린 설정을 제외한 **284개 실제 응답**을 모두 넣었다. "
        "`✓ 적중`은 유효한 점이 GT 안, `× GT 밖`은 유효하지만 GT 밖, "
        "`무효`는 단일 점을 얻지 못한 경우다. 원시 출력의 `⏎`는 줄바꿈을 뜻한다. "
        "줄바꿈 표시 외에 응답 원문은 줄이거나 고치지 않았다.", "",
        "### Qwen2.5: 같은 언어 8화면 × 전체 질문·짧은 설명", "",
        "JSON 최초 실행, 동일 입력 JSON 재실행, 괄호형 실행을 각각 표시한다. "
        "GT는 **원본 이미지 픽셀**, 출력 좌표는 **모델 입력 이미지 픽셀**이다. "
        "직접 숫자를 비교하지 않고 원본 크기로 환산해 채점했다.", "",
    ]
    used = 0
    for input_kind, name in (("full", "전체 관계 질문"), ("phrase", "짧은 설명")):
        lines += [f"#### {name}", "",
                  "| 문항 | GUI | GT bbox (원본 px) | 모델 화면 | 최초 JSON | 재실행 JSON | `(x, y)` |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        first_rows, repeat_rows, tuple_rows = [], [], []
        for pid in CONTROLS:
            for gui in GUI_ORDER:
                first = controls_original[input_kind][pid, gui]
                repeat = controls_repeat[pid, gui, f"{input_kind}_json"]
                tuple_record = controls_repeat[pid, gui, f"{input_kind}_tuple"]
                records = (first, repeat, tuple_record)
                assert all(first[field] == repeat[field] for field in (
                    "raw_output", "rendered_prompt", "valid_output", "point_in_gt_box",
                    "parsed_point_model_pixels", "image_grid_thw"))
                gt = original_gt(annotations, pid, gui, records)
                size = input_size(records)
                lines.append(f"| {code(pid)} | {gui.upper()} | {gt} | {size} | "
                             f"{result(first)} | {result(repeat)} | {result(tuple_record)} |")
                first_rows.append(first)
                repeat_rows.append(repeat)
                tuple_rows.append(tuple_record)
                used += 3
        expected = (6, 0, 6, 1) if input_kind == "full" else (3, 3, 6, 6)
        for group, valid, hit in ((first_rows, *expected[:2]),
                                  (repeat_rows, *expected[:2]),
                                  (tuple_rows, *expected[2:])):
            verified_count(group, count=8, valid=valid, hit=hit)
        lines.append("")

    lines += [
        "### Qwen2.5: 짧은 설명 O/R, 48언어쌍", "",
        "각 행은 한 조건의 **JSON과 괄호형 응답 두 개**다. "
        "GT는 원본 픽셀, 출력은 모델 입력 픽셀이다.", "",
    ]
    for gui in GUI_ORDER:
        lines += [f"#### {gui.upper()} GUI", "",
                  "| 문항 | 질문→GUI | 조건 | GT bbox (원본 px) | 모델 화면 | JSON | `(x, y)` |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for pid in pilot_ids:
            for condition in ("O", "R"):
                first = pilot_json[pid, gui, condition]
                second = pilot_tuple[pid, gui, condition]
                assert first["pair_id"] == second["pair_id"]
                assert first["query_language"] == second["query_language"]
                records = (first, second)
                gt = original_gt(annotations, pid, gui, records)
                size = input_size(records)
                direction = f"{first['query_language'].upper()}→{gui.upper()}"
                lines.append(f"| {code(pid)} | {direction} | {condition} | {gt} | {size} | "
                             f"{result(first)} | {result(second)} |")
                used += 2
        lines.append("")
    verified_count(list(pilot_json.values()), count=96, valid=43, hit=43)
    verified_count(list(pilot_tuple.values()), count=96, valid=52, hit=47)
    assert Counter(row["condition"] for row in pilot_json.values()) == {"O": 48, "R": 48}
    assert {arm: sum("addCriterion" in row["raw_output"] for row in group.values())
            for arm, group in (("JSON", pilot_json), ("(x, y)", pilot_tuple))} == {
                "JSON": 41, "(x, y)": 35}

    lines += [
        "### Qwen2.5: 같은 언어 8화면, 0–1000 상대좌표", "",
        "GT와 요청 출력은 **0–1000 상대 좌표**다. 완성된 좌표라도 범위를 넘으면 `무효`다. "
        "GT는 표시할 때만 반올림했다.", "",
        "| 문항 | GUI | GT bbox (0–1000) | 전체 관계 질문 | 짧은 설명 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for pid in CONTROLS:
        for gui in GUI_ORDER:
            full = qwen25_relative[pid, gui, "query_informed"]
            phrase = qwen25_relative[pid, gui, "element_only"]
            assert full["image_sha256"] == phrase["image_sha256"] == annotations[pid][gui]["image_sha256"]
            assert full["gt_bbox"] == phrase["gt_bbox"] == annotations[pid][gui]["bbox"]
            assert full["model_loading"] == phrase["model_loading"] == "from_pretrained"
            lines.append(f"| {code(pid)} | {gui.upper()} | {relative_gt(full)} | "
                         f"{result(full)} | {result(phrase)} |")
            used += 2
    lines.append("")
    for arm, count in (("query_informed", 5), ("element_only", 2)):
        group = [row for row in qwen25_relative.values() if row["arm"] == arm]
        verified_count(group, count=8, valid=0, hit=0)
        assert sum("addCriterion" in row["raw_output"] for row in group) == count

    lines += [
        "### Qwen3: 같은 언어 8화면", "",
        "GT와 출력은 모두 **0–1000 상대 좌표**다. 표의 GT만 읽기 쉽게 반올림했으며 "
        "실제 채점은 반올림 전 원본 bbox로 했다.", "",
        "| 문항 | GUI | GT bbox (0–1000) | 전체 관계 질문 | 짧은 설명 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for pid in CONTROLS:
        for gui in GUI_ORDER:
            full = qwen3_prompts[pid, gui, "query_informed"]
            phrase = qwen3_prompts[pid, gui, "element_only"]
            assert full["image_sha256"] == phrase["image_sha256"] == annotations[pid][gui]["image_sha256"]
            assert full["gt_bbox"] == phrase["gt_bbox"] == annotations[pid][gui]["bbox"]
            lines.append(f"| {code(pid)} | {gui.upper()} | {relative_gt(full)} | "
                         f"{result(full)} | {result(phrase)} |")
            used += 2
    lines.append("")
    full_rows = [row for row in qwen3_prompts.values() if row["arm"] == "query_informed"]
    phrase_rows = [row for row in qwen3_prompts.values() if row["arm"] == "element_only"]
    verified_count(full_rows, count=8, valid=8, hit=0)
    verified_count(phrase_rows, count=8, valid=8, hit=8)

    lines += [
        "### Qwen3: 짧은 설명 O/R/C, 4언어쌍", "",
        "GT와 출력은 모두 **0–1000 상대 좌표**다. GT는 표시할 때만 반올림했다.", "",
        "| 문항 | 질문→GUI | GT bbox (0–1000) | O | R | C |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    pair_ids = sorted({key[0] for key in qwen3_orc})
    assert len(pair_ids) == 4
    for pair_id in pair_ids:
        group = tuple(qwen3_orc[pair_id, condition] for condition in ("O", "R", "C"))
        first = group[0]
        pid, gui = first["parallel_id"], first["gui_language"]
        assert all(row["image_sha256"] == annotations[pid][gui]["image_sha256"]
                   and row["gt_bbox"] == annotations[pid][gui]["bbox"] for row in group)
        direction = f"{first['source_language'].upper()}→{gui.upper()}"
        lines.append(f"| {code(pid)} | {direction} | {relative_gt(first)} | "
                     + " | ".join(result(row) for row in group) + " |")
        used += 3
    lines.append("")
    for condition, hit in (("O", 3), ("R", 4), ("C", 3)):
        verified_count([row for row in qwen3_orc.values() if row["condition"] == condition],
                       count=4, valid=4, hit=hit)
    assert used == 284
    assert all(row["stop_reason"] == "eos" for row in (*qwen3_prompts.values(), *qwen3_orc.values()))
    return "\n".join(lines).rstrip(), used


def main() -> None:
    block, count = build_tables()
    report = REPORT.read_text(encoding="utf-8")
    if START in report:
        before, rest = report.split(START, 1)
        _, after = rest.split(END, 1)
        report = before.rstrip() + "\n\n" + START + "\n" + block + "\n" + END + after
    else:
        report = report.rstrip() + "\n\n" + START + "\n" + block + "\n" + END + "\n"
    REPORT.write_text(report, encoding="utf-8")
    print(f"Wrote {REPORT}: {count} individual outputs")


if __name__ == "__main__":
    main()
