# MPR-GUI Cross-Locale Evaluation

MPR-GUI-Bench의 질문 언어와 GUI 언어를 독립적으로 조합해 Qwen-VL과
InternVL2.5를 평가하는 코드입니다. 이 저장소는 모델 학습 코드가 아니라,
사전 학습된 모델을 이용한 inference 및 평가 코드입니다.

## 평가 구성

- 언어: `en`, `zh`, `fr`, `ru`, `ja`, `th`
- 1차 평가 dimension: `wf`, `wi`, `au`, `ap`, `ael`, `rel`
- 질문 언어와 GUI 언어의 6x6 조합
- semantic item 기준 고정 seed sampling
- A/B/C/D 생성 결과와 next-token label score 저장
- JSONL 중단 후 재실행
- 언어 조합 및 dimension별 결과 요약

원본 MPR-GUI 데이터, 생성된 manifest, 모델 checkpoint와 실험 결과는
저장소에 포함하지 않습니다.

## Vast.ai 준비

다음 조건을 만족하는 PyTorch 템플릿을 사용합니다.

- NVIDIA GPU
- GPU 메모리 16GB 이상, Qwen2.5-VL-7B/InternVL2.5-8B는 24GB 이상 권장
- 저장 공간 40GB 이상 권장
- Python 3.10 이상
- CUDA를 지원하는 `torch`와 이에 맞는 `torchvision`

Vast.ai 템플릿에 설치된 CUDA PyTorch를 유지해야 합니다. CPU용 PyTorch를
별도로 설치하면 모델이 GPU를 사용하지 못할 수 있습니다.

## 1. 저장소 받기

```bash
git clone https://github.com/dltmdwoOS/mpr-gui-crosslocale.git
cd mpr-gui-crosslocale
```

템플릿의 PyTorch를 그대로 사용하거나, 격리 환경이 필요하면 system package를
공유하는 virtual environment를 만듭니다.

```bash
python -m venv --system-site-packages .venv
source .venv/bin/activate
```

## 2. 환경 설치

```bash
cd 01_code
bash scripts/setup_vast.sh
bash scripts/vast_preflight.sh
```

`setup_vast.sh`는 InternVL2.5 tokenizer에 필요한 `protobuf`와 호환되는
`sentencepiece==0.2.0`도 현재 활성화된 venv에 설치합니다. 이미 환경을 만든
경우에는 다음 명령으로 의존성만 맞출 수 있습니다.

```bash
python -m pip install -e ".[models]"
```

`vast_preflight.sh`는 CUDA 연결, GPU 메모리, 디스크 공간, Qwen3-VL 클래스와
InternVL2.5 의존성 지원 여부를 확인합니다. InternVL 설정을 검사할 때도 모델
가중치는 다운로드하지 않습니다.

InternVL2.5를 실행할 인스턴스에서는 다음처럼 설정 파일을 지정합니다.

```bash
MODEL_CONFIG=configs/models/internvl2_5_8b.yaml \
bash scripts/vast_preflight.sh
```

## 3. 데이터 준비

```bash
bash scripts/prepare_vast_data.sh
```

이 명령은 다음 작업을 수행합니다.

1. 고정된 MPR-GUI-Bench revision 다운로드
2. 공식 QA 파일 다운로드
3. release 구조 검사
4. `data/manifests/mpr_gui_manifest.jsonl` 생성
5. 언어별 parallel item과 이미지 경로 검증

원본 데이터는 약 2.6GB이며, 다운로드 상태에 따라 시간이 걸릴 수 있습니다.

## 4. Vast.ai smoke test

```bash
bash scripts/run_vast_smoke.sh
```

smoke test 조건은 다음과 같습니다.

- 모델: `Qwen/Qwen3-VL-4B-Instruct`
- 모델 revision: `ebb281ec70b05090aa6165b016eac8ec08e71b17`
- 질문/GUI 방향: `en:ja`, `ja:en`
- semantic item: 2개
- 총 평가: 4건
- dimension: `wf`, `wi`, `au`, `ap`, `ael`, `rel`
- attention: PyTorch SDPA
- label scoring 사용

스크립트는 결과 4건이 모두 `success`인지 확인한 뒤 요약 파일을 만듭니다.

```text
results/raw/vast_smoke_qwen3_vl_4b_vast.jsonl
results/raw/vast_smoke_qwen3_vl_4b_vast_failures.jsonl
results/summaries/vast_smoke_qwen3_vl_4b_vast.json
results/summaries/vast_smoke_qwen3_vl_4b_vast.csv
```

failure JSONL은 오류가 없으면 생성되지 않을 수 있습니다.

### InternVL2.5 8B smoke test

모델 파일을 persistent Hugging Face cache에 미리 내려받으려면 GPU 인스턴스에서
다음 명령을 직접 실행합니다. 약 8B 규모의 가중치를 다운로드하므로 코드
설치나 preflight에는 이 명령이 포함되지 않습니다.

```bash
export HF_HOME=/path/to/persistent-volume/huggingface
hf download OpenGVLab/InternVL2_5-8B \
  --revision e9e4c0dc1db56bfab10458671519b7fa3dd29463
```

미리 다운로드하지 않아도 첫 smoke test에서 같은 revision을 Hugging Face
cache로 자동 다운로드합니다.

```bash
MODEL_CONFIG=configs/models/internvl2_5_8b.yaml \
MODEL_TAG=internvl2_5_8b \
bash scripts/run_vast_smoke.sh
```

InternVL 설정은 Qwen2.5-VL-7B 실험과 동일하게 label-only prompt, greedy
generation, `max_new_tokens=2`, 최대 2048 visual tokens를 사용합니다.
InternVL2.5 remote backend의 비-FlashAttention 경로는 SDPA가 아닌 eager이므로
실제 attention backend는 결과 metadata에 `eager`로 기록됩니다.

Transformers 4.57.x에서는 이 checkpoint의 legacy tokenizer metadata 때문에
`AutoTokenizer`가 tokenizer 대신 `False`를 반환할 수 있습니다. 어댑터는 이를
검출하고 pinned remote tokenizer class와 고정 special-token ID를 사용해
tokenizer를 다시 구성합니다.

또한 InternLM2 remote code는 legacy tuple KV cache를 기대하므로, 어댑터는
Transformers 4.57의 기본 `DynamicCache` 생성을 비활성화하고 기존 cache 형식을
사용합니다. KV cache 자체는 활성 상태로 유지됩니다.

## 5. 6x6 평가

6x6 평가에서는 sample size를 명시해야 합니다.

```bash
SAMPLE_SIZE=1 bash scripts/run_vast_6x6.sh
```

`SAMPLE_SIZE=1`은 semantic item 1개를 36개 언어 조합으로 평가하므로 총
36 evaluations입니다.

```text
1 semantic item x 36 language pairs = 36 evaluations
```

smoke 결과를 확인한 뒤 단계적으로 크기를 늘립니다.

```bash
SAMPLE_SIZE=5 bash scripts/run_vast_6x6.sh
SAMPLE_SIZE=12 bash scripts/run_vast_6x6.sh
SAMPLE_SIZE=60 bash scripts/run_vast_6x6.sh
```

InternVL2.5 8B는 같은 스크립트에 모델 설정과 tag를 지정합니다.

```bash
MODEL_CONFIG=configs/models/internvl2_5_8b.yaml \
MODEL_TAG=internvl2_5_8b \
SAMPLE_SIZE=1 \
bash scripts/run_vast_6x6.sh

MODEL_CONFIG=configs/models/internvl2_5_8b.yaml \
MODEL_TAG=internvl2_5_8b \
SAMPLE_SIZE=60 \
bash scripts/run_vast_6x6.sh
```

`SAMPLE_SIZE=60`은 총 2,160 evaluations입니다.

```text
60 semantic items x 36 language pairs = 2,160 evaluations
```

출력 파일 이름에는 설정 파일명 또는 `MODEL_TAG`가 들어갑니다. 예를 들어
InternVL 실행의 기본 출력은 다음과 같습니다.

```text
results/raw/vast_6x6_internvl2_5_8b.jsonl
results/raw/vast_6x6_internvl2_5_8b_failures.jsonl
results/summaries/vast_6x6_internvl2_5_8b.json
results/summaries/vast_6x6_internvl2_5_8b.csv
```

동일한 명령을 다시 실행하면 `--resume`에 의해 이미 성공한 항목은 건너뜁니다.
서로 다른 모델에 같은 `MODEL_TAG` 또는 `OUTPUT` 경로를 사용하면 안 됩니다.

## 결과 필드

주요 JSONL 필드는 다음과 같습니다.

- `question_language`: 질문 언어
- `gui_language`: GUI 이미지 언어
- `dimension`: 평가 dimension
- `generated_text`: 모델이 생성한 응답
- `parsed_generated_label`: 생성 응답에서 추출한 A/B/C/D
- `scored_predicted_label`: label score 기준 예측
- `gold_label`: 정답
- `correct`: 정답 여부
- `label_probabilities`: A/B/C/D 확률
- `runtime_ms`: 항목별 추론 시간
- `status`: `success` 또는 `failed`

`runtime_ms`는 항목별 이미지/prompt 전처리, generation, next-token label
scoring을 포함합니다. 모델 로딩, 실행 메타데이터 수집, 결과 파일 기록과
요약 생성은 포함하지 않습니다. Label score는 generation 첫 step의 raw
logits를 사용하므로 별도의 중복 model forward를 실행하지 않습니다.
결과 metadata에는 attention backend, GPU, CUDA runtime, PyTorch와
Transformers 버전이 자동으로 기록됩니다.

## 비용과 파일 보존

Vast.ai 인스턴스를 종료하거나 삭제하면 로컬 파일이 사라질 수 있습니다.
실험 중에는 persistent volume을 사용하거나 `results/`를 주기적으로 내려받아야
합니다. 6x6 실험은 sample size에 따라 실행 시간과 GPU 비용이 크게 증가하므로
4건 smoke test를 통과한 뒤 규모를 늘립니다.

## 로컬 코드 검증

모델을 불러오지 않는 코드 테스트는 다음 명령으로 실행합니다.

```bash
pip install -e ".[dev]"
pytest -q ../02_tests/tests
ruff check src ../02_tests/tests build_pilot.py
```

## 데이터 라이선스

저장소 코드는 MIT 라이선스입니다. MPR-GUI-Bench 데이터는 별도의
`CC-BY-NC-4.0` 조건을 따릅니다. 자세한 내용은 `THIRD_PARTY_DATA.md`를
확인합니다.

## 변경 기록

- 2026-07-24: generation 첫 step logits를 label scoring에 재사용해 중복
  전처리와 model forward를 제거했습니다. 동일한 72건에서 예측 결과는
  유지됐고 항목별 추론은 약 2.1배 빨라졌습니다. Attention backend는
  FlashAttention으로 변경하지 않고 SDPA를 계속 사용합니다.
