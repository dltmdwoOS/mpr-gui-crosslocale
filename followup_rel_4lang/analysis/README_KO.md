# REL 4언어 GLMM 입력 준비

이 폴더의 `prepare_glmm.py`는 완료된 두 모델의 압축 full 결과를 검증하고,
GLMM에 필요한 작은 CSV 두 개를 생성한다. 모델 추론이나 GLMM 적합은 실행하지 않는다.

작업 대상은 `internvl2_5_8b` batch 1 완료본과 `qwen2_5_vl_7b_batch32` 완료본이다.
Qwen batch 1의 중단 기록은 사용하지 않는다. 두 모델은 같은 생성 입력 SHA-256을
사용하며, 각 모델의 `results.jsonl.gz` 23,424행과 `predictions.jsonl.gz` 18,432행을
매니페스트의 압축·원본 SHA-256, 바이트 수, 행 수로 검증한다.

PowerShell이 `C:\Users\coex0\mpr-gui-crosslocale`에 열려 있다면, 먼저 별도
worktree로 이동한 다음 실행한다. 명령은 한 줄씩 입력한다.

```powershell
Set-Location -LiteralPath 'C:\Users\coex0\mpr-gui-crosslocale-rel-glmm'
git status --short --branch
python -X utf8 .\followup_rel_4lang\analysis\prepare_glmm.py
conda run --no-capture-output -n mpr-r-analysis Rscript .\followup_rel_4lang\analysis\check_glmm_input.R
```

`git status` 첫 줄에 `followup-rel-4lang-inference...origin/followup-rel-4lang-inference`가
표시돼야 한다. 준비된 CSV만 확인하려면 마지막 두 명령 대신 다음을 실행한다.

```powershell
Get-Item .\followup_rel_4lang\results\analysis_ready\glmm_rows.csv, .\followup_rel_4lang\results\analysis_ready\quartet_contrasts.csv
```

출력은 `followup_rel_4lang/results/analysis_ready/`에 생긴다. 최초 GLMM
결과와 입력 CSV는 이 브랜치에 스냅샷으로 게시했다. 결과 폴더는 기본적으로
`.gitignore` 대상이므로 재실행한 새 파일을 게시할 때는 명시적으로 추가해야 한다.

- `glmm_rows.csv`: 두 모델 합계 34,336행. 모델당 원본 문제가 없는 불일치 언어쌍
  4,292개 × O/R/C/F = 17,168행. `generation_correct`는 0/1이며,
  `reference_alignment`와 `context_localization`은 O=(0,0), R=(1,0),
  C=(0,1), F=(1,1)로 기록한다.
- `quartet_contrasts.csv`: 두 모델 합계 8,584행. 각 문항·방향성 언어쌍·모델의
  네 조건을 한 줄로 묶어 R−O, F−C, C−O, F−R과 상호작용을 기록한다.
- `preparation_report.json`: 커밋, 입력 지문, 포함·제외 수량, CSV 해시를 기록한다.

모델당 독립 집단 716 quartet, 종속 집단 3,576 quartet이다. 생성 정답률을
결과변수로 사용한다. Qwen의 파싱 실패 2건은 원본 결과의 `generation_correct=0`을
그대로 유지한다. 별개의 O/R/C/F 행은 같은 `pair_id`를 공유하며, 동일 입력을
재사용한 조건은 `reused_prediction`과 `equivalent_to_condition`으로 식별한다.
GLMM에서 행을 독립 표본처럼 취급하지 않도록 문항과 언어쌍의 반복 구조를 고려한다.

이전 6언어 GLMM 스크립트인 `01_code/analysis/rel_text_dependency_glmm.R`은
366문항 × 36언어 셀의 다른 설계에 맞춰져 있으므로 이 CSV에 직접 실행하지 않는다.
최종 GLMM의 고정효과·랜덤효과·대비와 bootstrap 단위는 이번 2×2 조건 설계에
맞춰 정한 뒤 적합한다. 원본 문제 400행과 일치 언어쌍 5,856행은 주 분석 CSV에서
제외되지만 압축 원본에 보존된다. 검수 상태는 원본 기록대로 유지한다.

`check_glmm_input.R`은 R 패키지, 누락값, 완전한 quartet, 고정효과 설계행렬의
계수를 사전 점검한다. 이 점검은 GLMM 적합이나 유의성 검정이 아니다.

## GLMM 적합 실행

입력 점검이 통과하면 같은 worktree의 PowerShell에서 다음을 실행한다.

```powershell
conda run --no-capture-output -n mpr-r-analysis Rscript .\followup_rel_4lang\analysis\fit_glmm.R .\followup_rel_4lang\results\analysis_ready\glmm_rows.csv .\followup_rel_4lang\results\glmm both
```

이 명령은 InternVL과 Qwen 각각에 대해 binomial logit GLMM을 적합한다.
고정효과는 참조 표현 정렬 × 문맥 현지화 × text dependency, 질의 언어,
GUI 언어이며, 문항과 방향성 언어쌍에 랜덤 절편을 둔다. 모델별 `.rds`,
`_contrasts.csv`, `_diagnostics.csv`, `_session_info.txt`가
`followup_rel_4lang/results/glmm/`에 생성된다. 대비 CSV에는 R−O, F−C,
C−O, F−R, `(F−C)−(R−O)`를 dependency별 조건부 오즈비와 95% Wald 구간으로
기록한다. 이는 정확도 %p 차이가 아니다. 결과 해석 전에 진단 CSV의 특이 적합과
수렴 메시지를 확인한다.

짧은 실행 점검에는 별도 출력 디렉터리를 사용한다.

```powershell
conda run --no-capture-output -n mpr-r-analysis Rscript .\followup_rel_4lang\analysis\fit_glmm.R .\followup_rel_4lang\results\analysis_ready\glmm_rows.csv .\followup_rel_4lang\results\glmm_smoke both --smoke
```

게시된 전체 적합은 두 모델 모두 17,168행·364문항·4,292방향성 언어쌍을
사용했다. `combined_diagnostics.csv`에서 두 모델 모두 `singular=FALSE`이고
수렴 메시지는 비어 있다. 적합 모델과 대비·진단·R 세션 기록, smoke 결과도
저장했다. `GLMM_RESULTS_MANIFEST.json`은 이 23개 파일의 SHA-256을 기록한다.
텍스트 파일은 Windows와 Linux의 줄바꿈 차이를 제거한 뒤 검증한다.
매니페스트를 다시 만들려면 다음을 실행한다.

```powershell
python -X utf8 .\followup_rel_4lang\analysis\make_results_manifest.py
```
