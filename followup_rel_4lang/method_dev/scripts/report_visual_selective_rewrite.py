"""Post-hoc analysis only. Source annotation is never imported by the method."""
import hashlib
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO/'01_code/src'),str(REPO),str(Path(__file__).parent)]
from followup_rel_4lang.method_dev import direct_selective_rewrite as method
from mpr_crosslocale.methods.selective_alignment.schemas import digest, fields, FIELDS
from mpr_crosslocale.inference.answer_parser import parse_label
from compare_end_to_end import batch_share, call_map, call_seconds
from run_stem_only_gui import read, unique, write
from reference_comparison import load_references
from search_pipeline import paired_bootstrap, EXCLUDED


def normalize_context(text):
    return ''.join(c for c in text.casefold() if unicodedata.category(c)[0] not in ('P','Z') and not c.isspace())


def protected_context_matches(source, target, spans, normalize=lambda x:x):
    """Necessary compatibility check, allowing arbitrary output inside source gold spans."""
    ranges=[]
    for span in sorted(spans,key=lambda s:(s['start'],s['end'])):
        a,b=span['start'],span['end']
        if not 0<=a<b<=len(source) or ('text' in span and source[a:b]!=span['text']):
            raise ValueError('Source annotation does not match original')
        if ranges and a<=ranges[-1][1]:ranges[-1]=(ranges[-1][0],max(ranges[-1][1],b))
        else:ranges.append((a,b))
    if not ranges:return normalize(source)==normalize(target)
    chunks=[];end=0
    for a,b in ranges:chunks.append(normalize(source[end:a]));end=b
    chunks.append(normalize(source[end:]));target=normalize(target)
    prefix,suffix=chunks[0],chunks[-1]
    if not target.startswith(prefix) or not target.endswith(suffix) or len(target)<len(prefix)+len(suffix):return False
    body=target[len(prefix):len(target)-len(suffix) if suffix else len(target)]
    cursor=0
    for fragment in chunks[1:-1]:
        start=body.find(fragment,cursor)
        if start<0:return False
        cursor=start+len(fragment)
    return True


def collect(output):
    contract=json.loads((output/'contract.json').read_text());done=json.loads((output/'COMPLETE.json').read_text())
    if done['execution_mode']!='gpu' or done['contract_sha256']!=digest(contract):raise ValueError('Completed GPU run required')
    for filename,sha in contract['source_sha256'].items():
        if hashlib.sha256(Path(filename).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen source changed')
    original=unique(read(output/'inputs.jsonl'));rows=unique(read(Path(done['rewrite'])/'rewritten.jsonl'))
    predictions=read(Path(done['infer'])/'predictions.jsonl');pred=unique(predictions)
    if set(rows)!=set(original) or set(pred)!=set(original) or digest(list(original.values()))!=contract['inputs_sha256']:raise ValueError('Incomplete paired data')
    labels=unique(read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels)!=contract['labels_sha256']:raise ValueError('Labels changed')
    ids=sorted(p for p in original if labels[p]['split']=='main' and p!=EXCLUDED)
    lookup={}
    for key in ('source_predictions','stem_predictions','single_pass_stem_predictions','single_pass_all_predictions'):
        for r in read(Path(contract[key])):
            k=(r['condition'],r['pair_id'])
            if k in lookup:raise ValueError('Duplicate baseline')
            lookup[k]=r
    def correct(r,p):
        if r['execution_mode']!='gpu' or parse_label(r['generated_text'])!=r['parsed_generated_label']:raise ValueError('Invalid prediction')
        return int(r['status']=='success' and r['parsed_generated_label']==labels[p]['gold_answer'])
    result=json.loads((output/'results.json').read_text())
    values={method.CONDITION:{p:correct(pred[p],p) for p in ids}}
    for c in result['correct']:
        if c!=method.CONDITION:values[c]={p:correct(lookup[c,p],p) for p in ids}
        if sum(values[c].values())!=result['correct'][c]:raise ValueError('Saved accuracy differs')
    source_parent=json.loads((Path(contract['source_cohort']).parent/'contract.json').read_text())
    source_annotations=read(ROOT/'artifacts/dataset_audit/oracle_spans_DIAGNOSTIC_ONLY.jsonl')
    if digest(source_annotations)!=source_parent['base_data_contract']['oracle']:raise ValueError('Source annotation lock mismatch')
    annotations=unique(source_annotations)
    audits=[]
    for p in ids:
        before,after=fields(original[p]),fields(rows[p]);spans=annotations[p]['referents']
        literal={f:protected_context_matches(before[f],after[f],[s for s in spans if s['field']==f]) for f in FIELDS}
        normalized={f:protected_context_matches(before[f],after[f],[s for s in spans if s['field']==f],normalize_context) for f in FIELDS}
        audits.append({'pair_id':p,'source_language':original[p]['source_language'],'gui_language':original[p]['gui_language'],
                       'changed':before!=after,'literal_compatible':all(literal.values()),
                       'format_compatible':all(normalized.values()),'literal_flagged_fields':[f for f in FIELDS if not literal[f]],
                       'format_flagged_fields':[f for f in FIELDS if not normalized[f]],
                       'digit_changed_fields':rows[p]['diagnostics']['digit_sequence_changed_fields'],
                       'new_duplicate_options':rows[p]['diagnostics']['new_duplicate_options'],
                       'source':before,'rewritten':after})
    captures={}
    def use(path):captures[str(path.relative_to(REPO))]=hashlib.sha256(path.read_bytes()).hexdigest();return path
    use(Path(__file__))
    use(ROOT/'artifacts/dataset_audit/oracle_spans_DIAGNOSTIC_ONLY.jsonl')
    refs,metadata,_=load_references(REPO,{p:labels[p] for p in ids},{'screen':original},use,contract['downstream']['model_config'],contract['config']['historical_baseline_contract_sha256'])
    for c in ('T_REF','R_REF','F_REF'):values[c]={p:int(refs[c][p]['status']=='success' and refs[c][p]['parsed_generated_label']==labels[p]['gold_answer']) for p in ids}
    # Historical direct edit protocol: compare only matched source pair IDs.
    old_run=ROOT/'artifacts/search_pipeline_v1/jobs/screen/pred_fixed_contrastive_GUI_DIRECT_VLM/attempt_0001'
    old_predictions=read(old_run/'predictions.jsonl')
    old={r['pair_id']:r for r in old_predictions if r['condition']=='GUI_DIRECT_VLM'}
    if not set(ids)<=set(old):raise ValueError('Old Direct pairs missing')
    values['GUI_DIRECT_VLM_OLD']={p:correct(old[p],p) for p in ids}
    use(old_run/'predictions.jsonl')
    main_calls=call_map([rows[p] for p in ids]);editor_seconds=call_seconds(main_calls)
    final=batch_share(predictions,lambda r:r['pair_id'] in ids)
    changed=[a for a in audits if a['changed']]
    context_summary={'primary_pairs':len(ids),'changed_pairs':len(changed),'literal_compatible_pairs':sum(a['literal_compatible'] for a in audits),
        'literal_compatible_changed_pairs':sum(a['literal_compatible'] for a in changed),
        'format_compatible_changed_pairs':sum(a['format_compatible'] for a in changed),
        'context_flagged_after_format_normalization':sum(not a['format_compatible'] for a in changed),
        'digit_changed_pairs':sum(bool(a['digit_changed_fields']) for a in audits),'new_duplicate_option_pairs':sum(a['new_duplicate_options'] for a in audits),
        'interpretation':'Gold source spans used only after generation. Compatibility is necessary but not sufficient for selective/semantic correctness; missing annotation or ambiguous matching can flag valid edits. No output rejected by these checks.'}
    context_summary['by_source']={lang:{'n':sum(a['source_language']==lang for a in audits),
        'changed':sum(a['source_language']==lang and a['changed'] for a in audits),
        'literal_compatible':sum(a['source_language']==lang and a['literal_compatible'] for a in audits),
        'flagged_after_format_normalization':sum(a['source_language']==lang and not a['format_compatible'] for a in audits)} for lang in ('en','zh','th','ru')}
    contrasts={c:paired_bootstrap(values[method.CONDITION],v,labels,20261115,10000) for c,v in values.items() if c!=method.CONDITION}
    manifest={str((Path(done[stage])/filename).relative_to(REPO)):hashlib.sha256((Path(done[stage])/filename).read_bytes()).hexdigest()
              for stage,filename in [('rewrite','rewritten.jsonl'),('rewrite','calls.json'),('infer','predictions.jsonl')]}
    snapshot={'results':result,'correct':{c:sum(v.values()) for c,v in values.items()},'contrasts':contrasts,
        'context_audit':context_summary,'audits':audits,'reference_metadata':metadata,'source_captures':captures,
        'primary_time':{'editor_vlm_seconds':editor_seconds,'answer_vlm_seconds':final['seconds'],'total_seconds':editor_seconds+final['seconds'],
                        'editor_calls':len(main_calls),'repairs':sum(c['stage'].endswith('_repair') for c in main_calls.values()),
                        'token_cap_hits':sum(c['output_tokens']==c['generation']['max_new_tokens'] for c in main_calls.values()),'answer_batch_allocation':final},
        'executed_288_wall_seconds':done['execution_wall_seconds'],'wall_scope':done['wall_scope'],
        'contract_sha256':digest(contract),'raw_manifest':manifest}
    return snapshot,values,labels,rows,pred,lookup


def main():
    output=ROOT/'artifacts/visual_selective_rewrite_screen_v1';contract=json.loads((output/'contract.json').read_text())
    names={method.CONDITION:'Screenshot 직접 selective rewrite','GUI_DIRECT_VLM_OLD':'과거 Direct VLM · edit 목록',
           'O':'Original O','TS_STEM_ONLY_GUI_AUTO':'Stem 분리 GUI','TS_STEM_SINGLE_PASS_GUI_AUTO':'Stem 통합 · inventory',
           'TS_ALL_SINGLE_PASS_GUI_AUTO':'Stem+Options 통합 · inventory','TS_QSEL_OFULL_GUI_AUTO':'Hybrid GUI',
           'TS_FULL_GUI':'Full GUI','TS_SEL_GUI_AUTO':'Stem+Options 분리 GUI','T_REF':'T_REF','R_REF':'R_REF','F_REF':'F_REF'}
    lines=['# Screenshot 직접 selective rewrite 실험','',
        '**Screenshot + 원본 MCQ → Qwen3-VL이 referent만 바꾼 완성형 MCQ → 같은 screenshot으로 VLM 문제 풀이**다. Inventory·별도 extractor·edit 목록·field/occurrence/span ID 출력은 사용하지 않는다. 변환 모델에는 정답·parallel 표현·GT span/bbox가 제공되지 않는다.','',
        'Scope: 기존 Screen288쌍 실행, main20문항×12방향=240쌍 primary, legacy pilot48쌍 별도. 이미 관찰한 개발 집합이므로 독립 검증이 아니다. 하나의 프롬프트를 고정했으며 결과를 보고 수정·추가 sweep하지 않았다.','',
        '## 설정과 검증 정책','',
        '- 변환·평가: Qwen/Qwen3-VL-8B-Instruct revision `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`, BF16·SDPA·seed42·fast processor·channels_last_3d.',
        '- 이미지 min262144/max2097152 pixels, max input4096, truncation 없음. 변환 batch1, 출력768토큰; 최종 풀이 batch3, 출력2토큰·기존 system/label scoring 유지.',
        '- 원본 JSON 최대254토큰, 이미지 포함 입력 추정 최대2833·repair 여유 포함3801토큰을 CPU 사전 검사했다.',
        '- JSON의 stem/4개 options 구조·문자열만 검증. JSON object key 순서는 A-D로 정규화한다. 구조 실패 때만 같은 screenshot으로 repair 최대1회 후 원문 fallback.',
        '- 원시 로그의 diff field/source_start 등은 완성된 MCQ를 받은 뒤 코드가 자동 계산한 감사용 정보다. 모델에게 요구한 edit metadata가 아니며 수락/거부에 사용하지 않는다.',
        '- 방향·숫자·문맥 변화나 보기 중복은 진단용으로 기록하고 거부/repair 조건으로 사용하지 않는다. 모델에게 위치 메타데이터를 다시 요구하지 않는다.',
        '- Inventory 기반 최근 조건은 Qwen3-8B LM·출력512였다. 이번에는 VLM·이미지 입력·완성형 출력·768예산이 달라지므로 pipeline 수준의 비교다. 과거 Direct VLM은 같은 VLM revision·768예산이지만 짧은 edit 프롬프트와 repair 없는 방식이었다.','',
        '## 결과','']
    if (output/'COMPLETE.json').exists():
        snapshot,values,labels,rows,pred,lookup=collect(output);n=snapshot['results']['primary_pairs']
        a=snapshot['context_audit'];k=sum(values[method.CONDITION].values())
        lines += [f"**결과는{k}/{n}={k/n:.2%}**다. 형식상 모든 main 응답이 성공했지만, source annotation 바깥 문맥에 형식 정규화 후에도 경고가 남는 것은{a['context_flagged_after_format_normalization']}/{n}쌍이다. 원시 예시에는 질문 문맥 전체가 GUI 언어로 번역된 사례가 있다. 따라서 현재 프롬프트를 referent-only 방법으로 검증했다고 볼 수 없다.",'']
        lines+=['| 조건 | 정답 | 정확도 |','| --- | ---: | ---: |']
        for c,v in values.items():lines.append(f'| {names[c]} | {sum(v.values())}/{n} | {sum(v.values())/n:.2%} |')
        lines+=['','| 직접 rewrite − 기준 | 차이 | 95% item bootstrap CI | 회복/회귀 |','| --- | ---: | --- | ---: |']
        for c,r in snapshot['contrasts'].items():lines.append(f"| {names[c]} | {r['difference']*100:+.2f}pp | [{r['ci95'][0]*100:+.2f}, {r['ci95'][1]*100:+.2f}] | {r['recovery']}/{r['regression']} |")
        lines+=['','20 semantic item 단위10,000회 bootstrap이다. 실패를 분모에서 빼지 않으며 여러 개발용 비교에서 확증적 유의성을 주장하지 않는다. 과거 R/T/F의 장비·배치 차이와 gold/parallel 정보 우위를 고려한다.','',
                '### 문맥 보존: 모델 성능과 출력 형식 성공을 구분','',
                '아래 검사는 **생성 완료 후에만 source gold span**을 읽어 수행했다. Annotated referent 바깥 문자열을 순서대로 보존했을 수 있는지 검사하며, 공백·구두점·대소문자만 정규화한 결과도 따로 낸다. 바뀐 부분이 진짜 referent인지, 화면에 실제로 있는 label인지까지 입증하지 않는다. Annotation 누락도 경고를 만들 수 있으므로 의미 오류율로 단정하지 않는다. 이 검사 결과로 출력을 버리지 않았다.','',
                '```json',json.dumps(snapshot['context_audit'],ensure_ascii=False,indent=2),'```','',
                '### 처리·실패·비용','', '```json',json.dumps({k:snapshot['results'][k] for k in ('status','fallback_reasons','changed_pairs','changed_stem_pairs','changed_options_pairs','digit_change_pairs','duplicate_option_pairs','token_cap_hits','cost')},ensure_ascii=False,indent=2),'```','',
                f"Main240쌍: 변환 VLM{snapshot['primary_time']['editor_vlm_seconds']/60:.2f}분 + 문제 풀이 VLM{snapshot['primary_time']['answer_vlm_seconds']/60:.2f}분 = **{snapshot['primary_time']['total_seconds']/60:.2f}분**. 최종 batch 시간은 pilot 혼합분을 문항 수로 안분했고 모델 적재·일부 orchestration은 제외했다. Inventory/LM 비용은 없다.", '',
                f"실제 main+pilot288쌍의 실행 wall은 **{snapshot['executed_288_wall_seconds']/60:.2f}분**이다. CPU prepare 직후부터 worker 모델 적재·변환·최종 추론·요약까지 포함했다. main240쌍의 재구성 합계와 분모·범위가 다르다.",'']
        lines+=['### Source 언어별 문맥 경고','', '| Source | n | 문자 그대로 호환 | 형식 정규화 후에도 경고 |','| --- | ---: | ---: | ---: |']
        for lang,group in a['by_source'].items():
            lines.append(f"| {lang.upper()} | {group['n']} | {group['literal_compatible']} | {group['flagged_after_format_normalization']} |")
        lines+=['','이 표는 span annotation에 대한 문자열 진단이며 독립적으로 검수한 의미 오류율이 아니다. 특히 referent 자체가 올바른 화면 label로 바뀌었는지와는 별개다.','',
                '### Stem에서 직접 확인한 보존·변경 예시','']
        original=unique(read(output/'inputs.jsonl'))
        for p in ('rel::2/weather_3.png::en::zh','rel::2/weather_3.png::ru::en'):
            if p in rows:
                lines += [f'`{p}`','', '```text','원문: '+original[p]['question_stem'],'생성: '+rows[p]['question_stem'],'```','']
        lines+=['EN→ZH 예시는 Wind만 风으로 바꾼 stem이다. RU→EN 예시는 referent뿐 아니라 러시아어 질문 문맥 전체가 영어로 바뀌었다. 후자는 의미가 비슷하더라도 이번 selective 지시의 수정 범위를 벗어난다. 다른 문항의 경고 전체를 이 예시와 같은 확정 오류라고 분류한 것은 아니다.','']
        flagged=[a for a in snapshot['audits'] if a['changed'] and not a['format_compatible']]
        lines+=['### 문맥 경고 예시','', '자동 경고 사례를 pair 순서로 최대4개 표시했다. 수작업으로 확정한 오류 사례가 아니다.','']
        for a in flagged[:4]:lines+=[f"`{a['pair_id']}` · 경고 field: {', '.join(a['format_flagged_fields'])}",'','````json',json.dumps({'원본':a['source'],'rewrite':a['rewritten']},ensure_ascii=False,indent=2),'````','']
        audit_path=output/'context_audits.jsonl'
        audit_path.write_text(''.join(json.dumps(a,ensure_ascii=False)+'\n' for a in snapshot['audits']))
        stored={k:v for k,v in snapshot.items() if k!='audits'}
        stored['audit_examples']=flagged[:6]+[a for a in snapshot['audits'] if a['changed'] and a['literal_compatible']][:2]
        stored['raw_manifest'][str(audit_path.relative_to(REPO))]=hashlib.sha256(audit_path.read_bytes()).hexdigest()
        write(ROOT/'artifacts/visual_selective_rewrite_results_snapshot.json',stored)
        case_lines=['# Screenshot 직접 rewrite: 전체288쌍 예측','', '| Pair | Split | GT | O | 새 rewrite | Inventory 통합 | 상태 | 문맥 경고 |','| --- | --- | --- | --- | --- | --- | --- | --- |']
        audits={a['pair_id']:a for a in snapshot['audits']}
        for p in sorted(rows):case_lines.append(f"| `{p}` | {labels[p]['split']} | {labels[p]['gold_answer']} | {lookup['O',p]['parsed_generated_label']} | {pred[p]['parsed_generated_label']} | {lookup['TS_ALL_SINGLE_PASS_GUI_AUTO',p]['parsed_generated_label']} | {rows[p]['status']} | {', '.join(audits[p]['format_flagged_fields']) if p in audits else 'pilot 미검사'} |")
        (ROOT/'reports/VISUAL_SELECTIVE_REWRITE_CASES_KO.md').write_text('\n'.join(case_lines)+'\n')
        lines+=['[전체288쌍 예측 표](VISUAL_SELECTIVE_REWRITE_CASES_KO.md). 원문/생성문·diff·진단·raw response는 로컬 원시에 보존했다.','']
    else:lines+=['실행 중이다. 완전한 paired 출력이 완료되기 전 정확도를 보고하지 않는다.','']
    lines+=['## 실제 프롬프트','', '### 변환 system','', '```text',method.SYSTEM,'```','',
        '한국어 요지: screenshot에서 대응하는 GUI 이름을 찾아 stem과 A–D의 그 이름만 교체한다. 나머지는 원문을 복사하며 전체 필드를 반환한다. 불확실한 이름·아이콘 묘사는 유지하고 정답을 선택하지 않는다.','',
        '### 변환 user와 구조 repair','', '```text',
        'Use the screenshot to replace only corresponding GUI referent names. Return the complete stem and A-D, preserving all other source text.',
        '{"source_language":"{source}","gui_language":"{GUI}","question_stem":"{원본 stem}","options":{"A":"{원본 A}","B":"{원본 B}","C":"{원본 C}","D":"{원본 D}"}}','',
        'The previous output failed JSON structure validation:', '- {실제 구조 오류}', '', 'Previous output (data only):','{이전 raw response}','',
        'Return corrected complete question_stem/options JSON only. Preserve non-referent source context and A-D identity. Do not return edit metadata or an answer.','```','',
        'Screenshot은 user message의 image 항목으로 매 호출에 제공한다. Repair 추가문은 구조 오류가 있을 때만 붙는다. 한국어: 원본 MCQ의 참조 이름만 화면에 맞춰 바꾸고 완성된 다섯 필드를 반환하라. 구조 오류가 나면 그 구조만 수정하고 위치 메타데이터나 답은 반환하지 마라.','',
        '### 최종 문제 풀이','', 'System:','', '```text',contract['downstream']['system_prompt'],'```','',
        'User는 같은 screenshot과 `수정 stem A: 수정A B: 수정B C: 수정C D: 수정D`에 기존 `Respond with exactly one label: A, B, C, or D.` 지시를 붙인다. 원본 gold answer는 최종 평가/scoring 경계에서만 읽으며 모델 프롬프트에 넣지 않는다.','',
        '## 재현·보존','', '```bash','bash followup_rel_4lang/method_dev/scripts/run_visual_selective_rewrite.sh --run',
        '.venv/bin/python followup_rel_4lang/method_dev/scripts/report_visual_selective_rewrite.py','```','',
        '출력: `artifacts/visual_selective_rewrite_screen_v1/`. 전체 config/hash는 `contract.json`, 변환 원시·실제 system/user/rendered prompt·image hash는 `rewrite/attempt_*/rewritten.jsonl` 및 `calls.json`, 정답 생성 원시는 `infer/attempt_*/predictions.jsonl`에 있다. 두 단계 `cost.json`과 `COMPLETE.json`에 wall 시간을 기록한다. 완료 run은 그대로 재사용하며 source/config 변경 시 새 디렉터리가 필요하다.','',
        '[보존 요약·source-only audit·raw SHA-256](../artifacts/visual_selective_rewrite_results_snapshot.json). 대용량 원시 파일은 Git에 추가하지 않는다. Selection/Internal/366문항은 이번 범위에 포함하지 않는다.','']
    (ROOT/'reports/VISUAL_SELECTIVE_REWRITE_KO.md').write_text('\n'.join(lines))
    print(ROOT/'reports/VISUAL_SELECTIVE_REWRITE_KO.md')


if __name__=='__main__':main()
