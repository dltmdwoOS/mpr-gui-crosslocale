"""Exact-message, stage-budgeted backend. New cache namespace; no v1 inventory reuse."""
import hashlib
import json
import time
from pathlib import Path
from mpr_crosslocale.methods.selective_alignment.schemas import digest


class Backend:
    def __init__(self,config,repo,cache,mock=False):
        self.config=config;self.repo=repo;self.cache=cache;self.mock=mock;self.calls=[];self.loaded=None
        self.limits=config['output_tokens']
        from mpr_crosslocale.inference.runtime import software_versions
        self.software=software_versions();self.hardware='CPU-MOCK'
        if not mock:
            import torch
            p=torch.cuda.get_device_properties(0)
            self.hardware={'name':p.name,'multiprocessors':p.multi_processor_count,'memory_bytes':p.total_memory}

    def _load(self,role):
        if self.loaded==role:return 0
        import torch
        from transformers import AutoModelForCausalLM,AutoProcessor,AutoTokenizer,Qwen3VLForConditionalGeneration,set_seed
        if self.loaded is not None:
            del self.model,self.processor
            import gc;gc.collect();torch.cuda.empty_cache()
        free,_=torch.cuda.mem_get_info()
        if free<self.config['min_free_gpu_gib']*2**30:raise RuntimeError('Insufficient free GPU memory before model load')
        started=time.perf_counter();set_seed(self.config['seed']);torch.set_num_threads(3)
        spec=self.config['models'][role];kw={'local_files_only':True}
        if role=='text':
            self.processor=AutoTokenizer.from_pretrained(spec['path'],**kw)
            self.model=AutoModelForCausalLM.from_pretrained(spec['path'],dtype=torch.bfloat16,attn_implementation='sdpa',device_map='cuda:0',**kw).eval()
        else:
            self.processor=AutoProcessor.from_pretrained(spec['path'],use_fast=True,min_pixels=262144,max_pixels=2097152,**kw)
            self.model=Qwen3VLForConditionalGeneration.from_pretrained(spec['path'],dtype=torch.bfloat16,attn_implementation='sdpa',device_map='cuda:0',**kw).eval()
            from mpr_crosslocale.models.qwen3_memory import configure_patch_embed_memory_format
            configure_patch_embed_memory_format(self.model,'channels_last_3d')
        self.loaded=role;torch.cuda.synchronize()
        return (time.perf_counter()-started)*1000

    def __call__(self,stage,role,system,user,image=None):
        if role not in ('inventory','text') or (image is not None)!=(role=='inventory'):raise ValueError('Only query-blind inventory may receive an image')
        if image is not None:
            if set(image)!={'image_path','image_sha256'}:raise ValueError('Inventory image allowlist violated')
            path=(self.repo/image['image_path']).resolve()
            if not path.is_relative_to(Path('/home/jovyan/seungjae')):raise ValueError('Image outside personal workspace')
            if not self.mock and hashlib.sha256(path.read_bytes()).hexdigest()!=image['image_sha256']:raise ValueError('Image checksum changed')
        messages=[{'role':'system','content':system},{'role':'user','content':user}]
        if image is not None:
            messages=[{'role':'system','content':[{'type':'text','text':system}]},{'role':'user','content':[{'type':'image','image':str(self.repo/image['image_path'])},{'type':'text','text':user}]}]
        generation={'do_sample':False,'num_beams':1,'max_new_tokens':self.limits[stage],'use_cache':True,'logits_to_keep':1}
        key=digest({'messages':messages,'image_sha256':None if image is None else image['image_sha256'],'model':self.config['models'][role],
                    'generation':generation,'max_input_tokens':self.config['max_input_tokens'],'seed':self.config['seed'],'backend':digest(Path(__file__).read_text()),
                    'software':self.software,'hardware':self.hardware,'mock':self.mock})
        path=self.cache/(key+'.json');hit=path.exists()
        if hit:record=json.loads(path.read_text())
        elif self.mock:
            raw=self._mock(stage,user)
            record={'raw_output':raw,'rendered_prompt':'MOCK','input_tokens':0,'output_tokens':0,'runtime_ms':0,'model_load_ms':0,'peak_reserved_bytes':None,'execution_mode':'mock'}
        else:
            import torch
            load_ms=self._load(role);started=time.perf_counter()
            text=self.processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,**({'enable_thinking':False} if role=='text' else {}))
            if role=='text':inputs=self.processor([text],return_tensors='pt')
            else:
                from qwen_vl_utils import process_vision_info
                images,videos=process_vision_info(messages,image_patch_size=16)
                inputs=self.processor(text=[text],images=images,videos=videos,return_tensors='pt')
                if int(inputs['image_grid_thw'].prod(-1).sum())>8192:raise RuntimeError('Vision patch budget exceeded; no silent resizing')
            tokens=int(inputs.input_ids.shape[1])
            if tokens>self.config['max_input_tokens']:raise RuntimeError(f'Input budget exceeded: {tokens}; no truncation')
            inputs=inputs.to('cuda:0');torch.cuda.reset_peak_memory_stats()
            with torch.inference_mode():out=self.model.generate(**inputs,**generation)
            torch.cuda.synchronize();generated=out[0,tokens:].detach().cpu().tolist()
            record={'raw_output':self.processor.decode(generated,skip_special_tokens=True,clean_up_tokenization_spaces=False).strip(),
                    'rendered_prompt':text,'input_tokens':tokens,'output_tokens':len(generated),'runtime_ms':(time.perf_counter()-started)*1000,'model_load_ms':load_ms,
                    'peak_reserved_bytes':torch.cuda.max_memory_reserved(),'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'execution_mode':'gpu'}
        record={**record,'stage':stage,'role':role,'system_prompt':system,'user_prompt':user,'model_id':self.config['models'][role]['model_id'],
                'revision':self.config['models'][role]['revision'],'generation':generation,'cache_key':key,'cache_hit':hit,'software':self.software,'hardware':self.hardware}
        if not hit:
            self.cache.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(record,ensure_ascii=False)+'\n');temp.replace(path)
        self.calls.append(record)
        return record

    @staticmethod
    def _mock(stage,user):
        if stage.startswith('inventory'):return '{"visible_strings":["Settings","Search","MOCK_LABEL"]}'
        data=json.JSONDecoder().raw_decode(user[user.index('{'):])[0]
        if stage.startswith('extract'):
            from mpr_crosslocale.methods.selective_alignment.search import quoted_referents
            try:refs=quoted_referents({'question_stem':data['fields']['question_stem'],'options':{k:data['fields'][k] for k in 'ABCD'}})
            except ValueError:refs=[]
            return json.dumps({'referents':[{k:r[k] for k in ('field','text','occurrence')} for r in refs]},ensure_ascii=False)
        if stage.startswith('selective'):return json.dumps({'translations':{r['span_id']:None for r in data['referents']}})
        return json.dumps({'question_stem':data['question_stem'],'options':data['options']},ensure_ascii=False)
