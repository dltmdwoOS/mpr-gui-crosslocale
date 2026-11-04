# 이전 MPR-GUI 추론과 grounding 파일럿 설정 대조

점검일: 2026-11-04. 이 문서는 **이미 실행한 입력과 결과의 해석**을 바로잡는다. 2026-11-03의 잠금 v3 입력·응답·게이트 수치를 소급 변경하지 않는다. 새 모델 추론은 하지 않았다.

## 어떤 실행을 확인했나

| 근거 | 실제로 확인된 메시지 구성 | 증거의 범위 |
| --- | --- | --- |
| 초기 Qwen 6×6의 [압축 원시 기록](../../01_code/results/summaries/6x6_qwen.zip) | 79,020행 **전부** `system_prompt_mode=english_fixed`, `prompt_profile=mpr_label_only_v1`, 동일한 영어 객관식 system 문구. 이미지 한 장. | 실행된 6×6 전체 행을 스트리밍해 확인했다. |
| REL O/R/C/F Qwen [full 실행 계약](../results/full/qwen2_5_vl_7b_batch32/run_contract.json)과 [압축 예측](../results/full/qwen2_5_vl_7b_batch32/predictions.jsonl.gz) | 초기 6×6과 **같은 system 문구**. 질문과 A–D 보기 다음에 `Respond with exactly one label: A, B, C, or D.`를 user 메시지에 붙였다. | 저장된 계약과 실제 렌더링 prompt를 확인했다. O/R/C/F의 조작 변수에 system은 포함되지 않는다. |
| [canonical 재현 러너](../../01_code/src/mpr_crosslocale/inference/run_canonical.py), [실험 설정](../../01_code/configs/experiments/canonical_reproduction.yaml) | 코드상 **명시적 system 메시지 없이** Qwen adapter를 호출한다. 설정 파일의 primary는 `mpr_minimal_v1`이다. 다만 러너의 인자 기본값은 모델 설정의 `mpr_label_only_v1`이며 CLI override 여부에 따라 user 문구가 달라진다. | 이 저장소에서 해당 canonical 실행의 **원시 예측 파일은 찾지 못했다**. 코드 경로를 실제 실행 사실로 말하면 안 된다. |

실행된 초기 6×6과 REL full의 영어 system 원문은 다음과 같다.

```text
You are a GUI reasoning assistant. Inspect the GUI image and answer the multiple-choice question. Respond with exactly one label: A, B, C, or D.
```

즉 **이전 실험에서 system 문구를 조건별로 바꾼 것은 아니다**. `run_cross_locale.py`에는 `query_aligned` 선택지가 있지만 초기 Qwen 6×6의 저장된 79,020행은 모두 `english_fixed`였다. 후속 REL full도 고정 영어 system을 사용했다. 외부 Qwen 예시는 이 프로젝트에서 실제로 쓰인 프롬프트를 대신하는 근거가 아니다.

## 설정별 비교

| 설정 | 이전 REL full Qwen | 이번 위치 파일럿 Qwen | 판단 |
| --- | --- | --- | --- |
| 체크포인트 | `Qwen2.5-VL-7B-Instruct`, revision `cc594898...` | 동일 revision | 유지 |
| 모델·전처리 | BF16, SDPA, `min_pixels=262144`, `max_pixels=2097152`, 이미지 1장 | 같은 값과 `qwen_vl_utils` 경로 | 유지. 같은 `booking_en_1.jpg`를 두 메시지 방식으로 CPU 전처리한 `image_grid_thw=[1,152,70]`과 `pixel_values`가 정확히 같았다. |
| system | 명시적 영어 **객관식** 문구를 모든 O/R/C/F에 고정 | v2는 화면 크기까지 넣은 새 위치 지시 system; v3·짧은 표현은 명시적 system 없이 Qwen template 기본 `You are a helpful assistant.` | **변경됨.** v2의 원문은 화면 크기에 따라 2종류였고 같은 이미지의 O/R에서는 동일했다. v2→v3 결과 차이에 system 역할·내용 변화가 섞인다. |
| user | 이미지 뒤 전체 질문+A–D 보기, 마지막에 A–D label 요청 | v2·v3는 보기 없는 관계 질문과 `<ref>` 표시; 짧은 표현은 기준 명사구만 | 위치 과제로 바뀌며 출력 지시는 필요하지만, **전체 관계 질문을 유지할지**는 별도 설계 선택이다. |
| 출력·생성 | A–D 한 글자, greedy, 최대 2토큰, next-token label score | JSON 점 하나, greedy, 최대 64토큰, label score 없음 | 점 과제에 필요한 변경. 원시 정확도끼리 직접 비교할 수 없다. |
| 배치·적재 | Qwen full batch 32, adapter의 `from_pretrained` | batch 1, 5개 shard를 SHA-256 검증해 GPU에 순차 적재 | 파일럿의 실행 차이. pilot weight tensor 명칭은 checkpoint 729개와 일치했지만, **원래 adapter와 생성 결과 동등성을 직접 시험하지 않았다**. |
| 환경 기록 | full 계약에 Python·Torch·Transformers 등 버전 기록 | pilot 결과에는 버전 필드 없음 | 현재 환경 버전은 REL full 계약의 Torch 2.9.1·Transformers 4.57.6·`qwen-vl-utils` 0.0.14와 일치한다. 초기 6×6은 Python 3.12.13·Torch 2.13.0에서 실행되어 그쪽과는 환경이 다르다. pilot 실행 당시 버전은 raw record만으로 증명할 수 없다. |

## 이 대조가 바꾸는 해석

1. **v2와 v3는 system만 바꾼 실험도, system을 고정한 형식 비교도 아니다.** 지시문 위치·내용, `label` 요청 여부 등이 함께 바뀌었다. v2 양성 대조 0/8 파싱과 v3 6/8 파싱의 차이를 특정 원인의 효과로 읽을 수 없다. 두 버전 모두 양성 대조 게이트에서 중지해 O/R 자체를 실행하지 않았다. 설계상 같은 이미지의 O/R에는 동일한 system 정책을 쓰도록 되어 있었다.
2. 이전 REL의 system을 **글자 그대로** 위치 과제에 넣으면 `A/B/C/D`만 답하라는 명령과 점 출력 명령이 충돌한다. 따라서 과제 변경에 맞춘 지시는 필요하다. 다만 v2처럼 system에 새 위치 규칙을 별도로 넣거나 v2↔v3의 system 구성을 바꾸는 선택은 원래 benchmark에서 자동으로 따라오지 않는다. 현재 결과만으로 system 변경이 실패의 원인이라고 단정할 수도 없다.
3. [초기 grounding 설계 검토](../GROUNDING_DESIGN_REVIEW_KO.md)는 **관계 질문의 다른 정보와 A–D를 제외하고**, 문맥을 포함한 **기준 요소 명사구**로 위치를 묻자고 했다. 실제 v3에는 전체 관계 질문이 들어가 답 요소를 가리키는 혼동이 생겼다. 짧은 표현 진단은 초기 목표 요소 정의에 더 가깝지만, 12문항에서만 수작업 추출했고 형식 게이트를 통과하지 못했다.
4. Qwen 자료에서 가져온 절대 픽셀 좌표와 `point_2d`는 **출력·채점 계약**에 관한 근거다. 그 자료는 이 REL 실험에서 system/user의 역할, 관계 질문 전체 사용, `label` 필드의 필요성을 검증하지 않는다. 이전 실험의 실제 입력을 우선 근거로 삼았어야 했다.
5. 아직 실행하지 않은 InternVL 위치 계획도 **새 위치 지시 system**을 포함한다. 이전 InternVL REL full은 Qwen과 같은 고정 영어 객관식 system을 사용했으므로, 이를 곧장 이전 실험과 정합한 설정이라고 부를 수 없다.

## 다음 버전에서 고정할 원칙

- 위치 과제는 별도 진단임을 명시하고, **한 모델 안에서** 양성 대조·O·R·모든 언어쌍에 동일한 system 정책을 적용한다. 새 위치 지시는 user 메시지에 두고, 모델의 기본 system이 자동 삽입된다면 렌더링된 정확한 문구를 기록한다. 이전의 A–D system 문구를 그대로 재사용하지 않는다.
- 기준 요소를 가리키는 **명사구 문맥**을 문항 전체에 대해 질문 언어별로 준비·검수한다. O/R은 그 안의 잠금 referent span만 바꾸고 나머지 텍스트·이미지·좌표계·생성 설정을 고정한다. 전체 관계 질문을 쓸지 여부는 출력 결과를 보고 섞지 않는다.
- 모델 가중치 적재, 전처리, chat template, 소프트웨어 버전, 출력 제한을 실행 계약에 남긴다. 형식 안정성은 이미 본 12문항의 O/R 차이로 튜닝하지 않고 **새 검증 문항**의 양성 대조에서 확인한다. 기능 게이트 전에는 본 분석을 시작하지 않는다.

원래 객관식과 새 위치 과제는 응답 공간이 다르다. 이 설정을 맞춰도 위치 점은 객관식 답을 만들던 순간의 내부 grounding을 직접 보여주지 않는다. 주장은 같은 문항에서 **별도 위치 지정 과제가 O→R에 반응하는지**로 제한한다.
