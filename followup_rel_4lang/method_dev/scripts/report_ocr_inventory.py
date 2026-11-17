"""CPU-only analysis of a completed OCR inventory-source ablation."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / '01_code/src'), str(REPO), str(Path(__file__).parent)]
from run_ocr_inventory import verify, latest, DEFAULT_OUTPUT, CONDITION
from run_stem_only_gui import read, unique, write
from compare_end_to_end import call_map, call_seconds, batch_share
from search_pipeline import EXCLUDED, paired_bootstrap
from mpr_crosslocale.methods.selective_alignment.schemas import digest, fields
from mpr_crosslocale.inference.answer_parser import parse_label
from followup_rel_4lang.method_dev.two_stage_v2 import prompts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT)
    output = parser.parse_args().output_dir.resolve()
    c = verify(output)
    done = json.loads((output / 'COMPLETE.json').read_text())
    if done['contract_sha256'] != digest(c):
        raise ValueError('Completion contract changed')
    if c['execution_mode'] == 'mock':
        write(output / 'results.json', {'execution_mode': 'mock', 'empirical': False,
                                       'note': 'CPU mock only; no measured OCR accuracy or VLM performance.'})
        print('Mock pipeline complete; no empirical results reported.')
        return
    labels = unique(read(ROOT / 'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels) != c['labels_sha256']:
        raise ValueError('Label lock changed')
    original = unique(read(output / 'inputs.jsonl'))
    ids = {p for p in original if labels[p]['split'] == 'main' and p != EXCLUDED}
    if len(ids) != 240:
        raise ValueError('Primary denominator changed')
    rw = unique(read(latest(output, 'rewrite') / 'rewritten.jsonl'))
    pp = read(latest(output, 'infer') / 'evaluation/predictions.jsonl')
    pred = unique(pp)
    if set(pred) != set(original) or set(rw) != set(original):
        raise ValueError('Incomplete paired output')
    if any(rw[p]['options'] != original[p]['options'] or pred[p]['condition'] != CONDITION or
           pred[p]['execution_mode'] != 'gpu' or parse_label(pred[p]['generated_text']) != pred[p]['parsed_generated_label'] for p in ids):
        raise ValueError('Output scope or prediction provenance changed')
    baseline = unique(read(Path(c['baseline_predictions'])))
    ext = {r['source_key']: r for r in read(Path(c['extraction_path']))}
    inventory = {r['image_sha256']: r for r in read(latest(output, 'ocr') / 'inventories.jsonl')}
    before = {r['image_sha256']: r for r in read(Path(c['baseline_inventory']))}
    images = {original[p]['image_sha256'] for p in ids}
    values = {name: {p: int(records[p]['status'] == 'success' and records[p]['parsed_generated_label'] == labels[p]['gold_answer']) for p in ids}
              for name, records in [('OCR_E1_M0', pred), ('VLM_E1_M0', baseline)]}
    costs = {'ocr_seconds': sum(inventory[s]['runtime_ms'] for s in images) / 1000,
             'extraction_seconds': call_seconds(call_map([ext[k] for k in {digest(prompts.extraction_payload(original[p], stem_only=True)) for p in ids}])),
             'matching_seconds': call_seconds(call_map([rw[p] for p in ids])),
             'answer_seconds': batch_share(pp, lambda r: r['pair_id'] in ids)['seconds']}
    costs['total_seconds'] = sum(costs.values())
    costs['seconds_per_pair'] = costs['total_seconds'] / len(ids)
    overlap = []
    for sha in sorted(images):
        a, b = set(before[sha]['visible_strings']), set(inventory[sha]['visible_strings'])
        overlap.append({'image_sha256': sha, 'gui_language': inventory[sha]['gui_language'],
                        'vlm_strings': len(a), 'ocr_strings': len(b), 'exact_intersection': len(a & b),
                        'vlm_only': sorted(a - b), 'ocr_only': sorted(b - a),
                        'ocr_status': inventory[sha]['status']})
    # Old selected labels are a diagnostic, not OCR ground truth.
    base_rewrite = latest(ROOT / 'artifacts/stem_refinement_2x2_screen_v1/E1_M0', 'rewrite')
    old_rewrites = unique(read(base_rewrite / 'rewritten.jsonl'))
    unchanged = [p for p in ids if rw[p]['modified_question'] == old_rewrites[p]['modified_question']]
    needed = [(p, e['replacement']) for p in ids for e in old_rewrites[p]['edits']]
    norm = lambda s: ' '.join(s.split()).casefold()
    membership = {'baseline_edit_instances': len(needed),
                  'exact_present': sum(t in inventory[original[p]['image_sha256']]['visible_strings'] for p, t in needed),
                  'case_space_normalized_present': sum(norm(t) in {norm(x) for x in inventory[original[p]['image_sha256']]['visible_strings']} for p, t in needed)}
    result = {'development_only': True, 'primary_pairs': len(ids), 'primary_items': 20,
              'executed_pairs': len(pp), 'primary_images': len(images), 'ocr_device': c['ocr_config']['device'],
              'correct': {k: sum(v.values()) for k, v in values.items()},
              'OCR_minus_VLM': paired_bootstrap(values['OCR_E1_M0'], values['VLM_E1_M0'], labels, 20261115, 10000),
              'cost': costs, 'inventory_overlap_not_ground_truth': overlap,
              'old_edit_label_membership_not_accuracy': membership,
              'ocr_status': dict(Counter(inventory[s]['status'] for s in images)),
              'rewrite_status': dict(Counter(rw[p]['status'] for p in ids)),
              'changed_pairs': sum(fields(rw[p]) != fields(original[p]) for p in ids),
              'same_MCQs_as_VLM_baseline': len(unchanged),
              'same_MCQs_label_differences': sum(pred[p]['parsed_generated_label'] != baseline[p]['parsed_generated_label'] for p in unchanged),
              'by_gui': {g: {'n': sum(original[p]['gui_language'] == g for p in ids),
                            'correct': {k: sum(v[p] for p in ids if original[p]['gui_language'] == g) for k, v in values.items()}} for g in ('en', 'zh', 'th', 'ru')},
              'stage_costs': {stage: json.loads((latest(output, stage) / ('evaluation/cost.json' if stage == 'infer' else 'cost.json')).read_text()) for stage in ('ocr', 'rewrite', 'infer')},
              'contract_sha256': digest(c), 'weights': json.loads((output / 'ocr_weights.json').read_text())}
    write(output / 'results.json', result)
    old_cost = json.loads((ROOT / 'artifacts/e1_stem_full_dev_results_snapshot.json').read_text())['logical_recipe_costs']['screen']
    ci = result['OCR_minus_VLM']
    lines = ['# EasyOCR inventory: Screen 비교 결과', '',
             '20개 main semantic item·240 pair. 기존 E1 출력·M0 prompt·downstream 설정을 유지하고 inventory 공급원만 바꿨다. 실행은 batch 구성을 유지한 288 pair이며 pilot 48 pair는 아래 정확도·계산 시간에서 제외한다.', '',
             '| 조건 | 정답/240 | 정확도 | Inventory | 추출+matching | 최종 풀이 | 총 계산 시간 | 초/pair |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |',
             f"| VLM inventory E1/M0 | {result['correct']['VLM_E1_M0']} | {result['correct']['VLM_E1_M0']/240:.2%} | {old_cost['inventory_seconds']/60:.2f}분 | {(old_cost['extraction_seconds']+old_cost['matching_seconds'])/60:.2f}분 | {old_cost['answer_seconds']/60:.2f}분 | {old_cost['total_seconds']/60:.2f}분 | {old_cost['total_seconds']/240:.3f} |",
             f"| EasyOCR inventory E1/M0 | {result['correct']['OCR_E1_M0']} | {result['correct']['OCR_E1_M0']/240:.2%} | {costs['ocr_seconds']/60:.2f}분 | {(costs['extraction_seconds']+costs['matching_seconds'])/60:.2f}분 | {costs['answer_seconds']/60:.2f}분 | {costs['total_seconds']/60:.2f}분 | {costs['seconds_per_pair']:.3f} |", '',
             f"OCR−VLM {ci['difference']*100:+.2f}pp, semantic-item bootstrap 95% CI [{ci['ci95'][0]*100:+.2f}, {ci['ci95'][1]*100:+.2f}]pp, 회복 {ci['recovery']} / 회귀 {ci['regression']} pair. 반복 관찰한 개발 집합의 탐색 결과다.", '',
             '비용은 CPU OCR와 GPU LM/VLM 호출 구간을 순차 합산했다. 모델 다운로드/적재·프로세스 기동은 제외하며 OCR stage wall과 reader 적재 시간은 results.json에 별도로 보존한다. 기존 추출과 재사용 풀이도 최초 호출 시간을 청구한다. 같은 완성 batch의 시간은 한 번만 계산하고 main 비율로 배분한다.', '',
             '## GUI 언어별', '', '| GUI | n | VLM inventory | EasyOCR inventory |', '| --- | ---: | ---: | ---: |']
    for g, s in result['by_gui'].items():
        lines.append(f"| {g.upper()} | {s['n']} | {s['correct']['VLM_E1_M0']/s['n']:.2%} | {s['correct']['OCR_E1_M0']/s['n']:.2%} |")
    lines += ['', '## OCR 처리 및 비교 범위', '',
              f"Main 이미지 {len(images)}개 상태: `{result['ocr_status']}`. 기존 VLM이 선택했던 교체 표현 {membership['baseline_edit_instances']}개 중 OCR inventory에 exact 존재하는 것은 {membership['exact_present']}개다. 이는 기존 선택과의 호환성 지표이며 실제 화면 label precision/recall이 아니다.", '',
              f"기존 VLM inventory와 완성 MCQ가 같은 경우 {len(unchanged)} pair, 그중 label 차이 {result['same_MCQs_label_differences']} pair. 동일 행만으로 재사용하지 않고 전체 batch/이미지/prompt/환경이 같은 경우에만 재사용했다.", '',
              '원시 bbox·문자열·confidence는 OCR 산출물에 저장하되 matching에는 정렬된 문자열 목록만 제공했다. OCR 빈 목록·실패·추출 실패·matching fallback을 분모에서 제거하지 않았다. OCR confidence와 문자열 겹침은 검증된 의미 정확도가 아니다.', '',
              '단계별 원시 자료와 SHA/config/model lock: 해당 run의 contract.json, ocr_weights.json, results.json. OCR와 VLM이 출력하는 문자열 단위·후보 수 차이도 이 공급원 교체 효과에 포함된다.', '']
    (output / 'REPORT_KO.md').write_text('\n'.join(lines))
    (ROOT / 'reports/OCR_INVENTORY_SCREEN_RESULTS_KO.md').write_text('\n'.join(lines))
    write(ROOT / 'artifacts/ocr_inventory_results_snapshot.json', result)
    print(json.dumps({'correct': result['correct'], 'cost': costs}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
