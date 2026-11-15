"""Downstream inference: labels/reference anchors remain outside method execution."""
import argparse,json,sys,time
from pathlib import Path
from types import SimpleNamespace
REPO=Path(__file__).resolve().parents[3];sys.path[:0]=[str(REPO/'01_code/src'),str(Path(__file__).parent)]
from evaluation import read
from mpr_crosslocale.inference.run_cross_locale import _build_model_adapter
from mpr_crosslocale.inference.answer_parser import parse_label
from mpr_crosslocale.methods.selective_alignment.schemas import digest


def main():
    p=argparse.ArgumentParser();p.add_argument('--rewritten',type=Path,required=True);p.add_argument('--labels',type=Path,required=True)
    p.add_argument('--baseline-contract',type=Path,required=True);p.add_argument('--original-inputs',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--limit-pairs',type=int)
    a=p.parse_args();meta=json.loads((a.rewritten.parent/'contract.json').read_text())
    if meta['mode']=='mock':raise ValueError('Refuse to evaluate mock rewrites')
    rewritten=read(a.rewritten);pairs=sorted({r['pair_id'] for r in rewritten})
    if a.limit_pairs:pairs=pairs[:a.limit_pairs]
    labels={r['pair_id']:r for r in read(a.labels)};originals={r['pair_id']:r for r in read(a.original_inputs)}
    if len(rewritten)!=len({(r['pair_id'],r['condition']) for r in rewritten}):raise ValueError('Duplicate rewritten pair-condition')
    selected=[r for r in rewritten if r['pair_id'] in set(pairs)]
    for r in selected:
        original=originals[r['pair_id']]
        for key in ('parallel_id','source_language','gui_language','image_sha256','image_path','option_order'):
            if r[key]!=original[key]:raise ValueError('Paired identity/image/order changed')
    import hashlib
    for row in selected:
        if hashlib.sha256((REPO/row['image_path']).read_bytes()).hexdigest()!=row['image_sha256']:
            raise ValueError('Screenshot checksum changed')
    baseline=json.loads(a.baseline_contract.read_text());config=baseline['model_config'];batch=baseline['batch_size']
    # Same batch size/backbone/system as historical baseline; composition is condition-major, explicitly different.
    queue=[]
    for condition in ('O','TXT_FULL','GUI_FULL','TXT_SEL','GUI_SEL'):
        for pid in pairs:
            if condition=='O':
                row=originals[pid];question=row['question_stem']+' '+' '.join(f'{k}: {row["options"][k]}' for k in 'ABCD')
            else:
                matches=[r for r in selected if r['pair_id']==pid and r['condition']==condition]
                if len(matches)!=1:raise ValueError('Incomplete paired rewrite')
                row=matches[0];question=row['modified_question']
            queue.append({'pair_id':pid,'parallel_id':row['parallel_id'],'condition':condition,'image_paths':[str(REPO/row['image_path'])],
                          'question_raw':question,'gold_label':labels[pid]['gold_answer']})
    contract={'baseline_contract_sha256':digest(baseline),'model_config':config,'batch_size':batch,
              'queue_order':'condition-major, pair_id sorted; different from historical O/T/R companions',
              'input_sha256':digest(queue),'rewrite_contract':meta,'implementation_sha256':digest(Path(__file__).read_text()),
              'execution_mode':'gpu','system_prompt':baseline['system_prompt']}
    if a.output_dir.exists():raise ValueError('Fresh output required; no silent partial resume')
    a.output_dir.mkdir(parents=True);(a.output_dir/'contract.json').write_text(json.dumps(contract,indent=2)+'\n')
    adapter=_build_model_adapter(SimpleNamespace(attn_implementation=None,device_map='cuda:0'),config)
    with (a.output_dir/'predictions.jsonl').open('w') as f:
        for start in range(0,len(queue),batch):
            chunk=queue[start:start+batch];t=time.perf_counter()
            output=adapter.generate_batch(chunk,config['prompt_profile'],config['generation'],system_prompt=baseline['system_prompt'],score_labels=baseline['score_labels'])
            if len(output)!=len(chunk):raise ValueError('Lost output')
            for row,pred in zip(chunk,output,strict=True):
                result={'pair_id':row['pair_id'],'parallel_id':row['parallel_id'],'condition':row['condition'],
                        'status':'success','execution_mode':'gpu','generated_text':pred.raw_output,'parsed_generated_label':parse_label(pred.raw_output),
                        'prompt_tokens':pred.prompt_token_count,'output_tokens':pred.output_token_count,
                        'batch_runtime_ms':(time.perf_counter()-t)*1000,'batch_size':len(chunk),'contract_sha256':digest(contract)}
                f.write(json.dumps(result,ensure_ascii=False)+'\n');f.flush()
if __name__=='__main__':main()
