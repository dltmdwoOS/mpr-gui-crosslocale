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

## 설치 및 이미지 준비

저장소 **최상위 디렉터리**에서 실행한다. Python **3.10 이상**이 필요하다. 검수 UI에는 GPU·PyTorch·모델 가중치가 필요 없으며 [`requirements.txt`](requirements.txt)의 Flask와 Pillow만 설치한다. 아래 `.venv-rel-grounding`은 이 검수 전용 환경이며 Git에 포함되지 않는다. 기존 `.venv`가 없어도 된다.

### Linux 연구실 서버

개인 캐시 위치를 설정하고 가상환경을 만든다. 기존 `.venv-rel-grounding`이 있으면 생성 명령을 건너뛴다.

```bash
cd /home/jovyan/seungjae/mpr-gui-crosslocale
export XDG_CACHE_HOME=/home/jovyan/seungjae/.cache
export HF_HOME=/home/jovyan/seungjae/.cache/huggingface
export TORCH_HOME=/home/jovyan/seungjae/.cache/torch
export PIP_CACHE_DIR=/home/jovyan/seungjae/.cache/pip
python3 --version
python3 -m venv .venv-rel-grounding
.venv-rel-grounding/bin/python -m pip install -r annotation/rel_grounding/requirements.txt
```

새 clone에서는 먼저 Git에 들어 있는 고정 질문 묶음을 풀고 이미지를 준비한다. 이미지가 이미 있으면 `fetch-images`를 생략하고 `verify`부터 실행한다. 새 환경에서 `fetch-images`는 1,464개 이미지(약 1.3 GiB)를 내려받으며, 같은 파일이 이미 있으면 checksum을 확인하고 재사용한다. 검수 도구는 이미지의 별도 사본을 만들지 않는다.

```bash
.venv-rel-grounding/bin/python followup_rel_4lang/data_bundle.py unpack
# 새 clone에 이미지가 없을 때만:
.venv-rel-grounding/bin/python followup_rel_4lang/data_bundle.py fetch-images --workers 3
.venv-rel-grounding/bin/python followup_rel_4lang/data_bundle.py verify
.venv-rel-grounding/bin/python annotation/rel_grounding/prepare_pilot.py
```

### Windows PowerShell

Python launcher에서 3.10 이상이 선택되는지 `py -3 --version`으로 확인한다. 더 오래된 버전이 선택되면 아래 `py -3`을 설치된 3.10 이상 버전의 선택자(예: `py -3.12`)로 바꾼다. `py`가 없다면 3.10 이상인 `python` 명령을 사용한다. 활성화 스크립트 없이 가상환경의 Python을 직접 호출하므로 PowerShell 실행 정책을 바꿀 필요가 없다.

```powershell
# 먼저 저장소 최상위 디렉터리로 이동
$env:PIP_CACHE_DIR = Join-Path $env:LOCALAPPDATA 'mpr-gui-crosslocale\pip'
py -3 --version
py -3 -m venv .venv-rel-grounding
.\.venv-rel-grounding\Scripts\python.exe -m pip install -r annotation\rel_grounding\requirements.txt
```

기존 `.venv-rel-grounding`이 있으면 `py -3 -m venv`는 생략한다. 새 clone에서 다음을 실행한다. 이미지가 이미 준비되어 있으면 `fetch-images` 줄은 생략한다.

```powershell
.\.venv-rel-grounding\Scripts\python.exe followup_rel_4lang\data_bundle.py unpack
# 새 clone에 이미지가 없을 때만:
.\.venv-rel-grounding\Scripts\python.exe followup_rel_4lang\data_bundle.py fetch-images --workers 3
.\.venv-rel-grounding\Scripts\python.exe followup_rel_4lang\data_bundle.py verify
.\.venv-rel-grounding\Scripts\python.exe annotation\rel_grounding\prepare_pilot.py
```

`prepare_pilot.py`는 Git에 포함된 `data/frame.json`과 `data/pilot_manifest.json`이 잠금 데이터·이미지와 같은지 확인하며, 다른 내용으로 덮어쓰지 않는다. 이미지가 없거나 checksum이 다르면 여기서 중지한다.

## 검수 UI 실행

두 검수자는 각각 **다른 이름과 포트**를 사용한다. 앱은 `127.0.0.1`에만 바인딩한다. 아래는 첫 번째 검수자의 명령이다. 두 번째 검수자는 `reviewer_b --port 8767`로 바꿔 **별도 터미널**에서 실행한다.

Linux:

```bash
.venv-rel-grounding/bin/python annotation/rel_grounding/app.py --annotator reviewer_a --port 8766
```

Windows PowerShell:

```powershell
.\.venv-rel-grounding\Scripts\python.exe annotation\rel_grounding\app.py --annotator reviewer_a --port 8766
```

브라우저에서 해당 `http://127.0.0.1:포트/`를 연다. 원격 연구실 서버에서 실행할 때는 사용 중인 원격 접속 도구로 포트를 로컬에 전달한 뒤 브라우저를 연다.

화면마다 bbox·상태·명사구·번역 판정을 저장한다. 오른쪽 위 `내 annotation JSON 내보내기`로 백업할 수 있다. 자동 저장 파일은 `annotation/rel_grounding/outputs/<annotator>.json`이며 Git 제외 대상이다. 두 파일을 받은 뒤 누락·판정 차이·box IoU를 정리한다.

Linux:

```bash
.venv-rel-grounding/bin/python annotation/rel_grounding/summarize_agreement.py \
  annotation/rel_grounding/outputs/reviewer_a.json \
  annotation/rel_grounding/outputs/reviewer_b.json
```

Windows PowerShell:

```powershell
.\.venv-rel-grounding\Scripts\python.exe annotation\rel_grounding\summarize_agreement.py `
  annotation\rel_grounding\outputs\reviewer_a.json `
  annotation\rel_grounding\outputs\reviewer_b.json
```

`outputs/agreement/cases.csv`에서 불일치 사례를 사람이 재검토한다. box IoU는 동일 요소 판정의 **대리 지표**일 뿐이며, 작거나 긴 UI 요소에서 낮게 나올 수 있다. 모든 차이를 자동으로 한쪽 bbox로 채택하지 않는다.

## 다음 게이트

파일럿의 독립 검수와 조정이 끝나야 요소 정의, 제외 기준, 좌표 출력 프롬프트, 주 분석 표본을 최종 동결할 수 있다. 이 단계 전에 기존 O/R 예측의 flip에 따라 문항을 제외하거나 위치 지정 prompt를 조정하지 않는다. 파일럿 12문항은 주 분석에서 제외한다. 전체 설계의 해석 한계는 [설계 검토안](../../followup_rel_4lang/GROUNDING_DESIGN_REVIEW_KO.md)에 적었다.
