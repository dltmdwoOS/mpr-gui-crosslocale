# PP-OCR 편집 모델·통합·범위 비교 실행

## V-D-S와 V-D-H의 Selection/Internal 확장

완료된 Screen 결과를 연결하고 **V-D-S와 V-D-H만 8B·4B에서** Selection, Internal 순서로 실행한다. 같은 모델에서 두 조건이 stem 추출을 공유한다. 편집과 풀이에는 Screen과 같은 프롬프트·checkpoint·decoding을 사용한다. PP-OCR inventory 및 O/L-D-S 예측은 각 집합의 완료 결과를 연결한다.

```bash
nohup bash followup_rel_4lang/method_dev/scripts/run_editor_matrix_remaining.sh >> followup_rel_4lang/method_dev/artifacts/ppocr_editor_matrix_vd_full_dev_v1.log 2>&1 < /dev/null &
```

추가 평가 입력은 조건·모델당 1,656쌍이며 두 조건과 두 모델을 합하면 6,624행이다. 동일한 기존 풀이 배치는 재사용한다. 주 집계에는 Selection 239쌍과 Internal 1,416쌍을 추가해 Screen을 포함한 158문항·1,895쌍을 비교한다. 같은 명령으로 재개할 수 있다. 결과는 `artifacts/ppocr_editor_matrix_vd_full_dev_v1/REPORT_KO.md`와 `results.json`에 집합별·전체 기준으로 기록한다.

## 기존 Screen matrix

이번 실행은 **Screen main20문항×12언어쌍=240쌍**에서 새7조건을 Qwen3-VL-8B·4B로 각각 평가한다. 기존 queue를 유지해 조건당288행을 실행하지만 pilot48행은 주 정확도·시간 분모에서 제외한다. Selection/Internal과 FULL control은 이번 명령에 포함하지 않는다.

| 조건 | 편집 모델 | 구성 | Stem | Options |
| --- | --- | --- | --- | --- |
| L-D-S · 재사용 | Qwen3-8B | E1 추출→M0 선택 | 참조만 정렬 | 원문 |
| L-D-H | Qwen3-8B | 추출→선택·보기 번역 | 참조만 정렬 | 전체 GUI 언어 번역 |
| L-J-S | Qwen3-8B | 추출·선택 통합 | 참조만 정렬 | 원문 |
| L-J-H | Qwen3-8B | 추출·선택·보기 번역 통합 | 참조만 정렬 | 전체 GUI 언어 번역 |
| V-D-S | 최종 VLM text-only | E1 추출→M0 선택 | 참조만 정렬 | 원문 |
| V-D-H | 최종 VLM text-only | 추출→선택·보기 번역 | 참조만 정렬 | 전체 GUI 언어 번역 |
| V-J-S | 최종 VLM text-only | 추출·선택 통합 | 참조만 정렬 | 원문 |
| V-J-H | 최종 VLM text-only | 추출·선택·보기 번역 통합 | 참조만 정렬 | 전체 GUI 언어 번역 |

V는8B solver에서8B,4B solver에서4B다. 고정 LM의3개 새 편집 결과를 두 solver에 공유하므로 새 편집 recipe는11개, 새 최종 평가 cell은14개다. 최종 예측4,032행 중 주 분석3,360행이다. 완전히 동일한 ordered batch는 기존 최종 예측을 재사용하므로 실제 신규 GPU 풀이 수는 이보다 적을 수 있다.

## 실행

Repository 루트에서:

```bash
nohup bash followup_rel_4lang/method_dev/scripts/run_editor_matrix.sh > followup_rel_4lang/method_dev/artifacts/ppocr_editor_matrix_screen_v2.log 2>&1 < /dev/null &
```

같은 명령으로 중단 지점부터 재개한다. 실행 중 중복 실행은 lock으로 거절한다. 코드·입력·기존 산출물 hash가 달라지면 같은 디렉터리를 덮어쓰지 않고 중단한다. 변경된 프로토콜은 새 `--output-dir`을 사용한다.

```bash
tail -f followup_rel_4lang/method_dev/artifacts/ppocr_editor_matrix_screen_v2.log
```

실행 순서는 고정 LM 편집→8B VLM text-only 편집 및7조건 풀이→4B 동일 작업이다. 진행 로그에 source 추출 수, 조건별 편집 수·상태·호출 수, 최종 batch 진행·재사용 여부가 표시된다. GPU에는 모델 하나만 적재한다. 새로운 설치·다운로드·OCR 추출은 하지 않는다.

## 프롬프트·출력·실패 처리

- D의 추출은 기존 E1 prompt와 stem-only 입력을 유지한다. Options·inventory를 추출기에 주지 않는다. 같은 모델의 D-S/H가 추출 결과를 공유한다.
- D-S는 기존 M0 prompt·`translations` schema와 검증을 그대로 사용한다. L-D-S는 기존 PP 실행의 결과와 시간을 연결하며 다시 실행하지 않는다.
- D-H는 두 번째 응답에 `translations`와 완성된 `options`를 함께 받는다. 별도 전체 MCQ 번역을 추가 호출하지 않는다.
- J는 원본 MCQ와 inventory를 한 번에 보고 `stem_edits:[{text,replacement}]`를 반환한다. 반복되는 원문에는 명시적인 occurrence가 필요하다. 유일한 substring은 occurrence 없이 복원한다. 원문 전체 stem을 재생성시키지 않는다.
- Stem replacement는 inventory의 정확한 문자열만 허용한다. Options는 inventory 문자열 하나일 필요가 없다. 이름 외의 설명·아이콘·distractor도 의미를 보존해 번역해야 한다.
- H의 stem과 options group을 따로 검증한다. 정상 component를 고정하고 잘못된 component만 최대1회 repair한다. Stem의 여러 edit 중 임의의 일부를 구제하지 않는다. Options는 A–D 전체가 하나의 group이다.
- Semantic warning은 기록만 하며 repair/fallback의 기준으로 쓰지 않는다. Gold나 기존 정오로 편집을 교정하지 않는다.

모든 실제 system/user 메시지와 렌더링·prompt hash는 call cache 및 rewritten JSONL의 `attempts`에 보존한다. 추출·선택·통합·최종 풀이 프롬프트는 생성 응답과 분리해서 확인할 수 있다. Native VLM text-only 호출에는 이미지가 없고, 최종 풀이는 screenshot을 넣은 새 대화로 시작한다. 중간 응답이나 KV cache는 solver에 전달하지 않는다.

## 고정 설정과 메모리

기존 revision의 Qwen3-8B, Qwen3-VL-8B-Instruct, Qwen3-VL-4B-Instruct를 사용한다. BF16·SDPA·seed42·greedy를 유지한다. 고정 LM thinking은 끈다. 편집 batch1, 입력 상한4,096tokens, E1 출력768, S 출력512, H 출력1,024tokens다. Repair도 해당 단계와 같은 출력 상한이다. 입력이 상한을 넘으면 조용히 자르지 않고 중단한다.

최종 풀이는 기존 batch3·최대2MP·입력4,096·출력2tokens·label scoring을 유지한다. Text-only 편집에는 vision 계산이 없지만 전체 VLM 가중치는 메모리에 존재한다. 모델 적재 전40GiB 이상 여유를 요구하며 다른 모델을 동시에 적재하지 않는다. 기존 최종 풀이 설정을 그대로 사용하므로 별도 최대 batch 탐색은 하지 않는다.

## 측정과 결과 위치

`artifacts/ppocr_editor_matrix_screen_v2/REPORT_KO.md`와 `results.json`을 actor 완료마다 갱신한다. 미완료 cell의 일부 정확도를 완성된 결과처럼 보고하지 않는다. 각 actor의 `rewrite/조건/rewritten.jsonl`, `infer/조건/predictions.jsonl`, `cache/`, `calls_*.json`, `cost_*.json`에 원시 결과를 보존한다.

측정 항목:

- 정확도·O/L-D-S 대비 item-cluster bootstrap95% CI·회복/회귀·source/GUI 언어별 및12언어쌍 결과·worst pair.
- 추출의 사후 exact-span precision/recall/F1, 추출 실패, 원문 복원·overlap·inventory 밖 target·옵션 중복 등 검증 오류, repair·cap hit·abstention·component fallback.
- 실제 stem/options 변경, S/H stem 일치율, 숫자·방향·부정 변화 heuristic. 의미 보존을 검증했다는 뜻은 아니다.
- 각 편집 호출의 입력·출력tokens, tokenizer·transfer·생성 wall, prefill/decode forward GPU 시간, EOS/출력 cap, peak VRAM, model/revision·software/hardware·prompt hash.
- V text-only의 input keys·vision tokens0·visual forward0. GPU forward 시간은 전체 생성 wall과 다르다.
- 기존 OCR·추출의 측정 시간을 포함한 독립 recipe와 이번 실제 신규 계산량을 분리한다. 중복 source/call을 한 번만 세고 최종 batch는 main 행 비율로 시간을 배분한다. 초/pair 분모는240이다.
- 모델 적재와 actor 실제 wall은 별도로 기록한다. 여러 조건이 같은 모델 적재를 공유하므로 actor wall을 개별 method latency로 취급하지 않는다. 과거 기록에 없는 세부 timing은0이 아니라 null이다.

이 matrix는 이미 관찰한 개발 문항의 탐색 비교다. D와 J는 추출 시점에 보는 정보도 다르고 H 출력이 stem 선택에 영향을 줄 수 있으므로, 순수한 호출 수 또는 options 추가의 인과 효과로 단정하지 않는다. Matching의 실제 정답률은 별도 화면 검수 없이 source-span F1이나 inventory membership으로 대신하지 않는다.


## 준비 시 확인한 사항

치환·중복·원문 위치·overlap·gold 입력 차단·component별 repair/fallback 테스트12개를 통과했다. 전체14cell의 CPU mock 흐름을 점검했다. 별도 한 문항 기능 점검에서 고정 LM 및8B/4B text-only generation, 각 VLM의 최종 screenshot 풀이 연결을 확인했다. 모든 editor 호출에서 visual forward0·vision tokens0였고 출력 cap에 도달하지 않았다. 이는 기능 점검이며 정확도 검증이나 winner 선택이 아니다.

초기 기능 점검에서는 비인벤토리 stem replacement와 repair의 불필요한 options 재출력이 관찰됐다. 최종 코드에서는 오류에 잘못된 source/target을 명시하고, repair system에도 반환할 component만 명시했다. 정상 options는 고정했다. 재점검에서8B는 repair 후 유효한 stem 출력을 반환했고4B는 한 번에 유효 출력이었다. 고정 LM은 여전히 stem fallback이었다. 이 한 문항의 결과를 일반적인 성능으로 해석하지 않는다. 두 점검 artifact는 각각 `ppocr_editor_matrix_screen_v1_smoke`, `ppocr_editor_matrix_function_smoke_v2`에 보존했다. 이후 추가된 변경은 matching 집계 등 기록과 실행 전 검사다.

세 tokenizer의 전체 Screen 입력 점검에서 일반 입력은 최대1,349tokens, 출력 cap 길이의 가상 이전 응답을 넣은 repair는 최대2,404tokens였다. 실제 repair의 오류 문구와 VLM 추출 span 수에 따라 길이가 달라지므로 런타임에서도4,096 상한을 검사한다. Silent truncation은 없다.

B200 MIG45GiB에서 이 기능 점검의 peak reserved는 편집 LM15.67GiB, V8 16.78GiB, V4 8.57GiB였다. 기존 동일 profile의 batch3 최종 풀이 최대치는8B18.70GiB·4B10.51GiB였다. Editor의 최대5,120tokens(입력4,096+출력1,024)에서 BF16 KV tensor 이론치는 세 모델 모두 약0.70GiB이며 weight·activation·allocator는 별도다. 현재 배치 구성에서 메모리 여유는 크지만, 모든 입력에 대한 OOM 부재를 보증하는 수치는 아니다.

별도16-token 점검에서 계측 유무의 warmed generation은 모두 약0.367초였다. 첫 호출은 약6.46초로 더 느렸다. 원인이나 일반적인 속도를 이 한 점검으로 확정하지 않는다. 본 실험에는 인위적인 warmup을 추가하지 않고 실제 첫 호출의 초기화 비용도 생성 runtime에 포함한다. Timing instrumentation 때문에 느려졌다는 증거는 이 점검에서 나오지 않았다.
