# EasyOCR inventory: Screen 비교 결과

20개 main semantic item·240 pair. 기존 E1 출력·M0 prompt·downstream 설정을 유지하고 inventory 공급원만 바꿨다. 실행은 batch 구성을 유지한 288 pair이며 pilot 48 pair는 아래 정확도·계산 시간에서 제외한다.

| 조건 | 정답/240 | 정확도 | Inventory | 추출+matching | 최종 풀이 | 총 계산 시간 | 초/pair |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| VLM inventory E1/M0 | 178 | 74.17% | 29.56분 | 6.37분 | 3.17분 | 39.10분 | 9.774 |
| EasyOCR inventory E1/M0 | 179 | 74.58% | 14.92분 | 6.50분 | 3.17분 | 24.59분 | 6.146 |

OCR−VLM +0.42pp, semantic-item bootstrap 95% CI [-2.08, +3.33]pp, 회복 7 / 회귀 6 pair. 반복 관찰한 개발 집합의 탐색 결과다.

비용은 CPU OCR와 GPU LM/VLM 호출 구간을 순차 합산했다. 모델 다운로드/적재·프로세스 기동은 제외하며 OCR stage wall과 reader 적재 시간은 results.json에 별도로 보존한다. 기존 추출과 재사용 풀이도 최초 호출 시간을 청구한다. 같은 완성 batch의 시간은 한 번만 계산하고 main 비율로 배분한다.

## GUI 언어별

| GUI | n | VLM inventory | EasyOCR inventory |
| --- | ---: | ---: | ---: |
| EN | 60 | 78.33% | 75.00% |
| ZH | 60 | 78.33% | 80.00% |
| TH | 60 | 68.33% | 68.33% |
| RU | 60 | 71.67% | 75.00% |

## OCR 처리 및 비교 범위

Main 이미지 80개 상태: `{'success': 80}`. 기존 VLM이 선택했던 교체 표현 225개 중 OCR inventory에 exact 존재하는 것은 188개다. 이는 기존 선택과의 호환성 지표이며 실제 화면 label precision/recall이 아니다.

기존 VLM inventory와 완성 MCQ가 같은 경우 178 pair, 그중 label 차이 0 pair. 동일 행만으로 재사용하지 않고 전체 batch/이미지/prompt/환경이 같은 경우에만 재사용했다.

원시 bbox·문자열·confidence는 OCR 산출물에 저장하되 matching에는 정렬된 문자열 목록만 제공했다. OCR 빈 목록·실패·추출 실패·matching fallback을 분모에서 제거하지 않았다. OCR confidence와 문자열 겹침은 검증된 의미 정확도가 아니다.

단계별 원시 자료와 SHA/config/model lock: 해당 run의 contract.json, ocr_weights.json, results.json. OCR와 VLM이 출력하는 문자열 단위·후보 수 차이도 이 공급원 교체 효과에 포함된다.
