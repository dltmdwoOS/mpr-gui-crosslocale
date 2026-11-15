"""Sequential, resumable search; the parent never loads model weights. No automatic instance creation."""
import argparse,fcntl,hashlib,json,os,struct,subprocess,sys,time
from pathlib import Path
from collections import defaultdict,Counter
REPO=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent;ROOT=HERE.parent
sys.path[:0]=[str(REPO/'01_code/src'),str(HERE),str(REPO)]
from mpr_crosslocale.methods.selective_alignment.schemas import digest
from build_search_plan import build,EXCLUDED
from materialize_config import materialize

GUI_METHODS=['GUI_EXACT','GUI_MATCH_LM','GUI_TARGETED_VLM','GUI_DIRECT_VLM']
BASELINE=REPO/'followup_rel_4lang/artifacts/new_models_expA_20261115/analysis/expA_8b_20261114/qwen3/expA_qwen3/full/run_contract.json'


def read(path):return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)


def shortlist(records,metric,cost,count,tolerance):
    """Preserve the accuracy leader and a potentially cheaper near-best candidate."""
    if not records:raise ValueError('No candidates')
    ordered=sorted(records,key=lambda r:(-r[metric],r[cost],r['id']));chosen=[ordered[0]]
    near=[r for r in ordered if r[metric]>=ordered[0][metric]-tolerance]
    cheap=min(near,key=lambda r:(r[cost],-r[metric],r['id']))
    if cheap['id']!=chosen[0]['id']:chosen.append(cheap)
    for r in ordered:
        if len(chosen)>=count:break
        if r['id'] not in {x['id'] for x in chosen}:chosen.append(r)
    return chosen[:count]


def decide(records,tolerance):
    best=max(r['accuracy'] for r in records)
    return min((r for r in records if r['accuracy']>=best-tolerance),key=lambda r:(r['method_ms_per_pair'],-r['accuracy'],r['id']))


def descriptive(predictions,labels,candidate,allow_mock=False):
    values={}
    for r in predictions:
        if r['execution_mode']!='gpu' and not allow_mock:raise ValueError('Mock is not empirical evidence')
        key=(r['pair_id'],r['condition'])
        if key in values:raise ValueError('Duplicate prediction')
        values[key]=r
    pairs={pid for pid,c in values}
    if any({c for p,c in values if p==pid}!={'O',candidate} for pid in pairs):raise ValueError('Missing paired conditions')
    groups={'main_primary':[p for p in pairs if labels[p]['split']=='main' and p!=EXCLUDED],
            'legacy_pilot':[p for p in pairs if labels[p]['split']=='pilot'], 'including_excluded':sorted(pairs)}
    out={}
    for name,ids in groups.items():
        if not ids:continue
        correct={c:{p:int(values[p,c].get('status')=='success' and values[p,c].get('parsed_generated_label')==labels[p]['gold_answer']) for p in ids} for c in ('O',candidate)}
        out[name]={'n':len(ids),'items':len({labels[p]['parallel_id'] for p in ids}),
            'accuracy':sum(correct[candidate].values())/len(ids),'O_accuracy':sum(correct['O'].values())/len(ids),
            'recovery':sum(correct[candidate][p]>correct['O'][p] for p in ids),'regression':sum(correct[candidate][p]<correct['O'][p] for p in ids)}
    by_gui={};by_direction={}
    primary=groups['main_primary'] or groups['legacy_pilot']
    for pid in primary:
        src,gui=pid.rsplit('::',2)[1:]
        for bucket,key in [(by_gui,gui),(by_direction,src+'->'+gui)]:
            bucket.setdefault(key,[]).append(int(values[pid,candidate].get('status')=='success' and values[pid,candidate].get('parsed_generated_label')==labels[pid]['gold_answer']))
    return {'groups':out,'by_gui':{k:sum(v)/len(v) for k,v in by_gui.items()},'by_direction':{k:sum(v)/len(v) for k,v in by_direction.items()}}


def paired_bootstrap(left,right,labels,seed,replicates):
    import numpy as np
    if set(left)!=set(right):raise ValueError('Unpaired comparison')
    grouped=defaultdict(list)
    for p in left:grouped[labels[p]['parallel_id']].append(p)
    items=sorted(grouped);counts=np.array([len(grouped[i]) for i in items]);sums=np.array([sum(left[p]-right[p] for p in grouped[i]) for i in items])
    draws=np.random.default_rng(seed).integers(0,len(items),size=(replicates,len(items)))
    observed=float(sums.sum()/counts.sum());bs=sums[draws].sum(1)/counts[draws].sum(1)
    return {'pairs':len(left),'items':len(items),'difference':observed,'ci95':[float(v) for v in np.quantile(bs,[.025,.975])],
            'exploratory_bootstrap_centered_p':float((1+(np.abs(bs-observed)>=abs(observed)).sum())/(replicates+1)),
            'recovery':sum(left[p]>right[p] for p in left),'regression':sum(left[p]<right[p] for p in left)}


def weight_bytes(path):
    total=0
    for f in path.glob('*.safetensors'):
        with f.open('rb') as h:header=json.loads(h.read(struct.unpack('<Q',h.read(8))[0]))
        total+=sum(v['data_offsets'][1]-v['data_offsets'][0] for k,v in header.items() if k!='__metadata__')
    return total


def oom_audit(config,policy,mock):
    entries=[]
    for role in ('translator','inventory'):
        spec=config['models'][role];path=Path(spec['path']);c=json.loads((path/'config.json').read_text());t=c.get('text_config',c)
        per_token=2*t['num_hidden_layers']*t['num_key_value_heads']*t['head_dim']*2
        index=path/'model.safetensors.index.json'
        if not index.is_file() or any(not (path/f).is_file() for f in set(json.loads(index.read_text())['weight_map'].values())):raise ValueError('Incomplete pinned model')
        entries.append({'role':role,'model_id':spec['model_id'],'weights_gib':weight_bytes(path)/2**30,'kv_bytes_per_token':per_token,
            'method_kv_gib_at_cap':per_token*(policy['max_input_tokens']+policy['max_new_tokens'])/2**30,
            'downstream_kv_gib_at_cap_batch3':per_token*3*(policy['max_input_tokens']+2)/2**30})
    result={'estimate_only':True,'guaranteed_no_oom':False,'models':entries,'method_batch':1,'downstream_batch':3,'max_input_tokens':policy['max_input_tokens'],
        'image_pixels_max':2097152,'premerge_patches_max_per_image':8192,'merged_vision_tokens_max_per_image':2048,
        'model_residency':'one model at a time; one child process per trial; no concurrent GPU children',
        'note':'Weights+KV are exact-size components, not peak-memory upper bounds. Attention/Conv3D workspaces, activations, CUDA context and allocator fragmentation remain. SDPA, inference_mode, channels_last_3d, logits_to_keep=1. No automatic batch reduction.'}
    if not mock:
        import torch
        if torch.cuda.device_count()!=1:raise ValueError('Pipeline expects exactly one visible GPU')
        free,total=torch.cuda.mem_get_info(0)
        result.update(gpu=torch.cuda.get_device_name(0),total_gib=total/2**30,free_gib=free/2**30)
        if free<policy['min_free_gpu_gib']*2**30:raise RuntimeError('Insufficient GPU headroom: requires '+str(policy['min_free_gpu_gib'])+' GiB free; this profile targets the current 45GB MIG, not a 24GB 4090')
    return result


class Pipeline:
    def __init__(self,args):
        self.args=args;self.out=args.output_dir.resolve();self.out.mkdir(parents=True,exist_ok=True)
        self.lock=(ROOT/'artifacts'/('search_pipeline_mock.lock' if args.mock else 'search_pipeline_gpu.lock')).open('a')
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.spec=json.loads((ROOT/'configs/search_v1.json').read_text());self.policy=json.loads((ROOT/'configs/search_pipeline_v1.json').read_text())
        self.config=materialize(json.loads((ROOT/'configs/gcsa_qwen3_fixed_lm_v1.json').read_text()),Path(os.environ['HF_HOME']))
        self.config.update(max_input_tokens=self.policy['max_input_tokens'],max_new_tokens=self.policy['max_new_tokens'],record_memory=True)
        sources=[HERE/'search_pipeline.py',HERE/'backend.py',HERE/'run_search_trial.py',HERE/'score_search_trial.py',HERE/'infer_search_trial.py',HERE/'build_search_plan.py',REPO/'01_code/src/mpr_crosslocale/models/qwen25vl.py']
        sources+=list((REPO/'01_code/src/mpr_crosslocale/methods/selective_alignment').glob('*.py'))
        self.fingerprint={'mode':'mock' if args.mock else 'gpu','spec':self.spec,'policy':self.policy,'models':self.config,'source_hashes':{str(p.relative_to(REPO)):digest(p.read_text()) for p in sources}}
        existing=self.out/'pipeline_contract.json'
        if existing.exists() and json.loads(existing.read_text())!=self.fingerprint:raise ValueError('Pipeline/source/config changed; use a new output directory. Existing results preserved.')
        write(existing,self.fingerprint);write(self.out/'oom_audit.json',oom_audit(self.config,self.policy,args.mock));write(self.out/'models.json',self.config)
        data=ROOT/'artifacts/dataset_audit'
        if not (data/'method_inputs.jsonl').exists():self.command([HERE/'audit.py','--output-dir',self.out/'dataset_audit'],'prepare_audit');data=self.out/'dataset_audit'
        self.labels_path=data/'evaluation_labels_PRIVATE.jsonl';self.oracle=data/'oracle_spans_DIAGNOSTIC_ONLY.jsonl';self.labels={r['pair_id']:r for r in read(self.labels_path)}
        rows=read(data/'method_inputs.jsonl');split=json.loads((data/'split.json').read_text());self.manifest,cohorts=build(rows,split,self.spec)
        internal=[r for r in rows if split['items'].get(r['parallel_id'])=='internal_evaluation'];cohorts['internal_evaluation']=sorted(internal,key=lambda r:r['pair_id'])
        if args.mock:
            for name,selected in cohorts.items():
                ids=sorted({r['parallel_id'] for r in selected if name!='screen' or self.labels[r['pair_id']]['split']=='main'})[:1]
                cohorts[name]=[r for r in selected if r['parallel_id'] in ids]
        for name,selected in cohorts.items():
            self.manifest['cohorts'][name]={'item_ids':sorted({r['parallel_id'] for r in selected}),'semantic_items':len({r['parallel_id'] for r in selected}),'pairs':len(selected),'inputs_sha256':digest(selected)}
        self.plan=self.out/'plan/manifest.json';self.manifest['automated_pipeline_policy_sha256']=digest(self.policy);self.manifest['mock_fixture']=args.mock
        for name,selected in cohorts.items():
            p=self.out/'plan'/(name+'.jsonl');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in selected))
        write(self.plan,self.manifest);self.input_files={name:self.plan.parent/(name+'.jsonl') for name in cohorts}
        data_identity={'method_inputs':digest(rows),'labels':digest(self.labels),'oracle':digest(read(self.oracle)),'split':digest(split),'baseline_contract':digest(json.loads(BASELINE.read_text())),'plan':digest(self.manifest)}
        path=self.out/'data_contract.json'
        if path.exists() and json.loads(path.read_text())!=data_identity:raise ValueError('Data identity changed on resume')
        write(path,data_identity)
        if not args.mock:
            for r in {r['image_path']:r for r in rows}.values():
                if hashlib.sha256((REPO/r['image_path']).read_bytes()).hexdigest()!=r['image_sha256']:raise ValueError('Dataset image changed')
        self.records={};self.extractor=None

    def command(self,argv,name):
        log=self.out/'logs'/(name+'.log');log.parent.mkdir(parents=True,exist_ok=True)
        print(time.strftime('%Y-%m-%d %H:%M:%S'),'RUN',name,flush=True)
        if not self.args.mock and Path(argv[0]).name in ('run_search_trial.py','infer_search_trial.py'):
            import torch
            free,_=torch.cuda.mem_get_info(0)
            if free<self.policy['min_free_gpu_gib']*2**30:raise RuntimeError('GPU headroom below required '+str(self.policy['min_free_gpu_gib'])+' GiB before '+name)
        with log.open('a') as f:
            subprocess.run([sys.executable,*map(str,argv)],cwd=REPO,stdout=f,stderr=subprocess.STDOUT,check=True)

    def job(self,key,argv):
        directory=self.out/'jobs'/key;directory.mkdir(parents=True,exist_ok=True)
        attempts=sorted(directory.glob('attempt_*'))
        completed=[p for p in attempts if (p/'COMPLETE').exists()]
        if completed:return completed[-1]
        attempt=directory/('attempt_'+str(len(attempts)+1).zfill(4))
        self.command([*argv,'--output-dir',attempt],key.replace('/','_')+'_'+attempt.name)
        if not (attempt/'COMPLETE').exists():raise RuntimeError('Child returned without COMPLETE')
        return attempt

    def trial(self,cohort,recipe,extractor):
        args=[HERE/'run_search_trial.py','--plan',self.plan,'--spec',ROOT/'configs/search_v1.json','--config',self.out/'models.json','--cohort',cohort,'--extractor',extractor,'--recipe',recipe,'--all-items','--mock' if self.args.mock else '--gpu','--cache-dir',self.out/'cache']
        if cohort=='internal_evaluation':args+=['--frozen-policy',self.out/'frozen_policy.json']
        trial=self.job(cohort+'/'+extractor+'_'+recipe,args)
        if recipe!='extraction':
            expected={r['pair_id'] for r in read(self.input_files[cohort])};actual=read(trial/'rewritten.jsonl')
            if len(actual)!=len(expected) or {r['pair_id'] for r in actual}!=expected:raise ValueError('Incomplete cached rewrite set')
        if not (trial/'quality.json').exists():self.command([HERE/'score_search_trial.py','--trial-dir',trial,'--oracle-spans',self.oracle],cohort+'_'+extractor+'_'+recipe+'_quality')
        return trial

    def infer(self,cohort,recipe,extractor):
        trial=self.trial(cohort,recipe,extractor)
        argv=[HERE/'infer_search_trial.py','--trial-dir',trial,'--original-inputs',self.input_files[cohort],'--labels',self.labels_path,'--baseline-contract',BASELINE,'--max-input-tokens',self.policy['max_input_tokens']]
        if self.args.mock:argv+=['--mock']
        prediction=self.job(cohort+'/pred_'+extractor+'_'+recipe,argv)
        predicted=read(prediction/'predictions.jsonl');expected={r['pair_id'] for r in read(self.input_files[cohort])}
        if len(predicted)!=2*len(expected) or {r['pair_id'] for r in predicted}!=expected:raise ValueError('Incomplete cached prediction set')
        results=descriptive(predicted,self.labels,recipe,self.args.mock)
        quality=json.loads((trial/'quality.json').read_text());cost=json.loads((trial/'cost.json').read_text());n=self.manifest['cohorts'][cohort]['pairs']
        record={'id':recipe,'cohort':cohort,'trial':str(trial.relative_to(self.out)),'predictions':str(prediction.relative_to(self.out)),
            'accuracy':(results['groups'].get('main_primary') or results['groups']['legacy_pilot'])['accuracy'],
            'method_ms_per_pair':cost['standalone_unique_runtime_ms']/n,'quality':quality,'cost':cost,**results}
        self.records[cohort,recipe]=record;write(self.out/'tables'/cohort/(recipe+'.json'),record)
        return record

    def extractor_records(self,cohort,ids):
        result=[]
        for name in ids:
            path=self.trial(cohort,'extraction',name);quality=json.loads((path/'quality.json').read_text());cost=json.loads((path/'cost.json').read_text())
            metrics=quality['metrics'];n=metrics.get('mcqs',1)
            result.append({'id':name,'f1':metrics['f1'] or 0,'ms_per_mcq':cost['standalone_unique_runtime_ms']/n,'metrics':metrics,'quality':quality,'cost':cost})
        write(self.out/'tables'/(cohort+'_extractors.json'),result);return result

    def run(self):
        all_extractors=list(self.spec['extractors']);probe=self.extractor_records('probe',all_extractors)
        shortlist_a=shortlist([r for r in probe if r['id']!='cpu_quoted'],'f1','ms_per_mcq',2,self.policy['extractor_f1_tolerance'])
        screened=self.extractor_records('screen',[r['id'] for r in shortlist_a]);self.extractor=decide_extractor(screened,self.policy['extractor_f1_tolerance'])['id']
        write(self.out/'extractor_decision.json',{'selected':self.extractor,'shortlist':[r['id'] for r in shortlist_a],'rule':'best F1; within 0.02 choose lower measured cost; all-zero remains diagnostic failure','records':screened})
        for recipe in self.spec['recipes']:self.infer('probe',recipe,self.extractor)
        screen=[self.infer('screen',recipe,self.extractor) for recipe in self.spec['recipes']]
        finalists=shortlist([r for r in screen if r['id'] in GUI_METHODS],'accuracy','method_ms_per_pair',2,self.policy['accuracy_tolerance_pp']/100)
        write(self.out/'shortlist_frozen_before_selection.json',{'extractor':self.extractor,'finalists':[r['id'] for r in finalists],'screen_records':screen,'policy_sha256':digest(self.policy)})
        controls={'TXT_SEL','TXT_FULL','GUI_FULL','TXT_DIRECT_VLM'}
        ids=sorted(controls|{r['id'] for r in finalists});selection=[self.infer('selection',recipe,self.extractor) for recipe in ids]
        winner=decide([r for r in selection if r['id'] in {x['id'] for x in finalists}],self.policy['accuracy_tolerance_pp']/100)
        evaluation_recipes=sorted(controls|{winner['id']})
        frozen={'extractor':self.extractor,'winner':winner['id'],'evaluation_recipes':evaluation_recipes,'plan_sha256':digest(self.manifest),'spec_sha256':digest(self.spec),'pipeline_sha256':digest(self.fingerprint),
                'selection_records':selection,'matching_review_status':'not independently reviewed','automatic_choice_is_provisional':True,'development_not_confirmatory':True}
        path=self.out/'frozen_policy.json'
        if path.exists() and json.loads(path.read_text())!=frozen:raise ValueError('Frozen selection changed on resume')
        write(path,frozen)
        for recipe in evaluation_recipes:self.infer('internal_evaluation',recipe,self.extractor)
        self.report(winner['id'],evaluation_recipes)
        write(self.out/'COMPLETE.json',{'mode':'mock' if self.args.mock else 'gpu','winner':winner['id'],'automatic_choice_is_provisional':True,'internal_evaluation_used_for_selection':False})
        print('COMPLETE:',self.out/'REPORT_KO.md',flush=True)

    def report(self,winner,recipes):
        summary={};outcome={};o_anchors=[]
        for recipe in recipes:
            record=self.records['internal_evaluation',recipe];preds=read(self.out/record['predictions']/'predictions.jsonl')
            outcome[recipe]={p['pair_id']:int(p['parsed_generated_label']==self.labels[p['pair_id']]['gold_answer']) for p in preds if p['condition']==recipe and self.labels[p['pair_id']]['split']=='main' and p['pair_id']!=EXCLUDED}
            o={p['pair_id']:int(p['parsed_generated_label']==self.labels[p['pair_id']]['gold_answer']) for p in preds if p['condition']=='O' and p['pair_id'] in outcome[recipe]}
            o_anchors.append({p['pair_id']:p['parsed_generated_label'] for p in preds if p['condition']=='O'});outcome.setdefault('O',o)
            summary[recipe]=record
        comparisons={}
        for control in ['O','TXT_SEL','GUI_FULL','TXT_FULL','TXT_DIRECT_VLM']:
            if control!=winner:comparisons[winner+'-'+control]=paired_bootstrap(outcome[winner],outcome[control],self.labels,self.policy['seed'],self.policy['bootstrap_replicates'])
        primary=[winner+'-'+c for c in ['O','TXT_SEL','GUI_FULL'] if winner+'-'+c in comparisons];adjusted=0
        for rank,name in enumerate(sorted(primary,key=lambda n:comparisons[n]['exploratory_bootstrap_centered_p'])):
            adjusted=max(adjusted,min(1,(len(primary)-rank)*comparisons[name]['exploratory_bootstrap_centered_p']));comparisons[name]['holm_primary_p']=adjusted
        acquisition=0;loads=0
        for cost in self.out.glob('jobs/**/cost.json'):
            c=json.loads(cost.read_text());acquisition+=c['acquired_runtime_ms'];loads+=c['acquired_model_load_ms']
        result={'execution_mode':'mock' if self.args.mock else 'gpu','winner':winner,'extractor':self.extractor,'internal_evaluation':summary,'contrasts':comparisons,
                'O_anchors_identical_across_candidates':all(x==o_anchors[0] for x in o_anchors),'method_acquired_runtime_ms':acquisition,'method_acquired_load_ms':loads,
                'matching_precision':None,'provisional_unreviewed':True,'historically_observed_development_cohort':True}
        write(self.out/'analysis.json',result)
        lines=['# 순차 method 탐색 결과','', '**MOCK — 성능·시간 실측이 아님**' if self.args.mock else '개발용 탐색 결과. 자동 선택은 화면 의미 검수가 끝나지 않은 잠정 선택이다.', '',f'선택 extractor: `{self.extractor}`; 선택 method: `{winner}`. Internal evaluation 정답률은 선택에 사용하지 않았다.','', '| 조건 | Main 정확도 | 분모 | method 시간/쌍¹ |','| --- | ---: | ---: | ---: |']
        lines.append(f'| O | {sum(outcome["O"].values())/len(outcome["O"]):.3%} | {len(outcome["O"])} | — |')
        for recipe,r in summary.items():lines.append(f'| {recipe} | {r["accuracy"]:.3%} | {len(outcome[recipe])} | {r["method_ms_per_pair"]/1000:.3f}초 |')
        lines+=['','¹ 고유 method 호출의 과거 runtime 합을 pair 수로 나눈 값. 모델 load·downstream 시간을 제외하며 cache hit의0초가 아니다. 콜드/실제 소비 비용은 cost.json과 analysis.json을 함께 본다.','','비교별 item-bootstrap95% CI·회복/회귀·GUI 언어·언어쌍 결과는 analysis.json에 있다. 독립 화면 검수 전 matching precision은 null이다. 원래 전체158개가 역사적으로 관찰된 개발 데이터이며 확증 결과로 쓰지 않는다.','','Scope: Qwen3 method search와 고정 내부 평가. Pivot routing과 추가 VLM은 포함하지 않는다.']
        (self.out/'REPORT_KO.md').write_text('\n'.join(lines)+'\n')


def decide_extractor(records,tolerance):
    best=max(r['f1'] for r in records)
    return min((r for r in records if r['f1']>=best-tolerance),key=lambda r:(r['ms_per_mcq'],-r['f1'],r['id']))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mock',action='store_true');p.add_argument('--output-dir',type=Path);a=p.parse_args()
    if a.output_dir is None:a.output_dir=ROOT/'artifacts'/('search_pipeline_v1_mock' if a.mock else 'search_pipeline_v1')
    try:
        runner=Pipeline(a);runner.run()
    except Exception as exc:
        write(a.output_dir/'STOPPED.json',{'error_type':type(exc).__name__,'error':str(exc),'time':time.strftime('%Y-%m-%dT%H:%M:%S'),'resume':'Repeat the same command; completed jobs reused; incomplete attempts preserved.'})
        raise
if __name__=='__main__':main()
