# Qwen 기준 요소 위치 지정 파일럿: Qwen2.5-VL과 Qwen3-VL

이 문서는 기존 MPR-GUI-Bench·REL의 **객관식 정답률**이 아니라, 후속으로 GUI의 *기준 요소*에 점을 찍게 한 파일럿을 정리한다. Qwen2.5-VL-7B-Instruct와 Qwen3-VL-8B-Instruct에서 실제로 실행한 결과만 포함한다. Grounding 본 분석과 기존 객관식 실험의 Qwen3 재실행은 아직 하지 않았다.

**핵심 관찰:** Qwen3는 0–1000 좌표를 요청한 이번 28응답에서 모두 유효한 점을 냈다. 같은 지시로 검사한 Qwen2.5의 16응답은 유효 점이 0개였다. 두 모델 모두 *관계 질문 전체*를 입력하면 기준 요소를 자주 놓쳤다. [부록](#부록-실행한-모든-개별-결과)에 중복 재실행 16건을 포함한 **284개 응답 원문과 판정**이 있다.

## 무엇을 시험했나

모델에 GUI 이미지 한 장을 주고 `<ref>...</ref>`가 가리키는 요소 안에 점 하나를 찍으라고 했다. **유효 점**은 요청한 좌표 형식·범위를 지킨 출력이고, **적중**은 점을 원본 화면으로 환산해 사람이 그린 정답 상자(GT bbox) 안에 넣은 경우다. 형식 실패도 오답으로 센다. `addCriterion`은 그 문자열이 **한 번 이상 나온 응답 수**다.

| 실험 | 모델 | 입력·표본 | 요청한 좌표 |
| --- | --- | --- | --- |
| 같은 언어 기능 검사 | Qwen2.5 | 2문항 × 4 GUI 언어 × 전체 질문/짧은 설명 × JSON/`(x, y)` = **32응답** | 모델 입력 화면의 절대 픽셀 |
| 언어 불일치 O/R | Qwen2.5 | 12문항 × 4 언어쌍 × O/R × 2형식 = **192응답** | 모델 입력 화면의 절대 픽셀 |
| 상대좌표 재검사 | Qwen2.5 | 같은 언어 8화면 × 전체 질문/짧은 설명 = **16응답** | 화면 전체의 0–1000 좌표 |
| 같은 언어 기능 검사 | Qwen3 | 같은 8화면 × 전체 질문/짧은 설명 = **16응답** | 화면 전체의 0–1000 좌표 |
| 언어 불일치 O/R/C | Qwen3 | 4문항 × 각 1개 언어쌍 × O/R/C = **12응답** | 화면 전체의 0–1000 좌표 |

**전체 질문**은 `booking_1`에서 “파란 `<ref>Search</ref>` 버튼의 위에 어떤 입력 칸이 있나?”처럼 관계의 *답 요소*를 묻는 문장까지 넣는다. **짧은 설명**은 `blue '<ref>Search</ref>' button`처럼 기준 요소를 가리키는 부분만 넣는다. 요소 이름 한 단어만 주는 설정은 아니다. 같은 언어 기능 검사는 `booking_1`·`message_1`의 EN/ZH/TH/RU 화면, 총 8화면이다.

Qwen2.5의 첫 위치 지정은 **전체 관계 질문·JSON 점 출력**으로 기능 검사를 했다. 그 뒤 짧은 설명을 따로 시험하고, 각 입력 방식 안에서 JSON `[{"point_2d": [x, y]}]`과 `(x, y)`를 비교했다. 두 출력 형식은 마지막 지시만 다르지만, **전체 질문과 짧은 설명은 앞부분 지시도 다르다.** 전체 질문·JSON은 기능 검사에서 정해 둔 기준에 미달해 **전체 질문 O/R 추론은 실행하지 않았다**. 아래 192개 O/R은 짧은 설명만 사용한 탐색 실행이다.

Qwen2.5 상대좌표 재검사와 Qwen3 같은 언어 검사는 **동일한 화면·기준 표현·user 메시지 텍스트**를 사용했다. 전체 질문과 짧은 설명 사이에서는 `{text}`만 바뀐다. Qwen3 O/R/C에도 같은 텍스트를 썼다.

```text
Locate the GUI reference element marked by <ref>...</ref> in the text below. Use surrounding words to identify it. Do not answer a relation question.
Text: {text}
Return only one point as (x, y), with integer x and y from 0 to 1000 relative to the full screenshot. (0, 0) is the top-left and (1000, 1000) is the bottom-right. No explanation or code fence.
```

모든 실행은 **BF16·SDPA·greedy·최대 64 새 토큰**, 동일한 이미지 픽셀 예산(262,144–2,097,152), 명시적 system 메시지 없음으로 설정했다. Qwen2.5 절대좌표는 배치 1·임시 shard 적재, Qwen2.5 상대좌표는 배치 1·`from_pretrained`; Qwen3 같은 언어는 배치 1, O/R/C는 **배치 3**·`from_pretrained`였다. 모델별 chat template과 이미지 처리 경로는 다르다.

## 같은 언어 8화면: 입력과 좌표 지시 비교

| 모델 | 좌표·출력 | 입력 | 유효 점 | GT 적중 | `addCriterion` |
| --- | --- | --- | ---: | ---: | ---: |
| Qwen2.5 | 절대 픽셀·JSON | 전체 질문 | 6/8 | **0/8** | 0/8 |
| Qwen2.5 | 절대 픽셀·JSON | 짧은 설명 | 3/8 | **3/8** | 5/8 |
| Qwen2.5 | 절대 픽셀·`(x, y)` | 전체 질문 | 6/8 | **1/8** | 2/8 |
| Qwen2.5 | 절대 픽셀·`(x, y)` | 짧은 설명 | 6/8 | **6/8** | 1/8 |
| Qwen2.5 | **0–1000**·`(x, y)` | 전체 질문 | **0/8** | 0/8 | 5/8 |
| Qwen2.5 | **0–1000**·`(x, y)` | 짧은 설명 | **0/8** | 0/8 | 2/8 |
| Qwen3 | **0–1000**·`(x, y)` | 전체 질문 | **8/8** | 0/8 | 0/8 |
| Qwen3 | **0–1000**·`(x, y)` | 짧은 설명 | **8/8** | **8/8** | 0/8 |

Qwen2.5 절대 픽셀·JSON 16응답은 형식 비교 때 **동일 입력으로 한 번 더 생성**했고 원문이 모두 일치했다. 위 표에는 각 조건을 한 번만 세고, 부록에는 최초·재실행을 모두 표시했다. 이 8화면은 **두 문항에서만** 나온다.

**이번 Qwen2.5 상대좌표 재검사**에서 완성된 `(x, y)` 5개도 모두 **y > 1000**이었다. 약속한 좌표 규칙에서는 0/16이 유효하다. 짧은 설명의 완성 좌표 3개를 *사후에* 모델 입력 이미지의 절대 픽셀로 읽으면 3개 모두 GT 안에 든다. 이는 정식 적중률이 아니며, 모델이 픽셀 좌표처럼 답했을 가능성을 점검한 값이다. 기존 절대좌표 실행과 프롬프트·적재 경로도 달라 **좌표계 하나의 효과**로 분리할 수 없다.

Qwen3는 전체 질문에서 **8/8 유효**했지만 GT 적중은 **0/8**이었다. 점이 모두 기준 요소 GT보다 위에 있어 관계 질문의 답 쪽을 찍었을 가능성이 있다. 답 요소의 GT가 없어 단정할 수는 없다. 짧은 설명에서는 **8/8 적중**했다.

## 언어 불일치 O/R/C: 짧은 설명만 사용

O는 **설명·기준 표현 모두 질문 언어**, R은 **설명은 질문 언어·기준 표현은 GUI 언어**, C는 **설명은 GUI 언어·기준 표현은 질문 언어**다. EN→ZH `booking_1`의 예시는 O=`blue '<ref>Search</ref>' button`, R=`blue '<ref>搜索</ref>' button`, C=`蓝色“<ref>Search</ref>”按钮`이다. 관계 질문 전체와 A–D 보기는 넣지 않았다.

**Qwen2.5**는 12문항의 EN→ZH, ZH→TH, TH→RU, RU→EN **48언어쌍 × O/R = 96입력**에 JSON과 괄호형을 각각 실행했다.

| 출력 | O 유효 / 적중 | R 유효 / 적중 | 전체 유효 / 적중 | `addCriterion` |
| --- | --- | --- | --- | ---: |
| JSON | 20/48 · 20/48 | 23/48 · 23/48 | **43/96 · 43/96** | 41/96 |
| `(x, y)` | 25/48 · 22/48 | 27/48 · 25/48 | **52/96 · 47/96** | 35/96 |

같은 96입력의 JSON→괄호 적중 변화는 **오답→정답 14건, 정답→오답 10건**이다. 두 형식 모두 출력 실패가 많았다. JSON에서 O↔R 정오가 달라진 **7쌍은 모두 한쪽의 형식 실패**가 끼어 있어, O/R 수치 차이를 기준 표현 번역의 위치 개선으로 해석할 수 없다.

**Qwen3**는 파일럿 12문항 중 앞의 **4문항에서 언어쌍을 하나씩** 선택했다. 4쌍 × O/R/C = 12응답이며 **F는 실행하지 않았다**.

| 조건 | 유효 점 | GT 적중 | `addCriterion` |
| --- | ---: | ---: | ---: |
| O | 4/4 | **3/4** | 0/4 |
| R | 4/4 | **4/4** | 0/4 |
| C | 4/4 | **3/4** | 0/4 |

ZH→TH `booking_10`에서 O·C는 `(0, 0)`으로 GT 밖, R은 `(247, 320)`으로 GT 안이었다. 나머지 3쌍은 세 조건 모두 적중했다. **4쌍만으로 R의 평균 이득을 주장할 수 없다.** `weather_3` GT는 화면의 약 28%를 차지해 적중을 정밀한 위치 지정으로 읽기도 어렵다. 이번 Qwen3 **전체 28응답은 유효한 점으로 정상 종료**했다.

## Qwen3 전환 판단의 범위

- **후속 Qwen 실험은 Qwen3 사용을 기준으로 준비한다.** 이번 위치 출력에서는 Qwen3가 상대좌표 형식을 28/28회 지켰고, Qwen2.5는 동일 user 지시의 16응답에서 0/16회 지켰다. 이 근거는 위치 지정 파일럿에 한정된다.
- Qwen3에서도 **전체 관계 질문의 대상 혼동**은 남았다. 기준 요소 위치 진단에는 짧은 설명을 쓰는 편이 이번 파일럿에서 잘 작동했다.
- Qwen3 O/R/C는 **4쌍의 탐색 결과**다. 기존 MPR-GUI-Bench 6×6·REL 객관식 결과는 여전히 Qwen2.5 실행 결과이며, Qwen3로 바꾸려면 그 과제를 별도로 실행·검증해야 한다. Qwen3 O/R/C의 생성 시간 중앙값은 **161초/배치 3**으로, 대규모 재실행 전 속도도 확인할 필요가 있다.

실행 조건·원본 근거: [Qwen2.5 절대좌표 상세](QWEN_FORMAT_COMPARISON_RESULTS_KO.md), [Qwen2.5 상대좌표 원시 결과](../results/grounding_pilot_qwen25_relative_controls/predictions.jsonl), [Qwen3 같은 언어 상세](QWEN3_PROMPT_PILOT_KO.md), [Qwen3 O/R/C 상세](QWEN3_ORC_ELEMENT_PILOT_KO.md).

<!-- ALL_RESULTS_START -->
## 부록: 실행한 모든 개별 결과

아래 표에는 이전에 버린 설정을 제외한 **284개 실제 응답**을 모두 넣었다. `✓ 적중`은 유효한 점이 GT 안, `× GT 밖`은 유효하지만 GT 밖, `무효`는 단일 점을 얻지 못한 경우다. 원시 출력의 `⏎`는 줄바꿈을 뜻한다. 줄바꿈 표시 외에 응답 원문은 줄이거나 고치지 않았다.

### Qwen2.5: 같은 언어 8화면 × 전체 질문·짧은 설명

JSON 최초 실행, 동일 입력 JSON 재실행, 괄호형 실행을 각각 표시한다. GT는 **원본 이미지 픽셀**, 출력 좌표는 **모델 입력 이미지 픽셀**이다. 직접 숫자를 비교하지 않고 원본 크기로 환산해 채점했다.

#### 전체 관계 질문

| 문항 | GUI | GT bbox (원본 px) | 모델 화면 | 최초 JSON | 재실행 JSON | `(x, y)` |
| --- | --- | --- | --- | --- | --- | --- |
| `rel::1/booking_1.jpg` | EN | `82,1396,1155,1569` | 980×2128 | × GT 밖 `[{"point_2d": [703, 1024]}]` | × GT 밖 `[{"point_2d": [703, 1024]}]` | × GT 밖 `(476, 1015)` |
| `rel::1/booking_1.jpg` | ZH | `76,1584,1146,1756` | 980×2128 | 무효 `[{"point_2d": [679` | 무효 `[{"point_2d": [679` | ✓ 적중 `(476, 1305)` |
| `rel::1/booking_1.jpg` | TH | `89,1597,1156,1755` | 980×2128 | × GT 밖 `[{"point_2d": [665, 1173]}]` | × GT 밖 `[{"point_2d": [665, 1173]}]` | × GT 밖 `(634, 1165)` |
| `rel::1/booking_1.jpg` | RU | `86,1550,1152,1728` | 980×2128 | × GT 밖 `[{"point_2d": [374, 1165]}]` | × GT 밖 `[{"point_2d": [374, 1165]}]` | × GT 밖 `(476, 1053)` |
| `rel::5/message_1.jpg` | EN | `71,1483,1000,1669` | 952×2128 | × GT 밖 `[{"point_2d": [476, 1173]}]` | × GT 밖 `[{"point_2d": [476, 1173]}]` | × GT 밖 `(163, 1204)` |
| `rel::5/message_1.jpg` | ZH | `71,1483,1000,1669` | 952×2128 | × GT 밖 `[{"point_2d": [476, 1234]}]` | × GT 밖 `[{"point_2d": [476, 1234]}]` | 무효 `(163, 129⏎ addCriterion` |
| `rel::5/message_1.jpg` | TH | `71,1483,1000,1669` | 952×2128 | 무효 `[{"point_2d": [463, 1378` | 무효 `[{"point_2d": [463, 1378` | 무효 `(476, 138⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` |
| `rel::5/message_1.jpg` | RU | `67,1490,1022,1749` | 952×2128 | × GT 밖 `[{"point_2d": [463, 1207]}]` | × GT 밖 `[{"point_2d": [463, 1207]}]` | × GT 밖 `(143, 1206)` |

#### 짧은 설명

| 문항 | GUI | GT bbox (원본 px) | 모델 화면 | 최초 JSON | 재실행 JSON | `(x, y)` |
| --- | --- | --- | --- | --- | --- | --- |
| `rel::1/booking_1.jpg` | EN | `82,1396,1155,1569` | 980×2128 | 무효 `[{"point_2d": [49⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `[{"point_2d": [49⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | ✓ 적중 `(435, 1160)` |
| `rel::1/booking_1.jpg` | ZH | `76,1584,1146,1756` | 980×2128 | 무효 `[{"point_2d": [48⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `[{"point_2d": [48⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | ✓ 적중 `(467, 1305)` |
| `rel::1/booking_1.jpg` | TH | `89,1597,1156,1755` | 980×2128 | ✓ 적중 `[{"point_2d": [476, 1315]}]` | ✓ 적중 `[{"point_2d": [476, 1315]}]` | ✓ 적중 `(435, 1316)` |
| `rel::1/booking_1.jpg` | RU | `86,1550,1152,1728` | 980×2128 | 무효 `[{"point_2d": [476, 128⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `[{"point_2d": [476, 128⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `(476, 128⏎⏎ addCriterion` |
| `rel::5/message_1.jpg` | EN | `71,1483,1000,1669` | 952×2128 | 무효 `[{"point_2d": [374, 138⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `[{"point_2d": [374, 138⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎ addCriterion` | ✓ 적중 `(163, 1407)` |
| `rel::5/message_1.jpg` | ZH | `71,1483,1000,1669` | 952×2128 | ✓ 적중 `[{"point_2d": [476, 1360]}]` | ✓ 적중 `[{"point_2d": [476, 1360]}]` | ✓ 적중 `(476, 1357)` |
| `rel::5/message_1.jpg` | TH | `71,1483,1000,1669` | 952×2128 | 무효 `[{"point_2d": [476, 139⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `[{"point_2d": [476, 139⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 ````(476, 139⏎⏎ 自动生成的代码如下所示：⏎```python⏎import cv2⏎import numpy as np⏎⏎# Load the image⏎image = cv2.imread('screenshot.png')⏎⏎# Convert the image to grayscale⏎gray = cv2.cvtColor(image, cv2.COLOR_BGR```` |
| `rel::5/message_1.jpg` | RU | `67,1490,1022,1749` | 952×2128 | ✓ 적중 `[{"point_2d": [374, 1406]}]` | ✓ 적중 `[{"point_2d": [374, 1406]}]` | ✓ 적중 `(163, 1427)` |

### Qwen2.5: 짧은 설명 O/R, 48언어쌍

각 행은 한 조건의 **JSON과 괄호형 응답 두 개**다. GT는 원본 픽셀, 출력은 모델 입력 픽셀이다.

#### EN GUI

| 문항 | 질문→GUI | 조건 | GT bbox (원본 px) | 모델 화면 | JSON | `(x, y)` |
| --- | --- | --- | --- | --- | --- | --- |
| `rel::1/booking_1.jpg` | RU→EN | O | `82,1396,1155,1569` | 980×2128 | 무효 `[]` | ✓ 적중 `(435, 1160)` |
| `rel::1/booking_1.jpg` | RU→EN | R | `82,1396,1155,1569` | 980×2128 | 무효 `[{"point_2d": [48⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `(467, 1159` |
| `rel::1/booking_10.jpg` | RU→EN | O | `66,887,516,971` | 980×2128 | ✓ 적중 `[{"point_2d": [236, 724]}]` | ✓ 적중 `(67, 715)` |
| `rel::1/booking_10.jpg` | RU→EN | R | `66,887,516,971` | 980×2128 | ✓ 적중 `[{"point_2d": [346, 725]}]` | ✓ 적중 `(156, 714)` |
| `rel::2/clock_10.png` | RU→EN | O | `1008,1776,1213,1882` | 1736×1204 | ✓ 적중 `[{"point_2d": [705, 1154]}]` | 무효 `(68⏎⏎ addCriterion: (69⏎ addCriterion:` |
| `rel::2/clock_10.png` | RU→EN | R | `1008,1776,1213,1882` | 1736×1204 | ✓ 적중 `[{"point_2d": [705, 1154]}]` | 무효 `(69⏎⏎ addCriterion 'вкладки '\''<ref>Alarm</ref>'\''' в нижней части экрана'` |
| `rel::2/weather_3.png` | RU→EN | O | `795,326,1948,1595` | 1736×1204 | 무효 `[{"point_2d": [9⏎ addCriterion` | 무효 `(8⏎ addCriterion⏎(9⏎ addCriterion⏎(` |
| `rel::2/weather_3.png` | RU→EN | R | `795,326,1948,1595` | 1736×1204 | 무효 `[{"point_2d": [9⏎ addCriterion` | 무효 ````(8⏎ addCriterion⏎```json⏎[9⏎ addCriterion⏎```json⏎1050,232,109⏎ addCriterion⏎``````` |
| `rel::3/music_7.jpg` | RU→EN | O | `28,933,317,1015` | 980×2100 | 무효 `[{"point_2d": [19⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `(145, 8⏎ addCriterion` |
| `rel::3/music_7.jpg` | RU→EN | R | `28,933,317,1015` | 980×2100 | 무효 `[{"point_2d": [19⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `(145, 8⏎ addCriterion` |
| `rel::3/settings_2.jpg` | RU→EN | O | `55,672,1022,817` | 980×2100 | ✓ 적중 `[{"point_2d": [435, 657]}]` | ✓ 적중 `(156, 654)` |
| `rel::3/settings_2.jpg` | RU→EN | R | `55,672,1022,817` | 980×2100 | ✓ 적중 `[{"point_2d": [456, 657]}]` | ✓ 적중 `(156, 654)` |
| `rel::4/Gmail_8.jpg` | RU→EN | O | `41,983,533,1136` | 952×2156 | 무효 `[{"point_2d": [476, 8⏎ addCriterion` | 무효 `(148⏎⏎ addCriterion), (317,` |
| `rel::4/Gmail_8.jpg` | RU→EN | R | `41,983,533,1136` | 952×2156 | 무효 `[{"point_2d": [473, 8⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | × GT 밖 `(134,8)` |
| `rel::4/twitter_6.jpg` | RU→EN | O | `9,647,843,918` | 868×1932 | 무효 `[{"point_2d": [457, 69⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎⏎ addCriterion` | 무효 `(174, 68⏎ addCriterion` |
| `rel::4/twitter_6.jpg` | RU→EN | R | `9,647,843,918` | 868×1932 | 무효 `[{"point_2d": [457, 69⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `(174, 68⏎ addCriterion` |
| `rel::5/camera_1.jpg` | RU→EN | O | `411,1732,640,1802` | 952×2128 | ✓ 적중 `[{"point_2d": [476, 1569]}]` | ✓ 적중 `(463, 1567)` |
| `rel::5/camera_1.jpg` | RU→EN | R | `411,1732,640,1802` | 952×2128 | ✓ 적중 `[{"point_2d": [476, 1569]}]` | ✓ 적중 `(473, 1566)` |
| `rel::5/message_1.jpg` | RU→EN | O | `71,1483,1000,1669` | 952×2128 | 무효 `[{"point_2d": [374, 138⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `(436, 138⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎⏎ addCriterion` |
| `rel::5/message_1.jpg` | RU→EN | R | `71,1483,1000,1669` | 952×2128 | 무효 `[{"point_2d": [374, 138⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎ addCriterion` | ✓ 적중 `(163, 1407)` |
| `rel::6/safari_7.jpg` | RU→EN | O | `71,804,1211,955` | 980×2100 | ✓ 적중 `[{"point_2d": [476, 673]}]` | ✓ 적중 `(163, 674)` |
| `rel::6/safari_7.jpg` | RU→EN | R | `71,804,1211,955` | 980×2100 | ✓ 적중 `[{"point_2d": [476, 673]}]` | ✓ 적중 `(163, 674)` |
| `rel::6/wallet_3.jpg` | RU→EN | O | `32,343,424,484` | 980×2100 | ✓ 적중 `[{"point_2d": [165, 314]}]` | ✓ 적중 `(103, 314)` |
| `rel::6/wallet_3.jpg` | RU→EN | R | `32,343,424,484` | 980×2100 | ✓ 적중 `[{"point_2d": [165, 314]}]` | ✓ 적중 `(134, 315)` |

#### ZH GUI

| 문항 | 질문→GUI | 조건 | GT bbox (원본 px) | 모델 화면 | JSON | `(x, y)` |
| --- | --- | --- | --- | --- | --- | --- |
| `rel::1/booking_1.jpg` | EN→ZH | O | `76,1584,1146,1756` | 980×2128 | 무효 `[{"point_2d": [48⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | ✓ 적중 `(437, 1305)` |
| `rel::1/booking_1.jpg` | EN→ZH | R | `76,1584,1146,1756` | 980×2128 | 무효 `[{"point_2d": [48⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | ✓ 적중 `(467, 1305)` |
| `rel::1/booking_10.jpg` | EN→ZH | O | `55,834,302,917` | 980×2128 | 무효 `[{"point_2d": [137, 68⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎ addCriterion⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎⏎ addCriterion` | 무효 `(67, 68⏎ addCriterion` |
| `rel::1/booking_10.jpg` | EN→ZH | R | `55,834,302,917` | 980×2128 | 무효 `[{"point_2d": [137, 68⏎ addCriterion` | 무효 `(67, 68⏎ addCriterion` |
| `rel::2/clock_10.png` | EN→ZH | O | `1008,1776,1213,1882` | 1736×1204 | ✓ 적중 `[{"point_2d": [705, 1154]}]` | 무효 `(69⏎⏎ addCriterion⏎(705, 1151` |
| `rel::2/clock_10.png` | EN→ZH | R | `1008,1776,1213,1882` | 1736×1204 | ✓ 적중 `[{"point_2d": [705, 1154]}]` | 무효 `(69` |
| `rel::2/weather_3.png` | EN→ZH | O | `795,326,1948,1595` | 1736×1204 | 무효 `[{"point_2d": [8⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `(8⏎ addCriterion⏎(8⏎ addCriterion⏎(` |
| `rel::2/weather_3.png` | EN→ZH | R | `795,326,1948,1595` | 1736×1204 | 무효 ``[{"point_2d": [8⏎⏎ addCriterion⏎⏎⏎ 自动生成的 JSON 格式数组 `[{"point_2d": [9⏎ addCriterion⏎⏎ 自动生成的 JSON 格式数组 `[{"point_2d": [`` | 무효 `(8⏎ addCriterion⏎(8⏎ !***` |
| `rel::3/music_7.jpg` | EN→ZH | O | `25,936,298,1025` | 980×2100 | 무효 `[{"point_2d": [176, 8⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `(173, 8⏎ addCriterion` |
| `rel::3/music_7.jpg` | EN→ZH | R | `25,936,298,1025` | 980×2100 | 무효 `[{"point_2d": [19⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `(170, 8⏎ addCriterion` |
| `rel::3/settings_2.jpg` | EN→ZH | O | `55,672,1022,817` | 980×2100 | ✓ 적중 `[{"point_2d": [463, 657]}]` | ✓ 적중 `(156, 673)` |
| `rel::3/settings_2.jpg` | EN→ZH | R | `55,672,1022,817` | 980×2100 | ✓ 적중 `[{"point_2d": [463, 657]}]` | ✓ 적중 `(134,657)` |
| `rel::4/Gmail_8.jpg` | EN→ZH | O | `45,990,438,1128` | 952×2156 | 무효 `[{"point_2d": [173, 8⏎ addCriterion` | × GT 밖 `(134,8)` |
| `rel::4/Gmail_8.jpg` | EN→ZH | R | `45,990,438,1128` | 952×2156 | 무효 `[{"point_2d": [478, 8⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | × GT 밖 `(134,8)` |
| `rel::4/twitter_6.jpg` | EN→ZH | O | `17,859,1199,1154` | 952×2156 | ✓ 적중 `[{"point_2d": [374, 742]}]` | 무효 `(378` |
| `rel::4/twitter_6.jpg` | EN→ZH | R | `17,859,1199,1154` | 952×2156 | ✓ 적중 `[{"point_2d": [374, 720]}]` | 무효 `(18⏎ addCriterion` |
| `rel::5/camera_1.jpg` | EN→ZH | O | `411,1732,640,1802` | 952×2128 | 무효 `[{"point_2d": [476, 1569]})` | ✓ 적중 `(467, 1563)` |
| `rel::5/camera_1.jpg` | EN→ZH | R | `411,1732,640,1802` | 952×2128 | ✓ 적중 `[{"point_2d": [476, 1569]}]` | ✓ 적중 `(467, 1563)` |
| `rel::5/message_1.jpg` | EN→ZH | O | `71,1483,1000,1669` | 952×2128 | ✓ 적중 `[{"point_2d": [476, 1360]}]` | ✓ 적중 `(476, 1357)` |
| `rel::5/message_1.jpg` | EN→ZH | R | `71,1483,1000,1669` | 952×2128 | ✓ 적중 `[{"point_2d": [346, 1360]}]` | ✓ 적중 `(163, 1354)` |
| `rel::6/safari_7.jpg` | EN→ZH | O | `71,804,1211,955` | 980×2100 | ✓ 적중 `[{"point_2d": [476, 673]}]` | ✓ 적중 `(156, 674)` |
| `rel::6/safari_7.jpg` | EN→ZH | R | `71,804,1211,955` | 980×2100 | 무효 `[{"point_2d": [49⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | ✓ 적중 `(134, 675)` |
| `rel::6/wallet_3.jpg` | EN→ZH | O | `32,343,424,484` | 980×2100 | ✓ 적중 `[{"point_2d": [113, 314]}]` | 무효 `(75, 304), (18⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` |
| `rel::6/wallet_3.jpg` | EN→ZH | R | `32,343,424,484` | 980×2100 | ✓ 적중 `[{"point_2d": [116, 314]}]` | ✓ 적중 `(64, 305)` |

#### TH GUI

| 문항 | 질문→GUI | 조건 | GT bbox (원본 px) | 모델 화면 | JSON | `(x, y)` |
| --- | --- | --- | --- | --- | --- | --- |
| `rel::1/booking_1.jpg` | ZH→TH | O | `89,1597,1156,1755` | 980×2128 | ✓ 적중 `[{"point_2d": [476, 1315]}]` | ✓ 적중 `(463, 1315)` |
| `rel::1/booking_1.jpg` | ZH→TH | R | `89,1597,1156,1755` | 980×2128 | ✓ 적중 `[{"point_2d": [476, 1315]}]` | ✓ 적중 `(436, 1315)` |
| `rel::1/booking_10.jpg` | ZH→TH | O | `77,850,559,921` | 980×2128 | 무효 ```````json⏎[{"point_2d": [364, 1750]}]⏎``````` | 무효 `None` |
| `rel::1/booking_10.jpg` | ZH→TH | R | `77,850,559,921` | 980×2128 | 무효 `[{"point_2d": [253, 68⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎ addCriterion⏎⏎ addCriterion⏎⏎⏎ addCriterion` | 무효 `(145, 68⏎ addCriterion` |
| `rel::2/clock_10.png` | ZH→TH | O | `893,1785,1134,1883` | 1736×1204 | ✓ 적중 `[{"point_2d": [658, 1159]}]` | 무효 `(59⏎ addCriterion` |
| `rel::2/clock_10.png` | ZH→TH | R | `893,1785,1134,1883` | 1736×1204 | ✓ 적중 `[{"point_2d": [658, 1151]}]` | ✓ 적중 `(658, 1153)` |
| `rel::2/weather_3.png` | ZH→TH | O | `795,326,1948,1595` | 1736×1204 | 무효 `[{"point_2d": [109⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `(118` |
| `rel::2/weather_3.png` | ZH→TH | R | `795,326,1948,1595` | 1736×1204 | 무효 `[{"point_2d": [9⏎ addCriterion` | 무효 `(1158, 209⏎⏎ addCriterion⏎⏎⏎��` |
| `rel::3/music_7.jpg` | ZH→TH | O | `28,936,377,1025` | 980×2100 | 무효 `[]` | × GT 밖 `(356, 1470)` |
| `rel::3/music_7.jpg` | ZH→TH | R | `28,936,377,1025` | 980×2100 | 무효 `[{"point_2d": [204, 8⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 ``(163, 8⏎ addCriterion中“<ref>เล่นซ้ำทั้งหมด</ref>”元素的位置信息如下：使用整数坐标（以像素为单位），左上角为原点 `(0, 0)`。在屏幕截图中查找并提供一个坐标`` |
| `rel::3/settings_2.jpg` | ZH→TH | O | `55,672,1022,817` | 980×2100 | 무효 `[]` | ✓ 적중 `(345, 670)` |
| `rel::3/settings_2.jpg` | ZH→TH | R | `55,672,1022,817` | 980×2100 | ✓ 적중 `[{"point_2d": [435, 667]}]` | ✓ 적중 `(153, 654)` |
| `rel::4/Gmail_8.jpg` | ZH→TH | O | `29,990,352,1136` | 952×2156 | 무효 `[{"point_2d": [143, 8⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `(73, 8⏎ addCriterion` |
| `rel::4/Gmail_8.jpg` | ZH→TH | R | `29,990,352,1136` | 952×2156 | 무효 `[{"point_2d": [148` | 무효 `(74, 8⏎ addCriterion` |
| `rel::4/twitter_6.jpg` | ZH→TH | O | `9,647,843,918` | 868×1932 | 무효 `[]` | × GT 밖 `(475, 1450)` |
| `rel::4/twitter_6.jpg` | ZH→TH | R | `9,647,843,918` | 868×1932 | ✓ 적중 `[{"point_2d": [457, 710]}]` | ✓ 적중 `(174, 705)` |
| `rel::5/camera_1.jpg` | ZH→TH | O | `411,1732,640,1802` | 952×2128 | 무효 `[{"point_2d": [674, 159⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `(647, 159⏎⏎ addCriterion⏎Locate this GUI` |
| `rel::5/camera_1.jpg` | ZH→TH | R | `411,1732,640,1802` | 952×2128 | 무효 `[{"point_2d": [476, 159⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | ✓ 적중 `(467, 1567)` |
| `rel::5/message_1.jpg` | ZH→TH | O | `71,1483,1000,1669` | 952×2128 | 무효 `[]` | 무효 `(476, 139⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎⏎ addCriterion` |
| `rel::5/message_1.jpg` | ZH→TH | R | `71,1483,1000,1669` | 952×2128 | 무효 `[{"point_2d": [476, 139⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `(476, 139⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` |
| `rel::6/safari_7.jpg` | ZH→TH | O | `71,804,1211,955` | 980×2100 | ✓ 적중 `[{"point_2d": [436, 675]}]` | ✓ 적중 `(163, 674)` |
| `rel::6/safari_7.jpg` | ZH→TH | R | `71,804,1211,955` | 980×2100 | 무효 `[]` | ✓ 적중 `(135, 674)` |
| `rel::6/wallet_3.jpg` | ZH→TH | O | `32,343,424,484` | 980×2100 | 무효 `[]` | 무효 `(134,29⏎ addCriterion` |
| `rel::6/wallet_3.jpg` | ZH→TH | R | `32,343,424,484` | 980×2100 | ✓ 적중 `[{"point_2d": [163, 324]}]` | ✓ 적중 `(103, 314)` |

#### RU GUI

| 문항 | 질문→GUI | 조건 | GT bbox (원본 px) | 모델 화면 | JSON | `(x, y)` |
| --- | --- | --- | --- | --- | --- | --- |
| `rel::1/booking_1.jpg` | TH→RU | O | `86,1550,1152,1728` | 980×2128 | 무효 `[{"point_2d": [476, 128⏎ addCriterion` | ✓ 적중 `(463, 1275)` |
| `rel::1/booking_1.jpg` | TH→RU | R | `86,1550,1152,1728` | 980×2128 | 무효 `[{"point_2d": [476, 128⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎⏎ addCriterion` | ✓ 적중 `(467, 1275)` |
| `rel::1/booking_10.jpg` | TH→RU | O | `71,952,644,1043` | 980×2128 | 무효 `[{"point_2d": [304, 78⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | ✓ 적중 `(67, 774)` |
| `rel::1/booking_10.jpg` | TH→RU | R | `71,952,644,1043` | 980×2128 | 무효 `[{"point_2d": [304, 78⏎ addCriterion` | 무효 `(54, 768` |
| `rel::2/clock_10.png` | TH→RU | O | `1008,1776,1213,1882` | 1736×1204 | 무효 `[{"point_2d": [708⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | ✓ 적중 `(705, 1153)` |
| `rel::2/clock_10.png` | TH→RU | R | `1008,1776,1213,1882` | 1736×1204 | 무효 `[{"point_2d": [708` | 무효 `(708, 1151` |
| `rel::2/weather_3.png` | TH→RU | O | `795,326,1948,1595` | 1736×1204 | 무효 `[{"point_2d": [8⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `(8⏎ addCriterion⏎(159` |
| `rel::2/weather_3.png` | TH→RU | R | `795,326,1948,1595` | 1736×1204 | 무효 `[{"point_2d": [8⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `(8⏎ addCriterion⏎(9⏎ addCriterion⏎(` |
| `rel::3/music_7.jpg` | TH→RU | O | `25,926,416,1025` | 980×2100 | 무효 `[{"point_2d": [304, 8⏎ addCriterion: "เล่นซ` | 무효 `(146, 8⏎ addCriterion` |
| `rel::3/music_7.jpg` | TH→RU | R | `25,926,416,1025` | 980×2100 | 무효 `[{"point_2d": [237, 8⏎ addCriterion: "ตัวเลือก \"<ref>Повторить все</ref>\" ในเมนู` | 무효 `(145, 8⏎ addCriterion` |
| `rel::3/settings_2.jpg` | TH→RU | O | `55,799,1023,904` | 980×2100 | ✓ 적중 `[{"point_2d": [374, 756]}]` | ✓ 적중 `(340, 756)` |
| `rel::3/settings_2.jpg` | TH→RU | R | `55,799,1023,904` | 980×2100 | ✓ 적중 `[{"point_2d": [476, 753]}]` | ✓ 적중 `(153, 746)` |
| `rel::4/Gmail_8.jpg` | TH→RU | O | `37,982,600,1155` | 952×2156 | 무효 `[]` | 무효 `(347, 8⏎ addCriterion` |
| `rel::4/Gmail_8.jpg` | TH→RU | R | `37,982,600,1155` | 952×2156 | 무효 `[{"point_2d": [473, 8⏎ addCriterion` | 무효 `(148⏎⏎ addCriterion'` |
| `rel::4/twitter_6.jpg` | TH→RU | O | `22,702,837,974` | 868×1932 | ✓ 적중 `[{"point_2d": [475, 740]}]` | 무효 `(175, 728` |
| `rel::4/twitter_6.jpg` | TH→RU | R | `22,702,837,974` | 868×1932 | ✓ 적중 `[{"point_2d": [475, 740]}]` | 무효 `(175, 729` |
| `rel::5/camera_1.jpg` | TH→RU | O | `411,1732,640,1802` | 952×2128 | ✓ 적중 `[{"point_2d": [476, 1569]}]` | ✓ 적중 `(467, 1566)` |
| `rel::5/camera_1.jpg` | TH→RU | R | `411,1732,640,1802` | 952×2128 | ✓ 적중 `[{"point_2d": [476, 1569]}]` | ✓ 적중 `(456, 1537)` |
| `rel::5/message_1.jpg` | TH→RU | O | `67,1490,1022,1749` | 952×2128 | 무효 `[{"point_2d": [476, 139⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | ✓ 적중 `(346, 1427)` |
| `rel::5/message_1.jpg` | TH→RU | R | `67,1490,1022,1749` | 952×2128 | ✓ 적중 `[{"point_2d": [374, 1406]}]` | ✓ 적중 `(163, 1427)` |
| `rel::6/safari_7.jpg` | TH→RU | O | `71,804,1211,955` | 980×2100 | ✓ 적중 `[{"point_2d": [173, 674]}]` | ✓ 적중 `(134, 675)` |
| `rel::6/safari_7.jpg` | TH→RU | R | `71,804,1211,955` | 980×2100 | ✓ 적중 `[{"point_2d": [476, 673]}]` | ✓ 적중 `(163, 675)` |
| `rel::6/wallet_3.jpg` | TH→RU | O | `32,343,424,484` | 980×2100 | ✓ 적중 `[{"point_2d": [173, 316]}]` | ✓ 적중 `(75, 304)` |
| `rel::6/wallet_3.jpg` | TH→RU | R | `32,343,424,484` | 980×2100 | ✓ 적중 `[{"point_2d": [173, 316]}]` | ✓ 적중 `(76, 304)` |

### Qwen2.5: 같은 언어 8화면, 0–1000 상대좌표

GT와 요청 출력은 **0–1000 상대 좌표**다. 완성된 좌표라도 범위를 넘으면 `무효`다. GT는 표시할 때만 반올림했다.

| 문항 | GUI | GT bbox (0–1000) | 전체 관계 질문 | 짧은 설명 |
| --- | --- | --- | --- | --- |
| `rel::1/booking_1.jpg` | EN | `67,517,941,581` | 무효 `(476, 9⏎ addCriterion` | 무효 `(435, 1156)` |
| `rel::1/booking_1.jpg` | ZH | `62,587,933,650` | 무효 `(436, 129⏎ addCriterion` | 무효 `(465, 1328` |
| `rel::1/booking_1.jpg` | TH | `72,591,941,650` | 무효 `(432, 1308` | 무효 `(436, 1312)` |
| `rel::1/booking_1.jpg` | RU | `70,574,938,640` | 무효 `(29⏎ addCriterion` | 무효 `(439, 1285` |
| `rel::5/message_1.jpg` | EN | `66,618,926,695` | 무효 `(75, 1234)` | 무효 `(8⏎ addCriterion` |
| `rel::5/message_1.jpg` | ZH | `66,618,926,695` | 무효 `(28⏎ addCriterion` | 무효 `(8⏎ addCriterion` |
| `rel::5/message_1.jpg` | TH | `66,618,926,695` | 무효 `(235, 129⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion⏎⏎ addCriterion` | 무효 `(235, 1406)` |
| `rel::5/message_1.jpg` | RU | `62,621,946,729` | 무효 `(72, 1163)` | 무효 `(235, 1428` |

### Qwen3: 같은 언어 8화면

GT와 출력은 모두 **0–1000 상대 좌표**다. 표의 GT만 읽기 쉽게 반올림했으며 실제 채점은 반올림 전 원본 bbox로 했다.

| 문항 | GUI | GT bbox (0–1000) | 전체 관계 질문 | 짧은 설명 |
| --- | --- | --- | --- | --- |
| `rel::1/booking_1.jpg` | EN | `67,517,941,581` | × GT 밖 `(300, 472)` | ✓ 적중 `(499, 547)` |
| `rel::1/booking_1.jpg` | ZH | `62,587,933,650` | × GT 밖 `(399, 527)` | ✓ 적중 `(499, 616)` |
| `rel::1/booking_1.jpg` | TH | `72,591,941,650` | × GT 밖 `(385, 547)` | ✓ 적중 `(484, 617)` |
| `rel::1/booking_1.jpg` | RU | `70,574,938,640` | × GT 밖 `(499, 518)` | ✓ 적중 `(499, 604)` |
| `rel::5/message_1.jpg` | EN | `66,618,926,695` | × GT 밖 `(156, 570)` | ✓ 적중 `(387, 650)` |
| `rel::5/message_1.jpg` | ZH | `66,618,926,695` | × GT 밖 `(122, 573)` | ✓ 적중 `(287, 637)` |
| `rel::5/message_1.jpg` | TH | `66,618,926,695` | × GT 밖 `(255, 551)` | ✓ 적중 `(401, 653)` |
| `rel::5/message_1.jpg` | RU | `62,621,946,729` | × GT 밖 `(185, 580)` | ✓ 적중 `(367, 664)` |

### Qwen3: 짧은 설명 O/R/C, 4언어쌍

GT와 출력은 모두 **0–1000 상대 좌표**다. GT는 표시할 때만 반올림했다.

| 문항 | 질문→GUI | GT bbox (0–1000) | O | R | C |
| --- | --- | --- | --- | --- | --- |
| `rel::1/booking_1.jpg` | EN→ZH | `62,587,933,650` | ✓ 적중 `(499, 616)` | ✓ 적중 `(499, 617)` | ✓ 적중 `(499, 617)` |
| `rel::1/booking_10.jpg` | ZH→TH | `63,315,455,341` | × GT 밖 `(0, 0)` | ✓ 적중 `(247, 320)` | × GT 밖 `(0, 0)` |
| `rel::2/clock_10.png` | TH→RU | `367,931,442,986` | ✓ 적중 `(410, 956)` | ✓ 적중 `(400, 956)` | ✓ 적중 `(407, 955)` |
| `rel::2/weather_3.png` | RU→EN | `290,171,709,836` | ✓ 적중 `(509, 192)` | ✓ 적중 `(509, 192)` | ✓ 적중 `(509, 192)` |
<!-- ALL_RESULTS_END -->
