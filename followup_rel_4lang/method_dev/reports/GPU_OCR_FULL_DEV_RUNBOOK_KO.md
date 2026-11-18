# GPU OCR Selection/Internal 실행

완료된 Screen의 설정을 고정한 채 **EasyOCR CUDA·PP-OCRv5 GPU × Qwen3-VL-8B·4B**를 Selection과 Internal까지 확장했고 네 조건 모두 완료했다. [전체 결과·효율·실패 분석](GPU_OCR_FULL_DEV_RESULTS_KO.md): main158문항·1,895쌍에서 PP-OCRv5는 8B74.93%·67.07분, 4B73.09%·65.02분이다. 시간은 전처리+풀이 호출 합이며 정확도 우위의 CI는 0을 포함한다.

## 실행 명령

현재 repository 루트에서 실행한다. 추가 설치나 모델 다운로드는 필요 없다. 완료 상태에서는 추론을 반복하지 않고 보고서를 갱신한다.

```bash
nohup bash followup_rel_4lang/method_dev/scripts/run_gpu_ocr_remaining.sh > followup_rel_4lang/method_dev/artifacts/gpu_ocr_remaining.log 2>&1 &
```

```bash
tail -f followup_rel_4lang/method_dev/artifacts/gpu_ocr_remaining.log
```

Selection의 EasyOCR → PP-OCRv5, 이어서 Internal의 EasyOCR → PP-OCRv5 순서다. 각 backend에서는 OCR → 고정 LM 정렬 → 8B 풀이 → 4B 풀이를 순차 실행한다. 같은 명령을 다시 실행하면 완료 stage를 건너뛰고 중단 지점부터 재개한다.

결과는 `followup_rel_4lang/method_dev/artifacts/gpu_ocr_full_dev_v1/REPORT_KO.md` 및 `results.json`에 누적된다. 보고서만 갱신하려면 다음을 실행한다.

```bash
.venv/bin/python followup_rel_4lang/method_dev/scripts/report_gpu_ocr_remaining.py
```

## 실행 규모

| 집합 | Semantic item | 조건당 주 분석 pair | 조건당 실제 풀이 입력 | OCR 화면/backend | 처리 |
| --- | ---: | ---: | ---: | ---: | --- |
| Screen | 20 | 240 | 288 | 128(main 80) | 기존 완료 결과 재사용 |
| Selection | 20 | 239 | 240 | 80 | 새 실행 |
| Internal | 118 | 1,416 | 1,416 | 472 | 새 실행 |
| 전체 main | 158 | 1,895 | 1,944(pilot 포함) | main 632 | 동일 범위로 통합 |

추가 풀이 입력은 **1,656행 × 4조건 = 6,624행**이다. 정확히 같은 기존 batch는 실제 재추론 없이 재사용하므로 새 GPU 호출량은 이보다 적을 수 있다. Selection에서 사전 제외했던 `rel::5/forest_9.jpg::zh::ru` 1행은 실행에 남기고 주 정확도·비용에서 제외한다. Screen pilot 48행도 주 분석에서 제외한다.

## 고정하는 방법과 설정

- Screenshot-only OCR inventory를 만들고 기존 **E1 stem-only referent 추출 결과를 재사용**한다. 추출 LM을 다시 돌리지 않는다.
- 같은 고정 Qwen3-8B LM·M0 prompt로 GUI inventory의 교체 표현을 선택한다. 구조 repair 최대 1회, 실패 시 원문 유지 정책을 유지한다.
- 코드가 stem의 검증된 referent만 치환한다. Options·이미지·보기 순서는 원본 그대로다. GUI inventory 실패를 VLM inventory로 대체하지 않는다.
- 같은 OCR·LM 수정 MCQ를 8B/4B가 공유한다. 한 solver의 예측 label을 다른 solver에 복사하지 않는다.
- 최종 VLM은 기존 BF16·SDPA·2MP·batch 3·seed 42·greedy 2 tokens·입력 상한 4,096 tokens·channels_last_3d를 유지한다. OCR recognizer batch는 8이다.
- EasyOCR 1.7.2 CUDA, RapidOCR 3.10.0 + Paddle Inference 3.3.0 CUDA13의 PP-OCRv5 mobile 및 EN/ZH/TH/RU 인식기를 유지한다. 상세 모델 revision·OCR 해상도·다운로드 SHA는 [Screen 실행 안내](GPU_OCR_SCREEN_RUNBOOK_KO.md)와 기존 config 그대로다.

실제 각 cohort/backend의 `contract.json`에 고정된 OCR software/weights, LM/VLM 설정, 입력·코드·의존 파일 SHA를 보존한다. Screen 코드는 변경하지 않았다. Semantic item은 기존 Screen/Selection/Internal partition을 그대로 사용한다. 이미 반복 관찰한 개발 데이터이므로 독립 검증이라는 의미를 부여하지 않는다.

## 캐시·재개와 자원

Screen의 GPU OCR 캐시를 backend별 새 공유 캐시에 연결한다. 기존 CPU OCR 실행과 두 GPU Screen 실행에서 **LM 응답 2,530개**도 seed한다. 충돌하는 응답은 발견되지 않았으며, 발견되는 키는 임의 선택하지 않고 seed에서 제외한다. 기존 파일은 읽기 전용으로 재사용하고 새 결과는 새 실험 디렉터리에만 기록한다.

LM 캐시 키에는 전체 prompt·inventory·모델·decoding·seed·software/hardware가 포함된다. 최종 풀이 캐시는 전체 ordered batch·이미지·prompt·checkpoint·seed·환경이 모두 같아야 재사용한다. 이전 미완료 attempt의 **완료된 batch**도 재개 시 회수한다. OCR와 LM 전처리는 두 solver 사이에서 다시 실행하지 않는다.

45GB MIG에서 모든 GPU stage를 별도 process로 순차 실행하고 기존 프로젝트 GPU lock을 공유한다. 새로운 모델을 동시에 적재하지 않으며, 이미 완료한 동일 해상도·batch 설정을 사용한다. CPU 관련 thread는 3 이하, Paddle worker의 OMP는 1이다. OOM·자원 부족 발생 시 중단하며 CPU 전환·batch 자동 축소·입력 자동 절삭은 하지 않는다.

## 집계와 검증

보고서는 cohort별 완료된 조건만 표시한다. **네 GPU 조건이 모두 끝난 cohort만 pooled 표에 추가**하므로, 일부 조건만 끝난 Selection/Internal을 서로 다른 분모로 비교하지 않는다. 최종적으로 Screen을 포함한 158문항·1,895쌍을 합산한다. 기존 O·VLM inventory·CPU EasyOCR도 각 solver에서 동일 pair와 비교한다.

정확도, GUI 언어별 결과, paired 회복/회귀, semantic-item bootstrap 10,000회 CI를 기록한다. 실패·빈 inventory·fallback·미파싱을 분모에서 삭제하지 않는다.

시간은 main pair에 대응하는 OCR + 기존 E1 추출 + M0 정렬 + 최종 VLM 풀이의 호출 구간 합이다. 기존 캐시를 쓰더라도 원래 측정 시간을 청구하고, 전역 중복 전처리는 한 번만 센다. Batch 시간은 cohort 안에서 한 번만 세고 main 비율로 배분한다. 모델 적재·기동·새 실행의 stage wall/cache hit는 별도로 기록한다. 두 solver의 독립 recipe에 포함된 공통 전처리를 실제 중복 실행한 것으로 해석하지 않는다.

실제 GPU 추론을 추가하지 않고 다음을 확인했다.

- Selection 240/239·Internal 1,416/1,416 pair와 4언어 이미지 linkage, 기존 E1·두 solver의 baseline coverage.
- 8개 추가 조건 전체 CPU mock 6,624개 예측 행 완료 및 재개 시 16개 stage 건너뛰기.
- 통합 보고서의 기존 Screen 10개 baseline/method 행이 원래 정확도·recipe 시간을 재현함.
- 분모·semantic partition·캐시 충돌 배제·공유 비용 중복 제거·부분 완료 시 pooled 범위를 점검하는 표적 테스트 20개.

준비 당시 기록은 `artifacts/gpu_ocr_full_dev_readiness.json`에 보존했다. 완료 결과와 queue 검증은 `artifacts/gpu_ocr_full_dev_results_snapshot.json`, 원시 산출물은 `artifacts/gpu_ocr_full_dev_completed.tar.gz`에 있다. 요약 보고서·검증·archive를 재생성하려면 `.venv/bin/python followup_rel_4lang/method_dev/scripts/finalize_gpu_ocr_remaining.py`를 사용한다. private labels와 데이터·모델은 실행 안내에 따라 별도 준비한다.
