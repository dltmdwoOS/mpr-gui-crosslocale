# Qwen 위치 지정 원시 출력: 읽는 법과 `addCriterion` 점검

점검일: 2026-11-04. [원시 출력 뷰어](QWEN_RAW_OUTPUT_VIEWER.html)에는 **중복 재실행을 제외한 232개 응답의 전문**을 화면·질문·GT bbox와 함께 넣었다. 상단에서 **대조군/O·R**, GUI·질문 언어, `addCriterion`, 형식 실패, JSON↔괄호 정오 변화를 골라 볼 수 있다. 각 결과의 **실제 렌더링 프롬프트**도 펼칠 수 있다. 이미지는 [기존 48장 갤러리](QWEN_PILOT_RESULTS_KO.md)의 GT 표시본을 사용한다. 이미지에 그려진 파란·초록·주황 점은 *이전 JSON 실행*의 표시이며, 새 괄호형 예측점은 뷰어의 수치로 읽는다.

## ‘대조군’은 F 조건인가?

**아니다.** 이 저장소에서 `positive_controls.jsonl`은 `booking_1`과 `message_1`을 EN/ZH/TH/RU **각 GUI 언어로 하나씩** 만든 8개 *같은 언어 위치 지정 기능 검사*다. 입력 생성 코드는 그 GUI 언어의 질문 문장과 화면을 함께 선택하고, 모델에 `<ref>` 기준 요소의 **점**을 요청한다. 결과의 `condition` 값도 `same`이다.

|  | 양성 대조군 8개 | 이전 ORCF의 F |
| --- | --- | --- |
| 질문과 화면 | 질문 언어 = GUI 언어 | 원래 서로 다른 source→GUI 쌍에서 질문 문맥과 기준 표현을 GUI 언어로 현지화 |
| 모델이 하는 일 | 기준 요소의 위치 `(x, y)` 또는 JSON 점 출력 | A–D 객관식 REL 정답 출력 |
| 쓰임 | 위치 출력·대상 지정이 작동하는지 먼저 확인 | O/R/C/F 성능 비교의 실험 조건 |

대조군은 표현과 문맥이 모두 GUI 언어라 **언어 배치만 보면 F와 닮았지만**, source와 GUI 언어가 원래부터 같고 과제·응답 공간도 다르다. F의 정확도나 O→F 전환으로 집계해서는 안 된다. 실제 O/R 위치 파일럿은 source≠GUI의 48쌍에 O와 R을 각각 물은 **96응답**이다.

## 뷰어에 포함된 실행

| 실행 | 원시 출력 수 | `addCriterion` 포함 | 비고 |
| --- | ---: | ---: | --- |
| v2 전체 질문 JSON+label 대조 | 8 | 1 | 새로운 위치 system을 쓴 과거 버전 |
| v3 전체 질문 JSON 대조 | 8 | 0 | v3 O/R은 게이트 실패로 미실행 |
| v3 전체 질문 괄호 대조 | 8 | 2 | 출력 문구만 바꾼 새 비교 |
| 짧은 표현 JSON 대조 | 8 | 5 | 이전 탐색 실행 |
| 짧은 표현 괄호 대조 | 8 | 1 | 출력 문구만 바꾼 새 비교 |
| 짧은 표현 JSON O/R | 96 | 41 | 기존 탐색 파일럿 |
| 짧은 표현 괄호 O/R | 96 | 35 | 새 형식 비교 파일럿 |

2026-11-04에 다시 생성한 v3 JSON 대조 8개와 짧은 표현 JSON 대조 8개는 이전 원시 텍스트와 **16/16 동일**해서 뷰어에서 중복 표시하지 않았다. 출력 문구만 바뀐 짝은 [분석 코드](analyze_qwen_format_comparison.py)에서 렌더링 프롬프트, 이미지 해시, 전처리 격자를 대조한다. [형식 비교 수치](QWEN_FORMAT_COMPARISON_RESULTS_KO.md)는 별도 보고서에 있다.

v1은 추론 전에 폐기되어 원시 출력이 없고, v2·v3의 O/R 파일럿도 양성 대조 게이트 실패로 실행되지 않았다.

## `addCriterion`은 실제로 어떻게 나타났나?

`addCriterion`은 **모델이 낸 원시 텍스트**에 나타난 문자열이다. JSON 파서나 결과 뷰어가 삽입한 단어가 아니다. 대부분 좌표가 완성되기 전에 끼어들어 그대로 끝나거나 반복된다.

- 짧은 표현 **JSON O/R 96개** 중 41개에 나타났다. 첫 등장 위치는 첫 번째 수만 쓴 뒤 16개, 두 번째 수를 쓰다 만 뒤 25개였다. 41개 중 30개는 `addCriterion`을 두 번 이상 반복했고, 29개는 64토큰 상한에 닿았다.
- 짧은 표현 **괄호 O/R 96개** 중 35개에 나타났다. 첫 등장 위치는 첫 번째 수 뒤 13개, 두 번째 수를 쓰다 만 뒤 21개, 한 쌍을 완성했지만 두 번째 쌍을 시작한 뒤 1개였다. 35개 중 9개가 반복했고 7개가 64토큰 상한에 닿았다. 따라서 괄호형에서는 반복이 줄었지만 문제가 없어지지 않았다.
- 같은 대조 8화면에서 **v3 JSON에는 0개**, 전체 질문 괄호에는 2개가 있었다. JSON이라는 형식만을 `addCriterion`의 원인으로 지목할 수 없다.

64토큰에 닿지 않고 끝난 `addCriterion` 사례도 JSON O/R에 **12개**, 괄호 O/R에 **28개** 있었다. 이들은 긴 반복만의 문제가 아니다.

다음은 실제 원문의 짧은 사례다. 긴 반복 출력의 **전문은 뷰어에서 해당 문항을 열어** 확인한다.

**괄호형, 좌표를 닫기 전 조기 종료** — `booking_10`, EN→ZH, O, 10토큰:

```text
(67, 68
 addCriterion
```

**JSON, 첫 좌표 뒤 반복** — `booking_1`, EN 화면 대조군, 64토큰 출력의 시작 부분:

```text
[{"point_2d": [49
 addCriterion

 addCriterion
```

**완성된 첫 좌표 뒤 추가 출력** — `wallet_3`, EN→ZH, O, 64토큰 출력의 시작 부분:

```text
(75, 304), (18
 addCriterion

 addCriterion
```

이 마지막 원문은 첫 `(75, 304)`가 GT 안에 들어가더라도 **두 번째 좌표를 시작한 뒤 망가진 출력**이다. 사전에 정한 단일 점 형식 파서는 실패로 센다. 사후에 첫 숫자쌍만 취하면 채점 규칙을 결과에 맞춰 바꾸게 된다.

괄호 파일럿의 무효 출력 44개 중 완성된 숫자 괄호 패턴이 *어디든* 검색되는 출력은 2개다. 위 `wallet_3`의 첫 쌍이 하나고, 다른 하나는 모델이 지시문을 되풀이하면서 원점 **`(0, 0)`**을 적은 `music_7` 사례다. 두 번째 것은 예측점으로 볼 수 없다. 숫자 두 개를 무조건 추출하는 느슨한 파서는 이런 사례를 잘못 채점한다.

`addCriterion`이 없는 오류도 있다. v3 JSON 대조에서는 12토큰 후 `'[{"point_2d": [679'`처럼 닫히지 않고 끝난 출력이 있었고, 괄호 O/R에서는 불완전한 괄호 8개와 `None` 1개가 있었다. JSON O/R에는 점이 없는 `[]`도 8개 있었다. `[]`는 JSON 문법이 맞아도 **요청한 위치가 없다**.

현재 관측으로는 `addCriterion`의 생성 원인을 특정할 수 없다. 토큰 상한에 닿지 않고 끝나는 경우도 있으므로 상한을 올리는 것만으로 해결된다고 가정하지 않는다. 출력 문제와 기준 요소를 잘못 찾는 문제는 분리해 판단해야 한다.

## 파일과 재생성

- [뷰어 생성 코드](build_qwen_raw_output_viewer.py)는 저장된 JSONL을 읽어 ID·이미지 해시를 검증한 뒤 HTML을 만든다. GPU 추론은 하지 않는다.
- 원시 파일: [v2 대조](../results/grounding_pilot_qwen_v2/controls.jsonl), [v3 대조](../results/grounding_pilot_qwen_v3/controls.jsonl), [짧은 표현 JSON 대조](../results/grounding_pilot_qwen_phrase_v1/controls.jsonl), [짧은 표현 JSON O/R](../results/grounding_pilot_qwen_phrase_v1/pilot.jsonl), [새 형식 대조](../results/grounding_format_comparison_v1/controls.jsonl), [괄호 O/R](../results/grounding_format_comparison_v1/pilot_phrase_tuple.jsonl).

```bash
.venv/bin/python followup_rel_4lang/grounding_eval/build_qwen_raw_output_viewer.py
```
