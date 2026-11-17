# 고정 두 방법의 잔여 개발 집합 실험 결과

**두 조건 모두 완료됐다.** 남은138개 semantic item·각1,656 mismatch pair를 실행했고 사전 제외1쌍을 적용한1,655쌍을 주 분석했다. 실제 전체 실행은 4.29시간(257.53분)이다.

**현재 판단:** Stem-only는 Selection74.48%, Internal74.08%로 직접 rewrite보다 두 집합 모두 높은 점추정을 보였다. Internal의 O 대비 차이는+3.67pp이고 탐색95% CI는[+1.20,+6.07]pp다. 그러나 두 자동 방법 간 차이의 CI는0을 조금 포함하므로 Stem-only의 우월성이나 직접 rewrite의 동등성을 확정하지 않는다. 직접 rewrite의 계산 구간 비용은 Stem-only보다 약47% 적어 비용 비교 후보로 의미가 있다.

## 무엇을 비교했는가

**이미지 직접 rewrite:** Qwen3-VL-8B가 screenshot과 원본 stem/A-D를 보고 GUI 이름만 바꾼 완성형 MCQ를 반환한다. 원문 복사를 강조한 프롬프트를 Screen 이후 고정했다. Inventory·별도 extractor·LM은 없으며 수정된 MCQ를 같은 VLM으로 푼다.

**Stem-only GUI:** 같은 VLM이 screenshot만 보고 문자열 inventory를 만든다. 고정 Qwen3-8B LM이 원본 stem의 referent를 추출하고, 원본 MCQ 전체와 referent·inventory를 보고 교체 이름을 선택한다. 코드가 stem만 치환하고 options는 원문 그대로 둔다. 마지막에 같은 VLM이 푼다. 불필요한 options 전체 번역은 수행하지 않았다.

두 조건은 같은 pair·이미지·정답·보기 순서를 사용했다. 다만 변환 모델·이미지 접근·option 처리 범위도 달라 inventory 하나의 순수 인과 효과를 비교하는 실험은 아니다.

## 같은 범위 정확도

| 조건 | Selection · 239쌍 | Internal · 1,416쌍 | 잔여 합계 · 1,655쌍 |
| --- | ---: | ---: | ---: |
| O · 기존 B200 | 171/239 (71.55%) | 997/1416 (70.41%) | 1168/1655 (70.57%) |
| O · ExpA | 169/239 (70.71%) | 993/1416 (70.13%) | 1162/1655 (70.21%) |
| T_REF | 169/239 (70.71%) | 1004/1416 (70.90%) | 1173/1655 (70.88%) |
| R_stem · 범위 일치 reference | 174/239 (72.80%) | 1113/1416 (78.60%) | 1287/1655 (77.76%) |
| R_REF | 196/239 (82.01%) | 1201/1416 (84.82%) | 1397/1655 (84.41%) |
| F_REF | 197/239 (82.43%) | 1162/1416 (82.06%) | 1359/1655 (82.11%) |
| 이미지 직접 rewrite | 173/239 (72.38%) | 1016/1416 (71.75%) | 1189/1655 (71.84%) |
| Stem-only GUI | 178/239 (74.48%) | 1049/1416 (74.08%) | 1227/1655 (74.14%) |

O_B200는 같은 모델·revision·system·batch3·원본 입력 hash의 이전 B200 실행을 재사용했다. O/T/R/F는 새로 추론하지 않았다. T_REF는 gold source span+Gemma 번역, R_REF는 gold span+parallel 표현, F_REF는 전체 parallel localization이다. R은 실제 화면 exact-label oracle이 아니다. ExpA/ORCF reference는 RTX4090 실행이며 F는 batch4라 실행 조건이 완전히 같은 대조는 아니다.

**Stem-only에 범위를 맞춘 기준은 R_stem이다.** Stem만 parallel 표현으로 정렬하고 options는 원문으로 남긴 입력을1,656쌍 전수 검증했다. R_stem의 과거 batch4·RTX4090·혼합 조건 큐는 현재 batch3·B200·조건별 큐와 다르다. 전체 R과의 격차에는 options 정렬 유무도 포함되므로 그 전부를 자동 stem matching의 실패로 해석하지 않는다.

## Paired 차이와 불확실성

| 집합 | 비교 | 차이 | 95% item bootstrap CI | 회복/회귀 |
| --- | --- | ---: | --- | ---: |
| selection | Stem-only − 직접 rewrite | +2.09pp | [-3.75, +9.21] | 16/11 |
| selection | 이미지 직접 rewrite − O · 기존 B200 | +0.84pp | [-2.09, +4.17] | 10/8 |
| selection | 이미지 직접 rewrite − R_REF | -9.62pp | [-19.17, -0.83] | 13/36 |
| selection | Stem-only GUI − O · 기존 B200 | +2.93pp | [-2.10, +9.21] | 17/10 |
| selection | Stem-only GUI − R_REF | -7.53pp | [-19.17, +4.64] | 22/40 |
| selection | Stem-only GUI − R_stem | +1.67pp | [-2.94, +8.79] | 9/5 |
| internal_evaluation | Stem-only − 직접 rewrite | +2.33pp | [-0.14, +4.80] | 129/96 |
| internal_evaluation | 이미지 직접 rewrite − O · 기존 B200 | +1.34pp | [-0.85, +3.60] | 90/71 |
| internal_evaluation | 이미지 직접 rewrite − R_REF | -13.06pp | [-15.96, -10.17] | 41/226 |
| internal_evaluation | Stem-only GUI − O · 기존 B200 | +3.67pp | [+1.20, +6.07] | 122/70 |
| internal_evaluation | Stem-only GUI − R_REF | -10.73pp | [-14.12, -7.34] | 55/207 |
| internal_evaluation | Stem-only GUI − R_stem | -4.52pp | [-6.29, -2.82] | 17/81 |
| remaining_all | Stem-only − 직접 rewrite | +2.30pp | [-0.06, +4.65] | 145/107 |
| remaining_all | 이미지 직접 rewrite − O · 기존 B200 | +1.27pp | [-0.67, +3.20] | 100/79 |
| remaining_all | 이미지 직접 rewrite − R_REF | -12.57pp | [-15.41, -9.79] | 54/262 |
| remaining_all | Stem-only GUI − O · 기존 B200 | +3.56pp | [+1.33, +5.80] | 139/80 |
| remaining_all | Stem-only GUI − R_REF | -10.27pp | [-13.72, -6.89] | 77/247 |
| remaining_all | Stem-only GUI − R_stem | -3.63pp | [-5.38, -1.81] | 26/86 |

같은 semantic item의 언어쌍을 묶어10,000회 bootstrap했다. 다중 비교 보정 전 탐색 구간이며 bootstrap은 실행 환경 차이와 반복 개발에 따른 선택 편향을 보정하지 않는다. 158문항 전체가 역사적으로 관찰된 development set이고 Internal도 이전 탐색에서 본 집합이다. 독립 최종 검증으로 기술하지 않는다.

## 실제 비용

| 집합 | 조건 | Inventory VLM | 추출 LM | 정렬 LM / 직접 rewrite VLM | 풀이 VLM | 계산 구간 합계 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| selection | 이미지 직접 rewrite | 0.00분 | 0.00분 | 11.64분 | 3.32분 | 14.97분 |
| selection | Stem-only GUI | 28.58분 | 1.59분 | 7.50분 | 3.13분 | 40.81분 |
| internal_evaluation | 이미지 직접 rewrite | 0.00분 | 0.00분 | 57.86분 | 14.55분 | 72.42분 |
| internal_evaluation | Stem-only GUI | 80.50분 | 6.17분 | 21.88분 | 14.21분 | 122.76분 |

비용은 실제 실행 분모240+1,416쌍이다(Selection 사전 제외1쌍 비용도 포함). 계산 구간 합계는 모델 적재를 제외한 호출 시간이며 cached 배치도 원래 시간을 청구해 단독 recipe 비용을 재구성했다. 전체 wall에는 두 조건·모델 적재·worker 시작/종료 등이 포함된다. Raw cost와 snapshot에는 실제 새 계산 및 stage wall을 별도 보존했다.

예상6.44–7.00시간보다 짧게 끝난 주된 이유는 남은 화면들의 inventory 생성이 Screen보다 빨랐기 때문이다. Internal inventory는472개 이미지에 실제 호출80.50분(이미지당 약10.23초)이었고, Screen 기준은80개에29.56분(약22.17초)이었다. 따라서 이번 시간 차이를 새 최적화나 장비 변경의 효과로 해석하지 않는다.

- 이미지 직접 rewrite: 계산 구간87.38분, 실제 새 계산87.38분, stage wall합89.47분.
- Stem-only GUI: 계산 구간163.56분, 실제 새 계산163.31분, stage wall합167.34분.

풀이 재사용은 24쌍이다. 이미지·프롬프트·순서·설정·환경이 같은 전체 배치만 재사용했다.

## 처리 품질과 남은 실패

| 집합 | 방법 | 변경 | 원문 유지 | fallback | 문맥 경고 | 숫자 변화 | 새 보기 중복 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| selection | 이미지 직접 rewrite | 159/239 | 80 | 1 | 21 | 6 | 0 |
| selection | Stem-only GUI | 213/239 | 26 | 17 | 21 | 0 | 0 |
| internal_evaluation | 이미지 직접 rewrite | 1001/1416 | 415 | 6 | 126 | 21 | 10 |
| internal_evaluation | Stem-only GUI | 1303/1416 | 113 | 86 | 89 | 3 | 0 |

문맥 경고는 생성 후 source annotation 바깥 문자 보존을 검사한 값이며 의미 오류율이 아니다. GT source span은 사후 진단에만 사용했다. Stem-only는 코드로 자동 추출 span 바깥을 보존하더라도 추출 span이 annotation과 다르면 이 검사에서 경고될 수 있다. 올바른 화면 요소를 골랐는지는 별도 문제다.

| 집합 | Inventory 실패 / 이미지 | Stem 추출 실패 / 고유 stem | 추출 precision / recall / F1 |
| --- | ---: | ---: | --- |
| selection | 3/80 | 0/80 | 83.68% / 83.68% / 83.68% |
| internal_evaluation | 7/472 | 3/472 | 89.15% / 88.77% / 88.96% |

Stem-only fallback103쌍 중93쌍은 최종 LM 출력이 inventory의 verbatim member가 아니어서 거절됐고,9쌍은 source 추출 실패,1쌍은 JSON parsing 실패였다. 이93쌍을 모두 잘못된 의미 대응이라고 판정한 것은 아니다. 단순 표기 차이인지, 없는 이름을 만든 것인지, inventory 누락인지 분해해야 한다.

### R_stem은 맞고 Stem-only는 틀린 사례

아래는 우선순위를 둔 관찰 상태 분류이며 단독 오답 원인 판정이 아니다. Source 경계·R target의 inventory 포함 여부도 별도로 저장했다. Parallel reference의 exact 부재는 OCR 누락과 같은 뜻이 아니다.

| 집합 | R_stem 정답·Stem-only 오답 | 관찰 상태 | 건수 |
| --- | ---: | --- | ---: |
| selection | 5 | 치환 후에도 오답 | 5 |
| internal_evaluation | 81 | 치환 후에도 오답 | 65 |
| internal_evaluation | 81 | 유효 처리·원문 유지 | 2 |
| internal_evaluation | 81 | 교체 출력 검증 실패 | 12 |
| internal_evaluation | 81 | inventory 생성 실패 | 2 |

Internal의81쌍 중67쌍은 source stem annotation 경계를 모두 정확히 포함했고,57쌍은 R target 표현이 이미 inventory에 exact로 있었다. 따라서 이 격차를 전부 추출 recall 또는 OCR 실패로 설명할 수 없다. 20쌍의 lexical 미발견은 실제 화면에서의 부재·누락·reference 표현 차이를 수작업으로 나누기 전까지 OCR 오류로 확정하지 않는다.

| 집합 | 전체 중 R_stem 입력과 완전히 동일 | R_stem 정답·Stem-only 오답 중 입력도 동일 |
| --- | ---: | ---: |
| selection | 146 | 0 |
| internal_evaluation | 992 | 5 |

입력까지 같은데 정오가 다른 사례는 matching 오류로 귀속하지 않는다. 과거·현재의 batch/device/queue 차이도 결과 차이에 기여할 수 있음을 보여준다. 새 inference 없이 기존 원시 문자열과 예측을 대조한 것이다.


추출 수치는 source stem exact-boundary 진단이다. 동일 source가 GUI 언어별로 반복되는 pair-weighted 값이며, 검증 실패는 예측 span 없음으로 포함한다. Target matching 정답률로 해석하지 않는다.

## GUI 언어별 결과

| 집합 | GUI | N | O_B200 | 직접 rewrite | Stem-only | R_REF |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| selection | EN | 60 | 83.33% | 83.33% | 80.00% | 90.00% |
| selection | ZH | 60 | 71.67% | 76.67% | 83.33% | 78.33% |
| selection | TH | 60 | 50.00% | 50.00% | 55.00% | 78.33% |
| selection | RU | 59 | 81.36% | 79.66% | 79.66% | 81.36% |
| internal_evaluation | EN | 354 | 81.92% | 81.36% | 81.92% | 87.85% |
| internal_evaluation | ZH | 354 | 76.27% | 76.27% | 77.97% | 82.77% |
| internal_evaluation | TH | 354 | 48.59% | 52.54% | 59.60% | 83.62% |
| internal_evaluation | RU | 354 | 74.86% | 76.84% | 76.84% | 85.03% |

Internal에서 Stem-only의 순증가52개 중39개가 태국어 GUI에서 나왔다. EN은 O와 같고, ZH는6개, RU는7개 순증가했다. 개선이 모든 언어에 동일하게 나타났다고 볼 수 없다.

언어별 표는 기술적 분해이며 작은 subset의 결과를 보고 언어별 on/off 정책을 새로 만들지 않았다. Source 언어별·language-pair별 및 모든 reference 대비 paired 값은 snapshot/전체 예측 표에 보존한다.

## 다음 판단

1. **Stem-only를 현재 주력 후보로 유지한다.** 전체 R과의 격차보다 범위를 맞춘 R_stem 대비 Internal−4.52pp를 우선 본다. Options 전체 번역이나 다른 architecture를 바로 추가할 필요는 없다.
2. **출력 거절과 잘못된 대응을 나눈다.** 93개의 non-member fallback 원시 응답과 R_stem 정답·Stem-only 오답81쌍을 우선 검토한다. 이미 inventory에 있는 이름을 놓치는지, source span이 틀렸는지부터 구분한다.
3. **Inventory 성공률을 lexical 정확도로 오해하지 않는다.** 생성 실패는10/552이미지로 적지만 필요한 label의 coverage는 별개다. 추출 F1이 Internal88.96%인 상황에서 새 NER 모델이나 OCR 모델을 먼저 추가할 근거는 충분하지 않다.
4. **직접 rewrite는 낮은 비용의 비교 후보로 남긴다.** 원문 유지와 잘못된 이름 대응, 문맥/숫자 변화, 보기 중복이 남아 있어 현재 성능을 robust selective alignment의 완성으로 보고하지 않는다.

## 설정·보존

평가 및 직접 변환 VLM: Qwen3-VL-8B-Instruct revision `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`. LM: Qwen3-8B revision `47719a242beab8f9aecc40ce3928b034dd5dd559`. BF16·SDPA·seed42·2MP·channels_last_3d, 변환batch1/풀이batch3. 실제 프롬프트와 생성 설정은 calls.json 및 상위 contract.json에 보존했다. 원문 복사 강화 프롬프트는 [Screen 보고서](SOURCE_COPY_REWRITE_RESULTS_KO.md), Stem-only는 [기존 프로토콜](TWO_STAGE_V2_PROTOCOL_KO.md)을 따른다.

Raw는 `artifacts/overnight_two_v1/`에 유지한다. 기존 실행기·원시 출력·자동 보고서를 바꾸지 않고 사후 보고서와 checksum snapshot을 분리했다. 추가 GPU 추론은 수행하지 않았다.

```bash
.venv/bin/python followup_rel_4lang/method_dev/scripts/report_overnight_two.py
```

[전체1,656쌍 예측 표](OVERNIGHT_TWO_CASES_KO.md) · [결과·비용·출처 checksum snapshot](../artifacts/overnight_two_results_snapshot.json)
