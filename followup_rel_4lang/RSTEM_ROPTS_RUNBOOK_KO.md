# Qwen3 R_stem / R_opts 실행 안내 (RTX 4090 한 장)

작성: 2026-11-09. 이 안내의 명령은 로컬에서 가짜 모델(`--mock-model`)과 `--dry-run`으로만 검사했다. GPU 실행은 하지 않았다(미검증).

## 무엇을 돌리나

REL 위치 지정 본 분석과 같은 158문항 × 불일치 언어쌍 12개 = 1,896쌍에 네 조건을 돌린다.

| 조건 | 질문 속 기준 요소 표현 | A–D 보기의 참조 표현 | 비고 |
| --- | --- | --- | --- |
| O | 질문 언어 | 질문 언어 | 11월 7일에 돌린 조건, 같은 실행에서 다시 돌림 |
| R_stem | 화면 언어 | 질문 언어 | 새 조건 |
| R_opts | 질문 언어 | 화면 언어 | 새 조건 |
| R | 화면 언어 | 화면 언어 | 11월 7일에 돌린 조건, 같은 실행에서 다시 돌림 |

추론은 1,896 × 4 = 7,584회다. 한 쌍의 네 조건이 한 배치(크기 4)에 같이 들어가므로 네 조건은 같은 화면, 같은 배치 안에서 비교된다. 다시 돌린 O·R은 11월 7일 답과 비교해 재현성을 확인하는 데 쓴다.

입력은 `grounding_eval/build_protocol_inputs.py`가 만든 잠긴 입력(`input_lock.json`의 해시와 같음)이다. 실행기 `run_rel_mixed.py`는 시작 전에 모든 새 행이 고정 데이터의 O·R 문자열을 정확히 재조합한 것인지(같은 이미지·정답·보기 순서) 검사한다. 모델 적재·프롬프트·배치·파싱·라벨 점수는 11월 7일 실행기(`run_rel_followup.py`)의 함수를 그대로 쓴다.

## 예상 시간과 비용

- 추론: 11월 7일 실측 평균 0.6~0.75초/회 기준 약 75~95분.
- 준비: 패키지 설치, 모델 17GB와 REL 이미지 다운로드에 30~60분. 서버 사정에 따라 다르다.
- 합계 약 2.5~3시간. Vast.ai RTX 4090 시간당 요금 × 3시간이다. 요금은 인스턴스마다 달라 확인 필요.

## 위험과 대처

| 위험 | 크기 | 대처 |
| --- | --- | --- |
| 인스턴스를 끄지 않아 요금이 계속 나감 | 시간당 요금 그대로 | 결과를 받은 뒤 Vast.ai 콘솔에서 **Destroy**까지 누른다. Stop만 하면 디스크 요금이 남는다 |
| 서버 코드가 11월 7일과 다름 | 결과 비교 불가 | 사전 점검이 코드 해시, torch·transformers 버전, 설정 해시를 비교해 다르면 멈춘다. 멈추면 그대로 두고 알려준다 |
| 11월 7일 커밋을 원격에서 못 찾음 | 실행 불가 | `git checkout`이 실패하면 진행하지 말고 알려준다 |
| 배치 4에서 메모리 부족 | 실행 중단 | `--strict-batch-size`라 자동으로 배치를 바꾸지 않고 멈춘다. 배치를 바꾸면 비교 조건이 달라지므로 임의로 바꾸지 말고 알려준다 |
| SSH 끊김 | 중단 | `tmux` 안에서 실행한다. 끊겨도 같은 명령을 다시 치면 이어서 돈다 |
| 디스크 부족 | 다운로드 실패 | 인스턴스 디스크 80GB 이상 |

## 1. 인스턴스와 코드

RTX 4090 1장, RAM 48GB 이상, 디스크 80GB 이상, CUDA 13.0 PyTorch를 지원하는 템플릿. **On-demand 인스턴스**를 고른다. Interruptible은 중간에 다른 호스트로 옮겨질 수 있고, 그러면 실행 기록의 플랫폼 문자열이 바뀌어 이어서 돌리기(`--resume`)가 거부된다. 접속 후 `tmux new -s rstem`으로 세션을 열고 그 안에서 진행한다.

```bash
cd /workspace
git clone --branch followup-rel-4lang-inference https://github.com/dltmdwoOS/mpr-gui-crosslocale.git
cd mpr-gui-crosslocale
git checkout 666440011f538cd9336794c9965429de640843c3   # 11월 7일 Qwen3 실행 커밋
git log -1 --format=%H
```

## 2. 추가 파일 올리기

로컬의 `rstem_ropts_addon_20261109.tar.gz`를 서버 `/workspace/mpr-gui-crosslocale/`에 올린다(Jupyter 업로드 또는 `scp`). 이 묶음은 `followup_rel_4lang/` 아래에 새 파일만 추가하며 기존 파일을 바꾸지 않는다.

```bash
tar -tzf rstem_ropts_addon_20261109.tar.gz          # 들어갈 파일 목록 확인
tar -xzf rstem_ropts_addon_20261109.tar.gz --skip-old-files
sha256sum -c followup_rel_4lang/rstem_ropts_inputs/ADDON_SHA256SUMS
```

## 3. 환경과 데이터

```bash
export XDG_CACHE_HOME="$PWD/.cache" HF_HOME="$PWD/.cache/huggingface"
export TORCH_HOME="$PWD/.cache/torch" PIP_CACHE_DIR="$PWD/.cache/pip"
export CUDA_VISIBLE_DEVICES=0 HF_HUB_DISABLE_XET=1
python3 --version    # 11월 7일은 3.12.15. 3.12가 아니면 진행하지 말고 알려준다
python -m venv .venv && source .venv/bin/activate
python -m pip install -r 01_code/requirements-qwen3-4090.txt
python -m pip install -e './01_code[models]'
source followup_rel_4lang/qwen3_4090_env.sh
python followup_rel_4lang/data_bundle.py unpack
python followup_rel_4lang/data_bundle.py fetch-images --workers 2
python followup_rel_4lang/data_bundle.py verify
hf download Qwen/Qwen3-VL-8B-Instruct --revision "$QWEN3_REVISION"
```

6×6 데이터(`download_mpr_gui.sh`)는 이번 실험에 필요 없다.

## 4. 실행

먼저 3문항(144회)으로 확인한다. 몇 분 걸린다.

```bash
bash followup_rel_4lang/run_rstem_ropts.sh smoke
cat followup_rel_4lang/results/qwen3_rstem_ropts/logs/smoke_gate.log
```

확인 기준: 144행 모두 성공, 모든 배치가 한 쌍의 네 조건, 답 파싱 실패 2개 이하, 다시 돌린 O·R의 답이 11월 7일 답과 90% 이상 같음. 하나라도 어긋나면 스크립트가 멈춘다. 멈추면 `smoke_gate.log`를 보내준다.

통과하면 본 실행을 한다.

```bash
bash followup_rel_4lang/run_rstem_ropts.sh full
```

진행 확인은 다른 tmux 창에서 한다.

```bash
cat followup_rel_4lang/results/qwen3_rstem_ropts/STATUS
tail -n 3 followup_rel_4lang/results/qwen3_rstem_ropts/logs/full.log
nvidia-smi
```

## 5. 결과 받기와 정리

`STATUS`에 `ALL DONE`이 뜨면 `followup_rel_4lang/results/qwen3_rstem_ropts_YYYYMMDD.tar.gz`를 내려받는다. 로컬에서 파일이 열리는지 확인한 뒤 Vast.ai에서 인스턴스를 **Destroy**한다.
