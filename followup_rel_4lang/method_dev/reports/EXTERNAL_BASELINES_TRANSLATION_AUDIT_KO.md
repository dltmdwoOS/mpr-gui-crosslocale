# Translate-Test 내용 보존 검토 후보

숫자/새 보기중복 및 방향·부정 표면 cue 차이를 표시한 검수 후보다. 의역·UI 이름으로 인한 오탐이 있어 의미 오류율로 해석하지 않는다. 자동 출력의 채택/수정/repair/점수에 사용하지 않았다.

## rel::3/backend_1.jpg::ru::en

```json
{
  "pair_id": "rel::3/backend_1.jpg::ru::en",
  "source": {
    "source_language": "ru",
    "question_stem": "Какой элемент находится в верхнем правом углу интерфейса приложения «Калькулятор» на этом мобильном скриншоте?",
    "options": {
      "A": "Антивирус",
      "B": "Очистка",
      "C": "Глубокая очистка",
      "D": "Приложения"
    }
  },
  "translated": {
    "question_stem": "Which element is located in the upper right corner of the Calculator app interface on this mobile screenshot?",
    "options": {
      "A": "Antivirus",
      "B": "Clean",
      "C": "Deep Clean",
      "D": "Apps"
    }
  },
  "cue_flags": [
    {
      "field": "question_stem",
      "source_cues": [],
      "english_cues": [
        "right"
      ]
    }
  ],
  "other_flags": {
    "digit_sequence_changed_fields": [],
    "new_duplicate_options": false,
    "semantic_equivalence_verified": false
  }
}
```

## rel::2/clock_4.png::ru::en

```json
{
  "pair_id": "rel::2/clock_4.png::ru::en",
  "source": {
    "source_language": "ru",
    "question_stem": "Какой элемент находится непосредственно слева от заголовка 'Мелодия' в правом верхнем углу интерфейса?",
    "options": {
      "A": "Кнопка \"Назад\"",
      "B": "Кнопка \"Править\"",
      "C": "Раздел \"Рингтоны\"",
      "D": "Опция \"Выбор песни\""
    }
  },
  "translated": {
    "question_stem": "Which element is directly to the left of the 'Melody' header in the top-right corner of the interface?",
    "options": {
      "A": "Back button",
      "B": "Edit button",
      "C": "Ringtones section",
      "D": "Song selection option"
    }
  },
  "cue_flags": [
    {
      "field": "question_stem",
      "source_cues": [
        "left"
      ],
      "english_cues": [
        "left",
        "right"
      ]
    }
  ],
  "other_flags": {
    "digit_sequence_changed_fields": [],
    "new_duplicate_options": false,
    "semantic_equivalence_verified": false
  }
}
```

## rel::2/setting_2.png::ru::en

```json
{
  "pair_id": "rel::2/setting_2.png::ru::en",
  "source": {
    "source_language": "ru",
    "question_stem": "Какой параметр находится непосредственно выше опции 'Пункт управления' в левом боковом меню?",
    "options": {
      "A": "Основные",
      "B": "Экранное время",
      "C": "Фокусирование",
      "D": "Экран и яркость"
    }
  },
  "translated": {
    "question_stem": "Which parameter is directly above the 'Parental Controls' option in the left sidebar menu?",
    "options": {
      "A": "General",
      "B": "Screen Time",
      "C": "Focus",
      "D": "Display and Brightness"
    }
  },
  "cue_flags": [
    {
      "field": "question_stem",
      "source_cues": [
        "above"
      ],
      "english_cues": [
        "above",
        "left"
      ]
    }
  ],
  "other_flags": {
    "digit_sequence_changed_fields": [],
    "new_duplicate_options": false,
    "semantic_equivalence_verified": false
  }
}
```

## rel::5/file_1.jpg::ru::en

```json
{
  "pair_id": "rel::5/file_1.jpg::ru::en",
  "source": {
    "source_language": "ru",
    "question_stem": "Какой элемент находится непосредственно под заголовком \"Статистика очистки\"?",
    "options": {
      "A": "Очистка кэша",
      "B": "Всего освобождено 6,81 ГБ",
      "C": "Установочные пакеты",
      "D": "По категориям"
    }
  },
  "translated": {
    "question_stem": "Which element is directly under the heading \"Cleanup Statistics\"?",
    "options": {
      "A": "Cache Cleanup",
      "B": "Total freed up 6.81 GB",
      "C": "Installation Packages",
      "D": "By Categories"
    }
  },
  "cue_flags": [],
  "other_flags": {
    "digit_sequence_changed_fields": [
      "B"
    ],
    "new_duplicate_options": false,
    "semantic_equivalence_verified": false
  }
}
```

## rel::3/homescreen_5.jpg::zh::en

```json
{
  "pair_id": "rel::3/homescreen_5.jpg::zh::en",
  "source": {
    "source_language": "zh",
    "question_stem": "在移动UI界面中，哪个元素直接位于「勿扰模式」选项下方？",
    "options": {
      "A": "省电模式",
      "B": "小米互传",
      "C": "振动",
      "D": "迷你小窗"
    }
  },
  "translated": {
    "question_stem": "In a mobile UI interface, which element is directly below the 'Do Not Disturb' option?",
    "options": {
      "A": "Power Saving Mode",
      "B": "Xiaomi Share",
      "C": "Vibration",
      "D": "Mini Floating Window"
    }
  },
  "cue_flags": [
    {
      "field": "question_stem",
      "source_cues": [
        "below"
      ],
      "english_cues": [
        "below",
        "negation"
      ]
    }
  ],
  "other_flags": {
    "digit_sequence_changed_fields": [],
    "new_duplicate_options": false,
    "semantic_equivalence_verified": false
  }
}
```

## rel::3/map_4.jpg::zh::en

```json
{
  "pair_id": "rel::3/map_4.jpg::zh::en",
  "source": {
    "source_language": "zh",
    "question_stem": "哪个选项位于“通勤方式”标题的正下方？",
    "options": {
      "A": "输入单位地址",
      "B": "让地图使用位置记录功能提高您的通勤时间准确性",
      "C": "选择交通模式",
      "D": "未设置"
    }
  },
  "translated": {
    "question_stem": "Which option is directly below the 'Commute Method' title?",
    "options": {
      "A": "Enter your unit address",
      "B": "Let the map use the location recording function to improve the accuracy of your commute time",
      "C": "Select transportation mode",
      "D": "Not set"
    }
  },
  "cue_flags": [
    {
      "field": "D",
      "source_cues": [],
      "english_cues": [
        "negation"
      ]
    }
  ],
  "other_flags": {
    "digit_sequence_changed_fields": [],
    "new_duplicate_options": false,
    "semantic_equivalence_verified": false
  }
}
```

## rel::4/google_play_5.jpg::zh::en

```json
{
  "pair_id": "rel::4/google_play_5.jpg::zh::en",
  "source": {
    "source_language": "zh",
    "question_stem": "哪个元素位于“扫描”按钮的正下方？",
    "options": {
      "A": "近期扫描的应用部分",
      "B": "未发现任何有害应用消息",
      "C": "了解详情链接",
      "D": "设置图标"
    }
  },
  "translated": {
    "question_stem": "Which element is directly below the 'Scan' button?",
    "options": {
      "A": "Recent scan application section",
      "B": "No harmful application messages found",
      "C": "Learn more link",
      "D": "Settings icon"
    }
  },
  "cue_flags": [
    {
      "field": "B",
      "source_cues": [],
      "english_cues": [
        "negation"
      ]
    }
  ],
  "other_flags": {
    "digit_sequence_changed_fields": [],
    "new_duplicate_options": false,
    "semantic_equivalence_verified": false
  }
}
```

## rel::6/phone_7.jpg::zh::en

```json
{
  "pair_id": "rel::6/phone_7.jpg::zh::en",
  "source": {
    "source_language": "zh",
    "question_stem": "哪个选项位于界面中“屏蔽来电号码”的正上方？",
    "options": {
      "A": "共享联系人",
      "B": "添加到紧急联系人",
      "C": "2025年6月6日",
      "D": "新建联系人"
    }
  },
  "translated": {
    "question_stem": "Which option is directly above the \"Block Callers\" feature in the interface?",
    "options": {
      "A": "Share Contact",
      "B": "Add to Emergency Contacts",
      "C": "June 6, 2025",
      "D": "New Contact"
    }
  },
  "cue_flags": [],
  "other_flags": {
    "digit_sequence_changed_fields": [
      "C"
    ],
    "new_duplicate_options": false,
    "semantic_equivalence_verified": false
  }
}
```

## rel::2/map_9.png::th::en

```json
{
  "pair_id": "rel::2/map_9.png::th::en",
  "source": {
    "source_language": "th",
    "question_stem": "องค์ประกอบใดอยู่ด้านล่างโดยตรงของสวิตช์สลับ 'เลี่ยงทางหลวง'?",
    "options": {
      "A": "เลี่ยงทางด่วน",
      "B": "เลี่ยงบันได",
      "C": "E-Bike",
      "D": "รถไฟใต้ดินและรถไฟรางเบา"
    }
  },
  "translated": {
    "question_stem": "Which component is directly below the 'Highway Bypass' switch?",
    "options": {
      "A": "Bypass Expressway",
      "B": "Bypass Stairs",
      "C": "E-Bike",
      "D": "Subway and Light Rail"
    }
  },
  "cue_flags": [
    {
      "field": "D",
      "source_cues": [
        "below"
      ],
      "english_cues": []
    }
  ],
  "other_flags": {
    "digit_sequence_changed_fields": [],
    "new_duplicate_options": false,
    "semantic_equivalence_verified": false
  }
}
```

## rel::3/homescreen_5.jpg::th::en

```json
{
  "pair_id": "rel::3/homescreen_5.jpg::th::en",
  "source": {
    "source_language": "th",
    "question_stem": "องค์ประกอบใดอยู่ด้านล่างของตัวเลือก 'ห้ามรบกวน' ในอินเทอร์เฟซมือถือ?",
    "options": {
      "A": "ตัวประหยัดแบตเตอรี",
      "B": "Mi แชร์",
      "C": "สั่นเตือน",
      "D": "หน้าต่างลอย"
    }
  },
  "translated": {
    "question_stem": "Which component is located below the 'Do Not Disturb' option in the mobile interface?",
    "options": {
      "A": "Battery Saver",
      "B": "Mi Share",
      "C": "Vibrate Alert",
      "D": "Floating Window"
    }
  },
  "cue_flags": [
    {
      "field": "question_stem",
      "source_cues": [
        "below"
      ],
      "english_cues": [
        "below",
        "negation"
      ]
    }
  ],
  "other_flags": {
    "digit_sequence_changed_fields": [],
    "new_duplicate_options": false,
    "semantic_equivalence_verified": false
  }
}
```

## rel::5/phone_4.jpg::th::en

```json
{
  "pair_id": "rel::5/phone_4.jpg::th::en",
  "source": {
    "source_language": "th",
    "question_stem": "Which option is directly below \"ชะลอการตอบกลับอัตโนมัติ\"?",
    "options": {
      "A": "กดปุ่มเปิดปิดเครื่องเพื่อวางสาย",
      "B": "รับสายอัตโนมัติเมื่อเชื่อมต่อกับอุปกรณ์เสียงจากภายนอก",
      "C": "Answer/End calls",
      "D": "บลูทูธหรือหูฟังแบบมีสาย และอุปกรณ์เสียงอื่น ๆ"
    }
  },
  "translated": {
    "question_stem": "Which option is directly below \"Automatic Response\"?",
    "options": {
      "A": "Press the power button to answer the call",
      "B": "Answer automatically when connected to an external audio device",
      "C": "Answer/End calls",
      "D": "Bluetooth or wired earphones and other audio devices"
    }
  },
  "cue_flags": [
    {
      "field": "question_stem",
      "source_cues": [],
      "english_cues": [
        "below"
      ]
    }
  ],
  "other_flags": {
    "digit_sequence_changed_fields": [],
    "new_duplicate_options": false,
    "semantic_equivalence_verified": false
  }
}
```

## rel::5/message_12.jpg::th::en

```json
{
  "pair_id": "rel::5/message_12.jpg::th::en",
  "source": {
    "source_language": "th",
    "question_stem": "ในภาพหน้าจอ UI มือถือ อะไรอยู่ทางขวาของแท็บ \"การแจ้งเตือน\" ในแถบนำทางด้านล่าง?",
    "options": {
      "A": "ไอคอน \"+\" ในวงกลมสีแดง",
      "B": "ไอคอนสี่เหลี่ยม",
      "C": "ไอคอนวงกลม",
      "D": "แท็บ \"ข้อความ\""
    }
  },
  "translated": {
    "question_stem": "In the mobile UI screen, what is located to the right of the \"Notifications\" tab in the bottom navigation bar?",
    "options": {
      "A": "The \"+\" icon in a red circle",
      "B": "A square icon",
      "C": "A circular icon",
      "D": "The \"Messages\" tab"
    }
  },
  "cue_flags": [
    {
      "field": "question_stem",
      "source_cues": [
        "below",
        "right"
      ],
      "english_cues": [
        "right"
      ]
    }
  ],
  "other_flags": {
    "digit_sequence_changed_fields": [],
    "new_duplicate_options": false,
    "semantic_equivalence_verified": false
  }
}
```
