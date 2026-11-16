"""One screenshot / one language-pair functionality check, never a pilot sweep."""
import argparse
import fcntl
import json
from pathlib import Path
from run_two_stage_v2 import REPO,ROOT,read,write,resolved_config,budget
from followup_rel_4lang.method_dev.two_stage_v2 import pipeline
from followup_rel_4lang.method_dev.two_stage_v2.backend import Backend


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--gpu',action='store_true');parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args();mock=not args.gpu
    output=args.output_dir or ROOT/'artifacts'/('two_stage_v2_gpu_smoke' if args.gpu else 'two_stage_v2_mock_smoke')
    if output.exists():raise ValueError('Fresh smoke output directory required')
    lock=(ROOT/'artifacts'/('search_pipeline_mock.lock' if mock else 'search_pipeline_gpu.lock')).open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    config=resolved_config()
    if args.gpu:budget(config)
    base=ROOT/'artifacts/two_stage_v2/screen';source=read(base/'inputs.jsonl')
    row=next(r for r in source if r['source_language']=='en' and r['gui_language']=='zh' and not r['parallel_id'].startswith('rel::1/'))
    refs=next(r['referents'] for r in read(base/'oracle_source_spans.jsonl') if r['pair_id']==row['pair_id'])
    output.mkdir(parents=True);backend=Backend(config,REPO,output/'cache',mock)
    results={};passed=False
    try:
        print('SMOKE 1/4 inventory screenshot-only',flush=True);inv=pipeline.inventory(row,backend);results['inventory']=inv
        print('SMOKE 2/4 automatic source extraction',flush=True);extraction=pipeline.extract(row,backend);results['extraction']=extraction
        print('SMOKE 3/4 legacy GUI full localization',flush=True);results['full_gui']=pipeline.full(row,backend,inv)
        print('SMOKE 4/4 oracle selective inventory-conditioned alignment',flush=True);results['selective_gui_oracle']=pipeline.selective(row,refs,backend,inv)
        passed=inv['status']=='success' and bool(inv['visible_strings']) and extraction['status']=='success' and results['full_gui']['status']=='success' and results['selective_gui_oracle']['status']!='fallback_original'
    finally:
        write(output/'calls.json',backend.calls)
        write(output/'results.json',{'execution_mode':'mock' if mock else 'gpu','functionality_only':True,'accuracy_measured':False,'pairs':1,'images':1,
              'pair_id':row['pair_id'],'passed':passed,'results':results})
    if not passed:raise RuntimeError('Smoke transformation/validation failed; inspect raw records')
    print('SMOKE COMPLETE',output,flush=True)


if __name__=='__main__':main()
