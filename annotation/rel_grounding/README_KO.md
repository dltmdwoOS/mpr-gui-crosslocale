# REL grounding: 전체 문항 화면 위치 표시

처음 검수한다면 [빠른 안내](QUICK_GUIDE_KO.md)를 먼저 읽는다.

## 목적과 범위

질문의 노란 표현이 실제 화면에서 가리키는 요소에 상자를 그린다. 두 사람은 서로의 기록을 보지 않고 작업한다. 모델 예측과 정답은 작업 화면·manifest에 들어 있지 않다.

전체 작업 대상은 구조적으로 선별된 **179문항 × EN/ZH/TH/RU 네 화면 = 716개 화면**이다. `prepare_pilot.py`는 잠금 데이터에서 `data/full_manifest.json`과 기존 `data/pilot_manifest.json`을 함께 만든다. 이전에 고른 파일럿 12문항도 전체 목록에 포함되며 화면에 표시된다. 주 분석에서는 이 12문항을 제외한다. 이미지는 복사하지 않고 기존 `followup_rel_4lang/assets/images`를 사용한다.

## bbox와 텍스트 판정 규칙

각 문항·GUI 언어마다 다음을 기록한다.

1. 각 카드의 **가리키는 말**은 노란 표현으로 미리 채워진다. 필요하면 질문에 나온 표현을 그대로 써서 `the blue 'Search' button`처럼 요소 종류까지 늘린다. 질문 전체나 관계를 묻는 절은 넣지 않는다. 이 문구는 이후 모델에게 위치를 물을 때 사용한다.
2. **대상 그리기**를 선택하고 네 이미지 각각에서 해당 요소 전체를 드래그한다. 버튼이면 버튼, 스위치면 스위치를 둘러싼다. 글자와 컨트롤이 떨어져 있으면 **글자 그리기**로 주황 상자를 추가할 수 있다. 작은 요소는 카드의 **크게**를 누른 뒤 그린다.
3. 상자를 그릴 수 있으면 **상태: 찾음**과 **종류**를 고른다. 대상이 애매하거나 여러 개이거나 화면에 없으면 해당 상태를 고르고 **추가 확인 · 메모**에 이유를 쓴다. 이런 경우 임의로 큰 상자를 그리지 않는다.
4. 영어와 같은 뜻인지 묻는 두 항목은 모두 **예**로 시작한다. 지금은 번역을 전수 검증하지 않는다. 뚜렷한 차이나 의심이 있을 때만 **추가 확인 · 메모**에서 바꾸고 이유를 적는다. 따라서 저장된 `yes`는 번역이 검증되었다는 뜻이 아니다.
5. 네 화면을 마치면 **저장하고 다음**을 누른다. 문항 번호를 입력해 이동할 수도 있다. 기존 gold 답이나 모델 출력을 찾지 않는다.

**찾음**에는 원본 이미지 픽셀 기준의 대상 상자와 종류가 필요하다. **가리키는 말**은 질문의 정확한 일부여야 하며 노란 표현을 한 번 포함해야 한다. **찾음**이 아니거나 뜻 비교를 바꾸면 메모가 필요하다. 네 화면은 한 번에 저장되므로 오류가 있으면 해당 언어를 고친 뒤 다시 저장한다.

네 화면에서 상자 그리기·지우기와 상태 변경은 `Ctrl+Z`(Mac `⌘Z`) 또는 **↶ 취소**로 되돌릴 수 있다. 최근 30번까지 가능하며 저장하거나 문항을 옮기면 기록이 초기화된다. 텍스트 칸의 `Ctrl+Z`는 글자 입력만 되돌린다.

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

`prepare_pilot.py`는 `frame.json`, `pilot_manifest.json`, `full_manifest.json`이 잠금 데이터·이미지와 같은지 확인하며, 다른 내용으로 덮어쓰지 않는다. 이미지가 없거나 checksum이 다르면 여기서 중지한다.

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

상단 **내보내기**로 백업할 수 있다. 전체 작업 저장 파일은 `annotation/rel_grounding/outputs/<annotator>.full.json`이며 Git 제외 대상이다. 예전 파일럿 기록인 `<annotator>.json`과 분리된다. 파일럿만 다시 열려면 `--manifest annotation/rel_grounding/data/pilot_manifest.json`을 추가한다. 두 사람의 전체 작업 파일을 비교하려면 다음을 실행한다.

Linux:

```bash
.venv-rel-grounding/bin/python annotation/rel_grounding/summarize_agreement.py \
  annotation/rel_grounding/outputs/reviewer_a.full.json \
  annotation/rel_grounding/outputs/reviewer_b.full.json
```

Windows PowerShell:

```powershell
.\.venv-rel-grounding\Scripts\python.exe annotation\rel_grounding\summarize_agreement.py `
  annotation\rel_grounding\outputs\reviewer_a.full.json `
  annotation\rel_grounding\outputs\reviewer_b.full.json
```

`outputs/agreement/cases.csv`에서 불일치 사례를 사람이 재검토한다. box IoU는 동일 요소 판정의 **대리 지표**일 뿐이며, 작거나 긴 UI 요소에서 낮게 나올 수 있다. 모든 차이를 자동으로 한쪽 bbox로 채택하지 않는다.

## 다음 게이트

전체 작업을 시작할 수 있지만 아직 grounding 진단의 프롬프트와 분석 규칙이 동결된 것은 아니다. 파일럿 12문항의 판정 차이를 먼저 검토하고, 주 분석에서는 이 12문항을 제외한다. 뜻 비교의 기본값 `yes`는 검증 결과로 해석하지 않는다. 실험 해석과 남은 결정은 [설계 검토안](../../followup_rel_4lang/GROUNDING_DESIGN_REVIEW_KO.md)에 있다.
