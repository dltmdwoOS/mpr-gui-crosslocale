"""Choose batch 4, or batch 3 only after a CUDA memory failure, on one RTX 4090."""
from __future__ import annotations
import argparse
import gc
import hashlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / '01_code/src'))
from mpr_crosslocale.data.cross_locale_sampling import build_cross_locale_plan, build_language_pairs
from mpr_crosslocale.inference.runtime import load_yaml, read_jsonl, resolve_paths, software_versions
from mpr_crosslocale.inference.run_cross_locale import _build_model_adapter
from mpr_crosslocale.inference.run_rel_followup import cuda_memory_error_kind
from mpr_crosslocale.inference.system_prompts import build_system_prompt
from followup_rel_4lang.grounding_eval.run_qwen3_grounding import build_groups
from followup_rel_4lang.grounding_eval.run_qwen3_prompt_pilot import PROMPT


def choose_batch(probe):
    attempts = []
    for size in (4, 3):
        result = probe(size)
        attempts.append(result)
        if result['status'] == 'passed':
            return size, attempts
        if result['status'] != 'memory_failure':
            raise RuntimeError('Non-memory failure: do not silently fall back')
    raise RuntimeError('Both batch 4 and 3 failed memory checks; full inference must not start')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--model-config', type=Path, default=REPO/'01_code/configs/models/qwen3_vl_8b_4090_channels_last.yaml')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--plan-only', action='store_true')
    a = p.parse_args()
    if a.output.exists():
        p.error('Use a fresh output path; do not overwrite batch selection')
    config = load_yaml(a.model_config)
    if config.get('model_family') != 'qwen3_vl' or config.get('patch_embed_memory_format') != 'channels_last_3d':
        p.error('Use the pinned channels_last_3d Qwen3 configuration')
    manifest = read_jsonl(a.manifest)
    plan = build_cross_locale_plan(manifest, build_language_pairs(None,None),
                                  {'wf','wi','au','ap','ael','rel'}, None, 'semantic_items',42)
    rows = resolve_paths(plan.rows, REPO/'01_code')
    groups = build_groups('pilot')
    metadata = {'config_sha256': hashlib.sha256(a.model_config.read_bytes()).hexdigest(),
                'manifest_sha256': hashlib.sha256(a.manifest.read_bytes()).hexdigest(),
                'cross_locale_inputs':len(rows), 'grounding_pilot_responses':sum(len(g['trials']) for g in groups),
                'policy':'try 4; only memory failure permits trying 3; otherwise stop',
                'software':software_versions()}
    if a.plan_only:
        print(json.dumps(metadata,indent=2));return
    import torch
    torch.set_num_threads(3)
    if torch.cuda.device_count() != 1 or '4090' not in torch.cuda.get_device_name(0):
        raise RuntimeError('Expose exactly one RTX 4090 with CUDA_VISIBLE_DEVICES')
    metadata['gpu'] = torch.cuda.get_device_name(0)
    adapter = _build_model_adapter(SimpleNamespace(attn_implementation=None,device_map='cuda:0'),config)
    tokenizer = adapter.processor.tokenizer
    # Every dimension is checked, including longest multi-image WF and long prompts.
    cases=[]
    for dim in ('wf','wi','au','ap','ael','rel'):
        candidates=[r for r in rows if r['dimension']==dim]
        unique_questions={r['question_raw']:r for r in candidates}
        longest=max(unique_questions.values(),key=lambda r:len(tokenizer.encode(r['question_raw'])))
        largest=max(candidates,key=lambda r:len(r['image_paths']))
        stress={**longest,'image_paths':largest['image_paths']}
        cases.append((dim,stress))
    trials=[r for g in groups for r in g['trials']]
    ground=max(trials,key=lambda r:len(tokenizer.encode(PROMPT.format(text=r['marked_text']))))
    from qwen_vl_utils import process_vision_info
    attempts_seen=[]
    metadata['cases']=[{'dimension':name,'text_input_id':r['input_id'],'image_paths':r['image_paths']} for name,r in cases]
    def probe(size):
        measurements=[]
        try:
            for name,row in cases+[('grounding',ground)]:
                gc.collect();torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats()
                start=time.perf_counter()
                if name=='grounding':
                    image=REPO/'followup_rel_4lang'/row['image_path']
                    messages=[[{'role':'user','content':[{'type':'image','image':str(image)},
                        {'type':'text','text':PROMPT.format(text=row['marked_text'])}]}] for _ in range(size)]
                    rendered=[adapter.processor.apply_chat_template(m,tokenize=False,add_generation_prompt=True) for m in messages]
                    images,videos=process_vision_info(messages,image_patch_size=16)
                    inputs=adapter.processor(text=rendered,images=images,videos=videos,padding=True,return_tensors='pt').to('cuda:0')
                    with torch.inference_mode():
                        output=adapter.model.generate(**inputs,do_sample=False,num_beams=1,max_new_tokens=64)
                    assert output.shape[0]==size
                    del output, inputs
                else:
                    output=adapter.generate_batch([row]*size,config['prompt_profile'],config['generation'],
                        system_prompt=build_system_prompt('english_fixed',row['question_language'])[0],score_labels=True)
                    if len(output)!=size or any(o.label_summary is None for o in output):
                        raise RuntimeError('Lost prediction or label scores')
                    del output
                torch.cuda.synchronize()
                measurements.append({'case':name,'seconds':time.perf_counter()-start,
                    'peak_reserved_gib':torch.cuda.max_memory_reserved()/2**30})
                print(f'PASS batch={size} case={name}',flush=True)
        except Exception as exc:
            if cuda_memory_error_kind(exc) is None:
                raise
            result={'batch_size':size,'status':'memory_failure','error':type(exc).__name__,
                    'measurements':measurements}
            attempts_seen.append(result)
            return result
        result={'batch_size':size,'status':'passed','measurements':measurements}
        attempts_seen.append(result)
        return result
    try:
        selected,attempts=choose_batch(probe)
    except Exception:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps({**metadata,'selected_batch_size':None,'status':'failed','attempts':attempts_seen},indent=2)+'\n')
        raise
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps({**metadata,'selected_batch_size':selected,'attempts':attempts,
        'note':'Memory functionality check, not a guarantee for every full-dataset input.'},indent=2)+'\n')
    print(f'Selected batch size: {selected}',flush=True)

if __name__=='__main__':
    main()
