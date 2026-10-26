# REL grounding: 독립 bbox 검수 파일럿

처음 검수한다면 [빠른 안내](QUICK_GUIDE_KO.md)를 먼저 읽는다.

## 목적과 범위

질문의 단일 기준 표현이 실제 GUI 화면에서 가리키는 요소를 사람 두 명이 독립적으로 판정한다. 모델의 O/R 정오나 예측은 UI와 파일럿 manifest에 들어 있지 않다. 기존 답변의 정오에 따라 대상을 고르지 않는다. 검수 결과로 **새 grounding 과제의 대상과 제외 기준**을 정한 뒤 프로토콜을 동결한다.

`prepare_pilot.py`가 기존 잠금 `conditions_4lang.jsonl`과 `reference_mappings.jsonl`만 읽어 구조적 후보 179문항을 정하고, 고정 seed `20261026`으로 REL 하위 유형 6개에서 2개씩 12문항을 고른다. GUI 언어 네 개에 대해 최대 48개 이미지의 SHA-256과 원본 크기를 기록한다. 파일럿 ID는 `data/frame.json`과 `data/pilot_manifest.json`에 고정되어 있다. 이미지는 복사하지 않고 `followup_rel_4lang/assets/images`의 기존 파일을 연다.

## bbox와 텍스트 판정 규칙

각 문항·GUI 언어마다 다음을 기록한다.

1. 질문에서 노란색으로 표시된 기준 span을 포함하는 **원문 그대로의 연속된 명사구**를 `기준 요소 명사구`에 입력한다. 가능한 경우 `the blue 'Search' button`, `the 'Avoid Tolls' toggle switch`처럼 요소 종류를 포함한다. 질문 전체나 관계를 묻는 절은 넣지 않는다. 이 문구가 추후 O/R grounding prompt의 대상 표현이 된다.
2. 질문의 명사구가 지시하는 **하나의 UI 요소 전체**에 파란 bbox를 그린다. 버튼이면 버튼, 스위치면 스위치 컨트롤, 이름 붙은 헤더면 헤더를 잡는다. 읽히는 글자가 별도로 있으면 주황 bbox에 표시한다. 큰 행이나 화면 전체를 편의상 둘러싸지 않는다.
3. 요소 경계가 여러 방식으로 해석되면 `ambiguous`, 같은 설명에 부합하는 요소가 여러 개면 `multiple_matches`, 화면에서 없으면 `absent`, 단일 좌표 대상이 아닌 개념이면 `unpointable`을 선택한다. 이 경우 bbox를 그리지 않고 이유를 메모한다. 예를 들어 `Calculator app interface` 전체는 단일 위젯으로 간주하지 않는다.
4. 기준 표현과 선택지 A–D의 의미가 영어 버전과 동등한지 **별도로** 판정한다. 번역이 다른 대상을 가리키거나 의미가 바뀌었다면 `no`, 판단하기 어렵다면 `uncertain`을 선택하고 메모에 구체적인 표현을 적는다. 영어 버전도 화면 자체의 오류나 잘못된 지시를 따로 기록한다. 태국어·러시아어·중국어를 확실히 검수할 수 없으면 추측하지 말고 `uncertain`으로 둔다.
5. 기존 gold 답이나 모델 출력을 찾지 않는다. 두 검수자는 서로의 기록도 보지 않는다. 각자는 고유한 ID로 작업하고 JSON을 별도로 내보낸다.

`valid` 판정에는 원본 이미지의 `(x1,y1,x2,y2)` 픽셀 bbox와 요소 종류가 필요하다. 원문 명사구는 질문의 정확한 부분 문자열이어야 하며 노란 기준 span을 한 번 포함해야 한다. `valid`가 아니거나 번역 판정이 `no/uncertain`이면 메모가 필요하다.

현재 화면에서 bbox 그리기·지우기 및 상태 변경으로 자동 삭제된 bbox는 `Ctrl+Z`(Mac `⌘Z`) 또는 **실행 취소** 버튼으로 되돌린다. 최근 30번까지 가능하며 저장하거나 화면을 옮기면 기록이 초기화된다. 텍스트 입력칸에서는 브라우저의 글자 실행 취소가 그대로 동작한다.

## 실행

저장소 최상위에서 기존 `.venv`를 사용한다. 설치가 없는 다른 개인 환경에서는 Flask 3, Pillow 10 이상만 있으면 된다. 서버는 `127.0.0.1`에만 바인딩한다.

```bash
python annotation/rel_grounding/prepare_pilot.py
.venv/bin/python annotation/rel_grounding/app.py --annotator reviewer_a --port 8766
```

브라우저에서 `http://127.0.0.1:8766/`을 열어 화면마다 bbox·상태·명사구·번역 판정을 저장한다. 다른 검수자는 **별도의 ID와 포트**를 쓴다.

```bash
.venv/bin/python annotation/rel_grounding/app.py --annotator reviewer_b --port 8767
```

각자 화면 오른쪽 위 `내 annotation JSON 내보내기` 링크로 백업한다. 자동 저장 파일은 `annotation/rel_grounding/outputs/<annotator>.json`이며 Git 제외 대상이다. 두 파일을 받으면 다음 명령으로 누락·상태/번역 판정 차이·box IoU를 정리한다.

```bash
python annotation/rel_grounding/summarize_agreement.py \
  annotation/rel_grounding/outputs/reviewer_a.json \
  annotation/rel_grounding/outputs/reviewer_b.json
```

`outputs/agreement/cases.csv`에서 불일치 사례를 사람이 재검토한다. box IoU는 동일 요소 판정의 **대리 지표**일 뿐이며, 작거나 긴 UI 요소에서 낮게 나올 수 있다. 모든 차이를 자동으로 한쪽 bbox로 채택하지 않는다.

## 다음 게이트

파일럿의 독립 검수와 조정이 끝나야 요소 정의, 제외 기준, 좌표 출력 프롬프트, 주 분석 표본을 최종 동결할 수 있다. 이 단계 전에 기존 O/R 예측의 flip에 따라 문항을 제외하거나 위치 지정 prompt를 조정하지 않는다. 파일럿 12문항은 주 분석에서 제외한다. 전체 설계의 해석 한계는 [설계 검토안](../../followup_rel_4lang/GROUNDING_DESIGN_REVIEW_KO.md)에 적었다.
