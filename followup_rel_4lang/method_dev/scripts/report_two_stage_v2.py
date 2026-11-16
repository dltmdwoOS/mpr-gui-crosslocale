"""Render the complete prompt/config contract directly from executable v2 definitions."""
import difflib
import json
import sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(REPO),str(REPO/'01_code/src')]
from followup_rel_4lang.method_dev.two_stage_v2 import legacy,prompts
from mpr_crosslocale.methods.selective_alignment.schemas import digest,render,fields
from mpr_crosslocale.inference.prompts import build_prompt_text
from mpr_crosslocale.inference.runtime import software_versions


def catalog():
    # Synthetic illustration only: all real calls substitute the actual allowlisted MCQ.
    row={'source_language':'en','gui_language':'zh','question_stem':"Which element is directly above 'Settings'?",
         'options':{'A':'Privacy','B':'Home','C':'Help','D':'Exit'}}
    inventory={'visible_strings':['帮助','主页','设置','退出','隐私']}
    start=row['question_stem'].index('Settings');refs=[{'span_id':f'question_stem:{start}:{start+8}','field':'question_stem','text':'Settings'},
        {'span_id':'A:0:7','field':'A','text':'Privacy'}]
    gui=prompts.original(row,inventory);txt=prompts.original(row)
    previous='<PREVIOUS_RAW_OUTPUT>';errors=['<VALIDATION_ERROR>'];reasons=['<SEMANTIC_REPAIR_REASON>']
    return {
        'I0':('inventory',legacy.INVENTORY_SYSTEM_PROMPT,legacy.INVENTORY_USER_PROMPT),
        'I1':('inventory_repair',legacy.INVENTORY_REPAIR_SYSTEM_PROMPT,legacy.INVENTORY_USER_PROMPT+legacy.INVENTORY_REPAIR_SUFFIX),
        'E0':('extract',prompts.EXTRACT_SYSTEM,prompts.extraction_user(row)),
        'E1':('extract_repair',prompts.EXTRACT_SYSTEM,prompts.extraction_user(row,previous,errors)),
        'FG0':('full',legacy.LEXICAL_SYSTEM_PROMPT,legacy.build_lexical_user_prompt(gui)),
        'FG1':('full_repair',legacy.LEXICAL_SYSTEM_PROMPT,legacy.build_lexical_repair_prompt(gui,previous,errors)),
        'FG2':('full_semantic_repair',legacy.LEXICAL_SYSTEM_PROMPT,legacy.build_lexical_semantic_repair_prompt(gui,previous,reasons)),
        'FT0':('full',legacy.SYSTEM_PROMPT,legacy.build_user_prompt(txt)),
        'FT1':('full_repair',legacy.SYSTEM_PROMPT,legacy.build_repair_prompt(txt,previous,errors)),
        'FT2':('full_semantic_repair',legacy.SYSTEM_PROMPT,legacy.build_semantic_repair_prompt(txt,previous,reasons)),
        'SG0':('selective',prompts.SELECTIVE_GUI_SYSTEM,prompts.selective_user(row,refs,inventory)),
        'SG1':('selective_repair',prompts.SELECTIVE_GUI_SYSTEM,prompts.selective_user(row,refs,inventory,previous,errors)),
        'ST0':('selective',prompts.SELECTIVE_TXT_SYSTEM,prompts.selective_user(row,refs)),
        'ST1':('selective_repair',prompts.SELECTIVE_TXT_SYSTEM,prompts.selective_user(row,refs,None,previous,errors)),
    },row


def main():
    config=json.loads((ROOT/'configs/two_stage_v2.json').read_text());items,row=catalog();manifest=json.loads((ROOT/'two_stage_v2/legacy_manifest.json').read_text())
    lines=['# Two-stage 재정비: 실험별 전체 프롬프트와 inference config','',
        '**상태: 재실행 준비. 아래 정의로 기존 결과를 덮어쓰거나 전체 GPU 실험을 시작하지 않았다.** 초기·repair·의미 repair·문제 풀이까지 실행 코드에서 직접 렌더링한 계약이다.','',
        '## 1. 앞선 Screen 설명','',
        '`GUI_MATCH_LM`은 Screen 실행 288쌍 중 main 240쌍을 주 분석했고 pilot 48쌍은 분리했다. Selection과 Internal은 수행하지 않았다. “전체 질문 문맥 없이”는 번역/매칭 모델이 source stem·A–D 전체 문장을 받지 않고 자동 추출 referent 목록과 inventory만 받았다는 뜻이다. Downstream 문제 풀이 모델에는 수정된 전체 MCQ와 screenshot을 제공했다.','',
        '## 2. 기존 결과 처리와 복원 기준','',
        '사용자 결정에 따라 기존 GUI_FULL, GUI_EXACT, GUI_MATCH_LM 및 Oracle GUI_EXACT 등 inventory 기반 결과는 **의도한 two-stage 방법의 유효한 평가에서 제외**한다. 원시 산출물·코드·hash는 이력으로 보존한다. 기존 TXT/direct-visual 결과까지 재실행 성공으로 간주하거나 삭제하지 않는다. 새 실행은 `artifacts/two_stage_v2/`, 새 mock은 `artifacts/two_stage_v2_mock/`를 쓴다.','',
        f"복원 기준 커밋: `{manifest['source_commit']}` (`origin/paper-freeze-20260814`). 과거 GUI lexical 및 contextual 모듈에서 순수 함수와 상수 {len(manifest['symbols'])}개를 원문 그대로 분리했다. [legacy_manifest.json](../two_stage_v2/legacy_manifest.json)에 함수별 원문 SHA-256과 위치가 있다. Gold target·R 질문·정답·bbox를 변환기에 제공하지 않는다.",'',
        '그대로 복원한 부분은 inventory 초기/repair system·user, 전체 GUI 및 text-only 번역 초기/구조 repair/의미 repair prompt, inventory parser·정규화·반복 복구, 구조/의미 진단과 repair 채택 규칙이다. **선택적 편집은 과거에 없던 작업**이므로 full-translation 지시를 그대로 붙이지 않고 SG/ST라는 명시적 새 adaptation으로 나눴다.','',
        '유지하거나 달라진 부분: 평가 및 inventory는 현재 Qwen3-VL-8B(과거 추출은 Qwen2.5-VL), 고정 text LM은 Qwen3-8B다. 과거 translator batch2 대신 method batch1을 사용한다. 데이터는 기존 4언어 158 main item과 별도 pilot이며 과거 6언어 전체셋을 재현하는 작업은 아니다. 입력 한도 4096을 넘으면 truncate하지 않고 중단한다. Full 번역이 구조 repair 후에도 실패하면 O로 fallback하여 모든 pair를 ITT에 유지한다.','',
        '## 3. 실험 단위와 연결되는 모든 prompt','',
        '| 실험 | Inventory | Span | 번역·정렬 입력 | 변환 범위 | Prompt 경로 |','| --- | --- | --- | --- | --- | --- |',
        '| TS_FULL_GUI | 신규 공통 inventory | 명시 추출 없음 | 전체 MCQ + inventory | 전체 번역 | I0→필요시 I1; FG0→필요시 FG1/FG2; V0 |',
        '| TS_FULL_TXT | 미제공 | 명시 추출 없음 | 전체 MCQ | 전체 번역 | FT0→필요시 FT1/FT2; V0 |',
        '| TS_SEL_GUI_AUTO | 같은 신규 inventory | 자동 | 전체 MCQ + span 목록 + inventory | referent만 | I0/I1; E0→필요시 E1; SG0→필요시 SG1; V0 |',
        '| TS_SEL_TXT_AUTO | 미제공 | 같은 자동 span | 전체 MCQ + span 목록 | referent만 | E0/E1; ST0→필요시 ST1; V0 |',
        '| TS_SEL_GUI_ORACLE | 같은 신규 inventory | source annotation | 전체 MCQ + span 목록 + inventory | referent만·진단 전용 | I0/I1; SG0/SG1; V0 |',
        '| TS_SEL_TXT_ORACLE | 미제공 | 같은 source annotation | 전체 MCQ + span 목록 | referent만·진단 전용 | ST0/ST1; V0 |',
        '| O | 미사용 | 미사용 | 원본 MCQ + screenshot | 변환 없음 | V0 |','',
        '자동/Oracle은 SG 또는 ST prompt가 같다. 바뀌는 것은 source span 목록뿐이다. Oracle임을 모델에 알려주지 않는다. Full 조건에는 referent extraction을 사용하지 않는다. GUI selective는 독립 번역 후 필터링하지 않고 inventory에서 대응 표현을 직접 선택하거나 null을 반환한다. GUI inventory에 없는 자유 번역은 GUI selective에서 허용하지 않는다. Full GUI는 과거처럼 애매한 표현의 일반 번역을 허용한다. 두 정책 차이를 숨기지 않는다.','',
        'Inventory는 screenshot만 보고 생성하며 query나 options가 없다. 문자열 정규화·dedup·lexical sort를 공유하고 실패 후에도 빈 evidence와 실패 로그를 보존한다. 모든 GUI 조건이 같은 inventory를 사용한다. 자동 추출은 source MCQ별로 한 번 생성해 GUI/TXT에서 공유한다. 이전 v1 inventory·번역 cache는 가져오지 않는다.','',
        '## 4. 실행 범위와 순서','',
        '| Cohort | 실행 pair | Primary main | 이미지 | 7개 조건(O 포함) 예측 행 |','| --- | ---: | ---: | ---: | ---: |',
        '| Screen | 288 | 240 | 128 | 2,016 |','| Selection | 240 | 239 | 80 | 1,680 |','| Internal | 1,416 | 1,416 | 472 | 9,912 |','| 전체 | 1,944 | 1,895 | 680 | 13,608 |','',
        '기존 split·pair ID·이미지·보기 순서를 그대로 사용한다. Pilot 48쌍과 사전 제외 `rel::5/forest_9.jpg::zh::ru`는 실행에 남기고 primary에서 분리한다. Screen→Selection→Internal 순서이며 이번에는 성능 순위로 GUI 조건을 자동 탈락시키지 않는다. 모두 관찰된 development 데이터다.','',
        '단계는 inventory(VLM) → 자동 추출(LM) → 여섯 조건 변환(LM) → O 및 여섯 조건 문제 풀이(VLM)다. 각 단계는 별도 자식 프로세스여서 두 모델을 동시에 적재하지 않는다. Text-only subset은 inventory를 만들지 않고, Oracle-only subset은 자동 추출 단계를 생략한다.','',
        '## 5. 전체 inference config','',
        '아래는 실행기가 읽는 [two_stage_v2.json](../configs/two_stage_v2.json) 원문이다. 모델 경로 placeholder는 개인 HF cache의 pinned snapshot으로만 해석하며 다운로드하지 않는다.','', '```json',json.dumps(config,ensure_ascii=False,indent=2),'```','',
        '| 단계 | Batch | Max input | Max new tokens | Decoding |','| --- | ---: | ---: | ---: | --- |']
    for key,limit in config['output_tokens'].items():lines.append(f'| {key} | 1 | 4,096 | {limit} | greedy, beams1, BF16, SDPA |')
    lines+=['| 문제 풀이 V0·모든 조건 | 3 | 4,096 | 2 | greedy, beams1, BF16, SDPA |','',
        '준비 환경의 package versions:','','```json',json.dumps(software_versions(),ensure_ascii=False,indent=2),'```','',
        '공통 seed42, `eval()`·`torch.inference_mode()`·`use_cache=true`·`logits_to_keep=1`. Method는 직접 지정한 generation 외 temperature/top_p를 새로 설정하지 않으며 greedy에서는 샘플링하지 않는다. Text LM은 `enable_thinking=false`. 이미지 processor는 fast=true, 262144≤pixels≤2097152, Qwen3-VL patch 입력 최대8192다. FlashAttention이나 raw backbone 수술은 사용하지 않는다. CUDA가 비결정적일 수 있으므로 seed만으로 bitwise 일치를 주장하지 않는다.','',
        '문제 풀이는 조건별로 나누고 pair_id 정렬 후 batch3으로 처리한다. 서로 다른 조건을 한 batch에 섞지 않는다. O는 cohort별로 새로 한 번 평가하여 모든 조건이 공유한다. 기존 O/R/T/F 예측은 변환 입력에 사용하지 않는다. `score_labels=true`를 유지하되 primary outcome은 생성 답의 정오다.','',
        '## 6. 실패 처리','',
        '- Inventory: 초기768 token → parser 오류면 기존 compact repair system/user로 1회3072 token. Repair도 cap에서 끝났을 때만 과거의 반복 prefix 복구 규칙을 적용한다. 최종 실패는 빈 inventory와 함께 포함한다. 예전 search의 임의80개 상한 대신 과거 parser의500개 검증 한도를 복원했다.',
        '- Full: 구조 실패에 1회 repair. 구조가 유효하면 과거 semantic 진단 이유가 있을 때만 1회 repair하고, hard error 없이 semantic score가 엄격히 개선될 때만 채택한다. 두 Full 조건의 숫자/파일 토큰 차이는 과거 GUI lexical validator처럼 진단으로 남긴다. Text-only도 같은 validator를 써서 검증 정책을 통일했으며, 과거 contextual의 hard numeric 검사 전체를 재현한다고 주장하지 않는다. 자동 점검 통과가 의미 동등성을 보장하지는 않는다.',
        '- Selective: 전체 MCQ를 문맥으로 받지만 출력은 고정 ID별 문자열/null뿐이다. GUI 문자열 membership·원문 span·option 순서를 코드로 검증하고 span 밖의 원문은 그대로 유지한다. 새 보기 중복도 거절한다. 구조/편집 오류에 1회 repair 후 실패하면 전체 원문으로 fallback한다. Selective용 의미 repair는 새로 추가하지 않았다.',
        '- Automatic extraction: 기존 fixed-contrastive prompt를 유지하고 원문 substring/occurrence 검증 오류에는 명시적 구조 repair를 1회 추가했다. 이것은 과거 two-stage에는 없던 adaptation이다. 실패는 원문 유지로 포함한다.',
        '- OOM·모델 적재·입력/vision budget 초과는 실험을 중단한다. 임의로 batch·해상도·분모를 줄이지 않는다. 재개하면 완료 단계는 재사용하고, 미완료 단계는 새 attempt에서 수행하며 같은 v2 호출 cache만 재사용한다.','',
        '## 7. 모든 system/user prompt 원문','',
        '아래 user message의 MCQ와 inventory는 **가상 en→zh 예시**다. 실제 호출은 같은 함수에 각 pair의 원본 MCQ·새 inventory·source spans를 넣는다. `<PREVIOUS_RAW_OUTPUT>`·`<VALIDATION_ERROR>`·`<SEMANTIC_REPAIR_REASON>`은 해당 실패의 실제 값이다. FT2의 source relation categories도 실제 source stem에서 계산한다. Inventory user message 앞에는 실제 screenshot image block이 붙는다.','']
    printed={}
    for name,(stage,system,user) in items.items():
        lines+=['### '+name+' — '+stage,'',f"출력 한도: {config['output_tokens'][stage]} tokens. System SHA-256: `{digest(system)}`.",'']
        if system in printed:lines+=['System은 **'+printed[system]+'과 동일**하다.','']
        else:
            printed[system]=name;lines+=['System:','','```text',system,'```','']
        lines+=['User:','','```text',user,'```','']
    downstream=config['downstream'];model=downstream['model_config']
    lines+=['### V0 — 문제 풀이·모든 조건 공통','', 'System:','','```text',downstream['system_prompt'],'```','',
        'User의 image block 뒤 text:','','```text',build_prompt_text(render(fields(row)),model['prompt_profile']),'```','',
        '여기서 MCQ는 각 조건의 최종 stem·A–D이며 이미지·gold·A–D 순서는 동일하다. System message를 조건마다 바꾸지 않는다.','',
        '## 8. Selective GUI와 과거 full prompt의 변경점','',
        '다음 diff는 단순히 기존 full 번역 지시 뒤에 선택적 지시를 덧붙여 충돌시키지 않았음을 확인하기 위한 것이다. SG는 과거와 동일한 prompt가 아니라 versioned adaptation이다.','',
        '```diff',*list(difflib.unified_diff(legacy.LEXICAL_SYSTEM_PROMPT.splitlines(),prompts.SELECTIVE_GUI_SYSTEM.splitlines(),fromfile='legacy_full_gui',tofile='selective_gui_v2',lineterm='')),'```','',
        'ST는 과거 text-only contextual 규칙의 “ordinary label 번역·전체 MCQ로 disambiguation·공간 관계/숫자 보존·문제 풀이 금지”를 선택적 ID 출력에 맞춰 새로 작성했다. E0는 기존 fixed-contrastive extractor이며 inventory 모델 프롬프트와 혼동하지 않는다.','',
        '## 9. 실행과 검증','',
        'CPU 준비만 수행(기본값):','','```bash','bash followup_rel_4lang/method_dev/scripts/run_two_stage_v2.sh','```','',
        'Screen에서 모든 새 조건 실행:','','```bash','bash followup_rel_4lang/method_dev/scripts/run_two_stage_v2.sh --stage all --cohort screen','```','',
        '전체 cohort 순차 실행:','','```bash','nohup bash followup_rel_4lang/method_dev/scripts/run_two_stage_v2.sh --stage all > followup_rel_4lang/method_dev/artifacts/two_stage_v2.log 2>&1 < /dev/null &','```','',
        '작은 CPU mock(실측 결과 아님):','','```bash','bash followup_rel_4lang/method_dev/scripts/run_two_stage_v2.sh --stage all --mock --cohort screen --limit-items 1','```','',
        '로그는 첫 항목 및 inventory10개·추출/변환20개·문제풀이약60개마다 진행 수를 출력한다. 각 cohort의 `COMPLETE.json`, 단계별 `calls.json`, `cost.json`, 조건별 rewritten JSONL과 `predictions.jsonl`을 남긴다. Mock은 accuracy를 출력하지 않는다. Source/config hash가 달라지면 기존 run 재개를 거절하므로 변경 시 새 `--output-dir`를 쓴다.','',
        '메모리 profile은 현재45GB B200 MIG이며 적재 전 free40GiB를 요구한다. 수식상 single inventory KV는 (4096+3072)token에서 약0.98GiB, BF16 VLM 가중치는 약16.33GiB다. Method batch1·평가batch3이며 activation/workspace를 포함한 OOM 보장은 아니다. 24GB4090용 profile로 간주하지 않는다.','',
        '준비/검증 실측 상태는 [two_stage_v2_readiness.json](../artifacts/two_stage_v2_readiness.json)에 기록한다. 이 문서만으로 새 성능이 측정됐다고 해석하지 않는다. 보고서 재생성: `.venv/bin/python followup_rel_4lang/method_dev/scripts/report_two_stage_v2.py`.']
    readiness=ROOT/'artifacts/two_stage_v2_readiness.json'
    if readiness.exists():
        data=json.loads(readiness.read_text())
        status=['## 실제 준비 검증과 NO-GO 항목','',
            '코드·CPU mock 준비는 완료했지만 **전체 실험 GO는 아니다.** 단일 캘린더 GPU smoke에서 inventory와 full GUI 변환은 구조상 성공했고, 자동 추출은 occurrence 오류로 1회 repair 후에도 실패했다. 관계 문구를 referent로 과다 추출한 문제도 보였다. Oracle selective는 모든 출력 ID와 inventory membership를 통과했으나 Tuesday를 `11 周三`로 연결해 의미상 잘못된 대응이 관찰됐다.','',
            '이 smoke는 `rel::2/calendar_6.png::en::zh` 1쌍만 관찰한 개발 기록이다. 정확도 평가는 하지 않았고 bbox·gold target도 사용하지 않았다. 이 결과로 전체 데이터 오류율을 추정하지 않는다. 전체 GPU 재실행은 시작하지 않았으며, 자동 추출과 선택적 정렬의 의미 보존은 다음 검토 항목이다.','',
            '```json',json.dumps(data,ensure_ascii=False,indent=2),'```','']
        lines[4:4]=status
    report=ROOT/'reports/TWO_STAGE_V2_PROTOCOL_KO.md';report.write_text('\n'.join('' if line==' ' else line for line in lines)+'\n')
    return report


if __name__=='__main__':print(main())
