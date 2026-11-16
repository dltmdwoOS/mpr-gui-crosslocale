# 수정 전 오답69쌍: 원문과 생성문

Post-hoc 검토용. 생성 모델에 제공되지 않은 평가 자료다.

## rel::2/calendar_6.png::en::th

GT B; 문맥 경고: 없음.

```json
{
  "source": {
    "question_stem": "Which day of the week has a scheduled event, and what is its relative position compared to Thursday?",
    "A": "Tuesday, one day before",
    "B": "Wednesday, one day before",
    "C": "Friday, one day after",
    "D": "Sunday, three days before"
  },
  "rewrite": {
    "question_stem": "Which day of the week has a scheduled event, and what is its relative position compared to พุธ.",
    "A": "จันทร์, one day before",
    "B": "อังคาร, one day before",
    "C": "พฤหัสบดี, one day after",
    "D": "อาทิตย์, three days before"
  }
}
```

## rel::2/map_9.png::ru::th

GT A; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "Какой элемент находится прямо под переключателем 'Избегать платных дорог'?",
    "A": "Избегать автомагистралей",
    "B": "Избегать лестниц",
    "C": "Электровелосипед",
    "D": "Метро и трамвай"
  },
  "rewrite": {
    "question_stem": "ข้อใดอยู่ตรงด้านล่างของสวิตช์ 'เลี่ยงทางด่วน'?",
    "A": "เลี่ยงทางด่วน",
    "B": "เลี่ยงทางหลวง",
    "C": "E-Bike",
    "D": "รถไฟใต้ดินและรถไฟฟ้า"
  }
}
```

## rel::2/map_9.png::th::en

GT A; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "องค์ประกอบใดอยู่ด้านล่างโดยตรงของสวิตช์สลับ 'เลี่ยงทางหลวง'?",
    "A": "เลี่ยงทางด่วน",
    "B": "เลี่ยงบันได",
    "C": "E-Bike",
    "D": "รถไฟใต้ดินและรถไฟรางเบา"
  },
  "rewrite": {
    "question_stem": "Which item is directly below the toggle switch 'Avoid Highways'?",
    "A": "Avoid Tolls",
    "B": "Avoid Stairs",
    "C": "E-Bike",
    "D": "Subway & Light Rail"
  }
}
```

## rel::2/map_9.png::th::ru

GT A; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "องค์ประกอบใดอยู่ด้านล่างโดยตรงของสวิตช์สลับ 'เลี่ยงทางหลวง'?",
    "A": "เลี่ยงทางด่วน",
    "B": "เลี่ยงบันได",
    "C": "E-Bike",
    "D": "รถไฟใต้ดินและรถไฟรางเบา"
  },
  "rewrite": {
    "question_stem": "Какой элемент находится прямо под переключателем 'Избегать автомагистралей'?",
    "A": "Избегать платных дорог",
    "B": "Избегать лестниц",
    "C": "Электровелосипед",
    "D": "Метро и трамвай"
  }
}
```

## rel::2/map_9.png::th::zh

GT A; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "องค์ประกอบใดอยู่ด้านล่างโดยตรงของสวิตช์สลับ 'เลี่ยงทางหลวง'?",
    "A": "เลี่ยงทางด่วน",
    "B": "เลี่ยงบันได",
    "C": "E-Bike",
    "D": "รถไฟใต้ดินและรถไฟรางเบา"
  },
  "rewrite": {
    "question_stem": "哪个组件位于“避开高速公路”开关的正下方？",
    "A": "避开高速",
    "B": "避开楼梯",
    "C": "电动自行车",
    "D": "地铁与轻轨"
  }
}
```

## rel::2/note_1.png::en::th

GT A; 문맥 경고: 없음.

```json
{
  "source": {
    "question_stem": "Which element is located directly to the below of the 'Draw with Finger' toggle switch?",
    "A": "Pencil Settings...",
    "B": "Auto-minimize toggle switch",
    "C": "Color selection circle",
    "D": "Eraser icon"
  },
  "rewrite": {
    "question_stem": "Which element is located directly to the below of the 'ย่ออัดโน้มติ' toggle switch?",
    "A": "Pencil Settings...",
    "B": "Auto-minimize toggle switch",
    "C": "Color selection circle",
    "D": "Eraser icon"
  }
}
```

## rel::2/note_1.png::ru::th

GT A; 문맥 경고: question_stem, C, D.

```json
{
  "source": {
    "question_stem": "Какой элемент находится непосредственно ниже переключателя 'Рисуйте пальцем'?",
    "A": "Настройки карандаша...",
    "B": "Автоматически убирать в Dock",
    "C": "Круг выбора цвета",
    "D": "Значок ластика"
  },
  "rewrite": {
    "question_stem": "Which item is directly below the toggle \"ออยอตโนมิติ\"?",
    "A": "การตั้งค่าดินสอ...",
    "B": "ใช้นิ้ววาด",
    "C": "วงเล็บเลือกสี",
    "D": "ไอคอนยางลบ"
  }
}
```

## rel::2/note_1.png::zh::th

GT A; 문맥 경고: B.

```json
{
  "source": {
    "question_stem": "哪个元素位于“用手指涂画”开关的正下方？",
    "A": "触控笔设置...",
    "B": "自动最小化开关",
    "C": "颜色选择圆圈",
    "D": "橡皮擦图标"
  },
  "rewrite": {
    "question_stem": "哪个元素位于“ย่ออัตโนมัติ”开关的正下方？",
    "A": "การตั้งค่าดินสอ...",
    "B": "ใช้นิ้ววาด",
    "C": "颜色选择圆圈",
    "D": "橡皮擦图标"
  }
}
```

## rel::2/note_8.png::ru::th

GT A; 문맥 경고: question_stem, D.

```json
{
  "source": {
    "question_stem": "Какой элемент находится непосредственно справа от опции 'Настройка' в меню настройки?",
    "A": "Готово",
    "B": "Сбросить",
    "C": "Перетяните объекты, чтобы удалить их",
    "D": "Значок камеры"
  },
  "rewrite": {
    "question_stem": "Which item is directly to the right of the \"Settings\" option in the settings menu?",
    "A": "รีเซ็ต",
    "B": "กำหนดเอง",
    "C": "ลากเพื่อเอารายการออก",
    "D": "ไอคอนกล้อง"
  }
}
```

## rel::2/setting_3.png::en::th

GT A; 문맥 경고: 없음.

```json
{
  "source": {
    "question_stem": "Which element is located directly to the right of the 'Handwrite' button?",
    "A": "Delete",
    "B": "Select",
    "C": "Insert",
    "D": "Join"
  },
  "rewrite": {
    "question_stem": "Which element is located directly to the right of the 'เขียนข้อความ' button?",
    "A": "Delete",
    "B": "Select",
    "C": "Insert",
    "D": "Join"
  }
}
```

## rel::2/setting_3.png::zh::th

GT A; 문맥 경고: 없음.

```json
{
  "source": {
    "question_stem": "哪个元素位于“手写”按钮的右侧？",
    "A": "删除",
    "B": "选择",
    "C": "插入",
    "D": "组合"
  },
  "rewrite": {
    "question_stem": "哪个元素位于“เขียนข้อความ”按钮的右侧？",
    "A": "ลบ",
    "B": "เลือก",
    "C": "แทรก",
    "D": "เขียนกัน"
  }
}
```

## rel::3/homescreen_3.jpg::ru::th

GT B; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "Какой значок находится непосредственно справа от приложения Диктофон на интерфейсе?",
    "A": "Часы",
    "B": "Запись экрана",
    "C": "Калькулятор",
    "D": "Загрузки"
  },
  "rewrite": {
    "question_stem": "Which icon is directly to the right of the Voice Recorder app on the interface?",
    "A": "นาฬิกา",
    "B": "บันทึกหน้าจอ",
    "C": "เครื่องคิดเลข",
    "D": "ดาวน์โหลด"
  }
}
```

## rel::3/homescreen_3.jpg::zh::ru

GT B; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "哪个图标出现在界面上录音机应用程序的右侧？",
    "A": "时钟",
    "B": "屏幕录制",
    "C": "计算器",
    "D": "下载管理"
  },
  "rewrite": {
    "question_stem": "Какой иконка появляется на экране справа от приложения Запись экрана?",
    "A": "Часы",
    "B": "Запись экрана",
    "C": "Калькулятор",
    "D": "Загрузки"
  }
}
```

## rel::3/homescreen_3.jpg::zh::th

GT B; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "哪个图标出现在界面上录音机应用程序的右侧？",
    "A": "时钟",
    "B": "屏幕录制",
    "C": "计算器",
    "D": "下载管理"
  },
  "rewrite": {
    "question_stem": "ซึ่งไอคอนปรากฏอยู่ทางขวาของแอปพลิเคชันเครื่องบันทึกเสียงบนหน้าจอ?",
    "A": "นาฬิกา",
    "B": "บันทึกหน้าจอ",
    "C": "เครื่องคิดเลข",
    "D": "ดาวน์โหลด"
  }
}
```

## rel::3/homescreen_5.jpg::en::th

GT B; 문맥 경고: 없음.

```json
{
  "source": {
    "question_stem": "Which element is directly below the 'DND' option in the mobile UI interface?",
    "A": "Battery saver",
    "B": "Mi Share",
    "C": "Vibrate",
    "D": "Floating window"
  },
  "rewrite": {
    "question_stem": "Which element is directly below the 'โหมดดับเสียง' option in the mobile UI interface?",
    "A": "ตัวประจุแบตเต็ม",
    "B": "Mi แชร์",
    "C": "สั่นเตือน",
    "D": "หน้าต่างลอย"
  }
}
```

## rel::3/homescreen_5.jpg::th::zh

GT B; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "องค์ประกอบใดอยู่ด้านล่างของตัวเลือก 'ห้ามรบกวน' ในอินเทอร์เฟซมือถือ?",
    "A": "ตัวประหยัดแบตเตอรี",
    "B": "Mi แชร์",
    "C": "สั่นเตือน",
    "D": "หน้าต่างลอย"
  },
  "rewrite": {
    "question_stem": "哪个选项位于“勿扰模式”下方？",
    "A": "超级省电",
    "B": "小米互传",
    "C": "振动",
    "D": "迷你小窗"
  }
}
```

## rel::3/homescreen_5.jpg::zh::th

GT B; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "在移动UI界面中，哪个元素直接位于「勿扰模式」选项下方？",
    "A": "省电模式",
    "B": "小米互传",
    "C": "振动",
    "D": "迷你小窗"
  },
  "rewrite": {
    "question_stem": "ในอินเทอร์เฟซ UI ของมือถือ องค์ประกอบใดอยู่ตรงด้านล่างของตัวเลือก \"โหมดไม่รบกวน\"?",
    "A": "โหมดประหยัดพลังงาน",
    "B": "Mi แชร์",
    "C": "สั่นเตือน",
    "D": "หน้าต่างเล็ก"
  }
}
```

## rel::3/map_4.jpg::en::ru

GT C; 문맥 경고: 없음.

```json
{
  "source": {
    "question_stem": "Which option is located directly beneath the 'How you commute' headline?",
    "A": "Enter work address",
    "B": "Let Maps improve your commute times accuracy by using Location History",
    "C": "Choose transportation mode",
    "D": "Not set up"
  },
  "rewrite": {
    "question_stem": "Which option is located directly beneath the 'Как вы добираетесь' headline?",
    "A": "Выберите средство передвижения",
    "B": "Использовать историю местоположений, чтобы отправлять более точную информацию о регулярных маршрутах",
    "C": "Выберите средство передвижения",
    "D": "Не настроено"
  }
}
```

## rel::3/map_4.jpg::ru::th

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "Какой вариант находится прямо под заголовком 'Как вы добираетесь'?",
    "A": "Введите рабочий адрес",
    "B": "Позвольте Картам улучшить точность времени в пути, используя Историю местоположений",
    "C": "Выберите средство передвижения",
    "D": "Не настроено"
  },
  "rewrite": {
    "question_stem": "Which option is directly below the title 'การตั้งค่าการเดินทาง'?",
    "A": "บ้าน",
    "B": "รับการแจ้งเตือนการเดินทาง ทราบเกี่ยวกับความล่าช้าและบริการชั้ดช่องก่อนเดินทาง",
    "C": "ที่ทำงาน",
    "D": "ไม่ได้ตั้งค่า"
  }
}
```

## rel::3/map_4.jpg::zh::ru

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "哪个选项位于“通勤方式”标题的正下方？",
    "A": "输入单位地址",
    "B": "让地图使用位置记录功能提高您的通勤时间准确性",
    "C": "选择交通模式",
    "D": "未设置"
  },
  "rewrite": {
    "question_stem": "Какой элемент находится непосредственно под заголовком «Как вы добираетесь»?",
    "A": "Выберите средство передвижения",
    "B": "Использовать историю местоположений, чтобы отправлять более точную информацию о регулярных маршрутах",
    "C": "Выберите средство передвижения",
    "D": "Не настроено"
  }
}
```

## rel::3/map_4.jpg::zh::th

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "哪个选项位于“通勤方式”标题的正下方？",
    "A": "输入单位地址",
    "B": "让地图使用位置记录功能提高您的通勤时间准确性",
    "C": "选择交通模式",
    "D": "未设置"
  },
  "rewrite": {
    "question_stem": "ซึ่งตัวเลือกอยู่ตรงด้านล่างของหัวข้อ \"การตั้งค่าการเดินทาง\"?",
    "A": "ป้อนที่อยู่ของคุณ",
    "B": "เปิดใช้งานการตั้งค่าการเดินทางเพื่อเพิ่มความแม่นยำของเวลาเดินทาง",
    "C": "เลือกโหมดการเดินทาง",
    "D": "ไม่ได้ตั้งค่า"
  }
}
```

## rel::3/music_10.jpg::zh::th

GT A; 문맥 경고: 없음.

```json
{
  "source": {
    "question_stem": "哪个元素位于界面中“自动升级”选项的正上方？",
    "A": "版本信息",
    "B": "用户协议",
    "C": "隐私政策",
    "D": "更高级设置"
  },
  "rewrite": {
    "question_stem": "哪个元素位于界面中“การตั้งค่าขั้นสูง”选项的正上方？",
    "A": "เวอร์ชั่น",
    "B": "ข้อตกลงการใช้งาน",
    "C": "นโยบายความเป็นส่วนตัว",
    "D": "บัญชี Mi"
  }
}
```

## rel::3/music_3.jpg::en::ru

GT C; 문맥 경고: 없음.

```json
{
  "source": {
    "question_stem": "Which playlist is located directly above '#1 Total 5 songs'?",
    "A": "#4 Total 8 songs",
    "B": "#2 Total 6 songs",
    "C": "#3 Total 4 songs",
    "D": "Shuffle playback"
  },
  "rewrite": {
    "question_stem": "Which playlist is located directly above '#1 Всего 5 треков'?",
    "A": "#4 Всего 8 треков",
    "B": "#2 Всего 6 треков",
    "C": "#3 Всего 4 трека",
    "D": "В случайном порядке"
  }
}
```

## rel::3/music_3.jpg::en::th

GT C; 문맥 경고: 없음.

```json
{
  "source": {
    "question_stem": "Which playlist is located directly above '#1 Total 5 songs'?",
    "A": "#4 Total 8 songs",
    "B": "#2 Total 6 songs",
    "C": "#3 Total 4 songs",
    "D": "Shuffle playback"
  },
  "rewrite": {
    "question_stem": "Which playlist is located directly above '#1 ทั้งหมด 5 เพลง'?",
    "A": "#4 ทั้งหมด 8 เพลง",
    "B": "#2 ทั้งหมด 6 เพลง",
    "C": "#3 ทั้งหมด 4 เพลง",
    "D": "เล่นสุ่ม"
  }
}
```

## rel::3/music_3.jpg::en::zh

GT C; 문맥 경고: 없음.

```json
{
  "source": {
    "question_stem": "Which playlist is located directly above '#1 Total 5 songs'?",
    "A": "#4 Total 8 songs",
    "B": "#2 Total 6 songs",
    "C": "#3 Total 4 songs",
    "D": "Shuffle playback"
  },
  "rewrite": {
    "question_stem": "Which playlist is located directly above '#1 共5首歌'?",
    "A": "#4 共8首歌",
    "B": "#2 共6首歌",
    "C": "#3 共4首歌",
    "D": "随机播放"
  }
}
```

## rel::3/music_3.jpg::ru::en

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "Какой плейлист находится прямо над '#1 Всего 5 треков'?",
    "A": "#4 Всего 8 треков",
    "B": "#2 Всего 6 треков",
    "C": "#3 Всего 4 трека",
    "D": "В случайном порядке"
  },
  "rewrite": {
    "question_stem": "Which playlist is directly above '#1 Total 5 songs'?",
    "A": "#4 Total 8 songs",
    "B": "#2 Total 6 songs",
    "C": "#3 Total 4 songs",
    "D": "Shuffle playback"
  }
}
```

## rel::3/music_3.jpg::ru::th

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "Какой плейлист находится прямо над '#1 Всего 5 треков'?",
    "A": "#4 Всего 8 треков",
    "B": "#2 Всего 6 треков",
    "C": "#3 Всего 4 трека",
    "D": "В случайном порядке"
  },
  "rewrite": {
    "question_stem": "Which playlist is directly above '#1 ทั้งหมด 5 เพลง'?",
    "A": "#4 ทั้งหมด 8 เพลง",
    "B": "#2 ทั้งหมด 6 เพลง",
    "C": "#3 ทั้งหมด 4 เพลง",
    "D": "ในลำดับสุ่ม"
  }
}
```

## rel::3/music_3.jpg::ru::zh

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "Какой плейлист находится прямо над '#1 Всего 5 треков'?",
    "A": "#4 Всего 8 треков",
    "B": "#2 Всего 6 треков",
    "C": "#3 Всего 4 трека",
    "D": "В случайном порядке"
  },
  "rewrite": {
    "question_stem": "哪个歌单位于“#1 共5首歌”正上方？",
    "A": "#4 共8首歌",
    "B": "#2 共6首歌",
    "C": "#3 共4首歌",
    "D": "随机播放"
  }
}
```

## rel::3/music_3.jpg::th::en

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "เพลย์ลิสต์ใดอยู่เหนือ \"#1 ทั้งหมด 5 เพลง\"?",
    "A": "#4 ทั้งหมด 8 เพลง",
    "B": "#2 ทั้งหมด 6 เพลง",
    "C": "#3 ทั้งหมด 4 เพลง",
    "D": "เล่นสลับ"
  },
  "rewrite": {
    "question_stem": "Which playlist is directly above \"#1 Total 5 songs\"?",
    "A": "#4 Total 8 songs",
    "B": "#2 Total 6 songs",
    "C": "#3 Total 4 songs",
    "D": "Shuffle playback"
  }
}
```

## rel::3/music_3.jpg::th::ru

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "เพลย์ลิสต์ใดอยู่เหนือ \"#1 ทั้งหมด 5 เพลง\"?",
    "A": "#4 ทั้งหมด 8 เพลง",
    "B": "#2 ทั้งหมด 6 เพลง",
    "C": "#3 ทั้งหมด 4 เพลง",
    "D": "เล่นสลับ"
  },
  "rewrite": {
    "question_stem": "Плейлист, который находится выше «#1 Всего 5 треков»?",
    "A": "#4 Всего 8 треков",
    "B": "#2 Всего 6 треков",
    "C": "#3 Всего 4 трека",
    "D": "В случайном порядке"
  }
}
```

## rel::3/music_3.jpg::th::zh

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "เพลย์ลิสต์ใดอยู่เหนือ \"#1 ทั้งหมด 5 เพลง\"?",
    "A": "#4 ทั้งหมด 8 เพลง",
    "B": "#2 ทั้งหมด 6 เพลง",
    "C": "#3 ทั้งหมด 4 เพลง",
    "D": "เล่นสลับ"
  },
  "rewrite": {
    "question_stem": "哪个播放列表位于“#1 共5首歌”上方？",
    "A": "#4 共8首歌",
    "B": "#2 共6首歌",
    "C": "#3 共4首歌",
    "D": "随机播放"
  }
}
```

## rel::3/music_3.jpg::zh::en

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "哪个播放列表位于“#1 共5首歌”正上方？",
    "A": "#4 共8首歌",
    "B": "#2 共6首歌",
    "C": "#3 共4首歌",
    "D": "随机播放"
  },
  "rewrite": {
    "question_stem": "Which playlist is directly above \"#1 Total 5 songs\"?",
    "A": "#4 Total 8 songs",
    "B": "#2 Total 6 songs",
    "C": "#3 Total 4 songs",
    "D": "Shuffle playback"
  }
}
```

## rel::3/music_3.jpg::zh::ru

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "哪个播放列表位于“#1 共5首歌”正上方？",
    "A": "#4 共8首歌",
    "B": "#2 共6首歌",
    "C": "#3 共4首歌",
    "D": "随机播放"
  },
  "rewrite": {
    "question_stem": "Какой плейлист находится прямо над «#1 Всего 5 треков»?",
    "A": "#4 Всего 8 треков",
    "B": "#2 Всего 6 треков",
    "C": "#3 Всего 4 трека",
    "D": "В случайном порядке"
  }
}
```

## rel::3/music_3.jpg::zh::th

GT C; 문맥 경고: 없음.

```json
{
  "source": {
    "question_stem": "哪个播放列表位于“#1 共5首歌”正上方？",
    "A": "#4 共8首歌",
    "B": "#2 共6首歌",
    "C": "#3 共4首歌",
    "D": "随机播放"
  },
  "rewrite": {
    "question_stem": "哪个播放列表位于“#1 ทั้งหมด 5 เพลง”正上方？",
    "A": "#4 ทั้งหมด 8 เพลง",
    "B": "#2 ทั้งหมด 6 เพลง",
    "C": "#3 ทั้งหมด 4 เพลง",
    "D": "เล่นสุ่ม"
  }
}
```

## rel::4/google_play_8.jpg::ru::th

GT A; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "Какой параметр находится непосредственно выше опции «Использовать данные о местоположении устройства» в меню настроек?",
    "A": "Отзывы в Google Play",
    "B": "Google Play Instant",
    "C": "Уведомления",
    "D": "Настройки аккаунта и устройства"
  },
  "rewrite": {
    "question_stem": "Which option is directly above the \"Use device location data\" setting in the settings menu?",
    "A": "Google Play Reviews",
    "B": "Google Play Instant",
    "C": "Notifications",
    "D": "Account and device settings"
  }
}
```

## rel::4/google_play_8.jpg::th::zh

GT A; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "ตัวเลือกใดอยู่เหนือ \"ใช้ตำแหน่งของอุปกรณ์\" ในเมนูการตั้งค่า?",
    "A": "ความคิดเห็นเกี่ยวกับ Google Play Store",
    "B": "Google Play Instant",
    "C": "การแจ้งเตือน",
    "D": "การตั้งค่าบัญชีและอุปกรณ์"
  },
  "rewrite": {
    "question_stem": "以下哪一项位于“使用设备位置信息”设置项的上方？",
    "A": "Google Play 商店反馈",
    "B": "Google Play 免安装体验",
    "C": "通知",
    "D": "账号和设备偏好设置"
  }
}
```

## rel::4/google_play_8.jpg::zh::th

GT A; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "在设置菜单中，哪个设置位于“使用设备位置信息”选项的正上方？",
    "A": "Google Play 商店反馈",
    "B": "Google Play 免安装体验",
    "C": "通知",
    "D": "账号和设备偏好设置"
  },
  "rewrite": {
    "question_stem": "ในเมนูตั้งค่า ตัวเลือกใดอยู่ตรงด้านบนของตัวเลือก \"ใช้ข้อมูลตำแหน่งของอุปกรณ์\"?",
    "A": "Google Play Instant",
    "B": "ความคิดเห็นเกี่ยวกับ Google Play Store",
    "C": "รีม",
    "D": "การตั้งค่าบัญชีและอุปกรณ์"
  }
}
```

## rel::5/forest_2.jpg::th::ru

GT B; 문맥 경고: question_stem, A, B, C, D.

```json
{
  "source": {
    "question_stem": "องค์ประกอบใดอยู่ด้านล่างของป้ายความสำเร็จ \"นักปลูกมือใหม่\" โดยตรง?",
    "A": "ไอคอนลูกศรย้อนกลับ",
    "B": "ข้อความ \"เคลมรางวัลแล้ว\"",
    "C": "ปุ่ม \"แชร์\"",
    "D": "เวลา \"15:02\""
  },
  "rewrite": {
    "question_stem": "Какой элемент находится прямо под надписью достижения \"Начинающий плантатор\"?",
    "A": "Иконка стрелки назад",
    "B": "Текст \"Вы получили награду\"",
    "C": "Кнопка \"Поделиться\"",
    "D": "Время \"15:48\""
  }
}
```

## rel::5/forest_2.jpg::zh::ru

GT B; 문맥 경고: question_stem, A, B, C, D.

```json
{
  "source": {
    "question_stem": "哪个元素位于“戴上草帽”成就标签的正下方？",
    "A": "返回箭头图标",
    "B": "“奖励已领取”文本",
    "C": "“分享”按钮",
    "D": "时间“15:22”"
  },
  "rewrite": {
    "question_stem": "Какой элемент находится непосредственно под надписью «Начинающий плантатор»?",
    "A": "Иконка стрелки назад",
    "B": "Текст «Вы получили награду»",
    "C": "Кнопка «Поделиться»",
    "D": "Время «15:48»"
  }
}
```

## rel::5/message_2.jpg::en::th

GT C; 문맥 경고: 없음.

```json
{
  "source": {
    "question_stem": "Which toggle switch is located directly below the \"Smart message recognition\" option?",
    "A": "Verification code protection",
    "B": "Service messages",
    "C": "Card view",
    "D": "Send service messages to"
  },
  "rewrite": {
    "question_stem": "Which toggle switch is located directly below the \"การรับรู้ข้อความอัจฉริยะ\" option?",
    "A": "การป้องกันรหัสยืนยัน",
    "B": "ข้อความบริการ",
    "C": "การแสดงผลแบบบัตร",
    "D": "ส่งข้อความบริการไปยัง"
  }
}
```

## rel::5/message_2.jpg::ru::th

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "Какой переключатель находится прямо под опцией «Умное распознавание сообщений»?",
    "A": "Защита с помощью проверочных кодов",
    "B": "Сервисные сообщения",
    "C": "В виде карточек",
    "D": "Отправить сервисные сообщения на"
  },
  "rewrite": {
    "question_stem": "Which toggle is directly below the \"Smart message recognition\" option?",
    "A": "Protection with verification codes",
    "B": "Service messages",
    "C": "As cards",
    "D": "Send service messages to"
  }
}
```

## rel::5/message_2.jpg::zh::th

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "哪个切换开关位于“智能信息识别”选项的正下方？",
    "A": "验证码安全保护",
    "B": "服务信息",
    "C": "卡片化显示",
    "D": "接收服务信息的号码"
  },
  "rewrite": {
    "question_stem": "ซึ่งสวิตช์การเปิด-ปิดอยู่ตรงด้านล่างของตัวเลือก \"การรับรู้ข้อมูลอัจฉริยะ\"?",
    "A": "การป้องกันรหัสผ่าน",
    "B": "ข้อมูลบริการ",
    "C": "การจัดแสดงแบบบัตร",
    "D": "หมายเลขที่รับข้อมูลบริการ"
  }
}
```

## rel::5/phone_4.jpg::th::ru

GT A; 문맥 경고: 없음.

```json
{
  "source": {
    "question_stem": "Which option is directly below \"ชะลอการตอบกลับอัตโนมัติ\"?",
    "A": "กดปุ่มเปิดปิดเครื่องเพื่อวางสาย",
    "B": "รับสายอัตโนมัติเมื่อเชื่อมต่อกับอุปกรณ์เสียงจากภายนอก",
    "C": "Answer/End calls",
    "D": "บลูทูธหรือหูฟังแบบมีสาย และอุปกรณ์เสียงอื่น ๆ"
  },
  "rewrite": {
    "question_stem": "Which option is directly below \"Автоматически отвечать на вызовы при подключении к внешнему аудиоустройству\"?",
    "A": "Завершение вызова кнопкой питания",
    "B": "Автоматически отвечать на вызовы при подключении к внешнему аудиоустройству",
    "C": "Answer/End calls",
    "D": "Наушники проводные или Bluetooth и другие аудиоустройства"
  }
}
```

## rel::5/phone_4.jpg::zh::th

GT A; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "哪个选项在“自动接听延时”下面？",
    "A": "按电源键结束通话",
    "B": "连接外部设备时自动接听",
    "C": "接听/挂断通话",
    "D": "蓝牙耳机、线控耳机等设备"
  },
  "rewrite": {
    "question_stem": "ซึ่งตัวเลือกอยู่ใต้ \"การตั้งค่าการตอบกลับอัตโนมัติ\"",
    "A": "กดปุ่มเปิดปิดเครื่องเพื่อวางสาย",
    "B": "ใช้ได้เฉพาะขณะเปิดหน้าจอ",
    "C": "สั่นเมื่ออีกฝ่ายรับ/วางสาย",
    "D": "ใช้ได้เฉพาะขณะเปิดหน้าจอ"
  }
}
```

## rel::5/record_2.jpg::en::th

GT C; 문맥 경고: 없음.

```json
{
  "source": {
    "question_stem": "Which option is located immediately below \"Set as alarm ringtone\" on the interface?",
    "A": "Set as call ringtone",
    "B": "Set as message tone",
    "C": "Set as contact ringtone",
    "D": "Cancel"
  },
  "rewrite": {
    "question_stem": "Which option is located immediately below \"ตั้งเป็นเสียงเรียกเข้า\" on the interface?",
    "A": "ตั้งค่าเป็นน ringing โทรศัพท์สำหรับชั่วคราว",
    "B": "ตั้งเป็นเสียงปลุก",
    "C": "ตั้งเป็นเสียงเรียกเข้าของรายชื่อ",
    "D": "ยกเลิก"
  }
}
```

## rel::5/record_2.jpg::ru::th

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "Какой вариант находится сразу под \"Задать как сигнал будильника\" на интерфейсе?",
    "A": "Задать как рингтон вызова",
    "B": "Задать как сигнал сообщения",
    "C": "Задать как сигнал для контакта",
    "D": "Отмена"
  },
  "rewrite": {
    "question_stem": "ตัวเลือกใดอยู่ตรงด้านล่างของ \"ตั้งเป็นเสียงเรียกเข้า\" บนอินเทอร์เฟซ?",
    "A": "ตั้งค่าเป็นริงโทนสำหรับข้อความ",
    "B": "ตั้งเป็นเสียงปลุก",
    "C": "ตั้งเป็นเสียงเรียกเข้าของรายชื่อ",
    "D": "ยกเลิก"
  }
}
```

## rel::5/record_2.jpg::th::en

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "ตัวเลือกใดอยู่ด้านล่างทันทีของ \"ตั้งเป็นเสียงเรียกเข้า\" ในอินเทอร์เฟซ?",
    "A": "ตั้งค่าเป็นริงโทนสำหรับข้อความ",
    "B": "ตั้งเป็นเสียงปลุก",
    "C": "ตั้งเป็นเสียงเรียกเข้าของรายชื่อ",
    "D": "ยกเลิก"
  },
  "rewrite": {
    "question_stem": "Which option is directly below \"Set as call ringtone\" in the interface?",
    "A": "Set as message tone",
    "B": "Set as alarm ringtone",
    "C": "Set as contact ringtone",
    "D": "Cancel"
  }
}
```

## rel::5/record_2.jpg::th::ru

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "ตัวเลือกใดอยู่ด้านล่างทันทีของ \"ตั้งเป็นเสียงเรียกเข้า\" ในอินเทอร์เฟซ?",
    "A": "ตั้งค่าเป็นริงโทนสำหรับข้อความ",
    "B": "ตั้งเป็นเสียงปลุก",
    "C": "ตั้งเป็นเสียงเรียกเข้าของรายชื่อ",
    "D": "ยกเลิก"
  },
  "rewrite": {
    "question_stem": "Какой элемент находится непосредственно под \"Задать как рингтон вызова\" в интерфейсе?",
    "A": "Задать как сигнал сообщения",
    "B": "Задать как сигнал будильника",
    "C": "Задать как сигнал для контакта",
    "D": "Отмена"
  }
}
```

## rel::5/record_2.jpg::th::zh

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "ตัวเลือกใดอยู่ด้านล่างทันทีของ \"ตั้งเป็นเสียงเรียกเข้า\" ในอินเทอร์เฟซ?",
    "A": "ตั้งค่าเป็นริงโทนสำหรับข้อความ",
    "B": "ตั้งเป็นเสียงปลุก",
    "C": "ตั้งเป็นเสียงเรียกเข้าของรายชื่อ",
    "D": "ยกเลิก"
  },
  "rewrite": {
    "question_stem": "以下哪个选项直接位于“设为电话铃声”下方？",
    "A": "设为信息铃声",
    "B": "设为闹钟铃声",
    "C": "设为联系人铃声",
    "D": "取消"
  }
}
```

## rel::5/record_2.jpg::zh::th

GT C; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "哪个选项位于界面上“设为闹钟铃声”正下方？",
    "A": "设为电话铃声",
    "B": "设为信息铃声",
    "C": "设为联系人铃声",
    "D": "取消"
  },
  "rewrite": {
    "question_stem": "ตัวเลือกใดอยู่ตรงด้านล่างของ \"ตั้งเป็นเสียงเรียกเข้า\"?",
    "A": "ตั้งค่าเป็นริงโทนสำหรับข้อความ",
    "B": "ตั้งเป็นเสียงปลุก",
    "C": "ตั้งเป็นเสียงเรียกเข้าของรายชื่อ",
    "D": "ยกเลิก"
  }
}
```

## rel::6/camera_8.jpg::ru::th

GT A; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "Какой режим находится непосредственно слева от режима \"ФОТО\" на этом пользовательском интерфейсе?",
    "A": "ВИДЕО",
    "B": "ПОРТРЕТ",
    "C": "КИНОЭФФЕКТ",
    "D": "ПАНОРАМА"
  },
  "rewrite": {
    "question_stem": "Which mode is directly to the left of the \"PHOTO\" mode on this user interface?",
    "A": "วิดีโอ",
    "B": "ภาพนิ่ง",
    "C": "รูปภาพ",
    "D": "ภาพถ่ายบุคคล"
  }
}
```

## rel::6/camera_8.jpg::ru::zh

GT A; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "Какой режим находится непосредственно слева от режима \"ФОТО\" на этом пользовательском интерфейсе?",
    "A": "ВИДЕО",
    "B": "ПОРТРЕТ",
    "C": "КИНОЭФФЕКТ",
    "D": "ПАНОРАМА"
  },
  "rewrite": {
    "question_stem": "哪个模式位于“照片”模式的正左侧？",
    "A": "视频",
    "B": "人像",
    "C": "电影效果",
    "D": "全景"
  }
}
```

## rel::6/camera_8.jpg::th::zh

GT A; 문맥 경고: question_stem.

```json
{
  "source": {
    "question_stem": "โหมดใดอยู่ทางซ้ายของโหมด \"รูปภาพ\" ในอินเทอร์เฟซผู้ใช้นี้?",
    "A": "วิดีโอ",
    "B": "ภาพถ่ายบุคคล",
    "C": "ภาพยนตร์",
    "D": "พาโน"
  },
  "rewrite": {
    "question_stem": "哪个模式位于“照片”模式的左侧？",
    "A": "视频",
    "B": "人像",
    "C": "电影效果",
    "D": "全景"
  }
}
```

## rel::6/wallet_6.jpg::en::ru

GT B; 문맥 경고: D.

```json
{
  "source": {
    "question_stem": "What element is located directly below the 'Nearby' label on the interface?",
    "A": "Search field",
    "B": "Jilin Transit Card",
    "C": "Beijing T-Union Transit Card",
    "D": "China label"
  },
  "rewrite": {
    "question_stem": "What element is located directly below the 'Назад' label on the interface?",
    "A": "Search field",
    "B": "Транспортная карта Jilin",
    "C": "Карта Chaozhou Transit Card",
    "D": "Китай континентальный"
  }
}
```

## rel::6/wallet_6.jpg::ru::en

GT B; 문맥 경고: question_stem, A.

```json
{
  "source": {
    "question_stem": "Какой элемент находится непосредственно под меткой 'Скоро' на интерфейсе?",
    "A": "Поле поиска",
    "B": "Транспортная карта Jilin",
    "C": "Beijing T-Union Transit Card",
    "D": "China label"
  },
  "rewrite": {
    "question_stem": "Which item is directly below the \"Back\" button on the interface?",
    "A": "Search field",
    "B": "Jilin Transit Card",
    "C": "Beijing T-Union Transit Card",
    "D": "China label"
  }
}
```

## rel::6/wallet_6.jpg::ru::th

GT B; 문맥 경고: question_stem, A.

```json
{
  "source": {
    "question_stem": "Какой элемент находится непосредственно под меткой 'Скоро' на интерфейсе?",
    "A": "Поле поиска",
    "B": "Транспортная карта Jilin",
    "C": "Beijing T-Union Transit Card",
    "D": "China label"
  },
  "rewrite": {
    "question_stem": "Which item is directly below the \"ย้อนกลับ\" button?",
    "A": "บัตรโดยสาร",
    "B": "บัตรโดยสารจีหลิน",
    "C": "บัตรโดยสาร Chaozhou",
    "D": "บัตรโดยสาร Heyuan"
  }
}
```

## rel::6/wallet_6.jpg::ru::zh

GT B; 문맥 경고: question_stem, A.

```json
{
  "source": {
    "question_stem": "Какой элемент находится непосредственно под меткой 'Скоро' на интерфейсе?",
    "A": "Поле поиска",
    "B": "Транспортная карта Jilin",
    "C": "Beijing T-Union Transit Card",
    "D": "China label"
  },
  "rewrite": {
    "question_stem": "哪个元素位于“返回”标签正下方？",
    "A": "搜索栏",
    "B": "吉林通",
    "C": "重庆畅通卡·交通联合版",
    "D": "中国"
  }
}
```

## rel::6/wallet_6.jpg::th::zh

GT B; 문맥 경고: question_stem, A, D.

```json
{
  "source": {
    "question_stem": "องค์ประกอบใดอยู่ด้านล่างของป้าย 'ใกล้เคียง' ในอินเทอร์เฟซ?",
    "A": "ช่องค้นหา",
    "B": "บัตรโดยสารจี๋หลิน",
    "C": "บัตรโดยสาร Beijing T-Union Transit Card",
    "D": "ป้าย China label"
  },
  "rewrite": {
    "question_stem": "哪个元素位于“附近”标签下方？",
    "A": "搜索栏",
    "B": "吉林通",
    "C": "重庆畅通卡·交通联合版",
    "D": "中国"
  }
}
```

## rel::6/wallet_6.jpg::zh::ru

GT B; 문맥 경고: D.

```json
{
  "source": {
    "question_stem": "界面上“附近”标签正下方的元素是什么？",
    "A": "搜索字段",
    "B": "吉林通",
    "C": "北京T-Union交通卡",
    "D": "中国标签"
  },
  "rewrite": {
    "question_stem": "界面上“Назад”标签正下方的元素是什么？",
    "A": "搜索字段",
    "B": "Транспортная карта Jilin",
    "C": "Карта Chaozhou Transit Card",
    "D": "Китай континентальный"
  }
}
```

## rel::6/wallet_8.jpg::en::ru

GT C; 문맥 경고: 없음.

```json
{
  "source": {
    "question_stem": "What is positioned immediately above the 'Find Apps for Wallet' text?",
    "A": "The battery indicator",
    "B": "The 'GET' button",
    "C": "The 'Boarding Passes and Tickets' text",
    "D": "The time display"
  },
  "rewrite": {
    "question_stem": "What is positioned immediately above the 'Найти приложения для Wallet' text?",
    "A": "The battery indicator",
    "B": "The 'GET' button",
    "C": "The 'Boarding Passes and Tickets' text",
    "D": "The time display"
  }
}
```

## rel::6/wallet_8.jpg::en::zh

GT C; 문맥 경고: 없음.

```json
{
  "source": {
    "question_stem": "What is positioned immediately above the 'Find Apps for Wallet' text?",
    "A": "The battery indicator",
    "B": "The 'GET' button",
    "C": "The 'Boarding Passes and Tickets' text",
    "D": "The time display"
  },
  "rewrite": {
    "question_stem": "What is positioned immediately above the '查找钱包适用 App' text?",
    "A": "The battery indicator",
    "B": "The '获取' button",
    "C": "The '收纳登机牌和票券' text",
    "D": "The time display"
  }
}
```

## rel::6/wallet_8.jpg::ru::en

GT C; 문맥 경고: question_stem, A, B, C, D.

```json
{
  "source": {
    "question_stem": "Что находится непосредственно выше текста «Найти приложения для Wallet»?",
    "A": "Индикатор батареи",
    "B": "Кнопка «ЗАГРУЗИТЬ»",
    "C": "Текст «Все мои билеты и поса...»",
    "D": "Отображение времени"
  },
  "rewrite": {
    "question_stem": "What is directly above the text \"Find Apps for Wallet\"?",
    "A": "Battery indicator",
    "B": "GET button",
    "C": "Text \"All in One Place\"",
    "D": "Time display"
  }
}
```

## rel::6/wallet_8.jpg::ru::th

GT C; 문맥 경고: question_stem, A, B, C, D.

```json
{
  "source": {
    "question_stem": "Что находится непосредственно выше текста «Найти приложения для Wallet»?",
    "A": "Индикатор батареи",
    "B": "Кнопка «ЗАГРУЗИТЬ»",
    "C": "Текст «Все мои билеты и поса...»",
    "D": "Отображение времени"
  },
  "rewrite": {
    "question_stem": "อะไรอยู่ตรงด้านบนของข้อความ \"ค้นหาแอปสำหรับกระเป๋าเงิน\"?",
    "A": "ไอคอนแบตเตอรี่",
    "B": "ปุ่ม \"รับ\"",
    "C": "ข้อความ \"ค้นหาแอปสำหรับกระเป๋าเงิน\"",
    "D": "การแสดงเวลา"
  }
}
```

## rel::6/wallet_8.jpg::ru::zh

GT C; 문맥 경고: question_stem, A, B, C, D.

```json
{
  "source": {
    "question_stem": "Что находится непосредственно выше текста «Найти приложения для Wallet»?",
    "A": "Индикатор батареи",
    "B": "Кнопка «ЗАГРУЗИТЬ»",
    "C": "Текст «Все мои билеты и поса...»",
    "D": "Отображение времени"
  },
  "rewrite": {
    "question_stem": "什么位于“查找钱包适用 App”文字的正上方？",
    "A": "电池指示器",
    "B": "获取按钮",
    "C": "文本“集中一处 收纳登机牌和票券”",
    "D": "时间显示"
  }
}
```

## rel::6/wallet_8.jpg::th::en

GT C; 문맥 경고: question_stem, A, B, C, D.

```json
{
  "source": {
    "question_stem": "มีอะไรอยู่เหนือข้อความ 'ค้นหาแอปสำหรับกระเป๋าสตางค์' โดยตรง?",
    "A": "ตัวบอกสถานะแบตเตอรี่",
    "B": "ปุ่ม 'รับ'",
    "C": "ข้อความ 'บัตรขึ้นเครื่องและตั๋วหรือบัตรต่างๆในที่เดียวกัน'",
    "D": "การแสดงเวลา"
  },
  "rewrite": {
    "question_stem": "What is directly above the \"Find Apps for Wallet\" message?",
    "A": "Battery status indicator",
    "B": "GET button",
    "C": "Message \"Boarding Passes and Tickets All in One Place\"",
    "D": "Time display"
  }
}
```

## rel::6/wallet_8.jpg::th::zh

GT C; 문맥 경고: question_stem, A, B, C, D.

```json
{
  "source": {
    "question_stem": "มีอะไรอยู่เหนือข้อความ 'ค้นหาแอปสำหรับกระเป๋าสตางค์' โดยตรง?",
    "A": "ตัวบอกสถานะแบตเตอรี่",
    "B": "ปุ่ม 'รับ'",
    "C": "ข้อความ 'บัตรขึ้นเครื่องและตั๋วหรือบัตรต่างๆในที่เดียวกัน'",
    "D": "การแสดงเวลา"
  },
  "rewrite": {
    "question_stem": "有哪个元素直接位于“查找钱包适用 App”文字的上方?",
    "A": "电池状态指示器",
    "B": "“获取”按钮",
    "C": "“集中一处 收纳登机牌和票券”文字",
    "D": "时间显示"
  }
}
```

## rel::6/wallet_8.jpg::zh::en

GT C; 문맥 경고: question_stem, A, B, C, D.

```json
{
  "source": {
    "question_stem": "什么位于“查找钱包适用 App”文本的正上方？",
    "A": "电池指示器",
    "B": "“获取”按钮",
    "C": "“收纳登机牌和票券”文本",
    "D": "时间显示"
  },
  "rewrite": {
    "question_stem": "What is directly above the \"Find Apps for Wallet\" text?",
    "A": "Battery indicator",
    "B": "GET button",
    "C": "Boarding Passes and Tickets text",
    "D": "Time display"
  }
}
```

## rel::6/wallet_8.jpg::zh::ru

GT C; 문맥 경고: question_stem, A, B, C, D.

```json
{
  "source": {
    "question_stem": "什么位于“查找钱包适用 App”文本的正上方？",
    "A": "电池指示器",
    "B": "“获取”按钮",
    "C": "“收纳登机牌和票券”文本",
    "D": "时间显示"
  },
  "rewrite": {
    "question_stem": "Что находится непосредственно над текстом «Найти приложения для Wallet»?",
    "A": "Индикатор батареи",
    "B": "«Загрузить» кнопка",
    "C": "Текст «Все мои билеты и посадочные талоны»",
    "D": "Отображение времени"
  }
}
```

## rel::6/wallet_8.jpg::zh::th

GT C; 문맥 경고: question_stem, A, B, C, D.

```json
{
  "source": {
    "question_stem": "什么位于“查找钱包适用 App”文本的正上方？",
    "A": "电池指示器",
    "B": "“获取”按钮",
    "C": "“收纳登机牌和票券”文本",
    "D": "时间显示"
  },
  "rewrite": {
    "question_stem": "อะไรอยู่ตรงด้านบนของข้อความ \"ค้นหาแอปสำหรับกระเป๋าสตางค์\"?",
    "A": "ไอคอนแบตเตอรี่",
    "B": "ปุ่ม \"รับ\"",
    "C": "ข้อความ \"ค้นหาแอปและเริ่มเก็บรวบรวมบัตรของคุณ\"",
    "D": "การแสดงเวลา"
  }
}
```
