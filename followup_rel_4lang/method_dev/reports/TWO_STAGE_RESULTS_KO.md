# Two-stage 재정비 실험 중간 결산

집계 시각: 2026-11-16T11:07:55.943024+00:00. 실행: `followup_rel_4lang/method_dev/artifacts/two_stage_v2_hybrid`. 실행 중인 코드·config·캐시·출력 파일을 변경하거나 GPU 추론을 추가하지 않았다.

**번역·변환 완료와 문제 풀이 완료를 구분한다.** 현재 pipeline은 각 cohort에서 모든 조건의 변환이 끝난 뒤 O와 각 조건의 VLM 문제 풀이를 수행한다. 아래 정확도는 전체 paired 출력이 완성된 조건에서만 표시한다.

## 진행 상태

| Cohort | 조건 | 변환 | 문제 풀이 출력 |
| --- | --- | ---: | ---: |
| screen | TS_FULL_GUI | 288/288 | 288/288 |
| screen | TS_FULL_TXT | 288/288 | 288/288 |
| screen | TS_SEL_GUI_AUTO | 288/288 | 288/288 |
| screen | TS_SEL_TXT_AUTO | 288/288 | 288/288 |
| screen | TS_SEL_GUI_ORACLE | 288/288 | 288/288 |
| screen | TS_SEL_TXT_ORACLE | 288/288 | 288/288 |
| screen | TS_QSEL_OFULL_GUI_AUTO | 288/288 | 288/288 |
| screen | TS_QSEL_OFULL_TXT_AUTO | 288/288 | 288/288 |
| selection | TS_FULL_GUI | 0/240 | 0/240 |
| selection | TS_FULL_TXT | 0/240 | 0/240 |
| selection | TS_SEL_GUI_AUTO | 0/240 | 0/240 |
| selection | TS_SEL_TXT_AUTO | 0/240 | 0/240 |
| selection | TS_SEL_GUI_ORACLE | 0/240 | 0/240 |
| selection | TS_SEL_TXT_ORACLE | 0/240 | 0/240 |
| selection | TS_QSEL_OFULL_GUI_AUTO | 0/240 | 0/240 |
| selection | TS_QSEL_OFULL_TXT_AUTO | 0/240 | 0/240 |
| internal_evaluation | TS_FULL_GUI | 0/1416 | 0/1416 |
| internal_evaluation | TS_FULL_TXT | 0/1416 | 0/1416 |
| internal_evaluation | TS_SEL_GUI_AUTO | 0/1416 | 0/1416 |
| internal_evaluation | TS_SEL_TXT_AUTO | 0/1416 | 0/1416 |
| internal_evaluation | TS_SEL_GUI_ORACLE | 0/1416 | 0/1416 |
| internal_evaluation | TS_SEL_TXT_ORACLE | 0/1416 | 0/1416 |
| internal_evaluation | TS_QSEL_OFULL_GUI_AUTO | 0/1416 | 0/1416 |
| internal_evaluation | TS_QSEL_OFULL_TXT_AUTO | 0/1416 | 0/1416 |

| Cohort | 조건 | 정답 | O 정답 | ΔO | 95% CI | 회복/회귀 |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| screen | TS_FULL_GUI | 170/240 | 162/240 | +3.33pp | [-6.25, +12.50] | 37/29 |
| screen | TS_FULL_TXT | 161/240 | 162/240 | -0.42pp | [-5.42, +4.58] | 28/29 |
| screen | TS_SEL_GUI_AUTO | 169/240 | 162/240 | +2.92pp | [-2.08, +8.33] | 19/12 |
| screen | TS_SEL_TXT_AUTO | 159/240 | 162/240 | -1.25pp | [-7.08, +4.17] | 17/20 |
| screen | TS_SEL_GUI_ORACLE | 180/240 | 162/240 | +7.50pp | [+0.00, +15.00] | 34/16 |
| screen | TS_SEL_TXT_ORACLE | 158/240 | 162/240 | -1.67pp | [-5.83, +2.50] | 20/24 |
| screen | TS_QSEL_OFULL_GUI_AUTO | 178/240 | 162/240 | +6.67pp | [-1.25, +15.00] | 39/23 |
| screen | TS_QSEL_OFULL_TXT_AUTO | 163/240 | 162/240 | +0.42pp | [-5.42, +5.83] | 27/26 |

## 완료된 cohort의 실제 문제 풀이 결과

**완료 cohort: screen**. 아직 완료되지 않은 cohort: selection, internal_evaluation. Pilot과 사전 제외 pair는 primary에서 분리한다. 모든 조건의 실패 fallback도 분모에 유지했다.

### screen: 정확도와 O 대비

실행288pair 중 primary20개 semantic item의240pair다.

| 조건 | 정답 | 정확도 | ΔO | Item bootstrap95% CI | 회복/회귀 |
| --- | ---: | ---: | ---: | --- | ---: |
| O | 162/240 | 67.50% | — | — | — |
| 전체 GUI 번역 | 170/240 | 70.83% | +3.33pp | [-6.25, +12.50] | 37/29 |
| 전체 TXT 번역 | 161/240 | 67.08% | -0.42pp | [-5.42, +4.58] | 28/29 |
| 자동 Selective GUI | 169/240 | 70.42% | +2.92pp | [-2.08, +8.33] | 19/12 |
| 자동 Selective TXT | 159/240 | 66.25% | -1.25pp | [-7.08, +4.17] | 17/20 |
| Oracle Selective GUI | 180/240 | 75.00% | +7.50pp | [+0.00, +15.00] | 34/16 |
| Oracle Selective TXT | 158/240 | 65.83% | -1.67pp | [-5.83, +2.50] | 20/24 |
| Query 선택적 + Options 전체 GUI | 178/240 | 74.17% | +6.67pp | [-1.25, +15.00] | 39/23 |
| Query 선택적 + Options 전체 TXT | 163/240 | 67.92% | +0.42pp | [-5.42, +5.83] | 27/26 |
| **Stem-only GUI · Options 원본** | **175/240** | **72.92%** | +5.42pp | [-1.67, +13.33] | 27/14 |
| R_REF · parallel reference | 194/240 | 80.83% | +13.33pp | — | — |
| F_REF · parallel reference | 192/240 | 80.00% | +12.50pp | — | — |

Stem-only는 완료된 Hybrid stem을 그대로 쓰고 A–D만 원본으로 복원했다. 새 추출·번역 없이 추가 downstream288쌍을 평가했다. **Stem-only−Hybrid는 -1.25pp**, CI[-9.58, +7.50]pp, 회복/회귀19/22이다. Options Full을 추가한 Hybrid가 정답3개 높은 점추정이지만 구간이 넓어 우위를 확정하지 않는다. R/F는 같은 primary pair의 기존 parallel reference이며 자동 method가 아니다.

CI는 semantic item 단위 10,000회 bootstrap이다. 240개 pair를 독립 문제240개로 취급하지 않는다. O 대비 CI는 모두 0을 포함하거나 경계가0이다. Point estimate만으로 유의한 개선을 주장하지 않으며, 여러 탐색 대비에 대한 보정된 유의성도 주장하지 않는다.

### 조건 간 주요 paired 비교

| 비교 | 차이 | 95% CI | 회복/회귀 |
| --- | ---: | --- | ---: |
| 전체 GUI 번역 − 전체 TXT 번역 | +3.75pp | [-7.51, +15.83] | 34/25 |
| 자동 Selective GUI − 자동 Selective TXT | +4.17pp | [-2.08, +10.43] | 22/12 |
| Oracle Selective GUI − Oracle Selective TXT | +9.17pp | [-1.25, +19.17] | 38/16 |
| Oracle Selective GUI − 자동 Selective GUI | +4.58pp | [-2.08, +11.67] | 21/10 |
| Query 선택적 + Options 전체 GUI − Query 선택적 + Options 전체 TXT | +6.25pp | [-3.75, +17.08] | 36/21 |
| Query 선택적 + Options 전체 GUI − 자동 Selective GUI | +3.75pp | [-2.50, +10.42] | 27/18 |
| Query 선택적 + Options 전체 GUI − 전체 GUI 번역 | +3.33pp | [-2.92, +10.00] | 26/18 |

여기서 GUI/TXT 차이는 inventory 사용뿐 아니라 서로 다른 system prompt·검증 경로도 포함한다. Hybrid는 stem-only 추출 prompt와 options context 언어가 달라지는 pipeline 수준의 비교다. 각 대비를 한 요인의 순수 인과 효과로 해석하지 않는다.

### R/T/F reference와 같은 분모 비교

| Reference | 정답 | 정확도 |
| --- | ---: | ---: |
| T_REF | 162/240 | 67.50% |
| R_REF | 194/240 | 80.83% |
| F_REF | 192/240 | 80.00% |

T_REF는 annotation span+Gemma 번역, R_REF는 parallel referent alignment, F_REF는 parallel 전체 localization이다. 예전 잘못된 inventory method 결과를 재사용한 것이 아니라 독립적인 기존 reference다. 같은 pair ID·gold·모델 revision·system을 검사해 결합했지만 이전 RTX4090 batch/queue와 현재 B200 MIG의 차이가 남는다. 각 신규 method−reference CI와 회복/회귀는 snapshot에 있다.

### 새 control에서 실패가 실제로 줄었나

| 조건 | 전체 원문 fallback | 부분 fallback | 주요 오류 |
| --- | ---: | ---: | --- |
| 전체 GUI 번역 | 0 | 0 | 없음 |
| 전체 TXT 번역 | 0 | 0 | 없음 |
| 자동 Selective GUI | 37 | 0 | source_extraction_failed: 18; Target is not a verbatim inventory member: 19 |
| 자동 Selective TXT | 18 | 0 | source_extraction_failed: 18 |
| Oracle Selective GUI | 24 | 0 | Target is not a verbatim inventory member: 21; New duplicate options: 3 |
| Oracle Selective TXT | 0 | 0 | 없음 |
| Query 선택적 + Options 전체 GUI | 0 | 12 | stem: Target is not a verbatim inventory member: 9; stem: source_extraction_failed: 3 |
| Query 선택적 + Options 전체 TXT | 0 | 3 | stem: source_extraction_failed: 3 |

GUI Hybrid의 Query 추출 실패3쌍·정렬 실패9쌍을 별도 기록했다. Options Full pipeline 실패는0쌍이었다. 전체 원문 fallback과 부분 fallback을 같은 실패로 세지 않는다. 단계별 parser 검증 실패 감소가 의미 정확도 향상을 자동으로 보장하지 않는다.

### GUI 언어별 결과

| 조건 | EN | ZH | TH | RU |
| --- | ---: | ---: | ---: | ---: |
| O | 45/60 (75.00%) | 44/60 (73.33%) | 27/60 (45.00%) | 46/60 (76.67%) |
| 전체 GUI 번역 | 50/60 (83.33%) | 42/60 (70.00%) | 33/60 (55.00%) | 45/60 (75.00%) |
| 전체 TXT 번역 | 48/60 (80.00%) | 41/60 (68.33%) | 34/60 (56.67%) | 38/60 (63.33%) |
| 자동 Selective GUI | 44/60 (73.33%) | 45/60 (75.00%) | 36/60 (60.00%) | 44/60 (73.33%) |
| 자동 Selective TXT | 42/60 (70.00%) | 43/60 (71.67%) | 34/60 (56.67%) | 40/60 (66.67%) |
| Oracle Selective GUI | 47/60 (78.33%) | 47/60 (78.33%) | 41/60 (68.33%) | 45/60 (75.00%) |
| Oracle Selective TXT | 43/60 (71.67%) | 44/60 (73.33%) | 35/60 (58.33%) | 36/60 (60.00%) |
| Query 선택적 + Options 전체 GUI | 50/60 (83.33%) | 47/60 (78.33%) | 41/60 (68.33%) | 40/60 (66.67%) |
| Query 선택적 + Options 전체 TXT | 45/60 (75.00%) | 44/60 (73.33%) | 36/60 (60.00%) | 38/60 (63.33%) |
| Stem-only GUI · Options 원본 | 46/60 (76.67%) | 46/60 (76.67%) | 40/60 (66.67%) | 43/60 (71.67%) |

GUI 언어별 결과도 같은 semantic item에서 나온 반복 관측이며 기술 통계로 본다. 전체 평균이 높아져도 모든 GUI 언어에 동일하게 이득이 생긴 것은 아니다.

### 비용과 재현 검사

| 단계 | Wall·분 | 호출 | cache hit |
| --- | ---: | ---: | ---: |
| inventory | 43.66 | 141 | 0 |
| extract | 8.91 | 147 | 0 |
| extract_stem | 2.73 | 129 | 0 |
| rewrite | 70.61 | 3067 | 897 |

Downstream batch 시간 합계는24.81분이며 모델 적재와 프로세스 기동은 제외한다. Peak reserved는18.70GiB, 전체 예측2,592행은 모두GPU mode였다. Attempt 수: inventory=1, extract=1, extract_stem=1, rewrite=1, infer=1. Hybrid options는 Full과 모든 실행 pair에서 정확히 같고, stem은 source span 밖이 보존되는 것을 재검증했다. 같은 자기 MCQ인데 O와 label이 바뀐 사례는 완료된 조건들에서0개였다. 이는 다른 batch 입력 효과가 일반적으로 불가능하다는 주장은 아니다.

### 현재 판단

- Inventory-conditioned 조건의 point estimate는 대응 text-only보다 일관되게 높았다. 다만 작은 Screen 표본에서 구간이 넓다.
- 자동 method 중 Query 선택적+Options 전체 GUI가74.17%로 가장 높고, Oracle GUI는75.00%였다. Oracle은 gold source span을 사용하므로 자동 method 순위에 넣지 않는다.
- 자동 Hybrid는 R_REF80.83%보다6.67pp, F_REF80.00%보다5.83pp 낮다. Oracle GUI도 R_REF보다5.83pp 낮다. 아직 R 효과를 재현했다고 말할 수 없다.
- 이 수치는 Screen만의 결과다. Screen을 본 뒤 method를 바꾸면 새 development iteration으로 기록하고, 이 수치를158-item 전체 평가로 확대 해석하지 않는다.

## screen: 완료 단계 비용

| 단계 | 출력 수 | Wall·분 |
| --- | ---: | ---: |
| inventory | 128 | 43.66 |
| extract | 128 | 8.91 |
| extract_stem | 128 | 2.73 |

## screen: Inventory

| 범위 | 고유 이미지 | 성공 | repair 시도 | repair 후 회복 | 최종 실패 | 실패 evidence를 받는 pair |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 128 | 125 | 13 | 10 | 3 | 9 |
| main | 80 | 77 | 6 | 3 | 3 | 9 |
| pilot | 48 | 48 | 7 | 7 | 0 | 0 |

실패 image는 삭제하지 않고 빈 inventory로 포함한다. Full GUI는 이 경우 일반 번역을 수행할 수 있으므로 변환 성공과 GUI evidence 사용 성공이 다르다. OCR 문자열 내용의 정확도는 이번 집계에서 독립 검수하지 않았다.

- `rel::3/homescreen_5.jpg` / GUI en: invalid_json:Expecting value

- `rel::3/map_6.jpg` / GUI th: invalid_json:Unterminated string starting at

- `rel::4/google_play_6.jpg` / GUI zh: invalid_json:Unterminated string starting at

## screen: 전체 필드 추출 vs stem-only

| 범위 | 고유 source MCQ | 전체 필드 실패 | Stem-only 실패 | 실패→성공 | 성공→실패 |
| --- | ---: | ---: | ---: | ---: | ---: |
| all | 128 | 15 | 1 | 15 | 1 |
| main | 80 | 6 | 1 | 6 | 1 |
| pilot | 48 | 9 | 0 | 9 | 0 |

### Main의 stem source-span 품질

| 추출 방식 | Precision | Recall | F1 | 유효하지만 stem ref 없음 |
| --- | ---: | ---: | ---: | ---: |
| all_fields | 92.59% | 62.50% | 74.63% | 20 |
| stem_only | 81.01% | 80.00% | 80.50% | 0 |

기존 main 실패 6개 중 options field만 검증 실패한 것은 2개다. 전체 필드 추출 실패를 모두 options 때문이라고 보지는 않는다. 이는 parser/span 검증 실패의 분류이며 형식이 유효한 options의 의미 오류까지 분해한 결과는 아니다. Stem-only는 실패를 줄이고 recall을 올렸지만 annotation과 일치하지 않는 추가 경계도 늘었다. 이는 source annotation의 exact span 경계 지표이며 GUI 대응 정답률이 아니다. 실패 응답은 실제 pipeline처럼 빈 추출로 취급하므로 모델의 raw 추출 능력뿐 아니라 검증 정책의 영향도 포함한다.

MCQ 단위는 (semantic item, source language)로 dedup했다. Main은 같은 source가 세 GUI로 반복되므로 pair 240개를 독립 source 240개로 세지 않는다. 기존 전체 필드와 stem-only는 prompt/scope가 달라진 pipeline 비교이며 단일 오류 유형의 순수 인과 효과가 아니다.

## screen: TS_FULL_GUI 변환 완료

| 범위 | N | 구조상 성공 | 구조 repair | 의미 repair 시도 | 의미 repair 채택 | 잔여 의미 경고 pair | 숫자 등 진단 pair |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 288 | 288 | 0 | 21 | 14 | 9 | 7 |
| main | 240 | 240 | 0 | 16 | 11 | 7 | 4 |
| pilot | 48 | 48 | 0 | 5 | 3 | 2 | 3 |

| Main GUI | N | 의미 repair | 잔여 의미 경고 |
| --- | ---: | ---: | ---: |
| en | 60 | 0 | 0 |
| ru | 60 | 1 | 1 |
| th | 60 | 14 | 5 |
| zh | 60 | 1 | 1 |

구조상 성공은 의미 보존을 보장하지 않는다. 의미 repair 채택은 자동 점수가 낮아졌다는 뜻이며 경고가 모두 사라졌다는 뜻은 아니다. 잔여 경고는 자동 휴리스틱이며, DND 같은 acronym 유지가 정당한 경우도 포함할 수 있다. 숫자 token 차이 역시 실제 GUI label 변화인지 번역 오류인지 별도 확인해야 한다.

### 검토할 원문/번역 사례

- `rel::2/calendar_6.png::ru::th`: number_tokens_changed:A:['10']->['9']

```text
Source: Какой день недели запланировано событие и каково его относительное положение по сравнению с "Чт, 12"?
Target: วันในสัปดาห์ใดที่มีเหตุการณ์ที่วางแผนไว้ และมันอยู่ในตำแหน่งสัมพัทธ์อย่างไรเมื่อเทียบกับ "พ. 12"?
```

```text
A source: "Вт, 10", за один день до
A target: "จ. 9", หนึ่งวันก่อน
```

- `rel::2/note_8.png::en::th`: quoted_gui_label_may_be_untranslated:customize

```text
Source: Which element is located directly to the right of the 'Customize' option in the customization menu?
Target: องค์ประกอบใดอยู่ด้านขวาของตัวเลือก 'Customize' ในเมนูการปรับแต่ง?
```

- `rel::2/setting_3.png::en::th`: quoted_gui_label_may_be_untranslated:handwrite

```text
Source: Which element is located directly to the right of the 'Handwrite' button?
Target: องค์ประกอบใดอยู่ด้านขวาของปุ่ม 'Handwrite'?
```

- `rel::3/homescreen_5.jpg::en::ru`: quoted_gui_label_may_be_untranslated:dnd

```text
Source: Which element is directly below the 'DND' option in the mobile UI interface?
Target: Какой элемент находится непосредственно ниже опции 'DND' в интерфейсе мобильного приложения?
```

- `rel::3/homescreen_5.jpg::en::th`: quoted_gui_label_may_be_untranslated:dnd

```text
Source: Which element is directly below the 'DND' option in the mobile UI interface?
Target: องค์ประกอบใดอยู่ตรงด้านล่างของตัวเลือก 'DND' ในอินเทอร์เฟซ UI ของมือถือ?
```

- `rel::3/homescreen_5.jpg::en::zh`: quoted_gui_label_may_be_untranslated:dnd

```text
Source: Which element is directly below the 'DND' option in the mobile UI interface?
Target: 在移动界面中，'DND'选项直接下方的元素是什么？
```

- `rel::3/map_6.jpg::en::th`: quoted_gui_label_may_be_untranslated:choose on map

```text
Source: What is immediately to the right of the 'Choose on map' button?
Target: อะไรอยู่ทางขวาของปุ่ม 'Choose on map' ทันที
```

- `rel::3/music_3.jpg::en::th`: spatial_opposition_introduced, spatial_core_relation_missing:above

```text
Source: Which playlist is located directly above '#1 Total 5 songs'?
Target: รายการเพลิงใดอยู่ตรงข้ามกับ '#1 ทั้งหมด 5 เพลง'?
```

- `rel::5/forest_2.jpg::en::th`: number_tokens_changed:D:['15', '22']->['15', '02']

```text
Source: Which element is located directly below the "Novice Planter" achievement label?
Target: องค์ประกอบใดอยู่ตรงด้านล่างของป้ายชื่อ "ความสำเร็จ นักปลูกมือใหม่"?
```

```text
D source: The time "15:22"
D target: เวลา "15:02"
```

- `rel::5/forest_2.jpg::ru::th`: number_tokens_changed:D:['15', '48']->['15', '02']

```text
Source: Какой элемент находится прямо под меткой достижения "Начинающий планта..."
Target: องค์ประกอบใดอยู่ตรงด้านล่างของป้ายชื่อ "ความสําเร็จ นักปลูกมือใหม่"
```

```text
D source: Время "15:48"
D target: เวลา "15:02"
```

- `rel::5/forest_2.jpg::zh::th`: number_tokens_changed:D:['15', '22']->['15', '02']

```text
Source: 哪个元素位于“戴上草帽”成就标签的正下方？
Target: องค์ประกอบใดอยู่ตรงด้านล่างของป้ายชื่อความสำเร็จ "สวมหมวกหญ้า"?
```

```text
D source: 时间“15:22”
D target: เวลา "15:02"
```

완료된 TS_FULL_GUI의 신규 call runtime 합계는 16.42분, model-load 합계 0.16분이다. Call runtime은 generation/preprocessing 구간이며 전체 조건 wall time은 아니다. Peak reserved는 15.72GiB였다.

## screen: TS_FULL_TXT 변환 완료

| 범위 | N | 구조상 성공 | 구조 repair | 의미 repair 시도 | 의미 repair 채택 | 잔여 의미 경고 pair | 숫자 등 진단 pair |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 288 | 288 | 0 | 54 | 27 | 39 | 2 |
| main | 240 | 240 | 0 | 46 | 25 | 32 | 1 |
| pilot | 48 | 48 | 0 | 8 | 2 | 7 | 1 |

| Main GUI | N | 의미 repair | 잔여 의미 경고 |
| --- | ---: | ---: | ---: |
| en | 60 | 0 | 0 |
| ru | 60 | 9 | 4 |
| th | 60 | 28 | 23 |
| zh | 60 | 9 | 5 |

구조상 성공은 의미 보존을 보장하지 않는다. 의미 repair 채택은 자동 점수가 낮아졌다는 뜻이며 경고가 모두 사라졌다는 뜻은 아니다. 잔여 경고는 자동 휴리스틱이며, DND 같은 acronym 유지가 정당한 경우도 포함할 수 있다. 숫자 token 차이 역시 실제 GUI label 변화인지 번역 오류인지 별도 확인해야 한다.

### 검토할 원문/번역 사례

- `rel::2/map_9.png::ru::th`: spatial_core_relation_missing:below

```text
Source: Какой элемент находится прямо под переключателем 'Избегать платных дорог'?
Target: องค์ประกอบใดอยู่ต่ำกว่าสวิตช์ 'หลีกเลี่ยงทางหลวงเสียค่าใช้จ่าย'?
```

- `rel::2/note_8.png::en::th`: spatial_core_relation_missing:right, quoted_gui_label_may_be_untranslated:customize

```text
Source: Which element is located directly to the right of the 'Customize' option in the customization menu?
Target: องค์ประกอบใดอยู่ติดกับตัวเลือก 'Customize' ในเมนูการปรับแต่ง?
```

- `rel::2/note_8.png::en::zh`: quoted_gui_label_may_be_untranslated:customize

```text
Source: Which element is located directly to the right of the 'Customize' option in the customization menu?
Target: 在自定义菜单中，'Customize'选项的右侧直接是什么元素？
```

- `rel::2/setting_3.png::en::th`: quoted_gui_label_may_be_untranslated:handwrite

```text
Source: Which element is located directly to the right of the 'Handwrite' button?
Target: องค์ประกอบใดอยู่ทางด้านขวาโดยตรงของปุ่ม 'Handwrite'?
```

- `rel::2/setting_3.png::ru::th`: spatial_opposition_introduced

```text
Source: Какой элемент находится непосредственно справа от кнопки 'Написание'?
Target: องค์ประกอบใดอยู่ทางขวาของปุ่ม 'การเขียน' อย่างตรงข้าม?
```

- `rel::3/homescreen_5.jpg::en::ru`: quoted_gui_label_may_be_untranslated:dnd

```text
Source: Which element is directly below the 'DND' option in the mobile UI interface?
Target: Какой элемент находится непосредственно ниже опции 'DND' в интерфейсе мобильного приложения?
```

- `rel::3/homescreen_5.jpg::en::th`: quoted_gui_label_may_be_untranslated:dnd

```text
Source: Which element is directly below the 'DND' option in the mobile UI interface?
Target: องค์ประกอบใดอยู่ตรงด้านล่างของตัวเลือก 'DND' ในอินเทอร์เฟซ UI บนมือถือ?
```

- `rel::3/homescreen_5.jpg::en::zh`: quoted_gui_label_may_be_untranslated:dnd

```text
Source: Which element is directly below the 'DND' option in the mobile UI interface?
Target: 在移动界面中，'DND'选项直接下方的元素是什么？
```

- `rel::3/homescreen_5.jpg::ru::th`: spatial_core_relation_missing:below

```text
Source: Какой элемент находится прямо под опцией 'Не беспокоить' в интерфейсе мобильного устройства?
Target: องค์ประกอบใดอยู่ต่ำกว่าตัวเลือก 'ไม่รบกวน' ในอินเทอร์เฟซของอุปกรณ์เคลื่อนที่?
```

- `rel::3/map_4.jpg::en::th`: quoted_gui_label_may_be_untranslated:how you commute

```text
Source: Which option is located directly beneath the 'How you commute' headline?
Target: ตัวเลือกใดอยู่ตรงด้านล่างของหัวข้อ 'How you commute'?
```

- `rel::3/map_4.jpg::ru::th`: spatial_core_relation_missing:below

```text
Source: Какой вариант находится прямо под заголовком 'Как вы добираетесь'?
Target: ตัวเลือกใดอยู่ต่ำกว่าหัวข้อ 'คุณเดินทางอย่างไร'
```

- `rel::3/map_6.jpg::en::th`: quoted_gui_label_may_be_untranslated:choose on map

```text
Source: What is immediately to the right of the 'Choose on map' button?
Target: อะไรอยู่ทางด้านขวาของปุ่ม 'Choose on map' ทันที
```

- `rel::3/music_10.jpg::en::th`: spatial_core_relation_missing:above, spatial_opposition_introduced

```text
Source: Which element is located directly above the 'Update automatically' option in the given interface?
Target: องค์ประกอบใดอยู่ตรงข้ามกับตัวเลือก 'อัปเดตอัตโนมัติ' ในอินเทอร์เฟซที่กำหนด?
```

- `rel::3/music_3.jpg::en::ru`: translatable_options_unchanged:A,B,C,D

```text
Source: Which playlist is located directly above '#1 Total 5 songs'?
Target: Какая плейлист находится непосредственно выше '#1 Total 5 songs'?
```

- `rel::3/music_3.jpg::en::th`: translatable_options_unchanged:A,B,C,D

```text
Source: Which playlist is located directly above '#1 Total 5 songs'?
Target: เพลย์ลิสต์ใดอยู่ตรงข้างบน '#1 Total 5 songs'?
```

- `rel::3/music_3.jpg::en::zh`: translatable_options_unchanged:A,B,C,D

```text
Source: Which playlist is located directly above '#1 Total 5 songs'?
Target: 哪一个播放列表直接位于 '#1 Total 5 songs' 的上方？
```

- `rel::4/google_play_6.jpg::en::th`: quoted_gui_label_may_be_untranslated:wishlist

```text
Source: Which element is located directly below the 'Wishlist' section?
Target: องค์ประกอบใดอยู่ตรงด้านล่างของส่วน 'Wishlist'?
```

- `rel::4/google_play_6.jpg::ru::th`: spatial_core_relation_missing:below

```text
Source: Какой элемент находится непосредственно под разделом 'Список желаний'?
Target: องค์ประกอบใดอยู่ต่ำกว่าส่วน 'รายการที่ต้องการ' อย่างตรงไปตรงมา
```

- `rel::4/google_play_8.jpg::ru::th`: spatial_core_relation_missing:above

```text
Source: Какой параметр находится непосредственно выше опции «Использовать данные о местоположении устройства» в меню настроек?
Target: ตัวเลือกใดอยู่ติดกับตัวเลือก "ใช้ข้อมูลตำแหน่งของอุปกรณ์" ในเมนูตั้งค่า?
```

- `rel::4/google_play_8.jpg::zh::ru`: number_tokens_changed:A:[]->['5']

```text
Source: 在设置菜单中，哪个设置位于“使用设备位置信息”选项的正上方？
Target: В меню настроек, какой параметр находится непосредственно выше опции «Использовать информацию о местоположении устройства»?
```

```text
A source: Google Play 商店反馈
A target: Обратная связь Google Play Маркета
```

- `rel::5/forest_2.jpg::en::th`: quoted_gui_label_may_be_untranslated:novice planter

```text
Source: Which element is located directly below the "Novice Planter" achievement label?
Target: องค์ประกอบใดอยู่ตรงด้านล่างของป้ายชื่อ "Novice Planter"?
```

- `rel::5/forest_2.jpg::en::zh`: quoted_gui_label_may_be_untranslated:novice planter

```text
Source: Which element is located directly below the "Novice Planter" achievement label?
Target: 以下哪个元素位于 "Novice Planter" 成就标签的正下方？
```

- `rel::5/forest_2.jpg::ru::th`: spatial_core_relation_missing:below

```text
Source: Какой элемент находится прямо под меткой достижения "Начинающий планта..."
Target: องค์ประกอบใดอยู่ต่ำกว่าป้ายชื่อ "ผู้เริ่มต้นปลูกต้นไม้..." อย่างตรงไปตรงมา
```

- `rel::5/message_2.jpg::en::th`: quoted_gui_label_may_be_untranslated:smart message recognition

```text
Source: Which toggle switch is located directly below the "Smart message recognition" option?
Target: สวิตช์แบบทูดที่อยู่ตรงด้านล่างของตัวเลือก "Smart message recognition" คือตัวเลือกใด
```

- `rel::5/phone_4.jpg::en::th`: quoted_gui_label_may_be_untranslated:delay auto answer

```text
Source: Which option is directly below "Delay auto answer"?
Target: ตัวเลือกใดอยู่ตรงด้านล่างของ "Delay auto answer"?
```

- `rel::5/phone_4.jpg::ru::th`: spatial_core_relation_missing:below

```text
Source: Какой вариант находится непосредственно под "Задержка автоответа"?
Target: ตัวเลือกใดอยู่ต่ำกว่า "การตั้งค่าการตอบกลับอัตโนมัติ"?
```

- `rel::6/camera_8.jpg::en::ru`: translatable_options_unchanged:A,B,C,D

```text
Source: Which mode is directly to the left of the PHOTO mode on this user interface?
Target: Какой режим находится непосредственно слева от режима PHOTO в этом пользовательском интерфейсе?
```

- `rel::6/camera_8.jpg::en::th`: translatable_options_unchanged:A,B,C,D

```text
Source: Which mode is directly to the left of the PHOTO mode on this user interface?
Target: โหมดใดอยู่ทางด้านซ้ายของโหมด PHOTO บนอินเทอร์เฟซนี้โดยตรง?
```

- `rel::6/camera_8.jpg::en::zh`: translatable_options_unchanged:A,B,C,D

```text
Source: Which mode is directly to the left of the PHOTO mode on this user interface?
Target: 以下哪种模式位于此用户界面的 PHOTO 模式左侧？
```

- `rel::6/wallet_6.jpg::en::th`: quoted_gui_label_may_be_untranslated:nearby

```text
Source: What element is located directly below the 'Nearby' label on the interface?
Target: องค์ประกอบใดอยู่ตรงด้านล่างของป้ายชื่อ 'Nearby' บนอินเทอร์เฟซ?
```

- `rel::6/wallet_6.jpg::ru::th`: spatial_core_relation_missing:below

```text
Source: Какой элемент находится непосредственно под меткой 'Скоро' на интерфейсе?
Target: องค์ประกอบใดอยู่ต่ำกว่าป้าย 'เร็วๆ นี้' บนอินเทอร์เฟซ?
```

- `rel::6/wallet_8.jpg::en::ru`: quoted_gui_label_may_be_untranslated:find apps for wallet

```text
Source: What is positioned immediately above the 'Find Apps for Wallet' text?
Target: Что расположено непосредственно выше текста 'Find Apps for Wallet'?
```

- `rel::6/wallet_8.jpg::en::th`: quoted_gui_label_may_be_untranslated:find apps for wallet

```text
Source: What is positioned immediately above the 'Find Apps for Wallet' text?
Target: สิ่งใดอยู่ทันทีข้างบนของข้อความ 'Find Apps for Wallet'?
```

완료된 TS_FULL_TXT의 신규 call runtime 합계는 12.78분, model-load 합계 0.00분이다. Call runtime은 generation/preprocessing 구간이며 전체 조건 wall time은 아니다. Peak reserved는 15.72GiB였다.

Full GUI와 Full TXT는 각각 과거 lexical/contextual prompt를 사용하므로 inventory 제공뿐 아니라 prompt 규칙도 다르다. 자동 경고 수 차이를 inventory만의 순수 인과 효과로 해석하지 않는다.

## 다음 집계에서 확인할 것

- 나머지 변환이 끝나면 O와 각 조건의 VLM generation accuracy 및 paired 회복/회귀를 확인한다.
- Hybrid의 옵션이 Full과 동일한지, stem 선택적 정렬의 이득이 있는지 본다.
- Stem-only의 낮은 parser 실패율이 실제 의미 오류 감소로 이어지는지 검토한다. 이전 NO-GO를 구조 통과율만으로 해제하지 않는다.

진행 중 파일은 완성된 newline 행만 읽었다. 변환은 전체 pair ID가 갖춰진 조건만 요약했고, 정확도는 O/조건 모두 전체 출력이 갖춰져야 계산한다. 숫자는 snapshot 시점 기준이며 계속 증가할 수 있다.

재집계 명령(추론 없음):

```bash
.venv/bin/python followup_rel_4lang/method_dev/scripts/update_two_stage_results.py
```

[집계 snapshot](../artifacts/two_stage_results_snapshot.json) · [Hybrid 설정](HYBRID_CONTROL_KO.md) · [기본 prompt/config](TWO_STAGE_V2_PROTOCOL_KO.md).
