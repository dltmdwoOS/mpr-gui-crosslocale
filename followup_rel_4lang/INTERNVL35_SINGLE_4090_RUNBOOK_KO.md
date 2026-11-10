# InternVL3.5 전체 실험: RTX 4090 한 장 실행 안내

작성: 2026-11-08. Qwen3 실행([안내](QWEN3_SINGLE_4090_RUNBOOK_KO.md))과 같은 입력·프롬프트·채점·순서로 InternVL3.5-8B를 돌린다. **이 문서와 코드는 로컬 점검만 거쳤고 GPU에서 실행하지 않았다(미검증).** 반드시 3단계 사전 점검과 4단계 smoke를 먼저 통과시킨다.

| 실험 | 규모 | Qwen3와 같은 점 |
| --- | ---: | --- |
| 6×6, 6개 차원 | 79,020응답 | 같은 manifest·seed 42·영어 고정 system·A–D 최대 2토큰·first-token label score |
| REL O/R/C/F | 23,424행, 고유 추론 18,432회 | 같은 bundle·프롬프트·채점 |
| Grounding main O/R/C/F | 7,584응답 | 같은 158문항·설명 파일·사용자 프롬프트·0–1000 점 채점 (입력 7,584개가 Qwen3 실행과 동일함을 로컬에서 확인) |

## Qwen3 실행과 다른 점 (논문 실행 계약에 적는다)

| 항목 | Qwen3 | InternVL3.5 | 이유 |
| --- | --- | --- | --- |
| 모델 | Qwen3-VL-8B `0c351dd` | InternVL3_5-8B `9bb6a56` | HF main(2025-08-29), 언어 모델 Qwen3ForCausalLM |
| 이미지 | max_pixels 2,097,152, 실제 1,620–2,010 시각 토큰(중앙값 1,998) | 448px 타일 max_num 8 + 썸네일: 세로 폰 화면 2,304, 가로 화면 1,792 시각 토큰(상한 2,304) | Qwen3의 실제 시각 토큰에 맞춘다(2026-11-08 결정) |
| 배치 | 4 | **1** | InternVL 어댑터는 배치 경로가 없다. 배치 4→3 검사 대신 3단계 점검을 쓴다 |
| attention | SDPA | eager | flash-attn 미설치 시 원격 코드가 eager로 고정한다(InternVL2.5 실행과 같음). 3단계에서 실제 값을 측정해 기록한다 |
| Grounding system 메시지 | 없음 | **빈 system 메시지** | InternVL 템플릿은 system 칸이 항상 있고, 비우지 않으면 중국어 기본 문구가 모든 조건에 붙는다 |
| thinking | 없음 | 꺼짐 | R1 system 프롬프트를 넣을 때만 켜진다. 6×6·REL은 영어 고정 system을 명시한다 |

로컬에서 확인한 것: InternVL3.5 토크나이저에서 A/B/C/D가 각각 토큰 하나(32–35)다. 영어 고정 system 문구가 렌더링된 프롬프트 맨 앞에 들어간다. 빈 system은 `<|im_start|>system\n<|im_end|>`로 렌더링된다. 기존 테스트 80개가 통과한다(로컬 데이터가 없어 실패하는 5개는 변경 전과 같다).

## 타일 상한: max_num 8 (2026-11-08 결정)

`max_pixels`와 타일 상한은 "상한"만 같고 실제 시각 토큰은 다르다. 위치 지정 GT 이미지 680장으로 계산한 InternVL 시각 토큰은 다음과 같다(Qwen3 실제값 중앙값 1,998).

| max_num | 세로 폰 화면 508장 | 가로 화면 172장 |
| --- | ---: | ---: |
| 7 (여름 InternVL2.5와 같음) | 768 | 1,792 |
| 8 | 2,304 | 1,792 |
| 12 (모델 카드 기본) | 2,304 또는 2,816 | 1,792 |

Qwen3와 실제 시각 정보량을 맞추기 위해 8을 쓴다(`vision_token_limit` 2,304). 실행 계약에 config 해시가 들어가므로 실행 중에 바꾸지 않는다. 시각 토큰이 늘어 응답당 시간이 max_num 7보다 길어질 수 있다(미검증, 3단계에서 측정). 여름 InternVL2.5 결과도 max_num 7이었으므로 세로 화면은 768토큰으로 돌았다는 점을 논문에 적는다.

## 1. 인스턴스와 환경

Qwen3를 돌린 인스턴스를 그대로 쓰면 1단계를 건너뛴다. 같은 venv(torch 2.9.1+cu130, transformers 4.57.6, timm, einops)에서 돈다. 새 인스턴스라면 [Qwen3 안내 1단계](QWEN3_SINGLE_4090_RUNBOOK_KO.md#1-인스턴스와-환경)와 같다: RTX 4090 1장, RAM 48GB 이상, 디스크 80GB 이상, `tmux` 안에서 진행.

이 브랜치의 변경 파일을 저장소에 반영한 뒤:

```bash
cd /workspace/mpr-gui-crosslocale
source .venv/bin/activate
export XDG_CACHE_HOME="$PWD/.cache" HF_HOME="$PWD/.cache/huggingface" CUDA_VISIBLE_DEVICES=0
python -m pip install -e './01_code[models]'   # 코드가 바뀌었으므로 다시 설치
source followup_rel_4lang/internvl35_4090_env.sh
python -c 'import torch,transformers,timm,einops;print(torch.__version__,transformers.__version__);print(torch.cuda.get_device_name(0))'
```

## 2. 체크포인트 준비

새 셸마다 `source .venv/bin/activate`와 `source followup_rel_4lang/internvl35_4090_env.sh`를 다시 실행한다. env 스크립트가 HF 캐시를 저장소 안 `.cache/huggingface`로 고정해 다운로드와 실행이 같은 캐시를 쓴다. 데이터·이미지는 Qwen3 실행 때 받은 것을 그대로 쓴다(`data_bundle.py verify`만 다시 실행). 모델은 약 17GB다.

```bash
python followup_rel_4lang/data_bundle.py verify
hf download "$INTERNVL35_MODEL_ID" --revision "$INTERNVL35_REVISION"
df -h .   # 남은 디스크 확인. Qwen3 캐시(약 17GB)와 함께 들어가야 한다
```

## 한 번에 돌리기 (권장: 돌려 두고 나중에 확인)

1–2단계(환경·체크포인트) 뒤에는 아래 한 줄로 사전 점검 → 예상 시간 계산 → smoke → 자동 판정 → 6×6 → REL → 위치 지정 → 완료 확인 → 결과 압축까지 사람 없이 진행한다. 각 판정에서 실패하면 그 자리에서 멈추고 `STATUS`에 이유를 남긴다. SSH가 끊겨도 돌도록 반드시 `tmux` 안에서 실행한다.

```bash
tmux new -s ivl35
bash followup_rel_4lang/run_full_internvl35.sh all
# Ctrl-b d 로 빠져나와도 계속 돈다. 다시 붙기: tmux attach -t ivl35
```

나중에 확인할 것:

```bash
cat followup_rel_4lang/results/internvl35_single4090/STATUS     # 단계별 시각, 예상 시간, 실패 위치
cat followup_rel_4lang/results/internvl35_single4090/gate_eta.json
tail -3 followup_rel_4lang/results/internvl35_single4090/logs/*.log
```

`STATUS` 마지막 줄이 `ALL DONE`이면 `followup_rel_4lang/results/internvl35_single4090_YYYYMMDD.tar.gz` 하나만 내려받으면 된다. `FAILED at stage ...`이면 로그를 확인하고, 원인을 고친 뒤 같은 명령을 다시 실행하면 끝난 부분은 건너뛰고 이어서 한다(단, 사전 점검이 실패했다면 `preflight.json`을 다른 이름으로 옮긴 뒤 재실행).

자동 판정 기준(`check_internvl_gates.py`): smoke 6×6 216개 고유 성공·파싱 실패 2개 이하, REL smoke 128행 전부 성공·파싱 실패 2개 이하, 위치 지정 파일럿 192응답·조건별 유효 출력 85% 이상·64토큰 길이 종료 10건 이하. Qwen3 파일럿은 조건별 유효 출력 98–100%였다. 기준에 걸리면 본 실행을 시작하지 않는다.

인스턴스는 끝나도 자동으로 끄지 않는다. Vast에서 인스턴스를 멈추면 같은 GPU가 다른 사람에게 대여된 동안 다시 켤 수 없어 결과를 꺼내지 못할 수 있기 때문이다. 대신 끝난 뒤 켜져 있는 시간만큼 비용이 나가므로 `STATUS`를 하루 한두 번 확인하고, 압축 파일을 내려받은 직후 인스턴스를 삭제한다.

아래 3–5단계는 같은 과정을 손으로 나눠 실행할 때의 설명이다.

## 3. 사전 점검 (필수, 약 5–10분)

각 차원의 가장 긴 질문 6개와 가장 긴 grounding 시도 1개를 배치 1로 실제 생성한다. 출력이 A–D 한 글자가 아니거나, 영어 system이 빠졌거나, 시각 토큰이 상한을 넘으면 실패로 멈춘다. 시간·최대 메모리를 기록한다.

```bash
mkdir -p "$OUT/logs"
python followup_rel_4lang/check_internvl_preflight.py \
  --manifest 01_code/data/manifests/mpr_gui_manifest.jsonl \
  --model-config "$MODEL_CONFIG" --output "$OUT/preflight.json" \
  2>&1 | tee "$OUT/preflight.log"
```

실패하면 원인을 고친 뒤 기존 `preflight.json`·`preflight.log`를 다른 이름으로 옮기고 다시 실행한다(덮어쓰기를 거부한다). `measured_runtime`에서 언어 모델 attention이 `eager`인지 확인한다. `preflight.json`의 `measurements`에서 `seconds`로 전체 시간을 다시 어림한다. grounding의 `raw_output`이 `(x, y)` 형식인지 본다. 상자(`[[x1,y1,x2,y2]]`) 형식이면 채점에서 형식 실패가 되므로 본 실행 전에 상의한다.

## 4. smoke (약 30분 안쪽, 추정)

```bash
bash followup_rel_4lang/run_full_internvl35.sh smoke   # 사전 점검이 없으면 먼저 실행한다
```

6×6 216응답, REL 고유 80회/128행, grounding 파일럿 192응답이다. 실행 실패·파싱 실패·좌표 형식 실패 수를 확인한다. grounding `pilot_orcf/summary.json`의 `complete=true`, 조건별 48응답을 확인한다.

본 실행으로 넘어가기 전 기준: grounding 파일럿의 조건별 `valid` 비율과 `stop_reason=="length"` 건수를 Qwen3 파일럿(`followup_rel_4lang/artifacts/qwen3_single4090_20261107/smoke_validation.json`: O 48/48, R 47/48, C 47/48, F 48/48 유효)과 나란히 적는다. 유효 비율이 크게 낮거나 length 종료가 여러 건이면(예: 상자 `[[...]]` 출력, 설명 문장 덧붙임) 본 실행 전에 상의한다. 6×6·REL smoke의 파싱 실패가 있으면 원문을 확인한다.

## 5. 전체 실행

```bash
bash followup_rel_4lang/run_full_internvl35.sh full    # 끝나면 완료 확인과 압축까지 한다
```

세 실험을 차례로 실행한다. 중단되면 같은 명령을 다시 실행하면 이어서 한다(6×6·REL은 `--resume`, grounding은 계약 확인 후 자동 재개). 설정·설명 파일을 바꿀 때는 `OUT`을 새 폴더로 바꾼다.

예상 시간(미검증): 비교 기준은 Qwen3 실측이다. 같은 4090에서 배치 4로 6×6 79,020응답에 13.1시간(응답당 약 0.6초), REL에 3.1시간이 걸렸다. InternVL3.5는 배치 1·eager·시각 토큰 최대 2,304라 응답당 약 0.8–1.3초로 본다. 그러면 6×6 18–29시간, REL 4–7시간, 위치 지정(최대 64토큰) 2–4시간, 합계 약 24–40시간에 설치·다운로드·사전 점검·smoke 약 1–2시간이 더해진다. `all` 실행은 사전 점검 직후 `gate_eta.json`에 실측 기반 예상 시간을 남긴다.

## 6. 완료 확인과 보존

Qwen3 안내 7단계와 같다. 6×6 성공 고유 입력 79,020개, REL `condition_rows=23424`·`actual_successful_inferences=18432`, grounding `complete=true`·`response_count=7584`를 확인한다. 인스턴스를 끄기 전에 `$OUT` 전체, `git rev-parse HEAD`, `python -m pip freeze`를 내려받는다.

## 위험과 대처

| 위험 | 크기 | 대처 |
| --- | --- | --- |
| 비용 | 4090 1장 약 1–1.5일 | 지원 후에는 직접 비용. 끝나면 인스턴스를 바로 끈다 |
| 디스크 부족 | 모델 17GB + 결과 수 GB | 2단계 `df -h`. 부족하면 Qwen3 캐시를 지우기 전에 Qwen3 결과를 먼저 내려받는다 |
| 메모리 부족 | 8.5B bf16 약 17GB + eager attention | 3단계에서 최대 길이 입력으로 확인. 본 실행 중 OOM은 멈추고 기록한다 |
| 인스턴스 중단 | 진행분은 한 줄씩 저장 | 같은 명령으로 재개. grounding은 반쯤 쓰인 마지막 줄을 자동으로 지우고 이어 한다 |
| 원격 코드 변경 | revision 고정 | `INTERNVL35_REVISION`을 바꾸지 않는다 |

InternVL2.5-8B를 같은 방식으로 다시 돌리려면 `MODEL_CONFIG=01_code/configs/models/internvl2_5_8b.yaml OUT=followup_rel_4lang/results/internvl25_single4090`로 바꿔 2–5단계를 반복한다(revision `e9e4c0d`, InternLM2.5 언어 모델).
