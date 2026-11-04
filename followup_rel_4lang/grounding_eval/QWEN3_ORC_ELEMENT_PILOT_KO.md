# Qwen3-VL O/R/C 요소 설명 파일럿과 속도 점검

실행일: 2026-11-04. 로컬 **Qwen3-VL-8B-Instruct** 체크포인트로 기존 12개 파일럿 문항 중 **4문항 × 언어쌍 1개 × O/R/C = 12응답**을 실행했다. F와 전체 관계 질문 입력은 실행하지 않았다. 각 문항의 O/R/C는 **같은 GUI 이미지**를 사용한다. 4개 언어쌍은 EN→ZH, ZH→TH, TH→RU, RU→EN을 하나씩 포함한다. 선택된 문항은 정렬된 파일럿 ID의 앞 4개이므로 앱·문항 유형의 대표 표본은 아니다.

12문항 전체에 대해 언어쌍 하나씩 실행하려던 요청은 자동 승인 검토에서 **앞선 배치당 약 155초를 근거로 장시간 GPU 작업**으로 판단돼 거절됐다. 이 파일은 승인된 **4쌍 제한 실행**의 결과다. 나머지 8문항이나 원래 파일럿의 48언어쌍은 실행하지 않았다.

## 입력과 실행 설정

`element-only`는 기준 요소의 짧은 설명을 뜻한다. 요소 라벨 한 단어만 주는 설정이 아니며, `blue '<ref>Search</ref>' button`처럼 색상·요소 종류가 포함될 수 있다. 원래 O/R/C의 **기준 표현과 그 짧은 주변 설명의 언어 배치**를 그대로 옮겼다.

| 조건 | 짧은 설명의 언어 | `<ref>` 기준 표현의 언어 |
| --- | --- | --- |
| O | Source | Source |
| R | Source | GUI |
| C | GUI | Source |

예를 들어 EN→ZH `booking_1`은 O=`blue '<ref>Search</ref>' button`, R=`blue '<ref>搜索</ref>' button`, C=`蓝色“<ref>Search</ref>”按钮`다. 각 설명이 해당 O/R/C 원본 질문 안에 실제로 등장하는지도 검사했다. 세 조건 모두 아래의 **같은** user 프롬프트를 사용하며, 명시적 system 메시지는 없다.

```text
Locate the GUI reference element marked by <ref>...</ref> in the text below. Use surrounding words to identify it. Do not answer a relation question.
Text: {element_description}
Return only one point as (x, y), with integer x and y from 0 to 1000 relative to the full screenshot. (0, 0) is the top-left and (1000, 1000) is the bottom-right. No explanation or code fence.
```

- 모델 revision `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`, BF16, Transformers 4.57.6, Torch 2.9.1+cu130. 캐시된 4개 shard를 `from_pretrained`로 적재했다.
- **Hugging Face attention 설정은 `sdpa`**이고, 빈 모델을 CPU에서 구성해 vision·text 하위 설정까지 `sdpa` 전달을 확인했다. 외부 FlashAttention-2 패키지는 사용하지 않았다. PyTorch SDPA 내부의 실제 CUDA 커널은 추적하지 않았다. [PyTorch 문서](https://docs.pytorch.org/docs/2.9/generated/torch.nn.functional.scaled_dot_product_attention.html)는 입력에 따른 커널 자동 선택을 설명한다.
- 세 조건을 왼쪽 패딩 **배치 3**으로 함께 처리했다. 이미지당 시각 토큰은 약 1,998–2,010개다. `min_pixels=262144`, `max_pixels=2097152`, greedy, 최대 64 새 토큰을 사용했다. [Qwen3 기술 보고서](https://arxiv.org/pdf/2511.21631)에 따라 점은 0–1000 상대 좌표로 받고, 원본 이미지로 환산해 GT bbox 안에 있는지 채점했다.

## 결과와 원시 좌표

| 조건 | 유효한 단일 점 | GT 적중 | `addCriterion` | EOS 종료 |
| --- | ---: | ---: | ---: | ---: |
| O | 4/4 | **3/4** | 0/4 | 4/4 |
| R | 4/4 | **4/4** | 0/4 | 4/4 |
| C | 4/4 | **3/4** | 0/4 | 4/4 |

GT 범위는 원본 bbox를 0–1000으로 환산해 반올림한 값이다. 모델 출력은 원시 텍스트 그대로다. ✓는 원본 좌표로 역변환한 점이 실제 GT 안에 있음을 뜻한다.

| 문항 · 언어쌍 | GT `(x1,y1,x2,y2)` | O 원시 출력 | R 원시 출력 | C 원시 출력 |
| --- | --- | --- | --- | --- |
| `booking_1` EN→ZH | `(62,587,933,650)` | `(499, 616)` ✓ | `(499, 617)` ✓ | `(499, 617)` ✓ |
| `booking_10` ZH→TH | `(63,315,455,341)` | `(0, 0)` ✗ | `(247, 320)` ✓ | `(0, 0)` ✗ |
| `clock_10` TH→RU | `(367,931,442,986)` | `(410, 956)` ✓ | `(400, 956)` ✓ | `(407, 955)` ✓ |
| `weather_3` RU→EN | `(290,171,709,836)` | `(509, 192)` ✓ | `(509, 192)` ✓ | `(509, 192)` ✓ |

`booking_10`에서 O와 C는 유효한 화면 좌표 `(0, 0)`을 냈지만 GT bbox 밖이고, 기준 표현만 GUI 언어로 바꾼 R은 GT에 들어갔다. **한 사례의 설명**이지 R의 일반적 이득을 추정한 결과는 아니다. `weather_3`의 GT는 화면의 약 28%를 차지하는 넓은 상자이므로 세 적중을 정밀한 위치 지정으로 읽기 어렵다. 4쌍만으로 조건별 성능 차이를 주장할 수 없다. 배치 3을 사용했으므로 이전 단건 Qwen3 실행과 생성 경로도 완전히 같지는 않다. 이 결과는 탐색용 파일럿이며 기존 [v3 확증 프로토콜](PROTOCOL_KO.md)의 결과에 합치지 않는다.

## 왜 느렸나?

| 측정 구간 | 관찰값 |
| --- | ---: |
| 모델 적재 | 첫 실행 20.7초, 캐시가 데워진 재개 실행 11.4초 |
| CPU 전처리 | 배치당 0.46–0.79초, 중앙값 **0.61초** |
| `model.generate` 전체 | 배치당 155.0–178.0초, 중앙값 **161.1초** |
| 첫 model forward | 계측한 3배치에서 158.5–176.1초, 생성 시간의 중앙 **98.4%** |
| 뒤따른 토큰 생성 forward | 계측한 3배치에서 합계 1.8–2.6초 |
| 최대 할당 GPU 메모리 | 약 **18.2GiB / 할당된 45GiB MIG** |

측정된 지연은 **첫 forward의 이미지 인코딩과 긴 멀티모달 프리필**에 집중된다. 설치된 Transformers의 Qwen3-VL 구현은 이 forward 안에서 image feature를 만든 뒤 language model을 호출한다. 배치 3은 같은 약 2,000개 시각 토큰짜리 이미지를 세 조건에 반복 입력한다. 첫 forward 내부에서 vision encoder와 language prefill의 시간은 따로 측정하지 않아 어느 쪽이 더 큰지는 아직 모른다. 이번 실행의 GPU 최대 할당량은 18.2GiB였으므로 VRAM 용량 부족 징후는 없었다. GPU는 45GiB 메모리를 가진 B200 MIG 슬라이스이지만 계산 자원은 36 SM으로 제한된다.

Qwen은 [공식 README](https://github.com/QwenLM/Qwen3-VL/blob/main/README.md)에서 FlashAttention-2를 속도·메모리 개선 선택지로 소개한다. **이번 `sdpa` 자체가 지연의 원인이라고 단정할 대조는 없다.** PyTorch SDPA가 내부적으로 어떤 커널을 선택했는지도 저장하지 않았다. 속도 개선을 확인하려면 동일 입력·해상도·배치에서 attention 구현만 바꾼 별도 단건 대조가 필요하다.

[실행 코드](run_qwen3_orc_element_pilot.py), [12개 원시 JSONL](../results/grounding_pilot_qwen3_8b_orc_element_only/predictions.jsonl), [집계 JSON](../results/grounding_pilot_qwen3_8b_orc_element_only/summary.json)에 조건별 설명·원본 질문·이미지 해시·렌더링 프롬프트·생성 토큰·시간을 저장했다. 아래 명령은 이미 완료한 4쌍을 검사하고 요약만 다시 계산하므로 GPU를 적재하지 않는다.

```bash
.venv/bin/python followup_rel_4lang/grounding_eval/run_qwen3_orc_element_pilot.py --limit-pairs 4
```
