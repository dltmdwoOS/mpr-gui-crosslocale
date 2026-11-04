# Vast.ai RTX 4090 한 장에서 Qwen3 지연 확인

목적: 기존 B200 MIG에서 `booking_10`의 Qwen3-VL-8B **O/R/C 배치 3·2MP가 161.289초** 걸린 이유를 4090에서 다시 측정한다. [기존 원시 예측](results/grounding_pilot_qwen3_8b_orc_element_only/predictions.jsonl)과 같은 모델 revision·프롬프트·이미지·BF16·SDPA·greedy를 쓴다. 새 [계측 도구](grounding_eval/benchmark_qwen3_runtime.py)는 총시간에 더해 vision encoder, 언어 모델 첫 처리, 이후 토큰 생성 시간을 나눠 기록한다. **계측 hook을 추가했으므로 이전 161.289초와 완전히 같은 실행 경로는 아니다.** 이미지 해시, 격자, 프롬프트 토큰 수를 함께 비교한다.

## 4090 인스턴스에서 준비

Vast.ai에서 **RTX 4090 1장, VRAM 24GB, 충분한 CPU RAM·디스크**가 있는 PyTorch/CUDA 템플릿을 선택한다. 설치·모델·출력 때문에 디스크는 여유 있게 잡는다. 한 장만 필요한 검사이므로 8장 인스턴스는 아직 빌릴 이유가 없다. 기존 [Vast 준비 안내](../01_code/README.md#vastai-준비)도 참고한다.

컨테이너의 개인 작업 디렉터리 예시를 `/workspace`로 적었다. 실제 배치 경로가 다르면 바꾼다. 모델은 공개 체크포인트이고 고정 revision을 다운로드한다.

```bash
cd /workspace
git clone --branch followup-rel-4lang-inference https://github.com/dltmdwoOS/mpr-gui-crosslocale.git
cd mpr-gui-crosslocale

export XDG_CACHE_HOME=/workspace/.cache
export HF_HOME=/workspace/.cache/huggingface
export TORCH_HOME=/workspace/.cache/torch
export PIP_CACHE_DIR=/workspace/.cache/pip
export OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3

python -m venv --system-site-packages .venv
source .venv/bin/activate
cd 01_code
bash scripts/setup_vast.sh
python -m pip install 'transformers==4.57.6' 'qwen-vl-utils==0.0.14'
cd ..

python followup_rel_4lang/data_bundle.py unpack
MODEL_SNAPSHOT="$(hf download Qwen/Qwen3-VL-8B-Instruct --revision 0c351dd01ed87e9c1b53cbc748cba10e6187ff3b)"
```

`unpack`은 질문·annotation 메타데이터를 푼다. 계측 도구는 선택된 **태국어 `booking_10` 이미지 한 장만** 고정 HF revision에서 받아 SHA-256을 검사한다. 전체 1.3GiB REL 이미지를 받을 필요는 없다. 이미지를 직접 다른 경로로 옮기지 않는다. 로컬 결과 파일에는 모델 다운로드 경로나 인증 정보를 기록하지 않는다.

### GPU 없이 입력 확인

```bash
python followup_rel_4lang/grounding_eval/benchmark_qwen3_runtime.py \
  --model-path "$MODEL_SNAPSHOT" --preflight-only
```

기존 2MP 기록과 `image_sha256=3f2fcbb5…`, `image_grid_thw=[1,134,60]`, 시각 토큰 **2,010**, `prompt_tokens=[2131,2141,2129]`가 일치해야 한다. `--preflight-only`는 GPU 모델을 적재하지 않는다.

### 실제 한 배치 측정

```bash
python followup_rel_4lang/grounding_eval/benchmark_qwen3_runtime.py \
  --model-path "$MODEL_SNAPSHOT" --batch-size 3 --max-pixels 2097152 \
  --output followup_rel_4lang/results/runtime_probe/rtx4090_booking10_2mp_b3.json
```

주요 필드는 `generate_s`(배치 3 전체), `prefill_forward_s`(첫 forward), `vision_forward_s`(이미지 인코딩), `language_prefill_s`(언어 모델 첫 처리), `language_decode_s`(후속 생성), `peak_allocated_gib`와 `peak_reserved_gib`다. `vision_forward_s`와 `language_prefill_s`의 합을 `prefill_forward_s`에서 빼면 나머지 첫 forward 작업과 계측 오버헤드가 남는다. **이 숫자로 처음으로 병목을 분리**할 수 있다. 기존 B200의 동일 배치 기록은 총 161.289초, 첫 forward 158.519초, 후속 forward 2.601초, 최대 allocated 18.208GiB였다. [기존 파일럿 설명](grounding_eval/QWEN3_ORC_ELEMENT_PILOT_KO.md#왜-느렸나).

4090의 24GB에서 배치 3이 메모리 부족이면 `--batch-size 1`로 **O 조건 하나**를 먼저 계측한다. 이는 기존 3응답 배치와 직접 같은 시간 비교는 아니다.

```bash
python followup_rel_4lang/grounding_eval/benchmark_qwen3_runtime.py \
  --model-path "$MODEL_SNAPSHOT" --batch-size 1 --max-pixels 2097152 \
  --output followup_rel_4lang/results/runtime_probe/rtx4090_booking10_2mp_b1.json
```

2MP 배치 3이 성공했다면 해상도만 바꿔 1MP 한 배치를 선택적으로 비교할 수 있다. **1MP는 출력·정확도가 달라질 수 있는 별도 실험 설정**이다.

```bash
python followup_rel_4lang/grounding_eval/benchmark_qwen3_runtime.py \
  --model-path "$MODEL_SNAPSHOT" --batch-size 3 --max-pixels 1048576 \
  --output followup_rel_4lang/results/runtime_probe/rtx4090_booking10_1mp_b3.json
```

JSON 출력은 Git에서 기본적으로 제외된다. 인스턴스를 정리하기 전에 결과를 내려받는다. 원시 결과에는 배치별 O/R/C 점 출력과 GT 적중 여부도 들어 있다. `generate_s`가 기존 기록과 차이나면 먼저 `vision_forward_s`, `language_prefill_s`, 이미지 격자, PyTorch 버전, GPU 이름을 비교한다. 한 화면의 4090 결과로 **전체 6×6/REL의 평균 처리량을 확정하지는 않는다**.

## 8× RTX 4090을 빌렸을 때 실제 병렬성

**원리상 가능하지만 현재 코드를 그대로 8번 실행한다고 8배가 되지는 않는다.** 각 GPU에 Qwen3 모델을 한 벌씩 올리고 *서로 다른 입력*을 맡기는 독립 추론이 필요하다. 한 8-GPU 인스턴스에서 `CUDA_VISIBLE_DEVICES=0`부터 `7`까지 서로 다른 환경으로 8개 프로세스를 띄우면 각 프로세스의 `cuda:0`은 지정된 GPU 한 장을 뜻한다. 모델 하나가 4090 한 장에 들어가는지 먼저 위 계측에서 확인한다. `device_map=auto`로 모델 하나를 8장에 쪼개는 방식은 이 과제의 처리량을 8배로 만드는 방법이 아니다. Vast.ai는 한 인스턴스에 여러 GPU를 할당할 수 있지만 실제 8×4090 상품의 공급·CPU·RAM·디스크는 선택 시점에 확인해야 한다. [Vast.ai 인스턴스 자원 문서](https://docs.vast.ai/guides/instances/docker-environment), [상품 검색 안내](https://github.com/vast-ai/vast-cli/blob/master/vastai/SKILL.md).

현재 저장소에서 바로 가능한 수준은 다음과 같다.

| 경로 | 현재 상태 | 8-GPU 본 실행 전에 필요한 것 |
| --- | --- | --- |
| [6×6 러너](../01_code/src/mpr_crosslocale/inference/run_cross_locale.py) | `--resume`은 있지만 배치·샤드 옵션 없음; Qwen3 구성은 4B만 있음 | Qwen3-8B 설정, 입력 분할, GPU별 출력·병합 검증 |
| [REL O/R/C/F 러너](../01_code/src/mpr_crosslocale/inference/run_rel_followup.py) | Qwen2.5 배치 지원, Qwen3의 배치>1 차단; 샤드 옵션 없음 | Qwen3 배치 지원, 입력 분할, GPU별 출력·병합 검증 |
| [grounding 파일럿](grounding_eval/run_qwen3_orc_element_pilot.py) | 12문항 중 최대 12쌍의 파일럿만 실행 | 158문항의 기준 설명 준비, 본 실행 러너와 분할 |

세 실험의 계획 입력은 합계 **103,140회**이고 8개 GPU에 균등하면 약 **12,893회/장**이다. 실제 총시간은 `가장 오래 걸린 GPU의 샤드 시간 + 설치·합치기 시간`이다. **정확히 8.00배를 보장할 수 없고**, 이미지·언어·배치별 처리량, 공유 CPU/RAM/SSD, 호스트의 전력 제한을 같은 시점에 1개·8개 프로세스로 측정해야 한다. 4090 한 장 계측은 모델 탑재와 단일 처리량을 검증하는 첫 단계다. [전체 런타임 분석](QWEN_RUNTIME_REPORT_KO.md).
