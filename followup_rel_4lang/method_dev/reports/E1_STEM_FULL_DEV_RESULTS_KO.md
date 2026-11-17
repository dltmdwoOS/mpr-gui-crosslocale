# 수정 추출 E1 + 기존 matcher M0: 전체 개발 집합 결과

**158개 semantic item·1,895 주 분석 pair 완료.** 전체main1,896쌍 중 기존 사전 제외1쌍을 제외했다. Screen20문항240쌍(실행288쌍·pilot48포함)은 완료 결과를 재사용했고, 남은138문항1,656쌍만 새로 실행했다. 새 실행 wall은23.36분이다.

**현재 결론:** 전체 정확도는73.98%→74.09%로 정답2개(+0.11pp) 증가에 그쳤고, 차이의 탐색95% CI[−0.47,+0.69]pp는0을 포함한다. Source 추출은 좋아졌지만 end-to-end 정확도 개선은 확인되지 않았다. 사용자가 선택한 E1 prompt는 바꾸지 않고 전체 산출물을 완성했다.

## 고정한 방법

Qwen3-VL의 기존 query-blind inventory → 고정 Qwen3-8B의 수정 stem referent 추출 E1 → 기존 GUI-conditioned 문자열 matcher M0 → source span의 결정적 치환 → Qwen3-VL MCQ 풀이. Options는 원본 그대로다. E1 prompt와 M0 prompt/model/decoding은 Screen2×2 이후 변경하지 않았다. 새 inventory 생성·M1·options 전체 번역·언어별 routing은 수행하지 않았다.

## 정확도

| 범위 | n | 기존 O | 기존 E0/M0 | 새 E1/M0 | R_stem |
| --- | ---: | ---: | ---: | ---: | ---: |
| screen | 240 | 162/240 (67.50%) | 175/240 (72.92%) | 178/240 (74.17%) | 185/240 (77.08%) |
| selection | 239 | 171/239 (71.55%) | 178/239 (74.48%) | 175/239 (73.22%) | 174/239 (72.80%) |
| internal_evaluation | 1416 | 997/1416 (70.41%) | 1049/1416 (74.08%) | 1051/1416 (74.22%) | 1113/1416 (78.60%) |
| all_158 | 1895 | 1330/1895 (70.18%) | 1402/1895 (73.98%) | 1404/1895 (74.09%) | 1472/1895 (77.68%) |

| 범위 | 새−기존 E0/M0 | 95% item bootstrap CI | 회복/회귀 |
| --- | ---: | --- | ---: |
| screen | +1.25pp | [+0.00, +2.50] | 3/0 |
| selection | -1.26pp | [-3.33, +0.00] | 0/3 |
| internal_evaluation | +0.14pp | [-0.49, +0.78] | 11/9 |
| all_158 | +0.11pp | [-0.47, +0.69] | 14/12 |

R_stem은 parallel stem 표현을 사용한 과거 reference이며 실제 screenshot exact-label oracle이 아니다. 모델/revision/system은 같으나 과거 RTX4090·batch4·혼합 조건 큐와 현재 B200·batch3의 차이가 있다. 전체158문항과 모든 부분 집합은 이미 반복 관찰한 development data다. 모든CI는 item 단위10,000회 bootstrap의 보정 전 탐색 구간이며 독립적인 confirmatory claim이 아니다.

## Source 추출과 처리 상태

| 집합 | Precision | Recall | F1 | 실제 수정 | fallback |
| --- | ---: | ---: | ---: | ---: | ---: |
| screen | 83.75% | 83.75% | 83.75% | 225 | 6 |
| selection | 92.27% | 89.96% | 91.10% | 218 | 12 |
| internal_evaluation | 94.19% | 92.80% | 93.49% | 1327 | 56 |

전체 source exact-span F1은기존87.23%→수정91.95%다. Selection에서는F1이83.68%→91.10%로 올라도 정확도는74.48%→73.22%로 낮아졌고, Internal에서는F1이88.96%→93.49%로 올라도 정확도는74.08%→74.22%였다. 추출 지표 개선을 곧바로 정렬/REL 개선으로 간주하지 않는다.

새/기존 MCQ가 완전히 같은 사례에서 label이 달라진 것은0쌍이다. 정오가 바뀐26쌍 중1쌍(Screen)은 이름 내용이 같고 따옴표만 바뀐 기존 관찰 사례다. 모든 순증가를 의미 대응 개선으로 귀속하지 않는다.


추출 점수는 GT source span을 생성 후에만 읽은 pair-weighted exact-boundary 진단이다. Target matching 품질을 직접 뜻하지 않는다. 추출/출력 실패는 사전 원문 fallback으로 평가에 포함했다.

## GUI 언어별

| 집합 | GUI | n | 기존 E0/M0 | 새 E1/M0 | O | R_stem |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| selection | EN | 60 | 80.00% | 80.00% | 83.33% | 76.67% |
| selection | ZH | 60 | 83.33% | 81.67% | 71.67% | 76.67% |
| selection | TH | 60 | 55.00% | 51.67% | 50.00% | 58.33% |
| selection | RU | 59 | 79.66% | 79.66% | 81.36% | 79.66% |
| internal_evaluation | EN | 354 | 81.92% | 81.92% | 81.92% | 84.75% |
| internal_evaluation | ZH | 354 | 77.97% | 77.68% | 76.27% | 82.77% |
| internal_evaluation | TH | 354 | 59.60% | 60.45% | 48.59% | 65.54% |
| internal_evaluation | RU | 354 | 76.84% | 76.84% | 74.86% | 81.36% |
| all_158 | EN | 474 | 81.01% | 81.22% | 81.22% | 82.91% |
| all_158 | ZH | 474 | 78.48% | 78.27% | 75.32% | 81.86% |
| all_158 | TH | 474 | 59.92% | 60.34% | 48.31% | 64.14% |
| all_158 | RU | 473 | 76.53% | 76.53% | 75.90% | 81.82% |

## 비용과 재사용

남은 두 cohort의 실제 추가 wall은23.36분이다. Screen은 재실행하지 않았고 inventory 신규 호출은0회다. 새1,656개 풀이 행 중1422개는 동일한 전체 ordered batch로 검증해 재사용하고234개만 새로 계산했다.

| 집합 | 새 추출 호출/캐시 hit | 새 matching 호출/캐시 hit | 실제 새 풀이 batch |
| --- | ---: | ---: | ---: |
| selection | 82/0 | 51/198 | 18 |
| internal_evaluation | 478/1 | 175/1293 | 60 |

| 주 분석 범위 | Inventory | E1 추출 | M0 matching | 풀이 | 처음부터 기록 구간 합 |
| --- | ---: | ---: | ---: | ---: | ---: |
| screen | 29.56분 | 1.06분 | 5.31분 | 3.17분 | 39.10분 |
| selection | 28.58분 | 2.24분 | 8.19분 | 3.26분 | 42.28분 |
| internal_evaluation | 80.50분 | 6.32분 | 24.20분 | 14.88분 | 125.89분 |

이 표는 cached 호출도 원래 runtime으로 청구한 standalone recipe 비용이다. 모델 적재·일부 CPU 작업은 제외하고 pilot 혼합 batch는 문항 수로 안분했다. 실제 새 실행 시간과 구별하며 서로 다른 시점의 cached 호출이 섞여 통제된 속도 벤치마크는 아니다.

## 보존·재현

원시와 계약은 `artifacts/e1_stem_full_dev_v1/`, Screen 원시는 기존 `artifacts/stem_refinement_2x2_screen_v1/`에 그대로 있다. source·prompt·model/config hash와 실제 cache provenance를 저장했다. 전체366문항 확장은 수행하지 않았다.

새 main MCQ 전체1,896쌍은 `artifacts/e1_stem_full_dev_v1/inputs_E1_M0_main1896.jsonl`로 모았다. 정답·GT span 없는 allowlist 입력이며 checksum·분모·cohort 원시 경로는 `full_set_manifest.json`에 있다. 이 export는pair ID순 데이터 파일이며 과거 예측의 실제 배치 구성과 구별한다.

[전체1,944행 예측 표](E1_STEM_FULL_DEV_CASES_KO.md) · [결과 snapshot](../artifacts/e1_stem_full_dev_results_snapshot.json) · [변경하지 않은 E1/M0 프롬프트](STEM_REFINEMENT_2X2_PROTOCOL_KO.md)

```bash
.venv/bin/python followup_rel_4lang/method_dev/scripts/report_e1_stem_full_dev.py
```
