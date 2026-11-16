# Oracle extraction 진단 실행안

이번에는 **기존 `GUI_EXACT`의 자동 referent 추출 결과만 annotation의 source span으로 교체**한다. 추출을 제대로 했어도 현재 번역·exact matching으로 REL 성능을 회복할 수 있는지 확인하는 진단이다. Automatic method의 새 성능으로 보고하지 않는다.

## 바꾸는 것과 유지하는 것

| 항목 | 설정 |
| --- | --- |
| Source referents | annotation의 원문 field·text·character offsets 사용 |
| ID·정렬 | 기존 자동 추출과 같은 `field:start:end`, `(field, start, end)` 순서 |
| 번역 | 같은 pinned Qwen3-8B, 같은 `TRANS_PROMPT`, 같은 JSON 인터페이스 |
| Inventory | 완료된 `GUI_EXACT`의 값을 그대로 재사용. 실패·빈 목록도 유지 |
| Matching | 기존 NFKC·casefold·공백 정규화 exact matching, threshold 1.0 / margin 0.05 |
| 편집 | 같은 deterministic replacement, context·A–D 순서 보존 |
| 실패 처리 | 기존 all-or-original fallback 유지. 개별 edit salvage는 이번에 추가하지 않음 |
| Downstream | 같은 pinned Qwen3-VL-8B-Instruct, BF16·SDPA·2MP·channels_last_3d, batch 3 |
| 실행 순서 | 각 cohort 안에서 Oracle만 pair ID 정렬. 기존 candidate와 같은 batch 구성원 유지 |

기존 고정 contrastive extractor는 모든 span을 `kind=label`로 반환했다. Oracle도 동일하게 처리하며 별도 요소 type 판단을 추가하지 않는다. 골드 span은 source text·offset·중첩·반복 출현을 검증한다. `ref_id` 및 예전 annotation ID는 모델에 전달하지 않는다. **Gold target label, R/T 질문, 정답, bbox는 rewrite 입력에 사용하지 않는다.** 정답 및 과거 예측은 후속 평가 경계에서만 읽는다.

Inventory와 extractor를 다시 호출하지 않는다. 번역 캐시는 기존 호출과 **전체 payload·모델·프롬프트·software·hardware 계약이 동일할 때만** 재사용한다. 서로 다른 호출에서 span별 번역을 잘라 조합하지 않는다. 원래 캐시에는 쓰지 않으며 새 캐시의 read-through symlink로 읽는다.

## 범위

| 순서 | Cohort | Item | 실행 pair | 주 분석 pair | 고정 inventory 실패 이미지 |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | Screen | 32 = main 20 + legacy pilot 12 | 288 | 240 | 10/128 |
| 2 | Selection | 20 | 240 | 239 | 3/80 |
| 3 | Internal evaluation | 118 | 1,416 | 1,416 | 28/472 |
| 합계 | main 158 + legacy pilot 12 | 170 | 1,944 | 1,895 | 41/680 |

기존 배치 구성을 유지하려고 pilot 48쌍과 사전 제외 pair `rel::5/forest_9.jpg::zh::ru`도 실행 입력에는 남겼다. 주 분석에서는 각각 분리한다. 이 분모를 맞추기 위해 비교 조건을 새로 추론할 필요는 없다.

## 실행

현재 서버의 `.venv`, pinned 모델 캐시, 완료된 `search_pipeline_v1`을 사용한다. 새 모델 다운로드나 환경 설치는 없다. 저장소 루트에서 다음 한 줄은 **Screen → Selection → Internal을 순차 실행**한다.

```bash
nohup bash followup_rel_4lang/method_dev/scripts/run_oracle_exact.sh > followup_rel_4lang/method_dev/artifacts/oracle_span_exact.log 2>&1 < /dev/null &
```

먼저 Screen만 확인하려면 다음 명령을 사용한다. 이후 위 전체 명령을 실행하면 완료된 Screen 단계는 재사용한다.

```bash
bash followup_rel_4lang/method_dev/scripts/run_oracle_exact.sh --cohort screen
```

로그에는 rewrite 20쌍마다, inference 약 60쌍마다 진행 수가 표시된다. 첫 모델 적재 중에는 진행 수가 잠시 갱신되지 않을 수 있다.

```bash
tail -f followup_rel_4lang/method_dev/artifacts/oracle_span_exact.log
```

중단 후에는 동일 명령을 사용한다. 완료된 rewrite/inference 단계는 건너뛰고, 미완료 attempt는 보존한 채 새 attempt를 만든다. 번역 캐시는 재사용한다. 미완료 inference는 해당 cohort를 처음부터 다시 수행하며 중간 예측을 이어 붙이지 않는다. 설정·코드·입력 hash가 달라졌으면 실행을 중단하므로, 의도적으로 변경할 때는 새 `--output-root`를 지정한다.

GPU를 쓰지 않는 확인 명령:

```bash
bash followup_rel_4lang/method_dev/scripts/run_oracle_exact.sh --stage prepare
bash followup_rel_4lang/method_dev/scripts/run_oracle_exact.sh --mock
```

실제 결과와 mock은 각각 `artifacts/oracle_span_exact_v1/`, `artifacts/oracle_span_exact_v1_mock/`로 분리된다. Mock은 정확도·CI를 산출하지 않는다.

## 메모리와 비용

현재 **45GB B200 MIG 전용**으로 GPU free memory 40GiB 이상을 요구하며, 이전 pipeline과 GPU lock을 공유한다. Translator는 batch 1, downstream은 batch 3이다. 두 단계는 별도 자식 프로세스에서 실행해 LM과 VLM을 동시에 적재하지 않는다. CPU thread는 최대 3개로 제한한다.

기존 계산에서 BF16 가중치는 LM 약 15.26GiB, VLM 약 16.33GiB다. 입력 최대 4,096 token, 번역 출력 최대 768 token, MCQ 출력 최대 2 token을 유지한다. Downstream KV cache 성분은 batch 3에서 약 1.69GiB이나 activation·workspace를 포함한 peak 상한은 아니다. 기존과 같은 실행 profile이지만 새 질문 길이에 따라 peak가 달라질 수 있으며, OOM 발생 시 자동 batch 축소나 실패 표본 제외를 하지 않고 중단한다. 24GB RTX 4090에 그대로 적용하는 profile은 아니다.

추가 계산은 새 Oracle referent 번역과 Oracle MCQ 평가뿐이다. O·Automatic·R·T·F는 기존 예측을 재사용한다. 새 소요 시간과 token 사용은 실행 후 raw calls/predictions에 기록되며, 아직 실측 소요 시간이나 Oracle 정확도를 제시하지 않는다.

## 결과 확인과 해석

각 cohort의 `REPORT_KO.md`와 `results.json`에 다음을 기록한다.

- 같은 primary pair의 O / Automatic GUI_EXACT / Oracle / T_REF / R_REF / F_REF 정확도.
- Oracle−Automatic을 중심으로 paired 차이, semantic-item bootstrap 10,000회 95% CI, 오답→정답 및 정답→오답.
- GUI 언어별 정확도, 실제 편집 수, match 수, fallback 상태와 비율.
- `paired_outcomes.jsonl`의 Automatic/Oracle 질문 및 pair별 정오 전환.
- `rewrite/attempt_*/calls.json`, `cost.json`의 번역 실패·cache hit·신규 호출 시간, `infer/attempt_*/predictions.jsonl`의 raw 답·token·batch 시간·GPU peak memory.

`T_REF`는 gold span + Gemma 번역, `R_REF`는 parallel referent alignment, `F_REF`는 parallel 전체 localization이다. 이들은 자동 Oracle 번역의 target label 정답이 아니다. 기존 report의 post-hoc loader로 모델·입력 대응을 검사한 후 같은 pair만 비교한다. 과거 run의 batch/queue 차이는 남는다.

**Oracle은 정확도의 엄밀한 상한이 아니다.** Annotation은 병렬 실험의 span 정의이며 실제 화면 대응이 모두 보장되지는 않는다. Referent 집합을 바꾸면 한 번에 번역하는 payload와 번역 응답도 달라진다. 같은 batch 구성원을 유지해도 동반 질문 길이와 padding은 달라질 수 있다. 자기 질문이 Automatic과 동일한데 답이 바뀐 사례는 별도로 집계한다.

큰 개선은 현재 pipeline에서 추출 교정이 중요하다는 근거가 된다. 개선이 작다면 번역·exact match coverage·inventory 실패·후속 REL 오류를 확인해야 하며, 이것만으로 추출 문제가 중요하지 않다고 결론 내리지 않는다. Flexible matching, NER, inventory-free matching은 이번 진단 결과를 확인한 후 별도 변경으로 비교한다. 이번 데이터는 이미 관찰된 development set이므로 결과를 보고 method를 바꾸면 그 사실을 기록한다.

준비 상태와 검증 기록: [`oracle_exact_readiness.json`](../artifacts/oracle_exact_readiness.json). 아직 실제 Oracle GPU inference 결과는 없다.
