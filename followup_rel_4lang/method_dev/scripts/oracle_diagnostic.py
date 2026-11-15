"""Explicitly oracle-assisted span diagnostic. Never reported as automatic GCSA."""
import argparse,json,sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];sys.path[:0]=[str(REPO/'01_code/src'),str(Path(__file__).parent)]
from backend import TransformersBackend,MockBackend
from mpr_crosslocale.methods.selective_alignment.pipeline import Pipeline


def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--oracle-spans',type=Path,required=True)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--mock',action='store_true');a=p.parse_args()
    if a.output.exists():raise ValueError('Fresh output required')
    spans={r['pair_id']:r for r in map(json.loads,a.oracle_spans.read_text().splitlines())}
    config=json.loads(a.config.read_text());legacy=json.loads((REPO/'followup_rel_4lang/method_dev/configs/legacy_prompts.json').read_text())
    backend=MockBackend() if a.mock else TransformersBackend(config,REPO)
    class OraclePipeline(Pipeline):
        def extract(self,row):
            refs=spans[row['pair_id']]['referents']
            return {'status':'success','raw_output':'ORACLE_ANNOTATED_SPANS','errors':[],
                    'referents':[{**r,'kind':'label'} for r in refs]}
    method=OraclePipeline(backend,config,legacy['prompts']['INVENTORY_SYSTEM_PROMPT'])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('w') as out:
        for row in map(json.loads,a.inputs.read_text().splitlines()):
            result=method.run(row)[3];result.update(condition='oracle_span_selective',oracle_span=True)
            out.write(json.dumps(result,ensure_ascii=False)+'\n')
if __name__=='__main__':main()
