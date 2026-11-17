"""Read-only analysis of completed frozen overnight runs. No model loading/inference."""
import hashlib
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

REPO=Path(__file__).resolve().parents[3]
ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(REPO/'01_code/src'),str(REPO),str(Path(__file__).parent)]
from run_stem_only_gui import read,write,unique
from run_overnight_two import latest,COHORTS,METHODS
from report_source_copy_rewrite import audit
from compare_end_to_end import batch_share,call_map,call_seconds
from reference_comparison import load_references
from search_pipeline import paired_bootstrap,EXCLUDED
from mpr_crosslocale.methods.selective_alignment.schemas import digest,fields,render
from mpr_crosslocale.inference.answer_parser import parse_label
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits


def main():
    output=ROOT/'artifacts/overnight_two_v1';captures={}
    def use(path):
        captures[str(path.relative_to(REPO))]=hashlib.sha256(path.read_bytes()).hexdigest();return path
    def load(path):return json.loads(use(path).read_text())
    def rows(path):return read(use(path))
    use(Path(__file__))
    c=load(output/'contract.json');done=load(output/'COMPLETE.json')
    if done['execution_mode']!='gpu' or done['contract_sha256']!=digest(c):raise ValueError('Run incomplete or contract changed')
    for filename,sha in c['source_sha256'].items():
        if hashlib.sha256((REPO/filename).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen source changed: '+filename)
    labels=unique(rows(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels)!=c['labels_sha256']:raise ValueError('Labels changed')
    annotated=rows(ROOT/'artifacts/dataset_audit/oracle_spans_DIAGNOSTIC_ONLY.jsonl')
    identity=load(ROOT/'artifacts/search_pipeline_v1/data_contract.json')
    if digest(annotated)!=identity['oracle']:raise ValueError('Diagnostic source annotation changed')
    annotations=unique(annotated)
    originals={};transformed={};predictions={};outcomes={};methods={};costs={};record_audits={};rawtable=[]
    logical_keys={};new_keys={}
    for cohort in COHORTS:
        originals[cohort]=unique(rows(output/cohort/'direct/inputs.jsonl'))
        ids=sorted(p for p in originals[cohort] if p!=EXCLUDED)
        methods[cohort]={};costs[cohort]={};transformed[cohort]={};predictions[cohort]={};outcomes[cohort]={};record_audits[cohort]={}
        for method in METHODS:
            work=output/cohort/method
            contract=load(work/'contract.json')
            if digest(list(originals[cohort].values()))!=contract['inputs_sha256']:raise ValueError('Input hash differs')
            if unique(rows(work/'inputs.jsonl'))!=originals[cohort]:raise ValueError('Methods have different inputs')
            rewrite=unique(rows(latest(work,'rewrite')/'rewritten.jsonl'))
            pp=rows(latest(work,'infer')/'evaluation/predictions.jsonl');pred=unique(pp)
            if set(rewrite)!=set(pred) or set(pred)!=set(originals[cohort]):raise ValueError('Incomplete paired output')
            for p in pred:
                rr=rewrite[p];before=originals[cohort][p]
                if rr['execution_mode']!='gpu' or pred[p]['execution_mode']!='gpu' or pred[p]['condition']!=METHODS[method]:raise ValueError('Unexpected condition/mode')
                if parse_label(pred[p]['generated_text'])!=pred[p]['parsed_generated_label']:raise ValueError('Parser differs')
                for key in ('parallel_id','source_language','gui_language','image_path','image_sha256','option_order'):
                    if rr[key]!=before[key]:raise ValueError('Pair linkage changed')
                if rr['modified_question']!=render(fields(rr)):raise ValueError('Rendered MCQ differs')
                if method=='stem':
                    if rr['options']!=before['options'] or any(e['field']!='question_stem' for e in rr['edits']):raise ValueError('Stem condition changed options')
                    if apply_edits(before,rr['edits'])!=fields(rr):raise ValueError('Stem context changed outside edits')
            transformed[cohort][method]=rewrite;predictions[cohort][method]=pred
            value={p:int(pred[p]['status']=='success' and pred[p]['parsed_generated_label']==labels[p]['gold_answer']) for p in ids}
            outcomes[cohort][method]=value
            audits=audit(rewrite,originals[cohort],annotations,ids);record_audits[cohort][method]=audits
            flags={a['pair_id']:a for a in audits}
            result={'n':len(ids),'correct':sum(value.values()),'status':dict(Counter(rewrite[p]['status'] for p in ids)),
                'fallback_reasons':dict(Counter(e for p in ids if rewrite[p]['status']=='fallback_original' for e in rewrite[p]['errors'])),
                'changed':sum(fields(rewrite[p])!=fields(originals[cohort][p]) for p in ids),
                'changed_stem':sum(rewrite[p]['question_stem']!=originals[cohort][p]['question_stem'] for p in ids),
                'changed_options':sum(rewrite[p]['options']!=originals[cohort][p]['options'] for p in ids),
                'context_flagged':sum(not a['format_compatible'] for a in audits),'digit_changed':sum(bool(a['digit_changed_fields']) for a in audits),
                'duplicate_options':sum(a['new_duplicate_options'] for a in audits),
                'wrong_unchanged':sum(not value[p] and fields(rewrite[p])==fields(originals[cohort][p]) for p in ids),
                'wrong_after_change':sum(not value[p] and fields(rewrite[p])!=fields(originals[cohort][p]) for p in ids),
                'wrong_with_context_flag':sum(not value[p] and not flags[p]['format_compatible'] for p in ids)}
            if method=='stem':
                inv=rows(latest(work,'inventory')/'inventories.jsonl');ext=rows(latest(work,'extract_stem')/'extractions.jsonl')
                result['inventory']={'unique_images':len(inv),'failed':sum(x['status']!='success' for x in inv),
                    'repairs':sum(len(x['attempts'])>1 for x in inv),'failed_affected_primary_pairs':sum(rewrite[p]['inventory_status']!='success' for p in ids)}
                result['extraction']={'unique_stems':len(ext),'failed':sum(x['status']!='success' for x in ext),
                    'repairs':sum(len(x['attempts'])>1 for x in ext),'no_referents':sum(x['referents']==[] for x in ext)}
                gold=found=matched=0
                for p in ids:
                    g={(s['start'],s['end']) for s in annotations[p]['referents'] if s['field']=='question_stem'}
                    f={(s['start'],s['end']) for s in rewrite[p]['extracted_referents'] or []}
                    gold+=len(g);found+=len(f);matched+=len(g&f)
                precision=matched/found if found else 0;recall=matched/gold if gold else 0
                result['extraction']['pair_weighted_exact_span']={'gold':gold,'predicted':found,'matched':matched,'precision':precision,'recall':recall,'f1':2*precision*recall/(precision+recall) if precision+recall else 0,
                    'scope':'source stem only; pair-weighted diagnostic, same source repeats across target GUI languages; includes failures as no predicted spans'}
            methods[cohort][method]=result
            stage_cost={};stages=('rewrite',) if method=='direct' else ('inventory','extract_stem','rewrite')
            for stage in stages:
                folder=latest(work,stage);calls=load(folder/'calls.json');logical={x['cache_key']:x for x in calls}
                for key,x in logical.items():
                    logical_keys[key]=x
                    if not x['cache_hit']:new_keys[key]=x
                stage_cost[stage]={'calls':len(calls),'unique_calls':len(logical),'cache_hits':sum(x['cache_hit'] for x in calls),
                    'repairs':sum('repair' in x['stage'] for x in calls),
                    'output_cap_hits':sum(x['output_tokens']==x['generation']['max_new_tokens'] for x in calls),
                    'logical_seconds':call_seconds(logical),'new_seconds':sum(x['runtime_ms'] for x in logical.values() if not x['cache_hit'])/1000,
                    'wall_seconds':load(folder/'cost.json')['wall_seconds'],
                    'peak_reserved_gib':max(x['peak_reserved_bytes'] for x in calls)/2**30 if calls else 0}
            logical_time=batch_share(pp,lambda r:True)['seconds']
            newtime=batch_share([{**r,'batch_runtime_ms':r['new_batch_runtime_ms']} for r in pp],lambda r:True)['seconds']
            info=load(latest(work,'infer')/'evaluation/cost.json')
            stage_cost['infer']={**info,'logical_seconds':logical_time,'new_seconds':newtime,'peak_reserved_gib':max(x['peak_reserved_bytes'] for x in pp)/2**30}
            costs[cohort][method]={'stages':stage_cost,'logical_seconds':sum(s['logical_seconds'] for s in stage_cost.values()),
                'new_seconds':sum(s['new_seconds'] for s in stage_cost.values()),'stage_wall_seconds':sum(s['wall_seconds'] for s in stage_cost.values()),
                'scope':'full executed cohort, includes the one pre-excluded pair in Selection; stage wall includes loads but excludes some worker startup/shutdown'}
        old=ROOT/'artifacts/search_pipeline_v1/jobs'/cohort/'pred_fixed_contrastive_GUI_EXACT/attempt_0001'
        oc=load(old/'contract.json')
        trial=old.parent.parent/'fixed_contrastive_GUI_EXACT/attempt_0001'
        tc=load(trial/'contract.json')
        from infer_search_trial import build_queue
        oldqueue=build_queue(rows(trial/'rewritten.jsonl'),originals[cohort],labels)
        if digest(tc)!=oc['trial_contract_sha256'] or tc['input_sha256']!=digest(list(originals[cohort].values())) or digest(oldqueue)!=oc['input_sha256']:
            raise ValueError('Historical O original input or full-queue checksum differs')
        if not (old/'COMPLETE').exists() or oc['model_config']!=c['config']['downstream']['model_config'] or oc['system_prompt']!=c['config']['downstream']['system_prompt'] or oc['batch_size']!=3 or oc['labels_sha256']!=c['labels_sha256']:
            raise ValueError('Prior B200 O contract differs')
        op=unique([x for x in rows(old/'predictions.jsonl') if x['condition']=='O'])
        if set(op)!=set(originals[cohort]):raise ValueError('B200 O pair coverage differs')
        outcomes[cohort]['O_B200']={p:int(op[p]['status']=='success' and op[p]['parsed_generated_label']==labels[p]['gold_answer']) for p in ids}
    wanted={p:labels[p] for oo in originals.values() for p in oo}
    refs,metadata,_=load_references(REPO,wanted,originals,use,c['config']['downstream']['model_config'],c['config']['historical_baseline_contract_sha256'])
    # Scope-matched parallel reference: only stem referents changed, options original.
    mixed_path=ROOT.parent/'rstem_ropts_inputs/mixed_conditions.jsonl'
    mixed_lock=load(ROOT.parent/'rstem_ropts_inputs/input_lock.json')
    rst_dir=ROOT.parent/'results/rstem_ropts_20261110/qwen3/raw'
    rst_contract=load(rst_dir/'run_contract.json')
    if hashlib.sha256(use(mixed_path).read_bytes()).hexdigest()!=rst_contract['mixed_inputs_sha256'] or rst_contract['mixed_inputs_sha256']!=mixed_lock['generated_sha256']['mixed_conditions.jsonl']:
        raise ValueError('R_stem input lock differs')
    if rst_contract['model_config']!=c['config']['downstream']['model_config'] or rst_contract['system_prompt']!=c['config']['downstream']['system_prompt']:
        raise ValueError('R_stem model/system differs')
    mixed=unique([x for x in read(mixed_path) if x['pair_id'] in wanted and x['condition']=='R_stem'])
    mapping_path=ROOT.parent/'data/rel_all_366/reference_mappings.jsonl'
    if hashlib.sha256(use(mapping_path).read_bytes()).hexdigest()!=mixed_lock['reference_mappings_sha256']:raise ValueError('R_stem parallel mapping lock differs')
    mappings={x['parallel_id']:x['spans'] for x in read(mapping_path)}
    with gzip.open(use(rst_dir/'predictions.jsonl.gz'),'rt') as f:
        rst_preds=unique([x for x in map(json.loads,f) if x['pair_id'] in wanted and x['condition']=='R_stem'])
    flat_original={p:x for oo in originals.values() for p,x in oo.items()}
    if set(mixed)!=set(wanted) or set(rst_preds)!=set(wanted):raise ValueError('R_stem pair coverage incomplete')
    for p,row in mixed.items():
        before=flat_original[p];mp=mappings[before['parallel_id']]
        gold=mp[before['source_language']]['question_stem'];targets={s['ref_id']:s['text'] for s in mp[before['gui_language']]['question_stem']}
        changed=apply_edits(before,[{**s,'field':'question_stem','span_id':s['ref_id'],'replacement':targets[s['ref_id']]} for s in gold])
        if row['question_stem']!=changed['question_stem'] or row['options']!=before['options'] or row['image_sha256']!=before['image_sha256'] or row['image_path']!=before['image_path'] or row['gold_answer']!=labels[p]['gold_answer']:
            raise ValueError('R_stem manipulation scope differs')
        if row['question']!=render(changed):raise ValueError('R_stem actual prompt text differs from reconstructed fields')
        pp=rst_preds[p]
        if pp['experiment_fingerprint']!=rst_contract['experiment_fingerprint'] or pp['gold_answer']!=labels[p]['gold_answer'] or pp['parallel_id']!=before['parallel_id'] or parse_label(pp['generated_text'])!=pp['parsed_generated_label']:
            raise ValueError('Invalid R_stem historical prediction')
    metadata['R_stem']={'path':str(rst_dir.relative_to(REPO)),'batch_size':rst_contract['batch_size'],
        'queue_order':rst_contract['queue_order'],'experiment_fingerprint':rst_contract['experiment_fingerprint'],
        'definition':'parallel referents in stem only; original options; old mixed-condition RTX4090 run; not screenshot exact-label oracle'}
    for cohort in COHORTS:
        ids=sorted(outcomes[cohort]['direct'])
        for name in ('O_EXP_A','T_REF','R_REF','F_REF'):
            outcomes[cohort][name]={p:int(refs[name][p]['status']=='success' and refs[name][p]['parsed_generated_label']==labels[p]['gold_answer']) for p in ids}
        outcomes[cohort]['R_STEM']={p:int(rst_preds[p]['status']=='success' and rst_preds[p]['parsed_generated_label']==labels[p]['gold_answer']) for p in ids}
        from diagnose_stem_only import membership,source_span_state
        inventories={x['image_sha256']:x for x in rows(latest(output/cohort/'stem','inventory')/'inventories.jsonl')}
        gap=[p for p in ids if outcomes[cohort]['R_STEM'][p] and not outcomes[cohort]['stem'][p]]
        buckets=Counter();coverage=Counter();target_presence=Counter()
        for p in gap:
            rr=transformed[cohort]['stem'][p];before=originals[cohort][p]
            if rr['extracted_referents'] is None:bucket='source 추출 실패'
            elif rr['inventory_status']!='success':bucket='inventory 생성 실패'
            elif rr['status']=='fallback_original':bucket='교체 출력 검증 실패'
            elif fields(rr)==fields(before):bucket='유효 처리·원문 유지'
            else:bucket='치환 후에도 오답'
            buckets[bucket]+=1
            coverage[source_span_state([s for s in annotations[p]['referents'] if s['field']=='question_stem'],rr['extracted_referents'])]+=1
            mp=mappings[before['parallel_id']][before['gui_language']]['question_stem']
            inv=inventories[before['image_sha256']]
            target_presence[membership([s['text'] for s in mp],inv['visible_strings'],inv['status']) if mp else 'no_annotated_stem_reference']+=1
        methods[cohort]['stem']['R_stem_gap']={'R_stem_correct_method_wrong':len(gap),'exclusive_observed_state':dict(buckets),
            'source_span_state':dict(coverage),'R_target_inventory_membership':dict(target_presence),
            'all_pairs_identical_reference_question':sum(transformed[cohort]['stem'][p]['modified_question']==mixed[p]['question'] for p in ids),
            'gap_identical_reference_question':sum(transformed[cohort]['stem'][p]['modified_question']==mixed[p]['question'] for p in gap),
            'causal_attribution':False}
    outcomes['remaining_all']={key:{p:x for cohort in COHORTS for p,x in outcomes[cohort][key].items()} for key in outcomes[COHORTS[0]]}
    summary={}
    for cohort,v in outcomes.items():
        ids=sorted(v['direct']);groups={}
        for axis in ('gui_language','source_language'):
            groups[axis]={lang:{'n':sum(p.rsplit('::',2)[1 if axis=='source_language' else 2]==lang for p in ids),
                'correct':{k:sum(x[p] for p in ids if p.rsplit('::',2)[1 if axis=='source_language' else 2]==lang) for k,x in v.items()}} for lang in ('en','zh','th','ru')}
        summary[cohort]={'n':len(ids),'items':len({labels[p]['parallel_id'] for p in ids}),'correct':{k:sum(x.values()) for k,x in v.items()},'by_language':groups,
            'by_pair':{src+'→'+gui:{'n':sum(p.endswith('::'+src+'::'+gui) for p in ids),
                'correct':{k:sum(x[p] for p in ids if p.endswith('::'+src+'::'+gui)) for k,x in v.items()}} for src in ('en','zh','th','ru') for gui in ('en','zh','th','ru') if src!=gui},
            'contrasts':{m:{ref:paired_bootstrap(v[m],v[ref],labels,20261115,10000) for ref in ('O_B200','T_REF','R_REF','F_REF','R_STEM') if ref!=m} for m in METHODS},
            'stem_minus_direct':paired_bootstrap(v['stem'],v['direct'],labels,20261115,10000)}
    automated=load(output/'results.json')
    for cohort in COHORTS:
        if automated['cohorts'][cohort]['n']!=summary[cohort]['n'] or automated['cohorts'][cohort]['correct']!={k:summary[cohort]['correct'][k] for k in METHODS}:
            raise ValueError('Independent aggregate differs from completed runner report')
    snapshot={'development_only':True,'executed_pairs_per_method':1656,'primary_pairs_per_method':1655,'summary':summary,'methods':methods,'costs':costs,
        'wall_seconds':done['wall_seconds'],'config':c['config'],'direct_config':c['direct_config'],'contract_sha256':digest(c),'prompt_sha256':c['prompt_sha256'],
        'references':metadata,'raw_and_source_sha256':captures}
    write(ROOT/'artifacts/overnight_two_results_snapshot.json',snapshot)
    titles={'direct':'이미지 직접 rewrite','stem':'Stem-only GUI','O_B200':'O · 기존 B200','O_EXP_A':'O · ExpA','T_REF':'T_REF','R_REF':'R_REF','F_REF':'F_REF','R_STEM':'R_stem · 범위 일치 reference'}
    lines=['# 고정 두 방법의 잔여 개발 집합 실험 결과','',
        '**두 조건 모두 완료됐다.** 남은138개 semantic item·각1,656 mismatch pair를 실행했고 사전 제외1쌍을 적용한1,655쌍을 주 분석했다. 실제 전체 실행은 '+f"{done['wall_seconds']/3600:.2f}시간({done['wall_seconds']/60:.2f}분)이다.",'',
        '**현재 판단:** Stem-only는 Selection74.48%, Internal74.08%로 직접 rewrite보다 두 집합 모두 높은 점추정을 보였다. Internal의 O 대비 차이는+3.67pp이고 탐색95% CI는[+1.20,+6.07]pp다. 그러나 두 자동 방법 간 차이의 CI는0을 조금 포함하므로 Stem-only의 우월성이나 직접 rewrite의 동등성을 확정하지 않는다. 직접 rewrite의 계산 구간 비용은 Stem-only보다 약47% 적어 비용 비교 후보로 의미가 있다.','',
        '## 무엇을 비교했는가','',
        '**이미지 직접 rewrite:** Qwen3-VL-8B가 screenshot과 원본 stem/A-D를 보고 GUI 이름만 바꾼 완성형 MCQ를 반환한다. 원문 복사를 강조한 프롬프트를 Screen 이후 고정했다. Inventory·별도 extractor·LM은 없으며 수정된 MCQ를 같은 VLM으로 푼다.','',
        '**Stem-only GUI:** 같은 VLM이 screenshot만 보고 문자열 inventory를 만든다. 고정 Qwen3-8B LM이 원본 stem의 referent를 추출하고, 원본 MCQ 전체와 referent·inventory를 보고 교체 이름을 선택한다. 코드가 stem만 치환하고 options는 원문 그대로 둔다. 마지막에 같은 VLM이 푼다. 불필요한 options 전체 번역은 수행하지 않았다.','',
        '두 조건은 같은 pair·이미지·정답·보기 순서를 사용했다. 다만 변환 모델·이미지 접근·option 처리 범위도 달라 inventory 하나의 순수 인과 효과를 비교하는 실험은 아니다.','',
        '## 같은 범위 정확도','', '| 조건 | Selection · 239쌍 | Internal · 1,416쌍 | 잔여 합계 · 1,655쌍 |','| --- | ---: | ---: | ---: |']
    for name in ('O_B200','O_EXP_A','T_REF','R_STEM','R_REF','F_REF','direct','stem'):
        lines.append('| '+titles[name]+' | '+' | '.join(f"{summary[cohort]['correct'][name]}/{summary[cohort]['n']} ({summary[cohort]['correct'][name]/summary[cohort]['n']:.2%})" for cohort in (*COHORTS,'remaining_all'))+' |')
    lines += ['', 'O_B200는 같은 모델·revision·system·batch3·원본 입력 hash의 이전 B200 실행을 재사용했다. O/T/R/F는 새로 추론하지 않았다. T_REF는 gold source span+Gemma 번역, R_REF는 gold span+parallel 표현, F_REF는 전체 parallel localization이다. R은 실제 화면 exact-label oracle이 아니다. ExpA/ORCF reference는 RTX4090 실행이며 F는 batch4라 실행 조건이 완전히 같은 대조는 아니다.','',
        '**Stem-only에 범위를 맞춘 기준은 R_stem이다.** Stem만 parallel 표현으로 정렬하고 options는 원문으로 남긴 입력을1,656쌍 전수 검증했다. R_stem의 과거 batch4·RTX4090·혼합 조건 큐는 현재 batch3·B200·조건별 큐와 다르다. 전체 R과의 격차에는 options 정렬 유무도 포함되므로 그 전부를 자동 stem matching의 실패로 해석하지 않는다.','',
        '## Paired 차이와 불확실성','', '| 집합 | 비교 | 차이 | 95% item bootstrap CI | 회복/회귀 |','| --- | --- | ---: | --- | ---: |']
    for cohort,ss in summary.items():
        compares=[('Stem-only − 직접 rewrite',ss['stem_minus_direct'])]
        for method in METHODS:
            compares += [(titles[method]+' − '+titles[ref],ss['contrasts'][method][ref]) for ref in ('O_B200','R_REF')]
        compares += [('Stem-only GUI − R_stem',ss['contrasts']['stem']['R_STEM'])]
        for name,x in compares:
            lines.append(f"| {cohort} | {name} | {x['difference']*100:+.2f}pp | [{x['ci95'][0]*100:+.2f}, {x['ci95'][1]*100:+.2f}] | {x['recovery']}/{x['regression']} |")
    lines += ['', '같은 semantic item의 언어쌍을 묶어10,000회 bootstrap했다. 다중 비교 보정 전 탐색 구간이며 bootstrap은 실행 환경 차이와 반복 개발에 따른 선택 편향을 보정하지 않는다. 158문항 전체가 역사적으로 관찰된 development set이고 Internal도 이전 탐색에서 본 집합이다. 독립 최종 검증으로 기술하지 않는다.','',
        '## 실제 비용','', '| 집합 | 조건 | Inventory VLM | 추출 LM | 정렬 LM / 직접 rewrite VLM | 풀이 VLM | 계산 구간 합계 |','| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for cohort in COHORTS:
        for method in METHODS:
            ss=costs[cohort][method]['stages'];minu=lambda stage:ss.get(stage,{}).get('logical_seconds',0)/60
            lines.append(f"| {cohort} | {titles[method]} | {minu('inventory'):.2f}분 | {minu('extract_stem'):.2f}분 | {minu('rewrite'):.2f}분 | {minu('infer'):.2f}분 | {costs[cohort][method]['logical_seconds']/60:.2f}분 |")
    lines += ['', '비용은 실제 실행 분모240+1,416쌍이다(Selection 사전 제외1쌍 비용도 포함). 계산 구간 합계는 모델 적재를 제외한 호출 시간이며 cached 배치도 원래 시간을 청구해 단독 recipe 비용을 재구성했다. 전체 wall에는 두 조건·모델 적재·worker 시작/종료 등이 포함된다. Raw cost와 snapshot에는 실제 새 계산 및 stage wall을 별도 보존했다.','',
        '예상6.44–7.00시간보다 짧게 끝난 주된 이유는 남은 화면들의 inventory 생성이 Screen보다 빨랐기 때문이다. Internal inventory는472개 이미지에 실제 호출80.50분(이미지당 약10.23초)이었고, Screen 기준은80개에29.56분(약22.17초)이었다. 따라서 이번 시간 차이를 새 최적화나 장비 변경의 효과로 해석하지 않는다.','']
    for method in METHODS:
        logical=sum(costs[cohort][method]['logical_seconds'] for cohort in COHORTS)
        new=sum(costs[cohort][method]['new_seconds'] for cohort in COHORTS)
        wall=sum(costs[cohort][method]['stage_wall_seconds'] for cohort in COHORTS)
        lines.append(f"- {titles[method]}: 계산 구간{logical/60:.2f}분, 실제 새 계산{new/60:.2f}분, stage wall합{wall/60:.2f}분.")
    lines += ['', f"풀이 재사용은 {sum(costs[cohort][method]['stages']['infer']['reused_rows'] for cohort in COHORTS for method in METHODS)}쌍이다. 이미지·프롬프트·순서·설정·환경이 같은 전체 배치만 재사용했다.",'',
        '## 처리 품질과 남은 실패','', '| 집합 | 방법 | 변경 | 원문 유지 | fallback | 문맥 경고 | 숫자 변화 | 새 보기 중복 |','| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for cohort in COHORTS:
        for method in METHODS:
            mm=methods[cohort][method]
            lines.append(f"| {cohort} | {titles[method]} | {mm['changed']}/{mm['n']} | {mm['n']-mm['changed']} | {mm['status'].get('fallback_original',0)} | {mm['context_flagged']} | {mm['digit_changed']} | {mm['duplicate_options']} |")
    lines += ['', '문맥 경고는 생성 후 source annotation 바깥 문자 보존을 검사한 값이며 의미 오류율이 아니다. GT source span은 사후 진단에만 사용했다. Stem-only는 코드로 자동 추출 span 바깥을 보존하더라도 추출 span이 annotation과 다르면 이 검사에서 경고될 수 있다. 올바른 화면 요소를 골랐는지는 별도 문제다.','',
        '| 집합 | Inventory 실패 / 이미지 | Stem 추출 실패 / 고유 stem | 추출 precision / recall / F1 |','| --- | ---: | ---: | --- |']
    for cohort in COHORTS:
        mm=methods[cohort]['stem'];inv=mm['inventory'];ex=mm['extraction'];qq=ex['pair_weighted_exact_span']
        lines.append(f"| {cohort} | {inv['failed']}/{inv['unique_images']} | {ex['failed']}/{ex['unique_stems']} | {qq['precision']:.2%} / {qq['recall']:.2%} / {qq['f1']:.2%} |")
    lines += ['', 'Stem-only fallback103쌍 중93쌍은 최종 LM 출력이 inventory의 verbatim member가 아니어서 거절됐고,9쌍은 source 추출 실패,1쌍은 JSON parsing 실패였다. 이93쌍을 모두 잘못된 의미 대응이라고 판정한 것은 아니다. 단순 표기 차이인지, 없는 이름을 만든 것인지, inventory 누락인지 분해해야 한다.','',
        '### R_stem은 맞고 Stem-only는 틀린 사례','',
        '아래는 우선순위를 둔 관찰 상태 분류이며 단독 오답 원인 판정이 아니다. Source 경계·R target의 inventory 포함 여부도 별도로 저장했다. Parallel reference의 exact 부재는 OCR 누락과 같은 뜻이 아니다.','',
        '| 집합 | R_stem 정답·Stem-only 오답 | 관찰 상태 | 건수 |','| --- | ---: | --- | ---: |']
    for cohort in COHORTS:
        gg=methods[cohort]['stem']['R_stem_gap']
        for name,count in gg['exclusive_observed_state'].items():lines.append(f"| {cohort} | {gg['R_stem_correct_method_wrong']} | {name} | {count} |")
    lines += ['', 'Internal의81쌍 중67쌍은 source stem annotation 경계를 모두 정확히 포함했고,57쌍은 R target 표현이 이미 inventory에 exact로 있었다. 따라서 이 격차를 전부 추출 recall 또는 OCR 실패로 설명할 수 없다. 20쌍의 lexical 미발견은 실제 화면에서의 부재·누락·reference 표현 차이를 수작업으로 나누기 전까지 OCR 오류로 확정하지 않는다.','',
        '| 집합 | 전체 중 R_stem 입력과 완전히 동일 | R_stem 정답·Stem-only 오답 중 입력도 동일 |','| --- | ---: | ---: |']
    for cohort in COHORTS:
        gg=methods[cohort]['stem']['R_stem_gap'];lines.append(f"| {cohort} | {gg['all_pairs_identical_reference_question']} | {gg['gap_identical_reference_question']} |")
    lines += ['', '입력까지 같은데 정오가 다른 사례는 matching 오류로 귀속하지 않는다. 과거·현재의 batch/device/queue 차이도 결과 차이에 기여할 수 있음을 보여준다. 새 inference 없이 기존 원시 문자열과 예측을 대조한 것이다.','']
    lines += ['', '추출 수치는 source stem exact-boundary 진단이다. 동일 source가 GUI 언어별로 반복되는 pair-weighted 값이며, 검증 실패는 예측 span 없음으로 포함한다. Target matching 정답률로 해석하지 않는다.','',
        '## GUI 언어별 결과','', '| 집합 | GUI | N | O_B200 | 직접 rewrite | Stem-only | R_REF |','| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for cohort in COHORTS:
        for lang,g in summary[cohort]['by_language']['gui_language'].items():
            lines.append(f"| {cohort} | {lang.upper()} | {g['n']} | "+' | '.join(f"{g['correct'][key]/g['n']:.2%}" for key in ('O_B200','direct','stem','R_REF'))+' |')
    lines += ['', 'Internal에서 Stem-only의 순증가52개 중39개가 태국어 GUI에서 나왔다. EN은 O와 같고, ZH는6개, RU는7개 순증가했다. 개선이 모든 언어에 동일하게 나타났다고 볼 수 없다.','',
        '언어별 표는 기술적 분해이며 작은 subset의 결과를 보고 언어별 on/off 정책을 새로 만들지 않았다. Source 언어별·language-pair별 및 모든 reference 대비 paired 값은 snapshot/전체 예측 표에 보존한다.','',
        '## 다음 판단','',
        '1. **Stem-only를 현재 주력 후보로 유지한다.** 전체 R과의 격차보다 범위를 맞춘 R_stem 대비 Internal−4.52pp를 우선 본다. Options 전체 번역이나 다른 architecture를 바로 추가할 필요는 없다.',
        '2. **출력 거절과 잘못된 대응을 나눈다.** 93개의 non-member fallback 원시 응답과 R_stem 정답·Stem-only 오답81쌍을 우선 검토한다. 이미 inventory에 있는 이름을 놓치는지, source span이 틀렸는지부터 구분한다.',
        '3. **Inventory 성공률을 lexical 정확도로 오해하지 않는다.** 생성 실패는10/552이미지로 적지만 필요한 label의 coverage는 별개다. 추출 F1이 Internal88.96%인 상황에서 새 NER 모델이나 OCR 모델을 먼저 추가할 근거는 충분하지 않다.',
        '4. **직접 rewrite는 낮은 비용의 비교 후보로 남긴다.** 원문 유지와 잘못된 이름 대응, 문맥/숫자 변화, 보기 중복이 남아 있어 현재 성능을 robust selective alignment의 완성으로 보고하지 않는다.','',
        '## 설정·보존','',
        '평가 및 직접 변환 VLM: Qwen3-VL-8B-Instruct revision `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`. LM: Qwen3-8B revision `47719a242beab8f9aecc40ce3928b034dd5dd559`. BF16·SDPA·seed42·2MP·channels_last_3d, 변환batch1/풀이batch3. 실제 프롬프트와 생성 설정은 calls.json 및 상위 contract.json에 보존했다. 원문 복사 강화 프롬프트는 [Screen 보고서](SOURCE_COPY_REWRITE_RESULTS_KO.md), Stem-only는 [기존 프로토콜](TWO_STAGE_V2_PROTOCOL_KO.md)을 따른다.','',
        'Raw는 `artifacts/overnight_two_v1/`에 유지한다. 기존 실행기·원시 출력·자동 보고서를 바꾸지 않고 사후 보고서와 checksum snapshot을 분리했다. 추가 GPU 추론은 수행하지 않았다.','',
        '```bash','.venv/bin/python followup_rel_4lang/method_dev/scripts/report_overnight_two.py','```','',
        '[전체1,656쌍 예측 표](OVERNIGHT_TWO_CASES_KO.md) · [결과·비용·출처 checksum snapshot](../artifacts/overnight_two_results_snapshot.json)','']
    (ROOT/'reports/OVERNIGHT_TWO_RESULTS_KO.md').write_text('\n'.join(lines).rstrip()+'\n')
    cases=['# 밤샘 실행 전체 pair 예측','','실행 분모1,656쌍. 사전 제외1쌍도 표시하되 주 분석에서는 제외.','',
        '| Cohort | Pair | 주 분석 | GT | O_B200 | 직접 rewrite | Stem-only | T_REF | R_stem | R_REF | F_REF | 직접 상태 | Stem 상태 |','| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for cohort in COHORTS:
        oldpath=ROOT/'artifacts/search_pipeline_v1/jobs'/cohort/'pred_fixed_contrastive_GUI_EXACT/attempt_0001/predictions.jsonl'
        old=unique([x for x in read(oldpath) if x['condition']=='O'])
        for p in sorted(originals[cohort]):
            label=lambda x:str(x['parsed_generated_label'])
            cases.append(f"| {cohort} | `{p}` | {'제외' if p==EXCLUDED else '포함'} | {labels[p]['gold_answer']} | {label(old[p])} | {label(predictions[cohort]['direct'][p])} | {label(predictions[cohort]['stem'][p])} | {label(refs['T_REF'][p])} | {label(rst_preds[p])} | {label(refs['R_REF'][p])} | {label(refs['F_REF'][p])} | {transformed[cohort]['direct'][p]['status']} | {transformed[cohort]['stem'][p]['status']} |")
    (ROOT/'reports/OVERNIGHT_TWO_CASES_KO.md').write_text('\n'.join(cases)+'\n')
    print(json.dumps({'summary':summary,'methods':methods,'wall_hours':done['wall_seconds']/3600},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
