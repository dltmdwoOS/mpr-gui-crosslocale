# REL 4언어 O/R/C/F 추론

366문항(dependent 302 / independent 64)에 영어·중국어·태국어·러시아어의
16언어쌍과 O/R/C/F를 적용한다. 질문과 A–D 보기를 함께 조작하고 GUI 이미지,
정답·보기 순서는 언어쌍 안에서 고정한다.

| 조건 | 문맥 | 참조 표현 |
|---|---|---|
| O | 원래 질의 언어 | 원래 질의 언어 |
| R | 원래 질의 언어 | GUI 언어 |
| C | GUI 언어 | 원래 질의 언어 |
| F | GUI 언어 | GUI 언어 |

참조 표현은 기존 병렬 QAS에서 추출한 proxy다. 간단한 Codex 점검과 구조 검증
후 사람 검수 전 탐색 추론을 실행한다. `human_reviewed`와 `screenshot_verified`는
그대로 false이며, 전수 의미·화면 레이블 검수 완료를 의미하지 않는다.

Qwen2.5-VL-7B-Instruct와 InternVL2.5-8B의 기존 고정 revision/config를 재사용한다.
BF16·양자화 없음·batch size 1·greedy·최대 2토큰,
영어 시스템 프롬프트 고정이다. 주 지표는 `generation_correct`, first-token
label score는 별도 보조 지표다. `correct`도 이 러너에서는 생성 정답률을 뜻한다.
이미지 전처리도 기존 설정을 유지한다: Qwen `min_pixels=262144`,
`max_pixels=2097152`; InternVL 448px 타일 최대 7개+thumbnail(최대 2,048 visual tokens).
Qwen config의 `vision_token_limit: 2048`은 메타데이터이며 러너가 강제하는 상한은 아니다.
실제 Qwen 해상도 제한은 [processor의 픽셀 설정](https://huggingface.co/docs/transformers/v4.49.0/model_doc/qwen2_5_vl#image-resolution-trade-off)으로 적용된다.

모델당 23,424조건 행이며 같은 문항·언어쌍 안의 동일 입력만 재사용해
18,432회 추론한다. 두 모델은 순차 실행한다. 주 분석은 불일치 12언어쌍이고,
일치 4언어쌍은 별도 기준 조건이다. 알려진 원본 문제 14문항·100언어쌍도
추론하지만 해당 400행은 주 분석에서 제외한다. 완전한 quartet 안에서
R−O, F−C, C−O, F−R을 dependent/independent별로 비교하고
`(F−C)−(R−O)`를 보조 상호작용으로 요약한다. 동일 입력은
독립 관측으로 세지 않으며 최종 신뢰구간은 문항의 반복 구조를 고려한다.

## 데이터 전달

Git에는 코드·이 설명·`dataset_lock.json`·간단한 검수 기록과 약 1.6MiB의
고정 생성 데이터 `bundles/rel_all_366.tar.gz`를 올린다. 별도 SCP 없이 clone하면
질문 데이터가 함께 온다. 이미지 1,464개(약 1.3GiB)는 서버에서 고정 HF revision으로 내려받는다.
압축 파일과 모든 이미지의 SHA-256을 검증한다. 전체 MPR-GUI 다운로드는 필요 없다.
이미지가 서버 네트워크에서 안 받아지는 경우 `pack --include-images`로
이미지까지 포함한 별도 패키지와 그 패키지의 lock을 함께 전달한다.
파생 데이터는 [MPR-GUI-Bench 데이터 조건](../01_code/THIRD_PARTY_DATA.md)을 따른다.

로컬에서 패키지를 다시 만들 때(작업공간 최상위):

```powershell
python -X utf8 followup_rel_4lang/data_bundle.py pack
```

패키지를 다시 만들면 SHA-256이 달라질 수 있으므로 압축 파일과
`dataset_lock.json`을 함께 Git에 갱신한다. 이미지 포함 패키지는 Git에 넣지 않고
SCP/SFTP로 별도 전달한다.

서버에서 clone한 저장소 최상위:

```bash
git clone --branch followup-rel-4lang-inference https://github.com/dltmdwoOS/mpr-gui-crosslocale.git
cd mpr-gui-crosslocale
python followup_rel_4lang/data_bundle.py unpack
python followup_rel_4lang/data_bundle.py fetch-images
python followup_rel_4lang/data_bundle.py verify
```

## B200 실행

Blackwell을 지원하는 CUDA PyTorch/torchvision 환경을 먼저 사용한다.
기존 CUDA PyTorch를 보존하는 `--system-site-packages` venv도 가능하다.
아래 설치는 CUDA PyTorch를 별도로 설치하지 않는다. 현재 모델 어댑터의
Transformers 범위는 4.57.x다.

```bash
python -m pip install -e '01_code[models]'
python followup_rel_4lang/run_inference.py \
  --model-config 01_code/configs/models/qwen2_5_vl_7b.yaml \
  --output-dir followup_rel_4lang/results/preflight --dry-run
bash followup_rel_4lang/run_b200.sh smoke
bash followup_rel_4lang/run_b200.sh full
```

smoke는 두 집단에서 1문항씩, 총 2문항의 모든 조건을 평가한다. 두 모델의
`summary.json`에서 실행 실패·파싱 실패와 메모리를 확인한 뒤 full을 실행한다.
메모리는 `nvidia-smi`로 확인하며 러너는 GPU 0 하나를 사용한다.
로그를 유지하려면 tmux 안에서 실행한다. 중단 시 같은 명령으로 재개한다.
로컬 연결 점검은 `--dry-run` 또는 `--mock-model`로 수행하며 GPU나 모델 다운로드가 없다.

출력은 모델·smoke/full별 디렉터리에 저장한다.

- `run_contract.json`: 데이터·모델·프롬프트·코드 지문. 다른 설정의 결과 혼합 차단.
- `predictions.jsonl`: 실제 추론의 append-only 기록. 성공한 입력은 재개 시 건너뛴다.
- `results.jsonl`: 재사용 출처와 문제 표시를 포함한 모든 조건 행.
- `summary.json`: 완전하고 문제 표시가 없는 불일치 quartet의 집단별 정확도·paired 차이.
- `plan.json`, `data_audit.json`: 실행 수량·입력 검증. dry-run은 별도 계획 파일만 만든다.

실행 실패는 null로 보존하며 quartet 전체를 요약에서 제외한다. 파싱 실패는
생성 정답률에서 오답이다. 연속 실행 실패 3회면 중지한다. 결과 요약은 기술 통계이며
최종 GLMM·bootstrap 신뢰구간은 별도 분석 단계다. 미완료 실행은 종료 코드가 0이 아니다.
