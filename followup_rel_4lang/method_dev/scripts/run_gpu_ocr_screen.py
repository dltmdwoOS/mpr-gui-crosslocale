"""Prepare/run two CUDA inventory providers with shared E1/M0 and 8B/4B solvers."""
import argparse
from collections import Counter
import fcntl
import gc
import hashlib
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
from run_stem_refinement_2x2 import latest
from run_overnight_two import completed_batches
from run_ocr_4b import four_b_profile
import run_ocr_inventory as frozen
import run_source_copy_rewrite as evaluator
from mpr_crosslocale.methods.selective_alignment.schemas import digest, validate_input
from followup_rel_4lang.method_dev import gpu_ocr_inventory as gpu

DEFAULT_OUTPUT = ROOT / 'artifacts/gpu_ocr_screen_paddle_v1'
CONFIG = ROOT / 'configs/gpu_ocr_screen_v1.json'
CPU = ROOT / 'artifacts/ocr_inventory_screen_v1'
CPU4 = ROOT / 'artifacts/ocr_qwen3_vl_4b_v1'
BASE4 = ROOT / 'artifacts/transfer_qwen3_vl_4b_e1m0_all_v1'
BACKENDS = ('easyocr_cuda', 'ppocrv5_cuda')
SOLVERS = ('8B', '4B')
STAGES = ('ocr', 'rewrite', 'infer_8B', 'infer_4B')
VLM_PY = REPO / '.venv/bin/python'
PP_PY = REPO / '.venv-ocr-gpu/bin/python'


def load(path):
    return json.loads(Path(path).read_text())


def package_versions(python, packages):
    code = 'import importlib.metadata as m,json; print(json.dumps({n:m.version(n) for n in ' + repr(packages) + '}))'
    return json.loads(subprocess.check_output([str(python), '-c', code], text=True, cwd=REPO))


def completed_source(work):
    c, done = load(work / 'contract.json'), load(work / 'COMPLETE.json')
    if done['execution_mode'] != 'gpu' or done['contract_sha256'] != digest(c):
        raise ValueError('Completed GPU source required: ' + str(work))
    return c


def prepare(output, mock=False):
    source = frozen.verify(CPU)
    completed_source(CPU)
    c4 = completed_source(CPU4)
    baseline4 = completed_source(BASE4)
    config4, downstream4 = four_b_profile(source, baseline4)
    rows = read(CPU / 'inputs.jsonl')
    if len(rows) != 288 or digest(rows) != source['inputs_sha256']:
        raise ValueError('Frozen Screen 288-row input required')
    if unique(rows) != unique(read(BASE4 / 'screen/inputs.jsonl')):
        raise ValueError('4B original Screen inputs differ')
    for row in rows:
        validate_input(row)
        if hashlib.sha256((REPO / row['image_path']).read_bytes()).hexdigest() != row['image_sha256']:
            raise ValueError('Screenshot changed')
    protocol = load(CONFIG)
    software = {} if mock else {
        'easyocr_cuda': package_versions(VLM_PY, ['easyocr', 'torch', 'torchvision', 'numpy', 'opencv-python-headless']),
        'ppocrv5_cuda': package_versions(PP_PY, ['rapidocr', 'paddlepaddle-gpu', 'torch', 'numpy', 'opencv-python-headless', 'omegaconf', 'shapely', 'pyclipper', 'opt-einsum', 'nvidia-cudnn-cu13'])}
    solver_defs = {
        '8B': {'config': source['inference_config'], 'downstream': source['downstream'],
               'reuse_sources': list(source['reuse_sources']),
               'O_predictions': load(ROOT / 'artifacts/e1_stem_full_dev_v1/contract.json')['descriptors']['screen']['O_pred'],
               'VLM_predictions': source['baseline_predictions']},
        '4B': {'config': config4, 'downstream': downstream4,
               'reuse_sources': list(c4['descriptors']['screen']['reuse_sources']),
               'O_predictions': c4['descriptors']['screen']['O_predictions'],
               'VLM_predictions': c4['descriptors']['screen']['VLM_E1_M0_predictions']}}
    captures = {REPO / name for name in source['source_sha256']}
    captures.update({Path(__file__), CONFIG, ROOT / 'gpu_ocr_inventory.py',
                     ROOT / 'configs/ppocrv5_paddle_models.json',
                     ROOT / 'scripts/report_gpu_ocr_screen.py', ROOT / 'requirements-ocr-gpu.txt',
                     ROOT / 'scripts/prepare_gpu_ocr_models.py', ROOT / 'scripts/setup_gpu_ocr.sh',
                     ROOT / 'scripts/run_gpu_ocr_screen.sh', ROOT / 'scripts/run_ocr_4b.py',
                     ROOT / 'scripts/run_overnight_two.py', ROOT / 'scripts/compare_end_to_end.py',
                     ROOT / 'scripts/search_pipeline.py', ROOT / 'scripts/report_ocr_4b.py',
                     CPU / 'contract.json', CPU / 'COMPLETE.json',
                     CPU4 / 'contract.json', CPU4 / 'COMPLETE.json',
                     BASE4 / 'contract.json', BASE4 / 'COMPLETE.json',
                     ROOT / 'artifacts/e1_stem_full_dev_v1/contract.json',
                     ROOT / 'artifacts/e1_stem_full_dev_results_snapshot.json',
                     ROOT / 'artifacts/transfer_qwen3_vl_4b_results_snapshot.json'})
    for solver in SOLVERS:
        work = CPU if solver == '8B' else CPU4 / 'screen'
        attempt = latest(work, 'infer')
        pred, env = attempt / 'evaluation/predictions.jsonl', attempt / 'environment.json'
        # The first CPU 8B runner did not save a separate environment file.
        environment = load(env) if env.exists() else source['reuse_sources'][0]['environment']
        spec = solver_defs[solver]
        spec['CPU_predictions'] = str(pred)
        spec['reuse_sources'].append({'path': str(pred), 'downstream': spec['downstream'],
                                      'seed': source['seed'], 'environment': environment})
        if env.exists():
            captures.add(env)
        captures.update({pred, attempt / 'evaluation/contract.json', Path(spec['O_predictions']), Path(spec['VLM_predictions'])})
        captures.update(Path(s['path']) for s in spec['reuse_sources'])
        model = Path(spec['config']['models']['editor_vlm']['path'])
        index = model / 'model.safetensors.index.json'
        if not index.exists() or any(not (model / name).exists() for name in set(load(index)['weight_map'].values())):
            raise ValueError('Pinned VLM checkpoint missing')
    output.mkdir(parents=True, exist_ok=True)
    for backend in BACKENDS:
        work = output / backend
        work.mkdir(exist_ok=True)
        cfg = protocol['backends'][backend]
        weight_lock = {} if mock else gpu.weights(cfg)
        condition = 'E1_M0_' + backend.upper()
        c = {**{k: source[k] for k in ('config', 'inference_config', 'downstream', 'seed', 'inputs_sha256',
                                      'labels_sha256', 'extraction_path', 'baseline_inventory', 'baseline_predictions')},
             'version': protocol['version'], 'execution_mode': 'mock' if mock else 'gpu',
             'condition': condition, 'ocr_config': cfg, 'ocr_software': software.get(backend, {}),
             'ocr_weights': weight_lock, 'solvers': solver_defs,
             'pairs_executed': 288, 'primary_pairs': 240, 'primary_items': 20, 'ocr_unique_images_executed': 128,
             'source_sha256': {str(p.resolve().relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(captures)},
             'policy': protocol['policy'],
             'reuse_policy': 'Only identical complete ordered batches, same checkpoint/profile/seed/software/hardware. No cross-model reuse.'}
        if (work / 'contract.json').exists() and load(work / 'contract.json') != c:
            raise ValueError('Frozen GPU OCR plan changed; choose new --output-dir')
        write(work / 'contract.json', c)
        jsonl(work / 'inputs.jsonl', rows)
    return output


def verify(work):
    c = frozen.verify(work)
    if c['execution_mode'] == 'gpu' and gpu.weights(c['ocr_config']) != c['ocr_weights']:
        raise ValueError('OCR weight lock changed')
    return c


def image_queue(rows, smoke=False):
    targets = {}
    for row in rows:
        if row['image_sha256'] in targets and targets[row['image_sha256']]['gui_language'] != row['gui_language']:
            raise ValueError('Incompatible GUI language for same screenshot')
        targets[row['image_sha256']] = row
    queue = sorted(targets.values(), key=lambda r: (r['gui_language'], r['image_sha256']))
    if smoke:
        queue = [next(r for r in queue if r['gui_language'] == language) for language in ('en', 'zh', 'th', 'ru')]
    return queue


def ocr_stage(work, attempt, mock, smoke=False):
    c = verify(work)
    cfg = c['ocr_config']
    attempt.mkdir(parents=True)
    cache = work / 'ocr_cache'
    cache.mkdir(exist_ok=True)
    queue = image_queue(read(work / 'inputs.jsonl'), smoke)
    started, reader, language, loads, results, profiles = time.perf_counter(), None, None, {}, [], []
    import torch
    for i, row in enumerate(queue, 1):
        sha = row['image_sha256']
        if hashlib.sha256((REPO / row['image_path']).read_bytes()).hexdigest() != sha:
            raise ValueError('Screenshot changed')
        key = digest({'sha256': sha, 'language': row['gui_language'], 'config': cfg,
                      'software': c['ocr_software'], 'weights': c['ocr_weights'], 'mock': mock})
        path = cache / (key + '.json')
        if path.exists() and not smoke:
            result = {**load(path), 'cache_hit': True}
        else:
            if not mock and language != row['gui_language']:
                if reader is not None:
                    if smoke and cfg['engine'] == 'rapidocr':
                        profiles.extend(reader.finish_profiles())
                    del reader
                    gc.collect()
                    torch.cuda.empty_cache()
                t = time.perf_counter()
                reader = gpu.CudaReader(row['gui_language'], cfg, profile_dir=attempt if smoke else None)
                torch.cuda.synchronize()
                loads[row['gui_language']] = time.perf_counter() - t
                language = row['gui_language']
            result = frozen.ocr.transcribe(lambda _: [], 'mock') if mock else reader.inventory(REPO / row['image_path'])
            result.update(image_sha256=sha, gui_language=row['gui_language'], image_path=row['image_path'],
                          engine=cfg['engine'], execution_mode='mock' if mock else 'cuda:0',
                          cache_key=key, cache_hit=False, weights_sha256=digest(c['ocr_weights']))
            if smoke:
                if not mock and result['status'] != 'success':
                    raise RuntimeError('GPU OCR smoke failed: ' + repr(result['errors']))
            else:
                write(path, result)
        results.append(result)
        print(f"OCR {i}/{len(queue)} {row['gui_language']} {result['status']} strings={len(result['visible_strings'])} {result['runtime_ms']/1000:.3f}s cached={result['cache_hit']}", flush=True)
    if smoke and not mock and cfg['engine'] == 'rapidocr':
        profiles.extend(reader.finish_profiles())
        # Provider registration alone does not prove CUDA kernels actually ran.
        counts = []
        for profile in profiles:
            events = load(profile)['traceEvents']
            count = sum(e.get('cat', '').lower() == 'kernel' for e in events)
            if not count:
                raise RuntimeError('PP-OCRv5 executed no profiled CUDA kernels')
            counts.append({'profile': profile, 'cuda_kernel_events': count})
        write(attempt / 'cuda_kernel_verification.json', counts)
    jsonl(attempt / 'inventories.jsonl', results)
    write(attempt / 'cost.json', {'execution_mode': c['execution_mode'], 'wall_seconds': time.perf_counter() - started,
          'reader_load_seconds': loads, 'images': len(results), 'statuses': dict(Counter(r['status'] for r in results)),
          'logical_runtime_seconds': sum(r['runtime_ms'] for r in results) / 1000,
          'new_runtime_seconds': sum(r['runtime_ms'] for r in results if not r['cache_hit']) / 1000,
          'smoke_only_not_performance_benchmark': smoke})
    (attempt / 'COMPLETE').write_text('complete\n')


def infer_stage(work, attempt, mock, solver):
    c = verify(work)
    spec = c['solvers'][solver]
    attempt.mkdir(parents=True)
    view = attempt / 'view'
    view.mkdir()
    fingerprint = evaluator.VisualRewriteBackend(spec['config'], REPO, work / 'solver_cache', mock)
    env = {'software': fingerprint.software, 'hardware': fingerprint.hardware}
    write(attempt / 'environment.json', env)
    reuse = [] if mock else list(spec['reuse_sources'])
    if not mock:
        # Resume incomplete attempts and reuse the other OCR's exact same batches.
        for backend in BACKENDS:
            for previous in sorted((work.parent / backend / ('infer_' + solver)).glob('attempt_*')):
                pp, ep = previous / 'evaluation/predictions.jsonl', previous / 'environment.json'
                if previous == attempt or not pp.exists() or not ep.exists() or load(ep) != env:
                    continue
                complete = completed_batches(pp)
                if complete:
                    path = view / f'reuse_{len(reuse):04d}.jsonl'
                    jsonl(path, complete)
                    reuse.append({'path': str(path), 'downstream': spec['downstream'], 'seed': c['seed'], 'environment': env})
    write(view / 'contract.json', {'execution_mode': c['execution_mode'], 'config': spec['config'],
          'downstream': spec['downstream'], 'seed': c['seed'], 'labels_sha256': c['labels_sha256'], 'reuse_sources': reuse})
    jsonl(view / 'inputs.jsonl', read(work / 'inputs.jsonl'))
    evaluator.CONDITION = c['condition'] + '_' + solver
    evaluator.infer(view, latest(work, 'rewrite'), attempt / 'evaluation', mock)
    (attempt / 'COMPLETE').write_text('complete\n')


def report(output):
    subprocess.run([str(VLM_PY), str(ROOT / 'scripts/report_gpu_ocr_screen.py'), '--output-dir', str(output)], cwd=REPO, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', action='store_true')
    p.add_argument('--mock', action='store_true')
    p.add_argument('--smoke', action='store_true', help='Only four screenshots per OCR; no LM or final inference')
    p.add_argument('--output-dir', type=Path)
    p.add_argument('--worker', choices=(*STAGES, 'smoke'))
    p.add_argument('--backend', choices=BACKENDS)
    p.add_argument('--attempt', type=Path)
    a = p.parse_args()
    default = DEFAULT_OUTPUT.with_name(DEFAULT_OUTPUT.name + '_mock') if a.mock else DEFAULT_OUTPUT
    output = (a.output_dir or default).resolve()
    if not output.is_relative_to(REPO):
        raise ValueError('Output must be inside repository')
    if a.worker:
        if not a.backend or not a.attempt or not a.attempt.resolve().is_relative_to(output / a.backend):
            raise ValueError('Backend and local attempt required')
        work = output / a.backend
        c = verify(work)
        if c['execution_mode'] != ('mock' if a.mock else 'gpu'):
            raise ValueError('Execution mode mismatch')
        if a.worker in ('ocr', 'smoke'):
            ocr_stage(work, a.attempt, a.mock, a.worker == 'smoke')
        elif a.worker == 'rewrite':
            frozen.CONDITION = c['condition']
            frozen.rewrite_stage(work, a.attempt, a.mock)
        else:
            infer_stage(work, a.attempt, a.mock, a.worker.removeprefix('infer_'))
        return
    prepare(output, a.mock)
    print('PREPARED EasyOCR CUDA + PP-OCRv5 Paddle CUDA; Screen main240/executed288; solvers8B+4B', flush=True)
    if not a.run and not a.smoke:
        return
    with (output / 'run.lock').open('a') as local:
        fcntl.flock(local, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for backend in BACKENDS:
            work = output / backend
            for stage in (('smoke',) if a.smoke else STAGES):
                try:
                    done = latest(work, stage)
                    print(f'SKIP {backend} {stage}: {done.name}', flush=True)
                    continue
                except ValueError:
                    pass
                folder = work / stage
                folder.mkdir(exist_ok=True)
                attempt = folder / f'attempt_{len(list(folder.glob("attempt_*"))) + 1:04d}'
                lock = None
                try:
                    if not a.mock:
                        lock = (ROOT / 'artifacts/search_pipeline_gpu.lock').open('a')
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    python = PP_PY if backend == 'ppocrv5_cuda' and stage in ('ocr', 'smoke') else VLM_PY
                    cmd = [str(python), '-u', str(Path(__file__)), '--output-dir', str(output),
                           '--backend', backend, '--worker', stage, '--attempt', str(attempt)]
                    if a.mock:
                        cmd.append('--mock')
                    print(f'RUN {backend} {stage}', flush=True)
                    env = os.environ.copy()
                    if python == PP_PY:
                        env['OMP_NUM_THREADS'] = '1'
                    subprocess.run(cmd, cwd=REPO, check=True, env=env)
                finally:
                    if lock is not None:
                        lock.close()
                if stage.startswith('infer_'):
                    report(output)
            if not a.smoke:
                write(work / 'COMPLETE.json', {'execution_mode': 'mock' if a.mock else 'gpu',
                      'contract_sha256': digest(verify(work))})
        if not a.smoke:
            report(output)
            write(output / 'COMPLETE.json', {'execution_mode': 'mock' if a.mock else 'gpu',
                  'contracts': {b: digest(verify(output / b)) for b in BACKENDS}})
        else:
            print('SMOKE COMPLETE: OCR only; no Screen accuracy measured.', flush=True)


if __name__ == '__main__':
    main()
