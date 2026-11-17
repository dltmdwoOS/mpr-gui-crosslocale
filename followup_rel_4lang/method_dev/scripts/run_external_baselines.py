"""Sequential, resumable local GUI adaptations of Translate-Test and CLP."""
import argparse
import copy
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[3]; ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(REPO/'01_code/src'),str(REPO),str(Path(__file__).parent)]
from run_stem_only_gui import read,write,jsonl,unique
from run_stem_refinement_2x2 import latest,save_cost
from run_overnight_two import completed_batches
from run_two_stage_v2 import budget
from mpr_crosslocale.methods.selective_alignment.schemas import digest,validate_input,fields,render
from mpr_crosslocale.models.qwen25vl import Qwen25VLAdapter
from followup_rel_4lang.method_dev.two_stage_v2.backend import Backend
from followup_rel_4lang.method_dev import external_baselines as method
import run_source_copy_rewrite as evaluator

COHORTS=('screen','selection','internal_evaluation')


class TextBackend(Backend):
    @staticmethod
    def _mock(stage,user):
        if stage=='alignment':return 'English interpretation for a CPU-only mock.'
        data=json.loads(user.split('\n\nPrevious output',1)[0])
        return json.dumps({'question_stem':data['question_stem'],'options':data['options']},ensure_ascii=False)


class CLPAdapter(Qwen25VLAdapter):
    @staticmethod
    def build_messages(input_row,prompt_profile,system_prompt=None):
        return input_row['messages']


def verify(output):
    c=json.loads((output/'contract.json').read_text())
    for path,sha in c['source_sha256'].items():
        if hashlib.sha256((REPO/path).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen source changed: '+path)
    for cohort in c['cohorts']:
        if digest(read(output/cohort/'inputs.jsonl'))!=c['inputs_sha256'][cohort]:raise ValueError('Input changed')
    return c


def prepare(output,mock=False,smoke=False):
    specpath=ROOT/'configs/external_baselines_v1.json';spec=json.loads(specpath.read_text())
    base=ROOT/'artifacts/e1_stem_full_dev_v1';old=json.loads((base/'contract.json').read_text())
    if json.loads((base/'COMPLETE.json').read_text())['contract_sha256']!=digest(old):raise ValueError('8B baseline incomplete')
    config=copy.deepcopy(old['config']);config['version']=spec['version'];config['output_tokens']=spec['output_tokens']
    config['models']={'text':config['models']['text'],'editor_vlm':config['models']['inventory']}
    if config['models']['text']['model_id']!=spec['translation_backbone'] or config['downstream']['model_config']['model_id']!=spec['evaluation_backbone']:raise ValueError('Pinned backbone differs')
    clp=copy.deepcopy(config['downstream']);clp['batch_size']=spec['solver_batch_size'];clp['score_labels']=False
    clp['model_config']['prompt_profile']='external_clp_dialogue'
    clp['model_config']['generation'].update(max_new_tokens=spec['solver_max_new_tokens'],use_cache=True,logits_to_keep=1)
    clp['system_prompt']=method.CLP_SOLVER_SYSTEM
    plan=ROOT/'artifacts/search_pipeline_v1';identity=json.loads((plan/'data_contract.json').read_text());manifest=json.loads((plan/'plan/manifest.json').read_text())
    if digest(manifest)!=identity['plan'] or identity['labels']!=old['labels_sha256']:raise ValueError('Dataset lock differs')
    captures=[Path(__file__),ROOT/'external_baselines.py',specpath,base/'contract.json',base/'COMPLETE.json',
        ROOT/'configs/external_baselines_sources.json',plan/'data_contract.json',plan/'plan/manifest.json',
        ROOT/'scripts/run_source_copy_rewrite.py',ROOT/'scripts/run_overnight_two.py',ROOT/'scripts/run_two_stage_v2.py',
        ROOT/'scripts/run_stem_refinement_2x2.py',ROOT/'scripts/run_stem_only_gui.py',ROOT/'two_stage_v2/backend.py',
        ROOT/'visual_rewrite_backend.py',ROOT/'source_copy_rewrite.py',ROOT/'direct_selective_rewrite.py',ROOT/'exact_batch_reuse.py',
        REPO/'01_code/src/mpr_crosslocale/models/qwen25vl.py',REPO/'01_code/src/mpr_crosslocale/models/qwen3_memory.py',
        REPO/'01_code/src/mpr_crosslocale/inference/prompts.py']
    captures += list((REPO/'01_code/src/mpr_crosslocale/methods/selective_alignment').glob('*.py'))
    inputs={};descriptors={}
    for cohort in COHORTS:
        path=plan/'plan'/f'{cohort}.jsonl';rows=read(path);captures.append(path)
        if digest(rows)!=manifest['cohorts'][cohort]['inputs_sha256']:raise ValueError('Original cohort changed')
        if smoke:
            if cohort!='screen':continue
            rows=[next(r for r in rows if r['source_language']==lang) for lang in ('en','ru','zh')]
        for row in rows:validate_input(row)
        unique(rows);inputs[cohort]=rows
        d=old['descriptors'][cohort]
        methodpred=Path(d['infer'])/'evaluation/predictions.jsonl' if cohort=='screen' else latest(base/cohort/'E1_M0','infer')/'evaluation/predictions.jsonl'
        originalpred=Path(d['O_pred']);captures += [methodpred,originalpred]
        descriptors[cohort]={'O_predictions':str(originalpred),'E1_M0_predictions':str(methodpred)}
    for row in {r['image_sha256']:r for rr in inputs.values() for r in rr}.values():
        path=(REPO/row['image_path']).resolve()
        if not path.is_relative_to(Path('/home/jovyan/seungjae')) or hashlib.sha256(path.read_bytes()).hexdigest()!=row['image_sha256']:raise ValueError('Image changed')
    oom=[]
    for role in ('text','editor_vlm'):
        path=Path(config['models'][role]['path']);model=json.loads((path/'config.json').read_text());text=model.get('text_config',model)
        index=json.loads((path/'model.safetensors.index.json').read_text())
        if any(not (path/name).exists() for name in set(index['weight_map'].values())):raise ValueError('Checkpoint incomplete')
        kv=2*text['num_hidden_layers']*text['num_key_value_heads']*text['head_dim']*2
        oom.append({'role':role,'weight_bytes':sum(p.stat().st_size for p in path.glob('*.safetensors')),
                    'kv_bytes_at_input4096_output512':kv*(4096+512)*(3 if role=='editor_vlm' else 1)})
    contract={'version':spec['version'],'execution_mode':'mock' if mock else 'gpu','smoke':smoke,
        'config':config,'clp_profile':clp,'seed':config['seed'],'labels_sha256':identity['labels'],
        'cohorts':list(inputs),'inputs_sha256':{k:digest(v) for k,v in inputs.items()},
        'pairs':{k:len(v) for k,v in inputs.items()},'descriptors':descriptors,'spec':spec,
        'prompt_sha256':{k:digest(getattr(method,k)) for k in ('TRANSLATE_SYSTEM','CLP_SOLVER_SYSTEM','CLP_SOLVER_USER')},
        'source_sha256':{str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in captures},
        'oom_components':oom,'oom_note':'Components, not a peak upper bound. One model per process, SDPA, BF16, channels_last_3d, batch3, logits_to_keep1. No all-step logits for CLP. No guarantee; GPU smoke checks actual peaks.'}
    output.mkdir(parents=True,exist_ok=True)
    if (output/'contract.json').exists() and json.loads((output/'contract.json').read_text())!=contract:raise ValueError('Frozen run differs; use fresh output directory')
    write(output/'contract.json',contract)
    for cohort,rows in inputs.items():
        work=output/cohort;work.mkdir(exist_ok=True);jsonl(work/'inputs.jsonl',rows)
    return contract


def transform(output,stage,attempt,mock):
    c=verify(output)
    if not mock:budget(c['config'])
    backend=TextBackend(c['config'],REPO,output/'cache',mock);attempt.mkdir(parents=True);started=time.perf_counter();complete=False
    sources={digest(method.source_payload(row)):row for cohort in c['cohorts'] for row in read(output/cohort/'inputs.jsonl')}
    try:
        with (attempt/'transformations.jsonl').open('w') as f:
            for i,(key,row) in enumerate(sorted(sources.items()),1):
                result=method.translate(row,backend) if stage=='translate' else method.alignment(row,backend)
                record={'source_key':key,'source_input':method.source_payload(row),**result}
                f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush()
                if i==1 or i%10==0 or i==len(sources):print(f'{stage.upper()} {i}/{len(sources)} {result["status"]}',flush=True)
        complete=True
    finally:save_cost(attempt,backend,started,complete)
    (attempt/'COMPLETE').write_text('complete\n')


def inference(output,cohort,stage,attempt,mock):
    c=verify(output);rows=read(output/cohort/'inputs.jsonl');attempt.mkdir(parents=True);view=attempt/'view';view.mkdir()
    env_backend=Backend(c['config'],REPO,output/'cache',mock)
    env={'software':env_backend.software,'hardware':env_backend.hardware};write(attempt/'environment.json',env)
    condition=method.TT if stage=='infer_tt' else method.CLP
    profile=c['config']['downstream'] if stage=='infer_tt' else c['clp_profile']
    sources=[]
    if not mock:
        for previous in sorted((output/cohort/stage).glob('attempt_*')):
            path=previous/'evaluation/predictions.jsonl';ep=previous/'environment.json'
            if previous==attempt or not path.exists() or not ep.exists() or json.loads(ep.read_text())!=env:continue
            records=completed_batches(path)
            if records:
                p=view/f'reuse_{len(sources):04d}.jsonl';jsonl(p,records)
                sources.append({'path':str(p),'predictions':records,'downstream':profile,'seed':c['seed'],'environment':env})
    if stage=='infer_tt':
        write(view/'contract.json',{'config':c['config'],'downstream':profile,'seed':c['seed'],'execution_mode':c['execution_mode'],
                                  'labels_sha256':c['labels_sha256'],'inputs_sha256':digest(rows),'reuse_sources':sources})
        jsonl(view/'inputs.jsonl',rows)
        transformed={r['source_key']:r for r in read(latest(output,'translate')/'transformations.jsonl')}
        rewrite=view/'rewrite';rewrite.mkdir();rewritten=[]
        for row in rows:
            record=copy.deepcopy(transformed[digest(method.source_payload(row))]);record.pop('source_key');record.pop('source_input')
            rewritten.append(method.translation_record(row,record,mock))
        jsonl(rewrite/'rewritten.jsonl',rewritten)
        evaluator.CONDITION=condition;evaluator.infer(view,rewrite,attempt/'evaluation',mock)
    else:
        infer_clp(c,rows,latest(output,'alignment')/'transformations.jsonl',attempt,env,sources,mock)
    (attempt/'COMPLETE').write_text('complete\n')


def infer_clp(c,rows,alignment_path,attempt,environment,sources,mock):
    from types import SimpleNamespace
    import torch
    from followup_rel_4lang.method_dev.exact_batch_reuse import build_index,batch_key
    profile=c['clp_profile'];model=profile['model_config'];aligned={r['source_key']:r for r in read(alignment_path)}
    queue=[{'pair_id':r['pair_id'],'parallel_id':r['parallel_id'],
            'messages':method.solver_messages(r,aligned[digest(method.source_payload(r))]['alignment_text'],REPO)} for r in sorted(rows,key=lambda r:r['pair_id'])]
    images={r['pair_id']:r['image_sha256'] for r in rows};adapter=None;index={};conflicts=set();started=time.perf_counter()
    if not mock:
        from transformers import AutoProcessor
        processor=AutoProcessor.from_pretrained(c['config']['models']['editor_vlm']['path'],use_fast=True,min_pixels=model['min_pixels'],max_pixels=model['max_pixels'],local_files_only=True)
        for row in queue:row['rendered_prompt']=processor.apply_chat_template(row['messages'],tokenize=False,add_generation_prompt=True)
        index,conflicts=build_index(sources,profile,c['seed'],images,environment)
    destination=attempt/'evaluation';destination.mkdir();new=reused=0
    write(destination/'contract.json',{'execution_mode':c['execution_mode'],'downstream':profile,'queue_sha256':digest(queue),'condition':method.CLP,'seed':c['seed']})
    try:
        with (destination/'predictions.jsonl').open('w') as f:
            for start in range(0,len(queue),profile['batch_size']):
                batch=queue[start:start+profile['batch_size']];hit=None if mock else index.get(batch_key(profile,c['seed'],batch,images,environment))
                if mock:preds=[SimpleNamespace(raw_output='Mock reasoning.\nAnswer: A',rendered_prompt='MOCK',prompt_token_count=0,output_token_count=0) for _ in batch]
                elif hit:preds=[SimpleNamespace(raw_output=r['generated_text'],rendered_prompt=r['rendered_prompt'],prompt_token_count=r['prompt_tokens'],output_token_count=r['output_tokens']) for r in hit['rows']]
                else:
                    if adapter is None:
                        from transformers import set_seed
                        budget(c['config']);set_seed(c['seed']);torch.set_num_threads(3)
                        adapter=CLPAdapter(model_id=model['model_id'],revision=model['revision'],dtype=model['dtype'],attn_implementation=model['attn_implementation'],device_map='cuda:0',
                            processor_kwargs={'use_fast':True,'min_pixels':model['min_pixels'],'max_pixels':model['max_pixels']},model_family=model['model_family'],patch_embed_memory_format=model['patch_embed_memory_format'])
                        adapter.max_input_tokens=profile['max_input_tokens']
                    torch.cuda.reset_peak_memory_stats();t=time.perf_counter()
                    preds=adapter.generate_batch(batch,model['prompt_profile'],model['generation'],score_labels=False)
                    torch.cuda.synchronize();elapsed=(time.perf_counter()-t)*1000
                if mock:elapsed=0
                if hit:elapsed=hit['rows'][0]['batch_runtime_ms']
                reused+=len(batch) if hit else 0;new+=0 if hit else len(batch)
                for row,pred in zip(batch,preds,strict=True):
                    record={'pair_id':row['pair_id'],'parallel_id':row['parallel_id'],'condition':method.CLP,'execution_mode':c['execution_mode'],'status':'success',
                        'generated_text':pred.raw_output,'parsed_generated_label':method.parse_clp_answer(pred.raw_output),'rendered_prompt':pred.rendered_prompt,
                        'prompt_tokens':pred.prompt_token_count,'output_tokens':pred.output_token_count,'output_cap_hit':pred.output_token_count>=model['generation']['max_new_tokens'],
                        'batch_id':method.CLP+':'+str(start),'batch_size':len(batch),'batch_runtime_ms':elapsed,
                        'peak_reserved_bytes':None if mock else hit['rows'][0]['peak_reserved_bytes'] if hit else torch.cuda.max_memory_reserved(),
                        'cache_hit':bool(hit),'new_batch_runtime_ms':0 if hit else elapsed,
                        'reuse_provenance':{'source':hit['source'],'batch_id':hit['batch_id']} if hit else None}
                    f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush()
                print(f'CLP INFER {start+len(batch)}/{len(queue)} reused={bool(hit)}',flush=True)
    finally:
        write(destination/'cost.json',{'wall_seconds':time.perf_counter()-started,'new_rows':new,'reused_rows':reused,'conflicting_keys':len(conflicts)})
    (destination/'COMPLETE').write_text('complete\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');p.add_argument('--mock',action='store_true');p.add_argument('--smoke',action='store_true');p.add_argument('--output-dir',type=Path)
    p.add_argument('--worker',choices=('translate','alignment','infer_tt','infer_clp'));p.add_argument('--cohort',choices=COHORTS);p.add_argument('--attempt',type=Path);a=p.parse_args()
    output=(a.output_dir or ROOT/'artifacts'/('external_baselines_mock' if a.mock else 'external_baselines_smoke_v1' if a.smoke else 'external_baselines_v1')).resolve()
    if not output.is_relative_to(REPO):p.error('Output must remain in repository')
    if a.worker:
        c=verify(output)
        if a.mock!=(c['execution_mode']=='mock'):raise ValueError('Mode differs')
        if a.worker in ('translate','alignment'):transform(output,a.worker,a.attempt,a.mock)
        else:inference(output,a.cohort,a.worker,a.attempt,a.mock)
        return
    with (ROOT/'artifacts'/('search_pipeline_mock.lock' if a.mock else 'search_pipeline_gpu.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);c=prepare(output,a.mock,a.smoke)
        if not a.run:print('PREPARED',output,flush=True);return
        if (output/'COMPLETE.json').exists():print('REUSE COMPLETE',output,flush=True);return
        started=time.perf_counter()
        schedule=[(None,'translate'),*[(k,'infer_tt') for k in c['cohorts']],(None,'alignment'),*[(k,'infer_clp') for k in c['cohorts']]]
        for cohort,stage in schedule:
            parent=output if cohort is None else output/cohort;directory=parent/stage;directory.mkdir(parents=True,exist_ok=True);attempts=sorted(directory.glob('attempt_*'))
            if any((x/'COMPLETE').exists() for x in attempts):print('REUSE',cohort,stage,flush=True);continue
            attempt=directory/f'attempt_{len(attempts)+1:04d}'
            cmd=[sys.executable,'-u',str(Path(__file__)),'--output-dir',str(output),'--worker',stage,'--attempt',str(attempt)]
            if cohort:cmd+=['--cohort',cohort]
            if a.mock:cmd+=['--mock']
            print(time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'RUN',cohort,stage,flush=True);subprocess.run(cmd,check=True)
            if not (attempt/'COMPLETE').exists():raise ValueError('Stage incomplete')
        write(output/'COMPLETE.json',{'execution_mode':c['execution_mode'],'smoke':c['smoke'],'contract_sha256':digest(c),'latest_invocation_wall_seconds':time.perf_counter()-started})
        print('COMPLETE',output,flush=True)


if __name__=='__main__':main()
