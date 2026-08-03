# REL Text Dependency Pilot Guideline v1

## 판정 대상

각 `parallel_id`는 하나의 semantic item이다. 모델의 정오, gold label, matched–mismatch 결과를 보지 않고 GUI text dependence만 판정한다.

## 판정 질문

> 화면의 읽을 수 있는 문자열을 모두 가려도 target과 reference element를 식별하고 두 요소의 상대 위치를 안정적으로 판단할 수 있는가?

## Text-dependent

다음 중 하나 이상이면 `text-dependent`로 판정한다.

- 화면 문자열을 읽지 않으면 target element를 안정적으로 특정할 수 없다.
- 화면 문자열을 읽지 않으면 reference element를 안정적으로 특정할 수 없다.
- 같은 형태의 row, button 또는 menu item이 여러 개여서 label을 읽어야 구분된다.
- 질문이 특정 숫자, 이름, 메뉴명, mode명 또는 text span 자체를 지칭한다.

화면에 icon이 있더라도 그 icon만으로 해당 요소를 안정적으로 구분할 수 없다면 dependent다.

## Text-independent

다음 조건을 모두 만족하면 `text-independent`로 판정한다.

- 문자열을 가려도 target과 reference를 icon, shape, control type 또는 고정된 시각적 위치로 식별할 수 있다.
- 두 요소의 식별에 앱이나 특정 화면에 대한 과도한 사전 암기가 필요하지 않다.
- 상대 위치 관계를 문자열의 내용과 무관하게 판단할 수 있다.

## 검토 필요 flag

`검토 필요`는 세 번째 분석 레이블이 아니다. 다음 사례를 억지로 확정하지 않기 위한 unresolved 상태다.

- locale에 따라 icon/text 구성이나 식별 가능성이 달라진다.
- text가 없어도 추측은 가능하지만 안정적인 식별인지 불분명하다.
- target은 dependent이고 reference는 independent여서 기준 논의가 필요하다.
- screenshot rendering이나 해상도 때문에 판정이 어렵다.
- text와 icon이 하나의 결합된 logo/brand mark처럼 보인다.

Pilot 종료 후 flag와 annotator disagreement를 함께 검토하여 guideline 수정 또는 새 label 필요성을 결정한다.

## UI 사용 원칙

- 한국어는 기계 번역된 보조 자료이며 영어 원문이 authoritative source다.
- 따옴표 안 GUI 문자열은 번역하지 않고 보존되어야 한다.
- 먼저 EN screenshot으로 판정하고, locale 차이가 의심될 때 다른 locale을 확인한다.
- 모델 결과는 표시되지 않는다. Gold answer는 요청에 따라 option의 녹색 테두리로 표시되며, 이는 정답 관계를 빠르게 확인하기 위한 보조 정보다.
- 확신이 낮으면 메모를 길게 쓰기보다 `검토 필요`를 표시하고 짧게 이유를 남긴다.
