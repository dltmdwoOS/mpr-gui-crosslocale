"""Prepare (default) or run the Screen E1/M0 inventory-source ablation."""
import argparse
from collections import Counter
import fcntl
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / '01_code/src'), str(REPO), str(Path(__file__).parent)]
from run_stem_only_gui import read, write, jsonl, unique
from run_stem_refinement_2x2 import latest, extraction, record, ExperimentBackend, save_cost
from run_two_stage_v2 import budget
from mpr_crosslocale.methods.selective_alignment.schemas import digest, validate_input
from followup_rel_4lang.method_dev import ocr_inventory as ocr
from followup_rel_4lang.method_dev.two_stage_v2 import pipeline, prompts
import run_source_copy_rewrite as evaluator

CONDITION = 'E1_M0_EASYOCR'
DEFAULT_OUTPUT = ROOT / 'artifacts/ocr_inventory_screen_v1'
DEFAULT_CONFIG = ROOT / 'configs/ocr_inventory_easyocr_v1.json'
MODEL_DIR = Path('/home/jovyan/seungjae/.cache/easyocr/model')


def load(path):
    return json.loads(Path(path).read_text())


def verify(output):
    c = load(output / 'contract.json')
    for name, sha in c['source_sha256'].items():
        if hashlib.sha256((REPO / name).read_bytes()).hexdigest() != sha:
            raise ValueError('Frozen source changed: ' + name)
    if digest(read(output / 'inputs.jsonl')) != c['inputs_sha256']:
        raise ValueError('Input lock changed')
    return c


def prepare(output, config_path, mock=False):
    source = ROOT / 'artifacts/stem_refinement_2x2_screen_v1'
    sc, done = load(source / 'contract.json'), load(source / 'COMPLETE.json')
    if done['execution_mode'] != 'gpu' or done['contract_sha256'] != digest(sc):
        raise ValueError('Completed Screen source required')
    inputs = read(source / 'inputs.jsonl')
    if len(inputs) != 288 or digest(inputs) != sc['inputs_sha256']:
        raise ValueError('Expected unchanged ordered Screen 288 rows, including 48 pilot companions')
    unique(inputs)
    for row in inputs:
        validate_input(row)
    exdir = latest(source / 'extraction', 'E1')
    ext = {r['source_key']: r for r in read(exdir / 'extractions.jsonl')}
    for row in inputs:
        if digest(prompts.extraction_payload(row, stem_only=True)) not in ext:
            raise ValueError('Missing frozen E1 source extraction')
        if hashlib.sha256((REPO / row['image_path']).read_bytes()).hexdigest() != row['image_sha256']:
            raise ValueError('Screenshot checksum mismatch')
    cfg = load(config_path)
    if cfg['engine'] != 'easyocr' or cfg['threads'] > 3 or cfg['confidence_filter'] is not None:
        raise ValueError('Unexpected OCR protocol')
    if cfg['readtext']['workers'] > 3 or cfg['readtext']['paragraph'] or cfg['readtext']['detail'] != 1:
        raise ValueError('Unexpected OCR output protocol')
    targets = {}
    for row in inputs:
        previous = targets.setdefault(row['image_sha256'], row['gui_language'])
        if previous != row['gui_language']:
            raise ValueError('Same image assigned incompatible GUI languages')
    seed_sources = []
    srcpred = latest(source / 'E1_M0', 'infer') / 'evaluation/predictions.jsonl'
    envpath = srcpred.parent.parent / 'environment.json'
    env = load(envpath)
    seed_sources.append({'path': str(srcpred), 'downstream': sc['downstream'],
                         'seed': sc['seed'], 'environment': env})
    # Existing mixed-condition sources carry their environment explicitly.
    seed_sources.extend(sc['legacy_reuse_sources'])
    captures = [Path(__file__), config_path, ROOT / 'ocr_inventory.py',
                ROOT / 'scripts/report_ocr_inventory.py', ROOT / 'requirements-ocr.txt',
                source / 'contract.json', source / 'COMPLETE.json', source / 'inputs.jsonl',
                exdir / 'extractions.jsonl', exdir / 'COMPLETE',
                Path(sc['inventory_path']), srcpred, srcpred.parent / 'contract.json', envpath,
                ROOT / 'scripts/run_stem_refinement_2x2.py', ROOT / 'scripts/run_source_copy_rewrite.py',
                ROOT / 'two_stage_v2/pipeline.py', ROOT / 'two_stage_v2/prompts.py',
                ROOT / 'two_stage_v2/backend.py', ROOT / 'two_stage_v2/legacy.py',
                ROOT / 'visual_rewrite_backend.py', ROOT / 'exact_batch_reuse.py']
    captures += [Path(s['path']) for s in seed_sources]
    captures += list((REPO / '01_code/src/mpr_crosslocale/methods/selective_alignment').glob('*.py'))
    captures += [REPO / '01_code/src/mpr_crosslocale/models/qwen25vl.py',
                 REPO / '01_code/src/mpr_crosslocale/models/qwen3_memory.py',
                 REPO / '01_code/src/mpr_crosslocale/inference/prompts.py']
    # Freeze relevant source code against its earlier run, without reading gold artifacts.
    for path in captures:
        expected = sc['source_sha256'].get(str(path.resolve()))
        if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Inherited frozen source changed: ' + str(path))
    c = {'version': cfg['version'], 'execution_mode': 'mock' if mock else 'gpu',
         'condition': CONDITION, 'ocr_config': cfg, 'config': sc['config'],
         'inference_config': sc['inference_config'], 'downstream': sc['downstream'], 'seed': sc['seed'],
         'inputs_sha256': digest(inputs), 'labels_sha256': sc['labels_sha256'],
         'extraction_path': str(exdir / 'extractions.jsonl'), 'baseline_inventory': sc['inventory_path'],
         'baseline_predictions': str(srcpred), 'reuse_sources': seed_sources,
         'pairs_executed': 288, 'primary_pairs': 240, 'primary_items': 20,
         'ocr_unique_images_executed': len(targets), 'model_dir': str(MODEL_DIR),
         'source_sha256': {str(p.resolve().relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in captures},
         'policy': 'Only inventory provider changes. Frozen E1 output/M0 prompt; original options. '
                   'No VLM fallback. Same full sorted 288-row batch3 queue; score main240. '
                   'Reuse only complete ordered batches with identical rendered prompts/images/profile/seed/environment.'}
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'contract.json').exists() and load(output / 'contract.json') != c:
        raise ValueError('Plan changed; use a new --output-dir')
    write(output / 'contract.json', c)
    jsonl(output / 'inputs.jsonl', inputs)
    return c


def ocr_stage(output, attempt, mock):
    c = verify(output)
    cfg = c['ocr_config']
    if not mock and metadata.version('easyocr') != cfg['package_version']:
        raise ValueError('Install the pinned EasyOCR package using setup_ocr.sh')
    source = {r['image_sha256']: r for r in read(output / 'inputs.jsonl')}
    queue = sorted(source.items(), key=lambda x: (x[1]['gui_language'], x[0]))
    attempt.mkdir(parents=True)
    started = time.perf_counter()
    reader, language = None, None
    load_seconds, results = {}, []
    if not mock:
        # Download/check all four readers before any measured OCR call.
        # Subsequent resume refuses changed model bytes rather than mixing revisions.
        weights = load(output / 'ocr_weights.json') if (output / 'ocr_weights.json').exists() else None
        if weights and ocr.weight_manifest(MODEL_DIR) != weights:
            raise ValueError('OCR weight checksum changed')
        if weights is None:
            for lang in sorted(cfg['languages']):
                t = time.perf_counter()
                reader = ocr.reader_factory(lang, cfg, MODEL_DIR, download=True)
                load_seconds[lang + '_download_check'] = time.perf_counter() - t
                del reader
            reader = None
            write(output / 'ocr_weights.json', ocr.weight_manifest(MODEL_DIR))
        # Do not use the VLM global lock for CPU-only OCR.
    weights = {} if mock else load(output / 'ocr_weights.json')
    cache = output / 'ocr_cache'
    cache.mkdir(exist_ok=True)
    with (attempt / 'inventories.jsonl').open('w') as f:
        for i, (sha, row) in enumerate(queue, 1):
            if hashlib.sha256((REPO / row['image_path']).read_bytes()).hexdigest() != sha:
                raise ValueError('Screenshot changed')
            key = digest({'image_sha256': sha, 'gui_language': row['gui_language'], 'config': cfg, 'weights': weights, 'mock': mock})
            target = cache / (key + '.json')
            if target.exists():
                result = {**load(target), 'cache_hit': True}
            else:
                if not mock and row['gui_language'] != language:
                    if reader is not None:
                        del reader
                        import gc
                        gc.collect()
                    t = time.perf_counter()
                    reader = ocr.reader_factory(row['gui_language'], cfg, MODEL_DIR, download=False)
                    load_seconds[row['gui_language']] = time.perf_counter() - t
                    language = row['gui_language']
                recognize = (lambda _: []) if mock else (lambda image: reader.readtext(image, **cfg['readtext']))
                result = ocr.transcribe(recognize, str(REPO / row['image_path']))
                result.update(image_sha256=sha, gui_language=row['gui_language'], image_path=row['image_path'],
                              engine='easyocr', execution_mode='mock' if mock else cfg['device'],
                              cache_key=key, cache_hit=False, weights_sha256=digest(weights))
                write(target, result)
            results.append(result)
            f.write(json.dumps(result, ensure_ascii=False) + '\n')
            f.flush()
            print(f"OCR {i}/{len(queue)} {row['gui_language']} {result['status']} strings={len(result['visible_strings'])} cached={result['cache_hit']}", flush=True)
    write(attempt / 'cost.json', {'execution_mode': 'mock' if mock else cfg['device'],
          'wall_seconds': time.perf_counter() - started, 'reader_load_seconds': load_seconds,
          'images': len(results), 'statuses': dict(Counter(r['status'] for r in results)),
          'logical_runtime_seconds': sum(r['runtime_ms'] for r in results) / 1000,
          'new_runtime_seconds': sum(r['runtime_ms'] for r in results if not r['cache_hit']) / 1000})
    (attempt / 'COMPLETE').write_text('complete\n')


def rewrite_stage(output, attempt, mock):
    c = verify(output)
    if not mock:
        budget(c['config'])
    backend = ExperimentBackend(c['config'], REPO, output / 'matching_cache', mock)
    ext = {r['source_key']: r for r in read(Path(c['extraction_path']))}
    inv = {r['image_sha256']: r for r in read(latest(output, 'ocr') / 'inventories.jsonl')}
    attempt.mkdir(parents=True)
    started, complete = time.perf_counter(), False
    inputs = read(output / 'inputs.jsonl')
    try:
        with (attempt / 'rewritten.jsonl').open('w') as f:
            for i, row in enumerate(inputs, 1):
                refs = ext[digest(prompts.extraction_payload(row, stem_only=True))]['referents']
                inventory = inv[row['image_sha256']]
                if inventory['status'] == 'failed':
                    from mpr_crosslocale.methods.selective_alignment.schemas import fields
                    result = {'output': fields(row), 'edits': [], 'attempts': [],
                              'status': 'fallback_original', 'errors': ['ocr_inventory_failed']}
                else:
                    result = pipeline.selective(row, refs, backend, inventory)
                rr = record(row, result, refs, inventory, CONDITION, mock)
                f.write(json.dumps(rr, ensure_ascii=False) + '\n')
                f.flush()
                print(f"MATCH {i}/{len(inputs)} {rr['status']}", flush=True)
        complete = True
    finally:
        save_cost(attempt, backend, started, complete)
    (attempt / 'COMPLETE').write_text('complete\n')


def infer_stage(output, attempt, mock):
    c = verify(output)
    attempt.mkdir(parents=True)
    view = attempt / 'view'
    view.mkdir()
    ic = {'execution_mode': c['execution_mode'], 'config': c['inference_config'], 'downstream': c['downstream'],
          'seed': c['seed'], 'labels_sha256': c['labels_sha256'], 'reuse_sources': [] if mock else c['reuse_sources']}
    write(view / 'contract.json', ic)
    jsonl(view / 'inputs.jsonl', read(output / 'inputs.jsonl'))
    evaluator.CONDITION = CONDITION
    evaluator.infer(view, latest(output, 'rewrite'), attempt / 'evaluation', mock)
    (attempt / 'COMPLETE').write_text('complete\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', action='store_true')
    p.add_argument('--mock', action='store_true')
    p.add_argument('--output-dir', type=Path)
    p.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    p.add_argument('--worker', choices=['ocr', 'rewrite', 'infer'])
    p.add_argument('--attempt', type=Path)
    a = p.parse_args()
    output = (a.output_dir or (DEFAULT_OUTPUT.with_name(DEFAULT_OUTPUT.name + '_mock') if a.mock else DEFAULT_OUTPUT)).resolve()
    if not output.is_relative_to(REPO):
        raise ValueError('Output must be inside the repository')
    if a.worker:
        if not a.attempt or not a.attempt.resolve().is_relative_to(output):
            raise ValueError('Worker attempt must be inside output')
        {'ocr': ocr_stage, 'rewrite': rewrite_stage, 'infer': infer_stage}[a.worker](output, a.attempt, a.mock)
        return
    c = prepare(output, a.config.resolve(), a.mock)
    print(f"PREPARED main=240 executed=288 images={c['ocr_unique_images_executed']} OCR={c['ocr_config']['device']}", flush=True)
    if not a.run:
        return
    with (output / 'run.lock').open('a') as local:
        fcntl.flock(local, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (output / 'COMPLETE.json').exists():
            print('Already complete; regenerate report without rerunning inference.', flush=True)
        else:
            started = time.perf_counter()
            for stage in ('ocr', 'rewrite', 'infer'):
                try:
                    latest(output, stage)
                    print('SKIP completed ' + stage, flush=True)
                    continue
                except ValueError:
                    pass
                # The same nonblocking lock as the other project GPU pipelines.
                needs_gpu = not a.mock and (stage != 'ocr' or c['ocr_config']['device'] != 'cpu')
                lock = None
                try:
                    if needs_gpu:
                        lock = (ROOT / 'artifacts/search_pipeline_gpu.lock').open('a')
                        try:
                            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            raise RuntimeError('Another project GPU pipeline is running. OCR cache is saved; rerun after it finishes.') from None
                    folder = output / stage
                    folder.mkdir(exist_ok=True)
                    attempt = folder / f'attempt_{len(list(folder.glob("attempt_*"))) + 1:04d}'
                    cmd = [sys.executable, '-u', str(Path(__file__)), '--output-dir', str(output), '--worker', stage, '--attempt', str(attempt)]
                    if a.mock:
                        cmd.append('--mock')
                    print('RUN ' + stage, flush=True)
                    subprocess.run(cmd, cwd=REPO, check=True)
                finally:
                    if lock is not None:
                        lock.close()
            write(output / 'COMPLETE.json', {'execution_mode': c['execution_mode'], 'contract_sha256': digest(c),
                  'last_invocation_wall_seconds': time.perf_counter() - started,
                  'note': 'Resumed invocation excludes previous attempts; stage costs and original cache runtime retained.'})
        subprocess.run([sys.executable, str(ROOT / 'scripts/report_ocr_inventory.py'), '--output-dir', str(output)], cwd=REPO, check=True)


if __name__ == '__main__':
    main()
