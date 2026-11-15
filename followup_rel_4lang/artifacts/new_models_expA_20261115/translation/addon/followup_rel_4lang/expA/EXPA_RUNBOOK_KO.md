# 실험 A (O·T·R) 실행 안내 (RTX 4090 한 장, 두 모델)

작성: 2026-11-14. 로컬에서 두 모델 모두 `--dry-run`과 가짜 모델(`--mock-model`) 실행으로 검사했다. 가짜 모델 실행은 3문항 smoke와 Qwen3 전체 5,688회다. 실제 GPU 실행은 하지 않았다(미검증).

## 무엇을 돌리나

R_stem/R_opts와 같은 158문항 × 불일치 언어쌍 12개 = 1,896쌍에 세 조건을 돌린다.

| 조건 | 질문 속 참조 이름 |
| --- | --- |
| O | 질문 언어 그대로 (다시 돌림) |
| T | 화면을 보지 않고 화면 언어로 기계 번역한 이름 (새 조건) |
| R | 화면 언어판 질문의 이름 (다시 돌림) |

- 모델당 추론은 1,896 × 3 = 5,688회다.
- 배치: Qwen3-VL-8B는 배치 3(한 배치 = 한 쌍의 세 조건), InternVL3.5-8B는 이전과 같이 배치 1이다.
- 같아야 하는 것: 모델 설정, 프롬프트, 코드, 주요 패키지 버전이 각 모델의 이전 R_stem/R_opts 실행과 같아야 한다. 다르면 사전 점검이 멈춘다.

## 필요한 파일 (로컬 `share_packages/expA_GPU_20261113/`)

| 파일 | 용도 |
| --- | --- |
| `rstem_ropts_addon_20261109.tar.gz` | Qwen3 이전 묶음 |
| `rstem_ropts_internvl_addon_20261110.tar.gz` | InternVL 이전 묶음 |
| `expA_addon_20261114.tar.gz` | 이번 묶음. 두 저장소 폴더에 각각 푼다. sha256은 `EXPA_ADDON_SHA256.txt`에 있다. |

## 예상 시간과 비용

- 추론: Qwen3 약 75분, InternVL3.5 약 70분. 근거는 같은 GPU에서 7,584회에 각각 99분, 93분이 걸린 이전 실측이다.
- 준비: 모델마다 패키지 설치, 모델 약 17GB, 이미지 내려받기에 30~60분.
- 합계: 약 4~4.5시간. 6시간이 넘으면 멈추고 연락한다.

## 위험과 대처

| 위험 | 크기 | 대처 |
| --- | --- | --- |
| 인스턴스를 끄지 않아 요금이 계속 나감 | 시간당 요금 그대로 | 두 결과를 모두 받은 뒤 **Destroy**까지 누른다(Stop만 하면 디스크 요금이 남는다) |
| 두 모델을 동시에 돌림 | 24GB에 두 모델이 안 들어가 둘 다 멈출 수 있음 | Qwen3 `STATUS`에 `ALL DONE`이 뜬 뒤 InternVL을 시작한다 |
| 두 저장소를 한 폴더에 섞음 | 코드 해시가 달라 사전 점검이 멈춤 | Qwen3는 `mpr-gui-crosslocale`, InternVL은 `mpr-ivl`에 따로 둔다 |
| 사전 점검 실패 | 실행 불가 | 그대로 두고 `logs/`의 오류를 보내준다. 임의로 고치지 않는다 |
| 배치 3에서 메모리 부족 (Qwen3) | 실행 중단 | 배치를 자동으로 바꾸지 않고 멈춘다. 알려준다 |
| 디스크 부족 | 내려받기 실패 | 디스크 100GB 이상(모델 2개, 가상환경 2개, 이미지 2벌) |
| SSH 끊김 | 중단 | 모든 명령을 `tmux` 안에서 실행한다. 같은 명령을 다시 치면 이어서 돈다 |
| Interruptible 인스턴스 | 호스트가 바뀌면 이어서 돌리기가 거부됨 | **On-demand**로 빌린다 |
| `git checkout`/`git am` 실패 | 실행 불가 | 진행하지 말고 알려준다(`git am` 실패 시 `git am --abort`) |

`tar`를 풀 때 "Ignoring unknown extended header keyword"라는 경고가 나올 수 있다. macOS에서 묶은 파일이라 생기는 무해한 경고다.

## 1. 인스턴스 빌리고 접속

1. RTX 4090 1장, RAM 48GB 이상, 디스크 100GB 이상, On-demand, CUDA 13.0 PyTorch 템플릿을 고른다.
2. 접속한 뒤 **한 번만** `tmux new -s expA`를 실행한다. 아래 모든 명령은 이 tmux 안에서 한다.
3. 로컬의 세 tar.gz 파일을 서버 `/workspace/`에 올린다(Jupyter 업로드 또는 `scp`).

```bash
cd /workspace && ls *.tar.gz
sha256sum expA_addon_20261114.tar.gz    # EXPA_ADDON_SHA256.txt의 값과 같아야 한다
python3 --version                        # 3.12.x가 아니면 멈추고 알려준다
```

## 2. Qwen3

### 2-1. 코드와 묶음

```bash
cd /workspace
git clone --branch followup-rel-4lang-inference https://github.com/dltmdwoOS/mpr-gui-crosslocale.git
cd mpr-gui-crosslocale
git checkout 666440011f538cd9336794c9965429de640843c3
tar -xzf /workspace/rstem_ropts_addon_20261109.tar.gz --skip-old-files
sha256sum -c followup_rel_4lang/rstem_ropts_inputs/ADDON_SHA256SUMS
tar -xzf /workspace/expA_addon_20261114.tar.gz
(cd followup_rel_4lang/expA && sha256sum -c expA_inputs/EXPA_SHA256SUMS)
```

### 2-2. 환경과 데이터 (30~60분)

```bash
export XDG_CACHE_HOME="$PWD/.cache" HF_HOME="$PWD/.cache/huggingface"
export TORCH_HOME="$PWD/.cache/torch" PIP_CACHE_DIR="$PWD/.cache/pip"
export CUDA_VISIBLE_DEVICES=0 HF_HUB_DISABLE_XET=1
python3 -m venv .venv && source .venv/bin/activate   # venv 오류면: apt-get update && apt-get install -y python3.12-venv
python -m pip install -r 01_code/requirements-qwen3-4090.txt
python -m pip install -e './01_code[models]'
source followup_rel_4lang/qwen3_4090_env.sh
python followup_rel_4lang/data_bundle.py unpack
python followup_rel_4lang/data_bundle.py fetch-images --workers 2
python followup_rel_4lang/data_bundle.py verify
hf download Qwen/Qwen3-VL-8B-Instruct --revision "$QWEN3_REVISION"
```

### 2-3. 실행 (약 75분)

```bash
bash followup_rel_4lang/expA/run_expA.sh qwen3 all
```

`all`은 다음 순서로 진행한다.

1. 사전 점검
2. 3문항 smoke(108회)와 확인
3. 본 실행(5,688회)과 완료 확인
4. 결과 묶기

smoke 확인 기준은 다음과 같다. 하나라도 어긋나면 멈춘다.

- 108행 모두 성공
- 모든 배치가 한 쌍의 O·T·R
- 답 파싱 실패 2개 이하
- 다시 돌린 O·R 답이 11월 7일 답과 90% 이상 같음

진행 확인은 tmux 새 창(`Ctrl-b` 다음 `c`, 창 이동은 `Ctrl-b` 다음 숫자)에서 한다.

```bash
cat /workspace/mpr-gui-crosslocale/followup_rel_4lang/results/expA_qwen3/STATUS
tail -n 3 /workspace/mpr-gui-crosslocale/followup_rel_4lang/results/expA_qwen3/logs/full.log
```

`ALL DONE`이 뜨면 `followup_rel_4lang/results/expA_qwen3_YYYYMMDD.tar.gz`를 내려받는다.

## 3. InternVL3.5 (Qwen3의 `ALL DONE` 뒤에, 같은 인스턴스)

Qwen3 가상환경이 켜진 셸을 쓰지 않는다. tmux 새 창(`Ctrl-b` 다음 `c`)을 열고 시작한다.

### 3-1. 코드, 패치, 묶음

```bash
cd /workspace
git clone --branch followup-rel-4lang-inference https://github.com/dltmdwoOS/mpr-gui-crosslocale.git mpr-ivl
cd mpr-ivl
git checkout 666440011f538cd9336794c9965429de640843c3
tar -xzf /workspace/rstem_ropts_internvl_addon_20261110.tar.gz --skip-old-files
sha256sum -c followup_rel_4lang/rstem_ropts_inputs/ADDON_INTERNVL_SHA256SUMS
git -c user.name=local -c user.email=local@local am rstem_internvl_patches/000*.patch
git log --oneline -6    # 맨 아래가 6664400, 위로 패치 5개
tar -xzf /workspace/expA_addon_20261114.tar.gz
(cd followup_rel_4lang/expA && sha256sum -c expA_inputs/EXPA_SHA256SUMS)
```

### 3-2. 환경과 데이터 (30~60분)

```bash
export XDG_CACHE_HOME="$PWD/.cache" HF_HOME="$PWD/.cache/huggingface"
export TORCH_HOME="$PWD/.cache/torch" PIP_CACHE_DIR="$PWD/.cache/pip"
export CUDA_VISIBLE_DEVICES=0 HF_HUB_DISABLE_XET=1
python3 -m venv .venv && source .venv/bin/activate
C=followup_rel_4lang/rstem_ropts_inputs/internvl35_constraints_20261109.txt
python -m pip install -r 01_code/requirements-qwen3-4090.txt -c "$C"
python -m pip install -e './01_code[models]' -c "$C"
python -c 'import torch,transformers,timm;print(torch.__version__,transformers.__version__,timm.__version__)'   # 2.9.1+cu130 4.57.6 1.0.31
source followup_rel_4lang/internvl35_4090_env.sh
python followup_rel_4lang/data_bundle.py unpack
python followup_rel_4lang/data_bundle.py fetch-images --workers 2
python followup_rel_4lang/data_bundle.py verify
hf download "$INTERNVL35_MODEL_ID" --revision "$INTERNVL35_REVISION"
```

### 3-3. 실행 (약 70분)

```bash
bash followup_rel_4lang/expA/run_expA.sh internvl35 all
```

smoke 기준은 Qwen3와 같지만 두 가지가 다르다. 배치마다 입력은 1개이고, 다시 돌린 O·R 답이 11월 9일 답과 97% 이상 같아야 한다. 진행 확인 경로는 `/workspace/mpr-ivl/followup_rel_4lang/results/expA_internvl35/`다.

## 4. 결과 받기와 정리

1. `expA_qwen3_YYYYMMDD.tar.gz`와 `expA_internvl35_YYYYMMDD.tar.gz` 두 파일을 받는다.
2. 로컬에서 열리는지 확인한다.
3. 인스턴스를 **Destroy**한다.

완료 확인 결과(`gate_complete.json`)에는 두 항목이 참고용으로 기록된다. 이 항목들 때문에 실행이 멈추지는 않는다.

- 이전 실행과의 패키지 버전 차이
- 다시 돌린 O·R의 일치율이 0.99 미만인지 여부

## 묶음을 다시 받은 경우

이미 푼 `followup_rel_4lang/expA` 폴더가 있으면 `rm -rf followup_rel_4lang/expA`로 지운 뒤 새 묶음을 푼다. 새 묶음은 파일 이름의 날짜가 바뀐다.
