"""Frozen E1/M0 transfer: evaluator-owned inventories and paired O/method inference."""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from collections import Counter

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO/'01_code/src'), str(REPO), str(Path(__file__).parent)]
from run_stem_only_gui import read, write, jsonl, unique
from run_stem_refinement_2x2 import latest, record, save_cost
from run_overnight_two import completed_batches
from run_two_stage_v2 import budget
import run_source_copy_rewrite as evaluator
from search_pipeline import EXCLUDED, paired_bootstrap
from mpr_crosslocale.methods.selective_alignment.schemas import digest, fields, render, validate_input
from followup_rel_4lang.method_dev import stem_refinement_2x2 as method
from followup_rel_4lang.method_dev.two_stage_v2 import pipeline, prompts
from followup_rel_4lang.method_dev.two_stage_v2.backend import Backend

COHORTS = ('screen', 'selection', 'internal_evaluation')
CONDITIONS = ('O', 'E1_M0')


def snapshot(spec):
    hf = Path(os.environ.get('HF_HOME', '/home/jovyan/seungjae/.cache/huggingface'))
    return hf/'hub'/('models--'+spec['model_id'].replace('/', '--'))/'snapshots'/spec['revision']


def transfer_config(path):
    """Change only the inventory/evaluation VLM, preserving the selected method contract."""
    spec = json.loads(path.read_text())
    old = json.loads((ROOT/'artifacts/e1_stem_full_dev_v1/contract.json').read_text())
    config = copy.deepcopy(old['config'])
    vlm = {**config['models']['inventory'], **spec['vlm']}
    if vlm['family'] != 'qwen3_vl' or len(vlm['revision']) != 40:
        raise ValueError('This adapter requires a pinned Qwen3-VL checkpoint')
    vlm['path'] = str(snapshot(vlm))
    config['models']['inventory'] = vlm
    config['models']['editor_vlm'] = copy.deepcopy(vlm)  # Processor locator for the frozen evaluator.
    config['downstream']['model_config'].update(model_id=vlm['model_id'], revision=vlm['revision'])
    config['version'] = spec['version']
    return config, old


def model_ready(config):
    missing = []
    for role in ('inventory', 'text'):
        path = Path(config['models'][role]['path'])
        index = path/'model.safetensors.index.json'
        if not index.exists():
            missing.append(role+': '+str(index))
        else:
            for name in sorted(set(json.loads(index.read_text())['weight_map'].values())):
                if not (path/name).exists():
                    missing.append(role+': '+name)
        for name in ('config.json', 'tokenizer_config.json'):
            if not (path/name).exists():
                missing.append(role+': '+name)
    return missing


def replay_extraction(row, result, text_model):
    """Verify source-only E1 traces; never reuse GUI matches or evaluation predictions."""
    queue = list(result['attempts'])
    def replay(stage, role, system, user):
        if not queue:
            raise ValueError('Missing source extraction attempt')
        call = queue.pop(0)
        if (stage, role, system, user) != (call['stage'], call['role'], call['system_prompt'], call['user_prompt']):
            raise ValueError('Source extraction prompt differs')
        if (call['model_id'], call['revision']) != (text_model['model_id'], text_model['revision']):
            raise ValueError('Source extractor model differs')
        return call
    replayed = method.extract(row, replay)
    if queue or any(replayed[k] != result[k] for k in ('status', 'referents', 'errors')):
        raise ValueError('Imported extraction cannot be reproduced from its frozen responses')


def prepare(output, config_path, cohorts, mock=False, limit=None):
    config, old = transfer_config(config_path)
    base = ROOT/'artifacts/search_pipeline_v1'
    identity = json.loads((base/'data_contract.json').read_text())
    manifest = json.loads((base/'plan/manifest.json').read_text())
    if digest(manifest) != identity['plan'] or old['labels_sha256'] != identity['labels']:
        raise ValueError('Dataset identity differs')
    if old['prompt_sha256'] != {'E1': digest(method.EXTRACT_SYSTEM), 'M0': digest(prompts.SELECTIVE_GUI_SYSTEM)}:
        raise ValueError('Selected prompts changed')
    if config['models']['text'] != old['config']['models']['text']:
        raise ValueError('Fixed extraction/translation LM changed')
    paths = [Path(__file__), config_path, base/'data_contract.json', base/'plan/manifest.json',
             ROOT/'artifacts/e1_stem_full_dev_v1/contract.json', ROOT/'stem_refinement_2x2.py',
             ROOT/'scripts/run_stem_refinement_2x2.py', ROOT/'scripts/run_source_copy_rewrite.py',
             ROOT/'scripts/run_overnight_two.py', ROOT/'scripts/run_two_stage_v2.py',
             ROOT/'source_copy_rewrite.py', ROOT/'direct_selective_rewrite.py',
             ROOT/'visual_rewrite_backend.py', ROOT/'exact_batch_reuse.py',
             REPO/'01_code/src/mpr_crosslocale/models/qwen25vl.py',
             REPO/'01_code/src/mpr_crosslocale/models/qwen3_memory.py',
             REPO/'01_code/src/mpr_crosslocale/inference/prompts.py']
    paths += list((ROOT/'two_stage_v2').glob('*.py'))
    paths += list((REPO/'01_code/src/mpr_crosslocale/methods/selective_alignment').glob('*.py'))
    for path in paths:
        prior = old['source_sha256'].get(str(path.relative_to(REPO)))
        if prior is not None and hashlib.sha256(path.read_bytes()).hexdigest() != prior:
            raise ValueError('Selected 8B implementation changed: '+str(path.relative_to(REPO)))
    originals, extractions = {}, {}
    for cohort in cohorts:
        path = base/'plan'/f'{cohort}.jsonl'
        rows = read(path)
        if digest(rows) != manifest['cohorts'][cohort]['inputs_sha256']:
            raise ValueError('Original cohort changed')
        if limit:
            chosen = sorted({r['parallel_id'] for r in rows})[:limit]
            rows = [r for r in rows if r['parallel_id'] in chosen]
        unique(rows)
        for row in rows:
            validate_input(row)
        source = ROOT/'artifacts'/('stem_refinement_2x2_screen_v1' if cohort == 'screen' else 'e1_stem_full_dev_v1/'+cohort)
        extraction = latest(source/'extraction', 'E1')/'extractions.jsonl'
        by_key = {r['source_key']: r for r in read(extraction)}
        selected = {}
        for row in rows:
            key = digest(prompts.extraction_payload(row, stem_only=True))
            if key not in selected:
                replay_extraction(row, by_key[key], config['models']['text'])
                selected[key] = by_key[key]
        originals[cohort], extractions[cohort] = rows, list(selected.values())
        paths += [path, extraction]
    images = {r['image_sha256']: r for rows in originals.values() for r in rows}
    for row in images.values():
        path = (REPO/row['image_path']).resolve()
        if not path.is_relative_to(Path('/home/jovyan/seungjae')) or hashlib.sha256(path.read_bytes()).hexdigest() != row['image_sha256']:
            raise ValueError('Screenshot checksum/path differs')
    c = {'version': config['version'], 'execution_mode': 'mock' if mock else 'gpu', 'config': config,
         'downstream': config['downstream'], 'seed': config['seed'], 'labels_sha256': identity['labels'],
         'prompt_sha256': old['prompt_sha256'], 'cohorts': list(cohorts), 'limit_items': limit,
         'conditions': list(CONDITIONS), 'source_extraction_reused': True, 'inventory_owner': config['models']['inventory'],
         'source_sha256': {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
         'counts': {k: {'executed_pairs': len(v), 'images': len({r['image_sha256'] for r in v}),
                        'source_stems': len(extractions[k])} for k, v in originals.items()},
         'policy': 'Frozen E1/M0, fixed Qwen3-8B LM; fresh evaluator-owned inventory. Paired O and method; condition-separated batch3 queues. Main 1895 ITT; Screen pilot companions excluded posthoc. No tuning, R/T targets, or 366-item expansion.'}
    output.mkdir(parents=True, exist_ok=True)
    if (output/'contract.json').exists() and json.loads((output/'contract.json').read_text()) != c:
        raise ValueError('Frozen plan differs; choose a fresh output directory')
    write(output/'contract.json', c)
    for cohort, rows in originals.items():
        work = output/cohort
        work.mkdir(exist_ok=True)
        jsonl(work/'inputs.jsonl', rows)
        imported = work/'extraction/E1/attempt_import'
        imported.mkdir(parents=True, exist_ok=True)
        jsonl(imported/'extractions.jsonl', extractions[cohort])
        write(imported/'cost.json', {'new_runtime_ms': 0, 'source_extraction_reused': True})
        (imported/'COMPLETE').write_text('imported source-only extraction\n')
        write(work/'contract.json', {**c, 'inputs_sha256': digest(rows), 'reuse_sources': []})
    return c


def verify(output):
    c = json.loads((output/'contract.json').read_text())
    for path, sha in c['source_sha256'].items():
        if hashlib.sha256((REPO/path).read_bytes()).hexdigest() != sha:
            raise ValueError('Frozen source changed: '+path)
    return c


def stage(output, cohort, name, attempt, mock):
    c = verify(output)
    if mock != (c['execution_mode'] == 'mock'):
        raise ValueError('Execution mode differs')
    work = output/cohort
    rows = read(work/'inputs.jsonl')
    wc = json.loads((work/'contract.json').read_text())
    if digest(rows) != wc['inputs_sha256']:
        raise ValueError('Prepared inputs changed')
    if name in ('inventory', 'rewrite'):
        if not mock:
            budget(c['config'])
        backend = Backend(c['config'], REPO, output/'cache', mock)
        attempt.mkdir(parents=True)
        started, complete = time.perf_counter(), False
        try:
            if name == 'inventory':
                queue = sorted({r['image_sha256']: r for r in rows}.items())
                filename = 'inventories.jsonl'
                def transform(key, row):
                    return {'image_sha256': key, **pipeline.inventory(row, backend)}
            else:
                inventories = {r['image_sha256']: r for r in read(latest(work, 'inventory')/'inventories.jsonl')}
                extracts = {r['source_key']: r for r in read(work/'extraction/E1/attempt_import/extractions.jsonl')}
                queue = [(r['pair_id'], r) for r in rows]
                filename = 'rewritten.jsonl'
                def transform(key, row):
                    refs = extracts[digest(prompts.extraction_payload(row, stem_only=True))]['referents']
                    inv = inventories[row['image_sha256']]
                    return record(row, pipeline.selective(row, refs, backend, inv), refs, inv, 'E1_M0', mock)
            with (attempt/filename).open('w') as stream:
                for i, (key, row) in enumerate(queue, 1):
                    result = transform(key, row)
                    stream.write(json.dumps(result, ensure_ascii=False)+'\n')
                    stream.flush()
                    print(f'{cohort} {name.upper()} {i}/{len(queue)} {result["status"]}', flush=True)
            complete = True
        finally:
            save_cost(attempt, backend, started, complete)
    else:
        condition = 'O' if name == 'infer_O' else 'E1_M0'
        attempt.mkdir(parents=True)
        view = attempt/'view'
        view.mkdir()
        environment = Backend(c['config'], REPO, output/'cache', mock)
        env = {'software': environment.software, 'hardware': environment.hardware}
        write(attempt/'environment.json', env)
        sources = []
        if not mock:
            for previous in sorted(work.glob('infer_*/attempt_*')):
                path, ep = previous/'evaluation/predictions.jsonl', previous/'environment.json'
                if previous == attempt or not path.exists() or not ep.exists() or json.loads(ep.read_text()) != env:
                    continue
                complete = completed_batches(path)
                if not complete:
                    continue
                pp = view/f'reuse_{len(sources):04d}.jsonl'
                jsonl(pp, complete)
                sources.append({'path': str(pp), 'downstream': c['downstream'], 'seed': c['seed'], 'environment': env})
        write(view/'contract.json', {**wc, 'reuse_sources': sources, 'condition': condition})
        jsonl(view/'inputs.jsonl', rows)
        if condition == 'O':
            rewrite = view/'original'
            rewrite.mkdir()
            jsonl(rewrite/'rewritten.jsonl', [{**r, 'modified_question': render(fields(r)), 'diffs': []} for r in rows])
        else:
            rewrite = latest(work, 'rewrite')
        evaluator.CONDITION = condition
        evaluator.infer(view, rewrite, attempt/'evaluation', mock)
    (attempt/'COMPLETE').write_text('complete\n')


def summarize(output, mock):
    c = verify(output)
    if mock:
        write(output/'results.json', {'execution_mode': 'mock', 'empirical': False})
        return
    labels = unique(read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels) != c['labels_sha256']:
        raise ValueError('Evaluation labels changed')
    values, quality, costs = {}, {}, {}
    for cohort in c['cohorts']:
        work = output/cohort
        originals = unique(read(work/'inputs.jsonl'))
        ids = sorted(p for p in originals if labels[p]['split'] == 'main' and p != EXCLUDED)
        if len(ids) != {'screen': 240, 'selection': 239, 'internal_evaluation': 1416}[cohort]:
            raise ValueError('Primary cohort denominator differs')
        values[cohort] = {}
        for condition in CONDITIONS:
            pred = unique(read(latest(work, 'infer_'+condition)/'evaluation/predictions.jsonl'))
            if set(pred) != set(originals) or any(r['execution_mode'] != 'gpu' for r in pred.values()):
                raise ValueError('Incomplete/non-empirical predictions')
            values[cohort][condition] = {p: int(pred[p]['status'] == 'success' and pred[p]['parsed_generated_label'] == labels[p]['gold_answer']) for p in ids}
        rw = unique(read(latest(work, 'rewrite')/'rewritten.jsonl'))
        inv = read(latest(work, 'inventory')/'inventories.jsonl')
        quality[cohort] = {'inventory_status': dict(Counter(r['status'] for r in inv)),
                           'rewrite_status': dict(Counter(rw[p]['status'] for p in ids)),
                           'changed': sum(fields(rw[p]) != fields(originals[p]) for p in ids),
                           'errors': dict(Counter(e for p in ids for e in rw[p]['errors']))}
        costs[cohort] = {s: json.loads((latest(work, s)/('evaluation/cost.json' if s.startswith('infer') else 'cost.json')).read_text())
                         for s in ('inventory', 'rewrite', 'infer_O', 'infer_E1_M0')}
    if len(c['cohorts']) > 1:
        values['combined'] = {k: {p: v for cohort in c['cohorts'] for p, v in values[cohort][k].items()} for k in CONDITIONS}
    summary = {}
    for cohort, v in values.items():
        ids = sorted(v['O'])
        summary[cohort] = {'n': len(ids), 'correct': {k: sum(v[k].values()) for k in CONDITIONS},
                           'method_minus_O': paired_bootstrap(v['E1_M0'], v['O'], labels, 20261115, 10000),
                           'by_gui': {g: {'n': sum(p.rsplit('::', 1)[1] == g for p in ids),
                                          'correct': {k: sum(v[k][p] for p in ids if p.rsplit('::', 1)[1] == g) for k in CONDITIONS}}
                                      for g in ('en', 'zh', 'th', 'ru')}}
    result = {'execution_mode': 'gpu', 'development_only': True, 'summary': summary, 'quality': quality,
              'new_stage_costs': costs, 'contract_sha256': digest(c)}
    write(output/'results.json', result)
    lines = ['# Qwen3-VL-4B: 고정 E1/M0 전이 평가', '',
             '고정 Qwen3-8B LM과 E1/M0 prompt를 유지하고 inventory와 최종 풀이만 4B로 수행했다. Options는 원문을 유지한다. 기존 8B inventory·최종 예측은 사용하지 않았다.', '',
             '| 범위 | n | O | E1/M0 | 차이 | 95% item bootstrap CI | 회복/회귀 |',
             '| --- | ---: | ---: | ---: | ---: | --- | ---: |']
    for cohort, s in summary.items():
        x = s['method_minus_O']
        lines.append(f'| {cohort} | {s["n"]} | {s["correct"]["O"]}/{s["n"]} ({s["correct"]["O"]/s["n"]:.2%}) | '
                     f'{s["correct"]["E1_M0"]}/{s["n"]} ({s["correct"]["E1_M0"]/s["n"]:.2%}) | {100*x["difference"]:+.2f}pp | '
                     f'[{100*x["ci95"][0]:+.2f}, {100*x["ci95"][1]:+.2f}] | {x["recovery"]}/{x["regression"]} |')
    lines += ['', 'Main만 분석하며 기존 제외 1쌍과 Screen pilot 48쌍은 제외한다. 실패는 원문 fallback으로 포함했다. 이미 반복 관찰한 development cohort이므로 독립적인 일반화 검증은 아니다.', '',
              'E1 추출은 동일 LM·prompt의 완료 trace를 검증하여 재사용했다. 새 실행 시간에는 과거 추출 비용이 포함되지 않는다. O는 method 전처리 비용 없이 최종 풀이만 수행한다. 전체 신규 비용과 cache 사용은 results.json 및 stage cost.json에 기록한다.', '',
              'GUI 언어별 정답 수와 inventory/치환 실패 내역은 results.json에 보존한다. 과거 4B O/T/R/F는 장비와 batch가 달라 이번 paired O와 구분해야 한다.', '']
    lines += ['| 범위 | GUI | n | O 정확도 | E1/M0 정확도 | 차이 |',
              '| --- | --- | ---: | ---: | ---: | ---: |']
    for cohort, s in summary.items():
        for gui, g in s['by_gui'].items():
            n = g['n']
            if n:
                a, b = g['correct']['O']/n, g['correct']['E1_M0']/n
                lines.append(f'| {cohort} | {gui.upper()} | {n} | {a:.2%} | {b:.2%} | {100*(b-a):+.2f}pp |')
    (output/'REPORT_KO.md').write_text('\n'.join(lines))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=ROOT/'configs/transfer_qwen3_vl_4b_e1m0.json')
    p.add_argument('--cohorts', nargs='+', choices=COHORTS, default=['screen'])
    p.add_argument('--run', action='store_true')
    p.add_argument('--mock', action='store_true')
    p.add_argument('--limit-items', type=int)
    p.add_argument('--output-dir', type=Path)
    p.add_argument('--worker', choices=('inventory', 'rewrite', 'infer_O', 'infer_E1_M0'))
    p.add_argument('--cohort', choices=COHORTS)
    p.add_argument('--attempt', type=Path)
    a = p.parse_args()
    if a.limit_items is not None and (not a.mock or a.limit_items < 1):
        p.error('--limit-items is positive and mock-only')
    if len(set(a.cohorts)) != len(a.cohorts):
        p.error('Duplicate cohorts')
    output = (a.output_dir or ROOT/'artifacts'/('transfer_qwen3_vl_4b_e1m0_mock' if a.mock else 'transfer_qwen3_vl_4b_e1m0_v1')).resolve()
    if not output.is_relative_to(REPO):
        p.error('Output must remain inside repository')
    if a.worker:
        stage(output, a.cohort, a.worker, a.attempt, a.mock)
        return
    with (ROOT/'artifacts'/('search_pipeline_mock.lock' if a.mock else 'search_pipeline_gpu.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        c = prepare(output, a.config.resolve(), a.cohorts, a.mock, a.limit_items)
        missing = model_ready(c['config'])
        write(output/'readiness.json', {'missing_model_files': missing, 'counts': c['counts'], 'gpu_started': False})
        if not a.run:
            print('PREPARED', output, 'missing_model_files=', len(missing), flush=True)
            return
        if missing and not a.mock:
            raise ValueError('Pinned model cache incomplete: '+str(missing))
        if (output/'COMPLETE.json').exists():
            print('REUSE COMPLETE', output, flush=True)
            return
        started = time.perf_counter()
        for cohort in a.cohorts:
            for name in ('inventory', 'rewrite', 'infer_O', 'infer_E1_M0'):
                directory = output/cohort/name
                directory.mkdir(parents=True, exist_ok=True)
                attempts = sorted(directory.glob('attempt_*'))
                if any((x/'COMPLETE').exists() for x in attempts):
                    print('REUSE', cohort, name, flush=True)
                    continue
                attempt = directory/f'attempt_{len(attempts)+1:04d}'
                cmd = [sys.executable, '-u', str(Path(__file__)), '--output-dir', str(output),
                       '--cohort', cohort, '--worker', name, '--attempt', str(attempt)]
                if a.mock:
                    cmd.append('--mock')
                print(time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'RUN', cohort, name, flush=True)
                subprocess.run(cmd, check=True)
                if not (attempt/'COMPLETE').exists():
                    raise ValueError('Stage incomplete')
        summarize(output, a.mock)
        write(output/'COMPLETE.json', {'execution_mode': c['execution_mode'], 'contract_sha256': digest(c),
                                     'latest_invocation_wall_seconds': time.perf_counter()-started})
        print('COMPLETE', output, flush=True)


if __name__ == '__main__':
    main()
