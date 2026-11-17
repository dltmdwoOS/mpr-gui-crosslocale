"""Extend the frozen OCR Screen method to Selection/Internal; prepare by default."""
import argparse
import fcntl
import hashlib
from importlib import metadata
import json
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / '01_code/src'), str(REPO), str(Path(__file__).parent)]
import run_ocr_inventory as frozen
from run_stem_only_gui import read, write, jsonl, unique
from run_stem_refinement_2x2 import latest
from search_pipeline import EXCLUDED
from mpr_crosslocale.methods.selective_alignment.schemas import digest, validate_input
from followup_rel_4lang.method_dev.two_stage_v2 import prompts
from followup_rel_4lang.method_dev.ocr_inventory import weight_manifest

COHORTS = ('selection', 'internal_evaluation')
DEFAULT_OUTPUT = ROOT / 'artifacts/ocr_inventory_full_dev_v1'
SCREEN = ROOT / 'artifacts/ocr_inventory_screen_v1'
E1 = ROOT / 'artifacts/e1_stem_full_dev_v1'


def load(path):
    return json.loads(Path(path).read_text())


def check_complete(folder):
    c, done = load(folder / 'contract.json'), load(folder / 'COMPLETE.json')
    if c['execution_mode'] != 'gpu' or done['contract_sha256'] != digest(c):
        raise ValueError('Completed frozen GPU source required: ' + str(folder))
    return c


def validate_remaining_rows(rows, cohort):
    unique(rows)
    for row in rows:
        validate_input(row)
    expected = {'selection': (240, 239, 20, 80), 'internal_evaluation': (1416, 1416, 118, 472)}[cohort]
    measured = (len(rows), sum(r['pair_id'] != EXCLUDED for r in rows),
                len({r['parallel_id'] for r in rows}), len({r['image_sha256'] for r in rows}))
    if measured != expected:
        raise ValueError(f'Unexpected {cohort} counts: {measured} != {expected}')
    languages = {}
    for row in rows:
        if languages.setdefault(row['image_sha256'], row['gui_language']) != row['gui_language']:
            raise ValueError('One image assigned incompatible languages')
    return dict(zip(('executed_pairs', 'primary_pairs', 'items', 'images'), measured))


def cache_links(source, target):
    """Link immutable existing entries; new writes stay in the new experiment."""
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in sorted(source.glob('*.json')):
        if len(path.stem) != 64 or any(c not in '0123456789abcdef' for c in path.stem):
            continue
        if not path.resolve().is_relative_to(REPO):
            raise ValueError('Cache source outside repository')
        record = load(path)
        if record['cache_key'] != path.stem:
            raise ValueError('Cache key/file mismatch')
        dest = target / path.name
        if not dest.exists():
            dest.symlink_to(path.resolve())
        elif load(dest)['raw_output' if 'raw_output' in record else 'visible_strings'] != record['raw_output' if 'raw_output' in record else 'visible_strings']:
            raise ValueError('Conflicting existing cache entry')
        count += 1
    return count


def prepare(output, mock=False):
    screen = check_complete(SCREEN)
    frozen.verify(SCREEN)
    e1 = check_complete(E1)
    if any(screen[k] != e1[k] for k in ('config', 'inference_config', 'downstream', 'seed', 'labels_sha256')):
        raise ValueError('Screen/remaining E1 method contracts differ')
    weights = load(SCREEN / 'ocr_weights.json')
    if not mock and weight_manifest(frozen.MODEL_DIR) != weights:
        raise ValueError('Cached OCR weights differ from completed Screen')
    if not mock and metadata.version('easyocr') != screen['ocr_config']['package_version']:
        raise ValueError('Pinned EasyOCR package required')
    sources = [Path(__file__), ROOT / 'scripts/report_ocr_remaining.py',
               SCREEN / 'contract.json', SCREEN / 'COMPLETE.json', SCREEN / 'results.json',
               SCREEN / 'ocr_weights.json', SCREEN / 'inputs.jsonl',
               E1 / 'contract.json', E1 / 'COMPLETE.json', E1 / 'results.json',
               ROOT / 'artifacts/e1_stem_full_dev_results_snapshot.json']
    sources += [REPO / name for name in screen['source_sha256']]
    if not mock:
        sources += list((SCREEN / 'ocr_cache').glob('*.json'))
        sources += list((SCREEN / 'matching_cache').glob('*.json'))
    desc, data, counts = {}, {}, {}
    for cohort in COHORTS:
        origin = E1 / cohort
        inputs = origin / 'inputs.jsonl'
        rows = read(inputs)
        counts[cohort] = validate_remaining_rows(rows, cohort)
        data[cohort] = rows
        ex = latest(origin / 'extraction', 'E1')
        extracted = {r['source_key']: r for r in read(ex / 'extractions.jsonl')}
        for row in rows:
            if digest(prompts.extraction_payload(row, stem_only=True)) not in extracted:
                raise ValueError('Missing existing E1 extraction')
        inventory = Path(e1['descriptors'][cohort]['inventory_path'])
        rewrite = latest(origin / 'E1_M0', 'rewrite')
        infer = latest(origin / 'E1_M0', 'infer')
        if set(unique(read(infer / 'evaluation/predictions.jsonl'))) != set(unique(rows)):
            raise ValueError('Missing existing paired E1 predictions')
        sources += [inputs, ex / 'extractions.jsonl', ex / 'COMPLETE', inventory,
                    rewrite / 'rewritten.jsonl', rewrite / 'COMPLETE',
                    infer / 'evaluation/predictions.jsonl', infer / 'evaluation/contract.json',
                    infer / 'environment.json', infer / 'COMPLETE']
        reuse = [{'path': str(infer / 'evaluation/predictions.jsonl'), 'downstream': screen['downstream'],
                  'seed': screen['seed'], 'environment': load(infer / 'environment.json')}]
        reuse += e1['descriptors'][cohort]['legacy_reuse_sources']
        sources += [Path(s['path']) for s in reuse]
        desc[cohort] = {'inputs_source': str(inputs), 'extraction_path': str(ex / 'extractions.jsonl'),
                        'baseline_inventory': str(inventory), 'baseline_rewrite': str(rewrite / 'rewritten.jsonl'),
                        'baseline_predictions': str(infer / 'evaluation/predictions.jsonl'),
                        'reuse_sources': reuse, 'O_predictions': e1['descriptors'][cohort]['O_pred']}
        sources.append(Path(desc[cohort]['O_predictions']))
    item_groups = [{r['parallel_id'] for r in read(SCREEN / 'inputs.jsonl')}]
    item_groups += [{r['parallel_id'] for r in data[c]} for c in COHORTS]
    if any(a & b for i, a in enumerate(item_groups) for b in item_groups[i + 1:]):
        raise ValueError('Semantic items overlap between cohorts')
    for row in {r['image_sha256']: r for group in data.values() for r in group}.values():
        if hashlib.sha256((REPO / row['image_path']).read_bytes()).hexdigest() != row['image_sha256']:
            raise ValueError('Screenshot checksum mismatch')
    contract = {'version': 'easyocr-frozen-remaining-dev-v1', 'execution_mode': 'mock' if mock else 'gpu',
                'screen_contract_sha256': digest(screen), 'screen_run': str(SCREEN), 'cohorts': list(COHORTS),
                'ocr_config': screen['ocr_config'], 'config': screen['config'], 'downstream': screen['downstream'],
                'inference_config': screen['inference_config'], 'seed': screen['seed'],
                'labels_sha256': screen['labels_sha256'], 'weights': {} if mock else weights,
                'descriptors': desc, 'counts': counts,
                'source_sha256': {str(p.resolve().relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in set(sources)},
                'policy': 'Freeze completed Screen OCR/E1/M0. Selection then Internal. '
                          'No Screen rerun, no new E1 extraction, no VLM inventory fallback or prompt tuning. '
                          'Whole ordered batch reuse only; retain failures and the pre-excluded Selection row in execution.'}
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'contract.json'
    if target.exists() and load(target) != contract:
        raise ValueError('Plan changed: choose a fresh output directory')
    write(target, contract)
    for cache in ('ocr_cache', 'matching_cache'):
        if mock:
            (output / cache).mkdir(exist_ok=True)
        else:
            cache_links(SCREEN / cache, output / cache)
    for cohort in COHORTS:
        work = output / cohort
        work.mkdir(exist_ok=True)
        cc = {**contract, **desc[cohort], 'condition': frozen.CONDITION,
              'inputs_sha256': digest(data[cohort]), 'model_dir': str(frozen.MODEL_DIR),
              'pairs_executed': counts[cohort]['executed_pairs'], 'primary_pairs': counts[cohort]['primary_pairs'],
              'primary_items': counts[cohort]['items'], 'parent_sha256': digest(contract)}
        write(work / 'contract.json', cc)
        jsonl(work / 'inputs.jsonl', data[cohort])
        write(work / 'ocr_weights.json', {} if mock else weights)
        for cache in ('ocr_cache', 'matching_cache'):
            link = work / cache
            if not link.exists():
                link.symlink_to(output / cache, target_is_directory=True)
            if link.resolve() != output / cache:
                raise ValueError('Unexpected cache target')
    return contract


def verify(output):
    c = load(output / 'contract.json')
    for name, sha in c['source_sha256'].items():
        if hashlib.sha256((REPO / name).read_bytes()).hexdigest() != sha:
            raise ValueError('Frozen source changed: ' + name)
    for cohort in c['cohorts']:
        cc = frozen.verify(output / cohort)
        if cc['parent_sha256'] != digest(c):
            raise ValueError('Parent run contract differs')
    return c


def report(output):
    subprocess.run([sys.executable, str(ROOT / 'scripts/report_ocr_remaining.py'), '--output-dir', str(output)],
                   cwd=REPO, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', action='store_true')
    p.add_argument('--mock', action='store_true')
    p.add_argument('--output-dir', type=Path)
    p.add_argument('--worker', choices=['ocr', 'rewrite', 'infer'])
    p.add_argument('--cohort', choices=COHORTS)
    p.add_argument('--attempt', type=Path)
    a = p.parse_args()
    output = (a.output_dir or (DEFAULT_OUTPUT.with_name(DEFAULT_OUTPUT.name + '_mock') if a.mock else DEFAULT_OUTPUT)).resolve()
    if not output.is_relative_to(REPO):
        raise ValueError('Output must be inside repository')
    if a.worker:
        c = verify(output)
        if c['execution_mode'] != ('mock' if a.mock else 'gpu'):
            raise ValueError('Worker execution mode differs')
        if not a.cohort or not a.attempt or not a.attempt.resolve().is_relative_to(output / a.cohort):
            raise ValueError('Worker cohort/attempt required')
        {'ocr': frozen.ocr_stage, 'rewrite': frozen.rewrite_stage, 'infer': frozen.infer_stage}[a.worker](output / a.cohort, a.attempt, a.mock)
        return
    c = prepare(output, a.mock)
    print('PREPARED Selection240/239, Internal1416/1416, Screen reuse; OCR CPU3, LM1, solver batch3', flush=True)
    if not a.run:
        return
    with (output / 'run.lock').open('a') as local:
        fcntl.flock(local, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not (output / 'COMPLETE.json').exists():
            started = time.perf_counter()
            for cohort in COHORTS:
                work = output / cohort
                for stage in ('ocr', 'rewrite', 'infer'):
                    try:
                        latest(work, stage)
                        print('SKIP completed ' + cohort + ' ' + stage, flush=True)
                        continue
                    except ValueError:
                        pass
                    lock = None
                    try:
                        if not a.mock and stage != 'ocr':
                            lock = (ROOT / 'artifacts/search_pipeline_gpu.lock').open('a')
                            try:
                                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            except BlockingIOError:
                                raise RuntimeError('Another GPU pipeline is active; completed stages are saved. Rerun after it finishes.') from None
                        folder = work / stage
                        folder.mkdir(exist_ok=True)
                        attempt = folder / f'attempt_{len(list(folder.glob("attempt_*"))) + 1:04d}'
                        cmd = [sys.executable, '-u', str(Path(__file__)), '--output-dir', str(output),
                               '--worker', stage, '--cohort', cohort, '--attempt', str(attempt)]
                        if a.mock:
                            cmd.append('--mock')
                        print('RUN ' + cohort + ' ' + stage, flush=True)
                        subprocess.run(cmd, cwd=REPO, check=True)
                    finally:
                        if lock is not None:
                            lock.close()
                write(work / 'COMPLETE.json', {'execution_mode': c['execution_mode'],
                      'contract_sha256': digest(load(work / 'contract.json'))})
                report(output)  # Publish completed cohort only; never score partial output.
            write(output / 'COMPLETE.json', {'execution_mode': c['execution_mode'], 'contract_sha256': digest(c),
                  'last_invocation_wall_seconds': time.perf_counter() - started})
        report(output)


if __name__ == '__main__':
    main()
