"""Native LM/VLM text-only editor, with per-call timing and no visual input."""
import json
import time
from pathlib import Path

from .two_stage_v2.backend import Backend
from .editor_matrix import LIMITS
from mpr_crosslocale.methods.selective_alignment.schemas import digest


class TextEditor(Backend):
    def __init__(self, config, repo, cache, kind, mock=False):
        super().__init__(config, repo, cache, mock)
        self.kind = kind
        self.load_events = []

    def ensure_loaded(self):
        if self.mock:
            return 0
        ms = self._load('text' if self.kind == 'L' else 'editor_vlm')
        if ms:
            self.load_events.append({'model_load_ms': ms, 'kind': self.kind})
        return ms

    def __call__(self, stage, role, system, user, image=None):
        if role != 'text' or image is not None or stage not in LIMITS:
            raise ValueError('Text-only allowlist violated')
        spec = self.config['models']['text' if self.kind == 'L' else 'editor_vlm']
        messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]
        generation = {'do_sample': False, 'num_beams': 1, 'max_new_tokens': LIMITS[stage],
                      'use_cache': True, 'logits_to_keep': 1}
        key = digest({'messages': messages, 'model': spec, 'generation': generation,
                      'input_limit': 4096, 'seed': self.config['seed'], 'kind': self.kind,
                      'backend_sha': digest(Path(__file__).read_text()), 'software': self.software,
                      'hardware': self.hardware, 'mock': self.mock})
        path = self.cache / (key + '.json')
        hit = path.exists()
        if hit:
            record = json.loads(path.read_text())
        elif self.mock:
            if stage.startswith('matrix_'):
                data = json.JSONDecoder().raw_decode(user[user.index('{'):])[0]
                requested = json.JSONDecoder().raw_decode(user.split('already fixed: ', 1)[1])[0]
                result = {'translations': {r['span_id']: None for r in data.get('referents', [])},
                          'stem_edits': [], 'options': data['options']}
                raw = json.dumps({k: result[k] for k in requested}, ensure_ascii=False)
            else:
                raw = self._mock(stage, user)
            record = {'raw_output': raw, 'rendered_prompt': 'MOCK', 'input_tokens': 0, 'output_tokens': 0,
                      'runtime_ms': 0, 'model_load_ms': 0, 'execution_mode': 'mock'}
        else:
            import torch
            load_ms = self.ensure_loaded()
            start = time.perf_counter()
            tokenizer = self.processor if self.kind == 'L' else self.processor.tokenizer
            rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                                     **({'enable_thinking': False} if self.kind == 'L' else {}))
            inputs = tokenizer([rendered], return_tensors='pt')
            tokens = int(inputs.input_ids.shape[1])
            if tokens > 4096:
                raise RuntimeError(f'Input budget exceeded: {tokens}; no silent truncation')
            tokenize_ms = (time.perf_counter() - start) * 1000
            t = time.perf_counter()
            inputs = inputs.to('cuda:0')
            torch.cuda.synchronize()
            transfer_ms = (time.perf_counter() - t) * 1000
            if set(inputs) - {'input_ids', 'attention_mask', 'token_type_ids'}:
                raise RuntimeError('Unexpected visual inputs in text-only editor')
            events, active, visual = [], [], [0]
            def pre(module, args, kwargs):
                a, b = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
                a.record(); active.append((a, b))
            def post(module, args, output):
                a, b = active.pop(); b.record(); events.append((a, b))
            def visual_pre(module, args):
                visual[0] += 1
            handles = [self.model.register_forward_pre_hook(pre, with_kwargs=True),
                       self.model.register_forward_hook(post)]
            vision = getattr(self.model, 'visual', None) or getattr(getattr(self.model, 'model', None), 'visual', None)
            if self.kind == 'V' and vision is None:
                raise RuntimeError('Cannot instrument visual module')
            if vision is not None:
                handles.append(vision.register_forward_pre_hook(visual_pre))
            torch.cuda.reset_peak_memory_stats()
            t = time.perf_counter()
            try:
                with torch.inference_mode():
                    out = self.model.generate(**inputs, **generation)
                torch.cuda.synchronize()
                generation_ms = (time.perf_counter() - t) * 1000
            finally:
                for handle in handles:
                    handle.remove()
            generated = out[0, tokens:].detach().cpu().tolist()
            raw = tokenizer.decode(generated, skip_special_tokens=True, clean_up_tokenization_spaces=False).strip()
            if visual[0]:
                raise RuntimeError('Visual forward unexpectedly executed')
            eos = self.model.generation_config.eos_token_id
            eos = [eos] if isinstance(eos, int) else (eos or [])
            record = {'raw_output': raw, 'rendered_prompt': rendered, 'input_tokens': tokens,
                      'output_tokens': len(generated), 'runtime_ms': (time.perf_counter() - start) * 1000,
                      'tokenization_ms': tokenize_ms, 'transfer_ms': transfer_ms, 'generation_ms': generation_ms,
                      'prefill_forward_gpu_ms': events[0][0].elapsed_time(events[0][1]) if events else None,
                      'decode_forward_gpu_ms': sum(a.elapsed_time(b) for a, b in events[1:]),
                      'forward_calls': len(events), 'visual_forward_calls': visual[0], 'vision_tokens': 0,
                      'input_keys': sorted(inputs), 'model_load_ms': load_ms,
                      'output_limit_reached': len(generated) >= LIMITS[stage],
                      'ended_with_eos': bool(generated and generated[-1] in eos),
                      'peak_reserved_bytes': torch.cuda.max_memory_reserved(),
                      'peak_allocated_bytes': torch.cuda.max_memory_allocated(), 'execution_mode': 'gpu'}
        record = {**record, 'stage': stage, 'role': role, 'editor_kind': self.kind, 'messages': messages,
                  'system_prompt': system, 'user_prompt': user, 'model_id': spec['model_id'],
                  'revision': spec['revision'], 'generation': generation, 'cache_key': key, 'cache_hit': hit,
                  'prompt_sha256': digest(messages), 'software': self.software, 'hardware': self.hardware}
        if not hit:
            self.cache.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(record, ensure_ascii=False) + '\n'); temp.replace(path)
        self.calls.append(record)
        return record
