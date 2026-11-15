# Smoke 재점검과 고정 LM 준비

2026-11-15. 이전 결과를 덮어쓰지 않고 같은 pilot `rel::1/booking_1.jpg::en::zh`를 짧게 재검사했다. 원래 모델 Qwen3-VL-8B의 고정 revision·BF16·SDPA·2MP·max_new_tokens384·greedy를 유지했다. GPU는 B200 MIG 2g.45gb, CPU는 3 thread다. 이 검사는 calibration이나 내부 성능 평가가 아니다.

## 변경한 실험 역할

사용자 결정에 따라 inventory는 **평가 VLM 자체**를 사용한다. 지금은 Qwen3-VL-8B가 대상이다. Qwen2.5-VL 및 InternVL3.5 실험은 이후 단계이며 현재 inventory 기본 모델로 요구하지 않는다.

참조 표현 추출은 다음 두 전략을 비교할 수 있게 역할을 분리했다.

- 고정 LM: text-only `Qwen/Qwen3-8B`, revision `47719a242beab8f9aecc40ce3928b034dd5dd559`.
- 평가 VLM의 backbone LM 활용: 후속 비교 대상으로 남긴다. 이번 Qwen3-VL의 no-image 호출 진단을 별도 backbone 추출 구현의 검증으로 부르지 않는다. Text-only Qwen3-8B와 multimodal 학습 후 VLM의 language weights는 같은 checkpoint가 아니다.

새 설정은 `configs/gcsa_qwen3_fixed_lm_v1.json`이다. Inventory/참조 추출/번역 모델을 각각 명시하고, inventory 모델이 evaluation_vlm과 다르면 거절한다. 이전 `gcsa_v0.json`과 첫 smoke는 역사적 기록으로 보존한다.

## 시간에 대한 실제 재계측

새 backend는 렌더링 프롬프트, 실제 input keys, model load, CPU 준비, 첫 forward, vision/patch, 후속 decode, 파라미터 device·dtype, patch weight stride와 선택 backend를 기록한다. 중첩 타이머 값이므로 모든 행을 더하면 안 된다. CUDA 동기화 hook의 오버헤드가 포함되며 원래 비계측 시간과 완전히 같은 경로는 아니다. 다운로드와 동시에 실행한 진단이므로 절대 처리량 benchmark로도 취급하지 않는다.

| Inventory 구간 | 재계측 |
| --- | ---: |
| 전체 호출, 모델 load 제외 | 79.102초 |
| 첫 model forward | 2.087초 |
| 첫 처리 안의 vision encoder | 1.097초 |
| vision 안의 patch Conv3D | **0.117초** |
| 후속 token forward 합계 | **76.478초** |
| 출력 token | 226 |

실제 Conv3D weight stride는 `[1536,1,768,48,3]`, BF16, `channels_last_3d=True`였다. 실제 patch 입력은 `[8040,3,2,16,16]` BF16이고 dispatcher의 선택은 `_ConvBackend.Cudnn`이었다. 이 화면에서는 이전 **SlowDilated3d 병목 재발이 관찰되지 않았다**. 79초 대부분은 약225회의 후속 토큰 생성에 소요됐다. 첫 smoke의 약77초는 이 재계측과 비슷하다. Inventory 원시 문자열 목록도 첫 실행과 정확히 같았다.

따라서 이전 77초를 단순히 “이미지 인코더가 다시 느리다”고 해석할 근거는 없다. 반대로 이 한 화면에서의 경로 확인을 모든 입력·다른 GPU의 성능 보장으로 확대하지 않는다. 긴 OCR 응답은 좌표7–11토큰 또는 객관식2토큰을 생성하던 이전 실험과 출력량이 다르다.

## 빈 referent 응답은 어디서 생겼나

| 진단 | 입력/지시 | 응답 |
| --- | --- | --- |
| 첫 smoke | 원래 참조 추출 지시 | 빈 referents |
| 같은 모델에서 inventory 뒤 재검사 | 동일 지시·동일 MCQ | 빈 referents |
| 새 프로세스에서 텍스트만 입력 | 동일 지시·동일 MCQ | 빈 referents |
| 새 프로세스의 literal-copy 대조 | 따옴표 안 문자열을 복사하라는 별도 지시 | **5개 모두 반환** |

텍스트-only 재검사의 실제 input keys는 `input_ids,attention_mask` 두 개였다. Image/video tensor가 없었고 vision/patch 호출도0회였다. 모델 파라미터는 모두 CUDA0·BF16이었다. 렌더링 프롬프트에는 Search·Adults·Children·Rooms·Check-out date 다섯 표현이 모두 있었으며, inventory 뒤 호출과 fresh 호출의 prompt/payload hash가 같았다. 따라서 원문 누락, 이미지 연산 지연, 직전 이미지 호출의 상태 오염이 원인이라는 근거는 현재 없다.

원래 지시는 정상 JSON `{"referents":[]}`를6토큰으로 반환했다. Token limit에 잘린 것이 아니다. Literal-copy 대조는 주어진 원문의 따옴표만 기준으로 다섯 span을 정상 schema로 반환했고 약57.97초가 걸렸다. 원래 지시로는 약2.4–2.9초였다. 여기서도 길어진 JSON의 후속 token 생성 비용을 분리해서 읽어야 한다.

가장 좁게 지지되는 해석은 **원래 추출 지시와 이 모델의 task 해석 사이 문제**다. Qwen3-VL이 텍스트를 읽거나 structured span을 반환하는 능력 자체가 없다고 결론 내릴 수 없다. 어떤 단어나 예시가 빈 출력을 유도했는지까지는 통제 실험하지 않았다. Literal-copy 대조는 따옴표 없는 참조·아이콘 표현·문맥을 포함한 참조의 일반 extractor가 아니며, 성능이 좋다고 production prompt로 교체하지 않았다.

## 고정 Qwen3-8B 다운로드와 다음 검사

`prepare_fixed_lm.py`는 개인 HF cache를 먼저 확인하고 pinned revision의 safetensors·config·tokenizer만 다운로드한다. 기존 다운로드를 재사용하며 worker는2개다. 전체 선택 파일은 **16,397,432,249바이트**, weight shard는5개다. 완료 후 shard의 LFS SHA-256과 byte size, weight index를 검증하고 manifest에 `verified=true`를 쓴다. Manifest가 나오기 전에는 다운로드/검증 완료라고 간주하지 않는다.

공식 Qwen3 템플릿의 `enable_thinking=False`를 명시한다. 기존 연구에서 사용한 greedy 설정은 그대로 두고 tokenizer template·모델 revision·generation 조건을 기록한다. [고정 Qwen3-8B 모델 카드](https://huggingface.co/Qwen/Qwen3-8B/blob/47719a242beab8f9aecc40ce3928b034dd5dd559/README.md).

다운로드 후 고정 LM에 **기존 추출 지시와 같은 pilot MCQ**를 그대로 넣는 한 호출을 검사했다. 이것은 모델 선택 효과를 확인하는 첫 비교다. 이후 필요한 prompt 변경은 pilot/calibration 데이터에서만 수행한다. Qwen2.5-VL·InternVL3.5 다운로드나 전체 method/REL 추론은 이번 작업에서 시작하지 않는다.


## 고정 LM 준비 완료 및 동일 지시 단건 결과

Qwen3-8B의 **13개 파일·16,397,432,249바이트** 다운로드와 검증이 완료됐다. Weight shard5개 모두 LFS SHA-256 일치, tokenizer.json의 LFS SHA-256도 일치했다. [준비 manifest](../artifacts/fixed_lm_ready.json)에 각 파일의 hash·바이트수를 기록했다. HF_HOME 기준 snapshot 경로는 manifest에 상대 경로로 남겼다. 캐시 외 별도 weight 복사본은 만들지 않았다.

고정 LM에 원래 추출 지시·동일 pilot·max384·greedy를 적용한 한 호출은 정상 JSON으로 **7개 span**을 반환했다. Qwen3 템플릿은 non-thinking으로 명시했다.

- Stem: `blue 'Search' button`, `horizontal center`, `number of guests`.
- A–D: `Adults`, `Children`, `Rooms`, `Check-out date`.

Annotated minimal span 기준으로 네 option은 정확하고 stem Search는 과도하게 넓다. `horizontal center`와 `number of guests`는 여기서 보호해야 할 문맥을 참조로 잡은 사례다. 사후 exact-span 진단은 TP4/predicted7/gold5, precision4/7, recall4/5, F1 약0.667이다. 한 pilot·한 언어쌍의 진단이며 일반 성능 추정이 아니다. 이 모델도 바로 production extractor로 통과시키지 않는다.

고정 LM 호출 시간은 약66.62초, output209토큰이었다. 긴 structured output의 비용도 고려해야 한다. 모델 load 시간과 첫 처리·decode는 원시 JSON에 따로 있다. 이번에는 추출 호출만 검증했고 이7개 span으로 MCQ를 실제로 고치거나 downstream 정답률을 재평가하지 않았다.

[재점검 실측 요약](../artifacts/smoke_reaudit_summary.json), [원시 JSON·당시 backend 압축](../artifacts/smoke_reaudit.tar.gz), [SHA-256](../artifacts/smoke_reaudit.tar.gz.sha256)을 보존했다. 기존 첫 smoke의 원시 자료는 변경하지 않았다. 새 계측/설정 관련 CPU 테스트는19개 통과했다.

현재 남은 단계는 이 고정 LM의 과다 추출·span 경계를 pilot/calibration에서 진단하고, 고정 LM 대 backbone LM 비교의 인터페이스·조건을 정한 뒤 본 2×2를 진행하는 것이다. Inventory는 앞으로 평가 VLM 자체를 사용하며 Qwen2.5-VL/InternVL3.5는 현재 준비의 blocker가 아니다.
