# Qwen3-VL: 질문 문맥과 요소 설명만 사용한 빠른 위치 파일럿

실행일: 2026-11-04. **Qwen3-VL-8B-Instruct** 로컬 체크포인트 `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`로, 기존 양성 대조 **2문항 × EN/ZH/TH/RU 화면 = 8화면**에 두 입력을 각각 시험했다. 총 16응답이다. 질문 언어와 GUI 언어를 같게 했고, **O/R 및 source→GUI 불일치 실험은 실행하지 않았다.** 12문항 × 4화면 전체로 확장하지 않은 빠른 기능 검사다.

## 설정

- BF16, Hugging Face `sdpa`, 배치 1, greedy, 최대 64 새 토큰. Transformers 4.57.6, Torch 2.9.1+cu130. 개인 캐시의 4개 shard를 `from_pretrained`로 읽었으며 다운로드는 없었다. Qwen2.5 파일럿과 같은 `min_pixels=262144`, `max_pixels=2097152`을 썼다.
- 두 입력은 **같은 원본 이미지·GT·생성 설정·출력 지시**를 썼다. `query informed`에는 `<ref>`가 표시된 GUI 언어의 관계 질문 전체를 넣었다. `element-only`에는 기존 [파일럿 기준 요소 표현](pilot_referent_phrases.json)의 짧은 설명만 넣었다. 이 설명에는 `blue Search button`처럼 요소 종류·색상 등 국소 문맥이 들어갈 수 있으므로 **라벨 문자열 한 단어만** 뜻하지 않는다.
- 명시적 system 메시지는 없고, 저장된 Qwen3 렌더링 프롬프트도 user→assistant 형식이다. 공통 user text는 다음과 같고 `{text}`만 두 입력 사이에서 바꿨다.

```text
Locate the GUI reference element marked by <ref>...</ref> in the text below. Use surrounding words to identify it. Do not answer a relation question.
Text: {text}
Return only one point as (x, y), with integer x and y from 0 to 1000 relative to the full screenshot. (0, 0) is the top-left and (1000, 1000) is the bottom-right. No explanation or code fence.
```

Qwen3-VL에는 Qwen2.5의 리사이즈된 화면 **절대 픽셀** 대신 [Qwen3 팀 기술 보고서](https://arxiv.org/pdf/2511.21631)의 **0–1000 상대 좌표**를 적용했다. 출력 전체가 단일 `(정수, 정수)`이고 두 값이 0–1000이면 유효로 보았다. 점을 원본 화면 크기로 환산해 GT bbox의 닫힌 경계 안에 있는지 채점했다.

## 결과

| 입력 | 유효한 단일 점 | GT bbox 적중 | `addCriterion` | 정상 EOS 종료 |
| --- | ---: | ---: | ---: | ---: |
| Query informed: 관계 질문 전체 | 8/8 | **0/8** | 0/8 | 8/8 |
| Element-only: 짧은 요소 설명 | 8/8 | **8/8** | 0/8 | 8/8 |

16응답 모두 **11토큰**을 생성하고 `<|im_end|>`(151645)로 끝났다. 미완성 좌표와 `addCriterion`은 없었다. 아래 좌표는 모델 원시 출력 그대로이며, GT 범위만 비교하기 편하도록 0–1000으로 환산해 반올림했다. 각 조건의 원시 응답은 출력 전체가 표시된 한 좌표쌍이다.

| 화면 | GUI | GT의 상대 x 범위 | GT의 상대 y 범위 | Query informed 원시 출력 | Element-only 원시 출력 |
| --- | --- | ---: | ---: | --- | --- |
| `booking_1` | EN | 67–941 | 517–581 | `(300, 472)` ✗ | `(499, 547)` ✓ |
| `booking_1` | ZH | 62–933 | 587–650 | `(399, 527)` ✗ | `(499, 616)` ✓ |
| `booking_1` | TH | 72–941 | 591–650 | `(385, 547)` ✗ | `(484, 617)` ✓ |
| `booking_1` | RU | 70–938 | 574–640 | `(499, 518)` ✗ | `(499, 604)` ✓ |
| `message_1` | EN | 66–926 | 618–695 | `(156, 570)` ✗ | `(387, 650)` ✓ |
| `message_1` | ZH | 66–926 | 618–695 | `(122, 573)` ✗ | `(287, 637)` ✓ |
| `message_1` | TH | 66–926 | 618–695 | `(255, 551)` ✗ | `(401, 653)` ✓ |
| `message_1` | RU | 62–946 | 621–729 | `(185, 580)` ✗ | `(367, 664)` ✓ |

**Query informed의 8점 모두 기준 요소 bbox보다 위쪽**에 있다. 두 관계 질문은 기준 요소의 *위에 있는 요소*를 묻기 때문에, 모델이 `<ref>` 기준 요소 대신 질문의 답 요소를 찍었을 가능성이 높다. 답 요소의 별도 GT는 없으므로 정확히 그 요소를 찍었다고 확정할 수는 없다. Element-only의 8점은 모두 기준 bbox 안에 들어갔다.

이 결과는 Qwen3에서도 **전체 관계 질문을 주는 방식의 대상 혼동**을 시사한다. `addCriterion` 부재는 이번 2문항·16응답의 관찰일 뿐 Qwen3 전체의 출력 안정성을 증명하지 않는다. 또한 Qwen2.5와 모델 크기·적재 경로·좌표계·프롬프트가 달라, 이 결과만으로 Qwen2.5의 이상 토큰 원인을 attention이나 모델 계열 중 하나로 판정할 수 없다. 이전 Qwen2.5의 같은 8화면 괄호형 실행은 전체 질문 **1/8 적중**, 짧은 표현 **6/8 적중**이었다. 둘 모두 짧은 요소 설명에서 기준 요소 선택이 쉬워지는 방향이라는 정도만 비교할 수 있다.

[실행 코드](run_qwen3_prompt_pilot.py), [16개 원시 JSONL](../results/grounding_pilot_qwen3_8b_prompts/predictions.jsonl), [집계 JSON](../results/grounding_pilot_qwen3_8b_prompts/summary.json)에 각 이미지 해시, 질문·표현, 렌더링 프롬프트, GT, 예측 점, 생성 토큰 ID와 종료 이유를 남겼다. 저장소 최상위에서 같은 8화면을 다시 선택하는 명령은 아래와 같다. 성공 기록이 이미 있으면 GPU를 적재하지 않고 요약만 다시 계산한다.

```bash
.venv/bin/python followup_rel_4lang/grounding_eval/run_qwen3_prompt_pilot.py --limit-screens 8
```
