# EasyOCR로 inventory만 교체하는 Screen 실험

기존 E1/M0 Stem-only GUI의 inventory 생성기를 EasyOCR로 교체한다. 정확도 개선을 가정하지 않고 같은 문항의 성능·계산 비용을 비교한다. 전체 158문항이나 366문항 확장은 이번 실행에 포함하지 않는다.

## 실행

현재 저장소 루트에서 OCR 의존성을 설치한다. 기존 `.venv`의 모든 설치 패키지를 constraints로 고정하므로 Torch·NumPy·Transformers를 업그레이드하지 않는다.

```bash
bash followup_rel_4lang/method_dev/scripts/setup_ocr.sh
```

준비만 확인하려면:

```bash
bash followup_rel_4lang/method_dev/scripts/run_ocr_inventory.sh
```

실제 Screen 전체 실행은 다음 한 줄이다. 최초 OCR 실행에서 필요한 모델을 개인 cache에 다운로드하고 SHA-256을 저장한다. 이후 같은 명령은 완료 단계와 유효 cache를 재사용한다.

```bash
nohup bash followup_rel_4lang/method_dev/scripts/run_ocr_inventory.sh --run > followup_rel_4lang/method_dev/artifacts/ocr_inventory_screen_v1.log 2>&1 < /dev/null &
```

다른 프로젝트 GPU 파이프라인이 실행 중이면 OCR 이후 matching에 진입하기 전에 중단한다. 기존 작업을 종료하지 않는다. 해당 작업이 끝난 뒤 같은 명령으로 재개하면 OCR를 다시 계산하지 않는다.

```bash
tail -f followup_rel_4lang/method_dev/artifacts/ocr_inventory_screen_v1.log
```

## 무엇을 유지하고 무엇을 교체하는가

1. **교체:** screenshot → EasyOCR → 정규화·중복 제거·lexical sorting된 `visible_strings`.
2. **재사용:** 기존 수정 E1 프롬프트로 얻은 stem referents. 새로운 추출 추론은 없다.
3. **유지:** 고정 Qwen3-8B LM의 기존 M0 프롬프트에 원본 MCQ·referents·OCR inventory를 제공한다. 같은 출력 검증, 최대 1회 구조 repair와 원문 fallback을 사용한다.
4. **유지:** 코드가 검증된 stem span만 치환한다. Options·관계 문맥·이미지·보기 순서는 유지한다.
5. **유지:** 같은 Qwen3-VL-8B revision, BF16·SDPA·2MP, batch 3, greedy 최대 2 tokens로 풀이한다.

실험 ID는 `E1_M0_EASYOCR`. 기존 E1/M0 코드·결과·inventory를 덮어쓰지 않는다.

## OCR 설정

설정 파일: [`../configs/ocr_inventory_easyocr_v1.json`](../configs/ocr_inventory_easyocr_v1.json).

EasyOCR **1.7.2**, CRAFT detector, 기본 script별 recognizer. EN=`en`, ZH=`ch_sim+en`, TH=`th+en`, RU=`ru+en`. 알려진 GUI 언어로 recognizer를 선택하며 질문·보기·정답은 OCR 입력에 주지 않는다.

기본은 **CPU 3스레드, OCR 인식 batch 8, workers 0**, greedy, `paragraph=False`, `canvas_size=2560`, `mag_ratio=1`, 나머지 검출·병합 설정도 JSON에 고정한다. CPU 실행은 새 OCR GPU 환경을 요구하지 않고 현재 GPU 실험과 메모리가 충돌하지 않도록 선택한 초기 설정이다. CPU와 GPU의 실행 시간은 구분해서 기록한다.

OCR confidence로 추가 필터링하지 않는다. 도구 자체의 검출 threshold는 설정대로 적용한다. 낮은 confidence, bbox, 인식 원문을 모두 기록하며, 기존 정규화 이후 별도 문구 분할·합치기·번역·교정을 하지 않는다. bbox와 confidence는 LM에 제공하지 않는다.

EasyOCR는 빈 인식 목록을 반환할 수 있다. 빈 목록은 명시적으로 `empty`로 기록하고 기존 M0에 빈 inventory를 제공한다. 이미지별 처리 실패는 `failed`로 기록하고 해당 MCQ를 원문으로 유지한다. 의존성·모델 초기화 오류와 OOM은 실행을 중단한다. VLM으로 inventory를 복구하는 fallback은 넣지 않는다.

캐시는 **image SHA + GUI language + OCR config + OCR weight SHA + mock 여부**로 분리한다. 모델은 `/home/jovyan/seungjae/.cache/easyocr/model`에 보존하며, 실행 중 모델 checksum이 달라지면 재개하지 않는다. 기존 OCR cache를 임의로 삭제하지 않는다.

## 분모와 재사용

기존 Screen batch 구성을 유지하려고 **32 item·288 pair·128 unique screenshot**을 처리한다. 이 중 주 분석은 **main 20 item·240 pair·80 screenshot**이다. 나머지 pilot 48 pair와 이미지 비용은 주 분석에서 제외한다.

최종 VLM 결과는 **순서가 같은 완성된 batch**의 pair ID·rendered prompt·image SHA·model/decoding·seed·software/hardware 환경이 모두 일치할 때만 재사용한다. 개별 MCQ가 같다는 이유만으로 해당 행의 예측을 복사하지 않는다. 변경되거나 재사용 계약이 불일치한 batch만 새로 푼다.

## 분석과 시간

- 기존 VLM inventory E1/M0와 paired accuracy, 회복·회귀, semantic-item bootstrap 10,000회 CI를 비교한다.
- GUI 언어별 결과, OCR 빈 목록·실패, matching fallback과 실제 수정 비율을 기록한다.
- 기존 VLM inventory와의 문자열 겹침 및 기존 E1/M0가 선택한 교체 이름의 OCR 포함 여부를 진단한다. **기존 inventory/교체 표현은 OCR 정답 annotation이 아니므로 이를 OCR accuracy라고 부르지 않는다.**
- 처음부터 필요한 비용은 main 이미지의 CPU OCR + 기존 LM 추출 + 이번 LM matching + 최종 VLM 풀이를 합산한다. 재사용 호출도 원래 측정 시간을 청구한다. 최종 풀이 batch 시간은 main 행 비율로 배분한다.
- 실제 추가 계산 시간, stage wall, reader 적재·다운로드 시간도 별도로 기록한다. 주 비교의 호출 시간에는 양쪽 모두 모델 적재·프로세스 기동을 포함하지 않는다.

결과는 실행 종료 시 자동 생성된다.

- `artifacts/ocr_inventory_screen_v1/REPORT_KO.md`
- `reports/OCR_INVENTORY_SCREEN_RESULTS_KO.md`
- `artifacts/ocr_inventory_screen_v1/results.json`
- `artifacts/ocr_inventory_screen_v1/ocr/attempt_*/inventories.jsonl`: 원시 bbox·text·confidence
- `artifacts/ocr_inventory_screen_v1/rewrite/attempt_*/rewritten.jsonl`
- `artifacts/ocr_inventory_screen_v1/infer/attempt_*/evaluation/predictions.jsonl`

기능 검증만 하는 CPU mock은 별도 디렉터리를 사용하며 측정 성능으로 보고하지 않는다.

```bash
bash followup_rel_4lang/method_dev/scripts/run_ocr_inventory.sh --mock --run
```

현재 비교는 이미 반복 관찰한 개발 Screen 실험이다. OCR의 품질이나 최종 일반화 성능을 독립 검증했다고 주장하지 않는다.

참고: [EasyOCR 1.7.2 공식 코드](https://github.com/JaidedAI/EasyOCR/tree/v1.7.2), [API 설정](https://www.jaided.ai/easyocr/documentation/).
