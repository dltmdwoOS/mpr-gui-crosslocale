# Stem-only GUI 추가 control

완료된 Hybrid GUI의 stem을 그대로 쓰고 A–D만 원본으로 되돌린다. **새 inventory 생성·referent 추출·번역은 없다.** Option-only 조건은 추가하지 않았다.

| 조건 | Question stem | A–D |
| --- | --- | --- |
| O | 원본 | 원본 |
| **TS_STEM_ONLY_GUI_AUTO** | 완료된 Hybrid의 선택적 정렬 결과 | 원본 |
| Hybrid GUI | 같은 선택적 정렬 결과 | Full GUI 번역 |
| Full GUI | Full GUI 번역 | 같은 Full GUI 번역 |

따라서 새 조건과 Hybrid의 차이는 options뿐이다. 새 조건과 O의 차이는 stem의 referent 치환뿐이다. 여기서 말하는 stem-only는 기존 `TS_SEL_GUI_AUTO`에서 options의 편집을 버리는 방식이 아니다. **Stem만 입력받은 extractor를 사용한 Hybrid의 stem**을 재사용한다. 원래 MCQ 전체를 매칭 문맥으로 제공했다는 사실은 유지한다.

## 범위와 검증

- Source: `artifacts/two_stage_v2_hybrid/screen/`의 완료된 GPU Hybrid GUI.
- 실행288쌍, primary main20개 item×12언어쌍=240쌍. 별도 legacy pilot48쌍은 주 분석에서 분리한다.
- 모든 pair ID·이미지 SHA·source/GUI 언어·보기 순서는 유지한다. Stem이 Hybrid와 같고 options가 원문과 같은지 검사한다.
- 원본에 저장된 stem edit만 적용하면 새 stem이 재현되는지 검사한다. Span 밖의 관계·부정 등 문맥이 바뀌면 중단한다.
- Hybrid에서 stem 추출/정렬이 실패한12개 main pair는 원문 stem으로 유지된다. 새 조건에서는 options도 원문이므로 해당 pair가 원문 O와 같아진다. 제외하지 않는다.
- 기존 실행 소스·산출물을 수정하지 않으며, source raw 파일·새 입력·실행기 hash를 별도 contract에 남긴다.

새 실험은 Screen을 본 뒤 추가한 개발 ablation이다. Semantic item 단위 반복 관측을 고려하며 최종 일반화 평가로 표현하지 않는다.

## 평가 설정과 프롬프트

새 변환 프롬프트는 없다. 준비된 stem을 필드 단위로 조합한다. 새 query를 푸는 VLM의 설정은 기존 Screen inference contract를 그대로 읽는다.

| 항목 | 설정 |
| --- | --- |
| 모델 | Qwen/Qwen3-VL-8B-Instruct |
| Revision | `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b` |
| 추론 | BF16, SDPA, greedy, beams1, max new tokens2 |
| 입력 | 최대4,096 tokens, truncation 없음 |
| 이미지 | fast processor, min262144 / max2097152 pixels, channels_last_3d |
| 배치 | 3, pair ID 정렬, 새 조건만 별도 batch block |
| Seed | 42 |
| Label scoring | true. Gold는 평가·scoring에만 사용하며 프롬프트에 넣지 않음 |

System:

```text
You are a GUI reasoning assistant. Inspect the GUI image and answer the multiple-choice question. Respond with exactly one label: A, B, C, or D.
```

User는 같은 screenshot과 다음 text다.

```text
{Hybrid의 stem} A: {원본 A} B: {원본 B} C: {원본 C} D: {원본 D}

Respond with exactly one label: A, B, C, or D.
```

기존 O·Hybrid·Full GUI·자동 Selective GUI 예측은 재사용하고 새 조건288건만 평가한다. Batch 구성원은 유지해도 options 길이와 padding은 달라지므로, 자기 질문이 O와 같은데 label이 바뀐 사례도 별도 집계한다.

주요 비교는 Stem-only−O와 Stem-only−Hybrid다. Full/Selective GUI도 참고 대비로 포함한다. 정답 수·GUI 언어별 정확도·회복/회귀와 semantic-item bootstrap10,000회95% CI를 저장한다. 다중 탐색 대비의 확증적 유의성을 주장하지 않는다.

## 실행

준비만(CPU, 기본값):

```bash
bash followup_rel_4lang/method_dev/scripts/run_stem_only_gui.sh
```

새 조건의 downstream 평가 실행:

```bash
bash followup_rel_4lang/method_dev/scripts/run_stem_only_gui.sh --run
```

출력: `artifacts/stem_only_gui_screen_v1/`. 중단 후 같은 명령으로 재개한다. 완료 attempt를 재사용하고, 미완료 attempt는 보존한 채 새 attempt를 시작한다. 변환 재생성은 하지 않는다. GPU lock은 기존 pipeline과 공유하며 현재45GB MIG의 free40GiB를 요구한다.

CPU mock:

```bash
bash followup_rel_4lang/method_dev/scripts/run_stem_only_gui.sh --run --mock
```

Mock과 실제 결과는 별도 경로로 저장한다. 실제 실행 후 `REPORT_KO.md`, `results.json`, `infer/attempt_*/predictions.jsonl`에서 확인한다. 준비 검증 기록은 [stem_only_gui_readiness.json](../artifacts/stem_only_gui_readiness.json)에 있다. 실제 GPU 평가가 완료됐다. Main240쌍에서175정답(72.92%), O 대비+5.42pp, Hybrid 대비−1.25pp다. CI와 같은 범위 R/F는 [누적 결과 보고서](TWO_STAGE_RESULTS_KO.md)에 반영했다. 준비 manifest는 준비 당시 기록으로 보존한다.
