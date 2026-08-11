# RQ4 NLLB Query-Alignment Intervention 구현 보고서

작성일: 2026-08-11
상태: 구현 및 비모델 검증 완료; NLLB 번역·VLM inference·RQ4 GLMM 적합 대기

## 1. Frozen RQ4

> 외부 NLLB 번역으로 source query를 target GUI 언어에 맞췄을 때, generation accuracy의 회복이 text-independent REL보다 text-dependent REL에서 더 크게 나타나는가?

네 조건의 명칭을 다음과 같이 고정한다.

| 명칭 | 조건 |
|---|---|
| Source matched endpoint | `(Q_A, G_A)` |
| Target human-parallel matched endpoint | `(Q_B, G_B)` |
| Original mismatch | `(Q_A, G_B)` |
| NLLB intervention | `(Q_MT[A→B], G_B)` |

`oracle_sample_id`라는 모호한 표현은 RQ4에서 사용하지 않는다. 기존 manifest의 legacy `oracle_sample_id`는 source matched endpoint를 가리키며, 새 `target_human_parallel_endpoint_id`가 `(Q_B,G_B)` endpoint를 명시한다.

## 2. 구현된 구성요소

### Source 및 endpoint semantics

- `input_specs.py`: legacy source endpoint를 보존하면서 source/target endpoint ID를 명시적으로 추가
- `validate_manifests.py`: target endpoint language, item, gold consistency 검증
- Frozen annotation manifest와 QAS source를 읽되 pair construction은 기존 `build_mismatch_inputs()`만 사용하여 366 REL × 30 directed mismatch를 생성
- Translation generation에는 `text_dependency`가 들어가지 않도록 fail-fast

### NLLB translation

- Model: `facebook/nllb-200-distilled-600M`
- Revision: `f8d333a098d19b4fd9a8b18f94170487ad3f821d`
- Transformers: `4.57.6`
- Dtype: fp32
- Field-wise translation: stem, A, B, C, D
- Decoding: deterministic beam 4, length penalty 1.0, early stopping, max new tokens 256
- Source option delimiter와 whitespace를 보존하는 span renderer
- Direction별 checkpoint와 `--resume` 지원
- Empty output이나 예외에 source fallback을 사용하지 않음

### Pair metadata hardening

각 pair에 대해 original control input과 NLLB input의 top-level diff를 계산한다. 다음 invariant가 하나라도 다르면 input 생성이 실패한다.

```text
image_paths
gold_label
parallel_id
source_question_language
gui_language
option_order
question_sample_id
gui_sample_id
```

허용된 변화는 query content, condition, effective query language 및 translation metadata뿐이다. 전체 10,980 pair의 diff가 `rel_nllb_pair_metadata_diff.csv`에 저장된다.

VLM inference 완료 후 두 번째 strict audit가 original result와 NLLB result에 대해 다음을 다시 비교한다.

- exact `image_paths`
- gold/item/source/GUI identity
- model 및 processor revision
- prompt profile와 fixed-English system prompt
- precision, attention 및 vision-processing metadata

이 audit를 통과해야 21,960행 GLMM table이 생성된다.

### Thin VLM runner

기존 Qwen/InternVL adapter와 model config를 그대로 재사용한다. 다음만 새로 추가한다.

- Direct intervention-input consumption
- RQ4 metadata 기록
- `generation_correct` 직접 기록
- 10,980행·language alignment·translator revision 사전 검증
- Missing image fail-fast
- failure log 및 resume

Primary outcome은 계속 `generation_correct`이다. Label scoring은 요구하지 않으며 RQ4 primary analysis에 사용하지 않는다.

### Statistical analysis

Target human-parallel endpoint 분석:

- 단위: `parallel_id × target GUI language`, 모델당 2,196개
- 각 단위의 다섯 original mismatch를 평균
- `(Q_B,G_B)` endpoint와의 gap 계산
- `parallel_id` cluster bootstrap
- intervention test가 아닌 headroom sanity check

Primary RQ4 GLMM:

```r
generation_correct ~
    source_question_language * text_dependency
    gui_language * text_dependency
    intervention * text_dependency
    (1 | parallel_id)
    (1 | pair_id)
```

- M1 대 M2 1-df LRT가 primary test
- Primary effect: `intervention × text_dependency`
- Pair random intercept가 실패하거나 M0–M2 중 하나라도 singular이면 전체 ladder를 `(1|parallel_id)`로 다시 적합
- M1과 M2는 항상 같은 random-effects structure 사용
- 30 directed language pair를 동일 가중한 independent/dependent MT gain과 probability DID 출력

## 3. GEE 범위 결정

GEE sensitivity는 사용자의 결정에 따라 **현재 구현과 실행 계획에서 제외했다.** 현재 코드에는 GEE 적합 또는 `geepack` 의존성이 없다. 이는 분석 포기가 아니라 primary GLMM 결과를 확인한 뒤 별도 승인하에 수행할 후속 sensitivity 계획이다.

## 4. 현재까지의 검증

- Frozen REL items: 366
- Directed directions: 30
- Translation rows: 10,980
- Translated fields: 54,900
- Translation plan에 dependency label: 없음
- Source question layout round trip: 2,196/2,196 exact
- Python tests: 통과
- R scripts: parse 통과
- VLM/NLLB model 실행: 아직 수행하지 않음
- GLMM fitting: 아직 수행하지 않음

## 5. 이미 계산된 target human-parallel headroom

이 결과는 NLLB intervention 결과가 아니라 기존 6×6 결과로 계산한 descriptive endpoint reference다.

| Model | Dependency | Original mismatch | Human-parallel endpoint | Recoverable gap | Item-bootstrap 95% CI |
|---|---|---:|---:|---:|---:|
| Qwen | Independent | 67.14% | 66.67% | −0.47%p | −2.86–2.19%p |
| Qwen | Dependent | 59.88% | 72.30% | +12.42%p | 10.23–14.75%p |
| InternVL | Independent | 60.21% | 59.90% | −0.31%p | −3.59–2.92%p |
| InternVL | Dependent | 48.72% | 61.87% | +13.15%p | 10.81–15.44%p |

Dependent-minus-independent headroom difference:

- Qwen: +12.89%p, 95% CI 9.45–16.15%p
- InternVL: +13.46%p, 95% CI 9.48–17.56%p

이는 RQ4에 필요한 headroom이 dependent subset에 존재한다는 sanity check다. Human-parallel wording까지 함께 달라지므로 causal language-only effect로 해석하지 않는다.

## 6. 실행 순서

아래 명령은 repository의 `01_code`에서 실행한다.

### Step 0 — 전용 Python 환경

```powershell
conda create -n mpr-rq4-nllb python=3.12 -y

conda run --no-capture-output -n mpr-rq4-nllb python -m pip install `
  torch==2.8.0 torchvision==0.23.0 `
  --index-url https://download.pytorch.org/whl/cu128

conda run --no-capture-output -n mpr-rq4-nllb python -m pip install -e ".[models]" `
  -c configs/interventions/rq4_nllb_constraints.txt
```

이미 CPU-only Torch가 설치된 경우에는 다음으로 교체한다.

```powershell
conda run --no-capture-output -n mpr-rq4-nllb python -m pip uninstall `
  torch torchvision -y

conda run --no-capture-output -n mpr-rq4-nllb python -m pip install `
  torch==2.8.0 torchvision==0.23.0 `
  --index-url https://download.pytorch.org/whl/cu128
```

환경 확인:

```powershell
conda run --no-capture-output -n mpr-rq4-nllb python -c `
  "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)"
```

기대값은 `2.8.0+cu128`, CUDA `12.8`, `True`, `NVIDIA GeForce RTX 3060`이다.

### Step 1 — Dependency-blind plan dry-run

```powershell
conda run --no-capture-output -n mpr-rq4-nllb python -m `
  mpr_crosslocale.interventions.build_rel_nllb_translations `
  --annotation-manifest ../annotation/rel_text_dependency/data/pilot_manifest.json `
  --qas-dir data/raw/mpr_gui_bench_qas/qas `
  --config configs/interventions/rel_nllb_query_alignment.yaml `
  --plan-out data/derived/interventions/rel_nllb_translation_plan.jsonl `
  --dry-run
```

기대 결과: `rows=10980`, `directions=30`, `translated_fields=54900`.

### Step 2 — 로컬 RTX 3060 NLLB 번역

```powershell
conda run --no-capture-output -n mpr-rq4-nllb python -m `
  mpr_crosslocale.interventions.build_rel_nllb_translations `
  --annotation-manifest ../annotation/rel_text_dependency/data/pilot_manifest.json `
  --qas-dir data/raw/mpr_gui_bench_qas/qas `
  --config configs/interventions/rel_nllb_query_alignment.yaml `
  --output data/derived/interventions/rel_nllb_translations.jsonl `
  --device cuda `
  --batch-size 16 `
  --resume
```

OOM이면 batch size만 8 또는 4로 낮춘다. Batch size는 row별 runtime metadata에 기록되며 translation protocol 자체는 변하지 않는다.

### Step 3 — Intervention input 및 pair diff audit

```powershell
conda run --no-capture-output -n mpr-rq4-nllb python -m `
  mpr_crosslocale.interventions.build_rel_nllb_inputs `
  --translations data/derived/interventions/rel_nllb_translations.jsonl `
  --nllb-inputs-out data/derived/interventions/rel_nllb_inputs.jsonl `
  --original-controls-out data/derived/interventions/rel_nllb_original_controls.jsonl `
  --pair-diff-audit-out data/derived/interventions/rel_nllb_pair_metadata_diff.csv
```

기대 결과: 세 artifact 모두 10,980 pairs, diff failures 0.

### Step 4 — 외부 GPU preflight

Qwen:

```bash
python -m mpr_crosslocale.inference.run_rel_nllb_intervention \
  --inputs data/derived/interventions/rel_nllb_inputs.jsonl \
  --model-config configs/models/qwen2_5_vl_7b.yaml \
  --output results/raw/rq4/qwen_rel_nllb.jsonl \
  --failures-out results/raw/rq4/qwen_rel_nllb_failures.jsonl \
  --repo-root . \
  --dry-run
```

InternVL은 model config와 output 이름만 바꾼다.

### Step 5 — 외부 GPU VLM inference

Qwen:

```bash
python -m mpr_crosslocale.inference.run_rel_nllb_intervention \
  --inputs data/derived/interventions/rel_nllb_inputs.jsonl \
  --model-config configs/models/qwen2_5_vl_7b.yaml \
  --output results/raw/rq4/qwen_rel_nllb.jsonl \
  --failures-out results/raw/rq4/qwen_rel_nllb_failures.jsonl \
  --repo-root . \
  --run-id rq4-qwen-rel-nllb-v1 \
  --resume
```

InternVL:

```bash
python -m mpr_crosslocale.inference.run_rel_nllb_intervention \
  --inputs data/derived/interventions/rel_nllb_inputs.jsonl \
  --model-config configs/models/internvl2_5_8b.yaml \
  --output results/raw/rq4/internvl_rel_nllb.jsonl \
  --failures-out results/raw/rq4/internvl_rel_nllb_failures.jsonl \
  --repo-root . \
  --run-id rq4-internvl-rel-nllb-v1 \
  --resume
```

### Step 6 — 21,960행 strict validation

Qwen:

```powershell
conda run --no-capture-output -n mpr-rq4-nllb python -m `
  mpr_crosslocale.interventions.validate_rel_nllb_results `
  --original-results results/raw/vast_6x6_qwen2_5_vl_7b.jsonl `
  --nllb-results results/raw/rq4/qwen_rel_nllb.jsonl `
  --nllb-inputs data/derived/interventions/rel_nllb_inputs.jsonl `
  --annotations ../annotation/rel_text_dependency/outputs/rel_annotations_integrated_366.csv `
  --combined-out data/derived/interventions/qwen_rel_nllb_combined_21960.csv `
  --pair-audit-out results/analysis/qwen/rq4_rel_nllb_v1/pair_result_audit.jsonl `
  --summary-out results/analysis/qwen/rq4_rel_nllb_v1/input_validation.json
```

InternVL은 original/NLLB input과 output prefix를 `internvl`로 바꾼다.

### Step 7 — Local pair-aware GLMM

Qwen:

```powershell
conda run --no-capture-output -n mpr-r-analysis Rscript `
  analysis/rel_nllb_intervention_glmm.R `
  data/derived/interventions/qwen_rel_nllb_combined_21960.csv `
  results/analysis/qwen/rq4_rel_nllb_v1 `
  1 2000 42
```

InternVL:

```powershell
conda run --no-capture-output -n mpr-r-analysis Rscript `
  analysis/rel_nllb_intervention_glmm.R `
  data/derived/interventions/internvl_rel_nllb_combined_21960.csv `
  results/analysis/internvl/rq4_rel_nllb_v1 `
  1 2000 42
```

### Step 8 — Human-parallel endpoint 재현

Qwen:

```powershell
conda run --no-capture-output -n mpr-r-analysis Rscript `
  analysis/rel_nllb_oracle_analysis.R `
  data/derived/qwen_glmm.csv `
  ../annotation/rel_text_dependency/outputs/rel_annotations_integrated_366.csv `
  results/analysis/qwen/rq4_target_human_parallel_v1 `
  2000 42
```

InternVL은 `qwen_glmm.csv`와 output directory를 `internvl`로 바꾼다.

## 7. 해석 순서

최종 보고 순서는 다음으로 고정한다.

1. Independent NLLB adjusted gain
2. Dependent NLLB adjusted gain
3. Dependent-minus-independent probability DID
4. M1 vs M2 LRT
5. Human-parallel endpoint residual headroom

Primary success pattern은 dependent gain이 independent gain보다 큰 경우다. NLLB가 향상되지 않거나 반대 패턴이어도 사전 고정된 RQ4 결과로 그대로 보고한다.

## Protocol amendment: deterministic empty-translation retry (2026-08-11)

Frozen decoding이 공백만 생성해 `decoded_output.strip() == ""`가 되는 경우에 한해 다음 정책을 적용한다.

1. 같은 NLLB model/revision과 원문을 유지한다.
2. 해당 field만 batch size 1로 한 번 재시도한다.
3. 재시도에는 `repetition_penalty = 1.1`만 추가한다.
4. source fallback과 human correction은 사용하지 않는다.
5. 재시도 결과가 non-empty이면 `recovered_after_empty_retry`로 기록한다.
6. 재시도도 empty이면 10,980행 artifact에는 그대로 보존하되 `failed_empty_after_retry`, `translation_analysis_eligible=false`, 실패 field를 기록한다.
7. 모든 문제 행은 `data/derived/interventions/rel_nllb_translation_issue_audit.jsonl`에도 별도로 저장한다.

이 amendment는 `rel::5/record_12.jpg::source=zh::gui=th::nllb`의 question stem에서 downstream VLM 결과를 보기 전에 발견된 deterministic empty decoding에 대응하기 위한 것이다. 번역의 자연스러움이나 downstream accuracy에 따라 retry를 적용하지 않는다.

최종 GLMM script의 선택적 여섯 번째 인수는 다음과 같다.

- `include`: 모든 10,980 pair 유지
- `exclude_failed`: 재시도 후에도 empty인 pair만 original/NLLB 양쪽에서 제외
- `exclude_any_issue`: empty retry가 발생한 pair를 recovery 여부와 무관하게 양쪽에서 제외

Primary 정책을 변경할 경우 결과 디렉터리를 분리하고 model spec에 정책을 남겨야 한다. GEE sensitivity는 기존 결정대로 현재 구현 범위에서 제외되어 있다.
