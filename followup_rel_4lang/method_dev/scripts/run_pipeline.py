"""Consume ONLY the allowlisted method_inputs.jsonl, never the privileged audit adapter."""
import argparse,json,sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];sys.path[:0]=[str(REPO/'01_code/src'),str(Path(__file__).parent)]
from mpr_crosslocale.methods.selective_alignment.pipeline import Pipeline
from mpr_crosslocale.methods.selective_alignment.schemas import digest,validate_input
from backend import MockBackend,TransformersBackend

def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--mock',action='store_true');p.add_argument('--limit',type=int)
    p.add_argument('--split-file',type=Path);p.add_argument('--partition',choices=['pilot','calibration','internal_evaluation'],default='pilot')
    a=p.parse_args();config=json.loads(a.config.read_text());rows=[validate_input(json.loads(l)) for l in a.inputs.read_text().splitlines() if l.strip()]
    if not a.split_file:raise ValueError('A fixed split file is required')
    split=json.loads(a.split_file.read_text())['items']
    rows=[r for r in rows if (r['parallel_id'] not in split if a.partition=='pilot' else split.get(r['parallel_id'])==a.partition)]
    if a.limit is not None:
        if a.limit<1:raise ValueError('limit must be positive')
        rows=rows[:a.limit]
    if not rows:raise ValueError('No selected inputs')
    if a.partition=='internal_evaluation' and not config.get('calibration_frozen') and not a.mock:
        raise ValueError('Freeze calibration config before internal evaluation')
    legacy=json.loads((REPO/'followup_rel_4lang/method_dev/configs/legacy_prompts.json').read_text())
    if not a.mock:
        for spec in config['models'].values():
            path=Path(spec['path'])
            if not path.is_dir() or path.name!=spec['revision'] or not list(path.glob('*.safetensors')):
                raise ValueError('Pinned model not locally cached: '+spec['model_id']+'; set path explicitly. No implicit download.')
    backend=MockBackend() if a.mock else TransformersBackend(config,REPO)
    scorer=None
    if config.get('retrieval')=='labse':
        from mpr_crosslocale.methods.selective_alignment.matcher import LabseScorer
        if Path(config['labse_snapshot']).name != config.get('labse_revision'):
            raise ValueError('Pin the LaBSE revision and snapshot path explicitly')
        scorer=LabseScorer(config['labse_snapshot'])
    elif config.get('retrieval')!='translated_normalized_exact_only':raise ValueError('Unknown retrieval')
    method=Pipeline(backend,config,legacy['prompts']['INVENTORY_SYSTEM_PROMPT'],scorer)
    contract={'config':config,'inputs_sha256':digest(rows),'split_sha256':digest(split),'partition':a.partition,
              'mode':'mock' if a.mock else 'gpu','implementation_sha256':{p.name:digest(p.read_text()) for p in (REPO/'01_code/src/mpr_crosslocale/methods/selective_alignment').glob('*.py')},
              'runner_sha256':digest(Path(__file__).read_text()),'backend_sha256':digest((Path(__file__).parent/'backend.py').read_text())}
    from mpr_crosslocale.inference.runtime import software_versions
    contract['software_versions']=software_versions()
    if a.output_dir.exists():raise ValueError('Use a fresh output directory (no silent mixing/resume)')
    a.output_dir.mkdir(parents=True)
    (a.output_dir/'contract.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n')
    # All screenshot-only calls precede the text-only phase; avoid repeated model swaps.
    inventory_records={r['image_sha256']:method.inventory(r) for r in rows}
    (a.output_dir/'inventories.json').write_text(json.dumps(inventory_records,ensure_ascii=False,indent=2)+'\n')
    with (a.output_dir/'rewritten.jsonl').open('w') as handle:
        for row in rows:
            for result in method.run(row):handle.write(json.dumps(result,ensure_ascii=False)+'\n');handle.flush()
    (a.output_dir/'backend_calls.json').write_text(json.dumps(backend.calls,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'pairs':len(rows),'condition_rows':len(rows)*4,'mode':contract['mode']}))
if __name__=='__main__':main()
