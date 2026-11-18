# PP-OCRv5 기반 Stem-only Selective Alignment 정리

앞으로 사용할 방법은 **PP-OCRv5 기반 Stem-only Selective Alignment**로 정리한다. 기존 코드의 `E1/M0 + ppocrv5_cuda`이며 새 추출기나 번역기를 추가한 방법이 아니다. Screenshot의 실제 문자열을 이용해 질문 본문(stem)의 GUI 참조 이름만 맞추고, 관계 문맥과 A–D 선택지는 원문 그대로 유지한다.

158개 main text-dependent REL 문항·EN/ZH/TH/RU의 12개 mismatch 방향, 총 1,895쌍에서 내부 개발 평가를 완료했다. 실행에는 기존 pilot 48행과 사전 제외 1행을 남기되 주 분석에서 뺐다. 학습·fine-tuning은 없고 추론 시 정답·gold span·parallel 질문·GT bbox를 사용하지 않는다. 다만 이 개발 집합을 관찰하면서 prompt와 방법을 선택했으므로 독립적인 최종 검증은 아니다.

## 1. 전체 흐름: 5단계

```text
Target GUI screenshot ── PP-OCRv5 ── 화면 문자열 inventory ───────────┐
Original question stem ── 고정 LM ── stem referent spans ──────────┤
Original MCQ + source/GUI language ───────────────────────────────┤
                                                               ↓
                                  고정 LM: 각 referent의 화면 이름 선택
                                                               ↓
                                  코드: stem의 유효한 span만 치환
                                                               ↓
                                  VLM: 수정 MCQ + 원본 screenshot → A–D
```

| 단계 | 담당 | 받는 정보 | 내보내는 정보 |
| --- | --- | --- | --- |
| 1. 화면 읽기 | PP-OCRv5 GPU | Screenshot·알려진 GUI 언어 | 정렬·중복 제거한 화면 문자열 |
| 2. 기준 이름 찾기 | 고정 Qwen3-8B LM | 원본 stem·source 언어 | 원문 참조 이름과 검증된 span |
| 3. 화면 이름 고르기 | 같은 Qwen3-8B LM | 원본 MCQ 전체·spans·inventory·언어 정보 | span ID별 inventory 문자열 또는 null |
| 4. 치환 | 결정적 코드 | 검증된 source span과 교체 문자열 | stem만 바뀐 MCQ |
| 5. 문제 풀기 | Qwen3-VL-8B 또는 4B | 수정 MCQ·원본 screenshot | A/B/C/D 한 글자 |

### Stage 1 — PP-OCRv5로 inventory 생성

질문·선택지·정답을 보지 않고 screenshot만 읽는다. PP-OCRv5 mobile detector와 GUI 언어별 mobile recognizer를 RapidOCR 3.10.0 + Paddle Inference 3.3.0 CUDA13으로 실행한다. EN은 English, ZH는 Chinese, TH는 Thai, RU는 East-Slavic 인식기를 쓴다. ONNX Runtime은 B200 커널 문제로 제외했다.

Raw bbox/text/confidence는 진단용으로 저장한다. LM에는 NFKC·공백 정리·중복 제거·lexical sorting을 거친 문자열만 제공한다. 위치·reading order·confidence를 matching 근거로 넘기지 않는다. Recognition confidence 추가 필터는 없고 text_score=0, detection max side 960, recognition batch 8이다.

### Stage 2 — stem의 실제 GUI 이름 추출

Qwen3-8B에 stem만 주며 screenshot과 options는 주지 않는다. 수정 E1 prompt로 `Settings`, `Export`, 명시적인 페이지 제목 등 **실제로 이름인 최소 원문 표현**을 찾는다. 공간 관계·색·수량·일반적인 “버튼/탭/제목” 같은 종류 설명은 이름으로 취급하지 않는다.

LM은 field=`question_stem`, 원문 substring, occurrence를 JSON으로 반환한다. 코드는 이를 원문에서 복원해 character offset과 span ID를 검증한다. Non-thinking·greedy·batch1·출력 상한768tokens이며 구조/원문 복원이 실패하면 한 차례 repair를 시도한다. 계속 실패하면 그 pair의 원문을 유지한다. 현재 실행에서는 이미 완료한 동일 E1 결과를 재사용했다. 방법의 전체 비용에는 그 원래 추출 시간도 포함한다.

### Stage 3 — inventory를 보면서 교체 표현 선택

**독립 번역 뒤 exact match로 걸러내는 과거 GUI_EXACT와 다르다.** M0 LM은 처음부터 원본 MCQ 전체, 추출된 referents, target GUI inventory를 함께 받는다. 전체 MCQ는 이름의 뜻을 구분하는 문맥이며, 답을 고르는 데 쓰라는 요청이 아니다.

각 span에 대해 inventory의 정확한 문자열 하나 또는 null을 반환한다. Non-thinking·greedy·batch1·출력 상한512tokens다. 새로운 이름을 만들어내거나 stem 전체를 자유롭게 다시 쓰지 않는다. Options는 이 단계의 읽기 전용 문맥이고 번역하지 않는다. E1 추출과 M0 정렬은 별도 호출이며 이전의 통합 LM prompt 실험이 아니다. 별도의 text-only 번역 호출·embedding retrieval·bbox grounding은 없다.

### Stage 4 — 코드로 유효한 부분만 치환

Source offset과 span ID, 모든 비-null 교체 문자열의 inventory membership을 검사한다. 구조 오류는 한 차례 repair하며, 계속 실패하면 원문으로 fallback한다. 불확실한 null은 해당 참조를 그대로 둔다. 유효한 edit를 offset 역순으로 적용하고, 선택된 span 바깥의 문자와 A–D 순서를 그대로 유지한다. 다만 추출 span의 의미적 경계나 선택한 label의 정체성이 맞다는 보장은 아니어서 문항 의미가 손상되는 오류는 남을 수 있다. Per-edit 임의 구제나 options full translation을 추가한 조건이 아니다.

가상 예시: `Which item is below "Settings"?` → `Which item is below "设置"?`. `below`와 영어 선택지들은 그대로다. 이것이 현재 방법의 조작 범위다.

### Stage 5 — 원본 screenshot으로 REL 풀이

수정된 MCQ와 원본 target screenshot을 Qwen3-VL에 제공한다. Inventory를 최종 solver에게 별도 hint로 붙이거나 OCR bbox로 화면을 crop하지 않는다. 기존 GUI reasoning system prompt, BF16·SDPA·2MP·batch3·seed42·greedy·max_new_tokens2를 유지하고 A–D 생성 정답으로 채점한다. Input cap은 4,096 tokens다.

**고정 LM은 두 solver 모두 Qwen3-8B다.** 4B 결과는 최종 VLM이 4B라는 뜻이며 전체 pipeline이 4B 모델만으로 구성됐다는 뜻은 아니다. 명목상 OCR 1회 + LM 2단계 + VLM 1회이고, 코드 치환은 별도 모델 호출이 아니다. 화면·source stem을 재사용하고 fallback/no-op이 있으면 실제 호출 수는 줄어든다.

## 2. O/R/T/F는 무엇이 다른가

| 조건 | Stem 참조 표현 | Options 참조 표현 | 비참조 문맥 | 평가 시 필요한 추가 정보 |
| --- | --- | --- | --- | --- |
| O | Source 원문 | Source 원문 | Source | 없음 |
| T_REF | Gold span을 Gemma로 GUI 언어 번역 | 동일 방식 번역 | Source | Gold source spans |
| R_REF | Parallel GUI-language 표현 | Parallel GUI-language 표현 | Source | Gold spans·병렬 표현 |
| F_REF | Parallel GUI-language 표현 | Parallel GUI-language 표현 | GUI | 병렬 전체 질문 |
| R_stem | Parallel GUI-language 표현 | Source 원문 유지 | Source | Gold stem spans·병렬 표현 |
| 현재 PP-OCR 방법 | 자동 추출·화면 문자열에 맞춘 선택 | Source 원문 유지 | Source | Screenshot OCR inventory |

**T_REF와 Translate-Test(TT)는 별개다.** T_REF는 과거 Experiment A의 gold referent-span 번역 조건이다. TT는 gold span 없이 질문·보기 전체를 영어로 번역한다. F_REF도 이번 자동 full translator가 아니라 병렬 데이터로 만든 reference다. R/F 표현이 실제 screenshot의 exact label이라고 보장되는 것도 아니다.

R/T/F는 자동 method와 정보량이 다른 reference다. 특히 현재 방법은 stem만 바꾸므로 조작 범위가 같은 **R_stem**이 가장 직접적인 reference다. R 전체와의 차이를 모두 stem extraction이나 OCR 품질 탓으로 돌리지 않는다.

## 3. 두 논문에서 이식한 baseline

**Translate-Test — Song et al., Findings NAACL 2025.** [논문](https://aclanthology.org/2025.findings-naacl.144/)과 [저자 코드](https://github.com/yueqis/Multilingual_Visual_Reasoning/tree/c326ad0eeb94c7a7eda76dff57225ad707451bf5)를 근거로 원본 stem·A–D 전체를 English로 번역하고 원본 screenshot으로 푼다. 원 논문의 Google Translate API 대신 고정 Qwen3-8B를 사용했다. EN source는 identity 처리하고, 구조 실패 1회 repair 뒤에도 실패하면 원문 유지다. Inventory는 없다. 최종 VLM은 현재와 같은 label-only 설정이다.

**CLP — Qin et al., EMNLP 2023.** [논문](https://aclanthology.org/2023.emnlp-main.163/)과 [저자 코드](https://github.com/LightChen233/cross-lingual-prompting/blob/affd839ba89745cf181a405395a1b410c41871d5/request.py)를 근거로 LM의 영어 이해 응답을 assistant 대화에 보존한 뒤, VLM이 원본 screenshot을 보고 단계별로 풀게 했다. 원래 GPT-3.5 기반 수학 task를 고정 Qwen3-8B → Qwen3-VL-8B GUI MCQ로 이식했다. LM·VLM 각각 최대512tokens, greedy이며 solver는 마지막 `Answer: A–D`로 채점한다. Inventory는 없다.

둘 다 원 논문 결과를 그대로 재현한 수치가 아니라 **논문 기반 GUI adaptation의 실제 실행 결과**다. CLP는 대화·system prompt·출력 예산이 label-only 방법과 다르므로 같은 token budget의 순수 prompting ablation으로 읽지 않는다. TT와 현재 방법도 inventory뿐 아니라 번역 언어·수정 범위·LM 호출 수가 달라, 두 성능 차이를 GUI evidence 하나의 인과 효과라고 단정하지 않는다.

## 4. 동일 158문항·1,895쌍의 8B 비교

| 조건 | 정답/1,895 | 정확도 | 총 처리 시간 | 비교 성격 |
| --- | ---: | ---: | ---: | --- |
| O · 원본 | 1330 | 70.18% | 17.63분 | 현재 자동 방법의 기준 |
| T · gold-span 번역 | 1335 | 70.45% | 동일 장비 총비용 없음 | Gold-span reference |
| R · 병렬 referent 정렬 | 1591 | 83.96% | 동일 장비 총비용 없음 | Parallel reference |
| F · 병렬 전체 현지화 | 1551 | 81.85% | 동일 장비 총비용 없음 | Parallel reference |
| R_stem · 병렬 stem 정렬 | 1472 | 77.68% | 동일 장비 총비용 없음 | Stem-only parallel reference |
| Translate-Test · 영어 전체 번역 | 1348 | 71.13% | 32.10분 | 외부 연구 GUI 이식 |
| CLP · 영어 이해 후 풀이 | 1250 | 65.96% | 270.14분 | 외부 연구 GUI 이식 |
| PP-OCRv5 Stem-only Alignment | 1420 | 74.93% | 67.07분 | 채택한 자동 방법 |

PP는 O보다 +4.75pp, TT보다 +3.80pp, CLP의 고정 채점 결과보다 +8.97pp다. TT는 32.10분으로 더 저렴하고 PP는 약2.09배 시간을 써 정답72개를 더 맞혔다. PP는 R_stem보다52개(2.74pp), R 전체보다171개(9.02pp), F보다131개(6.91pp) 적다. R/T/F의 gold/parallel 입력 생성·번역 비용이 완전히 측정되지 않았고 장비도 달라 시간 순위에 섞지 않는다.

### Paired 차이와 불확실성

| PP − baseline | 차이 | Item bootstrap 95% CI | 회복/회귀 |
| --- | ---: | --- | ---: |
| O · 원본 | +4.75pp | [+2.58, +7.02]pp | 169/79 |
| T · gold-span 번역 | +4.49pp | [+1.53, +7.49]pp | 249/164 |
| R · 병렬 referent 정렬 | -9.02pp | [-12.19, -5.86]pp | 100/271 |
| F · 병렬 전체 현지화 | -6.91pp | [-10.29, -3.48]pp | 159/290 |
| R_stem · 병렬 stem 정렬 | -2.74pp | [-4.54, -1.00]pp | 40/92 |
| Translate-Test · 영어 전체 번역 | +3.80pp | [+0.90, +6.91]pp | 222/150 |
| CLP · 영어 이해 후 풀이 | +8.97pp | [+5.12, +12.93]pp | 365/195 |

Semantic-item bootstrap 10,000회, seed20261115의 보정 전 탐색 구간이다. 이미 관찰한 개발 자료이고 비교도 사후 구성했으므로 작은 p값을 독립 검증된 우월성으로 해석하지 않는다. 이 CI에는 장비·batch·queue 차이에 따른 실행 변동이 포함되지 않는다.

### Reference 실행 차이

현재 O는 1330/1895(70.18%)지만, T/R와 같은 ExpA 실행의 O는 1322/1895(69.76%), F와 같은 ORCF 실행의 O는 1327/1895(70.03%)다. 문항 범위는 같아도 O anchor가 완전히 같지는 않다.

8B reference는 같은 checkpoint/revision·BF16·SDPA·2MP·system·greedy2tokens다. 다만 과거 T/R는 RTX4090 batch3, F/R_stem은 RTX4090 batch4·혼합 queue였고 현재 자동 방법은 B200 MIG batch3다. 따라서 R/T/F 대비 표는 동일 pair의 역사적 참고 비교이며 동일 실행 환경 재측정은 아니다. F의 alias는 frozen condition의 질문·보기·이미지·정답이 완전히 같은 대표 예측만 사용했다.

### CLP를 읽을 때의 핵심 제한

CLP의 고정 채점 정확도는65.96%지만 최종 파싱 실패가396/1,895건이다. 이 중338건은512token 상한에 도달했고, 별도54건은 명확한 마지막 답의 장식·표기 차이로 거절됐다. 이54건만 사후 형식 완화하면 정답50개가 늘어68.60%지만 이는 공식 점수를 대체하는 새 실험이 아니다. 현재 budget/출력 계약의 실패가 크므로 CLP의 cross-lingual reasoning 아이디어 자체가 열등하다고 결론 내리지 않는다.

## 5. 비용과 4B 적용

| 단계 | 8B recipe | 4B recipe |
| --- | ---: | ---: |
| PP-OCRv5 | 1.22분 | 1.22분 |
| E1 추출 | 9.61분 | 9.61분 |
| M0 정렬 | 33.59분 | 33.59분 |
| 최종 VLM 풀이 | 22.65분 | 20.60분 |
| 합계 | 67.07분 | 65.02분 |

시간은 model-call 구간 합으로, 재사용 호출도 원래 시간을 포함한다. 모델 적재·기동·다운로드를 제외하고 전처리 cache key는 전역 중복 제거, batch 시간은 main pair 비율로 배분했다. 분모는158 item이 아닌1,895 pair이며 단일 요청 latency가 아니다. 4B/8B를 함께 쓰면 전처리를 한 번만 청구해87.67분이다.

| 최종 solver | O | PP-OCR 방법 | O 대비 | 총 recipe |
| --- | ---: | ---: | ---: | ---: |
| Qwen3-VL-8B | 70.18% | 74.93% | +4.75pp | 67.07분 |
| Qwen3-VL-4B | 69.02% | 73.09% | +4.06pp | 65.02분 |

TT/CLP의 현재 완료 실행은8B뿐이다. 4B의 동일범위 F·TT·CLP 비교를 채운 결과는 아니며8B 수치를4B에 복사하지 않는다. 4B O/R/T의 과거 ExpA 집계는 별도로 있지만, 여기서는 원시 pair 재연결이 확인된8B를 모든 baseline의 주 비교로 삼았다.

## 6. 현재 정리와 다음 해석

이 방법의 핵심은 새로운 grounding task나 전체 질문 번역이 아니라 **화면 lexical evidence로 stem의 참조 이름만 정렬**하는 것이다. Options extraction/translation을 생략하고 문맥을 고정해 조작 범위를 줄였다. 가장 가까운 자동 비교는 기존 VLM-inventory E1/M0(8B74.09%·207.26분)이며, PP는74.93%·67.07분으로 시간을 크게 줄였다. 그 정확도 차이의 CI는0을 포함하므로 OCR 교체의 확정적 정확도 우위는 주장하지 않는다.

R_stem의77.68%와는 아직2.74pp 차이가 있다. 이는 남은 추출·화면 이름 대응·치환 이후 REL 실패를 분석할 필요가 있음을 보여주지만, R_stem 자체도 screenshot exact-label oracle이 아니므로 격차 전부를 OCR 오류라고 볼 수 없다. PP의 OCR는 전체 비용의약1.8%여서 이후 효율 개선의 주 대상은 LM 두 단계와 최종 풀이가 된다.

4B에서는 PP−VLM의 GUI별 정답 변화가 ZH+8·TH+6·RU−7로 상쇄됐다. 전체 평균의 작은 이득이 모든 언어에 균일하지 않다. 새 언어별 정책이나 전체366문항·추가 모델 일반화는 이번 wrap-up에서 실행하지 않았다.

[전체 GPU OCR 결과](GPU_OCR_FULL_DEV_RESULTS_KO.md) · [실행 안내](GPU_OCR_FULL_DEV_RUNBOOK_KO.md) · [외부 baseline의 정확한 이식 규칙](EXTERNAL_BASELINES_PROTOCOL_KO.md) · [검증된 비교 snapshot](../artifacts/ppocr_method_wrapup_snapshot.json)

재생성: `.venv/bin/python followup_rel_4lang/method_dev/scripts/wrap_up_ppocr_method.py`. 원시 예측을 읽는 사후 분석이며 추가 inference나 frozen artifact 수정을 하지 않는다.
