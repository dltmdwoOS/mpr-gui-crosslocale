# Qwen3-VL-4B: 수정 추출 E1 + 기존 정렬 M0 전이 평가

8B에서 선택한 방법을 수정 없이 4B에 적용한다. 4B 결과를 보고 prompt나 언어별 정책을 조정하지 않는다. 다른 모델·문항 영역 확장은 이번 결과를 확인한 뒤 결정한다.

## 무엇을 유지하고 바꾸는가

| 단계 | 담당 모델 | 처리 |
| --- | --- | --- |
| 화면 문자열 inventory | **Qwen3-VL-4B-Instruct** | Screenshot만 보고 추출. 중복 제거·정렬. 기존 two-stage inventory/repair prompt 유지 |
| Stem 참조 이름 추출 | **고정 Qwen3-8B** | 수정 E1 prompt. 동일 LM·prompt의 완료 raw trace를 재검증하여 재사용 |
| Inventory에서 교체 표현 선택 | **고정 Qwen3-8B** | 기존 M0 prompt. 원본 MCQ·추출 이름·**4B가 만든 inventory** 제공 |
| Stem 치환 | 코드 | 검증된 span만 교체. 나머지 문맥과 A–D options 원문 유지 |
| 최종 문제 풀이 | **Qwen3-VL-4B-Instruct** | 원본 O와 E1/M0를 같은 문항·설정으로 각각 평가 |

8B inventory와 8B 최종 예측은 4B 결과로 재사용하지 않는다. 고정 LM의 추출은 평가 모델과 무관한 source-only 작업이라 재사용한다. 이 평가는 **방법을 4B로 옮기는 실험**이며 참조 추출기를 4B backbone으로 바꾸는 실험은 아니다.

## 고정 계약

- VLM: `Qwen/Qwen3-VL-4B-Instruct`, revision `ebb281ec70b05090aa6165b016eac8ec08e71b17`.
- LM: `Qwen/Qwen3-8B`, revision `47719a242beab8f9aecc40ce3928b034dd5dd559`.
- BF16, **SDPA**, seed 42, fast processor, `min_pixels=262144`, `max_pixels=2097152`, `channels_last_3d` patch embedding.
- Inventory·정렬 batch 1. 최종 풀이 batch 3, greedy, 최대 2 output tokens, label scoring 유지.
- Inventory 최대 768 tokens, 구조 복구 최대 3072. M0 최대 512 tokens, 구조 복구 최대 512. 구조 복구 각 1회; 실패하면 원문 fallback.
- 입력 한도 4096 tokens. 초과 시 중단하며 조용히 자르거나 해상도·batch를 변경하지 않는다.
- 한 번에 한 모델만 GPU에 적재. 현재 B200 MIG에서 적재 전 40GiB free 검사. 기존 8B batch 3보다 가중치 부담은 작지만 실제 OOM 여부는 실행 검증으로 확인해야 한다.
- 조건별로 분리한 `pair_id` 정렬 batch. O와 method에 같은 pair 그룹 적용. 동일한 **전체 batch**의 prompt·이미지·모델·설정·환경이 일치할 때만 예측 재사용.

프롬프트 원문은 [`STEM_REFINEMENT_2X2_PROTOCOL_KO.md`](STEM_REFINEMENT_2X2_PROTOCOL_KO.md)의 E1/M0 및 기존 inventory/최종 풀이와 같다. `contract.json`에 실제 model spec·해석된 설정·prompt SHA·의존 코드 SHA를 보존한다. 실제 `system_prompt`, `user_prompt`, raw response는 inventory와 rewrite JSONL의 `attempts`에 저장한다. 최종 문제 풀이의 rendered prompt와 raw output은 predictions에 저장한다.

## 범위와 비교

| 범위 | 주 분석 문항 | 실행 pair/조건 | 주 분석 pair/조건 | 새 inventory 이미지 |
| --- | ---: | ---: | ---: | ---: |
| Screen | 20 | 288 | 240 | 128 |
| Selection | 20 | 240 | 239 | 80 |
| Internal | 118 | 1416 | 1416 | 472 |
| 전체 | 158 | 1944 | **1895** | **680** |

Screen은 기존 batch 구성을 유지하기 위한 pilot 48쌍을 함께 실행하되 주 분석에서 제외한다. Selection의 사전 제외 1쌍도 실행 후 주 분석에서 제외한다. Main만의 실제 화면 수는 632개다. O와 method를 모두 실행하므로 전체 최종 예측은 3888행이다.

주 비교는 **이번 장비·설정으로 실행한 4B method − 4B O**다. Semantic item 단위 bootstrap 10,000회로 95% CI 및 회복/회귀를 계산한다. GUI 언어별 결과, inventory 실패, 정렬 fallback, 실제 추가 시간을 함께 기록한다. 이미 관찰한 개발 문항이므로 독립적인 confirmatory 평가로 해석하지 않는다.

과거 4B O/T/R/F 패키지는 같은 revision·prompt지만 RTX 4090 batch 1이었다. 새로운 paired O를 대체하지 않는다. R 전체와 stem-only method는 조작 범위도 다르다. 8B 전체 결과 74.09%는 다른 평가 모델의 개발 결과이지 4B 목표치나 예측치가 아니다.

## 실행

Repository root에서 실행한다. 기존 `.venv`를 사용하며 새 환경·패키지를 설치하지 않는다. 체크포인트는 개인 cache에 한 번만 다운로드한다.

```bash
.venv/bin/python followup_rel_4lang/method_dev/scripts/download_transfer_model.py --download
```

준비만 수행하며 GPU를 사용하지 않는 명령:

```bash
bash followup_rel_4lang/method_dev/scripts/run_model_transfer.sh
```

Screen 결과부터 확인:

```bash
nohup bash followup_rel_4lang/method_dev/scripts/run_model_transfer.sh --run > followup_rel_4lang/method_dev/artifacts/transfer_qwen3_vl_4b_screen.log 2>&1 < /dev/null &
```

158문항 전체를 고정 설정으로 수행:

```bash
nohup bash followup_rel_4lang/method_dev/scripts/run_model_transfer.sh --cohorts screen selection internal_evaluation --output-dir followup_rel_4lang/method_dev/artifacts/transfer_qwen3_vl_4b_e1m0_all_v1 --run > followup_rel_4lang/method_dev/artifacts/transfer_qwen3_vl_4b_all.log 2>&1 < /dev/null &
```

같은 output-dir·cohorts로 재실행하면 완료 stage와 동일 cache를 재사용한다. Screen 전용 실행과 전체 실행은 별도 고정 계약이다. 둘을 연이어 실행하면 새 디렉터리에서 Screen을 재실행하므로 **처음에 범위를 선택하고 해당 명령 하나를 사용한다**. Screen 완료 후 확대할 경우에는 `--cohorts selection internal_evaluation`과 별도 output-dir를 지정해 나머지만 수행하면 된다. 전체 합산 보고서는 그 두 실행의 계약을 대조한 뒤 작성한다.

결과는 해당 output-dir의 `REPORT_KO.md`, `results.json` 및 각 cohort의 `inventory/`, `rewrite/`, `infer_O/`, `infer_E1_M0/`에 저장한다. 중단 시 같은 명령으로 재개한다. 기존 artifact는 수정하지 않는다. 현재 실행 시간은 미측정이며, 8B의 inventory 재사용 실행 시간을 4B 전체 ETA로 사용하지 않는다.
