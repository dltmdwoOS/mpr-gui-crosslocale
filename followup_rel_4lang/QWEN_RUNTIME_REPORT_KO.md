# Qwen 추론 시간 점검: 기존 기록, 병목, 전체 실행 계획

작성: 2026-11-04. 범위는 MPR-GUI 6×6, REL O/R/C/F, 기준 요소 위치 지정 파일럿의 **Qwen2.5-VL-7B-Instruct와 Qwen3-VL-8B-Instruct**다. 시간을 줄이는 방안을 논의하며 나온 수치 중 원시 결과로 재검산한 값과, 지난 대화의 단일 계측·외삽값을 구분한다. 이 보고서를 쓰기 위해 새 GPU 추론은 실행하지 않았다.

**후속 계측(2026-11-05):** [RTX 4090 결과](QWEN3_RTX4090_RESULTS_KO.md)에서
주된 병목은 BF16 patch Conv3D의 `SlowDilated3d` 경로로 확인됐다. weight를
`channels_last_3d`로 배치해 cuDNN 경로를 사용하자 같은 2MP·배치 3이
171.984초→2.421초였다. 아래의 attention 가설과 64일/28일 산술 예시는 당시
기본 실행 경로에 대한 기록이며 **개선한 런타임의 처리 시간으로 사용하지 않는다.**

## 먼저 읽을 결론

1. Qwen3 파일럿의 긴 시간은 **답을 한 토큰씩 생성하는 구간보다 첫 forward**에 몰려 있다. 계측한 배치 3에서 첫 forward가 생성 시간의 중앙 98.4%였고, 이미지·텍스트를 준비하는 CPU 단계의 중앙값은 0.61초였다.
2. 당시에는 **고해상도 이미지의 전체 attention 계산량**을 유력한 가설로 검토했다. 아래의 구조 비교는 계산량 지표이며 실측 시간 비율이 아니다. 후속 4090 계측에서 1MP·배치 3의 patch Conv3D만 81.873초였고 27개 vision block은 합계 약 0.22초였다. 이 환경의 주된 지연 설명은 Conv3D fallback으로 수정한다. 구조 비교 자체는 아래에 역사적 근거로 남긴다.
3. 이미지 최대 픽셀을 약 2MP에서 1MP로 줄인 **한 배치**에서는 161.3초→70.3초였다. 작은 GUI 글자와 요소 위치 정확도가 유지되는지는 한 사례로 판단할 수 없다. Qwen 공식 README도 이미지 토큰 예산을 조절하는 방법을 안내한다. [Qwen3-VL README](https://github.com/QwenLM/Qwen3-VL/blob/main/README.md#pixel-control-via-official-processor)
4. RTX 4090 여러 대는 **모델을 나누는 방식이 아니라 입력을 나누는 방식**으로 사용한다. 같은 4090 한 대의 처리량이 유지되면 4대/8대는 완료 시간의 약 1/4·1/8을 목표로 할 수 있다. 현재 Qwen3의 4090 실측치가 없으므로 절대 완료일은 확정할 수 없다.

## 1. 비교 대상과 남은 작업량

| 작업 | 계산 | 실제 필요한 추론 | 현재 기록 |
| --- | ---: | ---: | --- |
| 기존 6×6의 Qwen3 재실행 | 2,195 semantic item × 36 언어 조합 | 79,020 | Qwen2.5는 완료; Qwen3는 미실행 |
| REL O/R/C/F의 Qwen3 재실행 | 366문항 × 16언어쌍 × 4조건 = 23,424 결과 행 | 동일 입력 재사용 후 18,432 | Qwen2.5는 완료; Qwen3는 미실행 |
| 기준 요소 위치 찾기 | 158문항 × 12개 불일치 언어쌍 × O/R/C | 5,688 | Qwen3 4쌍 × 3조건만 파일럿 완료 |
| **합계** |  | **103,140** | 기존 실험 간 추가 중복 제거 전 |

6×6의 semantic item 2,195개는 WF 365개와 나머지 5개 차원 각 366개다. 위 REL 18,432는 O/R/C/F **조건 안의 중복 입력**을 재사용한 값이며 6×6과 REL 사이의 입력 재사용은 아직 계산에 넣지 않았다. 위치 찾기에 F나 다른 보조 조건을 추가하면 그만큼 늘어난다. 근거: [6×6 집계](../01_code/results/summaries/vast_6x6_qwen2_5_vl_7b.json), [REL 집계](results/full/qwen2_5_vl_7b_batch32/summary.json), [grounding 대상 고정 목록](grounding_eval/input_lock.json).

## 2. 실제로 측정한 시간

### 2.1 과거 전체 추론: 서로 다른 장비·작업

| 기록 | 장비·방식 | 실제 입력 | 기록된 추론 시간 합계 | 입력당 평균 | 시간 필드의 범위 |
| --- | --- | ---: | ---: | ---: | --- |
| Qwen2.5 6×6 | RTX 4090, 배치 1, BF16·SDPA | 79,020 | **19.449시간** | **0.886초** | 이미지/프롬프트 전처리, 생성, 첫 토큰 label score |
| Qwen2.5 REL O/R/C/F | B200 MIG 2g.45gb, 배치 32, BF16·SDPA | 18,432 | **5.704시간** | **1.114초** | 배치 추론 시간을 입력 수로 나눈 값 |

모델 로드·데이터 준비·결과 저장·집계는 위 합계에 들어 있지 않다. 두 작업은 입력 집합과 배치·장비·Torch 버전이 다르므로 19.449시간과 5.704시간만으로 장비 속도를 비교하면 안 된다. 원본: [6×6 압축 JSONL](../01_code/results/summaries/6x6_qwen.zip), [REL 압축 예측](results/full/qwen2_5_vl_7b_batch32/predictions.jsonl.gz), [runtime 필드 정의](../01_code/README.md#결과-필드).

더 가까운 비교를 위해 **같은 REL item·언어쌍·렌더링 프롬프트**인 O 입력을 연결했다. 4언어 5,856개 중 5,852개가 일치했고 4개는 프롬프트가 달랐다. 일치한 5,852개의 평균은 과거 RTX 4090 기록 **0.883초**, B200 MIG 배치 32 기록 **1.114초**였다. B200 기록이 약 26% 길다. 그러나 당시 RTX는 배치 1·Torch 2.13.0·Python 3.12.13, B200은 배치 32·Torch 2.9.1·Python 3.11.11이었고, 6×6 원본 이미지가 지금 로컬에 없어 이미지 바이트 동일성도 재검사하지 못했다. **4090 자체가 26% 빠르다는 인과 추정은 아니다.** 앞선 대화에서 언급한 607건 비교의 추출 조건은 현재 저장된 자료로 확인하지 못해, 여기서는 재현 가능한 5,852건 재집계를 사용한다.

현재 B200은 카드 전체가 아니라 **45GB VRAM·36 SM의 MIG 분할**이다. VRAM 용량과 계산 자원은 다른 값이므로, 이름의 `B200`만 보고 RTX 4090보다 반드시 빠를 것이라 가정할 수 없다. 반대로 이 구조적 정보만으로 Qwen3에서의 4090 우위도 계산할 수 없다. [MIG 파일럿 기록](grounding_eval/QWEN3_ORC_ELEMENT_PILOT_KO.md#왜-느렸나).

### 2.2 Qwen2.5 배치 크기 실험

같은 32개 입력과 별도 최악 크기 메모리 입력을 사용했다. 처리량에는 전처리·생성·label scoring이 포함된다. [실험 기록](SERVER_RUN_KO.md#배치-크기-실험-결과), [원시 집계](results/batch_benchmark/qwen2_5_vl_7b/summary.json).

| 배치 | 입력/초 | 최대 reserved VRAM | 결과 |
| ---: | ---: | ---: | --- |
| 1 | 0.4919 | 16.732GiB | 통과 |
| 2 | 0.5850 | 17.602GiB | 통과 |
| 4 | 0.6838 | 20.896GiB | 통과 |
| 8 | 0.7767 | 24.617GiB | 통과 |
| 16 | 0.7970 | 32.365GiB | 통과 |
| **32** | **0.8248** | **39.428GiB** | 선택; 배치 1 대비 1.68배 처리량 |
| 64 | — | — | 메모리 부족 진단 중 NVML 오류 |

이 값은 Qwen2.5/B200 MIG의 짧은 표본이다. Qwen3나 24GB RTX 4090의 최적 배치로 옮길 수 없다. 실제 Qwen2.5 REL full은 배치 32에서 입력당 1.114초로, 위 짧은 표본의 `1/0.8248≈1.212초`와도 다르다.

### 2.3 같은 B200 MIG에서의 위치 지정 파일럿

| 기록 | 입력·배치 | 생성 시간 | 유의할 점 |
| --- | --- | --- | --- |
| Qwen2.5 상대좌표 재검사 | 8화면 × 전체 질문/짧은 설명 = 16응답, 배치 1 | 중앙 **2.806초/응답**, 범위 1.674–20.576초 | 최대 20.576초 출력은 64토큰까지 이어짐 |
| Qwen3 같은 언어 기능 검사 | 같은 8화면 × 2입력 = 16응답, 배치 1 | **시간 미기록** | 프롬프트·화면은 Qwen2.5 상대좌표 검사와 같지만 속도 비교 불가 |
| Qwen3 O/R/C | 4문항 × 언어쌍 하나 × 3조건 = 12응답, **배치 3** | 배치당 중앙 **161.140초**, 범위 154.982–177.981초 | 입력당 단순 환산 **53.713초**; 같은 화면을 세 조건에 반복 |

모두 B200 MIG, BF16·SDPA, 이미지 픽셀 예산 `min=262,144, max=2,097,152`였다. Qwen2.5 상대좌표 기록의 `generate_s`와 Qwen3의 `generate_s`를 읽어 계산했다. 이들은 같은 장비라도 **서로 다른 입력·배치·모델**이어서 `53.713/2.806≈19.1배`를 모델만의 속도 차이로 해석할 수 없다. 같은 ZH `booking_1` 이미지 SHA의 짧은 설명에서 Qwen2.5 단건은 2.896초, Qwen3 O/R/C 세 응답 배치는 154.982초였다. 이 비교도 프롬프트·배치가 일치하지 않는다. 근거: [Qwen2.5 원시 16건](results/grounding_pilot_qwen25_relative_controls/predictions.jsonl), [Qwen3 원시 12건](results/grounding_pilot_qwen3_8b_orc_element_only/predictions.jsonl), [Qwen3 파일럿 설명](grounding_eval/QWEN3_ORC_ELEMENT_PILOT_KO.md).

Qwen3 배치 4개의 세부 기록은 다음과 같다. 첫 배치를 제외한 3개 배치에 첫 forward와 이후 forward의 별도 시간이 저장됐다.

| 문항·GUI | 이미지 격자 | 시각 토큰/화면 | `generate`/배치 | CPU 전처리 | 첫 forward | 이후 forward 합계 | 최대 allocated VRAM |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `booking_1` ZH | `1×134×60` | 2,010 | 154.982초 | 0.463초 | 미기록 | 미기록 | 18.203GiB |
| `booking_10` TH | `1×134×60` | 2,010 | 161.289초 | 0.623초 | 158.519초 | 2.601초 | 18.208GiB |
| `clock_10` RU | `1×74×108` | 1,998 | 177.981초 | 0.598초 | 176.125초 | 1.844초 | 18.201GiB |
| `weather_3` EN | `1×74×108` | 1,998 | 160.991초 | 0.788초 | 158.463초 | 2.517초 | 18.188GiB |

여기서 `image_grid_thw`는 **ViT patch 격자**이고 시각 토큰은 `grid_t×grid_h×grid_w/4`다. 세 조건이 같은 이미지를 사용하지만 현재 배치에서는 그 이미지를 **세 번 인코딩**한다. 각 응답은 실제 7–11토큰만 생성하고 정상 종료했다. 따라서 `max_new_tokens=64` 자체나 긴 답 생성이 161초의 주원인으로 보이지 않는다. 모델 적재 11–21초도 각 배치 시간에는 들어 있지 않다. 첫 forward에는 **vision encoder와 언어 모델 prefill이 모두 들어 있으므로**, 98.4%를 전부 vision encoder 시간으로 적으면 안 된다. [계측 코드](grounding_eval/run_qwen3_orc_element_pilot.py), [원시 예측](results/grounding_pilot_qwen3_8b_orc_element_only/predictions.jsonl).

### 2.4 2MP→1MP 한 배치 시험

직전 대화에서 같은 Qwen3 `booking_10` O/R/C 세 응답의 최대 픽셀만 **2,097,152→1,048,576**으로 바꾼 단건을 측정했다. 원시 결과 파일·재실행 스크립트는 저장소에 남지 않아 **낮은 신뢰도의 세션 계측**으로 분류한다.

같은 대화에서 grounding 본 분석에 해당하는 **158문항 × 4화면 = 632개 이미지**도 CPU 전처리로 훑었다. 화면당 시각 토큰 중앙값은 약 **1,998→987개**였다. 이 점검도 원시 계측 파일이 남지 않았으며, **GPU 시간이 632화면 모두에서 같은 비율로 줄었다는 뜻은 아니다**.

| `booking_10` 배치 3 | 약 2MP | 약 1MP | 변화 |
| --- | ---: | ---: | ---: |
| 이미지당 모델 시각 토큰 | 약 1,998–2,010 | 약 987 | 약 절반 |
| 생성 시간 | 161.289초 | 70.25초 | **2.30배 빠름** |
| 최대 allocated VRAM | 18.208GiB | 17.307GiB | 0.901GiB 감소 |
| GT 적중 O/R/C | ✗/✓/✗ | ✗/✓/✗ | 이 한 사례만 같은 판정 |

해상도에 대한 강한 **속도 단서**지만 1배치뿐이다. GUI의 작은 글자, 얇은 bbox, 태국어·중국어 화면 등에서 정확도를 별도 확인해야 한다. Qwen3 공식 README는 `max_pixels`를 통해 이미지당 **256–1,280 visual token** 예산을 설정하는 예를 제공한다. 여기서 1MP 약 1,000토큰은 그 예시 범위 안에 있다. 이는 공식 예시와 **설정 가능성**의 근거이며 MPR-GUI 정확도 보장의 근거는 아니다. [Qwen3-VL README](https://github.com/QwenLM/Qwen3-VL/blob/main/README.md#pixel-control-via-official-processor).

## 3. Qwen3가 왜 이렇게 느린가? (11월 4일 시점의 가설)

### 3.1 당시의 구조적 가설: 모든 vision 층의 전체 attention

실제로 사용한 고정 [Qwen2.5 체크포인트 구성](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct/blob/cc594898137f460bfe9f0759e9844b3ce807cfb5/config.json)과 [Qwen3 체크포인트 구성](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct/blob/0c351dd01ed87e9c1b53cbc748cba10e6187ff3b/config.json)을 비교했다.

| 요소 | Qwen2.5-VL-7B | Qwen3-VL-8B |
| --- | ---: | ---: |
| ViT patch 크기 | 14×14px | 16×16px |
| ViT 층수 | 32 | 27 |
| ViT 전체 화면 attention 층 | **4** | **27** |
| 나머지 ViT 층 | 28개 window attention | 없음 |
| ViT→언어 모델 병합 | 2×2 patch→1 token | 동일 병합 + 3개 층 DeepStack 특성 |
| 언어 모델 층·hidden size | 28층·3,584 | 36층·4,096 |

Qwen2.5의 28개 window 층은 한 화면의 patch를 작은 창으로 나눠 처리한다. Qwen3의 현 구현에는 그 window 분기가 없고, 모든 27개 층에 이미지 전체 길이를 전달한다. Qwen 팀도 Qwen2.5의 4개 전체 attention 층과 나머지 window 층을 설명한다. Qwen3 기술 보고서는 별도의 vision backbone과 DeepStack을 설명한다. [Qwen2.5 팀 설명](https://qwenlm.github.io/blog/qwen2.5-vl/), [두 구현: Qwen2.5](https://github.com/huggingface/transformers/blob/v4.57.6/src/transformers/models/qwen2_5_vl/modeling_qwen2_5_vl.py), [Qwen3](https://github.com/huggingface/transformers/blob/v4.57.6/src/transformers/models/qwen3_vl/modeling_qwen3_vl.py), [Qwen3 기술 보고서](https://arxiv.org/html/2511.21631v2).

실제 `booking_1` ZH 이미지는 Qwen2.5에서 **10,640 ViT patch→2,660 언어 모델 시각 토큰**, Qwen3에서 **8,040 patch→2,010 토큰**이었다. **Qwen3가 언어 모델에 더 많은 이미지 토큰을 넣어서 느리다는 설명은 이 화면에는 맞지 않는다.** ViT에서 얼마나 넓게 attention을 계산하는지가 다르다. 각 층·head에서 계산하는 attention 점수 쌍 수를 단순 합산하면 다음과 같다.

```text
Qwen2.5: 4 × 10,640² + 28 × (각 112px 창의 patch 수² 합) ≈ 4.71억
Qwen3:  27 × 8,040²                                      ≈ 17.45억
비율:   같은 이미지 1장 기준 약 3.70배
```

Qwen2.5 창의 최대 길이는 64 patch이며 가장자리의 짧은 창까지 실제 격자로 계산했다. 이 식은 **attention 점수 쌍 개수의 대략적 연산 지표**다. 커널의 효율, head dimension, MLP·projection, 언어 모델, 메모리 전송, Python 오버헤드를 포함한 총 FLOPs 또는 속도 예측식은 아니다. Qwen3 O/R/C 배치에는 같은 화면 3장이 들어가므로 해당 배치의 vision attention 점수 쌍은 Qwen2.5 단건과 비교하면 약 **11.1배**가 된다. 이것만으로 관측된 배치 시간 비율 전체를 설명했다고 주장하지 않는다.

### 3.2 다른 후보의 위치

| 후보 | 현재 근거 | 판단 |
| --- | --- | --- |
| 이미지 계산량·전체 ViT attention | 구현 차이가 명확하고, 한 배치 1MP 축소에서 2.30배 빨라짐 | **가장 강한 후보**. 실제 vision 시간 비중은 미계측 |
| Qwen3 언어 모델 규모·DeepStack | 36층/4,096과 3층 시각 특성 주입 대 28층/3,584 | 추가 비용은 합리적이지만 단독으로 수십 배를 설명했다고 볼 근거 없음 |
| SDPA 또는 특정 CUDA 커널 | 두 실험의 Hugging Face attention 설정은 SDPA. PyTorch는 입력에 따라 내부 커널을 고름 | 실제 커널 추적·동일 조건 대조가 없어 **원인 확정 불가** |
| B200 MIG 자체 | Qwen3와 Qwen2.5 위치 파일럿은 같은 B200 MIG | Qwen3와 4090의 속도 차이는 미측정. 장비 차이만으로 현재 파일럿 차이를 설명할 수 없음 |
| CPU 전처리·모델 적재 | 전처리 중앙 0.61초/배치, 적재 11–21초는 별도 | 161초/배치의 주원인 아님 |
| 출력 길이 | Qwen3 실제 7–11토큰; 이후 forward 1.8–2.6초/배치 | 주원인 아님 |

`attn_implementation="sdpa"`는 **PyTorch SDPA 경로 설정**이지 GPU에서 실행된 구체적인 커널의 이름이 아니다. 내부 커널은 자동 선택될 수 있다. 외부 `flash-attn` 패키지를 사용한 속도 대조는 저장돼 있지 않다. FA2가 빨라질 가능성은 있지만 현재 수치로 절감률을 제시할 수 없다. 사용자 방침인 SDPA를 유지한다면 우선 이미지 예산과 작업 분할을 최적화하는 편이 재현성 관리에도 단순하다. [PyTorch SDPA 문서](https://docs.pytorch.org/docs/2.9/generated/torch.nn.functional.scaled_dot_product_attention.html), [Qwen3 FA2 안내](https://github.com/QwenLM/Qwen3-VL/blob/main/README.md#flash-attention-2-to-speed-up-generation).

**원인을 정량 분해하려면** 같은 이미지·문구·배치·픽셀 예산을 고정한 채 `model.model.visual`과 `model.model.language_model`에 CUDA 동기화 타이머를 각각 걸어야 한다. 배치 1과 3, 1MP와 2MP를 각각 한 번씩 측정하면 vision/언어 모델·이미지 크기·중복 인코딩 영향을 분리할 수 있다. SDPA 내부 커널은 별도로 profiler로 확인한다. 이 진단은 아직 수행하지 않았다.

## 4. 해상도, 배치, 장비에 따른 시간 계산

표의 103,140회는 남은 세 실험을 합친 규모다. 다음은 **B200 MIG Qwen3 O/R/C 파일럿 속도가 전 과제에 그대로 적용되고, 모든 작업에서 배치 3이 가능하다**는 가정의 산술 예시다. RTX 4090 실측 예측치가 아니다.

| 동일 속도 GPU 수 | 2MP: 161.14초/배치 3 가정 | 1MP: 70.25초/배치 3 가정 |
| ---: | ---: | ---: |
| 1 | 약 **64.1일** | 약 **28.0일** |
| 2 | 32.1일 | 14.0일 |
| 4 | 16.0일 | 7.0일 |
| 8 | 8.0일 | 3.5일 |

계산식은 `103,140 × (배치 초 / 3) ÷ GPU 수 ÷ 86,400`이다. 2MP는 **4배치 파일럿의 중앙값**, 1MP는 **원시 파일을 보존하지 않은 한 배치**의 값이다. 6×6의 현재 러너는 배치 1이며 질문 형태·이미지 크기 분포도 파일럿과 다르다. 모델 로드, 데이터 전송, 느린 샤드, 중단 복구, 결과 합치기도 제외했다. 따라서 이 표는 장비 구매·대여를 확정할 완료일이 아니라 **처리량 변화의 규모를 보는 계산기**다. 같은 4090 한 대의 처리 시간을 `s`초/입력으로 계측하면 `103,140×s/GPU 수`로 다시 계산해야 한다.

이 산술 가정의 총 GPU 사용 시간은 2MP 약 **1,539 GPU·시간**, 1MP 약 **671 GPU·시간**이다. GPU 수를 4배로 늘리면 완료 시간은 대략 1/4이지만 총 GPU 사용 시간 자체는 비슷하다. Vast.ai 비용은 실제 상품의 GPU 시간당 요금 외에 저장공간·전송을 포함하며, 상품 가격은 변한다. [Vast.ai 가격 안내](https://docs.vast.ai/guides/instances/pricing).

### 최적화 우선순위

| 순서 | 조치 | 기대와 검증 기준 |
| ---: | --- | --- |
| 1 | Qwen3 이미지 상한 2MP/1MP를 고정 표본에서 비교 | 한 배치에서 약 2.30배 차이가 관찰됨. 작은 글자·좁은 bbox·언어별 정확도 확인 후 선택 |
| 2 | 선택한 해상도에서 Qwen3 배치 1·2·3·4를 짧게 측정 | 24GB 4090의 *reserved* VRAM과 입력/초 확인. Qwen2.5의 배치 32를 이식하지 않음 |
| 3 | 문항별 입력을 여러 GPU에 나눠 실행 | 같은 GPU 한 대의 처리량을 기준으로 거의 GPU 수만큼 완료 시간 단축을 목표로 함 |
| 이후 | 동일 이미지의 vision 특징 재사용, vLLM, FA2 등 별도 런타임 | 효과·출력 동등성을 **각각** 측정해야 함. 특히 DeepStack이 있어 이미지 특징 캐시는 현재 러너의 단순 옵션이 아님. Qwen은 [vLLM을 빠른 배포 경로로 안내](https://github.com/QwenLM/Qwen3-VL/blob/main/README.md#deployment)하지만 이 프로젝트의 수치는 아직 없음 |

첫 세 항목도 **한 번에 함께 변경하면 어떤 조치가 빨라졌는지 분리할 수 없다**. 정확도를 비교할 본 실험에서는 모델 revision·이미지 크기·추론 백엔드·배치를 결과 계약에 남겨야 한다.

### RTX 4090 한 대와 여러 대

- RTX 4090은 **24GB VRAM/장**이다. Qwen3 배치 3의 B200 MIG 최대 *allocated*가 18.2GiB였으므로 탑재 가능성은 있지만 4090에서 *reserved*와 런타임 여유까지 확인해야 한다. Qwen2.5의 배치 32는 B200 MIG에서 최대 39.4GiB였으므로 4090에 가져올 수 없다. [NVIDIA RTX 4090 사양](https://images.nvidia.com/aem-dam/Solutions/geforce/ada/nvidia-ada-gpu-architecture.pdf).
- 4090 여러 개를 **한 인스턴스**에서 빌리면 저장소·데이터·가중치를 한 번 준비하고 GPU당 모델 프로세스를 하나씩 띄운다. **인스턴스 여러 개**면 각 인스턴스에 준비·결과 수집이 필요하다. GPU들이 동일한 입력을 실행하지 않도록 나눈다는 점은 같다. Vast.ai는 한 실행 인스턴스에 하나 이상의 GPU를 할당한다. [Vast.ai 자원 할당 문서](https://docs.vast.ai/guides/instances/docker-environment).
- 4대라면 단순 평균 **25,785회/장**, 8대라면 **12,893회/장**이다. 이미지 크기와 질문 길이가 달라 실제 작업시간은 균등하지 않을 수 있으므로 완료 시간이 가장 긴 샤드가 전체 시간을 정한다. 4개·8개 GPU에서의 정확한 종료 시간은 **Qwen3 4090 대표 입력의 처리량·VRAM 측정 후** 계산한다.

## 5. 실제 실행을 위해 필요한 준비

1. **실험 계약 고정:** Qwen3-VL-8B revision, 프롬프트, 이미지 예산, BF16·SDPA, batch, 결과 파서와 label scoring을 고정한다. 이미지 예산을 바꾸면 2MP 결과와 1MP 결과를 섞지 않는다. 작은 GUI 글자·좁은 GT bbox·네 언어를 포함한 표본에서 먼저 정확도를 확인한다.
2. **러너 준비:** [6×6 러너](../01_code/src/mpr_crosslocale/inference/run_cross_locale.py)는 현재 배치/샤드 입력을 지원하지 않고 Qwen3 설정도 4B만 있다. [REL 러너](../01_code/src/mpr_crosslocale/inference/run_rel_followup.py)는 Qwen3 배치 추론을 아직 허용하지 않는다. [위치 파일럿 러너](grounding_eval/run_qwen3_orc_element_pilot.py)는 12개 파일럿에 한정된다. 각각 Qwen3-8B 전체 실행, 고정 `shard_index/num_shards`, 재개, 별도 출력 경로와 결과 병합 검증이 필요하다.
3. **데이터 준비:** 6×6 원본 manifest·이미지는 현재 로컬 `01_code/data`에 없다. 고정 source lock에서 다시 준비해야 한다. REL bundle·이미지는 현재 로컬에 있다. 위치 찾기 본 분석 158문항의 짧은 기준 요소 설명은 파일럿 12문항용 [설명 목록](grounding_eval/pilot_referent_phrases.json)에서 확장해야 한다.
4. **4090 짧은 계측:** 한 장비에서 대표 GUI 화면 몇 개를 배치 1·안전한 배치 크기와 1MP·2MP로 실행해 입력당 시간, vision/언어 모델 시간, *allocated/reserved* VRAM, 출력 정답을 기록한다. 그 값으로 4대·8대 일정과 비용을 다시 계산한다. 현재 보고서의 Qwen3/B200 파일럿 시간을 4090 속도라고 부르지 않는다.
5. **작업 분할:** 문항 ID의 안정적인 해시 등으로 샤드를 만들고 O/R/C/F와 같은 문항의 화면을 한 샤드에 두어 paired 분석과 중복 입력 재사용을 보존한다. GPU당 프로세스 하나·출력 파일 하나를 사용한다. 병합 시 계획한 입력 ID가 정확히 한 번씩 있고 모델·프롬프트·해상도 지문이 같은지 검사한다.

### 근거의 한계

- Qwen3의 4090 실측, 전체 6×6/REL 추론, grounding 158문항 본 분석은 **아직 없다**.
- Qwen3 1MP의 2.30배 개선은 한 배치에서만 관찰했고 보존된 원시 파일이 없다. 전체 속도나 정확도 유지의 증거로 쓰지 않는다.
- Qwen3 첫 forward 내부에서 vision encoder와 언어 모델 prefill의 시간 비율, SDPA의 실제 CUDA 커널은 아직 측정되지 않았다. 구조 분석은 유력한 기전이며 **확정된 원인별 초 단위 분해가 아니다**.
- 과거 4090/B200 비교와 Qwen2.5/Qwen3 파일럿 비교는 배치·프롬프트·환경 등 여러 변수가 다르다. 장비 또는 모델 한 변수의 인과 효과로 제시하지 않는다.
