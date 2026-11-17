# Qwen3-VL-4B: E1/M0 완료 결과

완료 범위: screen, selection. 미완료: internal_evaluation.

고정 Qwen3-8B LM과 E1/M0 prompt를 유지하고, inventory·최종 풀이만 4B로 수행했다. Options는 원문 그대로다. 세부 설정과 모든 초기·repair raw 응답은 snapshot 및 압축 원시에 보존했다.

| 범위 | 문항 | n | O | Method | 차이 | 95% item bootstrap CI | 회복/회귀 |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| screen | 20 | 240 | 174/240 (72.50%) | 181/240 (75.42%) | +2.92pp | [-2.93, +11.67] | 20/13 |
| selection | 20 | 239 | 179/239 (74.90%) | 182/239 (76.15%) | +1.26pp | [-3.75, +6.72] | 17/14 |
| combined | 40 | 479 | 353/479 (73.70%) | 363/479 (75.78%) | +2.09pp | [-2.08, +7.32] | 37/27 |

Pilot 48쌍과 사전 제외 1쌍은 주 분석에서 제외했다. 처리 실패는 원문 fallback으로 분모에 포함했다. CI는 semantic item 단위 10,000회 bootstrap이다. 현재 양의 점추정의 CI가 0을 포함하므로 개선을 확정하지 않는다. 반복 관찰한 development set의 결과다.

| 범위 | GUI | n | O | Method | 차이 |
| --- | --- | ---: | ---: | ---: | ---: |
| screen | EN | 60 | 81.67% | 88.33% | +6.67pp |
| screen | ZH | 60 | 80.00% | 73.33% | -6.67pp |
| screen | TH | 60 | 50.00% | 56.67% | +6.67pp |
| screen | RU | 60 | 78.33% | 83.33% | +5.00pp |
| selection | EN | 60 | 85.00% | 81.67% | -3.33pp |
| selection | ZH | 60 | 75.00% | 86.67% | +11.67pp |
| selection | TH | 60 | 53.33% | 51.67% | -1.67pp |
| selection | RU | 59 | 86.44% | 84.75% | -1.69pp |
| combined | EN | 120 | 83.33% | 85.00% | +1.67pp |
| combined | ZH | 120 | 77.50% | 80.00% | +2.50pp |
| combined | TH | 120 | 51.67% | 54.17% | +2.50pp |
| combined | RU | 119 | 82.35% | 84.03% | +1.68pp |

| 범위 | Inventory 성공/전체 main | MCQ 수정 | 원문 fallback | Label 파싱 실패 |
| --- | ---: | ---: | ---: | ---: |
| screen | 79/80 | 230/240 | 5 | 0 |
| selection | 79/80 | 222/239 | 14 | 0 |

| 범위 | 주 분석 n | Inventory+추출+정렬+풀이 초 | 초/pair | 실제 신규 method stage wall / 실행pair | 초/pair |
| --- | ---: | ---: | ---: | ---: | ---: |
| screen | 240 | 1229.64 | 5.123 | 2788.92초 / 288 | 9.684 |
| selection | 239 | 1272.41 | 5.324 | 1212.26초 / 240 | 5.051 |

첫 비용은 cache hit도 원래 runtime으로 청구하고 과거 고정 LM 추출을 포함한 단독 recipe 계산 구간이다. 모델 적재·일부 CPU 작업은 제외한다. 실제 신규 stage wall은 inventory+정렬+method 풀이이며 O baseline과 재사용 E1 추출은 제외한다. 서로 다른 집계 기준을 나눠 제시했다. 초/pair는 데이터셋 공유·batch를 반영한 상각 처리량이며 단일 질의 latency가 아니다.

[고정 프로토콜](QWEN3_VL_4B_TRANSFER_PROTOCOL_KO.md) · [설정·검증·시간 snapshot](../artifacts/transfer_qwen3_vl_4b_results_snapshot.json) · [완료 원시 archive](../artifacts/transfer_qwen3_vl_4b_completed.tar.gz)

Archive는 **빈 디렉터리**에 해제한다. 완료 cohort의 입력·inventory·E1 source 추출·M0 치환·O/method 예측·환경·설정·체크섬과 평가 전용 label을 포함한다. 모델 가중치·이미지·진행 중 출력은 포함하지 않는다. 평가 label은 automatic method 입력과 별도 파일이다.

재집계: `.venv/bin/python followup_rel_4lang/method_dev/scripts/report_model_transfer_progress.py`. GPU 추론 없이 완료 cohort만 읽는다. 실행 중인 runner·contract·출력·완료 marker는 변경하지 않는다.
