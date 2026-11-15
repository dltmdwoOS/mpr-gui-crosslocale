"""Bounded, unchanged-prompt replay of pilot inventory and referent extraction."""
import argparse,json,sys,time
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];sys.path[:0]=[str(REPO/'01_code/src'),str(Path(__file__).parent)]
from backend import TransformersBackend
from mpr_crosslocale.methods.selective_alignment.referent_extractor import PROMPT,resolve_referents
from mpr_crosslocale.methods.selective_alignment.schemas import fields,digest
from mpr_crosslocale.methods.selective_alignment.inventory import parse_inventory


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--stages',choices=['both','extract'],default='both')
    p.add_argument('--extractor-prompt',choices=['original','quoted_control'],default='original');a=p.parse_args()
    if a.output.exists():raise ValueError('Use a fresh output file')
    import torch
    torch.set_num_threads(3)
    row=json.loads(next((REPO/'followup_rel_4lang/method_dev/artifacts/dataset_audit/method_inputs.jsonl').open()))
    assert row['pair_id']=='rel::1/booking_1.jpg::en::zh'
    config=json.loads(a.config.read_text());config['profile_calls']=True
    backend=TransformersBackend(config,REPO)
    legacy=json.loads((REPO/'followup_rel_4lang/method_dev/configs/legacy_prompts.json').read_text())
    result={'schema':'gcsa-smoke-recheck-v1','config':config,'pair_id':row['pair_id'],
            'prompts_changed':a.extractor_prompt!='original','extractor_prompt_condition':a.extractor_prompt,'generation_changed_from_old_smoke':config['max_new_tokens']!=384,
            'backend_sha256':digest((Path(__file__).parent/'backend.py').read_text()),
            'runner_sha256':digest(Path(__file__).read_text())}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    def save():
        result['calls']=backend.calls;a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    if a.stages=='both':
        result['inventory']=parse_inventory(backend('inventory',legacy['prompts']['INVENTORY_SYSTEM_PROMPT'],
            {'image_path':row['image_path'],'image_sha256':row['image_sha256']}));save()
        print('Inventory completed',flush=True)
    # This control tests literal reading/copying only, not general referent extraction.
    selected_prompt=PROMPT if a.extractor_prompt=='original' else (
        'Read the JSON fields in the user message. For every substring enclosed in single quotation marks, '
        'copy the substring into referents. Do not answer or translate the question. '
        'Return JSON only with key referents, an array of objects with field, text, occurrence (zero-based), kind=label. '
        'Field names are question_stem,A,B,C,D. Copy all quoted substrings from all five fields.')
    raw=backend('extract',selected_prompt,{'source_language':row['source_language'],'fields':fields(row)})
    try:result['extracted_referents']=resolve_referents(row,raw);result['extraction_parse_status']='valid'
    except ValueError as exc:result['extracted_referents']=[];result['extraction_parse_status']='invalid';result['extraction_error']=str(exc)
    save();print(json.dumps({'extracted_count':len(result['extracted_referents']),'calls':len(backend.calls)},indent=2),flush=True)
if __name__=='__main__':main()
