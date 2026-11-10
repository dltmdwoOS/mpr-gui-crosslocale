# R_stem / R_opts 분석 코드와 통합 기록

2026-11-10 전달받은 `rstem_ropts_결과_20261110/rstem_ropts_결과_20261110/`를
기존 연구 폴더에 통합했다. [결과 요약](../../results/rstem_ropts_20261110/README_KO.md)은
Qwen3-VL-8B와 InternVL3.5-8B의 같은 158문항·1,896쌍·4조건을 비교한다.

| 위치 (`followup_rel_4lang/` 기준) | 내용 |
| --- | --- |
| `results/rstem_ropts_20261110/{qwen3,internvl35}/raw/` | 원시 예측 gzip, 실행 계약, smoke/완료 gate, STATUS, Qwen 검증 기록 |
| `results/rstem_ropts_20261110/{qwen3,internvl35}/analysis_out/` | 문항 bootstrap 대비, 화면 언어별 탐색 분석, GLMM 입력·계수·LRT·진단 |
| `analysis/rstem_ropts/` | 분석 Python/R 코드, 두 모델 사전 계획 및 정정 |
| `run_rel_mixed.py`, `run_rel_mixed_internvl.py` | 각 모델 R_stem/R_opts 실행기 |
| `run_rstem_ropts*.sh`, `check_rstem_gate*.py` | 실행·완료 점검 |
| `rstem_ropts_inputs/` | 공통 잠긴 입력, 모델별 기존 O/R 기준 예측·실행 계약·환경 제약, 입력 검토 표본 |
| `artifacts/rstem_ropts_20261110/` | InternVL 지원 패치 5개, 파일 대응·해시·커밋 선정 매니페스트. 원본 실행 tar.gz 두 개는 로컬 보관 |

기존 Qwen3 실행 코드와 공통 입력은 줄바꿈을 제외하면 전달본과 같아 유지했다.
기존 `artifacts/qwen3_rstem_ropts_20261109/`의 더 상세한 로그도 보존한다.
새 결과의 Qwen 예측이 기존 예측과 같은지는 통합 검증 기록에서 확인한다.
중복 전송용 tar.gz는 이전 Qwen3 결과 커밋과 같이 Git에서 제외한다.
성공 여부나 정오에 따라 예측 행을 선별하지 않으며 전달받은 두 모델의 전체 예측을 포함한다.
기존 Qwen3 예측과 동일한 gzip은 Git의 같은 blob으로 저장된다.

InternVL 지원 패치 0001–0005를 순서대로 작업 트리에 적용했다. `01_code/`의
InternVL3.5 설정·모델 어댑터·공통 러너와 관련 기존 테스트, 이 폴더 상위의
InternVL 전체 실행/grounding/사전 점검 코드가 포함된다. 현재 통합본에는 이미
적용돼 있다. `RSTEM_ROPTS_INTERNVL_RUNBOOK_KO.md`의 `git am` 절차는
과거 기준 커밋 `666440…`에서 서버 환경을 다시 만드는 절차다.

## 분석 재현

저장소 루트에서 실행한다. Python의 NumPy와 R의 lme4가 필요하다.
예시는 새 출력 폴더에 쓰므로 전달받은 분석 결과를 보존한다.

```bash
python followup_rel_4lang/analysis/rstem_ropts/analyze_rstem.py \
  followup_rel_4lang/results/rstem_ropts_20261110/qwen3/raw/predictions.jsonl.gz \
  followup_rel_4lang/rstem_ropts_inputs/reference_qwen3_20261107_OR.jsonl \
  followup_rel_4lang/results/rstem_ropts_reproduced/qwen3
python followup_rel_4lang/analysis/rstem_ropts/analyze_rstem.py \
  followup_rel_4lang/results/rstem_ropts_20261110/internvl35/raw/predictions.jsonl.gz \
  followup_rel_4lang/rstem_ropts_inputs/reference_internvl35_20261109_OR.jsonl \
  followup_rel_4lang/results/rstem_ropts_reproduced/internvl35
Rscript followup_rel_4lang/analysis/rstem_ropts/glmm_rstem.R \
  followup_rel_4lang/results/rstem_ropts_reproduced/qwen3/glmm_rows.csv \
  followup_rel_4lang/results/rstem_ropts_reproduced/qwen3/glmm
Rscript followup_rel_4lang/analysis/rstem_ropts/glmm_rstem.R \
  followup_rel_4lang/results/rstem_ropts_reproduced/internvl35/glmm_rows.csv \
  followup_rel_4lang/results/rstem_ropts_reproduced/internvl35/glmm
```

통합 시 분석 코드에 gzip 직접 읽기를 추가하고 재현성 JSON 키를 모델 공통
`acc_reference`, `R_minus_O_pp_reference`로 정리했다. 전달받은 Qwen 요약의
`acc_20261107`, `R_minus_O_pp_20261107`는 원본대로 유지했다. 통계 계산은 바꾸지 않았다.
사전 계획은 [Qwen3](ANALYSIS_PLAN_KO.md), [InternVL3.5](ANALYSIS_PLAN_INTERNVL_KO.md)에 있다.

통합 환경에서는 Python 문법, 파일 해시, 예측의 완전성·정답률·기존 O/R 재현성과
분석 CSV를 대조했다. NumPy·pytest·R이 준비되지 않아 bootstrap·GLMM 재적합과
pytest/GPU 실행은 하지 않았다. 상세 검증은
`../../results/rstem_ropts_20261110/integration_validation.json`을 참고한다.
