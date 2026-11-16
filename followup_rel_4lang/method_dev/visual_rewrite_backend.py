"""Query-informed VLM editing. Separate from the frozen query-blind inventory API."""
import hashlib
import json
import time
from pathlib import Path

from .two_stage_v2.backend import Backend
from mpr_crosslocale.methods.selective_alignment.schemas import digest


class VisualRewriteBackend(Backend):
    def __call__(self, stage, role, system, user, image=None):
        if role != 'editor_vlm' or stage not in ('visual_rewrite', 'visual_rewrite_repair'):
            raise ValueError('Only named screenshot editing stages allowed')
        if not isinstance(image, dict) or set(image) != {'image_path','image_sha256'}:
            raise ValueError('Screenshot metadata allowlist violated')
        path = (self.repo/image['image_path']).resolve()
        if not path.is_relative_to(Path('/home/jovyan/seungjae')):
            raise ValueError('Image outside personal workspace')
        if not self.mock and hashlib.sha256(path.read_bytes()).hexdigest() != image['image_sha256']:
            raise ValueError('Screenshot checksum changed')
        messages = [{'role':'system','content':[{'type':'text','text':system}]},
                    {'role':'user','content':[{'type':'image','image':str(path)},{'type':'text','text':user}]}]
        generation = {'do_sample':False,'num_beams':1,'max_new_tokens':self.limits[stage],'use_cache':True,'logits_to_keep':1}
        key = digest({'messages':messages,'image_sha256':image['image_sha256'],'model':self.config['models'][role],
                      'generation':generation,'max_input_tokens':self.config['max_input_tokens'],'seed':self.config['seed'],
                      'backend':digest(Path(__file__).read_text()),'software':self.software,'hardware':self.hardware,'mock':self.mock})
        target = self.cache/(key+'.json');hit = target.exists()
        if hit:
            record = json.loads(target.read_text())
        elif self.mock:
            data = json.JSONDecoder().raw_decode(user[user.index('{'):])[0]
            record = {'raw_output':json.dumps({'question_stem':data['question_stem'],'options':data['options']},ensure_ascii=False),
                      'rendered_prompt':'MOCK','input_tokens':0,'output_tokens':0,'runtime_ms':0,'model_load_ms':0,
                      'peak_reserved_bytes':None,'execution_mode':'mock'}
        else:
            import torch
            from qwen_vl_utils import process_vision_info
            load_ms = self._load(role);started = time.perf_counter()
            rendered = self.processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
            images,videos = process_vision_info(messages,image_patch_size=16)
            inputs = self.processor(text=[rendered],images=images,videos=videos,return_tensors='pt')
            patches = int(inputs['image_grid_thw'].prod(-1).sum())
            if patches > 8192:
                raise RuntimeError('Vision patch budget exceeded; no silent resize')
            tokens = int(inputs.input_ids.shape[1])
            if tokens > self.config['max_input_tokens']:
                raise RuntimeError(f'Input budget exceeded: {tokens}; no truncation')
            inputs = inputs.to('cuda:0');torch.cuda.reset_peak_memory_stats()
            with torch.inference_mode():
                result = self.model.generate(**inputs,**generation)
            torch.cuda.synchronize();generated = result[0,tokens:].detach().cpu().tolist()
            record = {'raw_output':self.processor.decode(generated,skip_special_tokens=True,clean_up_tokenization_spaces=False).strip(),
                      'rendered_prompt':rendered,'input_tokens':tokens,'output_tokens':len(generated),
                      'runtime_ms':(time.perf_counter()-started)*1000,'model_load_ms':load_ms,
                      'peak_reserved_bytes':torch.cuda.max_memory_reserved(),'peak_allocated_bytes':torch.cuda.max_memory_allocated(),
                      'image_grid_thw':inputs['image_grid_thw'].detach().cpu().tolist(),'execution_mode':'gpu'}
        record = {**record,'stage':stage,'role':role,'system_prompt':system,'user_prompt':user,'messages':messages,
                  'image_sha256':image['image_sha256'],'query_informed':True,'inventory_generated':False,
                  'model_id':self.config['models'][role]['model_id'],'revision':self.config['models'][role]['revision'],
                  'generation':generation,'cache_key':key,'cache_hit':hit,'software':self.software,'hardware':self.hardware}
        if not hit:
            self.cache.mkdir(parents=True,exist_ok=True)
            temp = target.with_suffix('.tmp');temp.write_text(json.dumps(record,ensure_ascii=False)+'\n');temp.replace(target)
        self.calls.append(record)
        return record
