"""Completed-cell GPU OCR results; aggregate only cohorts completed by all four conditions."""
import argparse
from collections import Counter
import hashlib
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / '01_code/src'), str(REPO), str(Path(__file__).parent)]
from run_gpu_ocr_remaining import verify, DEFAULT_OUTPUT, SCREEN, COHORTS, ALL_COHORTS, BACKENDS, SOLVERS, load
import run_gpu_ocr_screen as screen
import run_ocr_remaining as cpu
import run_ocr_4b as cpu4
from run_stem_only_gui import read, unique, write
from run_stem_refinement_2x2 import latest
from report_ocr_remaining import ocr_seconds
from compare_end_to_end import call_map, call_seconds, batch_share
from search_pipeline import EXCLUDED, paired_bootstrap
from mpr_crosslocale.methods.selective_alignment.schemas import digest, fields
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits
from mpr_crosslocale.inference.answer_parser import parse_label
from followup_rel_4lang.method_dev.two_stage_v2 import prompts

METHODS = ('O', 'VLM_inventory', 'EasyOCR_CPU', *BACKENDS)


def aggregate_cost(parts, n):
    """Deduplicate preprocessing keys globally; batch IDs are local to their cohort."""
    cost = {'inventory_seconds': ocr_seconds([r for part in parts for r in part['ocr']]) if any(part['ocr'] for part in parts)
            else call_seconds(call_map([r for part in parts for r in part['vlm_inventory']])),
            'extraction_seconds': call_seconds(call_map([r for part in parts for r in part['extraction']])),
            'matching_seconds': call_seconds(call_map([r for part in parts for r in part['matching']])),
            'answer_seconds': sum(part['answer_seconds'] for part in parts)}
    cost['total_seconds'] = sum(cost.values())
    cost['seconds_per_pair'] = cost['total_seconds'] / n
    return cost


def score(rows, original, ids, labels):
    pp = unique(rows)
    if set(pp) != set(original):
        raise ValueError('Incomplete paired prediction queue')
    if any(r['execution_mode'] != 'gpu' or parse_label(r['generated_text']) != r['parsed_generated_label'] for r in rows):
        raise ValueError('Invalid prediction provenance')
    return {p: int(pp[p]['status'] == 'success' and pp[p]['parsed_generated_label'] == labels[p]['gold_answer']) for p in ids}


def common_completed(values):
    return [cohort for cohort in ALL_COHORTS if all(b in values[cohort][s] for s in SOLVERS for b in BACKENDS)]


def report(output):
    c = verify(output)
    pending = []
    completed = {}
    for cohort in COHORTS:
        for b in BACKENDS:
            for solver in SOLVERS:
                try:
                    completed[cohort, b, solver] = latest(output / cohort / b, 'infer_' + solver)
                except ValueError:
                    pending.append(cohort + '/' + b + '/' + solver)
    if c['execution_mode'] == 'mock':
        write(output / 'results.json', {'execution_mode': 'mock', 'empirical': False,
              'completed_conditions': ['/'.join(key) for key in completed], 'pending_conditions': pending})
        print(f'MOCK report: {len(completed)}/8 completed; no empirical accuracy', flush=True)
        return
    labels = unique(read(ROOT / 'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels) != c['labels_sha256']:
        raise ValueError('Label lock differs')
    values, stages, summaries, originals, quality, captures = {}, {}, {}, {}, {}, {}
    def rows(path):
        path = Path(path)
        captures[str(path.resolve().relative_to(REPO))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return read(path)
    for cohort in ALL_COHORTS:
        works = {b: SCREEN / b if cohort == 'screen' else output / cohort / b for b in BACKENDS}
        cc = load(works[BACKENDS[0]] / 'contract.json')
        original = unique(rows(works[BACKENDS[0]] / 'inputs.jsonl'))
        ids = {p for p in original if labels[p]['split'] == 'main' and p != EXCLUDED}
        if len(ids) != {'screen': 240, 'selection': 239, 'internal_evaluation': 1416}[cohort]:
            raise ValueError('Cohort denominator differs')
        originals[cohort], values[cohort], stages[cohort], quality[cohort] = original, {}, {}, {}
        images = {original[p]['image_sha256'] for p in ids}
        ext = {r['source_key']: r for r in rows(cc['extraction_path'])}
        extraction = [ext[k] for k in sorted({digest(prompts.extraction_payload(original[p], stem_only=True)) for p in ids})]
        cpu_work = screen.CPU if cohort == 'screen' else cpu.DEFAULT_OUTPUT / cohort
        cpu_inv = {r['image_sha256']: r for r in rows(latest(cpu_work, 'ocr') / 'inventories.jsonl')}
        cpu_rw = unique(rows(latest(cpu_work, 'rewrite') / 'rewritten.jsonl'))
        for solver in SOLVERS:
            spec = cc['solvers'][solver]
            values[cohort][solver], stages[cohort][solver] = {}, {}
            for name, key in [('O', 'O_predictions'), ('VLM_inventory', 'VLM_predictions'), ('EasyOCR_CPU', 'CPU_predictions')]:
                pp = rows(spec[key])
                if name == 'O':
                    pp = [r for r in pp if r['condition'] == 'O']
                values[cohort][solver][name] = score(pp, original, ids, labels)
                part = {'ocr': [], 'vlm_inventory': [], 'extraction': [], 'matching': [],
                        'answer_seconds': batch_share(pp, lambda r: r['pair_id'] in ids)['seconds']}
                if name != 'O':
                    part['extraction'] = extraction
                    if name == 'EasyOCR_CPU':
                        part['ocr'] = [cpu_inv[s] for s in sorted(images)]
                        part['matching'] = [cpu_rw[p] for p in sorted(ids)]
                    else:
                        vlm_work = ROOT / 'artifacts/stem_refinement_2x2_screen_v1/E1_M0' if cohort == 'screen' else cpu.E1 / cohort / 'E1_M0'
                        inv_path = Path(cc['baseline_inventory'])
                        if solver == '4B':
                            vlm_work = screen.BASE4 / cohort
                            inv_path = latest(vlm_work, 'inventory') / 'inventories.jsonl'
                        old_inv = {r['image_sha256']: r for r in rows(inv_path)}
                        old_rw = unique(rows(latest(vlm_work, 'rewrite') / 'rewritten.jsonl'))
                        part['vlm_inventory'] = [old_inv[s] for s in sorted(images)]
                        part['matching'] = [old_rw[p] for p in sorted(ids)]
                stages[cohort][solver][name] = part
            for b in BACKENDS:
                work = works[b]
                if cohort != 'screen' and (cohort, b, solver) not in completed:
                    continue
                attempt = latest(work, 'infer_' + solver)
                bc = screen.verify(work)
                ec = load(attempt / 'evaluation/contract.json')
                if ec['execution_mode'] != 'gpu' or ec['downstream'] != spec['downstream'] or ec['parent_sha256'] != digest(load(attempt / 'view/contract.json')):
                    raise ValueError('Solver contract differs')
                pp = rows(attempt / 'evaluation/predictions.jsonl')
                if any(r['condition'] != bc['condition'] + '_' + solver for r in pp):
                    raise ValueError('Prediction condition differs')
                values[cohort][solver][b] = score(pp, original, ids, labels)
                inv = {r['image_sha256']: r for r in rows(latest(work, 'ocr') / 'inventories.jsonl')}
                rw = unique(rows(latest(work, 'rewrite') / 'rewritten.jsonl'))
                if set(rw) != set(original) or len(inv) != len({r['image_sha256'] for r in original.values()}):
                    raise ValueError('OCR/rewrite coverage differs')
                for p in original:
                    if rw[p]['options'] != original[p]['options'] or apply_edits(original[p], rw[p]['edits']) != fields(rw[p]):
                        raise ValueError('Selective rewrite scope differs')
                    for field in ('parallel_id', 'image_sha256', 'source_language', 'gui_language', 'option_order'):
                        if rw[p][field] != original[p][field]:
                            raise ValueError('Paired identity differs')
                stages[cohort][solver][b] = {'ocr': [inv[s] for s in sorted(images)], 'vlm_inventory': [],
                    'extraction': extraction, 'matching': [rw[p] for p in sorted(ids)],
                    'answer_seconds': batch_share(pp, lambda r: r['pair_id'] in ids)['seconds']}
                quality[cohort][b + '/' + solver] = {'inventory_status': dict(Counter(inv[s]['status'] for s in images)),
                    'rewrite_status': dict(Counter(rw[p]['status'] for p in ids)),
                    'changed_pairs': sum(fields(rw[p]) != fields(original[p]) for p in ids),
                    'unparsed': sum(r['pair_id'] in ids and r['parsed_generated_label'] not in ('A', 'B', 'C', 'D') for r in pp),
                    'ocr_stage_all_rows': load(latest(work, 'ocr') / 'cost.json'),
                    'matching_stage_all_rows': load(latest(work, 'rewrite') / 'cost.json'),
                    'inference_stage_all_rows': load(attempt / 'evaluation/cost.json')}
    complete = common_completed(values)
    pooled = 'all_158' if len(complete) == 3 else 'completed_cohorts_only'
    values[pooled], stages[pooled] = {}, {}
    for solver in SOLVERS:
        values[pooled][solver] = {m: {p: v for cohort in complete for p, v in values[cohort][solver][m].items()} for m in METHODS}
        stages[pooled][solver] = {m: [stages[cohort][solver][m] for cohort in complete] for m in METHODS}
    if pooled == 'all_158' and len(values[pooled]['8B']['O']) != 1895:
        raise ValueError('Full primary denominator differs')
    for cohort, by_solver in values.items():
        summaries[cohort] = {}
        for solver, methods in by_solver.items():
            ids = set(methods['O'])
            summary = {'n': len(ids), 'items': len({labels[p]['parallel_id'] for p in ids}), 'methods': {}}
            for name, scores in methods.items():
                parts = stages[cohort][solver][name] if cohort == pooled else [stages[cohort][solver][name]]
                summary['methods'][name] = {'correct': sum(scores.values()), 'accuracy': sum(scores.values()) / len(ids),
                    'cost': aggregate_cost(parts, len(ids)),
                    'by_gui': {g: {'n': sum(p.endswith('::' + g) for p in ids),
                                   'correct': sum(v for p, v in scores.items() if p.endswith('::' + g))} for g in ('en', 'zh', 'th', 'ru')}}
                if name in BACKENDS:
                    summary['methods'][name]['contrasts'] = {base: paired_bootstrap(scores, methods[base], labels, 20261115, 10000)
                                                             for base in ('O', 'VLM_inventory', 'EasyOCR_CPU')}
            if all(b in methods for b in BACKENDS):
                summary['ppocrv5_minus_easyocr_cuda'] = paired_bootstrap(methods[BACKENDS[1]], methods[BACKENDS[0]], labels, 20261115, 10000)
            summaries[cohort][solver] = summary
    result = {'execution_mode': 'gpu', 'development_only': True, 'completed_cohorts_all_four': complete,
              'pooled_cohorts': complete, 'pooled_key': pooled, 'pending_conditions': pending,
              'summary': summaries, 'quality': quality, 'contract_sha256': digest(c),
              'source_and_raw_sha256': captures,
              'cost_scope': 'Main rows only; globally deduplicated OCR/LM cache keys including original cached runtimes. '
                            'Each complete batch counted once and allocated by primary rows. Model load/startup excluded.'}
    write(output / 'results.json', result)
    lines = ['# GPU OCR: Screen・Selection・Internal', '',
             '완료된 prediction queue만 집계한다. Screen은 기존 결과를 재사용했다. 전체 주 분석은 main158문항·1,895쌍이며, Selection 사전 제외1쌍과 Screen pilot48쌍은 실행에 남기고 아래 성능·비용에서 제외한다.', '',
             '네 GPU 조건이 모두 완료된 집합: ' + ', '.join(complete) + '.',
             '미완료 조건: ' + (', '.join(pending) or '없음') + '.', '',
             'Pooled 표는 네 조건이 모두 끝난 동일 집합만 합산한다. 개별 Selection/Internal 조건이 먼저 끝나면 해당 행은 표시하지만 pooled 분모에 먼저 섞지 않는다.', '',
             '| 범위 | Solver | n | 방법 | 정답 | 정확도 | Inventory | 추출+정렬 | 풀이 | 총시간 | 초/pair |',
             '| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for cohort, by_solver in summaries.items():
        for solver, s in by_solver.items():
            for name, row in s['methods'].items():
                if cohort in COHORTS and not any(b in s['methods'] for b in BACKENDS):
                    continue
                t = row['cost']
                lines.append(f"| {cohort} | {solver} | {s['n']} | {name} | {row['correct']} | {row['accuracy']:.2%} | {t['inventory_seconds']/60:.2f}분 | {(t['extraction_seconds']+t['matching_seconds'])/60:.2f}분 | {t['answer_seconds']/60:.2f}분 | {t['total_seconds']/60:.2f}분 | {t['seconds_per_pair']:.3f} |")
    lines += ['', result['cost_scope'], '',
              '공유 전처리를 solver별 독립 recipe에 각각 청구한다. 기존 캐시 재사용으로 절약한 실제 신규 시간·stage wall은 results.json에 따로 보존한다. OCR 생성 성공은 문자 인식 정확도의 GT 검증이 아니다.', '',
              '## Paired 비교', '', '| 범위 | Solver | 비교 | 차이 | Item bootstrap 95% CI | 회복/회귀 |', '| --- | --- | --- | ---: | --- | ---: |']
    for cohort, by_solver in summaries.items():
        for solver, s in by_solver.items():
            contrasts = [(b + ' − ' + base, v) for b in BACKENDS if b in s['methods'] for base, v in s['methods'][b]['contrasts'].items()]
            if 'ppocrv5_minus_easyocr_cuda' in s:
                contrasts.append(('PP-OCRv5 − EasyOCR CUDA', s['ppocrv5_minus_easyocr_cuda']))
            for name, v in contrasts:
                lines.append(f"| {cohort} | {solver} | {name} | {100*v['difference']:+.2f}pp | [{100*v['ci95'][0]:+.2f}, {100*v['ci95'][1]:+.2f}]pp | {v['recovery']}/{v['regression']} |")
    lines += ['', '## GUI 언어별', '', '| 범위 | Solver | 방법 | EN | ZH | TH | RU |', '| --- | --- | --- | --- | --- | --- | --- |']
    for cohort, by_solver in summaries.items():
        for solver, s in by_solver.items():
            for b in BACKENDS:
                if b not in s['methods']:
                    continue
                g = s['methods'][b]['by_gui']
                lines.append('| ' + ' | '.join([cohort, solver, b] + [f"{g[l]['correct']}/{g[l]['n']}" for l in ('en', 'zh', 'th', 'ru')]) + ' |')
    lines += ['', '실패·fallback·미파싱을 분모에서 제외하지 않는다.',
              'Semantic-item bootstrap 10,000회이며 이 집합은 이미 반복 관찰한 개발 데이터다. Selection/Internal이라는 이름이 독립적인 최종 검증을 뜻하지 않는다.', '']
    (output / 'REPORT_KO.md').write_text('\n'.join(lines))
    print('REPORT ' + str(output / 'REPORT_KO.md'), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT)
    report(p.parse_args().output_dir.resolve())
