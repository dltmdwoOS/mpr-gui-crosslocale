# 실험별 전체 처리시간과 정확도

같은 Screen **20 semantic item·240 mismatch pair** 기준이다. Inventory는 고유 screenshot80개, source extraction은 고유 MCQ80개만 계산한다. 실패·repair를 포함하고 pilot48쌍은 주 비교에서 제외했다. 추가 추론은 실행하지 않았다.

**총 처리시간 = inventory VLM + referent 추출 LM + 번역/정렬 LM + 문제 풀이 VLM.** 아래는 저장된 실제 처리 구간을 합산해 재구성한 값이다. 모델 적재·프로세스 전환·일부 CPU 검증·사전 수작업은 포함되지 않으므로, 시작부터 종료까지의 전체 wall time과 다르다. 일부 배치에 pilot이 함께 있어 VLM 시간은 문항 수 비율로 안분했다. 새로 독립 실행한 실측 wall로 오해하지 않는다.

## 현재 B200 MIG: 같은 분모 비교

| 조건 | 정답 | 정확도 | Inventory VLM·분 | LM 합계·분 | 문제 풀이 VLM·분 | 처음부터 합계·분 | Inventory 재사용·분 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| O · 원본 | 162/240 | 67.50% | 0.00 | 0.00 | 2.92 | **2.92** | 2.92 |
| T형 · gold span+Qwen3 번역 | 158/240 | 65.83% | 0.00 | 8.10 | 2.07 | **10.17** | 10.17 |
| 참조 표현 텍스트 번역 · 자동 | 159/240 | 66.25% | 0.00 | 8.91 | 2.13 | **11.04** | 11.04 |
| 전체 텍스트 번역 | 161/240 | 67.08% | 0.00 | 10.20 | 2.44 | **12.64** | 12.64 |
| Hybrid TXT | 163/240 | 67.92% | 0.00 | 14.87 | 2.12 | **16.98** | 16.98 |
| Full GUI | 170/240 | 70.83% | 29.56 | 11.35 | 2.75 | **43.66** | 14.10 |
| Stem+Options 선택적 정렬 · 분리 | 169/240 | 70.42% | 29.56 | 9.97 | 2.06 | **41.59** | 12.03 |
| Stem-only GUI · 분리 | 175/240 | 72.92% | 29.56 | 4.35 | 3.06 | **36.97** | 7.41 |
| Hybrid GUI | 178/240 | 74.17% | 29.56 | 15.70 | 2.07 | **47.33** | 17.77 |
| Oracle span GUI · 진단 | 180/240 | 75.00% | 29.56 | 9.98 | 2.03 | **41.57** | 12.01 |
| Stem 통합 GUI | 173/240 | 72.08% | 29.56 | 7.14 | 3.12 | **39.82** | 10.26 |
| Stem+Options 통합 GUI | 179/240 | 74.58% | 29.56 | 17.87 | 3.05 | **50.49** | 20.93 |

### 주요 후보의 시간 증가와 정답 차이

| 비교 | 합계 시간 차이·분 | 정답 수 차이 |
| --- | ---: | ---: |
| Stem 통합 GUI − Stem-only GUI · 분리 | +2.84 | -2 |
| Hybrid GUI − Stem-only GUI · 분리 | +10.35 | +3 |
| Stem+Options 통합 GUI − Hybrid GUI | +3.16 | +1 |
| Stem+Options 통합 GUI − Stem 통합 GUI | +10.67 | +6 |

T형은 현재 Qwen3-8B로 gold source span만 텍스트 번역한 `TS_SEL_TXT_ORACLE`이며 기존 Gemma T와 다르다. 수작업 span 준비 비용은 미측정이고 automatic 조건이 아니다. Oracle span GUI도 진단 전용이다. 자동 text-only 참조 번역은 별도 행으로 포함했다.

Inventory 재사용 열은 inventory만 준비돼 있다고 가정한다. 추출·정렬까지 모두 cache hit여서 즉시 문제 풀이만 실행했던 실제 추가 실행 시간과는 다르다. 각 방법을 단독 실행한다고 보고 cached Full 등의 원래 처리시간도 다시 비용에 넣었다.

### LM 내부 분해

| 조건 | Referent 추출·분 | 번역/정렬·분 |
| --- | ---: | ---: |
| O · 원본 | 0.00 | 0.00 |
| T형 · gold span+Qwen3 번역 | 0.00 | 8.10 |
| 참조 표현 텍스트 번역 · 자동 | 3.34 | 5.57 |
| 전체 텍스트 번역 | 0.00 | 10.20 |
| Hybrid TXT | 1.61 | 13.25 |
| Full GUI | 0.00 | 11.35 |
| Stem+Options 선택적 정렬 · 분리 | 3.34 | 6.63 |
| Stem-only GUI · 분리 | 1.61 | 2.74 |
| Hybrid GUI | 1.61 | 14.08 |
| Oracle span GUI · 진단 | 0.00 | 9.98 |
| Stem 통합 GUI | 0.00 | 7.14 |
| Stem+Options 통합 GUI | 0.00 | 17.87 |

Hybrid는 options를 얻으려고 수행한 Full 전체 호출도 포함한다. Full에서 생성했다가 버린 stem의 계산을 빼지 않았다. Stem-only 분리는 Hybrid에서 실제로 측정된 inventory·stem 추출·stem 정렬만 재구성했으며, 원래 실행 때 발생한 불필요한 options Full까지 이 방법의 필수 비용으로 부과하지 않았다.

## 과거 O/R/T/F: RTX4090 기록

| 조건 | 정답 | 정확도 | 문제 풀이 VLM·분 | 전체 전처리 포함 시간 |
| --- | ---: | ---: | ---: | --- |
| O_EXP_A | 160/240 | 66.67% | 2.54 | VLM만 수행; 적재 제외 |
| R_REF | 194/240 | 80.83% | 2.54 | 미상: 사전 제작/번역 시간 미기록 |
| T_REF | 162/240 | 67.50% | 2.54 | 미상: 사전 제작/번역 시간 미기록 |
| F_REF | 192/240 | 80.00% | 2.43 | 미상: 사전 제작/번역 시간 미기록 |

R_REF는 parallel referent, F_REF는 parallel 전체 localization을 이미 보유한 reference다. 이 입력을 얻는 annotation·병렬 데이터 제작 비용을0으로 본 것이 아니다. 현재 B200에서 R/F240쌍을 다시 푼 기록은 없어 현재 장비의 전체 시간으로 환산하지 않았다. 같은 모델·revision·system과 pair/gold를 확인했지만 장비·배치·큐가 다르므로 위 B200 행과 직접적인 속도 경쟁으로 해석하지 않는다.

기존 T_REF는 `mlx-community/gemma-3-12b-it-4bit`를 Mac에서 사용한 번역+RTX4090 VLM이다. 저장된 translation 파일에는 runtime이 없어 전체 시간을 복원할 수 없었다. 기존 T_REF와 현재 T형을 하나의 조건으로 합치지 않는다.

## 실제 새 실행에서 기록된 시간

아래는 main+pilot288쌍이며 위240쌍 표와 분모가 다르다. Inventory는 이전에 준비돼 있었다. LM의 wall은 적재를 포함하지만 VLM 쪽은 batch 구간만 기록돼 있어 합계는 **전체 실행 시간의 하한**이다.

| 실행 | LM 단계 wall·분 | VLM batch 합·분 | 기록 구간 합·분 |
| --- | ---: | ---: | ---: |
| single_pass_stem_screen_v1 | 9.91 | 3.77 | ≥13.68 |
| single_pass_all_screen_v1 | 30.08 | 3.73 | ≥33.82 |

VLM 적재·입력 검사·프로세스 시작/종료 등이 추가되므로 이 하한을 정확한 전체 wall이라고 부르지 않는다. 기존9조건의 shared pipeline wall을 각 방법에 그대로 붙이는 것도 여러 방법의 공용 처리와 불필요한 단계를 중복 청구하므로 피했다.

## 비교를 읽는 법

GUI 방법은 같은 inventory 비용 **29.56분**을 공유한다. 따라서 처음 실행할 때는 inventory가 큰 비중을 차지하고, 같은 화면의 inventory가 준비돼 있으면 방법 간 LM 차이가 더 크게 드러난다. 고유80개 화면에 한 번씩만 계산했고 문항·언어쌍240개마다 재추출한 것으로 세지 않았다.

정확도는 이미 여러 번 관찰한 개발 Screen의 점추정이다. Hybrid와 Stem+Options 통합의 정답1개 차이를 안정적인 우위로 해석하지 않는다. 처리시간 역시 서로 다른 실행 시점·출력 길이·repair·배치의 영향을 포함하며 통제된 장비 성능 벤치마크가 아니다.

## 집계 검증·재현

- 모델 호출은 cache key별 한 번만 합산하고 cache hit를0초로 처리하지 않음.
- VLM은 행별 batch 시간을 그대로 더하지 않음. 전체 batch를 먼저 확인하고 선택된 문항 몫만 안분.
- Pair ID·주 분석 분모·generation parser·기존 정답 수·frozen 코드/입력·reference model/system 검사.
- 실패·repair·rejected semantic repair를 삭제하지 않음. 준비시간 미기록은0으로 대체하지 않음.

```bash
.venv/bin/python followup_rel_4lang/method_dev/scripts/compare_end_to_end.py
```

[시간·정확도·출처 SHA-256 snapshot](../artifacts/end_to_end_cost_snapshot.json), [누적 실험 결과](TWO_STAGE_RESULTS_KO.md), [통합 조건 상세](SINGLE_PASS_ALL_GUI_KO.md).
