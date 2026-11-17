# EasyOCR CUDA / PP-OCRv5 GPU: Screen 실행

두 OCR inventory를 기존 E1/M0 stem-only 방법에 연결하고 Qwen3-VL-8B·4B로 평가했다. **네 Screen 조건 모두 완료했다.** [결과·정확도·총 시간 비교](GPU_OCR_SCREEN_RESULTS_KO.md): 8B는 EasyOCR CUDA 75.42%, PP-OCRv5 75.83%, 4B는 모두 73.75%다. Selection/Internal GPU OCR은 아직 수행하지 않았다.

## 바로 실행

Repository 루트에서 실행한다. 두 OCR와 두 solver를 순차 실행하며 같은 명령으로 재개할 수 있다. 현재 완료 상태에서는 추론을 반복하지 않고 보고서만 갱신한다.

```bash
nohup bash followup_rel_4lang/method_dev/scripts/run_gpu_ocr_screen.sh > followup_rel_4lang/method_dev/artifacts/gpu_ocr_screen.log 2>&1 &
```

```bash
tail -f followup_rel_4lang/method_dev/artifacts/gpu_ocr_screen.log
```

결과는 `followup_rel_4lang/method_dev/artifacts/gpu_ocr_screen_paddle_v1/REPORT_KO.md`와 `results.json`에 누적된다. 8B/4B의 O·기존 VLM inventory·CPU EasyOCR·새 GPU OCR 조건을 같은 main 240쌍으로 비교한다. 아직 실행되지 않은 조건은 pending으로 남긴다.

보고서만 갱신하려면 다음 명령을 사용한다.

```bash
.venv/bin/python followup_rel_4lang/method_dev/scripts/report_gpu_ocr_screen.py
```

## 실행 범위와 흐름

| Inventory | 최종 solver | 주 분석 | 실제 풀이 입력 |
| --- | --- | ---: | ---: |
| EasyOCR CUDA | Qwen3-VL-8B | 240 pair | 288 pair |
| EasyOCR CUDA | Qwen3-VL-4B | 240 pair | 288 pair |
| PP-OCRv5 Paddle GPU | Qwen3-VL-8B | 240 pair | 288 pair |
| PP-OCRv5 Paddle GPU | Qwen3-VL-4B | 240 pair | 288 pair |

Main은 semantic item 20개 × mismatch 언어쌍 12개다. 기존 batch 구성을 유지하려고 legacy pilot 동반 48행도 처리하지만 주 정확도와 recipe 비용에서 제외한다. OCR는 backend마다 128개 고유 이미지(main 80개)를 처리한다. Selection/Internal은 이번 실행에 포함하지 않는다.

Backend마다 다음 순서로 실행한다.

1. Screenshot만 입력해 GPU OCR inventory를 만든다.
2. 기존에 완료한 **E1 stem referent 추출 결과를 재사용**한다. 새 추출은 하지 않는다.
3. 고정 Qwen3-8B LM의 **M0 prompt**에 원본 MCQ·referents·새 inventory를 제공한다. Inventory에 존재하는 교체 표현만 선택하고 코드로 stem에 치환한다. Options는 원본 그대로다.
4. 같은 수정 MCQ를 8B, 이어서 4B로 각각 푼다.

추출·정렬 prompt와 한 차례 구조 repair·전체 응답 fallback 정책은 기존 CPU OCR와 같다. 새로운 prompt나 oracle span을 도입하지 않았다. 빈 inventory와 OCR/정렬 실패를 조용히 제외하거나 VLM inventory로 대체하지 않는다. Raw bbox·text·confidence를 저장하지만 LM에는 정렬·중복 제거된 문자열만 제공한다.

## OCR 설정

전체 설정·weight SHA-256·다운로드 URL은 `configs/gpu_ocr_screen_v1.json`에 있다.

| 항목 | EasyOCR CUDA | PP-OCRv5 GPU |
| --- | --- | --- |
| 패키지 | EasyOCR 1.7.2 | RapidOCR 3.10.0 + Paddle GPU 3.3.0 CUDA13 |
| 실행기 | PyTorch CUDA | Native Paddle Inference CUDA |
| Detection | CRAFT | PP-OCRv5 mobile |
| EN 인식 | english_g2 | en_PP-OCRv5_rec_mobile |
| ZH 인식 | zh_sim_g2 + English | ch_PP-OCRv5_rec_mobile |
| TH 인식 | Thai + English | th_PP-OCRv5_rec_mobile |
| RU 인식 | Cyrillic + English | eslav_PP-OCRv5_rec_mobile |
| Recognition batch | 8 | 8 |
| Detection 해상도 | canvas_size 2560, mag_ratio 1 | limit_type max, limit_side_len 960 |
| 추가 인식 confidence 필터 | 없음 | 없음(text_score=0) |
| 회전 분류 | 해당 없음 | 사용 안 함 |

PP-OCRv5는 **RapidOCR 전후처리 + Paddle predictor** 구성이다. PaddleOCR Python pipeline 전체를 실행하는 설정과는 구분한다. Detector 크기·분할 단위·전후처리도 다른 backend 비교이며, 동일 해상도에서의 인식 모델만 비교하는 실험은 아니다.

기존 EasyOCR weights를 재사용했다. PP-OCRv5의 모델 파일은 RapidOCR v3.10.0 목록의 upstream SHA를 확인했고 dictionary도 SHA로 고정했다. 실제 화면 언어로 인식기를 선택한다. Query나 정답으로 언어/인식기를 선택하지 않는다.

처음 시도한 ONNX Runtime 1.32.0 및 공식 CUDA13 1.31.0 경로는 B200에서 `cudaErrorNoKernelImageForDevice`로 실패해 사용하지 않는다. 최종 경로는 Paddle이며 ONNX 실패를 CPU 실행으로 대체하지 않았다.

## 고정 LM / VLM

| 역할 | 체크포인트 revision |
| --- | --- |
| E1/M0 고정 LM: Qwen3-8B | `47719a242beab8f9aecc40ce3928b034dd5dd559` |
| 최종 Qwen3-VL-8B-Instruct | `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b` |
| 최종 Qwen3-VL-4B-Instruct | `ebb281ec70b05090aa6165b016eac8ec08e71b17` |

최종 풀이는 기존 BF16·SDPA·channels_last_3d·batch 3·seed 42·greedy·max_new_tokens 2·max_input_tokens 4096·min/max pixels 262144/2097152·score_labels 설정을 유지한다. M0는 thinking 비활성·greedy·출력 512 token, 구조 repair 최대 한 차례다. E1은 재추출하지 않는다.

실제로 적용하는 전체 system prompt·config·의존 파일 해시는 backend별 `contract.json`에 고정된다. 기존 코드와 결과는 덮어쓰지 않는다.

## 재개와 시간 집계

- OCR는 image·GUI language·패키지/config·weights hash로 캐시한다. CPU 결과를 CUDA 결과로 복사하지 않는다.
- 정렬은 기존 exact-message LM 캐시를 사용한다. OCR와 정렬은 backend당 한 번이며 두 solver가 공유한다.
- 풀이 재사용은 **동일 checkpoint·전체 ordered batch·프롬프트·이미지·seed·실행 환경**이 모두 같아야 한다. 8B 예측을 4B에 재사용하지 않는다.
- 중단한 OCR/LM 캐시와 완료된 풀이 batch를 재사용한다. 완료 단계는 건너뛴다.
- 정확도·언어별 정답 수·O/VLM/CPU 대비 회복/회귀와 semantic-item bootstrap CI를 생성한다.
- 총 시간은 inventory + 기존 E1 추출 + M0 정렬 + 최종 VLM 풀이를 합산한다. 재사용해도 원래 측정 시간을 포함하며, 분모는 main 240 pair다. OCR는 main 80개 화면을 한 번만 청구한다. Batch 시간도 한 번만 세고 main 비율로 배분한다.
- 모델 다운로드·적재·프로세스 기동은 recipe 합계에서 제외하고 stage wall/reader load/실제 새 추론량을 별도 보존한다. 두 solver를 함께 돌릴 때 전처리를 공유하는 것과 각 solver의 독립 recipe 비용을 구분한다.

## 설치와 검증

현재 서버에서는 이미 설치했다. 다시 구성하려면 기존 VLM `.venv`를 준비한 뒤 실행한다.

```bash
bash followup_rel_4lang/method_dev/scripts/setup_ocr.sh
bash followup_rel_4lang/method_dev/scripts/setup_gpu_ocr.sh
.venv/bin/python followup_rel_4lang/method_dev/scripts/run_gpu_ocr_screen.py --smoke
```

Paddle/RapidOCR는 repository 안 `.venv-ocr-gpu`에 분리했다. 기존 `.venv`와 frozen Torch/Transformers는 변경하지 않았다. 이 서버에 이미 있는 CUDA13/cuDNN9 라이브러리를 재사용하므로 Paddle 설치는 `--no-deps`이며, 선언된 일부 CUDA package patch 버전과는 차이가 있다. `pip check` 전체 통과를 주장하는 환경은 아니다. 실제 GPU 실행을 검증했으며 다른 서버에서는 CUDA smoke를 다시 확인해야 한다.

4개 언어 × 2 backend의 실제 screenshot smoke가 모두 성공했다. EasyOCR의 detector/recognizer가 CUDA에 있는지 검사했고, Paddle predictor의 GPU 설정 및 profiler의 실제 CUDA kernel을 확인했다(언어별 919~1,517개 kernel event). 이 8개 화면은 기능 확인용이며 OCR 정확도나 전체 속도 비교 결과가 아니다. Paddle 프로파일링 비용도 포함돼 있다.

CPU mock은 4개 평가 조건 모두 288행을 처리한다. 결과에 `empirical: false`를 기록해 실제 결과와 구분한다.

```bash
bash followup_rel_4lang/method_dev/scripts/run_gpu_ocr_screen.sh --mock
```

45GB MIG에서 OCR·LM·8B·4B를 별도 process로 순차 실행하고 프로젝트 GPU lock을 공유한다. EasyOCR smoke의 Torch peak allocation은 약 2.6~3.0GiB였다. Paddle allocation은 Torch 통계에 포함되지 않아 0을 사용량으로 해석하면 안 된다. PP-OCRv5 mobile은 작은 OCR 모델이며, LM/VLM은 이미 완료한 동일 batch·해상도 설정을 재사용한다. 자원 부족이나 OOM 발생 시 중단하고 자동 batch 축소·CPU fallback으로 조건을 바꾸지 않는다.
