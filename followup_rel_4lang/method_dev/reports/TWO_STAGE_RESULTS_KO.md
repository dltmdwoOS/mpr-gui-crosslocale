# Two-stage 재정비 실험 중간 결산

집계 시각: 2026-11-16T09:29:26.566461+00:00. 실행: `followup_rel_4lang/method_dev/artifacts/two_stage_v2_hybrid`. 실행 중인 코드·config·캐시·출력 파일을 변경하거나 GPU 추론을 추가하지 않았다.

**번역·변환 완료와 문제 풀이 완료를 구분한다.** 현재 pipeline은 각 cohort에서 모든 조건의 변환이 끝난 뒤 O와 각 조건의 VLM 문제 풀이를 수행한다. 아래 정확도는 전체 paired 출력이 완성된 조건에서만 표시한다.

## 진행 상태

| Cohort | 조건 | 변환 | 문제 풀이 출력 |
| --- | --- | ---: | ---: |
| screen | TS_FULL_GUI | 288/288 | 0/288 |
| screen | TS_FULL_TXT | 288/288 | 0/288 |
| screen | TS_SEL_GUI_AUTO | 288/288 | 0/288 |
| screen | TS_SEL_TXT_AUTO | 5/288 | 0/288 |
| screen | TS_SEL_GUI_ORACLE | 0/288 | 0/288 |
| screen | TS_SEL_TXT_ORACLE | 0/288 | 0/288 |
| screen | TS_QSEL_OFULL_GUI_AUTO | 0/288 | 0/288 |
| screen | TS_QSEL_OFULL_TXT_AUTO | 0/288 | 0/288 |
| selection | TS_FULL_GUI | 0/240 | 0/240 |
| selection | TS_FULL_TXT | 0/240 | 0/240 |
| selection | TS_SEL_GUI_AUTO | 0/240 | 0/240 |
| selection | TS_SEL_TXT_AUTO | 0/240 | 0/240 |
| selection | TS_SEL_GUI_ORACLE | 0/240 | 0/240 |
| selection | TS_SEL_TXT_ORACLE | 0/240 | 0/240 |
| selection | TS_QSEL_OFULL_GUI_AUTO | 0/240 | 0/240 |
| selection | TS_QSEL_OFULL_TXT_AUTO | 0/240 | 0/240 |
| internal_evaluation | TS_FULL_GUI | 0/1416 | 0/1416 |
| internal_evaluation | TS_FULL_TXT | 0/1416 | 0/1416 |
| internal_evaluation | TS_SEL_GUI_AUTO | 0/1416 | 0/1416 |
| internal_evaluation | TS_SEL_TXT_AUTO | 0/1416 | 0/1416 |
| internal_evaluation | TS_SEL_GUI_ORACLE | 0/1416 | 0/1416 |
| internal_evaluation | TS_SEL_TXT_ORACLE | 0/1416 | 0/1416 |
| internal_evaluation | TS_QSEL_OFULL_GUI_AUTO | 0/1416 | 0/1416 |
| internal_evaluation | TS_QSEL_OFULL_TXT_AUTO | 0/1416 | 0/1416 |

**아직 완료된 downstream 정확도는 없다.** 번역 파일의 `status=success`는 JSON·변환 검증 결과이며 REL 정답을 맞혔다는 뜻이 아니다. 과거 O/R/T/F 예측을 대신 붙여 새 정확도를 만들지 않았다.

## screen: 완료 단계 비용

| 단계 | 출력 수 | Wall·분 |
| --- | ---: | ---: |
| inventory | 128 | 43.66 |
| extract | 128 | 8.91 |
| extract_stem | 128 | 2.73 |

## screen: Inventory

| 범위 | 고유 이미지 | 성공 | repair 시도 | repair 후 회복 | 최종 실패 | 실패 evidence를 받는 pair |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 128 | 125 | 13 | 10 | 3 | 9 |
| main | 80 | 77 | 6 | 3 | 3 | 9 |
| pilot | 48 | 48 | 7 | 7 | 0 | 0 |

실패 image는 삭제하지 않고 빈 inventory로 포함한다. Full GUI는 이 경우 일반 번역을 수행할 수 있으므로 변환 성공과 GUI evidence 사용 성공이 다르다. OCR 문자열 내용의 정확도는 이번 집계에서 독립 검수하지 않았다.

- `rel::3/homescreen_5.jpg` / GUI en: invalid_json:Expecting value

- `rel::3/map_6.jpg` / GUI th: invalid_json:Unterminated string starting at

- `rel::4/google_play_6.jpg` / GUI zh: invalid_json:Unterminated string starting at

## screen: 전체 필드 추출 vs stem-only

| 범위 | 고유 source MCQ | 전체 필드 실패 | Stem-only 실패 | 실패→성공 | 성공→실패 |
| --- | ---: | ---: | ---: | ---: | ---: |
| all | 128 | 15 | 1 | 15 | 1 |
| main | 80 | 6 | 1 | 6 | 1 |
| pilot | 48 | 9 | 0 | 9 | 0 |

### Main의 stem source-span 품질

| 추출 방식 | Precision | Recall | F1 | 유효하지만 stem ref 없음 |
| --- | ---: | ---: | ---: | ---: |
| all_fields | 92.59% | 62.50% | 74.63% | 20 |
| stem_only | 81.01% | 80.00% | 80.50% | 0 |

기존 main 실패 6개 중 options field만 검증 실패한 것은 2개다. 전체 필드 추출 실패를 모두 options 때문이라고 보지는 않는다. 이는 parser/span 검증 실패의 분류이며 형식이 유효한 options의 의미 오류까지 분해한 결과는 아니다. Stem-only는 실패를 줄이고 recall을 올렸지만 annotation과 일치하지 않는 추가 경계도 늘었다. 이는 source annotation의 exact span 경계 지표이며 GUI 대응 정답률이 아니다. 실패 응답은 실제 pipeline처럼 빈 추출로 취급하므로 모델의 raw 추출 능력뿐 아니라 검증 정책의 영향도 포함한다.

MCQ 단위는 (semantic item, source language)로 dedup했다. Main은 같은 source가 세 GUI로 반복되므로 pair 240개를 독립 source 240개로 세지 않는다. 기존 전체 필드와 stem-only는 prompt/scope가 달라진 pipeline 비교이며 단일 오류 유형의 순수 인과 효과가 아니다.

## screen: TS_FULL_GUI 변환 완료

| 범위 | N | 구조상 성공 | 구조 repair | 의미 repair 시도 | 의미 repair 채택 | 잔여 의미 경고 pair | 숫자 등 진단 pair |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 288 | 288 | 0 | 21 | 14 | 9 | 7 |
| main | 240 | 240 | 0 | 16 | 11 | 7 | 4 |
| pilot | 48 | 48 | 0 | 5 | 3 | 2 | 3 |

| Main GUI | N | 의미 repair | 잔여 의미 경고 |
| --- | ---: | ---: | ---: |
| en | 60 | 0 | 0 |
| ru | 60 | 1 | 1 |
| th | 60 | 14 | 5 |
| zh | 60 | 1 | 1 |

구조상 성공은 의미 보존을 보장하지 않는다. 의미 repair 채택은 자동 점수가 낮아졌다는 뜻이며 경고가 모두 사라졌다는 뜻은 아니다. 잔여 경고는 자동 휴리스틱이며, DND 같은 acronym 유지가 정당한 경우도 포함할 수 있다. 숫자 token 차이 역시 실제 GUI label 변화인지 번역 오류인지 별도 확인해야 한다.

### 검토할 원문/번역 사례

- `rel::2/calendar_6.png::ru::th`: number_tokens_changed:A:['10']->['9']

```text
Source: Какой день недели запланировано событие и каково его относительное положение по сравнению с "Чт, 12"?
Target: วันในสัปดาห์ใดที่มีเหตุการณ์ที่วางแผนไว้ และมันอยู่ในตำแหน่งสัมพัทธ์อย่างไรเมื่อเทียบกับ "พ. 12"?
```

```text
A source: "Вт, 10", за один день до
A target: "จ. 9", หนึ่งวันก่อน
```

- `rel::2/note_8.png::en::th`: quoted_gui_label_may_be_untranslated:customize

```text
Source: Which element is located directly to the right of the 'Customize' option in the customization menu?
Target: องค์ประกอบใดอยู่ด้านขวาของตัวเลือก 'Customize' ในเมนูการปรับแต่ง?
```

- `rel::2/setting_3.png::en::th`: quoted_gui_label_may_be_untranslated:handwrite

```text
Source: Which element is located directly to the right of the 'Handwrite' button?
Target: องค์ประกอบใดอยู่ด้านขวาของปุ่ม 'Handwrite'?
```

- `rel::3/homescreen_5.jpg::en::ru`: quoted_gui_label_may_be_untranslated:dnd

```text
Source: Which element is directly below the 'DND' option in the mobile UI interface?
Target: Какой элемент находится непосредственно ниже опции 'DND' в интерфейсе мобильного приложения?
```

- `rel::3/homescreen_5.jpg::en::th`: quoted_gui_label_may_be_untranslated:dnd

```text
Source: Which element is directly below the 'DND' option in the mobile UI interface?
Target: องค์ประกอบใดอยู่ตรงด้านล่างของตัวเลือก 'DND' ในอินเทอร์เฟซ UI ของมือถือ?
```

- `rel::3/homescreen_5.jpg::en::zh`: quoted_gui_label_may_be_untranslated:dnd

```text
Source: Which element is directly below the 'DND' option in the mobile UI interface?
Target: 在移动界面中，'DND'选项直接下方的元素是什么？
```

- `rel::3/map_6.jpg::en::th`: quoted_gui_label_may_be_untranslated:choose on map

```text
Source: What is immediately to the right of the 'Choose on map' button?
Target: อะไรอยู่ทางขวาของปุ่ม 'Choose on map' ทันที
```

- `rel::3/music_3.jpg::en::th`: spatial_opposition_introduced, spatial_core_relation_missing:above

```text
Source: Which playlist is located directly above '#1 Total 5 songs'?
Target: รายการเพลิงใดอยู่ตรงข้ามกับ '#1 ทั้งหมด 5 เพลง'?
```

- `rel::5/forest_2.jpg::en::th`: number_tokens_changed:D:['15', '22']->['15', '02']

```text
Source: Which element is located directly below the "Novice Planter" achievement label?
Target: องค์ประกอบใดอยู่ตรงด้านล่างของป้ายชื่อ "ความสำเร็จ นักปลูกมือใหม่"?
```

```text
D source: The time "15:22"
D target: เวลา "15:02"
```

- `rel::5/forest_2.jpg::ru::th`: number_tokens_changed:D:['15', '48']->['15', '02']

```text
Source: Какой элемент находится прямо под меткой достижения "Начинающий планта..."
Target: องค์ประกอบใดอยู่ตรงด้านล่างของป้ายชื่อ "ความสําเร็จ นักปลูกมือใหม่"
```

```text
D source: Время "15:48"
D target: เวลา "15:02"
```

- `rel::5/forest_2.jpg::zh::th`: number_tokens_changed:D:['15', '22']->['15', '02']

```text
Source: 哪个元素位于“戴上草帽”成就标签的正下方？
Target: องค์ประกอบใดอยู่ตรงด้านล่างของป้ายชื่อความสำเร็จ "สวมหมวกหญ้า"?
```

```text
D source: 时间“15:22”
D target: เวลา "15:02"
```

완료된 TS_FULL_GUI의 신규 call runtime 합계는 16.42분, model-load 합계 0.16분이다. Call runtime은 generation/preprocessing 구간이며 전체 조건 wall time은 아니다. Peak reserved는 15.72GiB였다.

## screen: TS_FULL_TXT 변환 완료

| 범위 | N | 구조상 성공 | 구조 repair | 의미 repair 시도 | 의미 repair 채택 | 잔여 의미 경고 pair | 숫자 등 진단 pair |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 288 | 288 | 0 | 54 | 27 | 39 | 2 |
| main | 240 | 240 | 0 | 46 | 25 | 32 | 1 |
| pilot | 48 | 48 | 0 | 8 | 2 | 7 | 1 |

| Main GUI | N | 의미 repair | 잔여 의미 경고 |
| --- | ---: | ---: | ---: |
| en | 60 | 0 | 0 |
| ru | 60 | 9 | 4 |
| th | 60 | 28 | 23 |
| zh | 60 | 9 | 5 |

구조상 성공은 의미 보존을 보장하지 않는다. 의미 repair 채택은 자동 점수가 낮아졌다는 뜻이며 경고가 모두 사라졌다는 뜻은 아니다. 잔여 경고는 자동 휴리스틱이며, DND 같은 acronym 유지가 정당한 경우도 포함할 수 있다. 숫자 token 차이 역시 실제 GUI label 변화인지 번역 오류인지 별도 확인해야 한다.

### 검토할 원문/번역 사례

- `rel::2/map_9.png::ru::th`: spatial_core_relation_missing:below

```text
Source: Какой элемент находится прямо под переключателем 'Избегать платных дорог'?
Target: องค์ประกอบใดอยู่ต่ำกว่าสวิตช์ 'หลีกเลี่ยงทางหลวงเสียค่าใช้จ่าย'?
```

- `rel::2/note_8.png::en::th`: spatial_core_relation_missing:right, quoted_gui_label_may_be_untranslated:customize

```text
Source: Which element is located directly to the right of the 'Customize' option in the customization menu?
Target: องค์ประกอบใดอยู่ติดกับตัวเลือก 'Customize' ในเมนูการปรับแต่ง?
```

- `rel::2/note_8.png::en::zh`: quoted_gui_label_may_be_untranslated:customize

```text
Source: Which element is located directly to the right of the 'Customize' option in the customization menu?
Target: 在自定义菜单中，'Customize'选项的右侧直接是什么元素？
```

- `rel::2/setting_3.png::en::th`: quoted_gui_label_may_be_untranslated:handwrite

```text
Source: Which element is located directly to the right of the 'Handwrite' button?
Target: องค์ประกอบใดอยู่ทางด้านขวาโดยตรงของปุ่ม 'Handwrite'?
```

- `rel::2/setting_3.png::ru::th`: spatial_opposition_introduced

```text
Source: Какой элемент находится непосредственно справа от кнопки 'Написание'?
Target: องค์ประกอบใดอยู่ทางขวาของปุ่ม 'การเขียน' อย่างตรงข้าม?
```

- `rel::3/homescreen_5.jpg::en::ru`: quoted_gui_label_may_be_untranslated:dnd

```text
Source: Which element is directly below the 'DND' option in the mobile UI interface?
Target: Какой элемент находится непосредственно ниже опции 'DND' в интерфейсе мобильного приложения?
```

- `rel::3/homescreen_5.jpg::en::th`: quoted_gui_label_may_be_untranslated:dnd

```text
Source: Which element is directly below the 'DND' option in the mobile UI interface?
Target: องค์ประกอบใดอยู่ตรงด้านล่างของตัวเลือก 'DND' ในอินเทอร์เฟซ UI บนมือถือ?
```

- `rel::3/homescreen_5.jpg::en::zh`: quoted_gui_label_may_be_untranslated:dnd

```text
Source: Which element is directly below the 'DND' option in the mobile UI interface?
Target: 在移动界面中，'DND'选项直接下方的元素是什么？
```

- `rel::3/homescreen_5.jpg::ru::th`: spatial_core_relation_missing:below

```text
Source: Какой элемент находится прямо под опцией 'Не беспокоить' в интерфейсе мобильного устройства?
Target: องค์ประกอบใดอยู่ต่ำกว่าตัวเลือก 'ไม่รบกวน' ในอินเทอร์เฟซของอุปกรณ์เคลื่อนที่?
```

- `rel::3/map_4.jpg::en::th`: quoted_gui_label_may_be_untranslated:how you commute

```text
Source: Which option is located directly beneath the 'How you commute' headline?
Target: ตัวเลือกใดอยู่ตรงด้านล่างของหัวข้อ 'How you commute'?
```

- `rel::3/map_4.jpg::ru::th`: spatial_core_relation_missing:below

```text
Source: Какой вариант находится прямо под заголовком 'Как вы добираетесь'?
Target: ตัวเลือกใดอยู่ต่ำกว่าหัวข้อ 'คุณเดินทางอย่างไร'
```

- `rel::3/map_6.jpg::en::th`: quoted_gui_label_may_be_untranslated:choose on map

```text
Source: What is immediately to the right of the 'Choose on map' button?
Target: อะไรอยู่ทางด้านขวาของปุ่ม 'Choose on map' ทันที
```

- `rel::3/music_10.jpg::en::th`: spatial_core_relation_missing:above, spatial_opposition_introduced

```text
Source: Which element is located directly above the 'Update automatically' option in the given interface?
Target: องค์ประกอบใดอยู่ตรงข้ามกับตัวเลือก 'อัปเดตอัตโนมัติ' ในอินเทอร์เฟซที่กำหนด?
```

- `rel::3/music_3.jpg::en::ru`: translatable_options_unchanged:A,B,C,D

```text
Source: Which playlist is located directly above '#1 Total 5 songs'?
Target: Какая плейлист находится непосредственно выше '#1 Total 5 songs'?
```

- `rel::3/music_3.jpg::en::th`: translatable_options_unchanged:A,B,C,D

```text
Source: Which playlist is located directly above '#1 Total 5 songs'?
Target: เพลย์ลิสต์ใดอยู่ตรงข้างบน '#1 Total 5 songs'?
```

- `rel::3/music_3.jpg::en::zh`: translatable_options_unchanged:A,B,C,D

```text
Source: Which playlist is located directly above '#1 Total 5 songs'?
Target: 哪一个播放列表直接位于 '#1 Total 5 songs' 的上方？
```

- `rel::4/google_play_6.jpg::en::th`: quoted_gui_label_may_be_untranslated:wishlist

```text
Source: Which element is located directly below the 'Wishlist' section?
Target: องค์ประกอบใดอยู่ตรงด้านล่างของส่วน 'Wishlist'?
```

- `rel::4/google_play_6.jpg::ru::th`: spatial_core_relation_missing:below

```text
Source: Какой элемент находится непосредственно под разделом 'Список желаний'?
Target: องค์ประกอบใดอยู่ต่ำกว่าส่วน 'รายการที่ต้องการ' อย่างตรงไปตรงมา
```

- `rel::4/google_play_8.jpg::ru::th`: spatial_core_relation_missing:above

```text
Source: Какой параметр находится непосредственно выше опции «Использовать данные о местоположении устройства» в меню настроек?
Target: ตัวเลือกใดอยู่ติดกับตัวเลือก "ใช้ข้อมูลตำแหน่งของอุปกรณ์" ในเมนูตั้งค่า?
```

- `rel::4/google_play_8.jpg::zh::ru`: number_tokens_changed:A:[]->['5']

```text
Source: 在设置菜单中，哪个设置位于“使用设备位置信息”选项的正上方？
Target: В меню настроек, какой параметр находится непосредственно выше опции «Использовать информацию о местоположении устройства»?
```

```text
A source: Google Play 商店反馈
A target: Обратная связь Google Play Маркета
```

- `rel::5/forest_2.jpg::en::th`: quoted_gui_label_may_be_untranslated:novice planter

```text
Source: Which element is located directly below the "Novice Planter" achievement label?
Target: องค์ประกอบใดอยู่ตรงด้านล่างของป้ายชื่อ "Novice Planter"?
```

- `rel::5/forest_2.jpg::en::zh`: quoted_gui_label_may_be_untranslated:novice planter

```text
Source: Which element is located directly below the "Novice Planter" achievement label?
Target: 以下哪个元素位于 "Novice Planter" 成就标签的正下方？
```

- `rel::5/forest_2.jpg::ru::th`: spatial_core_relation_missing:below

```text
Source: Какой элемент находится прямо под меткой достижения "Начинающий планта..."
Target: องค์ประกอบใดอยู่ต่ำกว่าป้ายชื่อ "ผู้เริ่มต้นปลูกต้นไม้..." อย่างตรงไปตรงมา
```

- `rel::5/message_2.jpg::en::th`: quoted_gui_label_may_be_untranslated:smart message recognition

```text
Source: Which toggle switch is located directly below the "Smart message recognition" option?
Target: สวิตช์แบบทูดที่อยู่ตรงด้านล่างของตัวเลือก "Smart message recognition" คือตัวเลือกใด
```

- `rel::5/phone_4.jpg::en::th`: quoted_gui_label_may_be_untranslated:delay auto answer

```text
Source: Which option is directly below "Delay auto answer"?
Target: ตัวเลือกใดอยู่ตรงด้านล่างของ "Delay auto answer"?
```

- `rel::5/phone_4.jpg::ru::th`: spatial_core_relation_missing:below

```text
Source: Какой вариант находится непосредственно под "Задержка автоответа"?
Target: ตัวเลือกใดอยู่ต่ำกว่า "การตั้งค่าการตอบกลับอัตโนมัติ"?
```

- `rel::6/camera_8.jpg::en::ru`: translatable_options_unchanged:A,B,C,D

```text
Source: Which mode is directly to the left of the PHOTO mode on this user interface?
Target: Какой режим находится непосредственно слева от режима PHOTO в этом пользовательском интерфейсе?
```

- `rel::6/camera_8.jpg::en::th`: translatable_options_unchanged:A,B,C,D

```text
Source: Which mode is directly to the left of the PHOTO mode on this user interface?
Target: โหมดใดอยู่ทางด้านซ้ายของโหมด PHOTO บนอินเทอร์เฟซนี้โดยตรง?
```

- `rel::6/camera_8.jpg::en::zh`: translatable_options_unchanged:A,B,C,D

```text
Source: Which mode is directly to the left of the PHOTO mode on this user interface?
Target: 以下哪种模式位于此用户界面的 PHOTO 模式左侧？
```

- `rel::6/wallet_6.jpg::en::th`: quoted_gui_label_may_be_untranslated:nearby

```text
Source: What element is located directly below the 'Nearby' label on the interface?
Target: องค์ประกอบใดอยู่ตรงด้านล่างของป้ายชื่อ 'Nearby' บนอินเทอร์เฟซ?
```

- `rel::6/wallet_6.jpg::ru::th`: spatial_core_relation_missing:below

```text
Source: Какой элемент находится непосредственно под меткой 'Скоро' на интерфейсе?
Target: องค์ประกอบใดอยู่ต่ำกว่าป้าย 'เร็วๆ นี้' บนอินเทอร์เฟซ?
```

- `rel::6/wallet_8.jpg::en::ru`: quoted_gui_label_may_be_untranslated:find apps for wallet

```text
Source: What is positioned immediately above the 'Find Apps for Wallet' text?
Target: Что расположено непосредственно выше текста 'Find Apps for Wallet'?
```

- `rel::6/wallet_8.jpg::en::th`: quoted_gui_label_may_be_untranslated:find apps for wallet

```text
Source: What is positioned immediately above the 'Find Apps for Wallet' text?
Target: สิ่งใดอยู่ทันทีข้างบนของข้อความ 'Find Apps for Wallet'?
```

완료된 TS_FULL_TXT의 신규 call runtime 합계는 12.78분, model-load 합계 0.00분이다. Call runtime은 generation/preprocessing 구간이며 전체 조건 wall time은 아니다. Peak reserved는 15.72GiB였다.

Full GUI와 Full TXT는 각각 과거 lexical/contextual prompt를 사용하므로 inventory 제공뿐 아니라 prompt 규칙도 다르다. 자동 경고 수 차이를 inventory만의 순수 인과 효과로 해석하지 않는다.

## 다음 집계에서 확인할 것

- 나머지 변환이 끝나면 O와 각 조건의 VLM generation accuracy 및 paired 회복/회귀를 확인한다.
- Hybrid의 옵션이 Full과 동일한지, stem 선택적 정렬의 이득이 있는지 본다.
- Stem-only의 낮은 parser 실패율이 실제 의미 오류 감소로 이어지는지 검토한다. 이전 NO-GO를 구조 통과율만으로 해제하지 않는다.

진행 중 파일은 완성된 newline 행만 읽었다. 변환은 전체 pair ID가 갖춰진 조건만 요약했고, 정확도는 O/조건 모두 전체 출력이 갖춰져야 계산한다. 숫자는 snapshot 시점 기준이며 계속 증가할 수 있다.

재집계 명령(추론 없음):

```bash
.venv/bin/python followup_rel_4lang/method_dev/scripts/update_two_stage_results.py
```

[집계 snapshot](../artifacts/two_stage_results_snapshot.json) · [Hybrid 설정](HYBRID_CONTROL_KO.md) · [기본 prompt/config](TWO_STAGE_V2_PROTOCOL_KO.md).
