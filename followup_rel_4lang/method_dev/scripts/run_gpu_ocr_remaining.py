"""Freeze completed GPU OCR Screen settings and prepare/run Selection + Internal, 8B + 4B."""
import argparse
import copy
import fcntl
import hashlib
import os
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / '01_code/src'), str(REPO), str(Path(__file__).parent)]
import run_gpu_ocr_screen as screen
import run_ocr_remaining as cpu
import run_ocr_4b as cpu4
from run_stem_only_gui import read, write, jsonl, unique
from run_stem_refinement_2x2 import latest
from mpr_crosslocale.methods.selective_alignment.schemas import digest
from followup_rel_4lang.method_dev.two_stage_v2 import prompts

COHORTS = ('selection', 'internal_evaluation')
ALL_COHORTS = ('screen', *COHORTS)
DEFAULT_OUTPUT = ROOT / 'artifacts/gpu_ocr_full_dev_v1'
SCREEN = screen.DEFAULT_OUTPUT
BACKENDS, SOLVERS, STAGES = screen.BACKENDS, screen.SOLVERS, screen.STAGES
load = screen.load


def cache_plan(folders):
    """Use exact cache keys; conflicting responses are excluded from seeding."""
    selected, conflicts = {}, set()
    for folder in folders:
        for path in sorted(folder.glob('*.json')):
            if len(path.stem) != 64 or any(x not in '0123456789abcdef' for x in path.stem):
                continue
            if not path.resolve().is_relative_to(REPO):
                raise ValueError('Seed cache outside repository')
            record = load(path)
            if record['cache_key'] != path.stem:
                raise ValueError('Seed filename/key mismatch')
            if path.name in selected:
                prior = load(selected[path.name])
                key = 'raw_output' if 'raw_output' in record else 'visible_strings'
                if prior.get(key) != record[key]:
                    conflicts.add(path.name)
            else:
                selected[path.name] = path.resolve()
    return {k: p for k, p in selected.items() if k not in conflicts}, sorted(conflicts)


def link_cache(selected, destination):
    destination.mkdir(parents=True, exist_ok=True)
    for name, source in selected.items():
        target = destination / name
        if not target.exists():
            target.symlink_to(source)
        elif load(target) != load(source):
            raise ValueError('Existing seeded cache differs: ' + name)


def link_directory(target, source):
    if not target.exists():
        target.symlink_to(source, target_is_directory=True)
    if target.resolve() != source.resolve():
        raise ValueError('Unexpected shared cache directory: ' + str(target))


def validate_partitions(groups):
    item_sets = [{r['parallel_id'] for r in groups[name]} for name in ALL_COHORTS]
    if any(left & right for i, left in enumerate(item_sets) for right in item_sets[i + 1:]):
        raise ValueError('Semantic items overlap between cohorts')


def prepare(output, mock=False):
    sc = {b: screen.verify(SCREEN / b) for b in BACKENDS}
    sd = load(SCREEN / 'COMPLETE.json')
    if sd['execution_mode'] != 'gpu' or sd['contracts'] != {b: digest(c) for b, c in sc.items()}:
        raise ValueError('Completed real GPU OCR Screen required')
    for b in BACKENDS:
        screen.completed_source(SCREEN / b)
        if not mock and screen.package_versions(screen.VLM_PY if b == 'easyocr_cuda' else screen.PP_PY,
                                               list(sc[b]['ocr_software'])) != sc[b]['ocr_software']:
            raise ValueError('OCR packages differ from completed Screen')
    c8, c4 = cpu.verify(cpu.DEFAULT_OUTPUT), cpu4.verify(cpu4.DEFAULT_OUTPUT)
    screen.completed_source(cpu.DEFAULT_OUTPUT)
    screen.completed_source(cpu4.DEFAULT_OUTPUT)
    if any(c8[k] != sc[BACKENDS[0]][k] for k in ('config', 'inference_config', 'downstream', 'seed', 'labels_sha256')):
        raise ValueError('Remaining E1/M0 method differs from Screen')
    groups = {'screen': read(SCREEN / BACKENDS[0] / 'inputs.jsonl')}
    descriptors, counts = {}, {}
    captures = {REPO / name for c in sc.values() for name in c['source_sha256']}
    captures.update([Path(__file__), ROOT / 'scripts/report_gpu_ocr_remaining.py', ROOT / 'scripts/run_gpu_ocr_remaining.sh',
                     ROOT / 'scripts/report_ocr_remaining.py', ROOT / 'scripts/run_ocr_remaining.py',
                     ROOT / 'scripts/run_ocr_4b.py', ROOT / 'scripts/report_ocr_4b.py',
                     cpu.DEFAULT_OUTPUT / 'contract.json', cpu.DEFAULT_OUTPUT / 'COMPLETE.json',
                     cpu4.DEFAULT_OUTPUT / 'contract.json', cpu4.DEFAULT_OUTPUT / 'COMPLETE.json', SCREEN / 'COMPLETE.json'])
    for b in BACKENDS:
        work = SCREEN / b
        captures.update([work / 'contract.json', work / 'COMPLETE.json', work / 'inputs.jsonl'])
        for stage in STAGES:
            captures.update(p for p in latest(work, stage).rglob('*') if p.is_file())
    for cohort in COHORTS:
        origin = cpu.DEFAULT_OUTPUT / cohort
        cc = screen.completed_source(origin)
        rows = read(origin / 'inputs.jsonl')
        counts[cohort] = cpu.validate_remaining_rows(rows, cohort)
        groups[cohort] = rows
        if unique(rows) != unique(read(screen.BASE4 / cohort / 'inputs.jsonl')):
            raise ValueError('Historical 4B originals differ')
        ext = {r['source_key']: r for r in read(Path(cc['extraction_path']))}
        if any(digest(prompts.extraction_payload(row, stem_only=True)) not in ext for row in rows):
            raise ValueError('Existing E1 extraction incomplete')
        solvers = copy.deepcopy(sc[BACKENDS[0]]['solvers'])
        for solver, source in [('8B', origin), ('4B', cpu4.DEFAULT_OUTPUT / cohort)]:
            attempt = latest(source, 'infer')
            env, pred = attempt / 'environment.json', attempt / 'evaluation/predictions.jsonl'
            historical = cc if solver == '8B' else c4['descriptors'][cohort]
            spec = solvers[solver]
            spec['O_predictions'] = historical['O_predictions']
            spec['VLM_predictions'] = historical['baseline_predictions' if solver == '8B' else 'VLM_E1_M0_predictions']
            spec['CPU_predictions'] = str(pred)
            spec['reuse_sources'] = copy.deepcopy(historical['reuse_sources'])
            environment = load(env) if env.exists() else historical['reuse_sources'][0]['environment']
            spec['reuse_sources'].append({'path': str(pred), 'downstream': spec['downstream'],
                                           'seed': cc['seed'], 'environment': environment})
            if load(attempt / 'evaluation/contract.json')['downstream'] != spec['downstream']:
                raise ValueError('Historical solver profile differs')
            for key in ('O_predictions', 'VLM_predictions', 'CPU_predictions'):
                selected = read(Path(spec[key]))
                if key == 'O_predictions':
                    selected = [r for r in selected if r['condition'] == 'O']
                if set(unique(selected)) != set(unique(rows)):
                    raise ValueError('Historical paired prediction coverage differs')
                captures.add(Path(spec[key]))
            captures.update(Path(s['path']) for s in spec['reuse_sources'])
            captures.update([attempt / 'evaluation/contract.json', attempt / 'COMPLETE'])
            if env.exists():
                captures.add(env)
        descriptors[cohort] = {'inputs_source': str(origin / 'inputs.jsonl'), 'extraction_path': cc['extraction_path'],
            'baseline_inventory': cc['baseline_inventory'], 'baseline_rewrite': cc['baseline_rewrite'], 'solvers': solvers}
        captures.update([origin / 'contract.json', origin / 'COMPLETE.json', origin / 'inputs.jsonl',
                         Path(cc['extraction_path']), Path(cc['extraction_path']).parent / 'COMPLETE',
                         Path(cc['baseline_inventory']), Path(cc['baseline_rewrite'])])
        for folder, stage in [(origin, 'ocr'), (origin, 'rewrite'), (screen.BASE4 / cohort, 'inventory'),
                              (screen.BASE4 / cohort, 'rewrite')]:
            attempt = latest(folder, stage)
            captures.update(attempt / name for name in ('cost.json', 'COMPLETE'))
            captures.add(attempt / ('inventories.jsonl' if stage in ('ocr', 'inventory') else 'rewritten.jsonl'))
    validate_partitions(groups)
    for row in {r['image_sha256']: r for rows in groups.values() for r in rows}.values():
        if hashlib.sha256((REPO / row['image_path']).read_bytes()).hexdigest() != row['image_sha256']:
            raise ValueError('Screenshot checksum differs')
    # Same-message LM cache may be shared across OCR providers: the inventory
    # content is in the key, and backend/model/software/hardware/seed stay fixed.
    seed_plans, seed_conflicts = {}, {}
    sources = [cpu.DEFAULT_OUTPUT / 'matching_cache'] + [SCREEN / b / 'matching_cache' for b in BACKENDS]
    seed_plans['matching'], seed_conflicts['matching'] = ({}, []) if mock else cache_plan(sources)
    for b in BACKENDS:
        seed_plans[b], seed_conflicts[b] = ({}, []) if mock else cache_plan([SCREEN / b / 'ocr_cache'])
    captures.update(p for selected in seed_plans.values() for p in selected.values())
    contract = {'version': 'frozen-gpu-ocr-remaining-v1', 'execution_mode': 'mock' if mock else 'gpu',
        'screen_run': str(SCREEN), 'screen_contracts': {b: digest(c) for b, c in sc.items()},
        'cohorts': list(COHORTS), 'backends': list(BACKENDS), 'solvers': list(SOLVERS),
        'labels_sha256': sc[BACKENDS[0]]['labels_sha256'], 'counts': counts, 'descriptors': descriptors,
        'inputs_sha256': {cohort: digest(groups[cohort]) for cohort in COHORTS},
        'cache_seed_counts': {name: len(value) for name, value in seed_plans.items()},
        'cache_seed_conflicts': seed_conflicts,
        'source_sha256': {str(p.resolve().relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(captures)},
        'policy': 'Freeze completed Screen OCR/E1/M0 and solver profiles. Screen reuse, Selection then Internal. '
                  'Both OCR providers, shared fixed-LM preprocessing per provider, 8B then 4B. '
                  'No extraction rerun or tuning, no VLM inventory fallback. Include failures and excluded row in execution. '
                  'Reuse only exact-message LM calls or exact complete ordered same-model solver batches.'}
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'contract.json').exists() and load(output / 'contract.json') != contract:
        raise ValueError('Frozen remaining plan changed; choose new --output-dir')
    write(output / 'contract.json', contract)
    matching = output / 'shared/matching_cache'
    link_cache(seed_plans['matching'], matching)
    for b in BACKENDS:
        ocr_cache = output / 'shared' / b / 'ocr_cache'
        link_cache(seed_plans[b], ocr_cache)
        for cohort in COHORTS:
            work = output / cohort / b
            work.mkdir(parents=True, exist_ok=True)
            desc = descriptors[cohort]
            child = {**sc[b], **{k: desc[k] for k in ('extraction_path', 'baseline_inventory')},
                     'baseline_predictions': desc['solvers']['8B']['VLM_predictions'],
                     'solvers': desc['solvers'], 'execution_mode': contract['execution_mode'],
                     'cohort': cohort, 'parent_sha256': digest(contract), 'inputs_sha256': digest(groups[cohort]),
                     'pairs_executed': counts[cohort]['executed_pairs'], 'primary_pairs': counts[cohort]['primary_pairs'],
                     'primary_items': counts[cohort]['items'], 'ocr_unique_images_executed': counts[cohort]['images'],
                     'source_sha256': contract['source_sha256'], 'policy': contract['policy']}
            if (work / 'contract.json').exists() and load(work / 'contract.json') != child:
                raise ValueError('Child contract differs')
            write(work / 'contract.json', child)
            jsonl(work / 'inputs.jsonl', groups[cohort])
            link_directory(work / 'ocr_cache', ocr_cache)
            link_directory(work / 'matching_cache', matching)
    return contract


def verify(output):
    c = load(output / 'contract.json')
    for name, h in c['source_sha256'].items():
        if hashlib.sha256((REPO / name).read_bytes()).hexdigest() != h:
            raise ValueError('Frozen dependency differs: ' + name)
    for cohort in COHORTS:
        for b in BACKENDS:
            child = screen.frozen.verify(output / cohort / b)
            if child['parent_sha256'] != digest(c) or child['execution_mode'] != c['execution_mode']:
                raise ValueError('Child/parent contract differs')
    return c


def report(output):
    subprocess.run([str(screen.VLM_PY), str(ROOT / 'scripts/report_gpu_ocr_remaining.py'), '--output-dir', str(output)], cwd=REPO, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', action='store_true')
    p.add_argument('--mock', action='store_true')
    p.add_argument('--output-dir', type=Path)
    p.add_argument('--worker', choices=STAGES)
    p.add_argument('--cohort', choices=COHORTS)
    p.add_argument('--backend', choices=BACKENDS)
    p.add_argument('--attempt', type=Path)
    a = p.parse_args()
    default = DEFAULT_OUTPUT.with_name(DEFAULT_OUTPUT.name + '_mock') if a.mock else DEFAULT_OUTPUT
    output = (a.output_dir or default).resolve()
    if not output.is_relative_to(REPO):
        raise ValueError('Output outside repository')
    if a.worker:
        c = verify(output)
        if not a.cohort or not a.backend or not a.attempt or not a.attempt.resolve().is_relative_to(output / a.cohort / a.backend):
            raise ValueError('Local cohort/backend/attempt required')
        if c['execution_mode'] != ('mock' if a.mock else 'gpu'):
            raise ValueError('Worker execution mode differs')
        work = output / a.cohort / a.backend
        if a.worker == 'ocr':
            screen.ocr_stage(work, a.attempt, a.mock)
        elif a.worker == 'rewrite':
            screen.frozen.CONDITION = load(work / 'contract.json')['condition']
            screen.frozen.rewrite_stage(work, a.attempt, a.mock)
        else:
            screen.infer_stage(work, a.attempt, a.mock, a.worker.removeprefix('infer_'))
        return
    c = prepare(output, a.mock)
    print('PREPARED Selection239 + Internal1416 primary pairs per condition; two GPU OCR x 8B/4B; Screen reused', flush=True)
    if not a.run:
        return
    with (output / 'run.lock').open('a') as local:
        fcntl.flock(local, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for cohort in COHORTS:
            for backend in BACKENDS:
                work = output / cohort / backend
                for stage in STAGES:
                    try:
                        completed = latest(work, stage)
                        print(f'SKIP {cohort} {backend} {stage}: {completed.name}', flush=True)
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
                        python = screen.PP_PY if stage == 'ocr' and backend == 'ppocrv5_cuda' and not a.mock else screen.VLM_PY
                        cmd = [str(python), '-u', str(Path(__file__)), '--output-dir', str(output),
                               '--worker', stage, '--cohort', cohort, '--backend', backend, '--attempt', str(attempt)]
                        if a.mock:
                            cmd.append('--mock')
                        env = os.environ.copy()
                        if python == screen.PP_PY:
                            env['OMP_NUM_THREADS'] = '1'
                        print(f'RUN {cohort} {backend} {stage}', flush=True)
                        subprocess.run(cmd, cwd=REPO, check=True, env=env)
                    finally:
                        if lock is not None:
                            lock.close()
                write(work / 'COMPLETE.json', {'execution_mode': c['execution_mode'], 'contract_sha256': digest(load(work / 'contract.json'))})
                report(output)
        write(output / 'COMPLETE.json', {'execution_mode': c['execution_mode'], 'contract_sha256': digest(c)})
        report(output)


if __name__ == '__main__':
    main()
