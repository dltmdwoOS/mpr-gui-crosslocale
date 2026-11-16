# Screenshot 직접 rewrite: 전체288쌍 예측

| Pair | Split | GT | O | 새 rewrite | Inventory 통합 | 상태 | 문맥 경고 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `rel::1/booking_1.jpg::en::zh` | pilot | B | A | C | A | success | pilot 미검사 |
| `rel::1/booking_1.jpg::ru::en` | pilot | B | B | A | B | success | pilot 미검사 |
| `rel::1/booking_1.jpg::th::ru` | pilot | B | B | B | B | success | pilot 미검사 |
| `rel::1/booking_1.jpg::zh::th` | pilot | B | C | B | B | success | pilot 미검사 |
| `rel::1/booking_10.jpg::en::zh` | pilot | B | A | A | A | success | pilot 미검사 |
| `rel::1/booking_10.jpg::ru::en` | pilot | B | C | C | C | success | pilot 미검사 |
| `rel::1/booking_10.jpg::th::ru` | pilot | B | D | B | D | success | pilot 미검사 |
| `rel::1/booking_10.jpg::zh::th` | pilot | B | B | A | D | success | pilot 미검사 |
| `rel::2/calendar_6.png::en::ru` | main | B | B | B | B | success |  |
| `rel::2/calendar_6.png::en::th` | main | B | C | C | C | success |  |
| `rel::2/calendar_6.png::en::zh` | main | B | B | B | B | success |  |
| `rel::2/calendar_6.png::ru::en` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::2/calendar_6.png::ru::th` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::2/calendar_6.png::ru::zh` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::2/calendar_6.png::th::en` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::2/calendar_6.png::th::ru` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::2/calendar_6.png::th::zh` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::2/calendar_6.png::zh::en` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::2/calendar_6.png::zh::ru` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::2/calendar_6.png::zh::th` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::2/clock_10.png::en::zh` | pilot | A | A | A | A | success | pilot 미검사 |
| `rel::2/clock_10.png::ru::en` | pilot | A | A | A | A | success | pilot 미검사 |
| `rel::2/clock_10.png::th::ru` | pilot | A | A | A | A | success | pilot 미검사 |
| `rel::2/clock_10.png::zh::th` | pilot | A | A | A | A | success | pilot 미검사 |
| `rel::2/map_9.png::en::ru` | main | A | A | A | A | success |  |
| `rel::2/map_9.png::en::th` | main | A | C | A | A | success |  |
| `rel::2/map_9.png::en::zh` | main | A | A | A | A | success |  |
| `rel::2/map_9.png::ru::en` | main | A | A | A | A | success | question_stem |
| `rel::2/map_9.png::ru::th` | main | A | C | B | B | success | question_stem |
| `rel::2/map_9.png::ru::zh` | main | A | A | A | A | success | question_stem |
| `rel::2/map_9.png::th::en` | main | A | A | B | B | success | question_stem |
| `rel::2/map_9.png::th::ru` | main | A | A | B | B | success | question_stem |
| `rel::2/map_9.png::th::zh` | main | A | A | B | B | success | question_stem |
| `rel::2/map_9.png::zh::en` | main | A | A | A | A | success | question_stem |
| `rel::2/map_9.png::zh::ru` | main | A | A | A | A | success | question_stem |
| `rel::2/map_9.png::zh::th` | main | A | C | A | B | success |  |
| `rel::2/note_1.png::en::ru` | main | A | A | A | A | success | B |
| `rel::2/note_1.png::en::th` | main | A | A | B | A | success |  |
| `rel::2/note_1.png::en::zh` | main | A | A | A | A | success |  |
| `rel::2/note_1.png::ru::en` | main | A | A | A | A | success | question_stem, C, D |
| `rel::2/note_1.png::ru::th` | main | A | B | B | A | success | question_stem, C, D |
| `rel::2/note_1.png::ru::zh` | main | A | A | A | A | success | question_stem, C, D |
| `rel::2/note_1.png::th::en` | main | A | A | A | A | success | question_stem, C, D |
| `rel::2/note_1.png::th::ru` | main | A | A | A | A | success | question_stem, C, D |
| `rel::2/note_1.png::th::zh` | main | A | A | A | A | success | question_stem, C, D |
| `rel::2/note_1.png::zh::en` | main | A | A | A | A | success | question_stem, B, C, D |
| `rel::2/note_1.png::zh::ru` | main | A | A | A | A | success | question_stem, B, C, D |
| `rel::2/note_1.png::zh::th` | main | A | A | B | A | success | B |
| `rel::2/note_8.png::en::ru` | main | A | A | A | A | success |  |
| `rel::2/note_8.png::en::th` | main | A | B | A | D | success |  |
| `rel::2/note_8.png::en::zh` | main | A | A | A | A | success | D |
| `rel::2/note_8.png::ru::en` | main | A | A | A | A | success | question_stem, D |
| `rel::2/note_8.png::ru::th` | main | A | D | B | D | success | question_stem, D |
| `rel::2/note_8.png::ru::zh` | main | A | A | A | A | success | question_stem, D |
| `rel::2/note_8.png::th::en` | main | A | A | A | A | success | question_stem, D |
| `rel::2/note_8.png::th::ru` | main | A | A | A | A | success | question_stem, D |
| `rel::2/note_8.png::th::zh` | main | A | A | A | A | success | question_stem, D |
| `rel::2/note_8.png::zh::en` | main | A | A | A | A | success | question_stem, D |
| `rel::2/note_8.png::zh::ru` | main | A | A | A | A | success | question_stem, D |
| `rel::2/note_8.png::zh::th` | main | A | D | A | C | success | question_stem, D |
| `rel::2/setting_3.png::en::ru` | main | A | A | A | C | success |  |
| `rel::2/setting_3.png::en::th` | main | A | D | D | A | success |  |
| `rel::2/setting_3.png::en::zh` | main | A | A | A | A | success |  |
| `rel::2/setting_3.png::ru::en` | main | A | B | A | A | success | question_stem |
| `rel::2/setting_3.png::ru::th` | main | A | B | A | A | success | question_stem |
| `rel::2/setting_3.png::ru::zh` | main | A | B | A | A | success | question_stem |
| `rel::2/setting_3.png::th::en` | main | A | B | A | A | success | question_stem |
| `rel::2/setting_3.png::th::ru` | main | A | B | A | A | success | question_stem |
| `rel::2/setting_3.png::th::zh` | main | A | B | A | A | success | question_stem |
| `rel::2/setting_3.png::zh::en` | main | A | A | A | A | success | question_stem |
| `rel::2/setting_3.png::zh::ru` | main | A | A | A | C | success | question_stem |
| `rel::2/setting_3.png::zh::th` | main | A | A | B | C | success |  |
| `rel::2/weather_3.png::en::zh` | pilot | B | B | B | B | success | pilot 미검사 |
| `rel::2/weather_3.png::ru::en` | pilot | B | B | B | B | success | pilot 미검사 |
| `rel::2/weather_3.png::th::ru` | pilot | B | B | B | B | success | pilot 미검사 |
| `rel::2/weather_3.png::zh::th` | pilot | B | B | B | B | success | pilot 미검사 |
| `rel::3/homescreen_3.jpg::en::ru` | main | B | B | B | B | success |  |
| `rel::3/homescreen_3.jpg::en::th` | main | B | A | B | A | success |  |
| `rel::3/homescreen_3.jpg::en::zh` | main | B | B | B | B | success |  |
| `rel::3/homescreen_3.jpg::ru::en` | main | B | B | B | B | success | question_stem |
| `rel::3/homescreen_3.jpg::ru::th` | main | B | A | A | A | success | question_stem |
| `rel::3/homescreen_3.jpg::ru::zh` | main | B | B | B | B | success | question_stem |
| `rel::3/homescreen_3.jpg::th::en` | main | B | B | B | B | success | question_stem |
| `rel::3/homescreen_3.jpg::th::ru` | main | B | B | B | B | success | question_stem |
| `rel::3/homescreen_3.jpg::th::zh` | main | B | B | B | B | success | question_stem |
| `rel::3/homescreen_3.jpg::zh::en` | main | B | B | B | B | success | question_stem |
| `rel::3/homescreen_3.jpg::zh::ru` | main | B | B | A | B | success | question_stem |
| `rel::3/homescreen_3.jpg::zh::th` | main | B | A | A | B | success | question_stem |
| `rel::3/homescreen_5.jpg::en::ru` | main | B | C | B | A | success |  |
| `rel::3/homescreen_5.jpg::en::th` | main | B | C | C | A | success |  |
| `rel::3/homescreen_5.jpg::en::zh` | main | B | C | B | B | success |  |
| `rel::3/homescreen_5.jpg::ru::en` | main | B | B | B | B | success | question_stem |
| `rel::3/homescreen_5.jpg::ru::th` | main | B | A | B | B | success | question_stem |
| `rel::3/homescreen_5.jpg::ru::zh` | main | B | B | B | B | success | question_stem |
| `rel::3/homescreen_5.jpg::th::en` | main | B | C | B | C | success | question_stem |
| `rel::3/homescreen_5.jpg::th::ru` | main | B | C | B | C | success | question_stem |
| `rel::3/homescreen_5.jpg::th::zh` | main | B | C | C | C | success | question_stem |
| `rel::3/homescreen_5.jpg::zh::en` | main | B | B | B | B | success | question_stem |
| `rel::3/homescreen_5.jpg::zh::ru` | main | B | B | B | B | success | question_stem |
| `rel::3/homescreen_5.jpg::zh::th` | main | B | A | C | B | success | question_stem |
| `rel::3/map_4.jpg::en::ru` | main | C | C | A | C | success |  |
| `rel::3/map_4.jpg::en::th` | main | C | A | C | C | success |  |
| `rel::3/map_4.jpg::en::zh` | main | C | C | C | C | success |  |
| `rel::3/map_4.jpg::ru::en` | main | C | C | C | C | success | question_stem |
| `rel::3/map_4.jpg::ru::th` | main | C | C | A | C | success | question_stem |
| `rel::3/map_4.jpg::ru::zh` | main | C | C | C | C | success | question_stem |
| `rel::3/map_4.jpg::th::en` | main | C | C | C | C | success | question_stem |
| `rel::3/map_4.jpg::th::ru` | main | C | C | C | C | success | question_stem |
| `rel::3/map_4.jpg::th::zh` | main | C | C | C | C | success | question_stem |
| `rel::3/map_4.jpg::zh::en` | main | C | C | C | C | success | question_stem |
| `rel::3/map_4.jpg::zh::ru` | main | C | D | A | C | success | question_stem |
| `rel::3/map_4.jpg::zh::th` | main | C | C | B | C | success | question_stem |
| `rel::3/map_6.jpg::en::ru` | main | B | B | B | B | success |  |
| `rel::3/map_6.jpg::en::th` | main | B | B | B | B | success |  |
| `rel::3/map_6.jpg::en::zh` | main | B | B | B | B | success |  |
| `rel::3/map_6.jpg::ru::en` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::3/map_6.jpg::ru::th` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::3/map_6.jpg::ru::zh` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::3/map_6.jpg::th::en` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::3/map_6.jpg::th::ru` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::3/map_6.jpg::th::zh` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::3/map_6.jpg::zh::en` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::3/map_6.jpg::zh::ru` | main | B | B | B | B | success | question_stem |
| `rel::3/map_6.jpg::zh::th` | main | B | A | B | A | success | question_stem, A, B, C, D |
| `rel::3/music_10.jpg::en::ru` | main | A | A | A | A | success |  |
| `rel::3/music_10.jpg::en::th` | main | A | A | A | A | success |  |
| `rel::3/music_10.jpg::en::zh` | main | A | A | A | A | success |  |
| `rel::3/music_10.jpg::ru::en` | main | A | A | A | A | success | question_stem |
| `rel::3/music_10.jpg::ru::th` | main | A | A | A | A | success | question_stem |
| `rel::3/music_10.jpg::ru::zh` | main | A | A | A | A | success | question_stem |
| `rel::3/music_10.jpg::th::en` | main | A | A | A | A | success | question_stem |
| `rel::3/music_10.jpg::th::ru` | main | A | A | A | A | success | question_stem |
| `rel::3/music_10.jpg::th::zh` | main | A | A | A | A | success | question_stem |
| `rel::3/music_10.jpg::zh::en` | main | A | A | A | A | success | question_stem |
| `rel::3/music_10.jpg::zh::ru` | main | A | A | A | A | success | question_stem |
| `rel::3/music_10.jpg::zh::th` | main | A | A | D | A | success |  |
| `rel::3/music_3.jpg::en::ru` | main | C | B | B | B | success |  |
| `rel::3/music_3.jpg::en::th` | main | C | B | B | B | success |  |
| `rel::3/music_3.jpg::en::zh` | main | C | B | B | B | success |  |
| `rel::3/music_3.jpg::ru::en` | main | C | B | B | B | success | question_stem |
| `rel::3/music_3.jpg::ru::th` | main | C | B | B | B | success | question_stem |
| `rel::3/music_3.jpg::ru::zh` | main | C | B | B | B | success | question_stem |
| `rel::3/music_3.jpg::th::en` | main | C | B | B | C | success | question_stem |
| `rel::3/music_3.jpg::th::ru` | main | C | B | B | B | success | question_stem |
| `rel::3/music_3.jpg::th::zh` | main | C | B | B | B | success | question_stem |
| `rel::3/music_3.jpg::zh::en` | main | C | B | B | B | success | question_stem |
| `rel::3/music_3.jpg::zh::ru` | main | C | B | B | B | success | question_stem |
| `rel::3/music_3.jpg::zh::th` | main | C | B | B | B | success |  |
| `rel::3/music_7.jpg::en::zh` | pilot | A | A | A | A | success | pilot 미검사 |
| `rel::3/music_7.jpg::ru::en` | pilot | A | A | A | A | success | pilot 미검사 |
| `rel::3/music_7.jpg::th::ru` | pilot | A | C | A | C | success | pilot 미검사 |
| `rel::3/music_7.jpg::zh::th` | pilot | A | A | C | A | success | pilot 미검사 |
| `rel::3/settings_2.jpg::en::zh` | pilot | A | A | A | A | success | pilot 미검사 |
| `rel::3/settings_2.jpg::ru::en` | pilot | A | A | A | A | success | pilot 미검사 |
| `rel::3/settings_2.jpg::th::ru` | pilot | A | A | A | A | success | pilot 미검사 |
| `rel::3/settings_2.jpg::zh::th` | pilot | A | C | A | A | success | pilot 미검사 |
| `rel::4/Gmail_8.jpg::en::zh` | pilot | D | D | D | D | success | pilot 미검사 |
| `rel::4/Gmail_8.jpg::ru::en` | pilot | D | D | D | D | success | pilot 미검사 |
| `rel::4/Gmail_8.jpg::th::ru` | pilot | D | C | D | C | success | pilot 미검사 |
| `rel::4/Gmail_8.jpg::zh::th` | pilot | D | D | A | D | success | pilot 미검사 |
| `rel::4/google_play_6.jpg::en::ru` | main | A | A | A | A | success |  |
| `rel::4/google_play_6.jpg::en::th` | main | A | A | A | A | success |  |
| `rel::4/google_play_6.jpg::en::zh` | main | A | A | A | A | success |  |
| `rel::4/google_play_6.jpg::ru::en` | main | A | A | A | A | success | question_stem, A, B, C, D |
| `rel::4/google_play_6.jpg::ru::th` | main | A | A | A | A | success | question_stem, A, B, C, D |
| `rel::4/google_play_6.jpg::ru::zh` | main | A | A | A | A | success | question_stem, A, B, C, D |
| `rel::4/google_play_6.jpg::th::en` | main | A | A | A | A | success | question_stem, A, B, C, D |
| `rel::4/google_play_6.jpg::th::ru` | main | A | A | A | A | success | question_stem, A, B, C, D |
| `rel::4/google_play_6.jpg::th::zh` | main | A | A | A | A | success | question_stem, A, B, C, D |
| `rel::4/google_play_6.jpg::zh::en` | main | A | A | A | A | success | question_stem, A, B, C, D |
| `rel::4/google_play_6.jpg::zh::ru` | main | A | A | A | A | success | question_stem, A, B, C, D |
| `rel::4/google_play_6.jpg::zh::th` | main | A | A | A | A | success |  |
| `rel::4/google_play_8.jpg::en::ru` | main | A | A | A | A | success |  |
| `rel::4/google_play_8.jpg::en::th` | main | A | C | A | A | success |  |
| `rel::4/google_play_8.jpg::en::zh` | main | A | B | A | A | success |  |
| `rel::4/google_play_8.jpg::ru::en` | main | A | A | A | A | success | question_stem |
| `rel::4/google_play_8.jpg::ru::th` | main | A | B | B | A | success | question_stem |
| `rel::4/google_play_8.jpg::ru::zh` | main | A | B | A | A | success | question_stem |
| `rel::4/google_play_8.jpg::th::en` | main | A | A | A | A | success | question_stem |
| `rel::4/google_play_8.jpg::th::ru` | main | A | A | A | A | success | question_stem |
| `rel::4/google_play_8.jpg::th::zh` | main | A | A | B | A | success | question_stem |
| `rel::4/google_play_8.jpg::zh::en` | main | A | B | A | A | success | question_stem |
| `rel::4/google_play_8.jpg::zh::ru` | main | A | B | A | A | success | question_stem |
| `rel::4/google_play_8.jpg::zh::th` | main | A | B | B | B | success | question_stem |
| `rel::4/twitter_6.jpg::en::zh` | pilot | A | A | A | A | success | pilot 미검사 |
| `rel::4/twitter_6.jpg::ru::en` | pilot | A | A | A | A | success | pilot 미검사 |
| `rel::4/twitter_6.jpg::th::ru` | pilot | A | A | A | A | success | pilot 미검사 |
| `rel::4/twitter_6.jpg::zh::th` | pilot | A | D | D | C | success | pilot 미검사 |
| `rel::5/camera_1.jpg::en::zh` | pilot | C | C | C | C | success | pilot 미검사 |
| `rel::5/camera_1.jpg::ru::en` | pilot | C | C | C | C | success | pilot 미검사 |
| `rel::5/camera_1.jpg::th::ru` | pilot | C | D | C | C | success | pilot 미검사 |
| `rel::5/camera_1.jpg::zh::th` | pilot | C | D | A | D | success | pilot 미검사 |
| `rel::5/forest_2.jpg::en::ru` | main | B | B | B | B | success |  |
| `rel::5/forest_2.jpg::en::th` | main | B | B | B | B | success |  |
| `rel::5/forest_2.jpg::en::zh` | main | B | B | B | B | success |  |
| `rel::5/forest_2.jpg::ru::en` | main | B | C | B | D | success | question_stem, A, B, C, D |
| `rel::5/forest_2.jpg::ru::th` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::5/forest_2.jpg::ru::zh` | main | B | C | B | D | success | question_stem, A, B, C, D |
| `rel::5/forest_2.jpg::th::en` | main | B | C | B | C | success | question_stem, A, B, C, D |
| `rel::5/forest_2.jpg::th::ru` | main | B | C | C | C | success | question_stem, A, B, C, D |
| `rel::5/forest_2.jpg::th::zh` | main | B | C | B | C | success | question_stem, A, B, C, D |
| `rel::5/forest_2.jpg::zh::en` | main | B | B | B | B | success | question_stem, A, B, C, D |
| `rel::5/forest_2.jpg::zh::ru` | main | B | C | C | C | success | question_stem, A, B, C, D |
| `rel::5/forest_2.jpg::zh::th` | main | B | B | B | A | success |  |
| `rel::5/message_1.jpg::en::zh` | pilot | A | A | A | A | success | pilot 미검사 |
| `rel::5/message_1.jpg::ru::en` | pilot | A | D | D | D | success | pilot 미검사 |
| `rel::5/message_1.jpg::th::ru` | pilot | A | B | D | D | success | pilot 미검사 |
| `rel::5/message_1.jpg::zh::th` | pilot | A | B | B | B | success | pilot 미검사 |
| `rel::5/message_2.jpg::en::ru` | main | C | C | C | C | success |  |
| `rel::5/message_2.jpg::en::th` | main | C | B | A | C | success |  |
| `rel::5/message_2.jpg::en::zh` | main | C | C | C | C | success |  |
| `rel::5/message_2.jpg::ru::en` | main | C | C | C | C | success | question_stem |
| `rel::5/message_2.jpg::ru::th` | main | C | B | B | C | success | question_stem |
| `rel::5/message_2.jpg::ru::zh` | main | C | C | C | C | success | question_stem |
| `rel::5/message_2.jpg::th::en` | main | C | C | C | C | success | question_stem |
| `rel::5/message_2.jpg::th::ru` | main | C | C | C | C | success | question_stem |
| `rel::5/message_2.jpg::th::zh` | main | C | A | C | C | success | question_stem |
| `rel::5/message_2.jpg::zh::en` | main | C | C | C | C | success | question_stem |
| `rel::5/message_2.jpg::zh::ru` | main | C | C | C | C | success | question_stem |
| `rel::5/message_2.jpg::zh::th` | main | C | C | B | C | success | question_stem |
| `rel::5/phone_4.jpg::en::ru` | main | A | A | A | A | success |  |
| `rel::5/phone_4.jpg::en::th` | main | A | A | A | A | success |  |
| `rel::5/phone_4.jpg::en::zh` | main | A | A | A | A | success |  |
| `rel::5/phone_4.jpg::ru::en` | main | A | A | A | A | success | question_stem |
| `rel::5/phone_4.jpg::ru::th` | main | A | C | A | A | success | question_stem |
| `rel::5/phone_4.jpg::ru::zh` | main | A | A | A | A | success | question_stem |
| `rel::5/phone_4.jpg::th::en` | main | A | A | A | A | success |  |
| `rel::5/phone_4.jpg::th::ru` | main | A | A | D | A | success |  |
| `rel::5/phone_4.jpg::th::zh` | main | A | A | A | A | success |  |
| `rel::5/phone_4.jpg::zh::en` | main | A | A | A | A | success | question_stem |
| `rel::5/phone_4.jpg::zh::ru` | main | A | A | A | D | success | question_stem |
| `rel::5/phone_4.jpg::zh::th` | main | A | B | C | A | success | question_stem |
| `rel::5/record_2.jpg::en::ru` | main | C | B | C | C | success |  |
| `rel::5/record_2.jpg::en::th` | main | C | A | A | C | success |  |
| `rel::5/record_2.jpg::en::zh` | main | C | C | C | C | success |  |
| `rel::5/record_2.jpg::ru::en` | main | C | C | C | C | success | question_stem |
| `rel::5/record_2.jpg::ru::th` | main | C | A | B | A | success | question_stem |
| `rel::5/record_2.jpg::ru::zh` | main | C | C | C | C | success | question_stem |
| `rel::5/record_2.jpg::th::en` | main | C | B | A | A | success | question_stem |
| `rel::5/record_2.jpg::th::ru` | main | C | A | A | A | success | question_stem |
| `rel::5/record_2.jpg::th::zh` | main | C | B | A | D | success | question_stem |
| `rel::5/record_2.jpg::zh::en` | main | C | C | C | C | success | question_stem |
| `rel::5/record_2.jpg::zh::ru` | main | C | C | C | C | success | question_stem |
| `rel::5/record_2.jpg::zh::th` | main | C | B | B | B | success | question_stem |
| `rel::6/camera_8.jpg::en::ru` | main | A | A | A | A | success |  |
| `rel::6/camera_8.jpg::en::th` | main | A | A | A | B | success |  |
| `rel::6/camera_8.jpg::en::zh` | main | A | A | A | A | success |  |
| `rel::6/camera_8.jpg::ru::en` | main | A | A | A | A | success | question_stem |
| `rel::6/camera_8.jpg::ru::th` | main | A | A | C | C | success | question_stem |
| `rel::6/camera_8.jpg::ru::zh` | main | A | A | C | A | success | question_stem |
| `rel::6/camera_8.jpg::th::en` | main | A | A | A | A | success | question_stem |
| `rel::6/camera_8.jpg::th::ru` | main | A | A | A | A | success | question_stem |
| `rel::6/camera_8.jpg::th::zh` | main | A | A | C | A | success | question_stem |
| `rel::6/camera_8.jpg::zh::en` | main | A | A | A | A | success | question_stem |
| `rel::6/camera_8.jpg::zh::ru` | main | A | A | A | A | success | question_stem |
| `rel::6/camera_8.jpg::zh::th` | main | A | A | A | A | success |  |
| `rel::6/safari_7.jpg::en::zh` | pilot | B | B | B | B | success | pilot 미검사 |
| `rel::6/safari_7.jpg::ru::en` | pilot | B | B | B | B | success | pilot 미검사 |
| `rel::6/safari_7.jpg::th::ru` | pilot | B | B | B | B | success | pilot 미검사 |
| `rel::6/safari_7.jpg::zh::th` | pilot | B | B | B | B | success | pilot 미검사 |
| `rel::6/wallet_3.jpg::en::zh` | pilot | D | A | D | A | success | pilot 미검사 |
| `rel::6/wallet_3.jpg::ru::en` | pilot | D | A | A | A | success | pilot 미검사 |
| `rel::6/wallet_3.jpg::th::ru` | pilot | D | D | D | D | no_op_no_changes | pilot 미검사 |
| `rel::6/wallet_3.jpg::zh::th` | pilot | D | A | D | D | success | pilot 미검사 |
| `rel::6/wallet_6.jpg::en::ru` | main | B | A | A | A | success | D |
| `rel::6/wallet_6.jpg::en::th` | main | B | B | B | B | success |  |
| `rel::6/wallet_6.jpg::en::zh` | main | B | B | B | B | success | D |
| `rel::6/wallet_6.jpg::ru::en` | main | B | B | D | D | success | question_stem, A |
| `rel::6/wallet_6.jpg::ru::th` | main | B | B | A | B | success | question_stem, A |
| `rel::6/wallet_6.jpg::ru::zh` | main | B | B | D | B | success | question_stem, A |
| `rel::6/wallet_6.jpg::th::en` | main | B | C | B | D | success | question_stem, A, D |
| `rel::6/wallet_6.jpg::th::ru` | main | B | B | B | B | success | question_stem, A, D |
| `rel::6/wallet_6.jpg::th::zh` | main | B | B | D | B | success | question_stem, A, D |
| `rel::6/wallet_6.jpg::zh::en` | main | B | D | B | B | success | question_stem, A, D |
| `rel::6/wallet_6.jpg::zh::ru` | main | B | B | D | A | success | D |
| `rel::6/wallet_6.jpg::zh::th` | main | B | A | B | C | success | D |
| `rel::6/wallet_8.jpg::en::ru` | main | C | B | B | B | success |  |
| `rel::6/wallet_8.jpg::en::th` | main | C | C | C | B | success |  |
| `rel::6/wallet_8.jpg::en::zh` | main | C | B | B | B | success |  |
| `rel::6/wallet_8.jpg::ru::en` | main | C | B | B | C | success | question_stem, A, B, C, D |
| `rel::6/wallet_8.jpg::ru::th` | main | C | D | B | C | success | question_stem, A, B, C, D |
| `rel::6/wallet_8.jpg::ru::zh` | main | C | B | B | B | success | question_stem, A, B, C, D |
| `rel::6/wallet_8.jpg::th::en` | main | C | B | B | B | success | question_stem, A, B, C, D |
| `rel::6/wallet_8.jpg::th::ru` | main | C | C | C | C | success | question_stem, A, B, C, D |
| `rel::6/wallet_8.jpg::th::zh` | main | C | B | B | B | success | question_stem, A, B, C, D |
| `rel::6/wallet_8.jpg::zh::en` | main | C | B | B | B | success | question_stem, A, B, C, D |
| `rel::6/wallet_8.jpg::zh::ru` | main | C | C | B | B | success | question_stem, A, B, C, D |
| `rel::6/wallet_8.jpg::zh::th` | main | C | C | B | B | success | question_stem, A, B, C, D |
