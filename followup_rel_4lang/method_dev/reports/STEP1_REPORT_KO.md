# Step 1: 데이터와 deterministic harness

2026-11-15, 기준 커밋 `e4aff7ace7248f1dd4e5a5dac0d4f679b33c6b5a`에서 새 브랜치로 작업했다. 기존 artifact는 수정하지 않았다. [Audit JSON](../artifacts/dataset_audit/audit.json)에 frozen 번역·규칙·input 파일 SHA-256과 원본 bundle/T lock 검증을 남겼다.

| 검사 | 실측 결과 |
| --- | ---: |
| Bundle SHA-256·바이트수 | 일치 |
| 원본 conditions·mapping·mixed 입력·Gemma 번역 lock | 일치 |
| O→R stem 및 A–D 재구성 | 1,944/1,944 정확히 일치 |
| O→Gemma 초기 번역 T 재구성 | 1,944/1,944 정확히 일치 |
| Main pairs | 1,896 |
| 사전 제외 후 | 1,895 |
| 별도 pilot pairs | 48 |
| 검증된 이미지 | 680/680 SHA-256 일치 |

`translations_gemma.jsonl`의 parse 실패 1쌍은 기존 lock이 명시한 `translations_gemma_parsefail.jsonl`을 함께 적용해야 T가 복원된다. 새로 번역하거나 기존 번역을 고치지 않았다. `T_gemma_first_conditions.jsonl`과 최종 frozen T의 hash는 이 snapshot에서 같다. 기존 R/T의 옵션 충돌도 진단에서는 보존하며, 실제 method의 새 충돌은 원문 fallback 처리한다.

Method 입력은 원본 질문·A–D·source/GUI 언어·ID·이미지 경로/hash·보기 순서만 가진다. 평가 labels와 oracle spans는 별도 파일이며 method는 해당 파일 경로를 받지 않는다. 새로운 `apply_edits`는 character offset을 검사하고 UTF-8 byte offset도 기록한다. Reference reconstruction에만 충돌 허용 옵션을 쓰며 자동 method는 엄격 모드다.

분할 seed 20261115, 동일 screenshot SHA-256 또는 같은 `rel::` 뒤 화면 state ID를 union하여 묶었다. Calibration 40문항/480쌍(제외 후479), evaluation 118문항/1,416쌍이다. Frozen split은 [split.json](../artifacts/dataset_audit/split.json)에 저장했다. 매우 유사하지만 다른 바이트의 화면까지 perceptual 중복 검사했다고 주장하지 않는다.

CPU mock 48쌍×4조건=192행은 실제로 생성했다. 전체 pipeline이 mock이면 downstream 평가기가 실측 예측으로 받아들이지 않는다. 공통 baseline 로더는 Qwen3와 InternVL3.5의 ExpA JSONL 및 gzip을 읽고 중복·누락 조건을 거절한다. 기존 O/T/R gold는 method 추론 이후에만 join한다.
