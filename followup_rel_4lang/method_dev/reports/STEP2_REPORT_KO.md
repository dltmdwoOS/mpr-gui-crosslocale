# Step 2: 자동 selective pipeline와 실제 smoke

새 method-only 모듈을 inventory/extraction/matching/rewrite/routing/schema/validation으로 분리했다. 이전 `paper-freeze-20260814`의 query-blind inventory 프롬프트·정규화·dedup·lexical sorting 규칙을 포팅했고 정확한 출처 커밋을 [legacy_prompts.json](../configs/legacy_prompts.json)에 남겼다. 느슨한 JSON 복구로 임의의 truncated inventory를 성공 처리하지 않는다. 빈 목록·파싱 실패는 로그에 남으며 pair는 제외하지 않는다.

실제 smoke는 기본 extractor/translator가 캐시에 없어 **Qwen3-VL-8B를 두 역할에 사용한 별도 override**다. 기본 Qwen2.5-VL / text-only Qwen3 결과로 부르면 안 된다. 이미 관찰했던 pilot `booking_1` EN→ZH 한 쌍, B200 MIG 45GB, BF16·SDPA·2MP·channels_last_3d를 사용했다. Raw response·config·코드 hash·실제 package version은 압축 자료에 보존했다.

| 단계 | 실측 |
| --- | --- |
| Screenshot-only inventory | 성공, 정규화 dedup·정렬 후 34개 (raw 응답 보존) |
| Auto span extraction | 유효 JSON `{"referents":[]}`; 0개 반환 |
| Gold annotation과 사후 대조 | 5개 span 중 recall 0, F1 0; precision 분모 없음 |
| Selective GUI matching | 후보/편집 없음; matching precision 측정 불가 |
| TXT_FULL / GUI_FULL | 다섯 field JSON 생성·기본 검증 통과 |
| TXT_SEL / GUI_SEL | 입력 원문 유지, 실제 편집 0개 |

원시 목록과 정규화 inventory는 [실측 요약](../artifacts/smoke_summary.json) 및 압축 자료에 보존했다. 이 smoke는 pipeline I/O와 fallback의 실행 검사이며 **GCSA의 selective editing 성공 게이트는 통과하지 못했다**. 기본 matcher는 translated normalized exact-only이고 LaBSE 옵션은 구현했으나 이번에 적재·튜닝하지 않았다. Threshold 1.0은 검증된 최적값이 아니며 자기보고 confidence도 사용하지 않는다.

실측 backend 시간은 inventory 77.21초, extraction 2.22초, TXT_FULL 22.29초, GUI_FULL 25.05초, 합계 약126.78초다. 모델 로딩 제외, 입력 token 총2,985개·출력392개다. selective 전용 번역은 빈 span 때문에 호출하지 않았다. 따라서 이 비용을 정상 selective 매칭 완료 시 비용으로 일반화할 수 없다. dollar 비용은 대여료 자료가 없어 산출하지 않았다.

자동 method의 새 버전은 빈 span도 `no_extracted_referents`와 `no_op_no_referents`로 기록한다. 이 개선 이전의 첫 실제 smoke 원본 상태 필드는 그대로 보존한다. 원본 응답을 수정해 성공처럼 재작성하지 않았다.

Screenshot matching precision은 아직 별도 사람이 검토하지 않아 null이다. OCR 누락과 matcher 실수의 자동 판별도 확정하지 않는다. `quality.py`는 screenshot correspondence·OCR missing·wrong element를 별도로 검수할 CSV를 만든다. Parallel-QAS 문자열과의 일치만으로 GUI matching 정답을 판정하지 않는다.
