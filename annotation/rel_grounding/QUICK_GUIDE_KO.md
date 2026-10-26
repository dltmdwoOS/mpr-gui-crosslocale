# Grounding 파일럿 검수: 빠른 안내

두 검수자가 **서로의 기록과 모델 답을 보지 않고** 각자 12문항 × 4개 화면을 검수합니다. 가상환경과 이미지가 없는 새 환경이라면 먼저 [설치 및 이미지 준비](README_KO.md#설치-및-이미지-준비)를 완료하세요. 저장소 최상위에서 고유한 이름으로 실행합니다.

```bash
.venv-rel-grounding/bin/python annotation/rel_grounding/app.py --annotator 내이름 --port 8766
```

Windows PowerShell에서는 `\.venv-rel-grounding\Scripts\python.exe annotation\rel_grounding\app.py --annotator 내이름 --port 8766`을 실행합니다. 브라우저에서 `http://127.0.0.1:8766/`을 엽니다. 두 번째 검수자는 다른 이름과 포트(예: `8767`)를 사용합니다.

1. 노란색 기준 표현을 포함한 **원문 명사구**를 질문 문장에서 그대로 복사합니다. 가능하면 `the blue 'Search' button`처럼 요소 종류까지 포함합니다.
2. 그 명사구가 가리키는 **한 요소**에 파란 bbox를 드래그합니다. 글자와 컨트롤이 떨어져 있으면 글자에 주황 bbox를 추가할 수 있습니다. 대상이 모호하거나 없으면 상태를 선택하고 bbox 대신 이유를 메모합니다.
3. 기준 표현과 A–D 선택지 번역이 영어 버전과 같은 뜻인지 각각 `yes/no/uncertain`으로 표시합니다. 확신이 없으면 `uncertain`과 이유를 적습니다.
4. **저장하고 다음**을 누릅니다. 현재 화면에서 bbox 그리기·지우기나 상태 변경을 되돌리려면 `Ctrl+Z`(Mac `⌘Z`) 또는 **실행 취소**를 누릅니다. 텍스트 칸의 `Ctrl+Z`는 글자 입력만 되돌립니다. 저장하거나 화면을 옮기면 bbox 실행 취소 기록은 초기화됩니다.
5. 끝나면 오른쪽 위 **내 annotation JSON 내보내기**로 파일을 전달합니다.

자세한 판정 기준과 결과 비교 명령은 [전체 안내](README_KO.md)에 있습니다.
