"""Read-only paired Screen accuracy and full recipe cost for the GPU OCR comparison."""
import argparse
from collections import Counter
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / '01_code/src'), str(REPO), str(Path(__file__).parent)]
from run_gpu_ocr_screen import verify, load, BACKENDS, SOLVERS, DEFAULT_OUTPUT, CPU, latest
from run_stem_only_gui import read, write, unique
from compare_end_to_end import call_map, call_seconds, batch_share
from search_pipeline import EXCLUDED, paired_bootstrap
from mpr_crosslocale.methods.selective_alignment.schemas import digest, fields
from mpr_crosslocale.inference.answer_parser import parse_label
from followup_rel_4lang.method_dev.two_stage_v2 import prompts


def scores(rows, ids, labels):
    records = unique(rows)
    if not ids <= set(records):
        raise ValueError('Missing paired predictions')
    for p in ids:
        if records[p]['execution_mode'] != 'gpu' or parse_label(records[p]['generated_text']) != records[p]['parsed_generated_label']:
            raise ValueError('Invalid real prediction provenance')
    return {p: int(records[p]['status'] == 'success' and records[p]['parsed_generated_label'] == labels[p]['gold_answer']) for p in ids}


def cost_for(ocr, extraction, matching, answering):
    parts = {'inventory_seconds': ocr, 'extraction_seconds': extraction,
             'matching_seconds': matching, 'answer_seconds': answering}
    return {**parts, 'total_seconds': sum(parts.values()), 'seconds_per_pair': sum(parts.values()) / 240}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT)
    output = p.parse_args().output_dir.resolve()
    c = verify(output / BACKENDS[0])
    if c['execution_mode'] == 'mock':
        write(output / 'results.json', {'empirical': False, 'execution_mode': 'mock', 'note': 'No measured accuracy or speed.'})
        print('Mock report: no empirical results.')
        return
    labels = unique(read(ROOT / 'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels) != c['labels_sha256']:
        raise ValueError('Label lock changed')
    original = unique(read(output / BACKENDS[0] / 'inputs.jsonl'))
    ids = {p for p in original if labels[p]['split'] == 'main' and p != EXCLUDED}
    if len(ids) != 240:
        raise ValueError('Screen primary denominator changed')
    images = {original[p]['image_sha256'] for p in ids}
    ext = {r['source_key']: r for r in read(Path(c['extraction_path']))}
    exkeys = {digest(prompts.extraction_payload(original[p], stem_only=True)) for p in ids}
    extraction_seconds = call_seconds(call_map([ext[k] for k in exkeys]))
    old8 = load(ROOT / 'artifacts/e1_stem_full_dev_results_snapshot.json')['logical_recipe_costs']['screen']
    old4 = load(ROOT / 'artifacts/transfer_qwen3_vl_4b_results_snapshot.json')['costs']['screen']['primary_logical_recipe']
    cpu_inv = {r['image_sha256']: r for r in read(latest(CPU, 'ocr') / 'inventories.jsonl')}
    cpu_rw = unique(read(latest(CPU, 'rewrite') / 'rewritten.jsonl'))
    cpu_pre = (sum(cpu_inv[s]['runtime_ms'] for s in images) / 1000,
               extraction_seconds, call_seconds(call_map([cpu_rw[p] for p in ids])))
    result = {'development_only': True, 'primary_pairs': 240, 'primary_items': 20,
              'primary_images': 80, 'executed_pairs_per_solver_condition': 288,
              'ocr_images_per_backend': 128, 'models': {}, 'quality': {}, 'pending': []}
    vectors = {}
    for solver in SOLVERS:
        spec = c['solvers'][solver]
        group, vec = {}, {}
        for name, key in [('O', 'O_predictions'), ('VLM_inventory', 'VLM_predictions'), ('EasyOCR_CPU', 'CPU_predictions')]:
            pred = read(Path(spec[key]))
            if name == 'O':
                pred = [r for r in pred if r['condition'] == 'O']
            vec[name] = scores(pred, ids, labels)
            answer = batch_share(pred, lambda r: r['pair_id'] in ids)['seconds']
            if name == 'O':
                cost = cost_for(0, 0, 0, answer)
            elif name == 'VLM_inventory':
                old = old8 if solver == '8B' else old4
                cost = cost_for(old['inventory_seconds'], old['extraction_seconds'], old['matching_seconds'], answer)
            else:
                cost = cost_for(*cpu_pre, answer)
            group[name] = {'correct': sum(vec[name].values()), 'accuracy': sum(vec[name].values()) / 240,
                           'cost': cost, 'source': 'historical_completed'}
        for backend in BACKENDS:
            work = output / backend
            bc = verify(work)
            try:
                ia = latest(work, 'infer_' + solver)
            except ValueError:
                result['pending'].append(backend + '/' + solver)
                continue
            pp = read(ia / 'evaluation/predictions.jsonl')
            if set(unique(pp)) != set(original):
                raise ValueError('Executed 288-row queue incomplete')
            condition = bc['condition'] + '_' + solver
            if any(r['condition'] != condition for r in pp):
                raise ValueError('Condition label mismatch')
            vec[backend] = scores(pp, ids, labels)
            inv = {r['image_sha256']: r for r in read(latest(work, 'ocr') / 'inventories.jsonl')}
            rw = unique(read(latest(work, 'rewrite') / 'rewritten.jsonl'))
            if set(rw) != set(original) or any(rw[p]['options'] != original[p]['options'] for p in original):
                raise ValueError('Invalid rewritten MCQ scope')
            cost = cost_for(sum(inv[s]['runtime_ms'] for s in images) / 1000, extraction_seconds,
                            call_seconds(call_map([rw[p] for p in ids])),
                            batch_share(pp, lambda r: r['pair_id'] in ids)['seconds'])
            group[backend] = {'correct': sum(vec[backend].values()), 'accuracy': sum(vec[backend].values()) / 240,
                              'cost': cost, 'source': 'new_gpu_ocr',
                              'contrasts': {b: paired_bootstrap(vec[backend], vec[b], labels, 20261115, 10000)
                                            for b in ('O', 'VLM_inventory', 'EasyOCR_CPU')},
                              'actual_inference_stage': load(ia / 'evaluation/cost.json'),
                              'by_gui': {g: {'n': sum(original[p]['gui_language'] == g for p in ids),
                                             'correct': sum(vec[backend][p] for p in ids if original[p]['gui_language'] == g)} for g in ('en', 'zh', 'th', 'ru')}}
            result['quality'][backend] = {
                'inventory_status_primary': dict(Counter(inv[s]['status'] for s in images)),
                'rewrite_status_primary': dict(Counter(rw[p]['status'] for p in ids)),
                'changed_pairs': sum(fields(rw[p]) != fields(original[p]) for p in ids),
                'ocr_stage_all128': load(latest(work, 'ocr') / 'cost.json'),
                'rewrite_stage_all288': load(latest(work, 'rewrite') / 'cost.json'),
                'contract_sha256': digest(bc)}
        if all(b in vec for b in BACKENDS):
            group['ppocrv5_minus_easyocr_cuda'] = paired_bootstrap(vec[BACKENDS[1]], vec[BACKENDS[0]], labels, 20261115, 10000)
        result['models'][solver], vectors[solver] = group, vec
    write(output / 'results.json', result)
    lines = ['# GPU OCR: Screen 비교', '',
             '개발용 Screen 20문항·240 mismatch pair. 각 조건은 pilot 동반 행을 포함해 288 pair를 실행한다. OCR는 128개 화면을 처리하며 아래 주 분석 비용에는 main 화면 80개만 포함한다.', '',
             '같은 E1 stem 추출·M0 정렬을 유지하고 inventory만 교체한다. 8B/4B는 OCR와 수정 질문을 공유한다. PP-OCRv5는 RapidOCR 전후처리와 Paddle Inference CUDA의 mobile detector + 언어별 mobile recognizer를 사용한다. PaddleOCR Python pipeline 전체를 실행한 것은 아니다.', '',
             '| Solver | Inventory | 정답/240 | 정확도 | Inventory | 추출+정렬 | 풀이 | 총 시간 | 초/pair |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for solver, group in result['models'].items():
        for name in ('O', 'VLM_inventory', 'EasyOCR_CPU', *BACKENDS):
            if name not in group:
                continue
            s, t = group[name], group[name]['cost']
            lines.append(f"| {solver} | {name} | {s['correct']} | {s['accuracy']:.2%} | {t['inventory_seconds']/60:.2f}분 | {(t['extraction_seconds']+t['matching_seconds'])/60:.2f}분 | {t['answer_seconds']/60:.2f}분 | {t['total_seconds']/60:.2f}분 | {t['seconds_per_pair']:.3f} |")
    lines += ['', '시간은 기존 추출과 재사용한 풀이도 원래 측정된 호출 시간을 포함한 순차 실행 recipe 비용이다. batch 시간은 한 번만 세고 main 비율로 배분한다. 모델 다운로드·적재·프로세스 시작은 제외하며 stage wall·적재 시간·실제 새 호출량은 results.json에 별도로 보존한다. 공유 전처리 비용은 각 solver를 독립 실행할 때의 비교표에 각각 청구했다.', '',
              '## Paired 비교', '', '| Solver | 조건 − 기준 | 차이 | Item bootstrap 95% CI | 회복 / 회귀 |',
              '| --- | --- | ---: | --- | ---: |']
    for solver, group in result['models'].items():
        for backend in BACKENDS:
            if backend not in group:
                continue
            for base, contrast in group[backend]['contrasts'].items():
                lo, hi = contrast['ci95']
                lines.append(f"| {solver} | {backend} − {base} | {contrast['difference']*100:+.2f}pp | [{lo*100:+.2f}, {hi*100:+.2f}]pp | {contrast['recovery']} / {contrast['regression']} |")
    lines += ['', '## GUI 언어별', '', '| Solver | 조건 | EN /60 | ZH /60 | TH /60 | RU /60 |', '| --- | --- | ---: | ---: | ---: | ---: |']
    for solver, group in result['models'].items():
        for backend in BACKENDS:
            if backend in group:
                values = group[backend]['by_gui']
                lines.append('| ' + ' | '.join([solver, backend] + [str(values[g]['correct']) for g in ('en', 'zh', 'th', 'ru')]) + ' |')
    lines += ['', 'OCR 생성 성공·문자열 중복률은 OCR 정확도가 아니다. 빈 결과·OCR 실패·추출/정렬 fallback은 분모에서 제외하지 않는다. 이 개발 집합은 이미 반복 관찰했으며 독립 검증 결과로 해석하지 않는다.', '',
              '미완료: ' + (', '.join(result['pending']) or '없음'), '']
    (output / 'REPORT_KO.md').write_text('\n'.join(lines))
    print('REPORT ' + str(output / 'REPORT_KO.md'), flush=True)


if __name__ == '__main__':
    main()
