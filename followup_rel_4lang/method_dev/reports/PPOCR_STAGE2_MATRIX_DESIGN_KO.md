# 고정 PP-OCR inventory 이후의 모델·통합·변환 범위 비교 설계

상태: **설계안**. 이 문서만 작성했다. 실행 코드·prompt 파일·frozen artifact는 수정하지 않았고 새로운 inference도 수행하지 않았다. 기존 보고서 수치는 설계의 근거이며 아래 matrix의 새 실험 결과가 아니다.

## 1. 이번에 바꿀 대상

앞으로 편집을 수행하는 부분 전체를 Stage-2라고 부른다. 현재의 `E1 추출 → M0 정렬`이 그 내부 두 단계다.

```text
완료된 PP-OCR inventory ──────────────────────────────────────┐
원본 MCQ + source/GUI language ── Stage-2 편집 모델 ── 코드 조립 ├─ 최종 VLM 풀이
                                                           ┘
```

OCR는 재실행하지 않는다. 기존 Screen/Selection/Internal의 `ppocrv5_cuda/ocr/attempt_*/inventories.jsonl` 중 COMPLETE가 있는 산출물을 이미지 SHA로 연결하고 파일·문자열 hash를 고정한다. 재정규화·후보 선별·문자열 병합·bbox/reading order 추가도 하지 않는다. Main 화면 632개, 실제 Screen pilot까지 포함하면 680개 화면의 기존 결과다.

**편집에 VLM을 쓰는 조건에도 이미지를 주지 않는다.** 동일 OCR 문자열과 MCQ만 주는 native text-only generation이다. 최종 풀이에서만 원본 screenshot을 제공한다. 이미지 편집 VLM으로 바꾸면 모델과 정보량·vision 비용이 함께 달라진다.

## 2. 권장 주 matrix: 2×2×2 = 8조건

| 축 | 수준 1 | 수준 2 |
| --- | --- | --- |
| 편집 모델 | L: 고정 Qwen3-8B LM | V: 최종 solver와 같은 Qwen3-VL을 이미지 없이 사용 |
| 편집 구성 | D: source referent 추출 → 별도 이름 선택/번역 | J: 추출과 이름 선택/번역을 기본 호출 1회로 통합 |
| 변환 범위 | S: stem 참조만 정렬, options 원문 | H: stem 참조 정렬 + options 전체 번역 |

여기서 H의 options는 **GUI 언어로 전체 번역**한다. Options에서 이름 span을 따로 추출하지 않는다. Options까지 referents만 선택적으로 바꾸는 별도 방식과 구분한다.

| 조건 | 편집 모델 | 구성 | Stem | Options | 기본 편집 호출 |
| --- | --- | --- | --- | --- | ---: |
| L-D-S | 고정 LM | 분리 | 추출 후 참조 정렬 | 원문 | 2 |
| L-J-S | 고정 LM | 통합 | 한 응답에서 참조 정렬 | 원문 | 1 |
| V-D-S | 평가 VLM text-only | 분리 | 추출 후 참조 정렬 | 원문 | 2 |
| V-J-S | 평가 VLM text-only | 통합 | 한 응답에서 참조 정렬 | 원문 | 1 |
| L-D-H | 고정 LM | 분리 | 추출 후 참조 정렬 | 전체 번역 | 2 |
| L-J-H | 고정 LM | 통합 | 한 응답에서 참조 정렬 | 전체 번역 | 1 |
| V-D-H | 평가 VLM text-only | 분리 | 추출 후 참조 정렬 | 전체 번역 | 2 |
| V-J-H | 평가 VLM text-only | 통합 | 한 응답에서 참조 정렬 | 전체 번역 | 1 |

**D-H는 추출 1회 + 정렬/options 번역을 합친 1회다.** 별도 full translator를 한 번 더 호출해 stem을 버리는 과거 Hybrid 구현을 그대로 재사용하지 않는다. 그것은 기본 3호출이고 비용 축이 달라진다.

8B solver에서는 V=Qwen3-VL-8B, 4B solver에서는 V=Qwen3-VL-4B다. 두 solver의 matrix를 따로 보고, 8B 고정 LM과 4B VLM 비교에 parameter 수 차이도 포함된다는 점을 명시한다. L의 편집 결과는 solver 정보를 입력하지 않으므로 두 solver에 공유할 수 있다.

### MCQ 전체 번역은 별도 control 2개

| 조건 | 편집 모델 | 변환 | 기본 편집 호출 |
| --- | --- | --- | ---: |
| L-FULL | 고정 LM | Stem·options 전체를 GUI 언어로 번역 | 1 |
| V-FULL | 평가 VLM text-only | Stem·options 전체를 GUI 언어로 번역 | 1 |

FULL은 referent extraction을 요구하지 않으므로 D/J 축을 억지로 적용하지 않는다. H는 stem의 문맥을 source로 남기지만 FULL은 그 문맥도 번역한다. 둘은 같은 조건이 아니다. 과거 parallel `F_REF`와도 구분한다.

따라서 **solver당 핵심 8조건 + control 2조건 = 10조건**을 권장한다. 두 solver면 최종 평가 cell은 20개지만 고정 LM의 5개 편집 recipe를 공유하므로 편집 recipe는 최대 15종이다. 실제 호출 수는 source 캐시·fallback·repair에 따라 달라진다.

Options의 referents만 선택적으로 바꾸는 A 범위는 유용한 추가 진단이지만 H와 섞지 않는다. 필요할 경우 L/V×D/J의 4조건으로 명시적으로 추가한다. 이번 최소 matrix에서는 S/H와 FULL부터 비교한다. 그래야 options extraction을 다시 늘리기 전에 options 전체 처리의 가치부터 볼 수 있다.

## 3. 출력과 코드 치환 계약

권장 기본값은 **stem은 patch, options는 완성된 field**다. 둘을 억지로 같은 span 인터페이스로 표현하지 않는다.

### D: 추출과 선택을 분리

첫 호출은 기존 E1처럼 원문 stem만 보고 referents를 반환한다. 기존 field/text/occurrence 출력과 source 복원 검증을 유지하고, 코드가 offset과 span ID를 만든다. S/H는 편집 모델별로 같은 추출 결과를 공유한다.

두 번째 호출은 S에서 기존 M0의 `translations`를 유지한다. H에서는 같은 선택 결과와 A–D 전체 번역을 함께 받는다. 아래 ID와 문장은 형식 설명용 가상 예시다.

```json
{
  "translations": {"r001": "设置", "r002": null},
  "options": {"A": "账户按钮", "B": "蓝色圆圈", "C": "搜索框", "D": "帮助图标"}
}
```

S에는 options 출력을 요구하지 않고 기존 `translations` schema를 그대로 쓴다. H의 보기 전체를 inventory member 하나로 강제하지 않는다. 보기에는 아이콘 설명·색·관계·화면에 없는 distractor가 있을 수 있기 때문이다.

### J: source span과 선택을 함께 생성

통합 응답은 stem edit 목록을 반환한다. 전체 stem을 자유롭게 생성시키거나, rewritten stem의 diff를 정답 span으로 추정하지 않는다.

```json
{
  "stem_edits": [{"text": "Settings", "replacement": "设置"}],
  "options": {"A": "账户按钮", "B": "蓝色圆圈", "C": "搜索框", "D": "帮助图标"}
}
```

- S는 `stem_edits`만 받는다. H만 `options`를 추가한다.
- Stem만 수정하므로 edit마다 field를 생성하게 하지 않는다.
- `text`는 원본 stem의 정확한 substring, `replacement`는 고정 inventory의 정확한 문자열이어야 한다. 번역된 target을 source text에 넣으면 적용하지 않는다.
- 원문에서 한 번만 나오는 substring은 occurrence를 요구하지 않는다. 반복되어 위치가 모호하면 명시적인 occurrence가 있어 검증될 때만 적용한다. 없으면 첫 출현을 임의로 선택하지 않고 abstain으로 기록한다.
- Offset은 모델에 계산시키지 않는다. 코드가 정확한 원문 위치로 복원한다. 겹치는 span은 거부한다.

기존 E1의 main 631개 고유 추출 payload를 읽기 전용으로 확인한 결과, 반환된 622개 span 중 동일 substring이 stem에 반복된 경우는 1개, nonzero occurrence는 0개였다. 이는 현재 추출된 span만의 관찰이다. 앞으로 통합 모델이 반환할 모든 후보의 모호성이 작다고 보장하지 않는다.

Target은 우선 M0처럼 **inventory 문자열 그대로** 반환하게 한다. Candidate ID로 전면 변경하는 실험을 동시에 섞지 않는다. 과거 M1은 prompt와 ID 출력을 함께 바꿨고 E1/M0보다 정확도가 높지 않았다. 후보 ID가 반드시 나쁘다는 증거도 아니지만, 이번 세 축 외의 새 요인을 추가할 근거도 부족하다.

완성된 stem을 생성하게 하면 source substring/occurrence 오류를 피할 수는 있지만, selective 문맥 보존을 코드로 직접 강제하기 어려워진다. Diff만으로 의미적 참조 경계를 알 수 없고 post-hoc gold span으로 출력을 거절해서도 안 된다. 따라서 우선 patch를 공통 계약으로 두며, source 복원 오류가 다시 병목이면 동일 범위의 완성형 rewrite를 별도 interface 진단으로 다룬다. FULL control은 처음부터 전체 문장 번역을 허용하므로 완성형 field가 맞는 계약이다.

### 코드가 실제로 하는 일

두 구성의 응답을 모두 내부의 `field/start/end/source/replacement` edit 목록으로 정규화한다. 이 IR은 코드 내부 표현이며 모델이 모든 필드를 생성할 필요는 없다.

1. Stem edit의 source 위치·overlap·inventory membership을 검사한다.
2. 검증된 edit를 offset 역순으로 원문 stem에 적용한다. 선택된 span 바깥은 그대로다.
3. S에서는 원본 options를 복사한다.
4. H에서는 A–D 키·string type·누락·새 중복 등을 확인한 완성 options를 해당 field에 넣는다. Source substring을 다시 찾거나 options의 edit list를 역추정하지 않는다.
5. FULL에서는 완성 stem과 options를 고정 field에 조립한다. 선택적 문맥 보존을 만족했다고 주장하지 않는다.

**H의 options 전체 번역에는 inventory membership만으로 검증할 수 없는 의미 변화가 있다.** GUI 이름은 대응 inventory wording을 쓰도록 지시하되, 일반 설명과 화면에 없는 이름까지 억지로 inventory에 맞추지 않는다. 숫자·날짜·부정·방향·종류 변경을 따로 기록하고 대표 사례를 검수한다. 구조 성공을 의미 동등성으로 간주하거나 gold로 번역을 교정하지 않는다.

주 matrix에서 별도 LLM judge나 semantic repair 호출을 추가하지 않는다. 그 비용·모델 편향을 새 축으로 만들지 않기 위함이다. 구조 경고가 없는 명백한 의미 오류도 실패 사례 분석에서 반드시 보고한다.

## 4. 실패 처리

- **Stem과 Options는 독립 component로 검증**한다. H에서 stem 실패가 유효한 options까지 버리거나, options 실패가 유효한 stem까지 버리게 하지 않는다.
- Options는 A–D를 하나의 group으로 취급한다. 새 중복·누락 등의 실패 시 임의의 특정 보기만 살리지 않고 원본 options group으로 돌아간다.
- JSON 자체를 읽을 수 없으면 유효 component도 식별할 수 없으므로 구조 repair를 최대 한 차례 요청한다.
- JSON이 유효하면 정상 component는 고정하고 잘못된 component만 repair한다. Repair가 정상 부분을 새로 바꾸지 못하게 한다.
- D의 source extraction이 최종 실패해도 H는 두 번째 호출에서 options 번역을 할 수 있다. Stem은 원문으로 둔다. S는 extraction 실패 시 원문 유지다.
- 각 model step당 구조 repair 최대 1회다. D는 step이 둘이라 J보다 최대 repair 호출 수가 많을 수 있음을 기록한다. 이것도 실제 pipeline 구성의 비용 차이에 포함된다.
- Stem 안의 여러 edit 중 일부를 임의로 구제하는 per-edit salvage는 이번 primary에 추가하지 않는다. Null/abstention과 잘못된 proposal을 구별해 기록한다.

S의 L-D-S는 기존 E1/M0 prompt·출력·검증 경로를 유지할 수 있으므로 현재 PP 결과를 anchor로 재사용한다. 새로운 parser나 repair가 anchor의 결과를 바꾸면 기존 점수를 덮어쓰지 말고 새 버전의 bridge condition으로 분리한다.

## 5. VLM을 text-only editor로 쓰는 조건

평가 VLM checkpoint를 원래의 Qwen3-VL conditional-generation class로 로드하고, image content/pixel_values/image_grid 입력 없이 text generation한다. Vision 모듈을 떼어낸 별도 LM checkpoint를 만들거나 raw language decoder를 직접 호출하지 않는다. Attention 구현·가중치 수정도 하지 않는다.

기술 점검에서 확인할 것은 input keys, vision token 0, visual forward 0, 실제 model/revision/device/dtype, prefill/decode 시간과 출력 종료다. VLM을 로드했다는 사실만으로 text-only 경로가 정상·고속이라고 가정하지 않는다. 기존 TXT_DIRECT_VLM은 이미지 없는 호출이 있었지만 현재 OCR+E1/M0의 대체 실험과 같은 조건은 아니었다.

V 조건은 최종 풀이와 같은 checkpoint를 쓰므로 모델을 유지한 채 편집 후 풀이로 전환할 수 있다. **새 대화와 새 KV cache로 최종 풀이를 시작**하고, 중간 추출·번역 응답을 solver 대화에 넣지 않는다. 이렇게 해야 CLP식 추론 context 추가 효과가 섞이지 않는다.

Model-resident 실행의 적재 절약과 순수 생성 속도는 따로 보고한다. Text-only 호출에서도 전체 VLM weight가 메모리에 있으므로 vision 계산을 안 한다고 vision weight 메모리까지 사라지는 것은 아니다.

## 6. 통합은 왜 반드시 빨라지지 않는가

현재 PP 8B recipe는 OCR1.22분 + 추출9.61분 + 정렬33.59분 + 풀이22.65분 =67.07분이다. 실제 줄이고 싶은 부분은 LM43.20분이다.

현재 평가에서는 632개 source MCQ가 세 GUI에 반복되고, 실제 stem-only payload는 631개다. 분리형은 그 추출을 공유하지만 통합형은 GUI별로 다시 처리한다. Repair/no-op을 빼고 보면 호출 수는 약631+1,895→1,895로 **약25% 감소**이지 50% 감소가 아니다. Source 하나와 GUI 하나만 있는 단일 요청에서는 2→1의 이점이 더 직접적이다.

과거 VLM inventory를 사용한 Screen에서는 Stem-only 분리의 LM 시간이4.35분, 통합은7.14분이었다. Stem+Options referents 분리9.97분, 통합17.87분이었다. Prompt·출력·inventory가 현재와 다르므로 새 결과의 예측값으로 쓰지 않지만, 호출 감소만으로 속도를 보장할 수 없다는 근거다. 당시 통합 stem은72.08%, all-field referents 통합은74.58%였다.

이전 Hybrid는 Full MCQ 번역 결과에서 options만 가져왔으므로 불필요한 stem 생성과 검증 비용도 포함했다. 이번 H는 처음부터 options를 직접 출력해 이 경로를 없앤다.

단순히 추출9.61분만 없애고 정렬 비용이 같다면 총시간 감소는 약14%다. 반대로 LM 부분이 실제로 절반이 된다면 약45.47분이 된다. 둘 다 조건부 계산이며 실제 ETA나 측정 결과가 아니다. VLM text-only가 고정 LM보다 빠르거나 정확하다는 보장도 없다.

## 7. 비교를 해석할 때의 통제와 한계

- **L↔V:** 같은 구성·범위에서 편집 모델을 바꾼다. Task instruction·입력 정보·schema는 같게 하되 checkpoint 고유 chat template는 유지하고 렌더링을 기록한다.
- **D↔J:** 현재 D의 E1은 stem만 보지만 J는 inventory·MCQ를 처음부터 본다. 따라서 호출 수뿐 아니라 추출 시점 정보·출력·repair 경로까지 포함한 pipeline 비교다. 순수한 호출 분리 효과라고 부르지 않는다. 필요시 inventory를 보는 D 추출을 별도 matched-information 진단으로 둔다.
- **S↔H:** H가 options를 생성하면서 stem 출력도 바꿀 수 있다. 두 조건의 stem 일치율을 반드시 기록한다. Options의 순수 추가 효과가 필요하면 이미 생성한 S stem+H options를 조립하는 진단을 만들 수 있다. 편집 inference는 추가하지 않지만 새로운 최종 MCQ라면 downstream 평가는 필요하다.
- **H↔FULL:** 문맥 변환의 범위가 달라도 options까지 항상 같다고 가정하지 않는다. Field별 차이를 확인한다.
- 기존 R_stem/R/F/O·TT/CLP는 참고 기준으로 유지한다. Oracle source spans나 기존 정오를 새 editor 입력으로 주지 않는다.

## 8. 실행 전 고정할 설정과 평가 항목

현재 checkpoint revision·BF16·SDPA·seed42를 유지한다. 편집 batch1·greedy·고정 LM thinking 비활성, 최종 풀이 batch3·2MP·최대2tokens는 유지한다. 편집 output cap의 초안은 추출768, S 정렬/통합512, H/FULL1,024tokens다. 같은 범위에서는 L/V·D/J에 같은 변환 cap을 적용하고 repair도 같은 cap을 사용한다. D의 추출 예산은 별도로 센다.

이 값은 구현 전 기술 점검으로 확정할 초안이다. 짧은 budget 때문에 정상 출력이 끊기는지와 최대 입력 길이를 확인한 뒤, 정확도를 보고 바꾸지 않고 버전·hash를 고정한다. Silent truncation·검증되지 않은 stop sequence·출력 prefix salvage는 사용하지 않는다.

측정은 최소 다음을 포함한다.

- 같은 pair의 REL accuracy, 회복/회귀, semantic-item bootstrap CI, source/GUI 언어별 결과.
- Stage별 유효 출력·source 복원·overlap·비인벤토리 target·새 중복·cap hit·repair·abstention·component fallback.
- Stem/option 실제 변경과 S/H stem 일치, 숫자·방향·부정 등 의미 손상 사례. Gold 밖 문자 보존은 사후 진단에만 쓰며 method 출력 결정에는 쓰지 않는다.
- 편집 순수 runtime, prefill/decode·입출력 token 수, tokenizer/검증 시간, repair, 모델 적재·전환, 최종 VLM 풀이, 전체 wall.
- source 캐시가 없는 cold recipe와 기존 캐시를 쓰는 이번 신규 실행 비용. 공유 OCR의 새 실행 비용은0이지만 독립 recipe 비교에는 기존1.22분을 포함한다.

최종 MCQ가 같아도 기존과 같은 checkpoint·profile·seed·환경·**전체 ordered batch**가 같을 때만 예측을 재사용한다. 8B/4B 사이에 label을 복사하지 않는다.

## 9. 권장 진행 순서

1. **CPU 준비:** 기존 inventory/입력 lock, 예상 source ambiguity·token budget·출력 계약을 점검한다. 이번 턴에서는 기존 E1 출력의 반복 문자열 빈도만 읽기 전용으로 확인했다.
2. **작은 기능 점검:** 두 평가 VLM의 text-only 경로와 새 S/H/FULL 출력·component fallback을 확인한다. 모델이 문제를 푸는 답 대신 변환 응답을 내고 vision forward가0인지 본다. 아직 수행하지 않았다.
3. **Screen matrix:** 8핵심+2FULL을 같은 Screen main240쌍에서 비교한다. 기존288행 queue와 pilot 분리를 유지한다. 모델·prompt·출력 변경을 한 버전 안에서 몰래 섞지 않는다.
4. **Selection:** 같은 버전을 유지해 비용·정확도 Pareto 후보를 확인한다. 모든 집합은 이미 관찰한 개발 데이터다.
5. **Internal:** 실용적인 후보를 줄여 확장할지, 8조건의 전체 factorial 결과를 얻기 위해 모두 확장할지는 Screen 비용을 본 뒤 정한다. 일부만 확장하면 전체158문항의 완전한 matrix나 독립 holdout 검증이라고 주장하지 않는다.

우선순위는 **V-J-S와 V-J-H가 현재 L-D-S의 정확도를 얼마나 유지하면서 실제 편집 시간을 줄이는가**다. L-J와 V-D도 함께 둬야 개선이 통합 때문인지 모델 교체 때문인지 구분할 근거가 생긴다. 현재는 이 설계까지이며 구현·신규 실험은 다음 단계다.

근거: [현재 PP 방법](PPOCR_STEM_ALIGNMENT_WRAPUP_KO.md), [전체 비용](GPU_OCR_FULL_DEV_RESULTS_KO.md), [과거 stem 통합](SINGLE_PASS_STEM_GUI_KO.md), [과거 all-field 통합](SINGLE_PASS_ALL_GUI_KO.md), [Hybrid의 실제 호출 구조](HYBRID_CONTROL_KO.md), [E1/M0 대 M1](STEM_REFINEMENT_2X2_RESULTS_KO.md).
