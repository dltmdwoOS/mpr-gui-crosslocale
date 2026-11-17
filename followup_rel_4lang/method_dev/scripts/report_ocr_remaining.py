"""Report completed OCR cohorts only, with paired scores and matched time denominators."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / '01_code/src'), str(REPO), str(Path(__file__).parent)]
from run_ocr_remaining import verify, DEFAULT_OUTPUT, SCREEN, E1, COHORTS
from run_stem_only_gui import read, write, unique
from run_stem_refinement_2x2 import latest
from compare_end_to_end import batch_share, call_map, call_seconds
from search_pipeline import EXCLUDED, paired_bootstrap
from mpr_crosslocale.methods.selective_alignment.schemas import digest, fields
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits
from mpr_crosslocale.inference.answer_parser import parse_label
from followup_rel_4lang.method_dev.two_stage_v2 import prompts


def ocr_seconds(records):
    calls = {}
    for r in records:
        key = r['cache_key']
        if key in calls and r['runtime_ms'] != calls[key]['runtime_ms']:
            raise ValueError('Conflicting OCR cached runtime')
        calls[key] = r
    return sum(r['runtime_ms'] for r in calls.values()) / 1000


def report(output):
    c = verify(output)
    if c['execution_mode'] == 'mock':
        completed = [cohort for cohort in COHORTS if (output / cohort / 'COMPLETE.json').exists()]
        write(output / 'results.json', {'execution_mode': 'mock', 'empirical': False,
                                       'completed_cohorts': completed, 'performance_not_scored': True})
        print('MOCK report:', completed, 'no empirical performance', flush=True)
        return
    labels_path = ROOT / 'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'
    labels = unique(read(labels_path))
    if digest(labels) != c['labels_sha256']:
        raise ValueError('Labels changed')
    e1_contract = json.loads((E1 / 'contract.json').read_text())
    values, stages, quality, costs, captures = {}, {}, {}, {}, {}
    def rows(path):
        path = Path(path)
        captures[str(path.resolve().relative_to(REPO))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return read(path)
    captures[str(labels_path.relative_to(REPO))] = hashlib.sha256(labels_path.read_bytes()).hexdigest()
    captures[str(Path(__file__).relative_to(REPO))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    complete = ['screen'] + [cohort for cohort in COHORTS if (output / cohort / 'COMPLETE.json').exists()]
    for cohort in complete:
        work = SCREEN if cohort == 'screen' else output / cohort
        cc = json.loads((work / 'contract.json').read_text())
        done = json.loads((work / 'COMPLETE.json').read_text())
        if done['contract_sha256'] != digest(cc) or cc['execution_mode'] != 'gpu':
            raise ValueError('Incomplete real cohort')
        original = unique(rows(work / 'inputs.jsonl'))
        ids = sorted(p for p in original if labels[p]['split'] == 'main' and p != EXCLUDED)
        if len(ids) != {'screen': 240, 'selection': 239, 'internal_evaluation': 1416}[cohort]:
            raise ValueError('Cohort denominator changed')
        pp = rows(latest(work, 'infer') / 'evaluation/predictions.jsonl')
        pred = unique(pp)
        rr = unique(rows(latest(work, 'rewrite') / 'rewritten.jsonl'))
        old = unique(rows(cc['baseline_predictions']))
        opath = e1_contract['descriptors'][cohort]['O_pred']
        original_predictions = unique([r for r in rows(opath) if r['condition'] == 'O'])
        if set(rr) != set(original) or set(pred) != set(original):
            raise ValueError('Incomplete paired artifacts')
        for p in ids:
            if rr[p]['options'] != original[p]['options'] or apply_edits(original[p], rr[p]['edits']) != fields(rr[p]):
                raise ValueError('Selective manipulation changed context/options')
            for key in ('parallel_id', 'image_sha256', 'source_language', 'gui_language', 'option_order'):
                if rr[p][key] != original[p][key]:
                    raise ValueError('Pair identity mismatch')
            for record in (pred[p], old[p], original_predictions[p]):
                if record['execution_mode'] != 'gpu' or parse_label(record['generated_text']) != record['parsed_generated_label']:
                    raise ValueError('Invalid GPU/parser provenance')
        values[cohort] = {name: {p: int(group[p]['status'] == 'success' and group[p]['parsed_generated_label'] == labels[p]['gold_answer']) for p in ids}
                          for name, group in [('O', original_predictions), ('VLM_E1_M0', old), ('OCR_E1_M0', pred)]}
        inv = {r['image_sha256']: r for r in rows(latest(work, 'ocr') / 'inventories.jsonl')}
        old_inv = {r['image_sha256']: r for r in rows(cc['baseline_inventory'])}
        ex = {r['source_key']: r for r in rows(cc['extraction_path'])}
        old_dir = latest(ROOT / 'artifacts/stem_refinement_2x2_screen_v1/E1_M0', 'rewrite') if cohort == 'screen' else Path(cc['baseline_rewrite']).parent
        old_rw = unique(rows(old_dir / 'rewritten.jsonl'))
        images = sorted({original[p]['image_sha256'] for p in ids})
        sources = sorted({digest(prompts.extraction_payload(original[p], stem_only=True)) for p in ids})
        stages[cohort] = {'ocr': [inv[s] for s in images], 'vlm_inventory': [old_inv[s] for s in images],
                          'extraction': [ex[k] for k in sources], 'ocr_match': [rr[p] for p in ids],
                          'vlm_match': [old_rw[p] for p in ids]}
        costs[cohort] = {'n': len(ids), 'ocr_inventory_seconds': ocr_seconds(stages[cohort]['ocr']),
                         'vlm_inventory_seconds': call_seconds(call_map(stages[cohort]['vlm_inventory'])),
                         'extraction_seconds': call_seconds(call_map(stages[cohort]['extraction'])),
                         'ocr_matching_seconds': call_seconds(call_map(stages[cohort]['ocr_match'])),
                         'vlm_matching_seconds': call_seconds(call_map(stages[cohort]['vlm_match'])),
                         'ocr_answer_seconds': batch_share(pp, lambda r: r['pair_id'] in ids)['seconds'],
                         'vlm_answer_seconds': batch_share(list(old.values()), lambda r: r['pair_id'] in ids)['seconds']}
        shared = [p for p in ids if rr[p]['modified_question'] == old_rw[p]['modified_question']]
        quality[cohort] = {'ocr_status': dict(Counter(inv[s]['status'] for s in images)),
                           'rewrite_status': dict(Counter(rr[p]['status'] for p in ids)),
                           'changed_pairs': sum(fields(rr[p]) != fields(original[p]) for p in ids),
                           'invalid_labels': sum(pred[p]['parsed_generated_label'] not in ('A', 'B', 'C', 'D') for p in ids),
                           'same_MCQs': len(shared), 'same_MCQs_label_differences': sum(pred[p]['parsed_generated_label'] != old[p]['parsed_generated_label'] for p in shared),
                           'inventory_images': len(images), 'source_MCQs': len(sources),
                           'infer_cost': json.loads((latest(work, 'infer') / 'evaluation/cost.json').read_text())}
    pooled = 'all_158' if len(complete) == 3 else 'completed_cohorts_only'
    values[pooled] = {name: {p: v for cohort in complete for p, v in values[cohort][name].items()}
                      for name in ('O', 'VLM_E1_M0', 'OCR_E1_M0')}
    joined = defaultdict(list)
    for stage in stages.values():
        for name, records in stage.items():
            joined[name].extend(records)
    costs[pooled] = {'n': len(values[pooled]['O']), 'ocr_inventory_seconds': ocr_seconds(joined['ocr']),
                     'vlm_inventory_seconds': call_seconds(call_map(joined['vlm_inventory'])),
                     'extraction_seconds': call_seconds(call_map(joined['extraction'])),
                     'ocr_matching_seconds': call_seconds(call_map(joined['ocr_match'])),
                     'vlm_matching_seconds': call_seconds(call_map(joined['vlm_match'])),
                     'ocr_answer_seconds': sum(costs[c]['ocr_answer_seconds'] for c in complete),
                     'vlm_answer_seconds': sum(costs[c]['vlm_answer_seconds'] for c in complete)}
    summary = {}
    for cohort, groups in values.items():
        ids = sorted(groups['O'])
        summary[cohort] = {'n': len(ids), 'items': len({labels[p]['parallel_id'] for p in ids}),
                           'correct': {name: sum(v.values()) for name, v in groups.items()},
                           'OCR_minus_VLM': paired_bootstrap(groups['OCR_E1_M0'], groups['VLM_E1_M0'], labels, 20261115, 10000),
                           'OCR_minus_O': paired_bootstrap(groups['OCR_E1_M0'], groups['O'], labels, 20261115, 10000),
                           'by_gui': {g: {'n': sum(p.endswith('::' + g) for p in ids),
                                          'correct': {k: sum(v[p] for p in ids if p.endswith('::' + g)) for k, v in groups.items()}} for g in ('en', 'zh', 'th', 'ru')}}
        cost = costs[cohort]
        for method in ('ocr', 'vlm'):
            cost[method + '_total_seconds'] = cost[method + '_inventory_seconds'] + cost['extraction_seconds'] + cost[method + '_matching_seconds'] + cost[method + '_answer_seconds']
    if pooled == 'all_158' and summary[pooled]['n'] != 1895:
        raise ValueError('Full denominator differs')
    result = {'development_only': True, 'execution_mode': 'gpu', 'completed_cohorts': complete,
              'pending_cohorts': [c for c in COHORTS if c not in complete], 'summary': summary, 'costs': costs,
              'quality': quality, 'contract_sha256': digest(c), 'source_and_raw_sha256': captures,
              'cost_scope': 'Primary pairs; shared preprocessing cache keys counted once, including original cached runtimes. '
                            'CPU OCR + GPU calls; model loads/startup excluded, batch runtime allocated by primary-row fraction.'}
    write(output / 'results.json', result)
    write(ROOT / 'artifacts/ocr_inventory_full_dev_results_snapshot.json', result)
    lines = ['# EasyOCR inventory: 전체 개발 집합 비교', '',
             'Screen의 OCR/E1/M0를 고정하고 Selection → Internal 순으로 확장했다. Screen은 기존 결과를 재사용했다. '
             'OCR CPU3, 기존 E1 source 추출 재사용, 기존 Qwen3-8B M0, Qwen3-VL-8B BF16·SDPA·2MP·batch3·label-only2tokens다.', '',
             '완료: ' + ', '.join(complete) + '. 미완료: ' + (', '.join(result['pending_cohorts']) or '없음') + '.', '',
             '| 범위 | item | pair | O | VLM inventory E1/M0 | OCR inventory E1/M0 | OCR−VLM | 95% item CI | 회복/회귀 |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |']
    for cohort, s in summary.items():
        d = s['OCR_minus_VLM']
        cells = [f"{s['correct'][name]}/{s['n']} ({s['correct'][name]/s['n']:.2%})" for name in ('O', 'VLM_E1_M0', 'OCR_E1_M0')]
        lines.append(f"| {cohort} | {s['items']} | {s['n']} | " + ' | '.join(cells) + f" | {d['difference']*100:+.2f}pp | [{d['ci95'][0]*100:+.2f}, {d['ci95'][1]*100:+.2f}]pp | {d['recovery']}/{d['regression']} |")
    lines += ['', '미완료 cohort의 부분 출력은 정확도로 집계하지 않는다. Main1,895pair는158item×12방향에서 기존 사전 제외1pair를 뺀 값이다. '
              '실행에는 Selection의 제외1pair와 Screen pilot48pair가 남아 있지만 주 정확도·시간에서 제외했다. '
              '실패·빈 OCR·fallback·미파싱 답은 분모에 포함한다. CI는 item bootstrap10,000회이며 이미 관찰한 개발 집합의 탐색 결과다.', '',
              '| 범위 | 방법 | Inventory | E1 추출+M0 | 최종 풀이 | 총 계산 시간 | 초/pair |',
              '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for cohort, cost in costs.items():
        for m, label in [('vlm', 'VLM inventory'), ('ocr', 'CPU EasyOCR inventory')]:
            lines.append(f"| {cohort} | {label} | {cost[m+'_inventory_seconds']/60:.2f}분 | {(cost['extraction_seconds']+cost[m+'_matching_seconds'])/60:.2f}분 | {cost[m+'_answer_seconds']/60:.2f}분 | {cost[m+'_total_seconds']/60:.2f}분 | {cost[m+'_total_seconds']/cost['n']:.3f} |")
    lines += ['', result['cost_scope'], '',
              'CPU와 GPU 호출 시간을 순차 합산한 상각 처리량이며 단일 요청 latency/전체 wall time과 다르다. '
              '전역 중복 제거로 pooled 비용은 cohort별 단순 합과 소폭 다를 수 있다. 실제 추가 wall·cache 재사용은 각 stage cost.json에 있다.', '',
              '## GUI 언어별', '', '| 범위 | GUI | pair | O | VLM inventory | OCR inventory |',
              '| --- | --- | ---: | ---: | ---: | ---: |']
    for cohort, s in summary.items():
        for g, v in s['by_gui'].items():
            lines.append(f"| {cohort} | {g.upper()} | {v['n']} | " + ' | '.join(f"{v['correct'][name]/v['n']:.2%}" for name in ('O', 'VLM_E1_M0', 'OCR_E1_M0')) + ' |')
    lines += ['', '## 실패·재사용 진단', '', '```json', json.dumps(quality, ensure_ascii=False, indent=2), '```', '',
              '기존 VLM inventory나 parallel R은 OCR 전사의 GT가 아니다. OCR 문자 인식 정확도는 이 REL 결과만으로 판정하지 않는다. '
              '최종 예측 재사용은 순서가 같은 완성 batch의 prompt·이미지·모델·seed·환경이 일치할 때만 허용한다.', '',
              '[고정 확장 프로토콜](OCR_INVENTORY_FULL_DEV_PROTOCOL_KO.md) · '
              '[전체 결과 snapshot](../artifacts/ocr_inventory_full_dev_results_snapshot.json).', '']
    (output / 'REPORT_KO.md').write_text('\n'.join(lines))
    (ROOT / 'reports/OCR_INVENTORY_FULL_DEV_RESULTS_KO.md').write_text('\n'.join(lines))
    print('REPORTED OCR completed cohorts:', complete, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT)
    report(p.parse_args().output_dir.resolve())
