"""Screenshot directly to selectively rewritten complete MCQ, then matched VLM evaluation."""
import argparse
import fcntl
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO/'01_code/src'), str(REPO), str(Path(__file__).parent)]
from followup_rel_4lang.method_dev import direct_selective_rewrite as single_pass
from followup_rel_4lang.method_dev.visual_rewrite_backend import VisualRewriteBackend
from mpr_crosslocale.methods.selective_alignment.schemas import digest, fields, render, validate_input
from mpr_crosslocale.inference.answer_parser import parse_label
from run_stem_only_gui import read, write, jsonl, unique
from search_pipeline import paired_bootstrap, EXCLUDED

CONDITION = single_pass.CONDITION


def prepare(source, output, mock, limit_items):
    marker = json.loads((source/'COMPLETE.json').read_text())
    parent = json.loads((source.parent/'contract.json').read_text())
    if marker['execution_mode'] != 'gpu' or parent['mode'] != 'gpu':
        raise ValueError('Completed GPU benchmark required')
    for name, sha in parent['source_hashes'].items():
        if hashlib.sha256((REPO/name).read_bytes()).hexdigest() != sha:
            raise ValueError('Frozen benchmark source changed: '+name)
    rows = read(source/'inputs.jsonl')
    if digest(rows) != json.loads((source/'plan.json').read_text())['input_sha256']:
        raise ValueError('Original input hash changed')
    if limit_items:
        selected = sorted({r['parallel_id'] for r in rows})[:limit_items]
        rows = [r for r in rows if r['parallel_id'] in selected]
    unique(rows)
    for row in rows:
        validate_input(row)
    inference_dir = Path(marker['predictions'])
    if not (inference_dir/'COMPLETE').exists():
        raise ValueError('Incomplete benchmark inference')
    config = json.loads(json.dumps(parent['config']))
    config['version'] = 'visual-selective-complete-rewrite-v1'
    config['models'] = {'editor_vlm': config['models']['inventory']}
    config['output_tokens'] = {'visual_rewrite': 768, 'visual_rewrite_repair': 768}
    baselines = {'source_predictions': str(inference_dir/'predictions.jsonl')}
    captured = [Path(__file__), ROOT/'direct_selective_rewrite.py', ROOT/'visual_rewrite_backend.py',
                ROOT/'two_stage_v2/backend.py', ROOT/'scripts/run_stem_only_gui.py',
                source/'inputs.jsonl', source/'COMPLETE.json', source.parent/'contract.json',
                inference_dir/'contract.json', inference_dir/'predictions.jsonl']
    for folder, key, pred_key in [('stem_only_gui_screen_v1','stem_predictions','predictions'),
                                  ('single_pass_stem_screen_v1','single_pass_stem_predictions','infer'),
                                  ('single_pass_all_screen_v1','single_pass_all_predictions','infer')]:
        directory = ROOT/'artifacts'/folder
        done = json.loads((directory/'COMPLETE.json').read_text())
        contract = json.loads((directory/'contract.json').read_text())
        if done['execution_mode'] != 'gpu' or done['contract_sha256'] != digest(contract) or contract['downstream'] != config['downstream']:
            raise ValueError('Baseline profile/contract differs')
        prediction = Path(done[pred_key])/'predictions.jsonl'
        if not (prediction.parent/'COMPLETE').exists():
            raise ValueError('Incomplete baseline')
        baselines[key] = str(prediction)
        captured += [directory/'COMPLETE.json', directory/'contract.json', prediction]
    frozen = {'version': config['version'], 'condition': CONDITION, 'execution_mode': 'mock' if mock else 'gpu',
              'config': config, 'downstream': config['downstream'], 'seed': config['seed'], 'source_cohort': str(source),
              'inputs_sha256': digest(rows), 'pairs': len(rows), 'labels_sha256': parent['base_data_contract']['labels'],
              **baselines, 'source_sha256': {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in captured},
              'prompt_sha256': digest(single_pass.SYSTEM), 'inventory_used': False, 'extracted_spans_supplied': False,
              'gold_or_parallel_targets_used': False, 'basic_calls_per_pair': 1, 'max_structure_repairs': 1,
              'validation': 'JSON complete stem and four string options only; semantic/diff flags never trigger rejection or repair',
              'comparison': 'Screenshot+original MCQ to complete selective rewrite; no inventory, edits, span IDs or occurrence output. Changed editor model and protocol are pipeline-level factors.'}
    output.mkdir(parents=True, exist_ok=True)
    target = output/'contract.json'
    if target.exists() and json.loads(target.read_text()) != frozen:
        raise ValueError('Code/config/source changed; choose a fresh directory')
    if target.exists() and read(output/'inputs.jsonl') != rows:
        raise ValueError('Prepared input changed')
    if not target.exists():
        jsonl(output/'inputs.jsonl', rows)
        write(target, frozen)
    return frozen


def rewrite(output, attempt, mock):
    contract = json.loads((output/'contract.json').read_text())
    rows = read(output/'inputs.jsonl')
    if digest(rows) != contract['inputs_sha256']:
        raise ValueError('Inputs changed')
    if not mock:
        from run_two_stage_v2 import budget
        budget(contract['config'])
    backend = VisualRewriteBackend(contract['config'], REPO, output/'cache', mock)
    attempt.mkdir(parents=True)
    started = time.perf_counter()
    complete = False
    try:
        with (attempt/'rewritten.jsonl').open('w') as f:
            for i, row in enumerate(rows, 1):
                result = single_pass.rewrite(row, backend)
                transformed = result.pop('output')
                record = {**row, 'question_stem': transformed['question_stem'], 'options': {k: transformed[k] for k in 'ABCD'},
                          'modified_question': render(transformed), 'condition': CONDITION,
                          'oracle_span': False, 'gold_target_used': False,
                          'execution_mode': contract['execution_mode'], 'inventory_used': False, **result}
                f.write(json.dumps(record, ensure_ascii=False)+'\n')
                f.flush()
                print(f'REWRITE {i}/{len(rows)} {record["status"]} changes={len(record["diffs"])} attempts={len(record["attempts"])}', flush=True)
        complete = True
    finally:
        write(attempt/'calls.json', backend.calls)
        write(attempt/'cost.json', {'complete': complete, 'wall_seconds': time.perf_counter()-started,
              'calls': len(backend.calls), 'cache_hits': sum(c['cache_hit'] for c in backend.calls),
              'new_runtime_ms': sum(c['runtime_ms'] for c in backend.calls if not c['cache_hit'])})
    if complete:
        (attempt/'COMPLETE').write_text('complete\n')


def infer(output, rewrite_dir, attempt, mock):
    infer_started = time.perf_counter()
    from types import SimpleNamespace
    import torch
    from mpr_crosslocale.models.qwen25vl import Qwen25VLAdapter
    contract = json.loads((output/'contract.json').read_text())
    profile = contract['downstream']
    model = profile['model_config']
    labels = {r['pair_id']: r for r in read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl')}
    if digest(labels) != contract['labels_sha256']:
        raise ValueError('Evaluation labels changed')
    originals = unique(read(output/'inputs.jsonl'))
    rows = read(rewrite_dir/'rewritten.jsonl')
    if set(unique(rows)) != set(originals):
        raise ValueError('Incomplete rewritten condition')
    for row in rows:
        before = originals[row['pair_id']]
        for key in ('parallel_id','source_language','gui_language','image_path','image_sha256','option_order'):
            if row[key] != before[key]:
                raise ValueError('Paired identity changed')
        single_pass.validate_output(json.dumps({'question_stem': row['question_stem'], 'options': row['options']}, ensure_ascii=False))
        if single_pass.diff_fields(before, fields(row)) != row['diffs']:
            raise ValueError('Stored text diff differs')
        if row['modified_question'] != render(fields(row)):
            raise ValueError('Rendered question changed')
        if not mock and hashlib.sha256((REPO/row['image_path']).read_bytes()).hexdigest() != row['image_sha256']:
            raise ValueError('Image changed')
    torch.set_num_threads(3)
    adapter = None
    if not mock:
        from run_two_stage_v2 import budget
        from transformers import set_seed
        budget(contract['config'])
        set_seed(contract['seed'])
        adapter = Qwen25VLAdapter(model_id=model['model_id'], revision=model['revision'], dtype=model['dtype'],
            attn_implementation=model['attn_implementation'], device_map='cuda:0',
            processor_kwargs={'use_fast': profile['processor_use_fast'], 'min_pixels': model['min_pixels'], 'max_pixels': model['max_pixels']},
            model_family=model['model_family'], patch_embed_memory_format=model['patch_embed_memory_format'])
        adapter.max_input_tokens = profile['max_input_tokens']
    queue = [{'pair_id': r['pair_id'], 'parallel_id': r['parallel_id'], 'image_paths': [str(REPO/r['image_path'])],
              'question_raw': r['modified_question'], 'gold_label': labels[r['pair_id']]['gold_answer']} for r in sorted(rows, key=lambda r: r['pair_id'])]
    attempt.mkdir(parents=True)
    write(attempt/'contract.json', {'execution_mode': contract['execution_mode'], 'parent_sha256': digest(contract),
          'downstream': profile, 'queue_sha256': digest(queue), 'condition_order': [CONDITION], 'order': 'pair_id sorted'})
    with (attempt/'predictions.jsonl').open('w') as f:
        for start in range(0, len(queue), profile['batch_size']):
            batch = queue[start:start+profile['batch_size']]
            t = time.perf_counter()
            if mock:
                preds = [SimpleNamespace(raw_output='A', rendered_prompt='MOCK', prompt_token_count=0, output_token_count=0) for _ in batch]
            else:
                torch.cuda.reset_peak_memory_stats()
                preds = adapter.generate_batch(batch, model['prompt_profile'], model['generation'], system_prompt=profile['system_prompt'], score_labels=profile['score_labels'])
            elapsed = (time.perf_counter()-t)*1000
            if len(preds) != len(batch):
                raise ValueError('Missing model output')
            for row, pred in zip(batch, preds, strict=True):
                record = {'pair_id': row['pair_id'], 'parallel_id': row['parallel_id'], 'condition': CONDITION,
                          'execution_mode': contract['execution_mode'], 'status': 'success',
                          'generated_text': pred.raw_output, 'parsed_generated_label': parse_label(pred.raw_output),
                          'rendered_prompt': pred.rendered_prompt, 'prompt_tokens': pred.prompt_token_count, 'output_tokens': pred.output_token_count,
                          'batch_id': CONDITION+':'+str(start), 'batch_size': len(batch), 'batch_runtime_ms': elapsed,
                          'peak_reserved_bytes': None if mock else torch.cuda.max_memory_reserved()}
                f.write(json.dumps(record, ensure_ascii=False)+'\n')
                f.flush()
            print(f'INFER {start+len(batch)}/{len(queue)}', flush=True)
    write(attempt/'cost.json', {'wall_seconds': time.perf_counter()-infer_started, 'execution_mode': contract['execution_mode']})
    (attempt/'COMPLETE').write_text('complete\n')


def summarize(output, rewrite_dir, prediction_dir, mock):
    if mock:
        write(output/'results.json', {'execution_mode': 'mock', 'empirical': False})
        return
    contract = json.loads((output/'contract.json').read_text())
    rows = unique(read(rewrite_dir/'rewritten.jsonl'))
    pred = unique(read(prediction_dir/'predictions.jsonl'))
    if set(rows) != set(pred):
        raise ValueError('Incomplete evaluation')
    labels = {r['pair_id']: r for r in read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl')}
    if digest(labels) != contract['labels_sha256']:
        raise ValueError('Evaluation labels changed')
    historical = {}
    for path in ('source_predictions', 'stem_predictions', 'single_pass_stem_predictions', 'single_pass_all_predictions'):
        for row in read(Path(contract[path])):
            key = (row['condition'], row['pair_id'])
            if key in historical:
                raise ValueError('Duplicate baseline prediction')
            historical[key] = row
    baseline_names = ('TS_ALL_SINGLE_PASS_GUI_AUTO', 'O', 'TS_STEM_SINGLE_PASS_GUI_AUTO', 'TS_STEM_ONLY_GUI_AUTO', 'TS_QSEL_OFULL_GUI_AUTO', 'TS_FULL_GUI', 'TS_SEL_GUI_AUTO')
    ids = sorted(p for p in rows if labels[p]['split'] == 'main' and p != EXCLUDED)
    def correct(row, pid):
        if row['execution_mode'] != 'gpu' or parse_label(row['generated_text']) != row['parsed_generated_label']:
            raise ValueError('Invalid GPU prediction')
        return int(row['status'] == 'success' and row['parsed_generated_label'] == labels[pid]['gold_answer'])
    values = {CONDITION: {p: correct(pred[p], p) for p in ids},
              **{c: {p: correct(historical[c,p], p) for p in ids} for c in baseline_names}}
    calls = json.loads((rewrite_dir/'calls.json').read_text())
    originals = unique(read(output/'inputs.jsonl'))
    same = [p for p in ids if fields(rows[p]) == fields(originals[p])]
    batches = {r['batch_id']: r['batch_runtime_ms'] for r in pred.values()}
    result = {'execution_mode': 'gpu', 'development_only': True, 'executed_pairs': len(rows), 'primary_pairs': len(ids),
              'semantic_items': len({rows[p]['parallel_id'] for p in ids}), 'correct': {c: sum(v.values()) for c,v in values.items()},
              'contrasts': {c: paired_bootstrap(values[CONDITION], v, labels, 20261115, 10000) for c,v in values.items() if c != CONDITION},
              'status': dict(Counter(rows[p]['status'] for p in ids)), 'fallback_reasons': dict(Counter(e for p in ids for e in rows[p]['errors'])),
              'changed_pairs': len(ids)-len(same),
              'changed_stem_pairs': sum(rows[p]['question_stem'] != originals[p]['question_stem'] for p in ids),
              'changed_options_pairs': sum(rows[p]['options'] != originals[p]['options'] for p in ids),
              'diff_segments_by_field': dict(Counter(d['field'] for p in ids for d in rows[p]['diffs'])),
              'digit_change_pairs': sum(bool(rows[p]['diagnostics']['digit_sequence_changed_fields']) for p in ids),
              'duplicate_option_pairs': sum(rows[p]['diagnostics']['new_duplicate_options'] for p in ids),
              'token_cap_hits': sum(c['output_tokens'] == c['generation']['max_new_tokens'] for c in calls),
              'label_changes_without_input_change': sum(pred[p]['parsed_generated_label'] != historical['O',p]['parsed_generated_label'] for p in same),
              'by_gui': {g: {'n': sum(rows[p]['gui_language'] == g for p in ids),
                         'correct': {c: sum(v[p] for p in ids if rows[p]['gui_language'] == g) for c,v in values.items()}} for g in ('en','zh','th','ru')},
              'cost': {'rewrite_vlm_calls': len(calls), 'repairs': sum(c['stage'].endswith('_repair') for c in calls),
                       'rewrite_vlm_runtime_seconds': sum(c['runtime_ms'] for c in calls)/1000,
                       'input_tokens': sum(c['input_tokens'] for c in calls), 'output_tokens': sum(c['output_tokens'] for c in calls),
                       'rewrite_vlm_peak_reserved_gib': max((c['peak_reserved_bytes'] for c in calls), default=0)/2**30,
                       'inference_seconds': sum(batches.values())/1000,
                       'vlm_peak_reserved_gib': max(r['peak_reserved_bytes'] for r in pred.values())/2**30},
              'pair_ids_sha256': digest(ids), 'config_sha256': digest(contract['config']), 'prompt_sha256': contract['prompt_sha256']}
    write(output/'results.json', result)
    names = {CONDITION: 'Visual selective complete rewrite', 'TS_ALL_SINGLE_PASS_GUI_AUTO': 'Inventory-based all-field joint', 'TS_STEM_SINGLE_PASS_GUI_AUTO': 'Single-pass Stem GUI', 'O': 'Original O', 'TS_STEM_ONLY_GUI_AUTO': 'Stem-only GUI · 추출/정렬 분리',
             'TS_QSEL_OFULL_GUI_AUTO': 'Hybrid GUI', 'TS_FULL_GUI': 'Full GUI', 'TS_SEL_GUI_AUTO': 'Selective GUI Auto'}
    lines = ['# Screenshot 직접 selective rewrite 결과', '', f"기존 Screen을 관찰한 뒤 추가한 개발 실험. 실행{len(rows)}pair, 주 분석{result['semantic_items']}개 semantic item·{len(ids)}pair. Pilot은 주 분석에서 제외한다.", '',
             '| 조건 | 정답 | 정확도 |', '| --- | ---: | ---: |']
    for c, k in result['correct'].items():
        lines.append(f'| {names[c]} | {k}/{len(ids)} | {k/len(ids):.2%} |')
    lines += ['', '| Single-pass − 기준 | 차이 | 95% item bootstrap CI | 회복/회귀 |', '| --- | ---: | --- | ---: |']
    for c,r in result['contrasts'].items():
        lines.append(f"| {names[c]} | {r['difference']*100:+.2f}pp | [{r['ci95'][0]*100:+.2f}, {r['ci95'][1]*100:+.2f}] | {r['recovery']}/{r['regression']} |")
    lines += ['', '20 semantic item의 개발 탐색 결과다. 10,000회 item bootstrap으로 계산했고 모든 fallback을 포함한다. Inventory 제거·변환 모델 변경·완성형 출력·출력 토큰 예산 변경을 포함한 pipeline 수준의 비교다.', '',
              '## 처리 진단', '', '```json', json.dumps({k: result[k] for k in ('status','fallback_reasons','changed_pairs','changed_stem_pairs','changed_options_pairs','digit_change_pairs','duplicate_option_pairs','token_cap_hits','label_changes_without_input_change','by_gui','cost')}, ensure_ascii=False, indent=2), '```']
    (output/'REPORT_KO.md').write_text('\n'.join(lines)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-cohort', type=Path, default=ROOT/'artifacts/two_stage_v2_hybrid/screen')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--limit-items', type=int)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--mock', action='store_true')
    parser.add_argument('--worker', choices=('rewrite','infer'))
    parser.add_argument('--attempt', type=Path)
    parser.add_argument('--rewrite-dir', type=Path)
    args = parser.parse_args()
    if args.limit_items is not None and args.limit_items < 1:
        parser.error('--limit-items must be positive')
    output = (args.output_dir or ROOT/'artifacts'/('visual_selective_rewrite_screen_v1_mock' if args.mock else 'visual_selective_rewrite_screen_v1')).resolve()
    contract = prepare(args.source_cohort.resolve(), output, args.mock, args.limit_items)
    if args.worker:
        if args.worker == 'rewrite':
            rewrite(output, args.attempt, args.mock)
        else:
            infer(output, args.rewrite_dir, args.attempt, args.mock)
        return
    if not args.run:
        print(json.dumps({'prepared': str(output), 'pairs': contract['pairs'], 'gpu_started': False}), flush=True)
        return
    if (output/'COMPLETE.json').exists():
        print('REUSE COMPLETE', output, flush=True)
        return
    run_started = time.perf_counter()
    lock = (ROOT/'artifacts'/('search_pipeline_mock.lock' if args.mock else 'search_pipeline_gpu.lock')).open('a')
    fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
    completed = {}
    for stage in ('rewrite','infer'):
        directory = output/stage
        directory.mkdir(exist_ok=True)
        attempts = sorted(directory.glob('attempt_*'))
        done = [p for p in attempts if (p/'COMPLETE').exists()]
        if done:
            completed[stage] = done[-1]
            continue
        attempt = directory/f'attempt_{len(attempts)+1:04d}'
        command = [sys.executable, '-u', str(Path(__file__)), '--source-cohort', str(args.source_cohort.resolve()),
                   '--output-dir', str(output), '--worker', stage, '--attempt', str(attempt)]
        if stage == 'infer':
            command += ['--rewrite-dir', str(completed['rewrite'])]
        if args.mock:
            command.append('--mock')
        if args.limit_items:
            command += ['--limit-items', str(args.limit_items)]
        with (output/(stage+'.log')).open('a') as log:
            child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in child.stdout:
                log.write(line)
                log.flush()
                print(line, end='', flush=True)
            if child.wait():
                raise RuntimeError(stage+' failed; inspect '+str(output/(stage+'.log')))
        completed[stage] = attempt
    summarize(output, completed['rewrite'], completed['infer'], args.mock)
    write(output/'COMPLETE.json', {'execution_mode': contract['execution_mode'], 'contract_sha256': digest(contract),
          **{k: str(v) for k,v in completed.items()}, 'execution_wall_seconds': time.perf_counter()-run_started,
          'wall_scope': 'after prepare; includes lock acquisition, stage workers/model loads, rewrite, inference and summary; earlier incomplete attempts not charged'})
    print('COMPLETE', output, flush=True)


if __name__ == '__main__':
    main()
