# Grounding annotation 평가 전 전달본 (2026-11-03)

이 묶음은 요소 종류 정렬 **전**의 평가 입력입니다. 179문항 중 4개 언어 어느 하나라도 두 검수자의 `status`, 메모, 의미 차이 표시 등에서 문제 신호가 있던 9문항을 문항 단위로 제외했습니다. 번역 `unreviewed`와 bbox 복사 확인 `pending`은 제외 근거로 사용하지 않았습니다.

- 포함: 170문항 × 4 GUI 언어 = 680화면. 그중 12문항은 파일럿, 158문항은 본 분석 후보입니다.
- 위치 출처: 52문항은 4개 화면의 저장된 bbox 합의안, 118문항은 `baegihyeon` 원본입니다.
- 요소 종류는 잠정 값입니다. 두 검수자의 종류가 다른 문항 중 아직 별도 정렬이 필요한 문항은 47개입니다. `element_role`을 확정 레이블이나 층화 기준으로 사용하지 마세요.
- `grounding_gt_draft_170.json`의 bbox는 **원본 이미지 픽셀** 좌표 `[x1,y1,x2,y2]`입니다. `image_path`는 저장소 최상위 디렉터리 기준입니다.
- 이미지 자체는 zip에 없습니다. 이미 실험 서버에 준비된 이미지를 재사용합니다.

## 실험 서버에 설치

zip을 **저장소 최상위 디렉터리** (`followup_rel_4lang/`가 보이는 위치)에 옮깁니다. 예시는 그 디렉터리에서 실행합니다.

```bash
cd /path/to/mpr-gui-crosslocale
unzip -t grounding_eval_annotations_20261103.zip
unzip -q grounding_eval_annotations_20261103.zip -d .
python3 followup_rel_4lang/grounding_eval/annotations_20261103/verify.py --images
```

이 명령은 `followup_rel_4lang/grounding_eval/annotations_20261103/` 아래에만 파일을 풉니다. `--images`는 680개 원본 이미지의 SHA-256까지 확인합니다. 이미지가 아직 없으면 저장소 최상위 디렉터리에서 먼저 다음을 실행한 뒤 위 검증을 다시 실행하세요.

```bash
python3 followup_rel_4lang/data_bundle.py unpack
python3 followup_rel_4lang/data_bundle.py fetch-images --workers 3
python3 followup_rel_4lang/data_bundle.py verify
python3 followup_rel_4lang/grounding_eval/annotations_20261103/verify.py --images
```

`verify.py`는 Python 표준 라이브러리만 사용합니다. 이미지 해시 확인을 생략하고 데이터와 manifest만 검사하려면 `--images` 없이 실행할 수 있습니다. 현재 브랜치의 `annotation/rel_grounding/data/full_manifest.json` SHA-256은 `453fdb7d9e81dbca7443e1cd4c5eff411135f062fc964cf575ae10c601d85d0f`여야 합니다. 이 파일은 확인한 원격 `followup-rel-4lang-inference` 브랜치 커밋 `8bf5e49ed96750df4a2f5a6fb9309fabbbb857c1`과 동일합니다.

## 파일

- `grounding_gt_draft_170.json`: 모든 필드를 유지한 잠정 통합 annotation. `gt_assembly.item_sources`에 문항별 출처와 `pilot_item_ids`가 있습니다.
- `targets.jsonl`: 평가 코드에서 읽기 쉬운 680행 평면 목록. 각 행에 문항 ID, GUI 언어, 원본 이미지 상대 경로·SHA-256, bbox·중심, 기준 표현, 잠정 요소 종류, `pilot`/`main` 분할과 출처가 있습니다.
- `excluded_items.json`: 9문항을 제외한 원본 플래그와 언어별 근거.
- `audit/`: 두 검수자의 원본 full JSON과 bbox 합의 기록. GT를 재구성하거나 추적할 때 사용합니다.
- `checksums.json`, `verify.py`: 전달 파일·manifest·이미지 검증.

현재 원격 브랜치에는 이 GT를 사용해 모델의 위치 응답을 채점하는 **grounding 평가 러너가 없습니다**. 이 zip은 데이터와 재현 자료를 준비합니다. 모델 실행에는 별도의 위치 지정 프롬프트, 출력 파서, 원본 픽셀 좌표 변환 및 `point-in-GT-box` 채점 구현이 필요합니다. 본 분석에서는 `split == "main"` 158문항만 선택하고, 12문항 파일럿은 출력 형식 확인에 사용하세요.
