"""Read-only time/accuracy comparison; no model loading or new inference."""
import hashlib
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO/'01_code/src'), str(REPO), str(Path(__file__).parent)]
from mpr_crosslocale.methods.selective_alignment.schemas import digest
from mpr_crosslocale.inference.answer_parser import parse_label
from followup_rel_4lang.method_dev.two_stage_v2 import prompts
from reference_comparison import load_references, stream
from search_pipeline import EXCLUDED


def batch_share(rows, selected):
    """Count each full batch once; allocate its time by selected-row fraction."""
    groups = defaultdict(list)
    for row in rows:
        groups[row['batch_id']].append(row)
    seconds = 0.0
    count = mixed = touched = 0
    for batch in groups.values():
        size, runtime = batch[0]['batch_size'], batch[0]['batch_runtime_ms']
        if size != len(batch) or not isinstance(runtime, (float, int)) or not math.isfinite(runtime) or runtime < 0:
            raise ValueError('Incomplete batch or invalid runtime')
        if any(r['batch_size'] != size or r['batch_runtime_ms'] != runtime for r in batch):
            raise ValueError('Conflicting batch metadata')
        chosen = sum(bool(selected(row)) for row in batch)
        if chosen:
            count += chosen
            touched += 1
            mixed += chosen < size
            seconds += runtime/1000 * chosen/size
    return {'seconds': seconds, 'selected_rows': count, 'touched_batches': touched, 'mixed_batches': mixed,
            'allocation': 'batch_runtime_ms * selected_rows / actual_batch_size; not standalone latency'}


def call_map(records):
    result = {}
    for record in records:
        for call in record['attempts']:
            if call['execution_mode'] != 'gpu':
                raise ValueError('Only real GPU calls may be timed')
            key = call['cache_key']
            if key in result and result[key]['runtime_ms'] != call['runtime_ms']:
                raise ValueError('Conflicting cached call runtime')
            result[key] = call
    return result


def call_seconds(calls):
    # A hit is charged its original measured runtime for a standalone recipe.
    return sum(c['runtime_ms'] for c in calls.values())/1000


def read(path):
    return list(stream(path))


def unique(rows):
    out = {r['pair_id']: r for r in rows}
    if len(out) != len(rows):
        raise ValueError('Duplicate pair')
    return out


def collect():
    captures = {}
    def use(path):
        path = path.resolve()
        captures[str(path.relative_to(REPO))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path
    def load(path):
        return json.loads(use(path).read_text())
    def rows(path):
        return read(use(path))
    use(Path(__file__))
    base = ROOT/'artifacts/two_stage_v2_hybrid'
    work = base/'screen'
    done = load(work/'COMPLETE.json')
    parent = load(base/'contract.json')
    for filename, sha in parent['source_hashes'].items():
        if hashlib.sha256((REPO/filename).read_bytes()).hexdigest() != sha:
            raise ValueError('Frozen method source changed')
    originals = unique(rows(work/'inputs.jsonl'))
    labels = unique(rows(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels) != parent['base_data_contract']['labels']:
        raise ValueError('Labels changed')
    ids = {p for p in originals if labels[p]['split'] == 'main' and p != EXCLUDED}
    main = [originals[p] for p in sorted(ids)]
    images = {r['image_sha256'] for r in main}
    inventories = [r for r in rows(Path(done['inventory'])/'inventories.jsonl') if r['image_sha256'] in images]
    inventory_calls = call_map(inventories)
    extraction = {}
    for scope, stage in [('all', 'extract'), ('stem', 'extract_stem')]:
        keys = {digest(prompts.extraction_payload(r, stem_only=scope == 'stem')) for r in main}
        records = [r for r in rows(Path(done[stage])/'extractions.jsonl') if r['source_key'] in keys]
        if len(records) != len(keys):
            raise ValueError('Incomplete source extraction')
        extraction[scope] = call_map(records)
    current = rows(Path(done['predictions'])/'predictions.jsonl')
    transformations = {c: rows(Path(done['rewrite'])/(c+'.jsonl')) for c in parent['conditions']}
    saved = load(work/'results.json')
    comparisons = []
    def add(condition, name, inv, source_calls, local_calls, predictions, automatic=True, gold=False):
        chosen = [r for r in predictions if r['condition'] == condition and r['pair_id'] in ids]
        if {r['pair_id'] for r in chosen} != ids or len(chosen) != len(ids):
            raise ValueError('Missing or duplicate paired predictions')
        if any(r['execution_mode'] != 'gpu' or parse_label(r['generated_text']) != r['parsed_generated_label'] for r in chosen):
            raise ValueError('Invalid raw predictions')
        correct = sum(r['status'] == 'success' and r['parsed_generated_label'] == labels[r['pair_id']]['gold_answer'] for r in chosen)
        if condition in saved['conditions'] and saved['conditions'][condition]['correct'] != correct:
            raise ValueError('Saved accuracy differs')
        timing = batch_share(predictions, lambda r: r['condition'] == condition and r['pair_id'] in ids)
        if timing['selected_rows'] != len(ids):
            raise ValueError('VLM time denominator differs')
        source_s, local_s = call_seconds(source_calls), call_seconds(local_calls)
        inv_s = call_seconds(inventory_calls) if inv else 0.0
        comparisons.append({'condition': condition, 'name': name, 'device': 'B200 MIG45GB', 'n': len(ids),
            'correct': int(correct), 'accuracy': correct/len(ids), 'automatic': automatic, 'gold_span': gold,
            'inventory_seconds': inv_s, 'editor_vlm_seconds': 0.0, 'extraction_seconds': source_s, 'localization_seconds': local_s,
            'lm_seconds': source_s+local_s, 'vlm_seconds': timing['seconds'],
            'cold_total_seconds': inv_s+source_s+local_s+timing['seconds'],
            'inventory_cached_total_seconds': source_s+local_s+timing['seconds'], 'vlm_batch_allocation': timing,
            'required_call_counts': {'inventory': len(inventory_calls) if inv else 0, 'source_extraction': len(source_calls), 'localization': len(local_calls)}})
    add('O', 'O · 원본', False, {}, {}, current)
    recipes = [
        ('TS_SEL_TXT_ORACLE', 'T형 · gold span+Qwen3 번역', False, None, True),
        ('TS_SEL_TXT_AUTO', '참조 표현 텍스트 번역 · 자동', False, 'all', False),
        ('TS_FULL_TXT', '전체 텍스트 번역', False, None, False),
        ('TS_QSEL_OFULL_TXT_AUTO', 'Hybrid TXT', False, 'stem', False),
        ('TS_FULL_GUI', 'Full GUI', True, None, False),
        ('TS_SEL_GUI_AUTO', 'Stem+Options 선택적 정렬 · 분리', True, 'all', False),
        ('TS_STEM_ONLY_GUI_AUTO', 'Stem-only GUI · 분리', True, 'stem', False),
        ('TS_QSEL_OFULL_GUI_AUTO', 'Hybrid GUI', True, 'stem', False),
        ('TS_SEL_GUI_ORACLE', 'Oracle span GUI · 진단', True, None, True),
    ]
    for condition, name, inv, scope, oracle in recipes:
        if condition == 'TS_STEM_ONLY_GUI_AUTO':
            stem_root = ROOT/'artifacts/stem_only_gui_screen_v1'
            marker = load(stem_root/'COMPLETE.json')
            profile = load(stem_root/'contract.json')
            if profile['downstream'] != parent['config']['downstream'] or marker['contract_sha256'] != digest(profile):
                raise ValueError('Stem-only profile differs')
            predictions = rows(Path(marker['predictions'])/'predictions.jsonl')
            calls = call_map([r for r in transformations['TS_QSEL_OFULL_GUI_AUTO'] if r['pair_id'] in ids])
            calls = {k: v for k,v in calls.items() if v['component'] == 'stem_alignment'}
        else:
            predictions = current
            calls = call_map([r for r in transformations[condition] if r['pair_id'] in ids])
        add(condition, name, inv, extraction[scope] if scope else {}, calls, predictions, not oracle, oracle)
    runs = {}
    for folder, name in [('single_pass_stem_screen_v1', 'Stem 통합 GUI'), ('single_pass_all_screen_v1', 'Stem+Options 통합 GUI')]:
        directory = ROOT/'artifacts'/folder
        marker, profile = load(directory/'COMPLETE.json'), load(directory/'contract.json')
        if marker['contract_sha256'] != digest(profile) or profile['downstream'] != parent['config']['downstream']:
            raise ValueError('Single-pass profile differs')
        for filename, sha in profile['source_sha256'].items():
            if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != sha:
                raise ValueError('Frozen single-pass source changed')
        rewrite = rows(Path(marker['rewrite'])/'rewritten.jsonl')
        predictions = rows(Path(marker['infer'])/'predictions.jsonl')
        add(profile['condition'], name, True, {}, call_map([r for r in rewrite if r['pair_id'] in ids]), predictions)
        runtime = load(Path(marker['rewrite'])/'cost.json')
        all_vlm = batch_share(predictions, lambda r: True)
        runs[folder] = {'executed_pairs': len(predictions), 'inventory_preexisting': True,
                       'transformation_wall_seconds': runtime['wall_seconds'], 'transformation_role': 'LM', 'vlm_batch_seconds': all_vlm['seconds'],
                       'lower_bound_seconds': runtime['wall_seconds']+all_vlm['seconds'],
                       'missing_overheads': 'VLM model load, input checks, process startup/exit and orchestration not fully timed'}
    visual_dir=ROOT/'artifacts/visual_selective_rewrite_screen_v1'
    if (visual_dir/'COMPLETE.json').exists():
        marker,profile=load(visual_dir/'COMPLETE.json'),load(visual_dir/'contract.json')
        if marker['contract_sha256']!=digest(profile) or profile['downstream']!=parent['config']['downstream']:
            raise ValueError('Visual rewrite profile differs')
        for filename,sha in profile['source_sha256'].items():
            if hashlib.sha256(Path(filename).read_bytes()).hexdigest()!=sha:raise ValueError('Visual rewrite source changed')
        rewrite=rows(Path(marker['rewrite'])/'rewritten.jsonl');predictions=rows(Path(marker['infer'])/'predictions.jsonl')
        add(profile['condition'],'Screenshot 직접 rewrite · 문맥 보존 별도 진단',False,{},{},predictions)
        edit_seconds=call_seconds(call_map([r for r in rewrite if r['pair_id'] in ids]))
        comparisons[-1]['editor_vlm_seconds']=edit_seconds
        comparisons[-1]['cold_total_seconds']+=edit_seconds
        comparisons[-1]['inventory_cached_total_seconds']+=edit_seconds
        comparisons[-1]['selective_scope_verified']=False
        rewrite_cost=load(Path(marker['rewrite'])/'cost.json')
        all_vlm=batch_share(predictions,lambda r:True)
        runs[visual_dir.name]={'executed_pairs':len(predictions),'inventory_preexisting':False,
            'transformation_wall_seconds':rewrite_cost['wall_seconds'],'transformation_role':'VLM','vlm_batch_seconds':all_vlm['seconds'],
            'lower_bound_seconds':rewrite_cost['wall_seconds']+all_vlm['seconds'],
            'full_wall_seconds':marker['execution_wall_seconds'],'wall_scope':marker['wall_scope']}
    refs, ref_meta, _ = load_references(REPO, {p: labels[p] for p in ids}, {'screen': originals}, use,
        parent['config']['downstream']['model_config'], parent['config']['historical_baseline_contract_sha256'])
    for profile in ref_meta['source_runs'].values():
        if profile['model_config'] != parent['config']['downstream']['model_config'] or profile['system_prompt'] != parent['config']['downstream']['system_prompt']:
            raise ValueError('Historical model or system contract differs')
    historical = []
    old_files = {'ExpA': REPO/'followup_rel_4lang/artifacts/new_models_expA_20261115/analysis/expA_8b_20261114/qwen3/expA_qwen3/full/predictions.jsonl',
                 'ORCF': REPO/'followup_rel_4lang/artifacts/qwen3_single4090_20261107/full_rel/predictions.jsonl.gz'}
    batches = {}
    for run, conditions in [('ExpA', ('O_EXP_A', 'R_REF', 'T_REF')), ('ORCF', ('F_REF',))]:
        wanted_batches = {r['batch_id'] for c in conditions for r in refs[c].values()}
        batches[run] = [r for r in stream(use(old_files[run])) if r['batch_id'] in wanted_batches]
        for condition in conditions:
            selected = {r['input_id'] for r in refs[condition].values()}
            timing = batch_share(batches[run], lambda r: r['input_id'] in selected)
            if timing['selected_rows'] != len(selected):
                raise ValueError('Historical timing missing effective inputs')
            group = refs[condition]
            count = sum(r['status'] == 'success' and r['parsed_generated_label'] == labels[p]['gold_answer'] for p,r in group.items())
            historical.append({'condition': condition, 'device': 'RTX4090', 'n': len(group), 'correct': int(count),
                'accuracy': count/len(group), 'vlm_seconds': timing['seconds'], 'total_seconds': None,
                'preparation_seconds': None, 'vlm_batch_allocation': timing,
                'reason': 'Human/parallel artifact construction not timed; T Gemma translation runtime not recorded' if condition != 'O_EXP_A' else 'Original input; VLM only, model load excluded'})
    gemma_meta = load(REPO/'followup_rel_4lang/artifacts/new_models_expA_20261115/translation/work/translations_gemma_meta.json')
    return {'as_of_utc': datetime.now(timezone.utc).isoformat(), 'primary_pairs': len(ids), 'semantic_items': len({r['parallel_id'] for r in main}),
        'images': len(images), 'source_mcqs': len({(r['parallel_id'],r['source_language']) for r in main}),
        'pair_ids_sha256': digest(sorted(ids)), 'current': comparisons, 'historical': historical,
        'reference_metadata': ref_meta, 'gemma_translation_metadata': gemma_meta,
        'actual_new_run_lower_bounds': runs, 'source_sha256': captures,
        'inventory': {'seconds': call_seconds(inventory_calls), 'failed_images': sum(r['status'] != 'success' for r in inventories), 'calls': len(inventory_calls)},
        'methodology': {'total': 'Measured unique inventory+direct visual rewrite+extraction+localization call runtimes + batch-apportioned final VLM runtime',
            'batch_allocation': 'Full batches collected first, then runtime * selected rows / declared actual batch size. Eight pilot/main mixed batches per current condition.',
            'cache_policy': 'Each standalone method charged all required original call runtimes, even if reused from a cache. Inventory-cached column excludes only inventory.',
            'exclusions': 'Manual/parallel annotation construction, download, model loads, process startup and unmeasured CPU/orchestration overhead. Not a single stopwatch end-to-end wall measurement.',
            'hybrid': 'Charge complete Full recipe once, including its generated stem that is discarded. No double charging cached Full calls.',
            'stem_separate': 'Required-component reconstruction from frozen Hybrid; original Stem-only execution reused precomputed stems. Not a measured standalone fresh pipeline.'}}


def render(data):
    lines = ['# 실험별 전체 처리시간과 정확도', '',
        f"같은 Screen **{data['semantic_items']} semantic item·{data['primary_pairs']} mismatch pair** 기준이다. Inventory는 고유 screenshot{data['images']}개, source extraction은 고유 MCQ{data['source_mcqs']}개만 계산한다. 실패·repair를 포함하고 pilot48쌍은 주 비교에서 제외했다. 추가 추론은 실행하지 않았다.", '',
        '**총 처리시간 = inventory/직접 rewrite VLM + referent 추출 LM + 번역/정렬 LM + 문제 풀이 VLM.** 아래는 저장된 실제 처리 구간을 합산해 재구성한 값이다. 모델 적재·프로세스 전환·일부 CPU 검증·사전 수작업은 포함되지 않으므로, 시작부터 종료까지의 전체 wall time과 다르다. 일부 배치에 pilot이 함께 있어 VLM 시간은 문항 수 비율로 안분했다. 새로 독립 실행한 실측 wall로 오해하지 않는다.', '',
        '## 현재 B200 MIG: 같은 분모 비교', '',
        '| 조건 | 정답 | 정확도 | Inventory/Rewrite VLM·분 | LM 합계·분 | 문제 풀이 VLM·분 | 처음부터 합계·분 | Inventory 재사용·분 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in data['current']:
        lines.append(f"| {r['name']} | {r['correct']}/{r['n']} | {r['accuracy']:.2%} | {(r['inventory_seconds']+r['editor_vlm_seconds'])/60:.2f} | {r['lm_seconds']/60:.2f} | {r['vlm_seconds']/60:.2f} | **{r['cold_total_seconds']/60:.2f}** | {r['inventory_cached_total_seconds']/60:.2f} |")
    by_condition = {r['condition']: r for r in data['current']}
    lines += ['', '### 주요 후보의 시간 증가와 정답 차이', '',
              '| 비교 | 합계 시간 차이·분 | 정답 수 차이 |', '| --- | ---: | ---: |']
    for left, right in [('TS_STEM_SINGLE_PASS_GUI_AUTO','TS_STEM_ONLY_GUI_AUTO'),
                        ('TS_QSEL_OFULL_GUI_AUTO','TS_STEM_ONLY_GUI_AUTO'),
                        ('TS_ALL_SINGLE_PASS_GUI_AUTO','TS_QSEL_OFULL_GUI_AUTO'),
                        ('TS_ALL_SINGLE_PASS_GUI_AUTO','TS_STEM_SINGLE_PASS_GUI_AUTO')]:
        a,b = by_condition[left], by_condition[right]
        lines.append(f"| {a['name']} − {b['name']} | {(a['cold_total_seconds']-b['cold_total_seconds'])/60:+.2f} | {a['correct']-b['correct']:+d} |")
    lines += ['', 'T형은 현재 Qwen3-8B로 gold source span만 텍스트 번역한 `TS_SEL_TXT_ORACLE`이며 기존 Gemma T와 다르다. 수작업 span 준비 비용은 미측정이고 automatic 조건이 아니다. Oracle span GUI도 진단 전용이다. 자동 text-only 참조 번역은 별도 행으로 포함했다.', '',
        'Inventory 재사용 열은 inventory만 준비돼 있다고 가정한다. 추출·정렬까지 모두 cache hit여서 즉시 문제 풀이만 실행했던 실제 추가 실행 시간과는 다르다. 각 방법을 단독 실행한다고 보고 cached Full 등의 원래 처리시간도 다시 비용에 넣었다.', '',
        '### LM 내부 분해', '', '| 조건 | Referent 추출·분 | 번역/정렬·분 |', '| --- | ---: | ---: |']
    for r in data['current']:
        lines.append(f"| {r['name']} | {r['extraction_seconds']/60:.2f} | {r['localization_seconds']/60:.2f} |")
    lines += ['', 'Hybrid는 options를 얻으려고 수행한 Full 전체 호출도 포함한다. Full에서 생성했다가 버린 stem의 계산을 빼지 않았다. Stem-only 분리는 Hybrid에서 실제로 측정된 inventory·stem 추출·stem 정렬만 재구성했으며, 원래 실행 때 발생한 불필요한 options Full까지 이 방법의 필수 비용으로 부과하지 않았다.', '',
        '## 과거 O/R/T/F: RTX4090 기록', '',
        '| 조건 | 정답 | 정확도 | 문제 풀이 VLM·분 | 전체 전처리 포함 시간 |', '| --- | ---: | ---: | ---: | --- |']
    for r in data['historical']:
        lines.append(f"| {r['condition']} | {r['correct']}/{r['n']} | {r['accuracy']:.2%} | {r['vlm_seconds']/60:.2f} | "+('VLM만 수행; 적재 제외' if r['condition'] == 'O_EXP_A' else '미상: 사전 제작/번역 시간 미기록')+' |')
    lines += ['', 'R_REF는 parallel referent, F_REF는 parallel 전체 localization을 이미 보유한 reference다. 이 입력을 얻는 annotation·병렬 데이터 제작 비용을0으로 본 것이 아니다. 현재 B200에서 R/F240쌍을 다시 푼 기록은 없어 현재 장비의 전체 시간으로 환산하지 않았다. 같은 모델·revision·system과 pair/gold를 확인했지만 장비·배치·큐가 다르므로 위 B200 행과 직접적인 속도 경쟁으로 해석하지 않는다.', '',
        '기존 T_REF는 `mlx-community/gemma-3-12b-it-4bit`를 Mac에서 사용한 번역+RTX4090 VLM이다. 저장된 translation 파일에는 runtime이 없어 전체 시간을 복원할 수 없었다. 기존 T_REF와 현재 T형을 하나의 조건으로 합치지 않는다.', '',
        '## 실제 새 실행에서 기록된 시간', '',
        '아래는 main+pilot288쌍이며 위240쌍 표와 분모가 다르다. Inventory 기반 두 통합 실행은 inventory가 이미 준비돼 있었고, 변환 LM wall+문제 풀이 VLM batch만 기록돼 합계는 **전체 실행 시간의 하한**이다. 이미지 직접 rewrite는 inventory를 쓰지 않고 전체 worker 실행 wall도 추가로 기록했다.', '',
        '| 실행 | 변환 단계 wall·분 | 문제 풀이 VLM batch 합·분 | 실행 시간·분 |', '| --- | ---: | ---: | ---: |']
    for name,r in data['actual_new_run_lower_bounds'].items():
        total=f"{r['full_wall_seconds']/60:.2f} (실측 wall)" if 'full_wall_seconds' in r else f"≥{r['lower_bound_seconds']/60:.2f}"
        lines.append(f"| {name} | {r['transformation_wall_seconds']/60:.2f} | {r['vlm_batch_seconds']/60:.2f} | {total} |")
    lines += ['', '앞선 두 통합 실행의 하한에는 VLM 적재·입력 검사·프로세스 시작/종료 등이 추가된다. 이미지 직접 rewrite 행은 별도로 기록한 전체 worker 실행 wall이며 하한이 아니다. 기존9조건의 shared pipeline wall을 각 방법에 그대로 붙이는 것도 여러 방법의 공용 처리와 불필요한 단계를 중복 청구하므로 피했다.', '',
        '## 비교를 읽는 법', '',
        f"GUI 방법은 같은 inventory 비용 **{data['inventory']['seconds']/60:.2f}분**을 공유한다. 따라서 처음 실행할 때는 inventory가 큰 비중을 차지하고, 같은 화면의 inventory가 준비돼 있으면 방법 간 LM 차이가 더 크게 드러난다. 고유80개 화면에 한 번씩만 계산했고 문항·언어쌍240개마다 재추출한 것으로 세지 않았다.", '',
        '정확도는 이미 여러 번 관찰한 개발 Screen의 점추정이다. Hybrid와 Stem+Options 통합의 정답1개 차이를 안정적인 우위로 해석하지 않는다. 이미지 직접 rewrite는 문맥까지 변경했을 수 있으므로 정확도만으로 selective alignment의 성공을 주장하지 않는다. [문맥 audit](VISUAL_SELECTIVE_REWRITE_KO.md)을 함께 본다. 처리시간 역시 서로 다른 실행 시점·출력 길이·repair·배치의 영향을 포함하며 통제된 장비 성능 벤치마크가 아니다.', '',
        '## 집계 검증·재현', '',
        '- 모델 호출은 cache key별 한 번만 합산하고 cache hit를0초로 처리하지 않음.',
        '- VLM은 행별 batch 시간을 그대로 더하지 않음. 전체 batch를 먼저 확인하고 선택된 문항 몫만 안분.',
        '- Pair ID·주 분석 분모·generation parser·기존 정답 수·frozen 코드/입력·reference model/system 검사.',
        '- 실패·repair·rejected semantic repair를 삭제하지 않음. 준비시간 미기록은0으로 대체하지 않음.', '',
        '```bash', '.venv/bin/python followup_rel_4lang/method_dev/scripts/compare_end_to_end.py', '```', '',
        '[시간·정확도·출처 SHA-256 snapshot](../artifacts/end_to_end_cost_snapshot.json), [누적 실험 결과](TWO_STAGE_RESULTS_KO.md), [통합 조건 상세](SINGLE_PASS_ALL_GUI_KO.md).', '']
    return '\n'.join(lines)


def main():
    data = collect()
    out = ROOT/'artifacts/end_to_end_cost_snapshot.json'
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    report = ROOT/'reports/END_TO_END_COST_KO.md'
    report.write_text(render(data))
    print(json.dumps({'report': str(report), 'current': [{k:r[k] for k in ('name','correct','cold_total_seconds','inventory_cached_total_seconds')} for r in data['current']]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
