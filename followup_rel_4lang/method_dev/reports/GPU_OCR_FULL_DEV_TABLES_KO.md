# GPU OCR: Screen・Selection・Internal

완료된 prediction queue만 집계한다. Screen은 기존 결과를 재사용했다. 전체 주 분석은 main158문항·1,895쌍이며, Selection 사전 제외1쌍과 Screen pilot48쌍은 실행에 남기고 아래 성능·비용에서 제외한다.

네 GPU 조건이 모두 완료된 집합: screen, selection, internal_evaluation.
미완료 조건: 없음.

Pooled 표는 네 조건이 모두 끝난 동일 집합만 합산한다. 개별 Selection/Internal 조건이 먼저 끝나면 해당 행은 표시하지만 pooled 분모에 먼저 섞지 않는다.

| 범위 | Solver | n | 방법 | 정답 | 정확도 | Inventory | 추출+정렬 | 풀이 | 총시간 | 초/pair |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| screen | 8B | 240 | O | 162 | 67.50% | 0.00분 | 0.00분 | 2.92분 | 2.92분 | 0.730 |
| screen | 8B | 240 | VLM_inventory | 178 | 74.17% | 29.56분 | 6.37분 | 3.17분 | 39.10분 | 9.774 |
| screen | 8B | 240 | EasyOCR_CPU | 179 | 74.58% | 14.92분 | 6.50분 | 3.17분 | 24.59분 | 6.146 |
| screen | 8B | 240 | easyocr_cuda | 181 | 75.42% | 0.52분 | 6.40분 | 3.23분 | 10.15분 | 2.537 |
| screen | 8B | 240 | ppocrv5_cuda | 182 | 75.83% | 0.15분 | 6.54분 | 3.33분 | 10.02분 | 2.505 |
| screen | 4B | 240 | O | 174 | 72.50% | 0.00분 | 0.00분 | 2.84분 | 2.84분 | 0.711 |
| screen | 4B | 240 | VLM_inventory | 181 | 75.42% | 11.42분 | 6.22분 | 2.85분 | 20.49분 | 5.123 |
| screen | 4B | 240 | EasyOCR_CPU | 175 | 72.92% | 14.92분 | 6.50분 | 2.92분 | 24.34분 | 6.085 |
| screen | 4B | 240 | easyocr_cuda | 177 | 73.75% | 0.52분 | 6.40분 | 3.00분 | 9.92분 | 2.479 |
| screen | 4B | 240 | ppocrv5_cuda | 177 | 73.75% | 0.15분 | 6.54분 | 3.09분 | 9.78분 | 2.444 |
| selection | 8B | 239 | O | 171 | 71.55% | 0.00분 | 0.00분 | 2.59분 | 2.59분 | 0.650 |
| selection | 8B | 239 | VLM_inventory | 175 | 73.22% | 28.58분 | 10.44분 | 3.26분 | 42.28분 | 10.615 |
| selection | 8B | 239 | EasyOCR_CPU | 178 | 74.48% | 14.11분 | 9.54분 | 3.33분 | 26.98분 | 6.773 |
| selection | 8B | 239 | easyocr_cuda | 179 | 74.90% | 0.52분 | 10.20분 | 3.36분 | 14.08분 | 3.534 |
| selection | 8B | 239 | ppocrv5_cuda | 182 | 76.15% | 0.16분 | 9.21분 | 3.51분 | 12.87분 | 3.231 |
| selection | 4B | 239 | O | 179 | 74.90% | 0.00분 | 0.00분 | 2.35분 | 2.35분 | 0.591 |
| selection | 4B | 239 | VLM_inventory | 182 | 76.15% | 8.81분 | 9.39분 | 3.01분 | 21.21분 | 5.324 |
| selection | 4B | 239 | EasyOCR_CPU | 184 | 76.99% | 14.11분 | 9.54분 | 3.21분 | 26.86분 | 6.744 |
| selection | 4B | 239 | easyocr_cuda | 185 | 77.41% | 0.52분 | 10.20분 | 3.23분 | 13.95분 | 3.501 |
| selection | 4B | 239 | ppocrv5_cuda | 183 | 76.57% | 0.16분 | 9.21분 | 3.30분 | 12.67분 | 3.180 |
| internal_evaluation | 8B | 1416 | O | 997 | 70.41% | 0.00분 | 0.00분 | 12.12분 | 12.12분 | 0.514 |
| internal_evaluation | 8B | 1416 | VLM_inventory | 1051 | 74.22% | 80.50분 | 30.51분 | 14.88분 | 125.89분 | 5.334 |
| internal_evaluation | 8B | 1416 | EasyOCR_CPU | 1042 | 73.59% | 85.65분 | 27.39분 | 15.31분 | 128.35분 | 5.439 |
| internal_evaluation | 8B | 1416 | easyocr_cuda | 1045 | 73.80% | 3.11분 | 29.35분 | 15.58분 | 48.04분 | 2.036 |
| internal_evaluation | 8B | 1416 | ppocrv5_cuda | 1056 | 74.58% | 0.92분 | 27.46분 | 15.81분 | 44.19분 | 1.872 |
| internal_evaluation | 4B | 1416 | O | 955 | 67.44% | 0.00분 | 0.00분 | 10.83분 | 10.83분 | 0.459 |
| internal_evaluation | 4B | 1416 | VLM_inventory | 1015 | 71.68% | 67.00분 | 26.79분 | 12.94분 | 106.73분 | 4.523 |
| internal_evaluation | 4B | 1416 | EasyOCR_CPU | 1014 | 71.61% | 85.65분 | 27.39분 | 13.46분 | 126.50분 | 5.360 |
| internal_evaluation | 4B | 1416 | easyocr_cuda | 1015 | 71.68% | 3.11분 | 29.35분 | 13.72분 | 46.18분 | 1.957 |
| internal_evaluation | 4B | 1416 | ppocrv5_cuda | 1025 | 72.39% | 0.92분 | 27.46분 | 14.21분 | 42.59분 | 1.805 |
| all_158 | 8B | 1895 | O | 1330 | 70.18% | 0.00분 | 0.00분 | 17.63분 | 17.63분 | 0.558 |
| all_158 | 8B | 1895 | VLM_inventory | 1404 | 74.09% | 138.64분 | 47.31분 | 21.31분 | 207.26분 | 6.562 |
| all_158 | 8B | 1895 | EasyOCR_CPU | 1399 | 73.83% | 114.68분 | 43.43분 | 21.81분 | 179.91분 | 5.696 |
| all_158 | 8B | 1895 | easyocr_cuda | 1405 | 74.14% | 4.15분 | 45.95분 | 22.17분 | 72.26분 | 2.288 |
| all_158 | 8B | 1895 | ppocrv5_cuda | 1420 | 74.93% | 1.22분 | 43.20분 | 22.65분 | 67.07분 | 2.124 |
| all_158 | 4B | 1895 | O | 1308 | 69.02% | 0.00분 | 0.00분 | 16.03분 | 16.03분 | 0.507 |
| all_158 | 4B | 1895 | VLM_inventory | 1378 | 72.72% | 87.24분 | 42.39분 | 18.80분 | 148.43분 | 4.699 |
| all_158 | 4B | 1895 | EasyOCR_CPU | 1373 | 72.45% | 114.68분 | 43.43분 | 19.59분 | 177.70분 | 5.626 |
| all_158 | 4B | 1895 | easyocr_cuda | 1377 | 72.66% | 4.15분 | 45.95분 | 19.95분 | 70.04분 | 2.218 |
| all_158 | 4B | 1895 | ppocrv5_cuda | 1385 | 73.09% | 1.22분 | 43.20분 | 20.60분 | 65.02분 | 2.059 |

Main rows only; globally deduplicated OCR/LM cache keys including original cached runtimes. Each complete batch counted once and allocated by primary rows. Model load/startup excluded.

공유 전처리를 solver별 독립 recipe에 각각 청구한다. 기존 캐시 재사용으로 절약한 실제 신규 시간·stage wall은 results.json에 따로 보존한다. OCR 생성 성공은 문자 인식 정확도의 GT 검증이 아니다.

## Paired 비교

| 범위 | Solver | 비교 | 차이 | Item bootstrap 95% CI | 회복/회귀 |
| --- | --- | --- | ---: | --- | ---: |
| screen | 8B | easyocr_cuda − O | +7.92pp | [+1.67, +15.00]pp | 30/11 |
| screen | 8B | easyocr_cuda − VLM_inventory | +1.25pp | [-1.67, +4.58]pp | 8/5 |
| screen | 8B | easyocr_cuda − EasyOCR_CPU | +0.83pp | [+0.00, +2.50]pp | 2/0 |
| screen | 8B | ppocrv5_cuda − O | +8.33pp | [+2.08, +15.42]pp | 29/9 |
| screen | 8B | ppocrv5_cuda − VLM_inventory | +1.67pp | [-0.83, +4.17]pp | 6/2 |
| screen | 8B | ppocrv5_cuda − EasyOCR_CPU | +1.25pp | [-1.67, +4.17]pp | 6/3 |
| screen | 8B | PP-OCRv5 − EasyOCR CUDA | +0.42pp | [-2.08, +2.51]pp | 4/3 |
| screen | 4B | easyocr_cuda − O | +1.25pp | [-5.00, +9.59]pp | 19/16 |
| screen | 4B | easyocr_cuda − VLM_inventory | -1.67pp | [-5.83, +2.92]pp | 7/11 |
| screen | 4B | easyocr_cuda − EasyOCR_CPU | +0.83pp | [+0.00, +2.50]pp | 2/0 |
| screen | 4B | ppocrv5_cuda − O | +1.25pp | [-4.17, +8.33]pp | 20/17 |
| screen | 4B | ppocrv5_cuda − VLM_inventory | -1.67pp | [-5.42, +1.67]pp | 3/7 |
| screen | 4B | ppocrv5_cuda − EasyOCR_CPU | +0.83pp | [-2.08, +3.75]pp | 7/5 |
| screen | 4B | PP-OCRv5 − EasyOCR CUDA | +0.00pp | [-4.17, +3.75]pp | 6/6 |
| selection | 8B | easyocr_cuda − O | +3.35pp | [-2.09, +9.62]pp | 18/10 |
| selection | 8B | easyocr_cuda − VLM_inventory | +1.67pp | [+0.00, +3.77]pp | 5/1 |
| selection | 8B | easyocr_cuda − EasyOCR_CPU | +0.42pp | [+0.00, +1.26]pp | 1/0 |
| selection | 8B | ppocrv5_cuda − O | +4.60pp | [-0.83, +10.83]pp | 18/7 |
| selection | 8B | ppocrv5_cuda − VLM_inventory | +2.93pp | [+0.83, +5.46]pp | 8/1 |
| selection | 8B | ppocrv5_cuda − EasyOCR_CPU | +1.67pp | [+0.00, +3.78]pp | 5/1 |
| selection | 8B | PP-OCRv5 − EasyOCR CUDA | +1.26pp | [+0.00, +3.36]pp | 4/1 |
| selection | 4B | easyocr_cuda − O | +2.51pp | [-2.50, +7.95]pp | 19/13 |
| selection | 4B | easyocr_cuda − VLM_inventory | +1.26pp | [-0.42, +2.93]pp | 4/1 |
| selection | 4B | easyocr_cuda − EasyOCR_CPU | +0.42pp | [+0.00, +1.26]pp | 1/0 |
| selection | 4B | ppocrv5_cuda − O | +1.67pp | [-4.17, +7.53]pp | 17/13 |
| selection | 4B | ppocrv5_cuda − VLM_inventory | +0.42pp | [-2.10, +2.92]pp | 5/4 |
| selection | 4B | ppocrv5_cuda − EasyOCR_CPU | -0.42pp | [-2.92, +1.68]pp | 3/4 |
| selection | 4B | PP-OCRv5 − EasyOCR CUDA | -0.84pp | [-3.33, +1.27]pp | 3/5 |
| internal_evaluation | 8B | easyocr_cuda − O | +3.39pp | [+0.71, +5.93]pp | 125/77 |
| internal_evaluation | 8B | easyocr_cuda − VLM_inventory | -0.42pp | [-1.62, +0.78]pp | 27/33 |
| internal_evaluation | 8B | easyocr_cuda − EasyOCR_CPU | +0.21pp | [-0.07, +0.56]pp | 4/1 |
| internal_evaluation | 8B | ppocrv5_cuda − O | +4.17pp | [+1.55, +6.71]pp | 122/63 |
| internal_evaluation | 8B | ppocrv5_cuda − VLM_inventory | +0.35pp | [-0.99, +1.55]pp | 27/22 |
| internal_evaluation | 8B | ppocrv5_cuda − EasyOCR_CPU | +0.99pp | [-0.35, +2.19]pp | 34/20 |
| internal_evaluation | 8B | PP-OCRv5 − EasyOCR CUDA | +0.78pp | [-0.56, +2.05]pp | 34/23 |
| internal_evaluation | 4B | easyocr_cuda − O | +4.24pp | [+1.41, +7.06]pp | 143/83 |
| internal_evaluation | 4B | easyocr_cuda − VLM_inventory | +0.00pp | [-1.27, +1.27]pp | 31/31 |
| internal_evaluation | 4B | easyocr_cuda − EasyOCR_CPU | +0.07pp | [-0.21, +0.35]pp | 3/2 |
| internal_evaluation | 4B | ppocrv5_cuda − O | +4.94pp | [+2.33, +7.56]pp | 142/72 |
| internal_evaluation | 4B | ppocrv5_cuda − VLM_inventory | +0.71pp | [-0.56, +1.98]pp | 32/22 |
| internal_evaluation | 4B | ppocrv5_cuda − EasyOCR_CPU | +0.78pp | [-0.35, +1.84]pp | 30/19 |
| internal_evaluation | 4B | PP-OCRv5 − EasyOCR CUDA | +0.71pp | [-0.49, +1.77]pp | 30/20 |
| all_158 | 8B | easyocr_cuda − O | +3.96pp | [+1.74, +6.23]pp | 173/98 |
| all_158 | 8B | easyocr_cuda − VLM_inventory | +0.05pp | [-1.00, +1.06]pp | 40/39 |
| all_158 | 8B | easyocr_cuda − EasyOCR_CPU | +0.32pp | [+0.00, +0.69]pp | 7/1 |
| all_158 | 8B | ppocrv5_cuda − O | +4.75pp | [+2.58, +7.02]pp | 169/79 |
| all_158 | 8B | ppocrv5_cuda − VLM_inventory | +0.84pp | [-0.26, +1.85]pp | 41/25 |
| all_158 | 8B | ppocrv5_cuda − EasyOCR_CPU | +1.11pp | [+0.00, +2.16]pp | 45/24 |
| all_158 | 8B | PP-OCRv5 − EasyOCR CUDA | +0.79pp | [-0.32, +1.80]pp | 42/27 |
| all_158 | 4B | easyocr_cuda − O | +3.64pp | [+1.27, +6.12]pp | 181/112 |
| all_158 | 4B | easyocr_cuda − VLM_inventory | -0.05pp | [-1.21, +1.11]pp | 42/43 |
| all_158 | 4B | easyocr_cuda − EasyOCR_CPU | +0.21pp | [-0.11, +0.58]pp | 6/2 |
| all_158 | 4B | ppocrv5_cuda − O | +4.06pp | [+1.90, +6.39]pp | 179/102 |
| all_158 | 4B | ppocrv5_cuda − VLM_inventory | +0.37pp | [-0.74, +1.43]pp | 40/33 |
| all_158 | 4B | ppocrv5_cuda − EasyOCR_CPU | +0.63pp | [-0.37, +1.64]pp | 40/28 |
| all_158 | 4B | PP-OCRv5 − EasyOCR CUDA | +0.42pp | [-0.63, +1.48]pp | 39/31 |

## GUI 언어별

| 범위 | Solver | 방법 | EN | ZH | TH | RU |
| --- | --- | --- | --- | --- | --- | --- |
| screen | 8B | easyocr_cuda | 46/60 | 48/60 | 41/60 | 46/60 |
| screen | 8B | ppocrv5_cuda | 47/60 | 47/60 | 42/60 | 46/60 |
| screen | 4B | easyocr_cuda | 53/60 | 46/60 | 29/60 | 49/60 |
| screen | 4B | ppocrv5_cuda | 53/60 | 45/60 | 32/60 | 47/60 |
| selection | 8B | easyocr_cuda | 48/60 | 48/60 | 36/60 | 47/59 |
| selection | 8B | ppocrv5_cuda | 49/60 | 49/60 | 36/60 | 48/59 |
| selection | 4B | easyocr_cuda | 49/60 | 51/60 | 34/60 | 51/59 |
| selection | 4B | ppocrv5_cuda | 49/60 | 52/60 | 33/60 | 49/59 |
| internal_evaluation | 8B | easyocr_cuda | 288/354 | 270/354 | 217/354 | 270/354 |
| internal_evaluation | 8B | ppocrv5_cuda | 291/354 | 277/354 | 220/354 | 268/354 |
| internal_evaluation | 4B | easyocr_cuda | 284/354 | 256/354 | 187/354 | 288/354 |
| internal_evaluation | 4B | ppocrv5_cuda | 286/354 | 265/354 | 187/354 | 287/354 |
| all_158 | 8B | easyocr_cuda | 382/474 | 366/474 | 294/474 | 363/473 |
| all_158 | 8B | ppocrv5_cuda | 387/474 | 373/474 | 298/474 | 362/473 |
| all_158 | 4B | easyocr_cuda | 386/474 | 353/474 | 250/474 | 388/473 |
| all_158 | 4B | ppocrv5_cuda | 388/474 | 362/474 | 252/474 | 383/473 |

실패·fallback·미파싱을 분모에서 제외하지 않는다.
Semantic-item bootstrap 10,000회이며 이 집합은 이미 반복 관찰한 개발 데이터다. Selection/Internal이라는 이름이 독립적인 최종 검증을 뜻하지 않는다.
