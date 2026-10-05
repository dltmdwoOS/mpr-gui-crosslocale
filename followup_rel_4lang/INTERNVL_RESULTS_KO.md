# InternVL2.5-8B REL 4언어 결과

기존 실험과 같은 고정 `OpenGVLab/InternVL2_5-8B` revision,
BF16, batch 1, greedy 생성, 영어 시스템 프롬프트와 O/R/C/F 조건으로 full을 완료했다.
366문항·16언어쌍의 23,424조건 행에 대응하는 실제 추론 18,432개가 모두
`success` 상태다. 실행 실패·누락 입력·파싱 실패는 0건이다. 동일 입력을 재사용한
4,992행과 알려진 원본 문제 14문항·100언어쌍의 400행도 계획과 일치한다.
원본 문제 표시 행은 추론했지만 주 분석에서 제외했다.

| 결과 | 위치 |
|---|---|
| Full 요약·계약·감사 | `results/full/internvl2_5_8b/` |
| Full 예측·조건 행 | 같은 폴더의 `predictions.jsonl.gz`, `results.jsonl.gz` |
| Dependent/independent 각 1문항 smoke | `results/smoke/internvl2_5_8b/` |
| 전체 dry-run | `results/preflight/internvl2_5_8b/` |

주 분석에 포함되는 불일치 언어쌍의 생성 정답률 차이에 대한 기술 통계는 다음과 같다.

| 집단 | 완전한 미표시 quartet | R−O | F−C | `(F−C)−(R−O)` |
|---|---:|---:|---:|---:|
| Dependent | 3,576 | +10.68pp | +11.38pp | +0.70pp |
| Independent | 716 | −0.84pp | +0.98pp | +1.82pp |

이 값은 `summary.json`의 비조정 기술 통계이며 신뢰구간이나 인과 효과 추정이
아니다. 최종 GLMM·bootstrap 분석은 별도 단계다.

Git에는 full JSONL을 gzip 압축해 넣었다. 서버의 원본 JSONL은 변경하지 않았다.
압축 파일과 원본의 SHA-256·바이트 수·행 수, 게시한 smoke·dry-run 파일 목록은
[`INTERNVL_RESULTS_MANIFEST.json`](INTERNVL_RESULTS_MANIFEST.json)에 있다.
새 clone에서 JSONL을 복원할 때는 저장소 최상위에서 다음을 실행한다.
원본이 이미 있는 서버에서는 복원할 필요가 없다.

```bash
gzip -dk followup_rel_4lang/results/full/internvl2_5_8b/predictions.jsonl.gz
gzip -dk followup_rel_4lang/results/full/internvl2_5_8b/results.jsonl.gz
```

압축 파일을 풀어도 모델 가중치와 스크린샷은 포함되지 않는다. 추론 재현에는
[InternVL 서버 실행 안내](INTERNVL_SERVER_RUN_KO.md)에 따라 이미지와 고정
모델 캐시를 준비한다. 로그는 서버에만 보존했다. `human_reviewed`와
`screenshot_verified`는 false이며 전수 의미·화면 검수가 완료됐다는 뜻이 아니다.
질문·보기·예측 등 데이터셋 파생 내용은
[MPR-GUI-Bench의 CC-BY-NC-4.0 조건](../01_code/THIRD_PARTY_DATA.md)을 따른다.
