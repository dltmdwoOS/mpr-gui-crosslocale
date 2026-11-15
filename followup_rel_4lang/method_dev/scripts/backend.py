"""Backends use explicit pinned models; mock records never count as empirical inference."""
import hashlib,json,time
from collections import defaultdict
from pathlib import Path

class MockBackend:
    provenance={'execution_mode':'mock','model_id':'MOCK','revision':'none'}
    def __init__(self):
        self.calls=[]
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
        role='inventory' if stage=='inventory' else 'referent_extractor' if stage=='extract' and 'referent_extractor' in self.config['models'] else 'translator'
        spec=self.config['models'][role]
        load_started=time.perf_counter();load_ms=0.0
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
            torch.cuda.synchronize()
            load_ms=(time.perf_counter()-load_started)*1000
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
        preprocessing_ms=(time.perf_counter()-started)*1000
        timings=defaultdict(list);starts=defaultdict(list);hooks=[];patch_metadata={}
        if self.config.get('profile_calls',False):
            def instrument(module,name):
                def pre(_module,args):
                    torch.cuda.synchronize();starts[name].append(time.perf_counter())
                    if name=='patch' and not patch_metadata:
                        projection=module.proj
                        pixels=args[0].view(-1,module.in_channels,module.temporal_patch_size,module.patch_size,module.patch_size)
                        w=projection.weight
                        patch_metadata.update(weight_stride=list(w.stride()),weight_dtype=str(w.dtype),
                            weight_channels_last_3d=w.is_contiguous(memory_format=torch.channels_last_3d),
                            input_dtype=str(pixels.dtype),input_shape=list(pixels.shape),
                            selected_conv_backend=str(torch._C._select_conv_backend(pixels,w,projection.bias,
                              list(projection.stride),list(projection.padding),list(projection.dilation),False,[0,0,0],projection.groups)))
                def post(_module,args,output):
                    torch.cuda.synchronize();timings[name].append(time.perf_counter()-starts[name].pop())
                hooks.extend([module.register_forward_pre_hook(pre),module.register_forward_hook(post)])
            instrument(self.model,'whole')
            if spec['family']!='text':
                instrument(self.model.model.visual,'vision')
                instrument(self.model.model.visual.patch_embed,'patch')
                instrument(self.model.model.language_model,'language')
            else:instrument(self.model.model,'language')
        generate_started=time.perf_counter()
        try:
            with torch.inference_mode():out=self.model.generate(**inputs,do_sample=False,num_beams=1,max_new_tokens=self.config.get('max_new_tokens',768))
            torch.cuda.synchronize()
        finally:
            for handle in hooks:handle.remove()
        generate_ms=(time.perf_counter()-generate_started)*1000
        tokens=out[0,inputs.input_ids.shape[1]:].detach().cpu().tolist()
        raw=decoder.decode(tokens,skip_special_tokens=True,clean_up_tokenization_spaces=False).strip()
        self.calls.append({'stage':stage,'model_role':role,'profiling_enabled':bool(self.config.get('profile_calls',False)),'model_id':spec['model_id'],'revision':spec['revision'],'runtime_ms':(time.perf_counter()-started)*1000,
                           'input_tokens':int(inputs.input_ids.shape[1]),'output_tokens':len(tokens),'raw_output':raw,
                           'rendered_prompt':text,'payload_sha256':hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
                           'model_load_ms':load_ms,'preprocess_ms':preprocessing_ms,'generate_ms':generate_ms,
                           'first_forward_ms':timings['whole'][0]*1000 if timings['whole'] else None,
                           'decode_forward_ms':sum(timings['whole'][1:])*1000 if timings['whole'] else None,
                           'vision_forward_ms':sum(timings['vision'])*1000 if self.config.get('profile_calls',False) else None,
                           'patch_forward_ms':sum(timings['patch'])*1000 if self.config.get('profile_calls',False) else None,
                           'language_prefill_ms':timings['language'][0]*1000 if timings['language'] else None,
                           'language_decode_ms':sum(timings['language'][1:])*1000,
                           'forward_count':len(timings['whole']),'patch_metadata':patch_metadata,
                           'parameter_devices':sorted({str(p.device) for p in self.model.parameters()}),
                           'parameter_dtypes':sorted({str(p.dtype) for p in self.model.parameters()}),
                           'gpu':torch.cuda.get_device_name(0),'torch_threads':torch.get_num_threads(),
                           'cudnn_version':torch.backends.cudnn.version(),'input_keys':list(inputs.keys()),
                           'image_grid_thw':inputs['image_grid_thw'].tolist() if 'image_grid_thw' in inputs else None})
        return raw
