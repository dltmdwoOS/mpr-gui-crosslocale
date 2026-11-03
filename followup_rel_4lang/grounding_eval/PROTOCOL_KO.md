# REL 기준 요소 위치 지정 실험: 설계 고정 v1

고정일: **2026-11-03**. 이 문서는 새 모델 위치 응답을 보기 전에 확정한 **표본, 입력, 채점, 분석 규칙**이다. 장시간 추론은 아직 실행하지 않았다. 기존 O/R 정답은 이 연구 질문을 만드는 데 사용했으므로, 아래 실험은 독립 데이터셋 재현이 아니라 동일 문항에 대한 새 진단이다.

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
| 역할·종류 미정렬 | 47문항(본 분석 46문항) |
| bbox 복사 확인 `pending` | 453/680화면 |
| 번역 의미 `unreviewed` | 기준 표현 677/680, 선택지 678/680 |
| 이미지의 15%를 넘는 넓은 bbox | 22/680화면, 본 분석 8문항 포함 |

두 검수자는 상태 713/716, 요소 종류 398/716에서 일치했다. 두 bbox가 모두 유효한 713화면 중 IoU ≥ 0.5는 546화면이었다. 낮은 합의가 있던 포함 문항 52개에는 별도 검수 기록 208개가 있고 모두 `resolved`이며, GT의 핵심 필드가 이 기록과 일치한다. 제외 문항 5개의 검수 기록 20개도 해결 상태다. 원본부터 합의가 높았던 118문항은 추가 선택 없이 한 검수자의 bbox를 일관되게 채택했다. 제외 9문항은 원본의 문제 신호에서 그대로 재구성된다. 임의의 모델 정오 조건으로 고른 문항은 없다.

**한계:** `bbox_provenance.review_status=pending`은 화면 간 복사 확인 상태이고 합의 기록의 `resolution=resolved`와 별개다. 453화면을 최종 시각 승인했다고 해석하지 않는다. 수작업으로 극단적 불일치 두 사례(`rel::2/setting_2.png`, `rel::2/weather_3.png`)와 넓은 상자 두 사례를 원본 화면과 대조했지만 680화면 전체의 의미적 정답을 독립 재검수한 것은 아니다. GT는 이 의미에서 잠정판이다.

넓은 상자는 특히 **지시 대상의 단위** 문제를 만든다. `rel::5/manager_10.jpg`의 RU 화면에서 질문은 `Phone Manager services`의 토글을 관계 기준으로 삼지만, GT 상자는 토글이 포함된 설정 카드 전체(화면 면적의 39.6%)다. 두 검수자 모두 비슷한 카드 영역을 그렸으므로 높은 bbox IoU만으로는 이 차이를 발견할 수 없다. 원본 annotation을 임의 수정하지 않고, 본 분석에서 어느 언어든 상자 면적이 화면의 15%를 넘는 8문항을 **사전 지정 민감도 집합**으로 표시한다. 이 집합을 뺀 결과와 포함한 결과를 함께 보고하며, 큰 상자 안의 정답점이 정확한 토글 위치를 증명한다고 해석하지 않는다. 해당 8문항 ID는 [감사 결과](annotation_audit.json)에 고정했다.

역할 레이블은 47문항이 미정렬이므로 **채점·제외·층화에 사용하지 않는다**. 기본 `yes`였던 번역 필드도 전수 검수가 아니다. 실제 값은 대부분 `unreviewed`이며, 의미 동등성을 입증하는 자료로 사용하지 않는다. 기준 표현 `anchor_phrase`는 680화면 모두 노란 span과 정확히 같고 명사구 문맥을 따로 담지 않는다. 따라서 단어만 모델에 주지 않고 아래처럼 원 질문 문장을 함께 제시한다. 질문 하나는 span 문자열이 반복되므로 **문자열 검색 대신 잠금 시작·끝 오프셋**으로 표시한다.

## 2. 연구 질문과 주장 범위

1. **주 질문:** source 질문 문맥과 GUI 이미지를 고정하고 기준 요소 span만 source→GUI 언어로 바꾸면, 두 모델의 *명시적 위치 지정* 성공률이 변하는가?
2. **보조 질문:** 같은 158문항에서 기준 표현과 A–D 선택지 표현의 현지화는 기존 REL 객관식 정답에 각각 얼마나 기여하는가?
3. **서술 분석:** 위치 지정의 O→R 변화와 객관식 O→R 변화가 같은 문항·언어쌍에서 동반하는가?

명시적 위치 과제는 원래 객관식 답변 중 모델의 내부 grounding을 직접 관측하지 않는다. 위치 지정 성공과 객관식 성공의 동반 변화만으로 `grounding failure`와 `post-grounding reasoning failure`를 개별 문항에 확정 배정하거나 매개효과를 주장하지 않는다. 이 자료가 직접 지지하는 결론은 **표현 변화가 별도 위치 지정 과제를 바꾸는지**이다.

## 3. 표본과 입력 잠금

- 본 분석은 포함된 158문항의 4 GUI 언어 각각에 대해 나머지 3 source 언어를 사용한다. 모델당 **1,896개 방향성 `(parallel_id, source, GUI)` 쌍**이다. 각 쌍에서 O/R 위치 질문 두 개를 같은 원본 이미지에 제시한다.
- 12문항 파일럿은 본 분석에서 제외한다. 파일럿 위치 과제는 문항당 `EN→ZH, ZH→TH, TH→RU, RU→EN` 네 쌍, 모델당 **48쌍·96응답**이다.
- [`build_protocol_inputs.py`](build_protocol_inputs.py)는 잠금 `conditions_4lang.jsonl`, `reference_mappings.jsonl`, manifest, 감사된 GT를 읽고 `results/grounding_protocol_inputs/`에 정확한 입력을 만든다. 위치 과제 파일에는 **정답, bbox, 모델 출력이 없다**. 생성 내용은 Git에 포함한 [입력 잠금](input_lock.json)의 SHA-256과 먼저 비교하고, 재생성 시 내용이 다르면 덮어쓰지 않고 중지한다.
- 본 분석 O/R 객관식은 기존 `results/full/qwen2_5_vl_7b_batch32` 및 `results/full/internvl2_5_8b` 결과를 재사용한다. 각 모델의 1,896쌍 모두 O/R이 성공 상태이고 정오가 있다. 새 `R_stem`/`R_opts`만 추론한다.

### 위치 과제의 실제 텍스트

원래 O의 질문 문장에 `<ref>...</ref>`를 **잠금 span 오프셋**으로 삽입한다. R은 그 한 span만 GUI 언어 span으로 바꾼 뒤 같은 위치에 표시한다. 나머지 source 문맥·이미지·지시문은 동일하다. A–D 선택지와 gold는 넣지 않는다. 예: `... blue '<ref>Search</ref>' button?` 대 `... blue '<ref>搜索</ref>' button?`. 질문 전체를 제공하므로 `Search`처럼 span 자체가 짧아도 버튼이라는 문맥이 남는다.

두 모델에 같은 system prompt를 사용한다. 코드 상수 `SYSTEM_PROMPT`가 원문이다.

```text
Locate the marked reference element in the full GUI screenshot. Return only one point as (x, y), where x and y are integers from 0 to 1000. (0, 0) is the top-left and (1000, 1000) is the bottom-right. Do not answer the question or add any other text.
```

User text는 다음 두 문장이다. `{marked_stem}` 외 문구는 조건 간 같다.

```text
Question: {marked_stem}
Locate only the GUI element named between <ref> and </ref>. Return the center of that element as (x, y).
```

이미지는 기존 모델 입력 방법으로 한 장만 넣는다. 출력은 [`point_format.py`](point_format.py)의 **정확히 하나의 `(정수, 정수)`** 형식만 유효하며 두 값은 각각 0–1000이다. 추가 설명, 부동소수점, 범위 밖, 생성 실패는 오답으로 기록한다. `x_original=x·width/1000`, `y_original=y·height/1000`으로 옮겨 원본 bbox의 닫힌 경계 안에 있으면 성공이다. 양 모델 모두 원본 이미지 전체에 대한 정규화 좌표를 내도록 지시한다. 680개 이미지의 원본 크기는 manifest와 일치하고, EXIF 방향 회전이 필요한 파일은 없었다. 이 지표는 **annotation된 영역 안에 점이 있는지**만 측정하며, 영역이 카드 전체일 때 작은 토글을 맞혔다고 해석하지 않는다.

모델 revision과 영상 전처리는 기존 run contract를 따른다. Qwen2.5-VL-7B는 `cc594898137f460bfe9f0759e9844b3ce807cfb5`와 pixel budget 262,144–2,097,152, InternVL2.5-8B는 `e9e4c0dc1db56bfab10458671519b7fa3dd29463`와 448px 동적 타일 최대 7개+thumbnail이다. 위치 응답만 greedy(`do_sample=false`, `num_beams=1`, `temperature=null`, `max_new_tokens=32`)로 새로 생성한다. 모델별 응답을 독립적으로 보고하며 두 모델의 원시 위치 정확도를 우열 비교의 주 대상으로 삼지 않는다.

### REL 2×2 문항

같은 쌍에서 **질문 문맥·이미지·gold·A–D 순서**를 고정한다. `R_stem`은 기존 R의 질문 stem+O의 선택지, `R_opts`는 O의 stem+R의 선택지로 만든다. `R`은 기준 표현과 선택지의 참조 문자열 묶음을 함께 바꾼 기존 조건이다. 입력 생성기는 1,944개 선택 쌍의 질문 및 A–D에 대해 R이 잠금 참조 span 치환만으로 정확히 재구성되는지 확인한다. 새 두 조건의 최종 질문은 기존 방식인 `stem + " A: ... B: ... C: ... D: ..."`로 조립하고 기존 label-only system/user prompt, 모델 전처리 및 greedy 2토큰 생성을 사용한다. 기존 O/R과 동일한 입력에 대한 새 러너 출력이 파일럿에서 일치하는지 확인한 다음 새 조건만 본 분석에서 실행한다. 새 조건에서 실패한 쌍은 실패 수를 보고하고, 주 대비는 완전한 쌍에서만 계산한다.

## 4. 파일럿과 실행 게이트

모델 결과를 이용해 prompt를 고르지 않는다. 위치 과제의 파일럿 96응답/모델에 앞서, 8개 **GUI 언어 일치 positive control**을 실행한다. 각 GUI 언어에 `rel::1/booking_1.jpg`와 `rel::5/message_1.jpg`의 target을 사용한다. 둘 다 기존 파일럿 GT에서 큰 버튼으로 표시되어 있으며 생성한 `positive_controls.jsonl`은 로컬에 남는다.

1. CPU 단위 검사에서 비정사각 이미지 `(0,0)`, `(500,500)`, `(1000,1000)`의 원본 좌표 변환과 bbox 판정이 맞아야 한다. 실제 모델의 렌더링 prompt·전처리 이미지 크기·원시 응답을 기록한다.
2. 각 모델에서 positive control **8개 모두 형식 파싱 성공**, 그중 **최소 6개 point-in-box**이면 좌표 출력을 기술적으로 사용할 수 있다고 판단한다. 이어 96개 O/R 파일럿 응답 중 **최소 90개 형식 파싱 성공**을 요구한다. 모델별로 따로 판정한다.
3. 미달이면 전체 추론을 시작하지 않는다. 이미지 좌표 변환, prompt 직렬화, 출력 길이를 먼저 점검하고 수정 내역을 버전 올려 기록한다. O/R 정답 차이 또는 본 분석 예측을 보고 prompt를 최적화하지 않는다. 파일럿은 분석에서 영구 제외한다.

검사 통과 후 본 분석 추론은 모델별·조건별 한 번씩 실행한다. 같은 쌍 O/R 순서는 `SHA-256(pair_id)`의 첫 바이트 짝홀에 따라 교차시킨다. 배치가 결과에 영향을 주지 않는지 파일럿에서 확인하고, 예측마다 입력 해시, 모델 revision, 프로세서 설정, rendered prompt, 원시 응답, 파싱 결과, 이미지 해시와 실행 상태를 보존한다. GPU 메모리 오류는 배치를 줄여 해당 입력을 재시도하되 중복 성공 기록을 만들지 않는다.

## 5. 지표와 통계 계획

**주 지표:** 모델별 위치 지정 point-in-GT-box. 각 본 분석 문항의 12개 방향성 쌍에 대해 `hit_R−hit_O`를 평균하고, 그 158개 문항 평균을 백분율포인트(pp)로 보고한다. 파싱 실패도 0이다. 각 쌍의 `0→1`, `1→0`, `0→0`, `1→1` 개수와 형식 유효률을 함께 공개한다. 모델별 주 대비 두 개에는 문항 단위 복원추출 10,000회, seed `20261103`의 **양측 97.5% percentile 구간**을 사용해 두 모델에 대한 보수적 다중 비교 처리를 한다. 표본은 구조적·사람 검수 후 선택된 158문항이므로 신뢰구간을 전체 REL 모집단으로 일반화하지 않는다.

**보조 객관식:** 같은 158문항·1,896쌍에서 O/R 정오를 재집계한다. 신규 `R_stem`, `R_opts`가 준비되면 각 문항 내 12쌍 평균을 사용해 기준 표현 평균 효과 `[(R_stem−O)+(R−R_opts)]/2`, 선택지 묶음 평균 효과 `[(R_opts−O)+(R−R_stem)]/2`, 상호작용 `R−R_stem−R_opts+O`를 계산한다. 각 모델에 문항 bootstrap 95% 구간을 붙이고 탐색적 대비로 명시한다. 선택지 효과는 개별 선택지가 아니라 **A–D 참조 표현 묶음**의 효과다.

**동반 변화:** 동일 `(문항, source, GUI, 모델)`의 위치 `O→R` 전환과 객관식 `O→R_stem` 및 `O→R` 전환의 교차표를 낸다. `P(REL 0→1 | 위치 0→1)` 같은 조건부 비율과 문항 bootstrap 구간은 서술 자료로 보고한다. 위치 과제와 객관식 과제의 차이 때문에 이를 인과적 매개율로 해석하지 않는다.

**민감도:** (a) 두 원본 bbox가 네 화면 모두 IoU ≥ 0.5인 본 분석 **111문항**에서 반복한다. (b) 원본 두 검수자의 bbox로 각각 별도 채점해 GT 선택에 따른 차이를 보인다. (c) 넓은 상자가 하나라도 있는 사전 지정 8문항을 제외한 **150문항**에서 반복한다. (d) GT bbox 면적 비율 사분위, GUI 언어, 12개 언어쌍별 수치를 탐색적으로 제시한다. 47개 미정렬 요소 종류와 미검증 번역 필드는 층화·유의성 주장에 사용하지 않는다. 상자 크기에 따라 point-in-box 난도가 달라질 수 있으므로 유효 출력률과 원본 대각선으로 나눈 중심 거리도 보조 지표로 보고한다. 위치 출력을 보기 전에 넓은 영역의 GT를 별도 수정하지 않으며, 추후 재검수하면 v2로 기록한다.

## 6. 해석 한계와 다음 단계

R과 O의 차이는 언어 문자열 조작 효과다. 번역 의미가 같다고 확인한 효과로 부르지 않는다. 위치 정확도가 올라가고 객관식도 개선되면 **기준 요소 위치 지정이 병목일 가능성**을 지지하지만, 내부 grounding 변화의 직접 증명은 아니다. 위치 정확도가 그대로여도 선택지 grounding·OCR·관계 판단·점 출력 능력 중 어디가 실패했는지는 구별되지 않는다.

후속 위치 단서 개입은 이 v1의 확증 분석에 섞지 않는다. 필요하면 본 분석 결과를 본 뒤 별도 버전에서 GT 위치를 표시한 이미지와 중립 표시 이미지를 사전 정의해 `location cue`의 구제 효과를 검사한다. 그 개입도 정답 후보 위치 annotation 없이 `post-grounding reasoning failure`를 확정할 수 없다.

## 재현 명령

저장소 최상위에서 실행한다. 새 위치 입력 파일은 Git 제외된 `followup_rel_4lang/results/grounding_protocol_inputs/`에 생성된다. 원본 전달본과 [검증 스크립트](annotations_20261103/verify.py)는 수정하지 않는다.

```bash
python3 followup_rel_4lang/grounding_eval/annotations_20261103/verify.py --images
python3 followup_rel_4lang/grounding_eval/audit_annotations.py
python3 followup_rel_4lang/grounding_eval/build_protocol_inputs.py
```
