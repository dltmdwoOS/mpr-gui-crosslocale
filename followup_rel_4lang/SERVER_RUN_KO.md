# 현재 연구실 서버에서 Qwen2.5-VL REL 4언어 실험 실행하기

2026-09-29에 `followup-rel-4lang-inference` 브랜치의 `9bc4235`를 바탕으로
Qwen 배치 구현과 실제 배치 크기 실험을 완료했다. 현재 권장 배치는 **32**다.
명령은 저장소 최상위 `/home/jovyan/seungjae/mpr-gui-crosslocale`에서 실행한다.

현재 실행 범위는 Qwen2.5-VL-7B-Instruct다. 두 모델을 실행하는
`run_b200.sh` 대신 Qwen 설정을 지정해 `run_inference.py`를 직접 호출한다.

이전에 사용자가 실행한 batch 1 full은 SIGINT로 정상 중지했고, 실제 추론
1,951건의 기록을 보존했다. 새 batch 32 full은 이후 완료됐다. 실행 실패 없이
실제 입력 18,432개와 조건 결과 23,424행을 저장했고, 파싱 실패는 2건이다.
완료 기록은 `results/setup_checks/qwen_full_completion.json`에 있다.
`qwen_batch_readiness.json`과 `qwen_readiness.json`은 실행 전 준비 기록이다.
원격 Git의 결과 범위와 압축 파일 복원법은 [Qwen 결과 안내](QWEN_RESULTS_KO.md)를 본다.

## 설치 및 검증 상태

| 항목 | 확인 결과 |
|---|---|
| Python | 3.11.11 |
| GPU | NVIDIA B200 MIG 2g.45gb, CUDA에서 44.25GiB, compute capability 10.0 |
| CPU / RAM 할당 | 3 cores / 45GiB |
| CUDA PyTorch | 기존 `/opt/conda`의 torch 2.9.1+cu130 / torchvision 0.24.1+cu130 재사용 |
| 저장소 내부 환경 | `.venv`, `--system-site-packages` 방식 |
| 모델 의존성 | Transformers 4.57.6 / Accelerate 1.15.0 / qwen-vl-utils 0.0.14 |
| Qwen 가중치 | 고정 revision `cc594898137f460bfe9f0759e9844b3ce807cfb5`, 개인 캐시의 5개 shard 약 15.45GiB |
| 고정 질문 데이터 | 묶음 SHA-256 확인 완료, 366문항 / 23,424조건 행 |
| 전체 이미지 | 1,464개, 약 1.277GiB; 다운로드 / SHA-256 / 실제 디코딩 검증 완료 |
| 배치 회귀 테스트 | 25개 통과: 입력·출력·점수 대응, OOM 분할, 재개 계약 포함 |
| Qwen 전체 dry-run | 실제 입력 18,432개 / batch 32에서 576개 배치 |
| Qwen batch 32 smoke | 실제 입력 80개 / 3개 배치 / 결과 128행 성공, 실행·파싱 실패 0 |
| smoke 답 비교 | 기존 batch 1 smoke 80개와 생성 답·scored label 모두 일치 |
| Qwen batch 32 full | 실제 입력 18,432개 / 조건 23,424행 모두 성공 상태 / 파싱 실패 2 |

공유 Python의 Transformers 5.x와 어댑터가 요구하는 4.57.x가 달라
저장소 내부 `.venv`에 의존성을 설치했다. CUDA PyTorch는 기존 설치를 재사용한다.
SentencePiece 0.2.0 / timm 1.0.30 / einops 0.8.2도 설치돼 있다.
질문 구조와 checksum은 고정 lock과 일치하며 현재 이미지 감사 기록은
`results/setup_checks/current_data_audit.json`에 있다.

캐시된 Qwen의 단일 입력 및 기존 batch 1 smoke도 통과한 상태다.
InternVL 가중치나 GPU 추론은 이번 작업 범위에 포함하지 않는다.

## 매번 사용할 환경

새 셸에서도 아래 설정을 적용한다. 개인 캐시, CPU 스레드 3개, `.venv`,
기존 Qwen 캐시의 오프라인 재사용이 설정된다.
`PYTHONNOUSERSITE=1`은 공유 홈의 사용자 패키지가 환경에 끼어드는 것을 막는다.

```bash
cd /home/jovyan/seungjae/mpr-gui-crosslocale
source followup_rel_4lang/qwen_server_env.sh
```

현재 서버에는 이미 설치돼 있어 설치를 반복할 필요가 없다.
같은 CUDA PyTorch가 제공되는 서버에서 처음 설치할 때만 개인 캐시와
`PYTHONNOUSERSITE` 설정을 적용한 뒤 다음을 실행한다.

```bash
python -s -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -e '01_code[models]' 'pytest>=8,<9'
```

## 이미지 준비와 실행 계획

현재 이미지와 전체 계획 검증은 완료했다. 새 clone에서는 먼저
`python followup_rel_4lang/data_bundle.py unpack`을 실행한다.
이미지가 크기·checksum 검사에 통과하면 다운로드를 건너뛴다.

```bash
python followup_rel_4lang/data_bundle.py fetch-images --workers 3
python followup_rel_4lang/data_bundle.py verify

"$PYTHON_BIN" followup_rel_4lang/run_inference.py \
  --model-config 01_code/configs/models/qwen2_5_vl_7b.yaml \
  --batch-size 32 \
  --output-dir followup_rel_4lang/results/preflight/qwen2_5_vl_7b_batch32 --dry-run
```

계획은 `results/preflight/qwen2_5_vl_7b_batch32/dry_run_plan.json`에 저장했다.
동일 문항·언어쌍 안의 동일 입력만 재사용해 23,424행을 실제 입력 18,432개로
처리한다. 불일치 12언어쌍은 주 분석, 일치 4언어쌍은 기준 조건이다.
이 설계에는 `01_code/scripts/run_vast_6x6.sh` 대신 이 폴더의 러너를 사용한다.

## 배치 크기 실험 결과

고정 seed 42로 canonical 입력 32개를 뽑아 모든 배치에서 같은 입력을
비교했다. 이미지 전처리·greedy generation·first-token label scoring을 포함한
처리량이다. 별도로 전체 데이터에서 가장 긴 질문(255 text tokens)과 가장 큰
전처리 이미지(2,666 visual tokens)를 결합한 메모리 검사 입력을 사용했다.
합성 입력의 결과는 실험 예측에 섞지 않는다. 해상도·프롬프트·가중치·BF16·
최대 생성 2토큰 설정은 유지했다.

| 배치 | 표본 처리량 (입력/초) | 두 검사의 최대 reserved VRAM (GiB) | 결과 |
|---:|---:|---:|---|
| 1 | 0.4919 | 16.732 | 통과 |
| 2 | 0.5850 | 17.602 | 통과 |
| 4 | 0.6838 | 20.896 | 통과 |
| 8 | 0.7767 | 24.617 | 통과 |
| 16 | 0.7970 | 32.365 | 통과 |
| **32** | **0.8248** | **39.428** | **선택** |
| 64 | — | — | 메모리 부족 진단 중 NVML 오류 |

32는 측정한 안전 배치 중 가장 빨랐고, batch 1 대비 1.677배의 처리량이었다.
최대 입력에서 allocated는 35.335GiB / reserved는 39.428GiB로,
44.25GiB 중 reserved 기준 약 4.82GiB(10.9%) 여유가 있다.
64에서 메모리 한계에 도달해 128은 검사하지 않았다. 표본 속도이므로 full의
전체 시간을 확정하는 값은 아니다.

BF16 배치 계산에서는 답이 달라질 수 있다. 이번 표본에서는 batch 2·4·8이
batch 1과 각 1건 달랐고, 선택한 32는 32건 모두 생성 답·scored label이 같았다.
배치 크기를 run contract에 고정해 다른 배치의 결과를 섞지 않는다.

MIG 서버에서 64의 오류는 `NVML_SUCCESS == r INTERNAL ASSERT FAILED`였다.
[PyTorch 2.9.1의 CUDA allocator](https://github.com/pytorch/pytorch/blob/v2.9.1/c10/cuda/CUDACachingAllocator.cpp)
소스에서 메모리 할당 실패 후 OOM 진단 과정의 NVML 조회가 이 assertion을
발생시킬 수 있음을 확인했다. 해당 오류와 일반 CUDA OOM 모두 배치를
나누어 재시도하도록 처리했다. 다른 RuntimeError는 실행 실패로 남긴다.

원본 측정과 오류 로그는 `results/batch_benchmark/qwen2_5_vl_7b/summary.json`과
`results/logs/qwen_batch_benchmark.log`에 있다. 오류 처리만 수정한 뒤 기존
1~32 측정과 로그의 64 실패를 재사용해 결과를 확정했다. 원본 코드 지문은
유지하고 수정 내역은 보고서의 `finalization`에 기록했다.

배치 실험은 full과 별도 실행한다. 다시 비교할 필요가 있을 때 새 output을
사용하면 다음 명령으로 실행할 수 있다. 이 명령은 full을 시작하지 않는다.

```bash
BATCH_CHECK_DIR="followup_rel_4lang/results/batch_benchmark/qwen2_5_vl_7b_$(date -u +%Y%m%dT%H%M%SZ)"
"$PYTHON_BIN" -u followup_rel_4lang/benchmark_batch.py \
  --output-dir "$BATCH_CHECK_DIR" --samples 32 --max-batch-size 128 --memory-fraction 0.90
```

## 배치 32 smoke

dependent / independent 각 1문항의 모든 조건을 실제 GPU에서 검사했다.
실제 입력 80개를 32·32·16의 3개 배치로 처리했고 결과 128행이 모두 성공했다.
모든 예측에서 label score를 반환했고 파싱 실패가 없었다.
배치 추론 시간 합계는 95.339초이며 모델 로딩·검증 시간은 포함하지 않는다.
기존 batch 1 smoke와 생성 답·scored label이 80개 모두 일치했다.

결과는 `results/smoke/qwen2_5_vl_7b_batch32/summary.json`에 있다.
같은 환경에서 아래 명령을 다시 실행하면 성공한 예측을 재사용한다.

```bash
"$PYTHON_BIN" followup_rel_4lang/run_inference.py \
  --model-config 01_code/configs/models/qwen2_5_vl_7b.yaml \
  --batch-size 32 \
  --output-dir followup_rel_4lang/results/smoke/qwen2_5_vl_7b_batch32 \
  --max-items 2 --resume
```

러너는 left padding으로 입력을 묶고 입력별 first-token logits를 대응시킨다.
각 예측에 실제 `batch_size`, `batch_id`, `batch_runtime_ms`를 기록한다.
`inference_runtime_ms`는 배치 시간을 입력 수로 나눈 값이고,
재사용 조건의 `runtime_ms`는 0이다. 예상 밖의 OOM이 나면 해당 배치를
반씩 나눠 재시도하며 복구한 입력은 성공 결과로 저장한다.

## full 완료 결과와 재개 명령

현재 `results/full/qwen2_5_vl_7b_batch32/`는 완료된 출력 디렉터리다.
아래 명령은 이 서버에서 같은 계약으로 재개하며 완료된 입력은 건너뛴다.
처음부터 다시 실험하려면 별도의 새 출력 디렉터리를 지정한다.
코드·의존성·데이터·모델 설정·배치 크기를 유지해야 기존 출력을 재개할 수 있다.
원격 Git에는 큰 JSONL을 `.jsonl.gz`로 올렸으므로 새 clone에서 재개하려면
[결과 안내](QWEN_RESULTS_KO.md)에 따라 두 JSONL을 먼저 복원한다.

현재 PATH에 tmux가 없어 nohup으로 로그를 남기는 명령을 안내한다.
사용자 셸에서 실행한다.

```bash
cd /home/jovyan/seungjae/mpr-gui-crosslocale
source followup_rel_4lang/qwen_server_env.sh
mkdir -p followup_rel_4lang/results/logs
RUN_LOG="followup_rel_4lang/results/logs/qwen_full_batch32_$(date -u +%Y%m%dT%H%M%SZ).log"
nohup "$PYTHON_BIN" -u followup_rel_4lang/run_inference.py \
  --model-config 01_code/configs/models/qwen2_5_vl_7b.yaml \
  --batch-size 32 \
  --output-dir followup_rel_4lang/results/full/qwen2_5_vl_7b_batch32 \
  --resume > "$RUN_LOG" 2>&1 < /dev/null &
echo "PID=$! log=$RUN_LOG"
```

진행 상황은 `tail -f "$RUN_LOG"`로 확인한다. 출력은 위의 새 full 경로에 저장한다.
smoke·벤치마크·full을 동시에 실행하지 않는다.

실행 실패가 연속 3회 발생하면 중지하며 `predictions.jsonl`에 오류를 남긴다.
알려진 원본 문제 14문항 / 100언어쌍의 400행은 추론 후 주 분석에서 제외된다.
`human_reviewed`와 `screenshot_verified`는 false를 유지한다.
출력 `summary.json`은 기술 통계이며 최종 GLMM / bootstrap 분석은 별도 작업이다.
