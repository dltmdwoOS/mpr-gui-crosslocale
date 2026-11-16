"""Audit inventory inputs in historical/current prompts; no model inference."""
import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO=Path(__file__).resolve().parents[3]
ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(REPO/'01_code/src'),str(Path(__file__).parent)]
from mpr_crosslocale.methods.selective_alignment.schemas import digest

COMMIT='cdea4d1437f383f99f6b8dc63ecff38c364eb4d0'
OLD_PATH='01_code/src/mpr_crosslocale/interventions/rq4_gui_lexical.py'
COHORTS=['screen','selection','internal_evaluation']
STAGES={'GUI_EXACT':'translate','TXT_SEL':'translate','GUI_FULL':'GUI_FULL','TXT_FULL':'TXT_FULL','GUI_MATCH_LM':'match_text',
        'GUI_TARGETED_VLM':'ground_match','GUI_DIRECT_VLM':'direct_visual_edit','TXT_DIRECT_LM':'direct_text_edit','TXT_DIRECT_VLM':'vl_text_edit'}


def user_payload(call):
    text=call['rendered_prompt'].split('<|im_start|>user\n',1)[1]
    return json.JSONDecoder().raw_decode(text[text.index('{'):])[0]


def collect():
    inputs={}
    def use(path):
        inputs[str(path.relative_to(REPO))]=hashlib.sha256(path.read_bytes()).hexdigest()
        return path
    use(Path(__file__).resolve())
    source=subprocess.check_output(['git','show',COMMIT+':'+OLD_PATH],cwd=REPO,text=True)
    constants={}
    for node in ast.parse(source).body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('LEXICAL_SYSTEM_PROMPT','INVENTORY_SYSTEM_PROMPT') for t in node.targets):
            constants[node.targets[0].id]=ast.literal_eval(node.value)
    preserved=json.loads(use(ROOT/'configs/legacy_prompts.json').read_text())
    if preserved['source_commit']!=COMMIT or preserved['prompts']!=constants:raise ValueError('Legacy prompt provenance mismatch')
    snapshot=json.loads(use(ROOT/'artifacts/oracle_exact_results_snapshot.json').read_text())
    # Audit all files which the Oracle analysis locked, not a stale metric summary.
    for filename,sha in snapshot['sources_sha256'].items():
        if hashlib.sha256(use(REPO/filename).read_bytes()).hexdigest()!=sha:raise ValueError('Stale Oracle snapshot: '+filename)
    base=ROOT/'artifacts/search_pipeline_v1';methods={}
    for method,stage in STAGES.items():
        entry={'cohorts':{}}
        for cohort in COHORTS:
            table=base/'tables'/cohort/(method+'.json')
            if not table.exists():continue
            summary=json.loads(use(table).read_text());trial=base/summary['trial']
            if not (trial/'COMPLETE').exists():raise ValueError('Incomplete method')
            calls=[c for c in json.loads(use(trial/'calls.json').read_text()) if c['stage']==stage]
            if not calls or any(c['execution_mode']!='gpu' for c in calls):raise ValueError('Missing real method calls')
            payloads=[user_payload(c) for c in calls]
            system_prompts=[c['rendered_prompt'].split('<|im_start|>system\n',1)[1].split('<|im_end|>',1)[0] for c in calls]
            inv=['untrusted_unordered_visible_strings' in p for p in payloads]
            full=['fields' in p for p in payloads]
            expect_inventory=method in ('GUI_FULL','GUI_MATCH_LM')
            if not all(flag==expect_inventory for flag in inv):raise ValueError('Unexpected inventory exposure')
            entry['cohorts'][cohort]={'calls':len(calls),'with_inventory':sum(inv),'with_full_mcq':sum(full),
                'with_referent_list':sum('referents' in p for p in payloads),'legacy_system_prompt_exact_calls':sum(p==constants['LEXICAL_SYSTEM_PROMPT'] for p in system_prompts),
                'system_prompt_sha256':sorted({digest(p) for p in system_prompts}),'model_ids':sorted({c['model_id'] for c in calls})}
            entry.setdefault('system_prompt',system_prompts[0])
        methods[method]=entry
    oracle={}
    for cohort in COHORTS:
        run=ROOT/'artifacts/oracle_span_exact_v1'/cohort
        complete=json.loads(use(run/'COMPLETE.json').read_text())
        calls=json.loads(use(Path(complete['trial'])/'calls.json').read_text())
        payloads=[user_payload(c) for c in calls]
        if any('untrusted_unordered_visible_strings' in p or 'fields' in p for p in payloads):raise ValueError('Oracle contract differs')
        oracle[cohort]={'calls':len(calls),'with_inventory':0,'with_full_mcq':0,'with_referent_list':sum('referents' in p for p in payloads)}
    search=json.loads(use(ROOT/'artifacts/search_report_snapshot.json').read_text())
    return dict(old_commit=COMMIT,old_source_path=OLD_PATH,old_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        legacy_system_prompt=constants['LEXICAL_SYSTEM_PROMPT'],methods=methods,oracle_calls=oracle,
        scores={c:{name:r['groups']['main'] for name,r in search['records'][c].items() if name in ('GUI_FULL','GUI_MATCH_LM','GUI_EXACT')} for c in COHORTS},
        coverage={c:snapshot['cohorts'][c]['oracle_matching_coverage'] for c in COHORTS},internal_by_gui=snapshot['cohorts']['internal_evaluation']['oracle_matching_by_gui'],
        sources_sha256=inputs)


def markdown(s):
    out=['# Inventory 사용 방식 점검과 Oracle exact-match coverage','',
        '**과거 two-stage는 inventory를 번역 입력에 명시하고 화면 표현을 활용하도록 지시했다. 최근 GUI_FULL은 inventory를 제공했지만 과거 프롬프트를 그대로 재현하지 않았다. 현재 Oracle은 inventory를 번역기에 제공하지 않았다.**','',
        '## 1. 과거 two-stage에서 실제로 한 일','',
        f"로컬 remote-tracking branch `origin/paper-freeze-20260814`의 보존 커밋 `{s['old_commit']}`를 읽기 전용으로 확인했다. `rq4_gui_lexical.py`의 `lexical_payload()`는 source/target 언어, **target_gui_visible_strings, 원본 question_stem, A–D options**를 번역기에 함께 넣는다. Inventory는 query-blind 추출 후 정규화·중복 제거·정렬한다. 번역기는 screenshot이나 layout 자체를 보지 않는다.",'',
        '당시 system prompt의 핵심 부분:','',
        '```text','Translate the complete MCQ from the declared source language to the declared target language.',
        'Use an inventory string only when it clearly corresponds to a GUI label, menu item, tab, title, or other interface reference in the source MCQ.',
        'Copy such target-locale wording exactly when appropriate.',
        'If correspondence is uncertain, translate normally rather than forcing a match.','```','',
        '전체 query와 options를 번역하면서 대응 label에는 화면 어휘를 사용하고, 애매하면 일반 번역을 허용하는 방식이었다. 코드가 번역문과 inventory의 exact match만 골라 원문에 적용하는 방식은 아니었다. 방향·부정·숫자·브랜드 보존을 상세히 지시했고 구조 및 의미 검증 후 repair 경로도 있었다. 전체 원문 prompt는 [legacy_prompts.json](../configs/legacy_prompts.json)의 `LEXICAL_SYSTEM_PROMPT`에서 볼 수 있다.','',
        '과거 추출 모델은 Qwen2.5-VL-7B, 번역기는 Qwen3-8B였다. 이번에는 inventory 추출이 평가 모델인 Qwen3-VL-8B이며 번역기는 같은 pinned Qwen3-8B다. 과거 inventory에는 출력 초과 후 최대 3,072-token repair 경로가 있었지만 최근 search inventory는 768-token 첫 출력 실패를 유지했다. 이 차이들도 있어 과거 방법의 성능을 이번 결과로 그대로 대체할 수 없다.','',
        '## 2. 최근 실험 중 inventory를 입력으로 준 조건','',
        '아래는 `search_pipeline_v1`의 완료된 GPU 호출에서 실제 `rendered_prompt`의 user JSON을 전수 확인한 결과다. 한 셀의 숫자는 번역/매칭 호출 수이며 accuracy 분모와 다르다.','',
        '| 조건 | 번역/매칭 모델이 inventory를 받았나 | 전체 원본 MCQ 문맥 | Screen / Selection / Internal 호출 수 |','| --- | --- | --- | ---: |']
    for method,entry in s['methods'].items():
        inv='예' if method in ('GUI_FULL','GUI_MATCH_LM') else '아니오'
        context='예' if method in ('GUI_FULL','TXT_FULL','GUI_DIRECT_VLM','TXT_DIRECT_LM','TXT_DIRECT_VLM') else '아니오·referent 목록만'
        counts=' / '.join(str(entry['cohorts'][c]['calls']) if c in entry['cohorts'] else '미실행' for c in COHORTS)
        out.append(f'| {method} | {inv} | {context} | {counts} |')
    out+=['','GUI_TARGETED_VLM과 GUI_DIRECT_VLM은 screenshot을 직접 받았지만, inventory 문자열 목록은 받지 않았다. Oracle의 세 cohort 역시 referent 목록만 받고 inventory와 전체 MCQ는 받지 않았음을 실제 호출 기록에서 확인했다.','',
        '### GUI_FULL: 원래 two-stage에 가장 가까운 전체 번역 조건','',
        '전체 stem·A–D와 `untrusted_unordered_visible_strings`를 함께 주었다. 다만 실제 system prompt는 아래의 짧은 새 지시다.','',
        '```text',s['methods']['GUI_FULL']['system_prompt'],'```','',
        '과거처럼 “대응하는 inventory 표현을 그대로 복사하라”는 구체적 지시는 빠져 있다. Inventory를 전달한 실험은 맞지만, **원래 prompt·출력 schema·repair 정책을 복원한 재현 실험은 아니다.** 이 차이가 결과의 원인인지 자체는 아직 비교하지 않았다.','',
        '### GUI_MATCH_LM: inventory에서 referent의 대응 표현을 선택','',
        '고정 Qwen3-8B에 자동 추출한 referent 목록과 inventory를 함께 주고 각 span ID에 문자열 또는 null을 반환하게 했다. 이는 inventory-conditioned selective matching이다. 다만 전체 MCQ 문맥과 Oracle source span을 사용하지 않았고 Screen만 수행했다. Inventory 밖의 생성 문자열이나 ID 오류가 있으면 전체 응답을 거절하는 strict validation의 영향도 포함한다.','',
        '| 조건 | Screen main | Selection | Internal |','| --- | ---: | ---: | ---: |']
    for method in ['GUI_FULL','GUI_MATCH_LM']:
        values=[]
        for c in COHORTS:
            g=s['scores'][c].get(method)
            values.append(f"{g['correct']}/{g['n']} ({g['correct']/g['n']*100:.2f}%)" if g else '미실행')
        out.append('| '+method+' | '+' | '.join(values)+' |')
    out+=['','## 3. 현재 Oracle과의 차이','',
        '| 항목 | 과거 two-stage | 최근 GUI_FULL | 최근 GUI_MATCH_LM | 현재 Oracle GUI_EXACT |','| --- | --- | --- | --- | --- |',
        '| Source referent span | 명시 추출 없음 | 명시 추출 없음 | 자동 추출 | Annotation |',
        '| 번역/매칭 입력에 inventory | 있음 | 있음 | 있음 | **없음** |',
        '| 전체 MCQ 문맥 | 있음 | 있음 | 없음 | 없음 |',
        '| 변환 범위 | 전체 MCQ | 전체 MCQ | 추출 referent만 | Annotation referent만 |',
        '| 출력 적용 | 전체 번역 결과 | 전체 번역 결과 | inventory member 또는 null | 독립 번역 후 코드 exact match |',
        '| Context 언어 | GUI 언어 | GUI 언어 | Source 유지 | Source 유지 |','',
        '**아직 수행하지 않은 조합은 “Oracle source span + inventory를 명시한 referent 번역/선택”이다.** 지금 Oracle 결과는 이 조합의 성능을 말해 주지 않는다. GUI_FULL과 Oracle의 차이는 inventory 제공 외에도 전체 번역/선택적 편집, 문맥 제공, source span 정보, 검증 정책을 함께 포함한다. 두 조건의 정확도 차이를 inventory 제공 하나의 효과로 해석할 수 없다.','',
        '현재 Oracle은 추출 오류를 제거한 뒤에도 **inventory를 보지 않는 번역 + exact 필터**로 충분한지를 진단했다. 원래 원한 inventory-conditioned localization을 유지한 Oracle 실험과는 구별해야 한다. GUI_MATCH_LM의 낮은 Screen 성능만으로 Oracle+inventory 조건을 기각할 수도 없다.','',
        '## 4. Oracle의 exact-match 비율','',
        '“한 문제”는 semantic item 하나가 아니라 **문항×source/GUI 언어쌍**이다. 분모는 각 문항의 annotation referents 전체이며 stem과 A–D를 합친다. Referent가 없는 field를 억지로 하나로 세지 않는다.','',
        '| Primary 집합 | Pair N | 참조별 확인된 match | 문항별 match 비율 평균 | 최소 1개 match | 모든 referent match |','| --- | ---: | ---: | ---: | ---: | ---: |']
    pooled={key:sum(s['coverage'][c].get(key,0) for c in COHORTS) for key in ['pairs','referents','matched','any','all','partial','none','unknown_pairs','unknown_referents']}
    for cohort,c in s['coverage'].items():
        out.append(f"| {cohort} | {c['pairs']} | {c['matched']:,}/{c['referents']:,} ({c['micro_confirmed_ratio']*100:.2f}%) | {c['macro_confirmed_ratio']*100:.2f}% | {c['any']}/{c['pairs']} ({c['any']/c['pairs']*100:.2f}%) | {c['all']}/{c['pairs']} ({c['all']/c['pairs']*100:.2f}%) |")
    macro=sum(c['macro_confirmed_ratio']*c['pairs'] for c in s['coverage'].values())/pooled['pairs']
    out.append(f"| main 전체·기술 통계 | {pooled['pairs']} | {pooled['matched']:,}/{pooled['referents']:,} ({pooled['matched']/pooled['referents']*100:.2f}%) | {macro*100:.2f}% | {pooled['any']}/{pooled['pairs']} ({pooled['any']/pooled['pairs']*100:.2f}%) | {pooled['all']}/{pooled['pairs']} ({pooled['all']/pooled['pairs']*100:.2f}%) |")
    c=s['coverage']['internal_evaluation']
    out+=['',f"Internal의 평균 annotation referent는 문항당 **{c['mean_referents_per_pair']:.2f}개**, 평균 match는 **{c['mean_matched_per_pair']:.2f}개**다. 참조를 하나씩 합친 비율(micro)은 30.65%, 각 문항의 k/n을 동일 가중 평균한 비율(macro)은 30.25%다. 둘은 분모 가중치가 다르다.",'',
        '| Internal 문항 상태 | Pair 수 | 비율 |','| --- | ---: | ---: |']
    for label,key in [('전부 match','all'),('일부만 match','partial'),('하나도 match하지 않음','none')]:out.append(f"| {label} | {c[key]} | {c[key]/c['pairs']*100:.2f}% |")
    out+=['',f"최종 MCQ가 실제 바뀐 948쌍과 최소 1개 match한 {c['any']}쌍도 다르다. 이미 source와 같은 숫자·이름은 match해도 edit하지 않으며, 보기 중복으로 전체 편집이 거절된 경우도 있다. 모든 참조가 match했다고 R_REF 질문과 같아졌거나 실제 화면 대응이 모두 정확하다고 보장되는 것은 아니다.",'',
        '### Internal GUI 언어별','',
        '| GUI | Pair N | 참조별 match | 모든 referent match |','| --- | ---: | ---: | ---: |']
    for gui in ['en','zh','th','ru']:
        g=s['internal_by_gui'][gui];out.append(f"| {gui.upper()} | {g['pairs']} | {g['matched']}/{g['referents']} ({g['micro_confirmed_ratio']*100:.2f}%) | {g['all']}/{g['pairs']} ({g['all']/g['pairs']*100:.2f}%) |")
    out+=['','### 로그 분모와 실패 처리','',
        '기존 보고서의 1,966/6,415는 **저장된 중간 match 로그** 기준이다. 이번에는 저장된 번역 JSON과 같은 matcher를 CPU로 다시 계산해, 보기 중복 fallback 1쌍의 누락된 5개 판단을 복원했다. 이 중 2개가 match해서 **전체 matching 단계는 1,968/6,420**이다. 반올림한 비율은 둘 다 30.65%다. GPU 추론을 다시 수행하지 않았다.','',
        'Screen은 번역 JSON 실패 2쌍·7개 referent가 있어 matching 판정 불가로 분리했다. 전체 분모에는 유지하고 확인된 match 분자에는 넣지 않았다. 이것을 실제 no-match라고 단정하지 않는다. Primary 합계는 main 1,895쌍이며 pilot 48쌍과 사전 제외 1쌍은 포함하지 않았다.','',
        '## 5. 이번 수치가 말해 주는 범위','',
        'Oracle에서도 대부분의 문항은 일부 표현만 바뀌었다. 그러나 이 낮은 coverage를 inventory-conditioned 번역의 한계라고 부를 수는 없다. 현재 번역기는 inventory를 보지 않았기 때문이다. 번역의 동의어 선택, inventory 누락, source 표현의 비직접 대응 등은 아직 원인별로 나뉘지 않았다. 다음 비교는 같은 Oracle span과 LM·decoding을 고정하고 inventory를 번역/선택 입력에 명시하는 조건이다. 원래 긴 prompt의 재현과 짧은 새 prompt의 비교도 별도 변경으로 기록해야 한다.','',
        '재현 명령(추론 없음):','', '```bash','.venv/bin/python followup_rel_4lang/method_dev/scripts/analyze_oracle_exact.py','.venv/bin/python followup_rel_4lang/method_dev/scripts/audit_inventory_usage.py','```','',
        '[실제 호출 audit snapshot](../artifacts/inventory_usage_audit.json) · [Oracle 결과 보고서](ORACLE_RESULTS_KO.md).']
    return '\n'.join(out)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.parse_args()
    snapshot=collect()
    (ROOT/'artifacts/inventory_usage_audit.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n')
    report=ROOT/'reports/INVENTORY_USAGE_AND_EXACT_MATCH_KO.md';report.write_text(markdown(snapshot))
    print(report)


if __name__=='__main__':main()
