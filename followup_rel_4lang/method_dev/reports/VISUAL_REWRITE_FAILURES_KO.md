# Screenshot 직접 rewrite: 수정 전 실패 분석

Main20개 semantic item·240쌍, 이전 조건171정답·69오답. 기존 예측과 원시 출력만 읽었다. 생성·fallback 규칙을 소급 변경하지 않았다.

| 정오 | 문맥 호환 | 문맥 경고 | 합계 |
| --- | ---: | ---: | ---: |
| 정답 | 50 | 121 | 171 |
| 오답 | 16 | 53 | 69 |

문맥 호환은 source annotation 바깥의 문자를 보존했을 가능성을 뜻한다. 올바른 target label을 고른 증거가 아니다. 공백·구두점·대소문자 차이는 허용했다. Annotation 누락도 경고를 만들 수 있어 이 표를 의미 오류율이나 인과적 오답 분해로 해석하지 않는다.

| Source | O 정답 | 이전 rewrite 정답 | R 정답 | 문맥 경고 | O→rewrite 회귀 |
| --- | ---: | ---: | ---: | ---: | ---: |
| EN | 40/60 | 47/60 | 52/60 | 4/60 | 2 |
| ZH | 42/60 | 40/60 | 48/60 | 53/60 | 9 |
| TH | 41/60 | 43/60 | 46/60 | 57/60 | 7 |
| RU | 39/60 | 41/60 | 48/60 | 60/60 | 6 |

R이 맞히고 이전 rewrite가 틀린 것은 37쌍이다. 이 중 문맥 경고 29쌍, 문맥 호환 8쌍이다. 전체 오답69쌍 중 숫자 변화 2쌍, 보기 중복 3쌍이다. 이 분류는 서로 배타적인 오류 원인 분해가 아니다.

## 실제 출력에서 확인한 문제

1. **문맥 통번역:** 비영어 원문의 질문 문맥을 GUI 언어로 바꾼다. 정답에서도 많이 발생하므로 정확도만으로 selective 규칙 준수를 검증할 수 없다.
2. **기준 요소 정체성 변경:** `note_1` EN→TH에서 Draw with Finger를 Auto-minimize에 해당하는 화면의 위쪽 행 이름으로 바꿨다. Screenshot을 직접 확인하면 Auto-minimize·Draw with Finger·Pencil Settings 순으로 별개 행이다. 위치 관계로 답을 찾는 작업과 원래 이름의 대응을 찾는 작업이 섞일 수 있다.
3. **달력 값 변경:** `calendar_6` EN→TH에서 Thursday를 พุธ.(Wednesday)로, Tuesday를 จันทร์(Monday)로 바꿨다. 숫자가 없어 digit 검사로 잡히지 않으며 source span 내부라 문맥 검사도 통과한다. 날짜·요일 identity 보존이 필요하다. 다만 병렬 GUI 화면 자체의 날짜 차이는 데이터 검토와 구별해야 한다.
4. **실제 데이터 대응 오류:** `map_9` Thai source의 เลี่ยงทางหลวง는 Avoid Highways를 뜻하나, 기존 mapping audit에는 Avoid Tolls 자리에 들어간 `mapping_error`로 이미 기록돼 있다. TH→EN/RU/ZH의 3쌍은 reference와의 불일치만으로 새 방법의 오역으로 단정할 수 없다. 원문·GT를 고치거나 이 3쌍을 분모에서 빼지 않았다.
5. **정상 수정 후 남은 실패:** 문맥 호환 오답16쌍에는 잘못된 referent 대응과 실제 downstream REL 실패가 섞일 수 있다. 모든 오답을 문맥 번역 탓으로 돌리거나, R의 정답을 실제 화면 label의 oracle로 간주하지 않는다.

6. **번역만으로 설명되지 않는 공통 실패:** `music_3`은 O·R·F·이전 직접 rewrite 모두 0/12다. EN→ZH 생성은 화면의 #1 共5首歌와 #3 共4首歌를 대응시켰고, 화면에서도 #3이 #1 위에 놓여 있다. `wallet_8`도 R·F가 0/12다. 이 두 문항의 이전 오답22쌍을 모두 localization 실패로 셀 수는 없다. Downstream의 공간 관계 처리나 데이터/프롬프트 해석을 따로 검토해야 하며, 이번에는 정답/문항을 수정하지 않는다.

## 문항별 반복 실패

| Semantic item | O | 이전 rewrite | R | F | Inventory 통합 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `rel::2/calendar_6.png` | 11/12 | 11/12 | 12/12 | 12/12 | 11/12 |
| `rel::2/map_9.png` | 9/12 | 8/12 | 9/12 | 9/12 | 7/12 |
| `rel::2/note_1.png` | 11/12 | 9/12 | 12/12 | 12/12 | 12/12 |
| `rel::2/note_8.png` | 9/12 | 11/12 | 12/12 | 12/12 | 9/12 |
| `rel::2/setting_3.png` | 5/12 | 10/12 | 10/12 | 9/12 | 9/12 |
| `rel::3/homescreen_3.jpg` | 9/12 | 9/12 | 12/12 | 12/12 | 10/12 |
| `rel::3/homescreen_5.jpg` | 4/12 | 9/12 | 11/12 | 12/12 | 7/12 |
| `rel::3/map_4.jpg` | 10/12 | 8/12 | 12/12 | 12/12 | 12/12 |
| `rel::3/map_6.jpg` | 11/12 | 12/12 | 12/12 | 12/12 | 11/12 |
| `rel::3/music_10.jpg` | 12/12 | 11/12 | 12/12 | 12/12 | 12/12 |
| `rel::3/music_3.jpg` | 0/12 | 0/12 | 0/12 | 0/12 | 1/12 |
| `rel::4/google_play_6.jpg` | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |
| `rel::4/google_play_8.jpg` | 5/12 | 9/12 | 8/12 | 12/12 | 11/12 |
| `rel::5/forest_2.jpg` | 6/12 | 10/12 | 6/12 | 6/12 | 5/12 |
| `rel::5/message_2.jpg` | 9/12 | 9/12 | 12/12 | 9/12 | 12/12 |
| `rel::5/phone_4.jpg` | 10/12 | 10/12 | 11/12 | 12/12 | 11/12 |
| `rel::5/record_2.jpg` | 5/12 | 6/12 | 9/12 | 9/12 | 7/12 |
| `rel::6/camera_8.jpg` | 12/12 | 9/12 | 11/12 | 9/12 | 10/12 |
| `rel::6/wallet_6.jpg` | 8/12 | 6/12 | 11/12 | 9/12 | 7/12 |
| `rel::6/wallet_8.jpg` | 4/12 | 2/12 | 0/12 | 0/12 | 3/12 |

같은 semantic item의12방향은 독립 문항12개가 아니다. 특정 문항에 몰린 실패와 언어쌍 전반의 실패를 구별하기 위한 표다.

## 이번 수정으로 검증하는 범위

원문 복사·비영어 예시·같은 요소 identity·요일 보존 지시를 한 프롬프트에 고정했다. Gold 기반 validator나 추가 모델은 넣지 않았다. 따라서 결과는 이 prompt bundle의 효과이며 각 문장/예시의 개별 효과를 분리하지 않는다. 모든 fallback을 포함한 정확도와 수정 coverage를 함께 평가한다.

## 전체 오답69쌍

| Pair | GT | O | 이전 rewrite | R | 문맥 경고 field | 숫자 | 중복 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `rel::2/calendar_6.png::en::th` | B | 오답 | 오답 | 정답 | 없음 | - | - |
| `rel::2/map_9.png::ru::th` | A | 오답 | 오답 | 오답 | question_stem | - | - |
| `rel::2/map_9.png::th::en` | A | 정답 | 오답 | 정답 | question_stem | - | - |
| `rel::2/map_9.png::th::ru` | A | 정답 | 오답 | 정답 | question_stem | - | - |
| `rel::2/map_9.png::th::zh` | A | 정답 | 오답 | 정답 | question_stem | - | - |
| `rel::2/note_1.png::en::th` | A | 정답 | 오답 | 정답 | 없음 | - | - |
| `rel::2/note_1.png::ru::th` | A | 오답 | 오답 | 정답 | question_stem, C, D | - | - |
| `rel::2/note_1.png::zh::th` | A | 정답 | 오답 | 정답 | B | - | - |
| `rel::2/note_8.png::ru::th` | A | 오답 | 오답 | 정답 | question_stem, D | - | - |
| `rel::2/setting_3.png::en::th` | A | 오답 | 오답 | 정답 | 없음 | - | - |
| `rel::2/setting_3.png::zh::th` | A | 정답 | 오답 | 오답 | 없음 | - | - |
| `rel::3/homescreen_3.jpg::ru::th` | B | 오답 | 오답 | 정답 | question_stem | - | - |
| `rel::3/homescreen_3.jpg::zh::ru` | B | 정답 | 오답 | 정답 | question_stem | - | - |
| `rel::3/homescreen_3.jpg::zh::th` | B | 오답 | 오답 | 정답 | question_stem | - | - |
| `rel::3/homescreen_5.jpg::en::th` | B | 오답 | 오답 | 정답 | 없음 | - | - |
| `rel::3/homescreen_5.jpg::th::zh` | B | 오답 | 오답 | 오답 | question_stem | - | - |
| `rel::3/homescreen_5.jpg::zh::th` | B | 오답 | 오답 | 정답 | question_stem | - | - |
| `rel::3/map_4.jpg::en::ru` | C | 정답 | 오답 | 정답 | 없음 | - | yes |
| `rel::3/map_4.jpg::ru::th` | C | 정답 | 오답 | 정답 | question_stem | - | - |
| `rel::3/map_4.jpg::zh::ru` | C | 오답 | 오답 | 정답 | question_stem | - | yes |
| `rel::3/map_4.jpg::zh::th` | C | 정답 | 오답 | 정답 | question_stem | - | - |
| `rel::3/music_10.jpg::zh::th` | A | 정답 | 오답 | 정답 | 없음 | - | - |
| `rel::3/music_3.jpg::en::ru` | C | 오답 | 오답 | 오답 | 없음 | - | - |
| `rel::3/music_3.jpg::en::th` | C | 오답 | 오답 | 오답 | 없음 | - | - |
| `rel::3/music_3.jpg::en::zh` | C | 오답 | 오답 | 오답 | 없음 | - | - |
| `rel::3/music_3.jpg::ru::en` | C | 오답 | 오답 | 오답 | question_stem | - | - |
| `rel::3/music_3.jpg::ru::th` | C | 오답 | 오답 | 오답 | question_stem | - | - |
| `rel::3/music_3.jpg::ru::zh` | C | 오답 | 오답 | 오답 | question_stem | - | - |
| `rel::3/music_3.jpg::th::en` | C | 오답 | 오답 | 오답 | question_stem | - | - |
| `rel::3/music_3.jpg::th::ru` | C | 오답 | 오답 | 오답 | question_stem | - | - |
| `rel::3/music_3.jpg::th::zh` | C | 오답 | 오답 | 오답 | question_stem | - | - |
| `rel::3/music_3.jpg::zh::en` | C | 오답 | 오답 | 오답 | question_stem | - | - |
| `rel::3/music_3.jpg::zh::ru` | C | 오답 | 오답 | 오답 | question_stem | - | - |
| `rel::3/music_3.jpg::zh::th` | C | 오답 | 오답 | 오답 | 없음 | - | - |
| `rel::4/google_play_8.jpg::ru::th` | A | 오답 | 오답 | 정답 | question_stem | - | - |
| `rel::4/google_play_8.jpg::th::zh` | A | 정답 | 오답 | 오답 | question_stem | - | - |
| `rel::4/google_play_8.jpg::zh::th` | A | 오답 | 오답 | 오답 | question_stem | - | - |
| `rel::5/forest_2.jpg::th::ru` | B | 오답 | 오답 | 오답 | question_stem, A, B, C, D | D | - |
| `rel::5/forest_2.jpg::zh::ru` | B | 오답 | 오답 | 정답 | question_stem, A, B, C, D | D | - |
| `rel::5/message_2.jpg::en::th` | C | 오답 | 오답 | 정답 | 없음 | - | - |
| `rel::5/message_2.jpg::ru::th` | C | 오답 | 오답 | 정답 | question_stem | - | - |
| `rel::5/message_2.jpg::zh::th` | C | 정답 | 오답 | 정답 | question_stem | - | - |
| `rel::5/phone_4.jpg::th::ru` | A | 정답 | 오답 | 정답 | 없음 | - | - |
| `rel::5/phone_4.jpg::zh::th` | A | 오답 | 오답 | 정답 | question_stem | - | yes |
| `rel::5/record_2.jpg::en::th` | C | 오답 | 오답 | 오답 | 없음 | - | - |
| `rel::5/record_2.jpg::ru::th` | C | 오답 | 오답 | 오답 | question_stem | - | - |
| `rel::5/record_2.jpg::th::en` | C | 오답 | 오답 | 정답 | question_stem | - | - |
| `rel::5/record_2.jpg::th::ru` | C | 오답 | 오답 | 정답 | question_stem | - | - |
| `rel::5/record_2.jpg::th::zh` | C | 오답 | 오답 | 정답 | question_stem | - | - |
| `rel::5/record_2.jpg::zh::th` | C | 오답 | 오답 | 오답 | question_stem | - | - |
| `rel::6/camera_8.jpg::ru::th` | A | 정답 | 오답 | 정답 | question_stem | - | - |
| `rel::6/camera_8.jpg::ru::zh` | A | 정답 | 오답 | 정답 | question_stem | - | - |
| `rel::6/camera_8.jpg::th::zh` | A | 정답 | 오답 | 오답 | question_stem | - | - |
| `rel::6/wallet_6.jpg::en::ru` | B | 오답 | 오답 | 정답 | D | - | - |
| `rel::6/wallet_6.jpg::ru::en` | B | 정답 | 오답 | 정답 | question_stem, A | - | - |
| `rel::6/wallet_6.jpg::ru::th` | B | 정답 | 오답 | 정답 | question_stem, A | - | - |
| `rel::6/wallet_6.jpg::ru::zh` | B | 정답 | 오답 | 정답 | question_stem, A | - | - |
| `rel::6/wallet_6.jpg::th::zh` | B | 정답 | 오답 | 정답 | question_stem, A, D | - | - |
| `rel::6/wallet_6.jpg::zh::ru` | B | 정답 | 오답 | 정답 | D | - | - |
| `rel::6/wallet_8.jpg::en::ru` | C | 오답 | 오답 | 오답 | 없음 | - | - |
| `rel::6/wallet_8.jpg::en::zh` | C | 오답 | 오답 | 오답 | 없음 | - | - |
| `rel::6/wallet_8.jpg::ru::en` | C | 오답 | 오답 | 오답 | question_stem, A, B, C, D | - | - |
| `rel::6/wallet_8.jpg::ru::th` | C | 오답 | 오답 | 오답 | question_stem, A, B, C, D | - | - |
| `rel::6/wallet_8.jpg::ru::zh` | C | 오답 | 오답 | 오답 | question_stem, A, B, C, D | - | - |
| `rel::6/wallet_8.jpg::th::en` | C | 오답 | 오답 | 오답 | question_stem, A, B, C, D | - | - |
| `rel::6/wallet_8.jpg::th::zh` | C | 오답 | 오답 | 오답 | question_stem, A, B, C, D | - | - |
| `rel::6/wallet_8.jpg::zh::en` | C | 오답 | 오답 | 오답 | question_stem, A, B, C, D | - | - |
| `rel::6/wallet_8.jpg::zh::ru` | C | 정답 | 오답 | 오답 | question_stem, A, B, C, D | - | - |
| `rel::6/wallet_8.jpg::zh::th` | C | 정답 | 오답 | 오답 | question_stem, A, B, C, D | - | - |

[69쌍의 원문과 생성문 전체](VISUAL_REWRITE_FAILURE_CASES_KO.md). 조건별 전체288쌍 label은 [기존 표](VISUAL_SELECTIVE_REWRITE_CASES_KO.md)에 있다.
