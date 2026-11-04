"""Write Markdown reviews of saved Qwen grounding outputs, without inference."""

from __future__ import annotations

import json
import re
from pathlib import Path

from build_protocol_inputs import HERE, REPO
from run_qwen_pilot import _read_jsonl


RESULTS = REPO / "followup_rel_4lang/results"
INPUTS = RESULTS / "grounding_protocol_inputs_v3"
GT_PATH = HERE / "annotations_20261103/grounding_gt_draft_170.json"
DESCRIPTORS = HERE / "pilot_referent_phrases.json"
GUI_ORDER = ("en", "zh", "th", "ru")
CONTROLS_FIRST = ("rel::1/booking_1.jpg", "rel::5/message_1.jpg")
MARKED = re.compile(r"<ref>[^<>]+</ref>")


def _by_key(path: Path, key) -> dict:
    rows = _read_jsonl(path)
    indexed = {key(row): row for row in rows}
    assert len(indexed) == len(rows), path
    return indexed


def _phrase(question: str, descriptor: str) -> str:
    match = MARKED.search(question)
    assert match and descriptor.count("{ref}") == 1
    phrase = descriptor.format(ref=match.group(0))
    assert phrase in question
    return phrase


def _check(record: dict, item: dict, annotation: dict) -> None:
    assert record["parallel_id"] == item["parallel_id"]
    assert record["gui_language"] == item["gui_language"]
    assert record["query_language"] == item.get("query_language", item["gui_language"])
    assert record["image_path"] == item["image_path"]
    assert record["image_sha256"] == item["image_sha256"] == annotation["image_sha256"]
    assert record["original_image_size"] == annotation["image_size"]


def _same_regeneration(current: dict, previous: dict) -> None:
    for field in ("raw_output", "rendered_prompt", "valid_output", "point_in_gt_box",
                  "parsed_point_model_pixels", "image_grid_thw"):
        assert current[field] == previous[field], field


def load_cases() -> tuple[list[str], dict[str, list[dict]]]:
    package = json.loads(GT_PATH.read_text(encoding="utf-8"))
    gt = package["annotations"]
    pilot_ids = package["gt_assembly"]["pilot_item_ids"]
    assert len(pilot_ids) == 12 and set(CONTROLS_FIRST) <= set(pilot_ids)
    pilot_ids = list(CONTROLS_FIRST) + sorted(set(pilot_ids) - set(CONTROLS_FIRST))
    descriptors = json.loads(DESCRIPTORS.read_text(encoding="utf-8"))["descriptors"]

    controls = _by_key(INPUTS / "positive_controls.jsonl",
                       lambda row: (row["parallel_id"], row["gui_language"]))
    pilot_rows = [row for row in _read_jsonl(INPUTS / "grounding_pairs.jsonl")
                  if row["split"] == "pilot"]
    pairs = {(row["parallel_id"], row["gui_language"]): row for row in pilot_rows}
    assert len(pairs) == len(pilot_rows)
    assert len(controls) == 8 and len(pairs) == 48
    assert set(pairs) == {(pid, gui) for pid in pilot_ids for gui in GUI_ORDER}

    full_json = _by_key(RESULTS / "grounding_pilot_qwen_v3/controls.jsonl",
                        lambda row: (row["parallel_id"], row["gui_language"]))
    phrase_json = _by_key(RESULTS / "grounding_pilot_qwen_phrase_v1/controls.jsonl",
                          lambda row: (row["parallel_id"], row["gui_language"]))
    comparison = _by_key(RESULTS / "grounding_format_comparison_v1/controls.jsonl",
                         lambda row: (row["parallel_id"], row["gui_language"], row["arm"]))
    pilot_json = _by_key(RESULTS / "grounding_pilot_qwen_phrase_v1/pilot.jsonl",
                         lambda row: (row["pair_id"], row["condition"]))
    pilot_tuple = _by_key(RESULTS / "grounding_format_comparison_v1/pilot_phrase_tuple.jsonl",
                          lambda row: (row["pair_id"], row["condition"]))
    assert len(full_json) == len(phrase_json) == 8
    assert len(comparison) == 32 and len(pilot_json) == len(pilot_tuple) == 96

    cases = {gui: [] for gui in GUI_ORDER}
    for index, pid in enumerate(pilot_ids, 1):
        for gui in GUI_ORDER:
            key = pid, gui
            item = pairs[key]
            annotation = gt[pid][gui]
            image = HERE / f"qwen_pilot_gallery/pilot_{index:02d}_{gui}.webp"
            assert image.is_file()
            case = {
                "index": index, "pid": pid, "gui": gui, "query": item["query_language"],
                "image": image.relative_to(HERE).as_posix(), "gt": annotation["bbox"],
                "image_size": annotation["image_size"], "groups": [],
            }
            if key in controls:
                control = controls[key]
                records = {
                    "full_json": full_json[key],
                    "full_tuple": comparison[pid, gui, "full_tuple"],
                    "phrase_json": phrase_json[key],
                    "phrase_tuple": comparison[pid, gui, "phrase_tuple"],
                }
                for record in records.values():
                    _check(record, control, annotation)
                _same_regeneration(comparison[pid, gui, "full_json"], records["full_json"])
                _same_regeneration(comparison[pid, gui, "phrase_json"], records["phrase_json"])
                case["groups"].append({
                    "title": "같은 언어 대조 · 전체 관계 질문", "question": control["question"],
                    "phrase": None, "runs": (records["full_json"], records["full_tuple"]),
                })
                case["groups"].append({
                    "title": "같은 언어 대조 · 짧은 기준 표현", "question": control["question"],
                    "phrase": _phrase(control["question"], descriptors[pid][gui]),
                    "runs": (records["phrase_json"], records["phrase_tuple"]),
                })
            for condition in ("O", "R"):
                runs = (pilot_json[item["pair_id"], condition],
                        pilot_tuple[item["pair_id"], condition])
                question = item[f"question_{condition}"]
                for record in runs:
                    _check(record, item, annotation)
                    assert record["condition"] == condition
                assert runs[0]["image_grid_thw"] == runs[1]["image_grid_thw"]
                case["groups"].append({
                    "title": f"{condition} · 짧은 기준 표현", "question": question,
                    "phrase": _phrase(question, descriptors[pid][item["query_language"]]),
                    "runs": runs,
                })
            cases[gui].append(case)
    assert sum(len(case["groups"]) * 2 for group in cases.values() for case in group) == 224
    return pilot_ids, cases


def _inline(value: str) -> str:
    ticks = max((len(match.group()) for match in re.finditer(r"`+", value)), default=0) + 1
    fence = "`" * ticks
    return f"{fence} {value} {fence}" if ticks > 1 else f"`{value}`"


def _block(value: str) -> str:
    ticks = max(3, max((len(match.group()) for match in re.finditer(r"`+", value)), default=0) + 1)
    fence = "`" * ticks
    return f"{fence}text\n{value}\n{fence}"


def _verdict(record: dict) -> str:
    if not record["valid_output"]:
        return "형식 실패"
    return "GT 안" if record["point_in_gt_box"] else "GT 밖"


def _point(record: dict) -> str:
    point = record["parsed_point_model_pixels"]
    return "—" if point is None else f"({point[0]}, {point[1]})"


def _case_lines(case: dict) -> list[str]:
    gui = case["gui"].upper()
    pid = Path(case["pid"]).stem
    lines = [
        f"## {case['index']:02d} {pid} {gui} GUI", "",
        f"질문 {case['query'].upper()}→GUI {gui} · 문항 {_inline(case['pid'])}", "",
        f"![{pid} {gui} 화면 및 GT bbox]({case['image']})", "",
        f"GT 원본 bbox: {_inline(str(case['gt']))} · 원본 화면 "
        f"{case['image_size'][0]}×{case['image_size'][1]}px", "",
    ]
    for group in case["groups"]:
        first = group["runs"][0]
        grid = first["image_grid_thw"]
        width, height = grid[2] * 14, grid[1] * 14
        assert all(record["image_grid_thw"] == grid for record in group["runs"])
        lines += [f"### {group['title']}", "",
                  f"질문: {_inline(group['question'])}", ""]
        if group["phrase"] is not None:
            lines += [f"모델에 준 기준 표현: {_inline(group['phrase'])}", ""]
        lines += [f"모델 입력 화면: {width}×{height}px. 아래 점은 이 화면의 픽셀 좌표다.", "",
                  "| 출력 | 판정 | 점 | 토큰 | `addCriterion` |",
                  "| --- | --- | --- | ---: | ---: |"]
        for label, record in zip(("JSON", "(x, y)"), group["runs"], strict=True):
            lines.append(f"| {label} | {_verdict(record)} | {_point(record)} | "
                         f"{record['output_tokens']} | {record['raw_output'].count('addCriterion')} |")
        lines.append("")
        for label, record in zip(("JSON", "(x, y)"), group["runs"], strict=True):
            lines += [f"**{label} 원시 출력 전문**", "", _block(record["raw_output"]), ""]
        for label, record in zip(("JSON", "(x, y)"), group["runs"], strict=True):
            lines += [f"**{label} 실제 렌더링 프롬프트**", "",
                      _block(record["rendered_prompt"]), ""]
    return lines


def main() -> None:
    pilot_ids, cases = load_cases()
    for gui in GUI_ORDER:
        runs = [record for case in cases[gui] for group in case["groups"]
                for record in group["runs"]]
        lines = [
            f"# Qwen 위치 지정 원시 출력 · {gui.upper()} GUI", "",
            "[전체 요약과 `addCriterion` 점검](QWEN_RAW_OUTPUT_AUDIT_KO.md) · "
            "[JSON↔괄호 결과](QWEN_FORMAT_COMPARISON_RESULTS_KO.md)", "",
            f"{len(cases[gui])}개 화면, {len(runs)}개 응답의 **원문 전체**를 기록했다. "
            f"`addCriterion` 포함 응답은 {sum('addCriterion' in r['raw_output'] for r in runs)}개다. "
            "같은 언어 대조는 첫 두 문항에만 있다.", "",
            "이미지의 **빨간 bbox는 GT**, 파란 원·초록 X는 짧은 표현 JSON O/R 예측, "
            "주황 마름모는 v3 JSON 대조의 예측이다. 괄호형 예측점은 이미지에 그려져 "
            "있지 않으며 아래 표에서 확인한다. 이미지는 보기용이고 채점은 원본 이미지로 했다.", "",
            "| # | 문항 | 질문 방향 | `addCriterion` 응답 |",
            "| ---: | --- | --- | ---: |",
        ]
        for case in cases[gui]:
            pid = Path(case["pid"]).stem
            anchor = f"#{case['index']:02d}-{pid.lower()}-{gui}-gui"
            count = sum("addCriterion" in record["raw_output"]
                        for group in case["groups"] for record in group["runs"])
            lines.append(f"| {case['index']:02d} | [{pid}]({anchor}) | "
                         f"{case['query'].upper()}→{gui.upper()} | {count} |")
        lines.append("")
        for case in cases[gui]:
            lines.extend(_case_lines(case))
        output = HERE / f"QWEN_RAW_OUTPUT_{gui.upper()}_KO.md"
        output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        print(f"Wrote {output.relative_to(REPO)}: {len(runs)} full raw outputs")


if __name__ == "__main__":
    main()
