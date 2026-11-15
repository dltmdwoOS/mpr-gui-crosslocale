"""Backends use explicit pinned models; mock records never count as empirical inference."""
import hashlib,json,time
from pathlib import Path

class MockBackend:
    provenance={'execution_mode':'mock','model_id':'MOCK','revision':'none'}
    calls=[]
    def __call__(self,stage,prompt,payload):
        self.calls.append(stage)
        if stage=='inventory':return '{"visible_strings":[]}'
        if stage=='extract':return '{"referents":[]}'
        if stage=='translate':return '{}'
        return json.dumps(payload['fields'],ensure_ascii=False)

class TransformersBackend:
    def __init__(self,config,repo):
        self.config=config;self.repo=repo;self.loaded=None;self.calls=[]
        self.provenance={'execution_mode':'gpu','models':config['models']}
    def __call__(self,stage,prompt,payload):
        import torch
        from transformers import AutoProcessor,AutoTokenizer,AutoModelForCausalLM
        from transformers import Qwen2_5_VLForConditionalGeneration,Qwen3VLForConditionalGeneration
        role='inventory' if stage=='inventory' else 'translator';spec=self.config['models'][role]
        key=(spec['model_id'],spec['revision'])
        if self.loaded!=key:
            if self.loaded is not None:
                del self.model,self.processor
                import gc;gc.collect();torch.cuda.empty_cache()
            path=spec['path'];kwargs={'local_files_only':True}
            if spec['family']=='text':
                self.processor=AutoTokenizer.from_pretrained(path,**kwargs)
                self.model=AutoModelForCausalLM.from_pretrained(path,dtype=torch.bfloat16,attn_implementation='sdpa',device_map='cuda:0',**kwargs).eval()
            else:
                cls=Qwen3VLForConditionalGeneration if spec['family']=='qwen3_vl' else Qwen2_5_VLForConditionalGeneration
                self.processor=AutoProcessor.from_pretrained(path,min_pixels=262144,max_pixels=2097152,**kwargs)
                self.model=cls.from_pretrained(path,dtype=torch.bfloat16,attn_implementation='sdpa',device_map='cuda:0',**kwargs).eval()
                if spec['family']=='qwen3_vl':
                    from mpr_crosslocale.models.qwen3_memory import configure_patch_embed_memory_format
                    configure_patch_embed_memory_format(self.model,'channels_last_3d')
            self.loaded=key
        if Path(spec['path']).resolve().name!=spec['revision']:raise ValueError('Model directory must be pinned revision snapshot')
        started=time.perf_counter()
        if spec['family']=='text':
            if stage=='inventory':raise ValueError('Inventory requires a vision model')
            msgs=[{'role':'system','content':prompt},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]
            text=self.processor.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True,enable_thinking=False)
            inputs=self.processor([text],return_tensors='pt').to('cuda:0');decoder=self.processor
        else:
            content=[]
            if stage=='inventory':
                path=self.repo/payload['image_path']
                if hashlib.sha256(path.read_bytes()).hexdigest()!=payload['image_sha256']:raise ValueError('Image checksum differs')
                content.append({'type':'image','image':str(path)})
            content.append({'type':'text','text':'Transcribe visible screen strings.' if stage=='inventory' else json.dumps(payload,ensure_ascii=False)})
            msgs=[{'role':'system','content':prompt},{'role':'user','content':content}]
            text=self.processor.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True)
            from qwen_vl_utils import process_vision_info
            images,videos=process_vision_info(msgs,image_patch_size=16 if spec['family']=='qwen3_vl' else 14)
            inputs=self.processor(text=[text],images=images,videos=videos,return_tensors='pt').to('cuda:0');decoder=self.processor
        torch.cuda.synchronize()
        with torch.inference_mode():out=self.model.generate(**inputs,do_sample=False,num_beams=1,max_new_tokens=self.config.get('max_new_tokens',768))
        torch.cuda.synchronize()
        tokens=out[0,inputs.input_ids.shape[1]:].detach().cpu().tolist()
        raw=decoder.decode(tokens,skip_special_tokens=True,clean_up_tokenization_spaces=False).strip()
        self.calls.append({'stage':stage,'model_id':spec['model_id'],'revision':spec['revision'],'runtime_ms':(time.perf_counter()-started)*1000,
                           'input_tokens':int(inputs.input_ids.shape[1]),'output_tokens':len(tokens),'raw_output':raw})
        return raw
