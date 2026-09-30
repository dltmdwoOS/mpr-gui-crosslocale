# Qwen2.5-VL REL 4언어 결과

Batch 32 full을 완료했다. 고정 Qwen2.5-VL-7B-Instruct, BF16, greedy,
영어 시스템 프롬프트와 O/R/C/F 조건을 사용했다. 366문항·16언어쌍의
23,424조건 행에 대응하는 실제 추론 18,432개가 모두 `success` 상태다.
파싱 실패 2건은 생성 답을 A/B/C/D로 읽지 못한 경우이며 생성 정답률에서
오답으로 처리한다. 실행 실패나 누락 입력은 없다. 알려진 원본 문제에 해당하는
400행은 추론했지만 주 분석에서 제외했다.

| 결과 | 위치 |
|---|---|
| Batch 32 full 요약·계약·감사 | `results/full/qwen2_5_vl_7b_batch32/` |
| Batch 32 full 예측·조건 행 | 같은 폴더의 `predictions.jsonl.gz`, `results.jsonl.gz` |
| Batch 1 중단 기록 | `results/full/qwen2_5_vl_7b/` — 실제 추론 1,951건, 미완료 |
| Batch 1 및 batch 32 smoke | `results/smoke/qwen2_5_vl_7b/`, `results/smoke/qwen2_5_vl_7b_batch32/` |
| 배치 크기 1·2·4·8·16·32·64 실험 | `results/batch_benchmark/qwen2_5_vl_7b/summary.json` |
| 전체 dry-run·완료 감사 | `results/preflight/`, `results/setup_checks/qwen_full_completion.json` |

Git에는 full JSONL을 gzip 압축해 넣었다. 서버의 원본 파일은 변경하지 않았다.
압축 파일의 SHA-256과 원본 파일의 SHA-256·행 수는
[`QWEN_RESULTS_MANIFEST.json`](QWEN_RESULTS_MANIFEST.json)에 있다. 새 clone에서
JSONL을 복원할 때는 저장소 최상위에서 다음을 실행한다. 원본이 이미 있는
서버에서는 이 복원 명령을 실행할 필요가 없다.

```bash
gzip -dk followup_rel_4lang/results/full/qwen2_5_vl_7b_batch32/predictions.jsonl.gz
gzip -dk followup_rel_4lang/results/full/qwen2_5_vl_7b_batch32/results.jsonl.gz
```

Batch 1 중단 기록의 `.jsonl.gz`도 같은 방식으로 복원할 수 있다. 그 출력은
완료된 batch 32 결과와 설정·코드 지문이 달라 동일 실험으로 합치지 않는다.
압축 파일을 풀어도 모델 가중치와 스크린샷은 포함되지 않는다. 추론 재현에는
[서버 실행 안내](SERVER_RUN_KO.md)에 따라 이미지와 고정 Qwen 캐시를 준비한다.

전체 결과의 `summary.json`은 신뢰구간이나 인과 효과가 아닌 기술 통계다.
`human_reviewed`와 `screenshot_verified`는 여전히 false이며 전수 의미·화면
검수가 완료됐다는 뜻이 아니다. 질문·보기·예측 등 데이터셋 파생 내용은
[MPR-GUI-Bench의 CC-BY-NC-4.0 조건](../01_code/THIRD_PARTY_DATA.md)을 따른다.
