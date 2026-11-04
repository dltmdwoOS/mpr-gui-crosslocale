"""Build the audited Qwen pilot gallery from locked inputs and saved responses."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw

from point_format import score_qwen_point


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
INPUT_DIR = REPO / "followup_rel_4lang/results/grounding_protocol_inputs_v3"
RESULTS = REPO / "followup_rel_4lang/results"
GT_PATH = HERE / "annotations_20261103/grounding_gt_draft_170.json"
DESCRIPTORS = HERE / "pilot_referent_phrases.json"
REPORT = HERE / "QWEN_PILOT_RESULTS_KO.md"
GALLERY_DIR = HERE / "qwen_pilot_gallery"
START = "<!-- QWEN_PILOT_GALLERY_START -->"
END = "<!-- QWEN_PILOT_GALLERY_END -->"
GUI_ORDER = ("en", "zh", "th", "ru")
NAMES = {"en": "EN", "zh": "ZH", "th": "TH", "ru": "RU"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def code(value: str) -> str:
    assert "`" not in value
    return f"`{value}`"


def fmt_num(value: float) -> str:
    return f"{value:g}"


def fmt_box(box: list[float]) -> str:
    return f"[{fmt_num(box[0])}, {fmt_num(box[1])}]–[{fmt_num(box[2])}, {fmt_num(box[3])}]"


def classify_invalid(raw: str) -> str:
    if "addCriterion" in raw:
        return "addCriterion 반복/혼입"
    if raw.strip() == "[]":
        return "빈 배열"
    if "```" in raw:
        return "코드 블록 또는 추가 텍스트"
    if "point_2d" in raw:
        return "불완전한 JSON"
    if raw.startswith("["):
        return "요청 형식이 아닌 숫자 배열"
    return "기타 형식 오류"


def result_label(record: dict) -> str:
    if record["valid_output"]:
        point = record["parsed_point_model_pixels"]
        verdict = "GT 안" if record["point_in_gt_box"] else "GT 밖"
        return f"{verdict} · {code(str(point))}"
    return f"파싱 실패 · {classify_invalid(record['raw_output'])}"


def phrase(question: str, descriptor_template: str) -> str:
    match = re.search(r"<ref>[^<>]+</ref>", question)
    assert match and question.count("<ref>") == question.count("</ref>") == 1
    assert descriptor_template.count("{ref}") == 1
    text = descriptor_template.format(ref=match.group(0))
    assert text in question
    return text


def verify_record(record: dict, row: dict, gt: dict) -> None:
    assert record["parallel_id"] == row["parallel_id"]
    assert record["gui_language"] == row["gui_language"]
    assert record["image_path"] == row["image_path"]
    assert record["image_sha256"] == row["image_sha256"] == gt["image_sha256"]
    width, height = record["original_image_size"]
    assert [width, height] == gt["image_size"]
    grid = record["image_grid_thw"]
    model_width, model_height = grid[2] * 14, grid[1] * 14
    rescored = score_qwen_point(
        record["raw_output"], gt["bbox"], width, height, model_width, model_height,
    )
    for key in ("valid_output", "requested_format_adherent", "point_in_gt_box",
                "parsed_point_model_pixels", "point_original_pixels"):
        assert record[key] == rescored[key], (record["trial_id"], key)


def load_data() -> tuple[list[str], dict, dict, dict, dict, dict, dict]:
    lock = json.loads((HERE / "input_lock.json").read_text(encoding="utf-8"))
    assert lock["schema"] == "rel-grounding-protocol-inputs-v3"
    assert (INPUT_DIR / "input_lock.json").read_bytes() == (HERE / "input_lock.json").read_bytes()
    for name, expected in lock["generated_sha256"].items():
        assert sha256(INPUT_DIR / name) == expected, name

    package = json.loads(GT_PATH.read_text(encoding="utf-8"))
    gt = package["annotations"]
    pilot_ids = package["gt_assembly"]["pilot_item_ids"]
    assert len(pilot_ids) == 12 and len(set(pilot_ids)) == 12
    controls_first = ("rel::1/booking_1.jpg", "rel::5/message_1.jpg")
    assert set(controls_first) <= set(pilot_ids)
    pilot_ids = list(controls_first) + sorted(set(pilot_ids) - set(controls_first))
    pairs = {
        (row["parallel_id"], row["gui_language"]): row
        for row in jsonl(INPUT_DIR / "grounding_pairs.jsonl") if row["split"] == "pilot"
    }
    assert len(pairs) == 48 and {pid for pid, _ in pairs} == set(pilot_ids)
    controls = {
        (row["parallel_id"], row["gui_language"]): row
        for row in jsonl(INPUT_DIR / "positive_controls.jsonl")
    }
    assert len(controls) == 8
    descriptors = json.loads(DESCRIPTORS.read_text(encoding="utf-8"))["descriptors"]
    assert set(descriptors) == set(pilot_ids)

    control_results = {}
    for version in ("v2", "v3", "phrase_v1"):
        folder = RESULTS / f"grounding_pilot_qwen_{version}"
        records = {
            (row["parallel_id"], row["gui_language"]): row
            for row in jsonl(folder / "controls.jsonl")
        }
        assert set(records) == set(controls)
        for key, record in records.items():
            verify_record(record, controls[key], gt[key[0]][key[1]])
        control_results[version] = records
    pilot_results = {
        (row["pair_id"], row["condition"]): row
        for row in jsonl(RESULTS / "grounding_pilot_qwen_phrase_v1/pilot.jsonl")
    }
    assert len(pilot_results) == 96
    for row in pairs.values():
        for condition in ("O", "R"):
            key = (row["pair_id"], condition)
            assert key in pilot_results
            verify_record(pilot_results[key], row, gt[row["parallel_id"]][row["gui_language"]])
    return pilot_ids, pairs, controls, control_results, pilot_results, gt, descriptors


def annotate(image_path: Path, expected_hash: str, gt_box: list[float],
             o_record: dict, r_record: dict, v3_control: dict | None,
             output: Path) -> None:
    assert sha256(image_path) == expected_hash, image_path
    with Image.open(image_path) as loaded:
        image = loaded.convert("RGB")
    width, height = image.size
    assert 0 <= gt_box[0] < gt_box[2] <= width
    assert 0 <= gt_box[1] < gt_box[3] <= height
    draw = ImageDraw.Draw(image, "RGBA")
    line_width = max(4, round(min(width, height) / 180))
    draw.rectangle(gt_box, fill=(255, 46, 81, 20), outline=(240, 28, 65, 255),
                   width=line_width)
    radius = max(8, round(min(width, height) / 105))
    o = o_record["point_original_pixels"]
    if o is not None:
        x, y = o
        draw.ellipse((x-radius-2, y-radius-2, x+radius+2, y+radius+2),
                     outline=(255, 255, 255, 255), width=radius // 2 + 3)
        draw.ellipse((x-radius, y-radius, x+radius, y+radius),
                     outline=(0, 165, 245, 255), width=radius // 2)
    r = r_record["point_original_pixels"]
    if r is not None:
        x, y = r
        draw.line((x-radius, y-radius, x+radius, y+radius),
                  fill=(255, 255, 255, 255), width=radius // 2 + 4)
        draw.line((x-radius, y+radius, x+radius, y-radius),
                  fill=(255, 255, 255, 255), width=radius // 2 + 4)
        draw.line((x-radius, y-radius, x+radius, y+radius),
                  fill=(26, 194, 96, 255), width=radius // 2)
        draw.line((x-radius, y+radius, x+radius, y-radius),
                  fill=(26, 194, 96, 255), width=radius // 2)
    if v3_control is not None and v3_control["point_original_pixels"] is not None:
        x, y = v3_control["point_original_pixels"]
        diamond = [(x, y-radius), (x+radius, y), (x, y+radius), (x-radius, y)]
        draw.polygon(diamond, fill=(255, 153, 0, 255))
        draw.line(diamond + [diamond[0]], fill=(255, 255, 255, 255), width=3)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "WEBP", quality=84, method=5)


def build_gallery() -> str:
    pilot_ids, pairs, controls, control_results, pilot_results, gt, descriptors = load_data()
    lines = [
        START,
        "## 파일럿 갤러리: 12문항 × 4 GUI 언어",
        "",
        "각 이미지는 **원본 화면 전체**에 채점용 GT bbox를 빨간 테두리로 표시했다. "
        "파란 원은 짧은 표현 진단의 유효한 O 점, 초록 X는 유효한 R 점이다. "
        "양성 대조군 8개 화면의 주황 마름모는 v3에서 파싱된 점이다. "
        "형식 오류로 점을 얻지 못한 경우에는 표시하지 않았다. "
        "점을 겹쳐 찍은 경우 초록 X가 파란 원 안에 보인다. "
        "이미지를 누르면 큰 크기로 열린다. GT 범위는 왼쪽 위 `(x1,y1)`부터 오른쪽 아래 `(x2,y2)`까지다.",
        "",
        "아래 작은 이미지는 48개 화면을 한눈에 보는 목록이다. 각 이미지를 누르면 확대되며, "
        "질문과 좌표 범위는 이어지는 문항별 상세 보기에서 확인할 수 있다.",
        "",
        "| 문항 | EN GUI | ZH GUI | TH GUI | RU GUI | O/R 적중 · 유효 |",
        "| --- | --- | --- | --- | --- | ---: |",
    ]
    for index, pid in enumerate(pilot_ids, 1):
        group = [pairs[pid, gui] for gui in GUI_ORDER]
        records = [pilot_results[row["pair_id"], condition]
                   for row in group for condition in ("O", "R")]
        o_hit = sum(r["point_in_gt_box"] for r in records if r["condition"] == "O")
        r_hit = sum(r["point_in_gt_box"] for r in records if r["condition"] == "R")
        valid = sum(r["valid_output"] for r in records)
        thumbnails = []
        for gui in GUI_ORDER:
            relative = f"qwen_pilot_gallery/pilot_{index:02d}_{gui}.webp"
            thumbnails.append(
                f'<a href="{relative}"><img src="{relative}" alt="{pid} {gui} GT" width="110"></a>'
            )
        lines.append(
            f"| {index:02d}. {code(pid)} | " + " | ".join(thumbnails) +
            f" | O {o_hit}/4 · R {r_hit}/4 · {valid}/8 |"
        )
    lines.append("")

    for index, pid in enumerate(pilot_ids, 1):
        group = [pairs[pid, gui] for gui in GUI_ORDER]
        records = [pilot_results[row["pair_id"], condition]
                   for row in group for condition in ("O", "R")]
        o_hit = sum(r["point_in_gt_box"] for r in records if r["condition"] == "O")
        r_hit = sum(r["point_in_gt_box"] for r in records if r["condition"] == "R")
        valid = sum(r["valid_output"] for r in records)
        lines += [
            f"<details{' open' if index == 1 else ''}>",
            f"<summary><strong>{index:02d}. {pid}</strong> · O {o_hit}/4, R {r_hit}/4 · 유효 {valid}/8 · 화면 4개</summary>",
            "",
        ]
        for gui in GUI_ORDER:
            row = pairs[pid, gui]
            annotation = gt[pid][gui]
            o = pilot_results[row["pair_id"], "O"]
            r = pilot_results[row["pair_id"], "R"]
            width, height = annotation["image_size"]
            model_width = o["image_grid_thw"][2] * 14
            model_height = o["image_grid_thw"][1] * 14
            assert r["image_grid_thw"] == o["image_grid_thw"]
            gt_box = annotation["bbox"]
            model_box = [gt_box[0] * model_width / width,
                         gt_box[1] * model_height / height,
                         gt_box[2] * model_width / width,
                         gt_box[3] * model_height / height]
            outfile = GALLERY_DIR / f"pilot_{index:02d}_{gui}.webp"
            annotate(
                REPO / row["image_path"], row["image_sha256"], gt_box, o, r,
                control_results["v3"].get((pid, gui)), outfile,
            )
            relative = outfile.relative_to(HERE).as_posix()
            descriptor = descriptors[pid][row["query_language"]]
            lines += [
                f"### {NAMES[gui]} GUI · {NAMES[row['query_language']]}→{NAMES[gui]} 질문",
                "",
                f'<a href="{relative}"><img src="{relative}" alt="{pid} {gui} GUI, GT bbox와 유효한 O/R 점" width="420"></a>',
                "",
                f"- **GT 원본:** {code(fmt_box(gt_box))} · 화면 {width}×{height}px",
                f"- **GT Qwen 좌표:** {code(fmt_box([round(v, 1) for v in model_box]))} · 입력 {model_width}×{model_height}px",
                f"- **O 질문:** {code(row['question_O'])}",
                f"- **R 질문:** {code(row['question_R'])}",
                f"- **진단용 짧은 표현:** O {code(phrase(row['question_O'], descriptor))} / R {code(phrase(row['question_R'], descriptor))}",
                f"- **짧은 표현 결과:** O {result_label(o)} / R {result_label(r)}",
            ]
            if (pid, gui) in controls:
                control = controls[pid, gui]
                lines += [
                    f"- **양성 대조 질문:** {code(control['question'])}",
                    "- **대조군 결과:** " + " / ".join(
                        f"{name} {result_label(control_results[version][pid, gui])}"
                        for version, name in (("v2", "v2"), ("v3", "v3"),
                                              ("phrase_v1", "짧은 표현"))
                    ),
                ]
            lines.append("")
        lines += ["</details>", ""]
    lines.append(END)
    return "\n".join(lines) + "\n"


def main() -> None:
    report = REPORT.read_text(encoding="utf-8")
    assert report.count(START) == report.count(END) == 1
    start = report.index(START)
    end = report.index(END) + len(END)
    updated = report[:start] + build_gallery().rstrip("\n") + report[end:]
    REPORT.write_text(updated, encoding="utf-8")
    print(f"Wrote {REPORT} and {len(list(GALLERY_DIR.glob('*.webp')))} gallery images")


if __name__ == "__main__":
    main()
