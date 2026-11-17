# Stem-only GUI 2×2 실험 결과

**현재 선택은 E1_M0: 추출 수정만 유지하고 기존 matcher를 쓰는 조건이다.** Screen240쌍에서178정답으로 가장 높았다. 다만 개선3쌍 중1쌍은 이름 내용이 같고 따옴표만 달라진 사례여서, 모두 의미 대응 개선이라고 해석하지 않는다. 후보 ID matcher는 변경/구조 성공을 늘렸으나 정확도를 높이지 못했다.

## 범위와 검증

Screen main20개 semantic item×12방향=240쌍이 주 분석이다. 기존 batch 구성을 보존하기 위해 pilot48쌍을 포함한288쌍씩 네 조건을 구성했다. E0_M0는 저장된 raw 응답과 예측을 재사용했고 신규3조건만 실행했다. 전체 wall은 25.06분이다. 추가 GPU 추론 없이 완료된 자료만 분석했다.

Frozen source/data hash, 각 조건288행의 pair·이미지·정답 연결, source span 바깥과 options 불변, 두 matcher의 동일 extraction 입력, 재사용된 전체 배치의 source/prompt/output provenance를 검사했다. 독립 재계산한 정확도·paired bootstrap은 실행기 결과와 일치한다.

## 정확도와 R_stem 격차

| 조건 | 정답/240 | 정확도 | 기존 대비 | 회복/회귀 | R_stem 대비 |
| --- | ---: | ---: | ---: | ---: | ---: |
| E0_M0 · 기존 추출 + 기존 matcher | 175 | 72.92% | +0.00pp | 기준 | -4.17pp |
| E1_M0 · 수정 추출 + 기존 matcher | 178 | 74.17% | +1.25pp | 3/0 | -2.92pp |
| E0_M1 · 기존 추출 + 후보 ID matcher | 171 | 71.25% | -1.67pp | 6/10 | -5.83pp |
| E1_M1 · 수정 추출 + 후보 ID matcher | 177 | 73.75% | +0.83pp | 8/6 | -3.33pp |

같은 범위 O는162/240=67.50%, 과거 R_stem은185/240=77.08%다. R_stem−자동 방법의 정답 차이는10개에서7개로 줄었지만, 과거 reference는 RTX4090·batch4 실행이라 실행 환경이 완전히 같은 대조는 아니다.

| 대비 | 차이 | 95% item bootstrap CI |
| --- | ---: | --- |
| E1_M0 − E0_M0 | +1.25pp | [+0.00, +2.50] |
| E0_M1 − E0_M0 | -1.67pp | [-4.17, +0.83] |
| E1_M1 − E0_M0 | +0.83pp | [-1.67, +3.75] |
| extractor_main_effect | +1.88pp | [+0.42, +3.75] |
| matcher_main_effect | -1.04pp | [-3.12, +1.46] |
| interaction | +1.25pp | [-0.42, +2.92] |

Extractor 주 효과는 두 matcher에서의 수정 효과 평균이고 matcher 주 효과는 두 extractor에서의 평균이다. Interaction은(E1M1−E1M0)−(E0M1−E0M0)다. 이 factorial 대비의 recovery/regression 필드는 일반적인 정오 전환 개수로 해석하지 않는다.

10,000회 semantic-item bootstrap이며 모든 구간은 다중 비교 보정 전 탐색 구간이다. E1_M0의 구간 하한은0이다. 반복 관찰한 개발 Screen이므로 우월성·동등성·독립 일반화 검증을 주장하지 않는다. M1은 프롬프트와 출력 표현을 함께 바꿨으므로 ID 자체의 순수 효과도 아니다.

## 추출 품질과 처리 상태

| Extractor | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| E0 | 81.01% | 80.00% | 80.50% |
| E1 | 83.75% | 83.75% | 83.75% |

Source annotation은 생성 후 source 경계 진단에만 사용했다. F1은80개 고유 main source stem이 GUI3방향으로 반복되는 pair-weighted exact-span 점수다. Target 이름 대응의 정확도를 직접 뜻하지 않는다.

| 조건 | 실제 수정 | 원문 fallback | ID/비인벤토리 오류 | 원문 전체가 기존과 다른 pair |
| --- | ---: | ---: | ---: | ---: |
| E0_M0 | 219 | 12 | 9 | 0 |
| E1_M0 | 225 | 6 | 6 | 50 |
| E0_M1 | 228 | 7 | 4 | 39 |
| E1_M1 | 231 | 4 | 4 | 73 |

M1의 Unknown candidate ID4쌍은 각 조건 모두 같은4쌍이며 실제 raw는 잘못된 후보 번호가 아니라 JSON null 대신 문자열 `"null"`을 반환한 경우다. 모두 referent1개이고 최종 입력은 원문이다. 이 타입 오류만 정상 abstention으로 처리해도 이 사례들의 MCQ는 그대로이므로 정확도 개선으로 이어지지 않는다. Frozen parser와 점수는 소급 변경하지 않았다.

## E1_M0가 회복한3쌍

`rel::2/calendar_6.png::en::th`

day of the week라는 일반 표현 대신 실제 기준 이름 Thursday를 추출했다. 새 target은요일+날짜(พฤ.12) 형태라 원문의 값/표현 보존 문제는 별도 검수가 필요하다.

```text
원문: Which day of the week has a scheduled event, and what is its relative position compared to Thursday?
기존: Which วัน has a scheduled event, and what is its relative position compared to Thursday?
수정: Which day of the week has a scheduled event, and what is its relative position compared to พฤ. 12?
예측: C → B; GT B
```

`rel::4/google_play_8.jpg::ru::en`

선택한 이름 Use device location은 같다. E1이 source guillemets까지 span에 포함해 치환하면서 따옴표가 사라졌다. 형식/배치 영향 가능성이 있어 semantic alignment 개선으로 확정하지 않는다. 새 prompt는 인용부호를 제외하라고 했으므로 지시 준수도 완전하지 않다.

```text
원문: Какой параметр находится непосредственно выше опции «Использовать данные о местоположении устройства» в меню настроек?
기존: Какой параметр находится непосредственно выше опции «Use device location» в меню настроек?
수정: Какой параметр находится непосредственно выше опции Use device location в меню настроек?
예측: B → A; GT A
```

`rel::6/camera_8.jpg::th::zh`

generic mode와 인용부호까지 잡던 span을 실제 이름 รูปภาพ로 좁혔다. Target도视频(video)에서照片(photo)로 바뀌었다.

```text
원문: โหมดใดอยู่ทางซ้ายของโหมด "รูปภาพ" ในอินเทอร์เฟซผู้ใช้นี้?
기존: โหมดใดอยู่ทางซ้ายของ视频 ในอินเทอร์เฟซผู้ใช้นี้?
수정: โหมดใดอยู่ทางซ้ายของโหมด "照片" ในอินเทอร์เฟซผู้ใช้นี้?
예측: C → A; GT A
```

## 후보 ID matcher가 해결하지 못한 것

유효한 inventory ID를 고르는 것과 올바른 referent 이름을 고르는 것은 별개였다. 예를 들어 E0_M1은 toll roads를避开高速公路(highways)로, 照片(photo)를วิดีโอ(video)로, alarm ringtone을call ringtone으로 바꿔 회귀했다. 후보가 목록 안에 존재해도 source 요소의 의미를 보존했다고 볼 수 없다.

E0_M1은6쌍을 회복했지만10쌍을 잃었고, E1_M1은8쌍을 회복했지만6쌍을 잃었다. 따라서 더 많은 edit 적용이나 더 적은 fallback을 곧바로 성공으로 평가하지 않는다.

## GUI 언어별 정확도

| GUI | n | E0_M0 | E1_M0 | E0_M1 | E1_M1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| EN | 60 | 46/60 (76.67%) | 47/60 (78.33%) | 44/60 (73.33%) | 45/60 (75.00%) |
| ZH | 60 | 46/60 (76.67%) | 47/60 (78.33%) | 46/60 (76.67%) | 46/60 (76.67%) |
| TH | 60 | 40/60 (66.67%) | 41/60 (68.33%) | 38/60 (63.33%) | 39/60 (65.00%) |
| RU | 60 | 43/60 (71.67%) | 43/60 (71.67%) | 43/60 (71.67%) | 47/60 (78.33%) |

E1_M0는EN/ZH/TH에서각1쌍 순증가했고RU는같았다. E1_M1의RU 개선을 보고RU에만 새 matcher를 켜는 정책은 만들지 않았다. 언어별60쌍도20문항의 반복 관측이다.

## 계산 비용과 재사용

| 조건 | Inventory | 추출 LM | Matching LM | 풀이 VLM | 처음부터 계산 구간 |
| --- | ---: | ---: | ---: | ---: | ---: |
| E0_M0 | 29.56분 | 1.61분 | 2.74분 | 3.06분 | 36.97분 |
| E1_M0 | 29.56분 | 1.06분 | 5.31분 | 3.17분 | 39.10분 |
| E0_M1 | 29.56분 | 1.61분 | 6.66분 | 3.26분 | 41.10분 |
| E1_M1 | 29.56분 | 1.06분 | 8.54분 | 3.42분 | 42.59분 |

위 표는 main240쌍에서 해당 방법을 처음부터 수행한다고 볼 때의 기록 구간 합계다. 기존 호출도 원래 runtime을 청구하고 혼합 batch는 문항 비율로 안분했다. 모델 적재는 제외하며 cached/서로 다른 시점의 호출이 섞여 통제된 속도 벤치마크가 아니다.

이번 실제 추가 실험은25.06분이고 inventory 신규 생성은0회다. E1 추출은고유128source에129호출(구조repair1회), 새 matching 호출은396회다. 신규3조건의864개 풀이 행 중648개를 재사용하고216개(72batch)를 새로 계산했다. 기존E0_M0의288개도 전체 재사용했다.

## 다음 판단

E1_M0를 다음 후보로 고정할 근거는 있지만 최종 method로 확정할 근거는 부족하다. 다음 확인은 기존 inventory와 M0를 유지한 채 E1_M0만 Selection/Internal에 적용하는 방향이 단순하다. 단, 두 cohort도 이미 관찰했고 설계에 활용한 개발 자료이므로 독립 검증으로 부르지 않는다. M1을 더 확장하거나 언어별 분기 정책을 추가하기보다 실제 이름 대응 회복과 형식 변화 효과를 구분해야 한다. 이번에는 추가 추론이나 후속 실행을 시작하지 않았다.

[실행 전 고정 프로토콜·전체 프롬프트](STEM_REFINEMENT_2X2_PROTOCOL_KO.md) · [전체288쌍 결과와 회복/회귀 원문](STEM_REFINEMENT_2X2_CASES_KO.md) · [결과·비용·checksum snapshot](../artifacts/stem_refinement_2x2_results_snapshot.json)

```bash
.venv/bin/python followup_rel_4lang/method_dev/scripts/report_stem_refinement_2x2.py
```
