# 정확도·비용을 함께 보는 method 탐색 설계

2026-11-15. 상태: **설계·실행기·확대 cohort 준비 및 CPU 검증 완료. 신규 GPU 실측은 아직 없음.** 기존 한 pair의 smoke 결과를 후보 성능으로 일반화하지 않는다. 현재 원시 자료와 frozen dataset/split을 유지한다.

## 1. 무엇을 선택할 것인가

목표는 현재 inventory→referent→matching 구조를 통과시키는 것이 아니라, **원래 문맥을 보존하면서 실제 GUI 표현에 맞추는 방법 중 정확도·회귀·비용의 균형이 좋은 방법을 찾는 것**이다.

두 종류의 결론을 분리한다.

- 연구 결론: 같은 자동 span에서 TXT_SEL 대 GUI 기반 방법을 비교하면 화면 lexical evidence의 추가 가치를 볼 수 있다. TXT_FULL/GUI_FULL은 전체 번역 기준이다.
- 실용 선택: 직접 이미지 edit가 가장 잘 되면 그것도 채택 후보다. 다만 전체 screenshot을 보므로 이득을 lexical alignment 하나로 귀속하지 않는다. TXT_DIRECT_VLM과 같은 가중치·출력 인터페이스의 대조도 둔다.

여러 후보를 관찰하고 고른 방법은 개발 표본의 winner다. 작고 반복 관찰한 표본에서 얻은 최고 점수를 일반화 성능이라고 쓰지 않는다.

## 2. 파일럿 확대와 선택 편향 통제

기존 main 158개를 나눈 calibration40/internal evaluation118은 바꾸지 않는다. Calibration40 안에서 app군 비율을 보존하며 20/20으로 다시 나눈다. Seed20261115와 ID hash로 고정하고 결과 정확도를 사용하지 않았다.

| 용도 | Semantic items | 고유 source MCQ | GUI pair | 주 분석 main pair |
| --- | ---: | ---: | ---: | ---: |
| Probe: 빠른 기능·비용 확인 | 기존 pilot 중8 | 32 | 32 | 해당 없음 |
| 확대 screen: 반복 개선 허용 | 기존 pilot12 + calibration20 = **32** | **128** | **288** | **240** |
| Selection: shortlist 선택 확인 | 남은 calibration20 | 80 | 240 | **239** |
| Internal evaluation: 최종 고정 후 | 기존118 | 472 | 1,416 | 1,416 |

288을 32×12=384로 적지 않는다. 기존 pilot12는 각4개 순환 pair뿐이라48쌍이고, 추가20은 각12개 pair라240쌍이다. 따라서 screen의 12방향 분포는 균등하지 않다. 12방향을 모두 갖춘 **추가 main20의240쌍을 구조 선택의 주요 표본**으로 보고, legacy48쌍은 별도 robustness/디버깅 결과로 제시한다. 전체288을 단순 합산한 정확도는 보조치다.

사전 제외 `rel::5/forest_9.jpg::zh::ru`는 selection에 들어갔다. 실행·실패 로그에는 보존하고, primary accuracy에서는 제외하므로239쌍이다. 포함한240쌍의 sensitivity를 따로 낸다.

동일 screenshot SHA 또는 동일 state key의 기존 partition 간 중복은0개였다. Manifest 생성기는 이 경계를 넘는 중복이 생기면 중단하며, group을 조용히 쪼개지 않는다. Perceptual near-duplicate까지 판정한 것은 아니다.

**Selection 운영 규칙:** screen에서 튜닝 후 shortlist와 prompt/config hash를 고정한 뒤20개 selection item을 본다. Selection 결과를 보고 수정하면 해당 집합도 tuning에 사용됐다고 기록한다. 이후에도 탐색은 가능하지만 “계속 untouched였던 selection”으로 부르지 않는다. Internal evaluation118은 그때까지 사용하지 않는다. 전체158개가 역사적으로 관찰된 development cohort라는 한계는 그대로다.

Manifest: [search_plan_v1/manifest.json](../artifacts/search_plan_v1/manifest.json). 원문 입력은 allowlist JSONL로만 복원하며 정답·parallel 표현은 candidate 실행기에 전달하지 않는다.

## 3. 후보를 작은 축으로 나눈다

### A. 참조 추출: 3 prompts × 2 models + CPU 대조

| ID | 모델 | 지시 |
| --- | --- | --- |
| fixed_original | 고정 Qwen3-8B | 기존 지시 그대로 |
| fixed_minimal | 고정 Qwen3-8B | 최소 label·남길 문맥·숫자 포함 이름을 명확히 정의 |
| fixed_contrastive | 고정 Qwen3-8B | minimal + synthetic 경계/제외 예시 및 다국어 복사 예시 |
| vl_original | 평가 Qwen3-VL, 이미지 없음 | original |
| vl_minimal | 같은 Qwen3-VL, 이미지 없음 | minimal |
| vl_contrastive | 같은 Qwen3-VL, 이미지 없음 | contrastive |
| cpu_quoted | CPU 정규식 | 인용부호 안 문자열만 추출하는 진단 기준 |

`vl_text`는 **전체 VLM을 이미지 없이 호출**한다. Multimodal 학습 후 LM 가중치를 사용하지만 vision 모듈을 제거하거나 raw decoder 직접 호출을 구현한 것은 아니다. 순수 Qwen3-8B와 같은 checkpoint라고 부르지 않는다. Raw backbone 분리가 필요하면 출력 동등성·메모리·속도를 별도 engineering 실험으로 검증한다.

새 지시는 label 문자열과 `blue/button/input field/horizontal center` 같은 보호할 문맥을 구분한다. Original을 제외한 새 지시는 일반 `kind` 분류를 요구하지 않는다. 이름 없는 아이콘은 유지한다. Quote는 단서이지 필요조건은 아니다. 모든 annotation span에 대한 F1을 계산하되, 이름 없는 요소를 의도적으로 유지한 사례와 실패로 놓친 label은 검수에서 구분한다.

Contrastive 예시는 benchmark에서 가져오지 않은 synthetic 예시다. 영어 경계 예시와 RU/ZH/TH 복사 예시가 있으므로 이것이 완전히 언어 균형적인 few-shot이라고 주장하지 않는다. Source 언어별 결과를 반드시 본다.

### B. 전체 구조: 9개 recipe

| ID | 변환 | 화면 정보 | 주요 비교 목적 |
| --- | --- | --- | --- |
| TXT_SEL | 공통 자동 span만 번역 | 없음 | 같은 span을 사용하는 text-only 기준 |
| GUI_EXACT | span 번역→inventory exact match | 전체 query-blind inventory | 현재 보수적 구조 |
| GUI_MATCH_LM | LM이 source span을 inventory 문자열에 연결 | 같은 inventory | 번역 동의어 때문에 exact match가 놓치는 경우 |
| GUI_TARGETED_VLM | 추출 span별로 VLM이 화면 label 확인 | Screenshot + 모든 span | 전체 inventory 생성 비용을 생략 |
| GUI_DIRECT_VLM | VLM이 원문 span·target label edit를 함께 제안 | Screenshot + MCQ | 별도 inventory·extractor 생략 |
| TXT_DIRECT_LM | 고정 LM이 selective edit 직접 제안 | 없음 | 단일 text-only method |
| TXT_DIRECT_VLM | 평가 VLM이 같은 direct edit 지시 수행 | 없음 | GUI_DIRECT_VLM과 같은 모델의 이미지 대조 |
| TXT_FULL | MCQ 전체 번역 | 없음 | 전체 번역 기준 |
| GUI_FULL | MCQ 전체 번역 | Query-blind inventory | 전체 번역 + lexical evidence 기준 |

Inventory 모델은 항상 평가 VLM이다. 현재 실행기는 Qwen3-VL만 지원하며 Qwen2.5-VL/InternVL은 후속이다. 고정 translator/matcher는 Qwen3-8B를 쓴다.

GUI_TARGETED_VLM은 원래 공간 관계 질문 전체 대신 span ID·field·원문 표현을 모두 받는다. A–D 중 정답 하나를 고르지 않는다. GUI_DIRECT_VLM에는 전체 질문과 이미지가 있으므로 답 추론 개입의 가능성이 더 크다.

GUI_MATCH_LM은 반드시 inventory의 verbatim member 또는 null을 반환한다. GUI_TARGETED/GUI_DIRECT에는 독립 inventory가 없으므로 실제 화면에서 읽은 문자열인지 코드만으로 보증하지 못한다. 별도 화면 검수가 필요하다. 자기보고 confidence는 확률로 사용하지 않는다.

이9개를 extractor7개와 무조건 곱해63개 조합으로 실행하지 않는다. 먼저 추출 운영점을 줄이고 구조를 비교한다. Direct/full 계열은 공통 추출기를 쓰지 않는다.

## 4. 실행 순서와 승격

1. **Probe A:** 기존8개 item에서 CPU 기준과 LLM6조건을 비교한다. 32개 source MCQ/조건이며 최대192회 LLM 추출 호출이다. JSON 실패, 빈 목록, span 경계, 토큰·시간을 본다. 전부 실패하면 구조 비교를 바로 시작하지 않고 원인을 수정한다.
2. **Screen A:** quality–cost Pareto에서 최대2개 extractor를 확대128개 source MCQ로 늘린다. Probe와 같은 호출은 캐시한다. Recall이 낮아 빠른 empty-output을 효율 winner로 고르지 않는다. Stem/option·언어별 품질을 같이 보고 낮은 recall이 의도한 abstention인지 확인한다.
3. **Probe B:** 구조9개를 probe32쌍에서 먼저 실행한다. Schema·유효 edit·fallback·시간을 확인하고 O 대비 정확도도 탐색적으로 기록한다. 이 작은 순환 pair 집합에서 +1문항이라고 바로 승자를 정하지 않는다.
4. **Screen B:** 유효한 구조 중 최대3개를 screen으로 확대한다. TXT_SEL과 TXT_FULL은 유지하며, inventory finalist가 있으면 GUI_FULL, direct visual finalist가 있으면 TXT_DIRECT_VLM을 해당 대조로 유지한다. 정확도형·저비용형을 남겨 선택지가 한 가지로 조기에 좁아지지 않게 한다. 탈락 기준과 실행하지 않은 후보도 기록한다.
5. **Selection:** screen에서 고정한 최대2개 구조 finalist와 필요한 대조만 남은20문항에서 평가한다. 정답률·regression·Thai GUI·비용을 함께 확인한 뒤 모델·prompt·fallback·선택 규칙을 동결한다.
6. **Internal evaluation:** 준비된 실행 결과를 검토한 뒤 최종 method와 사전 대조를118개 item에 한 번 실행한다. Primary2×2 및 routing은 이때 고정한 method 정의에 맞춰 구성한다. Direct visual을 선택했다면 lexical-only 효과를 주장하는 factorial과 구별한다. Pivot 확장은 기본 method가 정리된 뒤다.

새 prompt나 matcher 정책을 추가할 때마다 새 ID·hash와 이유를 남긴다. Selection을 본 뒤 추가한 후보는 같은 selection의 독립 비교로 표시하지 않는다. 자동 sweep나 자동 winner 선정은 기본 제공하지 않는다.

## 5. 정확도·실패·효율의 공동 평가

### 추출과 edit 품질

- Schema 실패와 valid empty output을 구분한다.
- Exact-span precision/recall/F1, 완전한 span set 비율, stem/option별·언어별 누락과 문맥 침범을 집계한다.
- 같은 MCQ를 target GUI3개에 복제해 extraction 분모를3배로 부풀리지 않는다.
- 넓은 source span은 annotation exactness에서 따로 드러낸다. Annotation과의 일치만으로 target GUI 대응 정답을 판정하지 않는다.
- Direct method는 최종 edit만 드러낸다. 그 edit span의 정확도를 extractor의 전체 recall과 동일시하지 않는다.
- 실패와 abstention은 삭제하지 않고 원문 유지로 포함한다. Fallback도 downstream 평가 대상이다.

### 최종 문제 풀이

동일한 Qwen3-VL revision·system·greedy·2MP·max_new_tokens2를 사용한다. O와 후보를 condition별로 나눠 같은 pair 순서·배치 상한3으로 처리한다. 서로 다른 조건을 마지막 배치에 섞지 않는다. 과거 run과 batch composition이 완전히 같은 것은 아니므로 O anchor agreement는 최종 분석에서 따로 보고한다.

Main pair accuracy, O 대비 paired 차이, recovery/regression, GUI 언어·12방향, worst pair를 본다. 선택 단계의20 semantic item에 대한 cluster bootstrap CI를 사용하고,239쌍을239개의 독립 문항처럼 취급하지 않는다. Screen/selection의 다수 후보 p값으로 승자를 입증하지 않는다. 최종 고정 대비에서만 기존10,000회 bootstrap·primary contrast 보정 계획을 적용한다.

### 비용

- 모델 load를 포함한 wall time, load 제외 generate/runtime, input/output tokens, p50/p95, peak VRAM을 분리한다.
- 현재 실행기는 call별 tokens/runtime/load와 GPU hardware를 기록한다. p50/p95는 calls.json에서 계산한다. **Peak VRAM 수집은 아직 구현하지 않았으므로 모른다고 보고한다.**
- 실제 새로 소비한 비용과 캐시된 호출의 과거 비용을 분리한다. Cache hit를0초 method로 평가하지 않는다.
- Inventory/extraction의 한 번 생성 비용을 재사용 횟수와 함께 기록한다. 한 source MCQ→GUI3개, 같은 screenshot→source3개에서 공유 가능한 비용이 다르다.
- 콜드 스타트, 이번 데이터셋에서 공유한 전체 비용, query 한 개를 처리하는 비용을 따로 본다. 재사용 덕분의 이득을 단독 latency와 혼동하지 않는다.
- 달러 비용은 실제 장비의 청구 시간·요율이 있을 때만 환산한다. 이 서버의 미청구 시간에 임의의 VastAI 단가를 곱하지 않는다.

정확도 최대 후보와 Pareto의 저비용 후보를 함께 남긴다. 정량 cutoff를 아직 정답처럼 고정하지 않는다. Selection 전 운영상 동점 허용 폭(예:1pp), 허용할 regression 및 비용 우선순위를 decisions 기록에서 동결한다. 239쌍에서1pp는2–3문항 차이라 동점 대역은 통계적 동등성 주장이 아니다. 선택 자료의 불확실성이 크면 하나의 유일한 winner를 강제하지 않아도 된다.

### 독립 화면 검수

Finalist별 적용 edit 최대48개를 source/GUI 언어와 stem/option에서 가능한 한 고르게 표집해 화면 대응·다른 GUI 요소로의 오매칭·문맥 훼손을 검수한다. 실패·abstain도 별도로 표집해 inventory 누락과 matcher 실패를 구분한다. 수동 검수량·분모를 기록하며0/48을 모집단 오류0%로 표현하지 않는다. 미검수 matching precision은 null이다.

## 6. 예상 계산량을 읽는 법

기존 한 pair의 실측은 inventory79.1초/226tokens, non-empty 추출58.0–66.6초/181–209tokens였다. 다운로드 병행·계측 hook이 있어 정밀 throughput benchmark는 아니다.

같은66.6초라고 단순 가정하면 Probe A의192회는 약3.55시간이다. Screen A에서2개를128개까지 늘리면 probe 밖96개×2의192회가 추가되어 약3.55시간이다. 이는 **토큰 길이와 하드웨어가 같다고 가정한 산술 예시**이고 신규 추정 실측이 아니다. 새 prompt가 더 짧은 JSON을 생성하면 줄고, 참조가 많으면 늘 수 있다.

Screen의128개 screenshot을 전부 같은79.1초로 처리하면 inventory만 약2.81시간이다. 전체 inventory를 생략하는 후보를 두는 이유다. 반대로 direct visual은288개 pair마다 이미지 prefill과 edit 생성을 하므로 자동으로 더 싸다고 보장되지 않는다.

Probe 이후 실제 token/runtime 분포를 사용해 다음 단계의 **남은 고유 호출 수 × 평균 시간 + 모델 교체/load**로 재산정한다. 이 단계별 예산표를 확인하며 실행하고,9×288을 먼저 일괄 실행하지 않는다. 기본 method batch는1이며 output 길이·padding이 다른 후보를 무리하게 섞지 않는다. Batch 최적화는 finalist에 대해 따로 확인한다.

## 7. 구현된 실행 경로와 재현 명령

- 후보·prompt: [search.py](../../../01_code/src/mpr_crosslocale/methods/selective_alignment/search.py).
- 후보 registry: [search_v1.json](../configs/search_v1.json).
- 코호트 생성: [build_search_plan.py](../scripts/build_search_plan.py).
- 개별 추출/변환: [run_search_trial.py](../scripts/run_search_trial.py).
- 사후 span/검수표: [score_search_trial.py](../scripts/score_search_trial.py).
- 문제 풀이: [infer_search_trial.py](../scripts/infer_search_trial.py).

저장소 root에서 기존 venv를 사용한다. 새 모델이나 유료 GPU를 자동 생성하지 않는다.

```bash
source .venv/bin/activate
export OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3
export XDG_CACHE_HOME=/home/jovyan/seungjae/.cache
export HF_HOME="$XDG_CACHE_HOME/huggingface"
export TORCH_HOME="$XDG_CACHE_HOME/torch"
export PIP_CACHE_DIR="$XDG_CACHE_HOME/pip"
export PYTHONPATH=01_code/src:.
```

새 clone에서는 기존 README의 audit로 method_inputs/split/oracle/labels를 복원한 후 실행한다. 아래 manifest는 이미 생성했다. 새 실행은 output-dir을 바꾼다.

```bash
python followup_rel_4lang/method_dev/scripts/build_search_plan.py \
  --inputs followup_rel_4lang/method_dev/artifacts/dataset_audit/method_inputs.jsonl \
  --split followup_rel_4lang/method_dev/artifacts/dataset_audit/split.json \
  --spec followup_rel_4lang/method_dev/configs/search_v1.json \
  --output-dir followup_rel_4lang/method_dev/artifacts/search_plan_rebuild
```

Manifest는 파일 content의 canonical hash와 모든 item ID를 포함한다. 원래 manifest와 일치해야 한다. 실험 config의 모델 path가 없으면 다음처럼 개인 HF snapshot 경로를 만든다.

```bash
python followup_rel_4lang/method_dev/scripts/materialize_config.py \
  --template followup_rel_4lang/method_dev/configs/gcsa_qwen3_fixed_lm_v1.json \
  --hf-home "$HF_HOME" \
  --output followup_rel_4lang/method_dev/artifacts/search_models.json
```

한 candidate의 **CPU mock** 확인 명령이다. Mock 출력은 실제 정확도·시간으로 사용하지 못한다.

```bash
python followup_rel_4lang/method_dev/scripts/run_search_trial.py \
  --plan followup_rel_4lang/method_dev/artifacts/search_plan_v1/manifest.json \
  --spec followup_rel_4lang/method_dev/configs/search_v1.json \
  --config followup_rel_4lang/method_dev/artifacts/search_models.json \
  --cohort probe --extractor fixed_minimal --recipe GUI_DIRECT_VLM \
  --limit-items 1 --mock \
  --cache-dir followup_rel_4lang/method_dev/artifacts/search_cache \
  --output-dir followup_rel_4lang/method_dev/artifacts/probe_direct_mock
```

실제 GPU 추출 비교는 같은 명령 형식에서 `--recipe extraction --gpu`를 사용한다. 다음은 probe8문항 전체의 fixed_minimal 한 조건이다. **최대32개 고유 MCQ 호출의 긴 작업**이며 이번 준비 중 실행하지 않았다.

```bash
python followup_rel_4lang/method_dev/scripts/run_search_trial.py \
  --plan followup_rel_4lang/method_dev/artifacts/search_plan_v1/manifest.json \
  --spec followup_rel_4lang/method_dev/configs/search_v1.json \
  --config followup_rel_4lang/method_dev/artifacts/search_models.json \
  --cohort probe --extractor fixed_minimal --recipe extraction --all-items --gpu \
  --cache-dir followup_rel_4lang/method_dev/artifacts/search_cache \
  --output-dir followup_rel_4lang/method_dev/artifacts/probe_fixed_minimal
python followup_rel_4lang/method_dev/scripts/score_search_trial.py \
  --trial-dir followup_rel_4lang/method_dev/artifacts/probe_fixed_minimal \
  --oracle-spans followup_rel_4lang/method_dev/artifacts/dataset_audit/oracle_spans_DIAGNOSTIC_ONLY.jsonl
```

`--extractor`만 바꾸어 다른 추출 조건을 실행한다. 후보별 새 output-dir을 사용한다. 구조 비교는 `--recipe`를 registry의9개 ID 중 하나로 바꾼다. `--cohort screen/selection --all-items`는 해당 전체 cohort이며 묵시적으로 실행하지 않는다. Extraction cache는 같은 지시·payload·모델·generation·backend·소프트웨어·GPU일 때만 공유한다. 원문 모델 추출 결과를 캐시하고 post-hoc gold 점수는 캐시에 넣지 않는다. 병렬로 여러 GPU 작업을 띄우지 않는다.

완료된 실제 rewrite에 대한 문제 풀이는 다음 형식이다. Baseline contract는 Qwen3 ExpA8B의 frozen contract다.

```bash
python followup_rel_4lang/method_dev/scripts/infer_search_trial.py \
  --trial-dir followup_rel_4lang/method_dev/artifacts/probe_gui_direct_gpu \
  --original-inputs followup_rel_4lang/method_dev/artifacts/search_plan_v1/probe.jsonl \
  --labels followup_rel_4lang/method_dev/artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl \
  --baseline-contract followup_rel_4lang/artifacts/new_models_expA_20261115/analysis/expA_8b_20261114/qwen3/expA_qwen3/full/run_contract.json \
  --output-dir followup_rel_4lang/method_dev/artifacts/pred_probe_gui_direct
```

`probe_gui_direct_gpu`는 실제 GPU rewrite를 만들었을 때 지정할 예시 경로다. Mock trial은 이 실행기가 거절한다. `COMPLETE` 없는 부분 결과도 평가하지 않는다. 모델 적재·OOM 등 infrastructure 실패는 실패 호출의 wall time을 기록하고 trial을 중단한다. JSON/schema 실패는 원문 fallback으로 포함한다. Calibration/main과 legacy pilot을 섞은 최종 paired 분석과 finalist 자동 선택은 아직 구현하지 않았으며, descriptive_accuracy.json은 단순 집계라 screen의 main240/legacy48을 따로 분석해야 한다. Internal evaluation 및 pivot 실행은 이 search runner의 선택지에 없다.

## 8. 준비 상태와 남은 한계

신규9개 rewrite recipe와 extraction 경로를 한 item의4쌍에서 CPU mock으로 실행했다. 기존 테스트를 포함한27개 targeted CPU 테스트가 통과했다. 확대 screen의 extraction mock도 실행해32문항·288pair를128개의 source MCQ로 집계하는 것을 확인했다. 실제 새 prompt·matching·direct edit의 GPU 결과는 아직 없다. 따라서 성능 개선, 새 token/runtime 수치, matching precision 또는 winner는 보고하지 않는다.

새 명령으로 단계별 검증·원시 출력·재사용 비용·검수표·최종 문제 풀이를 기록할 수 있다. 이후 남는 일은 실제 probe 실행, 오류 분석과 소수 후보 승격, screen에서의 prompt/정책 선택, selection 관찰 전 shortlist 동결, paired 분석 및 내부 평가 gate다. 모델 수정·batch/vision-token 변경·context routing을 이번 prompt 탐색에 동시에 섞지 않는다.
