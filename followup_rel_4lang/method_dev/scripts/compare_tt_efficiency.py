"""CPU-only comparison of completed TT/CLP, E1/M0 and inventory-free runs."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / '01_code/src'), str(REPO), str(Path(__file__).parent)]
from compare_end_to_end import batch_share, call_map, call_seconds
from run_stem_only_gui import read, unique, write
from run_stem_refinement_2x2 import latest, extraction
from search_pipeline import EXCLUDED, paired_bootstrap
from mpr_crosslocale.methods.selective_alignment.schemas import digest
from mpr_crosslocale.inference.answer_parser import parse_label
from followup_rel_4lang.method_dev import external_baselines
from followup_rel_4lang.method_dev.two_stage_v2 import prompts

COHORTS = ('screen', 'selection', 'internal_evaluation')
METHODS = ('O', 'TT', 'CLP', 'DIRECT_COPY', 'E1_M0')
NAMES = {'O': 'O · 원본', 'TT': 'TT · 전체 영어 번역',
         'CLP': 'CLP · 영어 이해 후 단계별 풀이',
         'DIRECT_COPY': '이미지 직접 rewrite · 원문 복사 강화',
         'E1_M0': 'Stem-only GUI · E1/M0'}


def main():
    captures = {}

    def use(path):
        path = Path(path).resolve()
        captures[str(path.relative_to(REPO))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path

    def load(path):
        return json.loads(use(path).read_text())

    def rows(path):
        return read(use(path))

    def contract(folder, completed=True):
        c = load(folder / 'contract.json')
        if c['execution_mode'] != 'gpu':
            raise ValueError('Real GPU provenance required')
        if completed:
            done = load(folder / 'COMPLETE.json')
            if done['contract_sha256'] != digest(c):
                raise ValueError('Completed contract mismatch')
        for filename, sha in c['source_sha256'].items():
            if hashlib.sha256(use(REPO / filename).read_bytes()).hexdigest() != sha:
                raise ValueError('Frozen source mismatch: ' + filename)
        return c

    use(Path(__file__))
    ext = ROOT / 'artifacts/external_baselines_v1'
    ec = contract(ext)
    eroot = ROOT / 'artifacts/e1_stem_full_dev_v1'
    e1c = contract(eroot)
    night = ROOT / 'artifacts/overnight_two_v1'
    nc = contract(night)
    direct_screen = ROOT / 'artifacts/visual_source_copy_rewrite_screen_v1'
    dc = contract(direct_screen)
    labels = unique(rows(ROOT / 'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if any(c['labels_sha256'] != digest(labels) for c in (ec, e1c, nc, dc)):
        raise ValueError('Label lock mismatch')
    downstream = ec['config']['downstream']
    if any(c['config']['downstream'] != downstream for c in (e1c, nc)) or dc['downstream'] != downstream:
        raise ValueError('Downstream inference contract mismatch')
    if dc['config'] != nc['direct_config']:
        raise ValueError('Copy-first editor config changed after Screen')
    translations = {r['source_key']: r for r in rows(latest(ext, 'translate') / 'transformations.jsonl')}
    alignments = {r['source_key']: r for r in rows(latest(ext, 'alignment') / 'transformations.jsonl')}
    values, costs, stage_records = {}, {}, {}
    for cohort in COHORTS:
        original = unique(rows(ext / cohort / 'inputs.jsonl'))
        ids = {p for p in original if labels[p]['split'] == 'main' and p != EXCLUDED}
        values[cohort], costs[cohort] = {}, {}
        stage_records[cohort] = {m: defaultdict(list) for m in METHODS}
        pp = {}
        pp['O'] = [r for r in rows(ec['descriptors'][cohort]['O_predictions']) if r['condition'] == 'O']
        pp['TT'] = rows(latest(ext / cohort, 'infer_tt') / 'evaluation/predictions.jsonl')
        pp['CLP'] = rows(latest(ext / cohort, 'infer_clp') / 'evaluation/predictions.jsonl')
        pp['E1_M0'] = rows(ec['descriptors'][cohort]['E1_M0_predictions'])
        if cohort == 'screen':
            done = load(direct_screen / 'COMPLETE.json')
            dwork, ddir = direct_screen, Path(done['rewrite'])
            pp['DIRECT_COPY'] = rows(Path(done['infer']) / 'predictions.jsonl')
            desc = e1c['descriptors'][cohort]
            origin = ROOT / 'artifacts/stem_refinement_2x2_screen_v1'
            invpath = Path(load(origin / 'contract.json')['inventory_path'])
            edir = Path(desc['rewrite'])
            einputs = Path(desc['inputs'])
        else:
            dwork = night / cohort / 'direct'
            ddir = latest(dwork, 'rewrite')
            pp['DIRECT_COPY'] = rows(latest(dwork, 'infer') / 'evaluation/predictions.jsonl')
            origin = eroot / cohort
            invpath = Path(e1c['descriptors'][cohort]['inventory_path'])
            edir = latest(origin / 'E1_M0', 'rewrite')
            einputs = origin / 'inputs.jsonl'
        keys = ('pair_id', 'parallel_id', 'source_language', 'gui_language', 'image_sha256',
                'image_path', 'question_stem', 'options', 'option_order')
        for other in (unique(rows(dwork / 'inputs.jsonl')), unique(rows(einputs))):
            if set(other) != set(original) or any(
                any(other[p][k] != original[p][k] for k in keys) for p in original
            ):
                raise ValueError('Methods have different original MCQ/image/order inputs')
        direct = unique(rows(ddir / 'rewritten.jsonl'))
        e1 = unique(rows(edir / 'rewritten.jsonl'))
        inventory = {r['image_sha256']: r for r in rows(invpath)}
        ex = extraction(origin, 1)
        for p in ids:
            if e1[p]['options'] != original[p]['options']:
                raise ValueError('Stem-only options changed')
            if direct[p]['inventory_used'] or direct[p]['gold_target_used']:
                raise ValueError('Direct rewrite is not inventory/gold-free')
        required = {digest(external_baselines.source_payload(original[p])) for p in ids}
        stage_records[cohort]['TT']['translation'] = [translations[k] for k in sorted(required)]
        stage_records[cohort]['CLP']['alignment'] = [alignments[k] for k in sorted(required)]
        stage_records[cohort]['DIRECT_COPY']['visual_edit'] = [direct[p] for p in sorted(ids)]
        stage_records[cohort]['E1_M0']['inventory'] = [inventory[k] for k in sorted({original[p]['image_sha256'] for p in ids})]
        required = {digest(prompts.extraction_payload(original[p], stem_only=True)) for p in ids}
        stage_records[cohort]['E1_M0']['extraction'] = [ex[k] for k in sorted(required)]
        stage_records[cohort]['E1_M0']['matching'] = [e1[p] for p in sorted(ids)]
        for method in METHODS:
            pred = unique(pp[method])
            if not ids <= set(pred):
                raise ValueError('Missing paired predictions')
            parser = external_baselines.parse_clp_answer if method == 'CLP' else parse_label
            if any(pred[p]['execution_mode'] != 'gpu' or parser(pred[p]['generated_text']) != pred[p]['parsed_generated_label'] for p in ids):
                raise ValueError('Invalid raw GPU predictions')
            values[cohort][method] = {p: int(pred[p]['status'] == 'success' and pred[p]['parsed_generated_label'] == labels[p]['gold_answer']) for p in sorted(ids)}
            answer = batch_share(pp[method], lambda r: r['pair_id'] in ids)
            if answer['selected_rows'] != len(ids):
                raise ValueError('Time/performance denominators differ')
            stages = {k: call_seconds(call_map(v)) for k, v in stage_records[cohort][method].items()}
            costs[cohort][method] = {'stages_seconds': stages, 'answer_seconds': answer['seconds'],
                'preprocessing_seconds': sum(stages.values()), 'total_seconds': sum(stages.values()) + answer['seconds'],
                'n': len(ids), 'batch_allocation': answer}
    values['combined'] = {m: {p: v for c in COHORTS for p, v in values[c][m].items()} for m in METHODS}
    costs['combined'] = {}
    for method in METHODS:
        joined = defaultdict(list)
        for cohort in COHORTS:
            for stage, records in stage_records[cohort][method].items():
                joined[stage].extend(records)
        stages = {stage: call_seconds(call_map(records)) for stage, records in joined.items()}
        answer = sum(costs[c][method]['answer_seconds'] for c in COHORTS)
        costs['combined'][method] = {'stages_seconds': stages, 'answer_seconds': answer,
            'preprocessing_seconds': sum(stages.values()), 'total_seconds': sum(stages.values()) + answer,
            'cohort_total_sum_seconds': sum(costs[c][method]['total_seconds'] for c in COHORTS),
            'n': len(values['combined'][method]),
            'unique_preprocessing_calls': {k: len(call_map(v)) for k, v in joined.items()}}
    summary = {}
    for cohort, group in values.items():
        ids = set(group['O'])
        if any(set(group[m]) != ids for m in METHODS):
            raise ValueError('Unpaired result sets')
        summary[cohort] = {'n': len(ids), 'items': len({labels[p]['parallel_id'] for p in ids}),
            'correct': {m: sum(v.values()) for m, v in group.items()},
            'contrasts': {a + '_minus_' + b: paired_bootstrap(group[a], group[b], labels, 20261115, 10000)
                for a, b in [('TT', 'O'), ('CLP', 'O'), ('DIRECT_COPY', 'O'), ('E1_M0', 'O'), ('DIRECT_COPY', 'TT'), ('E1_M0', 'TT'), ('E1_M0', 'CLP'), ('E1_M0', 'DIRECT_COPY')]},
            'by_gui': {g: {'n': sum(p.endswith('::' + g) for p in ids),
                'correct': {m: sum(v[p] for p in ids if p.endswith('::' + g)) for m, v in group.items()}} for g in ('en', 'zh', 'th', 'ru')}}
    if summary['combined']['n'] != 1895 or summary['combined']['items'] != 158:
        raise ValueError('Unexpected full denominator')
    saved = load(ROOT / 'artifacts/external_baselines_results_snapshot.json')
    for cohort in (*COHORTS, 'combined'):
        for current, historical in [('O', 'O'), ('TT', external_baselines.TT), ('CLP', external_baselines.CLP), ('E1_M0', 'E1_M0')]:
            if summary[cohort]['correct'][current] != saved['summary'][cohort]['correct'][historical]:
                raise ValueError('Previously reported aggregate mismatch')
        if cohort != 'combined':
            for m, key in [('TT', external_baselines.TT), ('CLP', external_baselines.CLP)]:
                expected = saved['costs'][cohort][key]['total_seconds']
                if abs(costs[cohort][m]['total_seconds'] - expected) > 1e-6:
                    raise ValueError(m + ' cost reconstruction mismatch')
    old = load(ROOT / 'artifacts/visual_selective_rewrite_results_snapshot.json')
    screen_history = load(ROOT / 'artifacts/end_to_end_cost_snapshot.json')
    e1old = load(ROOT / 'artifacts/e1_stem_full_dev_results_snapshot.json')
    for cohort in COHORTS:
        if abs(costs[cohort]['E1_M0']['total_seconds'] - e1old['logical_recipe_costs'][cohort]['total_seconds']) > 1e-6:
            raise ValueError('E1/M0 cost reconstruction mismatch')
    snapshot = {'as_of_utc': datetime.now(timezone.utc).isoformat(), 'development_only': True,
        'summary': summary, 'costs': costs, 'TT_quality': saved['quality'],
        'direct_initial_screen': {'correct': 171, 'n': 240, 'time': old['primary_time']},
        'screen_history': screen_history['current'],
        'time_scope': 'Measured GPU call runtimes including repairs; globally deduplicate preprocessing cache keys; charge cached calls original runtime; prorate final batch runtime by selected rows; exclude model load, CPU/startup/orchestration. Not full wall or isolated query latency.',
        'source_and_raw_sha256': captures}
    write(ROOT / 'artifacts/tt_efficiency_comparison_snapshot.json', snapshot)
    emit_report(snapshot)
    print(json.dumps({'summary': summary['combined'], 'costs': costs['combined']}, ensure_ascii=False, indent=2))
    return snapshot


def emit_report(data):
    summary, costs = data['summary'], data['costs']
    total = summary['combined']
    pct = lambda x, n: f'{100*x/n:.2f}%'
    lines = ['# TT·CLP 완료: 성능과 전체 추론 비용 비교', '',
        'Qwen3-VL-8B, B200 MIG 45GB의 기존 측정치를 재집계했다. 추가 GPU 추론은 실행하지 않았다. '
        '주 분석은 동일한 158개 main semantic item·1,895 mismatch pair다. Pilot 48쌍과 기존 사전 제외 1쌍을 제외했다.', '',
        '## 비교 방법', '',
        '- **O:** 원본 MCQ와 screenshot으로 바로 풀이.',
        '- **TT:** 고정 Qwen3-8B LM으로 stem과 A–D 전체를 영어로 번역한 뒤 원래 screenshot으로 풀이. EN source는 그대로 사용한다. Inventory를 사용하지 않는다.',
        '- **CLP:** 같은 고정 LM이 원본 MCQ를 영어로 단계별 이해하고, 이 응답을 assistant 대화로 유지한 채 VLM이 screenshot으로 단계별 풀이한다. Inventory는 없다. LM·VLM 모두 최대 512 tokens이며 마지막 `Answer: A–D`로 채점한다.',
        '- **이미지 직접 rewrite · 원문 복사 강화:** Qwen3-VL-8B가 screenshot과 원본 MCQ를 보고 GUI referent만 바꾸도록 지시받아 완성된 stem/A–D를 출력한다. 같은 VLM이 이를 푼다. Inventory·별도 extractor·고정 LM이 없다. Screen에서 원문 복사를 강조하는 프롬프트로 수정한 뒤 Selection/Internal에는 이를 고정했다.',
        '- **Stem-only GUI · E1/M0:** VLM inventory → 수정 E1 프롬프트로 LM stem referent 추출 → LM GUI-conditioned 교체 표현 선택 → 코드의 stem 치환 → VLM 풀이. Options는 원문 유지.', '',
        '최종 풀이의 checkpoint revision, BF16·SDPA·2MP, batch 3은 같다. CLP 이외에는 greedy label-only 최대 2 tokens, CLP는 별도 대화/system prompt와 최대 512 tokens를 사용한다. 전처리의 입력과 출력 예산도 방법별로 다르다. '
        'TT·CLP는 원 논문의 API 모델을 로컬 Qwen3로 이식한 GUI adaptation이며 원 논문 수치 재현이 아니다.', '',
        '## 전체 158문항: 번역/편집부터 최종 풀이까지', '',
        '| 방법 | 정답/1,895 | 정확도 | O 대비 | 전처리 | 최종 VLM 풀이 | 합계 | 초/pair |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for m in METHODS:
        c, correct = costs['combined'][m], total['correct'][m]
        delta = '—' if m == 'O' else f"{100*(correct-total['correct']['O'])/total['n']:+.2f}pp"
        lines.append(f"| {NAMES[m]} | {correct:,} | {pct(correct,total['n'])} | {delta} | {c['preprocessing_seconds']/60:.2f}분 | {c['answer_seconds']/60:.2f}분 | {c['total_seconds']/60:.2f}분 | {c['total_seconds']/total['n']:.3f} |")
    lines += ['', '전처리에는 inventory, LM 추출·번역·matching 또는 VLM rewrite 중 해당 방법에 필요한 모든 호출과 repair를 포함한다. '
        '공유 전처리는 전체 cohort에서 cache key당 한 번만 계산했다. 캐시로 재사용한 호출도 최초의 측정 시간을 청구하므로 재실행 시 추가 비용과 구분한다.', '',
        '**합계는 기록된 계산 구간의 합이며 작업 시작부터 종료까지의 실제 wall time이 아니다.** 모델 적재, 프로세스 기동, CPU 검증·I/O·대기 시간은 제외한다. '
        '배치 시간은 중복 합산하지 않고 실제 batch size로 나눠 선택된 pair에 배분했다. 초/pair는 처리량 기준의 상각 시간이며 단일 요청 latency가 아니다. '
        '158 semantic item 각각에 여러 source/GUI 조합이 있어 분모는 158이 아닌 1,895 pair다.', '',
        'TT의 전체 영어 번역은 GUI 언어와 무관하므로 632개 고유 source MCQ 중 비영어 474개만 번역해 3개 GUI에 공유하고 영어 158개는 identity 처리한다. '
        '이는 전체 언어쌍을 처리하는 이번 workload에서의 실질적인 비용 이점이다.', '',
        '### 전처리 시간 분해', '',
        '| 방법 | VLM inventory | LM 추출 | LM 번역/matching | LM 영어 이해 | VLM rewrite |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for m in METHODS:
        s = costs['combined'][m]['stages_seconds']
        lines.append(f"| {NAMES[m]} | {s.get('inventory',0)/60:.2f}분 | {s.get('extraction',0)/60:.2f}분 | {(s.get('translation',0)+s.get('matching',0))/60:.2f}분 | {s.get('alignment',0)/60:.2f}분 | {s.get('visual_edit',0)/60:.2f}분 |")
    lines += ['', '## 범위를 맞춘 집합별 결과', '',
        '| 집합 | semantic item | pair | O | TT | CLP | 이미지 직접 rewrite | E1/M0 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for cohort in COHORTS:
        s = summary[cohort]
        lines.append(f"| {cohort} | {s['items']} | {s['n']} | " + ' | '.join(f"{s['correct'][m]}/{s['n']} ({pct(s['correct'][m],s['n'])})" for m in METHODS) + ' |')
    lines += ['', '| 집합 | 방법 | 전체 계산 시간 | 초/pair |', '| --- | --- | ---: | ---: |']
    for cohort in COHORTS:
        for m in METHODS:
            c = costs[cohort][m]
            lines.append(f"| {cohort} | {NAMES[m]} | {c['total_seconds']/60:.2f}분 | {c['total_seconds']/c['n']:.3f} |")
    lines += ['', '전체 비용 표는 cohort 사이의 동일 전처리 호출도 제거한다. 따라서 위 집합별 비용의 단순 합계와 소폭 다를 수 있다. '
        'Selection 비용과 정확도는 사전 제외를 반영한 동일한 239 pair로 다시 계산했다.', '',
        '## 이전 방법까지 같은 Screen 범위로 비교하면', '',
        '다음은 20개 semantic item·240 pair만의 비교다. 전체 158문항 표와 분모를 섞지 않는다. '
        '모든 inventory 기반 방법에는 inventory 추출 비용을 포함했다.', '',
        '| 방법 | 정확도 | 전처리 | 최종 VLM 풀이 | 합계 | 초/pair |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for m in METHODS:
        c, s = costs['screen'][m], summary['screen']
        lines.append(f"| {NAMES[m]} | {pct(s['correct'][m],s['n'])} | {c['preprocessing_seconds']/60:.2f}분 | {c['answer_seconds']/60:.2f}분 | {c['total_seconds']/60:.2f}분 | {c['total_seconds']/c['n']:.3f} |")
    selected = {'TS_FULL_TXT', 'TS_FULL_GUI', 'TS_QSEL_OFULL_GUI_AUTO',
                'TS_STEM_SINGLE_PASS_GUI_AUTO', 'TS_ALL_SINGLE_PASS_GUI_AUTO', 'VISUAL_SELECTIVE_REWRITE'}
    for r in data['screen_history']:
        if r['condition'] not in selected:
            continue
        if r['n'] != 240:
            raise ValueError('Historical Screen denominator differs')
        lines.append(f"| {r['name']} | {pct(r['correct'],r['n'])} | {(r['cold_total_seconds']-r['vlm_seconds'])/60:.2f}분 | {r['vlm_seconds']/60:.2f}분 | {r['cold_total_seconds']/60:.2f}분 | {r['cold_total_seconds']/r['n']:.3f} |")
    lines += ['', 'Hybrid는 stem을 선택적으로 바꾸고 options를 전체 번역한다. `통합 GUI`는 inventory를 LM에게 제공한 뒤 추출과 교체를 한 호출로 합친 조건이다. '
        '`전체 텍스트 번역`은 GUI 언어로 번역하므로 영어 고정 TT와 다르다. '
        'Hybrid와 E1/M0의 Screen 정확도는 모두 74.17%지만 prompt·조작 범위·정답 사례가 같은 방법이라는 뜻은 아니다.', '',
        '## 같은 pair의 회복·회귀와 불확실성', '',
        '| 전체 158문항 비교 | 차이 | 95% item bootstrap CI | 회복 | 회귀 |',
        '| --- | ---: | --- | ---: | ---: |']
    for key, c in total['contrasts'].items():
        a, b = key.split('_minus_')
        lines.append(f"| {NAMES[a]} − {NAMES[b]} | {100*c['difference']:+.2f}pp | [{100*c['ci95'][0]:+.2f}, {100*c['ci95'][1]:+.2f}]pp | {c['recovery']} | {c['regression']} |")
    ratio_direct = costs['combined']['DIRECT_COPY']['total_seconds']/costs['combined']['TT']['total_seconds']
    ratio_e1 = costs['combined']['E1_M0']['total_seconds']/costs['combined']['TT']['total_seconds']
    lines += ['', f"TT는 O보다 정답이 18개 늘었지만 신뢰구간은 0을 포함한다. 이미지 직접 rewrite는 TT보다 점추정이 높고 계산 시간은 약 {ratio_direct:.2f}배다. "
        f"E1/M0는 TT보다 정답이 56개 많고 계산 시간은 약 {ratio_e1:.2f}배다. 비용 대비 선호는 정확도와 자원 제약에 따라 달라진다.", '',
        'CI는 semantic item 단위 10,000회 bootstrap이다. Screen에서 수정한 prompt를 포함하고 과거에 이미 관찰한 개발 집합이므로 '
        '독립적인 최종 일반화 검증이나 확정적 우월성 주장으로 해석하지 않는다. 여러 탐색 비교의 다중 검정 보정은 하지 않았다.', '',
        '## GUI 언어별 전체 결과', '',
        '| GUI | pair | O | TT | CLP | 이미지 직접 rewrite | E1/M0 |', '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for g, s in total['by_gui'].items():
        lines.append(f"| {g.upper()} | {s['n']} | " + ' | '.join(pct(s['correct'][m], s['n']) for m in METHODS) + ' |')
    lines += ['', 'TT는 영어 GUI에서도 영어 source로 바꾸지만 원본 GUI의 문자열을 별도로 확인해 정렬하지 않는다. '
        'GUI별 차이는 번역과 referent 대응, 최종 풀이가 섞인 관찰 결과이며 언어별 정책을 소급 선택하지 않았다.', '',
        '## Inventory 없이 했던 이전 실험을 구분하면', '',
        '사용자가 언급한 조건은 **이미지 직접 rewrite** 계열이다. 이번 전체 비교에는 원문 복사를 강조한 수정 버전을 넣었다. '
        '그 이전 프롬프트는 Screen 240쌍에서 171정답·71.25%, VLM 편집+풀이 12.74분·3.185초/pair였다. '
        '수정 버전은 같은 Screen에서 170정답·70.83%, 11.75분·2.937초/pair였고 이후 Selection/Internal까지 실행됐다. '
        '초기 버전의 71.25%를 수정 버전의 전체 결과와 섞지 않았다.', '',
        '직접 rewrite는 출력된 문장이 문법·JSON 검증을 통과해도 non-referent context나 숫자가 바뀔 수 있다. '
        '원문 복사 강화 버전에도 이런 경고가 남아 있어, 정확도를 strict selective alignment 성공률로 읽으면 안 된다. '
        '기존 `Stem 통합`·`Stem+Options 통합` LM 실험은 inventory를 제공했으므로 inventory-free 조건과 구분한다.', '',
        '## TT·CLP 처리 확인', '',
        'TT는 세 집합 모두 완료 marker와 raw prediction을 확인했다. Primary pair에서 fallback 0, 잘못된 최종 label 0, '
        '번역 출력 길이 제한 도달 0이었다. 숫자 변화 경고는 Screen 0, Selection 3, Internal 6 pair다. '
        '경고는 UI 값 차이 등을 포함할 수 있어 자동 의미 오류 판정으로 취급하지 않는다. '
        '[검토 후보 전체](EXTERNAL_BASELINES_TRANSLATION_AUDIT_KO.md)에 원문과 번역이 있다.', '',
        'CLP도 세 집합 모두 완료됐다. CLP는 최종 label 파싱 실패와 출력 길이 제한 도달이 많아, 낮은 accuracy를 cross-lingual 이해 능력만의 차이로 해석하지 않는다. '
        '[현재 실험 종합과 CLP 출력 진단](CURRENT_EXPERIMENT_SUMMARY_KO.md)에 해당 건수를 구분했다. '
        'R/T/F reference는 병렬·수작업 준비 시간이나 과거 Gemma 번역 시간이 기록되지 않았고 RTX 4090 실행도 섞여 있어 '
        '현재 B200에서 전처리부터 잰 자동 방법의 총시간과 직접 등치하지 않았다. '
        '[기존 Screen 범위 reference/시간 비교](END_TO_END_COST_KO.md)를 함께 참고할 수 있다.', '',
        '재집계: `OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3 .venv/bin/python followup_rel_4lang/method_dev/scripts/compare_tt_efficiency.py`', '',
        '[집계와 사용 파일 SHA-256](../artifacts/tt_efficiency_comparison_snapshot.json) · '
        '[TT/CLP 고정 프로토콜](EXTERNAL_BASELINES_PROTOCOL_KO.md) · '
        '[TT 원시 결과 manifest](../artifacts/external_baselines_archive_manifest.json)', '']
    (ROOT / 'reports/TT_PERFORMANCE_EFFICIENCY_KO.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    main()
