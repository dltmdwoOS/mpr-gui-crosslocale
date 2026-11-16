# Qwen3 선택적 정렬 개발 실험 결과

<!-- AUTO_RESULTS_START -->
집계 기준 (UTC): **2026-11-16T03:22:12+00:00**. 상태: **전체 pipeline 완료**.

이 문서는 실제 GPU 결과만 집계한다. 변환·문제 풀이에 모두 `COMPLETE`가 있는 조건만 정확도 표에 넣고, 진행 중인 출력은 분모에서 제외한다. 원시 결과는 수정하지 않았다. 수동 메모는 자동 생성 영역 밖에 보존한다.

## 1. 현재 핵심 결과

- 내부 평가에서 `GUI_EXACT`: **985/1416 (69.56%)**, O: **997/1416 (70.41%)**. 차이는 **-0.85pp**, 회복17 / 회귀29다. 선택된 method의 점추정은 O 대비 개선을 보이지 않는다.
- 완료된 내부 평가 `GUI_FULL`: **1003/1416 (70.83%)**, O 대비 **+0.42pp**, 회복168 / 회귀162.
- 완료된 내부 평가 `TXT_DIRECT_VLM`: **978/1416 (69.07%)**, O 대비 **-1.34pp**, 회복59 / 회귀78.
- 완료된 내부 평가 `TXT_FULL`: **912/1416 (64.41%)**, O 대비 **-6.00pp**, 회복141 / 회귀226.
- 완료된 내부 평가 `TXT_SEL`: **946/1416 (66.81%)**, O 대비 **-3.60pp**, 회복81 / 회귀132.
- GUI_FULL은 순증가가 작아도 많은 문항의 정오를 바꿨다. Selection에서 높았던 TXT_DIRECT_VLM도 내부 평가에서는 O를 넘지 못했다. 작은 선택 집합의 순위를 최종 성능으로 해석하면 안 된다.
- Screen main240쌍: GUI_FULL **72.92%**, GUI_EXACT **67.08%**, O **67.50%**. 현재 selective 구현이 full localization보다 낫다는 결과는 아니다.
- Selection의 최고 관측 대조는 `TXT_DIRECT_VLM` **178/239 (74.48%)**. 자동 선택 `GUI_EXACT`는 GUI 후보4개 안에서 고른 잠정 후보이며 전체9조건의 최고를 뜻하지 않는다.
- 추출·matching·edit 프로토콜의 실패가 많이 남아 있다. 특히 원문 span 대신 번역문을 반환하거나 span ID를 잘못 반환하면 안전한 원문 fallback으로 처리됐다. 이를 화면 정보 자체가 효과 없다는 증거로 일반화하지 않는다.
- 독립 화면 검수가 없어 **GUI matching precision은 미측정**이다. Annotation span 경계 일치율을 replacement 정답률로 부르지 않는다.
- 같은 내부 평가1416쌍의 reference는 T_REF **70.90%**, R_REF **84.82%**, F_REF **82.06%**다. GUI_EXACT의 R 대비 차이는 **-15.25pp**, F 대비 차이는 **-12.50pp**다. 문항 범위는 같지만 과거 실행과의 batch/장비 차이는10절에 명시했다.

현재 내부 평가 진행 상태(파일 진행 수는 집계 시 읽은 참고값):

| 조건 | 상태 | 기록된 문제 풀이/O 행 |
| --- | --- | ---: |
| GUI_EXACT | 변환·문제 풀이·집계 완료 | 2832/2832 |
| GUI_FULL | 변환·문제 풀이·집계 완료 | 2832/2832 |
| TXT_DIRECT_VLM | 변환·문제 풀이·집계 완료 | 2832/2832 |
| TXT_FULL | 변환·문제 풀이·집계 완료 | 2832/2832 |
| TXT_SEL | 변환·문제 풀이·집계 완료 | 2832/2832 |

행 수는 O와 해당 조건을 합친 실행 진행량이다. 완료되지 않은 행에서 정답률을 계산하지 않았다.

## 2. 범위와 조건

Qwen3-VL-8B-Instruct가 inventory·시각적 edit·문제 풀이를 수행하고, 고정 Qwen3-8B가 추출·번역·text matching을 맡는다. VL 추출 대조는 전체 VLM을 이미지 없이 호출하며 raw backbone 분리가 아니다. 원본 MCQ·A–D 순서·target screenshot·gold를 고정했다. 정답과 parallel annotation은 사후 평가에서만 사용한다.

| 단계 | Semantic item | 원문 MCQ | pair | 주 accuracy 분모 |
| --- | ---: | ---: | ---: | --- |
| probe | 8 | 32 | 32 | 32 legacy |
| screen | 32 | 128 | 288 | 240 main + 48 legacy 별도 |
| selection | 20 | 80 | 240 | 239 main (전체240은 민감도) |
| internal_evaluation | 118 | 472 | 1416 | 1,416 main |

Screen32개는 pilot12 + calibration20이다. Selection은 나머지 calibration20, 내부 평가는 기존118이다. 사전 제외 `rel::5/forest_9.jpg::zh::ru`는 selection에서만 빠진다. 전체158개는 역사적으로 관찰된 development cohort다. Pilot과 main, 반복 튜닝한 screen과 selection, 내부 평가를 합쳐 하나의 일반화 accuracy로 보고하지 않는다.

### 단계를 나눈 이유

Probe는 작은 기존 pilot에서 프롬프트가 빈 목록만 내는지, span/JSON 형식을 지키는지와 호출 비용을 확인하는 단계다. Screen은 기존 pilot과 calibration 일부에서 후보를 비교하고 추출기와 구조 shortlist를 고르는 개발 단계다. 자동화 버전은 작은 probe의 우연한 점수로 구조를 버리지 않도록 9개 구조를 모두 screen에서 실행했다.

Selection은 남겨둔 20개 calibration item으로 shortlist 2개를 비교하는 단계다. 그 결과로 선택과 대조 조건을 동결한 뒤 118개 internal evaluation을 실행한다. 내부 평가 결과로 winner를 다시 선택하거나 프롬프트를 수정하지 않는다. 다만 전체 cohort 자체는 역사적으로 관찰됐으므로 이 분할만으로 완전히 독립적인 최종 검증이 되지는 않는다.

### 공통 절차와 O 대조

주 평가 대상은 text-dependent REL의 객관식 문제다. Point나bbox를 출력하는 grounding task의 정확도와 구별한다. 또한 GUI_FULL은 이번에 자동 번역으로 만든 조건이므로, 기존 ORCF의parallel F 입력과 같지 않다. GUI_EXACT도 기존 R_REF를 그대로 사용한 조건이 아니다.

Source는 원래 문제 언어, GUI 언어는 screenshot에 실제 표시된 언어다. Referent는 질문의 기준 요소나 선택지가 가리키는 이름이고, context는 방향·관계·일반 설명이다. 예를 들어 blue Search button에서 바꾸려는 최소 이름은 Search이며 blue와 button은 유지할 문맥이다. Span은 원문에서 교체할 부분의 문자 범위, edit는 그 부분을 어떤 표현으로 바꿀지에 대한 제안이다. Matching은 source 이름과 화면 표기를 연결하는 단계이고, fallback은 검증에 실패한 제안을 버리고 원래 문제를 사용하는 처리다. 이하 Rooms→房间/客房 같은 예시는 절차 설명용 가상 예시이고 실제 성공 출력으로 제시한 것은 아니다.

O는 screenshot과 원본 MCQ를 그대로 평가 VLM에 주는 mismatch 기준이다. 모든 변환 조건도 마지막에는 동일한 Qwen3-VL이 해당 screenshot과 최종 MCQ를 받아 A–D 한 글자를 답한다. Transform 단계가 내놓은 답을 채택하는 실험은 아니다. 정답은 이 마지막 평가 경계에서만 읽는다.

Inventory는 screenshot만 보고 추출한 화면 문자열 목록이다. Query나 A–D를 주지 않으며, 정규화·중복 제거·사전식 정렬 후 공유하므로 위치나 읽기 순서는 전달하지 않는다. 공통 referent extractor는 반대로 source MCQ와 source 언어만 보며 screenshot·inventory·GUI 언어는 보지 않는다. 두 입력 경계를 분리해 화면 어휘의 추가 효과를 비교한다.

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

### 각 변환 실험의 입력·절차·비교 목적

#### GUI_EXACT — 참조 번역 후 화면 문자열과 exact match

원본 MCQ에서 공통 추출기가 찾아낸 표현만 고정 Qwen3-8B로 GUI 언어로 번역한다. 번역기는 표현과 언어 정보를 받으며, 이 단계에서는 screenshot이나 inventory를 보지 않는다. 별도로 평가 VLM이 screenshot만 보고 전사한 inventory를 준비하고, 코드가 번역문과 화면 문자열을 정규화한 뒤 exact match한다. 맞는 문자열만 원문 span에 넣으며, 나머지 문맥과 보기 순서는 코드가 그대로 둔다.

이는 현재 GCSA의 가장 보수적인 구현이다. TXT_SEL과 같은 추출·번역 결과를 사용하면서 화면에 실제로 전사된 표현만 허용하므로, 화면 lexical evidence의 추가 효과를 비교할 수 있다. 가령 번역이 房间인데 inventory에는 客房만 있으면 의미가 가까워도 치환하지 않는다. 화면 근거 없는 표현을 줄이는 대신 동의어·OCR 누락·낮은 추출 recall 때문에 실제 편집을 못 하는 경우가 많아질 수 있다. 독립적인 semantic retrieval이나 LaBSE는 이 조건에 없다.

완료 결과를 따라 읽으면 screen 161/240 (67.08%, O 대비 -0.42pp), selection 173/239 (72.38%, O 대비 +0.84pp), internal_evaluation 985/1416 (69.56%, O 대비 -0.85pp)다.

완료된 내부 평가에서 실제 MCQ 변경은 496/1416쌍, 오류 fallback은 169쌍이었다. 이 결과는 실패와 무변경을 포함한 전체 pair 성능이며, 성공한 출력만 따로 골라 계산한 정확도가 아니다.

#### GUI_MATCH_LM — LM이 inventory에서 대응 표현 선택

공통 추출기가 찾은 source 표현 전체와 target GUI inventory를 고정 Qwen3-8B에 함께 준다. GUI_EXACT의 독립 번역→exact match 대신, LM 한 호출이 각 span ID에 대응하는 inventory 문자열 또는 null을 고른다. 모델은 screenshot과 원래 공간 관계 문장 전체를 보지 않고, 추출된 표현·field·언어·순서 없는 화면 문자열 목록을 본다.

의미상 같은데 독립 번역의 단어 선택이 달라 exact match가 실패하는 문제를 줄이려는 조건이다. 모델이 선택한 문자열이 inventory에 원문 그대로 들어 있는 문자열인지 코드가 다시 검사하며, 입력으로 준 span ID가 빠지거나 추가되어도 응답 전체를 거절한다. 따라서 잘못된 표현을 억제할 수 있지만 올바른 다른 제안도 한 오류와 함께 버려질 수 있다. GUI_EXACT와 비교할 때 추출기는 같고, 대응 결정을 코드가 하느냐 LM이 하느냐가 주된 차이다.

완료 결과를 따라 읽으면 screen 158/240 (65.83%, O 대비 -1.67pp)다.

이 조건은 이번 고정 내부 평가 대상에 포함되지 않았다. 개발 단계까지의 결과와 내부 평가 결과를 혼동하지 않는다.

#### GUI_TARGETED_VLM — 추출한 참조를 화면에서 개별 확인

먼저 공통 text extractor가 source 표현을 찾는다. 그다음 Qwen3-VL에 target screenshot과 모든 추출 표현의 ID·field·원문을 주고, 화면에 명확히 보이는 대응 label 또는 null을 반환하게 한다. 화면 전체 문자열 목록을 먼저 만들지 않으며, 원래 MCQ의 공간 관계 문장 전체도 이 확인 단계에 주지 않는다. Stem과 A–D에서 추출된 표현을 같은 규칙으로 모두 처리한다.

전체 inventory 생성 시간을 줄이고 필요한 label만 화면에서 확인할 수 있는지를 보는 조건이다. GUI_EXACT처럼 독립 inventory membership를 코드로 검증할 수 없으므로, 반환한 표현이 실제 화면 표기인지 별도 검수가 필요하다. Matching 실패가 적다고 자동으로 정확한 grounding이라고 볼 수 없다. 실제 span ID 대신 예시의 span_id라는 키를 반환한 경우도 있어, 현재 정확도에는 시각 인식 외에 출력 인터페이스 실패도 포함된다.

완료 결과를 따라 읽으면 screen 157/240 (65.42%, O 대비 -2.08pp)다.

이 조건은 이번 고정 내부 평가 대상에 포함되지 않았다. 개발 단계까지의 결과와 내부 평가 결과를 혼동하지 않는다.

#### GUI_DIRECT_VLM — 이미지와 MCQ에서 edit 직접 제안

Qwen3-VL 한 호출에 원본 stem·A–D, source/GUI 언어, target screenshot을 주고 교체할 원문 substring과 target label을 함께 제안하게 한다. 별도 referent extractor도 inventory도 사용하지 않는다. 출력은 field·text·occurrence·replacement의 edit 목록이며, 최종 MCQ는 LLM이 자유롭게 다시 쓰지 않고 코드가 source span을 복원해 수정한다.

단계를 통합하면 추출 오류의 전파와 여러 호출 비용을 줄일 수 있는지가 목적이다. TXT_DIRECT_VLM은 같은 VLM·같은 edit 지시에 이미지가 없는 대조다. 다만 GUI_DIRECT_VLM은 전체 이미지와 문제를 함께 보므로, 좋아지더라도 효과를 순수한 lexical alignment에만 귀속할 수 없다. 원문 text 자리에 번역된 label을 넣으면 source span을 복원할 수 없어 전체 원문으로 fallback한다. 따라서 현재 낮은 변경률은 이미지가 무용해서라고 단정할 수 없고, edit 프로토콜을 따르는 능력도 함께 평가한 결과다.

완료 결과를 따라 읽으면 screen 160/240 (66.67%, O 대비 -0.83pp), selection 173/239 (72.38%, O 대비 +0.84pp)다.

이 조건은 이번 고정 내부 평가 대상에 포함되지 않았다. 개발 단계까지의 결과와 내부 평가 결과를 혼동하지 않는다.

#### TXT_SEL — 같은 자동 참조만 text-only 번역

GUI_EXACT와 같은 공통 추출 span과 같은 고정 Qwen3-8B의 표현별 번역 결과를 사용한다. 차이는 inventory와 screenshot을 전혀 사용하지 않고, 번역문을 곧바로 원래 span에 넣는다는 것이다. 번역 대상은 stem의 기준 표현뿐 아니라 A–D 안의 표현도 포함한다. 선택한 span 밖의 원문은 코드로 보존한다.

이는 화면 없이 참조만 번역하는 automatic selective 기준이다. GUI_EXACT와 비교하면 화면 문자열로 제한한 덕분에 생기는 이득과, 제한 때문에 못 바꾼 표현의 손실을 함께 볼 수 있다. 추출기가 문맥을 잘못 span에 포함하면 이 조건도 그 문맥을 번역할 수 있으며, 애초에 추출하지 못한 표현은 그대로 남는다. 역사적 T_REF는 gold span과 Gemma를 썼으므로 TXT_SEL과 같은 실험이 아니다.

완료 결과를 따라 읽으면 screen 153/240 (63.75%, O 대비 -3.75pp), selection 172/239 (71.97%, O 대비 +0.42pp), internal_evaluation 946/1416 (66.81%, O 대비 -3.60pp)다.

완료된 내부 평가에서 실제 MCQ 변경은 1242/1416쌍, 오류 fallback은 169쌍이었다. 이 결과는 실패와 무변경을 포함한 전체 pair 성능이며, 성공한 출력만 따로 골라 계산한 정확도가 아니다.

#### TXT_DIRECT_LM — 고정 LM의 직접 edit

고정 text-only Qwen3-8B가 MCQ 전체와 source/target 언어를 받아 참조 추출과 번역을 한 edit 제안으로 처리한다. Screenshot·inventory와 별도 extraction 결과는 주지 않는다. GUI_DIRECT_VLM 및 TXT_DIRECT_VLM과 같은 edit task 지시를 사용하고, 반환한 원문 위치는 같은 코드로 검증한다.

여러 단계 없이 text-only 모델 한 번으로 selective translation을 수행할 수 있는지를 보는 실용 기준이다. TXT_SEL과 비교하면 같은 고정 LM을 쓰지만 전체 MCQ를 보며 span과 번역을 동시에 결정한다는 차이가 있다. 모델은 target 화면의 실제 단어를 확인할 수 없어 정확한 GUI label을 보장하지 못한다. TXT_DIRECT_VLM과의 차이는 이미지 유무가 아니라 checkpoint·학습 이력·chat template를 포함하므로 단순한 vision 효과로 해석하면 안 된다.

완료 결과를 따라 읽으면 screen 162/240 (67.50%, O 대비 +0.00pp)다.

이 조건은 이번 고정 내부 평가 대상에 포함되지 않았다. 개발 단계까지의 결과와 내부 평가 결과를 혼동하지 않는다.

#### TXT_DIRECT_VLM — 이미지 없는 VLM의 직접 edit

Qwen3-VL의 vision 입력을 비우고, MCQ 전체와 언어 정보만으로 직접 edit 목록을 만들게 한다. GUI_DIRECT_VLM과 같은 VLM 가중치·같은 edit 지시·같은 검증을 사용하되 screenshot을 제거한 조건이다. 고정 text-only Qwen3-8B를 호출하는 TXT_DIRECT_LM과 구별된다.

직접 시각 edit가 좋아질 때 실제로 이미지가 추가 가치를 주는지 확인하는 핵심 대조다. 동시에 별도 inventory/extractor 없이 현재 평가 VLM을 text editor로 쓰는 방법 자체의 성능도 보여준다. 화면 정보는 없으므로 성공하더라도 GUI에서 독립적으로 검증한 alignment라고 부르지 않는다. Selection에서 점수가 높았지만 GUI 구조4개만 자동 winner로 고르는 정책 때문에 선택 후보는 아니었고, 내부 평가의 대조로는 유지했다.

완료 결과를 따라 읽으면 screen 160/240 (66.67%, O 대비 -0.83pp), selection 178/239 (74.48%, O 대비 +2.93pp), internal_evaluation 978/1416 (69.07%, O 대비 -1.34pp)다.

완료된 내부 평가에서 실제 MCQ 변경은 673/1416쌍, 오류 fallback은 644쌍이었다. 이 결과는 실패와 무변경을 포함한 전체 pair 성능이며, 성공한 출력만 따로 골라 계산한 정확도가 아니다.

#### TXT_FULL — MCQ 전체 text-only 번역

고정 Qwen3-8B가 원본 MCQ 다섯 필드를 모두 target GUI 언어로 번역한다. Referent뿐 아니라 방향·관계·설명 문맥과 보기의 자연어 부분도 번역한다. Screenshot·inventory·공통 extraction 결과는 사용하지 않고, 정확한 다섯 필드를 가진 JSON을 받아 최종 MCQ를 구성한다.

Selective 편집보다 단순한 전체 번역이 충분한지 확인하는 기준이다. GUI_FULL과는 translator와 full-translation 지시가 같고 inventory 제공 여부가 다르다. 숫자·필드·중복 보기 등은 코드가 검사하지만 방향·부정·의미 보존 전체를 자동 보장하지는 못한다. 따라서 차이는 언어 이해와 번역 오류가 함께 반영된 pipeline 효과다. Full 조건의 edits 배열이 비어 있어도 실제 MCQ는 크게 바뀔 수 있어, 변경률은 최종 문자열로 다시 계산했다.

완료 결과를 따라 읽으면 screen 155/240 (64.58%, O 대비 -2.92pp), selection 156/239 (65.27%, O 대비 -6.28pp), internal_evaluation 912/1416 (64.41%, O 대비 -6.00pp)다.

완료된 내부 평가에서 실제 MCQ 변경은 1395/1416쌍, 오류 fallback은 21쌍이었다. 이 결과는 실패와 무변경을 포함한 전체 pair 성능이며, 성공한 출력만 따로 골라 계산한 정확도가 아니다.

#### GUI_FULL — Inventory를 제공한 MCQ 전체 번역

평가 VLM이 query 없이 target screenshot을 전사한 inventory를 만들고, 고정 Qwen3-8B가 이 목록과 원본 MCQ를 받아 다섯 필드를 모두 target 언어로 번역한다. 번역 LM에는 screenshot 자체나 위치 정보가 없고, 정렬된 문자열 목록만 lexical evidence로 준다. Referent 추출 단계는 사용하지 않는다.

TXT_FULL과 비교하면 같은 전체 번역에서 화면 어휘가 더해지는 효과를 본다. GUI_EXACT와 비교하면 화면 evidence는 공유하지만 context까지 번역하는 full pipeline과 selective pipeline의 차이를 볼 수 있다. 다만 span 추출·호출 구조도 달라 selectivity 하나의 순수 인과 효과는 아니다. GUI_MATCH_LM과 달리 full 출력의 각 단어가 반드시 inventory member여야 한다는 코드 제약은 없고, 대응이 불확실하면 일반 번역을 할 수 있다. Inventory가 실패해 빈 목록이 들어가도 pair를 버리지 않으므로 그 실패도 주 정확도에 포함된다.

완료 결과를 따라 읽으면 screen 175/240 (72.92%, O 대비 +5.42pp), selection 173/239 (72.38%, O 대비 +0.84pp), internal_evaluation 1003/1416 (70.83%, O 대비 +0.42pp)다.

완료된 내부 평가에서 실제 MCQ 변경은 1335/1416쌍, 오류 fallback은 81쌍이었다. 이 결과는 실패와 무변경을 포함한 전체 pair 성능이며, 성공한 출력만 따로 골라 계산한 정확도가 아니다.

## 3. 참조 추출 결과

P는 추출한 표현 중 맞은 비율, R은 찾아야 할 표현 중 찾은 비율, F1은 둘을 함께 반영한 값이다. 여기서는 원문 character span의 exact match로 판정한다. 응답 전체가 span 검증에서 실패하면 빈 결과로 포함한다. `검증 실패`에는 JSON syntax뿐 아니라 원문 substring·occurrence·중첩 오류도 들어간다. 정상 빈 목록과 구분한다.

### 추출 프롬프트 3종은 무엇이 다른가

`original`은 GUI를 가리키는 최소 표현을 찾되 공간 관계·부정·수량을 제외하라는 기존 지시다. field/text/occurrence와 label/icon/brand 등의 kind를 반환하게 했다. 이것은 이전 빈 목록 현상을 다시 확인하는 기준이며, 이 연구에서 이미 잘 작동한다고 검증된 prompt가 아니다.

`minimal`은 바꿀 대상을 화면에 쓰인 최소 이름으로 더 구체화했다. 색상·button/input field 같은 요소 종류·공간 관계·일반 문맥은 span에 포함하지 않고, 이름 안의 숫자와 파일 확장자는 유지하게 했다. 인용부호가 없어도 이름을 찾고, 이름 없는 아이콘 설명은 그대로 둔다. 일반 kind 분류도 요구하지 않아 original과는 경계 정의뿐 아니라 출력 과제의 복잡도도 달라진다.

`contrastive`는 minimal에 경계·제외 예시를 붙였다. 예를 들어 red Launch button에서는 Launch만, Archive 2024.zip에서는 숫자와 확장자까지 포함하고, 이름 없는 방향 기반 아이콘 설명은 추출하지 않는다는 synthetic 예시다. RU/ZH/TH의 복사 예시도 있다. Benchmark 정답이나 parallel 참조는 예시로 사용하지 않았다. 따라서 비교 대상은 단어 한두 개만 바꾼 prompt가 아니라 예시를 포함한 task instruction이다.

### 모델 2종과 CPU 기준은 어떻게 비교했나

`fixed_original/minimal/contrastive`는 고정 text-only Qwen3-8B를 쓰며 non-thinking template을 명시했다. `vl_original/minimal/contrastive`는 같은 세 지시를 Qwen3-VL에 이미지 없이 준다. 후자는 평가 VLM의 multimodal 학습 후 language weights를 활용하는 비교지만 vision 모듈을 제거한 raw backbone 실험은 아니다. 같은 prompt를 두 모델에 주었으므로 모델별 응답 성향을 볼 수 있고, 한 모델 안에서는 세 prompt의 차이를 볼 수 있다. 모두 같은 generation 상한과 검증 규칙을 사용했다.

`cpu_quoted`는 따옴표 안 문자열을 규칙으로 복사하는 진단 대조다. 빠르고 source span이 명확하지만 따옴표가 없는 이름이나 묘사를 놓친다. 이 조건의 좋은 F1은 따옴표 단서가 유용하다는 결과이며, 전체 언어·GUI를 해결했다는 뜻이 아니다. 이번 정책에서는 LM 후보 승격에서 제외했고 downstream recipe와 결합해 평가하지 않았다.

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

Screen fixed_contrastive는 minimal보다 precision이 높고 recall은 약간 낮았다. F1 차이는0.45%p로 작으며, 자동 정책은 F1 최고에서0.02(2%p) 이내면 비용을 비교한다. 이 단계에서는 contrastive가 더 빨라 고정됐다. 이를 모든 언어·문항에서 우월한 prompt라는 결론으로 확대하지 않는다.

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
| TXT_SEL | 946/1416 | 66.81% | -3.60pp | 81 | 132 | 1.56 |
| TXT_DIRECT_VLM | 978/1416 | 69.07% | -1.34pp | 59 | 78 | 2.75 |
| TXT_FULL | 912/1416 | 64.41% | -6.00pp | 141 | 226 | 1.85 |
| GUI_FULL | 1003/1416 | 70.83% | +0.42pp | 168 | 162 | 3.93 |

미완료로 제외한 조건: 없음. 부분 출력으로 정확도를 추정하지 않았다.

² 각 stage 전체 pair에서 공유 가능한 inventory/extraction을 한 번씩 계산한 runtime/쌍이다. Screen 비용은288쌍 기준이지만 정확도 주요 표는 main240쌍이다. CPU 전처리+GPU 실행을 포함하고 모델 load·downstream은 제외한다. 단일 query cold latency도, 이번 실행에서 새로 쓴 시간도 아니다. Stage 간 sample·공유량·cached historical timing이 달라 직접적인 속도 순위로 해석하지 않는다.

## 5. 선택 기록과 해석

Probe→screen 추출 shortlist는 fixed_contrastive/minimal, 고정 추출기는 fixed_contrastive다. Screen의 GUI 후보4개 중 GUI_EXACT와 GUI_DIRECT_VLM을 selection 전에 고정했다. Selection에서는 둘 다173/239였고 method 시간은 각각4.99초/쌍과5.27초/쌍이라 GUI_EXACT가 선택됐다.

중요한 한계는 선택 범위다. TXT_DIRECT_VLM은178/239로 더 높았지만 GUI 후보가 아닌 대조군이라 자동 winner 후보에 포함되지 않았다. GUI_FULL도 전체 번역 대조군이었다. 따라서 `winner=GUI_EXACT`는 전체 방법의 최고 정확도나 GCSA의 성공 판정이 아니다. Screen에서 네 GUI selective 후보 모두 O보다 낮았다는 사실도 보존한다.

Selection에서는 GUI_EXACT의 회복4/회귀2와 GUI_FULL의 회복27/회귀25가 같은 순증가2를 만들었다. 평균 정확도가 같아도 바뀐 문항과 회귀 위험은 다르다. 아래 완료된 내부 평가에서도 같은 관점으로 읽어야 한다.

내부 평가에서는 GUI_EXACT의 회복17/회귀29와 GUI_FULL의 회복168/회귀162를 비교할 수 있다. GUI_FULL이 정오를 바꾼 수는 330쌍이지만 순변화는 +6개다. GUI_EXACT보다 +18개 맞혔다는 점추정과, item별 변동을 반영한 CI를 함께 봐야 한다.

TXT_DIRECT_VLM은 selection에서 74.48%였지만 내부 평가에서는 69.07%였다. 두 집합의 난이도가 달라 절대값 하락만으로 과적합을 확정할 수는 없지만, 같은 내부 집합의 O 대비 -1.34pp이므로 selection의 우세가 그대로 이어졌다고 볼 수 없다.

완료된 전체 번역 대조에서는 GUI_FULL 70.83%와 TXT_FULL 64.41% 사이에 +6.43pp 차이가 있다. 같은 번역 모델·전체 번역 task에 화면 문자열을 추가한 pipeline이 더 나았다는 관찰이다. 반면 GUI_FULL 자체의 O 대비 차이는 +0.42pp이며 CI도 함께 확인해야 한다. 이를 참조 표현의 alignment 하나만의 인과 효과로 읽거나, 전체 번역이 원본보다 확실히 우수하다고 결론 내리지는 않는다.

## 6. Paired 차이와 불확실성

Semantic item을10,000회 bootstrap한95% CI다. 탐색·선택에 사용한 screen/selection은 확증 검정이 아니다. 내부 평가도 역사적으로 관찰된 development cohort이며, 일부 조건만 완료된 동안 p값이나 최종 승리 판정을 제시하지 않는다.

| 집합 | 대비 | 차이 | 95% CI | Item / pair |
| --- | --- | ---: | --- | ---: |
| screen | GUI_EXACT − O | -0.42pp | [-1.67pp, +0.83pp] | 20 / 240 |
| screen | GUI_EXACT − TXT_SEL | +3.33pp | [-0.83pp, +7.50pp] | 20 / 240 |
| screen | GUI_EXACT − GUI_FULL | -5.83pp | [-11.25pp, -0.42pp] | 20 / 240 |
| screen | GUI_FULL − O | +5.42pp | [+0.00pp, +10.83pp] | 20 / 240 |
| screen | TXT_DIRECT_VLM − O | -0.83pp | [-5.00pp, +2.92pp] | 20 / 240 |
| screen | TXT_FULL − O | -2.92pp | [-7.92pp, +1.67pp] | 20 / 240 |
| screen | TXT_SEL − O | -3.75pp | [-7.92pp, +0.42pp] | 20 / 240 |
| screen | GUI_FULL − TXT_FULL | +8.33pp | [+1.25pp, +16.25pp] | 20 / 240 |
| screen | GUI_DIRECT_VLM − TXT_DIRECT_VLM | +0.00pp | [-4.17pp, +4.58pp] | 20 / 240 |
| selection | GUI_EXACT − O | +0.84pp | [-1.67pp, +4.17pp] | 20 / 239 |
| selection | GUI_EXACT − TXT_SEL | +0.42pp | [-6.25pp, +7.08pp] | 20 / 239 |
| selection | GUI_EXACT − GUI_FULL | +0.00pp | [-7.11pp, +7.14pp] | 20 / 239 |
| selection | GUI_FULL − O | +0.84pp | [-5.88pp, +7.95pp] | 20 / 239 |
| selection | TXT_DIRECT_VLM − O | +2.93pp | [-2.93pp, +10.50pp] | 20 / 239 |
| selection | TXT_FULL − O | -6.28pp | [-16.81pp, +4.18pp] | 20 / 239 |
| selection | TXT_SEL − O | +0.42pp | [-6.25pp, +7.50pp] | 20 / 239 |
| selection | GUI_FULL − TXT_FULL | +7.11pp | [+0.00pp, +15.00pp] | 20 / 239 |
| selection | GUI_DIRECT_VLM − TXT_DIRECT_VLM | -2.09pp | [-8.82pp, +3.77pp] | 20 / 239 |
| internal_evaluation | GUI_EXACT − O | -0.85pp | [-1.84pp, +0.07pp] | 118 / 1416 |
| internal_evaluation | GUI_EXACT − TXT_SEL | +2.75pp | [+0.49pp, +5.16pp] | 118 / 1416 |
| internal_evaluation | GUI_EXACT − GUI_FULL | -1.27pp | [-4.24pp, +1.69pp] | 118 / 1416 |
| internal_evaluation | GUI_FULL − O | +0.42pp | [-2.47pp, +3.25pp] | 118 / 1416 |
| internal_evaluation | TXT_DIRECT_VLM − O | -1.34pp | [-3.18pp, +0.42pp] | 118 / 1416 |
| internal_evaluation | TXT_FULL − O | -6.00pp | [-9.39pp, -2.82pp] | 118 / 1416 |
| internal_evaluation | TXT_SEL − O | -3.60pp | [-6.21pp, -1.06pp] | 118 / 1416 |
| internal_evaluation | GUI_FULL − TXT_FULL | +6.43pp | [+3.39pp, +9.53pp] | 118 / 1416 |

최종 pipeline 집계가 완료되어 다음 내부 평가 primary Holm 보정값을 추가했다. 선택 후 고정 대비의 탐색적 bootstrap p이며 confirmatory claim이 아니다.

| 대비 | Bootstrap p | Holm p |
| --- | ---: | ---: |
| GUI_EXACT-O | 0.0876 | 0.1752 |
| GUI_EXACT-TXT_SEL | 0.0222 | 0.0666 |
| GUI_EXACT-GUI_FULL | 0.4095 | 0.4095 |

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

| GUI | 분모 | O | GUI_EXACT | GUI_FULL | TXT_SEL | TXT_DIRECT_VLM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| EN | 354 | 81.92% | 80.51% | 83.05% | 75.42% | 79.66% |
| ZH | 354 | 76.27% | 75.14% | 73.16% | 72.60% | 74.58% |
| TH | 354 | 48.59% | 47.74% | 49.72% | 52.26% | 50.00% |
| RU | 354 | 74.86% | 74.86% | 77.40% | 66.95% | 72.03% |

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
| TXT_SEL | 1242/1416 | 169 | 3286 | 2798/3286 |
| TXT_DIRECT_VLM | 673/1416 | 644 | 2830 | 1716/2830 |
| TXT_FULL | 1395/1416 | 21 | 전체 번역 | — |
| GUI_FULL | 1335/1416 | 81 | 전체 번역 | — |

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
| internal_evaluation | TXT_FULL | 1 |
| internal_evaluation | GUI_FULL | 1 |

## 9. 비용·메모리 실측

완료된 job만 합산한 method 신규 runtime은 **8.24시간**, method model-load 합계는 **8.83분**이다. Downstream·현재 진행 job·상위 스케줄링 대기 시간은 이 합계에 들어가지 않는다. Cache hit 비용을 다시 청구한 합계가 아니다.

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
| internal_evaluation | TXT_SEL | 0.05 | 26.79 | 15.41 | 18.25 |
| internal_evaluation | TXT_DIRECT_VLM | 65.23 | 25.83 | 16.46 | 18.25 |
| internal_evaluation | TXT_FULL | 44.32 | 26.75 | 15.33 | 18.27 |
| internal_evaluation | GUI_FULL | 51.22 | 26.39 | 16.98 | 18.27 |

Method wall은 cache·모델 교체를 포함한 해당 실행 시간이다. Peak는 generation 구간의 allocated memory이며 CUDA reserved/cold-load 전체 peak와 다르다. Cached call의 peak는 원래 측정값일 수 있다. GPU memory 수치만으로 다른 GPU/배치의 OOM 여부를 보장하지 않는다. 이번 관찰 속도를 이전 단건58–66초나RTX4090 결과와 직접 비교해 디바이스 속도 차이라고 해석하지 않는다.

## 10. O/R/T/F와 같은 범위에서 비교

주 비교는 screen main240쌍, selection main239쌍, internal evaluation main1,416쌍으로 각각 고정한다. 모든 조건에 같은 pair ID·semantic item·source→GUI 언어·정답·보기 순서·원본 이미지 연결을 사용한다. 실패 예측은 오답으로 포함하고, 누락된 reference가 있으면 교집합으로 분모를 줄이지 않고 오류로 중단한다. 과거 ORCF 전체366문항의 요약치를 옮긴 것이 아니라 raw 예측을 현재 cohort와 ExpA의 사전 제외 규칙으로 다시 집계했다. Legacy pilot에는 ExpA T/R가 없어 별도 표를 유지하며 이4조건 비교에 섞지 않는다.

**Reference의 뜻:** T_REF는 annotation span을 Gemma로 번역한 과거 T, R_REF는 annotation span과 parallel 표현을 쓴 과거 R이다. 두 조건은 context를 source 언어로 유지한다. F_REF는 context와 referent 모두 GUI 언어인 parallel F다. 현재 자동 추출을 쓰는 TXT_SEL/GUI_EXACT 및 자동 전체 번역 GUI_FULL과 정보량·입력 생성 방식이 다르다. F_REF는 screenshot exact-label oracle이라고 보장된 조건도 아니다.

### 같은 분모의 정확도

| 조건 | screen (240) | selection (239) | internal evaluation (1,416) |
| --- | ---: | ---: | ---: |
| O_CURRENT | 162/240 (67.50%) | 171/239 (71.55%) | 997/1416 (70.41%) |
| O_EXP_A | 160/240 (66.67%) | 169/239 (70.71%) | 993/1416 (70.13%) |
| O_ORCF | 161/240 (67.08%) | 170/239 (71.13%) | 996/1416 (70.34%) |
| T_REF | 162/240 (67.50%) | 169/239 (70.71%) | 1004/1416 (70.90%) |
| R_REF | 194/240 (80.83%) | 196/239 (82.01%) | 1201/1416 (84.82%) |
| R_ORCF | 194/240 (80.83%) | 196/239 (82.01%) | 1201/1416 (84.82%) |
| F_REF | 192/240 (80.00%) | 197/239 (82.43%) | 1162/1416 (82.06%) |
| GUI_EXACT | 161/240 (67.08%) | 173/239 (72.38%) | 985/1416 (69.56%) |
| GUI_MATCH_LM | 158/240 (65.83%) | 미실행/미완료 | 미실행/미완료 |
| GUI_TARGETED_VLM | 157/240 (65.42%) | 미실행/미완료 | 미실행/미완료 |
| GUI_DIRECT_VLM | 160/240 (66.67%) | 173/239 (72.38%) | 미실행/미완료 |
| TXT_SEL | 153/240 (63.75%) | 172/239 (71.97%) | 946/1416 (66.81%) |
| TXT_DIRECT_LM | 162/240 (67.50%) | 미실행/미완료 | 미실행/미완료 |
| TXT_DIRECT_VLM | 160/240 (66.67%) | 178/239 (74.48%) | 978/1416 (69.07%) |
| TXT_FULL | 155/240 (64.58%) | 156/239 (65.27%) | 912/1416 (64.41%) |
| GUI_FULL | 175/240 (72.92%) | 173/239 (72.38%) | 1003/1416 (70.83%) |

O_CURRENT는 현재 method와 함께 재실행한 O다. O_EXP_A는 R/T와 같은 과거 실행, O_ORCF는 F와 같은 과거 실행의 O이며, 새 method가 아니다. R_REF의 기본 출처는 batch3 ExpA이고, R_ORCF는 F 실행과의 연결 확인용으로 별도 보존한다.

### 각 method의 R/T/F 대비 paired 차이

아래 Δ는 method − reference이며 같은 pair에서 계산했다. 회복/회귀와 item 단위10,000회 bootstrap95% CI는 snapshot JSON에 모든 완료 method에 대해 저장한다. 본문 CI는 선택된 GUI_EXACT와 전체 번역 GUI_FULL을 중심으로 제시한다. 실행 환경 차이로 생기는 변동은 bootstrap CI에 포함되지 않는다.

#### screen

| Method | 정확도 | ΔO_CURRENT | ΔT_REF | ΔR_REF | ΔF_REF |
| --- | ---: | ---: | ---: | ---: | ---: |
| GUI_EXACT | 67.08% | -0.42pp | -0.42pp | -13.75pp | -12.92pp |
| GUI_MATCH_LM | 65.83% | -1.67pp | -1.67pp | -15.00pp | -14.17pp |
| GUI_TARGETED_VLM | 65.42% | -2.08pp | -2.08pp | -15.42pp | -14.58pp |
| GUI_DIRECT_VLM | 66.67% | -0.83pp | -0.83pp | -14.17pp | -13.33pp |
| TXT_SEL | 63.75% | -3.75pp | -3.75pp | -17.08pp | -16.25pp |
| TXT_DIRECT_LM | 67.50% | +0.00pp | +0.00pp | -13.33pp | -12.50pp |
| TXT_DIRECT_VLM | 66.67% | -0.83pp | -0.83pp | -14.17pp | -13.33pp |
| TXT_FULL | 64.58% | -2.92pp | -2.92pp | -16.25pp | -15.42pp |
| GUI_FULL | 72.92% | +5.42pp | +5.42pp | -7.92pp | -7.08pp |

#### selection

| Method | 정확도 | ΔO_CURRENT | ΔT_REF | ΔR_REF | ΔF_REF |
| --- | ---: | ---: | ---: | ---: | ---: |
| GUI_EXACT | 72.38% | +0.84pp | +1.67pp | -9.62pp | -10.04pp |
| GUI_DIRECT_VLM | 72.38% | +0.84pp | +1.67pp | -9.62pp | -10.04pp |
| TXT_SEL | 71.97% | +0.42pp | +1.26pp | -10.04pp | -10.46pp |
| TXT_DIRECT_VLM | 74.48% | +2.93pp | +3.77pp | -7.53pp | -7.95pp |
| TXT_FULL | 65.27% | -6.28pp | -5.44pp | -16.74pp | -17.15pp |
| GUI_FULL | 72.38% | +0.84pp | +1.67pp | -9.62pp | -10.04pp |

#### internal_evaluation

| Method | 정확도 | ΔO_CURRENT | ΔT_REF | ΔR_REF | ΔF_REF |
| --- | ---: | ---: | ---: | ---: | ---: |
| GUI_EXACT | 69.56% | -0.85pp | -1.34pp | -15.25pp | -12.50pp |
| TXT_SEL | 66.81% | -3.60pp | -4.10pp | -18.01pp | -15.25pp |
| TXT_DIRECT_VLM | 69.07% | -1.34pp | -1.84pp | -15.75pp | -12.99pp |
| TXT_FULL | 64.41% | -6.00pp | -6.50pp | -20.41pp | -17.66pp |
| GUI_FULL | 70.83% | +0.42pp | -0.07pp | -13.98pp | -11.23pp |

| 집합 | 대비 | 차이 | 95% CI | 회복 / 회귀 |
| --- | --- | ---: | --- | ---: |
| screen | GUI_EXACT − T_REF | -0.42pp | [-5.83pp, +4.58pp] | 23 / 24 |
| screen | GUI_EXACT − R_REF | -13.75pp | [-22.92pp, -5.00pp] | 10 / 43 |
| screen | GUI_EXACT − F_REF | -12.92pp | [-23.75pp, -2.92pp] | 16 / 47 |
| screen | GUI_FULL − T_REF | +5.42pp | [-0.42pp, +12.08pp] | 38 / 25 |
| screen | GUI_FULL − R_REF | -7.92pp | [-15.42pp, +0.83pp] | 17 / 36 |
| screen | GUI_FULL − F_REF | -7.08pp | [-15.00pp, +1.67pp] | 14 / 31 |
| selection | GUI_EXACT − T_REF | +1.67pp | [-6.67pp, +10.42pp] | 28 / 24 |
| selection | GUI_EXACT − R_REF | -9.62pp | [-19.58pp, +0.42pp] | 16 / 39 |
| selection | GUI_EXACT − F_REF | -10.04pp | [-19.33pp, -0.42pp] | 15 / 39 |
| selection | GUI_FULL − T_REF | +1.67pp | [-4.60pp, +7.92pp] | 32 / 28 |
| selection | GUI_FULL − R_REF | -9.62pp | [-18.91pp, +1.67pp] | 19 / 42 |
| selection | GUI_FULL − F_REF | -10.04pp | [-18.83pp, +0.84pp] | 14 / 38 |
| internal_evaluation | GUI_EXACT − T_REF | -1.34pp | [-4.31pp, +1.69pp] | 144 / 163 |
| internal_evaluation | GUI_EXACT − R_REF | -15.25pp | [-18.64pp, -11.86pp] | 43 / 259 |
| internal_evaluation | GUI_EXACT − F_REF | -12.50pp | [-16.17pp, -8.83pp] | 90 / 267 |
| internal_evaluation | GUI_FULL − T_REF | -0.07pp | [-3.53pp, +3.53pp] | 193 / 194 |
| internal_evaluation | GUI_FULL − R_REF | -13.98pp | [-17.37pp, -10.66pp] | 75 / 273 |
| internal_evaluation | GUI_FULL − F_REF | -11.23pp | [-14.27pp, -8.19pp] | 52 / 211 |

### 실행 계약과 비교의 한계

모델 ID/revision·BF16·SDPA·2MP·system prompt·label-only/greedy/최대2token은 계약상 일치한다. 그러나 ExpA R/T는 batch3, ORCF F는 batch4이며 현재 method는 batch3다. 과거 RTX4090과 현재 B200 MIG, batch 동반 입력·queue와 소프트웨어 일부 버전도 다르다. 따라서 **문항 범위는 맞췄지만 동일 실행 조건으로 재측정한 대조는 아니다.** 작은 차이는 특히 조심해서 읽는다. 새 GPU 추론으로 reference를 재실행한 결과는 아니다.

| 집합 | 현재 O vs ExpA O label 일치 | 현재 O vs ORCF O | ExpA R vs ORCF R | F 대표 조건 |
| --- | ---: | ---: | ---: | --- |
| screen | 238/240 | 237/240 | 240/240 | F: 238, R: 2 |
| selection | 233/239 | 236/239 | 239/239 | F: 239 |
| internal_evaluation | 1393/1416 | 1396/1416 | 1409/1416 | F: 1416 |

ORCF는 동일 pair 안의 동일 질문을 한 번만 추론했다. F가 다른 조건과 정확히 같으면 frozen conditions의 `equivalent_to_condition`을 따라 **질문·보기·이미지·정답·순서가 모두 같은 대표 예측**을 사용했다. Screen의 F238개는 직접 F 예측,2개는 F와 동일한 R 예측이다. 이는 누락을 임의 보간하거나 다른 pair의 답을 복사한 것이 아니다.

### GUI 언어별 reference 비교


#### screen

| GUI | N | O_CURRENT | T_REF | R_REF | F_REF | GUI_EXACT | GUI_FULL |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EN | 60 | 75.00% | 65.00% | 81.67% | 90.00% | 75.00% | 85.00% |
| RU | 60 | 76.67% | 70.00% | 86.67% | 85.00% | 76.67% | 75.00% |
| TH | 60 | 45.00% | 63.33% | 73.33% | 65.00% | 45.00% | 61.67% |
| ZH | 60 | 73.33% | 71.67% | 81.67% | 80.00% | 71.67% | 70.00% |

#### selection

| GUI | N | O_CURRENT | T_REF | R_REF | F_REF | GUI_EXACT | GUI_FULL |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EN | 60 | 83.33% | 78.33% | 90.00% | 90.00% | 83.33% | 76.67% |
| RU | 59 | 81.36% | 79.66% | 81.36% | 79.66% | 81.36% | 77.97% |
| TH | 60 | 50.00% | 61.67% | 78.33% | 70.00% | 51.67% | 55.00% |
| ZH | 60 | 71.67% | 63.33% | 78.33% | 90.00% | 73.33% | 80.00% |

#### internal_evaluation

| GUI | N | O_CURRENT | T_REF | R_REF | F_REF | GUI_EXACT | GUI_FULL |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EN | 354 | 81.92% | 75.71% | 87.85% | 88.98% | 80.51% | 83.05% |
| RU | 354 | 74.86% | 70.06% | 85.03% | 87.29% | 74.86% | 77.40% |
| TH | 354 | 48.59% | 67.51% | 83.62% | 67.80% | 47.74% | 49.72% |
| ZH | 354 | 76.27% | 70.34% | 82.77% | 84.18% | 75.14% | 73.16% |

### R이 맞히지만 현재 GUI_EXACT가 놓치는 사례

다음은 결과 차이에 대한 관찰적 분해다. 우선순위를 둔 상호 배타적 분류로 각 pair를 한 번만 센다. 예를 들어 추출과 inventory가 함께 실패해도 먼저 추출 실패로 분류한다. 이 표만으로 해당 단계가 오답의 단독 원인이라고 입증하지 않는다.

| 집합 | R 정답·method 오답 | Method 정답·R 오답 | 그중 O도 오답이어서 회복을 놓친 수 |
| --- | ---: | ---: | ---: |
| screen | 43 | 10 | 41 |
| selection | 39 | 16 | 38 |
| internal_evaluation | 259 | 43 | 238 |

| 집합 | 관찰된 상태 | Pair 수 |
| --- | --- | ---: |
| screen | 유효 처리·exact match 채택 없음 | 27 |
| screen | 편집 적용 후에도 오답 | 7 |
| screen | 추출 검증 실패 | 6 |
| screen | 후속 번역/출력 검증 실패 | 2 |
| screen | Inventory 생성 실패 | 1 |
| selection | 편집 적용 후에도 오답 | 19 |
| selection | 유효 처리·exact match 채택 없음 | 17 |
| selection | 추출 검증 실패 | 2 |
| selection | 후속 번역/출력 검증 실패 | 1 |
| internal_evaluation | 유효 처리·exact match 채택 없음 | 131 |
| internal_evaluation | 편집 적용 후에도 오답 | 75 |
| internal_evaluation | Inventory 생성 실패 | 15 |
| internal_evaluation | 후속 번역/출력 검증 실패 | 7 |
| internal_evaluation | 추출 검증 실패 | 30 |
| internal_evaluation | 유효 처리·최종 원문 유지 | 1 |

R이 맞히고 method가 틀린 사례에서 source 추출을 별도로 다시 보면 다음과 같다. Annotation span 전부 포함은 recall에 대한 exact 진단이며 과다 추출이나 target matching의 정확성을 보장하지 않는다.

| 집합 | Source span 관찰 | Pair 수 |
| --- | --- | ---: |
| screen | 유효 추출·annotation span 일부/전체 누락 | 31 |
| screen | 유효 추출·annotation span 전부 포함 | 6 |
| screen | 추출 검증 실패 | 6 |
| selection | 유효 추출·annotation span 일부/전체 누락 | 27 |
| selection | 유효 추출·annotation span 전부 포함 | 10 |
| selection | 추출 검증 실패 | 2 |
| internal_evaluation | 유효 추출·annotation span 일부/전체 누락 | 175 |
| internal_evaluation | 유효 추출·annotation span 전부 포함 | 54 |
| internal_evaluation | 추출 검증 실패 | 30 |

### Method를 더 개발할 때 우선할 일

현재 결과는 GCSA의 이득을 입증하지 못했고, R/F reference와의 격차가 크다. 여러 prompt를 실행했다는 사실만으로 구현이 충분히 성숙했다고 볼 수 없다. 일부 구조는 출력 계약과 coverage가 불안정한 상태로 큰 비교에 들어갔다. 다음 버전에서는 소규모 개발 표본에서 유효한 편집이 실제로 적용되는지 먼저 확인하고, 아래 병목을 분리해서 해결해야 한다.

1. **출력 인터페이스를 단순화한다.** 정답 annotation이 아닌 자동으로 얻고 원문에서 검증한 source 후보와 screenshot inventory 후보에만 안정적인 ID를 부여하고, 모델은 source ID→target 후보 ID/null을 고르게 하는 후보를 검토한다. 모델이 원문을 번역해 `text`에 넣거나 literal span_id를 반환하는 문제를 줄이는 것이 목적이다. 올바른 edit까지 한 오류 때문에 모두 버리는 정책도 per-edit 유효성·중복 보기·문맥 보존을 유지하면서 별도 ablation으로 비교한다.

2. **낮은 coverage의 원인을 나눈다.** 추출 recall, 원문 검증 실패, OCR 누락, 동의어 때문에 생긴 exact-match 거절, 실제 잘못된 label 선택을 따로 본다. Source 이름이 이미 주어진 뒤에도 matching이 실패하는지 oracle-span 진단으로 확인할 수 있지만, 이는 oracle_span 결과로 명시하고 automatic method 성능으로 합치지 않는다.

3. **Inventory의 잘림을 먼저 해결한다.** 출력 상한에 걸린 JSON 실패가 확인됐다. Compact 출력·중복 억제·필요시 query-blind 분할 전사 또는 출력 budget 확장을 각각 분리된 버전으로 검증한다. 더 긴 출력이나 crop은 비용과 정보량도 바꾸므로 prompt 보정과 동시에 섞어 성능 원인을 흐리지 않는다.

4. **Exact match를 넘어서는 대응을 안정화한다.** 단순 번역의 동의어를 화면 label에 연결하는 능력이 필요하다. ID 기반 inventory 선택과 독립 화면 검수를 우선하고, confidence는 확률처럼 취급하지 않는다. Span 경계 일치율이 높아도 target label이 틀릴 수 있다.

5. **선택과 검증 범위를 정직하게 관리한다.** 현재118개 내부 평가 결과도 이미 관찰했다. 이를 보고 v2를 고치고 같은 집합을 다시 사용하면 untouched evaluation이 아니라 development iteration이다. 기존 frozen artifact는 유지하고 변경 버전을 새로 기록한다. 최종 일반화는 별도 단계다. GUI 후보 최선과 전체 실용 baseline 최선도 나눠 보고하며, TXT_DIRECT_VLM을 포함해 고르는 것만으로 문제가 해결된다고 가정하지 않는다.

이 항목들은 현재 실패에 근거한 다음 개발 우선순위다. 새 method를 구현·실측해서 개선됐다는 결과가 아니며, 진행 중인 실험이나 reference artifact는 수정하지 않았다.

## 11. 이어서 채울 항목

이 보고서는 아래 명령으로 동일 파일의 자동 생성 영역을 갱신한다. GPU 추론을 실행하지 않으며, 완료된 새 조건만 추가한다. 아래 수동 메모는 유지된다. Pipeline 자체가 만드는 `REPORT_KO.md`와 이 누적 보고서는 서로 다른 파일이다.

```bash
.venv/bin/python followup_rel_4lang/method_dev/scripts/update_search_results_report.py
```

- [x] 내부 평가 winner + TXT_SEL/GUI_FULL/TXT_FULL/TXT_DIRECT_VLM 전 조건 완료 비교
- [x] 최종3 primary 대비·CI·Holm 결과와 최종 O anchor 확인
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

| 언어쌍 | N | O | GUI_EXACT | TXT_SEL | TXT_DIRECT_VLM | TXT_FULL | GUI_FULL |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| en→ru | 118 | 83.05% | 81.36% | 76.27% | 81.36% | 78.81% | 83.05% |
| en→th | 118 | 50.85% | 51.69% | 50.85% | 47.46% | 33.05% | 44.92% |
| en→zh | 118 | 84.75% | 82.20% | 80.51% | 83.05% | 71.19% | 77.12% |
| ru→en | 118 | 88.98% | 86.44% | 79.66% | 83.90% | 78.81% | 85.59% |
| ru→th | 118 | 49.15% | 47.46% | 55.08% | 48.31% | 50.85% | 53.39% |
| ru→zh | 118 | 80.51% | 80.51% | 73.73% | 77.97% | 66.95% | 75.42% |
| th→en | 118 | 73.73% | 71.19% | 63.56% | 73.73% | 70.34% | 78.81% |
| th→ru | 118 | 65.25% | 65.25% | 58.47% | 64.41% | 65.25% | 72.03% |
| th→zh | 118 | 63.56% | 62.71% | 63.56% | 62.71% | 57.63% | 66.95% |
| zh→en | 118 | 83.05% | 83.90% | 83.05% | 81.36% | 84.75% | 84.75% |
| zh→ru | 118 | 76.27% | 77.97% | 66.10% | 70.34% | 70.34% | 77.12% |
| zh→th | 118 | 45.76% | 44.07% | 50.85% | 54.24% | 44.92% | 50.85% |

## 부록 B. 재현·완료 판정

집계 원본: `followup_rel_4lang/method_dev/artifacts/search_pipeline_v1`. 대응 snapshot은 [search_report_snapshot.json](../artifacts/search_report_snapshot.json)이며 cutoff·입력SHA-256·완료 job 경로·집계값을 보존한다. 데이터/정답/annotation은 현재 audit artifact에서 읽었고, method 실행 입력으로 주입하지 않았다. 새 분석 코드는 실행 중인 pipeline의 코드·설정·raw 결과를 변경하지 않는다. 원시 대용량 산출물은 로컬 artifacts에 유지한다.
<!-- AUTO_RESULTS_END -->

## 검토 메모 — 자동 갱신 시 보존

이 영역에는 추가 해석·질문·후속 분석 메모를 이어 적을 수 있다.

### Oracle source-span 후속 진단 완료

기존 탐색 조건을 다시 실행하지 않고, **자동 추출 span만 annotation으로 교체한 GUI_EXACT**를 세 cohort에서 실행했다. 실제 GPU 실행 1,944쌍, primary main 1,895쌍을 검증했다. 위 자동 생성 영역은 기존 automatic method 탐색 기록이며, 아래 Oracle은 별도 diagnostic이다.

| Primary 집합 | N | Automatic | Oracle | Oracle − Automatic | O |
| --- | ---: | ---: | ---: | ---: | ---: |
| Screen main | 240 | 67.08% | 67.50% | +0.42pp | 67.50% |
| Selection | 239 | 72.38% | 72.80% | +0.42pp | 71.55% |
| Internal | 1,416 | 69.56% | 71.54% | +1.98pp | 70.41% |

Internal의 Oracle−Automatic 95% CI는 [+0.42, +3.67]pp, 회복/회귀는 52/24다. Oracle−O는 +1.13pp이며 CI [-0.71, +3.04]pp는 0을 포함한다. Thai GUI에서 +24개의 순증가가 관찰됐다. 추출 교정은 유용했지만 R_REF 84.82%와의 차이 13.28pp는 남는다.

기존 R 정답·Automatic 오답 259건 중 44건을 회복했고, R과 Automatic이 맞힌 21건을 새로 잃어 R 정답·Oracle 오답은 236건이었다. 편집 수가 759→1,904개로 늘어도 성능 이득은 제한적이었다. 다음 진단은 같은 Oracle span을 유지한 상태에서 번역과 inventory 표현의 불일치·OCR 누락·부분 치환을 구분하는 것이다. 추출 recall만이 원인이라고 확정하거나, Oracle을 automatic method 결과로 합치지 않는다.

[상세 보고서: ORACLE_RESULTS_KO.md](ORACLE_RESULTS_KO.md)에 O/R/T/F 비교, 전체 CI·언어별 결과, 단계별 실패, raw 회복·회귀 예시와 비용을 정리했다. 이 메모는 기존 보고서 자동 갱신 시 유지된다.
