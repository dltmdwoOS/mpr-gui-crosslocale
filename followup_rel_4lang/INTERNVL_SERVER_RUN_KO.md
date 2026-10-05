# 현재 연구실 서버에서 InternVL2.5-8B REL 4언어 실험 실행하기

Full 추론을 완료했다. 결과와 Git 복원법은 [InternVL 결과 안내](INTERNVL_RESULTS_KO.md)에 있다.

2026-10-05 기준, 기존 실험의 `OpenGVLab/InternVL2_5-8B`를 동일한 고정
revision `e9e4c0dc1db56bfab10458671519b7fa3dd29463`으로 준비했다.
모델 설정은 [`01_code/configs/models/internvl2_5_8b.yaml`](../01_code/configs/models/internvl2_5_8b.yaml)이다.
BF16, 양자화 없음, eager attention, 448px 동적 타일 최대 7개와 thumbnail,
greedy 생성 최대 2토큰을 사용한다. InternVL 어댑터의 batch size는 1이다.

현재 서버의 `.venv`에 필요한 의존성이 설치돼 있고, 모델 snapshot은 개인 캐시
`/home/jovyan/seungjae/.cache/huggingface/hub/models--OpenGVLab--InternVL2_5-8B/snapshots/e9e4c0dc1db56bfab10458671519b7fa3dd29463`
에 있다. 가중치 4개 shard는 약 15.04GiB이며, 이 캐시는 Git에 포함되지 않는다.
현재 서버에서는 오프라인으로 재사용한다. 새 서버에서 실행할 경우 고정 revision의
모델을 개인 캐시에 먼저 내려받아야 한다.

## 준비 상태

| 항목 | 확인 결과 |
|---|---|
| 환경 | 저장소 내부 `.venv`, Python 3.11, CUDA PyTorch 2.9.1+cu130, Transformers 4.57.6, Accelerate 1.15.0, timm 1.0.30, SentencePiece 0.2.0 |
| GPU | NVIDIA B200 MIG 2g.45gb, CUDA 가용 VRAM 44.25GiB |
| 모델 | 고정 revision snapshot 전체 캐시 및 오프라인 로딩 성공 |
| 데이터 | 366문항의 이미지 1,464개 검증 완료 |
| 관련 CPU 테스트 | 25개 통과 |
| 전체 dry-run | 조건 23,424행, 실제 추론 18,432회, 재사용 4,992행, 원본 문제 표시 400행 |
| GPU smoke | dependent/independent 각 1문항, 실제 추론 80회, 결과 128행 모두 성공, 파싱 실패 0 |
| full | 실제 추론 18,432개·조건 결과 23,424행 모두 성공, 파싱 실패 0 |

dry-run 결과는 `results/preflight/internvl2_5_8b/dry_run_plan.json`, smoke 결과는
`results/smoke/internvl2_5_8b/summary.json`과 `results/logs/internvl2_5_smoke.log`에 있다.
모두 현재 서버의 Git 제외 출력이다. smoke의 80개 예측에서 label score가 기록됐고,
실행 실패와 파싱 실패가 없었다. 이 점검은 전체 실험 결과를 대신하지 않는다.

## full 재개

저장소 최상위에서 다음 명령을 실행하면 현재 서버의 완료된 full을 같은 계약으로
재개하며 성공한 예측을 건너뛴다. 새 clone에서는 먼저
[결과 안내](INTERNVL_RESULTS_KO.md)에 따라 두 JSONL을 복원한다.
개인 캐시, 오프라인 모드, CPU 스레드 3개
제한과 `.venv`는 [`internvl_server_env.sh`](internvl_server_env.sh)가 설정한다.
Qwen full과 출력 디렉터리가 분리돼 있다. 현재 서버에서 다른 GPU 작업과 동시에
실행하지 않는다.

```bash
cd /home/jovyan/seungjae/mpr-gui-crosslocale
source followup_rel_4lang/internvl_server_env.sh
mkdir -p followup_rel_4lang/results/logs
RUN_LOG="followup_rel_4lang/results/logs/internvl_full_$(date -u +%Y%m%dT%H%M%SZ).log"
nohup "$PYTHON_BIN" -u followup_rel_4lang/run_inference.py \
  --model-config 01_code/configs/models/internvl2_5_8b.yaml \
  --batch-size 1 \
  --output-dir followup_rel_4lang/results/full/internvl2_5_8b \
  --resume > "$RUN_LOG" 2>&1 < /dev/null &
echo "PID=$! log=$RUN_LOG"
```

진행 로그는 `tail -f "$RUN_LOG"`로 확인한다. 중단 후 같은 명령을 실행하면
성공한 예측을 건너뛰며 재개한다. 코드·데이터·모델 설정·배치 크기가 바뀌면
기존 출력과 섞을 수 없으므로 새 출력 디렉터리를 사용한다. 끝나면
`results/full/internvl2_5_8b/summary.json`의 상태와 파싱 실패 수를 확인한다.

전체 분석의 알려진 원본 문제 14문항·100언어쌍에 해당하는 400행은 추론하되
주 분석에서 제외한다. `human_reviewed`와 `screenshot_verified`는 false이며,
최종 GLMM·bootstrap 신뢰구간은 별도 분석 단계다.
