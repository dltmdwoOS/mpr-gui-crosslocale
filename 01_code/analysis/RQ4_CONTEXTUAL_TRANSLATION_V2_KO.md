# RQ4 contextual query-translation v2 구현·실행 안내

## 1. 최종 treatment

최종 RQ4 intervention은 다음으로 고정한다.

```text
original mismatch:                 (Q_A, G_B)
Qwen3 contextual intervention:     (Q^CTX_{A→B}, G_B)
target human-parallel endpoint:    (Q_B, G_B)
```

번역기는 `Qwen/Qwen3-8B`이며 revision은
`47719a242beab8f9aecc40ce3928b034dd5dd559`로 고정했다. 전체 question stem과
A–D options를 하나의 MCQ로 함께 제시하고, prompted JSON을 parse·검증한다.

NLLB-600M field-wise 결과는 engineering pilot artifact로 보존하지만 최종 RQ4
분석에는 사용하지 않는다. 이번 변경은 translator 크기만 바꾼 비교가 아니라
`field-wise MT`를 `full-MCQ contextual translation`으로 교체한 것이다.

## 2. Translator가 볼 수 있는 정보

번역 payload에는 다음 네 top-level field만 들어간다.

```json
{
  "source_language": "...",
  "target_language": "...",
  "question_stem": "...",
  "options": {"A": "...", "B": "...", "C": "...", "D": "..."}
}
```

Screenshot, gold label, text-dependency label, VLM outcome, human target query,
NLLB output은 translation generation에서 구조적으로 제외된다. Human-parallel
text는 60행 smoke review CSV를 만들 때에만 사후 join되며 번역 수정에는 사용하지
않는다.

## 3. Validation과 repair

Hard validation은 다음 위반을 fail로 처리한다.

- JSON parse 실패 또는 extra/missing top-level field
- A/B/C/D key·순서 변경
- empty/non-string field
- field별 숫자·percentage 변경
- field별 명백한 file-format token 변경

첫 출력이 hard validation에 실패하면 실패 사유를 명시해 정확히 한 번, batch size
1로 repair한다. 모든 raw output과 parse 결과를 `translation_attempts`에 보존한다.
두 번째도 실패하면 번역 artifact에는 행을 남기되
`failed_after_structural_repair`, `translation_analysis_eligible=false`로 표시한다.
최종 VLM input builder는 이런 행이 하나라도 있으면 중단한다.

Spatial relation, negation, quoted proper-noun 변화, target script, 전 field 미번역은
`semantic_diagnostic_flags`일 뿐 자동 제외 기준이 아니다. 어휘 기반 false positive가
가능하므로 60행 smoke review 및 필요시 full artifact audit에 사용한다.

## 4. 로컬에서 완료한 검증

- Python compile 통과
- contextual unit test 5개 통과
- 실제 데이터로 60행 mock smoke artifact와 review CSV 생성 통과
- 실제 데이터로 10,980행 mock translation → paired input → metadata diff audit 통과
- contextual VLM input 10,980행 dry-run 통과
- GLMM R script parse 통과

Mock은 source text를 그대로 반환하므로 번역 품질 증거가 아니다. 실제 Qwen3 weight는
RTX 3060에서 로드하지 않았고, 아래 4090 smoke test가 최초 품질 관문이다.

## 5. Vast.ai RTX 4090 환경 준비

아래 명령은 repository root가 `/workspace/mpr-gui-crosslocale`인 Ubuntu Vast
instance를 가정한다. 실제 clone 위치만 다르면 첫 `cd`를 바꾼다.
아래 `git pull` 경로는 이 구현 변경을 `rq4` branch에 commit·push한 뒤 사용한다.

```bash
cd /workspace/mpr-gui-crosslocale
git fetch origin
git switch rq4
git pull --ff-only origin rq4
git lfs pull

cd 01_code
python3 -m venv --system-site-packages .venv-rq4-contextual
source .venv-rq4-contextual/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e '.[models]' \
  -c configs/interventions/rq4_qwen3_constraints.txt

export HF_HOME=/workspace/hf-cache
mkdir -p "$HF_HOME" logs data/derived/interventions
```

Vast image에 CUDA PyTorch가 없다면 그때만 다음을 먼저 설치한다.

```bash
python -m pip install torch==2.8.0 torchvision==0.23.0 \
  --index-url https://download.pytorch.org/whl/cu128
```

환경 확인:

```bash
python - <<'PY'
import torch, transformers
print("torch:", torch.__version__)
print("cuda runtime:", torch.version.cuda)
print("cuda available:", torch.cuda.is_available())
print("gpu:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)
print("vram GiB:", round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1))
print("transformers:", transformers.__version__)
assert torch.cuda.is_available()
assert torch.cuda.get_device_properties(0).total_memory >= 20 * 1024**3
assert transformers.__version__ == "4.57.6"
PY
```

## 6. Step A — 60행 smoke translation

먼저 model을 로드하지 않는 plan validation을 실행한다.

```bash
python -m mpr_crosslocale.interventions.build_rel_qwen3_contextual_translations \
  --scope smoke \
  --dry-run \
  --plan-out data/derived/interventions/rel_qwen3_contextual_smoke_plan_60.jsonl
```

기대값은 `rows=60`, `directions=30`이다. 이어서 실제 Qwen3 translation을
실행한다. RTX 4090에서 frozen runtime batch size는 2다.

```bash
python -m mpr_crosslocale.interventions.build_rel_qwen3_contextual_translations \
  --scope smoke \
  --device cuda \
  --batch-size 2 \
  --log-every-batches 5 \
  --output data/derived/interventions/rel_qwen3_contextual_smoke_60.jsonl \
  --issue-audit-out data/derived/interventions/rel_qwen3_contextual_smoke_issues_60.jsonl \
  --resume 2>&1 | tee logs/rq4_contextual_smoke.log
```

완료 요약에서 다음을 확인한다.

```text
rows = 60
eligible = 60
hard_failure_rows = 0
```

Repair 행 수와 diagnostic flag 행 수는 0일 필요가 없지만 확인·기록한다.

## 7. Step B — smoke review CSV

```bash
python -m mpr_crosslocale.interventions.build_rel_qwen3_contextual_review \
  --translations data/derived/interventions/rel_qwen3_contextual_smoke_60.jsonl \
  --output data/derived/interventions/rel_qwen3_contextual_smoke_review_60.csv
```

CSV는 30 directed direction마다 정확히 2개씩 포함한다. 다음 다섯 manual column을
채운다.

- `manual_structure_pass_0_or_1`
- `manual_correct_target_language_0_or_1`
- `manual_spatial_relation_preserved_0_or_1`
- `manual_gross_semantic_corruption_0_or_1` (`1`이 corruption 있음)
- `manual_overall_pass_0_or_1`

Full generation으로 넘어가는 smoke criterion은 option drop/empty, 명백한 wrong
language, spatial reversal, gross semantic corruption이 0건인 것이다. Human-parallel
columns는 reference-only이며 Qwen3 출력을 사람 손으로 수정하는 데 사용하지 않는다.
문제가 있으면 full run과 VLM inference를 시작하지 않는다.

## 8. Step C — 10,980행 full translation

Smoke를 통과한 뒤 같은 frozen config로 실행한다.

```bash
python -m mpr_crosslocale.interventions.build_rel_qwen3_contextual_translations \
  --scope full \
  --device cuda \
  --batch-size 2 \
  --log-every-batches 10 \
  --output data/derived/interventions/rel_qwen3_contextual_translations_v2.jsonl \
  --issue-audit-out data/derived/interventions/rel_qwen3_contextual_translation_issues_v2.jsonl \
  --resume 2>&1 | tee logs/rq4_contextual_full.log
```

`--resume`은 이미 checkpoint된 `translation_id`를 건너뛴다. 임의 source fallback은
없으며 repair 이후에도 hard-invalid인 행은 artifact에 보존된다. 최종 기대값은 다음과
같다.

```text
rows = 10980
eligible = 10980
hard_failure_rows = 0
```

## 9. Step D — VLM input 및 exact metadata diff

```bash
python -m mpr_crosslocale.interventions.build_rel_qwen3_contextual_inputs \
  --translations data/derived/interventions/rel_qwen3_contextual_translations_v2.jsonl \
  --contextual-inputs-out data/derived/interventions/rel_qwen3_contextual_inputs_v2.jsonl \
  --original-controls-out data/derived/interventions/rel_qwen3_contextual_original_controls_v2.jsonl \
  --pair-diff-audit-out data/derived/interventions/rel_qwen3_contextual_pair_metadata_diff_v2.csv
```

기대값:

```text
rows = 10980
pair_metadata_diff_failures = 0
```

Original과 contextual input 사이에는 query text와 intervention/translation metadata만
달라질 수 있다. Image, gold, parallel ID, source language stratum, GUI language,
option order, source question ID, GUI sample ID가 다르면 즉시 실패한다.

## 10. Step E — VLM input dry-run

```bash
python -m mpr_crosslocale.inference.run_rel_contextual_intervention \
  --inputs data/derived/interventions/rel_qwen3_contextual_inputs_v2.jsonl \
  --model-config configs/models/qwen2_5_vl_7b.yaml \
  --output results/raw/qwen/rel_contextual_v2.jsonl \
  --failures-out results/raw/qwen/rel_contextual_v2_failures.jsonl \
  --repo-root . \
  --dry-run
```

`rows=10980`, 기존 Qwen revision, `mpr_label_only_v1`, `english_fixed`, canonical
generation config가 출력되어야 한다.

## 11. Step F — Qwen 및 InternVL inference

Translation process가 종료되어 GPU memory가 반환된 뒤 Qwen을 실행한다.

```bash
mkdir -p results/raw/qwen results/raw/internvl

python -m mpr_crosslocale.inference.run_rel_contextual_intervention \
  --inputs data/derived/interventions/rel_qwen3_contextual_inputs_v2.jsonl \
  --model-config configs/models/qwen2_5_vl_7b.yaml \
  --output results/raw/qwen/rel_contextual_v2.jsonl \
  --failures-out results/raw/qwen/rel_contextual_v2_failures.jsonl \
  --repo-root . \
  --resume 2>&1 | tee logs/rq4_contextual_qwen.log
```

동일한 translation artifact를 InternVL에 그대로 사용한다.

```bash
python -m mpr_crosslocale.inference.run_rel_contextual_intervention \
  --inputs data/derived/interventions/rel_qwen3_contextual_inputs_v2.jsonl \
  --model-config configs/models/internvl2_5_8b.yaml \
  --output results/raw/internvl/rel_contextual_v2.jsonl \
  --failures-out results/raw/internvl/rel_contextual_v2_failures.jsonl \
  --repo-root . \
  --resume 2>&1 | tee logs/rq4_contextual_internvl.log
```

Qwen-family phrasing confound를 줄이기 위해 두 downstream VLM 결과가 모두 확보되기
전에는 최종 recovery claim을 닫지 않는다.

## 12. 결과 validation과 GLMM

모델별로 기존 canonical original mismatch 결과와 contextual 결과를 결합한다.
아래 `<ORIGINAL_...>`만 실제 canonical result path로 바꾼다.

```bash
python -m mpr_crosslocale.interventions.validate_rel_nllb_results \
  --original-results <ORIGINAL_QWEN_6X6_JSONL> \
  --intervention-results results/raw/qwen/rel_contextual_v2.jsonl \
  --intervention-inputs data/derived/interventions/rel_qwen3_contextual_inputs_v2.jsonl \
  --combined-out results/analysis/qwen/rq4_contextual_v2/combined_21960.csv \
  --pair-audit-out results/analysis/qwen/rq4_contextual_v2/pair_audit.jsonl \
  --summary-out results/analysis/qwen/rq4_contextual_v2/validation_summary.json
```

GLMM은 treatment label을 `original` 외의 유일한 값에서 자동으로 읽으므로 archived
NLLB와 contextual v2 모두 구분한다.

```bash
Rscript analysis/rel_nllb_intervention_glmm.R \
  results/analysis/qwen/rq4_contextual_v2/combined_21960.csv \
  results/analysis/qwen/rq4_contextual_v2/glmm \
  1 2000 42 include
```

Primary test는 `intervention × text_dependency`, primary outcome은 계속
`generation_correct`다. GEE sensitivity는 이번 구현·실행 계획에서 의도적으로
제외했으며, 별도 승인을 받은 후속 분석으로만 남겨 두었다.
