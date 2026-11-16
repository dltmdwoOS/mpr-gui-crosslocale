"""Prepare or sequentially run the restored two-stage protocol. Default: CPU prepare."""
import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

REPO=Path(__file__).resolve().parents[3];ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(REPO),str(REPO/'01_code/src'),str(Path(__file__).parent)]
from followup_rel_4lang.method_dev.two_stage_v2 import pipeline,prompts
from followup_rel_4lang.method_dev.two_stage_v2.backend import Backend
from mpr_crosslocale.methods.selective_alignment.schemas import digest,validate_input,fields,render
from run_oracle_exact import source_refs
from search_pipeline import paired_bootstrap,EXCLUDED

COHORTS=('screen','selection','internal_evaluation')


def read(path):return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)
def jsonl(path,rows):path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))


def resolved_config(path=None):
    config=json.loads((path or ROOT/'configs/two_stage_v2.json').read_text())
    if (config['dtype'],config['attn_implementation'],config['processor_use_fast'],config['method_batch_size'])!=('bfloat16','sdpa',True,1):raise ValueError('Unsupported execution profile')
    hf=Path(os.environ.get('HF_HOME','/home/jovyan/seungjae/.cache/huggingface'))
    for model in config['models'].values():
        model['path']=str(hf/'hub'/('models--'+model['model_id'].replace('/','--'))/'snapshots'/model['revision'])
        index=Path(model['path'])/'model.safetensors.index.json'
        if not index.exists() or any(not (index.parent/p).exists() for p in set(json.loads(index.read_text())['weight_map'].values())):raise ValueError('Pinned model cache incomplete; no download: '+model['model_id'])
    return config


def prepare(args):
    base=args.base_run.resolve();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    identity=json.loads((base/'data_contract.json').read_text());manifest=json.loads((base/'plan/manifest.json').read_text())
    if digest(manifest)!=identity['plan']:raise ValueError('Base dataset plan changed')
    rows=read(base/'plan'/(args.cohort+'.jsonl'))
    if digest(rows)!=manifest['cohorts'][args.cohort]['inputs_sha256']:raise ValueError('Base cohort changed')
    if args.limit_items:
        ids=sorted({r['parallel_id'] for r in rows});preferred=sorted(set(manifest.get('screen_calibration_items',[]))&set(ids))
        selected=(preferred+[i for i in ids if i not in preferred])[:args.limit_items]
        rows=[r for r in rows if r['parallel_id'] in selected]
    for row in rows:validate_input(row)
    config=resolved_config(args.config);mode='mock' if args.mock else 'gpu'
    if digest(json.loads((ROOT/'../artifacts/new_models_expA_20261115/analysis/expA_8b_20261114/qwen3/expA_qwen3/full/run_contract.json').read_text()))!=config['historical_baseline_contract_sha256']:raise ValueError('Historical baseline contract changed')
    if config['historical_baseline_contract_sha256']!=identity['baseline_contract']:raise ValueError('Dataset/baseline mismatch')
    sources=list((ROOT/'two_stage_v2').glob('*.py'))+[Path(__file__),ROOT/'scripts/run_oracle_exact.py',args.config.resolve(),ROOT/'two_stage_v2/legacy_manifest.json',REPO/'01_code/src/mpr_crosslocale/models/qwen25vl.py',REPO/'01_code/src/mpr_crosslocale/models/qwen3_memory.py',REPO/'01_code/src/mpr_crosslocale/inference/prompts.py']
    sources+=list((REPO/'01_code/src/mpr_crosslocale/methods/selective_alignment').glob('*.py'))
    frozen={'version':config['version'],'mode':mode,'base_data_contract':identity,'config':config,'conditions':args.conditions,
            'source_hashes':{str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    frozen_path=out/'contract.json'
    if frozen_path.exists() and json.loads(frozen_path.read_text())!=frozen:raise ValueError('Code/config changed: choose a fresh output directory')
    if not frozen_path.exists():write(frozen_path,frozen)
    work=out/args.cohort;work.mkdir(exist_ok=True);file=work/'inputs.jsonl'
    if file.exists() and read(file)!=rows:raise ValueError('Cohort or limit changed: choose a fresh output directory')
    if not file.exists():jsonl(file,rows)
    # Privileged source-only annotation adapter; no R/T target expressions or answers.
    if any(c.endswith('_ORACLE') for c in args.conditions):
        annotated=read(ROOT/'artifacts/dataset_audit/oracle_spans_DIAGNOSTIC_ONLY.jsonl')
        if digest(annotated)!=identity['oracle']:raise ValueError('Source annotations changed')
        by_pair={r['pair_id']:r for r in annotated}
        gold=[{'pair_id':r['pair_id'],'referents':source_refs(r,by_pair[r['pair_id']])} for r in rows]
        target=work/'oracle_source_spans.jsonl'
        if target.exists() and read(target)!=gold:raise ValueError('Prepared Oracle source spans changed')
        if not target.exists():jsonl(target,gold)
    plan={'cohort':args.cohort,'input_sha256':digest(rows),'pairs':len(rows),'items':len({r['parallel_id'] for r in rows}),
          'unique_images':len({r['image_sha256'] for r in rows}),'contract_sha256':digest(frozen),'limit_items':args.limit_items}
    if (work/'plan.json').exists() and json.loads((work/'plan.json').read_text())!=plan:raise ValueError('Plan changed')
    write(work/'plan.json',plan)
    return work,config,rows


def budget(config):
    import torch
    if torch.cuda.device_count()!=1:raise RuntimeError('One visible GPU required')
    free,_=torch.cuda.mem_get_info()
    if free<config['min_free_gpu_gib']*2**30:raise RuntimeError('Need40GiB free on45GB MIG; no batch reduction')
    torch.set_num_threads(3)


def transform(args,work,config,rows):
    if not args.mock:budget(config)
    out=args.attempt_dir;out.mkdir(parents=True);backend=Backend(config,REPO,args.output_dir/'cache_v2',args.mock)
    mode='mock' if args.mock else 'gpu';stage=args.stage;started=time.perf_counter();completed=False
    write(out/'contract.json',{'execution_mode':mode,'stage':stage,'plan_sha256':digest(json.loads((work/'plan.json').read_text())),'input_sha256':digest(rows)})
    try:
        if stage=='inventory':
            unique={r['image_sha256']:r for r in rows}
            with (out/'inventories.jsonl').open('w') as f:
                for i,(sha,row) in enumerate(sorted(unique.items()),1):
                    record={'image_sha256':sha,**pipeline.inventory(row,backend)}
                    f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush()
                    if i==1 or i%10==0 or i==len(unique):print(f'INVENTORY {i}/{len(unique)} {record["status"]}',flush=True)
        elif stage in ('extract','extract_stem'):
            stem_only=stage=='extract_stem'
            unique={digest(prompts.extraction_payload(r,stem_only=stem_only)):r for r in rows}
            with (out/'extractions.jsonl').open('w') as f:
                for i,(key,row) in enumerate(sorted(unique.items()),1):
                    record={'source_key':key,'scope':'question_stem' if stem_only else 'all_fields',**pipeline.extract(row,backend,stem_only=stem_only)}
                    f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush()
                    if i==1 or i%20==0 or i==len(unique):print(f'EXTRACT {i}/{len(unique)} {record["status"]}',flush=True)
        elif stage=='rewrite':
            inv={r['image_sha256']:r for r in read(args.inventory_dir/'inventories.jsonl')} if args.inventory_dir else {}
            extracted={r['source_key']:r for r in read(args.extraction_dir/'extractions.jsonl')} if args.extraction_dir else {}
            stem_extracted={r['source_key']:r for r in read(args.stem_extraction_dir/'extractions.jsonl')} if args.stem_extraction_dir else {}
            for condition in args.conditions:
                # No automatic branch reads source annotation artifacts.
                oracle={r['pair_id']:r['referents'] for r in read(work/'oracle_source_spans.jsonl')} if condition.endswith('_ORACLE') else None
                with (out/(condition+'.jsonl')).open('w') as f:
                    for i,row in enumerate(rows,1):
                        inventory=inv[row['image_sha256']] if '_GUI' in condition else None
                        refs=None;failure_fields=[]
                        if '_FULL_' in condition:result=pipeline.full(row,backend,inventory)
                        elif condition in prompts.HYBRID_CONDITIONS:
                            key=digest(prompts.extraction_payload(row,stem_only=True))
                            refs=stem_extracted[key]['referents']
                            failure_fields=stem_extracted[key].get('failure_fields',[])
                            result=pipeline.hybrid(row,refs,backend,inventory)
                        else:
                            key=digest(prompts.extraction_payload(row))
                            refs=oracle[row['pair_id']] if oracle is not None else extracted[key]['referents']
                            failure_fields=[] if oracle is not None else extracted[key].get('failure_fields',[])
                            result=pipeline.selective(row,refs,backend,inventory)
                        output=result.pop('output')
                        record={**row,'question_stem':output['question_stem'],'options':{k:output[k] for k in 'ABCD'},'modified_question':render(output),
                                'condition':condition,'oracle_span':oracle is not None,'gold_target_used':False,'extracted_referents':refs,'inventory_status':None if inventory is None else inventory['status'],
                                'execution_mode':mode,'extraction_failure_fields':failure_fields,**result}
                        f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush()
                        if i==1 or i%20==0 or i==len(rows):print(f'{condition} {i}/{len(rows)}',flush=True)
        completed=True
    finally:
        write(out/'calls.json',backend.calls)
        write(out/'cost.json',{'execution_mode':mode,'stage':stage,'wall_seconds':time.perf_counter()-started,'calls':len(backend.calls),'cache_hits':sum(c['cache_hit'] for c in backend.calls),
                              'new_runtime_ms':sum(c['runtime_ms'] for c in backend.calls if not c['cache_hit']),'complete':completed})
    if completed:(out/'COMPLETE').write_text('complete\n')


def infer(args,work,config,rows):
    from mpr_crosslocale.inference.answer_parser import parse_label
    from mpr_crosslocale.models.qwen25vl import Qwen25VLAdapter
    if not args.mock:budget(config)
    labels={r['pair_id']:r for r in read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl')}
    expected=json.loads((args.output_dir/'contract.json').read_text())['base_data_contract']['labels']
    if digest(labels)!=expected:raise ValueError('Evaluation labels changed')
    profile=config['downstream'];model=profile['model_config'];adapter=None
    if not args.mock:
        from transformers import set_seed
        set_seed(config['seed'])
        adapter=Qwen25VLAdapter(model_id=model['model_id'],revision=model['revision'],dtype=model['dtype'],attn_implementation=model['attn_implementation'],device_map='cuda:0',
             processor_kwargs={'use_fast':True,'min_pixels':model['min_pixels'],'max_pixels':model['max_pixels']},model_family=model['model_family'],patch_embed_memory_format=model['patch_embed_memory_format'])
        adapter.max_input_tokens=profile['max_input_tokens']
    args.attempt_dir.mkdir(parents=True);mode='mock' if args.mock else 'gpu'
    write(args.attempt_dir/'contract.json',{'execution_mode':mode,'downstream':profile,'input_sha256':digest(rows),'condition_order':['O',*args.conditions],
          'queue_order':'condition-separated; pair_id sorted; same source pair groups in every condition','seed':config['seed']})
    from types import SimpleNamespace
    import torch
    original={r['pair_id']:r for r in rows}
    with (args.attempt_dir/'predictions.jsonl').open('w') as f:
        for condition in ['O',*args.conditions]:
            rewritten=rows if condition=='O' else read(args.rewrite_dir/(condition+'.jsonl'))
            if len(rewritten)!=len(original) or {r['pair_id'] for r in rewritten}!=set(original):raise ValueError('Incomplete condition')
            queue=[]
            for row in sorted(rewritten,key=lambda r:r['pair_id']):
                before=original[row['pair_id']]
                for k in ['parallel_id','source_language','gui_language','image_path','image_sha256','option_order']:
                    if row[k]!=before[k]:raise ValueError('Paired identity changed')
                if not args.mock and hashlib.sha256((REPO/row['image_path']).read_bytes()).hexdigest()!=row['image_sha256']:raise ValueError('Image changed')
                queue.append({'pair_id':row['pair_id'],'parallel_id':row['parallel_id'],'image_paths':[str(REPO/row['image_path'])],
                              'question_raw':render(fields(row)),'gold_label':labels[row['pair_id']]['gold_answer']})
            for start in range(0,len(queue),profile['batch_size']):
                chunk=queue[start:start+profile['batch_size']];t=time.perf_counter()
                if args.mock:predictions=[SimpleNamespace(raw_output='A',rendered_prompt='MOCK',prompt_token_count=0,output_token_count=0) for _ in chunk]
                else:
                    torch.cuda.reset_peak_memory_stats()
                    predictions=adapter.generate_batch(chunk,model['prompt_profile'],model['generation'],system_prompt=profile['system_prompt'],score_labels=profile['score_labels'])
                runtime=(time.perf_counter()-t)*1000
                if len(predictions)!=len(chunk):raise ValueError('Lost model outputs')
                for row,pred in zip(chunk,predictions,strict=True):
                    f.write(json.dumps({'pair_id':row['pair_id'],'parallel_id':row['parallel_id'],'condition':condition,'execution_mode':mode,'status':'success',
                       'generated_text':pred.raw_output,'parsed_generated_label':parse_label(pred.raw_output),'rendered_prompt':pred.rendered_prompt,'prompt_tokens':pred.prompt_token_count,'output_tokens':pred.output_token_count,
                       'batch_id':condition+':'+str(start),'batch_size':len(chunk),'batch_runtime_ms':runtime,'peak_reserved_bytes':None if args.mock else torch.cuda.max_memory_reserved()},ensure_ascii=False)+'\n');f.flush()
                if start==0 or start%60==0 or start+len(chunk)==len(queue):print(f'INFER {condition} {start+len(chunk)}/{len(queue)}',flush=True)
    (args.attempt_dir/'COMPLETE').write_text('complete\n')


def hybrid_comparisons(rewritten,values,labels):
    """Paired evaluation only: no labels/predictions enter either transformation."""
    comparisons={}
    for condition in prompts.HYBRID_CONDITIONS:
        if condition not in values:continue
        gui='_GUI' in condition
        selective='TS_SEL_GUI_AUTO' if gui else 'TS_SEL_TXT_AUTO'
        full='TS_FULL_GUI' if gui else 'TS_FULL_TXT'
        primary=values[condition]
        rows={r['pair_id']:r for r in rewritten[condition]}
        group={'primary_pairs':len(primary),'components':{key:sum(bool(rows[p]['components'][key]) for p in primary) for key in ['stem_extraction_failed','stem_alignment_failed','options_full_pipeline_failed']},
               'stem_changed_pairs':sum(rows[p]['components']['stem_changed'] for p in primary),
               'options_changed_fields':sum(rows[p]['components']['options_changed'] for p in primary),'contrasts':{},
               'interpretation':'Pipeline-level control: extraction scope/prompt and option context language change; not a pure parser-only causal effect.'}
        for baseline in (selective,full):
            if baseline in values:group['contrasts'][baseline]=paired_bootstrap(primary,values[baseline],labels,20261115,10000)
        if selective in rewritten:
            before={r['pair_id']:r for r in rewritten[selective]}
            group['extraction_comparison']={
                'all_field_failed_pairs':sum(before[p]['extracted_referents'] is None for p in primary),
                'all_field_failed_only_options_pairs':sum(before[p]['extracted_referents'] is None and bool(before[p].get('extraction_failure_fields')) and all(f in ('A','B','C','D') for f in before[p]['extraction_failure_fields']) for p in primary),
                'all_field_failed_fields':dict(Counter(f for p in primary if before[p]['extracted_referents'] is None for f in before[p].get('extraction_failure_fields',[]))),
                'stem_only_failed_pairs':sum(rows[p]['extracted_referents'] is None for p in primary),
                'all_field_failed_stem_succeeded':sum(before[p]['extracted_referents'] is None and rows[p]['extracted_referents'] is not None for p in primary),
                'all_field_succeeded_stem_failed':sum(before[p]['extracted_referents'] is not None and rows[p]['extracted_referents'] is None for p in primary)}
        comparisons[condition]=group
    return comparisons


def report(work,predictions,mock,rewrite_dir=None):
    if mock:
        write(work/'results.json',{'execution_mode':'mock','empirical':False,'note':'CPU functionality only; no accuracy or timing claims.'});return
    labels={r['pair_id']:r for r in read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl')}
    preds=read(predictions/'predictions.jsonl');values={}
    for r in preds:
        if r['execution_mode']!='gpu':raise ValueError('Mock outputs cannot be evaluated')
        if labels[r['pair_id']]['split']!='main' or r['pair_id']==EXCLUDED:continue
        group=values.setdefault(r['condition'],{})
        if r['pair_id'] in group:raise ValueError('Duplicate predictions')
        group[r['pair_id']]=int(r['status']=='success' and r['parsed_generated_label']==labels[r['pair_id']]['gold_answer'])
    results={c:{'n':len(v),'correct':sum(v.values()),'vs_O':paired_bootstrap(v,values['O'],labels,20261115,10000) if c!='O' else None} for c,v in values.items()}
    transformations={c:read(rewrite_dir/(c+'.jsonl')) for c in values if c!='O'} if rewrite_dir else {}
    hybrid=hybrid_comparisons(transformations,values,labels) if transformations else {}
    write(work/'results.json',{'execution_mode':'gpu','development_only':True,'conditions':results,'hybrid_controls':hybrid})
    lines=['# Restored two-stage results','', '| Condition | Correct | Accuracy |','| --- | ---: | ---: |']
    for c,r in results.items():lines.append(f"| {c} | {r['correct']}/{r['n']} | {r['correct']/r['n']:.3%} |")
    if hybrid:
        lines+=['','| Hybrid control | Query 추출 실패 | Query 정렬 실패 | Options Full pipeline 실패 |','| --- | ---: | ---: | ---: |']
        for c,r in hybrid.items():lines.append(f"| {c} | {r['components']['stem_extraction_failed']} | {r['components']['stem_alignment_failed']} | {r['components']['options_full_pipeline_failed']} |")
        lines+=['','전체 필드 추출 대비 실패 수와 Full/Selective 대비 paired accuracy·회복/회귀·CI는 results.json의 hybrid_controls에 저장했다. Stem-only prompt와 options 문맥 언어도 달라지는 pipeline 수준의 비교다.']
    (work/'REPORT_KO.md').write_text('\n'.join(lines)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=['prepare','all','inventory','extract','extract_stem','rewrite','infer'],default='prepare')
    p.add_argument('--cohort',choices=['all',*COHORTS],default='all');p.add_argument('--base-run',type=Path,default=ROOT/'artifacts/search_pipeline_v1')
    p.add_argument('--config',type=Path,default=ROOT/'configs/two_stage_v2_hybrid.json')
    p.add_argument('--output-dir',type=Path);p.add_argument('--conditions',nargs='+',choices=prompts.CONDITIONS);p.add_argument('--limit-items',type=int)
    p.add_argument('--mock',action='store_true');p.add_argument('--attempt-dir',type=Path);p.add_argument('--inventory-dir',type=Path);p.add_argument('--extraction-dir',type=Path);p.add_argument('--stem-extraction-dir',type=Path);p.add_argument('--rewrite-dir',type=Path);args=p.parse_args()
    if args.conditions is None:args.conditions=json.loads(args.config.read_text()).get('conditions',list(prompts.BASE_CONDITIONS))
    if len(set(args.conditions))!=len(args.conditions) or args.limit_items is not None and args.limit_items<1:raise ValueError('Invalid selection')
    if args.output_dir is None:args.output_dir=ROOT/'artifacts'/(args.config.stem+('_mock' if args.mock else ''))
    args.output_dir=args.output_dir.resolve()
    def command(stage,cohort,extra=()):
        return [sys.executable,'-u',str(Path(__file__)),'--stage',stage,'--cohort',cohort,'--base-run',str(args.base_run),'--output-dir',str(args.output_dir),'--config',str(args.config.resolve()),
                '--conditions',*args.conditions,*(['--limit-items',str(args.limit_items)] if args.limit_items else []),*(['--mock'] if args.mock else []),*extra]
    if args.cohort=='all':
        if args.stage not in ('prepare','all'):raise ValueError('Worker stage requires one cohort')
        for cohort in COHORTS:subprocess.run(command(args.stage,cohort),check=True)
        return
    work,config,rows=prepare(args)
    if args.stage=='prepare':print(json.dumps({'prepared':str(work),**json.loads((work/'plan.json').read_text()),'conditions':args.conditions}),flush=True);return
    if args.stage in ('inventory','extract','extract_stem','rewrite'):transform(args,work,config,rows);return
    if args.stage=='infer':infer(args,work,config,rows);return
    lock=(ROOT/'artifacts'/('search_pipeline_mock.lock' if args.mock else 'search_pipeline_gpu.lock')).open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    def job(stage,extra=()):
        directory=work/stage;directory.mkdir(exist_ok=True);attempts=sorted(directory.glob('attempt_*'));done=[a for a in attempts if (a/'COMPLETE').exists()]
        if done:print('REUSE',stage,done[-1],flush=True);return done[-1]
        attempt=directory/f'attempt_{len(attempts)+1:04d}';log=work/(stage+'.log');print('RUN',args.cohort,stage,flush=True)
        with log.open('a') as f:
            child=subprocess.Popen(command(stage,args.cohort,['--attempt-dir',str(attempt),*extra]),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            for line in child.stdout:f.write(line);f.flush();print(line,end='',flush=True)
            if child.wait():raise RuntimeError('Stage failed; see '+str(log))
        if not (attempt/'COMPLETE').exists():raise ValueError('Missing completion marker')
        return attempt
    inventory=job('inventory') if any('_GUI' in c for c in args.conditions) else None
    extraction=job('extract') if any(c.startswith('TS_SEL_') and c.endswith('_AUTO') for c in args.conditions) else None
    stem_extraction=job('extract_stem') if any(c in prompts.HYBRID_CONDITIONS for c in args.conditions) else None
    dependencies=[*(['--inventory-dir',str(inventory)] if inventory else []),*(['--extraction-dir',str(extraction)] if extraction else []),*(['--stem-extraction-dir',str(stem_extraction)] if stem_extraction else [])]
    rewritten=job('rewrite',dependencies)
    predictions=job('infer',['--rewrite-dir',str(rewritten)]);report(work,predictions,args.mock,rewritten)
    write(work/'COMPLETE.json',{'execution_mode':'mock' if args.mock else 'gpu','inventory':str(inventory) if inventory else None,'extract':str(extraction) if extraction else None,'extract_stem':str(stem_extraction) if stem_extraction else None,'rewrite':str(rewritten),'predictions':str(predictions)})
    print('COMPLETE',work,flush=True)


if __name__=='__main__':main()
