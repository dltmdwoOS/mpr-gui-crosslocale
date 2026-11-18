"""Evaluation-only adapter: labels never enter editor generation."""
import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace

from run_stem_only_gui import read, write, jsonl, unique
from run_overnight_two import completed_batches
from followup_rel_4lang.method_dev.exact_batch_reuse import build_index, batch_key
from mpr_crosslocale.methods.selective_alignment.schemas import digest, fields, render
from mpr_crosslocale.inference.answer_parser import parse_label


def infer(repo, root, work, rows, rewritten, condition, solver, contract, backend, mock):
    import torch
    from mpr_crosslocale.models.qwen25vl import Qwen25VLAdapter
    spec = contract['solvers'][solver]
    profile, model = spec['downstream'], spec['downstream']['model_config']
    labels = unique(read(root / 'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels) != contract['labels_sha256']:
        raise ValueError('Evaluation labels changed')
    originals, changes = unique(rows), unique(rewritten)
    if set(originals) != set(changes):
        raise ValueError('Incomplete rewritten inputs')
    for pid, row in changes.items():
        for k in ('parallel_id', 'source_language', 'gui_language', 'image_path', 'image_sha256', 'option_order'):
            if row[k] != originals[pid][k]:
                raise ValueError('Paired invariant changed: ' + k)
        if row['modified_question'] != render(fields(row)):
            raise ValueError('Render mismatch')
    queue = [{'pair_id': r['pair_id'], 'parallel_id': r['parallel_id'],
              'image_paths': [str(repo / r['image_path'])], 'question_raw': r['modified_question'],
              'gold_label': labels[r['pair_id']]['gold_answer']} for r in sorted(rewritten, key=lambda r: r['pair_id'])]
    env = {'software': backend.software, 'hardware': backend.hardware}
    images = {p: r['image_sha256'] for p, r in originals.items()}
    index, conflicts, adapter = {}, set(), None
    t = time.perf_counter()
    if not mock:
        from transformers import AutoProcessor
        processor = AutoProcessor.from_pretrained(spec['config']['models']['editor_vlm']['path'],
            local_files_only=True, use_fast=profile['processor_use_fast'],
            min_pixels=model['min_pixels'], max_pixels=model['max_pixels'])
        for row in queue:
            row['rendered_prompt'] = processor.apply_chat_template(
                Qwen25VLAdapter.build_messages(row, model['prompt_profile'], profile['system_prompt']),
                tokenize=False, add_generation_prompt=True)
        sources = list(spec['reuse_sources'])
        # Whole completed batches only, including a previously interrupted matrix attempt.
        for path in sorted(work.parent.glob('*/predictions.jsonl')):
            ep = path.parent / 'environment.json'
            if ep.exists() and json.loads(ep.read_text()) == env:
                subset = completed_batches(path)
                if subset:
                    sources.append({'path': str(path), 'downstream': profile, 'seed': contract['seed'],
                                    'environment': env, 'predictions': subset})
        usable = []
        for source in sources:
            preds = source['predictions'] if 'predictions' in source else read(Path(source['path']))
            if all(r['pair_id'] in images for r in preds):
                usable.append({**source, 'predictions': preds})
        index, conflicts = build_index(usable, profile, contract['seed'], images, env)
    work.mkdir(parents=True, exist_ok=True)
    # Preserve partial predictions before replacing them; they have already entered the index.
    pred_path = work / 'predictions.jsonl'
    if pred_path.exists():
        pred_path.replace(work / f'partial_{time.time_ns()}.jsonl')
    write(work / 'environment.json', env)
    write(work / 'contract.json', {'downstream': profile, 'seed': contract['seed'],
          'parent_sha256': digest(contract), 'queue_sha256': digest(queue),
          'condition': condition, 'new_conversation_per_prediction': True})
    reused = new = 0
    with pred_path.open('w') as stream:
        for start in range(0, len(queue), profile['batch_size']):
            batch = queue[start:start + profile['batch_size']]
            hit = None if mock else index.get(batch_key(profile, contract['seed'], batch, images, env))
            if mock:
                predictions = [SimpleNamespace(raw_output='A', rendered_prompt='MOCK', prompt_token_count=0,
                                                output_token_count=0) for _ in batch]
                elapsed, peak = 0, None
            elif hit:
                predictions = [SimpleNamespace(raw_output=r['generated_text'], rendered_prompt=r['rendered_prompt'],
                                prompt_token_count=r['prompt_tokens'], output_token_count=r['output_tokens']) for r in hit['rows']]
                elapsed, peak = hit['rows'][0]['batch_runtime_ms'], hit['rows'][0]['peak_reserved_bytes']
            else:
                if adapter is None:
                    backend.ensure_loaded()
                    adapter = object.__new__(Qwen25VLAdapter)
                    adapter.model_id, adapter.revision = model['model_id'], model['revision']
                    adapter.model, adapter.processor = backend.model, backend.processor
                    adapter.model_family, adapter.max_input_tokens = model['model_family'], profile['max_input_tokens']
                torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats()
                started = time.perf_counter()
                # No editor chat, previous outputs, past_key_values or cross-query KV cache is supplied.
                predictions = adapter.generate_batch(batch, model['prompt_profile'], model['generation'],
                                system_prompt=profile['system_prompt'], score_labels=profile['score_labels'])
                torch.cuda.synchronize()
                elapsed, peak = (time.perf_counter() - started) * 1000, torch.cuda.max_memory_reserved()
            if len(predictions) != len(batch):
                raise ValueError('Missing output')
            reused += bool(hit); new += not bool(hit)
            for row, pred in zip(batch, predictions, strict=True):
                rec = {'pair_id': row['pair_id'], 'parallel_id': row['parallel_id'], 'condition': condition,
                       'execution_mode': 'mock' if mock else 'gpu', 'status': 'success',
                       'generated_text': pred.raw_output, 'parsed_generated_label': parse_label(pred.raw_output),
                       'rendered_prompt': pred.rendered_prompt, 'prompt_tokens': pred.prompt_token_count,
                       'output_tokens': pred.output_token_count, 'batch_id': condition + ':' + str(start),
                       'batch_size': len(batch), 'batch_runtime_ms': elapsed, 'peak_reserved_bytes': peak,
                       'cache_hit': bool(hit), 'new_batch_runtime_ms': 0 if hit else elapsed,
                       'reuse_provenance': {'source': hit['source'], 'batch_id': hit['batch_id']} if hit else None}
                stream.write(json.dumps(rec, ensure_ascii=False) + '\n')
            stream.flush()
            print(f'INFER {solver} {condition} {start + len(batch)}/{len(queue)} reused={bool(hit)}', flush=True)
    write(work / 'cost.json', {'wall_seconds': time.perf_counter() - t, 'reused_batches': reused,
                              'new_batches': new, 'conflicting_batch_keys': len(conflicts)})
    (work / 'COMPLETE').write_text('complete\n')
