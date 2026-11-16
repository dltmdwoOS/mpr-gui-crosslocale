"""Post-hoc checks and comparisons for fully completed restored two-stage cohorts."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from mpr_crosslocale.methods.selective_alignment.schemas import digest,fields,render
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits
from mpr_crosslocale.inference.answer_parser import parse_label
from search_pipeline import paired_bootstrap,EXCLUDED
from reference_comparison import load_references

CONTRASTS=[
    ('TS_FULL_GUI','TS_FULL_TXT'),('TS_SEL_GUI_AUTO','TS_SEL_TXT_AUTO'),
    ('TS_SEL_GUI_ORACLE','TS_SEL_TXT_ORACLE'),('TS_SEL_GUI_ORACLE','TS_SEL_GUI_AUTO'),
    ('TS_QSEL_OFULL_GUI_AUTO','TS_QSEL_OFULL_TXT_AUTO'),
    ('TS_QSEL_OFULL_GUI_AUTO','TS_SEL_GUI_AUTO'),('TS_QSEL_OFULL_GUI_AUTO','TS_FULL_GUI')]
SHORT={'O':'O','TS_FULL_GUI':'전체 GUI 번역','TS_FULL_TXT':'전체 TXT 번역',
    'TS_SEL_GUI_AUTO':'자동 Selective GUI','TS_SEL_TXT_AUTO':'자동 Selective TXT',
    'TS_SEL_GUI_ORACLE':'Oracle Selective GUI','TS_SEL_TXT_ORACLE':'Oracle Selective TXT',
    'TS_QSEL_OFULL_GUI_AUTO':'Query 선택적 + Options 전체 GUI','TS_QSEL_OFULL_TXT_AUTO':'Query 선택적 + Options 전체 TXT'}


def completed_summary(work,contract,originals,labels,read,refs):
    complete=json.loads((work/'COMPLETE.json').read_text())
    if complete['execution_mode']!='gpu':raise ValueError('Mock cohort is not empirical')
    rewrite=Path(complete['rewrite']);inference=Path(complete['predictions'])
    if not (rewrite/'COMPLETE').exists() or not (inference/'COMPLETE').exists():raise ValueError('Incomplete cohort stages')
    ic=json.loads((inference/'contract.json').read_text())
    if ic['execution_mode']!='gpu' or ic['downstream']!=contract['config']['downstream'] or ic['input_sha256']!=digest(list(originals.values())) or ic['condition_order']!=['O',*contract['conditions']]:raise ValueError('Downstream contract mismatch')
    predictions=read(inference/'predictions.jsonl');lookup={}
    for row in predictions:
        key=(row['condition'],row['pair_id'])
        if key in lookup:raise ValueError('Duplicate prediction')
        if row['execution_mode']!='gpu' or row['parallel_id']!=originals[row['pair_id']]['parallel_id']:raise ValueError('Prediction identity/mode mismatch')
        if parse_label(row['generated_text'])!=row['parsed_generated_label']:raise ValueError('Raw answer parse mismatch')
        lookup[key]=row
    conditions=['O',*contract['conditions']]
    if set(lookup)!={(c,p) for c in conditions for p in originals}:raise ValueError('Completed prediction set differs')
    primary=sorted(p for p in originals if labels[p]['split']=='main' and p!=EXCLUDED)
    values={c:{p:int(lookup[c,p]['status']=='success' and lookup[c,p]['parsed_generated_label']==labels[p]['gold_answer']) for p in primary} for c in conditions}
    rewritten={c:{r['pair_id']:r for r in read(rewrite/(c+'.jsonl'))} for c in contract['conditions']}
    saved=json.loads((work/'results.json').read_text())
    outcomes={}
    for condition in conditions:
        v=values[condition];result={'n':len(primary),'correct':sum(v.values()),'by_gui':{},'by_direction':{}}
        if saved['conditions'][condition]['n']!=len(primary) or saved['conditions'][condition]['correct']!=result['correct']:raise ValueError('Stored accuracy mismatch')
        if condition!='O':
            contrast=paired_bootstrap(v,values['O'],labels,20261115,10000)
            if contrast!=saved['conditions'][condition]['vs_O']:raise ValueError('Stored paired CI mismatch')
            result['vs_O']=contrast
            rr=rewritten[condition]
            if set(rr)!=set(originals):raise ValueError('Incomplete transformation')
            result['status']=dict(Counter(rr[p]['status'] for p in primary))
            result['fallback_errors']=dict(Counter(e for p in primary for e in rr[p]['errors']))
            result['changed_pairs']=sum(fields(rr[p])!=fields(originals[p]) for p in primary)
            same=[p for p in primary if render(fields(originals[p]))==rr[p]['modified_question']]
            result['same_as_O_questions']=len(same)
            result['label_changes_on_same_O_question']=sum(lookup[condition,p]['parsed_generated_label']!=lookup['O',p]['parsed_generated_label'] for p in same)
        for gui in sorted({originals[p]['gui_language'] for p in primary}):
            ids=[p for p in primary if originals[p]['gui_language']==gui]
            result['by_gui'][gui]={'n':len(ids),'correct':sum(v[p] for p in ids)}
        for direction in sorted({originals[p]['source_language']+'→'+originals[p]['gui_language'] for p in primary}):
            ids=[p for p in primary if originals[p]['source_language']+'→'+originals[p]['gui_language']==direction]
            result['by_direction'][direction]={'n':len(ids),'correct':sum(v[p] for p in ids)}
        outcomes[condition]=result
    contrasts={left+' − '+right:paired_bootstrap(values[left],values[right],labels,20261115,10000) for left,right in CONTRASTS if left in values and right in values}
    hybrid={}
    for gui in ('GUI','TXT'):
        name=f'TS_QSEL_OFULL_{gui}_AUTO';full=f'TS_FULL_{gui}'
        if name not in rewritten:continue
        rr=rewritten[name]
        if full in rewritten and any(rr[p]['options']!=rewritten[full][p]['options'] for p in originals):raise ValueError('Hybrid options differ from Full')
        if any(r['field']!='question_stem' for row in rr.values() for r in row['extracted_referents'] or []):raise ValueError('Hybrid used option spans')
        for pid in originals:
            if apply_edits(originals[pid],rr[pid]['edits'])['question_stem']!=rr[pid]['question_stem']:raise ValueError('Hybrid changed nonreferent stem context')
        hybrid[name]={'components':{key:sum(rr[p]['components'][key] for p in primary) for key in ('stem_extraction_failed','stem_alignment_failed','options_full_pipeline_failed')},
            'partial_fallback_pairs':sum(rr[p]['status']=='partial_fallback' for p in primary),'options_equal_full':full in rewritten,
            'options_changed_fields':sum(rr[p]['components']['options_changed'] for p in primary)}
    historical={}
    for name in ('T_REF','R_REF','F_REF'):
        if not set(primary)<=set(refs[name]):raise ValueError('Missing historical reference pairs')
        scores={p:int(refs[name][p].get('status')=='success' and refs[name][p].get('parsed_generated_label')==labels[p]['gold_answer']) for p in primary}
        historical[name]={'n':len(primary),'correct':sum(scores.values()),'contrasts':{c:paired_bootstrap(values[c],scores,labels,20261115,10000) for c in values if c!='O'}}
    stage_costs={}
    for stage in ('inventory','extract','extract_stem','rewrite'):
        directory=Path(complete[stage])
        cost=json.loads((directory/'cost.json').read_text())
        stage_costs[stage]={'wall_seconds':cost['wall_seconds'],'calls':cost['calls'],'cache_hits':cost['cache_hits'],'new_runtime_seconds':cost['new_runtime_ms']/1000}
    batches={}
    for row in predictions:
        key=row['batch_id'];value=(row['batch_runtime_ms'],row['batch_size'])
        if key in batches and batches[key]!=value:raise ValueError('Inconsistent inference batch accounting')
        batches[key]=value
    return {'executed_pairs':len(originals),'primary_pairs':len(primary),'items':len({labels[p]['parallel_id'] for p in primary}),
        'prediction_rows':len(predictions),'prediction_status':dict(Counter(r['status'] for r in predictions)),
        'outcomes':outcomes,'contrasts':contrasts,'hybrid':hybrid,'historical_references':historical,
        'stage_costs':stage_costs,'inference_batch_seconds':sum(v[0] for v in batches.values())/1000,
        'inference_peak_reserved_gib':max(r['peak_reserved_bytes'] for r in predictions)/2**30,
        'attempts':{s:len(list((work/s).glob('attempt_*'))) for s in ('inventory','extract','extract_stem','rewrite','infer')},
        'pair_ids_sha256':digest(primary),'checks':['raw answer parser','downstream model/system/input contract','saved accuracy and vs O CI','hybrid Full options identity','hybrid source-only edits','no duplicate/missing prediction']}


def add_completed(snapshot,run,repo,root,labels,contract,read):
    cohorts=[c for c in snapshot['cohorts'] if (run/c/'COMPLETE.json').exists()]
    if not cohorts:return
    originals={c:{r['pair_id']:r for r in read(run/c/'inputs.jsonl')} for c in snapshot['cohorts']}
    # Pure historical reference join; no invalidated v1 automatic predictions enter this table.
    def use(path):
        snapshot['source_captures'][str(path.relative_to(repo))]={'path':str(path.relative_to(repo)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'captured_bytes':path.stat().st_size}
        return path
    refs,metadata,_=load_references(repo,labels,originals,use,contract['config']['downstream']['model_config'],contract['config']['historical_baseline_contract_sha256'])
    for source in metadata['source_runs'].values():
        if source['model_config']!=contract['config']['downstream']['model_config'] or source['system_prompt']!=contract['config']['downstream']['system_prompt']:raise ValueError('Historical model/system differs from current evaluation')
    snapshot['reference_metadata']=metadata
    for cohort in cohorts:snapshot['cohorts'][cohort]['completed_evaluation']=completed_summary(run/cohort,contract,originals[cohort],labels,read,refs)
    stem_root=root/'artifacts/stem_only_gui_screen_v1'
    if 'screen' in cohorts and (stem_root/'COMPLETE.json').exists():
        marker=json.loads((stem_root/'COMPLETE.json').read_text());stem_contract=json.loads((stem_root/'contract.json').read_text())
        if Path(stem_contract['source_cohort']).resolve()!=(run/'screen').resolve():return
        if marker['execution_mode']!='gpu' or marker['contract_sha256']!=digest(stem_contract):raise ValueError('Stem-only contract mismatch')
        for filename,sha in stem_contract['source_sha256'].items():
            if hashlib.sha256(Path(filename).read_bytes()).hexdigest()!=sha:raise ValueError('Stem-only baseline changed')
        stem_rows={r['pair_id']:r for r in read(stem_root/'rewritten.jsonl')}
        if digest(list(stem_rows.values()))!=stem_contract['composed_sha256']:raise ValueError('Stem-only input changed')
        pred_dir=Path(marker['predictions'])
        if not (pred_dir/'COMPLETE').exists():raise ValueError('Stem-only incomplete')
        predictions=read(pred_dir/'predictions.jsonl');pred={r['pair_id']:r for r in predictions}
        if len(pred)!=len(predictions) or set(pred)!=set(originals['screen']):raise ValueError('Stem-only pair set mismatch')
        ids=sorted(p for p in pred if labels[p]['split']=='main' and p!=EXCLUDED)
        if any(r['execution_mode']!='gpu' or parse_label(r['generated_text'])!=r['parsed_generated_label'] for r in predictions):raise ValueError('Invalid Stem-only outputs')
        for pid,row in stem_rows.items():
            if row['options']!=originals['screen'][pid]['options']:raise ValueError('Stem-only options changed')
            if apply_edits(originals['screen'][pid],row['edits'])['question_stem']!=row['question_stem']:raise ValueError('Stem-only context changed')
        saved=json.loads((stem_root/'results.json').read_text())
        correct=sum(r['status']=='success' and r['parsed_generated_label']==labels[p]['gold_answer'] for p,r in pred.items() if p in ids)
        if saved['primary_pairs']!=len(ids) or saved['correct']['TS_STEM_ONLY_GUI_AUTO']!=correct:raise ValueError('Stem-only accuracy differs')
        saved['source_prediction_sha256']=hashlib.sha256((pred_dir/'predictions.jsonl').read_bytes()).hexdigest()
        snapshot['cohorts']['screen']['completed_evaluation']['stem_only']=saved
        diagnostic_path=root/'artifacts/stem_only_diagnostic_snapshot.json'
        if diagnostic_path.exists():
            diagnostic=json.loads(use(diagnostic_path).read_text());cohort=snapshot['cohorts']['screen']['completed_evaluation']
            if diagnostic['pair_ids_sha256']!=cohort['pair_ids_sha256'] or diagnostic['correct']['Stem-only']!=correct:raise ValueError('R_stem diagnostic cohort differs')
            cohort['R_stem_reference']={'n':len(ids),'correct':diagnostic['correct']['R_stem'],'Stem_only_vs_R_stem':diagnostic['contrasts']['Stem-only − R_stem'],
                                       'historical_contract':diagnostic['historical_contract']}
        single_path=root/'artifacts/single_pass_stem_results_snapshot.json'
        single_marker=root/'artifacts/single_pass_stem_screen_v1/COMPLETE.json'
        if single_path.exists() and single_marker.exists():
            single=json.loads(use(single_path).read_text())
            single_contract=json.loads((single_marker.parent/'contract.json').read_text())
            done=json.loads(single_marker.read_text())
            if single['contract_sha256']!=digest(single_contract) or done['contract_sha256']!=digest(single_contract) or done['execution_mode']!='gpu':raise ValueError('Single-pass contract mismatch')
            if Path(single_contract['source_cohort']).resolve()!=(run/'screen').resolve():raise ValueError('Single-pass source differs')
            if single['results']['pair_ids_sha256']!=snapshot['cohorts']['screen']['completed_evaluation']['pair_ids_sha256']:raise ValueError('Single-pass primary pair set differs')
            for filename,sha in single['raw_manifest'].items():
                if hashlib.sha256((repo/filename).read_bytes()).hexdigest()!=sha:raise ValueError('Single-pass raw output changed')
            snapshot['cohorts']['screen']['completed_evaluation']['single_pass']=single
        all_path=root/'artifacts/single_pass_all_results_snapshot.json'
        all_marker=root/'artifacts/single_pass_all_screen_v1/COMPLETE.json'
        if all_path.exists() and all_marker.exists():
            all_result=json.loads(use(all_path).read_text());done=json.loads(all_marker.read_text())
            all_contract=json.loads((all_marker.parent/'contract.json').read_text())
            if all_result['contract_sha256']!=digest(all_contract) or done['contract_sha256']!=digest(all_contract) or done['execution_mode']!='gpu':raise ValueError('All-field single-pass contract mismatch')
            if Path(all_contract['source_cohort']).resolve()!=(run/'screen').resolve():raise ValueError('All-field single-pass source differs')
            if all_result['results']['pair_ids_sha256']!=snapshot['cohorts']['screen']['completed_evaluation']['pair_ids_sha256']:raise ValueError('All-field single-pass pairs differ')
            for filename,sha in all_result['raw_manifest'].items():
                if hashlib.sha256((repo/filename).read_bytes()).hexdigest()!=sha:raise ValueError('All-field single-pass raw changed')
            snapshot['cohorts']['screen']['completed_evaluation']['single_pass_all']=all_result
        visual_path=root/'artifacts/visual_selective_rewrite_results_snapshot.json'
        visual_marker=root/'artifacts/visual_selective_rewrite_screen_v1/COMPLETE.json'
        if visual_path.exists() and visual_marker.exists():
            visual=json.loads(use(visual_path).read_text());done=json.loads(visual_marker.read_text())
            visual_contract=json.loads((visual_marker.parent/'contract.json').read_text())
            if visual['contract_sha256']!=digest(visual_contract) or done['contract_sha256']!=digest(visual_contract) or done['execution_mode']!='gpu':raise ValueError('Visual rewrite contract mismatch')
            if Path(visual_contract['source_cohort']).resolve()!=(run/'screen').resolve():raise ValueError('Visual rewrite source differs')
            if visual['results']['pair_ids_sha256']!=snapshot['cohorts']['screen']['completed_evaluation']['pair_ids_sha256']:raise ValueError('Visual rewrite pairs differ')
            for filename,sha in visual['raw_manifest'].items():
                if hashlib.sha256((repo/filename).read_bytes()).hexdigest()!=sha:raise ValueError('Visual rewrite raw changed')
            snapshot['cohorts']['screen']['completed_evaluation']['visual_selective_rewrite']=visual


def render_completed(snapshot):
    finished=[c for c,g in snapshot['cohorts'].items() if 'completed_evaluation' in g]
    pending=[c for c in snapshot['cohorts'] if c not in finished]
    out=['## 완료된 cohort의 실제 문제 풀이 결과','',
         '**완료 cohort: '+', '.join(finished)+'**. '+('아직 완료되지 않은 cohort: '+', '.join(pending)+'. ' if pending else '')+'Pilot과 사전 제외 pair는 primary에서 분리한다. 모든 조건의 실패 fallback도 분모에 유지했다.']
    for cohort,g in snapshot['cohorts'].items():
        if 'completed_evaluation' not in g:continue
        s=g['completed_evaluation'];outcomes=s['outcomes'];n=s['primary_pairs']
        out+=['',f'### {cohort}: 정확도와 O 대비','',f"실행{s['executed_pairs']}pair 중 primary{s['items']}개 semantic item의{n}pair다.",'', '| 조건 | 정답 | 정확도 | ΔO | Item bootstrap95% CI | 회복/회귀 |','| --- | ---: | ---: | ---: | --- | ---: |']
        for name,r in outcomes.items():
            c=r.get('vs_O');out.append(f"| {SHORT.get(name,name)} | {r['correct']}/{n} | {r['correct']/n*100:.2f}% | "+(f"{c['difference']*100:+.2f}pp | [{c['ci95'][0]*100:+.2f}, {c['ci95'][1]*100:+.2f}] | {c['recovery']}/{c['regression']} |" if c else '— | — | — |'))
        stem=s.get('stem_only')
        if stem:
            k=stem['correct']['TS_STEM_ONLY_GUI_AUTO'];c=stem['contrasts']['O']
            out.append(f"| **Stem-only GUI · Options 원본** | **{k}/{n}** | **{k/n*100:.2f}%** | {c['difference']*100:+.2f}pp | [{c['ci95'][0]*100:+.2f}, {c['ci95'][1]*100:+.2f}] | {c['recovery']}/{c['regression']} |")
        single=s.get('single_pass')
        if single:
            q=single['results'];k=q['correct']['TS_STEM_SINGLE_PASS_GUI_AUTO'];c=q['contrasts']['O']
            out.append(f"| **Single-pass Stem GUI · 추출/정렬 통합** | **{k}/{n}** | **{k/n*100:.2f}%** | {c['difference']*100:+.2f}pp | [{c['ci95'][0]*100:+.2f}, {c['ci95'][1]*100:+.2f}] | {c['recovery']}/{c['regression']} |")
        all_single=s.get('single_pass_all')
        if all_single:
            q=all_single['results'];k=q['correct']['TS_ALL_SINGLE_PASS_GUI_AUTO'];c=q['contrasts']['O']
            out.append(f"| **Single-pass All GUI · Stem+Options referents 통합** | **{k}/{n}** | **{k/n*100:.2f}%** | {c['difference']*100:+.2f}pp | [{c['ci95'][0]*100:+.2f}, {c['ci95'][1]*100:+.2f}] | {c['recovery']}/{c['regression']} |")
        visual=s.get('visual_selective_rewrite')
        if visual:
            q=visual['results'];k=q['correct']['VISUAL_SELECTIVE_REWRITE'];c=q['contrasts']['O']
            out.append(f"| **Screenshot 직접 완성형 rewrite · 문맥 보존 별도 진단** | **{k}/{n}** | **{k/n*100:.2f}%** | {c['difference']*100:+.2f}pp | [{c['ci95'][0]*100:+.2f}, {c['ci95'][1]*100:+.2f}] | {c['recovery']}/{c['regression']} |")
        if 'R_stem_reference' in s:
            r=s['R_stem_reference'];out.append(f"| **R_stem · Stem-only 대응 reference** | **{r['correct']}/{n}** | **{r['correct']/n*100:.2f}%** | {(r['correct']-outcomes['O']['correct'])/n*100:+.2f}pp | — | — |")
        for name in ('R_REF','F_REF'):
            r=s['historical_references'][name]
            out.append(f"| {name} · parallel reference | {r['correct']}/{n} | {r['correct']/n*100:.2f}% | {(r['correct']-outcomes['O']['correct'])/n*100:+.2f}pp | — | — |")
        if single:
            c=single['results']['contrasts']['TS_STEM_ONLY_GUI_AUTO'];cost=single['cost_comparison']
            out+=['',f"추가 개발 조건인 **Single-pass−분리 Stem-only는{c['difference']*100:+.2f}pp**, CI[{c['ci95'][0]*100:+.2f}, {c['ci95'][1]*100:+.2f}]pp, 회복/회귀{c['recovery']}/{c['regression']}이다. 같은 main240쌍의 LM 변환 시간은{cost['separate_extraction_and_alignment_seconds']/60:.2f}분→{cost['single_pass_seconds']/60:.2f}분으로 늘었다. Options 범위 위반과 전체 응답 fallback의 영향은 [통합 실험 보고서](SINGLE_PASS_STEM_GUI_KO.md)에 정리했다. 현재 결과만으로 기존 분리 방식을 대체할 근거는 없다."]
        if all_single:
            c=all_single['contrasts']['TS_STEM_SINGLE_PASS_GUI_AUTO'];cost=all_single['main_lm_costs']
            out+=['',f"Options referents까지 허용한 **All-field 통합−Stem 통합은{c['difference']*100:+.2f}pp**, CI[{c['ci95'][0]*100:+.2f}, {c['ci95'][1]*100:+.2f}]pp, 회복/회귀{c['recovery']}/{c['regression']}이다. Main의 LM 변환 시간은 Stem 통합{cost['Stem-only 통합']['total_seconds']/60:.2f}분, All-field 통합{cost['All-field 통합']['total_seconds']/60:.2f}분이다. 이는 options 전체 번역이 아니라 referent만의 치환이며 field 인터페이스도 바뀐다. [실제 프롬프트·전체 결과·비용·실패 추적](SINGLE_PASS_ALL_GUI_KO.md)."]
        if visual:
            a=visual['context_audit'];t=visual['primary_time']
            out+=['',f"이미지 직접 rewrite는 inventory·span 위치 출력을 없애고 완성형 MCQ를 VLM에 받았다. 변경{a['changed_pairs']}쌍 중 source annotation 바깥 문맥에 형식 정규화 후에도 경고가 있는 것은{a['context_flagged_after_format_normalization']}쌍이다. 이 진단으로 출력을 제외하지 않았다. Main의 변환+문제 풀이 합은{t['total_seconds']/60:.2f}분이다. 정확도와 selective 지시 준수는 별도로 평가한다. [전체 원문 프롬프트·문맥 audit·시간·예측](VISUAL_SELECTIVE_REWRITE_KO.md)."]
        if stem:
            c=stem['contrasts']['TS_QSEL_OFULL_GUI_AUTO']
            out+=['',f"Stem-only는 완료된 Hybrid stem을 그대로 쓰고 A–D만 원본으로 복원했다. 새 추출·번역 없이 추가 downstream288쌍을 평가했다. **Stem-only−Hybrid는 {c['difference']*100:+.2f}pp**, CI[{c['ci95'][0]*100:+.2f}, {c['ci95'][1]*100:+.2f}]pp, 회복/회귀{c['recovery']}/{c['regression']}이다. Options Full을 추가한 Hybrid가 정답3개 높은 점추정이지만 구간이 넓어 우위를 확정하지 않는다. R/F는 같은 primary pair의 기존 parallel reference이며 자동 method가 아니다."]
        if 'R_stem_reference' in s:
            c=s['R_stem_reference']['Stem_only_vs_R_stem'];out+=['',f"조작 범위를 맞춘 **Stem-only−R_stem은{c['difference']*100:+.2f}pp**, CI[{c['ci95'][0]*100:+.2f}, {c['ci95'][1]*100:+.2f}]pp다. 과거 R_stem run의 O는163/240, 현재 O는162/240이며 label239/240일치했다. R 전체와의 격차를 stem만의 미회복분으로 해석하지 않는다. [실패 단계·병렬 mapping 점검·잔여 ETA](STEM_ONLY_DIAGNOSTIC_KO.md)."]
        no_clear_effect=all(r['vs_O']['ci95'][0]<=0<=r['vs_O']['ci95'][1] for r in outcomes.values() if 'vs_O' in r)
        out+=['',f"CI는 semantic item 단위 10,000회 bootstrap이다. {n}개 pair를 독립 문제{n}개로 취급하지 않는다. "+('O 대비 CI는 모두 0을 포함하거나 경계가0이다. ' if no_clear_effect else '')+'Point estimate만으로 유의한 개선을 주장하지 않으며, 여러 탐색 대비에 대한 보정된 유의성도 주장하지 않는다.','',
              '### 조건 간 주요 paired 비교','', '| 비교 | 차이 | 95% CI | 회복/회귀 |','| --- | ---: | --- | ---: |']
        for name,c in s['contrasts'].items():
            left,right=name.split(' − ');out.append(f"| {SHORT[left]} − {SHORT[right]} | {c['difference']*100:+.2f}pp | [{c['ci95'][0]*100:+.2f}, {c['ci95'][1]*100:+.2f}] | {c['recovery']}/{c['regression']} |")
        out+=['','여기서 GUI/TXT 차이는 inventory 사용뿐 아니라 서로 다른 system prompt·검증 경로도 포함한다. Hybrid는 stem-only 추출 prompt와 options context 언어가 달라지는 pipeline 수준의 비교다. 각 대비를 한 요인의 순수 인과 효과로 해석하지 않는다.','',
              '### R/T/F reference와 같은 분모 비교','', '| Reference | 정답 | 정확도 |','| --- | ---: | ---: |']
        for name,r in s['historical_references'].items():out.append(f"| {name} | {r['correct']}/{n} | {r['correct']/n*100:.2f}% |")
        out+=['','T_REF는 annotation span+Gemma 번역, R_REF는 parallel referent alignment, F_REF는 parallel 전체 localization이다. 예전 잘못된 inventory method 결과를 재사용한 것이 아니라 독립적인 기존 reference다. 같은 pair ID·gold·모델 revision·system을 검사해 결합했지만 이전 RTX4090 batch/queue와 현재 B200 MIG의 차이가 남는다. 각 신규 method−reference CI와 회복/회귀는 snapshot에 있다.','',
              '### 새 control에서 실패가 실제로 줄었나','', '| 조건 | 전체 원문 fallback | 부분 fallback | 주요 오류 |','| --- | ---: | ---: | --- |']
        for name,r in outcomes.items():
            if name=='O':continue
            errors='; '.join(f'{e}: {v}' for e,v in r['fallback_errors'].items()) or '없음'
            out.append(f"| {SHORT[name]} | {r['status'].get('fallback_original',0)} | {r['status'].get('partial_fallback',0)} | {errors} |")
        if 'TS_QSEL_OFULL_GUI_AUTO' in s['hybrid']:
            hybrid=s['hybrid']['TS_QSEL_OFULL_GUI_AUTO']['components']
            out+=['',f"GUI Hybrid의 Query 추출 실패{hybrid['stem_extraction_failed']}쌍·정렬 실패{hybrid['stem_alignment_failed']}쌍을 별도 기록했다. Options Full pipeline 실패는{hybrid['options_full_pipeline_failed']}쌍이었다. 전체 원문 fallback과 부분 fallback을 같은 실패로 세지 않는다. 단계별 parser 검증 실패 감소가 의미 정확도 향상을 자동으로 보장하지 않는다."]
        out+=['',
              '### GUI 언어별 결과','', '| 조건 | EN | ZH | TH | RU |','| --- | ---: | ---: | ---: | ---: |']
        for name,r in outcomes.items():out.append('| '+SHORT[name]+' | '+' | '.join(f"{r['by_gui'][gui]['correct']}/{r['by_gui'][gui]['n']} ({r['by_gui'][gui]['correct']/r['by_gui'][gui]['n']*100:.2f}%)" for gui in ('en','zh','th','ru'))+' |')
        if stem:out.append('| Stem-only GUI · Options 원본 | '+' | '.join(f"{stem['by_gui'][gui]['correct']['TS_STEM_ONLY_GUI_AUTO']}/{stem['by_gui'][gui]['n']} ({stem['by_gui'][gui]['correct']['TS_STEM_ONLY_GUI_AUTO']/stem['by_gui'][gui]['n']*100:.2f}%)" for gui in ('en','zh','th','ru'))+' |')
        out+=['','GUI 언어별 결과도 같은 semantic item에서 나온 반복 관측이며 기술 통계로 본다. 전체 평균이 높아져도 모든 GUI 언어에 동일하게 이득이 생긴 것은 아니다.','',
              '### 비용과 재현 검사','', '| 단계 | Wall·분 | 호출 | cache hit |','| --- | ---: | ---: | ---: |']
        for name,cost in s['stage_costs'].items():out.append(f"| {name} | {cost['wall_seconds']/60:.2f} | {cost['calls']} | {cost['cache_hits']} |")
        attempts=', '.join(f'{key}={value}' for key,value in s['attempts'].items())
        shifts=sum(r.get('label_changes_on_same_O_question',0) for r in outcomes.values())
        out+=['',f"Downstream batch 시간 합계는{s['inference_batch_seconds']/60:.2f}분이며 모델 적재와 프로세스 기동은 제외한다. Peak reserved는{s['inference_peak_reserved_gib']:.2f}GiB, 전체 예측{s['prediction_rows']:,}행은 모두GPU mode였다. Attempt 수: {attempts}. Hybrid options는 Full과 모든 실행 pair에서 정확히 같고, stem은 source span 밖이 보존되는 것을 재검증했다. 같은 자기 MCQ인데 O와 label이 바뀐 사례는 완료된 조건들에서{shifts}개였다. 이는 다른 batch 입력 효과가 일반적으로 불가능하다는 주장은 아니다."]
        if cohort!='screen':continue
        out+=['',
              '### 현재 판단','',
              '- Inventory-conditioned 조건의 point estimate는 대응 text-only보다 일관되게 높았다. 다만 작은 Screen 표본에서 구간이 넓다.',
              '- 자동 method 중 Query 선택적+Options 전체 GUI가74.17%로 가장 높고, Oracle GUI는75.00%였다. Oracle은 gold source span을 사용하므로 자동 method 순위에 넣지 않는다.',
              '- 자동 Hybrid는 R_REF80.83%보다6.67pp, F_REF80.00%보다5.83pp 낮다. Oracle GUI도 R_REF보다5.83pp 낮다. 아직 R 효과를 재현했다고 말할 수 없다.',
              '- 이 수치는 Screen만의 결과다. Screen을 본 뒤 method를 바꾸면 새 development iteration으로 기록하고, 이 수치를158-item 전체 평가로 확대 해석하지 않는다.']
    return '\n'.join(out)
