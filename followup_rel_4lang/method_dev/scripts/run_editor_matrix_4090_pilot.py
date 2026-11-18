"""Run a fresh, paired O / V-D-S / V-D-H pilot on one RTX 4090."""
import argparse
import fcntl
from pathlib import Path
import time

from run_editor_matrix import ROOT, REPO, load, sha, TextEditor, matrix, refinement
from run_editor_matrix_remaining import LABELS, SOLVERS, CELLS, primary_ids, source_key
from run_stem_only_gui import read, unique, write, jsonl
from editor_matrix_eval import infer
from compare_end_to_end import batch_share, call_map, call_seconds
from mpr_crosslocale.methods.selective_alignment.schemas import digest, fields, render, validate_input

SOURCE = ROOT / 'artifacts/gpu_ocr_screen_paddle_v1/ppocrv5_cuda'
INPUT_SHA = '54357eb6778dc4b545924fb4ceba380a8b696a98c0612a8d7a985d720d2f7a8a'
INVENTORY_SHA = 'b6c1c52ed0ed523dfb9d577cb07354bee6d26b241665623242842d79853770c8'
LABELS_DIGEST = '989b62ae5fcff064253ec8a31fcc2eb2ba20d15f4fd119dd350b6a44e26df3dd'
REVISIONS = {'8B': '0c351dd01ed87e9c1b53cbc748cba10e6187ff3b', '4B': 'ebb281ec70b05090aa6165b016eac8ec08e71b17'}


def select_rows(items):
    from PIL import Image
    source = SOURCE / 'inputs.jsonl'
    inventory = SOURCE / 'ocr/attempt_0001/inventories.jsonl'
    if sha(source) != INPUT_SHA or sha(inventory) != INVENTORY_SHA:
        raise ValueError('PP-OCR Screen data differs from the frozen source')
    rows = read(source)
    labels = unique(read(LABELS))
    if digest(labels) != LABELS_DIGEST:
        raise ValueError('Rebuild the frozen evaluation labels via audit.py')
    main = set(primary_ids(rows, labels))
    eligible = [r for r in rows if r['pair_id'] in main]
    dimensions = {}
    score = {}
    for row in eligible:
        image_path = REPO / row['image_path']
        if image_path not in dimensions:
            with Image.open(image_path) as im:
                dimensions[image_path] = im.width * im.height
        item = row['parallel_id']
        score[item] = max(score.get(item, 0), dimensions[image_path])
    selected = set(sorted(score, key=lambda item: (-score[item], item))[:items])
    rows = [r for r in eligible if r['parallel_id'] in selected]
    if len(rows) != 12 * items:
        raise ValueError('Pilot items must retain all 12 directed language pairs')
    inv = {r['image_sha256']: r for r in read(inventory)}
    for row in rows:
        validate_input(row)
        if sha(REPO / row['image_path']) != row['image_sha256'] or inv[row['image_sha256']]['gui_language'] != row['gui_language']:
            raise ValueError('Screenshot or inventory linkage differs')
    return rows, inv, labels


def run(output, solver, items, mock):
    from huggingface_hub import try_to_load_from_cache
    started = time.perf_counter()
    rows, inv, labels = select_rows(items)
    model_id, revision = f'Qwen/Qwen3-VL-{solver}-Instruct', REVISIONS[solver]
    model_path = '<mock>'
    min_free = 0
    if not mock:
        import torch
        if torch.cuda.device_count() != 1 or 'RTX 4090' not in torch.cuda.get_device_name(0):
            raise ValueError('Select one RTX 4090 via CUDA_VISIBLE_DEVICES')
        config_file = try_to_load_from_cache(model_id, 'config.json', revision=revision)
        if not isinstance(config_file, str):
            raise ValueError(f'Download {model_id} at pinned revision {revision} first')
        model_path = str(Path(config_file).parent)
        index = load(Path(model_path) / 'model.safetensors.index.json')
        if any(not (Path(model_path) / shard).is_file() for shard in index['weight_map'].values()):
            raise ValueError('The pinned checkpoint is incomplete')
        min_free = index['metadata']['total_size'] / 2**30
    model = {'model_id': model_id, 'revision': revision, 'family': 'qwen3_vl', 'path': model_path}
    downstream = {
        'model_config': {'model_id': model_id, 'revision': revision, 'model_family': 'qwen3_vl', 'dtype': 'bfloat16',
                         'attn_implementation': 'sdpa', 'patch_embed_memory_format': 'channels_last_3d',
                         'min_pixels': 262144, 'max_pixels': 2097152, 'prompt_profile': 'mpr_label_only_v1',
                         'generation': {'do_sample': False, 'num_beams': 1, 'max_new_tokens': 2, 'temperature': None}},
        'system_prompt': 'You are a GUI reasoning assistant. Inspect the GUI image and answer the multiple-choice question. Respond with exactly one label: A, B, C, or D.',
        'batch_size': 3, 'max_input_tokens': 4096, 'score_labels': True, 'processor_use_fast': True,
    }
    backend = TextEditor({'seed': 42, 'min_free_gpu_gib': min_free, 'output_tokens': matrix.LIMITS,
                          'models': {'editor_vlm': model}}, REPO, output / 'cache', 'V', mock)
    contract = {'seed': 42, 'execution_mode': 'mock' if mock else 'gpu', 'labels_sha256': LABELS_DIGEST,
                'solvers': {solver: {'downstream': downstream, 'config': {'models': {'editor_vlm': model}},
                                     'reuse_sources': []}},
                'inputs_sha256': digest(rows), 'inventory_sha256': INVENTORY_SHA, 'editor_limits': matrix.LIMITS,
                'minimum_free_weight_gib': min_free, 'hardware': backend.hardware, 'software': backend.software}
    if (output / 'contract.json').exists() and load(output / 'contract.json') != contract:
        raise ValueError('Pilot contract changed; select a new output directory')
    write(output / 'contract.json', contract)
    jsonl(output / 'inputs.jsonl', rows)
    inputs = {source_key(r): r for r in rows}
    extraction = {k: refinement.extract(r, backend) for k, r in sorted(inputs.items())}
    jsonl(output / 'extractions.jsonl', [{'source_key': k, **value} for k, value in extraction.items()])
    rewrites = {}
    for cell in ('O', *CELLS):
        rewrites[cell] = []
        for row in rows:
            if cell == 'O':
                edits, modified = {}, fields(row)
            else:
                edits = matrix.rewrite(row, inv[row['image_sha256']], extraction[source_key(row)]['referents'],
                                       backend, 'D', cell[-1])
                modified = edits.pop('output')
            rewrites[cell].append({**row, **edits, 'question_stem': modified['question_stem'],
                                   'options': {k: modified[k] for k in 'ABCD'}, 'modified_question': render(modified)})
        jsonl(output / f'{cell}_rewritten.jsonl', rewrites[cell])
        target = output / 'infer' / cell
        if not (target / 'COMPLETE').is_file():
            infer(REPO, ROOT, target, rows, rewrites[cell], cell, solver, contract, backend, mock)
    write(output / 'calls.json', backend.calls)
    summary = {'empirical': not mock, 'pairs': len(rows), 'semantic_items': items,
               'wall_seconds': time.perf_counter() - started, 'model_loads': backend.load_events, 'conditions': {}}
    if not mock:
        for cell in rewrites:
            pred = read(output / 'infer' / cell / 'predictions.jsonl')
            correct = sum(r['parsed_generated_label'] == labels[r['pair_id']]['gold_answer'] for r in pred)
            summary['conditions'][cell] = {
                'correct': correct, 'accuracy': correct / len(rows),
                'extraction_seconds': call_seconds(call_map(extraction.values())) if cell != 'O' else 0,
                'editing_seconds': call_seconds(call_map(rewrites[cell])) if cell != 'O' else 0,
                'final_vlm_seconds': batch_share(pred, lambda _: True)['seconds'],
                'peak_solver_reserved_bytes': max(r['peak_reserved_bytes'] for r in pred),
            }
    write(output / 'summary.json', summary)
    print('PILOT COMPLETE', output, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--solver', choices=SOLVERS, default='8B')
    parser.add_argument('--items', type=int, choices=range(1, 21), default=4)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--mock', action='store_true')
    args = parser.parse_args()
    default = ROOT / 'artifacts' / ('ppocr_vd_4090_pilot_' + args.solver + ('_mock' if args.mock else ''))
    output = (args.output_dir or default).resolve()
    if not output.is_relative_to(ROOT / 'artifacts'):
        raise ValueError('Output must be inside method_dev/artifacts')
    output.mkdir(parents=True, exist_ok=True)
    lock = ROOT / 'artifacts' / ('search_pipeline_mock.lock' if args.mock else 'search_pipeline_gpu.lock')
    with lock.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(output, args.solver, args.items, args.mock)
