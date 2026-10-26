# R→F 정답 전환의 언어별 추적

2026-10-06에 Qwen batch 32와 InternVL batch 1의 완료된 REL 4언어 full 결과를
다시 분석했다. 새 추론은 수행하지 않았다. R은 문맥이 원래 질문 언어이고 참조
표현은 GUI 언어다. F는 문맥과 참조 표현이 모두 GUI 언어다. 따라서 같은
문항·언어쌍의 R→F는 GUI 이미지·정답·보기 순서·참조 언어를 고정한 채 질문과
보기의 문맥 언어를 바꾸는 비교다. 원본 문제 표시를 제외하고 O/R/C/F가 모두
성공한 text-dependent 불일치 언어쌍 3,576개를 주 분석으로 삼았다.
`source→target`은 원래 질문 언어→GUI 언어다.

| 언어쌍 | n | Qwen 교정/상실 | Qwen F−R | InternVL 교정/상실 | InternVL F−R |
|---|---:|---:|---:|---:|---:|
| en→zh | 299 | 23/19 | +1.34pp | 20/23 | −1.00pp |
| en→th | 298 | 21/46 | −8.39pp | 19/62 | −14.43pp |
| en→ru | 300 | 19/21 | −0.67pp | 13/46 | −11.00pp |
| zh→en | 299 | 15/16 | −0.33pp | 18/14 | +1.34pp |
| zh→th | 296 | 20/45 | −8.45pp | 19/59 | −13.51pp |
| zh→ru | 298 | 21/28 | −2.35pp | 17/49 | −10.74pp |
| th→en | 298 | 46/10 | +12.08pp | 80/16 | +21.48pp |
| th→zh | 296 | 51/12 | +13.18pp | 68/12 | +18.92pp |
| th→ru | 297 | 49/23 | +8.75pp | 70/27 | +14.48pp |
| ru→en | 300 | 22/9 | +4.33pp | 33/13 | +6.67pp |
| ru→zh | 298 | 34/15 | +6.38pp | 30/12 | +6.04pp |
| ru→th | 297 | 21/43 | −7.41pp | 19/50 | −10.44pp |

교정은 R 오답→F 정답, 상실은 R 정답→F 오답이다. 전체 교정/상실은
Qwen **342/287**, InternVL **406/383**으로 기존 `summary.json`과 일치한다.
타깃을 태국어로 바꾼 891개 언어쌍에서는 Qwen 62/134(−8.08pp),
InternVL 57/171(−12.79pp)였다. R에서 맞혔던 것 중 F에서 잃은 비율은
각각 134/622=21.5%, 171/350=48.9%다. 반대로 source가 태국어인
891개 언어쌍의 순증가는 Qwen +101(+11.34pp), InternVL +163(+18.29pp)다.

같은 source와 원본 문항을 고정하고 en/zh/ru에서 태국어 타깃을 선택한 경우와
다른 두 타깃을 비교했다. 원본 문제 표시가 없는 완전 사례 295문항에서
태국어 타깃의 F−R은 Qwen −8.14pp, InternVL −12.77pp였고, 다른 타깃은
각각 +1.47pp, −1.36pp였다. 차이는 Qwen **−9.60pp**
(문항 단위 5,000회 탐색적 bootstrap 95% 구간 −14.24∼−4.92),
InternVL **−11.41pp**(−16.38∼−6.44)다. source와 문항은 맞췄지만
타깃 GUI 이미지와 번역은 함께 달라진다.

같은 언어 질문·GUI를 사용한 301개 text-dependent 문항의 정확도는
Qwen에서 en 80.7%, zh 75.1%, ru 74.8%, th 61.8%였고,
InternVL에서 en 78.1%, zh 71.4%, ru 58.5%, th 26.2%였다.
이전 6×6 REL 실험의 같은 언어 조건 366문항도 두 모델 모두 태국어가 가장
낮았다(`01_code/results/summaries/vast_6x6_{model}.json`). 독립 집합은
아니지만 다른 실행 설정에서도 방향이 같았다. Text-independent 문항에서도
태국어 타깃 F−R은 Qwen −7.26pp, InternVL −17.32pp였다(n=179).

이 결과는 이 모델·데이터에서 **타깃 문맥 언어의 상대 난도**가 R→F 손익과
강하게 연관된다는 가설과 맞는다. 언어 자체의 모델 처리 능력, 번역 품질,
질문·보기의 의미 변화, 언어별 GUI 화면 품질은 아직 분리되지 않았다.
F는 질문 문장뿐 아니라 보기 문맥도 바꾸므로 어느 부분이 오답 전환을
일으켰는지도 추가 검토가 필요하다. 언어쌍별 수치는 기술 통계이며 개별
언어쌍의 검정이나 다중 비교 보정은 아직 하지 않았다.

두 모델이 **동일한 49개** 문항·언어쌍에서 R 정답→F 오답이 되었고,
그중 27개는 태국어 타깃이다. 예를 들어
`rel::4/Youtube_5.jpg::zh::th`에서 두 모델 모두 정답 C에서 F의 B로,
`rel::2/calendar_6.png::ru::th`에서는 정답 B에서 F의 C로 바뀌었다.
이 27개를 먼저 이중언어 검수해 R/F의 질문·보기 의미와 화면 정답을
확인하는 것이 다음 단계다.

전체 사례와 재현 자료:

- [언어쌍별 집계](results/analysis/rf_context_switch/rf_by_language_pair.csv)
- [개별 정답 전환 1,746건](results/analysis/rf_context_switch/rf_flipped_cases.csv): 두 집단·두 모델의 질문·보기와 생성 답 포함
- [두 모델 공통 정답 상실 49건](results/analysis/rf_context_switch/rf_common_losses.csv)
- [타깃별 집계](results/analysis/rf_context_switch/rf_by_target.csv)와 [같은 언어 기준선](results/analysis/rf_context_switch/matched_language_baseline.csv)
- [원본 문항 단위 태국어 타깃 대비](results/analysis/rf_context_switch/thai_target_within_item.csv)와 [분석 요약](results/analysis/rf_context_switch/summary.json)

결과는 서버의 Git 제외 디렉터리에 있다. 압축된 원격 결과에서도 다음 명령으로
동일하게 다시 생성할 수 있다.

```bash
python followup_rel_4lang/analyze_rf_flips.py
```
