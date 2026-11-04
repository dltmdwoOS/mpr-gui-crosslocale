# Qwen 기준 요소 위치 지정 파일럿 결과

실행일: 2026-11-03. 보고서 갱신일: 2026-11-04. 모델은 `Qwen/Qwen2.5-VL-7B-Instruct`의 고정 revision `cc594898137f460bfe9f0759e9844b3ce807cfb5`이다. 기존 객관식 실험과 같은 이미지 픽셀 예산을 썼다. 잠금 파일럿 **12문항**만 사용했고 본 분석 158문항은 실행하지 않았다. 이미지 48개의 해시와 Qwen 프로세서의 실제 `image_grid_thw`를 확인했다. 출력 점은 최종 모델 입력의 절대 픽셀로 해석한 뒤 원본 이미지 좌표로 변환해 GT bbox 안에 있는지 채점했다.

갤러리의 화면은 [chenruihan의 MPR-GUI-Bench](https://huggingface.co/datasets/chenruihan/MPR-GUI-Bench) 이미지(고정 revision `c1edb808d424a2fa7bc4a2e601d39b431b04acd5`)에 GT와 예측점을 덧그린 **보기용 파생 이미지**다. 모델 추론과 채점에는 원본 이미지를 사용했다. 데이터셋에 표시된 [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) 조건이 이 화면에도 적용되며 저장소 코드의 MIT 라이선스로 바뀌지 않는다. [저장소의 제3자 데이터 안내](../../01_code/THIRD_PARTY_DATA.md)도 함께 참고한다.

**읽는 순서:** 아래의 입력·프롬프트 설명 → 버전별 결과 표 → 실패 해석 → 12문항 갤러리. 갤러리에는 사용한 **48개 화면 전체**, O/R 질문, 정답 범위, 개별 출력 판정이 있다. 처음 문항은 펼쳐 두었고 나머지는 문항 이름을 누르면 열린다.

## 실제로 모델에 준 것

- 파일럿은 12문항 × GUI 언어 4개 = **48개의 방향성 쌍**이다. 각 문항의 언어 방향은 `EN→ZH`, `ZH→TH`, `TH→RU`, `RU→EN`이며, 같은 GUI 이미지에 O/R을 한 번씩 물어 **96응답**을 계획했다. O는 기준 표현도 질문 언어이고, R은 `<ref>...</ref>` 안의 기준 표현만 GUI 언어다. 그 밖의 문장, 이미지, GT는 같다.
- 예를 들어 EN→ZH `booking_1`의 O 질문은 `In the row for selecting the number of guests, which input field is located directly above the horizontal center of the blue '<ref>Search</ref>' button?`이고, R 질문에서는 **Search→搜索**만 바뀐다. 모델에는 객관식 A–D 보기나 정답을 주지 않았다.
- 각 실행은 GUI 스크린샷 **1장**과 텍스트를 Qwen에 넣었다. 좌표는 Qwen이 실제로 받은 이미지 크기 기준의 **절대 픽셀**이다. 원본 GT와 직접 대조할 때는 `x원본=x출력×원본폭/모델폭`, `y원본=y출력×원본높이/모델높이`로 바꿨다. 예를 들어 `booking_1` EN 화면은 원본 1228×2700, 모델 입력 980×2128이다. 점이 GT bbox 안에 있어야 적중이다. JSON 파싱 실패는 오답으로 센다.
- 먼저 같은 언어의 질문과 GUI를 사용한 **양성 대조군 8개**를 실행했다. 대상은 `booking_1`과 `message_1`의 EN/ZH/TH/RU 화면이다. v2·v3는 이 단계에서 중지했다. 짧은 표현 진단만 게이트 실패를 명시한 상태에서 96개의 O/R 파일럿도 탐색적으로 실행했다.
- 모든 버전에서 동일한 Qwen revision, 이미지 픽셀 예산 262,144–2,097,152, greedy 생성(`do_sample=false`, `num_beams=1`, 최대 64 새 토큰)을 사용했다. 질문에 필요한 `{W}×{H}`는 전처리 결과 `image_grid_thw`에서 계산했다. 각 실행의 실제 전체 chat template와 원시 응답은 아래 JSONL에 보존했다.

## 프롬프트와 버전 차이

이전 설계 v1의 **0–1000 정규화 점** 요청은 Qwen2.5의 실제 절대 픽셀 좌표계와 맞지 않아 실행 전에 폐기했다. 아래 표의 **v2·v3·짧은 표현**만 실제 모델 응답이 있다.

| 버전 | 기준 요소 설명 | 지시 위치 | 요청 출력 | O/R 실행 |
| --- | --- | --- | --- | --- |
| **v2** | 관계 질문 전체와 `<ref>` 표시 | 명시적 system + user 질문 | `point_2d`와 `label`이 있는 배열 | 양성 대조 실패로 중지 |
| **v3** | 관계 질문 전체와 `<ref>` 표시. 관계의 답을 찾지 말라고 앞에서 명시 | user 메시지에 이미지·지시·질문 | `point_2d` 하나의 배열 | 양성 대조 실패로 중지 |
| **짧은 표현 진단** | 관계 질문에서 기준 요소를 가리키는 명사구만 추출. 같은 `<ref>` 표시 | user 메시지에 이미지·표현·지시 | v3와 같은 배열 | 선정된 12문항에서만 탐색 실행 |

v2의 **system 메시지 전체**는 다음과 같다. `{W}`·`{H}`에는 화면별 Qwen 입력 크기가 들어간다.

```text
Locate one reference element in the full GUI screenshot. The screenshot shown to you is {W} pixels wide and {H} pixels high. Return only this JSON array with exactly one object: [{"point_2d": [x, y], "label": "target"}]. x and y must be integer pixel coordinates on that screenshot, with (0, 0) at the top-left. Do not add any other text.
```

v2의 **user 메시지 텍스트 전체**는 다음과 같다. 텍스트 앞에 이미지 토큰이 붙는다.

```text
Question: {marked_stem}
Locate the reference GUI element described by the marked expression and its surrounding words. Do not answer the relation question.
```

v3에는 별도 명시적 system 메시지가 없다. Qwen chat template이 기본 `You are a helpful assistant.`를 삽입한다. **user 메시지 텍스트 전체**는 다음과 같다.

```text
Locate the GUI reference element marked with <ref>...</ref> in the question below. The marked expression may be in a different language from the screenshot. Use surrounding words to identify the marked element. Do not locate the element that the question asks for.
Question: {marked_stem}
The screenshot is {W} pixels wide and {H} pixels high. Give one point inside the marked reference element using integer pixel coordinates on this screenshot, with (0, 0) at the top-left. Return only this JSON array: [{"point_2d": [x, y]}]. No explanation or code fence.
```

짧은 표현 진단도 기본 system 메시지를 사용한다. **user 메시지 텍스트 전체**는 다음과 같다. `{descriptor}`는 원래 질문에 실제로 포함된 짧은 부분 문자열이다. 예를 들어 EN `booking_1`의 O는 `blue '<ref>Search</ref>' button`, R은 `blue '<ref>搜索</ref>' button`이다. 사용한 12×4개 표현 템플릿은 [별도 목록](pilot_referent_phrases.json)에 고정했다.

```text
Reference phrase: {descriptor}
Locate this GUI element in the screenshot. The phrase may be in a different language from the screenshot. The screenshot is {W} pixels wide and {H} pixels high. Give one point inside the element, using integer pixel coordinates with (0, 0) at the top-left. Return only this JSON array: [{"point_2d": [x, y]}]. No explanation or code fence.
```

v3와 짧은 표현 진단의 **출력 지시가 같아도 입력 질문은 다르다**. 짧은 표현 진단의 결과를 v3의 O/R 결과로 바꾸어 읽을 수 없다.

## 실행 순서와 게이트

사전 지정 게이트는 양성 대조군 8개 **전부 파싱 성공**, 그중 **6개 이상 적중**, 이후 O/R 파일럿 96개 중 **90개 이상 파싱 성공**이다. 어느 실행도 이 기준을 넘지 못했다.

| 입력 방식 | 양성 대조군 파싱 | 양성 대조군 적중 | O/R 파일럿 파싱 | O/R 파일럿 적중 | 판정 |
| --- | ---: | ---: | ---: | ---: | --- |
| v2: 전체 관계 질문, system 지시, 점과 label 요청 | 0/8 | 0/8 | 실행 안 함 | — | 중지 |
| v3: 전체 관계 질문, user 지시, 점만 요청 | 6/8 | 0/8 | 실행 안 함 | — | 중지 |
| 짧은 기준 표현 진단: 관계 질문에서 기준 요소를 묘사하는 부분만 추출 | 3/8 | 3/8 | 43/96 | O 20/48, R 23/48 | **탐색용**; 게이트 실패 |

양성 대조군의 화면별 결과는 다음과 같다. 점 좌표는 **Qwen 입력 이미지 픽셀**이며, `안/밖`은 원본 GT로 변환한 뒤 판정했다. 각 버전의 실제 원시 텍스트는 [v2 대조군](../results/grounding_pilot_qwen_v2/controls.jsonl), [v3 대조군](../results/grounding_pilot_qwen_v3/controls.jsonl), [짧은 표현 대조군](../results/grounding_pilot_qwen_phrase_v1/controls.jsonl)에 있다.

| 화면 | v2 | v3 | 짧은 표현 진단 |
| --- | --- | --- | --- |
| `booking_1` EN | 숫자 배열, 파싱 실패 | `[703,1024]` 밖 | `addCriterion`, 파싱 실패 |
| `booking_1` ZH | 불완전 숫자 배열 | 불완전 JSON | `addCriterion`, 파싱 실패 |
| `booking_1` TH | 불완전 숫자 배열 | `[665,1173]` 밖 | `[476,1315]` 안 |
| `booking_1` RU | 불완전 숫자 배열 | `[374,1165]` 밖 | `addCriterion`, 파싱 실패 |
| `message_1` EN | 코드 블록·추가 텍스트 | `[476,1173]` 밖 | `addCriterion`, 파싱 실패 |
| `message_1` ZH | 코드 블록·추가 텍스트 | `[476,1234]` 밖 | `[476,1360]` 안 |
| `message_1` TH | `addCriterion`·추가 텍스트 | 불완전 JSON | `addCriterion`, 파싱 실패 |
| `message_1` RU | 숫자 배열, 파싱 실패 | `[463,1207]` 밖 | `[374,1406]` 안 |

v2·v3는 O/R 응답을 생성하지 않았다. 두 실행의 원시 양성 대조 결과를 확인한 뒤, 관계 질문이 **답 요소**를 찍도록 유도하는지 검사하려고 파일럿 12문항에만 짧은 기준 표현을 수작업으로 추출했다. 이 진단에서는 게이트 실패를 명시하고도 선택된 파일럿 48쌍의 O/R **96응답**을 끝까지 생성했다. 짧은 표현은 잠금 질문의 정확한 부분 문자열이며 O/R 사이에서는 표시한 기준 span만 달라진다. 이 표현 목록은 158문항 전체에 준비되지 않았고, v3의 확증 결과와 합치지 않는다.

## 실패 양상

- v3에서 파싱된 양성 대조 6개는 모두 GT 상자를 벗어났다. `booking`과 `message` 화면의 점은 기준 요소보다 위쪽, 관계 질문의 답 후보 쪽이었다. 즉 문장 전체를 읽고 **기준 요소가 아닌 관계의 답**을 찾는 혼동이 실재한다.
- 짧은 표현 진단의 96응답 중 43개만 요청한 `[{"point_2d": [x, y]}]` 형식으로 파싱됐고, 이 43개는 전부 GT 안에 들었다. 나머지 53개 중 41개에는 `addCriterion` 반복이 있었다. 그 외에는 빈 배열 8개, 잘린 JSON 2개, 코드 블록 1개, 닫는 문자 오류 1개가 있었다. 생성 제한 64토큰에 도달한 응답은 29개였다. `addCriterion` 반복은 원시 출력에서 직접 관찰한 현상이며 원인은 아직 분리하지 못했다.
- 48쌍의 O/R 이행은 `0→0` 23, `0→1` 5, `1→0` 2, `1→1` 18이다. 정오가 바뀐 **7쌍 모두** 한 조건에서 좌표 자체를 파싱하지 못했기 때문에 생겼다. 유효한 점이 다른 GUI 요소로 이동해 발생한 이행은 관찰되지 않았다. 따라서 O 20/48과 R 23/48의 차이를 언어에 따른 위치 지정 개선으로 해석하면 안 된다.
- 짧은 표현 진단의 문항별 파싱 성공은 0/8부터 7/8까지 크게 달랐다. `weather_3`, `music_7`, `Gmail_8`에서는 유효 출력이 **0/8**이었다. 실패가 임의로 흩어진다고 가정할 수 없다.

## 결론과 후속 확인

현재 프롬프트와 생성 설정으로는 Qwen 위치 출력이 **기능 게이트를 통과하지 못한다**. 본 분석을 시작하지 않는다. 짧은 표현에서 유효한 점이 모두 맞았다는 결과는 좌표 역변환과 GT 연결이 적어도 일부 화면에서 작동한다는 작은 sanity check일 뿐, 파싱 실패 53개나 전체 질문의 목표 혼동을 해결하지 않는다.

다음 버전에서는 **모델 출력 형식의 안정성**과 **입력에서 기준 요소를 지정하는 방식**을 별개로 검증해야 한다. 특히 반복 토큰의 원인을 점검하고, 12문항 밖의 새 검증 표본에서 양성 대조와 형식 게이트를 다시 설정해야 한다. 이번 12문항의 O/R 차이를 보고 프롬프트를 선택하면 파일럿에 과적합된다.

원시 응답·렌더링된 프롬프트·이미지 해시·좌표 변환·채점은 각각 `followup_rel_4lang/results/grounding_pilot_qwen_v2/`, `..._v3/`, `..._phrase_v1/`에 남겼다. 짧은 표현 목록은 [`pilot_referent_phrases.json`](pilot_referent_phrases.json), 실행 코드는 [`run_qwen_pilot.py`](run_qwen_pilot.py)에 있다. 이 러너는 **양성 대조 8개와 파일럿 96개만** 읽는다.

개별 96응답의 원문·렌더링 프롬프트는 [짧은 표현 파일럿 JSONL](../results/grounding_pilot_qwen_phrase_v1/pilot.jsonl)에서 확인할 수 있다. 아래 갤러리는 [생성 스크립트](build_qwen_pilot_gallery.py)가 잠금 입력·이미지 해시·GT·저장된 채점을 검증한 뒤 만든 것이다.

<!-- QWEN_PILOT_GALLERY_START -->
## 파일럿 갤러리: 12문항 × 4 GUI 언어

각 이미지는 **원본 화면 전체**에 채점용 GT bbox를 빨간 테두리로 표시했다. 파란 원은 짧은 표현 진단의 유효한 O 점, 초록 X는 유효한 R 점이다. 양성 대조군 8개 화면의 주황 마름모는 v3에서 파싱된 점이다. 형식 오류로 점을 얻지 못한 경우에는 표시하지 않았다. 점을 겹쳐 찍은 경우 초록 X가 파란 원 안에 보인다. 이미지를 누르면 큰 크기로 열린다. GT 범위는 왼쪽 위 `(x1,y1)`부터 오른쪽 아래 `(x2,y2)`까지다.

아래 작은 이미지는 48개 화면을 한눈에 보는 목록이다. 각 이미지를 누르면 확대되며, 질문과 좌표 범위는 이어지는 문항별 상세 보기에서 확인할 수 있다.

| 문항 | EN GUI | ZH GUI | TH GUI | RU GUI | O/R 적중 · 유효 |
| --- | --- | --- | --- | --- | ---: |
| 01. `rel::1/booking_1.jpg` | <a href="qwen_pilot_gallery/pilot_01_en.webp"><img src="qwen_pilot_gallery/pilot_01_en.webp" alt="rel::1/booking_1.jpg en GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_01_zh.webp"><img src="qwen_pilot_gallery/pilot_01_zh.webp" alt="rel::1/booking_1.jpg zh GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_01_th.webp"><img src="qwen_pilot_gallery/pilot_01_th.webp" alt="rel::1/booking_1.jpg th GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_01_ru.webp"><img src="qwen_pilot_gallery/pilot_01_ru.webp" alt="rel::1/booking_1.jpg ru GT" width="110"></a> | O 1/4 · R 1/4 · 2/8 |
| 02. `rel::5/message_1.jpg` | <a href="qwen_pilot_gallery/pilot_02_en.webp"><img src="qwen_pilot_gallery/pilot_02_en.webp" alt="rel::5/message_1.jpg en GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_02_zh.webp"><img src="qwen_pilot_gallery/pilot_02_zh.webp" alt="rel::5/message_1.jpg zh GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_02_th.webp"><img src="qwen_pilot_gallery/pilot_02_th.webp" alt="rel::5/message_1.jpg th GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_02_ru.webp"><img src="qwen_pilot_gallery/pilot_02_ru.webp" alt="rel::5/message_1.jpg ru GT" width="110"></a> | O 1/4 · R 2/4 · 3/8 |
| 03. `rel::1/booking_10.jpg` | <a href="qwen_pilot_gallery/pilot_03_en.webp"><img src="qwen_pilot_gallery/pilot_03_en.webp" alt="rel::1/booking_10.jpg en GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_03_zh.webp"><img src="qwen_pilot_gallery/pilot_03_zh.webp" alt="rel::1/booking_10.jpg zh GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_03_th.webp"><img src="qwen_pilot_gallery/pilot_03_th.webp" alt="rel::1/booking_10.jpg th GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_03_ru.webp"><img src="qwen_pilot_gallery/pilot_03_ru.webp" alt="rel::1/booking_10.jpg ru GT" width="110"></a> | O 1/4 · R 1/4 · 2/8 |
| 04. `rel::2/clock_10.png` | <a href="qwen_pilot_gallery/pilot_04_en.webp"><img src="qwen_pilot_gallery/pilot_04_en.webp" alt="rel::2/clock_10.png en GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_04_zh.webp"><img src="qwen_pilot_gallery/pilot_04_zh.webp" alt="rel::2/clock_10.png zh GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_04_th.webp"><img src="qwen_pilot_gallery/pilot_04_th.webp" alt="rel::2/clock_10.png th GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_04_ru.webp"><img src="qwen_pilot_gallery/pilot_04_ru.webp" alt="rel::2/clock_10.png ru GT" width="110"></a> | O 3/4 · R 3/4 · 6/8 |
| 05. `rel::2/weather_3.png` | <a href="qwen_pilot_gallery/pilot_05_en.webp"><img src="qwen_pilot_gallery/pilot_05_en.webp" alt="rel::2/weather_3.png en GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_05_zh.webp"><img src="qwen_pilot_gallery/pilot_05_zh.webp" alt="rel::2/weather_3.png zh GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_05_th.webp"><img src="qwen_pilot_gallery/pilot_05_th.webp" alt="rel::2/weather_3.png th GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_05_ru.webp"><img src="qwen_pilot_gallery/pilot_05_ru.webp" alt="rel::2/weather_3.png ru GT" width="110"></a> | O 0/4 · R 0/4 · 0/8 |
| 06. `rel::3/music_7.jpg` | <a href="qwen_pilot_gallery/pilot_06_en.webp"><img src="qwen_pilot_gallery/pilot_06_en.webp" alt="rel::3/music_7.jpg en GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_06_zh.webp"><img src="qwen_pilot_gallery/pilot_06_zh.webp" alt="rel::3/music_7.jpg zh GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_06_th.webp"><img src="qwen_pilot_gallery/pilot_06_th.webp" alt="rel::3/music_7.jpg th GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_06_ru.webp"><img src="qwen_pilot_gallery/pilot_06_ru.webp" alt="rel::3/music_7.jpg ru GT" width="110"></a> | O 0/4 · R 0/4 · 0/8 |
| 07. `rel::3/settings_2.jpg` | <a href="qwen_pilot_gallery/pilot_07_en.webp"><img src="qwen_pilot_gallery/pilot_07_en.webp" alt="rel::3/settings_2.jpg en GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_07_zh.webp"><img src="qwen_pilot_gallery/pilot_07_zh.webp" alt="rel::3/settings_2.jpg zh GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_07_th.webp"><img src="qwen_pilot_gallery/pilot_07_th.webp" alt="rel::3/settings_2.jpg th GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_07_ru.webp"><img src="qwen_pilot_gallery/pilot_07_ru.webp" alt="rel::3/settings_2.jpg ru GT" width="110"></a> | O 3/4 · R 4/4 · 7/8 |
| 08. `rel::4/Gmail_8.jpg` | <a href="qwen_pilot_gallery/pilot_08_en.webp"><img src="qwen_pilot_gallery/pilot_08_en.webp" alt="rel::4/Gmail_8.jpg en GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_08_zh.webp"><img src="qwen_pilot_gallery/pilot_08_zh.webp" alt="rel::4/Gmail_8.jpg zh GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_08_th.webp"><img src="qwen_pilot_gallery/pilot_08_th.webp" alt="rel::4/Gmail_8.jpg th GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_08_ru.webp"><img src="qwen_pilot_gallery/pilot_08_ru.webp" alt="rel::4/Gmail_8.jpg ru GT" width="110"></a> | O 0/4 · R 0/4 · 0/8 |
| 09. `rel::4/twitter_6.jpg` | <a href="qwen_pilot_gallery/pilot_09_en.webp"><img src="qwen_pilot_gallery/pilot_09_en.webp" alt="rel::4/twitter_6.jpg en GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_09_zh.webp"><img src="qwen_pilot_gallery/pilot_09_zh.webp" alt="rel::4/twitter_6.jpg zh GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_09_th.webp"><img src="qwen_pilot_gallery/pilot_09_th.webp" alt="rel::4/twitter_6.jpg th GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_09_ru.webp"><img src="qwen_pilot_gallery/pilot_09_ru.webp" alt="rel::4/twitter_6.jpg ru GT" width="110"></a> | O 2/4 · R 3/4 · 5/8 |
| 10. `rel::5/camera_1.jpg` | <a href="qwen_pilot_gallery/pilot_10_en.webp"><img src="qwen_pilot_gallery/pilot_10_en.webp" alt="rel::5/camera_1.jpg en GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_10_zh.webp"><img src="qwen_pilot_gallery/pilot_10_zh.webp" alt="rel::5/camera_1.jpg zh GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_10_th.webp"><img src="qwen_pilot_gallery/pilot_10_th.webp" alt="rel::5/camera_1.jpg th GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_10_ru.webp"><img src="qwen_pilot_gallery/pilot_10_ru.webp" alt="rel::5/camera_1.jpg ru GT" width="110"></a> | O 2/4 · R 3/4 · 5/8 |
| 11. `rel::6/safari_7.jpg` | <a href="qwen_pilot_gallery/pilot_11_en.webp"><img src="qwen_pilot_gallery/pilot_11_en.webp" alt="rel::6/safari_7.jpg en GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_11_zh.webp"><img src="qwen_pilot_gallery/pilot_11_zh.webp" alt="rel::6/safari_7.jpg zh GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_11_th.webp"><img src="qwen_pilot_gallery/pilot_11_th.webp" alt="rel::6/safari_7.jpg th GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_11_ru.webp"><img src="qwen_pilot_gallery/pilot_11_ru.webp" alt="rel::6/safari_7.jpg ru GT" width="110"></a> | O 4/4 · R 2/4 · 6/8 |
| 12. `rel::6/wallet_3.jpg` | <a href="qwen_pilot_gallery/pilot_12_en.webp"><img src="qwen_pilot_gallery/pilot_12_en.webp" alt="rel::6/wallet_3.jpg en GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_12_zh.webp"><img src="qwen_pilot_gallery/pilot_12_zh.webp" alt="rel::6/wallet_3.jpg zh GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_12_th.webp"><img src="qwen_pilot_gallery/pilot_12_th.webp" alt="rel::6/wallet_3.jpg th GT" width="110"></a> | <a href="qwen_pilot_gallery/pilot_12_ru.webp"><img src="qwen_pilot_gallery/pilot_12_ru.webp" alt="rel::6/wallet_3.jpg ru GT" width="110"></a> | O 3/4 · R 4/4 · 7/8 |

<details open>
<summary><strong>01. rel::1/booking_1.jpg</strong> · O 1/4, R 1/4 · 유효 2/8 · 화면 4개</summary>

### EN GUI · RU→EN 질문

<a href="qwen_pilot_gallery/pilot_01_en.webp"><img src="qwen_pilot_gallery/pilot_01_en.webp" alt="rel::1/booking_1.jpg en GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[82, 1396]–[1155, 1569]` · 화면 1228×2700px
- **GT Qwen 좌표:** `[65.4, 1100.3]–[921.7, 1236.6]` · 입력 980×2128px
- **O 질문:** `В строке выбора количества гостей, какое поле ввода расположено прямо над горизонтальным центром синей кнопки '<ref>Найти</ref>'?`
- **R 질문:** `В строке выбора количества гостей, какое поле ввода расположено прямо над горизонтальным центром синей кнопки '<ref>Search</ref>'?`
- **진단용 짧은 표현:** O `синей кнопки '<ref>Найти</ref>'` / R `синей кнопки '<ref>Search</ref>'`
- **짧은 표현 결과:** O 파싱 실패 · 빈 배열 / R 파싱 실패 · addCriterion 반복/혼입
- **양성 대조 질문:** `In the row for selecting the number of guests, which input field is located directly above the horizontal center of the blue '<ref>Search</ref>' button?`
- **대조군 결과:** v2 파싱 실패 · 요청 형식이 아닌 숫자 배열 / v3 GT 밖 · `[703, 1024]` / 짧은 표현 파싱 실패 · addCriterion 반복/혼입

### ZH GUI · EN→ZH 질문

<a href="qwen_pilot_gallery/pilot_01_zh.webp"><img src="qwen_pilot_gallery/pilot_01_zh.webp" alt="rel::1/booking_1.jpg zh GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[76, 1584]–[1146, 1756]` · 화면 1228×2700px
- **GT Qwen 좌표:** `[60.7, 1248.4]–[914.6, 1384]` · 입력 980×2128px
- **O 질문:** `In the row for selecting the number of guests, which input field is located directly above the horizontal center of the blue '<ref>Search</ref>' button?`
- **R 질문:** `In the row for selecting the number of guests, which input field is located directly above the horizontal center of the blue '<ref>搜索</ref>' button?`
- **진단용 짧은 표현:** O `blue '<ref>Search</ref>' button` / R `blue '<ref>搜索</ref>' button`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · addCriterion 반복/혼입
- **양성 대조 질문:** `在选择客人数的行中，哪个输入字段位于蓝色“<ref>搜索</ref>”按钮的水平中心正上方？`
- **대조군 결과:** v2 파싱 실패 · 요청 형식이 아닌 숫자 배열 / v3 파싱 실패 · 불완전한 JSON / 짧은 표현 파싱 실패 · addCriterion 반복/혼입

### TH GUI · ZH→TH 질문

<a href="qwen_pilot_gallery/pilot_01_th.webp"><img src="qwen_pilot_gallery/pilot_01_th.webp" alt="rel::1/booking_1.jpg th GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[89, 1597]–[1156, 1755]` · 화면 1228×2700px
- **GT Qwen 좌표:** `[71, 1258.7]–[922.5, 1383.2]` · 입력 980×2128px
- **O 질문:** `在选择客人数的行中，哪个输入字段位于蓝色“<ref>搜索</ref>”按钮的水平中心正上方？`
- **R 질문:** `在选择客人数的行中，哪个输入字段位于蓝色“<ref>ค้นหา</ref>”按钮的水平中心正上方？`
- **진단용 짧은 표현:** O `蓝色“<ref>搜索</ref>”按钮` / R `蓝色“<ref>ค้นหา</ref>”按钮`
- **짧은 표현 결과:** O GT 안 · `[476, 1315]` / R GT 안 · `[476, 1315]`
- **양성 대조 질문:** `ในแถวสำหรับเลือกจำนวนแขก ช่องป้อนข้อมูลใดอยู่ตรงกลางแนวนอนของปุ่มสีน้ำเงิน "<ref>ค้นหา</ref>"?`
- **대조군 결과:** v2 파싱 실패 · 요청 형식이 아닌 숫자 배열 / v3 GT 밖 · `[665, 1173]` / 짧은 표현 GT 안 · `[476, 1315]`

### RU GUI · TH→RU 질문

<a href="qwen_pilot_gallery/pilot_01_ru.webp"><img src="qwen_pilot_gallery/pilot_01_ru.webp" alt="rel::1/booking_1.jpg ru GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[86, 1550]–[1152, 1728]` · 화면 1228×2700px
- **GT Qwen 좌표:** `[68.6, 1221.6]–[919.3, 1361.9]` · 입력 980×2128px
- **O 질문:** `ในแถวสำหรับเลือกจำนวนแขก ช่องป้อนข้อมูลใดอยู่ตรงกลางแนวนอนของปุ่มสีน้ำเงิน "<ref>ค้นหา</ref>"?`
- **R 질문:** `ในแถวสำหรับเลือกจำนวนแขก ช่องป้อนข้อมูลใดอยู่ตรงกลางแนวนอนของปุ่มสีน้ำเงิน "<ref>Найти</ref>"?`
- **진단용 짧은 표현:** O `ปุ่มสีน้ำเงิน "<ref>ค้นหา</ref>"` / R `ปุ่มสีน้ำเงิน "<ref>Найти</ref>"`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · addCriterion 반복/혼입
- **양성 대조 질문:** `В строке выбора количества гостей, какое поле ввода расположено прямо над горизонтальным центром синей кнопки '<ref>Найти</ref>'?`
- **대조군 결과:** v2 파싱 실패 · 요청 형식이 아닌 숫자 배열 / v3 GT 밖 · `[374, 1165]` / 짧은 표현 파싱 실패 · addCriterion 반복/혼입

</details>

<details>
<summary><strong>02. rel::5/message_1.jpg</strong> · O 1/4, R 2/4 · 유효 3/8 · 화면 4개</summary>

### EN GUI · RU→EN 질문

<a href="qwen_pilot_gallery/pilot_02_en.webp"><img src="qwen_pilot_gallery/pilot_02_en.webp" alt="rel::5/message_1.jpg en GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[71, 1483]–[1000, 1669]` · 화면 1080×2400px
- **GT Qwen 좌표:** `[62.6, 1314.9]–[881.5, 1479.8]` · 입력 952×2128px
- **O 질문:** `Какой элемент расположен непосредственно выше '<ref>Скрывать данные уведомлений на экране блокировки</ref>'?`
- **R 질문:** `Какой элемент расположен непосредственно выше '<ref>Hide notification details on Lock screen</ref>'?`
- **진단용 짧은 표현:** O `'<ref>Скрывать данные уведомлений на экране блокировки</ref>'` / R `'<ref>Hide notification details on Lock screen</ref>'`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · addCriterion 반복/혼입
- **양성 대조 질문:** `Which element is positioned directly above '<ref>Hide notification details on Lock screen</ref>'?`
- **대조군 결과:** v2 파싱 실패 · 코드 블록 또는 추가 텍스트 / v3 GT 밖 · `[476, 1173]` / 짧은 표현 파싱 실패 · addCriterion 반복/혼입

### ZH GUI · EN→ZH 질문

<a href="qwen_pilot_gallery/pilot_02_zh.webp"><img src="qwen_pilot_gallery/pilot_02_zh.webp" alt="rel::5/message_1.jpg zh GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[71, 1483]–[1000, 1669]` · 화면 1080×2400px
- **GT Qwen 좌표:** `[62.6, 1314.9]–[881.5, 1479.8]` · 입력 952×2128px
- **O 질문:** `Which element is positioned directly above '<ref>Hide notification details on Lock screen</ref>'?`
- **R 질문:** `Which element is positioned directly above '<ref>锁屏隐藏通知内容</ref>'?`
- **진단용 짧은 표현:** O `'<ref>Hide notification details on Lock screen</ref>'` / R `'<ref>锁屏隐藏通知内容</ref>'`
- **짧은 표현 결과:** O GT 안 · `[476, 1360]` / R GT 안 · `[346, 1360]`
- **양성 대조 질문:** `哪个元素位于“<ref>锁屏隐藏通知内容</ref>”正上方？`
- **대조군 결과:** v2 파싱 실패 · 코드 블록 또는 추가 텍스트 / v3 GT 밖 · `[476, 1234]` / 짧은 표현 GT 안 · `[476, 1360]`

### TH GUI · ZH→TH 질문

<a href="qwen_pilot_gallery/pilot_02_th.webp"><img src="qwen_pilot_gallery/pilot_02_th.webp" alt="rel::5/message_1.jpg th GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[71, 1483]–[1000, 1669]` · 화면 1080×2400px
- **GT Qwen 좌표:** `[62.6, 1314.9]–[881.5, 1479.8]` · 입력 952×2128px
- **O 질문:** `哪个元素位于“<ref>锁屏隐藏通知内容</ref>”正上方？`
- **R 질문:** `哪个元素位于“<ref>ซ่อนรายละเอียดของการแจ้งบนหน้าจอล็อก</ref>”正上方？`
- **진단용 짧은 표현:** O `“<ref>锁屏隐藏通知内容</ref>”` / R `“<ref>ซ่อนรายละเอียดของการแจ้งบนหน้าจอล็อก</ref>”`
- **짧은 표현 결과:** O 파싱 실패 · 빈 배열 / R 파싱 실패 · addCriterion 반복/혼입
- **양성 대조 질문:** `องค์ประกอบใดที่อยู่เหนือ "<ref>ซ่อนรายละเอียดของการแจ้งบนหน้าจอล็อก</ref>"?`
- **대조군 결과:** v2 파싱 실패 · addCriterion 반복/혼입 / v3 파싱 실패 · 불완전한 JSON / 짧은 표현 파싱 실패 · addCriterion 반복/혼입

### RU GUI · TH→RU 질문

<a href="qwen_pilot_gallery/pilot_02_ru.webp"><img src="qwen_pilot_gallery/pilot_02_ru.webp" alt="rel::5/message_1.jpg ru GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[67, 1490]–[1022, 1749]` · 화면 1080×2400px
- **GT Qwen 좌표:** `[59.1, 1321.1]–[900.9, 1550.8]` · 입력 952×2128px
- **O 질문:** `องค์ประกอบใดที่อยู่เหนือ "<ref>ซ่อนรายละเอียดของการแจ้งบนหน้าจอล็อก</ref>"?`
- **R 질문:** `องค์ประกอบใดที่อยู่เหนือ "<ref>Скрывать данные уведомлений на экране блокировки</ref>"?`
- **진단용 짧은 표현:** O `"<ref>ซ่อนรายละเอียดของการแจ้งบนหน้าจอล็อก</ref>"` / R `"<ref>Скрывать данные уведомлений на экране блокировки</ref>"`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R GT 안 · `[374, 1406]`
- **양성 대조 질문:** `Какой элемент расположен непосредственно выше '<ref>Скрывать данные уведомлений на экране блокировки</ref>'?`
- **대조군 결과:** v2 파싱 실패 · 요청 형식이 아닌 숫자 배열 / v3 GT 밖 · `[463, 1207]` / 짧은 표현 GT 안 · `[374, 1406]`

</details>

<details>
<summary><strong>03. rel::1/booking_10.jpg</strong> · O 1/4, R 1/4 · 유효 2/8 · 화면 4개</summary>

### EN GUI · RU→EN 질문

<a href="qwen_pilot_gallery/pilot_03_en.webp"><img src="qwen_pilot_gallery/pilot_03_en.webp" alt="rel::1/booking_10.jpg en GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[66, 887]–[516, 971]` · 화면 1228×2700px
- **GT Qwen 좌표:** `[52.7, 699.1]–[411.8, 765.3]` · 입력 980×2128px
- **O 질문:** `Какая валютная опция находится сразу под разделом "<ref>Рекомендовано для вас</ref>"?`
- **R 질문:** `Какая валютная опция находится сразу под разделом "<ref>Suggested for you</ref>"?`
- **진단용 짧은 표현:** O `разделом "<ref>Рекомендовано для вас</ref>"` / R `разделом "<ref>Suggested for you</ref>"`
- **짧은 표현 결과:** O GT 안 · `[236, 724]` / R GT 안 · `[346, 725]`

### ZH GUI · EN→ZH 질문

<a href="qwen_pilot_gallery/pilot_03_zh.webp"><img src="qwen_pilot_gallery/pilot_03_zh.webp" alt="rel::1/booking_10.jpg zh GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[55, 834]–[302, 917]` · 화면 1228×2700px
- **GT Qwen 좌표:** `[43.9, 657.3]–[241, 722.7]` · 입력 980×2128px
- **O 질문:** `Which currency option is immediately below the "<ref>Suggested for you</ref>" section?`
- **R 질문:** `Which currency option is immediately below the "<ref>为你推荐</ref>" section?`
- **진단용 짧은 표현:** O `"<ref>Suggested for you</ref>" section` / R `"<ref>为你推荐</ref>" section`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · addCriterion 반복/혼입

### TH GUI · ZH→TH 질문

<a href="qwen_pilot_gallery/pilot_03_th.webp"><img src="qwen_pilot_gallery/pilot_03_th.webp" alt="rel::1/booking_10.jpg th GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[77, 850]–[559, 921]` · 화면 1228×2700px
- **GT Qwen 좌표:** `[61.4, 669.9]–[446.1, 725.9]` · 입력 980×2128px
- **O 질문:** `哪个货币选项在“<ref>为你推荐</ref>”部分的正下方？`
- **R 질문:** `哪个货币选项在“<ref>ตัวเลือกแนะนำสำหรับคุณ</ref>”部分的正下方？`
- **진단용 짧은 표현:** O `“<ref>为你推荐</ref>”部分` / R `“<ref>ตัวเลือกแนะนำสำหรับคุณ</ref>”部分`
- **짧은 표현 결과:** O 파싱 실패 · 코드 블록 또는 추가 텍스트 / R 파싱 실패 · addCriterion 반복/혼입

### RU GUI · TH→RU 질문

<a href="qwen_pilot_gallery/pilot_03_ru.webp"><img src="qwen_pilot_gallery/pilot_03_ru.webp" alt="rel::1/booking_10.jpg ru GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[71, 952]–[644, 1043]` · 화면 1228×2700px
- **GT Qwen 좌표:** `[56.7, 750.3]–[513.9, 822]` · 입력 980×2128px
- **O 질문:** `ตัวเลือกสกุลเงินใดอยู่ด้านล่างของส่วน "<ref>ตัวเลือกแนะนำสำหรับคุณ</ref>" ทันที?`
- **R 질문:** `ตัวเลือกสกุลเงินใดอยู่ด้านล่างของส่วน "<ref>Рекомендовано для вас</ref>" ทันที?`
- **진단용 짧은 표현:** O `ส่วน "<ref>ตัวเลือกแนะนำสำหรับคุณ</ref>"` / R `ส่วน "<ref>Рекомендовано для вас</ref>"`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · addCriterion 반복/혼입

</details>

<details>
<summary><strong>04. rel::2/clock_10.png</strong> · O 3/4, R 3/4 · 유효 6/8 · 화면 4개</summary>

### EN GUI · RU→EN 질문

<a href="qwen_pilot_gallery/pilot_04_en.webp"><img src="qwen_pilot_gallery/pilot_04_en.webp" alt="rel::2/clock_10.png en GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[1008, 1776]–[1213, 1882]` · 화면 2746×1908px
- **GT Qwen 좌표:** `[637.2, 1120.7]–[766.8, 1187.6]` · 입력 1736×1204px
- **O 질문:** `Какой элемент находится непосредственно справа от вкладки '<ref>Будильник</ref>' в нижней части экрана?`
- **R 질문:** `Какой элемент находится непосредственно справа от вкладки '<ref>Alarm</ref>' в нижней части экрана?`
- **진단용 짧은 표현:** O `вкладки '<ref>Будильник</ref>' в нижней части экрана` / R `вкладки '<ref>Alarm</ref>' в нижней части экрана`
- **짧은 표현 결과:** O GT 안 · `[705, 1154]` / R GT 안 · `[705, 1154]`

### ZH GUI · EN→ZH 질문

<a href="qwen_pilot_gallery/pilot_04_zh.webp"><img src="qwen_pilot_gallery/pilot_04_zh.webp" alt="rel::2/clock_10.png zh GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[1008, 1776]–[1213, 1882]` · 화면 2746×1908px
- **GT Qwen 좌표:** `[637.2, 1120.7]–[766.8, 1187.6]` · 입력 1736×1204px
- **O 질문:** `Which element is located directly to the right of the '<ref>Alarm</ref>' tab at the bottom of the screen?`
- **R 질문:** `Which element is located directly to the right of the '<ref>闹钟</ref>' tab at the bottom of the screen?`
- **진단용 짧은 표현:** O `'<ref>Alarm</ref>' tab at the bottom of the screen` / R `'<ref>闹钟</ref>' tab at the bottom of the screen`
- **짧은 표현 결과:** O GT 안 · `[705, 1154]` / R GT 안 · `[705, 1154]`

### TH GUI · ZH→TH 질문

<a href="qwen_pilot_gallery/pilot_04_th.webp"><img src="qwen_pilot_gallery/pilot_04_th.webp" alt="rel::2/clock_10.png th GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[893, 1785]–[1134, 1883]` · 화면 2746×1908px
- **GT Qwen 좌표:** `[564.5, 1126.4]–[716.9, 1188.2]` · 입력 1736×1204px
- **O 질문:** `哪个元素位于屏幕底部“<ref>闹钟</ref>”标签的右侧？`
- **R 질문:** `哪个元素位于屏幕底部“<ref>นาฬิกาปลุก</ref>”标签的右侧？`
- **진단용 짧은 표현:** O `屏幕底部“<ref>闹钟</ref>”标签` / R `屏幕底部“<ref>นาฬิกาปลุก</ref>”标签`
- **짧은 표현 결과:** O GT 안 · `[658, 1159]` / R GT 안 · `[658, 1151]`

### RU GUI · TH→RU 질문

<a href="qwen_pilot_gallery/pilot_04_ru.webp"><img src="qwen_pilot_gallery/pilot_04_ru.webp" alt="rel::2/clock_10.png ru GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[1008, 1776]–[1213, 1882]` · 화면 2746×1908px
- **GT Qwen 좌표:** `[637.2, 1120.7]–[766.8, 1187.6]` · 입력 1736×1204px
- **O 질문:** `องค์ประกอบใดอยู่ทางขวาของแท็บ '<ref>นาฬิกาปลุก</ref>' ที่ด้านล่างของหน้าจอ?`
- **R 질문:** `องค์ประกอบใดอยู่ทางขวาของแท็บ '<ref>Будильник</ref>' ที่ด้านล่างของหน้าจอ?`
- **진단용 짧은 표현:** O `แท็บ '<ref>นาฬิกาปลุก</ref>' ที่ด้านล่างของหน้าจอ` / R `แท็บ '<ref>Будильник</ref>' ที่ด้านล่างของหน้าจอ`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · 불완전한 JSON

</details>

<details>
<summary><strong>05. rel::2/weather_3.png</strong> · O 0/4, R 0/4 · 유효 0/8 · 화면 4개</summary>

### EN GUI · RU→EN 질문

<a href="qwen_pilot_gallery/pilot_05_en.webp"><img src="qwen_pilot_gallery/pilot_05_en.webp" alt="rel::2/weather_3.png en GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[795, 326]–[1948, 1595]` · 화면 2746×1908px
- **GT Qwen 좌표:** `[502.6, 205.7]–[1231.5, 1006.5]` · 입력 1736×1204px
- **O 질문:** `Какой элемент расположен непосредственно справа от раздела '<ref>Ветер</ref>' и выше датчика давления?`
- **R 질문:** `Какой элемент расположен непосредственно справа от раздела '<ref>Wind</ref>' и выше датчика давления?`
- **진단용 짧은 표현:** O `раздела '<ref>Ветер</ref>'` / R `раздела '<ref>Wind</ref>'`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · addCriterion 반복/혼입

### ZH GUI · EN→ZH 질문

<a href="qwen_pilot_gallery/pilot_05_zh.webp"><img src="qwen_pilot_gallery/pilot_05_zh.webp" alt="rel::2/weather_3.png zh GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[795, 326]–[1948, 1595]` · 화면 2746×1908px
- **GT Qwen 좌표:** `[502.6, 205.7]–[1231.5, 1006.5]` · 입력 1736×1204px
- **O 질문:** `Which element is located directly to the right of the '<ref>Wind</ref>' section and above the pressure gauge?`
- **R 질문:** `Which element is located directly to the right of the '<ref>风</ref>' section and above the pressure gauge?`
- **진단용 짧은 표현:** O `'<ref>Wind</ref>' section` / R `'<ref>风</ref>' section`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · addCriterion 반복/혼입

### TH GUI · ZH→TH 질문

<a href="qwen_pilot_gallery/pilot_05_th.webp"><img src="qwen_pilot_gallery/pilot_05_th.webp" alt="rel::2/weather_3.png th GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[795, 326]–[1948, 1595]` · 화면 2746×1908px
- **GT Qwen 좌표:** `[502.6, 205.7]–[1231.5, 1006.5]` · 입력 1736×1204px
- **O 질문:** `哪个元素位于「<ref>风</ref>」部分的右侧并且在气压表上方？`
- **R 질문:** `哪个元素位于「<ref>ลม</ref>」部分的右侧并且在气压表上方？`
- **진단용 짧은 표현:** O `「<ref>风</ref>」部分` / R `「<ref>ลม</ref>」部分`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · addCriterion 반복/혼입

### RU GUI · TH→RU 질문

<a href="qwen_pilot_gallery/pilot_05_ru.webp"><img src="qwen_pilot_gallery/pilot_05_ru.webp" alt="rel::2/weather_3.png ru GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[795, 326]–[1948, 1595]` · 화면 2746×1908px
- **GT Qwen 좌표:** `[502.6, 205.7]–[1231.5, 1006.5]` · 입력 1736×1204px
- **O 질문:** `องค์ประกอบใดอยู่ทางขวาของส่วน '<ref>ลม</ref>' และเหนือมาตรวัดความดัน?`
- **R 질문:** `องค์ประกอบใดอยู่ทางขวาของส่วน '<ref>Ветер</ref>' และเหนือมาตรวัดความดัน?`
- **진단용 짧은 표현:** O `ส่วน '<ref>ลม</ref>'` / R `ส่วน '<ref>Ветер</ref>'`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · addCriterion 반복/혼입

</details>

<details>
<summary><strong>06. rel::3/music_7.jpg</strong> · O 0/4, R 0/4 · 유효 0/8 · 화면 4개</summary>

### EN GUI · RU→EN 질문

<a href="qwen_pilot_gallery/pilot_06_en.webp"><img src="qwen_pilot_gallery/pilot_06_en.webp" alt="rel::3/music_7.jpg en GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[28, 933]–[317, 1015]` · 화면 1080×2340px
- **GT Qwen 좌표:** `[25.4, 837.3]–[287.6, 910.9]` · 입력 980×2100px
- **O 질문:** `Какой из следующих вариантов находится непосредственно под пунктом меню "<ref>Повторить все</ref>"?`
- **R 질문:** `Какой из следующих вариантов находится непосредственно под пунктом меню "<ref>Repeat all</ref>"?`
- **진단용 짧은 표현:** O `пунктом меню "<ref>Повторить все</ref>"` / R `пунктом меню "<ref>Repeat all</ref>"`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · addCriterion 반복/혼입

### ZH GUI · EN→ZH 질문

<a href="qwen_pilot_gallery/pilot_06_zh.webp"><img src="qwen_pilot_gallery/pilot_06_zh.webp" alt="rel::3/music_7.jpg zh GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[25, 936]–[298, 1025]` · 화면 1080×2340px
- **GT Qwen 좌표:** `[22.7, 840]–[270.4, 919.9]` · 입력 980×2100px
- **O 질문:** `Which of the following options is located directly below the "<ref>Repeat all</ref>" option in the menu?`
- **R 질문:** `Which of the following options is located directly below the "<ref>全部循环</ref>" option in the menu?`
- **진단용 짧은 표현:** O `"<ref>Repeat all</ref>" option in the menu` / R `"<ref>全部循环</ref>" option in the menu`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · addCriterion 반복/혼입

### TH GUI · ZH→TH 질문

<a href="qwen_pilot_gallery/pilot_06_th.webp"><img src="qwen_pilot_gallery/pilot_06_th.webp" alt="rel::3/music_7.jpg th GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[28, 936]–[377, 1025]` · 화면 1080×2340px
- **GT Qwen 좌표:** `[25.4, 840]–[342.1, 919.9]` · 입력 980×2100px
- **O 질문:** `以下哪个选项位于菜单中“<ref>全部循环</ref>”选项的正下方？`
- **R 질문:** `以下哪个选项位于菜单中“<ref>เล่นซ้ำทั้งหมด</ref>”选项的正下方？`
- **진단용 짧은 표현:** O `菜单中“<ref>全部循环</ref>”选项` / R `菜单中“<ref>เล่นซ้ำทั้งหมด</ref>”选项`
- **짧은 표현 결과:** O 파싱 실패 · 빈 배열 / R 파싱 실패 · addCriterion 반복/혼입

### RU GUI · TH→RU 질문

<a href="qwen_pilot_gallery/pilot_06_ru.webp"><img src="qwen_pilot_gallery/pilot_06_ru.webp" alt="rel::3/music_7.jpg ru GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[25, 926]–[416, 1025]` · 화면 1080×2340px
- **GT Qwen 좌표:** `[22.7, 831]–[377.5, 919.9]` · 입력 980×2100px
- **O 질문:** `ตัวเลือกใดต่อไปนี้อยู่ด้านล่างของตัวเลือก "<ref>เล่นซ้ำทั้งหมด</ref>" ในเมนู?`
- **R 질문:** `ตัวเลือกใดต่อไปนี้อยู่ด้านล่างของตัวเลือก "<ref>Повторить все</ref>" ในเมนู?`
- **진단용 짧은 표현:** O `ตัวเลือก "<ref>เล่นซ้ำทั้งหมด</ref>" ในเมนู` / R `ตัวเลือก "<ref>Повторить все</ref>" ในเมนู`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · addCriterion 반복/혼입

</details>

<details>
<summary><strong>07. rel::3/settings_2.jpg</strong> · O 3/4, R 4/4 · 유효 7/8 · 화면 4개</summary>

### EN GUI · RU→EN 질문

<a href="qwen_pilot_gallery/pilot_07_en.webp"><img src="qwen_pilot_gallery/pilot_07_en.webp" alt="rel::3/settings_2.jpg en GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[55, 672]–[1022, 817]` · 화면 1080×2340px
- **GT Qwen 좌표:** `[49.9, 603.1]–[927.4, 733.2]` · 입력 980×2100px
- **O 질문:** `Какой элемент находится непосредственно ниже '<ref>Установка сертификатов</ref>'?`
- **R 질문:** `Какой элемент находится непосредственно ниже '<ref>Install certificates</ref>'?`
- **진단용 짧은 표현:** O `'<ref>Установка сертификатов</ref>'` / R `'<ref>Install certificates</ref>'`
- **짧은 표현 결과:** O GT 안 · `[435, 657]` / R GT 안 · `[456, 657]`

### ZH GUI · EN→ZH 질문

<a href="qwen_pilot_gallery/pilot_07_zh.webp"><img src="qwen_pilot_gallery/pilot_07_zh.webp" alt="rel::3/settings_2.jpg zh GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[55, 672]–[1022, 817]` · 화면 1080×2340px
- **GT Qwen 좌표:** `[49.9, 603.1]–[927.4, 733.2]` · 입력 980×2100px
- **O 질문:** `Which element is located directly below '<ref>Install certificates</ref>'?`
- **R 질문:** `Which element is located directly below '<ref>安装证书</ref>'?`
- **진단용 짧은 표현:** O `'<ref>Install certificates</ref>'` / R `'<ref>安装证书</ref>'`
- **짧은 표현 결과:** O GT 안 · `[463, 657]` / R GT 안 · `[463, 657]`

### TH GUI · ZH→TH 질문

<a href="qwen_pilot_gallery/pilot_07_th.webp"><img src="qwen_pilot_gallery/pilot_07_th.webp" alt="rel::3/settings_2.jpg th GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[55, 672]–[1022, 817]` · 화면 1080×2340px
- **GT Qwen 좌표:** `[49.9, 603.1]–[927.4, 733.2]` · 입력 980×2100px
- **O 질문:** `哪个元素位于“<ref>安装证书</ref>”正下方？`
- **R 질문:** `哪个元素位于“<ref>ติดตั้งใบรับรอง</ref>”正下方？`
- **진단용 짧은 표현:** O `“<ref>安装证书</ref>”` / R `“<ref>ติดตั้งใบรับรอง</ref>”`
- **짧은 표현 결과:** O 파싱 실패 · 빈 배열 / R GT 안 · `[435, 667]`

### RU GUI · TH→RU 질문

<a href="qwen_pilot_gallery/pilot_07_ru.webp"><img src="qwen_pilot_gallery/pilot_07_ru.webp" alt="rel::3/settings_2.jpg ru GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[55, 799]–[1023, 904]` · 화면 1080×2340px
- **GT Qwen 좌표:** `[49.9, 717.1]–[928.3, 811.3]` · 입력 980×2100px
- **O 질문:** `องค์ประกอบใดอยู่ด้านล่างโดยตรงของ '<ref>ติดตั้งใบรับรอง</ref>'?`
- **R 질문:** `องค์ประกอบใดอยู่ด้านล่างโดยตรงของ '<ref>Установка сертификатов</ref>'?`
- **진단용 짧은 표현:** O `'<ref>ติดตั้งใบรับรอง</ref>'` / R `'<ref>Установка сертификатов</ref>'`
- **짧은 표현 결과:** O GT 안 · `[374, 756]` / R GT 안 · `[476, 753]`

</details>

<details>
<summary><strong>08. rel::4/Gmail_8.jpg</strong> · O 0/4, R 0/4 · 유효 0/8 · 화면 4개</summary>

### EN GUI · RU→EN 질문

<a href="qwen_pilot_gallery/pilot_08_en.webp"><img src="qwen_pilot_gallery/pilot_08_en.webp" alt="rel::4/Gmail_8.jpg en GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[41, 983]–[533, 1136]` · 화면 1260×2800px
- **GT Qwen 좌표:** `[31, 756.9]–[402.7, 874.7]` · 입력 952×2156px
- **O 질문:** `Какой элемент находится непосредственно выше текста-заполнителя '<ref>Текст сообщения</ref>'?`
- **R 질문:** `Какой элемент находится непосредственно выше текста-заполнителя '<ref>Compose email</ref>'?`
- **진단용 짧은 표현:** O `текста-заполнителя '<ref>Текст сообщения</ref>'` / R `текста-заполнителя '<ref>Compose email</ref>'`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · addCriterion 반복/혼입

### ZH GUI · EN→ZH 질문

<a href="qwen_pilot_gallery/pilot_08_zh.webp"><img src="qwen_pilot_gallery/pilot_08_zh.webp" alt="rel::4/Gmail_8.jpg zh GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[45, 990]–[438, 1128]` · 화면 1260×2800px
- **GT Qwen 좌표:** `[34, 762.3]–[330.9, 868.6]` · 입력 952×2156px
- **O 질문:** `Which element is located directly above the '<ref>Compose email</ref>' placeholder text?`
- **R 질문:** `Which element is located directly above the '<ref>撰写电子邮件</ref>' placeholder text?`
- **진단용 짧은 표현:** O `'<ref>Compose email</ref>' placeholder text` / R `'<ref>撰写电子邮件</ref>' placeholder text`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · addCriterion 반복/혼입

### TH GUI · ZH→TH 질문

<a href="qwen_pilot_gallery/pilot_08_th.webp"><img src="qwen_pilot_gallery/pilot_08_th.webp" alt="rel::4/Gmail_8.jpg th GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[29, 990]–[352, 1136]` · 화면 1260×2800px
- **GT Qwen 좌표:** `[21.9, 762.3]–[266, 874.7]` · 입력 952×2156px
- **O 질문:** `哪个元素位于“<ref>撰写电子邮件</ref>”占位符文本的正上方？`
- **R 질문:** `哪个元素位于“<ref>เขียนอีเมล</ref>”占位符文本的正上方？`
- **진단용 짧은 표현:** O `“<ref>撰写电子邮件</ref>”占位符文本` / R `“<ref>เขียนอีเมล</ref>”占位符文本`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · 불완전한 JSON

### RU GUI · TH→RU 질문

<a href="qwen_pilot_gallery/pilot_08_ru.webp"><img src="qwen_pilot_gallery/pilot_08_ru.webp" alt="rel::4/Gmail_8.jpg ru GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[37, 982]–[600, 1155]` · 화면 1260×2800px
- **GT Qwen 좌표:** `[28, 756.1]–[453.3, 889.4]` · 입력 952×2156px
- **O 질문:** `องค์ประกอบใดอยู่เหนือข้อความตัวอย่าง '<ref>เขียนอีเมล</ref>' โดยตรง?`
- **R 질문:** `องค์ประกอบใดอยู่เหนือข้อความตัวอย่าง '<ref>Текст сообщения</ref>' โดยตรง?`
- **진단용 짧은 표현:** O `ข้อความตัวอย่าง '<ref>เขียนอีเมล</ref>'` / R `ข้อความตัวอย่าง '<ref>Текст сообщения</ref>'`
- **짧은 표현 결과:** O 파싱 실패 · 빈 배열 / R 파싱 실패 · addCriterion 반복/혼입

</details>

<details>
<summary><strong>09. rel::4/twitter_6.jpg</strong> · O 2/4, R 3/4 · 유효 5/8 · 화면 4개</summary>

### EN GUI · RU→EN 질문

<a href="qwen_pilot_gallery/pilot_09_en.webp"><img src="qwen_pilot_gallery/pilot_09_en.webp" alt="rel::4/twitter_6.jpg en GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[9, 647]–[843, 918]` · 화면 864×1920px
- **GT Qwen 좌표:** `[9, 651]–[846.9, 923.7]` · 입력 868×1932px
- **O 질문:** `Какой параметр находится непосредственно ниже опции '<ref>Безопасность и доступ к учетной записи</ref>' в меню настроек?`
- **R 질문:** `Какой параметр находится непосредственно ниже опции '<ref>Security and account access</ref>' в меню настроек?`
- **진단용 짧은 표현:** O `опции '<ref>Безопасность и доступ к учетной записи</ref>' в меню настроек` / R `опции '<ref>Security and account access</ref>' в меню настроек`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · addCriterion 반복/혼입

### ZH GUI · EN→ZH 질문

<a href="qwen_pilot_gallery/pilot_09_zh.webp"><img src="qwen_pilot_gallery/pilot_09_zh.webp" alt="rel::4/twitter_6.jpg zh GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[17, 859]–[1199, 1154]` · 화면 1260×2800px
- **GT Qwen 좌표:** `[12.8, 661.4]–[905.9, 888.6]` · 입력 952×2156px
- **O 질문:** `Which setting is located directly below the '<ref>Security and account access</ref>' option in the settings menu?`
- **R 질문:** `Which setting is located directly below the '<ref>安全性和账号访问权限</ref>' option in the settings menu?`
- **진단용 짧은 표현:** O `'<ref>Security and account access</ref>' option in the settings menu` / R `'<ref>安全性和账号访问权限</ref>' option in the settings menu`
- **짧은 표현 결과:** O GT 안 · `[374, 742]` / R GT 안 · `[374, 720]`

### TH GUI · ZH→TH 질문

<a href="qwen_pilot_gallery/pilot_09_th.webp"><img src="qwen_pilot_gallery/pilot_09_th.webp" alt="rel::4/twitter_6.jpg th GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[9, 647]–[843, 918]` · 화면 864×1920px
- **GT Qwen 좌표:** `[9, 651]–[846.9, 923.7]` · 입력 868×1932px
- **O 질문:** `在设置菜单中，哪个设置位于“<ref>安全性和账号访问权限</ref>”选项的正下方？`
- **R 질문:** `在设置菜单中，哪个设置位于“<ref>ความปลอดภัยและการเข้าถึงบัญชี</ref>”选项的正下方？`
- **진단용 짧은 표현:** O `“<ref>安全性和账号访问权限</ref>”选项` / R `“<ref>ความปลอดภัยและการเข้าถึงบัญชี</ref>”选项`
- **짧은 표현 결과:** O 파싱 실패 · 빈 배열 / R GT 안 · `[457, 710]`

### RU GUI · TH→RU 질문

<a href="qwen_pilot_gallery/pilot_09_ru.webp"><img src="qwen_pilot_gallery/pilot_09_ru.webp" alt="rel::4/twitter_6.jpg ru GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[22, 702]–[837, 974]` · 화면 864×1920px
- **GT Qwen 좌표:** `[22.1, 706.4]–[840.9, 980.1]` · 입력 868×1932px
- **O 질문:** `ตัวเลือกใดอยู่ด้านล่างของตัวเลือก '<ref>ความปลอดภัยและการเข้าถึงบัญชี</ref>' ในเมนูการตั้งค่า?`
- **R 질문:** `ตัวเลือกใดอยู่ด้านล่างของตัวเลือก '<ref>Безопасность и доступ к учетной записи</ref>' ในเมนูการตั้งค่า?`
- **진단용 짧은 표현:** O `ตัวเลือก '<ref>ความปลอดภัยและการเข้าถึงบัญชี</ref>' ในเมนูการตั้งค่า` / R `ตัวเลือก '<ref>Безопасность и доступ к учетной записи</ref>' ในเมนูการตั้งค่า`
- **짧은 표현 결과:** O GT 안 · `[475, 740]` / R GT 안 · `[475, 740]`

</details>

<details>
<summary><strong>10. rel::5/camera_1.jpg</strong> · O 2/4, R 3/4 · 유효 5/8 · 화면 4개</summary>

### EN GUI · RU→EN 질문

<a href="qwen_pilot_gallery/pilot_10_en.webp"><img src="qwen_pilot_gallery/pilot_10_en.webp" alt="rel::5/camera_1.jpg en GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[411, 1732]–[640, 1802]` · 화면 1080×2400px
- **GT Qwen 좌표:** `[362.3, 1535.7]–[564.1, 1597.8]` · 입력 952×2128px
- **O 질문:** `Какой элемент находится прямо над кнопкой режима '<ref>ФОТО</ref>'?`
- **R 질문:** `Какой элемент находится прямо над кнопкой режима '<ref>PHOTO</ref>'?`
- **진단용 짧은 표현:** O `кнопкой режима '<ref>ФОТО</ref>'` / R `кнопкой режима '<ref>PHOTO</ref>'`
- **짧은 표현 결과:** O GT 안 · `[476, 1569]` / R GT 안 · `[476, 1569]`

### ZH GUI · EN→ZH 질문

<a href="qwen_pilot_gallery/pilot_10_zh.webp"><img src="qwen_pilot_gallery/pilot_10_zh.webp" alt="rel::5/camera_1.jpg zh GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[411, 1732]–[640, 1802]` · 화면 1080×2400px
- **GT Qwen 좌표:** `[362.3, 1535.7]–[564.1, 1597.8]` · 입력 952×2128px
- **O 질문:** `Which element is located directly above the '<ref>PHOTO</ref>' mode button?`
- **R 질문:** `Which element is located directly above the '<ref>照片</ref>' mode button?`
- **진단용 짧은 표현:** O `'<ref>PHOTO</ref>' mode button` / R `'<ref>照片</ref>' mode button`
- **짧은 표현 결과:** O 파싱 실패 · 불완전한 JSON / R GT 안 · `[476, 1569]`

### TH GUI · ZH→TH 질문

<a href="qwen_pilot_gallery/pilot_10_th.webp"><img src="qwen_pilot_gallery/pilot_10_th.webp" alt="rel::5/camera_1.jpg th GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[411, 1732]–[640, 1802]` · 화면 1080×2400px
- **GT Qwen 좌표:** `[362.3, 1535.7]–[564.1, 1597.8]` · 입력 952×2128px
- **O 질문:** `哪个元素位于“<ref>照片</ref>”模式按钮的正上方？`
- **R 질문:** `哪个元素位于“<ref>รูปถ่าย</ref>”模式按钮的正上方？`
- **진단용 짧은 표현:** O `“<ref>照片</ref>”模式按钮` / R `“<ref>รูปถ่าย</ref>”模式按钮`
- **짧은 표현 결과:** O 파싱 실패 · addCriterion 반복/혼입 / R 파싱 실패 · addCriterion 반복/혼입

### RU GUI · TH→RU 질문

<a href="qwen_pilot_gallery/pilot_10_ru.webp"><img src="qwen_pilot_gallery/pilot_10_ru.webp" alt="rel::5/camera_1.jpg ru GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[411, 1732]–[640, 1802]` · 화면 1080×2400px
- **GT Qwen 좌표:** `[362.3, 1535.7]–[564.1, 1597.8]` · 입력 952×2128px
- **O 질문:** `องค์ประกอบใดอยู่เหนือปุ่มโหมด '<ref>รูปถ่าย</ref>' โดยตรง?`
- **R 질문:** `องค์ประกอบใดอยู่เหนือปุ่มโหมด '<ref>ФОТО</ref>' โดยตรง?`
- **진단용 짧은 표현:** O `ปุ่มโหมด '<ref>รูปถ่าย</ref>'` / R `ปุ่มโหมด '<ref>ФОТО</ref>'`
- **짧은 표현 결과:** O GT 안 · `[476, 1569]` / R GT 안 · `[476, 1569]`

</details>

<details>
<summary><strong>11. rel::6/safari_7.jpg</strong> · O 4/4, R 2/4 · 유효 6/8 · 화면 4개</summary>

### EN GUI · RU→EN 질문

<a href="qwen_pilot_gallery/pilot_11_en.webp"><img src="qwen_pilot_gallery/pilot_11_en.webp" alt="rel::6/safari_7.jpg en GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[71, 804]–[1211, 955]` · 화면 1280×2769px
- **GT Qwen 좌표:** `[54.4, 609.8]–[927.2, 724.3]` · 입력 980×2100px
- **O 질문:** `Какой вариант отображается непосредственно выше настройки '<ref>Веб-архив</ref>' в списке, показанном на скриншоте?`
- **R 질문:** `Какой вариант отображается непосредственно выше настройки '<ref>Web Archive</ref>' в списке, показанном на скриншоте?`
- **진단용 짧은 표현:** O `настройки '<ref>Веб-архив</ref>' в списке` / R `настройки '<ref>Web Archive</ref>' в списке`
- **짧은 표현 결과:** O GT 안 · `[476, 673]` / R GT 안 · `[476, 673]`

### ZH GUI · EN→ZH 질문

<a href="qwen_pilot_gallery/pilot_11_zh.webp"><img src="qwen_pilot_gallery/pilot_11_zh.webp" alt="rel::6/safari_7.jpg zh GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[71, 804]–[1211, 955]` · 화면 1280×2769px
- **GT Qwen 좌표:** `[54.4, 609.8]–[927.2, 724.3]` · 입력 980×2100px
- **O 질문:** `Which option appears directly above the '<ref>Web Archive</ref>' setting in the list shown in the screenshot?`
- **R 질문:** `Which option appears directly above the '<ref>网页归档</ref>' setting in the list shown in the screenshot?`
- **진단용 짧은 표현:** O `'<ref>Web Archive</ref>' setting in the list` / R `'<ref>网页归档</ref>' setting in the list`
- **짧은 표현 결과:** O GT 안 · `[476, 673]` / R 파싱 실패 · addCriterion 반복/혼입

### TH GUI · ZH→TH 질문

<a href="qwen_pilot_gallery/pilot_11_th.webp"><img src="qwen_pilot_gallery/pilot_11_th.webp" alt="rel::6/safari_7.jpg th GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[71, 804]–[1211, 955]` · 화면 1280×2769px
- **GT Qwen 좌표:** `[54.4, 609.8]–[927.2, 724.3]` · 입력 980×2100px
- **O 질문:** `哪个选项在截图中列表显示的“<ref>网页归档</ref>”设置上方？`
- **R 질문:** `哪个选项在截图中列表显示的“<ref>ที่เก็บเว็บถาวร</ref>”设置上方？`
- **진단용 짧은 표현:** O `“<ref>网页归档</ref>”设置` / R `“<ref>ที่เก็บเว็บถาวร</ref>”设置`
- **짧은 표현 결과:** O GT 안 · `[436, 675]` / R 파싱 실패 · 빈 배열

### RU GUI · TH→RU 질문

<a href="qwen_pilot_gallery/pilot_11_ru.webp"><img src="qwen_pilot_gallery/pilot_11_ru.webp" alt="rel::6/safari_7.jpg ru GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[71, 804]–[1211, 955]` · 화면 1280×2769px
- **GT Qwen 좌표:** `[54.4, 609.8]–[927.2, 724.3]` · 입력 980×2100px
- **O 질문:** `ตัวเลือกใดปรากฏอยู่เหนือการตั้งค่า "<ref>ที่เก็บเว็บถาวร</ref>" ในรายการที่แสดงในภาพหน้าจอ?`
- **R 질문:** `ตัวเลือกใดปรากฏอยู่เหนือการตั้งค่า "<ref>Веб-архив</ref>" ในรายการที่แสดงในภาพหน้าจอ?`
- **진단용 짧은 표현:** O `การตั้งค่า "<ref>ที่เก็บเว็บถาวร</ref>" ในรายการ` / R `การตั้งค่า "<ref>Веб-архив</ref>" ในรายการ`
- **짧은 표현 결과:** O GT 안 · `[173, 674]` / R GT 안 · `[476, 673]`

</details>

<details>
<summary><strong>12. rel::6/wallet_3.jpg</strong> · O 3/4, R 4/4 · 유효 7/8 · 화면 4개</summary>

### EN GUI · RU→EN 질문

<a href="qwen_pilot_gallery/pilot_12_en.webp"><img src="qwen_pilot_gallery/pilot_12_en.webp" alt="rel::6/wallet_3.jpg en GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[32, 343]–[424, 484]` · 화면 1280×2769px
- **GT Qwen 좌표:** `[24.5, 260.1]–[324.6, 367.1]` · 입력 980×2100px
- **O 질문:** `Каков прямой порядок элементов сверху вниз на экране после заголовка "<ref>Заказы</ref>"?`
- **R 질문:** `Каков прямой порядок элементов сверху вниз на экране после заголовка "<ref>Orders</ref>"?`
- **진단용 짧은 표현:** O `заголовка "<ref>Заказы</ref>"` / R `заголовка "<ref>Orders</ref>"`
- **짧은 표현 결과:** O GT 안 · `[165, 314]` / R GT 안 · `[165, 314]`

### ZH GUI · EN→ZH 질문

<a href="qwen_pilot_gallery/pilot_12_zh.webp"><img src="qwen_pilot_gallery/pilot_12_zh.webp" alt="rel::6/wallet_3.jpg zh GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[32, 343]–[424, 484]` · 화면 1280×2769px
- **GT Qwen 좌표:** `[24.5, 260.1]–[324.6, 367.1]` · 입력 980×2100px
- **O 질문:** `What is the direct order of elements from top to bottom on the screen after the '<ref>Orders</ref>' title?`
- **R 질문:** `What is the direct order of elements from top to bottom on the screen after the '<ref>订单</ref>' title?`
- **진단용 짧은 표현:** O `'<ref>Orders</ref>' title` / R `'<ref>订单</ref>' title`
- **짧은 표현 결과:** O GT 안 · `[113, 314]` / R GT 안 · `[116, 314]`

### TH GUI · ZH→TH 질문

<a href="qwen_pilot_gallery/pilot_12_th.webp"><img src="qwen_pilot_gallery/pilot_12_th.webp" alt="rel::6/wallet_3.jpg th GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[32, 343]–[424, 484]` · 화면 1280×2769px
- **GT Qwen 좌표:** `[24.5, 260.1]–[324.6, 367.1]` · 입력 980×2100px
- **O 질문:** `在“<ref>订单</ref>”标题下，屏幕上元素从上到下的直接顺序是什么？`
- **R 질문:** `在“<ref>คำสั่งซื้อ</ref>”标题下，屏幕上元素从上到下的直接顺序是什么？`
- **진단용 짧은 표현:** O `“<ref>订单</ref>”标题` / R `“<ref>คำสั่งซื้อ</ref>”标题`
- **짧은 표현 결과:** O 파싱 실패 · 빈 배열 / R GT 안 · `[163, 324]`

### RU GUI · TH→RU 질문

<a href="qwen_pilot_gallery/pilot_12_ru.webp"><img src="qwen_pilot_gallery/pilot_12_ru.webp" alt="rel::6/wallet_3.jpg ru GUI, GT bbox와 유효한 O/R 점" width="420"></a>

- **GT 원본:** `[32, 343]–[424, 484]` · 화면 1280×2769px
- **GT Qwen 좌표:** `[24.5, 260.1]–[324.6, 367.1]` · 입력 980×2100px
- **O 질문:** `ลำดับโดยตรงขององค์ประกอบจากบนลงล่างบนหน้าจอหลังจากหัวข้อ "<ref>คำสั่งซื้อ</ref>" คืออะไร?`
- **R 질문:** `ลำดับโดยตรงขององค์ประกอบจากบนลงล่างบนหน้าจอหลังจากหัวข้อ "<ref>Заказы</ref>" คืออะไร?`
- **진단용 짧은 표현:** O `หัวข้อ "<ref>คำสั่งซื้อ</ref>"` / R `หัวข้อ "<ref>Заказы</ref>"`
- **짧은 표현 결과:** O GT 안 · `[173, 316]` / R GT 안 · `[173, 316]`

</details>

<!-- QWEN_PILOT_GALLERY_END -->
