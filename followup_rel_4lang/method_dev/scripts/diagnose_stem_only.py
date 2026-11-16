"""Privileged post-hoc R_stem comparison, failure audit and measured-runtime ETA. No inference."""
import csv
import gzip
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

REPO=Path(__file__).resolve().parents[3];ROOT=Path(__file__).resolve().parent.parent;REL=ROOT.parent
sys.path[:0]=[str(REPO),str(REPO/'01_code/src'),str(Path(__file__).parent)]
from mpr_crosslocale.methods.selective_alignment.schemas import digest,fields,render
from mpr_crosslocale.methods.selective_alignment.inventory import normalize
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits
from mpr_crosslocale.inference.answer_parser import parse_label
from followup_rel_4lang.method_dev.two_stage_v2 import prompts
from search_pipeline import paired_bootstrap,EXCLUDED

VISUAL_REVIEW=[
    {'parallel_id':'rel::3/map_6.jpg','gui_language':'th','finding':'R stem string เลือกในแผนที่ is visibly present in the screenshot; the inventory failed and is empty.','category':'visible_label_missing_due_to_inventory_failure'},
    {'parallel_id':'rel::5/forest_2.jpg','gui_language':'ru','finding':'Visible screenshot and inventory contain Начинающий плантатор; R uses truncated Начинающий планта.... Exact R membership absence is not a missing visible full label.','category':'reference_truncation_not_ocr_omission'},
    {'parallel_id':'rel::2/map_9.png','gui_language':'en','finding':'Both Avoid Tolls and Avoid Highways are visible and present in inventory. Existing mapping_audit_review.csv flags the Thai source expression as mapping_error.','category':'known_parallel_mapping_error_both_labels_present'}]


def unique(rows,key):
    out={}
    for r in rows:
        k=key(r)
        if k in out:raise ValueError('Duplicate ID: '+str(k))
        out[k]=r
    return out


def source_span_state(gold,predicted):
    if predicted is None:return 'extraction_failed'
    if all(any(p['start']==g['start'] and p['end']==g['end'] for p in predicted) for g in gold):return 'exact_boundary'
    if all(any(p['start']<=g['start'] and p['end']>=g['end'] for p in predicted) for g in gold):return 'overwide_boundary'
    return 'missing_or_partial_span'


def membership(targets,strings,status):
    normalized=[normalize(s) for s in strings]
    if all(normalize(t) in normalized for t in targets):return 'exact'
    if status!='success' or not strings:return 'inventory_failed_or_empty'
    if all(any(normalize(t) in s for s in normalized) for t in targets):return 'substring_only'
    if all(any(normalize(t).rstrip('.…') in s for s in normalized) for t in targets):return 'ellipsis_prefix_only'
    return 'not_found_by_lexical_checks'


def observed_bucket(row):
    if row['source_span_state']=='extraction_failed':return '추출 검증 실패'
    if row['source_span_state']!='exact_boundary':return 'Source span 누락·경계 차이'
    if row['inventory_status']!='success':return 'Inventory 생성 실패'
    if row['R_target_membership']!='exact':return 'R target exact membership 없음'
    if row['stem_alignment_failed']:return '정렬 출력 검증 실패'
    if not row['edits']:return '유효 처리·치환 미적용'
    return '편집 적용 후에도 오답'


def batch_seconds(rows):
    batch={}
    for row in rows:
        value=row['batch_runtime_ms']
        if row['batch_id'] in batch and batch[row['batch_id']]!=value:raise ValueError('Inconsistent batch runtime')
        batch[row['batch_id']]=value
    return sum(batch.values())/1000


def estimate_eta(rates,images,sources,pairs,baseline_overhead_seconds=600):
    inventory=images*rates['inventory_seconds_per_image'];extract=sources*rates['stem_extract_seconds_per_source']
    align=pairs*rates['stem_align_seconds_per_pair'];stem=pairs*rates['stem_infer_seconds_per_pair'];anchor=pairs*rates['O_infer_seconds_per_pair']
    full=pairs*rates['full_gui_seconds_per_pair'];hybrid=pairs*rates['hybrid_infer_seconds_per_pair']
    stem_only=inventory+extract+align+stem+anchor+baseline_overhead_seconds
    both=stem_only+full+hybrid
    all_grid=(images*rates['full_grid_inventory_wall_seconds_per_image']+sources*rates['full_grid_extract_wall_seconds_per_source']+
              sources*rates['full_grid_stem_extract_wall_seconds_per_source']+pairs*rates['full_grid_rewrite_wall_seconds_per_pair']+
              pairs*rates['full_grid_infer_seconds_per_pair']+stem+baseline_overhead_seconds)
    return {'new_images':images,'new_sources':sources,'new_pairs':pairs,'estimates_only':True,
        'stem_only_plus_O':{'prediction_rows':pairs*2,'hours':stem_only/3600,'planning_hours_plus25percent':stem_only/3600*1.25},
        'stem_and_hybrid_plus_O':{'prediction_rows':pairs*3,'hours':both/3600,'planning_hours_plus25percent':both/3600*1.25},
        'all_eight_v2_conditions_plus_stem_and_O':{'prediction_rows':pairs*10,'hours':all_grid/3600,'planning_hours_plus25percent':all_grid/3600*1.25}}


def collect():
    paths={}
    def use(path):paths[str(path.relative_to(REPO))]=hashlib.sha256(path.read_bytes()).hexdigest();return path
    def read(path):return [json.loads(l) for l in use(path).read_text().splitlines() if l.strip()]
    use(Path(__file__).resolve())
    run=ROOT/'artifacts/two_stage_v2_hybrid';work=run/'screen';stem_root=ROOT/'artifacts/stem_only_gui_screen_v1'
    parent=json.loads(use(run/'contract.json').read_text());done=json.loads(use(work/'COMPLETE.json').read_text());sd=json.loads(use(stem_root/'COMPLETE.json').read_text())
    if done['execution_mode']!='gpu' or sd['execution_mode']!='gpu':raise ValueError('Real completed GPU runs required')
    for filename,sha in parent['source_hashes'].items():
        if hashlib.sha256(use(REPO/filename).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen execution code changed')
    original=unique(read(work/'inputs.jsonl'),lambda r:r['pair_id']);labels=unique(read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'),lambda r:r['pair_id'])
    if digest(labels)!=parent['base_data_contract']['labels']:raise ValueError('Labels changed')
    ids=sorted(p for p in original if labels[p]['split']=='main' and p!=EXCLUDED)
    stem=unique(read(stem_root/'rewritten.jsonl'),lambda r:r['pair_id']);sp=unique(read(Path(sd['predictions'])/'predictions.jsonl'),lambda r:r['pair_id'])
    hybrid=unique(read(Path(done['rewrite'])/'TS_QSEL_OFULL_GUI_AUTO.jsonl'),lambda r:r['pair_id'])
    inventory=unique(read(Path(done['inventory'])/'inventories.jsonl'),lambda r:r['image_sha256'])
    current=unique(read(Path(done['predictions'])/'predictions.jsonl'),lambda r:(r['pair_id'],r['condition']))
    olddir=REL/'results/rstem_ropts_20261110/qwen3/raw';oldcontract=json.loads(use(olddir/'run_contract.json').read_text())
    lock=json.loads(use(REL/'rstem_ropts_inputs/input_lock.json').read_text());mixed_path=REL/'rstem_ropts_inputs/mixed_conditions.jsonl'
    if hashlib.sha256(use(mixed_path).read_bytes()).hexdigest()!=oldcontract['mixed_inputs_sha256'] or oldcontract['mixed_inputs_sha256']!=lock['generated_sha256']['mixed_conditions.jsonl']:raise ValueError('R_stem input lock mismatch')
    mapping_path=REL/'data/rel_all_366/reference_mappings.jsonl'
    if hashlib.sha256(use(mapping_path).read_bytes()).hexdigest()!=lock['reference_mappings_sha256']:raise ValueError('Parallel source/target mapping lock mismatch')
    dataset_lock=json.loads(use(REL/'dataset_lock.json').read_text());conditions_path=REL/'data/rel_all_366/conditions_4lang.jsonl'
    if hashlib.sha256(use(conditions_path).read_bytes()).hexdigest()!=dataset_lock['conditions_sha256'] or oldcontract['dataset_sha256']!=dataset_lock['conditions_sha256']:raise ValueError('Dataset lock mismatch')
    expected=parent['config']['downstream']
    if oldcontract['model_config']!=expected['model_config'] or oldcontract['system_prompt']!=expected['system_prompt']:raise ValueError('R_stem model/system contract mismatch')
    mixed=unique([r for r in read(mixed_path) if r['pair_id'] in ids and r['condition']=='R_stem'],lambda r:r['pair_id'])
    with gzip.open(use(olddir/'predictions.jsonl.gz'),'rt') as f:
        old=unique([r for r in map(json.loads,f) if r['pair_id'] in ids],lambda r:(r['pair_id'],r['condition']))
    if set(old)!={(p,c) for p in ids for c in ('O','R_stem','R_opts','R')}:raise ValueError('Missing paired historical predictions')
    maps={r['parallel_id']:r['spans'] for r in read(mapping_path)}
    with use(REL/'artifacts/new_models_expA_20261115/translation/work/mapping_audit_review.csv').open(encoding='utf-8-sig') as f:
        audit={(r['parallel_id'],r['ref_id']):r for r in csv.DictReader(f)}
    values={name:{} for name in ('O_current','O_Rstem_run','R_stem','R_opts','R','Stem-only','Hybrid')};pair_records=[]
    for pid in ids:
        o=original[pid];mapping=maps[o['parallel_id']];gold=mapping[o['source_language']]['question_stem'];targets={r['ref_id']:r['text'] for r in mapping[o['gui_language']]['question_stem']}
        reference=mixed[pid];edits=[{**g,'field':'question_stem','span_id':g['ref_id'],'replacement':targets[g['ref_id']]} for g in gold]
        reconstructed=apply_edits(o,edits)
        if reference['question_stem']!=reconstructed['question_stem'] or reference['options']!=o['options'] or reference['image_sha256']!=o['image_sha256'] or reference['image_path']!=o['image_path'] or reference['gold_answer']!=labels[pid]['gold_answer']:raise ValueError('R_stem manipulation scope/identity differs')
        if reference['query_language']!=o['source_language'] or reference['gui_language']!=o['gui_language']:raise ValueError('R_stem language mismatch')
        for condition in ('O','R_stem','R_opts','R'):
            row=old[pid,condition]
            if row['experiment_fingerprint']!=oldcontract['experiment_fingerprint'] or row['gold_answer']!=labels[pid]['gold_answer'] or row['parallel_id']!=o['parallel_id']:raise ValueError('Mixed historical run')
            if parse_label(row['generated_text'])!=row['parsed_generated_label']:raise ValueError('Historical raw parser mismatch')
            key='O_Rstem_run' if condition=='O' else condition
            values[key][pid]=int(row['status']=='success' and row['parsed_generated_label']==labels[pid]['gold_answer'])
        for key,row in [('O_current',current[pid,'O']),('Hybrid',current[pid,'TS_QSEL_OFULL_GUI_AUTO']),('Stem-only',sp[pid])]:
            if row['execution_mode']!='gpu' or parse_label(row['generated_text'])!=row['parsed_generated_label']:raise ValueError('Invalid current prediction')
            values[key][pid]=int(row['status']=='success' and row['parsed_generated_label']==labels[pid]['gold_answer'])
        if stem[pid]['question_stem']!=hybrid[pid]['question_stem'] or stem[pid]['options']!=o['options'] or apply_edits(o,stem[pid]['edits'])['question_stem']!=stem[pid]['question_stem']:raise ValueError('Stem-only/Hybrid composition changed')
        inv=inventory[o['image_sha256']];target_strings=[targets[g['ref_id']] for g in gold]
        a=hybrid[pid];state=source_span_state(gold,a['extracted_referents'])
        target_matched=all(any(e['start']==g['start'] and e['end']==g['end'] and normalize(e['replacement'])==normalize(targets[g['ref_id']]) for e in a['edits']) or (o['question_stem'][g['start']:g['end']]==targets[g['ref_id']] and not a['components']['stem_alignment_failed']) for g in gold)
        row={'pair_id':pid,'parallel_id':o['parallel_id'],'source_language':o['source_language'],'gui_language':o['gui_language'],'image_path':o['image_path'],
             'gold_answer':labels[pid]['gold_answer'],'correct':{key:v[pid] for key,v in values.items()},
             'R_source_referents':[{'text':g['text'],'start':g['start'],'end':g['end']} for g in gold],'R_target_referents':target_strings,
             'source_span_state':state,'inventory_status':inv['status'],'R_target_membership':membership(target_strings,inv['visible_strings'],inv['status']),
             'R_target_selected_or_already_identical':target_matched,'stem_alignment_failed':a['components']['stem_alignment_failed'],
             'automatic_referents':[{'text':x['text'],'start':x['start'],'end':x['end']} for x in a['extracted_referents'] or []],
             'edits':[{'text':e['text'],'replacement':e['replacement']} for e in a['edits']],
             'source_question':render(fields(o)),'R_stem_question':reference['question'],'stem_only_question':stem[pid]['modified_question'],'hybrid_question':a['modified_question'],
             'options_original':o['options'],'options_hybrid':a['options'],
             'changed_option_fields':[k for k in 'ABCD' if o['options'][k]!=a['options'][k]],
             'inventory_strings':inv['visible_strings'],
             'known_mapping_review':[{'ref_id':g['ref_id'],'verdict':audit[o['parallel_id'],g['ref_id']]['verdict'],'bad_langs':audit[o['parallel_id'],g['ref_id']]['bad_langs'],'note':audit[o['parallel_id'],g['ref_id']]['note']} for g in gold if (o['parallel_id'],g['ref_id']) in audit],
             'raw_labels':{'Stem-only':sp[pid]['parsed_generated_label'],'Hybrid':current[pid,'TS_QSEL_OFULL_GUI_AUTO']['parsed_generated_label'],'R_stem':old[pid,'R_stem']['parsed_generated_label']}}
        row['observed_bucket']=observed_bucket(row);pair_records.append(row)
    contrasts={left+' − '+right:paired_bootstrap(values[left],values[right],labels,20261115,10000) for left,right in [('Stem-only','R_stem'),('Stem-only','O_current'),('R_stem','O_Rstem_run'),('Hybrid','Stem-only')]}
    gap=[r for r in pair_records if r['correct']['R_stem'] and not r['correct']['Stem-only']]
    wrong=[r for r in pair_records if not r['correct']['Stem-only']]
    changed=[r for r in pair_records if r['correct']['Hybrid']!=r['correct']['Stem-only']]
    label_changed=[r for r in pair_records if r['raw_labels']['Hybrid']!=r['raw_labels']['Stem-only']]
    inventory_summary=dict(Counter(r['R_target_membership'] for r in pair_records))
    avail=[r for r in pair_records if r['R_target_membership']=='exact']
    # Standalone rates include historical measured call runtime for each unique payload,
    # even when that call was cached within another condition. Do not charge shared Full twice.
    mainrows=[original[p] for p in ids];image_ids={r['image_sha256'] for r in mainrows}
    inv_calls=[a for sha,v in inventory.items() if sha in image_ids for a in v['attempts']]
    extraction=read(Path(done['extract_stem'])/'extractions.jsonl');keys={digest(prompts.extraction_payload(r,stem_only=True)) for r in mainrows}
    extract_calls=[a for r in extraction if r['source_key'] in keys for a in r['attempts']]
    align={a['cache_key']:a for p in ids for a in hybrid[p]['attempts'] if a['component']=='stem_alignment'}
    full=read(Path(done['rewrite'])/'TS_FULL_GUI.jsonl');full_calls={a['cache_key']:a for r in full if r['pair_id'] in ids for a in r['attempts']}
    all_current=list(current.values());stem_pred=list(sp.values())
    stage_costs={stage:json.loads(use(Path(done[stage])/'cost.json').read_text()) for stage in ('inventory','extract','extract_stem','rewrite')}
    rates={'inventory_seconds_per_image':sum(a['runtime_ms'] for a in inv_calls)/1000/len(image_ids),
           'stem_extract_seconds_per_source':sum(a['runtime_ms'] for a in extract_calls)/1000/len(keys),
           'stem_align_seconds_per_pair':sum(a['runtime_ms'] for a in align.values())/1000/len(ids),
           'full_gui_seconds_per_pair':sum(a['runtime_ms'] for a in full_calls.values())/1000/len(ids),
           'stem_infer_seconds_per_pair':batch_seconds(stem_pred)/len(stem_pred),
           'O_infer_seconds_per_pair':batch_seconds([r for r in all_current if r['condition']=='O'])/len(original),
           'hybrid_infer_seconds_per_pair':batch_seconds([r for r in all_current if r['condition']=='TS_QSEL_OFULL_GUI_AUTO'])/len(original),
           'full_grid_inventory_wall_seconds_per_image':stage_costs['inventory']['wall_seconds']/len(inventory),
           'full_grid_extract_wall_seconds_per_source':stage_costs['extract']['wall_seconds']/len(read(Path(done['extract'])/'extractions.jsonl')),
           'full_grid_stem_extract_wall_seconds_per_source':stage_costs['extract_stem']['wall_seconds']/len(extraction),
           'full_grid_rewrite_wall_seconds_per_pair':stage_costs['rewrite']['wall_seconds']/len(original),
           'full_grid_infer_seconds_per_pair':batch_seconds(all_current)/len(original)}
    remaining={}
    for cohort in ('selection','internal_evaluation'):
        rows=read(run/cohort/'inputs.jsonl')
        if (run/cohort/'COMPLETE.json').exists():raise ValueError('ETA assumptions stale: another cohort completed')
        remaining[cohort]={'pairs':len(rows),'images':len({r['image_sha256'] for r in rows}),'sources':len({(r['parallel_id'],r['source_language']) for r in rows}),
                           'items':len({r['parallel_id'] for r in rows})}
    conditions=read(conditions_path);full_mismatch=[r for r in conditions if r['condition']=='O' and r['query_language']!=r['gui_language']]
    missing=[r for r in full_mismatch if r['pair_id'] not in original]
    oldimages={r['image_path'].removeprefix('followup_rel_4lang/') for r in original.values()};oldsources={(r['parallel_id'],r['source_language']) for r in original.values()}
    newimages=len({r['image_path'] for r in missing}-oldimages);newsources=len({(r['parallel_id'],r['query_language']) for r in missing}-oldsources)
    total={key:sum(v[key] for v in remaining.values()) for key in ('pairs','images','sources','items')}
    eta={'device':'current B200 MIG45GB; BF16 SDPA, methodbatch1/downstreambatch3','measured_rates':rates,
        'remaining_development':total,'remaining_by_cohort':remaining,
        'plans':{'selection':estimate_eta(rates,**{k:remaining['selection'][v] for k,v in [('images','images'),('sources','sources'),('pairs','pairs')]},baseline_overhead_seconds=300),
                 'internal_evaluation':estimate_eta(rates,remaining['internal_evaluation']['images'],remaining['internal_evaluation']['sources'],remaining['internal_evaluation']['pairs'],300),
                 'remaining_development':estimate_eta(rates,total['images'],total['sources'],total['pairs']),
                 'full366_additional':estimate_eta(rates,newimages,newsources,len(missing))},
        'full366':{'total_items':366,'total_mismatch_pairs':len(full_mismatch),'already_executed_pairs':len(original),'additional_pairs':len(missing),'additional_image_paths':newimages,'additional_sources':newsources},
        'assumptions':['Rates are measured Screen main averages; mixed pilot+main downstream rates kept condition batches intact.',
                       'Standalone Stem-only plan skips unused option full translation and all-field extraction; needs a small execution adapter, not the present eight-condition default.',
                       'Two-candidate plan shares inventory, stem extraction/alignment, runs GUI Full only to reuse options and discards Full stem; no double charging.',
                       'Ten-condition grid means eight v2 conditions + O + composed Stem-only. Default v2 emits nine; Stem-only downstream is a separate reuse step.',
                       'Model/process overhead allowance5min per remaining cohort; 25percent planning margin is a heuristic, not a confidence interval or guaranteed upper bound.',
                       'No new inference or method changes performed. All366 is a rough compute extrapolation; data/input adapters outside current158 cohort are not prepared.']}
    return {'as_of_utc':datetime.now(timezone.utc).isoformat(),'primary_pairs':len(ids),'pair_ids_sha256':digest(ids),'semantic_items':len({original[p]['parallel_id'] for p in ids}),
        'correct':{name:sum(v.values()) for name,v in values.items()},'contrasts':contrasts,
        'historical_contract':{'path':str(olddir.relative_to(REPO)),'batch_size':oldcontract['batch_size'],'queue_order':oldcontract['queue_order'],'experiment_fingerprint':oldcontract['experiment_fingerprint'],
             'model_and_system_identical':True,'hardware':'historical RTX4090 vs current B200 MIG; batch4 mixed conditions vs batch3 separated conditions',
             'O_label_agreement':sum(old[p,'O']['parsed_generated_label']==current[p,'O']['parsed_generated_label'] for p in ids)},
        'R_gap':{'R_stem_correct_Stem_wrong':len(gap),'R_stem_wrong_Stem_correct':sum(not r['correct']['R_stem'] and r['correct']['Stem-only'] for r in pair_records),
             'observed_buckets':dict(Counter(r['observed_bucket'] for r in gap)),'source_span_states':dict(Counter(r['source_span_state'] for r in gap)),
             'R_target_exact_present':sum(r['R_target_membership']=='exact' for r in gap),'causal_attribution':False,'pairs':gap},
        'all_Stem_wrong':{'n':len(wrong),'observed_buckets':dict(Counter(r['observed_bucket'] for r in wrong))},
        'R_target_inventory':{'all_primary_states':inventory_summary,'available_pairs':len(avail),'available_and_R_target_selected_or_identical':sum(r['R_target_selected_or_already_identical'] for r in avail),
                              'same_R_stem_question_pairs':sum(r['R_stem_question']==r['stem_only_question'] for r in pair_records)},
        'hybrid_vs_stem':{'same_stem_all288':all(stem[p]['question_stem']==hybrid[p]['question_stem'] for p in original),
             'primary_label_differences':len(label_changed),'primary_correctness_differences':len(changed),
             'different_wrong_labels':len(label_changed)-len(changed),'hybrid_recovers':sum(r['correct']['Hybrid']>r['correct']['Stem-only'] for r in changed),
             'hybrid_regresses':sum(r['correct']['Hybrid']<r['correct']['Stem-only'] for r in changed),'pairs':changed},
        'by_gui':{gui:{'n':sum(r['gui_language']==gui for r in pair_records),'correct':{name:sum(r['correct'][name] for r in pair_records if r['gui_language']==gui) for name in values}} for gui in ('en','zh','th','ru')},
        'visual_reviews':VISUAL_REVIEW,'eta':eta,'source_sha256':paths,'new_gpu_inference':False,'analysis_type':'posthoc development diagnostic; no new primary exclusions'}


def esc(s):return str(s).replace('|','\\|').replace('\n',' ')


def markdown(s):
    n=s['primary_pairs'];c=s['contrasts']['Stem-only − R_stem'];gap=s['R_gap'];inv=s['R_target_inventory'];h=s['hybrid_vs_stem']
    out=['# Stem-only: R_stem 대응 진단과 남은 실행 ETA','',f"집계 시각: {s['as_of_utc']}. 기존 raw 결과만 분석했다. 새 GPU 추론·inventory 개선·method 변경은 하지 않았다.",'',
        '**Stem-only의 조작 범위에 맞춘 reference는 R_stem이다.** 같은 Screen20개 item·240쌍에서 Stem-only175정답(72.92%), R_stem185정답(77.08%)이다. 차이는−4.17pp이며95% CI[−11.67,+3.75]pp로0을 포함한다. R 전체80.83%를 Stem-only의 유일한 목표로 놓는 것은 범위를 맞춘 비교가 아니다.','',
        '## 1. 동일 문항·동일 조작 범위 확인','', '| 조건 | Stem | Options | 정답 / 240 | 정확도 |','| --- | --- | --- | ---: | ---: |']
    for name,stem,options in [('O_current','원본','원본'),('Stem-only','자동 선택적','원본'),('R_stem','parallel referent','원본'),('Hybrid','같은 자동 선택적','전체 GUI 번역'),('R','parallel referent','parallel referent'),('R_opts','원본','parallel referent')]:
        k=s['correct'][name];out.append(f'| {name} | {stem} | {options} | {k} | {k/n*100:.2f}% |')
    out+=['','| 대비 | 차이 | Item bootstrap95% CI | 회복 / 회귀 |','| --- | ---: | --- | ---: |']
    for name,r in s['contrasts'].items():out.append(f"| {name} | {r['difference']*100:+.2f}pp | [{r['ci95'][0]*100:+.2f}, {r['ci95'][1]*100:+.2f}] | {r['recovery']} / {r['regression']} |")
    out+=['','R_stem 입력은 고정된 mixed input과 원본 O/annotation을 대조해 stem만 parallel 표현으로 바뀌고 options·이미지·정답이 원본 그대로인지240쌍 전수 검사했다. 기존 Qwen3 R_stem 예측은 이미 있어 재추론하지 않았다. 모델 revision·generation·system은 같지만 과거 RTX4090·batch4·O/R_stem/R_opts/R 혼합 queue와 현재 B200 MIG·batch3·조건별 queue가 다르다.','',
        f"과거 같은240쌍의 O는{s['correct']['O_Rstem_run']}/240(67.92%), 현재 O는{s['correct']['O_current']}/240(67.50%)이며 label은{s['historical_contract']['O_label_agreement']}/240일치했다. 따라서 gap을 전부 method 차이라고 단정하지 않는다. 모든 CI는 semantic item 단위10,000회 bootstrap이다. Stem-only−O CI는 이전 보고서에도 이미 제시됐으며 여기서 누락 없이 다시 표시했다.",'',
        '## 2. R_stem 정답·Stem-only 오답20쌍','',
        f"R_stem이 맞고 Stem-only가 틀린 것은{gap['R_stem_correct_Stem_wrong']}쌍, 반대는{gap['R_stem_wrong_Stem_correct']}쌍이다. 아래는 관찰 상태의 상호 배타적 분류이며 인과 원인이나 GUI 대응 정답 판정이 아니다.",'',
        '| 관찰 상태 | 건수 |','| --- | ---: |']
    for name,count in gap['observed_buckets'].items():out.append(f'| {name} | {count} |')
    out+=['',f"20쌍 중 **{gap['R_target_exact_present']}쌍은 R target 문자열이 이미 inventory에 있었다.** 6쌍의 source 경계 차이 중5쌍은 annotation보다 넓은 span,1쌍은 해당 span 누락이었다. 11쌍은 annotation 경계를 맞췄고 edit도 적용됐지만 다른 inventory 문자열을 골랐다. 이들을 일괄적으로 OCR 실패나 post-grounding reasoning 실패로 부를 수 없다.",'',
        '### 전체240쌍의 R target lexical availability','', '| 상태 | Pair |','| --- | ---: |']
    for name,count in inv['all_primary_states'].items():out.append(f'| {name} | {count} |')
    out+=['',f"Normalized exact membership는{inv['available_pairs']}/240(80%)다. 부재48쌍 중9쌍은 inventory 실패·빈 목록,3쌍은 더 긴 inventory 문자열 안에 R 표현이 들어 있고3쌍은 ellipsis를 제외한 R prefix가 포함된다. 나머지33쌍도 화면을 보지 않고 OCR 누락이라고 판정하지 않는다. R 표현의 exact 부재와 실제 화면 글자 누락은 다른 지표다.",'',
        f"Inventory에 R 표현이 있는192쌍 중 원문 exact span에서 R 표현으로 치환했거나 원래 동일한 경우는{inv['available_and_R_target_selected_or_identical']}쌍, 그렇지 않은 것은{inv['available_pairs']-inv['available_and_R_target_selected_or_identical']}쌍이었다. 이 수치는 source 추출·정렬을 함께 거친 reference 일치율이며, 실제 GUI matching precision을 뜻하지 않는다. 완성 질문이 R_stem과 완전히 같은 경우는{inv['same_R_stem_question_pairs']}쌍이다.",'',
        '### 화면 문자열만 직접 본 세 사례','',
        '- `rel::3/map_6.jpg`, TH: 화면에 `เลือกในแผนที่`가 보이지만 inventory가 구조 repair 후 실패해 빈 목록이다. 실제 visible label을 잃은 사례다.',
        '- `rel::5/forest_2.jpg`, RU: 화면과 inventory에는 `Начинающий плантатор`가 있고 R은 `Начинающий планта...`다. R의 축약 표기 exact match가 없다는 이유로 OCR 누락으로 세면 안 된다.',
        '- `rel::2/map_9.png`, EN: `Avoid Tolls`와 `Avoid Highways`가 모두 화면·inventory에 있다. 자동 method는 후자를, parallel reference는 전자를 쓴 Thai-source 사례가 있다. 기존 `mapping_audit_review.csv`에도 Thai source가 고속도로 회피인데 유료도로 회피에 연결됐다는 mapping_error가 기록돼 있다. 이2개 gap pair를 자동 정렬 오류라고 확정할 수 없다.','',
        '이3장만 수동으로 봤으며 전체 missing48쌍의 screenshot audit를 마친 것은 아니다. 기존 mapping_error를 이유로 이번 주 분석에서 새 pair를 제외하지 않았다. Labels/locks도 수정하지 않았다.','',
        '## 3. Stem-only와 Hybrid: 순증가3개 뒤의 실제 전환','',
        f"실행288쌍에서 두 조건의 stem은 모두 동일하다. Main240쌍에서 Hybrid는 Stem-only의 오답{h['hybrid_recovers']}개를 회복하고 정답{h['hybrid_regresses']}개를 잃었다. 따라서 단순히175→178로만 보는 대신 **22회복·19회귀**를 함께 봐야 한다. 정오가 달라진 것은{h['primary_correctness_differences']}쌍이고, 출력 label이 달라진 것은{h['primary_label_differences']}쌍이다. 나머지{h['different_wrong_labels']}쌍은 서로 다른 오답을 냈다.",'',
        'Hybrid−Stem-only는+1.25pp,95% CI[−7.50,+9.58]pp다. Options 번역의 안정적인 추가 이득이나 불필요함 어느 쪽도 아직 확정하지 않는다. 두 조건의 stem은 동일하지만 options 길이가 달라 batch padding이 달라질 수 있다. 공간 관계 context가 유지되는 장점과 options 의미 보존 문제를 분리해서 봐야 한다.','',
        '| GUI | Stem-only | Hybrid | R_stem |','| --- | ---: | ---: | ---: |']
    for gui,g in s['by_gui'].items():out.append('| '+gui.upper()+' | '+' | '.join(f"{g['correct'][name]}/{g['n']} ({g['correct'][name]/g['n']*100:.2f}%)" for name in ['Stem-only','Hybrid','R_stem'])+' |')
    out+=['','RU에서 Stem-only는43/60, Hybrid는40/60이다. Options 전체 번역을 빼면3개를 회복하지만 O46/60에는 여전히 못 미친다. 언어별 on/off 정책을 새로 만들지는 않았다.','',
        '## 4. 다음 판단','',
        '현재 evidence는 inventory 생성 정확도 개선을 먼저 시작할 근거로 충분하지 않다. R gap20쌍에서 inventory exact 부재는2쌍뿐이고 하나는 R 축약 문제였다. 오히려 inventory 안에서 다른 label을 선택하거나 source span을 넓게 잡은 사례를 먼저 검토하는 것이 직접적이다. 일부 parallel mapping 자체도 문제여서 R을 실제 화면 대응의 절대 정답으로 쓰지 않는다. −4.17pp의 구간이0을 포함한다는 사실도 R_stem과 동등하거나 비열등하다는 검증은 아니다.','',
        '지금은 Stem-only와 Hybrid를 고정해 아직 v2로 평가하지 않은 Selection에서 재확인할 수 있다. 다만 전체158 item은 역사적으로 이미 관찰된 development cohort이고 Internal도 독립적인 최종 confirmatory test가 아니다. 이번 진단에 맞춰 threshold/prompt를 바꾸면 새 개발 버전과 관찰 이력을 기록해야 한다.','',
        '## 5. 나머지 샘플 ETA','',
        '**아래는 현재 B200 MIG45GB, BF16 SDPA, method batch1·VLM batch3에서 측정한 시간에 근거한 추정이다.** 실행을 시작한 것이 아니다. 잔여 development는 Selection20문항240쌍 + Internal118문항1,416쌍 =138문항1,656쌍, 새 image552개·source MCQ552개다. Selection의 사전 제외1쌍은 실행에는 포함하고 primary에서 분리한다.','',
        '| 범위 | Stem-only + O | Stem-only + Hybrid + O | 기존8조건 + Stem-only + O |','| --- | ---: | ---: | ---: |']
    for key,name in [('selection','Selection20'),('internal_evaluation','Internal118'),('remaining_development','나머지138문항 전체'),('full366_additional','전체366문항까지 추가분·단순 외삽')]:
        e=s['eta']['plans'][key]
        out.append('| '+name+' | '+' | '.join(f"약{e[plan]['hours']:.1f}h (여유25%: {e[plan]['planning_hours_plus25percent']:.1f}h)" for plan in ['stem_only_plus_O','stem_and_hybrid_plus_O','all_eight_v2_conditions_plus_stem_and_O'])+' |')
    out+=['','**현재 기본 실행기를 그대로 재개하는 것은 기존8조건+O의 전체 grid**다. Stem-only downstream은 나중에 별도 추가하므로 우측은총10조건 비용이다. 좌측의 최소 실행은 Options Full 호출 자체를 생략하는 작은 실행 adapter가 필요하며 아직 실행 명령을 준비하거나 시작하지 않았다. 현재 Stem-only builder는 완료된 Hybrid stem을 재사용하므로 그대로 end-to-end 단독 실행하면 이 절감분이 자동으로 생기는 것은 아니다. 두 후보 실행은 inventory·stem 추출/정렬을 공유하고 Hybrid용 Full options를1회만 생성하는 계획이다.','',
        '| 나머지138문항 계획 | 추가 VLM 예측 행 |','| --- | ---: |']
    e=s['eta']['plans']['remaining_development']
    for name,key in [('Stem-only + O','stem_only_plus_O'),('Stem-only + Hybrid + O','stem_and_hybrid_plus_O'),('기존8조건 + Stem-only + O','all_eight_v2_conditions_plus_stem_and_O')]:out.append(f"| {name} | {e[key]['prediction_rows']:,} |")
    out+=['','### 시간 산식과 한계','', '```json',json.dumps(s['eta']['measured_rates'],ensure_ascii=False,indent=2),'```','',
        'Inventory는 Screen main80장 중 모든 initial/repair 호출 runtime을 합쳐 image당 평균을 구했다. Stem extraction은 고유 source80개, alignment/Full은 main240쌍에서 payload hash별 호출을 한 번만 셌다. Cache hit도 그 payload를 독립 실행할 때 필요한 측정 runtime으로 한 번 포함해 공유 호출 비용을0으로 오인하지 않았다. VLM 시간은 batch마다 한 번만 합산하고288개 실행 pair로 나눴다. 전체 grid는 기존 Screen 단계별 wall을 scale했다. Cold-load/프로세스·보고서 여유는 remaining cohort당5분으로 별도 더했다.','',
        '25%는 통계적 신뢰구간이나 최대시간 보장이 아니라 일정 여유다. 다른 화면 밀도·텍스트 길이·repair 비율·서버 자원 경합·OOM 중단에 따라 더 걸릴 수 있다. 주로 inventory가 시간을 지배하며 더 넓은 데이터의 latency는 아직 실제 측정하지 않았다. 같은 장비 기준이며 RTX4090 속도로 환산하지 않는다.','',
        f"366문항 전체는12방향 기준4,392pair다. 이미 main240+legacy pilot48=288pair를 처리했으므로 추가는{s['eta']['full366']['additional_pairs']:,}pair, 새 image/source는각{s['eta']['full366']['additional_image_paths']:,}개다. 366−20=346문항×12를 그대로 추가로 세면 이미 처리한pilot48pair를 중복 계산한다. 366 확장은 현재 범위 밖이고 새 입력·분모·어댑터 준비가 필요하므로 위 시간은 compute 외삽만이다.",'',
        '재현: `.venv/bin/python followup_rel_4lang/method_dev/scripts/diagnose_stem_only.py`. [집계·원시 대응 snapshot](../artifacts/stem_only_diagnostic_snapshot.json). 기존 결과를 재추론하거나 수정하지 않는다.','',
        '## 부록: R_stem 정답·Stem-only 오답20쌍','', '| Pair | 관찰 상태 | R target | 실제 치환 |','| --- | --- | --- | --- |']
    for r in gap['pairs']:out.append('| '+r['pair_id']+' | '+r['observed_bucket']+' | '+esc('; '.join(r['R_target_referents']))+' | '+esc('; '.join(e['text']+' → '+e['replacement'] for e in r['edits']) or '없음')+' |')
    out+=['','## 부록: Hybrid와 Stem-only 정오가 다른41쌍','',
        '원문·변환 MCQ와 모든 options의 before/after는 snapshot에 있다. 아래는 실제 전환을 놓치지 않기 위한 목록이다. 의미 오류로 자동 판정한 것은 아니다.','',
        '| Pair | Stem-only label | Hybrid label | Gold | Hybrid 기준 전환 |','| --- | --- | --- | --- | --- |']
    for r in h['pairs']:out.append(f"| {r['pair_id']} | {r['raw_labels']['Stem-only']} | {r['raw_labels']['Hybrid']} | {r['gold_answer']} | {'회복' if r['correct']['Hybrid'] else '회귀'} |")
    return '\n'.join(out)+'\n'


def main():
    snapshot=collect();(ROOT/'artifacts/stem_only_diagnostic_snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n')
    report=ROOT/'reports/STEM_ONLY_DIAGNOSTIC_KO.md';report.write_text(markdown(snapshot));print(report)


if __name__=='__main__':main()
