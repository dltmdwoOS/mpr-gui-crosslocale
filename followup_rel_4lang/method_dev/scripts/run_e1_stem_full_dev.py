"""Frozen E1 extractor + original M0 matcher on the entire 158-item dev cohort."""
import argparse
import fcntl
import gzip
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

REPO=Path(__file__).resolve().parents[3];ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(REPO/'01_code/src'),str(REPO),str(Path(__file__).parent)]
from run_stem_only_gui import read,write,jsonl,unique
from run_two_stage_v2 import resolved_config
from run_stem_refinement_2x2 import latest
import run_stem_refinement_2x2 as experiment
from search_pipeline import EXCLUDED,paired_bootstrap
from compare_end_to_end import batch_share
from mpr_crosslocale.methods.selective_alignment.schemas import digest,fields
from mpr_crosslocale.inference.answer_parser import parse_label
from followup_rel_4lang.method_dev import stem_refinement_2x2 as method
from followup_rel_4lang.method_dev.two_stage_v2 import prompts

COHORTS=('selection','internal_evaluation')


def verify_sources(contract):
    for name,sha in contract['source_sha256'].items():
        if hashlib.sha256((REPO/name).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen source changed: '+name)


def prepare(output,mock=False,limit=None):
    screen=ROOT/'artifacts/stem_refinement_2x2_screen_v1';sc=json.loads((screen/'contract.json').read_text());sd=json.loads((screen/'COMPLETE.json').read_text())
    night=ROOT/'artifacts/overnight_two_v1';nc=json.loads((night/'contract.json').read_text());nd=json.loads((night/'COMPLETE.json').read_text())
    if sd['execution_mode']!='gpu' or sd['contract_sha256']!=digest(sc) or nd['execution_mode']!='gpu' or nd['contract_sha256']!=digest(nc):raise ValueError('Completed Screen and remaining baseline required')
    for name,sha in sc['source_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha:raise ValueError('Screen source changed')
    verify_sources(nc)
    if sc['prompt_sha256']['E1']!=digest(method.EXTRACT_SYSTEM) or sc['prompt_sha256']['M0']!=digest(prompts.SELECTIVE_GUI_SYSTEM):raise ValueError('Selected method changed')
    if resolved_config(ROOT/'configs/two_stage_v2_hybrid.json')!=sc['config'] or nc['config']!=sc['config']:raise ValueError('Config differs')
    captures=[Path(__file__),ROOT/'scripts/run_stem_refinement_2x2.py',ROOT/'stem_refinement_2x2.py',ROOT/'scripts/run_source_copy_rewrite.py',
        screen/'contract.json',screen/'COMPLETE.json',night/'contract.json',night/'COMPLETE.json']
    captures += [REPO/p for p in nc['source_sha256']]
    captures += [Path(p) for p in sc['source_sha256']]
    descriptors={};cohort_rows={}
    screen_base=ROOT/'artifacts/stem_only_gui_screen_v1'
    descriptors['screen']={'inputs':str(screen/'inputs.jsonl'),'rewrite':str(latest(screen/'E1_M0','rewrite')),
        'infer':str(latest(screen/'E1_M0','infer')),'baseline_rewrite':str(screen/'E0_M0/rewrite/attempt_import/rewritten.jsonl'),
        'baseline_pred':str(screen/'E0_M0/infer/attempt_import/evaluation/predictions.jsonl'),
        'O_pred':sc['legacy_reuse_sources'][0]['path'],'reuse_only':True}
    for p in [Path(descriptors['screen'][k]) for k in ('inputs','baseline_rewrite','baseline_pred','O_pred')]:captures.append(p)
    captures += [Path(descriptors['screen']['rewrite'])/'rewritten.jsonl',Path(descriptors['screen']['infer'])/'evaluation/predictions.jsonl']
    for cohort in COHORTS:
        work=night/cohort/'stem';rr=read(work/'inputs.jsonl')
        if limit:
            selected=sorted({r['parallel_id'] for r in rr})[:limit];rr=[r for r in rr if r['parallel_id'] in selected]
        cohort_rows[cohort]=rr
        inv=latest(work,'inventory')/'inventories.jsonl';ex=latest(work,'extract_stem')/'extractions.jsonl';oldrewrite=latest(work,'rewrite')/'rewritten.jsonl'
        captures += [work/'inputs.jsonl',inv,ex,oldrewrite]
        originals=unique(rr);inventory={r['image_sha256']:r for r in read(inv)};rewrites=unique(read(oldrewrite));extracted={r['source_key']:r for r in read(ex)}
        for row in rr:
            refs=extracted[digest(prompts.extraction_payload(row,stem_only=True))]['referents']
            replay=experiment.replay_baseline(row,refs,inventory[row['image_sha256']],rewrites[row['pair_id']]['attempts'])
            if replay['output']!=fields(rewrites[row['pair_id']]):raise ValueError('Baseline replay differs')
        sources=[]
        for baseline_method in ('stem','direct'):
            base=night/cohort/baseline_method;attempt=latest(base,'infer');pred=attempt/'evaluation/predictions.jsonl';env=attempt/'environment.json'
            evaluation=json.loads((attempt/'evaluation/contract.json').read_text())
            if evaluation['downstream']!=sc['downstream']:raise ValueError('Prior inference profile differs')
            sources.append({'path':str(pred),'downstream':sc['downstream'],'seed':sc['seed'],'environment':json.loads(env.read_text())})
            captures += [pred,env,attempt/'evaluation/contract.json']
        descriptors[cohort]={'source_inputs':str(work/'inputs.jsonl'),'inventory_path':str(inv),'legacy_extraction_path':str(ex),
            'baseline_rewrite':str(oldrewrite),'baseline_pred':sources[0]['path'],
            'O_pred':str(ROOT/'artifacts/search_pipeline_v1/jobs'/cohort/'pred_fixed_contrastive_GUI_EXACT/attempt_0001/predictions.jsonl'),
            'legacy_reuse_sources':sources,'pairs':len(rr),'baseline_replayed_pairs':len(rr)}
        captures.append(Path(descriptors[cohort]['O_pred']))
    if not limit and [len(cohort_rows[k]) for k in COHORTS]!=[240,1416]:raise ValueError('Remaining cohort count differs')
    for row in {r['image_sha256']:r for rr in cohort_rows.values() for r in rr}.values():
        if hashlib.sha256((REPO/row['image_path']).read_bytes()).hexdigest()!=row['image_sha256']:raise ValueError('Image changed')
    sources=(night/'cache_stem',screen/'cache');cache_files={};conflicts=set()
    if not mock:
        for source in sources:
            for p in source.glob('*.json'):
                if len(p.stem)!=64 or not p.is_file() or not p.resolve().is_relative_to(REPO):continue
                if p.name in cache_files:
                    if json.loads(p.read_text())['raw_output']!=json.loads(cache_files[p.name].read_text())['raw_output']:conflicts.add(p.name)
                else:cache_files[p.name]=p
    contract={'version':'E1-M0-full-dev-v1','execution_mode':'mock' if mock else 'gpu','limit_items':limit,
        'config':sc['config'],'inference_config':sc['inference_config'],'downstream':sc['downstream'],'seed':sc['seed'],
        'labels_sha256':sc['labels_sha256'],'oracle_sha256':sc['oracle_sha256'],'prompt_sha256':{'E1':digest(method.EXTRACT_SYSTEM),'M0':digest(prompts.SELECTIVE_GUI_SYSTEM)},
        'descriptors':descriptors,'cohorts':list(COHORTS),'method':'E1_M0','screen_reused':True,
        'LM_cache_imports':len(cache_files)-len(conflicts),'LM_cache_conflicts':sorted(conflicts),
        'source_sha256':{str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in captures},
        'scope':'158-item development main:1896 executed/1895 primary. Screen288 including48pilot reused; only remaining1656 pairs executed. No366-item expansion. Frozen E1 and M0, no language policy.'}
    output.mkdir(parents=True,exist_ok=True)
    if (output/'contract.json').exists() and json.loads((output/'contract.json').read_text())!=contract:raise ValueError('Full-dev plan changed; fresh output required')
    write(output/'contract.json',contract);cache=output/'cache';cache.mkdir(exist_ok=True)
    for name,path in cache_files.items():
        if name in conflicts:continue
        dest=cache/name
        if not dest.exists():dest.symlink_to(path)
    for cohort,rr in cohort_rows.items():
        work=output/cohort;work.mkdir(exist_ok=True)
        link=work/'cache'
        if not link.exists():link.symlink_to(cache,target_is_directory=True)
        if link.resolve()!=cache:raise ValueError('Shared cache location differs')
        jsonl(work/'inputs.jsonl',rr)
        cc={**contract,**descriptors[cohort],'inputs_sha256':digest(rr),'baseline_replay_pairs':len(rr),
            'inventory_images':len(read(Path(descriptors[cohort]['inventory_path'])))}
        write(work/'contract.json',cc)
        old=work/'extraction/E0';old.mkdir(parents=True,exist_ok=True);jsonl(old/'extractions.jsonl',read(Path(descriptors[cohort]['legacy_extraction_path'])));(old/'COMPLETE').write_text('imported\n')
        cell=work/'E1_M0';cell.mkdir(exist_ok=True);jsonl(cell/'inputs.jsonl',rr)
        write(cell/'contract.json',{'config':sc['inference_config'],'downstream':sc['downstream'],'seed':sc['seed'],'execution_mode':contract['execution_mode'],
            'inputs_sha256':digest(rr),'labels_sha256':sc['labels_sha256'],'reuse_sources':[],'parent_sha256':digest(contract),'condition':'E1_M0'})
    return contract


def summarize(output,mock):
    if mock:write(output/'results.json',{'execution_mode':'mock','empirical':False});return
    c=json.loads((output/'contract.json').read_text());labels=unique(read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels)!=c['labels_sha256']:raise ValueError('Labels changed')
    annotations_rows=read(ROOT/'artifacts/dataset_audit/oracle_spans_DIAGNOSTIC_ONLY.jsonl')
    if digest(annotations_rows)!=c['oracle_sha256']:raise ValueError('Diagnostic annotation changed')
    annotations=unique(annotations_rows)
    originals={};predictions={};rewrites={};values={};cost={};quality={}
    for cohort in ('screen',*COHORTS):
        d=c['descriptors'][cohort]
        if cohort=='screen':
            originals[cohort]=unique(read(Path(d['inputs'])));rw=Path(d['rewrite']);inf=Path(d['infer'])
        else:
            work=output/cohort;originals[cohort]=unique(read(work/'inputs.jsonl'));rw=latest(work/'E1_M0','rewrite');inf=latest(work/'E1_M0','infer')
            cost[cohort]={'extract':json.loads((latest(work/'extraction','E1')/'cost.json').read_text()),'rewrite':json.loads((rw/'cost.json').read_text()),'infer':json.loads((inf/'evaluation/cost.json').read_text())}
        rr=unique(read(rw/'rewritten.jsonl'));pp=unique(read(inf/'evaluation/predictions.jsonl'))
        old=unique(read(Path(d['baseline_pred'])));op=unique([r for r in read(Path(d['O_pred'])) if r['condition']=='O'])
        if set(rr)!=set(originals[cohort]) or set(pp)!=set(rr):raise ValueError('Incomplete new predictions')
        ids=sorted(p for p in rr if labels[p]['split']=='main' and p!=EXCLUDED)
        for p in rr:
            if rr[p]['options']!=originals[cohort][p]['options'] or parse_label(pp[p]['generated_text'])!=pp[p]['parsed_generated_label']:raise ValueError('Option/parser differs')
        values[cohort]={key:{p:int(records[p]['status']=='success' and records[p]['parsed_generated_label']==labels[p]['gold_answer']) for p in ids} for key,records in [('E1_M0',pp),('E0_M0',old),('O_B200',op)]}
        predictions[cohort]=pp;rewrites[cohort]=rr
        gold=found=matched=0
        for p in ids:
            g={(s['start'],s['end']) for s in annotations[p]['referents'] if s['field']=='question_stem'}
            f={(s['start'],s['end']) for s in rr[p]['extracted_referents'] or []}
            gold+=len(g);found+=len(f);matched+=len(g&f)
        pr=matched/found if found else 0;rc=matched/gold if gold else 0
        quality[cohort]={'status':dict(Counter(rr[p]['status'] for p in ids)),
            'errors':dict(Counter(e for p in ids for e in rr[p]['errors'])),
            'changed':sum(fields(rr[p])!=fields(originals[cohort][p]) for p in ids),
            'digit_changed':sum(bool(rr[p]['diagnostics']['digit_sequence_changed_fields']) for p in ids),
            'new_duplicate_options':sum(rr[p]['diagnostics']['new_duplicate_options'] for p in ids),
            'source_extraction':{'precision':pr,'recall':rc,'f1':2*pr*rc/(pr+rc) if pr+rc else 0,'gold':gold,'predicted':found,'matched':matched}}
    wanted={p for v in values.values() for p in v['E1_M0']}
    rdir=ROOT.parent/'results/rstem_ropts_20261110/qwen3/raw'
    rcontract=json.loads((rdir/'run_contract.json').read_text())
    if rcontract['model_config']!=c['downstream']['model_config'] or rcontract['system_prompt']!=c['downstream']['system_prompt']:raise ValueError('R_stem model/system differs')
    with gzip.open(rdir/'predictions.jsonl.gz','rt') as f:reference=unique([r for r in map(json.loads,f) if r['pair_id'] in wanted and r['condition']=='R_stem'])
    if set(reference)!=wanted:raise ValueError('R_stem incomplete')
    for cohort,v in values.items():v['R_stem']={p:int(reference[p]['status']=='success' and reference[p]['parsed_generated_label']==labels[p]['gold_answer']) for p in v['E1_M0']}
    values['all_158']={key:{p:x for cohort in ('screen',*COHORTS) for p,x in values[cohort][key].items()} for key in values['screen']}
    if len(values['all_158']['E1_M0'])!=1895:raise ValueError('Full development primary denominator differs')
    summary={}
    for cohort,v in values.items():
        ids=sorted(v['E1_M0']);summary[cohort]={'n':len(ids),'items':len({labels[p]['parallel_id'] for p in ids}),
            'correct':{k:sum(x.values()) for k,x in v.items()},
            'contrasts':{ref:paired_bootstrap(v['E1_M0'],v[ref],labels,20261115,10000) for ref in ('E0_M0','O_B200','R_stem')},
            'by_gui':{g:{'n':sum(p.endswith('::'+g) for p in ids),'correct':{k:sum(x[p] for p in ids if p.endswith('::'+g)) for k,x in v.items()}} for g in ('en','zh','th','ru')}}
    result={'execution_mode':'gpu','development_only':True,'summary':summary,'quality':quality,'new_stage_costs':cost,'method':'E1_M0','prompt_sha256':c['prompt_sha256'],'contract_sha256':digest(c)}
    write(output/'results.json',result)
    lines=['# E1 수정 추출 + M0: 전체158문항 개발 결과','','고정 E1 prompt와 기존 M0. Screen은 완료 예측을 재사용하고 Selection/Internal만 새로 수행했다. 전체366문항 평가가 아니며 모든 집합은 반복 관찰한 development set이다.','',
        '| 범위 | n | 기존 O | 기존 E0_M0 | 새 E1_M0 | R_stem |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for cohort,ss in summary.items():lines.append(f"| {cohort} | {ss['n']} | "+' | '.join(f"{ss['correct'][key]}/{ss['n']} ({ss['correct'][key]/ss['n']:.2%})" for key in ('O_B200','E0_M0','E1_M0','R_stem'))+' |')
    lines+=['','| 범위 | 새−기존 추출 | 95% item bootstrap CI | 회복/회귀 |','| --- | ---: | --- | ---: |']
    for cohort,ss in summary.items():
        x=ss['contrasts']['E0_M0'];lines.append(f"| {cohort} | {x['difference']*100:+.2f}pp | [{x['ci95'][0]*100:+.2f}, {x['ci95'][1]*100:+.2f}] | {x['recovery']}/{x['regression']} |")
    lines+=['','R_stem은 과거 parallel stem reference이며 장비·batch·queue 차이가 있다. 모든 CI는 반복 관찰한 개발 자료의 탐색 구간이며 독립 확인 실험이 아니다. 생성 실패는 사전 fallback에 따라 포함했다. 실제 추가 시간과 재사용 수는 COMPLETE.json 및 stage cost.json에 보존한다.','',
        '## 처리 진단','', '```json',json.dumps(quality,ensure_ascii=False,indent=2),'```','']
    (output/'REPORT_KO.md').write_text('\n'.join(lines))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');p.add_argument('--mock',action='store_true');p.add_argument('--limit-items',type=int);p.add_argument('--output-dir',type=Path)
    p.add_argument('--worker',choices=('extract','rewrite','infer'));p.add_argument('--cohort',choices=COHORTS);p.add_argument('--attempt',type=Path);args=p.parse_args()
    if args.limit_items is not None and (not args.mock or args.limit_items<1):p.error('Positive --limit-items is mock-only')
    output=(args.output_dir or ROOT/'artifacts'/('e1_stem_full_dev_v1_mock' if args.mock else 'e1_stem_full_dev_v1')).resolve()
    if not output.is_relative_to(REPO):p.error('Output must remain in repository')
    if args.worker:
        c=json.loads((output/'contract.json').read_text());verify_sources(c)
        if c['execution_mode']!=('mock' if args.mock else 'gpu'):raise ValueError('Mode changed')
        work=output/args.cohort
        cc=json.loads((work/'contract.json').read_text())
        if cc['config']!=c['config'] or cc['inference_config']!=c['inference_config'] or digest(read(work/'inputs.jsonl'))!=cc['inputs_sha256']:raise ValueError('Worker config/input changed')
        if args.worker=='extract':experiment.extract_stage(work,args.attempt,args.mock)
        elif args.worker=='rewrite':experiment.rewrite_stage(work,'E1_M0',args.attempt,args.mock)
        else:experiment.infer_stage(work,'E1_M0',args.attempt,args.mock)
        return
    with (ROOT/'artifacts'/('search_pipeline_mock.lock' if args.mock else 'search_pipeline_gpu.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        c=prepare(output,args.mock,args.limit_items)
        if not args.run:
            for cohort in COHORTS:experiment.readiness(output/cohort)
            print('PREPARED',output,'GPU not started',flush=True);return
        if (output/'COMPLETE.json').exists():print('REUSE COMPLETE',output,flush=True);return
        started=time.perf_counter()
        for cohort in COHORTS:
            work=output/cohort
            for stage in ('extract','rewrite','infer'):
                directory=work/'extraction/E1' if stage=='extract' else work/'E1_M0'/stage
                directory.mkdir(parents=True,exist_ok=True);attempts=sorted(directory.glob('attempt_*'))
                if any((a/'COMPLETE').exists() for a in attempts):print('REUSE',cohort,stage,flush=True);continue
                attempt=directory/f'attempt_{len(attempts)+1:04d}'
                cmd=[sys.executable,'-u',str(Path(__file__)),'--output-dir',str(output),'--cohort',cohort,'--worker',stage,'--attempt',str(attempt)]
                if args.mock:cmd.append('--mock')
                print(time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'RUN',cohort,stage,flush=True)
                subprocess.run(cmd,check=True)
                if not (attempt/'COMPLETE').exists():raise ValueError('Stage incomplete')
        summarize(output,args.mock);write(output/'COMPLETE.json',{'execution_mode':c['execution_mode'],'contract_sha256':digest(c),'wall_seconds':time.perf_counter()-started})
        print('COMPLETE',output,flush=True)


if __name__=='__main__':main()
