"""Audit and archive completed Screen/Selection/Internal GPU OCR development results."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sys
import tarfile

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / '01_code/src'), str(REPO), str(Path(__file__).parent)]
from run_gpu_ocr_remaining import DEFAULT_OUTPUT, SCREEN, ALL_COHORTS, BACKENDS, SOLVERS, STAGES, verify, load
import run_gpu_ocr_screen as screen
import run_ocr_remaining as cpu
from run_stem_only_gui import read, unique, write
from run_stem_refinement_2x2 import latest
from report_gpu_ocr_remaining import aggregate_cost, score
from finalize_gpu_ocr_screen import checked_contrast
from mpr_crosslocale.methods.selective_alignment.schemas import digest, fields, render
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits
from followup_rel_4lang.method_dev.two_stage_v2 import prompts
from compare_end_to_end import batch_share
from search_pipeline import EXCLUDED

REPORT = ROOT / 'reports/GPU_OCR_FULL_DEV_RESULTS_KO.md'
TABLES = ROOT / 'reports/GPU_OCR_FULL_DEV_TABLES_KO.md'
SNAPSHOT = ROOT / 'artifacts/gpu_ocr_full_dev_results_snapshot.json'
ARCHIVE = ROOT / 'artifacts/gpu_ocr_full_dev_completed.tar.gz'
MANIFEST = ROOT / 'artifacts/gpu_ocr_full_dev_archive_manifest.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_queue(rows, predictions, labels, expected):
    queue = [{'pair_id': r['pair_id'], 'parallel_id': r['parallel_id'],
              'image_paths': [str(REPO / r['image_path'])], 'question_raw': r['modified_question'],
              'gold_label': labels[r['pair_id']]['gold_answer'],
              'rendered_prompt': predictions[r['pair_id']]['rendered_prompt']}
             for r in sorted(rows, key=lambda r: r['pair_id'])]
    if digest(queue) != expected:
        raise ValueError('Inference queue differs from stored rewritten MCQs/images/labels/prompts')


def audit(output):
    c = verify(output)
    if load(output / 'COMPLETE.json') != {'execution_mode': 'gpu', 'contract_sha256': digest(c)}:
        raise ValueError('Completed real extension required')
    result = load(output / 'results.json')
    if result['contract_sha256'] != digest(c) or result['pending_conditions'] or result['pooled_key'] != 'all_158':
        raise ValueError('Full result missing or contract differs')
    if result['completed_cohorts_all_four'] != list(ALL_COHORTS):
        raise ValueError('Missing completed cohort')
    labels = unique(read(ROOT / 'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels) != c['labels_sha256']:
        raise ValueError('Label lock differs')
    files = {REPO / name for name in c['source_sha256']}
    files.update([output / 'contract.json', output / 'COMPLETE.json', output / 'results.json', output / 'REPORT_KO.md'])
    vectors = {b: {s: {} for s in SOLVERS} for b in BACKENDS}
    parts = {b: {s: [] for s in SOLVERS} for b in BACKENDS}
    wall, overlap, raw_count = {}, {}, 0
    for cohort in ALL_COHORTS:
        wall[cohort], overlap[cohort] = {}, {}
        for b in BACKENDS:
            work = SCREEN / b if cohort == 'screen' else output / cohort / b
            cc = screen.verify(work)
            if load(work / 'COMPLETE.json')['contract_sha256'] != digest(cc):
                raise ValueError('Incomplete child')
            original = unique(read(work / 'inputs.jsonl'))
            ids = {p for p in original if labels[p]['split'] == 'main' and p != EXCLUDED}
            if len(ids) != {'screen': 240, 'selection': 239, 'internal_evaluation': 1416}[cohort]:
                raise ValueError('Primary denominator differs')
            for row in {r['image_sha256']: r for r in original.values()}.values():
                if sha(REPO / row['image_path']) != row['image_sha256']:
                    raise ValueError('Screenshot bytes differ')
            inv = {r['image_sha256']: r for r in read(latest(work, 'ocr') / 'inventories.jsonl')}
            if set(inv) != {r['image_sha256'] for r in original.values()}:
                raise ValueError('Inventory image coverage differs')
            rw = unique(read(latest(work, 'rewrite') / 'rewritten.jsonl'))
            if set(rw) != set(original):
                raise ValueError('Rewrite coverage differs')
            for p in original:
                if rw[p]['options'] != original[p]['options'] or apply_edits(original[p], rw[p]['edits']) != fields(rw[p]) or rw[p]['modified_question'] != render(fields(rw[p])):
                    raise ValueError('Deterministic stem-only rewrite differs')
            images = {original[p]['image_sha256'] for p in ids}
            ext = {r['source_key']: r for r in read(Path(cc['extraction_path']))}
            extraction = [ext[k] for k in {digest(prompts.extraction_payload(original[p], stem_only=True)) for p in ids}]
            wall[cohort][b], overlap[cohort][b] = {}, {}
            cpu_work = screen.CPU if cohort == 'screen' else cpu.DEFAULT_OUTPUT / cohort
            cpu_rw = unique(read(latest(cpu_work, 'rewrite') / 'rewritten.jsonl'))
            files.update([work / 'contract.json', work / 'COMPLETE.json', work / 'inputs.jsonl',
                          latest(cpu_work, 'rewrite') / 'rewritten.jsonl', latest(cpu_work, 'ocr') / 'inventories.jsonl'])
            for s in SOLVERS:
                attempt = latest(work, 'infer_' + s)
                ec, vc = load(attempt / 'evaluation/contract.json'), load(attempt / 'view/contract.json')
                if ec['execution_mode'] != 'gpu' or ec['downstream'] != cc['solvers'][s]['downstream'] or ec['parent_sha256'] != digest(vc):
                    raise ValueError('Solver contract differs')
                pp = read(attempt / 'evaluation/predictions.jsonl')
                pred = unique(pp)
                if any(r['condition'] != cc['condition'] + '_' + s for r in pp):
                    raise ValueError('Condition differs')
                check_queue(list(rw.values()), pred, labels, ec['queue_sha256'])
                values = score(pp, original, ids, labels)
                stored = result['summary'][cohort][s]['methods'][b]
                if sum(values.values()) != stored['correct']:
                    raise ValueError('Raw accuracy differs')
                raw_count += len(pp)
                vectors[b][s].update(values)
                part = {'ocr': [inv[h] for h in images], 'vlm_inventory': [], 'extraction': extraction,
                        'matching': [rw[p] for p in ids], 'answer_seconds': batch_share(pp, lambda r: r['pair_id'] in ids)['seconds']}
                cost = aggregate_cost([part], len(ids))
                if any(abs(cost[k] - stored['cost'][k]) > 1e-8 for k in cost):
                    raise ValueError('Raw recipe cost differs')
                parts[b][s].append(part)
                spec = cc['solvers'][s]
                overlap[cohort][b][s] = {}
                for base, key in [('O', 'O_predictions'), ('VLM_inventory', 'VLM_predictions'), ('EasyOCR_CPU', 'CPU_predictions')]:
                    records = read(Path(spec[key]))
                    if base == 'O':
                        records = [r for r in records if r['condition'] == 'O']
                    checked_contrast(values, score(records, original, ids, labels), stored['contrasts'][base])
                    if base != 'O':
                        old_work = (ROOT / 'artifacts/stem_refinement_2x2_screen_v1/E1_M0' if cohort == 'screen' else cpu.E1 / cohort / 'E1_M0') if s == '8B' else screen.BASE4 / cohort
                        old_rw = cpu_rw if base == 'EasyOCR_CPU' else unique(read(latest(old_work, 'rewrite') / 'rewritten.jsonl'))
                        old_pred = unique(records)
                        same = {p for p in ids if fields(old_rw[p]) == fields(rw[p])}
                        overlap[cohort][b][s][base] = {'same_MCQs': len(same),
                            'same_MCQs_label_differences': sum(pred[p]['parsed_generated_label'] != old_pred[p]['parsed_generated_label'] for p in same)}
                        files.add(latest(old_work if base == 'VLM_inventory' else cpu_work, 'rewrite') / 'rewritten.jsonl')
                wall[cohort][b]['infer_' + s] = load(attempt / 'evaluation/cost.json')['wall_seconds']
            for stage in ('ocr', 'rewrite'):
                wall[cohort][b][stage] = load(latest(work, stage) / 'cost.json')['wall_seconds']
            wall[cohort][b]['total_seconds'] = sum(wall[cohort][b].values())
            for stage in STAGES:
                files.update(p for p in latest(work, stage).rglob('*') if p.is_file())
    for b in BACKENDS:
        for s in SOLVERS:
            v = vectors[b][s]
            if len(v) != 1895 or len({labels[p]['parallel_id'] for p in v}) != 158:
                raise ValueError('Full item/pair denominator differs')
            stored = result['summary']['all_158'][s]['methods'][b]
            if sum(v.values()) != stored['correct']:
                raise ValueError('Pooled accuracy differs')
            cost = aggregate_cost(parts[b][s], len(v))
            if any(abs(cost[k] - stored['cost'][k]) > 1e-8 for k in cost):
                raise ValueError('Pooled recipe cost differs')
    for s in SOLVERS:
        checked_contrast(vectors[BACKENDS[1]][s], vectors[BACKENDS[0]][s], result['summary']['all_158'][s]['ppocrv5_minus_easyocr_cuda'])
    return c, result, files, {'prediction_rows_including_reused_screen': raw_count,
        'queue_hashes_verified': 12, 'primary_pairs_each': 1895, 'semantic_items_each': 158,
        'same_question_diagnostics': overlap, 'stage_wall_seconds': wall,
        'extension_stage_wall_seconds': sum(wall[cohort][b]['total_seconds'] for cohort in ALL_COHORTS[1:] for b in BACKENDS),
        'joint_8b_4b_recipe_seconds': {b: result['summary']['all_158']['8B']['methods'][b]['cost']['total_seconds']
                + result['summary']['all_158']['4B']['methods'][b]['cost']['answer_seconds'] for b in BACKENDS}}


def main():
    c, result, files, diagnostics = audit(DEFAULT_OUTPUT)
    snapshot = {'as_of_utc': datetime.now(timezone.utc).isoformat(), 'completed': True,
                'result': result, 'completion_audit': diagnostics, 'contract_sha256': digest(c),
                'raw_result_sha256': sha(DEFAULT_OUTPUT / 'results.json')}
    write(SNAPSHOT, snapshot)
    TABLES.write_text((DEFAULT_OUTPUT / 'REPORT_KO.md').read_text())
    # The summary renderer is separate from the frozen inference/report sources.
    from gpu_ocr_full_summary import render_summary
    REPORT.write_text(render_summary(result, diagnostics))
    files.update([Path(__file__), ROOT / 'scripts/gpu_ocr_full_summary.py', REPORT, TABLES, SNAPSHOT,
                  ROOT / 'reports/GPU_OCR_FULL_DEV_RUNBOOK_KO.md', ROOT / 'artifacts/gpu_ocr_full_dev_readiness.json',
                  ROOT / 'tests/test_gpu_ocr_remaining.py', ROOT / 'tests/test_gpu_ocr_completion.py'])
    entries = {}
    for path in sorted(files):
        if not path.resolve().is_relative_to(REPO) or 'PRIVATE' in str(path):
            raise ValueError('Private/outside file forbidden in archive')
        if path.suffix.lower() in ('.safetensors', '.pth', '.onnx', '.pdiparams', '.jpg', '.jpeg', '.png', '.pyc'):
            raise ValueError('Model/image/bytecode forbidden in archive')
        h = sha(path)
        relative = str(path.resolve().relative_to(REPO))
        if relative in c['source_sha256'] and c['source_sha256'][relative] != h:
            raise ValueError('Frozen dependency changed before archive')
        entries[str(path.relative_to(REPO))] = {'bytes': path.stat().st_size, 'sha256': h}
    with tarfile.open(ARCHIVE, 'w:gz', compresslevel=6, dereference=True) as archive:
        for name in entries:
            archive.add(REPO / name, arcname=name, recursive=False)
    with tarfile.open(ARCHIVE, 'r:gz') as archive:
        if set(archive.getnames()) != set(entries):
            raise ValueError('Archive coverage differs')
        for member in archive:
            if hashlib.sha256(archive.extractfile(member).read()).hexdigest() != entries[member.name]['sha256']:
                raise ValueError('Archive member checksum differs')
    write(MANIFEST, {'as_of_utc': snapshot['as_of_utc'], 'archive': str(ARCHIVE.relative_to(REPO)),
        'bytes': ARCHIVE.stat().st_size, 'sha256': sha(ARCHIVE), 'files': entries,
        'scope': 'Completed GPU OCR Screen/Selection/Internal raw inventories, LM calls/rewrites, 8B/4B predictions, '
                 'contracts, costs, environment and frozen repository dependencies including referenced seed cache records. '
                 'No checkpoints, screenshots, private labels, mock/incomplete attempts or redundant newly generated cache copies.',
        'restore': 'Extract from repository root in a clean checkout; existing paths are overwritten. '
                   'Restore screenshots/models/OCR weights using dataset locks and runbooks. '
                   'Private evaluation labels must be supplied separately; historical contracts use this lab workspace paths.'})
    print('AUDITED 12 completed queues /', diagnostics['prediction_rows_including_reused_screen'], 'prediction rows')
    print('ARCHIVED', len(entries), 'files,', ARCHIVE.stat().st_size, 'bytes')
    print('REPORT', REPORT)


if __name__ == '__main__':
    main()
