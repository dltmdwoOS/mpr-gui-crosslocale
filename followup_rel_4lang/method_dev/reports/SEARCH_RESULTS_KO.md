# Qwen3 선택적 정렬 개발 실험 결과

<!-- AUTO_RESULTS_START -->
집계 기준 (UTC): **2026-11-15T23:01:27+00:00**. 상태: **진행 중 — 완료 조건만 집계**.

이 문서는 실제 GPU 결과만 집계한다. 변환·문제 풀이에 모두 `COMPLETE`가 있는 조건만 정확도 표에 넣고, 진행 중인 출력은 분모에서 제외한다. 원시 결과는 수정하지 않았다. 수동 메모는 자동 생성 영역 밖에 보존한다.

## 1. 현재 핵심 결과

- 내부 평가에서 `GUI_EXACT`: **985/1416 (69.56%)**, O: **997/1416 (70.41%)**. 차이는 **-0.85pp**, 회복17 / 회귀29다. 이 완료된 한 조건의 점추정은 개선을 보이지 않는다.
- Screen main240쌍: GUI_FULL **72.92%**, GUI_EXACT **67.08%**, O **67.50%**. 현재 selective 구현이 full localization보다 낫다는 결과는 아니다.
- Selection의 최고 관측 대조는 `TXT_DIRECT_VLM` **178/239 (74.48%)**. 자동 선택 `GUI_EXACT`는 GUI 후보4개 안에서 고른 잠정 후보이며 전체9조건의 최고를 뜻하지 않는다.
- 추출·matching·edit 프로토콜의 실패가 많이 남아 있다. 특히 원문 span 대신 번역문을 반환하거나 span ID를 잘못 반환하면 안전한 원문 fallback으로 처리됐다. 이를 화면 정보 자체가 효과 없다는 증거로 일반화하지 않는다.
- 독립 화면 검수가 없어 **GUI matching precision은 미측정**이다. Annotation span 경계 일치율을 replacement 정답률로 부르지 않는다.

## 2. 범위와 조건

Qwen3-VL-8B-Instruct가 inventory·시각적 edit·문제 풀이를 수행하고, 고정 Qwen3-8B가 추출·번역·text matching을 맡는다. VL 추출 대조는 전체 VLM을 이미지 없이 호출하며 raw backbone 분리가 아니다. 원본 MCQ·A–D 순서·target screenshot·gold를 고정했다. 정답과 parallel annotation은 사후 평가에서만 사용한다.

| 단계 | Semantic item | 원문 MCQ | pair | 주 accuracy 분모 |
| --- | ---: | ---: | ---: | --- |
| probe | 8 | 32 | 32 | 32 legacy |
| screen | 32 | 128 | 288 | 240 main + 48 legacy 별도 |
| selection | 20 | 80 | 240 | 239 main (전체240은 민감도) |
| internal_evaluation | 118 | 472 | 1416 | 1,416 main |

Screen32개는 pilot12 + calibration20이다. Selection은 나머지 calibration20, 내부 평가는 기존118이다. 사전 제외 `rel::5/forest_9.jpg::zh::ru`는 selection에서만 빠진다. 전체158개는 역사적으로 관찰된 development cohort다. Pilot과 main, 반복 튜닝한 screen과 selection, 내부 평가를 합쳐 하나의 일반화 accuracy로 보고하지 않는다.

| ID | 방법 |
| --- | --- |
| GUI_EXACT | 참조 번역 후 화면 문자열과 exact match |
| GUI_MATCH_LM | LM이 inventory에서 대응 표현 선택 |
| GUI_TARGETED_VLM | 추출한 참조를 화면에서 개별 확인 |
| GUI_DIRECT_VLM | 이미지와 MCQ에서 edit 직접 제안 |
| TXT_SEL | 같은 자동 참조만 text-only 번역 |
| TXT_DIRECT_LM | 고정 LM의 직접 edit |
| TXT_DIRECT_VLM | 이미지 없는 VLM의 직접 edit |
| TXT_FULL | MCQ 전체 text-only 번역 |
| GUI_FULL | Inventory를 제공한 MCQ 전체 번역 |

설정: BF16·SDPA·2MP, patch Conv3D channels_last_3d, method batch1/최대768token, 문제 풀이 batch3/최대2token. 전체 입력4096token 상한이며 초과 시 무음 truncation하지 않는다. 원문에서 복원할 수 없는 edit나 새 중복 보기는 거절하고 원문을 유지한다. 실제 prompt는 [원문 해설](PROMPTS_AND_GO_NO_GO_KO.md)과 [현재 후보 코드](../../../01_code/src/mpr_crosslocale/methods/selective_alignment/search.py), 선택 규칙은 [pipeline/OOM 문서](PIPELINE_OOM_AUDIT_KO.md)를 참고한다.

## 3. 참조 추출 결과

P는 추출한 표현 중 맞은 비율, R은 찾아야 할 표현 중 찾은 비율, F1은 둘을 함께 반영한 값이다. 여기서는 원문 character span의 exact match로 판정한다. 응답 전체가 span 검증에서 실패하면 빈 결과로 포함한다. `검증 실패`에는 JSON syntax뿐 아니라 원문 substring·occurrence·중첩 오류도 들어간다. 정상 빈 목록과 구분한다.

### probe: 32개 원문 MCQ

| 조건 | P | R | F1 | 정상 빈 목록 | 검증 실패 | 완전한 span set | 초/MCQ¹ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cpu_quoted | 100.00% | 38.33% | 55.42% | 0 | 0 | 5/32 | — (미계측 CPU) |
| fixed_original | 69.70% | 12.78% | 21.60% | 0 | 5 | 0/32 | 9.96 |
| fixed_minimal | 61.76% | 23.33% | 33.87% | 0 | 8 | 4/32 | 6.26 |
| fixed_contrastive | 78.95% | 33.33% | 46.88% | 0 | 7 | 4/32 | 6.53 |
| vl_original | 11.76% | 1.11% | 2.03% | 30 | 0 | 0/32 | 6.18 |
| vl_minimal | 46.51% | 11.11% | 17.94% | 8 | 3 | 0/32 | 7.68 |
| vl_contrastive | 38.10% | 22.22% | 28.07% | 0 | 2 | 0/32 | 9.57 |

### screen: 128개 원문 MCQ

| 조건 | P | R | F1 | 정상 빈 목록 | 검증 실패 | 완전한 span set | 초/MCQ¹ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed_contrastive | 81.51% | 39.40% | 53.12% | 0 | 19 | 18/128 | 3.25 |
| fixed_minimal | 74.55% | 40.73% | 52.68% | 0 | 19 | 21/128 | 3.56 |

¹ Load 제외 고유 backend runtime의 평균이며 cache hit도 원래 측정값으로 산입한다. CPU 기준의0 기록은 GPU 호출이 없다는 뜻이지 실제 CPU 시간이0초라는 뜻은 아니다.

Probe에서 VL original은 정상 빈 목록이30/32개였다. 예시를 추가한 VL contrastive는 빈 응답을 줄였지만 낮은 precision이 남았다. 고정 LM도 prompt 보정으로 좋아졌으나, screen fixed_contrastive의 recall39.40%·F1 53.12%라 충분히 해결됐다고 보기 어렵다. CPU quoted의 probe F1이55.42%로 가장 높았지만, 이 조건은 인용부호 한정 진단 기준이라 자동 LM 승격 대상에서 제외됐다.

Screen fixed_contrastive는 minimal보다 precision이 높고 recall은 약간 낮았다. F1 차이는0.45%p로 작으며, 자동 정책은 F1 최고에서0.02 이내면 비용을 비교한다. 이 단계에서는 contrastive가 더 빨라 고정됐다. 이를 모든 언어·문항에서 우월한 prompt라는 결론으로 확대하지 않는다.

Exact span 평가에서는 의미상 타당해 보이는 넓은 표현도 경계가 다르면 틀린 것으로 센다. 이름 없는 아이콘 유지 정책과 annotation 범위의 차이도 별도 검토해야 한다. 반면 원문 text/occurrence 복원 실패와 span 중첩은 로그로 확인한 실제 프로토콜 오류다. CPU 인용부호 기준은 downstream method로 실행하지 않았으므로, 높은 추출 F1만으로 최종 정답률까지 우수하다고 결론 내릴 수 없다.

## 4. 완료된 문제 풀이 결과

각 행의 O는 같은 조건과 짝지어 재실행한 baseline이다. 모든 조건은 실패/fallback을 포함한다. 회복=O 오답→정답, 회귀=O 정답→오답이다.

### probe

O: **20/32 (62.50%)**. O anchor 조건 간 일치: 전부 일치.

| 조건 | 정답/분모 | 정확도 | O 대비 | 회복 | 회귀 | method 초/쌍² |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GUI_EXACT | 23/32 | 71.88% | +9.38pp | 3 | 0 | 20.75 |
| GUI_MATCH_LM | 20/32 | 62.50% | +0.00pp | 1 | 1 | 22.47 |
| GUI_TARGETED_VLM | 22/32 | 68.75% | +6.25pp | 3 | 1 | 10.10 |
| GUI_DIRECT_VLM | 22/32 | 68.75% | +6.25pp | 2 | 0 | 14.44 |
| TXT_SEL | 20/32 | 62.50% | +0.00pp | 2 | 2 | 9.34 |
| TXT_DIRECT_LM | 20/32 | 62.50% | +0.00pp | 3 | 3 | 10.35 |
| TXT_DIRECT_VLM | 18/32 | 56.25% | -6.25pp | 1 | 3 | 7.62 |
| TXT_FULL | 18/32 | 56.25% | -6.25pp | 4 | 6 | 5.72 |
| GUI_FULL | 24/32 | 75.00% | +12.50pp | 6 | 2 | 17.82 |

### screen

O: **162/240 (67.50%)**. O anchor 조건 간 일치: 전부 일치.

| 조건 | 정답/분모 | 정확도 | O 대비 | 회복 | 회귀 | method 초/쌍² |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GUI_EXACT | 161/240 | 67.08% | -0.42pp | 1 | 2 | 7.11 |
| GUI_MATCH_LM | 158/240 | 65.83% | -1.67pp | 12 | 16 | 7.93 |
| GUI_TARGETED_VLM | 157/240 | 65.42% | -2.08pp | 5 | 10 | 3.60 |
| GUI_DIRECT_VLM | 160/240 | 66.67% | -0.83pp | 3 | 5 | 6.77 |
| TXT_SEL | 153/240 | 63.75% | -3.75pp | 13 | 22 | 2.94 |
| TXT_DIRECT_LM | 162/240 | 67.50% | +0.00pp | 19 | 19 | 4.22 |
| TXT_DIRECT_VLM | 160/240 | 66.67% | -0.83pp | 8 | 10 | 3.83 |
| TXT_FULL | 155/240 | 64.58% | -2.92pp | 23 | 30 | 2.41 |
| GUI_FULL | 175/240 | 72.92% | +5.42pp | 37 | 24 | 7.55 |

Legacy pilot48쌍은 위 main 표와 분리한다.

| 조건 | Legacy 정답/48 | 전체288 정답 |
| --- | ---: | ---: |
| GUI_EXACT | 34/48 | 195/288 |
| GUI_MATCH_LM | 32/48 | 190/288 |
| GUI_TARGETED_VLM | 33/48 | 190/288 |
| GUI_DIRECT_VLM | 33/48 | 193/288 |
| TXT_SEL | 31/48 | 184/288 |
| TXT_DIRECT_LM | 31/48 | 193/288 |
| TXT_DIRECT_VLM | 30/48 | 190/288 |
| TXT_FULL | 28/48 | 183/288 |
| GUI_FULL | 35/48 | 210/288 |

### selection

O: **171/239 (71.55%)**. O anchor 조건 간 일치: 전부 일치.

| 조건 | 정답/분모 | 정확도 | O 대비 | 회복 | 회귀 | method 초/쌍² |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GUI_EXACT | 173/239 | 72.38% | +0.84pp | 4 | 2 | 4.99 |
| GUI_DIRECT_VLM | 173/239 | 72.38% | +0.84pp | 6 | 4 | 5.27 |
| TXT_SEL | 172/239 | 71.97% | +0.42pp | 16 | 15 | 2.27 |
| TXT_DIRECT_VLM | 178/239 | 74.48% | +2.93pp | 17 | 10 | 3.38 |
| TXT_FULL | 156/239 | 65.27% | -6.28pp | 20 | 35 | 2.18 |
| GUI_FULL | 173/239 | 72.38% | +0.84pp | 27 | 25 | 5.90 |

제외1쌍을 포함한240쌍에서는 GUI_EXACT·GUI_DIRECT_VLM·GUI_FULL이 각각174/240=72.50%, TXT_DIRECT_VLM은179/240=74.58%였다. Primary239쌍과 혼동하지 않는다.

### internal_evaluation

O: **997/1416 (70.41%)**. O anchor 조건 간 일치: 전부 일치.

| 조건 | 정답/분모 | 정확도 | O 대비 | 회복 | 회귀 | method 초/쌍² |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GUI_EXACT | 985/1416 | 69.56% | -0.85pp | 17 | 29 | 3.34 |

미완료로 제외한 조건: GUI_FULL, TXT_DIRECT_VLM, TXT_FULL, TXT_SEL. 부분 출력으로 정확도를 추정하지 않았다.

² 각 stage 전체 pair에서 공유 가능한 inventory/extraction을 한 번씩 계산한 runtime/쌍이다. Screen 비용은288쌍 기준이지만 정확도 주요 표는 main240쌍이다. CPU 전처리+GPU 실행을 포함하고 모델 load·downstream은 제외한다. 단일 query cold latency도, 이번 실행에서 새로 쓴 시간도 아니다. Stage 간 sample·공유량·cached historical timing이 달라 직접적인 속도 순위로 해석하지 않는다.

## 5. 선택 기록과 해석

Probe→screen 추출 shortlist는 fixed_contrastive/minimal, 고정 추출기는 fixed_contrastive다. Screen의 GUI 후보4개 중 GUI_EXACT와 GUI_DIRECT_VLM을 selection 전에 고정했다. Selection에서는 둘 다173/239였고 method 시간은 각각4.99초/쌍과5.27초/쌍이라 GUI_EXACT가 선택됐다.

중요한 한계는 선택 범위다. TXT_DIRECT_VLM은178/239로 더 높았지만 GUI 후보가 아닌 대조군이라 자동 winner 후보에 포함되지 않았다. GUI_FULL도 전체 번역 대조군이었다. 따라서 `winner=GUI_EXACT`는 전체 방법의 최고 정확도나 GCSA의 성공 판정이 아니다. Screen에서 네 GUI selective 후보 모두 O보다 낮았다는 사실도 보존한다.

Selection에서는 GUI_EXACT의 회복4/회귀2와 GUI_FULL의 회복27/회귀25가 같은 순증가2를 만들었다. 평균 정확도가 같아도 바뀐 문항과 회귀 위험은 다르다. 내부 평가 조건들이 모두 끝나면 같은 관점으로 비교를 추가한다.

## 6. Paired 차이와 불확실성

Semantic item을10,000회 bootstrap한95% CI다. 탐색·선택에 사용한 screen/selection은 확증 검정이 아니다. 내부 평가도 역사적으로 관찰된 development cohort이며, 일부 조건만 완료된 동안 p값이나 최종 승리 판정을 제시하지 않는다.

| 집합 | 대비 | 차이 | 95% CI | Item / pair |
| --- | --- | ---: | --- | ---: |
| screen | GUI_EXACT − O | -0.42pp | [-1.67pp, +0.83pp] | 20 / 240 |
| screen | GUI_EXACT − TXT_SEL | +3.33pp | [-0.83pp, +7.50pp] | 20 / 240 |
| screen | GUI_EXACT − GUI_FULL | -5.83pp | [-11.25pp, -0.42pp] | 20 / 240 |
| screen | GUI_FULL − TXT_FULL | +8.33pp | [+1.25pp, +16.25pp] | 20 / 240 |
| screen | GUI_DIRECT_VLM − TXT_DIRECT_VLM | +0.00pp | [-4.17pp, +4.58pp] | 20 / 240 |
| selection | GUI_EXACT − O | +0.84pp | [-1.67pp, +4.17pp] | 20 / 239 |
| selection | GUI_EXACT − TXT_SEL | +0.42pp | [-6.25pp, +7.08pp] | 20 / 239 |
| selection | GUI_EXACT − GUI_FULL | +0.00pp | [-7.11pp, +7.14pp] | 20 / 239 |
| selection | GUI_FULL − TXT_FULL | +7.11pp | [+0.00pp, +15.00pp] | 20 / 239 |
| selection | GUI_DIRECT_VLM − TXT_DIRECT_VLM | -2.09pp | [-8.82pp, +3.77pp] | 20 / 239 |
| internal_evaluation | GUI_EXACT − O | -0.85pp | [-1.84pp, +0.07pp] | 118 / 1416 |

## 7. GUI 언어별 결과

### screen

| GUI | 분모 | O | GUI_EXACT | GUI_FULL | TXT_SEL | TXT_DIRECT_VLM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| EN | 60 | 75.00% | 75.00% | 85.00% | 66.67% | 76.67% |
| ZH | 60 | 73.33% | 71.67% | 70.00% | 70.00% | 75.00% |
| TH | 60 | 45.00% | 45.00% | 61.67% | 50.00% | 45.00% |
| RU | 60 | 76.67% | 76.67% | 75.00% | 68.33% | 70.00% |

### selection

| GUI | 분모 | O | GUI_EXACT | GUI_FULL | TXT_SEL | TXT_DIRECT_VLM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| EN | 60 | 83.33% | 83.33% | 76.67% | 80.00% | 85.00% |
| ZH | 60 | 71.67% | 73.33% | 80.00% | 75.00% | 73.33% |
| TH | 60 | 50.00% | 51.67% | 55.00% | 55.00% | 60.00% |
| RU | 59 | 81.36% | 81.36% | 77.97% | 77.97% | 79.66% |

### internal_evaluation

| GUI | 분모 | O | GUI_EXACT |
| --- | ---: | ---: | ---: |
| EN | 354 | 81.92% | 80.51% |
| ZH | 354 | 76.27% | 75.14% |
| TH | 354 | 48.59% | 47.74% |
| RU | 354 | 74.86% | 74.86% |

TH GUI는 여러 조건에서 낮지만 단일한 target-language 난이도 효과로 단정하지 않는다. 화면 OCR, 참조 추출, target 표현 선택, 모델의 GUI 이해가 함께 작용한다. Screen에서 GUI_FULL의 TH 개선이 보였지만 다른 집합에서 크기가 달라지고, 개별 언어 표본·CI를 고려해야 한다.

## 8. 실제 변환 범위와 실패 원인

Full 조건의 `edits=[]`는 변환이 없다는 뜻이 아니다. 아래 변경 수는 실제 최종 MCQ를 원본과 비교해 다시 계산했다. Fallback 수와 정상적인 no-op도 구별한다.

### screen

| 조건 | 실제 MCQ 변경/주 분모 | 오류 fallback | 적용 edit 수 | Annotation과 경계 일치³ |
| --- | ---: | ---: | ---: | ---: |
| GUI_EXACT | 61/240 | 34 | 80 | 80/80 |
| GUI_MATCH_LM | 159/240 | 81 | 395 | 360/395 |
| GUI_TARGETED_VLM | 127/240 | 113 | 446 | 379/446 |
| GUI_DIRECT_VLM | 18/240 | 216 | 90 | 50/90 |
| TXT_SEL | 205/240 | 34 | 545 | 441/545 |
| TXT_DIRECT_LM | 229/240 | 11 | 1012 | 731/1012 |
| TXT_DIRECT_VLM | 106/240 | 113 | 461 | 313/461 |
| TXT_FULL | 240/240 | 0 | 전체 번역 | — |
| GUI_FULL | 232/240 | 8 | 전체 번역 | — |

### selection

| 조건 | 실제 MCQ 변경/주 분모 | 오류 fallback | 적용 edit 수 | Annotation과 경계 일치³ |
| --- | ---: | ---: | ---: | ---: |
| GUI_EXACT | 88/239 | 34 | 125 | 117/125 |
| GUI_DIRECT_VLM | 23/239 | 209 | 119 | 70/119 |
| TXT_SEL | 202/239 | 34 | 507 | 419/507 |
| TXT_DIRECT_VLM | 116/239 | 103 | 457 | 277/457 |
| TXT_FULL | 232/239 | 7 | 전체 번역 | — |
| GUI_FULL | 220/239 | 19 | 전체 번역 | — |

### internal_evaluation

| 조건 | 실제 MCQ 변경/주 분모 | 오류 fallback | 적용 edit 수 | Annotation과 경계 일치³ |
| --- | ---: | ---: | ---: | ---: |
| GUI_EXACT | 496/1416 | 169 | 759 | 746/759 |

³ 오직 **source span 경계**가 annotation과 같은지 검사한다. Target replacement의 화면 대응 정답률이 아니다. 같은 문항의 GUI pair 반복을 독립 annotation 사례처럼 취급하지 않는다.

Screen inventory: 고유 이미지128개 중10개 실패했고, 실패10개 모두 출력768token 상한에 도달했다. JSON이 닫히지 않은 실제 응답이 있으므로 token-budget truncation과 일관된 실패다. 화면에 텍스트가 없다는 뜻이 아니다.

Screen main240쌍에서의 fallback 분류:

| 조건 | 원인별 건수 |
| --- | --- |
| GUI_EXACT | 상위 추출 실패 30, JSON 파싱 4 |
| GUI_MATCH_LM | 상위 추출 실패 30, inventory 밖 문자열 43, span ID 누락/추가 6, JSON 파싱 1, 보기 중복 1 |
| GUI_TARGETED_VLM | 상위 추출 실패 30, span ID 누락/추가 83 |
| GUI_DIRECT_VLM | 원문 text/occurrence 복원 실패 212, edit 필드/schema 2, JSON 파싱 1, span 중첩 1 |
| TXT_SEL | 상위 추출 실패 30, JSON 파싱 4 |
| TXT_DIRECT_LM | 원문 text/occurrence 복원 실패 11 |
| TXT_DIRECT_VLM | 원문 text/occurrence 복원 실패 10, edit 필드/schema 103 |
| TXT_FULL | 없음 |
| GUI_FULL | 전체 번역 필드/schema 8 |

특히 직접 시각 edit는 source `text`에 target GUI 문자열을 넣는 오류가 많았다. Targeted VLM은 실제 span ID 대신 예시의 리터럴 `span_id`를 키로 반환하기도 했다. Strict validation은 이런 응답을 전체 원문 fallback으로 처리하므로, 한 잘못된 edit/ID가 같은 응답의 다른 유효 제안도 막을 수 있다. 현재 결과에는 이 정책의 비용이 포함된다. 지금 실행 중인 정책을 중간에 바꾸지는 않았다.

예: `GUI_DIRECT_VLM`, `rel::1/booking_1.jpg::en::zh`. 원래 A: `The 'Adults' input field`. 거절 이유: `Span cannot be recovered from original text`.

```json
{
  "edits": [
    {
      "field": "A",
      "text": "成人",
      "occurrence": 0,
      "replacement": "成人"
    },
    {
      "field": "B",
      "text": "儿童",
      "occurrence": 0,
      "replacement": "儿童"
    },
    {
      "field": "C",
      "text": "客房",
      "occurrence": 0,
      "replacement": "客房"
    },
    {
      "field": "D",
      "text": "退房日期",
      "occurrence": 0,
      "replacement": "退房日期"
    }
  ]
}
```

예: `GUI_TARGETED_VLM`, `rel::1/booking_10.jpg::en::zh`. 원래 A: `Singaporean Dollar`. 거절 이유: `Missing or unexpected span IDs`.

```json
{
  "matches": {
    "span_id": "为你推荐"
  }
}
```

추가 확인: 자기 MCQ에 edit가 없는데 O와 예측이 달라진 건수도 집계했다. 이 경우 batch 동반 입력·padding에 따른 변화를 해당 문항 자체의 localization 효과로 단정하면 안 된다.

| 집합 | 조건 | 자기 edit 없는 정오 전환 |
| --- | --- | ---: |
| screen | GUI_DIRECT_VLM | 1 |
| selection | GUI_EXACT | 1 |
| internal_evaluation | GUI_EXACT | 2 |

## 9. 비용·메모리 실측

완료된 job만 합산한 method 신규 runtime은 **5.58시간**, method model-load 합계는 **8.09분**이다. Downstream·현재 진행 job·상위 스케줄링 대기 시간은 이 합계에 들어가지 않는다. Cache hit 비용을 다시 청구한 합계가 아니다.

| 집합 | 조건 | Method wall 분 | Downstream wall 분 | Method peak GiB | Downstream peak GiB |
| --- | --- | ---: | ---: | ---: | ---: |
| screen | GUI_EXACT | 14.17 | 6.63 | 16.98 | 18.31 |
| screen | GUI_MATCH_LM | 9.78 | 7.23 | 16.98 | 18.31 |
| screen | GUI_TARGETED_VLM | 9.07 | 6.98 | 17.02 | 18.31 |
| screen | GUI_DIRECT_VLM | 25.43 | 6.84 | 17.03 | 18.31 |
| screen | TXT_SEL | 5.92 | 7.13 | 15.43 | 18.31 |
| screen | TXT_DIRECT_LM | 15.27 | 7.25 | 15.40 | 18.31 |
| screen | TXT_DIRECT_VLM | 14.57 | 6.75 | 16.45 | 18.31 |
| screen | TXT_FULL | 8.88 | 7.23 | 15.37 | 18.31 |
| screen | GUI_FULL | 13.35 | 7.41 | 16.98 | 18.31 |
| selection | GUI_EXACT | 20.95 | 5.67 | 16.97 | 18.26 |
| selection | GUI_DIRECT_VLM | 21.61 | 5.32 | 17.02 | 18.24 |
| selection | TXT_SEL | 0.01 | 6.28 | 15.41 | 18.25 |
| selection | TXT_DIRECT_VLM | 14.07 | 6.21 | 16.45 | 18.26 |
| selection | TXT_FULL | 9.20 | 6.26 | 15.33 | 18.25 |
| selection | GUI_FULL | 13.22 | 6.39 | 16.97 | 18.28 |
| internal_evaluation | GUI_EXACT | 79.80 | 25.28 | 16.98 | 18.25 |

Method wall은 cache·모델 교체를 포함한 해당 실행 시간이다. Peak는 generation 구간의 allocated memory이며 CUDA reserved/cold-load 전체 peak와 다르다. Cached call의 peak는 원래 측정값일 수 있다. GPU memory 수치만으로 다른 GPU/배치의 OOM 여부를 보장하지 않는다. 이번 관찰 속도를 이전 단건58–66초나RTX4090 결과와 직접 비교해 디바이스 속도 차이라고 해석하지 않는다.

## 10. Historical O/T/R reference — 신규 자동 method와 분리

기존 ExpA의 완료 예측을 같은 pair ID·정답으로 결합했다. T는 Gemma와 gold span을, R은 parallel reference span을 사용한 역사적 조건이다. 현재 자동 Qwen3 extractor/translator와 정보량·백본이 달라 공정한 순수 모델 대조로 부르지 않는다.

| 집합 | 기존 O | T_REF | R_REF | 현재 O와 기존 O label 일치 |
| --- | ---: | ---: | ---: | ---: |
| screen | 160/240 (66.67%) | 162/240 (67.50%) | 194/240 (80.83%) | 238/240 |
| selection | 169/239 (70.71%) | 169/239 (70.71%) | 196/239 (82.01%) | 233/239 |
| internal_evaluation | 993/1416 (70.13%) | 1004/1416 (70.90%) | 1201/1416 (84.82%) | 1393/1416 |

## 11. 이어서 채울 항목

이 보고서는 아래 명령으로 동일 파일의 자동 생성 영역을 갱신한다. GPU 추론을 실행하지 않으며, 완료된 새 조건만 추가한다. 아래 수동 메모는 유지된다. Pipeline 자체가 만드는 `REPORT_KO.md`와 이 누적 보고서는 서로 다른 파일이다.

```bash
.venv/bin/python followup_rel_4lang/method_dev/scripts/update_search_results_report.py
```

- [ ] 내부 평가 winner + TXT_SEL/GUI_FULL/TXT_FULL/TXT_DIRECT_VLM 전 조건 완료 비교
- [ ] 최종3 primary 대비·CI·Holm 결과와 최종 O anchor 확인
- [ ] 독립 화면 matching 검수와 Thai GUI 실패의 단계별 분리
- [ ] Finalist의 대표 회복·회귀 사례와 원문/최종 MCQ 대조
- [ ] 최종 총 wall·신규 소비 비용·공유 비용·raw artifact 보존 manifest
- [ ] GCSA 개선이 없는 경우도 포함한 최종 개발 결론과 RFA 진행 여부

## 부록 A. 완료 조건의12방향 결과

각 셀은 정답률이다. 분모는 해당 row의N이며, screen/selection/internal의 main primary만 사용한다. Probe는4개 순환 방향이라 제외했다.

### screen

| 언어쌍 | N | O | GUI_EXACT | GUI_MATCH_LM | GUI_TARGETED_VLM | GUI_DIRECT_VLM | TXT_SEL | TXT_DIRECT_LM | TXT_DIRECT_VLM | TXT_FULL | GUI_FULL |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| en→ru | 20 | 75.00% | 75.00% | 75.00% | 75.00% | 75.00% | 70.00% | 75.00% | 70.00% | 75.00% | 75.00% |
| en→th | 20 | 45.00% | 45.00% | 60.00% | 40.00% | 40.00% | 55.00% | 60.00% | 55.00% | 50.00% | 60.00% |
| en→zh | 20 | 80.00% | 80.00% | 80.00% | 80.00% | 85.00% | 80.00% | 85.00% | 85.00% | 80.00% | 85.00% |
| ru→en | 20 | 80.00% | 80.00% | 75.00% | 75.00% | 80.00% | 75.00% | 65.00% | 90.00% | 75.00% | 90.00% |
| ru→th | 20 | 40.00% | 40.00% | 40.00% | 35.00% | 40.00% | 45.00% | 55.00% | 40.00% | 55.00% | 60.00% |
| ru→zh | 20 | 75.00% | 70.00% | 75.00% | 75.00% | 75.00% | 65.00% | 70.00% | 75.00% | 65.00% | 70.00% |
| th→en | 20 | 65.00% | 65.00% | 60.00% | 70.00% | 65.00% | 55.00% | 60.00% | 60.00% | 70.00% | 70.00% |
| th→ru | 20 | 75.00% | 75.00% | 65.00% | 75.00% | 80.00% | 70.00% | 65.00% | 60.00% | 50.00% | 65.00% |
| th→zh | 20 | 65.00% | 65.00% | 65.00% | 60.00% | 65.00% | 65.00% | 60.00% | 65.00% | 60.00% | 55.00% |
| zh→en | 20 | 80.00% | 80.00% | 70.00% | 80.00% | 80.00% | 70.00% | 90.00% | 80.00% | 80.00% | 95.00% |
| zh→ru | 20 | 80.00% | 80.00% | 70.00% | 80.00% | 70.00% | 65.00% | 75.00% | 80.00% | 60.00% | 85.00% |
| zh→th | 20 | 50.00% | 50.00% | 55.00% | 40.00% | 45.00% | 50.00% | 50.00% | 40.00% | 55.00% | 65.00% |

### selection

| 언어쌍 | N | O | GUI_EXACT | GUI_DIRECT_VLM | TXT_SEL | TXT_DIRECT_VLM | TXT_FULL | GUI_FULL |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| en→ru | 20 | 90.00% | 90.00% | 80.00% | 80.00% | 85.00% | 80.00% | 80.00% |
| en→th | 20 | 50.00% | 50.00% | 55.00% | 45.00% | 60.00% | 45.00% | 55.00% |
| en→zh | 20 | 80.00% | 75.00% | 90.00% | 80.00% | 85.00% | 75.00% | 95.00% |
| ru→en | 20 | 75.00% | 80.00% | 75.00% | 80.00% | 75.00% | 75.00% | 70.00% |
| ru→th | 20 | 50.00% | 55.00% | 50.00% | 65.00% | 60.00% | 40.00% | 50.00% |
| ru→zh | 20 | 70.00% | 80.00% | 70.00% | 75.00% | 70.00% | 60.00% | 70.00% |
| th→en | 20 | 80.00% | 75.00% | 80.00% | 70.00% | 85.00% | 75.00% | 75.00% |
| th→ru | 20 | 65.00% | 65.00% | 65.00% | 75.00% | 70.00% | 65.00% | 65.00% |
| th→zh | 20 | 65.00% | 65.00% | 65.00% | 70.00% | 65.00% | 65.00% | 75.00% |
| zh→en | 20 | 95.00% | 95.00% | 95.00% | 90.00% | 95.00% | 85.00% | 85.00% |
| zh→ru | 19 | 89.47% | 89.47% | 89.47% | 78.95% | 84.21% | 73.68% | 89.47% |
| zh→th | 20 | 50.00% | 50.00% | 55.00% | 55.00% | 60.00% | 45.00% | 60.00% |

### internal_evaluation

| 언어쌍 | N | O | GUI_EXACT |
| --- | ---: | ---: | ---: |
| en→ru | 118 | 83.05% | 81.36% |
| en→th | 118 | 50.85% | 51.69% |
| en→zh | 118 | 84.75% | 82.20% |
| ru→en | 118 | 88.98% | 86.44% |
| ru→th | 118 | 49.15% | 47.46% |
| ru→zh | 118 | 80.51% | 80.51% |
| th→en | 118 | 73.73% | 71.19% |
| th→ru | 118 | 65.25% | 65.25% |
| th→zh | 118 | 63.56% | 62.71% |
| zh→en | 118 | 83.05% | 83.90% |
| zh→ru | 118 | 76.27% | 77.97% |
| zh→th | 118 | 45.76% | 44.07% |

## 부록 B. 재현·완료 판정

집계 원본: `followup_rel_4lang/method_dev/artifacts/search_pipeline_v1`. 대응 snapshot은 [search_report_snapshot.json](../artifacts/search_report_snapshot.json)이며 cutoff·입력SHA-256·완료 job 경로·집계값을 보존한다. 데이터/정답/annotation은 현재 audit artifact에서 읽었고, method 실행 입력으로 주입하지 않았다. 새 분석 코드는 실행 중인 pipeline의 코드·설정·raw 결과를 변경하지 않는다. 원시 대용량 산출물은 로컬 artifacts에 유지한다.
<!-- AUTO_RESULTS_END -->

## 검토 메모 — 자동 갱신 시 보존

이 영역에는 추가 해석·질문·후속 분석 메모를 이어 적을 수 있다.
