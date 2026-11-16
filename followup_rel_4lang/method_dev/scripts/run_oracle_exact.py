"""Source-span oracle diagnostic for frozen GUI_EXACT. No gold target strings or bbox are loaded."""
import argparse,fcntl,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from collections import Counter
REPO=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent;ROOT=HERE.parent
sys.path[:0]=[str(REPO/'01_code/src'),str(HERE),str(REPO)]
from mpr_crosslocale.methods.selective_alignment.schemas import digest,fields,render,validate_input
from mpr_crosslocale.methods.selective_alignment.search import rewrite
from mpr_crosslocale.inference.run_cross_locale import _build_model_adapter
from mpr_crosslocale.inference.answer_parser import parse_label
from backend import TransformersBackend
from run_search_trial import CachedBackend
from infer_search_trial import build_queue
from search_pipeline import BASELINE,paired_bootstrap

CONDITION='oracle_span_selective'
COHORTS=['screen','selection','internal_evaluation']


def read(path):return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)
def jsonl(path,rows):path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))


def source_refs(row,annotation):
    """Discard parallel reference IDs and derive the SAME IDs/order as automatic extraction."""
    validate_input(row)
    if set(annotation)!={'pair_id','oracle_span','referents'} or annotation['pair_id']!=row['pair_id'] or annotation['oracle_span'] is not True:
        raise ValueError('Expected source-only oracle annotation record')
    allowed={'start','end','text','field','span_id','ref_id'};source=fields(row);refs=[]
    for span in annotation['referents']:
        if set(span)-allowed or not {'start','end','text','field'}<=set(span):raise ValueError('Only source span fields are allowed; no target/answer/bbox')
        field=span['field'];start=span['start'];end=span['end'];text=span['text']
        if field not in source or type(start) is not int or type(end) is not int or not isinstance(text,str) or not 0<=start<end<=len(source[field]) or source[field][start:end]!=text:
            raise ValueError('Oracle source offset/text mismatch')
        positions=[];offset=0
        while (pos:=source[field].find(text,offset))>=0:positions.append(pos);offset=pos+len(text)
        if start not in positions:raise ValueError('Oracle span cannot use existing non-overlapping occurrence convention')
        refs.append({'field':field,'text':text,'start':start,'end':end,'span_id':f'{field}:{start}:{end}',
            'occurrence':positions.index(start),'kind':'label','utf8_start':len(source[field][:start].encode()),'utf8_end':len(source[field][:end].encode())})
    refs.sort(key=lambda r:(r['field'],r['start'],r['end']))
    for a,b in zip(refs,refs[1:]):
        if a['field']==b['field'] and a['end']>b['start']:raise ValueError('Oracle source spans overlap')
    return refs


def prepare(base,work,cohort,mock):
    if not (base/'COMPLETE.json').exists():raise ValueError('Completed automatic base run required')
    fingerprint=json.loads((base/'pipeline_contract.json').read_text())
    for filename,expected in fingerprint['source_hashes'].items():
        if digest((REPO/filename).read_text())!=expected:raise ValueError('Frozen implementation changed: '+filename)
    identity=json.loads((base/'data_contract.json').read_text());rows=[validate_input(r) for r in read(base/'plan'/(cohort+'.jsonl'))]
    manifest=json.loads((base/'plan/manifest.json').read_text())
    if digest(rows)!=manifest['cohorts'][cohort]['inputs_sha256']:raise ValueError('Original cohort changed')
    annotations=read(ROOT/'artifacts/dataset_audit/oracle_spans_DIAGNOSTIC_ONLY.jsonl')
    if digest(annotations)!=identity['oracle']:raise ValueError('Frozen source annotation changed')
    by_pair={r['pair_id']:r for r in annotations}
    if len(by_pair)!=len(annotations):raise ValueError('Duplicate oracle pair IDs')
    summary=json.loads((base/'tables'/cohort/'GUI_EXACT.json').read_text());auto=base/summary['trial'];pred=base/summary['predictions']
    if not all((p/'COMPLETE').exists() for p in [auto,pred]):raise ValueError('Automatic comparison incomplete')
    auto_contract=json.loads((auto/'contract.json').read_text());baseline=json.loads((pred/'contract.json').read_text())
    expected_config=json.loads((base/'models.json').read_text());expected_config['profile_calls']=False
    if auto_contract['config']!=expected_config or baseline['baseline_contract_sha256']!=identity['baseline_contract']:
        raise ValueError('Automatic model/config contract mismatch')
    original_ids={r['pair_id'] for r in rows};auto_rows=read(auto/'rewritten.jsonl')
    if len(auto_rows)!=len(original_ids) or {r['pair_id'] for r in auto_rows}!=original_ids:raise ValueError('Automatic pair set differs')
    inventories={}
    for r in auto_rows:
        if r['inventory'] is None:raise ValueError('Missing frozen inventory')
        sha=r['image_sha256']
        if sha in inventories and inventories[sha]!=r['inventory']:raise ValueError('Inconsistent inventory for same screenshot')
        inventories[sha]=r['inventory']
        if any(ref['kind']!='label' for ref in r['extracted_referents'] or []):raise ValueError('Automatic kind differs; review type intervention before proceeding')
    normalized=[{'pair_id':r['pair_id'],'oracle_span':True,'referents':source_refs(r,by_pair[r['pair_id']])} for r in rows]
    source_groups={}
    for row,spans in zip(rows,normalized,strict=True):
        key=(row['parallel_id'],row['source_language']);value=spans['referents']
        if key in source_groups and source_groups[key]!=value:raise ValueError('Source annotation differs across target GUI pairs')
        source_groups[key]=value
    config=auto_contract['config'];baseline_run=json.loads(BASELINE.read_text())
    if digest(baseline_run)!=identity['baseline_contract']:raise ValueError('Historical evaluation contract changed')
    body={'version':'oracle-source-span-gui-exact-v1','condition':CONDITION,'oracle_span':True,'gold_target_used':False,'cohort':cohort,'mode':'mock' if mock else 'gpu',
        'base_run':str(base.resolve()),'labels_sha256':identity['labels'],'score_labels':baseline_run['score_labels'],
        'only_intervention':'Automatic source referents -> annotated source referents. Translation model/prompt, canonical span IDs, inventory bytes, matcher, fallback and downstream settings unchanged.',
        'inputs_sha256':digest(rows),'source_annotation_sha256':identity['oracle'],'canonical_spans_sha256':digest(normalized),'inventories_sha256':digest(inventories),
        'config':config,'automatic_trial':str(auto),'automatic_predictions':str(pred),'automatic_rewrite_sha256':hashlib.sha256((auto/'rewritten.jsonl').read_bytes()).hexdigest(),
        'automatic_prediction_sha256':hashlib.sha256((pred/'predictions.jsonl').read_bytes()).hexdigest(),'baseline_contract':baseline,
        'runner_sha256':digest(Path(__file__).read_text()),'counts':{'pairs':len(rows),'semantic_items':len({r['parallel_id'] for r in rows}),'source_mcqs':len(source_groups),
            'source_spans_pair_repeated':sum(len(r['referents']) for r in normalized),'unique_images':len(inventories),'inventory_failed':sum(v['status']=='failed' for v in inventories.values())}}
    work.mkdir(parents=True,exist_ok=True);contract=work/'plan.json'
    if contract.exists() and json.loads(contract.read_text())!=body:raise ValueError('Oracle plan/source/config changed; choose a new output root')
    if not contract.exists():
        jsonl(work/'inputs.jsonl',rows);jsonl(work/'oracle_source_spans.jsonl',normalized);write(work/'frozen_inventories.json',inventories);write(contract,body)
    else:
        if digest(read(work/'inputs.jsonl'))!=body['inputs_sha256'] or digest(read(work/'oracle_source_spans.jsonl'))!=body['canonical_spans_sha256'] or digest(json.loads((work/'frozen_inventories.json').read_text()))!=body['inventories_sha256']:raise ValueError('Prepared inputs changed')
    return body


def seed_translation_cache(base,cache):
    """Read-through via symlinks; never modify the old cache or merge per-span translations."""
    cache.mkdir(parents=True,exist_ok=True);count=0
    for source in (base/'cache').glob('*.json'):
        if json.loads(source.read_text()).get('stage')!='translate':continue
        dest=cache/source.name
        if not dest.exists() and not dest.is_symlink():dest.symlink_to(source.resolve());count+=1
    return count


def budget():
    import torch
    if torch.cuda.device_count()!=1:raise RuntimeError('Exactly one visible GPU is required')
    free,_=torch.cuda.mem_get_info()
    if free<40*2**30:raise RuntimeError('Need40GiB free on current45GB MIG before loading a model; no automatic batch/image reduction')
    torch.set_num_threads(3)


def rewrite_stage(work,output,cache,mock):
    plan=json.loads((work/'plan.json').read_text());rows=read(work/'inputs.jsonl');refs={r['pair_id']:r['referents'] for r in read(work/'oracle_source_spans.jsonl')};inventories=json.loads((work/'frozen_inventories.json').read_text())
    if not mock:budget()
    backend=CachedBackend(None if mock else TransformersBackend(plan['config'],REPO),plan['config'],cache,mock)
    output.mkdir(parents=True);start=time.perf_counter();completed=False
    write(output/'contract.json',{'condition':CONDITION,'oracle_span':True,'gold_target_used':False,'execution_mode':'mock' if mock else 'gpu','plan_sha256':digest(plan),'input_sha256':digest(rows),'config':plan['config']})
    try:
        with (output/'rewritten.jsonl').open('w') as f:
            for index,row in enumerate(rows,1):
                result=rewrite(row,'GUI_EXACT',backend,refs[row['pair_id']],inventories[row['image_sha256']]);out=result['output']
                f.write(json.dumps({**row,'question_stem':out['question_stem'],'options':{k:out[k] for k in 'ABCD'},'condition':CONDITION,'oracle_span':True,'gold_target_used':False,
                    'modified_question':render(out),'extracted_referents':refs[row['pair_id']],'inventory':inventories[row['image_sha256']],'edits':result['edits'],
                    'generation_status':result['status'],'details':result['details'],'execution_mode':'mock' if mock else 'gpu'},ensure_ascii=False)+'\n');f.flush()
                if index==1 or index%20==0 or index==len(rows):print(f'ORACLE rewrite {index}/{len(rows)}',flush=True)
        completed=True
    finally:
        write(output/'calls.json',backend.calls);misses=[c for c in backend.calls if not c['cache_hit']]
        write(output/'cost.json',{'execution_mode':'mock' if mock else 'gpu','wall_ms':(time.perf_counter()-start)*1000,'calls':len(backend.calls),'cache_hits':sum(c['cache_hit'] for c in backend.calls),
            'new_runtime_ms':sum(c['runtime_ms'] for c in misses),'new_load_ms':sum(c.get('model_load_ms') or 0 for c in misses),'inventory_calls':sum(c['stage']=='inventory' for c in backend.calls),
            'extraction_calls':sum(c['stage']=='extract' for c in backend.calls),'complete':completed,'note':'Inventory/extractor are not run. Exact full translation payload cache only; shared-span translations are not spliced.'})
    if completed:(output/'COMPLETE').write_text('completed\n')


def infer_stage(work,trial,output,mock):
    from types import SimpleNamespace
    plan=json.loads((work/'plan.json').read_text());rewritten=read(trial/'rewritten.jsonl');originals={r['pair_id']:r for r in read(work/'inputs.jsonl')}
    labels={r['pair_id']:r for r in read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl')}
    queue=[r for r in build_queue(rewritten,originals,labels) if r['condition']==CONDITION]
    if digest(labels)!=plan['labels_sha256']:raise ValueError('Evaluation labels changed')
    meta=json.loads((trial/'contract.json').read_text())
    if not (trial/'COMPLETE').exists() or meta['plan_sha256']!=digest(plan) or meta['execution_mode']!=('mock' if mock else 'gpu'):raise ValueError('Incomplete or mismatched Oracle rewrite')
    if not mock:
        for r in {r['image_path']:r for r in rewritten}.values():
            if hashlib.sha256((REPO/r['image_path']).read_bytes()).hexdigest()!=r['image_sha256']:raise ValueError('Image changed')
    baseline=plan['baseline_contract'];config=baseline['model_config'];batch=baseline['batch_size']
    if not mock:budget()
    adapter=None if mock else _build_model_adapter(SimpleNamespace(attn_implementation=None,device_map='cuda:0'),config)
    if adapter is not None:adapter.max_input_tokens=4096
    output.mkdir(parents=True);write(output/'contract.json',{'oracle_span':True,'execution_mode':'mock' if mock else 'gpu','plan_sha256':digest(plan),'model_config':config,
        'batch_size':batch,'system_prompt':baseline['system_prompt'],'queue_order':'Oracle only; condition-separated, pair_id sorted, same row groups as automatic candidate block',
        'labels_sha256':digest(labels),'max_input_tokens':4096,'score_labels':plan['score_labels'],
        'O_source':'reuse frozen automatic O for comparison, not newly inferred','input_sha256':digest(queue)})
    import torch
    with (output/'predictions.jsonl').open('w') as f:
        for start in range(0,len(queue),batch):
            chunk=queue[start:start+batch];t=time.perf_counter()
            if mock:preds=[SimpleNamespace(raw_output='A',prompt_token_count=0,output_token_count=0) for _ in chunk]
            else:
                torch.cuda.reset_peak_memory_stats();preds=adapter.generate_batch(chunk,config['prompt_profile'],config['generation'],system_prompt=baseline['system_prompt'],score_labels=plan['score_labels'])
            elapsed=(time.perf_counter()-t)*1000
            if len(preds)!=len(chunk):raise ValueError('Lost oracle output')
            for row,pred in zip(chunk,preds,strict=True):
                f.write(json.dumps({'pair_id':row['pair_id'],'parallel_id':row['parallel_id'],'condition':CONDITION,'oracle_span':True,'execution_mode':'mock' if mock else 'gpu',
                    'status':'success','generated_text':pred.raw_output,'parsed_generated_label':parse_label(pred.raw_output),'prompt_tokens':pred.prompt_token_count,'output_tokens':pred.output_token_count,
                    'batch_id':CONDITION+':'+str(start),'batch_size':len(chunk),'batch_runtime_ms':elapsed,'peak_allocated_bytes':None if mock else torch.cuda.max_memory_allocated(),'peak_reserved_bytes':None if mock else torch.cuda.max_memory_reserved()},ensure_ascii=False)+'\n');f.flush()
            if start==0 or (start//batch)%20==0 or start+batch>=len(queue):print(f'ORACLE inference {min(start+batch,len(queue))}/{len(queue)}',flush=True)
    (output/'COMPLETE').write_text('completed\n')


def summarize(work,trial,prediction,mock):
    plan=json.loads((work/'plan.json').read_text());rewritten=read(trial/'rewritten.jsonl');oracle_predictions=read(prediction/'predictions.jsonl')
    if len(oracle_predictions)!=len(rewritten) or {r['pair_id'] for r in oracle_predictions}!={r['pair_id'] for r in rewritten}:raise ValueError('Incomplete oracle prediction set')
    if mock:
        summary={'execution_mode':'mock','empirical':False,'pairs':len(rewritten),'note':'Functionality check only; no accuracy, CI or timing claim.'};write(work/'results.json',summary);(work/'REPORT_KO.md').write_text('# Oracle source-span diagnostic\n\nMOCK 기능 검사 완료. 실측 정확도가 아니다.\n');return
    labels={r['pair_id']:r for r in read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl')}
    if digest(labels)!=plan['labels_sha256']:raise ValueError('Evaluation labels changed')
    if any(r['execution_mode']!='gpu' for r in oracle_predictions):raise ValueError('Mock predictions cannot be reported as empirical')
    automatic=read(Path(plan['automatic_predictions'])/'predictions.jsonl');lookup={(r['pair_id'],r['condition']):r for r in automatic}
    if len(lookup)!=len(automatic):raise ValueError('Duplicate automatic prediction')
    ids={r['pair_id'] for r in rewritten if labels[r['pair_id']]['split']=='main' and r['pair_id']!='rel::5/forest_9.jpg::zh::ru'}
    if not ids:raise ValueError('No main primary pairs')
    oracle={r['pair_id']:r for r in oracle_predictions}
    correct=lambda r,p:int(r.get('status')=='success' and r.get('parsed_generated_label')==labels[p]['gold_answer'])
    values={'Oracle':{p:correct(oracle[p],p) for p in ids},'Automatic':{p:correct(lookup[p,'GUI_EXACT'],p) for p in ids},'O':{p:correct(lookup[p,'O'],p) for p in ids}}
    from reference_comparison import load_references
    base=Path(plan['base_run']);original_cohorts={c:{r['pair_id']:r for r in read(base/'plan'/(c+'.jsonl'))} for c in COHORTS}
    refs,reference_meta,_=load_references(REPO,labels,original_cohorts,lambda path:path,plan['baseline_contract']['model_config'],plan['baseline_contract']['baseline_contract_sha256'])
    for name in ['T_REF','R_REF','F_REF']:
        if not ids<=set(refs[name]):raise ValueError('Historical reference pair set incomplete')
        values[name]={p:correct(refs[name][p],p) for p in ids}
    rewritten_by_id={r['pair_id']:r for r in rewritten}
    original={r['pair_id']:r for r in read(work/'inputs.jsonl')};auto_rewritten={r['pair_id']:r for r in read(Path(plan['automatic_trial'])/'rewritten.jsonl')}
    changed=sum(r['pair_id'] in ids and r['modified_question']!=render(fields(original[r['pair_id']])) for r in rewritten)
    unchanged_transitions=sum(r['pair_id'] in ids and r['modified_question']==auto_rewritten[r['pair_id']]['modified_question'] and oracle[r['pair_id']]['parsed_generated_label']!=lookup[r['pair_id'],'GUI_EXACT']['parsed_generated_label'] for r in rewritten)
    contrasts={key:paired_bootstrap(values['Oracle'],values[key],labels,20261115,10000) for key in ['Automatic','O','T_REF','R_REF','F_REF']}
    summary={'execution_mode':'gpu','diagnostic_only':True,'oracle_span':True,'gold_target_used':False,'primary_pairs':len(ids),'items':len({labels[p]['parallel_id'] for p in ids}),
        'correct':{key:sum(v.values()) for key,v in values.items()},'reference_metadata':reference_meta,'contrasts':contrasts,'changed_pairs':changed,
        'fallback_pairs':sum(r['pair_id'] in ids and r['generation_status']=='fallback_original' for r in rewritten),'prediction_changes_without_question_change':unchanged_transitions,
        'by_gui':{gui:{'n':sum(original[p]['gui_language']==gui for p in ids),'correct':{name:sum(v[p] for p in ids if original[p]['gui_language']==gui) for name,v in values.items()}} for gui in sorted({original[p]['gui_language'] for p in ids})},
        'generation_status':dict(Counter(r['generation_status'] for r in rewritten if r['pair_id'] in ids)),
        'matched_referents':sum(m['decision']=='match' for r in rewritten if r['pair_id'] in ids for m in r['details'].get('matches',[])),
        'edits_applied':sum(len(r['edits']) for r in rewritten if r['pair_id'] in ids),'batch_composition_preserved':True,'accuracy_is_strict_upper_bound':False,'plan_sha256':digest(plan)}
    write(work/'results.json',summary)
    jsonl(work/'paired_outcomes.jsonl',[{'pair_id':p,'parallel_id':labels[p]['parallel_id'],'correct':{name:v[p] for name,v in values.items()},
        'automatic_question':auto_rewritten[p]['modified_question'],'oracle_question':rewritten_by_id[p]['modified_question'],
        'transition':'recovery' if values['Oracle'][p]>values['Automatic'][p] else 'regression' if values['Oracle'][p]<values['Automatic'][p] else 'same'} for p in sorted(ids)])
    n=len(ids);lines=['# Oracle source-span extraction 진단','',f"범위: {plan['cohort']}, {summary['items']}개 item / primary{n}쌍. 실행{len(rewritten)}쌍 전체를 보존했고 pilot과 사전 제외는 primary에서 분리했다.",'',
        '| 조건 | 정답 | 정확도 |','| --- | ---: | ---: |']
    for name in ['O','Automatic','Oracle','T_REF','R_REF','F_REF']:lines.append(f"| {name} | {summary['correct'][name]}/{n} | {summary['correct'][name]/n:.3%} |")
    lines+=['','| 대비 | 차이 | Item bootstrap95% CI | 회복/회귀 |','| --- | ---: | --- | ---: |']
    for name,c in contrasts.items():lines.append(f"| Oracle − {name} | {c['difference']*100:+.3f}pp | [{c['ci95'][0]*100:+.3f}, {c['ci95'][1]*100:+.3f}]pp | {c['recovery']}/{c['regression']} |")
    lines+=['','| GUI | 쌍 수 | O | Automatic | Oracle | T_REF | R_REF | F_REF |','| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for gui,g in summary['by_gui'].items():lines.append('| '+gui+' | '+str(g['n'])+' | '+' | '.join(f"{g['correct'][name]/g['n']:.2%}" for name in ['O','Automatic','Oracle','T_REF','R_REF','F_REF'])+' |')
    lines+=['',f"Oracle 실제 MCQ 변경{changed}/{n}, 오류 fallback{summary['fallback_pairs']}/{n}. Automatic과 자기 질문이 같은데 label이 바뀐 사례{unchanged_transitions}개는 batch 동반 입력 효과 가능성도 고려한다.",'',
        '입력에서 바꾼 것은 source referent spans다. Gold target 표현·정답·bbox를 rewrite 모델에 제공하지 않았다. 같은 canonical span ID·정렬, Qwen3 translator prompt/설정, 원래 inventory와 실패, exact matcher, all-or-original fallback을 유지했다. 기존 O와 Automatic은 완료된 예측을 재사용했고 Oracle만 같은 순서·배치3으로 새로 평가했다.','',
        '참조 집합이 바뀌면 joint translation 응답과 batch padding도 달라질 수 있다. 따라서 엄밀한 accuracy 상한이 아니라 oracle_span pipeline 진단이다. 개선이 작더라도 extraction이 중요하지 않다거나 matching이 유일한 원인이라고 단정하지 않는다. Flexible matching은 이번에 바꾸지 않았다.','',
        'T_REF는 gold span + Gemma 번역, R_REF는 parallel referent 표현, F_REF는 parallel 전체 localization이다. 기존 run의 예측을 같은 primary pair ID로 맞췄다. 모델 revision·설정은 같지만 역사적 run의 batch/queue 차이를 포함하므로 Oracle과의 차이를 순수한 method 효과라고 단정하지 않는다. CI는 탐색적 95% 구간이며 여러 비교의 유의성을 확정하는 검정이 아니다.','',
        '현재 cohort는 이미 관찰된 개발 데이터다. 결과를 보고 다음 method를 수정한다면 development iteration으로 기록한다. 원래 Automatic 결과와 pipeline contract는 변경하지 않았다.']
    (work/'REPORT_KO.md').write_text('\n'.join(lines)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cohort',choices=['all',*COHORTS],default='all');p.add_argument('--base-run',type=Path,default=ROOT/'artifacts/search_pipeline_v1')
    p.add_argument('--output-root',type=Path);p.add_argument('--stage',choices=['all','prepare','rewrite','infer','report'],default='all');p.add_argument('--attempt-dir',type=Path);p.add_argument('--trial-dir',type=Path);p.add_argument('--prediction-dir',type=Path);p.add_argument('--mock',action='store_true');a=p.parse_args()
    if a.output_root is None:a.output_root=ROOT/'artifacts'/('oracle_span_exact_v1_mock' if a.mock else 'oracle_span_exact_v1')
    if a.cohort=='all':
        if a.stage not in ['all','prepare']:raise ValueError('Child stage requires one cohort')
        for cohort in COHORTS:subprocess.run([sys.executable,'-u',str(Path(__file__)), '--cohort',cohort,'--base-run',str(a.base_run),'--output-root',str(a.output_root),'--stage',a.stage,*(['--mock'] if a.mock else [])],check=True)
        return
    work=a.output_root/a.cohort;plan=prepare(a.base_run,work,a.cohort,a.mock);cache=a.output_root/'translation_cache'
    if a.stage=='prepare':print(json.dumps({'cohort':a.cohort,'prepared':True,**plan['counts']},indent=2),flush=True);return
    if a.stage=='rewrite':rewrite_stage(work,a.attempt_dir,cache,a.mock);return
    if a.stage=='infer':infer_stage(work,a.trial_dir,a.attempt_dir,a.mock);return
    if a.stage=='report':summarize(work,a.trial_dir,a.prediction_dir,a.mock);return
    lock=(ROOT/'artifacts'/('search_pipeline_mock.lock' if a.mock else 'search_pipeline_gpu.lock')).open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if not a.mock:print('Seeded translation cache:',seed_translation_cache(a.base_run,cache),flush=True)
    def job(stage,extra):
        directory=work/stage;directory.mkdir(exist_ok=True);attempts=sorted(directory.glob('attempt_*'));done=[p for p in attempts if (p/'COMPLETE').exists()]
        if done:return done[-1]
        attempt=directory/('attempt_'+str(len(attempts)+1).zfill(4));log=work/(stage+'.log')
        cmd=[sys.executable,'-u',str(Path(__file__)),'--cohort',a.cohort,'--base-run',str(a.base_run),'--output-root',str(a.output_root),'--stage',stage,'--attempt-dir',str(attempt),*extra,*(['--mock'] if a.mock else [])]
        print('RUN',a.cohort,stage,'log=',log,flush=True)
        with log.open('a') as f:
            child=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            for line in child.stdout:f.write(line);f.flush();print(line,end='',flush=True)
            code=child.wait()
            if code:raise subprocess.CalledProcessError(code,cmd)
        if not (attempt/'COMPLETE').exists():raise RuntimeError('Incomplete oracle stage')
        return attempt
    trial=job('rewrite',[]);prediction=job('infer',['--trial-dir',str(trial)]);summarize(work,trial,prediction,a.mock)
    write(work/'COMPLETE.json',{'oracle_span':True,'gold_target_used':False,'execution_mode':'mock' if a.mock else 'gpu','plan_sha256':digest(plan),'trial':str(trial),'predictions':str(prediction)})
    print('COMPLETE',work/'REPORT_KO.md',flush=True)
if __name__=='__main__':main()
