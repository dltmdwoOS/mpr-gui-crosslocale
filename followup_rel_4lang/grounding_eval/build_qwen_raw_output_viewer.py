"""Build a self-contained data view of all saved Qwen grounding pilot text outputs.

The HTML embeds raw text and prompts but reuses the already tracked 48-image
pilot gallery. It performs no model inference and does not change scores.
"""

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
OUTPUT = HERE / "QWEN_RAW_OUTPUT_VIEWER.html"
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


def _run(record: dict, label: str) -> dict:
    return {
        "label": label,
        "raw": record["raw_output"],
        "prompt": record["rendered_prompt"],
        "valid": record["valid_output"],
        "hit": record["point_in_gt_box"],
        "point_model": record["parsed_point_model_pixels"],
        "point_original": record["point_original_pixels"],
        "tokens": record["output_tokens"],
        "add_count": record["raw_output"].count("addCriterion"),
    }


def _check(record: dict, item: dict) -> None:
    assert record["parallel_id"] == item["parallel_id"]
    assert record["gui_language"] == item["gui_language"]
    assert record["image_path"] == item["image_path"]
    assert record["image_sha256"] == item["image_sha256"]


def build_payload() -> dict:
    gt_package = json.loads(GT_PATH.read_text(encoding="utf-8"))
    gt = gt_package["annotations"]
    pilot_ids = gt_package["gt_assembly"]["pilot_item_ids"]
    assert len(pilot_ids) == 12 and set(CONTROLS_FIRST) <= set(pilot_ids)
    pilot_ids = list(CONTROLS_FIRST) + sorted(set(pilot_ids) - set(CONTROLS_FIRST))
    gallery_index = {pid: i for i, pid in enumerate(pilot_ids, 1)}
    descriptors = json.loads(DESCRIPTORS.read_text(encoding="utf-8"))["descriptors"]

    controls = _by_key(INPUTS / "positive_controls.jsonl",
                       lambda row: (row["parallel_id"], row["gui_language"]))
    pairs = _by_key(INPUTS / "grounding_pairs.jsonl",
                    lambda row: row["pair_id"])
    pairs = {key: row for key, row in pairs.items() if row["split"] == "pilot"}
    assert len(controls) == 8 and len(pairs) == 48
    assert {row["parallel_id"] for row in pairs.values()} == set(pilot_ids)

    v2 = _by_key(RESULTS / "grounding_pilot_qwen_v2/controls.jsonl",
                 lambda row: (row["parallel_id"], row["gui_language"]))
    v3 = _by_key(RESULTS / "grounding_pilot_qwen_v3/controls.jsonl",
                 lambda row: (row["parallel_id"], row["gui_language"]))
    phrase_controls = _by_key(RESULTS / "grounding_pilot_qwen_phrase_v1/controls.jsonl",
                              lambda row: (row["parallel_id"], row["gui_language"]))
    comparison_controls = _by_key(RESULTS / "grounding_format_comparison_v1/controls.jsonl",
                                  lambda row: (row["parallel_id"], row["gui_language"], row["arm"]))
    pilot_json = _by_key(RESULTS / "grounding_pilot_qwen_phrase_v1/pilot.jsonl",
                         lambda row: (row["pair_id"], row["condition"]))
    pilot_tuple = _by_key(RESULTS / "grounding_format_comparison_v1/pilot_phrase_tuple.jsonl",
                          lambda row: (row["pair_id"], row["condition"]))
    assert len(v2) == len(v3) == len(phrase_controls) == 8
    assert len(comparison_controls) == 32
    assert len(pilot_json) == len(pilot_tuple) == 96

    output_controls = []
    for pid in CONTROLS_FIRST:
        for gui in GUI_ORDER:
            key = pid, gui
            item = controls[key]
            annotation = gt[pid][gui]
            assert annotation["image_sha256"] == item["image_sha256"]
            records = [
                ("v2 · 전체 질문 · JSON+label", v2[key]),
                ("v3 · 전체 질문 · JSON", v3[key]),
                ("v3 · 전체 질문 · (x, y)", comparison_controls[pid, gui, "full_tuple"]),
                ("짧은 표현 · JSON", phrase_controls[key]),
                ("짧은 표현 · (x, y)", comparison_controls[pid, gui, "phrase_tuple"]),
            ]
            for _, record in records:
                _check(record, item)
            assert comparison_controls[pid, gui, "full_json"]["raw_output"] == v3[key]["raw_output"]
            assert comparison_controls[pid, gui, "phrase_json"]["raw_output"] == phrase_controls[key]["raw_output"]
            path = HERE / f"qwen_pilot_gallery/pilot_{gallery_index[pid]:02d}_{gui}.webp"
            assert path.is_file()
            output_controls.append({
                "kind": "control", "id": f"control::{pid}::{gui}", "item": pid,
                "gui": gui, "query": gui, "condition": "same",
                "image": path.relative_to(HERE).as_posix(),
                "question": item["question"],
                "descriptor": _phrase(item["question"], descriptors[pid][gui]),
                "gt": annotation["bbox"], "image_size": annotation["image_size"],
                "runs": [_run(record, label) for label, record in records],
            })

    output_pilot = []
    for pid in pilot_ids:
        for gui in GUI_ORDER:
            item = next(row for row in pairs.values()
                        if row["parallel_id"] == pid and row["gui_language"] == gui)
            annotation = gt[pid][gui]
            assert annotation["image_sha256"] == item["image_sha256"]
            path = HERE / f"qwen_pilot_gallery/pilot_{gallery_index[pid]:02d}_{gui}.webp"
            assert path.is_file()
            outcomes = []
            for condition in ("O", "R"):
                records = [
                    ("JSON", pilot_json[item["pair_id"], condition]),
                    ("(x, y)", pilot_tuple[item["pair_id"], condition]),
                ]
                for _, record in records:
                    _check(record, item)
                    assert record["condition"] == condition
                question = item[f"question_{condition}"]
                outcomes.append({
                    "condition": condition,
                    "question": question,
                    "descriptor": _phrase(question, descriptors[pid][item["query_language"]]),
                    "runs": [_run(record, label) for label, record in records],
                })
            output_pilot.append({
                "kind": "pilot", "id": item["pair_id"], "item": pid,
                "gui": gui, "query": item["query_language"],
                "image": path.relative_to(HERE).as_posix(),
                "gt": annotation["bbox"], "image_size": annotation["image_size"],
                "outcomes": outcomes,
            })
    assert len(output_controls) == 8 and len(output_pilot) == 48
    return {"controls": output_controls, "pilot": output_pilot}


HTML = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Qwen 위치 지정 원시 출력</title>
<style>
:root { color-scheme: light; font: 15px/1.55 system-ui, sans-serif; background: #f5f7fa; color: #172033; }
* { box-sizing: border-box; }
body { margin: 0; }
header { background: #172d48; color: white; padding: 24px clamp(16px, 3vw, 44px); }
header h1 { margin: 0 0 6px; font-size: 1.7rem; }
header p { max-width: 1050px; margin: 4px 0; color: #e4ebf6; }
header a { color: #c2e2ff; }
main { max-width: 1500px; margin: auto; padding: 20px clamp(12px, 2vw, 28px) 70px; }
.note { background: #e8f3ff; border-left: 4px solid #2274af; padding: 12px 16px; border-radius: 6px; margin-bottom: 16px; }
.filters { position: sticky; top: 0; z-index: 4; display: flex; flex-wrap: wrap; align-items: end; gap: 10px; padding: 12px; background: #fff; border: 1px solid #d9e1ec; border-radius: 10px; box-shadow: 0 4px 15px #172d4815; margin-bottom: 14px; }
label { display: grid; gap: 3px; font-weight: 600; color: #34445c; font-size: .84rem; }
select, input, button { font: inherit; border: 1px solid #a9b8cc; border-radius: 6px; background: white; color: #172033; padding: 7px 10px; }
input { min-width: 210px; flex: 1; }
button { cursor: pointer; background: #f3f7fb; }
.count { margin: 4px 0 14px; color: #43536b; }
.case { background: white; border: 1px solid #d9e1ec; border-radius: 10px; margin-bottom: 12px; overflow: hidden; }
.case > summary { cursor: pointer; padding: 13px 16px; font-weight: 650; list-style-position: inside; background: #fafdff; }
.case[open] > summary { border-bottom: 1px solid #d9e1ec; }
.case-body { padding: 14px 18px 19px; }
.meta { display: flex; gap: 16px; flex-wrap: wrap; align-items: start; margin-bottom: 12px; }
.meta img { width: min(300px, 100%); max-height: 290px; object-fit: contain; border: 1px solid #c7d2e1; background: #edf1f6; }
.meta a { display: block; }
.meta-text { flex: 1; min-width: 260px; }
.meta-text p { margin: 3px 0 9px; }
.minor { color: #5d6d81; font-size: .88rem; }
.question { white-space: pre-wrap; background: #f4f6f9; border-radius: 6px; padding: 8px 10px; overflow-wrap: anywhere; }
.group { margin-top: 16px; border-top: 1px solid #d9e1ec; padding-top: 10px; }
.group h3 { margin: 0 0 7px; }
.run-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(295px, 1fr)); gap: 10px; }
.run { min-width: 0; border: 1px solid #d9e1ec; border-radius: 7px; padding: 9px; background: #fcfdff; }
.run h4 { font-size: .95rem; margin: 0 0 6px; }
.badges { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 6px; }
.badge { display: inline-block; border-radius: 999px; padding: 2px 7px; font-size: .78rem; font-weight: 700; }
.hit { background: #e1f6ea; color: #106737; }
.miss { background: #fff1d7; color: #845200; }
.invalid { background: #fbe5e7; color: #a32131; }
.warn { background: #ede8ff; color: #5a2c94; }
pre { font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; background: #f2f4f8; margin: 6px 0; padding: 9px; border-radius: 5px; max-height: 300px; overflow: auto; }
pre.raw { background: #eff4fb; border-left: 3px solid #6488b8; }
mark { background: #ffe36c; color: #282400; border-radius: 2px; font-weight: bold; }
.prompt { margin-top: 6px; }
.prompt summary { cursor: pointer; color: #2d5b89; font-size: .85rem; }
.empty { text-align: center; padding: 28px; color: #66758a; }
@media (max-width: 650px) { .filters { position: static; } .run-grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<header>
  <h1>Qwen 기준 요소 위치 지정 · 원시 출력</h1>
  <p>v2·v3·짧은 표현 JSON·괄호형 비교를 같은 화면별로 확인합니다. 노란 강조는 모델이 실제로 출력한 <code>addCriterion</code>입니다. 원시 텍스트는 생략하지 않았습니다.</p>
  <p><a href="QWEN_FORMAT_COMPARISON_RESULTS_KO.md">결과 요약</a> · <a href="QWEN_PILOT_RESULTS_KO.md">기존 이미지 갤러리</a> · <a href="../results/grounding_format_comparison_v1/analysis.json">집계 JSON</a></p>
</header>
<main>
  <div class="note"><strong>‘대조군’은 F가 아닙니다.</strong> <code>booking_1</code>과 <code>message_1</code>의 네 GUI 언어별 한 화면씩, 총 8개의 <strong>같은 언어 위치 지정 기능 검사</strong>입니다. 질문 언어 = GUI 언어이고, A–D 답 대신 기준 요소의 점을 요청합니다. O/R/C/F 객관식 조건에는 넣지 않았습니다.</div>
  <div class="count" id="stats"></div>
  <div class="filters">
    <label>집합<select id="set"><option value="control">대조군 8화면 · 5개 출력</option><option value="pilot">O/R 파일럿 48쌍 · 4개 출력</option></select></label>
    <label>GUI 언어<select id="gui"><option value="all">전체</option><option value="en">EN</option><option value="zh">ZH</option><option value="th">TH</option><option value="ru">RU</option></select></label>
    <label>질문 언어<select id="query"><option value="all">전체</option><option value="en">EN</option><option value="zh">ZH</option><option value="th">TH</option><option value="ru">RU</option></select></label>
    <label>출력 필터<select id="issue"><option value="all">전체</option><option value="add">addCriterion 포함</option><option value="invalid">형식 실패 포함</option><option value="flip">JSON↔괄호 정오 변화</option></select></label>
    <label style="flex:1">검색<input id="search" placeholder="문항명·질문·원시 출력 검색"></label>
    <button id="expand" type="button">모두 펼치기</button><button id="collapse" type="button">모두 접기</button>
  </div>
  <div class="count" id="count"></div><div id="cases"></div>
  <p class="minor">화면 이미지는 기존 갤러리의 파생 이미지입니다. 빨간 bbox는 GT이고, 파란·초록·주황 점은 <strong>이전 JSON 실행</strong>의 표시입니다. 괄호형 점은 아래의 수치로 확인하세요. v2·v3의 O/R 파일럿은 실행되지 않았으므로 해당 집합에는 표시되지 않습니다.</p>
</main>
<script type="application/json" id="payload">__PAYLOAD__</script>
<script>
"use strict";
const data = JSON.parse(document.getElementById("payload").textContent);
const $ = id => document.getElementById(id);
const el = (tag, cls, value) => { const node = document.createElement(tag); if (cls) node.className = cls; if (value !== undefined) node.textContent = value; return node; };
function runsOf(item) { return item.kind === "control" ? item.runs : item.outcomes.flatMap(x => x.runs); }
const allRuns = [...data.controls, ...data.pilot].flatMap(runsOf);
$("stats").textContent = "원시 출력 " + allRuns.length + "개 · 대조군 " + data.controls.length + "화면 × 5개 · O/R " + data.pilot.length + "언어쌍 × 4개 · addCriterion 포함 " + allRuns.filter(r => r.add_count).length + "개";
function hasFlip(item) {
  if (item.kind === "control") {
    const map = Object.fromEntries(item.runs.map(r => [r.label, r]));
    return map["v3 · 전체 질문 · JSON"].hit !== map["v3 · 전체 질문 · (x, y)"].hit ||
           map["짧은 표현 · JSON"].hit !== map["짧은 표현 · (x, y)"].hit;
  }
  return item.outcomes.some(x => x.runs[0].hit !== x.runs[1].hit);
}
function matches(item) {
  if ($( "gui" ).value !== "all" && item.gui !== $("gui").value) return false;
  if ($( "query" ).value !== "all" && item.query !== $("query").value) return false;
  const issue = $("issue").value, runs = runsOf(item);
  if (issue === "add" && !runs.some(r => r.add_count)) return false;
  if (issue === "invalid" && !runs.some(r => !r.valid)) return false;
  if (issue === "flip" && !hasFlip(item)) return false;
  const q = $("search").value.trim().toLocaleLowerCase();
  if (q && !(item.id + " " + (item.question || "") + " " +
            (item.descriptor || "") + " " +
            (item.outcomes || []).map(x => x.question + " " + x.descriptor).join(" ") + " " +
            runs.map(r => r.raw).join(" ")).toLocaleLowerCase().includes(q)) return false;
  return true;
}
function rawPre(raw) {
  const pre = el("pre", "raw");
  raw.split(/(addCriterion)/g).forEach(part => {
    if (part === "addCriterion") pre.appendChild(el("mark", "", part));
    else pre.appendChild(document.createTextNode(part));
  });
  return pre;
}
function renderRun(run) {
  const node = el("section", "run");
  node.appendChild(el("h4", "", run.label));
  const badges = el("div", "badges");
  badges.appendChild(el("span", "badge " + (run.hit ? "hit" : run.valid ? "miss" : "invalid"),
    run.hit ? "GT 적중" : run.valid ? "유효·GT 밖" : "형식 실패"));
  badges.appendChild(el("span", "badge", run.tokens + " 토큰"));
  if (run.add_count) badges.appendChild(el("span", "badge warn", "addCriterion × " + run.add_count));
  node.appendChild(badges);
  if (run.point_model) node.appendChild(el("div", "minor", "모델 픽셀 " + JSON.stringify(run.point_model) + " · 원본 " + JSON.stringify(run.point_original)));
  node.appendChild(rawPre(run.raw));
  const prompt = el("details", "prompt"); prompt.appendChild(el("summary", "", "실제 렌더링 프롬프트"));
  prompt.appendChild(el("pre", "", run.prompt)); node.appendChild(prompt);
  return node;
}
function renderCase(item, index) {
  const node = el("details", "case"); node.open = index === 0;
  const head = item.kind === "control" ? "대조군" : "O/R";
  const add = runsOf(item).reduce((n,r) => n + Number(r.add_count > 0), 0);
  node.appendChild(el("summary", "", head + " · " + item.item + " · 질문 " + item.query.toUpperCase() + " → GUI " + item.gui.toUpperCase() + (add ? " · addCriterion 출력 " + add + "개" : "")));
  const body = el("div", "case-body"), meta = el("div", "meta");
  const link = el("a"); link.href = item.image; link.target = "_blank";
  const image = el("img"); image.src = item.image; image.alt = item.item + " " + item.gui + " GUI 및 GT bbox";
  link.appendChild(image); meta.appendChild(link);
  const info = el("div", "meta-text");
  info.appendChild(el("p", "minor", "GT bbox(원본): " + JSON.stringify(item.gt) + " · 화면 " + item.image_size[0] + "×" + item.image_size[1] + "px"));
  if (item.kind === "control") {
    info.appendChild(el("div", "question", "질문: " + item.question));
    info.appendChild(el("p", "minor", "짧은 기준 표현: " + item.descriptor));
  } else {
    info.appendChild(el("p", "minor", "O/R은 같은 GUI 화면에 source 언어 질문을 제시하고 <ref> 안 기준 표현만 바꿉니다."));
  }
  meta.appendChild(info); body.appendChild(meta);
  if (item.kind === "control") {
    const grid = el("div", "run-grid"); item.runs.forEach(r => grid.appendChild(renderRun(r))); body.appendChild(grid);
  } else {
    item.outcomes.forEach(outcome => {
      const group = el("section", "group"); group.appendChild(el("h3", "", outcome.condition + " 조건"));
      group.appendChild(el("div", "question", outcome.question));
      group.appendChild(el("p", "minor", "실제로 위치 지정에 준 짧은 표현: " + outcome.descriptor));
      const grid = el("div", "run-grid"); outcome.runs.forEach(r => grid.appendChild(renderRun(r)));
      group.appendChild(grid); body.appendChild(group);
    });
  }
  node.appendChild(body); return node;
}
function render() {
  const items = data[$("set").value].filter(matches), host = $("cases"); host.replaceChildren();
  $("count").textContent = items.length + "개 화면/언어쌍 표시 · 클릭하면 모든 원시 출력과 프롬프트가 열립니다.";
  if (!items.length) host.appendChild(el("p", "empty", "일치하는 결과가 없습니다."));
  items.forEach((item,index) => host.appendChild(renderCase(item,index)));
}
["set","gui","query","issue","search"].forEach(id => $(id).addEventListener(id === "search" ? "input" : "change", render));
$("expand").addEventListener("click", () => document.querySelectorAll("details.case").forEach(x => x.open = true));
$("collapse").addEventListener("click", () => document.querySelectorAll("details.case").forEach(x => x.open = false));
render();
</script>
</body>
</html>
"""


def main() -> None:
    payload = build_payload()
    assert HTML.count("__PAYLOAD__") == 1
    embedded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    OUTPUT.write_text(HTML.replace("__PAYLOAD__", embedded), encoding="utf-8")
    print(f"Built {OUTPUT.relative_to(REPO)}: {len(payload['controls'])} controls, "
          f"{len(payload['pilot'])} paired GUI screens, {OUTPUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
