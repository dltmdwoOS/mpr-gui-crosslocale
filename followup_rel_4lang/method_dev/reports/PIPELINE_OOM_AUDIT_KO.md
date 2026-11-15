# 순차 파이프라인과 단계별 OOM 검토

2026-11-15. 현재 대상은 B200 MIG 2g.45gb 하나다. 할당 GPU의 실제 용량은44.25GiB, 점검 당시 free44.05GiB였다. Cgroup RAM45GiB·CPU3core를 기준으로 했다. 타 사용자의 프로세스나 파일은 조회하지 않았다.

**판단:** 아래 제한을 지키면 현재45GB MIG에서 각 후보를 실행할 합리적인 여유가 있다. 단, 가중치+KV 계산만으로 allocator·cuDNN/SDPA workspace의 상한까지 증명할 수 없으므로 **OOM이 절대로 없다는 보장은 하지 않는다.** 24GB RTX4090용 검증 프로필이 아니다. 그 장비에서는 아래 명령이 여유 메모리 검사에서 중단된다.

## 실제 파일에서 계산한 크기

모델 가중치는 safetensors header의 data offsets를 합산했다. GPU에 모델을 올리지 않았다.

| 모델 | BF16 가중치 | Decoder layers | KV heads | Head dim |
| --- | ---: | ---: | ---: | ---: |
| Qwen3-8B | 15.256GiB | 36 | 8 | 128 |
| Qwen3-VL-8B | 16.330GiB | 36 | 8 | 128 |

BF16 KV cache는 token당 `2(K/V) × 36 × 8 × 128 × 2bytes = 147,456bytes`, 즉144KiB다.

- Method: batch1, 전체 입력4096token + 생성768token 상한 → KV 약0.668GiB.
- Downstream: batch3, 전체 입력4096token + 생성2token 상한 → KV 약1.688GiB.
- 입력 상한4096은 image token을 포함한다. 길이를 넘으면 자르거나 pair를 삭제하지 않고 중단·기록한다.
- 이미지2,097,152pixels 상한, patch16×16, merge2×2 → 최대8192 pre-merge patch / 2048 merged image token이다. Method의 실제 image grid도 검사한다.

이 값은 peak VRAM이 아니다. Weight 외 vision encoder, MLP activation, attention workspace, CUDA context, allocator reserve가 추가된다.

## 각 테스트의 위험

| 테스트 | GPU에 남는 모델 | Batch / 생성 상한 | 주요 추가 메모리 | 상대적 위험 |
| --- | --- | --- | --- | --- |
| cpu_quoted | 없음 | CPU | 작음 | GPU OOM 없음 |
| fixed_original/minimal/contrastive | Qwen3-8B 하나 | 1 / 768 | KV≤0.668GiB, text prefill | 낮음 |
| vl_original/minimal/contrastive | Qwen3-VL 하나, vision 호출 없음 | 1 / 768 | KV≤0.668GiB; vision weights는 포함 | 낮음 |
| Inventory | Qwen3-VL 하나 | 1 / 768 | Vision prefill·Conv3D/SDPA workspace | 중간 |
| TXT_SEL | Qwen3-8B 하나 | 1 / 768 | 작은 참조 JSON | 낮음 |
| GUI_EXACT | Inventory 때 VL, 추출/번역 때 LM; 순차 교체 | 1 / 768 | Inventory 순간이 최고 위험 | 중간 |
| GUI_MATCH_LM | Inventory VL → text LM, 순차 | 1 / 768 | Inventory 순간과 inventory 포함 text | 중간 |
| GUI_TARGETED_VLM | 추출 LM → 화면 확인 VL, 순차 | 1 / 768 | Vision prefill | 중간 |
| GUI_DIRECT_VLM | Qwen3-VL 하나 | 1 / 768 | Vision + MCQ prefill, 긴 edit 출력 | 중간 |
| TXT_DIRECT_LM | Qwen3-8B 하나 | 1 / 768 | Text prefill·KV | 낮음 |
| TXT_DIRECT_VLM | Qwen3-VL 하나, 이미지 없음 | 1 / 768 | Vision weights만 상주 | 낮음 |
| TXT_FULL / GUI_FULL | Qwen3-8B; GUI_FULL inventory는 VL에서 선행 | 1 / 768 | GUI_FULL은 inventory 순간 | 낮음 / 중간 |
| 모든 후보의 최종 문제 풀이 | Qwen3-VL 하나 | 3 / 2 | 세 이미지와 padding된 prefill | 상대적으로 가장 높음 |
| Bootstrap·품질 집계 | GPU 모델 없음 | CPU3thread 이하 | 10,000×118 int index 약9MiB | GPU OOM 없음 |

긴768token 출력이 입력·출력 모두768배 메모리를 요구하는 것은 아니다. 생성은 autoregressive하며 KV가 token 수에 따라 증가한다. 반면 image attention은 merge 전 patch 수가 중요하다.

SDPA의 memory-efficient 경로가 아니라 math 경로로 실행되는 보수적 경우도 고려했다. 8192patch·16head의 FP32 attention score 한 버퍼는 약4GiB다. Vision SDPA 코드는 이미지별 chunk를 처리하므로 batch3을24576patch짜리 한 이미지로 합쳐 제곱하지 않는다. Decoder batch3·4096token·32head의 FP32 score 한 버퍼는 약6GiB다. Softmax/복사 때문에 여러 버퍼가 존재할 수 있으므로 이 값을 단순한 peak 상한으로 사용하지 않는다. 이 점 때문에 free40GiB를 요구한다.

현재 설치된 Transformers4.57.6의 generate는 지원 모델에서 `logits_to_keep=1`을 기본 적용한다. Method backend에도 이를 명시했다. 따라서 prefill 전체 `sequence × vocab` logits를 보관하는 비용을 예상치에 추가하지 않는다. Downstream의2token label scoring logits도 작다. 이 설정은 기존 installed generate의 기본 동작과 같다.

## 코드로 적용한 제한

1. Pipeline parent에는 모델 weights를 올리지 않는다. GPU 자식은 한 번에 하나다.
2. 각 trial·downstream은 별도 subprocess다. 종료하면 해당 모델·CUDA allocator가 해제된다.
3. 한 trial 안에서 VL/LM을 바꿀 때 이전 모델을 먼저 삭제하고 GC/empty_cache한다. 두8B 모델을 동시에 적재하지 않는다.
4. 시작 전과 **각 GPU child 시작 전 free40GiB**를 검사한다. 다른 작업 때문에 줄었으면 중단한다. 다른 프로세스를 죽이지 않는다.
5. Method batch1, downstream 기존 batch3, BF16·SDPA·2MP·channels_last_3d를 유지한다. OOM 뒤 자동으로 batch·이미지 크기를 줄이지 않는다.
6. CPU 전처리 후 GPU 복사 전4096token 상한을 검사한다. Method image grid도 검사한다.
7. 호출·downstream batch별 peak allocated/reserved bytes를 기록한다. 이는 reset 시점에 이미 올라간 모델을 포함한 generation 구간 peak이며 cold model-load peak 전체를 측정한 값은 아니다.
8. OOM/모델 적재 오류는 failure로 기록하고 pipeline을 중단한다. 계속 실패하면서 전체 pair를 원문 fallback으로 채우지 않는다. 잘못된 JSON 등 출력 문제는 기존 원문 fallback으로 포함한다.
9. 완료 marker 없는 attempt는 보존한다. 같은 명령을 다시 실행하면 완료 job을 재사용하고 미완료 job만 새 attempt에서 실행하며 성공 call cache를 재사용한다.

## 한 줄 실행의 범위와 선택 규칙

[run_search_pipeline.sh](../scripts/run_search_pipeline.sh)가 환경변수·개인 cache·thread3·offline 모델 경로를 맞춘다. 모델 다운로드·유료 인스턴스 생성은 하지 않는다.

순서는 다음과 같다.

1. 고정 cohort/hash·가중치·이미지·OOM preflight.
2. Probe 추출7조건 → F1 최고와 근접 저비용 후보 최대2개 승격.
3. Screen 추출2조건 → F1 최고에서0.02 이내인 후보 중 method 시간이 낮은 extractor 고정.
4. Probe 구조9조건과 문제 풀이.
5. Screen 구조9조건과 문제 풀이. 기존 설계의 수동 최대3개 승격 대신 **9개를 모두 screen**하여 수동 중단점과 작은 probe의 우연한 탈락을 없앤다. 그만큼 총 실행 비용은 더 크다.
6. Screen main240쌍으로 GUI 구조4개 중 accuracy 최고·근접 저비용 구조 최대2개를 shortlist하고, selection을 읽기 전에 파일로 동결.
7. Selection239쌍에서 shortlist2개와 대조4개 실행. 최고 정확도에서1%p 이내면 standalone method runtime/쌍이 낮은 방법을 잠정 선택.
8. 선택과 평가 recipe를 동결한 뒤 internal evaluation118문항·1,416쌍에서 winner와 대조4개 실행. 내부 평가 점수로 winner를 다시 고르지 않는다.
9. Item단위10,000회 bootstrap CI·primary3대비 Holm 보정·회복/회귀·언어별 결과·비용 보고서 생성.

Score를 보고 threshold나 prompt를 자동 수정하는 무제한 탐색은 아니다. 고정 registry만 실행한다. 독립 화면 검수 전 matching precision은 null이고 자동 선택은 잠정 선택이다. Pivot routing·추가 VLM은 범위 밖이다. 원래 전체158문항은 역사적으로 관찰한 개발 데이터이므로 confirmatory claim으로 쓰지 않는다.

출력은 `followup_rel_4lang/method_dev/artifacts/search_pipeline_v1/`이며 `REPORT_KO.md`, `analysis.json`, `oom_audit.json`, `frozen_policy.json`, `jobs/`, `logs/`를 남긴다. 동일 명령으로 재개할 수 있다. 코드·정책·데이터가 바뀌면 기존 결과를 섞지 않고 새 output-dir을 요구한다.

## 검증

관련 CPU 테스트32개와 기존 Qwen batch 회귀 테스트가 통과했다. GPU 메타데이터만 사용한 실제 preflight도 free40GiB 기준을 통과했다. [준비 상태·메모리 계산 기록](../artifacts/pipeline_readiness.json). 작은 mock cohort에서 전 단계(내부 평가·보고서 포함)를 실행했고 동일 명령 재개가 완료 job을 반복하지 않는 것을 확인했다. 실제 GPU 실험은 이번 준비 과정에서 시작하지 않았다. 이론 검토와 CPU 검증을 GPU peak 실측으로 표현하지 않는다.
