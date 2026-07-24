# Cross-Locale Smoke Test

실제 모델 실행 전에 cross-locale 평가 파이프라인의 입력 구성과 결과 저장을 확인하기 위한 로컬 테스트입니다.

## 확인 범위

- `en -> ja`, `ja -> en` 방향 구성
- 6개 평가 차원과 12개 semantic item
- 총 24개 평가 입력
- GUI 언어에 맞는 이미지 경로 연결
- A/B/C/D 점수와 확률 계산
- JSONL 저장과 resume 처리
- 방향별 결과 집계

이 테스트는 고정 seed로 생성한 mock score를 사용합니다. 출력되는 accuracy는 모델 성능이 아닙니다.

## 실행

Python 3.10 이상에서 저장소 루트를 기준으로 실행합니다.

```bash
python demo/run_demo.py --clean-demo-output --run-resume-check
```

테스트 코드까지 확인하려면:

```bash
python -m pip install pytest
pytest -q
```

정상 실행 시 24개 평가가 기록되고 `demo/outputs/demo_validation_report.txt`의 모든 항목이 `PASS`로 표시됩니다.

## 파일

- `demo/run_demo.py`: smoke test 실행 파일
- `demo/examples/`: 이전 실행의 요약 결과
- `src/mpr_crosslocale/`: 테스트에서 사용하는 공통 모듈
- `tests/test_demo.py`: smoke test 검증 코드

실제 MPR-GUI 이미지와 모델 체크포인트는 포함하지 않습니다.
