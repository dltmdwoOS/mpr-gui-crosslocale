# REL Text Dependency Annotation Tool

REL 366개 semantic item 전체를 독립 annotation하는 로컬 웹 도구다. 정답은 표시하지만 모델 output과 다른 annotator의 판정은 표시하지 않는다.

## 현재 준비된 데이터

- Source: 잠금된 MPR-GUI GitHub commit `e4f1cfcd11ee0d0dfa8ee6a0a97c2c782ce21aba`
- Image source: Hugging Face revision `c1edb808d424a2fa7bc4a2e601d39b431b04acd5`
- Ordering seed: `20260803`
- Full size: 366 items
- Images: 366 × 6 = 2,196개
- Gold: manifest에는 없으며, 요청에 따라 잠금 QAS에서 runtime으로 연결해 정답 option에 녹색 테두리 표시
- 모델 output: UI에서 제외
- 한국어: quoted GUI token을 보존한 기계 번역 보조 자료

처음 48개는 guideline pilot에서 사용한 source-stratified 순서가 그대로 유지된다. 나머지 318개가 뒤에 추가되므로 기존 pilot annotation을 잃지 않고 전체 REL annotation으로 이어갈 수 있다.

## 처음 설치 및 데이터 준비

이미지·QAS·번역·pilot manifest는 Git에 포함하지 않는다. 각 annotator가 저장소를 받은 뒤 한 번 준비한다.

### Windows 11 PowerShell

```powershell
python -m venv .venv-rel-annotation
.\.venv-rel-annotation\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r annotation/rel_text_dependency/requirements.txt
python annotation/rel_text_dependency/prepare_pilot.py --sample-size 366 --seed 20260803 --workers 8
```

### macOS Terminal

Python 3.10 이상과 Git이 필요하다. 저장소 루트에서:

```bash
python3 -m venv .venv-rel-annotation
source .venv-rel-annotation/bin/activate
python -m pip install --upgrade pip
python -m pip install -r annotation/rel_text_dependency/requirements.txt
python annotation/rel_text_dependency/prepare_pilot.py \
  --sample-size 366 \
  --seed 20260803 \
  --workers 8
```

처음 준비할 때 잠금된 MPR-GUI QAS와 2,196개 이미지를 내려받고 한국어 보조 번역을 생성하므로 네트워크 연결이 필요하다. 같은 seed와 source revision을 사용하면 두 annotator에게 동일한 366개 문항과 순서가 만들어진다.

## 기존 48-item pilot에서 전체 366개로 확장

먼저 실행 중인 annotation server를 `Ctrl+C`로 종료하고 UI의 `CSV export`로 한 번 백업한다. 이후 저장소 루트에서 다음을 실행한다.

Windows PowerShell:

```powershell
python annotation/rel_text_dependency/prepare_pilot.py `
  --sample-size 366 `
  --seed 20260803 `
  --workers 8
```

macOS Terminal:

```bash
python annotation/rel_text_dependency/prepare_pilot.py \
  --sample-size 366 \
  --seed 20260803 \
  --workers 8
```

기존 SQLite를 삭제하거나 수정할 필요는 없다. 저장된 label, review flag, note와 annotation time은 `parallel_id` 기준으로 그대로 유지된다. 첫 48개 순서도 유지되며, server를 다시 시작할 때 새 manifest의 순서와 provenance metadata만 자동 정합화된다. 기존 288개 이미지는 재사용하고 나머지만 다운로드한다.

## 가장 간단한 실행

### Windows 11 PowerShell

저장소 루트의 PowerShell에서:

```powershell
powershell -ExecutionPolicy Bypass -File annotation/rel_text_dependency/run_annotation.ps1 -AnnotatorId coex0
```

브라우저가 자동으로 `http://127.0.0.1:8765`를 연다. 종료할 때 PowerShell 창에서 `Ctrl+C`를 누른다.

직접 실행할 수도 있다.

```powershell
python annotation/rel_text_dependency/app.py --open-browser --annotator coex0
```

### macOS Terminal

가상환경을 활성화한 상태에서 annotator별로 서로 다른 ID를 지정한다.

```bash
./annotation/rel_text_dependency/run_annotation.sh team_member_mac
```

실행 권한이 없다면 다음 중 하나를 사용한다.

```bash
chmod +x annotation/rel_text_dependency/run_annotation.sh
./annotation/rel_text_dependency/run_annotation.sh team_member_mac
```

```bash
python annotation/rel_text_dependency/app.py \
  --open-browser \
  --annotator team_member_mac
```

브라우저가 자동으로 열리지 않으면 `http://127.0.0.1:8765`를 직접 연다. 종료는 Terminal에서 `Ctrl+C`다.

## 단축키

| 키 | 기능 |
|---|---|
| `1` | Text-dependent로 저장하고 다음 item |
| `2` | Text-independent로 저장하고 다음 item |
| `F` | 검토 필요 flag 전환 및 저장 |
| `S` | 현재 상태 저장 |
| `J` / `←` | 이전 item |
| `K` / `→` | 다음 item |
| `[` / `]` | 이전·다음 GUI locale |
| `Z` | screenshot 확대 |
| `Esc` | 확대 닫기 |

Label을 누르면 자동 저장 후 다음 item으로 이동한다. Note는 입력창에서 포커스가 빠질 때 저장된다.

## 결과 저장과 export

내부 결과는 다음 SQLite에 annotator별로 저장된다.

```text
annotation/rel_text_dependency/outputs/rel_text_dependency.sqlite3
```

화면 오른쪽 위 `CSV export`를 누르면 현재 annotator의 결과만 내려받는다. annotator마다 각자 clone한 저장소와 고유 ID를 사용하면 상대방의 label이 보이지 않는다. SQLite 파일은 Git에 포함하지 말고, 완료한 CSV만 연구 책임자에게 전달한다.

중간 백업을 위해 annotation을 마칠 때마다 CSV export를 권장한다.

## 두 annotator agreement

각 annotator의 CSV를 받은 뒤:

Windows PowerShell:

```powershell
python annotation/rel_text_dependency/summarize_agreement.py `
  path/to/rel_pilot_annotator_A.csv `
  path/to/rel_pilot_annotator_B.csv `
  --output-dir annotation/rel_text_dependency/outputs/agreement
```

macOS Terminal:

```bash
python annotation/rel_text_dependency/summarize_agreement.py \
  path/to/rel_pilot_annotator_A.csv \
  path/to/rel_pilot_annotator_B.csv \
  --output-dir annotation/rel_text_dependency/outputs/agreement
```

다음이 생성된다.

- `agreement_summary.json`: raw agreement, expected agreement, Cohen’s κ, confusion counts
- `disagreements.csv`: adjudication 대상과 양쪽 note

## 데이터를 다시 준비하는 경우

로컬에서 준비를 마쳤다면 다시 실행할 필요가 없다.

```powershell
python annotation/rel_text_dependency/prepare_pilot.py `
  --sample-size 366 `
  --seed 20260803 `
  --workers 8
```

이 명령은 잠금된 QAS, 2,196개 이미지와 한국어 보조 번역을 준비한다. 같은 seed와 source revision에서는 같은 semantic items와 순서가 선택된다. 파일명 `pilot_manifest.json`은 기존 설치와의 호환성을 위해 유지한다.

## 검증

```powershell
pytest -q annotation/rel_text_dependency/tests/test_annotation_tool.py
python annotation/rel_text_dependency/validate_ui.py
```

브라우저 검증 screenshot은 `validation/ui_1440x900.png`에 저장된다.

macOS의 자동 브라우저 검증은 `/Applications`의 Chrome, Edge 또는 Chromium을 찾는다. 다른 위치라면 실행 파일을 지정한다.

```bash
CHROME_PATH="/path/to/Google Chrome" \
  python annotation/rel_text_dependency/validate_ui.py
```
