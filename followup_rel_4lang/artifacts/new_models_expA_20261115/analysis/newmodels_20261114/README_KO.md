# run_frozen_analysis.py 사용법

```
python3 run_frozen_analysis.py <model_key> <unpacked_dir> <out_dir> [--no-context] [--skip-diag]
```

- `unpacked_dir`: `rel_full/`과 `expa_full/`이 들어 있는 폴더(예: `.../unpacked/sizes_qwen3_vl_4b`). 상위 폴더를 줘도 `*/rel_full`을 찾는다.
- 로컬 전용. 네트워크, GPU, R 호출 없음. 약 15초(8B 참고 계산 포함).
- 시작할 때 `분석규칙_v1.md`의 sha256을 `.FROZEN.txt`와, `diag_expA.py`의 sha256을 `DIAGNOSTIC_PLAN_THAI_KO.FROZEN.txt`와 대조한다. 다르면 중단한다. 입력 3개 파일의 sha256, 코드 sha256은 `results.json`의 `provenance`에 기록한다.

## 기존 코드 재사용(원본 수정 없음)
| 단계 | 재사용 대상 |
|---|---|
| REL quartet 구성, 제외 규칙, 큐 summary.json 대조 | `analysis_qwen3_20261108/rel4/prepare_glmm_qwen3.py`의 `project_row`, `quartet_table`, `validate_summary`를 경로로 import |
| REL bootstrap/Holm | `analysis_plan_followup/scripts/t1_holm.py` 로직(경로가 하드코딩이라 약 10줄 복사). p는 규칙 문구대로 (1+개수)/(B+1) |
| 실험 A 주 분석 | `analyze_expA.py`를 CLI로 한 번, import로 한 번(태국어 제외 변형용) 돌려 두 값이 같은지 assert |
| 실험 A 진단 | `diag_expA.py`를 `python3 -I`로 실행. 라벨은 모델 이름이 `qwen3`/`internvl35`(-8b)가 아니면 "descriptive" |

## 출력(out_dir)
`results.json`(모든 수치), `tables_KO.md`(표), `expA_analyze/`, `diag_expA/`.

## 다른 모델에 쓸 때
- 필드 이름은 큐 어댑터가 같은 `results.jsonl`/`predictions.jsonl` 스키마를 쓴다는 가정이다. REL `results.jsonl`에 `primary_analysis_eligible`, `source_issue`, `referent_alignment`, `context_localization` 등이 있어야 한다(없으면 `project_row`에서 KeyError로 멈춘다).
- `visual_token_count`가 기록되는 모델(InternVL/MiniCPM)이면 `tokens.*.visual`에 값이 들어가고, 아니면(Qwen3) `prompt_token_count`만 보고한다. 둘 다 `results.json`의 `tokens`에 나온다.
- 모델 이름이 `diag_expA.py`의 확인용 집합에 없으면 라벨은 자동으로 descriptive다. 새 모델에 "confirmatory"가 붙는 일은 없다.
- 6×6은 이 버전에 없다. 읽기 지표 (b)도 계산하지 않는다.
- GLMM Wald p(민감도)는 `Rscript`가 있어야 하는데 이 컴퓨터에 없다. `results.json`의 `rel_glmm`에 건너뛴 사실을 적고, 다른 방법으로 대체하지 않는다. R이 있는 환경에서 돌리는 래퍼는 아직 없다(미검증).

## 기록해 둔 정의 선택(규칙이 정하지 않은 부분)
1. "태국어 제외"를 두 가지로 모두 계산한다. `noTH_screen`: 화면 언어가 태국어인 쌍 제외(규칙 0절의 "en·zh·ru 화면 묶음"). `noTH_both`: 질문·화면 어느 쪽에도 태국어 없음(6×6의 5×5와 같은 방식). 규칙은 REL·실험 A에 어느 쪽인지 적지 않았다.
2. 읽기 지표 (a)의 분모 "전체 문항": 8B 두 모델에서 규칙에 적힌 0.95/0.60을 재현하는 정의를 기준으로 썼다(교차 언어, source_issue 없는 R 행, 의존·독립 문항 모두). 모든 행을 쓰는 변형도 같이 적는다.
