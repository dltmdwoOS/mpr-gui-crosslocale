"""Run one registered candidate on probe/screen/selection; full sweeps are never implicit."""
import argparse,copy,hashlib,json,sys,time
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];sys.path[:0]=[str(REPO/'01_code/src'),str(Path(__file__).parent)]
from backend import TransformersBackend
from mpr_crosslocale.methods.selective_alignment.schemas import digest,fields,render,validate_input
from mpr_crosslocale.methods.selective_alignment.inventory import parse_inventory
from mpr_crosslocale.methods.selective_alignment.search import extract,rewrite,quoted_referents,BackendFailure,INVENTORY_RECIPES,EXTRACTION_RECIPES


class CachedBackend:
    def __init__(self,backend,config,cache,mock=False):
        self.backend=backend;self.config=config;self.cache=cache;self.mock=mock;self.calls=[]
        from mpr_crosslocale.inference.runtime import software_versions
        self.software=software_versions()
        source=REPO/'followup_rel_4lang/method_dev/scripts/backend.py'
        self.implementation_sha256=digest(source.read_text())
        self.hardware='CPU-MOCK'
        if not mock:
            import torch
            device=torch.cuda.get_device_properties(0)
            self.hardware={'gpu':device.name,'multiprocessors':device.multi_processor_count,'memory_bytes':device.total_memory}
    def __call__(self,stage,prompt,payload):
        role='inventory' if stage in ('inventory','ground_match','direct_visual_edit','vl_text_edit') else 'referent_extractor' if stage=='extract' else 'translator'
        spec=self.config['models'][role]
        key=digest({'stage':stage,'prompt':prompt,'payload':payload,'model':spec,'max_new_tokens':self.config['max_new_tokens'],
                    'backend':self.implementation_sha256,'software':self.software,'hardware':self.hardware,'mock':self.mock})
        path=self.cache/(key+'.json');cached=path.exists()
        if not self.mock and 'image_path' in payload:
            try:
                if hashlib.sha256((REPO/payload['image_path']).read_bytes()).hexdigest()!=payload['image_sha256']:raise ValueError('Image changed before cache lookup')
            except Exception as exc:raise BackendFailure(str(exc)) from exc
        if cached:data=json.loads(path.read_text())
        elif self.mock:
            if stage=='inventory':raw='{"visible_strings":[]}'
            elif stage=='extract':raw=json.dumps({'referents':[{k:r[k] for k in ('field','text','occurrence')} for r in quoted_referents({'question_stem':payload['fields']['question_stem'],'options':{k:payload['fields'][k] for k in 'ABCD'}})]})
            elif stage=='translate':raw=json.dumps({r['span_id']:'MOCK_'+r['text'] for r in payload['referents']})
            elif stage in ('match_text','ground_match'):raw=json.dumps({'matches':{r['span_id']:None for r in payload['referents']}})
            elif stage in ('TXT_FULL','GUI_FULL'):raw=json.dumps(payload['fields'])
            else:raw='{"edits":[]}'
            data={'raw_output':raw,'runtime_ms':0,'model_load_ms':0,'input_tokens':0,'output_tokens':0,'execution_mode':'mock'}
        else:
            started=time.perf_counter()
            try:
                raw=self.backend(stage,prompt,payload);data={**self.backend.calls[-1],'execution_mode':'gpu'}
            except Exception as exc:
                self.calls.append({'stage':stage,'cache_key':key,'cache_hit':False,'runtime_ms':(time.perf_counter()-started)*1000,'model_load_ms':None,
                    'input_tokens':None,'output_tokens':None,'execution_mode':'gpu','failure':type(exc).__name__+': '+str(exc),'runtime_scope':'failed call wall, load may be included'})
                raise BackendFailure(type(exc).__name__+': '+str(exc)) from exc
        if not cached:
            self.cache.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False)+'\n');tmp.replace(path)
        self.calls.append({**data,'stage':stage,'cache_key':key,'cache_hit':cached,'prompt_sha256':digest(prompt),'payload_sha256':digest(payload)})
        return data['raw_output']


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--spec',type=Path,required=True);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--cohort',choices=['probe','screen','selection'],default='probe');p.add_argument('--extractor',required=True)
    p.add_argument('--recipe',default='extraction');p.add_argument('--cache-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--mock',action='store_true');mode.add_argument('--gpu',action='store_true')
    limits=p.add_mutually_exclusive_group();limits.add_argument('--limit-items',type=int,default=1);limits.add_argument('--all-items',action='store_true');a=p.parse_args()
    if a.output_dir.exists():raise ValueError('Fresh output required')
    spec=json.loads(a.spec.read_text());config=json.loads(a.config.read_text());choice=spec['extractors'][a.extractor]
    if a.recipe!='extraction' and a.recipe not in spec['recipes']:raise ValueError('Unregistered recipe')
    if a.limit_items<1:raise ValueError('Positive item limit required')
    manifest=json.loads(a.plan.read_text());rows=[validate_input(json.loads(l)) for l in (a.plan.parent/(a.cohort+'.jsonl')).read_text().splitlines()]
    if digest(rows)!=manifest['cohorts'][a.cohort]['inputs_sha256'] or digest(spec)!=manifest['spec_sha256']:raise ValueError('Frozen search plan/input/spec mismatch')
    selected_ids=sorted({r['parallel_id'] for r in rows})
    if not a.all_items:selected_ids=selected_ids[:a.limit_items]
    rows=[r for r in rows if r['parallel_id'] in selected_ids]
    config=copy.deepcopy(config);config['max_new_tokens']=spec['max_new_tokens'];config['profile_calls']=False
    if choice['model']=='vl_text':config['models']['referent_extractor']=copy.deepcopy(config['models']['inventory'])
    inv=config['models']['inventory'];vlm=config['evaluation_vlm']
    if (inv['model_id'],inv['revision'])!=(vlm['model_id'],vlm['revision']):raise ValueError('Inventory must use evaluation VLM')
    if a.gpu:
        import torch
        torch.set_num_threads(3)
        if config['models']['inventory']['family']!='qwen3_vl':raise ValueError('Search v1 supports Qwen3-VL only; other VLM adapters are future work')
        for model in config['models'].values():
            path=Path(model['path']);index=path/'model.safetensors.index.json'
            if path.name!=model['revision'] or not index.is_file():raise ValueError('Pinned model snapshot unavailable: '+model['model_id'])
            if any(not (path/shard).is_file() for shard in set(json.loads(index.read_text())['weight_map'].values())):raise ValueError('Incomplete model snapshot')
    backend=CachedBackend(None if a.mock else TransformersBackend(config,REPO),config,a.cache_dir,a.mock)
    a.output_dir.mkdir(parents=True);start=time.perf_counter()
    import mpr_crosslocale.methods.selective_alignment.search as module
    contract={'execution_mode':'mock' if a.mock else 'gpu','cohort':a.cohort,'candidate_id':a.recipe,'extractor':a.extractor,'config':config,'spec_sha256':digest(spec),'plan_sha256':digest(manifest),
        'selected_item_ids':selected_ids,'input_sha256':digest(rows),'method_sha256':digest(Path(module.__file__).read_text()),'runner_sha256':digest(Path(__file__).read_text()),'backend_sha256':backend.implementation_sha256,'software':backend.software,
        'generation':'greedy, BF16, SDPA; method batch=1; non-thinking for fixed LM; no raw backbone surgery',
        'unreviewed_visual_evidence':a.recipe in ('GUI_TARGETED_VLM','GUI_DIRECT_VLM'),'option_order':list('ABCD')}
    (a.output_dir/'contract.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n')
    inventories={};extractions={};completed=False
    legacy=json.loads((REPO/'followup_rel_4lang/method_dev/configs/legacy_prompts.json').read_text())
    try:
        if a.recipe in INVENTORY_RECIPES:
            for row in rows:
                sha=row['image_sha256']
                if sha not in inventories:
                    try:inventories[sha]=parse_inventory(backend('inventory',legacy['prompts']['INVENTORY_SYSTEM_PROMPT'],{'image_path':row['image_path'],'image_sha256':sha}))
                    except BackendFailure:raise
                    except Exception as exc:inventories[sha]={**parse_inventory(''),'errors':[str(exc)]}
        if a.recipe=='extraction' or a.recipe in EXTRACTION_RECIPES:
            with (a.output_dir/'extractions.jsonl').open('w') as f:
                recorded=set()
                for row in rows:
                    key=digest({'source_language':row['source_language'],'fields':fields(row)})
                    identity=(row['parallel_id'],row['source_language'])
                    if identity in recorded:continue
                    recorded.add(identity)
                    try:result={'status':'success','referents':extract(row,backend,choice['prompt']),'error':None}
                    except BackendFailure:raise
                    except Exception as exc:result={'status':'failed','referents':[],'error':str(exc)}
                    extractions[key]=result;f.write(json.dumps({'pair_id':row['pair_id'],'parallel_id':row['parallel_id'],'source_language':row['source_language'],**result},ensure_ascii=False)+'\n');f.flush()
        if a.recipe!='extraction':
            with (a.output_dir/'rewritten.jsonl').open('w') as f:
                for row in rows:
                    key=digest({'source_language':row['source_language'],'fields':fields(row)})
                    extraction=extractions.get(key);refs=extraction['referents'] if extraction and extraction['status']=='success' else None
                    result=rewrite(row,a.recipe,backend,refs,inventories.get(row['image_sha256']))
                    if extraction and extraction['status']!='success':result['details']['extraction_error']=extraction['error']
                    out={**row,'condition':a.recipe,'candidate_id':a.recipe,'extracted_referents':refs,'extraction':extraction,'inventory':inventories.get(row['image_sha256']),
                        'edits':result['edits'],'generation_status':result['status'],'details':result['details'],'modified_question':render(result['output']),
                        'question_stem':result['output']['question_stem'],'options':{k:result['output'][k] for k in 'ABCD'},'execution_mode':contract['execution_mode']}
                    f.write(json.dumps(out,ensure_ascii=False)+'\n');f.flush()
        completed=True
    finally:
        (a.output_dir/'calls.json').write_text(json.dumps(backend.calls,ensure_ascii=False,indent=2)+'\n')
        unique={c['cache_key']:c for c in backend.calls};misses=[c for c in backend.calls if not c['cache_hit']]
        cost={'execution_mode':contract['execution_mode'],'wall_ms':(time.perf_counter()-start)*1000,'calls':len(backend.calls),'unique_calls':len(unique),'cache_hits':sum(c['cache_hit'] for c in backend.calls),
            'acquired_runtime_ms':sum(c['runtime_ms'] for c in misses),'acquired_model_load_ms':sum(c.get('model_load_ms',0) or 0 for c in misses),
            'standalone_unique_runtime_ms':sum(c['runtime_ms'] for c in unique.values()),'standalone_unique_input_tokens':sum(c['input_tokens'] or 0 for c in unique.values()),'standalone_unique_output_tokens':sum(c['output_tokens'] or 0 for c in unique.values()),
            'failed_calls':sum('failure' in c for c in backend.calls),'unknown_token_calls':sum(c['input_tokens'] is None for c in backend.calls),'complete':completed,'note':'Cached GPU timings are historical measurements, not a new trial measurement. Standalone sum omits scheduling/model-switch overhead. MOCK is not timing or accuracy evidence.'}
        (a.output_dir/'cost.json').write_text(json.dumps(cost,indent=2)+'\n')
    if completed:(a.output_dir/'COMPLETE').write_text('completed\n')
    print(json.dumps({'output_dir':str(a.output_dir),'items':len(selected_ids),'pairs':len(rows),'mode':contract['execution_mode']}))
if __name__=='__main__':main()
