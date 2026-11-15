"""Generation evaluation of one frozen search candidate, with condition-separated batches."""
import argparse,json,hashlib,sys,time
from pathlib import Path
from types import SimpleNamespace
REPO=Path(__file__).resolve().parents[3];sys.path[:0]=[str(REPO/'01_code/src'),str(Path(__file__).parent)]
from evaluation import read
from mpr_crosslocale.inference.run_cross_locale import _build_model_adapter
from mpr_crosslocale.inference.answer_parser import parse_label
from mpr_crosslocale.methods.selective_alignment.schemas import digest


def build_queue(rewritten,originals,labels):
    if len({r['pair_id'] for r in rewritten})!=len(rewritten):raise ValueError('Duplicate rewritten pair')
    conditions={r['condition'] for r in rewritten}
    if len(conditions)!=1 or 'O' in conditions:raise ValueError('One candidate per trial')
    queue=[]
    for condition in ['O',next(iter(conditions))]:
        for r in sorted(rewritten,key=lambda r:r['pair_id']):
            original=originals[r['pair_id']]
            for key in ('parallel_id','source_language','gui_language','image_path','image_sha256','option_order'):
                if r[key]!=original[key]:raise ValueError('Paired identity changed')
            question=original['question_stem']+' '+' '.join(f'{k}: {original["options"][k]}' for k in 'ABCD') if condition=='O' else r['modified_question']
            queue.append({'pair_id':r['pair_id'],'parallel_id':r['parallel_id'],'condition':condition,'image_paths':[str(REPO/r['image_path'])],
                          'question_raw':question,'gold_label':labels[r['pair_id']]['gold_answer']})
    return queue


def main():
    p=argparse.ArgumentParser();p.add_argument('--trial-dir',type=Path,required=True);p.add_argument('--original-inputs',type=Path,required=True)
    p.add_argument('--mock',action='store_true');p.add_argument('--max-input-tokens',type=int,default=4096);p.add_argument('--labels',type=Path,required=True);p.add_argument('--baseline-contract',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    meta=json.loads((a.trial_dir/'contract.json').read_text())
    if meta['execution_mode']!=('mock' if a.mock else 'gpu') or not (a.trial_dir/'COMPLETE').exists():raise ValueError('Only complete GPU rewrites can be evaluated')
    if a.output_dir.exists():raise ValueError('Fresh output required')
    rewritten=read(a.trial_dir/'rewritten.jsonl');originals={r['pair_id']:r for r in read(a.original_inputs)};labels={r['pair_id']:r for r in read(a.labels)}
    if digest([originals[r['pair_id']] for r in rewritten])!=meta['input_sha256']:raise ValueError('Original inputs differ from trial contract')
    queue=build_queue(rewritten,originals,labels)
    for r in rewritten:
        if not a.mock and hashlib.sha256((REPO/r['image_path']).read_bytes()).hexdigest()!=r['image_sha256']:raise ValueError('Image changed')
    baseline=json.loads(a.baseline_contract.read_text());config=baseline['model_config'];batch=baseline['batch_size']
    contract={'execution_mode':'mock' if a.mock else 'gpu','trial_contract_sha256':digest(meta),'baseline_contract_sha256':digest(baseline),'model_config':config,'batch_size':batch,'system_prompt':baseline['system_prompt'],
              'input_sha256':digest(queue),'labels_sha256':digest(labels),'queue_order':'O then candidate; pair_id sorted; condition-separated chunks; final partial batch explicit',
              'max_input_tokens':a.max_input_tokens,'adapter_sha256':digest((REPO/'01_code/src/mpr_crosslocale/models/qwen25vl.py').read_text()),'implementation_sha256':digest(Path(__file__).read_text())}
    a.output_dir.mkdir(parents=True);(a.output_dir/'contract.json').write_text(json.dumps(contract,indent=2)+'\n')
    import torch
    torch.set_num_threads(3)
    adapter=None if a.mock else _build_model_adapter(SimpleNamespace(attn_implementation=None,device_map='cuda:0'),config)
    if adapter is not None:adapter.max_input_tokens=a.max_input_tokens
    correct={};total={}
    with (a.output_dir/'predictions.jsonl').open('w') as f:
        for condition in dict.fromkeys(r['condition'] for r in queue):
            block=[r for r in queue if r['condition']==condition]
            for start in range(0,len(block),batch):
                chunk=block[start:start+batch];t=time.perf_counter()
                if a.mock:
                    outputs=[SimpleNamespace(raw_output='A',prompt_token_count=0,output_token_count=0) for _ in chunk]
                else:
                    torch.cuda.reset_peak_memory_stats()
                    outputs=adapter.generate_batch(chunk,config['prompt_profile'],config['generation'],system_prompt=baseline['system_prompt'],score_labels=baseline['score_labels'])
                elapsed=(time.perf_counter()-t)*1000
                if len(outputs)!=len(chunk):raise ValueError('Lost output')
                for row,pred in zip(chunk,outputs,strict=True):
                    label=parse_label(pred.raw_output);included=row['pair_id']!='rel::5/forest_9.jpg::zh::ru'
                    result={k:row[k] for k in ('pair_id','parallel_id','condition')};result.update(execution_mode='mock' if a.mock else 'gpu',status='success',generated_text=pred.raw_output,parsed_generated_label=label,
                        prompt_tokens=pred.prompt_token_count,output_tokens=pred.output_token_count,batch_runtime_ms=elapsed,batch_size=len(chunk),primary_included=included,batch_id=condition+':'+str(start),peak_allocated_bytes=None if a.mock else torch.cuda.max_memory_allocated(),peak_reserved_bytes=None if a.mock else torch.cuda.max_memory_reserved())
                    f.write(json.dumps(result,ensure_ascii=False)+'\n');f.flush()
                    if included:correct[condition]=correct.get(condition,0)+(label==row['gold_label']);total[condition]=total.get(condition,0)+1
    (a.output_dir/'COMPLETE').write_text('completed\n')
    (a.output_dir/'descriptive_accuracy.json').write_text(json.dumps({c:{'correct':correct[c],'n':total[c],'accuracy':correct[c]/total[c]} for c in total},indent=2)+'\n')
if __name__=='__main__':main()
