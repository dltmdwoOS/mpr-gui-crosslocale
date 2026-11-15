"""Resolve portable model snapshot placeholders; never download or change model identities."""
import argparse,json
from pathlib import Path

def materialize(config,hf_home):
    result=json.loads(json.dumps(config))
    vlm=result['evaluation_vlm'];inventory=result['models']['inventory']
    if (inventory['model_id'],inventory['revision']) != (vlm['model_id'],vlm['revision']):
        raise ValueError('Inventory must use the evaluation VLM itself')
    if result['referent_extraction_strategy']=='fixed_lm' and result['models']['referent_extractor']['family']!='text':
        raise ValueError('Fixed LM extraction requires the explicit text model')
    for role,spec in result['models'].items():
        if spec['path']=='HF_HOME_SNAPSHOT':
            spec['path']=str(hf_home.resolve()/'hub'/('models--'+spec['model_id'].replace('/','--'))/'snapshots'/spec['revision'])
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--template',type=Path,required=True);p.add_argument('--hf-home',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Fresh output required')
    config=materialize(json.loads(a.template.read_text()),a.hf_home)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
