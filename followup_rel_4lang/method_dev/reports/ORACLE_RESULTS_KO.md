> **프로토콜 변경 — 2026-11-16:** 사용자 결정에 따라 이 문서의 기존 inventory 기반 결과는 의도한 two-stage 방법의 유효한 평가에서 제외하고 이력으로 보존합니다. 새 실행 기준은 [TWO_STAGE_V2_PROTOCOL_KO.md](TWO_STAGE_V2_PROTOCOL_KO.md)입니다. 과거 수치가 새 방법의 결과를 뜻하지 않습니다.

# Qwen3 Oracle source-span 진단 결과

**추출을 annotation으로 교정하면 기존 GUI_EXACT보다 개선되지만, 이것만으로 R의 효과를 재현하지는 못했다.** Internal 1,416쌍에서 69.56% → 71.54%(+1.98pp)였다. 원본 O 대비 +1.13pp의 95% CI는 0을 포함한다. 큰 시스템을 추가하기 전에 번역→화면 표현 대응의 coverage와 편집 후 회귀를 확인하는 것이 다음 과제다.

집계 시각: 2026-11-16T06:09:29.150263+00:00. 실제 GPU 실행 3 cohort 모두 완료, 총 1,944쌍. 아래 accuracy는 pilot 48쌍과 사전 제외 1쌍을 뺀 main 1,895쌍만 사용한다. 기존 예측과 hash·pair ID·span·inventory·deterministic edit를 재검증했고 저장된 정확도와 bootstrap CI를 독립 재계산해 일치시켰다. 추가 추론은 하지 않았다.

## 1. 무엇을 바꾼 실험인가

기존 Automatic GUI_EXACT는 자동 추출한 referent를 Qwen3-8B로 번역하고, Qwen3-VL이 전사한 GUI inventory와 정규화 exact match하는 표현만 교체했다. Oracle은 **자동 추출 결과 대신 annotation의 source span**을 사용한다. 번역 모델·프롬프트·ID 규칙·inventory·matching·fallback·downstream Qwen3-VL 설정은 유지했다. Inventory의 기존 실패도 재생성하지 않았다.

Gold target 표현·R 질문·정답·bbox를 번역/편집 모델에 주지 않았다. O와 Automatic은 완료된 기존 예측을 재사용했고 Oracle 질문만 새로 풀었다. 따라서 이 실험은 **oracle_span 진단**이며 automatic method 성능이 아니다. 참조 집합이 바뀌면 공동 번역 payload와 번역 응답도 달라지므로, 추출 recall만의 순수 효과나 엄밀한 정확도 상한으로 해석하지 않는다.

T_REF는 annotation span + 기존 Gemma 번역, R_REF는 parallel referent alignment, F_REF는 parallel 전체 localization이다. 같은 pair로 맞췄지만 기존 ExpA는 RTX4090·batch3, ORCF는 RTX4090·batch4, 이번 Automatic/Oracle은 B200 MIG·batch3으로 GPU와 queue가 다르다. F_REF와 자동 GUI_FULL은 다른 조건이다.

## 2. 전체 결과

| 집합 | 주 분석 N | O | Automatic | Oracle | T_REF | R_REF | F_REF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| screen | 240 | 67.50% | 67.08% | 67.50% | 67.50% | 80.83% | 80.00% |
| selection | 239 | 71.55% | 72.38% | 72.80% | 70.71% | 82.01% | 82.43% |
| internal_evaluation | 1416 | 70.41% | 69.56% | 71.54% | 70.90% | 84.82% | 82.06% |
| main 전체·기술 통계 | 1895 | 70.18% | 69.60% | 71.19% | 70.45% | 83.96% | 81.85% |

Screen과 selection은 calibration에 속하며, internal과 구분한다. 전체 합계는 개발 표본의 기술 통계다. 이 158개 item은 이전 실험에서도 관찰됐으므로 독립적인 최종 일반화 평가로 취급하지 않는다.

| 집합 | Oracle − Automatic | 95% CI | 회복 | 회귀 | Oracle − O | 95% CI |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| screen | +0.42pp | [-0.83, +2.08] | 3 | 2 | +0.00pp | [-2.08, +2.08] |
| selection | +0.42pp | [-2.94, +3.75] | 7 | 6 | +1.26pp | [-1.69, +4.20] |
| internal_evaluation | +1.98pp | [+0.42, +3.67] | 52 | 24 | +1.13pp | [-0.71, +3.04] |

CI는 semantic item을 단위로 10,000회 bootstrap한 탐색적 95% 구간이다. 아래 여러 비교에 대한 보정된 유의성을 주장하지 않는다. Screen / Selection / Internal에서 자기 질문이 Automatic과 같은데 출력 label이 달라진 pair는 각각 0 / 1 / 0개였다. Selection의 작은 순증가를 해석할 때도 이 변동을 고려한다.

### Internal에서 reference와 비교

| 대비 | 정답 수 차이 | 정확도 차이 | 95% CI | 회복 / 회귀 |
| --- | ---: | ---: | --- | ---: |
| Oracle − Automatic | +28 | +1.98pp | [+0.42, +3.67] | 52 / 24 |
| Oracle − O | +16 | +1.13pp | [-0.71, +3.04] | 60 / 44 |
| Oracle − T_REF | +9 | +0.64pp | [-1.98, +3.32] | 144 / 135 |
| Oracle − R_REF | -188 | -13.28pp | [-16.81, -9.75] | 48 / 236 |
| Oracle − F_REF | -149 | -10.52pp | [-14.27, -6.71] | 94 / 243 |

## 3. 추출을 교정하면 어느 단계가 달라졌는가

| Internal 지표 | Automatic | Oracle |
| --- | ---: | ---: |
| Source referent 수·pair 반복 포함 | 3,375 | 6,420 |
| 실제 질문이 바뀐 pair | 496 | 948 |
| 적용된 edit 수 | 759 | 1,904 |
| 오류 fallback pair | 169 | 1 |
| Annotation source span recall | 44.67% | 100.00%·정의상 |
| 저장된 exact match 채택 수 | 783/3,357 | 1,966/6,415 |

Automatic fallback 169건 중 153건은 추출 검증 실패로 referent를 전달하지 못한 경우이고, 나머지는 번역 JSON 오류였다. Oracle에서는 이 경로가 제거됐고, 남은 fallback 1건은 **번역 후 보기 중복**으로 인한 편집 검증 실패였다. 이를 번역 JSON 실패로 분류하지 않는다.

Oracle에서는 편집 대상과 실제 치환이 늘었지만, 저장된 match 판단 6,415개 중 1,966개(30.65%)만 exact match했다. 4,101개는 번역문과 inventory가 일치하지 않았고 348개는 inventory가 비거나 실패했다. 편집 검증 fallback에 걸린 5개 referent는 기존 로그가 중간 match 판단을 보존하지 않아 이 분모에서 빠진다. 이 수치는 **matching 정확도가 아니라 채택 coverage**다.

자기 질문이 Automatic과 동일한 pair는 761/1416개이며, 이 중 출력 label이 바뀐 것은 0개였다. 실제 추가/변경 편집이 있는 사례에서 관찰된 회복과 회귀를 아래에서 본다. Batch 구성원을 유지했어도 동반 질문 길이와 padding은 달라질 수 있다.

### 문항 전체가 exact match한 비율

| 집합 | Referent별 확인된 match | 문항별 match 비율 평균 | 1개 이상 match | 모든 referent match |
| --- | ---: | ---: | ---: | ---: |
| screen | 237/1,044 (22.70%) | 23.05% | 130/240 (54.17%) | 5/240 (2.08%) |
| selection | 322/1,100 (29.27%) | 29.04% | 169/239 (70.71%) | 7/239 (2.93%) |
| internal_evaluation | 1,968/6,420 (30.65%) | 30.25% | 965/1416 (68.15%) | 68/1416 (4.80%) |

Internal에서는 한 문항·언어쌍에 평균 4.53개의 annotation referent가 있고, 그중 평균 1.39개가 match했다. **전체 referent가 match한 것은 68/1416쌍(4.80%)**뿐이다. 일부만 match한 897쌍과 하나도 match하지 않은 451쌍을 구분한다. Referent가 없는 field는 분모에 억지로 넣지 않는다.

위 표는 저장된 번역 JSON에서 matcher를 CPU로 재실행한 값이다. Internal의 보기 중복 fallback 1쌍에서 중간 로그가 빠졌던 5개 referent를 복원했고, 이 중 2개가 match했다. 따라서 전체 matching 단계 기준은 1,968/6,420이며, 앞의 저장된 match 로그 기준 1,966/6,415와 다르다. 최종 적용 edit 1,904개와도 다른 지표다. 이미 같은 숫자/이름도 exact match로 센다.

Screen에서는 번역 JSON 실패 2쌍의 7개 referent를 판정할 수 없다. 표의 전체 분모에는 유지하되 확인된 match 분자에는 넣지 않았고, 실제 no-match와 구별한다. 전체 match는 모델이 제안한 번역과 inventory의 일치이며 R_REF와의 표현 동일성이나 실제 GUI 대응 정답률을 뜻하지 않는다.

### 기존 R gap 259건은 얼마나 회복됐나

기존 R 정답·Automatic 오답 259건 중 Oracle이 44건을 회복했다. 215건은 여전히 오답이며, 반대로 R과 Automatic이 맞혔지만 Oracle이 새로 틀린 21건이 생겼다. 그 결과 R 정답·Oracle 오답은 236건이다.

| 기존 R gap의 source span 상태 | 기존 N | Oracle 회복 |
| --- | ---: | ---: |
| 추출 검증 실패 | 30 | 11 |
| Annotation span 일부/전체 누락 | 175 | 33 |
| Annotation span 전부 포함 | 54 | 0 |

| R 정답·Oracle 오답의 관찰 상태 | 건수 |
| --- | ---: |
| 편집 적용 후에도 오답 | 136 |
| Inventory 생성 실패 | 18 |
| Exact match 채택 없음 | 80 |
| 편집 검증 실패 | 1 |
| 기타 원문 유지 | 1 |

상태 분류는 편집 검증 실패 → inventory 실패 → 편집 적용 → exact match 미채택 → 기타 순서로 상호 배타적으로 집계했다. **원인의 인과 분해는 아니다.** 예를 들어 편집 후 오답은 잘못된 치환, 일부 참조만 치환, 또는 REL 문제 풀이 오류일 수 있다. Inventory 실패 수만으로 OCR의 전체 영향 크기를 정할 수도 없다.

## 4. 이득은 Thai GUI에 집중됐다

| GUI | N | O | Automatic | Oracle | Oracle − Automatic | 회복 / 회귀 | R_REF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EN | 354 | 81.92% | 80.51% | 80.79% | +0.28pp | 6 / 5 | 87.85% |
| ZH | 354 | 76.27% | 75.14% | 75.14% | +0.00pp | 6 / 6 | 82.77% |
| TH | 354 | 48.59% | 47.74% | 54.52% | +6.78pp | 31 / 7 | 83.62% |
| RU | 354 | 74.86% | 74.86% | 75.71% | +0.85pp | 9 / 6 | 85.03% |

Thai GUI에서 +24개가 늘어 전체 순증가 +28개의 85.7%를 차지했다. 추출 교정이 Thai에서 특히 유용했지만 Oracle 54.52%와 R 83.62% 사이에는 큰 차이가 남는다. 이것만으로 target 언어 난이도가 원인이라고 확정하지는 않는다. 번역 표현 선택·OCR·표기 차이와 부분 치환을 나눠 확인해야 한다.

## 5. 실제 회복·회귀 예시

아래는 raw 기록에서 선택한 internal 사례다. 화면을 새로 검수한 matching 정답 판정은 아니며, 각 치환이 왜 모델 답을 바꿨는지까지 확정하지 않는다. 전체 pair별 비교는 각 cohort의 `paired_outcomes.jsonl`에 있다.

### 회복: `rel::2/freeform_10.png::ru::th`

정오(O / Automatic / Oracle / T / R / F): 0 / 0 / 1 / 1 / 1 / 1. Automatic 추출 상태: `success`.

| 조건 | field: 원문 → 치환 |
| --- | --- |
| Automatic | 치환 없음 |
| Oracle | A: Настройки карандаша... → การตั้งค่าดินสอ... |

원본 MCQ:

```text
Какой элемент находится прямо под переключателем 'Рисуйте пальцем'? A: Настройки карандаша... B: Переключатель Автоматически убирать в Dock C: Круг выбора цвета D: Кнопка отмены
```

### 회복: `rel::3/clock_2.jpg::en::th`

정오(O / Automatic / Oracle / T / R / F): 0 / 0 / 1 / 1 / 1 / 1. Automatic 추출 상태: `success`.

| 조건 | field: 원문 → 치환 |
| --- | --- |
| Automatic | 치환 없음 |
| Oracle | question_stem: Additional settings → การตั้งค่าเพิ่มเติม |

원본 MCQ:

```text
Which element is positioned directly above the 'Additional settings' button on the interface? A: The number 07 B: The toggle switch for 'Monday to Friday' C: The number 50 D: The clock icon at the top
```

### 회귀: `rel::2/clock_9.png::ru::th`

정오(O / Automatic / Oracle / T / R / F): 1 / 1 / 0 / 0 / 1 / 1. Automatic 추출 상태: `success`.

| 조건 | field: 원문 → 치환 |
| --- | --- |
| Automatic | 치환 없음 |
| Oracle | D: Сохранить → บันทึก |

원본 MCQ:

```text
Какой элемент находится непосредственно под опцией 'Мелодия' в панели настроек будильника? A: Snooze B: Название C: Повтор D: Сохранить
```

### 회귀: `rel::2/note_2.png::zh::th`

정오(O / Automatic / Oracle / T / R / F): 1 / 1 / 0 / 1 / 0 / 0. Automatic 추출 상태: `success`.

| 조건 | field: 원문 → 치환 |
| --- | --- |
| Automatic | A: 拷贝 → คัดลอก; D: 打印 → พิมพ์ |
| Oracle | D: 打印 → พิมพ์ |

원본 MCQ:

```text
哪个元素位于分享菜单中“标记”选项的右侧？ A: 拷贝 B: 一个类似铅笔和纸的图标 C: 存储到“文件” D: 打印
```

Freeform 회복 사례에서는 기존 추출에서 빠진 A의 펜 설정 표현이 추가됐고, clock 회복에서는 stem의 Additional settings가 추가됐다. 두 사례의 기존 추출은 형식 검증에는 성공했지만 필요한 표현을 놓쳤다. 반면 clock 회귀는 Oracle이 보기에 태국어를 넣은 후 기존 정답을 잃은 사례다. Note 사례에서는 두 조건 모두 A의 拷贝 span을 사용했지만, Automatic 번역은 คัดลอก, Oracle 번역은 สำเนา였다. Inventory와 exact match한 전자만 적용됐고 Oracle은 A의 치환을 잃었다. 전체 referent 집합이 바뀌면 같은 표현도 공동 번역 결과가 달라질 수 있으므로, 항상 자동 span에 gold span을 단순 추가한 실험으로 보면 안 된다.

## 6. 추가 계산 비용과 완료 상태

| Cohort | 번역 wall·분 | 새 번역 호출 / 전체 | Inference batch 합계·분 | Inference peak reserved·GiB |
| --- | ---: | ---: | ---: | ---: |
| screen | 10.95 | 242/288 | 3.72 | 18.54 |
| selection | 7.62 | 198/240 | 3.02 | 19.09 |
| internal_evaluation | 36.37 | 1173/1416 | 14.77 | 18.54 |

번역 단계 wall 합계 54.94분, downstream batch 시간 합계 21.51분이다. 후자는 batch당 값을 한 번만 셌고 inference 모델 적재·전체 프로세스 기동·보고서 생성 시간은 포함하지 않는다. 따라서 두 값을 전체 실행 wall time으로 부르지 않는다. 비용 분모는 pilot·사전 제외 pair를 포함한 실행 1,944쌍이다.

각 cohort의 rewrite와 inference는 attempt 1회씩 완료됐다. 예측은 전부 GPU 모드·success였으며 OOM으로 인한 batch 축소나 표본 제외는 없었다. Inventory와 extractor 신규 호출은 0회다. 캐시 hit의 과거 runtime을 신규 비용으로 다시 합산하지 않았다. Dollar 비용은 기록이 없어 추정하지 않았다. Token 사용량과 원시 파일 SHA-256은 snapshot에 보존한다.

## 7. 다음에 할 최소 변경

1. **같은 Oracle source span을 고정한 채 남은 matching 실패를 표본 검수한다.** 번역문 불일치인지, inventory 누락인지, 원래 화면에 직접 대응하지 않는 표현인지 구별한다. 현재 exact-match 미채택 80건은 R 정답·Oracle 오답의 한 관찰 집단이며 전체 번역/OCR 오류 수는 아니다.
2. 그 원인에 맞는 **유연한 matching 한 조건만** 기존 Oracle+Exact와 비교한다. 번역기·span·inventory·fallback은 함께 바꾸지 않는다. Inventory에 없는 표현을 허용하려면 별도 ablation으로 표시한다.
3. 편집 후에도 틀린 136건과 새 회귀 24건을 함께 본다. 부분 치환 및 잘못된 대응을 확인하지 않고 coverage만 올리면 회귀도 늘 수 있다.
4. 유망한 matching이 확인되면 그때 자동 추출기로 되돌려 실제 method의 이득과 비용을 평가한다. 현재 결과만으로 NER 도입이나 inventory 제거를 결정할 근거는 부족하다.

새 GPU 실험은 이번 집계에서 실행하지 않았다. 이번 결과는 extraction 개선이 무의미하다는 결론도, extraction만 개선하면 충분하다는 결론도 지지하지 않는다. 현 pipeline에서 추출 교정으로 일부 회복했고, 큰 잔여 gap이 남았다는 범위까지 확인했다.

## 부록: Internal 12방향 결과

| Source → GUI | N | O | Automatic | Oracle | T_REF | R_REF | F_REF | 회복 / 회귀 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| en→ru | 118 | 83.05% | 81.36% | 83.05% | 77.97% | 86.44% | 87.29% | 2 / 0 |
| en→th | 118 | 50.85% | 51.69% | 55.08% | 74.58% | 83.90% | 67.80% | 8 / 4 |
| en→zh | 118 | 84.75% | 82.20% | 82.20% | 77.12% | 84.75% | 83.90% | 2 / 2 |
| ru→en | 118 | 88.98% | 86.44% | 85.59% | 79.66% | 88.98% | 88.98% | 0 / 1 |
| ru→th | 118 | 49.15% | 47.46% | 53.39% | 65.25% | 83.90% | 67.80% | 8 / 1 |
| ru→zh | 118 | 80.51% | 80.51% | 78.81% | 72.03% | 86.44% | 84.75% | 1 / 3 |
| th→en | 118 | 73.73% | 71.19% | 74.58% | 67.80% | 85.59% | 88.98% | 5 / 1 |
| th→ru | 118 | 65.25% | 65.25% | 67.80% | 63.56% | 81.36% | 87.29% | 4 / 1 |
| th→zh | 118 | 63.56% | 62.71% | 64.41% | 61.86% | 77.12% | 83.90% | 3 / 1 |
| zh→en | 118 | 83.05% | 83.90% | 82.20% | 79.66% | 88.98% | 88.98% | 1 / 3 |
| zh→ru | 118 | 76.27% | 77.97% | 76.27% | 68.64% | 87.29% | 87.29% | 3 / 5 |
| zh→th | 118 | 45.76% | 44.07% | 55.08% | 62.71% | 83.05% | 67.80% | 15 / 2 |

재현 명령:

```bash
.venv/bin/python followup_rel_4lang/method_dev/scripts/analyze_oracle_exact.py
```

실행 설정: [Oracle 실행안](ORACLE_SPAN_EXACT_KO.md). 원시 결과 루트: `followup_rel_4lang/method_dev/artifacts/oracle_span_exact_v1`. 집계값·입력 SHA-256: [oracle_exact_results_snapshot.json](../artifacts/oracle_exact_results_snapshot.json). 기존 method 탐색 결과: [SEARCH_RESULTS_KO.md](SEARCH_RESULTS_KO.md).
