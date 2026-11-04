# REL 기준 요소 위치 지정 실험: 사전 지정 프로토콜 v3

고정일: **2026-11-03**. 이 문서는 Qwen 파일럿 O/R 응답을 보기 전에 확정한 **표본, 입력, 채점, 분석 규칙**이다. 장시간 본 분석 추론은 아직 실행하지 않았다. 기존 O/R 정답은 이 연구 질문을 만드는 데 사용했으므로, 아래 실험은 독립 데이터셋 재현이 아니라 동일 문항에 대한 새 진단이다. v1의 0–1000 점 계약은 Qwen2.5 좌표계와 맞지 않았다. v2의 양성 대조 8건은 출력 형식 게이트를 통과하지 못해 파일럿 O/R을 시작하지 않았다. v3는 그 원시 응답만 보고 system/user 역할, 출력 지시, `label` 요청과 목표 요소 설명을 함께 수정했으며, 새 파일럿 O/R 결과를 보고 선택한 형식이 아니다. [출력 형식 검토](FORMAT_REVIEW_KO.md)에 경위를 남겼다. 각 버전 입력·결과는 분리한다.

**현재 상태:** v3도 양성 대조 게이트에 실패해 v3 O/R 파일럿과 본 분석은 실행하지 않았다. 선정된 12문항의 짧은 기준 표현을 이용한 별도 탐색 실행은 O/R 96응답까지 완료했으나 형식 게이트에 실패했다. 수치와 해석 제한은 [Qwen 파일럿 결과](QWEN_PILOT_RESULTS_KO.md)에 기록했다. 아래 v3 규칙은 성공한 프로토콜이 아니라 **사전 지정 후 검증에 실패한 프로토콜**이다.

**이전 실행과의 정합성 점검(2026-11-04):** [설정 대조](BASELINE_ALIGNMENT_AUDIT_KO.md)에서 초기 6×6과 REL full은 영어 객관식 system을 모든 조건에 고정했음을 확인했다. 아래 v3 Qwen은 명시적 system이 없고, 미실행 InternVL 계획은 새 위치 지시 system을 쓴다. 따라서 아래의 system/user 설계는 이전 객관식 실험에서 그대로 가져온 설정이 아니다. 두 모델 모두 **새 버전의 고정 system 정책과 기준 명사구 입력**을 정하기 전에는 본 위치 추론을 시작하지 않는다. v3의 잠금 입력과 파일럿 결과는 역사적 기록으로 유지한다.

## 1. 가져온 annotation의 판정

`annotations_20261103/verify.py --images`와 [`audit_annotations.py`](audit_annotations.py)가 통과했다. [검증 수치](annotation_audit.json)는 원본 두 파일, 검수 기록, GT, 잠금 manifest, 680개 이미지의 연결을 확인한다.

| 확인 항목 | 결과 |
| --- | ---: |
| 구조적 후보 / 원본 두 검수자 | 179문항 / 각 716화면 완료 |
| 사람 메모·상태·의미 문제 신호로 문항 단위 제외 | 9문항 |
| 채점 가능 GT | 170문항 × 4 GUI 언어 = 680화면, 전부 `valid`·범위 내 bbox |
| 파일럿 / 본 분석 | 12문항 / 158문항 |
| bbox 선택 출처 | 118문항은 `baegihyeon` 원본, 52문항은 4화면씩 해결된 합의안 |
| 원본 그대로 선택된 118문항 | 모든 화면에서 두 검수자 bbox IoU ≥ 0.5 |
| 이미지의 15%를 넘는 넓은 bbox | 22/680화면, 본 분석 8문항 포함 |

두 검수자는 상태 713/716, 요소 종류 398/716에서 일치했다. 두 bbox가 모두 유효한 713화면 중 IoU ≥ 0.5는 546화면이었다. 낮은 합의가 있던 포함 문항 52개에는 별도 검수 기록 208개가 있고 모두 `resolved`이며, GT의 핵심 필드가 이 기록과 일치한다. 제외 문항 5개의 검수 기록 20개도 해결 상태다. 원본부터 합의가 높았던 118문항은 추가 선택 없이 한 검수자의 bbox를 일관되게 채택했다. 제외 9문항은 원본의 문제 신호에서 그대로 재구성된다. 임의의 모델 정오 조건으로 고른 문항은 없다.

수작업으로 극단적 불일치 두 사례(`rel::2/setting_2.png`, `rel::2/weather_3.png`)와 넓은 상자 두 사례를 원본 화면과 대조했다. 680화면 전체의 의미적 정답을 독립 재검수한 것은 아니다.

넓은 상자는 특히 **지시 대상의 단위** 문제를 만든다. `rel::5/manager_10.jpg`의 RU 화면에서 질문은 `Phone Manager services`의 토글을 관계 기준으로 삼지만, GT 상자는 토글이 포함된 설정 카드 전체(화면 면적의 39.6%)다. 두 검수자 모두 비슷한 카드 영역을 그렸으므로 높은 bbox IoU만으로는 이 차이를 발견할 수 없다. 원본 annotation을 임의 수정하지 않고, 본 분석에서 어느 언어든 상자 면적이 화면의 15%를 넘는 8문항을 **사전 지정 민감도 집합**으로 표시한다. 이 집합을 뺀 결과와 포함한 결과를 함께 보고하며, 큰 상자 안의 정답점이 정확한 토글 위치를 증명한다고 해석하지 않는다. 해당 8문항 ID는 [감사 결과](annotation_audit.json)에 고정했다.

annotation의 `unreviewed`, `pending`, 요소 종류 필드는 이번 실험의 **포함·제외, 채점, 층화에 사용하지 않는다**. 기준 표현 `anchor_phrase`는 680화면 모두 노란 span과 정확히 같고 명사구 문맥을 따로 담지 않는다. 따라서 단어만 모델에 주지 않고 아래처럼 원 질문 문장을 함께 제시한다. 질문 하나는 span 문자열이 반복되므로 **문자열 검색 대신 잠금 시작·끝 오프셋**으로 표시한다.

## 2. 연구 질문과 주장 범위

1. **주 질문:** source 질문 문맥과 GUI 이미지를 고정하고 기준 요소 span만 source→GUI 언어로 바꾸면, 두 모델의 *명시적 위치 지정* 성공률이 변하는가?
2. **보조 질문:** 같은 158문항에서 기준 표현과 A–D 선택지 표현의 현지화는 기존 REL 객관식 정답에 각각 얼마나 기여하는가?
3. **서술 분석:** 위치 지정의 O→R 변화와 객관식 O→R 변화가 같은 문항·언어쌍에서 동반하는가?

명시적 위치 과제는 원래 객관식 답변 중 모델의 내부 grounding을 직접 관측하지 않는다. 위치 지정 성공과 객관식 성공의 동반 변화만으로 `grounding failure`와 `post-grounding reasoning failure`를 개별 문항에 확정 배정하거나 매개효과를 주장하지 않는다. 이 자료가 직접 지지하는 결론은 **표현 변화가 별도 위치 지정 과제를 바꾸는지**이다.

## 3. 표본과 입력 잠금

- 본 분석은 포함된 158문항의 4 GUI 언어 각각에 대해 나머지 3 source 언어를 사용한다. 모델당 **1,896개 방향성 `(parallel_id, source, GUI)` 쌍**이다. 각 쌍에서 O/R 위치 질문 두 개를 같은 원본 이미지에 제시한다.
- 12문항 파일럿은 본 분석에서 제외한다. 파일럿 위치 과제는 문항당 `EN→ZH, ZH→TH, TH→RU, RU→EN` 네 쌍, 모델당 **48쌍·96응답**이다.
- [`build_protocol_inputs.py`](build_protocol_inputs.py)는 잠금 `conditions_4lang.jsonl`, `reference_mappings.jsonl`, manifest, 감사된 GT를 읽고 `results/grounding_protocol_inputs_v3/`에 정확한 입력을 만든다. 위치 과제 파일에는 **정답, bbox, 모델 출력이 없다**. 생성 내용은 Git에 포함한 [입력 잠금](input_lock.json)의 SHA-256과 먼저 비교하고, 재생성 시 내용이 다르면 덮어쓰지 않고 중지한다. 이전 버전 입력은 별도 디렉터리에 남겨 혼합하지 않는다.
- 본 분석 O/R 객관식은 기존 `results/full/qwen2_5_vl_7b_batch32` 및 `results/full/internvl2_5_8b` 결과를 재사용한다. 각 모델의 1,896쌍 모두 O/R이 성공 상태이고 정오가 있다. 새 `R_stem`/`R_opts`만 추론한다.

### 위치 과제의 실제 텍스트

원래 O의 질문 문장에 `<ref>...</ref>`를 **잠금 span 오프셋**으로 삽입한다. R은 그 한 span만 GUI 언어 span으로 바꾼 뒤 같은 위치에 표시한다. 나머지 source 문맥·이미지·지시문은 동일하다. A–D 선택지와 gold는 넣지 않는다. 예: `... blue '<ref>Search</ref>' button?` 대 `... blue '<ref>搜索</ref>' button?`. 질문 전체를 제공하므로 `Search`처럼 span 자체가 짧아도 버튼이라는 문맥이 남는다.

아래는 **실행했던 v3의 역사적 위치 출력 계약**이다. Qwen2.5-VL에는 지시문과 이미지가 같은 **user 메시지**에 들어가고, 별도 명시적 system prompt는 없다. 이는 모델 공식 예시를 참고해 선택한 방식이지만, 이전 REL full의 고정 영어 객관식 system과 다르다. 공식 예시는 좌표계와 출력 형식의 근거이지 이 연구의 **메시지 역할 선택을 검증한 근거는 아니다**. `{model_width}`와 `{model_height}`는 Qwen 프로세서의 실제 `image_grid_thw`에서 각각 `grid[2]×14`, `grid[1]×14`로 읽는다. 이 크기를 알기 전에는 prompt를 완성하거나 추론하지 않는다. Qwen user text 전체는 다음과 같다.

```text
Locate the GUI reference element marked with <ref>...</ref> in the question below. The marked expression may be in a different language from the screenshot. Use surrounding words to identify the marked element. Do not locate the element that the question asks for.
Question: {marked_stem}
The screenshot is {model_width} pixels wide and {model_height} pixels high. Give one point inside the marked reference element using integer pixel coordinates on this screenshot, with (0, 0) at the top-left. Return only this JSON array: [{"point_2d": [x, y]}]. No explanation or code fence.
```

아래 InternVL2.5-8B system prompt는 **실행하지 않은 v3 계획**이다. 공식 grounding 데이터의 **0–1000 정규화 bbox** 출력 계약은 참고할 수 있으나, 새 위치 지시를 system에 넣는 선택은 이전 REL full과 다르다. 새 버전에서 메시지 역할을 다시 고정해야 한다. 두 모델에서 지시 대상·O/R 차이·원본 이미지를 같게 하려는 계획이었다.

```text
Locate one reference element in the full GUI screenshot. Return exactly one bounding box as <box>[[x1, y1, x2, y2]]</box>. Use integer coordinates normalized from 0 to 1000 over the full screenshot, with (0, 0) at the top-left and (1000, 1000) at the bottom-right. Do not add any other text.
```

InternVL의 user text는 다음과 같다. 두 모델에서 `{marked_stem}`과 그 O/R 차이는 같고, 모델별 출력 지시만 다르다.

```text
Question: {marked_stem}
Locate the reference GUI element described by the marked expression and its surrounding words. Do not answer the relation question.
```

이미지는 기존 모델 입력 방법으로 한 장만 넣는다. Qwen에는 **점 하나의 JSON 배열**을 요청한다. 채점은 한 점만 명확한 JSON 객체 또는 단일 객체 배열에서 `point_2d`를 읽으며, 선택적인 `label`은 무시한다. 숫자와 공식 예시의 숫자 문자열을 모두 받는다. 요청한 배열·정수 형태를 지킨 비율은 위치 정오와 별도로 기록한다. 최종 입력 폭·높이 `(Wm,Hm)`과 원본 폭·높이 `(Wo,Ho)`를 기록하고 `x_original=x·Wo/Wm`, `y_original=y·Ho/Hm`으로 옮긴다. InternVL 출력은 단일 `<box>[[x1,y1,x2,y2]]</box>`(선택적으로 앞에 `<ref>...</ref>`)만 받는다. 정규화 bbox 중심을 `((x1+x2)·Wo/2000,(y1+y2)·Ho/2000)`으로 옮긴다. [파서·채점 계약](point_format.py)에 맞지 않는 추가 설명, 범위 밖 좌표, 생성 실패는 오답이다. 변환된 점이 원본 GT bbox의 닫힌 경계 안에 있으면 성공이다. 680개 이미지의 원본 크기는 manifest와 일치하고, EXIF 방향 회전이 필요한 파일은 없었다. 이 지표는 **annotation된 영역 안에 점이 있는지**만 측정하며, 영역이 카드 전체일 때 작은 토글을 맞혔다고 해석하지 않는다.

모델 revision과 영상 전처리는 기존 run contract를 따른다. Qwen2.5-VL-7B는 `cc594898137f460bfe9f0759e9844b3ce807cfb5`와 pixel budget 262,144–2,097,152, InternVL2.5-8B는 `e9e4c0dc1db56bfab10458671519b7fa3dd29463`와 448px 동적 타일 최대 7개+thumbnail이다. 위치 응답만 greedy(`do_sample=false`, `num_beams=1`, `temperature=null`, `max_new_tokens=64`)로 새로 생성한다. 모델별 응답을 독립적으로 보고하며 두 모델의 원시 위치 정확도를 우열 비교의 주 대상으로 삼지 않는다. Qwen 점과 InternVL bbox 중심의 차이 때문에 R−O 크기의 모델 간 직접 우열도 주장하지 않는다.

### REL 2×2 문항

같은 쌍에서 **질문 문맥·이미지·gold·A–D 순서**를 고정한다. `R_stem`은 기존 R의 질문 stem+O의 선택지, `R_opts`는 O의 stem+R의 선택지로 만든다. `R`은 기준 표현과 선택지의 참조 문자열 묶음을 함께 바꾼 기존 조건이다. 입력 생성기는 1,944개 선택 쌍의 질문 및 A–D에 대해 R이 잠금 참조 span 치환만으로 정확히 재구성되는지 확인한다. 새 두 조건의 최종 질문은 기존 방식인 `stem + " A: ... B: ... C: ... D: ..."`로 조립하고 기존 label-only system/user prompt, 모델 전처리 및 greedy 2토큰 생성을 사용한다. 기존 O/R과 동일한 입력에 대한 새 러너 출력이 파일럿에서 일치하는지 확인한 다음 새 조건만 본 분석에서 실행한다. 새 조건에서 실패한 쌍은 실패 수를 보고하고, 주 대비는 완전한 쌍에서만 계산한다.

## 4. 파일럿과 실행 게이트

모델 결과를 이용해 prompt를 고르지 않는다. 위치 과제의 파일럿 96응답/모델에 앞서, 8개 **GUI 언어 일치 positive control**을 실행한다. 각 GUI 언어에 `rel::1/booking_1.jpg`와 `rel::5/message_1.jpg`의 target을 사용한다. 둘 다 기존 파일럿 GT에서 큰 버튼으로 표시되어 있으며 생성한 `positive_controls.jsonl`은 로컬에 남는다.

1. CPU 단위 검사에서 Qwen의 실제 `image_grid_thw`와 픽셀 역변환, InternVL 정규화 bbox 중심 역변환, 비정사각 이미지의 경계 판정이 맞아야 한다. 실제 모델의 렌더링 prompt·중간/최종 전처리 이미지 크기·원시 응답을 기록한다.
2. 각 모델에서 positive control **8개 모두 형식 파싱 성공**, 그중 **최소 6개 point-in-box**이면 좌표 출력을 기술적으로 사용할 수 있다고 판단한다. 이어 96개 O/R 파일럿 응답 중 **최소 90개 형식 파싱 성공**을 요구한다. 모델별로 따로 판정한다.
3. 미달이면 전체 추론을 시작하지 않는다. 이미지 좌표 변환, prompt 직렬화, 출력 길이를 먼저 점검하고 수정 내역을 버전 올려 기록한다. O/R 정답 차이 또는 본 분석 예측을 보고 prompt를 최적화하지 않는다. 파일럿은 분석에서 영구 제외한다.

검사 통과 후 본 분석 추론은 모델별·조건별 한 번씩 실행한다. 같은 쌍 O/R 순서는 `SHA-256(pair_id)`의 첫 바이트 짝홀에 따라 교차시킨다. 배치가 결과에 영향을 주지 않는지 파일럿에서 확인하고, 예측마다 입력 해시, 모델 revision, 프로세서 설정, rendered prompt, 원시 응답, 파싱 결과, 이미지 해시와 실행 상태를 보존한다. GPU 메모리 오류는 배치를 줄여 해당 입력을 재시도하되 중복 성공 기록을 만들지 않는다.

## 5. 지표와 통계 계획

**주 지표:** 모델별 위치 지정 point-in-GT-box. Qwen은 예측 점, InternVL은 예측 bbox의 중심을 사용한다. 각 본 분석 문항의 12개 방향성 쌍에 대해 `hit_R−hit_O`를 평균하고, 그 158개 문항 평균을 백분율포인트(pp)로 보고한다. 파싱 실패도 0이다. 각 쌍의 `0→1`, `1→0`, `0→0`, `1→1` 개수와 단일 점·상자 추출 유효률을 함께 공개한다. Qwen의 요청 형식 준수율과 InternVL bbox IoU는 보조 지표다. 모델별 주 대비 두 개에는 문항 단위 복원추출 10,000회, seed `20261103`의 **양측 97.5% percentile 구간**을 사용해 두 모델에 대한 보수적 다중 비교 처리를 한다. 표본은 구조적·사람 검수 후 선택된 158문항이므로 신뢰구간을 전체 REL 모집단으로 일반화하지 않는다.

**보조 객관식:** 같은 158문항·1,896쌍에서 O/R 정오를 재집계한다. 신규 `R_stem`, `R_opts`가 준비되면 각 문항 내 12쌍 평균을 사용해 기준 표현 평균 효과 `[(R_stem−O)+(R−R_opts)]/2`, 선택지 묶음 평균 효과 `[(R_opts−O)+(R−R_stem)]/2`, 상호작용 `R−R_stem−R_opts+O`를 계산한다. 각 모델에 문항 bootstrap 95% 구간을 붙이고 탐색적 대비로 명시한다. 선택지 효과는 개별 선택지가 아니라 **A–D 참조 표현 묶음**의 효과다.

**동반 변화:** 동일 `(문항, source, GUI, 모델)`의 위치 `O→R` 전환과 객관식 `O→R_stem` 및 `O→R` 전환의 교차표를 낸다. `P(REL 0→1 | 위치 0→1)` 같은 조건부 비율과 문항 bootstrap 구간은 서술 자료로 보고한다. 위치 과제와 객관식 과제의 차이 때문에 이를 인과적 매개율로 해석하지 않는다.

**민감도:** (a) 두 원본 bbox가 네 화면 모두 IoU ≥ 0.5인 본 분석 **111문항**에서 반복한다. (b) 원본 두 검수자의 bbox로 각각 별도 채점해 GT 선택에 따른 차이를 보인다. (c) 넓은 상자가 하나라도 있는 사전 지정 8문항을 제외한 **150문항**에서 반복한다. (d) GT bbox 면적 비율 사분위, GUI 언어, 12개 언어쌍별 수치를 탐색적으로 제시한다. 상자 크기에 따라 point-in-box 난도가 달라질 수 있으므로 유효 출력률과 원본 대각선으로 나눈 중심 거리도 보조 지표로 보고한다. 위치 출력을 보기 전에 넓은 영역의 GT를 별도 수정하지 않으며, 추후 재검수하면 annotation 버전을 올려 기록한다.

## 6. 해석 한계와 다음 단계

R과 O의 차이는 언어 문자열 조작 효과다. 번역 의미가 같다고 확인한 효과로 부르지 않는다. 위치 정확도가 올라가고 객관식도 개선되면 **기준 요소 위치 지정이 병목일 가능성**을 지지하지만, 내부 grounding 변화의 직접 증명은 아니다. 위치 정확도가 그대로여도 선택지 grounding·OCR·관계 판단·점 출력 능력 중 어디가 실패했는지는 구별되지 않는다.

후속 위치 단서 개입은 이 v3의 확증 분석에 섞지 않는다. 필요하면 본 분석 결과를 본 뒤 별도 버전에서 GT 위치를 표시한 이미지와 중립 표시 이미지를 사전 정의해 `location cue`의 구제 효과를 검사한다. 그 개입도 정답 후보 위치 annotation 없이 `post-grounding reasoning failure`를 확정할 수 없다.

## 재현 명령

저장소 최상위에서 실행한다. 새 위치 입력 파일은 Git 제외된 `followup_rel_4lang/results/grounding_protocol_inputs_v3/`에 생성된다. 원본 전달본과 [검증 스크립트](annotations_20261103/verify.py)는 수정하지 않는다. Qwen [파일럿 러너](run_qwen_pilot.py)는 현재 공유 디스크 여유를 고려해 고정 revision의 가중치를 한 shard씩 임시 다운로드·SHA-256 검증·GPU 적재 후 제거한다. 입력·결과 버전을 확인하며 본 분석 문항은 실행하지 않는다. 본 분석 러너는 아직 구현하지 않았다.

```bash
python3 followup_rel_4lang/grounding_eval/annotations_20261103/verify.py --images
python3 followup_rel_4lang/grounding_eval/audit_annotations.py
python3 followup_rel_4lang/grounding_eval/build_protocol_inputs.py
source followup_rel_4lang/qwen_server_env.sh
"$PYTHON_BIN" followup_rel_4lang/grounding_eval/run_qwen_pilot.py
```
