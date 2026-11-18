# RTX 4090에서 PP-OCR 편집 재검증

첫 실행은 **8B V-D-H, V-D-S, O**를 같은 48쌍에서 새로 풀이하는 pilot이다. Screen의 주 분석 문항에서 최대 원본 이미지 면적이 큰 네 문항을 고르고, 문항마다 12개 언어쌍을 모두 남긴다. 동일 모델에서 stem 추출을 공유하고, PP-OCR inventory는 기존 추출 결과를 사용한다. 기존 B200의 40 GiB 여유 메모리 검사 대신 로컬 체크포인트 가중치 크기를 적재 전 하한으로 확인한다. 실제 peak VRAM·속도는 pilot에서 확인한다.

## 4090에서 실행

저장소 루트와 이 커밋에서 시작한다. 기존 Qwen3 4090 환경을 재사용할 수 있다. 새 환경은 CUDA 13 지원 드라이버와 저장소의 4090 요구사항으로 만든다. [기존 4090 환경 안내](../../QWEN3_SINGLE_4090_RUNBOOK_KO.md)

```bash
export XDG_CACHE_HOME="$PWD/.cache"
export HF_HOME="$XDG_CACHE_HOME/huggingface"
export TORCH_HOME="$XDG_CACHE_HOME/torch"
export PIP_CACHE_DIR="$XDG_CACHE_HOME/pip"
export CUDA_VISIBLE_DEVICES=0 OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3 TOKENIZERS_PARALLELISM=false

# 새 환경을 만드는 경우
python -m venv .venv
.venv/bin/python -m pip install -r 01_code/requirements-qwen3-4090.txt
.venv/bin/python -m pip install -e './01_code[models]'

.venv/bin/python followup_rel_4lang/data_bundle.py unpack
.venv/bin/python followup_rel_4lang/data_bundle.py fetch-images --workers 2
tar -xzf followup_rel_4lang/method_dev/artifacts/gpu_ocr_full_dev_completed.tar.gz \
  followup_rel_4lang/method_dev/artifacts/gpu_ocr_screen_paddle_v1/ppocrv5_cuda/inputs.jsonl \
  followup_rel_4lang/method_dev/artifacts/gpu_ocr_screen_paddle_v1/ppocrv5_cuda/ocr/attempt_0001/inventories.jsonl

# 평가 라벨이 준비된 경우 이 audit과 cp는 생략
.venv/bin/python followup_rel_4lang/method_dev/scripts/audit.py \
  --output-dir followup_rel_4lang/method_dev/artifacts/audit_4090
cp followup_rel_4lang/method_dev/artifacts/audit_4090/evaluation_labels_PRIVATE.jsonl \
   followup_rel_4lang/method_dev/artifacts/dataset_audit/

.venv/bin/hf download Qwen/Qwen3-VL-8B-Instruct --revision 0c351dd01ed87e9c1b53cbc748cba10e6187ff3b
.venv/bin/python -u followup_rel_4lang/method_dev/scripts/run_editor_matrix_4090_pilot.py
```

파일과 스크린샷 checksum, 평가 라벨 digest, 모델 revision을 검사한다. 같은 프롬프트, BF16, SDPA, 2MP, 편집 batch 1, 풀이 batch 3을 사용한다. `--solver 4B`는 4B 체크포인트 `ebb281ec70b05090aa6165b016eac8ec08e71b17`를 받아 둔 뒤 실행한다. 정확도·단계별 시간·peak VRAM은 `artifacts/ppocr_vd_4090_pilot_8B/summary.json`에서 확인한다. 원시 편집과 풀이 출력도 같은 폴더에 보존한다. CPU 모의 실행으로 48쌍 × 3조건의 흐름을 확인했다. 실제 4090의 응답과 속도는 측정 전이다.

전체 RTX 4090 재실험의 첫 비교는 **8B O / V-D-S / V-D-H**, 필요시 기존 L-D-S까지 같은 장비에서 측정하는 구성이다. 위 pilot은 메모리·출력 경로를 확인하는 용도이며 정확도 편차는 전체의 동일 1,895쌍에서 확인한다. PP-OCR의 기존 inventory 생성 시간과 새 장비에서 다시 측정한 시간을 구분한다. B200 전체 집합에서 V-D-H는 8B 78.26%·78.98분, 4B 73.98%·83.79분이었다. 4B는 4090에서 메모리 여유가 필요하거나 속도 차이를 별도로 확인할 때 비교한다. [B200 전체 결과](PPOCR_EDITOR_MATRIX_VD_RESULTS_KO.md)
