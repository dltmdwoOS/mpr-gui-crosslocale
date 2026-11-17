# 외부 연구 기반 baseline: Translate-Test와 CLP의 GUI-REL 이식

2026-11-17. 기본 범위는 기존 **158-item development set**, EN/ZH/TH/RU mismatch12방향, Qwen3-VL-8B다. 실행은 기존 batch 구성의1944쌍(pilot48 포함)을 유지하고, 주 분석은 기존 제외1쌍과 pilot을 뺀1895쌍이다. 새로운 질문·모델·데이터 분할을 선택하지 않는다.

## 원 구현 확인과 적용 범위

| 조건 ID | 원 연구 | 확인한 저자 저장소 | 현재 적용 |
| --- | --- | --- | --- |
| `TRANSLATE_TEST_EN_QWEN3` | [Song et al., NAACL Findings2025, §6.1](https://aclanthology.org/2025.findings-naacl.144/) | [고정 commit README](https://github.com/yueqis/Multilingual_Visual_Reasoning/blob/c326ad0eeb94c7a7eda76dff57225ad707451bf5/README.md), [GPT-4V 소비 코드](https://github.com/yueqis/Multilingual_Visual_Reasoning/blob/c326ad0eeb94c7a7eda76dff57225ad707451bf5/gpt4v/marvl/gpt4v.py) | Full MCQ→English, 원본 screenshot 유지, 기존 A–D VLM 풀이 |
| `CLP_GUI_LM_VLM` | [Qin et al., EMNLP2023, §3](https://aclanthology.org/2023.emnlp-main.163/) | [고정 commit request.py](https://github.com/LightChen233/cross-lingual-prompting/blob/affd839ba89745cf181a405395a1b410c41871d5/request.py) | LM 영어 이해 응답→대화에 보존→원본 screenshot을 받는 VLM의 단계별 풀이 |

원 논문 결과의 재현과 구분한다. Translate-Test 원 논문은 **Google Translate API**를 사용하고, 공개 GPT-4V 코드는 CSV의 statement를 읽어 추론한다. 번역 API 자체를 그 파일이 구현한다고 보지 않는다. 이번에는 기존 **Qwen3-8B LM**으로 번역한다. 유료 API·자격 증명·새 가중치 다운로드는 사용하지 않는다.

CLP 공식 코드는 GPT-3.5에 source-language 이해 요청을 보내고, assistant 응답을 같은 대화에 남긴 뒤 arithmetic solver 요청을 추가한다. Sampling temperature는1.0/0.2다. 이번에는 **고정 LM→평가 VLM**, arithmetic→GUI spatial reasoning, 숫자 답→A–D, greedy로 변경한다. 두 단계 상호작용은 유지한다. CLSP의 여러 경로 샘플링·투표는 수행하지 않는다. 이 baseline을 단순 English 번역이나 label-only solver로 바꾸지 않는다.

위 차이 때문에 결과는 **논문 기반 GUI adaptation**으로 표기한다. 순수 GUI evidence 효과나 특정 prompting 한 요소의 인과 효과로 단정하지 않는다. 현재 E1/M0와 같은 작업·데이터·고정 LM·평가 VLM을 쓰지만 CLP는 긴 solver 생성을 추가로 사용한다.

## 정확한 처리

**Translate-Test**

1. Screenshot·GUI language·reference·정답 없이 source MCQ의 stem과 A–D 전체를 LM에 제공한다.
2. English로 전체 번역한 `question_stem/options` JSON을 받는다. Source EN은 원문을 유지한다.
3. A–D 필드 구조를 검사하고 구조 실패만1회 repair한다. 이후에도 실패하면 원본 MCQ로 fallback하며 정확도 분모에 남긴다.
4. 원본 GUI screenshot과 번역 MCQ를 기존 label-only VLM에 제공한다. 최대2tokens, greedy, batch3, 기존 system/prompt 유지.

**CLP**

1. Source MCQ 전체를 고정 LM에 주어 English로 단계별로 이해하게 한다. 정답·이미지·inventory는 주지 않는다. System 문자열은 비워 두며 기존 text backend가 빈 system turn을 렌더링한다. 공식 user 요청의 구조를 사용한다.
2. VLM 대화는 `GUI solver system → 원래 CLP 이해 요청(user) → LM 이해 응답(assistant) → screenshot+GUI solver 요청(user)`다. 중간 이해 응답을 영어 번역 JSON으로 강제하거나 원문 대신 덮어쓰지 않는다.
3. VLM은 English로 풀이하고 마지막 줄에 `Answer: A`~`Answer: D`를 출력한다. 최대512tokens, greedy, batch3다. Step별 logits 전체를 저장하지 않는다.
4. 마지막 Answer 줄이나 단일 A–D 출력만 채점한다. 풀이 중에 등장한 보기 글자는 정답으로 추출하지 않는다. 미완료·형식 실패는 오답으로 남기며 후속 LM 정답 추출 호출을 추가하지 않는다.

GUI language는 알려진 데이터 metadata지만 두 전처리 prompt에서 사용하지 않는다. 원본 screenshot·pair ID·보기 순서·gold는 기존 데이터와 동일하게 유지한다. 추출 span·inventory·R/T/F 입력·bbox·정오를 자동 method에 제공하지 않는다. 공통 source MCQ가 GUI3언어에 반복될 때 전처리는 source 내용 key로 공유한다.

## 모델·메모리·실행 설정

- LM: `Qwen/Qwen3-8B`, `47719a242beab8f9aecc40ce3928b034dd5dd559`, non-thinking.
- VLM: `Qwen/Qwen3-VL-8B-Instruct`, `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`.
- BF16, SDPA, seed42, 2MP(min262144/max2097152), fast processor, patch embed `channels_last_3d`.
- LM batch1, 출력512tokens. Translate-Test 구조 repair512tokens 최대1회. CLP alignment는 자유 텍스트이며 별도 repair 없음.
- VLM batch3. TT는 기존2tokens/label scoring 유지. CLP는512tokens/label scoring 비활성화(`score_labels=False`), `logits_to_keep=1`·KV cache 사용.
- 입력4096tokens 상한, 초과 시 중단. 조용한 truncation·이미지 축소·batch 축소 없음. Model은 worker별 순차 적재하며 free40GiB 검사.

현재 8B VLM weight 파일 합은17,534,339,512bytes, 약16.33GiB다. Text decoder는36layers, KV heads8, head_dim128이다. BF16 KV는 token당147,456bytes로, batch3×(입력4096+출력512)에서약1.90GiB다. 출력2→512로 늘어나는 KV 약0.21GiB이며, 모든step logits를 반환하지 않아512step vocabulary tensor 누적도 피한다. LM weight는약15.26GiB, 같은 token 상한의 batch1 KV는약0.63GiB다.

이는 weight+KV 구성요소 계산이며 peak 상한은 아니다. Vision activation·SDPA/Conv3D workspace·allocator 여유가 필요하므로 실제3쌍 GPU smoke에서 기능·peak를 확인한 뒤 전체를 실행한다. 현재 할당은45GB MIG이며 smoke 전 free44.05GiB였다. 다른 GPU job과 동시 실행하지 않는다. CPU/thread는3 이하, 모델·패키지는 기존 개인 cache/venv를 사용한다.

GPU smoke 완료: TT/CLP 모두3/3개 최종 label 파싱 성공, TT 번역2건+English identity1건, CLP 이해3건 성공이었다. Peak reserved는 TT18.54GiB, CLP19.32GiB, CLP 최대 입력2782tokens였다. 이해 단계1건은512token 상한에 도달했고 최종 solver는3건 모두 상한 이전에 답을 냈다. 이를 전체 cap-hit율이나 정확도 개선으로 일반화하지 않으며 예산을 바꾸지 않았다. 원시는 `artifacts/external_baselines_smoke_v1/SMOKE_CHECK.json` 및 해당 stage에 보존했다.

## 실패·비용·분석

Prompt·기본값은 GPU smoke 전에 고정한다. Smoke는 EN/RU/ZH source의3쌍으로 기능만 확인하고 정답률을 보고 prompt를 고르지 않는다. 기능 오류를 고치면 새 버전/출력 경로를 사용한다. 전체 실행 후 source item 단위로 paired accuracy/회복·회귀·95%bootstrap CI를 계산한다.

숫자 sequence·새 중복 보기의 사후 경고를 기록한다. 구조 검증이나 이 경고만으로 부정·방향·의미 보존을 검증했다고 말하지 않는다. CLP의 토큰 제한 도달·최종 label 실패도 보고한다. 결과를 보고 실패한 사례를 삭제하지 않는다.

비용은 **LM 번역/이해 + 최종 VLM 풀이**다. Source key와 batch를 중복 청구하지 않고 cache hit의 원래 runtime을 포함한 recipe와 실제 신규 wall을 구분한다. 초/pair의 분모는 해당 비용의 실행/주 분석 범위에 맞춘다. 기존 E1/M0 O baseline 예측을 재사용해 새 O 추론을 반복하지 않으며 그 provenance와 실행 설정 차이를 기록한다.

입력·고정 config·prompt/code SHA는 `contract.json`, 모든 raw LM 응답은 `translate/`·`alignment/`, VLM raw 출력·대화 template는 각 cohort의 `infer_tt/`·`infer_clp/`에 저장한다. 기존 frozen 결과는 수정하지 않는다. Source commit·capture SHA는 [외부 source manifest](../configs/external_baselines_sources.json), 정확한 adapter prompt는 [external_baselines.py](../external_baselines.py)에 있다.

```bash
bash followup_rel_4lang/method_dev/scripts/run_external_baselines.sh --smoke --run
```

```bash
bash followup_rel_4lang/method_dev/scripts/run_external_baselines.sh --run
```

전체 평가와 종료 후 CPU 보고서 생성을 연결한 명령:

```bash
nohup bash followup_rel_4lang/method_dev/scripts/run_external_baselines_full.sh > followup_rel_4lang/method_dev/artifacts/external_baselines_full.log 2>&1 < /dev/null &
```

완료 보고서는 `reports/EXTERNAL_BASELINES_RESULTS_KO.md`, 구조화 수치는 `artifacts/external_baselines_results_snapshot.json`이다. 새 O 풀이를 추가하지 않고 같은 cohort의 기존 O/E1 예측과 paired 비교한다. 완료 raw archive 및 source checksum도 자동 생성한다.

같은 명령으로 재개하면 완료 단계와 캐시를 재사용한다. 모형·입력·코드가 바뀌면 기존 계약에 이어 쓰지 않고 중단한다. CPU mock 결과는 실제 성능·비용으로 보고하지 않는다.
