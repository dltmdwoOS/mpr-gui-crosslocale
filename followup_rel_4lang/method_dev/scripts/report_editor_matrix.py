"""Incremental Screen matrix report; no model loading or editing."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from run_editor_matrix import ROOT, DEFAULT, verify, load
from run_stem_only_gui import read, write, unique
from compare_end_to_end import batch_share, call_map, call_seconds
from search_pipeline import paired_bootstrap, EXCLUDED
from mpr_crosslocale.methods.selective_alignment.schemas import digest
from followup_rel_4lang.method_dev import editor_matrix as matrix


def source_quality(original, ids, records):
    # Post-generation diagnostics only; this module is never imported by the editor.
    annotated = unique(read(ROOT / 'artifacts/dataset_audit/oracle_spans_DIAGNOSTIC_ONLY.jsonl'))
    gold = found = matched = 0
    for pid in ids:
        refs = records[digest(matrix.prompts.extraction_payload(original[pid], stem_only=True))]['referents'] or []
        g = {(r['start'], r['end']) for r in annotated[pid]['referents'] if r['field'] == 'question_stem'}
        f = {(r['start'], r['end']) for r in refs}
        gold += len(g); found += len(f); matched += len(g & f)
    p, r = matched / found if found else 0, matched / gold if gold else 0
    return {'precision': p, 'recall': r, 'f1': 2*p*r/(p+r) if p+r else 0,
            'gold': gold, 'found': found, 'matched': matched,
            'scope': 'pair-weighted exact source-span diagnostic; not GUI correspondence precision'}


def call_stats(calls):
    calls = list(calls.values())
    def total(key):
        return sum(c[key] for c in calls) if all(c.get(key) is not None for c in calls) else None
    return {'calls': len(calls), 'repairs': sum(c['stage'].endswith('repair') for c in calls),
            'input_tokens': total('input_tokens'), 'output_tokens': total('output_tokens'),
            'prefill_forward_gpu_ms': total('prefill_forward_gpu_ms'),
            'decode_forward_gpu_ms': total('decode_forward_gpu_ms'),
            'tokenization_ms': total('tokenization_ms'),
            'cap_hits': sum(c.get('output_limit_reached', c.get('output_tokens', 0) >= c['generation']['max_new_tokens']) for c in calls),
            'visual_forward_calls': total('visual_forward_calls'),
            'runtime_seconds': call_seconds({str(i): c for i, c in enumerate(calls)}),
            'peak_reserved_bytes': max((c.get('peak_reserved_bytes') or 0 for c in calls), default=0) or None,
            'historical_missing_metrics_are_null': True}


def report(output):
    c = verify(output)
    if c['execution_mode'] == 'mock':
        paths = list(output.glob('V*/infer/*/COMPLETE'))
        write(output / 'results.json', {'execution_mode': 'mock', 'empirical': False, 'completed_cells': len(paths)})
        return
    original = unique(read(output / 'inputs.jsonl'))
    labels = unique(read(ROOT / 'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels) != c['labels_sha256']:
        raise ValueError('Evaluation labels changed')
    ids = sorted(p for p in original if labels[p]['split'] == 'main' and p != EXCLUDED)
    if len(ids) != 240:
        raise ValueError('Screen main denominator must be 240')
    images = {original[p]['image_sha256'] for p in ids}
    inventories = {r['image_sha256']: r for r in read(Path(c['inventory_path']))}
    ocr_seconds = sum(inventories[s]['runtime_ms'] for s in images) / 1000
    result = {'execution_mode': 'gpu', 'development_only': True, 'primary_pairs': 240,
              'semantic_items': 20, 'executed_pairs_per_cell': 288, 'solvers': {}, 'actor_attempt_costs': {},
              'timing': 'Cold recipe = unique main OCR + unique main source extraction + unique localization/repair + batch-apportioned final VLM. Excludes model load. Incremental wall is separate. Missing historical metrics are null, never zero.',
              'semantic_warnings': 'Heuristic only; translation can legitimately change lexical counts. Not validated semantic errors.'}
    def values(pred):
        if not set(ids) <= set(pred):
            raise ValueError('Incomplete predictions')
        if any(pred[p]['execution_mode'] != 'gpu' for p in ids):
            raise ValueError('Mock predictions in GPU report')
        return {p: int(pred[p]['status'] == 'success' and pred[p]['parsed_generated_label'] == labels[p]['gold_answer']) for p in ids}
    for actor in ('L', 'V8', 'V4'):
        result['actor_attempt_costs'][actor] = [load(p) for p in sorted((output / actor).glob('cost_*.json'))]
    for solver in ('8B', '4B'):
        actor = 'V' + solver[:-1]
        spec = c['solvers'][solver]
        baseline = read(Path(spec['baseline_predictions']))
        base_values = values(unique(baseline))
        op = [r for r in read(Path(spec['O_predictions'])) if r['condition'] == 'O']
        o_values = values(unique(op))
        cell_values, rewrites, summaries = {}, {}, {}
        for cell in ('L-D-S', *matrix.CELLS):
            editor = 'L' if cell.startswith('L') else actor
            rw_path = Path(spec['baseline_rewrite']) if cell == 'L-D-S' else output / editor / 'rewrite' / cell / 'rewritten.jsonl'
            pred_dir = output / actor / 'infer' / cell
            if cell != 'L-D-S' and not (pred_dir / 'COMPLETE').exists():
                continue
            predictions = baseline if cell == 'L-D-S' else read(pred_dir / 'predictions.jsonl')
            rewritten = unique(read(rw_path))
            if set(rewritten) != set(original) or len(predictions) != 288:
                raise ValueError('Incomplete cell')
            v = values(unique(predictions)); cell_values[cell] = v; rewrites[cell] = rewritten
            keyset = {digest(matrix.prompts.extraction_payload(original[p], stem_only=True)) for p in ids}
            extraction_path = Path(c['fixed_extraction']) if editor == 'L' else output / editor / 'extractions.jsonl'
            extracts = {r['source_key']: r for r in read(extraction_path)} if cell[2] == 'D' else {}
            extract_calls = call_map([extracts[k] for k in keyset]) if extracts else {}
            edit_calls = call_map([rewritten[p] for p in ids])
            answer = batch_share(predictions, lambda r: r['pair_id'] in ids)
            parts = {'ocr_seconds': ocr_seconds, 'extraction_seconds': call_seconds(extract_calls),
                     'localization_seconds': call_seconds(edit_calls), 'final_vlm_seconds': answer['seconds']}
            total = sum(parts.values())
            groups = {}
            for field in ('source_language', 'gui_language'):
                groups[field] = {lang: {'n': sum(original[p][field] == lang for p in ids),
                    'correct': sum(v[p] for p in ids if original[p][field] == lang)} for lang in ('en', 'zh', 'th', 'ru')}
            pair_groups = {}
            for p in ids:
                key = original[p]['source_language'] + '->' + original[p]['gui_language']
                g = pair_groups.setdefault(key, {'n': 0, 'correct': 0})
                g['n'] += 1; g['correct'] += v[p]
            errors = Counter()
            for p in ids:
                for call in rewritten[p]['attempts']:
                    errors.update(call.get('component_errors', {}).values())
                    errors.update(call.get('errors', []))
            summaries[cell] = {'correct': sum(v.values()), 'n': 240, 'accuracy': sum(v.values()) / 240,
                'vs_L_D_S': paired_bootstrap(v, base_values, labels, 20261115, 10000),
                'vs_O': paired_bootstrap(v, o_values, labels, 20261115, 10000),
                'recovery_vs_L_D_S': sum(v[p] and not base_values[p] for p in ids),
                'regression_vs_L_D_S': sum(base_values[p] and not v[p] for p in ids),
                'cold_recipe': {**parts, 'total_seconds': total, 'seconds_per_pair': total / 240},
                'editor_calls': call_stats(edit_calls), 'extraction_calls': call_stats(extract_calls) if extracts else None,
                'extraction_quality': source_quality(original, ids, extracts) if extracts else None,
                'status': dict(Counter(rewritten[p]['status'] for p in ids)),
                'component_status': dict(Counter(k + ':' + str(vv) for p in ids for k, vv in rewritten[p].get('component_status', {}).items())),
                'validation_errors_all_attempts': dict(errors),
                'matching_counts': {k: sum(rewritten[p].get('matching_counts', {}).get(k) or 0 for p in ids)
                                    for k in ('source_candidates', 'selected', 'null_abstentions', 'applied_edits')}
                                   if cell != 'L-D-S' else None,
                'matching_denominator_note': 'D supplied extraction spans; J proposed edits only. These are not independently verified matching precision or gold referent coverage. Historical L-D-S detailed counts remain in raw attempts.',
                'fallback_pair_rate': sum('fallback' in rewritten[p]['status'] for p in ids) / 240,
                'ambiguous_source_abstentions': sum(len(rewritten[p].get('ambiguous_source_abstentions', [])) for p in ids),
                'stem_changed_pairs': sum(rewritten[p]['question_stem'] != original[p]['question_stem'] for p in ids),
                'options_changed_pairs': sum(rewritten[p]['options'] != original[p]['options'] for p in ids),
                'semantic_warning_examples': [p for p in ids if rewritten[p].get('diagnostics', {}).get('relation_negation_heuristic_changes')][:15],
                'final_batch_allocation': answer, 'reused_final_rows': sum(r.get('cache_hit', False) for r in predictions if r['pair_id'] in ids),
                'language_groups': groups, 'language_pairs': pair_groups,
                'worst_pair_accuracy': min(g['correct'] / g['n'] for g in pair_groups.values())}
        contrasts, sh = {}, {}
        for left in cell_values:
            for right in cell_values:
                if left > right and sum(a != b for a, b in zip(left.split('-'), right.split('-'))) == 1:
                    contrasts[left + ' minus ' + right] = paired_bootstrap(cell_values[left], cell_values[right], labels, 20261115, 10000)
        for editor in ('L', 'V'):
            for form in ('D', 'J'):
                s, h = editor + '-' + form + '-S', editor + '-' + form + '-H'
                if s in rewrites and h in rewrites:
                    sh[editor + '-' + form] = {'same_stem': sum(rewrites[s][p]['question_stem'] == rewrites[h][p]['question_stem'] for p in ids), 'n': 240}
        result['solvers'][solver] = {'conditions': summaries, 'matched_axis_paired_contrasts': contrasts,
                                      'S_H_stem_agreement': sh, 'O_correct': sum(o_values.values())}
    write(output / 'results.json', result)
    lines = ['# PP-OCR 편집 matrix · Screen', '', '20 semantic item·240 mismatch pair. 조건마다 pilot 포함288행 실행. 개발용 탐색 결과이며 bootstrap은 semantic item 단위10,000회다.', '',
             '| Solver | 조건 | 정답 | 정확도 | OCR | 추출 | 정렬/통합 | 최종 VLM | 총 계산시간 | 초/pair |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for solver, s in result['solvers'].items():
        for cell, r in s['conditions'].items():
            t = r['cold_recipe']
            parts = [f'{t[k]/60:.2f}분' for k in ('ocr_seconds', 'extraction_seconds', 'localization_seconds', 'final_vlm_seconds', 'total_seconds')]
            lines.append(f'| {solver} | {cell} | {r["correct"]}/240 | {r["accuracy"]:.2%} | ' + ' | '.join(parts) + f' | {t["seconds_per_pair"]:.3f} |')
    lines += ['', 'L-D-S는 기존 결과다. OCR와 고정 LM 추출은 독립 recipe 비용에 포함하지만 이번에 재실행하지 않는다. 총 계산시간은 모델 적재를 제외한다. 실제 신규 실행·적재·캐시 비용은 results.json의 actor_attempt_costs와 각 actor의 cost 파일에 따로 기록한다.', '',
              '미완료 조건은 표에 표시하지 않는다. Prefill/decode는 editor forward의 GPU 시간이며 생성 전체 wall과 다르다. 기존 기록에 없는 세부 시간은 null이다. 구조 성공이나 heuristic 경고를 의미 보존/손상의 확정 판정으로 취급하지 않는다.', '',
              'CI·회복/회귀·언어별 결과·추출 F1·검증 오류·repair/cap hit·fallback·S/H stem 일치율·토큰은 results.json에 저장한다. 모든 대비는 탐색적이며 다중 비교를 보정한 확증 검정으로 보고하지 않는다.']
    (output / 'REPORT_KO.md').write_text('\n'.join(lines) + '\n')
    print('REPORT', output / 'REPORT_KO.md', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DEFAULT)
    report(parser.parse_args().output_dir.resolve())
