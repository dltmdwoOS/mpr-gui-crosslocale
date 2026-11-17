# 선택적 정렬 개발 실험: 현재까지의 정리

후속 GPU OCR Screen 네 조건도 완료했다. [별도 결과와 시간 비교](GPU_OCR_SCREEN_RESULTS_KO.md): main20문항·240쌍에서 8B는 EasyOCR CUDA75.42%, PP-OCRv5 75.83%, 4B는 모두73.75%다. 총 recipe는 약10분이며 CPU OCR 대비 크게 줄었지만 GPU OCR의 Selection/Internal은 아직 없다. 아래 158문항 표의 OCR는 기존 CPU EasyOCR 결과다.

정리 시점(UTC): 2026-11-17T22:16:05.556265+00:00. **TT·CLP 전체 완료, OCR 8B·4B 전체158문항 완료.** 이 보고서는 최근 158문항 method 개발 실험을 정리하며, 과거 전체 cross-locale benchmark의 새 재실행 결과가 아니다.

현재 주력은 **E1/M0 Stem-only GUI**다. 8B에서 O 70.18% → 74.09%, 4B에서 69.02% → 72.72%였다. TT는 8B에서 71.13%로 비용이 적다. Inventory 없는 이미지 직접 rewrite는 71.72%였다. **CLP의 저장된 규칙 기준 accuracy는 65.96%지만 출력 길이와 최종 답 표기 문제가 많아, CLP 자체의 유효성을 부정하는 결과로 읽으면 안 된다.**

## 평가 범위와 비교 원칙

- EN/ZH/TH/RU, 158개 main semantic item × 12 mismatch 방향 = 1,896 pair. 기존 사전 제외 1pair를 유지해 주 분석은 **1,895 pair**다.
- Screen 20 item·240 pair, Selection 20 item·239 pair, Internal 118 item·1,416 pair다. Pilot 48 pair는 배치 유지용 동반 행이며 주 분석에서 제외한다.
- 모든 집합은 이미 관찰한 development cohort다. Internal이라는 이름이 독립적인 최종 검증을 뜻하지 않는다. 실패·fallback·미파싱 답도 분모에 포함한다.
- 아래 8B 비용은 B200 MIG에서 기록된 전처리와 풀이 호출 시간을 합산했다. 공유 호출은 cache key당 한 번, 배치는 실제 행 수로 안분한다. 모델 적재·프로세스 기동·일부 CPU/I/O는 제외하므로 전체 wall time과 다르다.

## 무엇을 시도했는가

| 계열 | 실험 | 구성과 현재 상태 |
| --- | --- | --- |
| 과거 구현 이력 | 초기 GUI_EXACT, GUI_MATCH_LM, GUI_TARGETED_VLM, edit-list direct, 초기 GUI_FULL, 초기 oracle | 자동 추출·matching·출력 인터페이스의 병목을 조사했다. 사용자 결정으로 초기 inventory 기반 구현은 의도한 two-stage 평가에서 제외했고 원시 결과만 보존한다. 아래 유효 방법과 섞지 않는다. |
| 복원한 two-stage | Full GUI/TXT, Selective Auto/Oracle GUI/TXT | 과거 inventory-conditioned 번역 프롬프트와 repair 구조를 복원해 Screen에서 비교했다. Oracle은 gold source span 진단이다. |
| 역할별 처리 | Hybrid GUI/TXT, Stem-only GUI | Stem referent만 치환하고 options를 전체 번역하거나 원문으로 유지한다. Hybrid GUI는 Screen 74.17%, 초기 Stem-only GUI는 72.92%였다. |
| LM 호출 통합 | Stem 통합, Stem+Options 통합 | Inventory를 제공한 채 추출+정렬을 LM 한 기본 호출로 합쳤다. Screen 72.08%, 74.58%다. Inventory-free 실험이 아니다. |
| VLM 직접 편집 | 완성 MCQ rewrite, 원문 복사 강화 rewrite | Screenshot+MCQ에서 완성 stem/options를 생성하고 VLM으로 푼다. Inventory·별도 extractor·고정 LM이 없다. 수정 버전을 158문항에 고정 적용했다. |
| 추출×matching 2×2 | E0/E1 × M0/M1 | 추출 프롬프트 수정(E1)과 후보 ID matcher(M1)를 분리했다. E1/M0를 선택했고 전체 158문항 완료했다. |
| 모델 전이 | Qwen3-VL-4B E1/M0 | LM과 방법을 고정하고 inventory/최종 풀이 VLM만 4B로 교체했다. 전체 158문항 완료다. |
| 외부 baseline 이식 | TT, CLP | TT는 전체 영어 번역, CLP는 영어 이해 응답을 대화에 유지한 뒤 단계별 시각 풀이를 한다. 모두 8B 전체 158문항 완료. 원 논문 모델/API 설정의 재현과 구분한다. |
| OCR 비교 | EasyOCR inventory E1/M0 | 기존 E1 출력·M0·최종 8B를 유지하고 inventory만 OCR로 바꾼다. OCR 8B·4B 전체158문항 완료. 아래 단계 상태와 별도 Screen 보고서를 기준으로 확인한다. |

초기 구현의 자세한 수치는 [이전 search 보고서](SEARCH_RESULTS_KO.md)와 [초기 oracle 보고서](ORACLE_RESULTS_KO.md)에 남아 있다. 특히 초기 GUI_EXACT는 **inventory를 주지 않고 독립 번역한 뒤 exact matching**했고, 현재 M0는 **번역/교체 이름을 고르는 LM에 inventory와 원본 MCQ를 함께 제공**한다. 이 차이가 이름보다 중요하다.

## 전체 158문항: 8B 성능과 효율

| 방법 | 정답/1,895 | 정확도 | O 대비 | 전처리 | 최종 풀이 | 합계 | 초/pair |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| O · 원본 | 1330 | 70.18% | +0.00pp | 0.00분 | 17.63분 | 17.63분 | 0.558 |
| TT · 전체 영어 번역 | 1348 | 71.13% | +0.95pp | 15.33분 | 16.77분 | 32.10분 | 1.016 |
| CLP · 영어 이해 후 단계별 풀이 | 1250 | 65.96% | -4.22pp | 113.96분 | 156.18분 | 270.14분 | 8.553 |
| 이미지 직접 rewrite · 원문 복사 강화 | 1359 | 71.72% | +1.53pp | 78.21분 | 20.86분 | 99.07분 | 3.137 |
| Stem-only GUI · E1/M0 | 1404 | 74.09% | +3.91pp | 185.96분 | 21.31분 | 207.26분 | 6.562 |

**E1/M0의 구체적 구성:** Qwen3-VL-8B screenshot-only inventory → 고정 Qwen3-8B LM의 E1 stem 추출 → 같은 LM의 M0 inventory-conditioned 교체 이름 선택 → 코드가 stem span만 치환 → 원래 options와 screenshot으로 Qwen3-VL-8B 풀이. VLM은 BF16·SDPA·2MP·batch3, 일반 풀이 최대 2 tokens다. CLP는 같은 checkpoint를 사용하지만 별도 대화/system prompt와 최대 512 tokens로 풀고 label scoring도 사용하지 않는다.

TT는 비영어 source MCQ 474개를 영어로 번역해 GUI 3방향에 공유하고, 영어 source 158개는 그대로 쓴다. CLP는 영어 source도 이해 단계를 거치며 632개 source MCQ를 처리한다. 호출 수와 출력량이 달라 단순한 모델 속도 비교가 아니다.

| 집합 | n | O | TT | CLP | 이미지 직접 rewrite | E1/M0 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| screen | 240 | 162/240 (67.50%) | 171/240 (71.25%) | 166/240 (69.17%) | 170/240 (70.83%) | 178/240 (74.17%) |
| selection | 239 | 171/239 (71.55%) | 170/239 (71.13%) | 147/239 (61.51%) | 173/239 (72.38%) | 175/239 (73.22%) |
| internal_evaluation | 1416 | 997/1416 (70.41%) | 1007/1416 (71.12%) | 937/1416 (66.17%) | 1016/1416 (71.75%) | 1051/1416 (74.22%) |

| 전체 paired 비교 | 차이 | 95% semantic-item bootstrap CI | 회복/회귀 |
| --- | ---: | --- | ---: |
| TT · 전체 영어 번역 − O · 원본 | +0.95pp | [-1.53, +3.38]pp | 157/139 |
| CLP · 영어 이해 후 단계별 풀이 − O · 원본 | -4.22pp | [-8.13, -0.42]pp | 237/317 |
| 이미지 직접 rewrite · 원문 복사 강화 − O · 원본 | +1.53pp | [-0.21, +3.27]pp | 115/86 |
| Stem-only GUI · E1/M0 − O · 원본 | +3.91pp | [+1.69, +6.18]pp | 168/94 |
| Stem-only GUI · E1/M0 − TT · 전체 영어 번역 | +2.96pp | [+0.00, +6.07]pp | 221/165 |
| Stem-only GUI · E1/M0 − CLP · 영어 이해 후 단계별 풀이 | +8.13pp | [+4.32, +12.09]pp | 361/207 |

CI는 item 단위 10,000회 bootstrap이다. 반복 개발·다중 비교를 보정한 독립 확인 실험의 유의성으로 해석하지 않는다.

## CLP 결과를 해석할 때 먼저 봐야 할 출력 문제

| 관찰 지표 | 건수 | 분모 | 비율 |
| --- | ---: | ---: | ---: |
| LM 이해 출력이 512-token 상한 도달 | 359 | 632 | 56.80% |
| 최종 VLM 출력 상한 도달 | 339 | 1895 | 17.89% |
| 최종 label 파싱 실패 | 396 | 1895 | 20.90% |
| 파싱 실패 중 상한 도달 | 338 | 396 | 85.35% |
| 파싱 실패 중 상한 미도달 | 58 | 396 | 14.65% |

주 정확도 **1250/1895=65.96%는 그대로 유지**한다. 미파싱 396쌍 중 338쌍은 길이 제한에 도달했다. JSON 생성 실패와는 다르며, 긴 풀이가 마지막 답까지 도달하지 못한 사례가 실제 raw에 보인다.

상한에 도달하지 않은 미파싱 58쌍 중 54쌍은 마지막 줄이 `### ✅ Final Answer: A` 또는 `✅ Answer: A` 같은 명확한 답이었다. 고정 parser가 요구한 `Answer: A` 형식과 맞지 않아 거절됐다. Markdown bold만 제거하고 heading·체크표시·Final 접두어는 허용하지 않았기 때문이다.

**사후 형식 진단:** 이 54쌍 중 50쌍이 정답이다. 마지막 줄의 이 제한된 표기만 허용하면 **1300/1895=68.60%**가 된다. 이는 사후 parser 민감도 수치이며 고정 baseline의 공식 점수를 대체하지 않는다. 잘린 출력에서 추론 중 등장한 A–D를 끌어오지 않았고 추가 추론·답 추출 호출도 수행하지 않았다.

유효 최종 답이 있는 1499쌍만 보면 CLP 83.39%, 같은 subset의 E1/M0 77.92%다. 하지만 유효 출력 여부로 표본을 선택한 결과이므로 이 조건부 수치를 전체 성능이나 개선된 CLP의 예상 정확도로 사용할 수 없다. 현재 CLP는 이해/추론 오류, 과도한 출력, 형식 실패가 함께 섞인 pipeline 결과다.

따라서 **“일반 cross-lingual prompting은 도움이 없다”는 결론은 보류**한다. 현재 고정 이식 구현의 ITT 성능과 비용이 좋지 않았다는 결론은 가능하다. 복구 실험을 하려면 final-line 규칙과 출력 예산을 새 버전으로 고정해야 하며 이번 점수를 소급 수정하지 않는다.

## GUI 언어별 8B 전체 결과

| GUI | n | O | TT | CLP | 직접 rewrite | E1/M0 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| EN | 474 | 81.22% | 77.00% | 77.22% | 80.80% | 81.22% |
| ZH | 474 | 75.32% | 77.64% | 67.51% | 76.16% | 78.27% |
| TH | 474 | 48.31% | 50.63% | 53.38% | 52.74% | 60.34% |
| RU | 473 | 75.90% | 79.28% | 65.75% | 77.17% | 76.53% |

E1/M0는 Thai GUI에서 O 48.31% → 60.34%로 가장 큰 개선을 보인다. TT는 RU에서 79.28%로 E1/M0 76.53%보다 높고 EN에서는 O보다 낮다. 한 평균이나 한 언어를 근거로 소급 routing 정책을 만들지 않는다.

## OCR 전체 집합 완료: 성능과 효율

**Screen에서 보였던 OCR의 작은 정확도 우위는 전체 집합에서 유지되지 않았다.** 전체에서는8B·4B 모두 VLM inventory보다 정답이5개 적었고, 차이의95% item bootstrap CI는0을 포함한다. 동등성·비열등성을 검증한 결과는 아니다.

분모는158개 main semantic item·1,895pair다. Pilot48pair와 사전 제외1pair는 실행에 남기고 분석·비용에서 제외했다. 실패·fallback·미파싱을 삭제하지 않았다. 이미 반복 관찰한 development cohort의 탐색 결과이며 전체366문항 평가나 독립 일반화 검증이 아니다.

| 모델 | O | VLM inventory | OCR inventory | OCR−O | OCR−VLM / 95% item CI | 회복/회귀 vs VLM |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| 8B | 1330/1895 (70.18%) | 1404/1895 (74.09%) | 1399/1895 (73.83%) | +3.64pp | -0.26pp [-1.32, +0.74] | 36/41 |
| 4B | 1308/1895 (69.02%) | 1378/1895 (72.72%) | 1373/1895 (72.45%) | +3.43pp | -0.26pp [-1.42, +0.90] | 41/46 |

| 집합 | n | 8B VLM inventory | 8B OCR | 4B VLM inventory | 4B OCR |
| --- | ---: | ---: | ---: | ---: | ---: |
| screen | 240 | 74.17% | 74.58% | 75.42% | 72.92% |
| selection | 239 | 73.22% | 74.48% | 76.15% | 76.99% |
| internal_evaluation | 1416 | 74.22% | 73.59% | 71.68% | 71.61% |

8B OCR는Screen+1개·Selection+3개·Internal−9개였다. 4B OCR는Screen−6개·Selection+2개·Internal−1개다. 따라서 Screen만으로 전체 accuracy나 속도를 예상하면 안 된다.

### 총 처리 시간과 GPU 호출 시간

| 모델·방법 | CPU OCR | GPU 전처리+풀이 | 총 호출 시간 | 초/pair |
| --- | ---: | ---: | ---: | ---: |
| 8B · VLM inventory | — | 207.26분 | 207.26분 | 6.562 |
| 8B · OCR inventory | 114.68분 | 65.23분 | 179.91분 | 5.696 |
| 4B · VLM inventory | — | 148.43분 | 148.43분 | 4.699 |
| 4B · OCR inventory | 114.68분 | 63.02분 | 177.70분 | 5.626 |

8B의 총시간은 **13.2% 감소**했지만4B는 **19.7% 증가**했다. CPU OCR 자체는 두 solver가 공유하며114.68분이다. 이전4B VLM inventory가 이미 빠르므로 CPU OCR 교체가4B 단독 recipe의 속도 개선으로 이어지지 않았다.

8B Internal만 보면125.89→128.35분으로 소폭 느려졌다. Screen에서의37.1% 감소와 달리 전체8B 감소는13.2%다. OCR는 GPU를 CPU로 옮겨 GPU 호출 구간을 크게 줄이지만 항상 총시간까지 줄이는 방법은 아니다.

공통 OCR+LM 전처리는158.10분이다. 단독 recipe에는 이를 각 모델에 청구하되, 8B+4B 공동 recipe는 한 번만 더해 **199.50분**이다. 이번 실제 신규4B 풀이 호출은 cache를 제외해10.94분이었다. 이는 전체4B 단독 처리시간과 다르다.

모든 시간은 기록된 호출 구간의 합으로 모델 적재·프로세스 기동·일부CPU/I/O를 제외한다. CPU는3스레드, GPU는B200 MIG45GB이며 GPU 호출 시간은 GPU utilization이나 전력 측정치가 아니다. 재사용 호출도 원래 시간을 청구했고, 공유 cache key는 전역으로 한 번, batch 시간은 primary행 비율로 배분했다.

### 언어별 변화와 품질 확인

| GUI | n | 8B VLM→OCR | 4B VLM→OCR |
| --- | ---: | ---: | ---: |
| EN | 474 | 81.22% → 80.17% | 81.86% → 81.43% |
| ZH | 474 | 78.27% → 77.00% | 74.68% → 74.68% |
| TH | 474 | 60.34% → 62.03% | 51.90% → 52.11% |
| RU | 473 | 76.53% → 76.11% | 82.45% → 81.61% |

Main632개 OCR 이미지는 모두 처리에 성공했고 최종 label 파싱 실패는 두 모델 모두0이었다. 8B는원문 fallback77pair를 포함했다. VLM inventory와 완성 MCQ가 같았던1,481pair 중2pair에서 label 차이가 있어, 관찰된 정오 변화 전부를 inventory 내용 차이로 단정하지 않는다. 문자 인식 GT를 별도로 검수한 실험은 아니므로 OCR 문자 인식 자체가 더 정확하다고 주장하지 않는다.

8B/4B OCR는 전처리와1,895개 완성 MCQ를 정확히 공유했다. 8B73.83%와4B72.45%의 차이는1.37pp이며 4B−8B CI는[−4.55,+1.74]pp다. 두 solver의 동등성도 확인한 것은 아니다.

**현재 판단:** OCR는8B에서 작은 accuracy 하락 점추정과 총시간/GPU 비용 절감이 관찰된 실용적 대안이다. 4B에서는 accuracy 점추정도 약간 낮고 총시간은 늘어, GPU 호출 시간을 줄이는 가치와 CPU 비용을 함께 고려해야 한다. 전 모델 공통의 정확도·속도 우월성을 결론 내리지 않는다.

[완료 raw archive](../artifacts/ocr_completed_8b_4b.tar.gz)와 [파일별 SHA-256·복원 범위](../artifacts/ocr_completed_archive_manifest.json)에 계약·전사 원문·matching 응답·예측·비용·고정 의존 파일을 보존한다. 모델 weights·screenshot·private label 파일·mock·미완료 attempt는 archive에 포함하지 않는다. 깨끗한 checkout의 저장소 루트에서 `tar -xzf followup_rel_4lang/method_dev/artifacts/ocr_completed_8b_4b.tar.gz`로 복원한다. 데이터·이미지와 frozen HF checkpoint는 기존 lock/runbook에 따라 별도 준비해야 하며 일부 런타임 경로는 이 연구실 workspace의 절대 경로다.

## Screen에서 비교하고 확장하지 않은 후보

| 방법 | Screen 정답/240 | 정확도 | 전처리+풀이 시간 |
| --- | ---: | ---: | ---: |
| 전체 텍스트 번역 | 161 | 67.08% | 12.64분 |
| Hybrid TXT | 163 | 67.92% | 16.98분 |
| Full GUI | 170 | 70.83% | 43.66분 |
| Stem+Options 선택적 정렬 · 분리 | 169 | 70.42% | 41.59분 |
| Stem-only GUI · 분리 | 175 | 72.92% | 36.97분 |
| Hybrid GUI | 178 | 74.17% | 47.33분 |
| Oracle span GUI · 진단 | 180 | 75.00% | 41.57분 |
| Stem 통합 GUI | 173 | 72.08% | 39.82분 |
| Stem+Options 통합 GUI | 179 | 74.58% | 50.49분 |
| Screenshot 직접 rewrite · 문맥 보존 별도 진단 | 171 | 71.25% | 12.74분 |

Oracle은 gold source span을 쓰는 진단이며 자동 방법이 아니다. 위 초기 Stem-only는 E0/M0이고 주력 E1/M0와 구분한다. Hybrid의 options 전체 번역과 통합 방법의 자동 span·교체 표현 선택에는 context/숫자/선택지 의미 손상 위험이 남아 있다. 직접 rewrite는 이후 원문 복사 강화 버전으로 확장했으며, 위 초기 버전의 Screen 수치를 수정 버전의 전체 결과와 합치지 않는다.

### E0/E1 × M0/M1 선택 근거

| 추출 / matching | M0 · 기존 표현 선택 | M1 · 후보 ID 선택 |
| --- | ---: | ---: |
| E0 · 기존 추출 | 175/240 (72.92%) | 171/240 (71.25%) |
| E1 · 수정 추출 | 178/240 (74.17%) | 177/240 (73.75%) |

E1/M0를 전체 158문항에 적용했을 때 E0/M0 1,402정답 → E1/M0 1,404정답, **+0.11pp(CI [−0.47,+0.69])**였다. Source extraction F1은 87.23% → 91.95%로 올랐지만 REL 개선은 매우 작았다. 추출 지표 개선만으로 정확도 개선을 보장하지 않는다는 결과다.

## 4B 전이와 parallel reference

| VLM | O | E1/M0 | 차이 | method 전체 계산 시간 |
| --- | ---: | ---: | ---: | ---: |
| Qwen3-VL-8B | 1330/1895 (70.18%) | 1404/1895 (74.09%) | +3.91pp | 207.26분 |
| Qwen3-VL-4B | 1308/1895 (69.02%) | 1378/1895 (72.72%) | +3.69pp | 148.43분 |

4B의 method−O CI는 [+1.32,+6.23]pp다. LM은 계속 Qwen3-8B이고 inventory와 최종 풀이 VLM만 4B로 바뀐다. 4B 비용은 기존 보고서의 cohort별 recipe 합계이며 8B의 전역 cache 중복 제거 집계와 미세한 차이가 있다. 두 모델 모두 개발 자료의 전이 결과다.

| 같은 1,895쌍의 참고 기준 | 정답 | 정확도 | 구분 |
| --- | ---: | ---: | --- |
| T_REF | 1335 | 70.45% | Gold source span + 기존 Gemma 번역 |
| R_stem | 1472 | 77.68% | Parallel referent를 stem에만 적용 |
| R_REF | 1591 | 83.96% | Parallel referent를 stem/options에 적용 |
| F_REF | 1551 | 81.85% | Parallel 전체 localization |

이 reference들은 자동 방법이 아니며 과거 RTX4090·batch/queue 차이가 있다. R/F는 실제 screenshot exact-label oracle도 아니다. 준비·번역 시간 일부가 기록되지 않아 자동 방법의 B200 총시간과 합쳐 비용 순위를 만들지 않는다.

Stem-only와 조작 범위가 맞는 R_stem은 77.68%이고 E1/M0는 74.09%라 차이는 **3.59pp·정답68개**다. Options까지 바꾸는 R_REF와의 더 큰 격차 전체를 inventory 품질 탓으로 돌리지 않는다.

## 현재 OCR 실험의 위치

진행 확인 시점: 2026-11-17T22:16:05.176809+00:00. 아래 행 수는 해당 시점의 기록이며 계속 증가한다.

| 단계 | 기록 행 | 완료 |
| --- | ---: | --- |
| ocr | 128/128 | 완료 |
| rewrite | 288/288 | 완료 |
| infer | 288/288 | 완료 |

CPU EasyOCR screenshot-only inventory → **기존 E1 출력 재사용** → 기존 M0 matching → 기존 Qwen3-VL-8B 풀이 순서다. OCR bbox/confidence는 진단에만 저장하고 LM에는 정렬된 문자열 목록만 제공한다. 최종 MCQ가 같더라도 전체 ordered batch와 실행 환경까지 맞아야 이전 풀이를 재사용한다.

부분 출력으로 accuracy나 최종 총시간을 추정하지 않는다. OCR의 완료 결과는 기존 E1/M0와 같은 main240쌍으로 accuracy·회복/회귀·언어별 효과·전체 CPU+GPU 호출 시간을 비교한다. 기존 inventory나 R 표현과의 겹침을 OCR 정답률로 부르지 않는다.

현재 E1/M0의 전체 inventory 비용은 138.64분, 전체 recipe의 약 67%다. OCR는 이 비용을 줄일 수 있는지 확인하는 실험이며, CPU OCR가 자동으로 더 빠르거나 정확하다고 가정하지 않는다.

다른 단계 비용이 그대로라면 inventory를 제외해도 기존 추출+matching+풀이에 68.62분이 남는다. 따라서 OCR 교체 하나로 TT의 32.10분까지 도달한다고 예상하지 않는다. 실제로는 OCR 목록 길이와 내용에 따라 matching 비용도 바뀌므로 종료 후 다시 측정한다.

### OCR Screen 완료 결과

**이번 표본에서는 정확도 점추정이 1문제 높고 전체 계산 비용이 약 37% 낮았다.** 정확도 우월성·비열등성이나 OCR 문자 인식 품질 자체를 검증한 것은 아니다.

| 조건 | 정답/240 | 정확도 | Inventory | 추출+matching | 최종 풀이 | 총 계산 시간 | 초/pair |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| VLM inventory · 8B | 178 | 74.17% | 29.56분 GPU | 6.37분 | 3.17분 | 39.10분 | 9.774 |
| EasyOCR inventory · CPU | 179 | 74.58% | 14.92분 CPU | 6.50분 | 3.17분 | 24.59분 | 6.146 |

OCR−VLM +0.42pp, item bootstrap 95% CI [-2.08, +3.33]pp. 회복 7 / 회귀 6 pair다. Inventory는 1.98배, 전체 recipe는 1.59배 빠르며 전체 시간은 37.1% 감소했다.

기존 전체 호출 시간은 GPU 39.10분이었다. OCR 교체 후에는 CPU OCR 14.92분 + GPU 추출/matching/풀이 9.67분이다. 이는 기록된 호출 구간 기준의 GPU 사용 시간 절감이며 전체 파이프라인이 GPU를 필요로 하지 않는다는 뜻은 아니다.

Main80개 OCR inventory가 모두 성공했다. 기존 VLM inventory는77성공·3실패였다. MCQ 수정은225→233 pair, 최종 원문 fallback은6→4 pair였다. 두 조건의 완성 MCQ가 같은178 pair에서는 최종 label 차이가0이었다. 이 값은 문자 인식 정확도나 교체 의미 정확도의 GT 검증을 대체하지 않는다.

실제 launcher wall은34.42분이며 pilot을 포함한288 pair·128이미지의 실행 시간이다. 기존 E1 추출과 풀이135행을 재사용했다. 위24.59분은 main240 pair·80이미지에 필요한 최초 호출 시간을 청구한 비교용 비용이므로 두 시간의 분모와 범위를 혼동하지 않는다.

이37%는Screen20개 semantic item에서 얻었던 값이다. 전체158문항의 결과와 구분한다. 4B inventory+4B 풀이 결과와도 downstream 모델이 달라 inventory 공급원만의 비교로 섞지 않는다.

[GUI별 수치와 원시 산출물 설명](OCR_INVENTORY_SCREEN_RESULTS_KO.md).

## 다음 판단 순서

1. OCR 전체 결과의 모델별 정확도·CPU/GPU 비용을 검토하고 전처리 공급원을 고정한다.
2. E1/M0의 남은 손실은 추출 F1뿐 아니라 이름 대응·inventory coverage·치환 후 REL 실패를 구분한다. R_stem과 scope를 맞춘 비교를 유지한다.
3. CLP를 주요 external baseline으로 해석하려면 별도 버전의 출력 종료/표기 문제를 먼저 검증한다. 현재 score는 보존한다.
4. 이 개발 결과를 검토한 뒤 확장 범위를 결정한다. 현재 결과만으로 전체366문항이나 새로운 모델 일반화가 완료됐다고 주장하지 않는다.

자세한 [TT·CLP 비용 비교](TT_PERFORMANCE_EFFICIENCY_KO.md), [외부 baseline 프로토콜](EXTERNAL_BASELINES_PROTOCOL_KO.md), [OCR 프로토콜](OCR_INVENTORY_SCREEN_PROTOCOL_KO.md), [8B 전체 결과](E1_STEM_FULL_DEV_RESULTS_KO.md), [4B 전체 결과](QWEN3_VL_4B_TRANSFER_RESULTS_KO.md).

재집계: `OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3 .venv/bin/python followup_rel_4lang/method_dev/scripts/report_current_experiments.py`

[정확한 수치·CLP 형식 진단·집계 provenance](../artifacts/current_experiment_summary_snapshot.json). 새 inference는 실행하지 않았다.
