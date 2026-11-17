# OCR 방법: 8B 잔여 작업 → 4B 전체 집합 연속 실행

진행 중이던8B는 사용자 요청으로 안전하게 중지했다. Selection은 완료됐고 Internal OCR의 완료 이미지별 cache가 보존됐다. 기존8B 코드·config·산출물은 변경하지 않는다.

## 실행 명령

저장소 루트에서 다음 한 줄을 실행한다.

```bash
nohup bash followup_rel_4lang/method_dev/scripts/run_ocr_8b_then_4b.sh > followup_rel_4lang/method_dev/artifacts/ocr_8b_then_4b.log 2>&1 < /dev/null &
```

```bash
tail -f followup_rel_4lang/method_dev/artifacts/ocr_8b_then_4b.log
```

같은 명령으로 재개할 수 있다. 8B가 실패하면4B를 시작하지 않는다. 이미 완료된 단계·집합은 다시 계산하지 않는다.

## 순서와 분모

1. **8B 재개:** 완료 Selection을 건너뛰고 Internal OCR를 cache에서 재개한다. 이미 완료된 이미지의 OCR는 다시 하지 않는다. 이후 M0 matching → 8B 최종 풀이 → 전체8B 보고서를 수행한다.
2. **4B Screen:** 기존8B가 만든 OCR-localized MCQ288쌍을4B로 푼다. 주 분석은main240쌍이다.
3. **4B Selection:** 240쌍을 실행하고 사전 제외1쌍을 뺀239쌍을 분석한다.
4. **4B Internal:** 1,416쌍을 실행·분석한다.
5. **전체 비교:** 4B/8B 각각main158문항·1,895쌍의 accuracy, 회복/회귀, item bootstrap CI와 전체 처리 비용을 보고한다.

4B의 실제 queue는 Screen288+Selection240+Internal1,416=**1,944행**이다. Pilot48행과 사전 제외1행을 queue에 유지해 기존 batch 구성을 보존하고 accuracy/비용에서 제외한다.

## 4B에서 무엇을 바꾸는가

**최종 solver checkpoint만 Qwen3-VL-4B로 바꾼다.** 다음은8B와 정확히 공유한다.

- CPU EasyOCR1.7.2 inventory 및 고정 OCR weights/config.
- 고정 Qwen3-8B LM의 E1 source referents.
- 동일 LM·M0 prompt가 만든 교체 표현과 deterministic stem 치환.
- 원본 options, A–D 순서, screenshot, pair ID, 정답.

이 전처리에는 평가 VLM이 들어가지 않으므로4B용 OCR·추출·matching을 새로 돌릴 이유가 없다. 완성 MCQ의 원시 파일 SHA-256을4B 실행에 결합해 두 solver가 같은 질문을 받았음을 검사한다. **8B의 최종 답은4B 입력이나 예측으로 복사하지 않는다.**

4B checkpoint는 이미 캐시된 `Qwen/Qwen3-VL-4B-Instruct`, revision `ebb281ec70b05090aa6165b016eac8ec08e71b17`이다. BF16·SDPA·2MP·channels_last_3d·batch3·greedy 최대2tokens·seed42·입력한도4,096을 유지한다. 8B와4B profile의 차이는 model ID/revision뿐인지 코드가 검사한다.

4B O와 과거4B VLM-inventory E1/M0는 같은 데이터·checkpoint·run profile의 완료 예측을 기준으로 비교한다. 4B 신규 풀이도 같은 완성 ordered batch의 prompt·image SHA·model·seed·software/hardware가 일치할 때만 기존4B 예측을 재사용한다. 다른 모델의 답이나 개별 행을 무조건 재사용하지 않는다.

## 실패·재개·자원

8B Internal OCR의 중간 `attempt_0001`은 완료로 간주하지 않는다. 새 attempt가 유효 이미지 cache를 읽고 남은 이미지만 처리한다. 기존 부분 로그·원시 파일도 보존한다. Matching도 캐시를 재사용한다.

4B 풀이 중 중단되면 완료 집합은 건너뛰고 미완료 집합의 완성된 batch를 검증해 재사용한다. 미완성 batch는 다시 계산한다. 부분 출력으로 accuracy를 보고하지 않는다.

CPU3스레드·GPU1개에서 순차 실행한다. 4B와8B를 동시에 적재하지 않는다. 4B 입력/배치 상한은8B와 같고 체크포인트는 더 작다. 기존 GPU free-memory 검사·project lock·입력한도 실패 처리를 그대로 사용하며 자동 축소·조용한 truncation은 없다. 새 dependency 설치나 모델 다운로드는 없다.

## 산출물과 시간 해석

- 8B: `artifacts/ocr_inventory_full_dev_v1/REPORT_KO.md`, `reports/OCR_INVENTORY_FULL_DEV_RESULTS_KO.md`
- 4B: `artifacts/ocr_qwen3_vl_4b_v1/REPORT_KO.md`, `reports/OCR_QWEN3_VL_4B_RESULTS_KO.md`
- 4B 구조화 결과: `artifacts/ocr_qwen3_vl_4b_results_snapshot.json`

각4B 집합이 완료될 때 보고서가 갱신된다. 4B 단독 recipe 비용에는 공통 전처리도 최초 기록 시간으로 포함한다. **이번에 추가로 필요한 비용은4B 최종 풀이뿐**이며, 공동8B+4B 비용에서는 공통 전처리를 한 번만 더한다. 모델 적재·프로세스 기동을 제외한 호출 시간과 실제stage wall을 구분한다.

이전4B VLM-inventory 조건은4B가 inventory를 만들었던 실험이다. 현재 OCR 조건의4B/8B는 공통 inventory·LM·MCQ를 사용하므로 두 solver 비교의 의미를 구분한다. 모든 결과는 반복 관찰한158문항 개발 자료의 탐색 결과이며 전체366문항 일반화 실험이 아니다.

준비만 확인하려면 `bash followup_rel_4lang/method_dev/scripts/run_ocr_4b.sh`, 실제 모델 추론 없는 연결 검증은 `bash followup_rel_4lang/method_dev/scripts/run_ocr_8b_then_4b.sh --mock`이다.
