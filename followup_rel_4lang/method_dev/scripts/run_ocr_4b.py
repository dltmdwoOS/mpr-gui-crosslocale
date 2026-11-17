"""Evaluate frozen OCR-localized MCQs with Qwen3-VL-4B; no new preprocessing."""
import argparse
import copy
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / '01_code/src'), str(REPO), str(Path(__file__).parent)]
import run_ocr_inventory as screen_runner
import run_ocr_remaining as remaining
import run_source_copy_rewrite as evaluator
from run_stem_only_gui import read, write, jsonl, unique
from run_stem_refinement_2x2 import latest
from run_overnight_two import completed_batches
from mpr_crosslocale.methods.selective_alignment.schemas import digest, fields

COHORTS = ('screen', 'selection', 'internal_evaluation')
CONDITION = 'E1_M0_EASYOCR_4B'
DEFAULT_OUTPUT = ROOT / 'artifacts/ocr_qwen3_vl_4b_v1'
BASE4 = ROOT / 'artifacts/transfer_qwen3_vl_4b_e1m0_all_v1'


def load(path):
    return json.loads(Path(path).read_text())


def four_b_profile(screen, baseline4):
    if screen['labels_sha256'] != baseline4['labels_sha256']:
        raise ValueError('Historical 4B label lock differs')
    before, after = screen['downstream'], baseline4['downstream']
    allowed = copy.deepcopy(before)
    for name in ('model_id', 'revision'):
        allowed['model_config'][name] = after['model_config'][name]
    if allowed != after or baseline4['seed'] != screen['seed']:
        raise ValueError('4B transfer may change only solver checkpoint ID/revision')
    if baseline4['config']['models']['text'] != screen['config']['models']['text']:
        raise ValueError('Fixed Qwen3-8B LM differs')
    config = copy.deepcopy(screen['inference_config'])
    config['models']['editor_vlm'] = copy.deepcopy(baseline4['config']['models']['editor_vlm'])
    config['downstream'] = copy.deepcopy(after)
    return config, copy.deepcopy(after)


def prepare(output, mock=False):
    screen = remaining.check_complete(remaining.SCREEN)
    screen_runner.verify(remaining.SCREEN)
    base8 = remaining.DEFAULT_OUTPUT.with_name(remaining.DEFAULT_OUTPUT.name + '_mock') if mock else remaining.DEFAULT_OUTPUT
    c8 = remaining.verify(base8)
    if c8['execution_mode'] != ('mock' if mock else 'gpu'):
        raise ValueError('8B source execution mode mismatch')
    baseline4 = remaining.check_complete(BASE4)
    config, downstream = four_b_profile(screen, baseline4)
    model = Path(config['models']['editor_vlm']['path'])
    index = model / 'model.safetensors.index.json'
    if not index.exists() or any(not (model / x).exists() for x in set(load(index)['weight_map'].values())):
        raise ValueError('Pinned 4B checkpoint missing; no automatic download')
    sources = [Path(__file__), ROOT / 'scripts/report_ocr_4b.py',
               remaining.SCREEN / 'contract.json', remaining.SCREEN / 'COMPLETE.json',
               BASE4 / 'contract.json', BASE4 / 'COMPLETE.json',
               ROOT / 'scripts/run_source_copy_rewrite.py', ROOT / 'scripts/run_ocr_inventory.py',
               ROOT / 'visual_rewrite_backend.py', ROOT / 'exact_batch_reuse.py',
               ROOT / 'scripts/run_overnight_two.py', ROOT / 'scripts/run_two_stage_v2.py']
    sources += [REPO / n for n in screen['source_sha256']]
    desc, inputs = {}, {}
    for cohort in COHORTS:
        source8 = remaining.SCREEN if cohort == 'screen' else base8 / cohort
        rows = read(source8 / 'inputs.jsonl')
        oldrows = read(BASE4 / cohort / 'inputs.jsonl')
        if unique(rows) != unique(oldrows):
            raise ValueError('Prior 4B O and new method have different original inputs')
        inputs[cohort] = rows
        reuse = []
        for condition in ('O', 'E1_M0'):
            attempt = latest(BASE4 / cohort, 'infer_' + condition)
            pc = load(attempt / 'evaluation/contract.json')
            if pc['downstream'] != downstream:
                raise ValueError('Historical 4B downstream config differs')
            pp, env = attempt / 'evaluation/predictions.jsonl', attempt / 'environment.json'
            if set(unique(read(pp))) != set(unique(rows)):
                raise ValueError('Historical 4B pair coverage mismatch')
            reuse.append({'path': str(pp), 'downstream': downstream, 'seed': screen['seed'], 'environment': load(env)})
            sources += [pp, env, attempt / 'evaluation/contract.json', attempt / 'COMPLETE']
        desc[cohort] = {'source8': str(source8), 'O_predictions': reuse[0]['path'],
                        'VLM_E1_M0_predictions': reuse[1]['path'], 'reuse_sources': reuse,
                        'source8_contract_sha256': digest(load(source8 / 'contract.json')),
                        'executed_pairs': len(rows), 'primary_pairs': {'screen': 240, 'selection': 239, 'internal_evaluation': 1416}[cohort]}
        sources += [source8 / 'inputs.jsonl', BASE4 / cohort / 'inputs.jsonl']
    c = {'version': 'frozen-ocr-qwen3-vl-4b-v1', 'execution_mode': 'mock' if mock else 'gpu',
         'condition': CONDITION, 'config': config, 'downstream': downstream, 'seed': screen['seed'],
         'labels_sha256': screen['labels_sha256'], 'base8': str(base8), 'base4': str(BASE4),
         'base8_contract_sha256': digest(c8),
         'cohorts': list(COHORTS), 'descriptors': desc, 'originals_sha256': {k: digest(v) for k, v in inputs.items()},
         'source_sha256': {str(p.resolve().relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in set(sources)},
         'policy': 'Same OCR+fixed-LM localized MCQs as 8B; only final solver is 4B. '
                   'No new OCR/extraction/matching and no cross-model prediction reuse. '
                   'O is historical same-profile 4B. Reuse only exact complete ordered 4B batches.'}
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'contract.json').exists() and load(output / 'contract.json') != c:
        raise ValueError('Frozen 4B plan changed; choose fresh output directory')
    write(output / 'contract.json', c)
    for cohort in COHORTS:
        work = output / cohort
        work.mkdir(exist_ok=True)
        jsonl(work / 'inputs.jsonl', inputs[cohort])
    return c


def verify(output):
    c = load(output / 'contract.json')
    for name, sha in c['source_sha256'].items():
        if hashlib.sha256((REPO / name).read_bytes()).hexdigest() != sha:
            raise ValueError('Frozen source changed: ' + name)
    if digest(remaining.verify(Path(c['base8']))) != c['base8_contract_sha256']:
        raise ValueError('8B contract content changed')
    for cohort in COHORTS:
        # The 8B preparer rewrites JSON key order on resume. Freeze content rather
        # than byte layout for those manifests; their data/code hashes stay fixed.
        desc = c['descriptors'][cohort]
        if digest(load(Path(desc['source8']) / 'contract.json')) != desc['source8_contract_sha256']:
            raise ValueError('8B cohort contract content changed')
        if digest(read(output / cohort / 'inputs.jsonl')) != c['originals_sha256'][cohort]:
            raise ValueError('Original input checksum mismatch')
    return c


def bind_preprocessing(c, cohort):
    """Bind immutable completed 8B output; no prediction or gold enters a model query."""
    source = Path(c['descriptors'][cohort]['source8'])
    sc, done = load(source / 'contract.json'), load(source / 'COMPLETE.json')
    if done['contract_sha256'] != digest(sc):
        raise ValueError('8B preprocessing source incomplete/changed')
    rewrite = latest(source, 'rewrite')
    rows = read(rewrite / 'rewritten.jsonl')
    original = unique(read(source / 'inputs.jsonl'))
    if set(unique(rows)) != set(original):
        raise ValueError('8B localized input coverage mismatch')
    from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits
    for row in rows:
        if row['options'] != original[row['pair_id']]['options'] or apply_edits(original[row['pair_id']], row['edits']) != fields(row):
            raise ValueError('Shared localized MCQ violates selective scope')
    return rewrite, {'source_run': str(source), 'source_contract_sha256': digest(sc),
                     'rewritten_path': str(rewrite / 'rewritten.jsonl'),
                     'rewritten_sha256': hashlib.sha256((rewrite / 'rewritten.jsonl').read_bytes()).hexdigest(),
                     'source_execution_mode': sc['execution_mode']}


def infer(output, cohort, attempt, mock):
    c = verify(output)
    rewrite, binding = bind_preprocessing(c, cohort)
    attempt.mkdir(parents=True)
    write(attempt / 'preprocessing_binding.json', binding)
    fingerprint = evaluator.VisualRewriteBackend(c['config'], REPO, output / 'cache', mock)
    env = {'software': fingerprint.software, 'hardware': fingerprint.hardware}
    write(attempt / 'environment.json', env)
    view = attempt / 'view'
    view.mkdir()
    reuse = [] if mock else list(c['descriptors'][cohort]['reuse_sources'])
    if not mock:
        for previous in sorted((output / cohort / 'infer').glob('attempt_*')):
            path, ep = previous / 'evaluation/predictions.jsonl', previous / 'environment.json'
            if previous == attempt or not path.exists() or not ep.exists() or load(ep) != env:
                continue
            complete = completed_batches(path)
            if complete:
                path = view / f'reuse_{len(reuse):04d}.jsonl'
                jsonl(path, complete)
                reuse.append({'path': str(path), 'downstream': c['downstream'], 'seed': c['seed'], 'environment': env})
    write(view / 'contract.json', {**c, 'reuse_sources': reuse})
    jsonl(view / 'inputs.jsonl', read(output / cohort / 'inputs.jsonl'))
    evaluator.CONDITION = CONDITION
    evaluator.infer(view, rewrite, attempt / 'evaluation', mock)
    (attempt / 'COMPLETE').write_text('complete\n')


def report(output):
    subprocess.run([sys.executable, str(ROOT / 'scripts/report_ocr_4b.py'), '--output-dir', str(output)], cwd=REPO, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', action='store_true')
    p.add_argument('--mock', action='store_true')
    p.add_argument('--output-dir', type=Path)
    p.add_argument('--worker', action='store_true')
    p.add_argument('--cohort', choices=COHORTS)
    p.add_argument('--attempt', type=Path)
    a = p.parse_args()
    output = (a.output_dir or (DEFAULT_OUTPUT.with_name(DEFAULT_OUTPUT.name + '_mock') if a.mock else DEFAULT_OUTPUT)).resolve()
    if not output.is_relative_to(REPO):
        raise ValueError('Output outside repository')
    if a.worker:
        if not a.cohort or not a.attempt or not a.attempt.resolve().is_relative_to(output / a.cohort):
            raise ValueError('Worker cohort/attempt required')
        if verify(output)['execution_mode'] != ('mock' if a.mock else 'gpu'):
            raise ValueError('Execution mode mismatch')
        infer(output, a.cohort, a.attempt, a.mock)
        return
    c = prepare(output, a.mock)
    print('PREPARED 4B Screen288 + Selection240 + Internal1416; primary1895; preprocessing reused', flush=True)
    if not a.run:
        return
    if not (Path(c['base8']) / 'COMPLETE.json').exists():
        raise RuntimeError('Finish the remaining 8B run first, or use run_ocr_8b_then_4b.sh')
    with (output / 'run.lock').open('a') as local:
        fcntl.flock(local, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not (output / 'COMPLETE.json').exists():
            started = time.perf_counter()
            for cohort in COHORTS:
                work = output / cohort
                try:
                    latest(work, 'infer')
                    print('SKIP completed 4B ' + cohort, flush=True)
                except ValueError:
                    lock = None
                    try:
                        if not a.mock:
                            lock = (ROOT / 'artifacts/search_pipeline_gpu.lock').open('a')
                            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        folder = work / 'infer'
                        folder.mkdir(exist_ok=True)
                        attempt = folder / f'attempt_{len(list(folder.glob("attempt_*"))) + 1:04d}'
                        cmd = [sys.executable, '-u', str(Path(__file__)), '--output-dir', str(output),
                               '--worker', '--cohort', cohort, '--attempt', str(attempt)]
                        if a.mock:
                            cmd.append('--mock')
                        print('RUN 4B ' + cohort + ' inference', flush=True)
                        subprocess.run(cmd, cwd=REPO, check=True)
                    finally:
                        if lock is not None:
                            lock.close()
                report(output)
            write(output / 'COMPLETE.json', {'execution_mode': c['execution_mode'], 'contract_sha256': digest(c),
                  'last_invocation_wall_seconds': time.perf_counter() - started})
        report(output)


if __name__ == '__main__':
    main()
