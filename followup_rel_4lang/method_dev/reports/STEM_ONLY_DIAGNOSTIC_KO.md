# Stem-only: R_stem 대응 진단과 남은 실행 ETA

집계 시각: 2026-11-16T11:44:53.952264+00:00. 기존 raw 결과만 분석했다. 새 GPU 추론·inventory 개선·method 변경은 하지 않았다.

**Stem-only의 조작 범위에 맞춘 reference는 R_stem이다.** 같은 Screen20개 item·240쌍에서 Stem-only175정답(72.92%), R_stem185정답(77.08%)이다. 차이는−4.17pp이며95% CI[−11.67,+3.75]pp로0을 포함한다. R 전체80.83%를 Stem-only의 유일한 목표로 놓는 것은 범위를 맞춘 비교가 아니다.

## 1. 동일 문항·동일 조작 범위 확인

| 조건 | Stem | Options | 정답 / 240 | 정확도 |
| --- | --- | --- | ---: | ---: |
| O_current | 원본 | 원본 | 162 | 67.50% |
| Stem-only | 자동 선택적 | 원본 | 175 | 72.92% |
| R_stem | parallel referent | 원본 | 185 | 77.08% |
| Hybrid | 같은 자동 선택적 | 전체 GUI 번역 | 178 | 74.17% |
| R | parallel referent | parallel referent | 194 | 80.83% |
| R_opts | 원본 | parallel referent | 164 | 68.33% |

| 대비 | 차이 | Item bootstrap95% CI | 회복 / 회귀 |
| --- | ---: | --- | ---: |
| Stem-only − R_stem | -4.17pp | [-11.67, +3.75] | 10 / 20 |
| Stem-only − O_current | +5.42pp | [-1.67, +13.33] | 27 / 14 |
| R_stem − O_Rstem_run | +9.17pp | [+4.17, +14.58] | 25 / 3 |
| Hybrid − Stem-only | +1.25pp | [-7.50, +9.58] | 22 / 19 |

R_stem 입력은 고정된 mixed input과 원본 O/annotation을 대조해 stem만 parallel 표현으로 바뀌고 options·이미지·정답이 원본 그대로인지240쌍 전수 검사했다. 기존 Qwen3 R_stem 예측은 이미 있어 재추론하지 않았다. 모델 revision·generation·system은 같지만 과거 RTX4090·batch4·O/R_stem/R_opts/R 혼합 queue와 현재 B200 MIG·batch3·조건별 queue가 다르다.

과거 같은240쌍의 O는163/240(67.92%), 현재 O는162/240(67.50%)이며 label은239/240일치했다. 따라서 gap을 전부 method 차이라고 단정하지 않는다. 모든 CI는 semantic item 단위10,000회 bootstrap이다. Stem-only−O CI는 이전 보고서에도 이미 제시됐으며 여기서 누락 없이 다시 표시했다.

## 2. R_stem 정답·Stem-only 오답20쌍

R_stem이 맞고 Stem-only가 틀린 것은20쌍, 반대는10쌍이다. 아래는 관찰 상태의 상호 배타적 분류이며 인과 원인이나 GUI 대응 정답 판정이 아니다.

| 관찰 상태 | 건수 |
| --- | ---: |
| 편집 적용 후에도 오답 | 11 |
| Inventory 생성 실패 | 1 |
| Source span 누락·경계 차이 | 6 |
| R target exact membership 없음 | 1 |
| 정렬 출력 검증 실패 | 1 |

20쌍 중 **18쌍은 R target 문자열이 이미 inventory에 있었다.** 6쌍의 source 경계 차이 중5쌍은 annotation보다 넓은 span,1쌍은 해당 span 누락이었다. 11쌍은 annotation 경계를 맞췄고 edit도 적용됐지만 다른 inventory 문자열을 골랐다. 이들을 일괄적으로 OCR 실패나 post-grounding reasoning 실패로 부를 수 없다.

### 전체240쌍의 R target lexical availability

| 상태 | Pair |
| --- | ---: |
| exact | 192 |
| not_found_by_lexical_checks | 33 |
| substring_only | 3 |
| inventory_failed_or_empty | 9 |
| ellipsis_prefix_only | 3 |

Normalized exact membership는192/240(80%)다. 부재48쌍 중9쌍은 inventory 실패·빈 목록,3쌍은 더 긴 inventory 문자열 안에 R 표현이 들어 있고3쌍은 ellipsis를 제외한 R prefix가 포함된다. 나머지33쌍도 화면을 보지 않고 OCR 누락이라고 판정하지 않는다. R 표현의 exact 부재와 실제 화면 글자 누락은 다른 지표다.

Inventory에 R 표현이 있는192쌍 중 원문 exact span에서 R 표현으로 치환했거나 원래 동일한 경우는123쌍, 그렇지 않은 것은69쌍이었다. 이 수치는 source 추출·정렬을 함께 거친 reference 일치율이며, 실제 GUI matching precision을 뜻하지 않는다. 완성 질문이 R_stem과 완전히 같은 경우는118쌍이다.

### 화면 문자열만 직접 본 세 사례

- `rel::3/map_6.jpg`, TH: 화면에 `เลือกในแผนที่`가 보이지만 inventory가 구조 repair 후 실패해 빈 목록이다. 실제 visible label을 잃은 사례다.
- `rel::5/forest_2.jpg`, RU: 화면과 inventory에는 `Начинающий плантатор`가 있고 R은 `Начинающий планта...`다. R의 축약 표기 exact match가 없다는 이유로 OCR 누락으로 세면 안 된다.
- `rel::2/map_9.png`, EN: `Avoid Tolls`와 `Avoid Highways`가 모두 화면·inventory에 있다. 자동 method는 후자를, parallel reference는 전자를 쓴 Thai-source 사례가 있다. 기존 `mapping_audit_review.csv`에도 Thai source가 고속도로 회피인데 유료도로 회피에 연결됐다는 mapping_error가 기록돼 있다. 이2개 gap pair를 자동 정렬 오류라고 확정할 수 없다.

이3장만 수동으로 봤으며 전체 missing48쌍의 screenshot audit를 마친 것은 아니다. 기존 mapping_error를 이유로 이번 주 분석에서 새 pair를 제외하지 않았다. Labels/locks도 수정하지 않았다.

## 3. Stem-only와 Hybrid: 순증가3개 뒤의 실제 전환

실행288쌍에서 두 조건의 stem은 모두 동일하다. Main240쌍에서 Hybrid는 Stem-only의 오답22개를 회복하고 정답19개를 잃었다. 따라서 단순히175→178로만 보는 대신 **22회복·19회귀**를 함께 봐야 한다. 정오가 달라진 것은41쌍이고, 출력 label이 달라진 것은44쌍이다. 나머지3쌍은 서로 다른 오답을 냈다.

Hybrid−Stem-only는+1.25pp,95% CI[−7.50,+9.58]pp다. Options 번역의 안정적인 추가 이득이나 불필요함 어느 쪽도 아직 확정하지 않는다. 두 조건의 stem은 동일하지만 options 길이가 달라 batch padding이 달라질 수 있다. 공간 관계 context가 유지되는 장점과 options 의미 보존 문제를 분리해서 봐야 한다.

| GUI | Stem-only | Hybrid | R_stem |
| --- | ---: | ---: | ---: |
| EN | 46/60 (76.67%) | 50/60 (83.33%) | 47/60 (78.33%) |
| ZH | 46/60 (76.67%) | 47/60 (78.33%) | 49/60 (81.67%) |
| TH | 40/60 (66.67%) | 41/60 (68.33%) | 37/60 (61.67%) |
| RU | 43/60 (71.67%) | 40/60 (66.67%) | 52/60 (86.67%) |

RU에서 Stem-only는43/60, Hybrid는40/60이다. Options 전체 번역을 빼면3개를 회복하지만 O46/60에는 여전히 못 미친다. 언어별 on/off 정책을 새로 만들지는 않았다.

## 4. 다음 판단

현재 evidence는 inventory 생성 정확도 개선을 먼저 시작할 근거로 충분하지 않다. R gap20쌍에서 inventory exact 부재는2쌍뿐이고 하나는 R 축약 문제였다. 오히려 inventory 안에서 다른 label을 선택하거나 source span을 넓게 잡은 사례를 먼저 검토하는 것이 직접적이다. 일부 parallel mapping 자체도 문제여서 R을 실제 화면 대응의 절대 정답으로 쓰지 않는다. −4.17pp의 구간이0을 포함한다는 사실도 R_stem과 동등하거나 비열등하다는 검증은 아니다.

지금은 Stem-only와 Hybrid를 고정해 아직 v2로 평가하지 않은 Selection에서 재확인할 수 있다. 다만 전체158 item은 역사적으로 이미 관찰된 development cohort이고 Internal도 독립적인 최종 confirmatory test가 아니다. 이번 진단에 맞춰 threshold/prompt를 바꾸면 새 개발 버전과 관찰 이력을 기록해야 한다.

## 5. 나머지 샘플 ETA

**아래는 현재 B200 MIG45GB, BF16 SDPA, method batch1·VLM batch3에서 측정한 시간에 근거한 추정이다.** 실행을 시작한 것이 아니다. 잔여 development는 Selection20문항240쌍 + Internal118문항1,416쌍 =138문항1,656쌍, 새 image552개·source MCQ552개다. Selection의 사전 제외1쌍은 실행에는 포함하고 primary에서 분리한다.

| 범위 | Stem-only + O | Stem-only + Hybrid + O | 기존8조건 + Stem-only + O |
| --- | ---: | ---: | ---: |
| Selection20 | 약0.8h (여유25%: 0.9h) | 약1.0h (여유25%: 1.2h) | 약2.0h (여유25%: 2.5h) |
| Internal118 | 약4.0h (여유25%: 5.0h) | 약5.3h (여유25%: 6.7h) | 약11.6h (여유25%: 14.5h) |
| 나머지138문항 전체 | 약4.8h (여유25%: 6.0h) | 약6.3h (여유25%: 7.9h) | 약13.6h (여유25%: 17.1h) |
| 전체366문항까지 추가분·단순 외삽 | 약11.4h (여유25%: 14.2h) | 약15.2h (여유25%: 19.0h) | 약33.3h (여유25%: 41.7h) |

**현재 기본 실행기를 그대로 재개하는 것은 기존8조건+O의 전체 grid**다. Stem-only downstream은 나중에 별도 추가하므로 우측은총10조건 비용이다. 좌측의 최소 실행은 Options Full 호출 자체를 생략하는 작은 실행 adapter가 필요하며 아직 실행 명령을 준비하거나 시작하지 않았다. 현재 Stem-only builder는 완료된 Hybrid stem을 재사용하므로 그대로 end-to-end 단독 실행하면 이 절감분이 자동으로 생기는 것은 아니다. 두 후보 실행은 inventory·stem 추출/정렬을 공유하고 Hybrid용 Full options를1회만 생성하는 계획이다.

| 나머지138문항 계획 | 추가 VLM 예측 행 |
| --- | ---: |
| Stem-only + O | 3,312 |
| Stem-only + Hybrid + O | 4,968 |
| 기존8조건 + Stem-only + O | 16,560 |

### 시간 산식과 한계

```json
{
  "inventory_seconds_per_image": 22.16986217905069,
  "stem_extract_seconds_per_source": 1.2092010437045246,
  "stem_align_seconds_per_pair": 0.6841788001164484,
  "full_gui_seconds_per_pair": 2.8367323811282406,
  "stem_infer_seconds_per_pair": 0.7778860291162144,
  "O_infer_seconds_per_pair": 0.7456508980507756,
  "hybrid_infer_seconds_per_pair": 0.5167823607852269,
  "full_grid_inventory_wall_seconds_per_image": 20.467747197479184,
  "full_grid_extract_wall_seconds_per_source": 4.176717006412218,
  "full_grid_stem_extract_wall_seconds_per_source": 1.2814521000764216,
  "full_grid_rewrite_wall_seconds_per_pair": 14.709738784628119,
  "full_grid_infer_seconds_per_pair": 5.1696523400379295
}
```

Inventory는 Screen main80장 중 모든 initial/repair 호출 runtime을 합쳐 image당 평균을 구했다. Stem extraction은 고유 source80개, alignment/Full은 main240쌍에서 payload hash별 호출을 한 번만 셌다. Cache hit도 그 payload를 독립 실행할 때 필요한 측정 runtime으로 한 번 포함해 공유 호출 비용을0으로 오인하지 않았다. VLM 시간은 batch마다 한 번만 합산하고288개 실행 pair로 나눴다. 전체 grid는 기존 Screen 단계별 wall을 scale했다. Cold-load/프로세스·보고서 여유는 remaining cohort당5분으로 별도 더했다.

25%는 통계적 신뢰구간이나 최대시간 보장이 아니라 일정 여유다. 다른 화면 밀도·텍스트 길이·repair 비율·서버 자원 경합·OOM 중단에 따라 더 걸릴 수 있다. 주로 inventory가 시간을 지배하며 더 넓은 데이터의 latency는 아직 실제 측정하지 않았다. 같은 장비 기준이며 RTX4090 속도로 환산하지 않는다.

366문항 전체는12방향 기준4,392pair다. 이미 main240+legacy pilot48=288pair를 처리했으므로 추가는4,104pair, 새 image/source는각1,336개다. 366−20=346문항×12를 그대로 추가로 세면 이미 처리한pilot48pair를 중복 계산한다. 366 확장은 현재 범위 밖이고 새 입력·분모·어댑터 준비가 필요하므로 위 시간은 compute 외삽만이다.

재현: `.venv/bin/python followup_rel_4lang/method_dev/scripts/diagnose_stem_only.py`. [집계·원시 대응 snapshot](../artifacts/stem_only_diagnostic_snapshot.json). 기존 결과를 재추론하거나 수정하지 않는다.

## 부록: R_stem 정답·Stem-only 오답20쌍

| Pair | 관찰 상태 | R target | 실제 치환 |
| --- | --- | --- | --- |
| rel::2/map_9.png::th::en | 편집 적용 후에도 오답 | Avoid Tolls | เลี่ยงทางหลวง → Avoid Highways |
| rel::2/map_9.png::th::ru | 편집 적용 후에도 오답 | Избегать платных дорог | เลี่ยงทางหลวง → Избегать автомагистралей |
| rel::2/setting_3.png::en::ru | 편집 적용 후에도 오답 | Написание | Handwrite → написать от руки |
| rel::2/setting_3.png::th::ru | 편집 적용 후에도 오답 | Написание | เขียนข้อความ → Вставка |
| rel::2/setting_3.png::th::zh | 편집 적용 후에도 오답 | 手写 | เขียนข้อความ → 插入 |
| rel::2/setting_3.png::zh::ru | 편집 적용 후에도 오답 | Написание | 手写 → написать от руки |
| rel::3/map_6.jpg::zh::th | Inventory 생성 실패 | เลือกในแผนที่ | 없음 |
| rel::4/google_play_8.jpg::th::ru | Source span 누락·경계 차이 | Использовать данные о местоположении устройства | เมนูการตั้งค่า → Настройки аккаунта и устройства |
| rel::5/forest_2.jpg::zh::ru | R target exact membership 없음 | Начинающий планта... | 없음 |
| rel::5/record_2.jpg::th::en | 편집 적용 후에도 오답 | Set as alarm ringtone | ตั้งเป็นเสียงเรียกเข้า → Set as call ringtone |
| rel::5/record_2.jpg::th::ru | 정렬 출력 검증 실패 | Задать как сигнал будильника | 없음 |
| rel::5/record_2.jpg::th::zh | 편집 적용 후에도 오답 | 设为闹钟铃声 | ตั้งเป็นเสียงเรียกเข้า → 设为联系人铃声 |
| rel::6/camera_8.jpg::en::th | Source span 누락·경계 차이 | รูปภาพ | PHOTO mode → ภาพถ่ายบุคคล |
| rel::6/camera_8.jpg::ru::th | 편집 적용 후에도 오답 | รูปภาพ | ФОТО → ภาพถ่ายบุคคล |
| rel::6/camera_8.jpg::th::zh | Source span 누락·경계 차이 | 照片 | โหมด "รูปภาพ" → 视频 |
| rel::6/wallet_6.jpg::en::ru | 편집 적용 후에도 오답 | Скоро | Nearby → Назад |
| rel::6/wallet_6.jpg::th::en | Source span 누락·경계 차이 | Nearby | ป้าย 'ใกล้เคียง' → Nearby |
| rel::6/wallet_6.jpg::th::ru | Source span 누락·경계 차이 | Скоро | ป้าย 'ใกล้เคียง' → Транспортная карта |
| rel::6/wallet_6.jpg::th::zh | Source span 누락·경계 차이 | 附近 | ป้าย 'ใกล้เคียง' → 附近 |
| rel::6/wallet_6.jpg::zh::ru | 편집 적용 후에도 오답 | Скоро | 附近 → Транспортная карта |

## 부록: Hybrid와 Stem-only 정오가 다른41쌍

원문·변환 MCQ와 모든 options의 before/after는 snapshot에 있다. 아래는 실제 전환을 놓치지 않기 위한 목록이다. 의미 오류로 자동 판정한 것은 아니다.

| Pair | Stem-only label | Hybrid label | Gold | Hybrid 기준 전환 |
| --- | --- | --- | --- | --- |
| rel::2/calendar_6.png::en::th | C | B | B | 회복 |
| rel::2/map_9.png::ru::th | A | B | A | 회귀 |
| rel::2/map_9.png::th::zh | A | B | A | 회귀 |
| rel::2/note_8.png::en::th | D | A | A | 회복 |
| rel::2/note_8.png::ru::th | D | A | A | 회복 |
| rel::2/note_8.png::zh::th | D | A | A | 회복 |
| rel::2/setting_3.png::ru::en | B | A | A | 회복 |
| rel::2/setting_3.png::ru::th | B | A | A | 회복 |
| rel::2/setting_3.png::th::en | B | A | A | 회복 |
| rel::2/setting_3.png::zh::en | B | A | A | 회복 |
| rel::2/setting_3.png::zh::th | A | C | A | 회귀 |
| rel::3/homescreen_5.jpg::en::zh | C | B | B | 회복 |
| rel::3/map_4.jpg::en::th | D | C | C | 회복 |
| rel::3/map_4.jpg::zh::ru | D | C | C | 회복 |
| rel::3/map_4.jpg::zh::th | D | C | C | 회복 |
| rel::3/map_6.jpg::zh::th | A | B | B | 회복 |
| rel::3/music_10.jpg::zh::ru | A | C | A | 회귀 |
| rel::3/music_3.jpg::en::th | C | B | C | 회귀 |
| rel::3/music_3.jpg::ru::en | C | B | C | 회귀 |
| rel::3/music_3.jpg::ru::th | C | B | C | 회귀 |
| rel::3/music_3.jpg::th::ru | C | B | C | 회귀 |
| rel::4/google_play_8.jpg::en::zh | B | A | A | 회복 |
| rel::4/google_play_8.jpg::ru::th | B | A | A | 회복 |
| rel::4/google_play_8.jpg::zh::en | B | A | A | 회복 |
| rel::4/google_play_8.jpg::zh::ru | B | A | A | 회복 |
| rel::4/google_play_8.jpg::zh::th | B | A | A | 회복 |
| rel::5/forest_2.jpg::en::ru | B | C | B | 회귀 |
| rel::5/forest_2.jpg::ru::en | C | B | B | 회복 |
| rel::5/forest_2.jpg::ru::th | B | C | B | 회귀 |
| rel::5/forest_2.jpg::zh::th | B | C | B | 회귀 |
| rel::5/phone_4.jpg::ru::th | C | A | A | 회복 |
| rel::5/phone_4.jpg::zh::ru | A | D | A | 회귀 |
| rel::5/phone_4.jpg::zh::th | C | A | A | 회복 |
| rel::5/record_2.jpg::en::th | C | B | C | 회귀 |
| rel::5/record_2.jpg::ru::th | C | B | C | 회귀 |
| rel::5/record_2.jpg::zh::th | C | B | C | 회귀 |
| rel::6/wallet_6.jpg::en::ru | A | B | B | 회복 |
| rel::6/wallet_8.jpg::en::th | C | B | C | 회귀 |
| rel::6/wallet_8.jpg::th::ru | C | D | C | 회귀 |
| rel::6/wallet_8.jpg::zh::ru | C | B | C | 회귀 |
| rel::6/wallet_8.jpg::zh::th | C | B | C | 회귀 |
