# EasyOCR inventory: 전체 개발 집합 비교

Screen의 OCR/E1/M0를 고정하고 Selection → Internal 순으로 확장했다. Screen은 기존 결과를 재사용했다. OCR CPU3, 기존 E1 source 추출 재사용, 기존 Qwen3-8B M0, Qwen3-VL-8B BF16·SDPA·2MP·batch3·label-only2tokens다.

완료: screen, selection, internal_evaluation. 미완료: 없음.

| 범위 | item | pair | O | VLM inventory E1/M0 | OCR inventory E1/M0 | OCR−VLM | 95% item CI | 회복/회귀 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| screen | 20 | 240 | 162/240 (67.50%) | 178/240 (74.17%) | 179/240 (74.58%) | +0.42pp | [-2.08, +3.33]pp | 7/6 |
| selection | 20 | 239 | 171/239 (71.55%) | 175/239 (73.22%) | 178/239 (74.48%) | +1.26pp | [-0.83, +3.75]pp | 5/2 |
| internal_evaluation | 118 | 1416 | 997/1416 (70.41%) | 1051/1416 (74.22%) | 1042/1416 (73.59%) | -0.64pp | [-1.84, +0.56]pp | 24/33 |
| all_158 | 158 | 1895 | 1330/1895 (70.18%) | 1404/1895 (74.09%) | 1399/1895 (73.83%) | -0.26pp | [-1.32, +0.74]pp | 36/41 |

미완료 cohort의 부분 출력은 정확도로 집계하지 않는다. Main1,895pair는158item×12방향에서 기존 사전 제외1pair를 뺀 값이다. 실행에는 Selection의 제외1pair와 Screen pilot48pair가 남아 있지만 주 정확도·시간에서 제외했다. 실패·빈 OCR·fallback·미파싱 답은 분모에 포함한다. CI는 item bootstrap10,000회이며 이미 관찰한 개발 집합의 탐색 결과다.

| 범위 | 방법 | Inventory | E1 추출+M0 | 최종 풀이 | 총 계산 시간 | 초/pair |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| screen | VLM inventory | 29.56분 | 6.37분 | 3.17분 | 39.10분 | 9.774 |
| screen | CPU EasyOCR inventory | 14.92분 | 6.50분 | 3.17분 | 24.59분 | 6.146 |
| selection | VLM inventory | 28.58분 | 10.44분 | 3.26분 | 42.28분 | 10.615 |
| selection | CPU EasyOCR inventory | 14.11분 | 9.54분 | 3.33분 | 26.98분 | 6.773 |
| internal_evaluation | VLM inventory | 80.50분 | 30.51분 | 14.88분 | 125.89분 | 5.334 |
| internal_evaluation | CPU EasyOCR inventory | 85.65분 | 27.39분 | 15.31분 | 128.35분 | 5.439 |
| all_158 | VLM inventory | 138.64분 | 47.31분 | 21.31분 | 207.26분 | 6.562 |
| all_158 | CPU EasyOCR inventory | 114.68분 | 43.43분 | 21.81분 | 179.91분 | 5.696 |

Primary pairs; shared preprocessing cache keys counted once, including original cached runtimes. CPU OCR + GPU calls; model loads/startup excluded, batch runtime allocated by primary-row fraction.

CPU와 GPU 호출 시간을 순차 합산한 상각 처리량이며 단일 요청 latency/전체 wall time과 다르다. 전역 중복 제거로 pooled 비용은 cohort별 단순 합과 소폭 다를 수 있다. 실제 추가 wall·cache 재사용은 각 stage cost.json에 있다.

## GUI 언어별

| 범위 | GUI | pair | O | VLM inventory | OCR inventory |
| --- | --- | ---: | ---: | ---: | ---: |
| screen | EN | 60 | 75.00% | 78.33% | 75.00% |
| screen | ZH | 60 | 73.33% | 78.33% | 80.00% |
| screen | TH | 60 | 45.00% | 68.33% | 68.33% |
| screen | RU | 60 | 76.67% | 71.67% | 75.00% |
| selection | EN | 60 | 83.33% | 80.00% | 80.00% |
| selection | ZH | 60 | 71.67% | 81.67% | 78.33% |
| selection | TH | 60 | 50.00% | 51.67% | 60.00% |
| selection | RU | 59 | 81.36% | 79.66% | 79.66% |
| internal_evaluation | EN | 354 | 81.92% | 81.92% | 81.07% |
| internal_evaluation | ZH | 354 | 76.27% | 77.68% | 76.27% |
| internal_evaluation | TH | 354 | 48.59% | 60.45% | 61.30% |
| internal_evaluation | RU | 354 | 74.86% | 76.84% | 75.71% |
| all_158 | EN | 474 | 81.22% | 81.22% | 80.17% |
| all_158 | ZH | 474 | 75.32% | 78.27% | 77.00% |
| all_158 | TH | 474 | 48.31% | 60.34% | 62.03% |
| all_158 | RU | 473 | 75.90% | 76.53% | 76.11% |

## 실패·재사용 진단

```json
{
  "screen": {
    "ocr_status": {
      "success": 80
    },
    "rewrite_status": {
      "success": 233,
      "fallback_original": 4,
      "no_op_no_edits": 3
    },
    "changed_pairs": 233,
    "invalid_labels": 0,
    "same_MCQs": 178,
    "same_MCQs_label_differences": 0,
    "inventory_images": 80,
    "source_MCQs": 80,
    "infer_cost": {
      "wall_seconds": 147.94028572831303,
      "execution_mode": "gpu",
      "reused_batches": 45,
      "reused_rows": 135,
      "new_batches": 51,
      "conflicting_cache_keys": 0
    }
  },
  "selection": {
    "ocr_status": {
      "success": 80
    },
    "rewrite_status": {
      "fallback_original": 14,
      "success": 223,
      "no_op_no_edits": 2
    },
    "changed_pairs": 223,
    "invalid_labels": 0,
    "same_MCQs": 180,
    "same_MCQs_label_differences": 0,
    "inventory_images": 80,
    "source_MCQs": 80,
    "infer_cost": {
      "wall_seconds": 129.6199371488765,
      "execution_mode": "gpu",
      "reused_batches": 38,
      "reused_rows": 114,
      "new_batches": 42,
      "conflicting_cache_keys": 0
    }
  },
  "internal_evaluation": {
    "ocr_status": {
      "success": 472
    },
    "rewrite_status": {
      "success": 1346,
      "fallback_original": 59,
      "no_op_no_edits": 11
    },
    "changed_pairs": 1346,
    "invalid_labels": 0,
    "same_MCQs": 1123,
    "same_MCQs_label_differences": 2,
    "inventory_images": 472,
    "source_MCQs": 472,
    "infer_cost": {
      "wall_seconds": 516.5786009086296,
      "execution_mode": "gpu",
      "reused_batches": 236,
      "reused_rows": 708,
      "new_batches": 236,
      "conflicting_cache_keys": 0
    }
  }
}
```

기존 VLM inventory나 parallel R은 OCR 전사의 GT가 아니다. OCR 문자 인식 정확도는 이 REL 결과만으로 판정하지 않는다. 최종 예측 재사용은 순서가 같은 완성 batch의 prompt·이미지·모델·seed·환경이 일치할 때만 허용한다.

[고정 확장 프로토콜](OCR_INVENTORY_FULL_DEV_PROTOCOL_KO.md) · [전체 결과 snapshot](../artifacts/ocr_inventory_full_dev_results_snapshot.json).
