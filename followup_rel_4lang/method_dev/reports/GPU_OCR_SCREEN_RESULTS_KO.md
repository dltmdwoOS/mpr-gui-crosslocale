# GPU OCR Screen 결과: Qwen3-VL-8B·4B

네 조건을 모두 완료했고 입력·이미지·frozen code/weights·편집 범위·예측·시간을 재검증했다. 추가 GPU 추론은 수행하지 않았다.

Main 20개 semantic item·240 mismatch pair 기준이다. 기존 batch 구성을 유지한 실제 입력은 조건당 288행이며 pilot 48행은 아래 성능·recipe 비용에서 제외했다. OCR는 backend당 128개 화면을 처리했고 main 비용에는 80개만 청구한다.

## 성능과 총 처리 시간

| Solver | Inventory | 정답/240 | 정확도 | OCR | 추출+정렬 | 최종 풀이 | 총 시간 | 초/pair |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8B | O | 162 | 67.50% | 0.00분 | 0.00분 | 2.92분 | 2.92분 | 0.730 |
| 8B | VLM inventory | 178 | 74.17% | 29.56분 | 6.37분 | 3.17분 | 39.10분 | 9.774 |
| 8B | EasyOCR CPU | 179 | 74.58% | 14.92분 | 6.50분 | 3.17분 | 24.59분 | 6.146 |
| 8B | EasyOCR CUDA | 181 | 75.42% | 0.52분 | 6.40분 | 3.23분 | 10.15분 | 2.537 |
| 8B | PP-OCRv5 GPU | 182 | 75.83% | 0.15분 | 6.54분 | 3.33분 | 10.02분 | 2.505 |
| 4B | O | 174 | 72.50% | 0.00분 | 0.00분 | 2.84분 | 2.84분 | 0.711 |
| 4B | VLM inventory | 181 | 75.42% | 11.42분 | 6.22분 | 2.85분 | 20.49분 | 5.123 |
| 4B | EasyOCR CPU | 175 | 72.92% | 14.92분 | 6.50분 | 2.92분 | 24.34분 | 6.085 |
| 4B | EasyOCR CUDA | 177 | 73.75% | 0.52분 | 6.40분 | 3.00분 | 9.92분 | 2.479 |
| 4B | PP-OCRv5 GPU | 177 | 73.75% | 0.15분 | 6.54분 | 3.09분 | 9.78분 | 2.444 |

**속도 개선은 크고, GPU OCR끼리의 정확도 차이는 작다.** CPU OCR의 main 80화면 894.92초가 EasyOCR CUDA 31.03초, PP-OCRv5 8.86초로 줄었다. OCR 단계만 보면 각각 약 28.8배·101.0배이며 PP-OCRv5는 EasyOCR CUDA보다 약 3.50배 빠르다. LM 정렬·최종 풀이가 남아 총시간은 두 GPU 방법 모두 약 10분이다.

8B에서는 PP-OCRv5가 EasyOCR CUDA보다 정답 1개 많고 4B에서는 같다. CPU EasyOCR 대비 두 GPU 방법 모두 정답 수가 소폭 늘었지만, 별도 문자 인식 GT를 검수하지 않아 OCR 자체의 인식 정확도 우위를 뜻하지 않는다. 4B에서는 두 GPU 방법 모두 VLM inventory보다 4개 적다.

시간은 OCR+기존 E1 추출+M0 정렬+VLM 풀이의 호출 구간 합이다. 캐시로 재사용한 추출·풀이도 원래 시간을 포함하고 batch 시간은 main 비율로 한 번만 배분한다. 모델 적재·기동·다운로드는 제외한다. 모든 비용을 이 서버의 Screen 측정치로 비교했으며 전체 158문항의 GPU OCR 속도는 측정하지 않았다.

## 정확도 차이와 불확실성

| Solver | 비교 | 차이 | Semantic-item bootstrap 95% CI | 회복/회귀 |
| --- | --- | ---: | --- | ---: |
| 8B | easyocr_cuda − O | +7.92pp | [+1.67, +15.00]pp | 30/11 |
| 8B | easyocr_cuda − VLM_inventory | +1.25pp | [-1.67, +4.58]pp | 8/5 |
| 8B | easyocr_cuda − EasyOCR_CPU | +0.83pp | [+0.00, +2.50]pp | 2/0 |
| 8B | ppocrv5_cuda − O | +8.33pp | [+2.08, +15.42]pp | 29/9 |
| 8B | ppocrv5_cuda − VLM_inventory | +1.67pp | [-0.83, +4.17]pp | 6/2 |
| 8B | ppocrv5_cuda − EasyOCR_CPU | +1.25pp | [-1.67, +4.17]pp | 6/3 |
| 8B | PP-OCRv5 − EasyOCR CUDA | +0.42pp | [-2.08, +2.51]pp | 4/3 |
| 4B | easyocr_cuda − O | +1.25pp | [-5.00, +9.59]pp | 19/16 |
| 4B | easyocr_cuda − VLM_inventory | -1.67pp | [-5.83, +2.92]pp | 7/11 |
| 4B | easyocr_cuda − EasyOCR_CPU | +0.83pp | [+0.00, +2.50]pp | 2/0 |
| 4B | ppocrv5_cuda − O | +1.25pp | [-4.17, +8.33]pp | 20/17 |
| 4B | ppocrv5_cuda − VLM_inventory | -1.67pp | [-5.42, +1.67]pp | 3/7 |
| 4B | ppocrv5_cuda − EasyOCR_CPU | +0.83pp | [-2.08, +3.75]pp | 7/5 |
| 4B | PP-OCRv5 − EasyOCR CUDA | +0.00pp | [-4.17, +3.75]pp | 6/6 |

8B의 O 대비 CI는 양수지만 이미 반복 관찰한 개발 Screen의 탐색 결과다. PP-OCRv5와 EasyOCR CUDA 간 차이 및 각 방법의 VLM inventory 대비 차이는 CI가 0을 포함한다. 동등성·비열등성·전체 집합 우월성을 검증한 것은 아니다.

## 언어별 정답 수

| Solver | Inventory | EN /60 | ZH /60 | TH /60 | RU /60 |
| --- | --- | ---: | ---: | ---: | ---: |
| 8B | easyocr_cuda | 46 | 48 | 41 | 46 |
| 8B | ppocrv5_cuda | 47 | 47 | 42 | 46 |
| 4B | easyocr_cuda | 53 | 46 | 29 | 49 |
| 4B | ppocrv5_cuda | 53 | 45 | 32 | 47 |

4B에서는 PP-OCRv5가 EasyOCR CUDA 대비 TH에서 +3개, ZH에서 −1개, RU에서 −2개로 전체 정답 수가 같다. 언어당 60 pair도 같은 20문항의 반복 관측이므로 언어별 일반 특성으로 해석하지 않는다.

## 품질과 실제 신규 실행 비용

두 backend 모두 128/128 화면을 전사했고 main 80개에서도 실패·빈 목록이 없었다. Main 240쌍 중 실제 stem 변경은 각각 231쌍이다. EasyOCR CUDA는 fallback 6쌍·유효한 무편집 3쌍, PP-OCRv5는 fallback 8쌍·무편집 1쌍이었다. 정렬 fallback을 분모에 포함했고 네 조건의 최종 label 미파싱은 모두 0이다.

CPU OCR와 완성 MCQ가 같았던 것은 EasyOCR CUDA 236/240쌍, PP-OCRv5 197/240쌍이다. 이 동일 MCQ 부분집합에서는 각 solver의 CPU 대비 예측 label 차이가 0이었다. EasyOCR의 CPU/CUDA 전환도 완전히 같은 전사·질문을 보장하는 변경은 아니다.

| Inventory | OCR wall | 정렬 wall | 8B wall | 4B wall | 합계 wall |
| --- | ---: | ---: | ---: | ---: | ---: |
| easyocr_cuda | 1.02분 | 8.07분 | 0.64분 | 0.54분 | 10.26분 |
| ppocrv5_cuda | 0.35분 | 7.92분 | 1.77분 | 1.60분 | 11.63분 |

실제 288행 실행의 stage wall 합은 **21.89분**이다. 기존 E1 추출을 재사용했고, EasyOCR CUDA는 solver별 96 batch 중 92개, PP-OCRv5는 64개를 재사용했다. 이 합은 새로 실행한 stage의 적재·I/O 등을 포함하지만 parent 기동·단계 사이 보고서 작성은 제외하며, main 240쌍을 처음부터 처리하는 위 recipe 시간과 다르다.

두 solver를 함께 사용할 때 main 전처리를 한 번만 청구한 joint recipe는 EasyOCR CUDA **13.15분**, PP-OCRv5 **13.11분**이다. 단독 solver 표의 총시간을 두 번 더하면 공유 전처리가 중복된다.

## 설정과 다음 판단

기존 E1 stem-only 추출 결과와 고정 Qwen3-8B M0 matcher를 유지하고 inventory 공급원만 바꿨다. Options는 원본 그대로다. VLM은 BF16·SDPA·2MP·batch 3·seed 42·greedy 2 tokens로 유지했고 8B/4B에 같은 수정 MCQ를 제공했다.

EasyOCR 1.7.2 CUDA와 PP-OCRv5 mobile detector/언어별 mobile recognizer를 비교했다. PP-OCRv5는 RapidOCR 3.10.0 전후처리와 Paddle Inference 3.3.0 CUDA13을 사용한다. 해상도·분할 단위·전후처리 차이도 포함된 backend 비교다. ONNX Runtime 경로는 B200 커널 호환성 문제로 제외했다.

**현재 선택은 속도와 두 solver의 결과를 함께 보면 PP-OCRv5가 유망하다.** 다만 GPU OCR의 Selection/Internal은 아직 수행하지 않았다. 다음 검증은 Screen 정확도 우위를 전제하지 않고 고정 설정 그대로 더 넓은 집합에서 측정하는 것이다. 기존 CPU OCR 전체 1,895쌍 결과와 이번 GPU OCR Screen 240쌍을 구분한다.

[실행·설정 안내](GPU_OCR_SCREEN_RUNBOOK_KO.md) · [완료 결과 snapshot](../artifacts/gpu_ocr_screen_results_snapshot.json) · [원시 결과 archive](../artifacts/gpu_ocr_screen_completed.tar.gz) · [SHA manifest와 복원 범위](../artifacts/gpu_ocr_screen_archive_manifest.json)
