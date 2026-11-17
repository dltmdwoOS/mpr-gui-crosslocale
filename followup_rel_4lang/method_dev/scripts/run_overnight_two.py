"""Frozen direct rewrite and separate Stem-only on remaining development cohorts."""
import argparse
import fcntl
import hashlib
import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO=Path(__file__).resolve().parents[3]
ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(REPO/'01_code/src'),str(REPO),str(Path(__file__).parent)]
from run_stem_only_gui import read, write, jsonl, unique
from run_two_stage_v2 import resolved_config, budget
from search_pipeline import EXCLUDED, paired_bootstrap
from mpr_crosslocale.methods.selective_alignment.schemas import digest, fields, render, validate_input
from followup_rel_4lang.method_dev import source_copy_rewrite as direct
from followup_rel_4lang.method_dev.two_stage_v2 import pipeline, prompts
from followup_rel_4lang.method_dev.two_stage_v2.backend import Backend
import run_source_copy_rewrite as visual

METHODS={'direct':direct.CONDITION,'stem':'TS_STEM_ONLY_GUI_AUTO'}
COHORTS=('selection','internal_evaluation')


def prepare(output,mock=False,limit=None):
    base=ROOT/'artifacts/search_pipeline_v1'
    identity=json.loads((base/'data_contract.json').read_text())
    manifest=json.loads((base/'plan/manifest.json').read_text())
    if digest(manifest)!=identity['plan']:raise ValueError('Dataset plan changed')
    config=resolved_config(ROOT/'configs/two_stage_v2_hybrid.json')
    screen=json.loads((ROOT/'artifacts/visual_source_copy_rewrite_screen_v1/contract.json').read_text())
    if config['downstream']!=screen['downstream']:raise ValueError('Screen downstream differs')
    direct_config=screen['config']
    if direct_config['models']['editor_vlm']!=config['models']['inventory']:raise ValueError('Editor model differs')
    sources=[Path(__file__),ROOT/'source_copy_rewrite.py',ROOT/'direct_selective_rewrite.py',ROOT/'exact_batch_reuse.py',
        ROOT/'visual_rewrite_backend.py',ROOT/'scripts/run_source_copy_rewrite.py',ROOT/'scripts/run_two_stage_v2.py',
        ROOT/'configs/two_stage_v2_hybrid.json',base/'data_contract.json',base/'plan/manifest.json']
    sources+=list((ROOT/'two_stage_v2').glob('*.py'))
    sources+=list((REPO/'01_code/src/mpr_crosslocale/methods/selective_alignment').glob('*.py'))
    sources += [REPO/'01_code/src/mpr_crosslocale/models/qwen25vl.py',REPO/'01_code/src/mpr_crosslocale/models/qwen3_memory.py',REPO/'01_code/src/mpr_crosslocale/inference/prompts.py']
    allrows={}
    for cohort in COHORTS:
        path=base/'plan'/(cohort+'.jsonl');rows=read(path);sources.append(path)
        if digest(rows)!=manifest['cohorts'][cohort]['inputs_sha256']:raise ValueError('Cohort changed')
        if limit:
            selected=sorted({r['parallel_id'] for r in rows})[:limit]
            rows=[r for r in rows if r['parallel_id'] in selected]
        unique(rows)
        for row in rows:validate_input(row)
        allrows[cohort]=rows
    if not limit and [len(allrows[c]) for c in COHORTS]!=[240,1416]:raise ValueError('Unexpected remaining cohort size')
    if {r['parallel_id'] for r in allrows[COHORTS[0]]}&{r['parallel_id'] for r in allrows[COHORTS[1]]}:raise ValueError('Item partition overlap')
    for row in {r['image_sha256']:r for rows in allrows.values() for r in rows}.values():
        if hashlib.sha256((REPO/row['image_path']).read_bytes()).hexdigest()!=row['image_sha256']:raise ValueError('Image changed')
    contract={'version':'overnight-two-frozen-v1','execution_mode':'mock' if mock else 'gpu','config':config,
        'direct_config':direct_config,'labels_sha256':identity['labels'],'conditions':METHODS,'cohorts':list(COHORTS),
        'limit_items':limit,'source_sha256':{str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        'prompt_sha256':{'direct':digest(direct.SYSTEM),'extract_stem':digest(prompts.EXTRACT_STEM_SYSTEM),'selective':digest(prompts.SELECTIVE_GUI_SYSTEM)},
        'cohort_counts':{c:{'pairs':len(rr),'primary_pairs':sum(r['pair_id']!=EXCLUDED for r in rr),'items':len({r['parallel_id'] for r in rr})} for c,rr in allrows.items()},
        'policy':'Selection then Internal; direct and Stem-only fixed; no Screen/pilot rerun, no options full localization, no O/R/T/F rerun; one GPU worker at a time.'}
    output.mkdir(parents=True,exist_ok=True);target=output/'contract.json'
    if target.exists() and json.loads(target.read_text())!=contract:raise ValueError('Run contract changed; use a fresh --output-dir')
    write(target,contract)
    for cohort,rows in allrows.items():
        for method in METHODS:
            work=output/cohort/method;work.mkdir(parents=True,exist_ok=True)
            ic={'config':direct_config,'downstream':config['downstream'],'seed':config['seed'],'execution_mode':contract['execution_mode'],
                'inputs_sha256':digest(rows),'labels_sha256':identity['labels'],'reuse_sources':[],
                'night_contract_sha256':digest(contract),'condition':METHODS[method]}
            if (work/'inputs.jsonl').exists() and read(work/'inputs.jsonl')!=rows:raise ValueError('Inputs changed')
            jsonl(work/'inputs.jsonl',rows);write(work/'contract.json',ic)
    return contract


def latest(work,stage):
    done=sorted(p for p in (work/stage).glob('attempt_*') if (p/'COMPLETE').exists())
    if not done:raise ValueError('Dependency incomplete: '+stage)
    return done[-1]


def stem_stage(output,cohort,stage,attempt,mock):
    contract=json.loads((output/'contract.json').read_text());config=contract['config']
    work=output/cohort/'stem';rows=read(work/'inputs.jsonl')
    if not mock:budget(config)
    backend=Backend(config,REPO,output/'cache_stem',mock);attempt.mkdir(parents=True)
    started=time.perf_counter();complete=False
    try:
        filename={'inventory':'inventories.jsonl','extract_stem':'extractions.jsonl','rewrite':'rewritten.jsonl'}[stage]
        with (attempt/filename).open('w') as f:
            if stage=='inventory':
                queue=sorted({r['image_sha256']:r for r in rows}.items())
            elif stage=='extract_stem':
                queue=sorted({digest(prompts.extraction_payload(r,stem_only=True)):r for r in rows}.items())
            else:
                queue=[(r['pair_id'],r) for r in rows]
                inventories={r['image_sha256']:r for r in read(latest(work,'inventory')/'inventories.jsonl')}
                extracted={r['source_key']:r for r in read(latest(work,'extract_stem')/'extractions.jsonl')}
            for i,(key,row) in enumerate(queue,1):
                if stage=='inventory':record={'image_sha256':key,**pipeline.inventory(row,backend)}
                elif stage=='extract_stem':record={'source_key':key,'scope':'question_stem',**pipeline.extract(row,backend,stem_only=True)}
                else:
                    inv=inventories[row['image_sha256']];ex=extracted[digest(prompts.extraction_payload(row,stem_only=True))]
                    result=pipeline.selective(row,ex['referents'],backend,inv);modified=result.pop('output')
                    if any(modified[k]!=row['options'][k] for k in 'ABCD'):raise ValueError('Stem-only changed options')
                    record={**row,**result,'question_stem':modified['question_stem'],'options':dict(row['options']),
                        'modified_question':render(modified),'diffs':direct.diff_fields(row,modified),'diagnostics':direct.diagnostics(row,modified),
                        'condition':METHODS['stem'],'execution_mode':'mock' if mock else 'gpu','oracle_span':False,'gold_target_used':False,
                        'extracted_referents':ex['referents'],'inventory_status':inv['status']}
                f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush()
                print(f'{cohort} STEM {stage} {i}/{len(queue)} {record["status"]}',flush=True)
        complete=True
    finally:
        write(attempt/'calls.json',backend.calls)
        write(attempt/'cost.json',{'complete':complete,'wall_seconds':time.perf_counter()-started,'calls':len(backend.calls),
            'cache_hits':sum(c['cache_hit'] for c in backend.calls),'new_runtime_ms':sum(c['runtime_ms'] for c in backend.calls if not c['cache_hit'])})
    (attempt/'COMPLETE').write_text('complete\n')


def completed_batches(path):
    """Ignore only an interrupted trailing JSON line; keep complete batches only."""
    lines=path.read_text().splitlines();groups=defaultdict(list)
    for i,line in enumerate(lines):
        if not line.strip():continue
        try:row=json.loads(line)
        except json.JSONDecodeError:
            if i!=len(lines)-1:raise
            break
        groups[row['batch_id']].append(row)
    return [row for batch in groups.values() if len(batch)==batch[0]['batch_size'] for row in batch]


def infer_stage(output,cohort,method,attempt,mock):
    work=output/cohort/method;attempt.mkdir(parents=True)
    view=attempt/'view';view.mkdir()
    contract=json.loads((work/'contract.json').read_text());config=contract['config']
    fingerprint=visual.VisualRewriteBackend(config,REPO,output/'cache_direct',mock)
    environment={'software':fingerprint.software,'hardware':fingerprint.hardware}
    write(attempt/'environment.json',environment)
    sources=[]
    if not mock:
        for other in METHODS:
            for previous in sorted((output/cohort/other/'infer').glob('attempt_*')):
                path=previous/'evaluation/predictions.jsonl';env=previous/'environment.json'
                if previous==attempt or not path.exists() or not env.exists():continue
                oldenv=json.loads(env.read_text())
                if oldenv!=environment:continue
                rows=completed_batches(path)
                if not rows:continue
                materialized=view/f'reuse_{len(sources):04d}.jsonl';jsonl(materialized,rows)
                sources.append({'path':str(materialized),'downstream':contract['downstream'],'seed':contract['seed'],'environment':oldenv})
    contract['reuse_sources']=sources;write(view/'contract.json',contract)
    jsonl(view/'inputs.jsonl',read(work/'inputs.jsonl'))
    visual.CONDITION=METHODS[method]
    visual.infer(view,latest(work,'rewrite'),attempt/'evaluation',mock)
    (attempt/'COMPLETE').write_text('complete\n')


def report(output,mock):
    if mock:
        write(output/'results.json',{'execution_mode':'mock','empirical':False});return
    contract=json.loads((output/'contract.json').read_text())
    labels=unique(read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels)!=contract['labels_sha256']:raise ValueError('Labels changed')
    result={'execution_mode':'gpu','development_only':True,'cohorts':{}}
    lines=['# 밤샘 고정 두 조건 결과','','기존 관찰 development set. Screen/pilot 제외. 두 프롬프트는 실행 전 고정했으며 internal도 과거 관찰된 집합이다.','',
        '| Cohort | n | 직접 rewrite | Stem-only GUI | 차이·직접−Stem | 95% item bootstrap CI |','| --- | ---: | ---: | ---: | ---: | --- |']
    for cohort in COHORTS:
        values={}
        for method in METHODS:
            work=output/cohort/method;original=unique(read(work/'inputs.jsonl'))
            pred=unique(read(latest(work,'infer')/'evaluation/predictions.jsonl'))
            if set(pred)!=set(original):raise ValueError('Missing paired predictions')
            ids=sorted(p for p in original if p!=EXCLUDED)
            values[method]={p:int(pred[p]['status']=='success' and pred[p]['parsed_generated_label']==labels[p]['gold_answer']) for p in ids}
        contrast=paired_bootstrap(values['direct'],values['stem'],labels,20261115,10000)
        result['cohorts'][cohort]={'n':len(ids),'correct':{m:sum(v.values()) for m,v in values.items()},'direct_minus_stem':contrast}
        n=len(ids);lines.append(f"| {cohort} | {n} | {sum(values['direct'].values())}/{n} ({sum(values['direct'].values())/n:.2%}) | {sum(values['stem'].values())}/{n} ({sum(values['stem'].values())/n:.2%}) | {contrast['difference']*100:+.2f}pp | [{contrast['ci95'][0]*100:+.2f}, {contrast['ci95'][1]*100:+.2f}] |")
    write(output/'results.json',result);(output/'REPORT_KO.md').write_text('\n'.join(lines)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path);p.add_argument('--run',action='store_true');p.add_argument('--mock',action='store_true');p.add_argument('--limit-items',type=int)
    p.add_argument('--worker',choices=['inventory','extract_stem','rewrite','infer']);p.add_argument('--cohort',choices=COHORTS);p.add_argument('--method',choices=list(METHODS));p.add_argument('--attempt',type=Path);args=p.parse_args()
    if args.limit_items is not None and args.limit_items<1:p.error('Positive limit required')
    output=(args.output_dir or ROOT/'artifacts'/('overnight_two_v1_mock' if args.mock else 'overnight_two_v1')).resolve()
    if not output.is_relative_to(REPO):p.error('Output must stay inside repository')
    if args.worker:
        # Parent prepared and froze all inputs before any GPU worker starts.
        if args.worker=='infer':infer_stage(output,args.cohort,args.method,args.attempt,args.mock)
        elif args.method=='direct':
            visual.CONDITION=METHODS['direct'];visual.rewrite(output/args.cohort/'direct',args.attempt,args.mock)
        else:stem_stage(output,args.cohort,args.worker,args.attempt,args.mock)
        return
    lockpath=ROOT/'artifacts'/('search_pipeline_mock.lock' if args.mock else 'search_pipeline_gpu.lock')
    with lockpath.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        contract=prepare(output,args.mock,args.limit_items)
        if not args.run:print(json.dumps({'prepared':str(output),'cohorts':contract['cohort_counts'],'gpu_started':False}),flush=True);return
        if (output/'COMPLETE.json').exists():print('REUSE COMPLETE',output,flush=True);return
        started=time.perf_counter()
        for cohort in COHORTS:
            for method in METHODS:
                stages=('rewrite','infer') if method=='direct' else ('inventory','extract_stem','rewrite','infer')
                work=output/cohort/method
                for stage in stages:
                    directory=work/stage;directory.mkdir(exist_ok=True)
                    attempts=sorted(directory.glob('attempt_*'))
                    if any((a/'COMPLETE').exists() for a in attempts):print('REUSE',cohort,method,stage,flush=True);continue
                    attempt=directory/f'attempt_{len(attempts)+1:04d}'
                    command=[sys.executable,'-u',str(Path(__file__)), '--output-dir',str(output),'--cohort',cohort,'--method',method,'--worker',stage,'--attempt',str(attempt)]
                    if args.mock:command.append('--mock')
                    print(time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'RUN',cohort,method,stage,flush=True)
                    subprocess.run(command,check=True)
                    if not (attempt/'COMPLETE').exists():raise RuntimeError('Stage marker missing')
        report(output,args.mock)
        write(output/'COMPLETE.json',{'execution_mode':contract['execution_mode'],'contract_sha256':digest(contract),'wall_seconds':time.perf_counter()-started})
        print('COMPLETE',output,flush=True)


if __name__=='__main__':main()
