# 입력 단위 진단 (정답률 파일은 열람하지 않음)

사용한 입력은 work/T_gemma_first_spans.jsonl과 addon/followup_rel_4lang/expA/expA_inputs/T_conditions.jsonl 두 개다. 유사도 파일(T_gemma_first_similarity.jsonl)은 열어 필드만 확인했고 이번 특징에는 쓰지 않았다. 대상은 split=main의 1,896쌍 중 rel::5/forest_9.jpg::zh::ru를 뺀 1,895쌍(스팬 8,564개)이다. 스팬은 질문 줄기 1개와 선택지 A-D에 들어간 UI 이름 하나하나를 뜻한다. 쌍당 스팬 수가 다르므로 요약표의 스팬 비율은 스팬 수 가중이고, 쌍 단위 평균(delta, chrF, LCS, 혼합 스크립트율)은 쌍을 동일 가중으로 평균한다. 분모는 모든 요약 파일에 n_pairs, n_spans로 남겨 두었다.

## 조건과 정의
O는 질문어로 쓰인 원본 이름(source_text), T는 기계번역 이름(translation), R은 화면 이름(screen_text)이다. 이 중 R 조건의 질문 문자열은 T_conditions.jsonl에 없다(파일에는 T 조건만 있음). 그래서 O·R의 실제 질문 문자열을 쓴 계산은 없고, O는 source_text만으로 추정했다.

- 정확 일치(exact): 문자열이 완전히 같음. 정규화 일치(norm): NFKC, casefold 후 공백과 유니코드 구두점(P*)을 모두 제거한 문자열이 같음. 기호(S*)는 제거하지 않았다. 원 파일의 match 필드와 비교하면 exact는 전부 일치하고, normalized 판정은 27개 스팬에서 내 정규화와 다르다(원 추출 스크립트의 정규화 규칙을 확인하지 않았음, 확인 필요).
- 쌍 단위 변화: delta = T 일치 비율 - O 일치 비율. lost = 스팬 수준에서 source==screen이면서 translation!=screen, gained = 반대로 translation==screen이면서 source!=screen. n_lost_exact, n_gained_exact는 쌍 안의 스팬 수, any_lost, any_gained는 쌍에 하나라도 있는지(0/1)이다.
- chrF: sacrebleu가 설치돼 있지 않아 직접 구현했다. 문자 n-gram n=1..6, beta=2, 공백 제거, 스팬별 문장 수준 점수(0-100)를 쌍 안에서 평균했다. sacrebleu 값과 소수점까지 같다고 검증하지는 않았다(미검증). 길이가 짧은 스팬은 높은 n의 n-gram이 없어 그 n을 건너뛰고 평균한다.
- LCS 비율: 공백 제거 후 최장 공통 부분문자열 길이를 두 문자열 중 긴 쪽 길이로 나눈 값.
- 혼합 스크립트: 질문어의 스크립트(en 라틴, zh CJK, th 태국, ru 키릴)와 다른 문자 스크립트가 이름에 하나라도 들어 있으면 해당 스팬은 혼합이다. 숫자, 기호, 구두점은 문자가 아니므로 무시했다. mixed_O_span은 O의 source_text 기준(쌍에 하나라도 있으면 1), mixed_T_span은 T의 translation 기준, mixed_T_questiontext는 T_conditions의 실제 question 문자열 전체 기준이다. 각 질문 문자열 안에 translation이 문자 그대로 들어 있음을 전수 확인했다(예외 0).
- 필드 분해: stem은 question_stem, opt는 A-D. 쌍당 stem 1개, 선택지 평균 약 3.5개(총 stem 1,895, opt 6,669).
- 부분문자열 포함: 공백을 제거한 뒤 두 문자열이 다르면서 한쪽이 다른 쪽에 포함될 때. T_sub는 번역이 화면 이름의 부분문자열, T_super는 번역이 화면 이름을 포함(상위 문자열). 태국어는 띄어쓰기가 없어 모든 언어에 공백 제거를 똑같이 적용했다. 빈 문자열은 없었다.

## 주의사항
T의 혼합 스크립트율은 구조상 거의 100%다. 번역된 이름이 GUI 언어로 질문에 들어가고 모든 칸에서 질문어와 GUI 언어가 다르기 때문이다. 그래서 변별력은 O(원문 이름이 이미 외래 스크립트를 포함하는 비율)에 있다. 번역 실패(untranslated=true)가 232스팬 있고, 이들은 제외하지 않고 그대로 두었다. output_script가 비어 있는 스팬이 54개 있다(원 파일 그대로). 이 파일들은 정답률과 합쳐 보기 전의 입력 기술 통계이며, 결과 해석은 포함하지 않는다.

파일: diag_inputs.py(python3 -I로 실행, 출력은 이 폴더에 쓰고 입력은 읽기만 함), per_pair_features.csv(쌍당 1행, 1,895행), summary_by_gui.csv, summary_by_cell.csv.
