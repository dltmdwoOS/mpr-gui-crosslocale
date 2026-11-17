# OCR inventory 최종 개발 결과: Qwen3-VL-8B·4B

두 모델 모두 Screen·Selection·Internal 실행을 완료했다. 새 inference 없이 완료 원시 예측과 frozen run contract를 재검증했다.

원본 screenshot → CPU EasyOCR → 고정 Qwen3-8B LM의 E1 referent 추출·M0 이름 선택 → stem만 코드로 치환 → VLM label-only 풀이 순서다. E1 추출은 기존 결과를 재사용했고, 4B는8B와 동일한 OCR·LM 완성 MCQ를 공유한다. Options·이미지·정답·A–D 순서를 유지한다. 최종 VLM은 BF16·SDPA·2MP·batch3·greedy2tokens·seed42이며 checkpoint만4B/8B로 바뀐다.

## OCR 전체 집합 완료: 성능과 효율

**Screen에서 보였던 OCR의 작은 정확도 우위는 전체 집합에서 유지되지 않았다.** 전체에서는8B·4B 모두 VLM inventory보다 정답이5개 적었고, 차이의95% item bootstrap CI는0을 포함한다. 동등성·비열등성을 검증한 결과는 아니다.

분모는158개 main semantic item·1,895pair다. Pilot48pair와 사전 제외1pair는 실행에 남기고 분석·비용에서 제외했다. 실패·fallback·미파싱을 삭제하지 않았다. 이미 반복 관찰한 development cohort의 탐색 결과이며 전체366문항 평가나 독립 일반화 검증이 아니다.

| 모델 | O | VLM inventory | OCR inventory | OCR−O | OCR−VLM / 95% item CI | 회복/회귀 vs VLM |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| 8B | 1330/1895 (70.18%) | 1404/1895 (74.09%) | 1399/1895 (73.83%) | +3.64pp | -0.26pp [-1.32, +0.74] | 36/41 |
| 4B | 1308/1895 (69.02%) | 1378/1895 (72.72%) | 1373/1895 (72.45%) | +3.43pp | -0.26pp [-1.42, +0.90] | 41/46 |

| 집합 | n | 8B VLM inventory | 8B OCR | 4B VLM inventory | 4B OCR |
| --- | ---: | ---: | ---: | ---: | ---: |
| screen | 240 | 74.17% | 74.58% | 75.42% | 72.92% |
| selection | 239 | 73.22% | 74.48% | 76.15% | 76.99% |
| internal_evaluation | 1416 | 74.22% | 73.59% | 71.68% | 71.61% |

8B OCR는Screen+1개·Selection+3개·Internal−9개였다. 4B OCR는Screen−6개·Selection+2개·Internal−1개다. 따라서 Screen만으로 전체 accuracy나 속도를 예상하면 안 된다.

### 총 처리 시간과 GPU 호출 시간

| 모델·방법 | CPU OCR | GPU 전처리+풀이 | 총 호출 시간 | 초/pair |
| --- | ---: | ---: | ---: | ---: |
| 8B · VLM inventory | — | 207.26분 | 207.26분 | 6.562 |
| 8B · OCR inventory | 114.68분 | 65.23분 | 179.91분 | 5.696 |
| 4B · VLM inventory | — | 148.43분 | 148.43분 | 4.699 |
| 4B · OCR inventory | 114.68분 | 63.02분 | 177.70분 | 5.626 |

8B의 총시간은 **13.2% 감소**했지만4B는 **19.7% 증가**했다. CPU OCR 자체는 두 solver가 공유하며114.68분이다. 이전4B VLM inventory가 이미 빠르므로 CPU OCR 교체가4B 단독 recipe의 속도 개선으로 이어지지 않았다.

8B Internal만 보면125.89→128.35분으로 소폭 느려졌다. Screen에서의37.1% 감소와 달리 전체8B 감소는13.2%다. OCR는 GPU를 CPU로 옮겨 GPU 호출 구간을 크게 줄이지만 항상 총시간까지 줄이는 방법은 아니다.

공통 OCR+LM 전처리는158.10분이다. 단독 recipe에는 이를 각 모델에 청구하되, 8B+4B 공동 recipe는 한 번만 더해 **199.50분**이다. 이번 실제 신규4B 풀이 호출은 cache를 제외해10.94분이었다. 이는 전체4B 단독 처리시간과 다르다.

모든 시간은 기록된 호출 구간의 합으로 모델 적재·프로세스 기동·일부CPU/I/O를 제외한다. CPU는3스레드, GPU는B200 MIG45GB이며 GPU 호출 시간은 GPU utilization이나 전력 측정치가 아니다. 재사용 호출도 원래 시간을 청구했고, 공유 cache key는 전역으로 한 번, batch 시간은 primary행 비율로 배분했다.

### 언어별 변화와 품질 확인

| GUI | n | 8B VLM→OCR | 4B VLM→OCR |
| --- | ---: | ---: | ---: |
| EN | 474 | 81.22% → 80.17% | 81.86% → 81.43% |
| ZH | 474 | 78.27% → 77.00% | 74.68% → 74.68% |
| TH | 474 | 60.34% → 62.03% | 51.90% → 52.11% |
| RU | 473 | 76.53% → 76.11% | 82.45% → 81.61% |

Main632개 OCR 이미지는 모두 처리에 성공했고 최종 label 파싱 실패는 두 모델 모두0이었다. 8B는원문 fallback77pair를 포함했다. VLM inventory와 완성 MCQ가 같았던1,481pair 중2pair에서 label 차이가 있어, 관찰된 정오 변화 전부를 inventory 내용 차이로 단정하지 않는다. 문자 인식 GT를 별도로 검수한 실험은 아니므로 OCR 문자 인식 자체가 더 정확하다고 주장하지 않는다.

8B/4B OCR는 전처리와1,895개 완성 MCQ를 정확히 공유했다. 8B73.83%와4B72.45%의 차이는1.37pp이며 4B−8B CI는[−4.55,+1.74]pp다. 두 solver의 동등성도 확인한 것은 아니다.

**현재 판단:** OCR는8B에서 작은 accuracy 하락 점추정과 총시간/GPU 비용 절감이 관찰된 실용적 대안이다. 4B에서는 accuracy 점추정도 약간 낮고 총시간은 늘어, GPU 호출 시간을 줄이는 가치와 CPU 비용을 함께 고려해야 한다. 전 모델 공통의 정확도·속도 우월성을 결론 내리지 않는다.

[완료 raw archive](../artifacts/ocr_completed_8b_4b.tar.gz)와 [파일별 SHA-256·복원 범위](../artifacts/ocr_completed_archive_manifest.json)에 계약·전사 원문·matching 응답·예측·비용·고정 의존 파일을 보존한다. 모델 weights·screenshot·private label 파일·mock·미완료 attempt는 archive에 포함하지 않는다. 깨끗한 checkout의 저장소 루트에서 `tar -xzf followup_rel_4lang/method_dev/artifacts/ocr_completed_8b_4b.tar.gz`로 복원한다. 데이터·이미지와 frozen HF checkpoint는 기존 lock/runbook에 따라 별도 준비해야 하며 일부 런타임 경로는 이 연구실 workspace의 절대 경로다.

[8B 전체 원시 집계](OCR_INVENTORY_FULL_DEV_RESULTS_KO.md) · [4B 전체 원시 집계](OCR_QWEN3_VL_4B_RESULTS_KO.md) · [모든 방법의 개발 이력](CURRENT_EXPERIMENT_SUMMARY_KO.md) · [8B→4B 고정 프로토콜](OCR_8B_4B_CHAIN_PROTOCOL_KO.md)
