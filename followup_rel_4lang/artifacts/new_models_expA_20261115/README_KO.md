# 새 모델 REL·실험 A 결과와 번역 자료 (2026-11-14 ~ 11-15)

RTX 4090 단일 GPU(Vast)에서 돌린 결과 묶음, 실험 A의 번역 입력, 로컬 분석 코드와 결과표를 모은 폴더입니다. 서버에서 받은 묶음은 sha256을 대조한 뒤 그대로 넣었고, 압축을 풀거나 다시 만들지 않았습니다.

## 폴더 구성

| 경로 | 내용 |
|---|---|
| `packages/qwen3_vl_4b/` | Qwen3-VL-4B REL O/R/C/F + 실험 A O/T/R 원시 결과 (`SHA256SUMS`, `COMPLETE` 포함) |
| `packages/internvl35_4b/` | InternVL3.5-4B, 같은 구성 |
| `packages/uitars_15_7b/` | UI-TARS-1.5-7B, 같은 구성 |
| `packages/internvl25_expA/` | InternVL2.5-8B 실험 A만 (`.sha256` 포함) |
| `packages/expA_8b_20261114/` | Qwen3-VL-8B, InternVL3.5-8B 실험 A (sha는 이 폴더에서 새로 계산한 `SHA256SUMS`) |
| `translation/` | 실험 A의 T 조건 입력 생성 전부: 이름 추출, Gemma 번역 원출력, T 질문 생성, LaBSE 유사도, NLLB 비교, 설계·진단 계획(FROZEN 표시 포함), 대체된 이전 버전(`*_superseded*`) |
| `analysis/newmodels_20261114/` | 새 모델 분석 코드(`run_frozen_analysis.py`, `run_frozen_expA_only.py`, `compile_five_models.py`)와 모델별 `results.json`·`tables_KO.md` |
| `analysis/expA_8b_20261114/` | 8B 두 모델 실험 A 분석과 결과 보고서 |
| `rules/` | 분석 규칙 v1과 부록 1(FROZEN sha 파일 포함), 초안과 대체된 후보 |

묶음 검증: 각 `packages/<모델>/`에서 `shasum -a 256 -c SHA256SUMS` (InternVL2.5의 `.sha256`에는 서버 경로가 적혀 있으므로 `shasum -a 256 *.tar.gz` 값을 파일 첫 칸과 직접 비교).

## 조건 정의 (생성 코드 기준)

REL O/R/C/F는 **이름**과 **이름을 둘러싼 문장**을 따로 바꾸는 2×2 설계입니다(`followup_rel_4lang/generate_variants.py`).

| 조건 | 이름 | 이름을 둘러싼 문장 |
|---|---|---|
| O | 질문 언어 | 질문 언어 |
| R | 화면 언어판 이름 | 질문 언어 |
| C | 질문 언어 | 화면 언어 |
| F | 화면 언어판 이름 | 화면 언어 |

실험 A의 T는 R과 같은 자리의 이름을, 화면을 보지 않은 번역기(Gemma 3 12B, 텍스트만) 출력으로 바꿉니다(`translation/build_T.py`). 답을 고르는 VLM에는 모든 조건에서 화면을 줍니다.

- 바뀌는 자리는 질문과 보기 A–D 양쪽입니다. 따옴표 안 이름만 바뀌고 나머지 문장은 그대로입니다.
- "화면 언어판 이름"은 스크린숏에서 읽은 글자가 아니라 같은 문항의 화면 언어판 질문·보기에서 가져온 이름입니다(`label_provenance=parallel_qas_text_proxy`, `screenshot_verified=false`).
- 실험 A의 "뜻 보존" 부분집합(708쌍)은 사람이 확인한 집합이 아니라 번역–화면판 이름의 LaBSE 유사도 0.7 이상이라는 자동 기준으로 고른 집합입니다.
- 실험 A 1,895쌍 = 158문항 × 불일치 언어쌍 12개(1,896) − 사전 제외 1쌍.

## 아직 없는 것

- UI-TARS 6×6: 서버에서 실행 중. 끝나면 따로 올립니다.
- MiniCPM-V REL·실험 A: 6×6 다음 순서. 끝나면 따로 올립니다.
- 6×6 GLMM(R) 분석: 결과 도착 후.

## 참고

- 분석 기록과 로그에는 작업한 컴퓨터의 절대 경로가 그대로 남아 있습니다. sha 대조와 재현 기록을 위해 고치지 않았습니다.
- 태국어 제외 분석과 태국어 읽기 지표의 0.7 기준은 결과를 본 뒤 정한 것입니다(`rules/분석규칙_v1_부록1.md`). 4언어 전체 결과도 함께 들어 있습니다.
