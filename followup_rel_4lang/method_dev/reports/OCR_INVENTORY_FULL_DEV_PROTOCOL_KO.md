# 고정 OCR E1/M0: Selection → Internal 실행

Screen에서 수행한 EasyOCR inventory + E1/M0를 변경 없이 남은 개발 문항에 적용한다. **기존 Screen은 재실행하지 않고 전체158문항 집계에 재사용한다.** 전체366문항 확장은 아니다.

## 바로 실행

현재 저장소 루트에서 다음 한 줄을 실행한다. OCR 패키지와 네 언어 checkpoint는 이미 준비되어 있다.

```bash
nohup bash followup_rel_4lang/method_dev/scripts/run_ocr_remaining.sh --run > followup_rel_4lang/method_dev/artifacts/ocr_inventory_full_dev_v1.log 2>&1 < /dev/null &
```

```bash
tail -f followup_rel_4lang/method_dev/artifacts/ocr_inventory_full_dev_v1.log
```

Selection의 **OCR → matching → 최종 풀이 → 보고서**를 끝내고 Internal의 같은 순서를 실행한다. Selection 완료 보고서는 Internal 실행 중에도 확인할 수 있다. 중단되면 같은 명령으로 재개한다. 완료 단계는 건너뛰고, 미완료 단계의 유효 OCR/LM cache를 재사용한다. 전체 완료 후 같은 명령은 추론을 다시 하지 않고 보고서를 재생성한다.

다른 프로젝트 GPU 작업이 실행 중이면 matching/풀이 전에 중단한다. 해당 작업을 종료하지 않는다. GPU가 비워진 뒤 같은 명령으로 재개한다.

## 정확한 범위

| 범위 | semantic item | 실행 pair | 주 분석 pair | OCR 이미지 |
| --- | ---: | ---: | ---: | ---: |
| Screen · 기존 결과 재사용 | main20 + pilot12 | 288 | 240 | 기존128개 중 main80개 비용 |
| Selection · 신규 실행 | 20 | 240 | 239 | 80 |
| Internal · 신규 실행 | 118 | 1,416 | 1,416 | 472 |
| 남은 신규 실행 합계 | 138 | 1,656 | 1,655 | 552 |
| 전체 main 분석 | 158 | main1,896 | **1,895** | main632개 비용 |

사전 제외는 기존 `rel::5/forest_9.jpg::zh::ru` 하나를 그대로 유지한다. 이 행을 queue에서 제거하면 batch 구성이 달라지므로 실행에는 남긴다. 정확도와 비용을 주 분석239/1,416/1,895pair에 맞춰 집계한다. 실패·원문 fallback·미파싱 답은 분모에서 빼지 않는다.

## 고정한 설정

- **Inventory:** Screen과 동일한 EasyOCR1.7.2, CRAFT + 언어별 recognizer, CPU3스레드, 인식batch8, workers0. Known GUI language로 EN/ZH/TH/RU recognizer를 선택한다. Query/options/gold는 OCR에 제공하지 않는다.
- **OCR 출력:** 원문·bbox·confidence를 보존하고, 기존 정규화·중복 제거·lexical sorting된 문자열만 LM에 제공한다. 추가 confidence filter·문자열 병합·번역 교정은 없다. 빈 OCR와 이미지별 실패 처리도 Screen과 같다. VLM inventory fallback은 없다.
- **추출:** 기존 `e1_stem_full_dev_v1`의 수정 E1 출력과 원시 호출을 재사용한다. 새 referent 추출 추론은 없다.
- **Matching:** 기존 Qwen3-8B, M0 system/user prompt, 최대1회 구조 repair, 기존 검증과 원문 fallback을 유지한다. Original MCQ·E1 referents·OCR inventory를 제공한다.
- **치환:** deterministic code가 stem span만 바꾼다. Options와 span 바깥 context, 이미지, A–D 순서는 유지한다.
- **최종 풀이:** 동일 Qwen3-VL-8B revision, BF16·SDPA·2MP, channels_last_3d, greedy 최대2tokens, batch3, seed42. 입력한도4,096tokens를 유지한다.

새 모델·prompt·threshold 선택을 Selection/Internal 결과에 맞춰 바꾸지 않는다. 두 집합 역시 과거 관찰한 개발 자료이며 untouched confirmatory evaluation으로 주장하지 않는다.

## 재사용과 자원

Screen 코드와 config는 수정하지 않고 `run_ocr_inventory.py`의 OCR/matching/풀이 함수를 그대로 호출한다. 새로운 코드와 결과는 `ocr_inventory_full_dev_v1`에 분리한다. Screen 원시 파일은 덮어쓰지 않는다.

Screen의 OCR/matching cache는 새 공유 cache에서 참조하고, 신규 cache는 새 실험 디렉터리에 쓴다. 실제 cache key와 원시 출력의 충돌을 검사한다. CPU/GPU 단계는 순차 실행하며 GPU LM/VLM을 동시에 적재하지 않는다.

최종 풀이 재사용은 순서가 같은 **완성 batch 전체**에서 이미지SHA·rendered prompt·model/decoding·seed·software/hardware가 일치할 때만 허용한다. 개별 MCQ가 같다는 이유로 예측 한 행을 복사하지 않는다. 신규 환경과 맞지 않거나 출력 충돌이 있는 batch는 다시 푼다.

데이터가 많아져도 OCR는 이미지 한 장씩, LM은batch1, VLM은batch3으로 처리한다. 메모리 상한을 결정하는 설정은 Screen과 같다. GPU 메모리 점검과 프로젝트 GPU lock도 재사용한다. 큰 inventory로 입력한도4,096tokens를 넘거나 OOM이 발생하면 명시적으로 중단하며, 조용히 잘라내거나 batch를 낮추지 않는다. 체크포인트를 바꿔 대응하지 않는다.

## 결과와 비용

종료 시 아래 보고서와 JSON을 자동 생성한다.

- `followup_rel_4lang/method_dev/reports/OCR_INVENTORY_FULL_DEV_RESULTS_KO.md`
- `followup_rel_4lang/method_dev/artifacts/ocr_inventory_full_dev_v1/REPORT_KO.md`
- `followup_rel_4lang/method_dev/artifacts/ocr_inventory_full_dev_v1/results.json`
- `followup_rel_4lang/method_dev/artifacts/ocr_inventory_full_dev_results_snapshot.json`

O·기존VLM inventory E1/M0·OCR inventory E1/M0를 같은 pair로 비교한다. Accuracy, 회복/회귀, item bootstrap10,000회 CI, GUI별 결과, OCR 실패·fallback·완성 MCQ 일치와 label 차이를 기록한다. 미완료 cohort의 부분 정확도는 공개하지 않는다.

전처리부터 풀이까지의 비교용 비용은 **main 이미지의 CPU OCR + 기존 E1 GPU 추출 + M0 GPU matching + VLM 풀이**다. 재사용 호출도 최초 측정 시간을 청구하고, 공유 호출을 전역cache key당 한 번 계산한다. 최종 batch runtime은 primary행 비율로 배분한다. 모델 적재·기동을 제외한 호출 시간과 실제 추가stage wall을 구분한다. Screen의37% 비용 감소를 전체에 미리 적용하지 않는다.

## 준비와 CPU 검증

다음은 긴 실제 추론을 시작하지 않는다.

```bash
bash followup_rel_4lang/method_dev/scripts/run_ocr_remaining.sh
bash followup_rel_4lang/method_dev/scripts/run_ocr_remaining.sh --mock --run
```

Mock는 별도 `ocr_inventory_full_dev_v1_mock`를 사용하며 실제 성능으로 집계하지 않는다. 기존 Screen 결과·설정은 [Screen 프로토콜](OCR_INVENTORY_SCREEN_PROTOCOL_KO.md)과 [Screen 결과](OCR_INVENTORY_SCREEN_RESULTS_KO.md)를 참고한다.
