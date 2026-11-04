# Qwen `addCriterion`과 미완성 좌표 응답 진단

점검일: 2026-11-04. [저장된 원시 출력 224개](QWEN_RAW_OUTPUT_AUDIT_KO.md), 실행 코드, 현재 로컬 환경과 Qwen·Transformers·PyTorch의 1차 자료를 대조했다. **발생 경로는 좁혔지만 원인 하나로 확정하지는 못했다.** 현재 개인 캐시에 체크포인트 가중치가 남아 있지 않아, 모델을 다시 적재하는 대조 추론은 하지 않았다.

## 현재 실제 설정

| 항목 | 이번 grounding 파일럿 | 이전 REL full |
| --- | --- | --- |
| 모델 | 동일한 Qwen2.5-VL-7B-Instruct revision `cc594898...` | 동일 |
| 가중치·attention | BF16, Hugging Face `sdpa` | BF16, `sdpa` |
| 전처리 | 이미지 1장, `min_pixels=262144`, `max_pixels=2097152` | 동일한 픽셀 설정 |
| 배치·패딩 | 배치 1, tokenizer 왼쪽 패딩 | 배치 32, 왼쪽 패딩 |
| 적재 | 5개 체크포인트 shard를 순서대로 검증·GPU 적재 | `from_pretrained` |
| 생성 | greedy, 최대 64개 새 토큰, 좌표 출력 | greedy, 최대 2개 새 토큰, A–D 출력 |

근거: [파일럿 러너](run_qwen_pilot.py), [기존 모델 설정](../../01_code/configs/models/qwen2_5_vl_7b.yaml), [기존 어댑터](../../01_code/src/mpr_crosslocale/models/qwen25vl.py), [REL 실행 계약](../results/full/qwen2_5_vl_7b_batch32/run_contract.json). 어댑터 생성자의 기본값은 `flash_attention_2`이지만, **실제 REL 설정은 `sdpa`로 덮어쓴다.** 파일럿은 `config._attn_implementation="sdpa"`를 명시한다. 설치된 Transformers 4.57.6에서 빈 모델을 CPU로 구성해 확인한 결과, 이 값은 vision과 language 하위 구성으로도 전달됐다. 파일럿 코드에는 attention hook, `output_attentions=True`, attention mask 수동 수정, `torch.compile`, SDPA 커널 강제가 없다. 외부 `flash-attn` 패키지도 설치돼 있지 않다.

파일럿은 체크포인트의 `generation_config.json`을 그대로 읽은 뒤 `do_sample=False`, `num_beams=1`, `max_new_tokens=64`로 호출한다. 로컬 설정에 남는 값은 `repetition_penalty=1.05`, EOS ID `[151645, 151643]`, `use_cache=True`다. 체크포인트의 `do_sample=True`와 `temperature=1e-6`은 호출 인자에서 greedy로 덮인다. 반복 패널티가 이번 이상 출력을 일으켰다는 근거는 없지만, 대조 추론에서는 이 값과 실제 종료 ID도 기록해야 한다. 파일럿 결과에는 설치 패키지 버전이 따로 저장되지 않았으므로 **현재 환경의 4.57.6을 파일럿 실행 당시 버전으로 확정할 수는 없다.**

다만 Hugging Face의 `sdpa`는 PyTorch 함수 호출 방식이다. CUDA에서 실제로 실행한 내부 커널은 입력에 따라 자동 선택될 수 있다. 현재 결과 파일에는 커널 추적 정보가 없으므로 “Flash 계열 커널이 전혀 실행되지 않았다”라고 말할 수는 없다. [PyTorch 2.9 SDPA 문서](https://docs.pytorch.org/docs/2.9/generated/torch.nn.functional.scaled_dot_product_attention.html)는 커널 자동 선택과 수치 차이를 명시한다.

모델 YAML의 `vision_token_limit: 2048`은 이 실행 경로에서는 기록용 값이며, 실제 전처리 상한은 `max_pixels`가 정한다. 저장된 화면의 이미지 grid를 계산하면 대체로 약 2,600개의 시각 토큰이 들어간다. 2,048개로 잘라 쓰는 설정이라고 해석하면 안 된다. 이 차이가 이상 출력의 원인이라는 증거는 없다.

체크포인트 shard는 다운로드 시 크기와 SHA-256을 확인했고, 적재한 729개 tensor 이름은 모델의 state dict와 일치한다. 이것은 파일 손상이나 이름 누락 가능성을 줄이지만, **수동 적재와 `from_pretrained`의 logits가 같은지는 아직 검사하지 않았다.**

## 저장된 출력이 말하는 것

- 전체 관계 질문을 쓴 대조군에서 `addCriterion`은 JSON 0/8, `(x, y)` 2/8이다. 짧은 기준 표현을 쓴 대조군에서는 JSON 5/8, `(x, y)` 1/8이다.
- 짧은 기준 표현 O/R 96개씩에서는 JSON **41/96**, `(x, y)` **35/96**에 나타났다. 같은 96개 입력을 두 형식으로 비교하면 양쪽에서 나타난 것이 25개, JSON에서만 16개, `(x, y)`에서만 10개다. 두 형식에서 무효 응답은 합계 97/192개이고, 그중 76개에 `addCriterion`이 있다. 출력 형식에 민감하지만 JSON만의 문제는 아니다.
- O/R의 `addCriterion` 포함 응답 **76개 중 40개는 64토큰보다 먼저 종료**했고, 36개는 상한에 닿았다. 따라서 토큰 상한은 일부 미완성 응답을 설명하지만, 이상 토큰의 등장과 이른 종료 전체를 설명하지 못한다. 저장 파일은 특수 토큰 ID와 종료 이유를 기록하지 않았으므로, 조기 종료 40개가 실제 EOS를 생성했는지는 재추론 때 확인해야 한다.
- 12개 화면별 문항 중 `weather_3`에서 15/16, `music_7`에서 14/16에 나타난다. 반면 시각 토큰 수가 `music_7`과 같은 `settings_2`에서는 0/16이다. 입력 화면·문구와의 상호작용은 크지만, **이미지 토큰 길이만의 효과도 아니다.**
- `addCriterion`은 프롬프트에 없고 Qwen tokenizer의 일반 토큰 하나(`ĠaddCriterion`, ID 18724)로 인코딩된다. 저장된 `raw_output`은 생성된 suffix를 decode한 값이다. 파서나 Markdown 생성기가 붙인 글자가 아니다. 단, 출력의 원래 토큰 ID를 저장하지 않아 해당 표면 문자열이 실제로 한 토큰으로 생성됐는지는 확인할 수 없다.
- 동일 입력으로 다시 실행한 대조군 16개는 저장된 텍스트와 같았다. 무작위 sampling 변동으로 생긴 현상이라는 설명은 약하다. 이전 REL full의 18,432개 `generated_text`에는 이 문자열이 없지만, 그 실행은 **2토큰 A–D 과제**여서 이번 좌표 생성의 음성 대조군으로 삼을 수 없다.

`addCriterion`이 없는 실패도 있다. 일부는 `[]`, `None`, 닫히지 않은 좌표이고, 전체 관계 질문은 기준 요소와 답 요소를 혼동할 여지도 있다. 따라서 모든 grounding 오류를 이 이상 토큰 한 가지로 환원할 수 없다.

## 알려진 사례와 이번 조건의 차이

1. Qwen 저장소의 [동일 증상 보고](https://github.com/QwenLM/Qwen3-VL/issues/759)에는 배치·오른쪽 패딩, `eager`/FA2 변경, Transformers 버전과 관련된 경험담이 섞여 있다. 최초 보고자는 **배치 1에서도** 발생했다고 밝혔다. [Qwen 모델 토론의 한 재현](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct/discussions/54)은 왼쪽 패딩으로 해결됐지만, 우리 파일럿은 이미 배치 1·왼쪽 패딩이다. 해당 해결책을 그대로 적용할 조건이 없다.
2. Transformers의 [Qwen2.5-VL 통합 테스트](https://github.com/huggingface/transformers/blob/main/tests/models/qwen2_5_vl/test_modeling_qwen2_5_vl.py)에는 CUDA에서 `addCriterion`이 섞인 **잘못된 응답을 기대값으로 남기고 FIXME를 단 사례**가 있다. 공식 테스트에서도 나타나는 출력 이상이라는 강한 정황이지만, 그 시험은 FA2와 혼합 배치이므로 우리 SDPA·배치 1의 직접 재현은 아니다.
3. [Transformers의 attention 비교 이슈](https://github.com/huggingface/transformers/issues/39067)는 Qwen2.5-VL의 이미지 입력에서 SDPA·FA2·eager 간 logits 차이를 보고한다. Qwen 개발자는 vision encoder의 수치 민감성과 이미지 크기 영향을 지적했다. 우리 이미지가 대체로 약 2,600개의 시각 토큰을 쓰는 점과 함께 보면 attention 수치 경로는 **검증할 가치가 있는 후보**다. 같은 길이의 정상 사례가 있으므로 확정 원인은 아니다.
4. Transformers 4.55.0의 [Qwen2.5-VL 위치 인덱스 회귀](https://github.com/huggingface/transformers/issues/40154)는 실제 문제였지만, [4.57.0 릴리스](https://github.com/huggingface/transformers/releases/tag/v4.57.0)에 관련 수정이 포함됐다. 현재 설치 버전은 4.57.6이며 로컬 모델 구현에도 수정된 위치 처리 경로가 있다. 다만 저장된 파일럿 결과에 당시 버전이 없어 과거 실행 환경까지 확정할 수는 없다. **증상이 비슷하다는 이유만으로 다운그레이드하거나 이 회귀라고 판정할 수 없다.**

## 원인을 가르는 최소 대조

1. **먼저 적재 경로를 검증한다.** 동일한 체크포인트·전처리 결과·`sdpa`·BF16·생성 설정에서 파일럿의 shard 적재와 공식 `from_pretrained`를 각각 실행한다. 이미 실패한 `weather_3` 한 입력과 정상인 `settings_2` 한 입력으로 시작한다. 완성 문자열만 비교하지 말고 첫 토큰 및 `addCriterion` 직전의 top-k logits, 생성 token ID, EOS/64토큰 종료 여부를 기록한다. 두 경로가 같으면 수동 적재 원인을 제외할 수 있다.
2. **그 다음 attention을 한 변수로 비교한다.** 적재 경로를 고정한 채 같은 입력·이미지 크기에서 `sdpa`와 `eager`를 비교한다. `flash_attention_2`는 현재 설치돼 있지 않으므로 별도 설치를 전제하지 않는다. 45GB MIG 메모리에서 `eager`의 큰 이미지 입력은 부담이 될 수 있어 짧은 입력에서 메모리부터 확인해야 한다. 결과가 달라지면 vision/text attention 및 생성 단계별 logits를 좁혀 본다. 출력이 같으면 attention 교체만으로 설명하기 어렵다.
3. **마지막으로 입력 민감도를 확인한다.** 적재·attention을 고정하고 동일 문항의 JSON/괄호 형식, 이미지 `max_pixels`, 전체 질문/짧은 표현을 하나씩 바꾼다. 이 단계는 원인 추적용이며, 이미 본 파일럿에서 선택한 유리한 설정을 확정 프로토콜 성능으로 보고하지 않는다.

현재 개인 캐시에는 모델 설정·토크나이저·index만 있고 가중치 shard는 없다. 위 대조에는 체크포인트 재다운로드와 GPU 적재가 필요하다. 이번에는 저장 결과의 CPU 분석까지만 수행했다. **현재 가장 강한 결론은 “우리가 attention을 중간에 변조해서 생긴 오류”라는 증거가 없고, Qwen2.5-VL의 멀티모달 생성 경로·입력과 형식의 상호작용 또는 아직 미검증인 적재 경로가 남아 있다는 것**이다. 모델 원인을 확인하기 전에는 `addCriterion` 제거, 첫 숫자쌍 강제 추출, 토큰 상한 증가를 정상 응답의 대체물로 사용하면 안 된다.
