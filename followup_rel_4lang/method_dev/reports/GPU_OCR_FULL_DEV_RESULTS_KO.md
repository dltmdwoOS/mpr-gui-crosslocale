# GPU OCR 전체 개발 결과: Qwen3-VL-8B·4B

**두 GPU OCR × 두 solver의 Screen·Selection·Internal 평가가 모두 완료됐다.** PP-OCRv5의 점추정 정확도는 8B 74.93%, 4B 73.09%로 이번 inventory 조건 중 가장 높았고, 총 recipe 시간은 67.07분·65.02분이다. 기존 VLM inventory 대비 시간은 크게 줄었지만 정확도 우위의 CI는 0을 포함한다.

158개 main semantic item·1,895 mismatch pair가 주 분석이다. 조건당 실제 입력은 1,944행이며 Screen pilot 48행과 Selection 사전 제외 1행을 분석·비용에서 제외했다. 실패·fallback·미파싱을 삭제하지 않았다. 기존 Screen을 재사용하고 Selection/Internal만 추가 실행했으며, 결과 정리 과정에서 GPU 추론을 추가하지 않았다.

## 정확도와 총 시간

| Solver | Inventory | 정답/1,895 | 정확도 | 총 recipe | 초/pair |
| --- | --- | ---: | ---: | ---: | ---: |
| 8B | O | 1330 | 70.18% | 17.63분 | 0.558 |
| 8B | VLM inventory | 1404 | 74.09% | 207.26분 | 6.562 |
| 8B | EasyOCR CPU | 1399 | 73.83% | 179.91분 | 5.696 |
| 8B | EasyOCR CUDA | 1405 | 74.14% | 72.26분 | 2.288 |
| 8B | PP-OCRv5 GPU | 1420 | 74.93% | 67.07분 | 2.124 |
| 4B | O | 1308 | 69.02% | 16.03분 | 0.507 |
| 4B | VLM inventory | 1378 | 72.72% | 148.43분 | 4.699 |
| 4B | EasyOCR CPU | 1373 | 72.45% | 177.70분 | 5.626 |
| 4B | EasyOCR CUDA | 1377 | 72.66% | 70.04분 | 2.218 |
| 4B | PP-OCRv5 GPU | 1385 | 73.09% | 65.02분 | 2.059 |

EasyOCR CUDA는 VLM inventory 대비 8B +1개, 4B −1개로 정답 수가 비슷했다. PP-OCRv5는 각각 +16개·+7개였다. GPU OCR 두 방법 사이에서는 PP-OCRv5가 +15개·+8개지만 차이의 불확실성이 남는다.

시간은 OCR + 기존 E1 referent 추출 + M0 이름 정렬 + 최종 VLM 풀이의 호출 구간 합이다. 재사용한 단계도 원래 측정 시간을 청구하며, 공유 cache key는 한 번만 세고 batch 시간은 main 비율로 배분한다. 모델 적재·기동·다운로드는 제외한다. 각 solver를 단독 사용하는 recipe를 비교하므로 공통 전처리가 각 행에 포함된다.

## 정확도 차이: paired 비교

| Solver | 비교 | 차이 | Item bootstrap 95% CI | 회복/회귀 |
| --- | --- | ---: | --- | ---: |
| 8B | EasyOCR CUDA − VLM | +0.05pp | [-1.00, +1.06]pp | 40/39 |
| 8B | PP-OCRv5 − O | +4.75pp | [+2.58, +7.02]pp | 169/79 |
| 8B | PP-OCRv5 − VLM inventory | +0.84pp | [-0.26, +1.85]pp | 41/25 |
| 8B | PP-OCRv5 − EasyOCR CPU | +1.11pp | [+0.00, +2.16]pp | 45/24 |
| 8B | PP-OCRv5 − EasyOCR CUDA | +0.79pp | [-0.32, +1.80]pp | 42/27 |
| 4B | EasyOCR CUDA − VLM | -0.05pp | [-1.21, +1.11]pp | 42/43 |
| 4B | PP-OCRv5 − O | +4.06pp | [+1.90, +6.39]pp | 179/102 |
| 4B | PP-OCRv5 − VLM inventory | +0.37pp | [-0.74, +1.43]pp | 40/33 |
| 4B | PP-OCRv5 − EasyOCR CPU | +0.63pp | [-0.37, +1.64]pp | 40/28 |
| 4B | PP-OCRv5 − EasyOCR CUDA | +0.42pp | [-0.63, +1.48]pp | 39/31 |

Semantic-item bootstrap 10,000회다. PP-OCRv5−VLM과 PP-OCRv5−EasyOCR CUDA는 두 solver 모두 CI가 0을 포함한다. 8B PP−CPU의 구간도 하한이 0이므로 이 비교만으로 확정적 우월성을 주장하지 않는다. 이미 반복 관찰한 개발 집합의 탐색 결과이며, 동등성·비열등성이나 독립 일반화 검증도 아니다.

## 집합별 결과

| 집합 | n | Solver | VLM inventory | CPU OCR | CUDA EasyOCR | PP-OCRv5 |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| screen | 240 | 8B | 178/240 (74.17%) | 179/240 (74.58%) | 181/240 (75.42%) | 182/240 (75.83%) |
| screen | 240 | 4B | 181/240 (75.42%) | 175/240 (72.92%) | 177/240 (73.75%) | 177/240 (73.75%) |
| selection | 239 | 8B | 175/239 (73.22%) | 178/239 (74.48%) | 179/239 (74.90%) | 182/239 (76.15%) |
| selection | 239 | 4B | 182/239 (76.15%) | 184/239 (76.99%) | 185/239 (77.41%) | 183/239 (76.57%) |
| internal_evaluation | 1416 | 8B | 1051/1416 (74.22%) | 1042/1416 (73.59%) | 1045/1416 (73.80%) | 1056/1416 (74.58%) |
| internal_evaluation | 1416 | 4B | 1015/1416 (71.68%) | 1014/1416 (71.61%) | 1015/1416 (71.68%) | 1025/1416 (72.39%) |

4B의 Selection에서는 EasyOCR CUDA 185개, PP-OCRv5 183개로 PP가 2개 적다. Internal에서는 1,015→1,025개로 10개 많았다. 모든 집합에서 같은 방향의 차이가 난 것은 아니다.

## GUI 언어별

| Solver | GUI | n | VLM inventory | EasyOCR CUDA | PP-OCRv5 | PP−VLM |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 8B | EN | 474 | 385/474 (81.22%) | 382/474 (80.59%) | 387/474 (81.65%) | +0.42pp |
| 8B | ZH | 474 | 371/474 (78.27%) | 366/474 (77.22%) | 373/474 (78.69%) | +0.42pp |
| 8B | TH | 474 | 286/474 (60.34%) | 294/474 (62.03%) | 298/474 (62.87%) | +2.53pp |
| 8B | RU | 473 | 362/473 (76.53%) | 363/473 (76.74%) | 362/473 (76.53%) | +0.00pp |
| 4B | EN | 474 | 388/474 (81.86%) | 386/474 (81.43%) | 388/474 (81.86%) | +0.00pp |
| 4B | ZH | 474 | 354/474 (74.68%) | 353/474 (74.47%) | 362/474 (76.37%) | +1.69pp |
| 4B | TH | 474 | 246/474 (51.90%) | 250/474 (52.74%) | 252/474 (53.16%) | +1.27pp |
| 4B | RU | 473 | 390/473 (82.45%) | 388/473 (82.03%) | 383/473 (80.97%) | -1.48pp |

8B PP−VLM의 순증가 16개 중 TH GUI가 12개다. 4B는 ZH +8개·TH +6개를 얻었지만 RU에서 7개 잃었다. 태국어 GUI의 절대 성능은 여전히 낮으며, 전체 평균 개선이 모든 GUI 언어에 균일하게 적용되지는 않는다. 이 결과로 언어별 on/off 정책을 새로 만들지는 않았다.

## 속도 개선과 남은 병목

| 공통 inventory 방법 | OCR | E1 추출 | M0 정렬 | 8B 풀이 | 4B 풀이 |
| --- | ---: | ---: | ---: | ---: | ---: |
| EasyOCR CPU | 114.68분 | 9.61분 | 33.81분 | 21.81분 | 19.59분 |
| EasyOCR CUDA | 4.15분 | 9.61분 | 36.34분 | 22.17분 | 19.95분 |
| PP-OCRv5 GPU | 1.22분 | 9.61분 | 33.59분 | 22.65분 | 20.60분 |

Main 632화면의 OCR 시간은 CPU 114.68분 → EasyOCR CUDA 4.15분 → PP-OCRv5 1.22분이다. PP는 OCR 단계에서 CPU 대비 약 93.9배, CUDA EasyOCR 대비 3.39배 빠르다.

- 8B: PP 총시간은 VLM inventory 대비 67.6% 감소했다.
- 4B: PP 총시간은 VLM inventory 대비 56.2% 감소했다.

PP의 8B recipe에서 OCR는 1.8%다. 이제 비용의 큰 부분은 E1 추출 9.61분·M0 정렬 33.59분과 VLM 풀이 22.65분이다. OCR를 더 빠르게 하는 것만으로 얻을 수 있는 총시간 절감은 작다.

## 실제 새로 실행한 시간과 품질

| 추가 집합 | OCR | Stage wall 합 | 8B 새 batch/전체 | 4B 새 batch/전체 |
| --- | --- | ---: | ---: | ---: |
| selection | EasyOCR CUDA | 6.97분 | 3/80 | 2/80 |
| selection | PP-OCRv5 GPU | 9.88분 | 24/80 | 15/80 |
| internal_evaluation | EasyOCR CUDA | 21.66분 | 19/472 | 20/472 |
| internal_evaluation | PP-OCRv5 GPU | 32.02분 | 108/472 | 115/472 |

이번 Selection/Internal의 stage wall 합은 70.54분이다.
이는 두 OCR·두 solver를 모두 실행하면서 캐시로 절약한 실제 신규 stage 시간이며, 위의 main 단독 recipe와 다르다. Stage 안의 적재·I/O는 포함하지만 단계 사이 보고서 작성·parent 기동은 제외한다. PP는 재사용 가능한 LM 응답·풀이 batch가 더 적어 이번 추가 실행의 wall 합은 EasyOCR보다 길었다. 이를 PP의 cold recipe가 더 느리다는 뜻으로 읽으면 안 된다.

한 OCR의 전처리를 공유해 8B+4B를 함께 쓸 때의 main joint recipe는 EasyOCR CUDA 92.21분, PP-OCRv5 87.67분이다.

- EasyOCR CUDA: main 632화면 전사 성공. Stem 변경 1802쌍, 원문 fallback 77쌍, 유효한 무편집 16쌍. 최종 미파싱은 8B·4B 모두 0이다.
- PP-OCRv5 GPU: main 632화면 전사 성공. Stem 변경 1808쌍, 원문 fallback 74쌍, 유효한 무편집 13쌍. 최종 미파싱은 8B·4B 모두 0이다.

CPU OCR와 완성 MCQ가 같은 경우는 EasyOCR CUDA 1866/1,895쌍, PP-OCRv5 1567/1,895쌍이었다. 동일 MCQ에서도 CPU 대비 label 변화가 8B에서 각각 0/1개, 4B에서 1/1개 있었다. Batch 구성·수치 변동의 영향이 남으므로 정오 변화 전체를 OCR 문자열 차이에만 귀속하지 않는다.

OCR의 bbox/text/confidence는 보존했지만 문자 인식 GT를 별도 검수한 실험은 아니다. 별도 OCR accuracy와 REL accuracy를 구분한다. 12개 실행 queue의 이미지·질문·정답·rendered prompt hash와 7,776개 예측 행을 검증했으며, 상세 기록은 snapshot에 보존했다.

## 재현과 현재 판단

E1 stem-only 추출과 고정 Qwen3-8B M0는 유지했다. Options는 원본 그대로이며 8B/4B는 같은 OCR·LM 수정 질문을 공유한다. 최종 VLM은 BF16·SDPA·2MP·batch3·seed42·greedy2tokens다. EasyOCR 1.7.2 CUDA와 RapidOCR 3.10.0 + Paddle Inference 3.3.0 CUDA13의 PP-OCRv5 mobile 및 언어별 인식기를 사용했다. Detector 해상도·문자열 단위·전후처리 차이도 포함한 backend 비교다.

**PP-OCRv5는 다음 단계의 실용적인 inventory 후보가 됐다.** 이번 inventory 조건 중 두 solver 모두 가장 높은 점추정과 가장 짧은 recipe를 보였지만, 정확도 우위를 확정하지는 않는다. 전체 366문항·추가 모델 일반화는 이번 실행 범위가 아니다.

[전체 표·모든 대비·언어별 수치](GPU_OCR_FULL_DEV_TABLES_KO.md) · [실행 안내](GPU_OCR_FULL_DEV_RUNBOOK_KO.md) · [검증 snapshot](../artifacts/gpu_ocr_full_dev_results_snapshot.json) · [완료 raw archive](../artifacts/gpu_ocr_full_dev_completed.tar.gz) · [SHA manifest·복원 범위](../artifacts/gpu_ocr_full_dev_archive_manifest.json)
