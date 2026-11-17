"""Prepare or sequentially evaluate a frozen Screen extractor x matcher comparison."""
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
from run_two_stage_v2 import budget,resolved_config
from run_overnight_two import completed_batches
from search_pipeline import paired_bootstrap,EXCLUDED
from compare_end_to_end import call_map,call_seconds,batch_share
from mpr_crosslocale.methods.selective_alignment.schemas import digest,fields,render,validate_input
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits
from followup_rel_4lang.method_dev import stem_refinement_2x2 as method
from followup_rel_4lang.method_dev import direct_selective_rewrite as diagnostics
from followup_rel_4lang.method_dev.two_stage_v2 import pipeline,prompts
from followup_rel_4lang.method_dev.two_stage_v2.backend import Backend
import run_source_copy_rewrite as evaluator


class ExperimentBackend(Backend):
    @staticmethod
    def _mock(stage,user):
        if stage.startswith('selective'):
            data=json.JSONDecoder().raw_decode(user[user.index('{'):])[0]
            key='matches' if 'target_gui_candidates' in data else 'translations'
            return json.dumps({key:{r['span_id']:None for r in data['referents']}})
        return Backend._mock(stage,user)


def record(row,result,refs,inventory,cell,mock):
    out=result.pop('output')
    if out!={**fields(row),'question_stem':out['question_stem']} or any(e['field']!='question_stem' for e in result['edits']):raise ValueError('Options changed')
    if apply_edits(row,result['edits'])!=out:raise ValueError('Non-span context changed')
    return {**row,**result,'question_stem':out['question_stem'],'options':dict(row['options']),
        'modified_question':render(out),'diffs':diagnostics.diff_fields(row,out),'diagnostics':diagnostics.diagnostics(row,out),
        'extracted_referents':refs,'inventory_status':inventory['status'],'condition':cell,
        'execution_mode':'mock' if mock else 'gpu','oracle_span':False,'gold_target_used':False}


def replay_baseline(row,refs,inventory,attempts):
    queue=list(attempts)
    def backend(stage,role,system,user):
        if not queue:raise ValueError('Missing original matching call')
        previous=queue.pop(0)
        if (stage,role,system,user)!=(previous['stage'],previous['role'],previous['system_prompt'],previous['user_prompt']):raise ValueError('Original matching prompt differs')
        return previous
    result=pipeline.selective(row,refs,backend,inventory)
    if queue:raise ValueError('Unused original matching call')
    return result


def prepare(output,mock):
    source=ROOT/'artifacts/two_stage_v2_hybrid/screen'
    done=json.loads((source/'COMPLETE.json').read_text());parent=json.loads((source.parent/'contract.json').read_text())
    if resolved_config(ROOT/'configs/two_stage_v2_hybrid.json')!=parent['config']:raise ValueError('Pinned config/model cache changed')
    baseline=ROOT/'artifacts/stem_only_gui_screen_v1';bd=json.loads((baseline/'COMPLETE.json').read_text());bc=json.loads((baseline/'contract.json').read_text())
    if done['execution_mode']!='gpu' or bd['execution_mode']!='gpu' or bd['contract_sha256']!=digest(bc):raise ValueError('Completed GPU Screen baseline required')
    for filename,sha in parent['source_hashes'].items():
        if hashlib.sha256((REPO/filename).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen source changed: '+filename)
    for filename,sha in bc['source_sha256'].items():
        if hashlib.sha256(Path(filename).read_bytes()).hexdigest()!=sha:raise ValueError('Baseline raw source changed: '+filename)
    rows=read(source/'inputs.jsonl')
    if len(rows)!=288 or digest(rows)!=json.loads((source/'plan.json').read_text())['input_sha256']:raise ValueError('Unexpected Screen input')
    for row in rows:validate_input(row)
    unique(rows)
    old=unique(read(baseline/'rewritten.jsonl'))
    invpath=Path(done['inventory'])/'inventories.jsonl';extpath=Path(done['extract_stem'])/'extractions.jsonl'
    inv={r['image_sha256']:r for r in read(invpath)};ext={r['source_key']:r for r in read(extpath)}
    hybridpath=Path(done['rewrite'])/'TS_QSEL_OFULL_GUI_AUTO.jsonl';hybrid=unique(read(hybridpath))
    if set(old)!=set(hybrid) or set(old)!={r['pair_id'] for r in rows}:raise ValueError('Baseline coverage differs')
    baseline_rows=[];seed_calls=[]
    for row in rows:
        p=row['pair_id'];ex=ext[digest(prompts.extraction_payload(row,stem_only=True))]
        if ex['referents']!=old[p]['extracted_referents']:raise ValueError('Baseline source spans differ')
        calls=[a for a in hybrid[p]['attempts'] if a['component']=='stem_alignment']
        result=replay_baseline(row,ex['referents'],inv[row['image_sha256']],calls)
        if result['output']!=fields(old[p]):raise ValueError('M0 baseline replay differs')
        seed_calls+=calls
        baseline_rows.append(record(row,result,ex['referents'],inv[row['image_sha256']],'E0_M0',mock))
    predictions_path=Path(bd['predictions'])/'predictions.jsonl';predictions=read(predictions_path)
    if set(unique(predictions))!=set(old):raise ValueError('Baseline predictions incomplete')
    visual_contract_path=ROOT/'artifacts/visual_source_copy_rewrite_screen_v1/contract.json';vc=json.loads(visual_contract_path.read_text())
    if parent['config']['downstream']!=vc['downstream'] or bc['downstream']!=vc['downstream']:raise ValueError('Downstream profiles differ')
    labels_path=ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl';labels=unique(read(labels_path))
    if digest(labels)!=parent['base_data_contract']['labels']:raise ValueError('Labels changed')
    sources=[Path(__file__),ROOT/'stem_refinement_2x2.py',ROOT/'two_stage_v2/pipeline.py',ROOT/'two_stage_v2/prompts.py',
        ROOT/'two_stage_v2/backend.py',ROOT/'visual_rewrite_backend.py',ROOT/'direct_selective_rewrite.py',ROOT/'exact_batch_reuse.py',
        ROOT/'scripts/run_source_copy_rewrite.py',ROOT/'scripts/run_overnight_two.py',ROOT/'scripts/run_stem_only_gui.py',
        source/'inputs.jsonl',source/'COMPLETE.json',source.parent/'contract.json',source/'plan.json',ROOT/'configs/two_stage_v2_hybrid.json',
        baseline/'contract.json',baseline/'COMPLETE.json',baseline/'rewritten.jsonl',predictions_path,
        invpath,extpath,hybridpath,visual_contract_path,labels_path,
        ROOT/'artifacts/dataset_audit/oracle_spans_DIAGNOSTIC_ONLY.jsonl',
        ROOT.parent/'results/rstem_ropts_20261110/qwen3/raw/run_contract.json',
        ROOT.parent/'results/rstem_ropts_20261110/qwen3/raw/predictions.jsonl.gz']
    sources+=list((REPO/'01_code/src/mpr_crosslocale/methods/selective_alignment').glob('*.py'))
    sources += [REPO/'01_code/src/mpr_crosslocale/models/qwen25vl.py',REPO/'01_code/src/mpr_crosslocale/models/qwen3_memory.py',REPO/'01_code/src/mpr_crosslocale/inference/prompts.py']
    for s in vc['reuse_sources']:sources.append(Path(s['path']))
    for r in {r['image_sha256']:r for r in rows}.values():
        if hashlib.sha256((REPO/r['image_path']).read_bytes()).hexdigest()!=r['image_sha256']:raise ValueError('Image changed')
    contract={'version':'stem-refinement-screen-2x2-v1','execution_mode':'mock' if mock else 'gpu',
        'config':parent['config'],'inference_config':vc['config'],'downstream':vc['downstream'],'seed':parent['config']['seed'],
        'labels_sha256':parent['base_data_contract']['labels'],'oracle_sha256':parent['base_data_contract']['oracle'],
        'inputs_sha256':digest(rows),'pairs':len(rows),'primary_pairs':sum(labels[r['pair_id']]['split']=='main' and r['pair_id']!=EXCLUDED for r in rows),
        'semantic_items_primary':20,'inventory_images':len(inv),'source_stems':len(ext),'cells':{k:list(v) for k,v in method.CELLS.items()},
        'inventory_path':str(invpath),'legacy_extraction_path':str(extpath),'legacy_reuse_sources':vc['reuse_sources'],
        'prompt_sha256':{'E0':digest(prompts.EXTRACT_STEM_SYSTEM),'E1':digest(method.EXTRACT_SYSTEM),'M0':digest(prompts.SELECTIVE_GUI_SYSTEM),'M1':digest(method.MATCH_SYSTEM)},
        'source_sha256':{str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        'baseline_replay_pairs':len(baseline_rows),'baseline_predictions_source':str(predictions_path),
        'policy':'Screen only, same 288-row ordered batches including 48 pilot companions; primary 240. Frozen inventory reused. E1 shared by both matchers. Same spans shared within extractor. One structure repair; whole-response fallback unchanged. No gold method inputs.'}
    output.mkdir(parents=True,exist_ok=True);target=output/'contract.json'
    if target.exists() and json.loads(target.read_text())!=contract:raise ValueError('Frozen plan changed: choose fresh output directory')
    write(target,contract);jsonl(output/'inputs.jsonl',rows)
    legacy=output/'extraction/E0';legacy.mkdir(parents=True,exist_ok=True);jsonl(legacy/'extractions.jsonl',list(ext.values()));(legacy/'COMPLETE').write_text('imported\n')
    for cell in method.CELLS:
        work=output/cell;work.mkdir(exist_ok=True);jsonl(work/'inputs.jsonl',rows)
        write(work/'contract.json',{'config':vc['config'],'downstream':vc['downstream'],'seed':contract['seed'],
            'execution_mode':contract['execution_mode'],'inputs_sha256':digest(rows),'labels_sha256':contract['labels_sha256'],
            'reuse_sources':[],'parent_sha256':digest(contract),'condition':cell})
    base=output/'E0_M0/rewrite/attempt_import';base.mkdir(parents=True,exist_ok=True);jsonl(base/'rewritten.jsonl',baseline_rows);(base/'COMPLETE').write_text('imported\n')
    base=output/'E0_M0/infer/attempt_import';(base/'evaluation').mkdir(parents=True,exist_ok=True)
    imported=[]
    for row in predictions:
        r={**row,'condition':'E0_M0','batch_id':'E0_M0:'+row['batch_id'],'cache_hit':True,'new_batch_runtime_ms':0,
            'reuse_provenance':{'source':str(predictions_path),'batch_id':row['batch_id']}}
        if mock:r.update(execution_mode='mock',generated_text='A',parsed_generated_label='A',prompt_tokens=0,output_tokens=0,batch_runtime_ms=0,peak_reserved_bytes=None)
        imported.append(r)
    jsonl(base/'evaluation/predictions.jsonl',imported);(base/'COMPLETE').write_text('imported\n')
    if not mock:
        cache=output/'cache';cache.mkdir(exist_ok=True)
        for call in seed_calls:
            path=cache/(call['cache_key']+'.json')
            if not path.exists():write(path,call)
    return contract


def latest(work,stage):
    done=sorted(p for p in (work/stage).glob('attempt_*') if (p/'COMPLETE').exists())
    if not done:raise ValueError('Dependency incomplete '+stage)
    return done[-1]


def extract_stage(output,attempt,mock):
    c=json.loads((output/'contract.json').read_text());rr=read(output/'inputs.jsonl')
    if not mock:budget(c['config'])
    backend=ExperimentBackend(c['config'],REPO,output/'cache',mock);attempt.mkdir(parents=True);started=time.perf_counter()
    queue=sorted({digest(prompts.extraction_payload(r,stem_only=True)):r for r in rr}.items());complete=False
    try:
        with (attempt/'extractions.jsonl').open('w') as f:
            for i,(key,row) in enumerate(queue,1):
                result={'source_key':key,'scope':'question_stem',**method.extract(row,backend)}
                f.write(json.dumps(result,ensure_ascii=False)+'\n');f.flush();print(f'EXTRACT E1 {i}/{len(queue)} {result["status"]}',flush=True)
        complete=True
    finally:save_cost(attempt,backend,started,complete)
    (attempt/'COMPLETE').write_text('complete\n')


def extraction(output,e):
    folder=output/'extraction'/f'E{e}'
    path=folder/'extractions.jsonl' if e==0 else latest(output/'extraction','E1')/'extractions.jsonl'
    return {r['source_key']:r for r in read(path)}


def rewrite_stage(output,cell,attempt,mock):
    c=json.loads((output/'contract.json').read_text());rows=read(output/'inputs.jsonl');e,m=method.CELLS[cell]
    if not mock:budget(c['config'])
    backend=ExperimentBackend(c['config'],REPO,output/'cache',mock);attempt.mkdir(parents=True);started=time.perf_counter();complete=False
    inventories={r['image_sha256']:r for r in read(Path(c['inventory_path']))};extracted=extraction(output,e)
    try:
        with (attempt/'rewritten.jsonl').open('w') as f:
            for i,row in enumerate(rows,1):
                refs=extracted[digest(prompts.extraction_payload(row,stem_only=True))]['referents'];inv=inventories[row['image_sha256']]
                result=pipeline.selective(row,refs,backend,inv) if m==0 else method.selective(row,refs,backend,inv)
                rr=record(row,result,refs,inv,cell,mock)
                f.write(json.dumps(rr,ensure_ascii=False)+'\n');f.flush();print(f'REWRITE {cell} {i}/{len(rows)} {rr["status"]}',flush=True)
        complete=True
    finally:save_cost(attempt,backend,started,complete)
    (attempt/'COMPLETE').write_text('complete\n')


def save_cost(attempt,backend,started,complete):
    write(attempt/'calls.json',backend.calls);write(attempt/'cost.json',{'complete':complete,'wall_seconds':time.perf_counter()-started,
        'calls':len(backend.calls),'cache_hits':sum(c['cache_hit'] for c in backend.calls),
        'new_runtime_ms':sum(c['runtime_ms'] for c in backend.calls if not c['cache_hit'])})


def infer_stage(output,cell,attempt,mock):
    c=json.loads((output/'contract.json').read_text());work=output/cell;attempt.mkdir(parents=True);view=attempt/'view';view.mkdir()
    contract=json.loads((work/'contract.json').read_text())
    fingerprint=evaluator.VisualRewriteBackend(c['inference_config'],REPO,output/'cache',mock)
    env={'software':fingerprint.software,'hardware':fingerprint.hardware};write(attempt/'environment.json',env)
    sources=[] if mock else list(c['legacy_reuse_sources'])
    if not mock:
        for other in method.CELLS:
            for previous in sorted((output/other/'infer').glob('attempt_*')):
                path=previous/'evaluation/predictions.jsonl';ep=previous/'environment.json'
                if previous==attempt or not path.exists() or not ep.exists() or json.loads(ep.read_text())!=env:continue
                complete=completed_batches(path)
                if not complete:continue
                pp=view/f'reuse_{len(sources):04d}.jsonl';jsonl(pp,complete)
                sources.append({'path':str(pp),'downstream':c['downstream'],'seed':c['seed'],'environment':env})
    contract['reuse_sources']=sources;write(view/'contract.json',contract);jsonl(view/'inputs.jsonl',read(output/'inputs.jsonl'))
    evaluator.CONDITION=cell;evaluator.infer(view,latest(work,'rewrite'),attempt/'evaluation',mock)
    (attempt/'COMPLETE').write_text('complete\n')


def summarize(output,mock):
    if mock:write(output/'results.json',{'execution_mode':'mock','empirical':False});return
    c=json.loads((output/'contract.json').read_text());labels=unique(read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels)!=c['labels_sha256']:raise ValueError('Labels changed')
    original=unique(read(output/'inputs.jsonl'));ids=sorted(p for p in original if labels[p]['split']=='main' and p!=EXCLUDED)
    if len(ids)!=240:raise ValueError('Primary denominator changed')
    values={};quality={};cost={};rewrites={}
    inv=unique_by_image(read(Path(c['inventory_path'])));inventory_calls=call_map([inv[s] for s in {original[p]['image_sha256'] for p in ids}])
    for cell,(e,m) in method.CELLS.items():
        rr=unique(read(latest(output/cell,'rewrite')/'rewritten.jsonl'));pp=read(latest(output/cell,'infer')/'evaluation/predictions.jsonl');pred=unique(pp)
        if set(rr)!=set(original) or set(pred)!=set(original):raise ValueError('Incomplete cell')
        values[cell]={p:int(pred[p]['status']=='success' and pred[p]['parsed_generated_label']==labels[p]['gold_answer']) for p in ids};rewrites[cell]=rr
        quality[cell]={'changed':sum(fields(rr[p])!=fields(original[p]) for p in ids),'status':dict(Counter(rr[p]['status'] for p in ids)),
            'errors':dict(Counter(x for p in ids for x in rr[p]['errors']))}
        ex=extraction(output,e);extract_calls=call_map([ex[digest(prompts.extraction_payload(original[p],stem_only=True))] for p in ids]);match_calls=call_map([rr[p] for p in ids]);answer=batch_share(pp,lambda r:r['pair_id'] in ids)
        cost[cell]={'inventory_seconds':call_seconds(inventory_calls),'extraction_seconds':call_seconds(extract_calls),
            'matching_seconds':call_seconds(match_calls),'answer_seconds':answer['seconds'],
            'cold_total_seconds':call_seconds(inventory_calls)+call_seconds(extract_calls)+call_seconds(match_calls)+answer['seconds'],
            'answer_reused_pairs_all':sum(r.get('cache_hit',False) for r in pp)}
    for left,right in [('E0_M0','E0_M1'),('E1_M0','E1_M1')]:
        if any(rewrites[left][p]['extracted_referents']!=rewrites[right][p]['extracted_referents'] for p in original):raise ValueError('Matcher cells received different source spans')
    contrasts={cell:paired_bootstrap(v,values['E0_M0'],labels,20261115,10000) for cell,v in values.items() if cell!='E0_M0'}
    source_annotations=read(ROOT/'artifacts/dataset_audit/oracle_spans_DIAGNOSTIC_ONLY.jsonl')
    if digest(source_annotations)!=c['oracle_sha256']:raise ValueError('Post-hoc annotation changed')
    annotations=unique(source_annotations);extract_quality={}
    for e in (0,1):
        ex=extraction(output,e);gold=found=matched=0
        for p in ids:
            g={(s['start'],s['end']) for s in annotations[p]['referents'] if s['field']=='question_stem'}
            f={(s['start'],s['end']) for s in ex[digest(prompts.extraction_payload(original[p],stem_only=True))]['referents'] or []}
            gold+=len(g);found+=len(f);matched+=len(g&f)
        pr=matched/found if found else 0;rc=matched/gold if gold else 0
        extract_quality[f'E{e}']={'precision':pr,'recall':rc,'f1':2*pr*rc/(pr+rc) if pr+rc else 0,
            'gold_spans':gold,'predicted_spans':found,'matched_spans':matched,'scope':'pair-weighted source stem exact-boundary diagnostic; never method input'}
    refs={}
    rdir=ROOT.parent/'results/rstem_ropts_20261110/qwen3/raw';rcontract=json.loads((rdir/'run_contract.json').read_text())
    if rcontract['model_config']!=c['downstream']['model_config'] or rcontract['system_prompt']!=c['downstream']['system_prompt']:raise ValueError('R_stem model/system differs')
    with gzip.open(rdir/'predictions.jsonl.gz','rt') as f:
        reference=unique([r for r in map(json.loads,f) if r['pair_id'] in ids and r['condition']=='R_stem'])
    if set(reference)!=set(ids):raise ValueError('R_stem references missing')
    for p,r in reference.items():
        if r['gold_answer']!=labels[p]['gold_answer'] or r['experiment_fingerprint']!=rcontract['experiment_fingerprint']:raise ValueError('R_stem paired identity differs')
    refs['R_stem']={p:int(reference[p]['status']=='success' and reference[p]['parsed_generated_label']==labels[p]['gold_answer']) for p in ids}
    oldpred=read(Path(c['legacy_reuse_sources'][0]['path']));op=unique([r for r in oldpred if r['condition']=='O' and r['pair_id'] in ids])
    if set(op)!=set(ids):raise ValueError('O predictions missing')
    refs['O']={p:int(op[p]['status']=='success' and op[p]['parsed_generated_label']==labels[p]['gold_answer']) for p in ids}
    factorial={
        'extractor_main_effect':paired_bootstrap({p:(values['E1_M0'][p]+values['E1_M1'][p])/2 for p in ids},{p:(values['E0_M0'][p]+values['E0_M1'][p])/2 for p in ids},labels,20261115,10000),
        'matcher_main_effect':paired_bootstrap({p:(values['E0_M1'][p]+values['E1_M1'][p])/2 for p in ids},{p:(values['E0_M0'][p]+values['E1_M0'][p])/2 for p in ids},labels,20261115,10000),
        'interaction':paired_bootstrap({p:values['E1_M1'][p]-values['E1_M0'][p] for p in ids},{p:values['E0_M1'][p]-values['E0_M0'][p] for p in ids},labels,20261115,10000)}
    result={'execution_mode':'gpu','development_only':True,'primary_pairs':240,'items':20,'correct':{cell:sum(v.values()) for cell,v in values.items()},
        'contrasts_vs_baseline':contrasts,'factorial':factorial,'quality':quality,'logical_recipe_cost':cost,'contract_sha256':digest(c),
        'source_extraction_quality':extract_quality,'reference_correct':{k:sum(v.values()) for k,v in refs.items()},
        'contrasts_vs_R_stem':{cell:paired_bootstrap(v,refs['R_stem'],labels,20261115,10000) for cell,v in values.items()},
        'by_gui':{gui:{'n':sum(original[p]['gui_language']==gui for p in ids),'correct':{cell:sum(v[p] for p in ids if original[p]['gui_language']==gui) for cell,v in values.items()}} for gui in ('en','zh','th','ru')}}
    write(output/'results.json',result)
    lines=['# Stem extractor × matcher: Screen 2×2 결과','','기존에 반복 관찰한 Screen20문항240쌍의 탐색적 개발 실험. 실행288쌍 중 pilot48쌍은 주 분석 제외. Inventory/정답/이미지/보기 순서를 고정했다.','',
        '| 조건 | 정답/240 | 정확도 | 실제 수정 | 처음부터 계산 구간 |','| --- | ---: | ---: | ---: | ---: |']
    for cell in method.CELLS:lines.append(f"| {cell} | {result['correct'][cell]} | {result['correct'][cell]/240:.2%} | {quality[cell]['changed']} | {cost[cell]['cold_total_seconds']/60:.2f}분 |")
    lines+=['',f"기존 O {result['reference_correct']['O']}/240, 과거 R_stem {result['reference_correct']['R_stem']}/240. R_stem은 parallel stem referent를 쓰는 참고 조건이며 과거 batch4·RTX4090 실행이라 현재 batch3·B200와 실행 조건이 다르다. 새로 재추론하지 않았다.",'',
        '| Extractor | Precision | Recall | F1 |','| --- | ---: | ---: | ---: |']
    for e,q in extract_quality.items():lines.append(f"| {e} | {q['precision']:.2%} | {q['recall']:.2%} | {q['f1']:.2%} |")
    lines+=['','| 신규 조건 − E0_M0 | 차이 | 95% item bootstrap CI | 회복/회귀 |','| --- | ---: | --- | ---: |']
    for name,x in contrasts.items():lines.append(f"| {name} | {x['difference']*100:+.2f}pp | [{x['ci95'][0]*100:+.2f}, {x['ci95'][1]*100:+.2f}] | {x['recovery']}/{x['regression']} |")
    lines+=['','| Factorial contrast | 차이 | 95% CI |','| --- | ---: | --- |']
    for name,x in factorial.items():lines.append(f"| {name} | {x['difference']*100:+.2f}pp | [{x['ci95'][0]*100:+.2f}, {x['ci95'][1]*100:+.2f}] |")
    lines+=['','E/M 주 효과는 다른 factor 두 수준에 걸친 평균이며 interaction은(E1M1−E1M0)−(E0M1−E0M0)다. Matcher factor는 프롬프트와 출력 표현을 함께 바꾸므로 ID 하나의 순수 효과라고 단정하지 않는다. 모든 CI는 다중 비교 보정 전 탐색 구간이다. 기존 정답의 회귀와 실패를 분모에 포함했다. 계산 구간은 cached 호출도 원래 비용으로 청구하며 모델 적재를 제외한다. 실제 추가 실행 비용은 각 stage cost.json과 COMPLETE.json에 있다.','',
        '## 처리 상태','', '```json',json.dumps(quality,ensure_ascii=False,indent=2),'```','']
    (output/'REPORT_KO.md').write_text('\n'.join(lines))


def unique_by_image(rows):return {r['image_sha256']:r for r in rows}


def readiness(output):
    """CPU-only input estimates and weights/KV audit; never a GPU smoke test."""
    from transformers import AutoTokenizer
    from search_pipeline import oom_audit
    c=json.loads((output/'contract.json').read_text());config=c['config']
    tokenizer=AutoTokenizer.from_pretrained(config['models']['text']['path'],local_files_only=True)
    rr=read(output/'inputs.jsonl');ex=extraction(output,0);inv=unique_by_image(read(Path(c['inventory_path'])))
    maxima={'E1':0,'M0':0,'M1':0,'M1_full_stem_probe':0}
    def count(system,user):
        text=tokenizer.apply_chat_template([{'role':'system','content':system},{'role':'user','content':user}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
        return len(tokenizer.encode(text,add_special_tokens=False))
    for row in rr:
        maxima['E1']=max(maxima['E1'],count(method.EXTRACT_SYSTEM,prompts.extraction_user(row,stem_only=True)))
        refs=ex[digest(prompts.extraction_payload(row,stem_only=True))]['referents'] or []
        inventory=inv[row['image_sha256']]
        if refs:
            maxima['M0']=max(maxima['M0'],count(prompts.SELECTIVE_GUI_SYSTEM,prompts.selective_user(row,refs,inventory)))
            maxima['M1']=max(maxima['M1'],count(method.MATCH_SYSTEM,method.match_user(row,refs,inventory)))
        probe=[{'span_id':f'question_stem:0:{len(row["question_stem"])}','field':'question_stem','text':row['question_stem']}]
        maxima['M1_full_stem_probe']=max(maxima['M1_full_stem_probe'],count(method.MATCH_SYSTEM,method.match_user(row,probe,inventory)))
    estimates={k:v+(768 if k=='E1' else 512)+200 for k,v in maxima.items()}
    if max(estimates.values())>config['max_input_tokens']:raise ValueError('Input/repair estimate exceeds fixed budget: '+str(estimates))
    memory=oom_audit({'models':{'translator':config['models']['text'],'inventory':config['models']['inventory']}},
        {'max_input_tokens':config['max_input_tokens'],'max_new_tokens':768,'min_free_gpu_gib':40},True)
    result={'cpu_only':True,'baseline_replay_pairs':c['baseline_replay_pairs'],'frozen_inventory_images':c['inventory_images'],
        'initial_token_max':maxima,'repair_upper_estimate':estimates,'max_input_tokens':config['max_input_tokens'],
        'memory_estimate':memory,'gpu_inference_started':False,
        'note':'Estimates use frozen E0 spans and a whole-stem probe. E1 spans are unknown before generation; runtime checks actual input and refuses silent truncation. Weights/KV are not a peak-memory guarantee.'}
    write(output/'readiness.json',result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');p.add_argument('--mock',action='store_true');p.add_argument('--output-dir',type=Path)
    p.add_argument('--worker',choices=('extract','rewrite','infer'));p.add_argument('--cell',choices=list(method.CELLS));p.add_argument('--attempt',type=Path);args=p.parse_args()
    output=(args.output_dir or ROOT/'artifacts'/('stem_refinement_2x2_screen_v1_mock' if args.mock else 'stem_refinement_2x2_screen_v1')).resolve()
    if not output.is_relative_to(REPO):p.error('Output must remain inside repository')
    if args.worker:
        c=json.loads((output/'contract.json').read_text())
        if c['execution_mode']!=('mock' if args.mock else 'gpu') or digest(read(output/'inputs.jsonl'))!=c['inputs_sha256']:raise ValueError('Worker mode/inputs changed')
        for name,sha in c['source_sha256'].items():
            if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen source changed: '+name)
        if args.worker=='extract':extract_stage(output,args.attempt,args.mock)
        elif args.worker=='rewrite':rewrite_stage(output,args.cell,args.attempt,args.mock)
        else:infer_stage(output,args.cell,args.attempt,args.mock)
        return
    with (ROOT/'artifacts'/('search_pipeline_mock.lock' if args.mock else 'search_pipeline_gpu.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        c=prepare(output,args.mock)
        ready=readiness(output)
        if not args.run:print(json.dumps({'prepared':str(output),'primary_pairs':c['primary_pairs'],'baseline_replayed':c['baseline_replay_pairs'],'initial_token_max':ready['initial_token_max'],'gpu_started':False}),flush=True);return
        if (output/'COMPLETE.json').exists():print('REUSE COMPLETE',output,flush=True);return
        started=time.perf_counter()
        tasks=[('extract',None,output/'extraction/E1')]+[(stage,cell,output/cell/stage) for cell in ('E0_M1','E1_M0','E1_M1') for stage in ('rewrite','infer')]
        for stage,cell,directory in tasks:
            directory.mkdir(parents=True,exist_ok=True);attempts=sorted(directory.glob('attempt_*'))
            if any((a/'COMPLETE').exists() for a in attempts):print('REUSE',stage,cell,flush=True);continue
            attempt=directory/f'attempt_{len(attempts)+1:04d}'
            cmd=[sys.executable,'-u',str(Path(__file__)), '--output-dir',str(output),'--worker',stage,'--attempt',str(attempt)]
            if cell:cmd+=['--cell',cell]
            if args.mock:cmd.append('--mock')
            print(time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'RUN',stage,cell,flush=True)
            subprocess.run(cmd,check=True)
            if not (attempt/'COMPLETE').exists():raise ValueError('Missing stage marker')
        summarize(output,args.mock);write(output/'COMPLETE.json',{'execution_mode':c['execution_mode'],'contract_sha256':digest(c),'wall_seconds':time.perf_counter()-started})
        print('COMPLETE',output,flush=True)


if __name__=='__main__':main()
