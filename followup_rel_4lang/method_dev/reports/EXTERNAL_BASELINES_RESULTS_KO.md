# 외부 baseline GUI 이식 결과

[고정 프로토콜과 원 논문·공식 구현](EXTERNAL_BASELINES_PROTOCOL_KO.md). TT는 Qwen3-8B English 전체 번역, CLP는 고정 LM의 English 이해 응답을 대화에 보존한 뒤 Qwen3-VL-8B가 이미지를 보며 단계별 풀이한다. Google Translate/GPT-3.5 원 결과의 재현과 구분한다.

| 범위 | n | O | E1/M0 | Translate-Test EN | CLP GUI |
| --- | ---: | ---: | ---: | ---: | ---: |
| screen | 240 | 162/240 (67.50%) | 178/240 (74.17%) | 171/240 (71.25%) | 166/240 (69.17%) |
| selection | 239 | 171/239 (71.55%) | 175/239 (73.22%) | 170/239 (71.13%) | 147/239 (61.51%) |
| internal_evaluation | 1416 | 997/1416 (70.41%) | 1051/1416 (74.22%) | 1007/1416 (71.12%) | 937/1416 (66.17%) |
| combined | 1895 | 1330/1895 (70.18%) | 1404/1895 (74.09%) | 1348/1895 (71.13%) | 1250/1895 (65.96%) |

| 범위 | 비교 | 차이 | 95% item bootstrap CI | 회복/회귀 |
| --- | --- | ---: | --- | ---: |
| screen | E1/M0 − TRANSLATE_TEST_EN_QWEN3 | +2.92pp | [-7.08, +12.50] | 31/24 |
| screen | E1/M0 − CLP_GUI_LM_VLM | +5.00pp | [-6.25, +14.59] | 47/35 |
| selection | E1/M0 − TRANSLATE_TEST_EN_QWEN3 | +2.09pp | [-5.83, +10.42] | 27/22 |
| selection | E1/M0 − CLP_GUI_LM_VLM | +11.72pp | [+0.00, +24.27] | 48/20 |
| internal_evaluation | E1/M0 − TRANSLATE_TEST_EN_QWEN3 | +3.11pp | [-0.21, +6.50] | 163/119 |
| internal_evaluation | E1/M0 − CLP_GUI_LM_VLM | +8.05pp | [+3.53, +12.50] | 266/152 |
| combined | E1/M0 − TRANSLATE_TEST_EN_QWEN3 | +2.96pp | [+0.00, +6.07] | 221/165 |
| combined | E1/M0 − CLP_GUI_LM_VLM | +8.13pp | [+4.32, +12.09] | 361/207 |

전체 주 분석은 pilot 48쌍과 사전 제외 1쌍을 뺀 main 1895쌍이다. 실패·미변환·CLP 최종 label 실패를 제거하지 않았다. 이미 관찰한 158개 개발 문항의 탐색 결과다. 모든 CI는 semantic item 단위 10,000회 bootstrap이며, 반복 개발·다중 비교를 보정한 독립 검증은 아니다.

| 범위 | 조건 | 비용n | LM 초 | 풀이VLM 초 | 합계 초 | 초/pair | 초/item |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| screen | TRANSLATE_TEST_EN_QWEN3 | 240 | 142.91 | 162.39 | 305.30 | 1.272 | 15.26 |
| screen | CLP_GUI_LM_VLM | 240 | 1004.59 | 1720.06 | 2724.65 | 11.353 | 136.23 |
| selection | TRANSLATE_TEST_EN_QWEN3 | 239 | 104.94 | 150.82 | 255.77 | 1.070 | 12.79 |
| selection | CLP_GUI_LM_VLM | 239 | 842.93 | 1378.48 | 2221.41 | 9.295 | 111.07 |
| internal_evaluation | TRANSLATE_TEST_EN_QWEN3 | 1416 | 672.11 | 692.94 | 1365.05 | 0.964 | 11.57 |
| internal_evaluation | CLP_GUI_LM_VLM | 1416 | 4989.86 | 6272.22 | 11262.07 | 7.953 | 95.44 |

위 시간은 고유 source 처리를 공유한 recipe 계산 구간이다. Cache도 원래 runtime으로 청구하고 batch는 선택행비율로 안분했다. 모델적재·worker기동·일부CPU처리는 제외한다. 초/pair는 상각 처리량이며 단일 query latency가 아니다. COMPLETE는 마지막 재개 invocation wall, stage cost는 완료 attempt wall을 기록한다. 중단된 이전 attempt의 wall이 없을 수 있으므로 이를 모든 시도 합산 wall로 부르지 않는다. 원래 cache 호출 runtime은 recipe에 보존한다.

CLP는 VLM출력512tokens로 기존 label-only2tokens보다 큰 예산이다. E1/M0와의 차이는GUI inventory 하나의 순수 효과가아니다. 숫자/보기중복 경고는의미 오류율이아니며, 번역의 방향·부정 의미 보존을 자동 보장하지 않는다.

## 처리 진단

```json
{
  "screen": {
    "TRANSLATE_TEST_EN_QWEN3": {
      "source_status": {
        "success": 60,
        "english_identity": 20
      },
      "LM_cap_hits_unique_sources": 0,
      "invalid_final_label_pairs": 0,
      "solver_cap_hits_pairs": 0,
      "generated_output_tokens": 480,
      "digit_change_pairs": 0,
      "duplicate_option_pairs": 0,
      "fallback_pairs": 0,
      "surface_direction_or_negation_cue_flags": 15,
      "unchanged_MCQs_label_changes": 0
    },
    "CLP_GUI_LM_VLM": {
      "source_status": {
        "success": 80
      },
      "LM_cap_hits_unique_sources": 51,
      "invalid_final_label_pairs": 46,
      "solver_cap_hits_pairs": 43,
      "generated_output_tokens": 73973
    }
  },
  "selection": {
    "TRANSLATE_TEST_EN_QWEN3": {
      "source_status": {
        "success": 60,
        "english_identity": 20
      },
      "LM_cap_hits_unique_sources": 0,
      "invalid_final_label_pairs": 0,
      "solver_cap_hits_pairs": 0,
      "generated_output_tokens": 478,
      "digit_change_pairs": 3,
      "duplicate_option_pairs": 0,
      "fallback_pairs": 0,
      "surface_direction_or_negation_cue_flags": 12,
      "unchanged_MCQs_label_changes": 0
    },
    "CLP_GUI_LM_VLM": {
      "source_status": {
        "success": 80
      },
      "LM_cap_hits_unique_sources": 49,
      "invalid_final_label_pairs": 66,
      "solver_cap_hits_pairs": 57,
      "generated_output_tokens": 80048
    }
  },
  "internal_evaluation": {
    "TRANSLATE_TEST_EN_QWEN3": {
      "source_status": {
        "success": 354,
        "english_identity": 118
      },
      "LM_cap_hits_unique_sources": 0,
      "invalid_final_label_pairs": 0,
      "solver_cap_hits_pairs": 0,
      "generated_output_tokens": 2832,
      "digit_change_pairs": 6,
      "duplicate_option_pairs": 0,
      "fallback_pairs": 0,
      "surface_direction_or_negation_cue_flags": 84,
      "unchanged_MCQs_label_changes": 0
    },
    "CLP_GUI_LM_VLM": {
      "source_status": {
        "success": 472
      },
      "LM_cap_hits_unique_sources": 259,
      "invalid_final_label_pairs": 284,
      "solver_cap_hits_pairs": 239,
      "generated_output_tokens": 446006
    }
  }
}
```

[전체 설정·비용·언어별 결과 snapshot](../artifacts/external_baselines_results_snapshot.json) · [번역 내용 보존 검토 후보](EXTERNAL_BASELINES_TRANSLATION_AUDIT_KO.md) · [완료 raw archive](../artifacts/external_baselines_completed.tar.gz) · [archive checksum](../artifacts/external_baselines_archive_manifest.json)
