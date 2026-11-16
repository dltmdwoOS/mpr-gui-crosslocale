"""Compose frozen Hybrid stems with original options; default CPU prepare, no translation."""
import argparse
import fcntl
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

REPO=Path(__file__).resolve().parents[3];ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(REPO/'01_code/src'),str(REPO),str(Path(__file__).parent)]
from mpr_crosslocale.methods.selective_alignment.schemas import digest,fields,render,validate_input
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits
from mpr_crosslocale.inference.answer_parser import parse_label
from search_pipeline import paired_bootstrap,EXCLUDED

CONDITION='TS_STEM_ONLY_GUI_AUTO'
HYBRID='TS_QSEL_OFULL_GUI_AUTO'
BASELINES=('O',HYBRID,'TS_FULL_GUI','TS_SEL_GUI_AUTO')


def read(path):return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');temp.replace(path)
def jsonl(path,rows):path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
def unique(rows):
    result={r['pair_id']:r for r in rows}
    if len(result)!=len(rows):raise ValueError('Duplicate pair ID')
    return result


def compose(original,hybrid):
    """No target annotations or answers; preserve Hybrid stem bytes and original A-D."""
    validate_input(original)
    for key in ('pair_id','parallel_id','source_language','gui_language','image_path','image_sha256','option_order'):
        if hybrid[key]!=original[key]:raise ValueError('Hybrid/original paired identity changed')
    if hybrid['condition']!=HYBRID or hybrid['execution_mode']!='gpu':raise ValueError('Frozen GPU Hybrid required')
    if any(e['field']!='question_stem' for e in hybrid['edits']):raise ValueError('Hybrid contains option edits')
    if any(r['field']!='question_stem' for r in hybrid['extracted_referents'] or []):raise ValueError('Hybrid contains option referents')
    applied=apply_edits(original,hybrid['edits'])
    if applied['question_stem']!=hybrid['question_stem']:raise ValueError('Hybrid modified context outside source referents')
    components=hybrid['components'];failed=components['stem_extraction_failed'] or components['stem_alignment_failed']
    if failed and hybrid['question_stem']!=original['question_stem']:raise ValueError('Failed stem component contains edits')
    output={**original,'question_stem':hybrid['question_stem']}
    return {**output,'condition':CONDITION,'source_condition':HYBRID,'oracle_span':False,'gold_target_used':False,
        'modified_question':render(fields(output)),'extracted_referents':hybrid['extracted_referents'],'edits':hybrid['edits'],
        'status':'fallback_original' if failed else 'success' if output['question_stem']!=original['question_stem'] else 'no_op_no_edits',
        'stem_components':{k:components[k] for k in ('stem_extraction_failed','stem_alignment_failed','stem_status')},
        'composition_only':True,'new_translation_calls':0}


def prepare(source,output,mock):
    complete=json.loads((source/'COMPLETE.json').read_text());parent=json.loads((source.parent/'contract.json').read_text())
    if complete['execution_mode']!='gpu' or parent['mode']!='gpu':raise ValueError('Completed GPU source run required')
    inputs=source/'inputs.jsonl';hybrid=Path(complete['rewrite'])/(HYBRID+'.jsonl');predictions=Path(complete['predictions'])/'predictions.jsonl'
    for marker in [Path(complete['rewrite'])/'COMPLETE',Path(complete['predictions'])/'COMPLETE']:
        if not marker.exists():raise ValueError('Incomplete source run')
    original_rows=read(inputs);plan=json.loads((source/'plan.json').read_text())
    if digest(original_rows)!=plan['input_sha256']:raise ValueError('Frozen source input changed')
    originals=unique(original_rows);hybrids=unique(read(hybrid))
    if set(originals)!=set(hybrids):raise ValueError('Missing Hybrid source pairs')
    rows=[compose(r,hybrids[r['pair_id']]) for r in original_rows]
    inference=json.loads((Path(complete['predictions'])/'contract.json').read_text())
    if inference['downstream']!=parent['config']['downstream'] or inference['input_sha256']!=plan['input_sha256']:raise ValueError('Source inference contract differs')
    for name,sha in parent['source_hashes'].items():
        if hashlib.sha256((REPO/name).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen execution source changed: '+name)
    sources=[inputs,hybrid,predictions,source/'COMPLETE.json',source.parent/'contract.json',source/'plan.json',Path(complete['predictions'])/'contract.json']
    contract={'version':'stem-only-from-frozen-hybrid-gui-v1','condition':CONDITION,'execution_mode':'mock' if mock else 'gpu',
        'source_cohort':str(source.resolve()),'original_inputs':str(inputs.resolve()),'source_predictions':str(predictions.resolve()),
        'downstream':inference['downstream'],'seed':inference['seed'],'labels_sha256':parent['base_data_contract']['labels'],
        'source_sha256':{str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        'script_sha256':digest(Path(__file__).read_text()),'inputs_sha256':digest(original_rows),'composed_sha256':digest(rows),
        'pairs':len(rows),'items':len({r['parallel_id'] for r in rows}),'new_extraction_calls':0,'new_inventory_calls':0,'new_translation_calls':0,
        'queue_order':'new condition only; pair_id sorted; same condition-separated batch groups as frozen Hybrid; O/Hybrid/Full/Selective predictions reused',
        'comparison':'Hybrid vs Stem-only changes only A-D. O vs Stem-only changes only selectively aligned query stem.'}
    output.mkdir(parents=True,exist_ok=True);path=output/'contract.json'
    if path.exists() and json.loads(path.read_text())!=contract:raise ValueError('Source/config/script changed; choose a fresh output directory')
    if path.exists():
        if read(output/'rewritten.jsonl')!=rows:raise ValueError('Prepared Stem-only queries changed')
    else:jsonl(output/'rewritten.jsonl',rows);write(path,contract)
    return contract


def infer(output,attempt,mock):
    from mpr_crosslocale.models.qwen25vl import Qwen25VLAdapter
    from types import SimpleNamespace
    contract=json.loads((output/'contract.json').read_text());rows=read(output/'rewritten.jsonl');profile=contract['downstream'];model=profile['model_config']
    if contract['execution_mode']!=('mock' if mock else 'gpu') or digest(rows)!=contract['composed_sha256']:raise ValueError('Invalid inference inputs')
    labels={r['pair_id']:r for r in read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl')}
    if digest(labels)!=contract['labels_sha256']:raise ValueError('Evaluation labels changed')
    import torch
    torch.set_num_threads(3);adapter=None
    if not mock:
        if torch.cuda.device_count()!=1 or torch.cuda.mem_get_info()[0]<40*2**30:raise RuntimeError('One45GB MIG with40GiB free required; no automatic batch reduction')
        for row in {r['image_path']:r for r in rows}.values():
            if hashlib.sha256((REPO/row['image_path']).read_bytes()).hexdigest()!=row['image_sha256']:raise ValueError('Image changed')
        from transformers import set_seed
        set_seed(contract['seed'])
        adapter=Qwen25VLAdapter(model_id=model['model_id'],revision=model['revision'],dtype=model['dtype'],attn_implementation=model['attn_implementation'],device_map='cuda:0',
            processor_kwargs={'use_fast':profile['processor_use_fast'],'min_pixels':model['min_pixels'],'max_pixels':model['max_pixels']},model_family=model['model_family'],patch_embed_memory_format=model['patch_embed_memory_format'])
        adapter.max_input_tokens=profile['max_input_tokens']
    queue=[{'pair_id':r['pair_id'],'parallel_id':r['parallel_id'],'image_paths':[str(REPO/r['image_path'])],'question_raw':r['modified_question'],'gold_label':labels[r['pair_id']]['gold_answer']} for r in sorted(rows,key=lambda r:r['pair_id'])]
    attempt.mkdir(parents=True);write(attempt/'contract.json',{'execution_mode':contract['execution_mode'],'parent_sha256':digest(contract),'queue_sha256':digest(queue),'downstream':profile})
    with (attempt/'predictions.jsonl').open('w') as f:
        for start in range(0,len(queue),profile['batch_size']):
            batch=queue[start:start+profile['batch_size']];t=time.perf_counter()
            if mock:preds=[SimpleNamespace(raw_output='A',rendered_prompt='MOCK',prompt_token_count=0,output_token_count=0) for _ in batch]
            else:
                torch.cuda.reset_peak_memory_stats()
                preds=adapter.generate_batch(batch,model['prompt_profile'],model['generation'],system_prompt=profile['system_prompt'],score_labels=profile['score_labels'])
            if len(preds)!=len(batch):raise ValueError('Missing generation')
            elapsed=(time.perf_counter()-t)*1000
            for r,pred in zip(batch,preds,strict=True):
                f.write(json.dumps({'pair_id':r['pair_id'],'parallel_id':r['parallel_id'],'condition':CONDITION,'execution_mode':contract['execution_mode'],'status':'success',
                    'generated_text':pred.raw_output,'parsed_generated_label':parse_label(pred.raw_output),'rendered_prompt':pred.rendered_prompt,'prompt_tokens':pred.prompt_token_count,'output_tokens':pred.output_token_count,
                    'batch_id':CONDITION+':'+str(start),'batch_size':len(batch),'batch_runtime_ms':elapsed,'peak_reserved_bytes':None if mock else torch.cuda.max_memory_reserved()},ensure_ascii=False)+'\n');f.flush()
            if start==0 or start%60==0 or start+len(batch)==len(queue):print(f'STEM-ONLY INFER {start+len(batch)}/{len(queue)}',flush=True)
    (attempt/'COMPLETE').write_text('complete\n')


def summarize(output,prediction,mock):
    contract=json.loads((output/'contract.json').read_text());rows=unique(read(output/'rewritten.jsonl'));pred=unique(read(prediction/'predictions.jsonl'))
    if set(rows)!=set(pred):raise ValueError('Incomplete Stem-only evaluation')
    if mock:
        write(output/'results.json',{'execution_mode':'mock','empirical':False,'pairs':len(rows),'new_translation_calls':0});return
    if any(r['execution_mode']!='gpu' or parse_label(r['generated_text'])!=r['parsed_generated_label'] for r in pred.values()):raise ValueError('Invalid GPU prediction')
    labels={r['pair_id']:r for r in read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl')}
    if digest(labels)!=contract['labels_sha256']:raise ValueError('Evaluation labels changed')
    historical={}
    for r in read(Path(contract['source_predictions'])):
        key=(r['condition'],r['pair_id'])
        if key in historical:raise ValueError('Duplicate baseline prediction')
        historical[key]=r
    ids=sorted(p for p in rows if labels[p]['split']=='main' and p!=EXCLUDED)
    correct=lambda row,p:int(row['status']=='success' and row['parsed_generated_label']==labels[p]['gold_answer'])
    values={CONDITION:{p:correct(pred[p],p) for p in ids},**{c:{p:correct(historical[c,p],p) for p in ids} for c in BASELINES}}
    contrasts={c:paired_bootstrap(values[CONDITION],v,labels,20261115,10000) for c,v in values.items() if c!=CONDITION}
    originals=unique(read(Path(contract['original_inputs'])))
    same=[p for p in ids if rows[p]['modified_question']==render(fields(originals[p]))]
    result={'execution_mode':'gpu','development_only':True,'pairs':len(rows),'primary_pairs':len(ids),'correct':{c:sum(v.values()) for c,v in values.items()},'contrasts':contrasts,
        'by_gui':{gui:{'n':sum(rows[p]['gui_language']==gui for p in ids),'correct':{c:sum(v[p] for p in ids if rows[p]['gui_language']==gui) for c,v in values.items()}} for gui in ('en','zh','th','ru')},
        'stem_status':dict(Counter(rows[p]['status'] for p in ids)),'same_as_O_question_pairs':len(same),
        'label_changes_without_question_change':sum(pred[p]['parsed_generated_label']!=historical['O',p]['parsed_generated_label'] for p in same),'new_translation_calls':0}
    write(output/'results.json',result)
    lines=['# Stem-only GUI 결과','',f"실행{len(rows)}쌍, primary{len(ids)}쌍. 기존 Screen을 본 뒤 추가한 개발 진단이다.",'', '| 조건 | 정답 | 정확도 |','| --- | ---: | ---: |']
    for c,k in result['correct'].items():lines.append(f'| {c} | {k}/{len(ids)} | {k/len(ids):.3%} |')
    lines+=['','| Stem-only − 기준 | 차이 | 95% item bootstrap CI | 회복/회귀 |','| --- | ---: | --- | ---: |']
    for c,r in contrasts.items():lines.append(f"| {c} | {r['difference']*100:+.2f}pp | [{r['ci95'][0]*100:+.2f}, {r['ci95'][1]*100:+.2f}] | {r['recovery']}/{r['regression']} |")
    lines+=['','Options는 원본, stem은 완료된 Hybrid와 동일하다. Batch 구성원은 같아도 문장 길이와 padding은 달라질 수 있다. 기존 O·Hybrid·Full·Selective 예측은 재사용했고 새 조건만 추론했다. 정확도는 탐색적 개발 결과이며 독립 최종 검증이 아니다.']
    (output/'REPORT_KO.md').write_text('\n'.join(lines)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-cohort',type=Path,default=ROOT/'artifacts/two_stage_v2_hybrid/screen')
    p.add_argument('--output-dir',type=Path);p.add_argument('--run',action='store_true');p.add_argument('--mock',action='store_true');p.add_argument('--worker',type=Path);a=p.parse_args()
    output=(a.output_dir or ROOT/'artifacts'/('stem_only_gui_screen_v1_mock' if a.mock else 'stem_only_gui_screen_v1')).resolve()
    contract=prepare(a.source_cohort.resolve(),output,a.mock)
    if a.worker:infer(output,a.worker,a.mock);return
    if not a.run:print(json.dumps({'prepared':str(output),'pairs':contract['pairs'],'new_translation_calls':0,'downstream_started':False}),flush=True);return
    lock=(ROOT/'artifacts'/('search_pipeline_mock.lock' if a.mock else 'search_pipeline_gpu.lock')).open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    directory=output/'infer';directory.mkdir(exist_ok=True);attempts=sorted(directory.glob('attempt_*'));done=[d for d in attempts if (d/'COMPLETE').exists()]
    if done:attempt=done[-1]
    else:
        attempt=directory/f'attempt_{len(attempts)+1:04d}'
        command=[sys.executable,'-u',str(Path(__file__)),'--source-cohort',str(a.source_cohort.resolve()),'--output-dir',str(output),'--worker',str(attempt),*(['--mock'] if a.mock else [])]
        with (output/'infer.log').open('a') as log:
            child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            for line in child.stdout:log.write(line);log.flush();print(line,end='',flush=True)
            if child.wait():raise RuntimeError('Inference failed; inspect '+str(output/'infer.log'))
    summarize(output,attempt,a.mock)
    write(output/'COMPLETE.json',{'execution_mode':contract['execution_mode'],'contract_sha256':digest(contract),'predictions':str(attempt)})
    print('COMPLETE',output,flush=True)


if __name__=='__main__':main()
