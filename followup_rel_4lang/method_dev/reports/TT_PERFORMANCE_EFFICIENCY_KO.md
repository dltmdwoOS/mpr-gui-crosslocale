# TT·CLP 완료: 성능과 전체 추론 비용 비교

Qwen3-VL-8B, B200 MIG 45GB의 기존 측정치를 재집계했다. 추가 GPU 추론은 실행하지 않았다. 주 분석은 동일한 158개 main semantic item·1,895 mismatch pair다. Pilot 48쌍과 기존 사전 제외 1쌍을 제외했다.

## 비교 방법

- **O:** 원본 MCQ와 screenshot으로 바로 풀이.
- **TT:** 고정 Qwen3-8B LM으로 stem과 A–D 전체를 영어로 번역한 뒤 원래 screenshot으로 풀이. EN source는 그대로 사용한다. Inventory를 사용하지 않는다.
- **CLP:** 같은 고정 LM이 원본 MCQ를 영어로 단계별 이해하고, 이 응답을 assistant 대화로 유지한 채 VLM이 screenshot으로 단계별 풀이한다. Inventory는 없다. LM·VLM 모두 최대 512 tokens이며 마지막 `Answer: A–D`로 채점한다.
- **이미지 직접 rewrite · 원문 복사 강화:** Qwen3-VL-8B가 screenshot과 원본 MCQ를 보고 GUI referent만 바꾸도록 지시받아 완성된 stem/A–D를 출력한다. 같은 VLM이 이를 푼다. Inventory·별도 extractor·고정 LM이 없다. Screen에서 원문 복사를 강조하는 프롬프트로 수정한 뒤 Selection/Internal에는 이를 고정했다.
- **Stem-only GUI · E1/M0:** VLM inventory → 수정 E1 프롬프트로 LM stem referent 추출 → LM GUI-conditioned 교체 표현 선택 → 코드의 stem 치환 → VLM 풀이. Options는 원문 유지.

최종 풀이의 checkpoint revision, BF16·SDPA·2MP, batch 3은 같다. CLP 이외에는 greedy label-only 최대 2 tokens, CLP는 별도 대화/system prompt와 최대 512 tokens를 사용한다. 전처리의 입력과 출력 예산도 방법별로 다르다. TT·CLP는 원 논문의 API 모델을 로컬 Qwen3로 이식한 GUI adaptation이며 원 논문 수치 재현이 아니다.

## 전체 158문항: 번역/편집부터 최종 풀이까지

| 방법 | 정답/1,895 | 정확도 | O 대비 | 전처리 | 최종 VLM 풀이 | 합계 | 초/pair |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| O · 원본 | 1,330 | 70.18% | — | 0.00분 | 17.63분 | 17.63분 | 0.558 |
| TT · 전체 영어 번역 | 1,348 | 71.13% | +0.95pp | 15.33분 | 16.77분 | 32.10분 | 1.016 |
| CLP · 영어 이해 후 단계별 풀이 | 1,250 | 65.96% | -4.22pp | 113.96분 | 156.18분 | 270.14분 | 8.553 |
| 이미지 직접 rewrite · 원문 복사 강화 | 1,359 | 71.72% | +1.53pp | 78.21분 | 20.86분 | 99.07분 | 3.137 |
| Stem-only GUI · E1/M0 | 1,404 | 74.09% | +3.91pp | 185.96분 | 21.31분 | 207.26분 | 6.562 |

전처리에는 inventory, LM 추출·번역·matching 또는 VLM rewrite 중 해당 방법에 필요한 모든 호출과 repair를 포함한다. 공유 전처리는 전체 cohort에서 cache key당 한 번만 계산했다. 캐시로 재사용한 호출도 최초의 측정 시간을 청구하므로 재실행 시 추가 비용과 구분한다.

**합계는 기록된 계산 구간의 합이며 작업 시작부터 종료까지의 실제 wall time이 아니다.** 모델 적재, 프로세스 기동, CPU 검증·I/O·대기 시간은 제외한다. 배치 시간은 중복 합산하지 않고 실제 batch size로 나눠 선택된 pair에 배분했다. 초/pair는 처리량 기준의 상각 시간이며 단일 요청 latency가 아니다. 158 semantic item 각각에 여러 source/GUI 조합이 있어 분모는 158이 아닌 1,895 pair다.

TT의 전체 영어 번역은 GUI 언어와 무관하므로 632개 고유 source MCQ 중 비영어 474개만 번역해 3개 GUI에 공유하고 영어 158개는 identity 처리한다. 이는 전체 언어쌍을 처리하는 이번 workload에서의 실질적인 비용 이점이다.

### 전처리 시간 분해

| 방법 | VLM inventory | LM 추출 | LM 번역/matching | LM 영어 이해 | VLM rewrite |
| --- | ---: | ---: | ---: | ---: | ---: |
| O · 원본 | 0.00분 | 0.00분 | 0.00분 | 0.00분 | 0.00분 |
| TT · 전체 영어 번역 | 0.00분 | 0.00분 | 15.33분 | 0.00분 | 0.00분 |
| CLP · 영어 이해 후 단계별 풀이 | 0.00분 | 0.00분 | 0.00분 | 113.96분 | 0.00분 |
| 이미지 직접 rewrite · 원문 복사 강화 | 0.00분 | 0.00분 | 0.00분 | 0.00분 | 78.21분 |
| Stem-only GUI · E1/M0 | 138.64분 | 9.61분 | 37.70분 | 0.00분 | 0.00분 |

## 범위를 맞춘 집합별 결과

| 집합 | semantic item | pair | O | TT | CLP | 이미지 직접 rewrite | E1/M0 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| screen | 20 | 240 | 162/240 (67.50%) | 171/240 (71.25%) | 166/240 (69.17%) | 170/240 (70.83%) | 178/240 (74.17%) |
| selection | 20 | 239 | 171/239 (71.55%) | 170/239 (71.13%) | 147/239 (61.51%) | 173/239 (72.38%) | 175/239 (73.22%) |
| internal_evaluation | 118 | 1416 | 997/1416 (70.41%) | 1007/1416 (71.12%) | 937/1416 (66.17%) | 1016/1416 (71.75%) | 1051/1416 (74.22%) |

| 집합 | 방법 | 전체 계산 시간 | 초/pair |
| --- | --- | ---: | ---: |
| screen | O · 원본 | 2.92분 | 0.730 |
| screen | TT · 전체 영어 번역 | 5.09분 | 1.272 |
| screen | CLP · 영어 이해 후 단계별 풀이 | 45.41분 | 11.353 |
| screen | 이미지 직접 rewrite · 원문 복사 강화 | 11.75분 | 2.937 |
| screen | Stem-only GUI · E1/M0 | 39.10분 | 9.774 |
| selection | O · 원본 | 2.59분 | 0.650 |
| selection | TT · 전체 영어 번역 | 4.26분 | 1.070 |
| selection | CLP · 영어 이해 후 단계별 풀이 | 37.02분 | 9.295 |
| selection | 이미지 직접 rewrite · 원문 복사 강화 | 14.91분 | 3.743 |
| selection | Stem-only GUI · E1/M0 | 42.28분 | 10.615 |
| internal_evaluation | O · 원본 | 12.12분 | 0.514 |
| internal_evaluation | TT · 전체 영어 번역 | 22.75분 | 0.964 |
| internal_evaluation | CLP · 영어 이해 후 단계별 풀이 | 187.70분 | 7.953 |
| internal_evaluation | 이미지 직접 rewrite · 원문 복사 강화 | 72.42분 | 3.069 |
| internal_evaluation | Stem-only GUI · E1/M0 | 125.89분 | 5.334 |

전체 비용 표는 cohort 사이의 동일 전처리 호출도 제거한다. 따라서 위 집합별 비용의 단순 합계와 소폭 다를 수 있다. Selection 비용과 정확도는 사전 제외를 반영한 동일한 239 pair로 다시 계산했다.

## 이전 방법까지 같은 Screen 범위로 비교하면

다음은 20개 semantic item·240 pair만의 비교다. 전체 158문항 표와 분모를 섞지 않는다. 모든 inventory 기반 방법에는 inventory 추출 비용을 포함했다.

| 방법 | 정확도 | 전처리 | 최종 VLM 풀이 | 합계 | 초/pair |
| --- | ---: | ---: | ---: | ---: | ---: |
| O · 원본 | 67.50% | 0.00분 | 2.92분 | 2.92분 | 0.730 |
| TT · 전체 영어 번역 | 71.25% | 2.38분 | 2.71분 | 5.09분 | 1.272 |
| CLP · 영어 이해 후 단계별 풀이 | 69.17% | 16.74분 | 28.67분 | 45.41분 | 11.353 |
| 이미지 직접 rewrite · 원문 복사 강화 | 70.83% | 8.76분 | 2.99분 | 11.75분 | 2.937 |
| Stem-only GUI · E1/M0 | 74.17% | 35.93분 | 3.17분 | 39.10분 | 9.774 |
| 전체 텍스트 번역 | 67.08% | 10.20분 | 2.44분 | 12.64분 | 3.161 |
| Full GUI | 70.83% | 40.91분 | 2.75분 | 43.66분 | 10.915 |
| Hybrid GUI | 74.17% | 45.26분 | 2.07분 | 47.33분 | 11.832 |
| Stem 통합 GUI | 72.08% | 36.70분 | 3.12분 | 39.82분 | 9.954 |
| Stem+Options 통합 GUI | 74.58% | 47.43분 | 3.05분 | 50.49분 | 12.621 |
| Screenshot 직접 rewrite · 문맥 보존 별도 진단 | 71.25% | 9.56분 | 3.18분 | 12.74분 | 3.185 |

Hybrid는 stem을 선택적으로 바꾸고 options를 전체 번역한다. `통합 GUI`는 inventory를 LM에게 제공한 뒤 추출과 교체를 한 호출로 합친 조건이다. `전체 텍스트 번역`은 GUI 언어로 번역하므로 영어 고정 TT와 다르다. Hybrid와 E1/M0의 Screen 정확도는 모두 74.17%지만 prompt·조작 범위·정답 사례가 같은 방법이라는 뜻은 아니다.

## 같은 pair의 회복·회귀와 불확실성

| 전체 158문항 비교 | 차이 | 95% item bootstrap CI | 회복 | 회귀 |
| --- | ---: | --- | ---: | ---: |
| TT · 전체 영어 번역 − O · 원본 | +0.95pp | [-1.53, +3.38]pp | 157 | 139 |
| CLP · 영어 이해 후 단계별 풀이 − O · 원본 | -4.22pp | [-8.13, -0.42]pp | 237 | 317 |
| 이미지 직접 rewrite · 원문 복사 강화 − O · 원본 | +1.53pp | [-0.21, +3.27]pp | 115 | 86 |
| Stem-only GUI · E1/M0 − O · 원본 | +3.91pp | [+1.69, +6.18]pp | 168 | 94 |
| 이미지 직접 rewrite · 원문 복사 강화 − TT · 전체 영어 번역 | +0.58pp | [-2.27, +3.38]pp | 192 | 181 |
| Stem-only GUI · E1/M0 − TT · 전체 영어 번역 | +2.96pp | [+0.00, +6.07]pp | 221 | 165 |
| Stem-only GUI · E1/M0 − CLP · 영어 이해 후 단계별 풀이 | +8.13pp | [+4.32, +12.09]pp | 361 | 207 |
| Stem-only GUI · E1/M0 − 이미지 직접 rewrite · 원문 복사 강화 | +2.37pp | [+0.16, +4.69]pp | 170 | 125 |

TT는 O보다 정답이 18개 늘었지만 신뢰구간은 0을 포함한다. 이미지 직접 rewrite는 TT보다 점추정이 높고 계산 시간은 약 3.09배다. E1/M0는 TT보다 정답이 56개 많고 계산 시간은 약 6.46배다. 비용 대비 선호는 정확도와 자원 제약에 따라 달라진다.

CI는 semantic item 단위 10,000회 bootstrap이다. Screen에서 수정한 prompt를 포함하고 과거에 이미 관찰한 개발 집합이므로 독립적인 최종 일반화 검증이나 확정적 우월성 주장으로 해석하지 않는다. 여러 탐색 비교의 다중 검정 보정은 하지 않았다.

## GUI 언어별 전체 결과

| GUI | pair | O | TT | CLP | 이미지 직접 rewrite | E1/M0 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| EN | 474 | 81.22% | 77.00% | 77.22% | 80.80% | 81.22% |
| ZH | 474 | 75.32% | 77.64% | 67.51% | 76.16% | 78.27% |
| TH | 474 | 48.31% | 50.63% | 53.38% | 52.74% | 60.34% |
| RU | 473 | 75.90% | 79.28% | 65.75% | 77.17% | 76.53% |

TT는 영어 GUI에서도 영어 source로 바꾸지만 원본 GUI의 문자열을 별도로 확인해 정렬하지 않는다. GUI별 차이는 번역과 referent 대응, 최종 풀이가 섞인 관찰 결과이며 언어별 정책을 소급 선택하지 않았다.

## Inventory 없이 했던 이전 실험을 구분하면

사용자가 언급한 조건은 **이미지 직접 rewrite** 계열이다. 이번 전체 비교에는 원문 복사를 강조한 수정 버전을 넣었다. 그 이전 프롬프트는 Screen 240쌍에서 171정답·71.25%, VLM 편집+풀이 12.74분·3.185초/pair였다. 수정 버전은 같은 Screen에서 170정답·70.83%, 11.75분·2.937초/pair였고 이후 Selection/Internal까지 실행됐다. 초기 버전의 71.25%를 수정 버전의 전체 결과와 섞지 않았다.

직접 rewrite는 출력된 문장이 문법·JSON 검증을 통과해도 non-referent context나 숫자가 바뀔 수 있다. 원문 복사 강화 버전에도 이런 경고가 남아 있어, 정확도를 strict selective alignment 성공률로 읽으면 안 된다. 기존 `Stem 통합`·`Stem+Options 통합` LM 실험은 inventory를 제공했으므로 inventory-free 조건과 구분한다.

## TT·CLP 처리 확인

TT는 세 집합 모두 완료 marker와 raw prediction을 확인했다. Primary pair에서 fallback 0, 잘못된 최종 label 0, 번역 출력 길이 제한 도달 0이었다. 숫자 변화 경고는 Screen 0, Selection 3, Internal 6 pair다. 경고는 UI 값 차이 등을 포함할 수 있어 자동 의미 오류 판정으로 취급하지 않는다. [검토 후보 전체](EXTERNAL_BASELINES_TRANSLATION_AUDIT_KO.md)에 원문과 번역이 있다.

CLP도 세 집합 모두 완료됐다. CLP는 최종 label 파싱 실패와 출력 길이 제한 도달이 많아, 낮은 accuracy를 cross-lingual 이해 능력만의 차이로 해석하지 않는다. [현재 실험 종합과 CLP 출력 진단](CURRENT_EXPERIMENT_SUMMARY_KO.md)에 해당 건수를 구분했다. R/T/F reference는 병렬·수작업 준비 시간이나 과거 Gemma 번역 시간이 기록되지 않았고 RTX 4090 실행도 섞여 있어 현재 B200에서 전처리부터 잰 자동 방법의 총시간과 직접 등치하지 않았다. [기존 Screen 범위 reference/시간 비교](END_TO_END_COST_KO.md)를 함께 참고할 수 있다.

재집계: `OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3 .venv/bin/python followup_rel_4lang/method_dev/scripts/compare_tt_efficiency.py`

[집계와 사용 파일 SHA-256](../artifacts/tt_efficiency_comparison_snapshot.json) · [TT/CLP 고정 프로토콜](EXTERNAL_BASELINES_PROTOCOL_KO.md) · [TT 원시 결과 manifest](../artifacts/external_baselines_archive_manifest.json)
