# Qwen3 전체 실험: RTX 4090 한 장 실행 안내

갱신: 2026-11-07. 아래 명령은 **저장소 최상위**에서 실행한다. 서버에서 전체 실험을 시작하는 절차이며, 이 문서를 작성하면서 전체 추론을 실행하지 않았다. 6×6·REL·grounding을 **차례로** 실행해 모델 한 벌만 GPU에 올린다.

| 실험 | 입력/결과 규모 |
| --- | ---: |
| 6×6, 6개 차원 | 2,195문항 × 36언어 조합 = 79,020응답 |
| REL O/R/C/F | 366문항 × 16언어쌍 × 4조건 = 23,424행, 고유 추론 18,432회 |
| Grounding main O/R/C/F | 158문항 × 12불일치 언어쌍 × 4조건 = 7,584응답 |
| 합계 | 고유 추론 계획 105,036회; 과제 사이 추가 재사용 없음 |

모델은 Qwen3-VL-8B-Instruct 고정 revision, BF16·SDPA·2MP(`max_pixels=2097152`)이며 patch Conv3D 가중치에 **`channels_last_3d`**를 적용한다. 이 정책은 기존 4090 진단에서 확인한 Conv3D 병목을 피하기 위한 것이다. [기존 측정](QWEN3_RTX4090_RESULTS_KO.md). 전체 입력의 수치적 동등성을 보증하는 설정 변경은 아니므로 계약에 기록한다.

배치는 **4부터 검사하고 메모리 실패일 때만 3을 검사해 선택**한다. 3도 실패하거나 다른 오류가 나면 중지한다. 선택한 크기는 세 실험에 공통 적용한다. 마지막 남은 입력은 더 작은 배치로 처리한다. OOM이 나도 전체 러너가 자동으로 작은 배치로 바꾸지 않게 한다.

## 1. 인스턴스와 환경

RTX 4090 **1장(24GB)**, CPU 3개 이상, 모델 적재 여유가 있는 RAM(48GB 이상 권장), 디스크 약 80GB 이상을 준비한다. 실제 필요 공간은 기존 캐시·출력에 따라 달라진다. CUDA 드라이버가 CUDA 13.0 PyTorch를 지원하는 템플릿을 선택한다. 최초 설치 전에 프로젝트가 있는지 확인해 중복 clone을 피한다. SSH가 끊겨도 실행하려면 `tmux` 세션 안에서 아래 절차를 진행한다.

```bash
cd /workspace
# 아직 저장소가 없을 때만:
git clone --branch followup-rel-4lang-inference https://github.com/dltmdwoOS/mpr-gui-crosslocale.git
cd mpr-gui-crosslocale
# 이미 clone했다면 현재 변경을 확인한 뒤 최신 코드로 맞춘다.
git status --short --branch
git pull --ff-only

export XDG_CACHE_HOME="$PWD/.cache"
export HF_HOME="$XDG_CACHE_HOME/huggingface"
export TORCH_HOME="$XDG_CACHE_HOME/torch"
export PIP_CACHE_DIR="$XDG_CACHE_HOME/pip"
export OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3
export CUDA_VISIBLE_DEVICES=0 TOKENIZERS_PARALLELISM=false
python -m venv .venv
source .venv/bin/activate
python -m pip install -r 01_code/requirements-qwen3-4090.txt
python -m pip install -e './01_code[models]'
source followup_rel_4lang/qwen3_4090_env.sh
python -c 'import torch, transformers; print(torch.__version__,transformers.__version__); print(torch.cuda.get_device_name(0)); assert torch.cuda.device_count()==1'
```

캐시가 다른 개인 경로에 이미 있으면 위 `HF_HOME` 등을 그 경로로 지정해 재사용한다. 새 셸에서는 캐시 환경변수·venv·`qwen3_4090_env.sh`를 다시 설정한다. 설정 파일은 `01_code/configs/models/qwen3_vl_8b_4090_channels_last.yaml`이다.

## 2. 고정 데이터와 체크포인트 준비

```bash
cd 01_code
bash scripts/download_mpr_gui.sh --source-lock data/manifests/source_lock.json --download-workers 2
bash scripts/audit_release.sh
cd ..
python followup_rel_4lang/data_bundle.py unpack
python followup_rel_4lang/data_bundle.py fetch-images --workers 2
python followup_rel_4lang/data_bundle.py verify
hf download Qwen/Qwen3-VL-8B-Instruct --revision "$QWEN3_REVISION"
test -s "$MODEL_SNAPSHOT/config.json"
```

6×6 manifest는 `01_code/data/manifests/mpr_gui_manifest.jsonl`이다. REL bundle은 Git에 포함되며 GUI 이미지는 고정 revision에서 다운로드·SHA-256 검사한다. 다운로드 요청 제한이 나면 멈춘 뒤 같은 명령을 재개한다. 데이터셋이나 모델 revision을 임의로 바꾸지 않는다.

## 3. 배치 4→3 검사와 선택 고정

```bash
mkdir -p followup_rel_4lang/results/qwen3_single4090/logs
set -euo pipefail
python followup_rel_4lang/check_qwen3_batch.py \
  --manifest 01_code/data/manifests/mpr_gui_manifest.jsonl \
  --output followup_rel_4lang/results/qwen3_single4090/batch_selection.json \
  2>&1 | tee followup_rel_4lang/results/qwen3_single4090/logs/batch_check.log

export MODEL_CONFIG=01_code/configs/models/qwen3_vl_8b_4090_channels_last.yaml
BATCH=$(python - <<'PY'
import hashlib,json,os
from pathlib import Path
p=Path('followup_rel_4lang/results/qwen3_single4090/batch_selection.json')
r=json.loads(p.read_text())
assert r['selected_batch_size'] in (3,4), 'Batch check failed'
assert r['config_sha256']==hashlib.sha256(Path(os.environ['MODEL_CONFIG']).read_bytes()).hexdigest(), 'Config changed since batch check'
assert r['manifest_sha256']==hashlib.sha256(Path('01_code/data/manifests/mpr_gui_manifest.jsonl').read_bytes()).hexdigest(), 'Manifest changed since batch check'
assert '4090' in r['gpu']
print(r['selected_batch_size'])
PY
)
export BATCH
echo "Fixed batch: $BATCH"
```

검사기는 각 차원의 긴 질문과 최대 이미지 장수 조합, grounding 위치 출력(최대 64토큰)을 실제 생성한다. 합성 메모리 검사 입력은 연구 결과에 포함하지 않는다. 전체 데이터의 모든 조합이 메모리에 들어간다는 증명은 아니므로 이후 OOM은 중단·기록 후 원인을 확인한다. 다른 오류를 OOM으로 간주해 배치 3으로 넘어가지 않는다. `batch_selection.json`이 이미 있으면 덮어쓰지 않고 종료한다. 재검사가 필요하면 별도 출력 경로를 사용하고 기존 결과를 보존한다.

## 4. 전체 실행 전 짧은 smoke

```bash
python 01_code/run_cross_locale.py \
  --manifest 01_code/data/manifests/mpr_gui_manifest.jsonl --repo-root 01_code \
  --model-config "$MODEL_CONFIG" --dimensions wf wi au ap ael rel \
  --sample-size 6 --sample-unit semantic_items --seed 42 --batch-size "$BATCH" \
  --score-labels --system-prompt-mode english_fixed --device-map cuda:0 --resume \
  --output followup_rel_4lang/results/qwen3_single4090/smoke_6x6.jsonl \
  --failures-out followup_rel_4lang/results/qwen3_single4090/smoke_6x6_failures.jsonl
python followup_rel_4lang/run_inference.py \
  --model-config "$MODEL_CONFIG" --batch-size "$BATCH" --strict-batch-size \
  --max-items 2 --resume --output-dir followup_rel_4lang/results/qwen3_single4090/smoke_rel
python followup_rel_4lang/grounding_eval/run_qwen3_grounding.py \
  --model-path "$MODEL_SNAPSHOT" --suite pilot --batch-size "$BATCH" \
  --max-pixels 2097152 --patch-embed-memory-format channels_last_3d \
  --output-dir followup_rel_4lang/results/qwen3_single4090/pilot_orcf
```

6×6 smoke는 6문항×36=216응답, REL은 고유80회/128행, grounding 파일럿은 12문항×4언어쌍×4조건=192응답이다. 오류·누락·좌표 형식 실패를 확인한다. F 추가와 배치 변경 때문에 기존 O/R/C 파일럿 출력 폴더를 재개 대상으로 쓰지 않는다. Grounding `summary.json`에서 `complete=true`와 O/R/C/F의 각 48응답을 확인한다. 모델의 오답은 실행 실패와 구분한다.

## 5. Grounding 입력과 조건

O는 문맥·기준 표현 모두 source, R은 문맥 source·기준 표현 GUI, C는 문맥 GUI·기준 표현 source, **F는 둘 다 GUI**다. 동일 pair 안에서 이미지·GT bbox와 점 출력 지시는 고정한다. 원래 관계 질문의 답을 묻지 않고, `<ref>`로 표시된 기준 요소의 짧은 설명으로 위치를 묻는다. 명시적 system 메시지는 없고, 점은 전체 화면 대비 0–1000 정수 `(x, y)`로 받는다. 원본 좌표로 되돌려 GT bbox 안이면 적중이며 형식 실패도 오답이다. 프롬프트 원문은 [PROMPT](grounding_eval/run_qwen3_prompt_pilot.py)에 있다.

본 분석 설명은 다음 기존 파일을 사용하면 기술적으로 전체 계획을 만들 수 있다.

```bash
export DESCRIPTORS=followup_rel_4lang/grounding_eval/rtx4090_20261105/main_descriptors_draft_v2.json
python followup_rel_4lang/grounding_eval/run_qwen3_grounding.py \
  --model-path "$MODEL_SNAPSHOT" --suite main --descriptors "$DESCRIPTORS" \
  --batch-size "$BATCH" --max-pixels 2097152 --patch-embed-memory-format channels_last_3d \
  --output-dir followup_rel_4lang/results/qwen3_single4090/grounding_main_orcf --dry-run
```

이 파일은 **158문항·632개 언어별 설명의 자동 추출 초안(`reviewed=false`)**이다. 사람 bbox 검수가 끝났다는 사실과 별개다. 원문 부분 문자열·기준 표현 매핑은 자동 검증하지만, 모든 설명의 의미적 적절성을 사람이 검수했다고 주장하지 않는다. 초안을 그대로 사용하면 결과를 그 입력에 대한 탐색 실험으로 해석한다. 설명을 검토·수정할 경우 이 단계에서 최종 파일 경로를 `DESCRIPTORS`에 지정하고 이후 고정한다. 실행 계약은 설명으로 만든 모든 입력·코드를 해시해 변경된 설명으로 같은 결과 폴더를 재개하지 못하게 한다.

ORCF main은 7,584응답이고 배치 4면 1,896배치, 배치 3이면 2,528배치다. F의 같은 GUI 표현은 여러 source 방향에서 반복되지만 현재 러너는 각 pair의 결과를 모두 생성한다. 반복된 F를 서로 독립인 문항으로 해석하지 않는다.

## 6. 전체 실행: 한 번에 하나씩

다음 세 명령은 **전체 GPU 추론**이다. 위 smoke·입력 확인 후 실행한다. `set -euo pipefail`을 유지하고 각 명령이 끝난 뒤 다음 명령을 실행한다. 로그와 결과 경로를 새 실험용으로 고정한다.

```bash
python 01_code/run_cross_locale.py \
  --manifest 01_code/data/manifests/mpr_gui_manifest.jsonl --repo-root 01_code \
  --model-config "$MODEL_CONFIG" --dimensions wf wi au ap ael rel \
  --sample-unit semantic_items --seed 42 --batch-size "$BATCH" \
  --score-labels --system-prompt-mode english_fixed --device-map cuda:0 --resume \
  --output followup_rel_4lang/results/qwen3_single4090/full_6x6.jsonl \
  --failures-out followup_rel_4lang/results/qwen3_single4090/full_6x6_failures.jsonl \
  --sample-manifest-out followup_rel_4lang/results/qwen3_single4090/full_6x6_plan.json \
  2>&1 | tee -a followup_rel_4lang/results/qwen3_single4090/logs/full_6x6.log
python -m mpr_crosslocale.analysis.summarize_cross_locale \
  --input followup_rel_4lang/results/qwen3_single4090/full_6x6.jsonl \
  --json-out followup_rel_4lang/results/qwen3_single4090/full_6x6_summary.json \
  --csv-out followup_rel_4lang/results/qwen3_single4090/full_6x6_summary.csv

python followup_rel_4lang/run_inference.py \
  --model-config "$MODEL_CONFIG" --batch-size "$BATCH" --strict-batch-size --resume \
  --output-dir followup_rel_4lang/results/qwen3_single4090/full_rel \
  2>&1 | tee -a followup_rel_4lang/results/qwen3_single4090/logs/full_rel.log

python followup_rel_4lang/grounding_eval/run_qwen3_grounding.py \
  --model-path "$MODEL_SNAPSHOT" --suite main --descriptors "$DESCRIPTORS" \
  --batch-size "$BATCH" --max-pixels 2097152 --patch-embed-memory-format channels_last_3d \
  --output-dir followup_rel_4lang/results/qwen3_single4090/grounding_main_orcf \
  2>&1 | tee -a followup_rel_4lang/results/qwen3_single4090/logs/grounding_main_orcf.log
```

6×6는 영어 고정 system, A–D 최대 2토큰 생성과 first-token score를 유지한다. REL도 기존 ORCF의 프롬프트·채점 규칙을 유지한다. 6×6의 `correct`는 기존대로 score 기준이므로 생성 정답은 `parsed_generated_label==gold_label`로 별도 집계한다. Grounding은 최대 64 새 토큰·점 하나 출력이다.

## 7. 完了確認・再開・結果保存

6×6는 저장 행 수보다 **성공한 고유 입력 ID가 79,020개**이고 계획 ID 집합과 같은지 확인한다. 재개 기록의 실패 행도 남으므로 ID별 마지막 성공 기록을 사용한다. REL은 `summary.json`의 `condition_rows=23424`, `actual_successful_inferences=18432`와 status를 확인한다. Grounding은 `complete=true`, `response_count=7584`, 조건별 1,896응답을 확인한다.

중단되면 환경변수를 복원하고 **같은 코드·설정·batch·출력 경로**로 같은 명령을 실행한다. 6×6와 REL은 `--resume`, grounding은 계약 검사 후 자동 재개한다. 배치나 설명을 바꿀 때는 새 출력 폴더를 사용한다.

인스턴스 정리 전에 `followup_rel_4lang/results/qwen3_single4090/` 전체(batch 선택·계약·입력 계획·원시 JSONL·summary·로그), `git rev-parse HEAD`, `python -m pip freeze`를 내려받는다. 결과 디렉터리는 Git 기본 제외이므로 push만으로 보존되지 않는다.
