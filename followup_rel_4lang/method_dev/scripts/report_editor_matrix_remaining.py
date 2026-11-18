"""Summarize completed paired V-D cohorts and pool their main items."""
import argparse
from collections import Counter
from pathlib import Path

from run_editor_matrix_remaining import (
    DEFAULT, LABELS, COHORTS, SOLVERS, CELLS, actor, primary_ids, source_key, load,
)
from run_stem_only_gui import read, unique, write
from compare_end_to_end import batch_share, call_map
from report_editor_matrix import call_stats, source_quality
from search_pipeline import paired_bootstrap
from mpr_crosslocale.inference.answer_parser import parse_label
from mpr_crosslocale.methods.selective_alignment.schemas import digest


def cohort_data(output, contract, cohort, solver, labels):
    spec = contract['cohorts'][cohort]
    model = spec['solvers'][solver]
    folder = (Path(contract['screen_run']) if cohort == 'screen' else output / cohort) / actor(solver)
    originals = unique(read(Path(spec['inputs_path'])))
    ids = primary_ids(originals.values(), labels)
    primary = set(ids)
    inventory = {r['image_sha256']: r for r in read(Path(spec['inventory_path']))}
    extracts = {r['source_key']: r for r in read(folder / 'extractions.jsonl')}
    fixed = {r['source_key']: r for r in read(Path(spec['fixed_extraction']))}
    options = {}
    orig_pred = [r for r in read(Path(model['O_predictions'])) if r['condition'] == 'O']
    for cell in ('O', 'L-D-S', *CELLS):
        if cell == 'O':
            pred, rewrites, extracted = orig_pred, {}, {}
        elif cell == 'L-D-S':
            pred = read(Path(model['baseline_predictions']))
            rewrites = unique(read(Path(model['baseline_rewrite'])))
            extracted = fixed
        else:
            pred = read(folder / 'infer' / cell / 'predictions.jsonl')
            rewrites = unique(read(folder / 'rewrite' / cell / 'rewritten.jsonl'))
            extracted = extracts
            if any(r['extracted_referents'] != extracted[source_key(originals[p])]['referents']
                   for p, r in rewrites.items()):
                raise ValueError('V-D-S and V-D-H must share source extraction')
        by_pair = unique(pred)
        if by_pair.keys() != originals.keys() or (rewrites and rewrites.keys() != originals.keys()):
            raise ValueError('Incomplete paired cohort')
        if any(r['execution_mode'] != 'gpu' or parse_label(r['generated_text']) != r['parsed_generated_label']
               or r['parallel_id'] != originals[p]['parallel_id'] for p, r in by_pair.items()):
            raise ValueError('Invalid paired prediction')
        keys = {source_key(originals[p]) for p in ids}
        options[cell] = {
            'correct': {p: int(by_pair[p]['status'] == 'success' and by_pair[p]['parsed_generated_label'] ==
                               labels[p]['gold_answer']) for p in ids},
            'extractions': {k: extracted[k] for k in keys} if extracted else {},
            'rewrites': {p: rewrites[p] for p in ids} if rewrites else {},
            'final_vlm_seconds': batch_share(pred, lambda r: r['pair_id'] in primary)['seconds'],
            'reused_final_rows': sum(by_pair[p].get('cache_hit', False) for p in ids),
            'unparsed': sum(by_pair[p]['parsed_generated_label'] is None for p in ids),
        }
    return originals, {originals[p]['image_sha256']: inventory[originals[p]['image_sha256']] for p in ids}, options


def aggregate(groups, labels):
    originals = {p: r for orig, _, _ in groups for p, r in orig.items()}
    inventories = {sha: r for _, inv, _ in reversed(groups) for sha, r in inv.items()}
    ocr = sum(r['runtime_ms'] for r in inventories.values()) / 1000
    values = {cell: {p: v for _, _, options in groups for p, v in options[cell]['correct'].items()}
              for cell in ('O', 'L-D-S', *CELLS)}
    ids = sorted(values['O'])
    stats = {}
    for cell, correct in values.items():
        members = [options[cell] for _, _, options in groups]
        rewrites = {p: r for m in members for p, r in m['rewrites'].items()}
        extraction = {k: r for m in reversed(members) for k, r in m['extractions'].items()}
        ext_stats = call_stats(call_map(r for m in members for r in m['extractions'].values()))
        edit_stats = call_stats(call_map(rewrites.values()))
        final = sum(m['final_vlm_seconds'] for m in members)
        total = (ocr if cell != 'O' else 0) + ext_stats['runtime_seconds'] + edit_stats['runtime_seconds'] + final
        languages = {}
        for field in ('source_language', 'gui_language', 'language_pair'):
            by_language = {}
            for p in ids:
                r = originals[p]
                lang = r[field] if field != 'language_pair' else r['source_language'] + '→' + r['gui_language']
                record = by_language.setdefault(lang, {'n': 0, 'correct': 0})
                record['n'] += 1
                record['correct'] += correct[p]
            languages[field] = by_language
        stats[cell] = {
            'n': len(ids), 'correct': sum(correct.values()), 'accuracy': sum(correct.values()) / len(ids),
            'language_groups': languages,
            'cold_recipe': {'ocr_seconds': ocr if cell != 'O' else 0, 'extraction_seconds': ext_stats['runtime_seconds'],
                            'localization_seconds': edit_stats['runtime_seconds'], 'final_vlm_seconds': final,
                            'total_seconds': total, 'seconds_per_pair': total / len(ids)},
            'extraction_calls': ext_stats, 'editor_calls': edit_stats,
            'reused_final_rows': sum(m['reused_final_rows'] for m in members), 'unparsed': sum(m['unparsed'] for m in members),
            'extraction_quality': source_quality(originals, ids, extraction) if extraction else None,
            'rewrite_status': dict(Counter(r['status'] for r in rewrites.values())),
            'component_status': dict(Counter(f'{k}:{v}' for r in rewrites.values() for k, v in r.get('component_status', {}).items())),
            'stem_changed_pairs': sum(r['question_stem'] != originals[p]['question_stem'] for p, r in rewrites.items()),
            'options_changed_pairs': sum(r['options'] != originals[p]['options'] for p, r in rewrites.items()),
            'semantic_warning_pairs': sum(bool(r.get('diagnostics', {}).get('relation_negation_heuristic_changes'))
                                          for r in rewrites.values()) if cell in CELLS else None,
            'vs_O': paired_bootstrap(correct, values['O'], labels, 20261115, 10000) if cell != 'O' else None,
            'vs_L_D_S': paired_bootstrap(correct, values['L-D-S'], labels, 20261115, 10000) if cell in CELLS else None,
        }
    stem_s = {p: r['question_stem'] for _, _, options in groups for p, r in options['V-D-S']['rewrites'].items()}
    stem_h = {p: r['question_stem'] for _, _, options in groups for p, r in options['V-D-H']['rewrites'].items()}
    return {'conditions': stats, 'V-D-H_minus_V-D-S': paired_bootstrap(values['V-D-H'], values['V-D-S'], labels, 20261115, 10000),
            'S_H_same_stem': sum(stem_s[p] == stem_h[p] for p in ids), 'primary_pairs': len(ids)}


def report(output):
    contract = load(output / 'contract.json')
    complete = ['screen'] + [c for c in COHORTS if all((output / c / actor(s) / 'COMPLETE').is_file() for s in SOLVERS)]
    if contract['execution_mode'] == 'mock':
        write(output / 'results.json', {'empirical': False, 'completed_new_cohorts': complete[1:]})
        return
    labels = unique(read(LABELS))
    if digest(labels) != contract['labels_sha256']:
        raise ValueError('Evaluation label digest differs')
    stats = {}
    attempts = {}
    for solver in SOLVERS:
        groups = {c: cohort_data(output, contract, c, solver, labels) for c in complete}
        stats[solver] = {c: aggregate([group], labels) for c, group in groups.items()}
        stats[solver]['pooled_completed'] = aggregate(list(groups.values()), labels)
        attempts[solver] = {c: [load(p) for p in sorted((output / c / actor(solver)).glob('cost_*.json'))] for c in COHORTS}
    write(output / 'results.json', {'empirical': True, 'development_only': True, 'completed_cohorts': complete,
                                     'solvers': stats, 'actor_attempt_costs': attempts})
    lines = ['# PP-OCR V-D-S / V-D-H 전체 개발 평가', '',
             '완료 집합은 ' + ', '.join(complete) + '이다. 모든 조건이 완료된 집합만 합산했다. 시간은 OCR, 추출, 편집 및 repair, 최종 풀이의 합이며 모델 적재는 별도로 기록했다.', '',
             '| 집합 | Solver | 조건 | 정답 | 정확도 | 초/pair |', '| --- | --- | --- | ---: | ---: | ---: |']
    for solver, datasets in stats.items():
        for cohort, data in datasets.items():
            for cell, row in data['conditions'].items():
                lines.append(f'| {cohort} | {solver} | {cell} | {row["correct"]}/{row["n"]} | {row["accuracy"]:.2%} | {row["cold_recipe"]["seconds_per_pair"]:.3f} |')
    lines += ['', '언어별 결과, 회복·회귀, semantic item bootstrap CI, 단계별 시간·토큰·repair·fallback, S/H 간 stem 일치 수는 results.json에 기록했다.']
    (output / 'REPORT_KO.md').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, default=DEFAULT)
    report(p.parse_args().output_dir)
