# RTX 4090 실행 보충 자료

[최종 보고서](../../QWEN3_RTX4090_RESULTS_KO.md)의 재현과 검토에 필요한 작은 자료를 함께 보존한다. 기존 [49개 핵심 파일 묶음](../rtx4090_20261105/artifact_manifest.json)은 그대로 유지했다. 이 폴더의 20개 자료는 별도 [SHA-256 manifest](artifact_manifest.json)로 검증한다. `.gz`에는 압축 전 내용의 SHA-256도 있다.

| 자료 | 용도 |
| --- | --- |
| 네 대조·파일럿 폴더의 `input_plan.json.gz` | 실제 실행한 문항·언어쌍·조건·설명·GT의 정확한 계획과 실행 계약의 입력 지문 대조 |
| `6x6_smoke_manifest.jsonl.gz`, `6x6_smoke_plan.json` | 한 REL 문항의 36언어 조합 실행 재현 |
| `rel_qwen3_smoke/` | 실제 추론 80개·128조건 행의 계획과 데이터 감사 |
| `main_v2_dry_run.json`, `main_descriptors_draft_v2_summary.json` | 검토 초안에 대한 158문항·5,688입력 계획 확인. 본 분석 추론 결과가 아님 |
| `qwen25_pinned_config.json` | Qwen2.5의 패치 커널·출력 채널 등 형상 대조 근거. 가중치나 전체 모델 실행 결과가 아님 |
| `source_metadata.json`, `source_inventory.json`, `hf_rate_limit.json` | 고정 데이터 출처, 범위·크기, 다운로드 재개 당시 요청 한도 응답 |
| `checks/` | 최종 회귀 검사 67통과·1생략 및 cross-locale 18통과, GT 이미지 검증, manifest 생성, 추가 추론 없는 파일럿 재개 기록 |

Qwen2.5 설정은 [고정 revision의 원본 config](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct/blob/cc594898137f460bfe9f0759e9844b3ce807cfb5/config.json)에서 받았다. 경로 선택 대조는 [별도 JSON](../qwen25_qwen3_dispatch_20261105.json)에 있다.

`data_6x6_manifest.log`의 13,470행은 RI/SI 질문도 포함한 원본 전체 metadata 수다. 이번 이미지 준비·분석 대상은 6차원의 13,170행이다. GT 이미지 680개의 해시 검증은 의미·역할의 최종 검수와 다르며, 원본의 요소 역할 47개 pending 상태와 설명 초안의 `reviewed=false`를 유지했다.

모델 가중치·이미지·환경 캐시, 원시 결과와 중복되는 진행 로그, 실패 후 교체한 중간 초안은 올리지 않았다. 모델·데이터는 고정 revision/lock으로 다시 준비할 수 있고, 완료한 파일럿·smoke의 원시 응답은 핵심 묶음에 모두 있다. 데이터 파생 내용은 [기존 데이터 조건](../../../01_code/THIRD_PARTY_DATA.md)을 따른다.

기록된 테스트의 실행 위치는 다음과 같다. 먼저 프로젝트와 테스트 의존성을 설치하고 `data_bundle.py unpack`으로 고정 metadata를 준비한다.

```bash
# 저장소 루트
PYTHONPATH="$PWD:$PWD/01_code/src" .venv/bin/python -m pytest -q \
  02_tests/tests --ignore=02_tests/tests/test_cross_locale_inference.py

# 01_code 디렉터리
../.venv/bin/python -m pytest -q ../02_tests/tests/test_cross_locale_inference.py
```
