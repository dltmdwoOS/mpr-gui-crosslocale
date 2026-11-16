# GCSA / RFA development harness

**2026-11-15 사용자 수정 반영:** 현재 inventory는 평가 VLM 자체를 사용한다. Qwen3용 새 설정은
`configs/gcsa_qwen3_fixed_lm_v1.json`이며 참조 추출·번역은 고정 text-only Qwen3-8B다.
Qwen3-8B 다운로드·SHA 검증은 완료됐다. [실제 프롬프트 원문·한국어 해석·GO/NO-GO 검토](reports/PROMPTS_AND_GO_NO_GO_KO.md). 이전 v0 설정은 보존하며 현재 모델 준비 명령은 문서 마지막에 있다. [Smoke 재점검](reports/SMOKE_REAUDIT_KO.md)을 우선 참고한다.

기준: `results-new-models-expA-20261115`, `e4aff7ace7248f1dd4e5a5dac0d4f679b33c6b5a`. 작업 브랜치 `method-selective-alignment-dev`. 기존 frozen 데이터·분석 규칙·원시 예측은 수정하지 않는다. [초기 준비 단계 보고](reports/FINAL_DEV_REPORT_KO.md).

[확대 파일럿·후보 탐색 설계 및 실행 명령](reports/SEARCH_DESIGN_KO.md): 기존 split을 보존한 32-item screen과 20-item selection, 추출 7조건·구조 9조건을 준비했다. 실제 진행 결과는 위 누적 실측 보고서에서 확인한다.

전체 순차 실행은 `bash followup_rel_4lang/method_dev/scripts/run_search_pipeline.sh` 한 줄이다. [OOM 검토·자동 선택·재개 설명](reports/PIPELINE_OOM_AUDIT_KO.md). 현재45GB MIG용이며 free40GiB를 요구한다.

누적 실측 결과: [SEARCH_RESULTS_KO.md](reports/SEARCH_RESULTS_KO.md). 완료 조건만 집계하며 `.venv/bin/python followup_rel_4lang/method_dev/scripts/update_search_results_report.py`로 같은 보고서를 갱신한다. 아래 상태 설명은 초기 harness/smoke의 역사적 기록이다.

완료된 후속 진단: [Oracle 결과·실패 분석](reports/ORACLE_RESULTS_KO.md), [실행안](reports/ORACLE_SPAN_EXACT_KO.md). Source span만 교정한 실제 GPU 1,944쌍이 완료됐다. Internal에서 Automatic 69.56% → Oracle 71.54%(+1.98pp), O 대비 +1.13pp의 CI는 0을 포함한다. 추론 없이 `.venv/bin/python followup_rel_4lang/method_dev/scripts/analyze_oracle_exact.py`로 상세 보고서를 재생성한다. 기존 frozen 실행기와 예측은 보존한다.

[Inventory 사용 방식·문항 전체 exact match 점검](reports/INVENTORY_USAGE_AND_EXACT_MATCH_KO.md): 최근 inventory 입력 조건은 GUI_FULL·GUI_MATCH_LM이며 Oracle GUI_EXACT는 독립 번역 후 필터링이다. 과거 전체 번역 prompt와의 차이를 실제 호출에서 확인했다. Internal의 모든 referent match는 68/1,416쌍(4.80%)이다.

## 현재 상태

Gate 0/1은 실제 데이터·hash·T/R 재구성과 CPU mock 검사를 통과했다. Gate 2의 CPU 구성요소와 실제 화면 기능 검사는 실행했지만, 대체 모델의 referent extraction이 빈 목록을 내 **실제 selective editing 성공 게이트는 미통과**다. Calibration, 2×2 내부 평가, RFA 성능 평가는 실행하지 않았다. 이 상태를 method의 성능 검증 완료로 해석하면 안 된다.

| 입력 범위 | 문항 | 불일치 pair | 사전 제외 후 |
| --- | ---: | ---: | ---: |
| 전체 development main | 158 | 1,896 | 1,895 |
| Calibration | 40 | 480 | 479 |
| Internal evaluation | 118 | 1,416 | 1,416 |
| 별도 pilot | 12 | 48 (기존 순환 4방향) | 주 분석 제외 |

분할 seed `20261115`; 동일 이미지 SHA 또는 `rel::` 뒤 state key가 같으면 union하여 같은 partition에 둔다. 지각적으로 유사한 이미지까지 검출한 것은 아니다. 새 method 결과를 보고 evaluation partition을 수정하지 않았다. 전체 158문항은 역사적으로 이미 관찰된 development cohort다.

## 실행 경계

- `scripts/audit.py`: privileged 데이터 어댑터. 원본 O/R·annotated span·T·정답을 읽어 검증하고 **allowlist method 입력**과 평가 전용 파일을 분리한다.
- `01_code/src/mpr_crosslocale/methods/selective_alignment/`: method-only 모듈. 데이터셋·reference mapping·정답·GT bbox를 읽는 경로가 없다. schema 외 입력 키가 오면 거절한다.
- `scripts/run_pipeline.py`: allowlist 입력만 소비한다. `TXT_SEL`과 `GUI_SEL`은 캐시된 동일 extraction/번역 결과를 공유한다. Screenshot inventory는 모든 query 처리보다 먼저 screenshot-only payload로 추출·hash 캐시한다.
- `scripts/oracle_diagnostic.py`: `oracle_span_selective` 전용. automatic 결과에 합치지 않는다.
- `scripts/infer.py`, `evaluation.py`, `quality.py`: 변환 완료 후 평가 경계에서만 정답·진단 annotation·과거 예측을 읽는다.

`GUI_SEL=auto_selective`는 screenshot inventory 안에 **실제로 반환된 원시 문자열**만 채택한다. NFKC·공백·casefold로 dedup/sort하되 raw spelling은 보존한다. 초기 matcher는 번역 후 normalized exact만 허용하며 불확실한 참조는 유지한다. `retrieval=labse`와 로컬 `labse_snapshot`을 지정하면 embedding retrieval이 가능하지만 이번 작업에서는 해당 모델을 적재·튜닝하지 않았다. score는 확률이 아니다. `TXT_SEL=text_only_selective`은 같은 자동 span에 screen-blind 번역만 적용한다.

## CPU 검증과 복원

저장소 최상위에서 CUDA 가상환경 또는 기존 프로젝트 venv를 활성화한다. CPU 검사에는 새 모델을 다운로드하지 않는다.

```bash
export OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3
export XDG_CACHE_HOME=/home/jovyan/seungjae/.cache
export HF_HOME="$XDG_CACHE_HOME/huggingface"
export TORCH_HOME="$XDG_CACHE_HOME/torch"
export PIP_CACHE_DIR="$XDG_CACHE_HOME/pip"
export PYTHONPATH=01_code/src:.
python followup_rel_4lang/data_bundle.py unpack
# 새 clone에서는 이미지가 필요할 때만:
python followup_rel_4lang/data_bundle.py fetch-images --workers 2
python -m pytest -q followup_rel_4lang/method_dev/tests

# 기존 artifact를 덮어쓰지 않으므로 별도 새 디렉터리 지정:
python followup_rel_4lang/method_dev/scripts/audit.py \
  --output-dir followup_rel_4lang/method_dev/artifacts/audit_recheck
python followup_rel_4lang/method_dev/scripts/run_pipeline.py \
  --inputs followup_rel_4lang/method_dev/artifacts/audit_recheck/method_inputs.jsonl \
  --split-file followup_rel_4lang/method_dev/artifacts/audit_recheck/split.json \
  --config followup_rel_4lang/method_dev/configs/gcsa_v0.json \
  --partition pilot --mock \
  --output-dir followup_rel_4lang/method_dev/artifacts/mock_recheck
```

`audit_recheck/split.json`이 추적된 `artifacts/dataset_audit/split.json`과 동일해야 한다. audit의 680개 이미지 검증이 빠졌으면 `missing_images`에 표시되므로 이미지 확보 후 재검사한다. 저장된 bundle의 HF revision은 `c1edb808d424a2fa7bc4a2e601d39b431b04acd5`다.

## 실제 모델 준비

현재는 평가 VLM인 **Qwen3-VL-8B**가 inventory를 만들고 **text-only Qwen3-8B**가 참조 추출·번역을 맡는다. 두 모델은 로컬 pinned snapshot이 준비됐다. 문서 마지막의 `materialize_config.py`로 `gcsa_qwen3_fixed_lm_v1.json`을 실행용 config로 변환한다. 아래 실행 예시의 `config_primary.json`에는 이 생성 config를 지정한다. Revision·모델·generation을 바꾸면 새 version으로 기록한다.

현재 및 후속 모델의 고정 revision (Qwen2.5-VL/InternVL3.5는 이후 단계):

- `Qwen/Qwen2.5-VL-7B-Instruct`, `cc594898137f460bfe9f0759e9844b3ce807cfb5`.
- `Qwen/Qwen3-8B`, `47719a242beab8f9aecc40ce3928b034dd5dd559`.
- downstream `Qwen/Qwen3-VL-8B-Instruct`, `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`.
- downstream `OpenGVLab/InternVL3_5-8B`, `9bb6a56ad9cc69db95e2d4eeb15a52bbcac4ef79`.

기존 프로젝트 `.[models]` 환경을 사용한다. Transformers 4.57.6, BF16·SDPA, translator `enable_thinking=false`를 계약에 기록한다. 모델 적재는 순차 수행하며 두 모델을 동시에 GPU에 두지 않는다. 각 source field span은 Python character offsets와 UTF-8 byte offsets 모두 남긴다. 자유로운 최종 selective 재작성은 허용하지 않는다.

```bash
# method_dev/artifacts/config_primary.json에 고정 snapshot 경로를 먼저 설정한다.
python followup_rel_4lang/method_dev/scripts/run_pipeline.py \
  --inputs followup_rel_4lang/method_dev/artifacts/audit_recheck/method_inputs.jsonl \
  --split-file followup_rel_4lang/method_dev/artifacts/audit_recheck/split.json \
  --config followup_rel_4lang/method_dev/artifacts/config_primary.json \
  --partition pilot --limit 1 \
  --output-dir followup_rel_4lang/method_dev/artifacts/primary_smoke
```

이 실제 smoke에서 extraction/유효 편집이 작동하는지 확인하고, calibration 40문항을 대상으로 같은 CLI의 `--partition calibration`과 `--limit` 생략을 사용한다. Threshold/prompt/fallback 수정은 calibration 결과만 보며 version을 모두 보존한다. 필요하면 `quality.py`로 annotation span F1과 screenshot matching 검수표를 만든다. **평행 문구 일치를 실제 GUI matching 정답으로 채점하지 않는다.**

```bash
python followup_rel_4lang/method_dev/scripts/quality.py \
  --rewritten followup_rel_4lang/method_dev/artifacts/calibration_v0/rewritten.jsonl \
  --oracle-spans followup_rel_4lang/method_dev/artifacts/audit_recheck/oracle_spans_DIAGNOSTIC_ONLY.jsonl \
  --output-dir followup_rel_4lang/method_dev/artifacts/calibration_quality_v0
python followup_rel_4lang/method_dev/scripts/freeze_calibration.py \
  --config followup_rel_4lang/method_dev/artifacts/config_primary.json \
  --calibration-run followup_rel_4lang/method_dev/artifacts/calibration_v0 \
  --split followup_rel_4lang/method_dev/artifacts/audit_recheck/split.json \
  --output followup_rel_4lang/method_dev/artifacts/frozen_config.json
```

그 뒤 frozen config와 `--partition internal_evaluation`으로 1,416쌍을 실행한다. 현재 runner는 fresh 디렉터리를 요구하며 부분 결과를 자동 재개/덮어쓰기하지 않는다. 변환·모델 실패는 원문 fallback을 기록하며 pair를 삭제하지 않는다. 실행 자체가 중단되면 완료된 평가라고 간주하지 않는다. 원시 출력과 backend call별 시간·입출력 token 수를 함께 보존한다.

## Downstream와 paired 분석

두 모델에 대해 같은 `rewritten.jsonl`을 평가한다. `--baseline-contract`는 아래 ExpA 계약을 각각 사용한다.

```text
followup_rel_4lang/artifacts/new_models_expA_20261115/analysis/expA_8b_20261114/qwen3/expA_qwen3/full/run_contract.json
followup_rel_4lang/artifacts/new_models_expA_20261115/analysis/expA_8b_20261114/internvl35/expA_internvl35/full/run_contract.json
```

`scripts/infer.py --help`의 경로 인자로 rewrite·평가 label·원본 allowlist·위 계약을 전달한다. 우선 `--limit-pairs 1`로 O anchor 및 생성 파서·label score 경로를 확인한다. 전체는 limit을 생략한다. Qwen3 배치 3, InternVL3.5 배치 1, 기존 system·decoding을 사용한다. **새 큐는 condition-major**이고 과거 ExpA의 O/T/R pair-major와 batch 동반 입력이 다르므로 O anchor agreement를 반드시 기록한다. 이 버전은 O만 재실행하며 R anchor 재실행의 일반적 동등성은 검증되지 않았다. 모델 실패로 중단된 부분 파일은 완성 결과로 분석하지 않는다.

```bash
python followup_rel_4lang/method_dev/scripts/evaluation.py \
  --predictions followup_rel_4lang/method_dev/artifacts/predictions_qwen3/predictions.jsonl \
  --baseline followup_rel_4lang/artifacts/new_models_expA_20261115/analysis/expA_8b_20261114/qwen3/expA_qwen3/full/predictions.jsonl \
  --labels followup_rel_4lang/method_dev/artifacts/audit_recheck/evaluation_labels_PRIVATE.jsonl \
  --split followup_rel_4lang/method_dev/artifacts/audit_recheck/split.json \
  --partition internal_evaluation \
  --output followup_rel_4lang/method_dev/artifacts/analysis_qwen3.json
```

Historical T/R은 별도 reference로 가져오고 새 O와 historical O의 label agreement를 기록한다. 조건 누락/중복은 오류로 중단한다. 생성 파싱 실패·모델 실패는 오답으로 포함한다. 10,000회 semantic-item cluster bootstrap, 95% CI, 사전 3개 primary contrast의 bootstrap-centered 양측 p에 Holm 보정을 계산한다. p는 bootstrap 근사 탐색치이며 독립 확증 검정이 아니다. Language-pair·worst-pair와 recovery/regression 수를 낸다. 전체 1,895쌍과 internal-evaluation 1,416쌍을 혼동하지 않는다. Calibration을 합친 전체 development 분석은 별도 sensitivity로 표기한다.

## Pivot 확장

`context_router.py`와 `scripts/route.py`는 aligned와 abstained referents를 모두 placeholder로 보호하고 EN 또는 calibration에서 고정한 model pivot으로 context만 번역한다. `pivot_policy_PENDING.json`은 **미확정**이며 자동 통과하지 않는다. 먼저 Step 3 게이트를 통과하고 calibration에서 정책을 고정해야 한다. 모델별 최적 pivot을 현재 기록에서 추정하지 않는다. Placeholder·field·숫자 검사는 자동화했지만 방향·부정·인접 의미의 cross-language 동등성은 독립 검토가 필요하다. RFA 성능 분석과 추가 대비는 아직 실행·검증되지 않았다.

## 자료 보존

작은 audit·분할·smoke 요약과 압축된 실제 smoke 원시 자료는 Git에 둔다. 그 외 method-only 입력, oracle 진단, 정답 label, 장시간 결과는 로컬 `artifacts/` 아래 분리한다. `scripts/audit.py`가 같은 lock에서 복원한다. `artifacts/smoke_archive.tar.gz`와 `.sha256`은 실제 한 화면 smoke·downstream·당시 소스 스냅샷을 포함하며 이미지는 포함하지 않는다. 어떤 결과도 mock 정확도를 실측처럼 보고하지 않는다.


## Qwen3 고정 LM 준비 명령

개인 캐시 환경변수를 위와 같이 설정하고 실행한다. `--download`를 생략하면 파일·용량·기존 캐시만 확인한다.

```bash
python followup_rel_4lang/method_dev/scripts/prepare_fixed_lm.py \
  --hf-home "$HF_HOME" --download \
  --manifest followup_rel_4lang/method_dev/artifacts/qwen3_8b_download_manifest.json
python followup_rel_4lang/method_dev/scripts/materialize_config.py \
  --template followup_rel_4lang/method_dev/configs/gcsa_qwen3_fixed_lm_v1.json \
  --hf-home "$HF_HOME" \
  --output followup_rel_4lang/method_dev/artifacts/fixed_lm_config.json
# 다운로드 manifest의 verified=true를 확인한 뒤 기존 추출 지시로 한 호출만 검사:
python followup_rel_4lang/method_dev/scripts/recheck_smoke.py \
  --config followup_rel_4lang/method_dev/artifacts/fixed_lm_config.json --stages extract \
  --output followup_rel_4lang/method_dev/artifacts/fixed_lm_extraction_probe.json
```

생성 config가 이미 있으면 새 경로를 사용한다. Snapshot의 모든 weight shard가 있어야 실제 pipeline preflight를 통과한다. 재점검용 `--extractor-prompt quoted_control`은 literal-copy 진단이며 primary extractor 조건이 아니다.
