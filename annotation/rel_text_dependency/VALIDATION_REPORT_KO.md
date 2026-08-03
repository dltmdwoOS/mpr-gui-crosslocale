# REL Annotation Tool 검증 결과

검증일: 2026-08-03

## 데이터 준비

| 항목 | 결과 |
|---|---:|
| REL 모집단 semantic items | 366 |
| Pilot items | 48 |
| Source strata | 6 |
| Stratum별 pilot item | 8 |
| Locale images | 288 / 288 |
| 손상되거나 열리지 않는 image | 0 |
| 한국어 보조 번역 | 48 / 48 |
| 보존되지 않은 quoted GUI token | 0 |
| Gold/model-output field in manifest | 0 |
| Runtime QAS에서 불러온 gold answer | 48 / 48 |

Pilot manifest SHA-256:

```text
2f27ad631c001c9b2aecd70a3a2a1ee4bdc88c1b91bbc71396dafa754defa010
```

Downloaded images는 PNG 60장, JPEG 228장이며 Pillow decode/verify를 모두 통과했다.

## 기능 검증

자동화 test 4개가 통과했다.

- SQLite annotation upsert와 누적 시간 저장
- Annotator별 progress 및 CSV export
- 48-item blind manifest와 complete six-locale 구조
- 실제 Flask API, image serving, annotation 저장, export integration
- 두 annotator raw agreement와 Cohen’s κ 계산

Health endpoint 결과:

```json
{
  "status": "ok",
  "items": 48,
  "images": 288,
  "expected_images": 288,
  "gold_in_manifest": false,
  "gold_in_ui": true
}
```

## 브라우저 검증

Microsoft Edge headless browser의 `1440×900` viewport에서 실제 server와 JavaScript를 실행해 렌더링했다.

- 한국어 질문과 options 표시
- 영어 원문 동시 표시
- 정답 option에 녹색 테두리, 연녹색 배경, 굵은 글씨 표시
- screenshot과 6개 locale tab 표시
- 판정 기준과 두 label 표시
- review flag, note와 save control 표시
- 진행률과 CSV export 표시
- `J` 이전, `K` 다음 단축키와 좌우 화살표 이동 확인
- 화면 겹침이나 잘림 없음

검증 screenshot:

```text
validation/ui_1440x900.png
```

검증은 별도 임시 database와 port를 사용하므로 실제 annotation database를 변경하지 않는다.

## 판정

48-item guideline pilot에 바로 사용할 수 있다. Pilot 표본은 source diversity 확인을 위한 equal-stratum sample이므로 label prevalence나 model effect 추정에는 사용하지 않는다. Guideline을 고정한 뒤 전체 REL 366개 annotation을 위한 별도 manifest를 생성해야 한다.
