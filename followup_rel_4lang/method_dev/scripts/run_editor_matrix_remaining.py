"""Extend the frozen Screen V-D-S and V-D-H protocols to Selection and Internal."""
import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time

from run_editor_matrix import ROOT, REPO, DEFAULT as SCREEN, actor_config, load, sha, verify
from run_stem_only_gui import read, write, jsonl, unique
from run_stem_refinement_2x2 import latest
from run_gpu_ocr_screen import completed_source
from editor_matrix_eval import infer
from search_pipeline import EXCLUDED
from mpr_crosslocale.methods.selective_alignment.schemas import digest, render, validate_input
from followup_rel_4lang.method_dev import editor_matrix as matrix, stem_refinement_2x2 as refinement
from followup_rel_4lang.method_dev.editor_matrix_backend import TextEditor

DEFAULT = ROOT / 'artifacts/ppocr_editor_matrix_vd_full_dev_v1'
PP_FULL = ROOT / 'artifacts/gpu_ocr_full_dev_v1'
COHORTS = ('selection', 'internal_evaluation')
SOLVERS = ('8B', '4B')
CELLS = ('V-D-S', 'V-D-H')
COUNTS = {'screen': (288, 240, 20), 'selection': (240, 239, 20),
          'internal_evaluation': (1416, 1416, 118)}
LABELS = ROOT / 'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'


def actor(solver):
    return 'V' + solver[0]


def source_key(row):
    return digest(matrix.prompts.extraction_payload(row, stem_only=True))


def primary_ids(rows, labels):
    return sorted(r['pair_id'] for r in rows
                  if labels[r['pair_id']]['split'] == 'main' and r['pair_id'] != EXCLUDED)


def seed_sources(screen, solver):
    folder = screen / actor(solver)
    calls = {a['cache_key'] for r in read(folder / 'extractions.jsonl') for a in r['attempts']}
    return [folder / 'cache' / (key + '.json') for key in sorted(calls)]


def prepare(output, mock):
    screen = verify(SCREEN)
    done = load(SCREEN / 'COMPLETE.json')
    if done['execution_mode'] != 'gpu' or done['smoke_only'] or done['contract_sha256'] != digest(screen):
        raise ValueError('Completed GPU Screen matrix required')
    labels = unique(read(LABELS))
    if digest(labels) != screen['labels_sha256']:
        raise ValueError('Evaluation label digest differs from Screen')
    captures = {Path(__file__), ROOT / 'scripts/report_editor_matrix_remaining.py',
                ROOT / 'scripts/run_editor_matrix_remaining.sh', SCREEN / 'COMPLETE.json',
                SCREEN / 'contract.json', SCREEN / 'inputs.jsonl', Path(screen['inventory_path']),
                Path(screen['fixed_extraction'])}
    captures.update(REPO / name for name in screen['source_sha256'])
    for solver in SOLVERS:
        folder = SCREEN / actor(solver)
        captures.update({folder / 'extractions.jsonl', folder / 'EXTRACTION_COMPLETE'})
        if not mock:
            captures.update(seed_sources(SCREEN, solver))
        for cell in CELLS:
            captures.update(folder / stage / cell / 'COMPLETE' for stage in ('rewrite', 'infer'))
            captures.update({folder / 'rewrite' / cell / 'rewritten.jsonl',
                             folder / 'infer' / cell / 'predictions.jsonl'})
    item_ids = set()
    descriptors = {}
    common = {k: screen[k] for k in ('config', 'seed', 'labels_sha256', 'editor_limits', 'method_batch_size')}
    for cohort in ('screen', *COHORTS):
        if cohort == 'screen':
            base = SCREEN
            source = screen
            inventory = Path(source['inventory_path'])
        else:
            base = PP_FULL / cohort / 'ppocrv5_cuda'
            source = completed_source(base)
            if any(source[k] != screen[k] for k in ('seed', 'config', 'labels_sha256')):
                raise ValueError('PP-OCR contract differs from frozen Screen')
            inventory = latest(base, 'ocr') / 'inventories.jsonl'
            captures.update({base / 'contract.json', base / 'COMPLETE.json', inventory,
                             Path(source['extraction_path'])})
        input_path = base / 'inputs.jsonl'
        rows = read(input_path)
        original = unique(rows)
        ids = primary_ids(rows, labels)
        items = {original[pid]['parallel_id'] for pid in ids}
        if digest(rows) != source['inputs_sha256'] or (len(rows), len(ids), len(items)) != COUNTS[cohort] or items & item_ids:
            raise ValueError('Cohort input, denominator or split differs: ' + cohort)
        item_ids.update(items)
        images = {row['image_sha256']: row for row in rows}
        inventories = read(inventory)
        inv_by_sha = {r['image_sha256']: r for r in inventories}
        if len(inv_by_sha) != len(inventories) or inv_by_sha.keys() != images.keys():
            raise ValueError('Inventory coverage differs: ' + cohort)
        for row in rows:
            validate_input(row)
            if inv_by_sha[row['image_sha256']]['gui_language'] != row['gui_language']:
                raise ValueError('Inventory GUI language differs')
        for key, row in images.items():
            if sha(REPO / row['image_path']) != key:
                raise ValueError('Screenshot checksum differs')
        solvers = {}
        for solver in SOLVERS:
            spec = dict(source['solvers'][solver])
            if any(spec[k] != screen['solvers'][solver][k] for k in ('config', 'downstream')):
                raise ValueError('Solver checkpoint or downstream contract differs')
            if cohort != 'screen':
                attempt = latest(base, 'infer_' + solver)
                evaluation = attempt / 'evaluation'
                pred, env = evaluation / 'predictions.jsonl', attempt / 'environment.json'
                if load(evaluation / 'contract.json')['downstream'] != spec['downstream']:
                    raise ValueError('PP-OCR baseline solver profile differs')
                spec.update(baseline_predictions=str(pred), baseline_rewrite=str(latest(base, 'rewrite') / 'rewritten.jsonl'))
                spec['reuse_sources'] = [*spec['reuse_sources'], {'path': str(pred), 'downstream': spec['downstream'],
                                                               'seed': common['seed'], 'environment': load(env)}]
                captures.update({env, evaluation / 'contract.json'})
            for key in ('baseline_predictions', 'O_predictions'):
                path = Path(spec[key])
                predictions = read(path)
                selected = [r for r in predictions if r['condition'] == 'O'] if key == 'O_predictions' else predictions
                if set(unique(selected)) != set(original):
                    raise ValueError('Baseline prediction coverage differs: ' + key)
                captures.add(path)
            captures.add(Path(spec['baseline_rewrite']))
            captures.update(Path(s['path']) for s in spec['reuse_sources'])
            solvers[solver] = spec
        captures.add(input_path)
        descriptors[cohort] = {'inputs_path': str(input_path), 'inputs_sha256': digest(rows),
                               'inventory_path': str(inventory), 'solvers': solvers,
                               'fixed_extraction': source.get('fixed_extraction', source.get('extraction_path'))}
    contract = {**common, 'version': 'ppocr-editor-matrix-vd-full-dev-v1', 'cells': list(CELLS),
                'execution_mode': 'mock' if mock else 'gpu', 'screen_run': str(SCREEN), 'cohorts': descriptors,
                'source_sha256': {str(p.resolve().relative_to(REPO)): sha(p) for p in sorted(captures)}}
    output.mkdir(parents=True, exist_ok=True)
    path = output / 'contract.json'
    if path.exists():
        if load(path) != contract:
            raise ValueError('Frozen V-D plan differs; use a new --output-dir')
    else:
        write(path, contract)
    return contract


def run_actor(output, cohort, solver):
    contract = load(output / 'contract.json')
    config = {**contract, **contract['cohorts'][cohort]}
    rows = read(Path(config['inputs_path']))
    inv = {r['image_sha256']: r for r in read(Path(config['inventory_path']))}
    name = actor(solver)
    folder = output / cohort / name
    folder.mkdir(parents=True, exist_ok=True)
    mock = contract['execution_mode'] == 'mock'
    cache = output / 'cache' / name
    if not mock:
        cache.mkdir(parents=True, exist_ok=True)
        for path in seed_sources(SCREEN, solver):
            target = cache / path.name
            if not target.exists():
                target.symlink_to(path)
    backend = TextEditor(actor_config(config, name), REPO, cache, 'V', mock)
    start, complete = time.perf_counter(), False
    try:
        sources = {source_key(row): row for row in rows}
        extraction = folder / 'extractions.jsonl'
        if not (folder / 'EXTRACTION_COMPLETE').exists():
            with extraction.open('w') as stream:
                for index, (key, row) in enumerate(sorted(sources.items()), 1):
                    result = refinement.extract(row, backend)
                    stream.write(json.dumps({'source_key': key, **result}, ensure_ascii=False) + '\n')
                    print(f'EXTRACT {cohort} {solver} {index}/{len(sources)} {result["status"]}', flush=True)
            (folder / 'EXTRACTION_COMPLETE').write_text('complete\n')
        extracted = {r['source_key']: r['referents'] for r in read(extraction)}
        if extracted.keys() != sources.keys():
            raise ValueError('Incomplete shared VLM extraction')
        for cell in CELLS:
            rw = folder / 'rewrite' / cell
            if not (rw / 'COMPLETE').exists():
                rw.mkdir(parents=True, exist_ok=True)
                with (rw / 'rewritten.jsonl').open('w') as stream:
                    for index, row in enumerate(rows, 1):
                        refs = extracted[source_key(row)]
                        inventory = inv[row['image_sha256']]
                        result = matrix.rewrite(row, inventory, refs, backend, 'D', cell[-1])
                        fields = result.pop('output')
                        record = {**row, 'question_stem': fields['question_stem'], 'options': {k: fields[k] for k in 'ABCD'},
                                  'condition': cell, 'modified_question': render(fields), 'extracted_referents': refs,
                                  'execution_mode': contract['execution_mode'], 'oracle_span': False,
                                  'gold_target_used': False, 'inventory_status': inventory['status'], **result}
                        stream.write(json.dumps(record, ensure_ascii=False) + '\n')
                        print(f'REWRITE {cohort} {solver} {cell} {index}/{len(rows)} {result["status"]}', flush=True)
                (rw / 'COMPLETE').write_text('complete\n')
        for cell in CELLS:
            rw = folder / 'rewrite' / cell
            target = folder / 'infer' / cell
            if not (target / 'COMPLETE').exists():
                infer(REPO, ROOT, target, rows, read(rw / 'rewritten.jsonl'), cell, solver, config, backend, mock)
        complete = True
    finally:
        stamp = time.time_ns()
        write(folder / f'cost_{stamp}.json', {
            'complete': complete, 'wall_seconds': time.perf_counter() - start, 'model_loads': backend.load_events,
            'new_editor_runtime_ms': sum(r['runtime_ms'] for r in backend.calls if not r['cache_hit']),
            'editor_cache_hits': sum(r['cache_hit'] for r in backend.calls), 'editor_calls': len(backend.calls)})
    (folder / 'COMPLETE').write_text('complete\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--mock', action='store_true')
    parser.add_argument('--worker', nargs=2, metavar=('COHORT', 'SOLVER'))
    args = parser.parse_args()
    output = (args.output_dir or (DEFAULT.with_name(DEFAULT.name + '_mock') if args.mock else DEFAULT)).resolve()
    if not output.is_relative_to(ROOT / 'artifacts'):
        raise ValueError('Output must be inside method_dev/artifacts')
    if args.worker:
        cohort, solver = args.worker
        if cohort not in COHORTS or solver not in SOLVERS:
            raise ValueError('Unknown cohort or solver')
        run_actor(output, cohort, solver)
        return
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'run.lock').open('a') as local:
        fcntl.flock(local, fcntl.LOCK_EX | fcntl.LOCK_NB)
        contract = prepare(output, args.mock)
        print('PREPARED V-D-S and V-D-H x 8B and 4B; Selection 239 + Internal 1416; Screen reused', flush=True)
        if not args.run:
            return
        from report_editor_matrix_remaining import report
        lock_name = 'search_pipeline_mock.lock' if args.mock else 'search_pipeline_gpu.lock'
        with (ROOT / 'artifacts' / lock_name).open('a') as gpu_lock:
            fcntl.flock(gpu_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for cohort in COHORTS:
                for solver in SOLVERS:
                    if (output / cohort / actor(solver) / 'COMPLETE').exists():
                        print('REUSE', cohort, solver, flush=True)
                        continue
                    print('RUN', cohort, solver, flush=True)
                    subprocess.run([sys.executable, '-u', str(Path(__file__)), '--output-dir', str(output),
                                    '--worker', cohort, solver], cwd=REPO, check=True)
                report(output)
        write(output / 'COMPLETE.json', {'execution_mode': contract['execution_mode'], 'contract_sha256': digest(contract)})
        print('COMPLETE', output, flush=True)


if __name__ == '__main__':
    main()
