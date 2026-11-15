# Step 3: 2×2 하네스와 내부 평가 상태

같은 자동 extraction 결과를 TXT_SEL과 GUI_SEL이 공유하고, 전체 번역에는 inventory 제공 여부만 구분한다. 모든 결과에 raw output·edit·fallback·config/prompt 지문을 남긴다. Full 조건은 자유로운 전체 번역이므로 selective 조건과 단계가 동일하지 않다. Numeric·옵션 필드 검사는 수행하지만 방향·부정의 번역 의미까지 자동 보증하지 않는다.

실제 downstream smoke는 기존 ExpA Qwen3 계약의 모델 revision·system·greedy·최대2토큰·label scoring·배치3을 사용했다. 같은 pilot 한 쌍의 결과는 다음과 같다. 정답 B는 평가 단계에서만 읽었다.

| 조건 | 생성 답 | 정답 여부 |
| --- | --- | --- |
| O 재실행 | A | 오답 |
| TXT_FULL | A | 오답 |
| GUI_FULL | A | 오답 |
| TXT_SEL | A | 오답 |
| GUI_SEL | A | 오답 |

과거 Qwen3 full REL의 같은 pilot O도 A였다. 과거 배치는4, 새 smoke는3이며 새로운 큐는 condition-major다. **한 O 응답의 일치는 전체 batch composition 동등성을 입증하지 않는다.** ExpA와 동일 pair들의 O/R 재현성 검사는 아직 미완료다. T/R은 역사적 reference로 공통 로더에서 분리하지만 새 selective 실측 개선과 비교할 main 결과가 없다.

Calibrated primary 모델과 40문항 calibration이 아직 준비되지 않아 internal evaluation은 실행하지 않았다. 따라서 1,895쌍 전체 또는1,416쌍 held-out accuracy·차이·CI·p값은 **없다**. 내부 결과를 보고 method를 튜닝한 적도 없다. 이 pilot 1쌍으로 성공률·언어 효과·회복 효과를 주장하지 않는다.

분석 코드는 paired generation accuracy, item단위 bootstrap10,000회·95% CI, 사전 primary3대비의 Holm 보정, T/R reference 차이, recovery/regression, GUI 언어·언어쌍·worst pair를 제공한다. 빈/실패 변환은 원문 fallback을 포함하며 실패·미파싱 생성은 오답이다. 조건 누락·중복이면 분석을 거절한다. 모델 예측 없이 synthetic fixture에서만 수학적 동작을 테스트했다. GLMM sensitivity와 screenshot-cluster sensitivity는 아직 구현·실행하지 않았다.
