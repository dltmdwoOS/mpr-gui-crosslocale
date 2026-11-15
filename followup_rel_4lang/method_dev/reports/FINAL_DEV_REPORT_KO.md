# GCSA / RFA 개발 중간 보고: 구현·검증·실측 실패

2026-11-15. 기준 커밋 `e4aff7ace7248f1dd4e5a5dac0d4f679b33c6b5a`, 작업 브랜치 `method-selective-alignment-dev`. **전체 method 개발 목표 중 데이터 하네스와 CPU pipeline, pilot 한 쌍의 실제 GPU 기능 검사를 수행했다. Calibration 및 내부 성능 평가 완료 보고서는 아니다.** GCSA가 R을 재현하거나 능가했다는 결과는 없다.

| Gate | 상태 | 근거/남은 일 |
| --- | --- | --- |
| 0: repo/data audit | 통과 | Bundle/T lock·원본 이미지680개·기준 commit 확인 |
| 1: deterministic harness | 통과 | T/R 1,944쌍 정확 재구성, allowlist 입력, split·mock·baseline 로더 |
| 2: automatic selective | 부분 완료, 실제 편집 게이트 실패 | 모듈·CPU 검사는 통과; Qwen3-VL override에서 referent 0개로 실제 편집0 |
| 3: calibration | 미실행 | 기본 inventory Qwen2.5-VL와 text-only Qwen3 체크포인트가 없음; extractor 동작 확인 필요 |
| 4: 2×2 internal evaluation | 미실행 | Gate2/3을 통과하지 않아 main GPU 추론·성능 해석을 진행하지 않음 |
| 5: pivot routing | 코드·CPU 검사만 | EN 후보/placeholder 보호 구현. pivot 선택·의미 검수·실제 평가 미완료 |
| 6: 개발 보고 | 현재 수행 상태 기록 | 전체 성능 보고는 Gate3–5 완료 후 갱신 |

## 데이터 범위와 정보 분리

Main158문항×12방향=1,896쌍이며 사전 제외 `rel::5/forest_9.jpg::zh::ru` 후1,895쌍이다. Source lock의 HF revision과 기존 frozen 결과는 바꾸지 않았다. 같은 screenshot SHA 또는 동일 state ID를 union하여 calibration40문항, internal evaluation118문항을 고정했다. 제외쌍은 calibration에 있어 각각479/1,416쌍이 주 분모다. 전체158문항은 독립 신규 평가 데이터가 아닌 이미 관찰한 개발 표본이다. [Step1](STEP1_REPORT_KO.md), [audit](../artifacts/dataset_audit/audit.json), [split](../artifacts/dataset_audit/split.json).

Method는 원본 MCQ·언어·이미지·ID만 받는다. Gold span, parallel target 표현, R/T 질문, 정답, bbox, prior 정오는 사용할 수 없다. 평가/진단 코드는 별도 CLI다. Strict input schema와 file-open 차단 테스트로 이 경계를 검사했다. Oracle 모드는 명시적으로 `oracle_span_selective`로 구분한다. 조건별 pair·보기 순서·이미지 metadata는 동일하게 유지한다.

## Method 정의와 현재 설정

- Primary 계획: query-blind Qwen2.5-VL-7B visible-string extraction + text-only Qwen3-8B 자동 span 추출·번역. 이전 two-stage 고정 revision을 유지한다.
- GCSA/GUI_SEL: source context를 유지하고 자동 referent만 target inventory의 문자열로 교체한다. TXT_SEL은 동일 spans에 screen-blind 번역을 적용한다. GUI_FULL/TXT_FULL은 전체 질문·보기를 번역한다.
- GUI inventory는 원시 응답·원시 spelling과 정규화된 unordered inventory를 함께 보존한다. Icon/nontext·누락·모호한 후보는 abstain한다. 새 옵션 충돌이나 offset 오류는 원문 fallback이다.
- 초기 retrieval은 normalized exact, threshold1.0/margin0.05, **uncalibrated**다. LaBSE 코드 옵션은 있으나 실제 추론·threshold 선택은 수행하지 않았다. 모델 자기보고 confidence는 확률로 쓰지 않는다.
- Selective rewrite는 deterministic reverse-offset 치환으로 unedited 문자를 그대로 보존한다. Full/RFA의 번역 의미는 숫자·schema 검사만으로 보장되지 않는다.

## 실제 pilot 결과와 비용

기본 모델들이 캐시에 없어 임의로 primary 모델을 바꾸지 않았다. 대신 이미 캐시된 Qwen3-VL-8B-Instruct를 inventory와 translator 모두에 쓰는 **별도 smoke override**를 만들었다. 모델·설정 hash·raw output·코드 snapshot은 [압축 실측 자료](../artifacts/smoke_archive.tar.gz), [checksum](../artifacts/smoke_archive.tar.gz.sha256), [요약](../artifacts/smoke_summary.json)에 있다.

`booking_1` EN→ZH 한 쌍에서 inventory는 34개 normalized unique string을 반환했다. Extractor는 `{"referents":[]}`를 반환했다. 사후 gold span5개 대비 recall/F1은0이고 precision 분모는 없다. TXT_SEL·GUI_SEL은 원문을 유지했으므로 **GUI matching 효과를 이 사례에서 검증할 수 없다**. Full 번역 두 조건은 정상 JSON을 생성했다. GUI_FULL은 예를 들어 Rooms를 화면 inventory의 `客房` 표기로 사용했지만, 그 사실이 REL 정답 개선의 근거는 아니다.

같은 Qwen3 downstream 조건의 생성 답은 O/TXT_FULL/GUI_FULL/TXT_SEL/GUI_SEL 모두A, 정답B로 모두 오답이었다. 과거 같은 pilot O도A였으나 배치4와 새 배치3이 다르다. 이 한 O 일치는 ExpA O/R 전체의 재실행 안정성 검증이 아니다. 대표 recovery는 이 smoke에서 **없고**, regression의 성능 차이를 추정할 표본도 없다. [Step2](STEP2_REPORT_KO.md), [Step3](STEP3_REPORT_KO.md).

Backend 실측은 inventory77.21초, extraction2.22초, TXT_FULL22.29초, GUI_FULL25.05초, 합계126.78초다. 입력2,985/output392 tokens, 모델 load 제외다. 빈 추출 때문에 selective 번역·matching 실행 비용은 측정되지 않았다. GPU 대여료·총 달러 비용은 자료가 없어 계산하지 않았다. 현재 환경은 B200 MIG45GB이며 이 시간을4090 비용·throughput으로 읽을 수 없다.

## 아직 없는 결과

| 요구 지표 | 현재 값 |
| --- | --- |
| Calibration/internal-evaluation 2×2 accuracy·CI·Holm | 미측정 |
| GUI_SEL−O / TXT_SEL / GUI_FULL | 미측정 |
| T_REF/R_REF와 자동 method 성능 격차 | 미측정 |
| GUI 언어·12방향·worst-pair 성능 | 미측정 |
| Matching precision·incorrect replacement | 독립 screenshot 검수 미완료, null |
| Thai GUI 실패율 | 미측정; 중국어 pilot 실패를 Thai 일반성으로 확장하지 않음 |
| RFA pivot 추가효과·translation error율 | 미측정 |

분석기는 paired generation outcome, 실패 포함, semantic-item bootstrap10,000회·95%CI·primary3대비 Holm, recovery/regression 및 언어별 결과를 구현했고 synthetic fixture로 검사했다. 아직 실제 main 예측이 없으므로 이 코드의 출력 수치를 연구 결과로 채우지 않았다. Calibration과 evaluation을 합친 전체 development 성능을 held-out 성능으로 보고하지 않는다.

## 재개 순서와 구체적 blocker

1. **기본 checkpoint 확보:** Qwen2.5-VL-7B와 text-only Qwen3-8B는 현재 개인 캐시에 없다. Qwen2-VL-7B나 Qwen3-VL-8B를 동일 모델로 취급하지 않는다. InternVL3.5-8B downstream 체크포인트도 없다. 새 대형 모델 다운로드·유료 인스턴스 생성은 실행하지 않았다.
2. 기본 설정으로 pilot smoke를 재검사해 span과 유효 편집이 실제로 나오는지 확인한다. 현재 대체 smoke의 빈 추출 원인을 성공으로 덮지 않는다.
3. Calibration40문항에서만 extraction prompt/threshold/fallback을 선택하고 version을 동결한다. Screenshot matching 검수 표를 채워 OCR 누락과 잘못된 대응을 구분한다.
4. 두 downstream 모델의 작은 O/R 재실행 검사를 보강하고, 고정한 조건별 batch composition으로 internal evaluation1,416쌍을 실행한다. Raw·config·token·실패를 포함해 보고한다.
5. 그 후에만 EN/model-pivot 조건과 translation 오류 검사를 수행한다. 방향·부정·인접 의미 검수와 RFA paired 분석은 아직 완성되지 않았다.

[README의 실행·복원 명령](../README_KO.md)을 따른다. 새 파일만 커밋하며 frozen 입력의 전후 hash가 동일한지 검사한다. 전체366문항 확장·추가 모델 일반화 실험은 수행하지 않았다.

## 검증과 커밋

관련 CPU 테스트 **18개 통과**, Python 구문·문서 로컬 링크·Bash 명령 블록 검사 통과, frozen artifact hash 재검증 통과다. 코드와 데이터 감사/분할 milestone은 `c0f4227`에 기록했다. 실측 smoke의 실패와 비용을 보존하는 보고·원시 압축 자료는 별도 커밋으로 남긴다. 유료 인스턴스는 생성하지 않았고, 원격 push는 수행하지 않았다.
