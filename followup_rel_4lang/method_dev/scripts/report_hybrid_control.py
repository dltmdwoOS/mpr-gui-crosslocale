"""Document the query-selective/options-full control from executable prompt definitions."""
import json
import sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(REPO),str(REPO/'01_code/src'),str(Path(__file__).parent)]
from followup_rel_4lang.method_dev.two_stage_v2 import prompts
from report_two_stage_v2 import catalog
from mpr_crosslocale.methods.selective_alignment.schemas import digest


def main():
    config=json.loads((ROOT/'configs/two_stage_v2_hybrid.json').read_text())
    common,row=catalog();inv={'visible_strings':['帮助','主页','设置','退出','隐私']}
    start=row['question_stem'].index('Settings');refs=[{'field':'question_stem','text':'Settings','span_id':f'question_stem:{start}:{start+8}'}]
    previous='<PREVIOUS_RAW_OUTPUT>';errors=['<VALIDATION_ERROR>']
    additional={
        'EQ0':('extract_stem',prompts.EXTRACT_STEM_SYSTEM,prompts.extraction_user(row,stem_only=True)),
        'EQ1':('extract_stem_repair',prompts.EXTRACT_STEM_SYSTEM,prompts.extraction_user(row,previous,errors,stem_only=True)),
        'QG0':('selective',prompts.SELECTIVE_GUI_SYSTEM,prompts.selective_user(row,refs,inv)),
        'QG1':('selective_repair',prompts.SELECTIVE_GUI_SYSTEM,prompts.selective_user(row,refs,inv,previous,errors)),
        'QT0':('selective',prompts.SELECTIVE_TXT_SYSTEM,prompts.selective_user(row,refs)),
        'QT1':('selective_repair',prompts.SELECTIVE_TXT_SYSTEM,prompts.selective_user(row,refs,None,previous,errors)),
    }
    lines=['# 추가 control: Query referent 선택적 정렬 + Options 전체 localization','',
        '**최종 stem에서는 참조 표현만 바꾸고, A–D는 전체 번역한다.** 자동 추출 오류가 options에서 생겨 query 처리까지 실패하는 경로를 분리해 보는 control이다. GUI inventory 사용/미사용 두 버전을 짝으로 추가했다. 실제 성능이나 오류 감소량은 아직 측정하지 않았다.','',
        '| 새 조건 | Stem 추출 | Stem 정렬 | Options |','| --- | --- | --- | --- |',
        '| TS_QSEL_OFULL_GUI_AUTO | stem만 입력 | 전체 원본 MCQ + stem refs + inventory | TS_FULL_GUI의 A–D와 동일 |',
        '| TS_QSEL_OFULL_TXT_AUTO | 같은 stem-only 추출 | 전체 원본 MCQ + stem refs | TS_FULL_TXT의 A–D와 동일 |','',
        'QSEL은 query 선택적 변환, OFULL은 options 전체 변환을 뜻한다. 원본 조건 O와 혼동하지 않는다. Query는 `question_stem`이며 보기 설명·관계·색상·요소 종류 등의 option 문맥도 GUI 언어로 번역된다.','',
        '## 구현에서 고정한 부분','',
        '1. Query extractor에는 source language와 `fields.question_stem`만 넣는다. A–D를 함께 추출한 뒤 필터링하는 방식이 아니다. 모델이 option field를 반환하면 scope 오류로 검증하고 1회 repair한다. Stem-only prompt는 최소 경계 지시를 기반으로 만들었으며 occurrence가 동일 substring의 반복 번호임을 명시했다.',
        '2. Stem 정렬은 기존 selective system prompt와 출력 검증을 사용한다. 원래 전체 MCQ는 disambiguation 문맥으로 주되, 전달하는 span ID는 query의 것뿐이다. Stem의 span 밖 문자열은 코드가 보존한다.',
        '3. Options에는 새 추출기나 별도 번역 prompt를 만들지 않는다. 기존 Full recipe를 같은 원본 MCQ·inventory로 실행해 **A–D만 채택하고 생성된 stem은 버린다.** 내부 LM 호출은 전체 MCQ 번역이라는 점을 명시한다. 같은 Full 조건이 먼저 실행됐으면 초기·repair·의미 repair 호출의 cache가 재사용되므로 추가 Full generation이 없다. 검증도 같은 Full recipe이므로 실패 원인에 버릴 stem의 검증 문제가 포함될 수 있어 options 자체의 오류와 동일시하지 않는다.',
        '4. Stem 정렬과 Full 번역은 모두 원래 MCQ를 본다. 한쪽이 번역한 결과를 다른 쪽의 문맥으로 다시 주지 않는다.',
        '5. Stem 실패는 원래 stem 유지, Full 실패는 원래 options 유지로 처리한다. 한쪽 실패 때문에 다른 쪽의 성공한 변환까지 버리지 않는다. `partial_fallback`과 컴포넌트별 원인을 저장하며 전체 pair를 평가에 유지한다.','',
        '## 비교와 분모','',
        '기본 실행에는 기존 6조건 + 새 control 2조건 + O, 총 9조건이 들어간다. Screen 288쌍(주 분석240), Selection 240쌍(239), Internal 1,416쌍(1,416)을 유지한다. 전체 실행 1,944쌍·예측17,496행이며 primary는1,895쌍이다. 기존 inventory·번역 결과는 가져오지 않는다.','',
        '- Hybrid vs 같은 GUI/TXT Full: options가 같은 상태에서 stem을 전체 번역할지 선택적으로 바꿀지 비교한다.',
        '- Hybrid vs 같은 GUI/TXT Selective AUTO: options 전체 번역과 stem-only 추출을 합친 pipeline 수준의 비교다. 추출 prompt/scope 및 option context 언어도 달라지므로 occurrence 오류 하나만의 순수 인과 효과라고 단정하지 않는다.',
        '- Accuracy·오답→정답/정답→오답·semantic-item bootstrap95% CI를 paired 계산한다. 자동 추출 실패와 언어 혼합이 줄어도 의미 번역 오류가 남을 수 있다. 기존 v2 단일 smoke의 NO-GO 관찰은 이 변경으로 해소됐다고 주장하지 않는다.','',
        '실제 GPU 실행 후 `results.json.hybrid_controls`에는 다음을 기록한다.','',
        '- Query 추출 실패 / Query 정렬 실패 / Options용 Full pipeline 실패 수.',
        '- 기존 전체 필드 추출 실패 수와 새 stem-only 추출 실패 수.',
        '- 전체 필드에서는 실패했지만 stem-only에서는 성공한 pair, 반대 전환.',
        '- 기존 추출 실패가 검증상 A–D에만 있었던 pair와 field별 실패 빈도. JSON schema 오류는 별도 schema로 남긴다. Field별 실패는 중복 집계될 수 있어 빈도의 합이 실패 pair 수를 넘을 수 있다. 이 진단은 의미 오역 검수가 아니다.',
        '- Query와 options 실제 변경 수, Full/Selective 대비 paired accuracy 차이와 회복·회귀.','',
        '## 전체 config','', '```json',json.dumps(config,ensure_ascii=False,indent=2),'```','',
        '기존의 fixed Qwen3-8B / inventory·평가 Qwen3-VL-8B revision과 BF16·SDPA를 유지한다. Method batch1, 평가batch3, 입력한도4096. 추가 stem extraction/repair는 각768 token이며 정렬/repair512, Full 초기/구조/의미 repair512다. Inventory 초기768·repair3072는 그대로다. 관련 공통 system/user 원문·평가 V0는 [기존 전체 프로토콜](TWO_STAGE_V2_PROTOCOL_KO.md)에 있다.','',
        '## 새 control에 실제 연결되는 모든 prompt','',
        '아래는 코드가 생성한 가상 en→zh 예시다. 실제 실행에서는 source MCQ·새 inventory·stem-only 자동 spans로 채운다. GUI는 I0/I1→EQ0/EQ1→QG0/QG1 및 FG0/FG1/FG2→V0, TXT는 EQ0/EQ1→QT0/QT1 및 FT0/FT1/FT2→V0를 사용한다. Full의 stem은 최종 결과에 쓰지 않는다.','']
    items={**{key:common[key] for key in ['I0','I1']},**additional,**{key:common[key] for key in ['FG0','FG1','FG2','FT0','FT1','FT2']}}
    printed={}
    for name,(stage,system,user) in items.items():
        lines+=['### '+name+' — '+stage,'',f"Max new tokens: {config['output_tokens'][stage]}. System SHA-256: `{digest(system)}`.",'']
        if system in printed:lines+=['System: **'+printed[system]+'과 동일**.','']
        else:printed[system]=name;lines+=['System:','','```text',system,'```','']
        lines+=['User:','','```text',user,'```','']
    lines+=['## 실행과 재개','',
        '현재 runner 기본 config과 namespace는 `two_stage_v2_hybrid.json`, `artifacts/two_stage_v2_hybrid/`다. 이전 v2 output을 덮어쓰거나 그 contract를 수정하지 않는다. Mock은 `artifacts/two_stage_v2_hybrid_mock/`로 분리한다.','',
        'CPU 준비만:','','```bash','bash followup_rel_4lang/method_dev/scripts/run_two_stage_v2.sh','```','',
        'Screen에서 기존 조건과 새 control 전부:','','```bash','bash followup_rel_4lang/method_dev/scripts/run_two_stage_v2.sh --stage all --cohort screen','```','',
        '새 control 2개와 O만 실행하려면 별도 output 디렉터리로:','','```bash','bash followup_rel_4lang/method_dev/scripts/run_two_stage_v2.sh --stage all --cohort screen --conditions TS_QSEL_OFULL_GUI_AUTO TS_QSEL_OFULL_TXT_AUTO --output-dir followup_rel_4lang/method_dev/artifacts/hybrid_control_only','```','',
        '이 경우 전체 필드 extract 단계는 실행하지 않으며 새 `extract_stem` 단계만 실행한다. Options 생성용 Full recipe는 내부 호출하지만 Full/Selective baseline의 downstream 예측은 추가하지 않는다. 직접 paired 비교하려면 기본8조건을 사용한다.','',
        '전체 재실행은 명시적으로 `--stage all`을 주며, 현재 작업에서는 새 GPU 추론을 시작하지 않았다. 준비 검증: [hybrid_control_readiness.json](../artifacts/hybrid_control_readiness.json). 프롬프트/코드 변경 시 새 output 디렉터리를 사용한다.']
    path=ROOT/'reports/HYBRID_CONTROL_KO.md';path.write_text('\n'.join(lines)+'\n');print(path)


if __name__=='__main__':main()
