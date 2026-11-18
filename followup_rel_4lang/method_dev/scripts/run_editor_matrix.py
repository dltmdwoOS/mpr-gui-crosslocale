"""Seven new Screen conditions, fixed PP-OCR, sequential L / V8 / V4 actors."""
import argparse
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
from run_stem_only_gui import read, write, jsonl
from run_stem_refinement_2x2 import latest
from mpr_crosslocale.methods.selective_alignment.schemas import digest, render, validate_input
from followup_rel_4lang.method_dev import editor_matrix as matrix, stem_refinement_2x2 as refinement
from followup_rel_4lang.method_dev.editor_matrix_backend import TextEditor

SOURCE = ROOT / 'artifacts/gpu_ocr_screen_paddle_v1/ppocrv5_cuda'
DEFAULT = ROOT / 'artifacts/ppocr_editor_matrix_screen_v2'
ACTORS = ('L', 'V8', 'V4')


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(output, mock=False, smoke=False):
    from run_gpu_ocr_screen import verify
    source = verify(SOURCE)
    if load(SOURCE / 'COMPLETE.json')['contract_sha256'] != digest(source):
        raise ValueError('Incomplete PP-OCR source')
    rows = read(SOURCE / 'inputs.jsonl')
    if len(rows) != 288 or digest(rows) != source['inputs_sha256']:
        raise ValueError('Frozen Screen 288 rows required')
    for row in rows:
        validate_input(row)
        if sha(REPO / row['image_path']) != row['image_sha256']:
            raise ValueError('Screenshot changed')
    if smoke:
        rows = [next(r for r in rows if r['source_language'] == 'en')]
    inventory_path = latest(SOURCE, 'ocr') / 'inventories.jsonl'
    extract_path = Path(source['extraction_path'])
    captures = {Path(__file__), ROOT / 'editor_matrix.py', ROOT / 'editor_matrix_backend.py',
                ROOT / 'scripts/editor_matrix_eval.py', ROOT / 'scripts/report_editor_matrix.py',
                ROOT / 'scripts/preflight_editor_matrix.py',
                ROOT / 'scripts/run_editor_matrix.sh', SOURCE / 'contract.json', SOURCE / 'COMPLETE.json',
                SOURCE / 'inputs.jsonl', inventory_path, extract_path,
                ROOT / 'artifacts/dataset_audit/oracle_spans_DIAGNOSTIC_ONLY.jsonl'}
    captures.update(REPO / p for p in source['source_sha256'])
    solvers = json.loads(json.dumps(source['solvers']))
    for solver, spec in solvers.items():
        previous = latest(SOURCE, 'infer_' + solver)
        pred, env = previous / 'evaluation/predictions.jsonl', previous / 'environment.json'
        spec['baseline_predictions'] = str(pred)
        spec['baseline_rewrite'] = str(latest(SOURCE, 'rewrite') / 'rewritten.jsonl')
        spec['reuse_sources'].append({'path': str(pred), 'downstream': spec['downstream'],
                                     'seed': source['seed'], 'environment': load(env)})
        captures.update({pred, env, Path(spec['baseline_rewrite'])})
        captures.update(Path(s['path']) for s in spec['reuse_sources'])
    contract = {'version': 'ppocr-editor-matrix-screen-v2', 'execution_mode': 'mock' if mock else 'gpu',
                'smoke_only': smoke, 'seed': source['seed'], 'inputs_sha256': digest(rows),
                'labels_sha256': source['labels_sha256'], 'inventory_path': str(inventory_path),
                'fixed_extraction': str(extract_path), 'config': source['config'], 'solvers': solvers,
                'cells': list(matrix.CELLS), 'inventory_regeneration': False, 'baseline_reexecution': False,
                'primary_pairs': 0 if smoke else 240, 'executed_pairs_per_cell': len(rows),
                'primary_semantic_items': 0 if smoke else 20,
                'source_sha256': {str(p.resolve().relative_to(REPO)): sha(p) for p in sorted(captures)},
                'editor_limits': matrix.LIMITS, 'method_batch_size': 1,
                'comparison': 'Development Screen. Joint sees MCQ+inventory; D extraction sees only source stem. Pipeline effects, not pure call-count intervention.',
                'fallback': 'One structural repair for failed components only. Failed stem preserved; failed A-D group preserved. Semantic warnings never reject.',
                'reuse': 'Fixed L extraction, inventory and L-D-S reused. L rewrite shared across solvers. Solver exact complete ordered batches only; conflicting outputs excluded.'}
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'contract.json').exists() and load(output / 'contract.json') != contract:
        raise ValueError('Frozen plan changed: use a new --output-dir')
    write(output / 'contract.json', contract)
    jsonl(output / 'inputs.jsonl', rows)
    return contract


def verify(output):
    c = load(output / 'contract.json')
    for path, expected in c['source_sha256'].items():
        if sha(REPO / path) != expected:
            raise ValueError('Frozen source changed: ' + path)
    if digest(read(output / 'inputs.jsonl')) != c['inputs_sha256']:
        raise ValueError('Inputs changed')
    return c


def actor_config(c, actor):
    config = json.loads(json.dumps(c['config']))
    config['output_tokens'] = matrix.LIMITS
    if actor != 'L':
        config['models']['editor_vlm'] = c['solvers'][actor[1:] + 'B']['config']['models']['editor_vlm']
    return config


def worker(output, actor, mock):
    c = verify(output)
    rows = read(output / 'inputs.jsonl')
    inventories = {r['image_sha256']: r for r in read(Path(c['inventory_path']))}
    folder = output / actor
    folder.mkdir(exist_ok=True)
    backend = TextEditor(actor_config(c, actor), REPO, folder / 'cache', actor[0], mock)
    start, complete = time.perf_counter(), False
    try:
        if actor == 'L':
            extractions = {r['source_key']: r for r in read(Path(c['fixed_extraction']))}
        else:
            ep = folder / 'extractions.jsonl'
            if (folder / 'EXTRACTION_COMPLETE').exists():
                extractions = {r['source_key']: r for r in read(ep)}
            else:
                sources = {digest(matrix.prompts.extraction_payload(r, stem_only=True)): r for r in rows}
                extractions = {}
                with ep.open('w') as f:
                    for i, (key, row) in enumerate(sorted(sources.items()), 1):
                        result = {'source_key': key, **refinement.extract(row, backend)}
                        extractions[key] = result
                        f.write(json.dumps(result, ensure_ascii=False) + '\n'); f.flush()
                        print(f'EXTRACT {actor} {i}/{len(sources)} {result["status"]}', flush=True)
                (folder / 'EXTRACTION_COMPLETE').write_text('complete\n')
        cells = [cell for cell in matrix.CELLS if cell.startswith(actor[0])]
        if c['smoke_only']:
            cells = [actor[0] + '-J-H']
        for cell in cells:
            target = folder / 'rewrite' / cell
            if (target / 'COMPLETE').exists():
                print('REUSE rewrite', actor, cell, flush=True)
                continue
            target.mkdir(parents=True, exist_ok=True)
            with (target / 'rewritten.jsonl').open('w') as f:
                for i, row in enumerate(rows, 1):
                    key = digest(matrix.prompts.extraction_payload(row, stem_only=True))
                    refs = extractions[key]['referents'] if cell[2] == 'D' else None
                    result = matrix.rewrite(row, inventories[row['image_sha256']], refs, backend, cell[2], cell[4])
                    out = result.pop('output')
                    record = {**row, 'question_stem': out['question_stem'], 'options': {k: out[k] for k in 'ABCD'},
                              'condition': cell, 'modified_question': render(out), 'extracted_referents': refs,
                              'execution_mode': c['execution_mode'], 'oracle_span': False, 'gold_target_used': False,
                              'inventory_status': inventories[row['image_sha256']]['status'], **result}
                    f.write(json.dumps(record, ensure_ascii=False) + '\n'); f.flush()
                    print(f'REWRITE {actor} {cell} {i}/{len(rows)} {record["status"]} calls={len(record["attempts"])}', flush=True)
            (target / 'COMPLETE').write_text('complete\n')
        if actor != 'L':
            from editor_matrix_eval import infer
            solver = actor[1:] + 'B'
            for cell in (cells if c['smoke_only'] else matrix.CELLS):
                target = folder / 'infer' / cell
                if (target / 'COMPLETE').exists():
                    print('REUSE inference', solver, cell, flush=True)
                    continue
                src = output / ('L' if cell.startswith('L') else actor) / 'rewrite' / cell / 'rewritten.jsonl'
                infer(REPO, ROOT, target, rows, read(src), cell, solver, c, backend, mock)
        complete = True
    finally:
        stamp = str(time.time_ns())
        write(folder / ('calls_' + stamp + '.json'), backend.calls)
        write(folder / ('cost_' + stamp + '.json'), {'actor': actor, 'execution_mode': c['execution_mode'],
              'complete': complete, 'wall_seconds': time.perf_counter() - start, 'model_loads': backend.load_events,
              'new_editor_runtime_ms': sum(r['runtime_ms'] for r in backend.calls if not r['cache_hit']),
              'cache_hits': sum(r['cache_hit'] for r in backend.calls), 'calls_observed_this_attempt': len(backend.calls)})
    if complete:
        (folder / 'COMPLETE').write_text('complete\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', action='store_true'); p.add_argument('--mock', action='store_true')
    p.add_argument('--smoke', action='store_true', help='One source query per actor plus one solver answer per VLM; no sweep or accuracy')
    p.add_argument('--worker', choices=ACTORS); p.add_argument('--output-dir', type=Path)
    a = p.parse_args()
    output = (a.output_dir or DEFAULT.with_name(DEFAULT.name + ('_mock' if a.mock else '') + ('_smoke' if a.smoke else ''))).resolve()
    if not output.is_relative_to(ROOT / 'artifacts'):
        raise ValueError('Output must be in method_dev/artifacts')
    if a.worker:
        c = verify(output)
        if c['execution_mode'] != ('mock' if a.mock else 'gpu'):
            raise ValueError('Execution mode mismatch')
        worker(output, a.worker, a.mock); return
    c = prepare(output, a.mock, a.smoke)
    print(f'PREPARED seven cells x 8B/4B; PP-OCR + L-D-S reused; primary={c["primary_pairs"]}/cell', flush=True)
    if not a.run and not a.smoke:
        return
    if not a.mock and not a.smoke:
        preflight = output / 'token_preflight.json'
        if not preflight.exists() or load(preflight).get('contract_sha256') != digest(c):
            subprocess.run([sys.executable, str(ROOT / 'scripts/preflight_editor_matrix.py'),
                            '--output-dir', str(output)], cwd=REPO, check=True)
    with (output / 'run.lock').open('a') as local, (ROOT / 'artifacts' / ('search_pipeline_mock.lock' if a.mock else 'search_pipeline_gpu.lock')).open('a') as gpu_lock:
        fcntl.flock(local, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(gpu_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for actor in ACTORS:
            if (output / actor / 'COMPLETE').exists():
                print('REUSE actor', actor, flush=True); continue
            cmd = [sys.executable, '-u', str(Path(__file__)), '--output-dir', str(output), '--worker', actor]
            if a.mock:
                cmd.append('--mock')
            print('RUN actor', actor, flush=True)
            subprocess.run(cmd, cwd=REPO, check=True)
            if not a.smoke:
                subprocess.run([sys.executable, str(ROOT / 'scripts/report_editor_matrix.py'), '--output-dir', str(output)], cwd=REPO, check=True)
        write(output / 'COMPLETE.json', {'execution_mode': c['execution_mode'], 'smoke_only': a.smoke,
                                        'contract_sha256': digest(c)})
        print('COMPLETE', output, flush=True)


if __name__ == '__main__':
    main()
