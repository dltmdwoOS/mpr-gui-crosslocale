# Qwen 위치 지정 원시 출력과 `addCriterion` 점검

점검일: 2026-11-04. **v3와 그 후속 형식 비교의 응답 224개**를 아래 네 Markdown 파일에 원문 그대로 모았다. 같은 입력을 재생성해 이전 기록과 텍스트가 일치한 16개는 중복해서 싣지 않았다. 이미지·질문·기준 표현·GT bbox·형식 판정·좌표·출력 토큰 수·실제 렌더링 프롬프트를 응답과 함께 볼 수 있다.

| GUI 언어 | 원시 응답 | `addCriterion` 포함 | 상세 |
| --- | ---: | ---: | --- |
| EN | 56 | 23 | [EN 화면과 출력](QWEN_RAW_OUTPUT_EN_KO.md) |
| ZH | 56 | 22 | [ZH 화면과 출력](QWEN_RAW_OUTPUT_ZH_KO.md) |
| TH | 56 | 20 | [TH 화면과 출력](QWEN_RAW_OUTPUT_TH_KO.md) |
| RU | 56 | 19 | [RU 화면과 출력](QWEN_RAW_OUTPUT_RU_KO.md) |

각 상세 파일은 **12문항 목차 → 화면별 이미지와 GT → 대조군(해당 시) → O·R** 순서다. 코드 블록의 원시 출력은 길거나 반복되어도 자르지 않았다. 문항이나 `addCriterion`을 찾으려면 Markdown 뷰어의 검색을 쓰면 된다. 이미지는 기존 보기용 파생 이미지로, 빨간 bbox가 GT다. 파란 원·초록 X는 짧은 표현 JSON의 O/R 예측이고 주황 마름모는 v3 JSON 대조의 예측이다. 괄호형 점은 이미지에 그려져 있지 않다.

## ‘대조군’은 F 조건인가?

**아니다.** 여기서 양성 대조군은 `booking_1`과 `message_1`을 EN/ZH/TH/RU 화면에서 하나씩 시험한 **8개 같은 언어 위치 지정 검사**다. 질문 언어와 GUI 언어가 같고, 모델은 `<ref>`가 가리키는 요소의 점을 낸다. 결과의 `condition` 값도 `same`이다.

|  | 양성 대조군 | 이전 ORCF의 F |
| --- | --- | --- |
| 질문과 화면 | 질문 언어 = GUI 언어 | 서로 다른 source→GUI 쌍에서 문맥과 기준 표현을 GUI 언어로 현지화 |
| 응답 | 기준 요소의 점 | A–D 객관식 REL 정답 |
| 목적 | 위치 지정이 작동하는지 확인 | O/R/C/F 성능 비교 |

두 조건은 언어 배치가 닮아 보이지만 과제와 응답 공간이 다르다. 대조군을 F의 정확도로 집계할 수 없다. 실제 O/R 위치 지정 파일럿은 source≠GUI의 48언어쌍에 두 조건을 각각 물은 96응답이다.

## 포함한 실행과 프롬프트

| 기준 요소 입력 | 출력 형식 | 대조군 | O/R | `addCriterion` 포함 |
| --- | --- | ---: | ---: | ---: |
| v3 전체 관계 질문 | JSON | 8 | 실행 안 함 | 0 |
| v3 전체 관계 질문 | `(x, y)` | 8 | 실행 안 함 | 2 |
| 짧은 기준 표현 | JSON | 8 | 96 | 대조 5 · O/R 41 |
| 짧은 기준 표현 | `(x, y)` | 8 | 96 | 대조 1 · O/R 35 |

모두 같은 Qwen2.5-VL-7B-Instruct 고정 revision, 스크린샷 1장, greedy 생성, 최대 64 새 토큰을 썼다. 명시적 system 메시지는 없고 Qwen chat template의 기본 `You are a helpful assistant.`가 들어간다. v3는 관계 질문 전체에서 `<ref>` 기준 요소를 찾도록 지시한다. 짧은 표현은 그 질문에서 기준 요소를 가리키는 부분만 추출한다. **각 입력 방식 안에서** JSON과 괄호형의 마지막 출력 지시만 바꿨다.

```text
JSON: Return only this JSON array: [{"point_2d": [x, y]}]. No explanation or code fence.
괄호: Return only one coordinate as (x, y). No explanation or code fence.
```

각 화면별 실제 질문과 짧은 표현은 상세 파일에 있다. 두 방식의 전체 지시문과 나머지 실행 조건은 [형식 비교 보고서](QWEN_FORMAT_COMPARISON_RESULTS_KO.md)에 기록했다. 점은 Qwen 입력 화면의 절대 픽셀 좌표로 파싱한 뒤 원본 화면으로 역변환해 GT bbox 안에 있는지 채점했다. 표의 **형식 실패**는 좌표가 없거나 요청한 단일 점 형식을 지키지 못한 경우다.

## `addCriterion`은 실제로 어떻게 나왔나?

`addCriterion`은 **모델 원시 출력에 들어 있는 문자열**이다. 파서나 보고서 생성기가 붙인 것이 아니다. 이번 224응답 중 **84개**에 나타났고, 대부분 좌표가 완성되기 전에 끼어들었다.

- 짧은 표현 **JSON O/R 96개** 중 41개에 나타났다. 첫 등장 위치는 첫 번째 수만 쓴 뒤 16개, 두 번째 수를 쓰다 만 뒤 25개였다. 30개는 두 번 이상 반복했고 29개는 64토큰 상한에 닿았다.
- 짧은 표현 **괄호 O/R 96개** 중 35개에 나타났다. 첫 등장 위치는 첫 번째 수 뒤 13개, 두 번째 수를 쓰다 만 뒤 21개, 첫 좌표를 완성하고 두 번째 쌍을 시작한 뒤 1개였다. 9개가 반복했고 7개가 64토큰 상한에 닿았다.
- 64토큰 상한 **이전에** 끝난 사례도 JSON O/R에 12개, 괄호 O/R에 28개였다. 긴 반복이나 토큰 상한만의 문제로 설명할 수 없다.
- 같은 대조 화면의 v3 전체 질문에서는 JSON 0개, 괄호형 2개였다. JSON 형식만을 원인으로 특정할 수 없다.

예를 들어 `booking_10`의 EN→ZH O 괄호 출력은 다음처럼 10토큰에서 끝났다. [ZH 상세](QWEN_RAW_OUTPUT_ZH_KO.md#03-booking_10-zh-gui)에서 이미지·질문·짝이 되는 JSON 출력까지 볼 수 있다.

```text
(67, 68
 addCriterion
```

`wallet_3`의 EN→ZH O 괄호 출력은 `(75, 304), (18` 뒤에 `addCriterion`이 반복된다. 첫 쌍이 GT에 들어가더라도 두 번째 좌표를 시작한 **무효 단일 점 출력**이다. 반대로 `music_7`의 ZH→TH R에서는 모델이 지시문을 되풀이하며 원점 `(0, 0)`을 적었다. 그 숫자쌍은 예측점이 아니다. 첫 숫자쌍을 무조건 추출하는 사후 파서는 두 사례를 잘못 채점할 수 있다.

`addCriterion`이 없는 실패도 있다. v3 JSON 대조에는 닫히지 않은 JSON, 짧은 표현 JSON O/R에는 점이 없는 `[]`, 괄호 O/R에는 불완전한 괄호와 `None`이 있다. 현재 출력만으로 `addCriterion`의 생성 원인을 특정할 수 없다.

## 재생성

[Markdown 생성 코드](build_qwen_raw_output_markdown.py)는 저장된 JSONL의 ID·이미지 해시·중복 재실행 일치를 확인한다. GPU 추론은 하지 않는다.

```bash
.venv/bin/python followup_rel_4lang/grounding_eval/build_qwen_raw_output_markdown.py
```
