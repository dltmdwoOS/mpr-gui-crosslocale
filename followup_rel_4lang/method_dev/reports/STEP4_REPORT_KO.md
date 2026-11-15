# Step 4: RFA 준비 상태

Referent와 abstained referent를 placeholder로 보호하고 context를 EN 또는 고정 model pivot으로 번역하는 모듈·CLI를 준비했다. Placeholder의 field 이동·중복·누락, 숫자 변경, 보기 충돌을 검사하고 실패하면 GUI_SEL의 aligned 입력을 그대로 보존한다. source·GUI·pivot이 모두 다른지 별도 필드로 남긴다.

`pivot_policy_PENDING.json`의 EN은 후보일 뿐 선택 완료가 아니다. Calibration-only 정책이 고정되지 않았으면 실행기가 거절한다. InternVL3.5의 최적 pivot을 기존 불완전 행렬에서 추측하지 않았다.

Step 3 이전 게이트가 미통과라 RFA GPU 번역·REL 평가·추가 대비·의미 검토를 실행하지 않았다. Direction, adjacency, negation의 cross-language 동등성은 placeholder·digit 검사만으로 입증할 수 없어 별도 검토가 필요하다. 정책 calibration, translation error율, latency와 성능효과는 아직 미측정이다.
