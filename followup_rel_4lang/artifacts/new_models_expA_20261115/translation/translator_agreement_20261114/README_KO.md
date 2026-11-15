# 번역기 일치도 분석 (NLLB vs Gemma), 2026-11-14

탐색적 분석이며 사전등록되지 않았다. InternVL 결과는 열지 않았고 Qwen3 예측만 사용했다.

## 한 일

기존 translate_nllb.py를 복사해 translate_nllb_full.py로 저장했다(원본은 그대로). 바뀐 점은 모델 revision을 7be3e24664b38ce1cac29b8aeed6911aa0cf0576(facebook/nllb-200-distilled-1.3B)으로 고정한 것, 입력 작업 파일과 기본 출력 경로를 인자로 받게 한 것뿐이다. 생성 설정은 스모크 때와 같다(beam 4, 샘플링 없음, max_new_tokens 64, CPU fp32, 배치 16). 입력은 work/translation_jobs.jsonl의 고유 (원문, 원문 언어, 목표 언어) 6,917건으로, Gemma T와 같은 목록이다. 5,824초 걸렸고 모델 프로세스 메모리는 약 4.4 GB였다. 결과는 work/translations_nllb_full.jsonl.

역번역은 Gemma T의 번역문(T_gemma_first_spans.jsonl) 6,993개 고유 (번역문, 화면 언어, 질문 언어)를 NLLB로 질문 언어로 되돌렸다(6,101초). 결과는 work/backtranslations_nllb_full.jsonl. LaBSE는 revision 836121a0…, 정규화 임베딩 코사인을 썼다.

## 정의와 분모

일치(agree)는 build_T.norm()을 적용한 Gemma 번역과 NLLB 번역이 같은 경우다. 짝(pair)은 그 짝의 모든 span이 일치할 때만 agreed다. 화면 일치 수준은 build_T.match_level()을 그대로 썼다(exact, normalized, different). 분모는 main split 8,564 span, 1,895 짝이다. 사전등록에서 제외된 rel::5/forest_9.jpg::zh::ru 한 짝은 뺐다. 역번역 일치는 NLLB 역번역과 원문의 exact/normalized 비교와 LaBSE 유사도다. 모든 표는 tables/에 있고 span 단위 원자료는 work/agreement_spans.jsonl이다.

## 결과 (측정값)

Gemma와 NLLB가 일치한 span은 2,050개(23.9%)이고, 짝 기준 agreed는 1,895개 중 49개(2.6%)뿐이다. 화면 언어별 span 일치율은 en 13.3%, zh 27.4%, th 27.5%, ru 27.6%다. 짝 기준 agreed 비율은 en 0.4%(2짝), zh 3.2%(15), th 3.2%(15), ru 3.6%(17)다. 질문×화면 셀별 값은 tables/agreement_by_cell.csv에 있고, 일치율이 가장 낮은 셀은 th→en(span 6.7%), 높은 셀은 en→ru(39.2%)다. 12개 셀 중 ru→en은 agreed 짝이 0개다.

화면 텍스트와 맞는 비율(exact+normalized)은 Gemma가 전체 39.0%, NLLB가 17.1%다. 언어별로는 en 48.5 vs 9.9, zh 38.2 vs 18.6, th 35.6 vs 21.7, ru 33.6 vs 18.0이다. NLLB는 모든 화면 언어에서 낮다.

Gemma 번역을 NLLB로 역번역했을 때 원문과 정규화 후 같은 비율은 전체 23.4%(exact 20.2%), LaBSE 평균 0.811, 0.7 이상 75.8%다. 화면 언어별 정규화 일치는 en 33.9, zh 23.3, th 13.3, ru 23.0이고 LaBSE 평균은 0.882, 0.828, 0.696, 0.837이다. 태국어가 특히 낮다. 두 번역기가 일치한 span은 역번역 정규화 일치 35.2%, 불일치 span은 19.6%다.

## Qwen3 대비 (T−O, R−T, R−O, 단위 %p, 문항 bootstrap 10,000회, seed 20261114)

전체 1,895짝(158문항)은 T−O 0.69 [−2.06, 3.38], R−T 13.49 [10.00, 17.13], R−O 14.18 [11.13, 17.30]이다. agreed 49짝(23문항)은 T−O 4.39 [−9.44, 17.68], R−T 7.97 [0.0, 18.84], R−O 12.36 [3.77, 23.23]이다. not-agreed 1,846짝은 T−O 0.69 [−2.11, 3.45], R−T 13.44 [9.92, 17.07], R−O 14.13 [11.04, 17.32]로 전체와 거의 같다. agreed 집합은 문항 23개뿐이라 구간이 넓고, 이 숫자로 두 집합의 차이를 말할 근거는 없다. 화면 언어별 결과는 agreement_expA 출력의 agreement_contrasts.csv에 있다(문항 10개 미만인 집합은 생략되어 agreed|screen_en은 없다). agreed의 zh/th/ru는 짝이 15~17개, 문항 10~14개라 해석하기 어렵다.

## 주의할 점

- NLLB는 짧은 UI 문자열에서 약하다. 실제로 "Meeting"에 "The meeting."처럼 관사와 마침표가 붙는 출력이 보이고, 80건은 번역이 원문과 동일했다. 원인 분리는 하지 않았다.
- 짝 단위 agreed는 모든 span 일치를 요구하므로 span 일치율 24%에서는 거의 남지 않는다. 기준을 완화(예: span 80% 이상 일치)하면 집합이 커지지만 이번에는 하지 않았고, 정의를 바꾸는 일은 결정이 필요하다.
- 일치는 문자열 일치이며 의미 일치가 아니다. 의미가 같아도 표현이 다르면 differ다. LaBSE labse_gemma_nllb 값을 span 파일에 저장해 두었으니 완화 기준에 쓸 수 있다.
- 역번역은 NLLB의 오차가 섞여 있어 Gemma 번역 품질의 직접 측정이 아니다. 원문이 한 단어일수록 되돌림 일치가 낮을 수 있다.
- NLLB-200의 라이선스는 모델 카드상 CC-BY-NC 4.0으로 알고 있으나 이번에 확인하지 않았다: 확인 필요.
- Gemma 쪽 span은 한 짝 안의 맥락(parallel_id)에서 번역되었고 NLLB는 고유 문자열 단위로 번역되어 입력 조건이 다르다.
- bootstrap 시드는 analyze_expA.py의 20261113 대신 지시된 20261114로 모듈 변수를 덮어써서 썼다(파일은 수정하지 않음).

## 파일

- translate_nllb_full.py, build_agreement.py, analysis/agreement_expA.py
- work/: 번역·역번역 원출력, agreed_pairs.json, agreement_spans.jsonl, agreement_summary.json, 로그
- tables/: 일치율·화면 일치·역번역 CSV
- qwen3_out/: contrasts (agreement_contrasts.csv, agreement_summary.json)
- run_meta.json: revision, 입력 sha256, 시간
- 다른 모델 재실행: ../.venv/bin/python analysis/agreement_expA.py <model> <predictions> <out_dir>
