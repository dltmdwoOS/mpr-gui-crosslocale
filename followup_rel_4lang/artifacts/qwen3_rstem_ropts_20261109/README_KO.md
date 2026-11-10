# Qwen3 R_stem / R_opts 완료 결과

2026-11-09 UTC, RTX 4090 한 장에서 실행한 158문항 × 12불일치 언어쌍 × 4조건의 결과다.
본 실행은 15:14:57에 시작해 16:53:37에 완료됐다(사전 검사 이후 약 98분 40초).

| 조건 | 질문 기준 표현 | 선택지 참조 표현 | 정답 / 전체 | 생성 정답률 |
| --- | --- | --- | --- | --- |
| O | source | source | 1,330 / 1,896 | 70.15% |
| R_stem | GUI | source | 1,473 / 1,896 | 77.69% |
| R_opts | source | GUI | 1,388 / 1,896 | 73.21% |
| R | GUI | GUI | 1,592 / 1,896 | 83.97% |

같은 실행의 O 대비 차이는 R_stem +7.54%p, R_opts +3.06%p, R +13.82%p다.
이 수치는 기술 통계이며 문항 단위 신뢰구간, 유의성 검정, 인과적 매개 분석은 포함하지 않는다.
문항마다 12언어쌍이 반복되므로 7,584행을 독립 표본으로 해석하지 않는다.

## 완료와 재현성

- full 7,584행 전부 성공, 중복 ID·누락·파싱 실패 0건.
- 1,896배치 전부 같은 문항·언어쌍의 O/R_stem/R_opts/R 네 조건으로 구성.
- 기존 2026-11-07 O/R 3,792답변과 라벨 일치율 99.53%(18건 차이).
- smoke 144행 전부 성공, 파싱 실패 0건, 기존 O/R 일치율 98.61%.
- 잠긴 입력의 질문·정답·전체 ID와 실제 출력을 대조하고 정답률을 재계산했다.
  자세한 검사 결과는 `validation_report.json`과 원본 gate JSON에 있다.

Qwen3-VL-8B-Instruct revision `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`,
BF16, SDPA, 최대 2MP, `channels_last_3d`, strict batch 4, greedy 최대 2토큰을 사용했다.
정확한 프롬프트·코드 해시·소프트웨어 버전은 각 `run_contract.json`에 보존했다.
실행 시 base commit은 `d97d463fa094496318563a9460a779cd4e25f40b`이며,
이번 커밋에 당시 미추적 상태였던 전용 러너·입력·검증기·runbook도 함께 보존한다.

## 보존 범위와 읽는 방법

`results/qwen3_rstem_ropts/` 아래의 모든 파일을 보존했다. full과 smoke의 원시 예측,
계획·계약·요약·gate, 설치·다운로드·추론 로그, 패키지 목록과 GPU·Git 기록을 포함한다.
정오에 따른 선별은 없으며 원본 결과는 수정하지 않았다.
원시 JSONL 두 파일만 무손실 gzip으로 압축했고 나머지는 바이트 단위로 복사했다.
`MANIFEST.json`은 각 원본과 보존 파일의 SHA-256·크기·JSONL 행 수를 기록한다.
같은 결과를 중복 저장하는 별도 tar.gz, 이미지, 모델 가중치, 가상환경은 Git에 포함하지 않는다.

저장소 루트에서 원시 full 예측을 읽는 예:

```bash
gzip -dc followup_rel_4lang/artifacts/qwen3_rstem_ropts_20261109/full/predictions.jsonl.gz | head -n 1
```

실행 절차는 [전용 runbook](../../RSTEM_ROPTS_RUNBOOK_KO.md)에 있다.
데이터셋 파생 자료에는 [CC-BY-NC-4.0 조건](../../../01_code/THIRD_PARTY_DATA.md)이 적용된다.
