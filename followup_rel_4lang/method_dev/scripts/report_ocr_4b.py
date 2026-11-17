"""Completed-cohort 4B OCR report; common preprocessing is shared with 8B."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / '01_code/src'), str(REPO), str(Path(__file__).parent)]
from run_ocr_4b import verify, DEFAULT_OUTPUT, COHORTS, CONDITION, bind_preprocessing
from run_stem_only_gui import read, write, unique
from run_stem_refinement_2x2 import latest
from compare_end_to_end import batch_share, call_map, call_seconds
from report_ocr_remaining import ocr_seconds
from search_pipeline import EXCLUDED, paired_bootstrap
from mpr_crosslocale.methods.selective_alignment.schemas import digest
from mpr_crosslocale.inference.answer_parser import parse_label
from followup_rel_4lang.method_dev.two_stage_v2 import prompts


def report(output):
    c = verify(output)
    completed = []
    for cohort in COHORTS:
        try:
            latest(output / cohort, 'infer')
            completed.append(cohort)
        except ValueError:
            pass
    if c['execution_mode'] == 'mock':
        write(output / 'results.json', {'execution_mode': 'mock', 'empirical': False, 'completed_cohorts': completed})
        print('MOCK 4B report:', completed, 'no empirical accuracy', flush=True)
        return
    if not completed:
        print('No completed 4B cohort; no partial accuracy reported.', flush=True)
        return
    labels = unique(read(ROOT / 'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels) != c['labels_sha256']:
        raise ValueError('Labels changed')
    old4 = json.loads((ROOT / 'artifacts/transfer_qwen3_vl_4b_results_snapshot.json').read_text())
    values, costs, quality, preprocessing, captures = {}, {}, {}, {}, {}
    def rows(path):
        path = Path(path)
        captures[str(path.resolve().relative_to(REPO))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return read(path)
    for cohort in completed:
        work = output / cohort
        attempt = latest(work, 'infer')
        rewrite_dir, binding = bind_preprocessing(c, cohort)
        saved_binding = json.loads((attempt / 'preprocessing_binding.json').read_text())
        if saved_binding != binding:
            raise ValueError('Shared OCR-localized input changed after inference')
        source8 = Path(c['descriptors'][cohort]['source8'])
        original = unique(rows(work / 'inputs.jsonl'))
        ids = sorted(p for p in original if labels[p]['split'] == 'main' and p != EXCLUDED)
        if len(ids) != c['descriptors'][cohort]['primary_pairs']:
            raise ValueError('4B primary denominator changed')
        pp = rows(attempt / 'evaluation/predictions.jsonl')
        pred = unique(pp)
        prior = {name: unique(rows(c['descriptors'][cohort][key])) for name, key in
                 [('O_4B', 'O_predictions'), ('VLM_INV_4B', 'VLM_E1_M0_predictions')]}
        prior['OCR_8B'] = unique(rows(latest(source8, 'infer') / 'evaluation/predictions.jsonl'))
        prior['OCR_4B'] = pred
        if set(pred) != set(original) or any(pred[p]['condition'] != CONDITION for p in ids):
            raise ValueError('Incomplete/wrong 4B condition')
        for group in prior.values():
            if set(group) != set(original):
                raise ValueError('Comparison pair coverage mismatch')
            if any(group[p]['execution_mode'] != 'gpu' or parse_label(group[p]['generated_text']) != group[p]['parsed_generated_label'] for p in ids):
                raise ValueError('Invalid GPU/parser provenance')
        values[cohort] = {name: {p: int(group[p]['status'] == 'success' and group[p]['parsed_generated_label'] == labels[p]['gold_answer']) for p in ids}
                          for name, group in prior.items()}
        cc = json.loads((source8 / 'contract.json').read_text())
        inv = {r['image_sha256']: r for r in rows(latest(source8, 'ocr') / 'inventories.jsonl')}
        ext = {r['source_key']: r for r in rows(cc['extraction_path'])}
        rw = unique(rows(rewrite_dir / 'rewritten.jsonl'))
        preprocessing[cohort] = {'ocr': [inv[s] for s in sorted({original[p]['image_sha256'] for p in ids})],
                                 'extract': [ext[k] for k in sorted({digest(prompts.extraction_payload(original[p], stem_only=True)) for p in ids})],
                                 'match': [rw[p] for p in ids]}
        costs[cohort] = {'n': len(ids), 'answer_4b_seconds': batch_share(pp, lambda r: r['pair_id'] in ids)['seconds'],
                         'new_answer_4b_seconds': batch_share([{**r, 'batch_runtime_ms': r['new_batch_runtime_ms']} for r in pp], lambda r: r['pair_id'] in ids)['seconds'],
                         'answer_8b_seconds': batch_share(list(prior['OCR_8B'].values()), lambda r: r['pair_id'] in ids)['seconds'],
                         'old_vlm_inventory_4b_recipe_seconds': old4['costs'][cohort]['primary_logical_recipe']['total_seconds']}
        quality[cohort] = {'infer_cost': json.loads((attempt / 'evaluation/cost.json').read_text()),
                           'invalid_labels': sum(pred[p]['parsed_generated_label'] not in ('A', 'B', 'C', 'D') for p in ids),
                           'preprocessing_binding': binding, 'identical_localized_MCQs_8b_4b': len(ids)}
        if sum(values[cohort]['O_4B'].values()) != old4['summary'][cohort]['correct']['O']:
            raise ValueError('Historical 4B O score changed')
    pooled = 'all_158' if len(completed) == 3 else 'completed_cohorts_only'
    names = ('O_4B', 'VLM_INV_4B', 'OCR_4B', 'OCR_8B')
    values[pooled] = {name: {p: v for cohort in completed for p, v in values[cohort][name].items()} for name in names}
    preprocessing[pooled] = {stage: [record for cohort in completed for record in preprocessing[cohort][stage]]
                             for stage in ('ocr', 'extract', 'match')}
    costs[pooled] = {'n': len(values[pooled]['O_4B']),
                     **{key: sum(costs[x][key] for x in completed) for key in
                        ('answer_4b_seconds', 'new_answer_4b_seconds', 'answer_8b_seconds', 'old_vlm_inventory_4b_recipe_seconds')}}
    summary = {}
    for cohort, groups in values.items():
        ids = sorted(groups['O_4B'])
        cost = costs[cohort]
        stage = preprocessing[cohort]
        cost['shared_ocr_seconds'] = ocr_seconds(stage['ocr'])
        cost['shared_LM_seconds'] = call_seconds(call_map(stage['extract'])) + call_seconds(call_map(stage['match']))
        cost['shared_preprocessing_seconds'] = cost['shared_ocr_seconds'] + cost['shared_LM_seconds']
        cost['standalone_4b_recipe_seconds'] = cost['shared_preprocessing_seconds'] + cost['answer_4b_seconds']
        cost['joint_8b_4b_recipe_seconds'] = cost['shared_preprocessing_seconds'] + cost['answer_4b_seconds'] + cost['answer_8b_seconds']
        summary[cohort] = {'n': len(ids), 'items': len({labels[p]['parallel_id'] for p in ids}),
                           'correct': {k: sum(v.values()) for k, v in groups.items()},
                           'contrasts': {ref: paired_bootstrap(groups['OCR_4B'], groups[ref], labels, 20261115, 10000)
                                         for ref in ('O_4B', 'VLM_INV_4B', 'OCR_8B')},
                           'by_gui': {g: {'n': sum(p.endswith('::' + g) for p in ids),
                                          'correct': {k: sum(v[p] for p in ids if p.endswith('::' + g)) for k, v in groups.items()}} for g in ('en', 'zh', 'th', 'ru')}}
    if pooled == 'all_158' and summary[pooled]['n'] != 1895:
        raise ValueError('Full primary denominator differs')
    result = {'development_only': True, 'completed_cohorts': completed,
              'pending_cohorts': [x for x in COHORTS if x not in completed], 'summary': summary, 'costs': costs,
              'quality': quality, 'shared_preprocessing_with_8b': True, 'contract_sha256': digest(c),
              'source_and_raw_sha256': captures}
    write(output / 'results.json', result)
    write(ROOT / 'artifacts/ocr_qwen3_vl_4b_results_snapshot.json', result)
    lines = ['# 동일 OCR 질문의 Qwen3-VL-4B 평가', '',
             'OCR·고정 Qwen3-8B LM의 E1/M0 전처리는8B와 정확히 공유했다. 새로 실행한 것은4B 최종 풀이이며, 8B 예측을4B에 복사하지 않았다. '
             '4B O와 기존4B VLM-inventory 방법은 동일 데이터·run profile의 완료 예측을 재사용한다.', '',
             '완료: '+', '.join(completed)+'. 미완료: '+(', '.join(result['pending_cohorts']) or '없음')+'.', '',
             '| 범위 | item | pair | 4B O | 4B VLM inventory | 4B OCR | 8B OCR · 동일 MCQ |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for cohort, s in summary.items():
        cells = [f"{s['correct'][name]}/{s['n']} ({s['correct'][name]/s['n']:.2%})" for name in names]
        lines.append(f"| {cohort} | {s['items']} | {s['n']} | "+' | '.join(cells)+' |')
    lines += ['', '| 범위 | 4B OCR − 기준 | 차이 | 95% item CI | 회복/회귀 |', '| --- | --- | ---: | --- | ---: |']
    for cohort, s in summary.items():
        for ref, d in s['contrasts'].items():
            lines.append(f"| {cohort} | {ref} | {100*d['difference']:+.2f}pp | [{100*d['ci95'][0]:+.2f}, {100*d['ci95'][1]:+.2f}]pp | {d['recovery']}/{d['regression']} |")
    lines += ['', '주 분석은main158문항·1,895pair다. Screen pilot48pair와 사전 제외1pair는 실행 queue에 남기고 정확도·비용에서 제외한다. '
              '실패·미파싱 답은 분모에 포함한다. Item bootstrap10,000회이며 반복 관찰한 개발 집합의 탐색 결과다.', '',
              '| 범위 | 공통 OCR+LM | 4B 풀이 | 4B 단독 recipe | 초/pair | 이번 신규4B 풀이 | 8B+4B 공동 recipe |',
              '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for cohort, v in costs.items():
        lines.append(f"| {cohort} | {v['shared_preprocessing_seconds']/60:.2f}분 | {v['answer_4b_seconds']/60:.2f}분 | {v['standalone_4b_recipe_seconds']/60:.2f}분 | {v['standalone_4b_recipe_seconds']/v['n']:.3f} | {v['new_answer_4b_seconds']/60:.2f}분 | {v['joint_8b_4b_recipe_seconds']/60:.2f}분 |")
    lines += ['', '단독 recipe에는 공통 전처리도 최초 호출 시간으로 청구한다. 실제 추가4B 비용은 새로 계산한 풀이만이며 공동 recipe는 공통 전처리를 한 번만 더한다. '
              '모델 적재·기동·일부CPU처리를 제외한 호출 시간이며 전체 wall time과 다르다. 완성 batch의 시간만 primary 행 비율로 배분한다.', '',
              '이전4B VLM-inventory 방법은4B가 inventory를 추출한 결과이고 현재는OCR다. 현재4B/8B OCR는 동일 MCQ를 사용하므로 이 두 모델 간 비교는 최종 solver checkpoint의 차이다.', '',
              '## GUI별', '', '| 범위 | GUI | pair | 4B O | 4B VLM inventory | 4B OCR | 8B OCR |',
              '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for cohort, s in summary.items():
        for g, v in s['by_gui'].items():
            lines.append(f"| {cohort} | {g.upper()} | {v['n']} | "+' | '.join(f"{v['correct'][name]/v['n']:.2%}" for name in names)+' |')
    lines += ['', '[연속 실행 프로토콜](OCR_8B_4B_CHAIN_PROTOCOL_KO.md) · '
              '[전체 snapshot](../artifacts/ocr_qwen3_vl_4b_results_snapshot.json).', '']
    (output / 'REPORT_KO.md').write_text('\n'.join(lines))
    (ROOT / 'reports/OCR_QWEN3_VL_4B_RESULTS_KO.md').write_text('\n'.join(lines))
    print('REPORTED 4B OCR:', completed, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT)
    report(p.parse_args().output_dir.resolve())
