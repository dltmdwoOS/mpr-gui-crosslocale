# InternVL3.5 R_stem / R_opts 실행 안내 (RTX 4090 한 장)

2026-11-10 통합 메모: 이 저장소에는 아래 실행 코드와 지원 패치가 이미 적용돼 있다.
1–2절은 과거 기준 커밋에서 서버 코드를 복원하는 절차이며, 현재 통합본에
`git am`을 다시 실행하지 않는다. 패치는 `artifacts/rstem_ropts_20261110/`에
보존했다. 중복 tar.gz는 같은 폴더의 `code/`에 로컬로만 보관하며 Git에서는 제외한다.
아래 과거 복원 절차의 tar.gz는 별도 전달본을 사용한다. 완료 결과와 분석은
[결과 요약](results/rstem_ropts_20261110/README_KO.md)에 있다.

작성: 2026-11-10. 로컬에서 가짜 모델(`--mock-model`)과 `--dry-run`으로만 검사했다. GPU 실행은 하지 않았다(미검증).

## 무엇을 돌리나

Qwen3 실험과 같은 158문항 × 불일치 언어쌍 12개 = 1,896쌍에 O, R_stem, R_opts, R 네 조건을 InternVL3.5-8B로 돌린다. 추론은 7,584회다. 입력 파일(`mixed_conditions.jsonl`, `input_lock.json`)은 Qwen3 묶음과 바이트까지 같다.

InternVL은 2026-11-09 실행과 같이 **배치 1**로 돈다. 저장소 코드는 배치 2 이상을 InternVL에 허용하지 않는다. 배치 1이라 한 추론이 옆 입력의 영향을 받지 않는다. O·R은 이번 실행에서 다시 돌려 주 분석에 쓰고, 2026-11-09 답은 재현성 확인에만 쓴다.

코드는 2026-11-09 InternVL 실행과 같아야 한다. 그 실행 코드는 GitHub 커밋 `666440…`에 패치 0001~0005를 얹은 것이다. 로컬에서 같은 방법으로 만든 코드의 해시 12개가 2026-11-09 실행 기록과 모두 같았고, 설정 파일 해시(`7fed517c…`)도 같았다. 서버 사전 점검이 이 둘과 torch·transformers·timm 버전을 다시 비교하고, 다르면 멈춘다.

## 예상 시간과 비용

- 추론: 2026-11-09 InternVL REL 18,432회가 3시간 44분(평균 0.73초/회) 걸렸다. 7,584회면 약 90~100분이다.
- 준비: 패키지 설치, 모델 약 17GB, REL 이미지 다운로드에 30~60분.
- 새 인스턴스면 합계 약 2.5~3시간이다. Qwen3를 돌린 인스턴스에서 이어서 돌리면 약 2시간이 더 든다. 요금은 인스턴스마다 달라 확인 필요다.

## 위험과 대처

| 위험 | 크기 | 대처 |
| --- | --- | --- |
| 인스턴스를 끄지 않아 요금이 계속 나감 | 시간당 요금 그대로 | 결과를 받은 뒤 **Destroy**까지 누른다 |
| Qwen3 실행 중에 같은 GPU로 시작 | 두 모델이 24GB에 안 들어가 둘 다 멈출 수 있음 | Qwen3 `STATUS`에 `ALL DONE`이 뜬 뒤에 시작한다 |
| 11월 7일 커밋을 원격에서 못 찾음 | 실행 불가 | `git checkout`이 실패하면 진행하지 말고 알려준다 |
| 패치가 안 붙음 (`git am` 실패) | 실행 불가 | `git am --abort` 후 멈추고 알려준다 |
| 서버 코드나 버전이 11월 9일과 다름 | 결과 비교 불가 | 사전 점검이 멈춘다. 그대로 두고 알려준다 |
| 디스크 부족 | 다운로드 실패 | 새 인스턴스는 80GB 이상. Qwen3 인스턴스에서 이어 돌리면 `df -h /workspace`로 40GB 이상 남았는지 본다 |
| SSH 끊김 | 중단 | `tmux` 안에서 실행. 같은 명령을 다시 치면 이어서 돈다 |

## 1. 코드 받기

새 인스턴스라면 RTX 4090 1장, RAM 48GB 이상, 디스크 80GB 이상, **On-demand**로 빌린다. Interruptible은 다른 호스트로 옮겨질 수 있고, 그러면 실행 기록의 플랫폼 문자열이 바뀌어 이어서 돌리기(`--resume`)가 거부된다.

Qwen3 저장소와 섞이지 않도록 **다른 폴더**에 받는다. `tmux new -s ivl` 안에서 진행한다. `git checkout`이 실패하면 진행하지 말고 알려준다.

```bash
cd /workspace
git clone --branch followup-rel-4lang-inference https://github.com/dltmdwoOS/mpr-gui-crosslocale.git mpr-ivl
cd mpr-ivl
git checkout 666440011f538cd9336794c9965429de640843c3
```

## 2. 추가 파일 올리고 패치 적용

로컬의 `rstem_ropts_internvl_addon_20261110.tar.gz`를 `/workspace/mpr-ivl/`에 올린다(VS Code 탐색기에 끌어다 놓기 또는 `scp`).

```bash
tar -tzf rstem_ropts_internvl_addon_20261110.tar.gz   # 들어갈 파일 목록 확인
tar -xzf rstem_ropts_internvl_addon_20261110.tar.gz --skip-old-files
sha256sum -c followup_rel_4lang/rstem_ropts_inputs/ADDON_INTERNVL_SHA256SUMS
git -c user.name=local -c user.email=local@local am rstem_internvl_patches/000*.patch
git log --oneline -6    # 맨 아래가 666440, 위로 패치 5개
```

## 3. 환경과 데이터

```bash
export XDG_CACHE_HOME="$PWD/.cache" HF_HOME="$PWD/.cache/huggingface"
export TORCH_HOME="$PWD/.cache/torch" PIP_CACHE_DIR="$PWD/.cache/pip"
export CUDA_VISIBLE_DEVICES=0 HF_HUB_DISABLE_XET=1
python3 --version    # 3.12.x가 아니면 멈추고 알려준다
python3 -m venv .venv && source .venv/bin/activate   # venv 모듈이 없다는 오류면: apt-get update && apt-get install -y python3.12-venv
C=followup_rel_4lang/rstem_ropts_inputs/internvl35_constraints_20261109.txt   # 11월 9일 InternVL 서버의 pip freeze
python -m pip install -r 01_code/requirements-qwen3-4090.txt -c "$C"
python -m pip install -e './01_code[models]' -c "$C"
python -c 'import torch,transformers,timm;print(torch.__version__,transformers.__version__,timm.__version__)'   # 2.9.1+cu130 4.57.6 1.0.31
source followup_rel_4lang/internvl35_4090_env.sh
python followup_rel_4lang/data_bundle.py unpack
python followup_rel_4lang/data_bundle.py fetch-images --workers 2
python followup_rel_4lang/data_bundle.py verify
hf download "$INTERNVL35_MODEL_ID" --revision "$INTERNVL35_REVISION"
```

## 4. 실행

```bash
bash followup_rel_4lang/run_rstem_ropts_internvl.sh all
```

사전 점검 → 3문항 smoke(144회) → 확인 → 본 실행(7,584회) → 완료 확인 → 결과 묶기를 차례로 한다. smoke 확인 기준은 144행 모두 성공, 배치마다 입력 1개, 답 파싱 실패 2개 이하, 다시 돌린 O·R 답이 11월 9일 답과 97% 이상 같음(배치 1·같은 코드라 거의 100%를 기대한다)이다. 하나라도 어긋나면 멈춘다. 진행 확인은 다른 창에서 한다.

```bash
cat /workspace/mpr-ivl/followup_rel_4lang/results/internvl35_rstem_ropts/STATUS
tail -n 3 /workspace/mpr-ivl/followup_rel_4lang/results/internvl35_rstem_ropts/logs/full.log
```

## 5. 결과 받기와 정리

`STATUS`에 `ALL DONE`이 뜨면 `followup_rel_4lang/results/internvl35_rstem_ropts_YYYYMMDD.tar.gz`를 내려받고, 열리는지 확인한 뒤 인스턴스를 **Destroy**한다.
