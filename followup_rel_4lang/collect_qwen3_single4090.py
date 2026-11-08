"""Validate the completed run and archive all outcomes without selecting by score.

Run from the repository root with the experiment venv. Original outputs are read only.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / '01_code/src'))
SOURCE = ROOT / 'followup_rel_4lang/results/qwen3_single4090'
DEST = ROOT / 'followup_rel_4lang/artifacts/qwen3_single4090_20261107'


def read(path):
    return json.loads(path.read_text())


def rows(path):
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    x = rows(SOURCE / 'full_6x6.jsonl')
    xp = read(SOURCE / 'full_6x6_plan.json')
    xc = read(SOURCE / 'full_6x6.jsonl.contract.json')
    xs = read(SOURCE / 'full_6x6_summary.json')
    assert len(x) == len({r['input_id'] for r in x}) == 79020
    assert {r['input_id'] for r in x} == set(xp['input_ids']) == set(xc['input_ids'])
    assert all(r['status'] == 'success' for r in x)
    assert xc['manifest_sha256'] == sha(ROOT / '01_code/data/manifests/mpr_gui_manifest.jsonl')
    from mpr_crosslocale.analysis.summarize_cross_locale import summarize
    assert summarize(x) == xs, 'Stored 6x6 summary does not match the raw output'
    generation = {}
    for name, subset in [('overall', x), ('matched', [r for r in x if r['matched']]),
                         ('mismatch', [r for r in x if not r['matched']])]:
        correct = sum(r['parsed_generated_label'] == r['gold_label'] for r in subset)
        generation[name] = {'n': len(subset), 'correct': correct, 'accuracy': correct / len(subset)}
    matrix = []
    for q, cells in xs['accuracy_matrix'].items():
        for g, cell in cells.items():
            matrix.append({'question_language': q, 'gui_language': g, **cell})
    with (DEST / 'accuracy_6x6.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['question_language', 'gui_language', 'accuracy', 'n'],
                                lineterminator='\n')
        writer.writeheader()
        writer.writerows(matrix)

    rp = rows(SOURCE / 'full_rel/predictions.jsonl')
    rr = rows(SOURCE / 'full_rel/results.jsonl')
    rs = read(SOURCE / 'full_rel/summary.json')
    rc = read(SOURCE / 'full_rel/run_contract.json')
    assert len(rp) == len({r['input_id'] for r in rp}) == 18432
    assert len(rr) == len({r['input_id'] for r in rr}) == 23424
    assert all(r['status'] == 'success' for r in rp + rr)
    assert all(r['experiment_fingerprint'] == rc['experiment_fingerprint'] for r in rp + rr)
    cache = {r['input_id']: r for r in rp}
    for r in rr:
        p = cache[r['prediction_source_input_id']]
        for k in ('generated_text', 'parsed_generated_label', 'generation_correct', 'scored_predicted_label'):
            assert r[k] == p[k], (r['input_id'], k)
    quartets = defaultdict(dict)
    for r in rr:
        if r['primary_analysis_eligible']:
            quartets[r['pair_id']][r['condition']] = r
    assert all(set(q) == set('ORCF') for q in quartets.values())
    assert rs['statuses'] == {'success': 23424} and rs['actual_successful_inferences'] == 18432
    assert rs['source_issue_rows'] == sum(not r['eligible_without_source_adjudication'] for r in rr) == 400
    for dep, summary in rs['primary_descriptive_summary'].items():
        qs = [q for q in quartets.values() if q['O']['text_dependency'] == dep]
        assert len(qs) == summary['complete_unflagged_mismatch_quartets']
        assert len({q['O']['parallel_id'] for q in qs}) == summary['items']
        for c in 'ORCF':
            assert math.isclose(sum(q[c]['generation_correct'] for q in qs) / len(qs),
                                summary['generation_accuracy'][c])
        for contrast, values in summary['paired_contrasts'].items():
            later, earlier = contrast.split('-')
            corrected = sum(q[later]['generation_correct'] and not q[earlier]['generation_correct'] for q in qs)
            introduced = sum(not q[later]['generation_correct'] and q[earlier]['generation_correct'] for q in qs)
            assert corrected == values['errors_corrected'] and introduced == values['errors_introduced']

    gp = rows(SOURCE / 'grounding_main_orcf/predictions.jsonl')
    gb = rows(SOURCE / 'grounding_main_orcf/batches.jsonl')
    plan = read(SOURCE / 'grounding_main_orcf/input_plan.json')
    gs = read(SOURCE / 'grounding_main_orcf/summary.json')
    gc = read(SOURCE / 'grounding_main_orcf/run_contract.json')
    assert len(gp) == len({r['trial_id'] for r in gp}) == 7584
    assert {r['trial_id'] for r in gp} == {r['trial_id'] for g in plan for r in g['trials']}
    assert len(gb) == len({b['group_id'] for b in gb}) == len(plan) == 1896
    assert {b['group_id'] for b in gb} == {g['group_id'] for g in plan}
    assert [r for b in gb for r in b['results']] == gp
    from followup_rel_4lang.grounding_eval.run_qwen3_grounding import (
        digest, summarize as ground_summary, build_groups, pack_groups,
    )
    assert digest(plan) == gc['groups_sha256']
    descriptors = ROOT / 'followup_rel_4lang/grounding_eval/rtx4090_20261105/main_descriptors_draft_v2.json'
    assert pack_groups(build_groups('main', descriptors), 4) == plan
    assert all(b['contract_sha256'] == digest(gc) for b in gb)
    assert ground_summary(gb, len(plan)) == gs
    conditions = {}
    for c in 'ORCF':
        s = gs['conditions'][c]
        assert s['count'] == 1896
        conditions[c] = {**s, 'accuracy': s['hit'] / s['count'], 'invalid': s['count'] - s['valid']}
    for contract in (xc['model_config'], rc['model_config'], gc):
        assert contract['revision'] == '0c351dd01ed87e9c1b53cbc748cba10e6187ff3b'
        assert contract['patch_embed_memory_format'] == 'channels_last_3d'
        assert contract['max_pixels'] == 2097152
    assert xc['batch_size'] == rc['batch_size'] == gc['batch_size'] == 4
    failure_files = list(SOURCE.glob('*failures*.jsonl'))
    assert all(not rows(p) for p in failure_files)
    invalid = [r for r in gp if not r['valid_output']]
    write(DEST / 'grounding_format_failures.json', [
        {k: r[k] for k in ('trial_id', 'parallel_id', 'query_language', 'gui_language', 'condition',
                           'raw_output', 'stop_reason', 'output_tokens')} for r in invalid])
    metrics = {
        'validation_passed': True,
        'six_by_six': {'responses': len(x), 'score_accuracy': xs['overall_accuracy'],
                      'score_matched_accuracy': xs['matched_mean'], 'score_mismatch_accuracy': xs['mismatch_mean'],
                      'generation': generation, 'parse_failures': sum(not r['parse_success'] for r in x),
                      'first_response_utc': x[0]['timestamp'], 'last_response_utc': x[-1]['timestamp']},
        'rel': {'condition_rows': len(rr), 'unique_inferences': len(rp), 'source_issue_rows': 400,
                'primary': rs['primary_descriptive_summary'],
                'first_response_utc': rp[0]['timestamp'], 'last_response_utc': rp[-1]['timestamp']},
        'grounding': {'responses': len(gp), 'conditions': conditions, 'format_failures': len(invalid),
                      'R_minus_O_pp': 100 * (conditions['R']['accuracy'] - conditions['O']['accuracy']),
                      'F_minus_C_pp': 100 * (conditions['F']['accuracy'] - conditions['C']['accuracy'])},
    }
    write(DEST / 'metrics_and_validation.json', metrics)

    # Every full-run outcome is retained, including wrong answers and format failures.
    compressed = ['full_6x6.jsonl', 'full_6x6.jsonl.contract.json', 'full_6x6_plan.json',
                  'full_6x6_summary.csv',
                  'full_rel/predictions.jsonl', 'full_rel/results.jsonl',
                  'grounding_main_orcf/batches.jsonl', 'grounding_main_orcf/predictions.jsonl',
                  'grounding_main_orcf/input_plan.json',
                  'logs/full_6x6.log', 'logs/full_rel.log', 'logs/grounding_main_orcf.log']
    copied = ['full_6x6_summary.json', 'full_rel/summary.json',
              'full_rel/plan.json', 'full_rel/run_contract.json', 'full_rel/data_audit.json',
              'grounding_main_orcf/summary.json', 'grounding_main_orcf/run_contract.json',
              'batch_selection.json', 'smoke_validation.json', 'requirements.freeze.txt', 'git_commit.txt', 'run_full.sh']
    sources = {}
    for name in compressed + copied:
        src = SOURCE / name
        dst = DEST / (name + '.gz' if name in compressed else name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if name in compressed:
            with src.open('rb') as inp, dst.open('wb') as out:
                with gzip.GzipFile(filename='', mode='wb', fileobj=out, mtime=0, compresslevel=6) as zipped:
                    shutil.copyfileobj(inp, zipped)
            with gzip.open(dst, 'rb') as f:
                h = hashlib.sha256()
                n = 0
                for line in f:
                    h.update(line)
                    n += 1
            assert h.hexdigest() == sha(src)
        else:
            shutil.copyfile(src, dst)
        sources[name] = {'sha256': sha(src), 'bytes': src.stat().st_size,
                         'packaged_as': dst.relative_to(DEST).as_posix()}
        if name.endswith('.jsonl'):
            sources[name]['rows'] = n
    package_files = {p.relative_to(DEST).as_posix(): {'sha256': sha(p), 'bytes': p.stat().st_size}
                     for p in sorted(DEST.rglob('*')) if p.is_file() and p.name != 'MANIFEST.json'}
    write(DEST / 'MANIFEST.json', {
        'schema': 'qwen3-single4090-completed-run-v1',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'inference_code_commit': (SOURCE / 'git_commit.txt').read_text().strip(),
        'source_directory': SOURCE.relative_to(ROOT).as_posix(),
        'selection_policy': 'All outcomes from all three full runs, with no filtering by correctness. '
                            'Lossless gzip for large raw outputs, input plans, contracts and inference logs; '
                            'summaries, batch/smoke validation and runtime provenance retained. '
                            'Caches, screenshots, weights, setup/download logs and raw smoke outputs excluded.',
        'dataset_derived_license': 'CC-BY-NC-4.0; see 01_code/THIRD_PARTY_DATA.md',
        'descriptor_file': 'followup_rel_4lang/grounding_eval/rtx4090_20261105/main_descriptors_draft_v2.json',
        'descriptor_sha256': sha(ROOT / 'followup_rel_4lang/grounding_eval/rtx4090_20261105/main_descriptors_draft_v2.json'),
        'collector_sha256': sha(Path(__file__)), 'sources': sources, 'files': package_files})
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print('Packaged bytes:', sum(v['bytes'] for v in package_files.values()))


if __name__ == '__main__':
    main()
