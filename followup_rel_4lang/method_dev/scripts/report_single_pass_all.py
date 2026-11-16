"""Read-only paired analysis of the completed all-field single-pass condition."""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO/'01_code/src'), str(REPO), str(Path(__file__).parent)]
from followup_rel_4lang.method_dev import single_pass_all
from followup_rel_4lang.method_dev.two_stage_v2 import prompts
from mpr_crosslocale.methods.selective_alignment.schemas import digest, fields
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits
from mpr_crosslocale.inference.answer_parser import parse_label
from run_stem_only_gui import read, write, unique
from reference_comparison import load_references
from search_pipeline import paired_bootstrap, EXCLUDED

NAMES = {'O': 'Original O', 'TS_STEM_ONLY_GUI_AUTO': 'Stem-only GUI · 분리',
         'TS_STEM_SINGLE_PASS_GUI_AUTO': 'Stem-only GUI · 통합', 'TS_SEL_GUI_AUTO': 'Stem+Options selective · 분리',
         single_pass_all.CONDITION: 'Stem+Options selective · 통합', 'TS_QSEL_OFULL_GUI_AUTO': 'Hybrid GUI',
         'TS_FULL_GUI': 'Full GUI', 'T_REF': 'T_REF', 'R_REF': 'R_REF', 'F_REF': 'F_REF'}


def unique_calls(rows):
    calls = {}
    for row in rows:
        for call in row['attempts']:
            calls.setdefault(call['cache_key'], call)
    return list(calls.values())


def seconds(calls):
    return sum(c['runtime_ms'] for c in calls)/1000


def collect(output):
    contract = json.loads((output/'contract.json').read_text())
    done = json.loads((output/'COMPLETE.json').read_text())
    if done['execution_mode'] != 'gpu' or done['contract_sha256'] != digest(contract):
        raise ValueError('Completed GPU contract required')
    for filename, sha in contract['source_sha256'].items():
        if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != sha:
            raise ValueError('Frozen source changed: '+filename)
    originals = unique(read(output/'inputs.jsonl'))
    rows = unique(read(Path(done['rewrite'])/'rewritten.jsonl'))
    pred = unique(read(Path(done['infer'])/'predictions.jsonl'))
    inventories = {r['image_sha256']: r for r in read(Path(contract['inventories']))}
    if set(originals) != set(rows) or set(rows) != set(pred) or digest(list(originals.values())) != contract['inputs_sha256']:
        raise ValueError('Incomplete/changed paired inputs')
    labels = {r['pair_id']: r for r in read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl')}
    if digest(labels) != contract['labels_sha256']:
        raise ValueError('Labels changed')
    ids = sorted(p for p in originals if labels[p]['split'] == 'main' and p != EXCLUDED)
    for p, row in rows.items():
        for k in ('parallel_id','source_language','gui_language','image_path','image_sha256','option_order'):
            if row[k] != originals[p][k]:
                raise ValueError('Paired identity changed')
        if apply_edits(originals[p], row['edits']) != fields(row):
            raise ValueError('Context outside edits changed')
        if pred[p]['execution_mode'] != 'gpu' or pred[p]['parsed_generated_label'] != parse_label(pred[p]['generated_text']):
            raise ValueError('Invalid raw prediction')
    result = json.loads((output/'results.json').read_text())
    def correct(row, p):
        return int(row['status'] == 'success' and row['parsed_generated_label'] == labels[p]['gold_answer'])
    values = {single_pass_all.CONDITION: {p: correct(pred[p], p) for p in ids}}
    lookup = {(c,p): r for path in ('source_predictions','stem_predictions','single_pass_stem_predictions')
              for r in read(Path(contract[path])) for c,p in [(r['condition'],r['pair_id'])]}
    for c in result['correct']:
        if c != single_pass_all.CONDITION:
            values[c] = {p: correct(lookup[c,p], p) for p in ids}
        if sum(values[c].values()) != result['correct'][c]:
            raise ValueError('Saved accuracy mismatch')
    captures = {}
    def use(path):
        captures[str(path.relative_to(REPO))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path
    refs, metadata, _ = load_references(REPO, {p: labels[p] for p in ids}, {'screen': originals}, use,
        contract['downstream']['model_config'], contract['config']['historical_baseline_contract_sha256'])
    for profile in metadata['source_runs'].values():
        if profile['model_config'] != contract['downstream']['model_config'] or profile['system_prompt'] != contract['downstream']['system_prompt']:
            raise ValueError('Reference model/system differs')
    for c in ('T_REF','R_REF','F_REF'):
        values[c] = {p: correct(refs[c][p], p) for p in ids}
    base_done = json.loads((Path(contract['source_cohort'])/'COMPLETE.json').read_text())
    mainrows = [originals[p] for p in ids]
    costs = {}
    for name, stage, condition, stem_only in [('Stem-only 분리','extract_stem','TS_QSEL_OFULL_GUI_AUTO',True),
                                               ('All-field 분리','extract','TS_SEL_GUI_AUTO',False)]:
        keys = {digest(prompts.extraction_payload(r, stem_only=stem_only)) for r in mainrows}
        extraction = [r for r in read(Path(base_done[stage])/'extractions.jsonl') if r['source_key'] in keys]
        translated = [r for r in read(Path(base_done['rewrite'])/(condition+'.jsonl')) if r['pair_id'] in ids]
        align_calls = unique_calls(translated)
        if stem_only:
            align_calls = [a for a in align_calls if a['component'] == 'stem_alignment']
        extraction_calls = unique_calls(extraction)
        costs[name] = {'extraction_seconds': seconds(extraction_calls), 'alignment_seconds': seconds(align_calls),
                    'total_seconds': seconds(extraction_calls)+seconds(align_calls), 'calls': len(extraction_calls)+len(align_calls)}
    stem_root = ROOT/'artifacts/single_pass_stem_screen_v1'
    stem_done = json.loads((stem_root/'COMPLETE.json').read_text())
    stem_rows = unique(read(Path(stem_done['rewrite'])/'rewritten.jsonl'))
    input_comparison = {'same_stem_as_stem_single_pass': sum(rows[p]['question_stem'] == stem_rows[p]['question_stem'] for p in ids),
                        'different_stem_from_stem_single_pass': sum(rows[p]['question_stem'] != stem_rows[p]['question_stem'] for p in ids)}
    for name, selected in [('Stem-only 통합', [stem_rows[p] for p in ids]), ('All-field 통합', [rows[p] for p in ids])]:
        calls = unique_calls(selected)
        costs[name] = {'total_seconds': seconds(calls), 'calls': len(calls),
                       'repairs': sum(c['stage'].endswith('_repair') for c in calls),
                       'input_tokens': sum(c['input_tokens'] for c in calls), 'output_tokens': sum(c['output_tokens'] for c in calls),
                       'token_cap_hits': sum(c['output_tokens'] == c['generation']['max_new_tokens'] for c in calls)}
    previous_failures = json.loads((ROOT/'artifacts/single_pass_stem_results_snapshot.json').read_text())['failure_examples']
    option_scope_ids = [r['pair_id'] for r in previous_failures if r['option_only_source_text']]
    tracked = [{'pair_id': p, 'status': rows[p]['status'], 'edits': len(rows[p]['edits']),
                'old_label': lookup['TS_STEM_SINGLE_PASS_GUI_AUTO',p]['parsed_generated_label'],
                'new_label': pred[p]['parsed_generated_label'], 'gold': labels[p]['gold_answer'],
                'old_correct': values['TS_STEM_SINGLE_PASS_GUI_AUTO'][p], 'new_correct': values[single_pass_all.CONDITION][p]}
               for p in option_scope_ids]
    failures = []
    for p in ids:
        row = rows[p]
        if row['status'] != 'fallback_original' or not row['attempts']:
            continue
        try:
            response = json.loads(row['attempts'][-1]['raw_output'])
            proposals = response.get('edits', []) if isinstance(response, dict) else []
        except ValueError:
            proposals = []
        usable = []
        for proposal in proposals if isinstance(proposals, list) else []:
            try:
                _, _, edits = single_pass_all.validate_edits(originals[p], inventories[row['image_sha256']],
                    json.dumps({'edits': [proposal]}, ensure_ascii=False))
                usable += edits
            except (ValueError, KeyError, TypeError):
                pass
        failures.append({'pair_id': p, 'errors': row['errors'], 'valid_single_edits_discarded': len(usable),
                         'raw_output': row['attempts'][-1]['raw_output']})
    contrasts = {c: paired_bootstrap(values[single_pass_all.CONDITION], v, labels, 20261115, 10000)
                 for c,v in values.items() if c != single_pass_all.CONDITION}
    for c, prior in result['contrasts'].items():
        if contrasts[c] != prior:
            raise ValueError('Saved paired contrast mismatch')
    manifest = {str((Path(done[s])/f).relative_to(REPO)): hashlib.sha256((Path(done[s])/f).read_bytes()).hexdigest()
                for s,f in [('rewrite','rewritten.jsonl'),('rewrite','calls.json'),('infer','predictions.jsonl')]}
    snapshot = {'results': result, 'references': {c: sum(values[c].values()) for c in ('T_REF','R_REF','F_REF')},
                'contrasts': contrasts, 'main_lm_costs': costs, 'previous_option_scope_failures': tracked,
                'input_comparison': input_comparison,
                'validation_failure_examples': failures, 'reference_metadata': metadata,
                'source_captures': captures, 'contract_sha256': digest(contract), 'raw_manifest': manifest}
    return snapshot, values, labels, rows, pred, lookup


def main():
    output = ROOT/'artifacts/single_pass_all_screen_v1'
    contract = json.loads((output/'contract.json').read_text())
    lines = ['# Stem+Options referents 통합 실험', '',
        '원본 MCQ와 완료 GUI inventory를 고정 Qwen3-8B에 함께 주고, **stem과 A–D의 referents를 한 번의 기본 호출에서 찾아 정렬**한다. 코드가 검증된 부분만 치환하고 모든 나머지 문맥을 유지한다. Options 전체 번역인 Hybrid와 다르다.', '',
        '기존 Screen을 관찰한 뒤 추가한 개발 실험이다. 범위 변경과 field 출력 인터페이스의 효과를 포함하며, selectivity 하나의 순수 인과 효과나 독립 최종 검증으로 해석하지 않는다. 프롬프트 한 버전을 고정했으며 결과를 보고 변경하거나 추가 sweep을 하지 않았다.', '',
        '## 범위·고정 설정', '',
        'Screen288쌍을 실행하고 main20 semantic item×12방향=240쌍을 주 분석에 사용한다. Legacy pilot48쌍은 주 분석에서 제외한다. 모든 pair ID·이미지 SHA·정답·A–D 순서는 동일하고 실패도 원문 fallback으로 분모에 남긴다.', '',
        '- Inventory: 완료된 평가 VLM의 query-blind inventory를 그대로 재사용.',
        '- 변환 LM: Qwen3-8B, revision `47719a242beab8f9aecc40ce3928b034dd5dd559`.',
        '- 평가 VLM: Qwen3-VL-8B-Instruct, revision `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`.',
        '- BF16·SDPA·greedy·seed42·LM batch1·thinking=false·출력512토큰. 검증 실패 시 같은 예산의 repair 최대1회.',
        '- 전체 응답 fallback, inventory의 원시 문자열만 허용, 새 중복 보기 거부. 개별 edit만 살리는 정책은 도입하지 않았다.',
        '- 평가 batch3·출력2토큰·기존 system/label scoring/이미지 처리 설정 유지. 두 모델은 별도 subprocess에서 순차 적재.',
        '- 사전 tokenizer 검사: 최대 입력1388, repair 보수적 여유 포함2150토큰으로4096한도 안. 이전 실측 LM15.83/VLM18.70GiB 대비 현재45GB MIG에 여유가 있음.', '',
        '## 결과', '']
    if (output/'COMPLETE.json').exists():
        snapshot, values, labels, rows, pred, lookup = collect(output)
        result = snapshot['results'];n = result['primary_pairs']
        contrast = snapshot['contrasts']['TS_STEM_SINGLE_PASS_GUI_AUTO']
        hybrid_difference = sum(values[single_pass_all.CONDITION].values())-sum(values['TS_QSEL_OFULL_GUI_AUTO'].values())
        lines += [f"**새 통합 조건은{sum(values[single_pass_all.CONDITION].values())}/{n}={sum(values[single_pass_all.CONDITION].values())/n:.2%}**다. Stem 전용 통합 대비{contrast['difference']*100:+.2f}pp, 95% item bootstrap CI[{contrast['ci95'][0]*100:+.2f}, {contrast['ci95'][1]*100:+.2f}]pp로 우위를 확정하지 않는다. Hybrid와의 정답 수 차이는{hybrid_difference:+d}개이며, 아래 비용·오류도 함께 평가한다.", '']
        lines += ['| 조건 | 정답 | 정확도 |', '| --- | ---: | ---: |']
        for c in ('O','TS_FULL_GUI','TS_SEL_GUI_AUTO','TS_STEM_ONLY_GUI_AUTO','TS_STEM_SINGLE_PASS_GUI_AUTO',single_pass_all.CONDITION,'TS_QSEL_OFULL_GUI_AUTO','T_REF','R_REF','F_REF'):
            lines.append(f'| {NAMES[c]} | {sum(values[c].values())}/{n} | {sum(values[c].values())/n:.2%} |')
        lines += ['', '| All-field 통합 − 기준 | 차이 | 95% item bootstrap CI | 회복/회귀 |', '| --- | ---: | --- | ---: |']
        for c, r in snapshot['contrasts'].items():
            lines.append(f"| {NAMES[c]} | {r['difference']*100:+.2f}pp | [{r['ci95'][0]*100:+.2f}, {r['ci95'][1]*100:+.2f}] | {r['recovery']}/{r['regression']} |")
        lines += ['', 'Semantic item 단위10,000회 bootstrap이다. 다수의 개발용 탐색 비교이며 독립적인 확증적 유의성을 주장하지 않는다.', '',
                  f"Stem 전용 통합과 실제 stem이 같은 것은{snapshot['input_comparison']['same_stem_as_stem_single_pass']}/{n}쌍이고, {snapshot['input_comparison']['different_stem_from_stem_single_pass']}쌍은 stem도 달라졌다. 따라서 정답 수 차이를 options 편집만의 순수 효과로 해석하지 않는다.", '',
                  'T_REF는 gold span+Gemma 번역, R_REF는 gold span+parallel referent, F_REF는 parallel 전체 localization이다. 같은 pair·gold·model/system은 검사했지만 과거 RTX4090·batch/queue 차이가 있다. R/F가 실제 screenshot exact-label oracle이라는 뜻은 아니다.', '',
                  '### GUI 언어별', '', '| GUI | n | O | Stem 통합 | All-field 통합 | All-field 분리 |', '| --- | ---: | ---: | ---: | ---: | ---: |']
        for g, group in result['by_gui'].items():
            q=group['correct'];d=group['n']
            lines.append(f"| {g.upper()} | {d} | {q['O']/d:.2%} | {q['TS_STEM_SINGLE_PASS_GUI_AUTO']/d:.2%} | {q[single_pass_all.CONDITION]/d:.2%} | {q['TS_SEL_GUI_AUTO']/d:.2%} |")
        lines += ['', '### 변환 비용: Step 2 추출을 포함', '', '| 방식 | 추출·분 | 정렬·분 | 합계·분 | 고유 LM 호출 |', '| --- | ---: | ---: | ---: | ---: |']
        for name, c in snapshot['main_lm_costs'].items():
            lines.append(f"| {name} | "+(f"{c['extraction_seconds']/60:.2f} | {c['alignment_seconds']/60:.2f}" if 'extraction_seconds' in c else '통합 | 통합')+f" | {c['total_seconds']/60:.2f} | {c['calls']} |")
        costs = snapshot['main_lm_costs']
        all_separate = costs['All-field 분리']
        cap_main = costs['All-field 통합']['token_cap_hits']
        lines += ['', '위 표는 같은 main240쌍의 실제 call runtime을 고유 cache key별 한 번 합산했다. Source 추출은 고유 source80개만 계산하며 세 GUI에 재사용한다. Repair를 포함하고 inventory·VLM 문제 풀이·모델 cold-load는 제외한다. 호출을 합쳐도 출력 길이와 repair가 늘면 시간이 줄지 않을 수 있다.', '',
                  f"이번 main의 LM 시간은 Stem 전용 통합{costs['Stem-only 통합']['total_seconds']/60:.2f}분→All-field 통합{costs['All-field 통합']['total_seconds']/60:.2f}분이다. 같은 전체 필드 범위의 분리 방식은 추출{all_separate['extraction_seconds']/60:.2f}분+정렬{all_separate['alignment_seconds']/60:.2f}분={all_separate['total_seconds']/60:.2f}분이다. 정확도와 속도를 별도로 판단한다. 실행 시점과 출력 길이 등의 영향을 포함한 현재 서버 실측이며 장비의 보편적 처리 속도라고 주장하지 않는다.", '',
                  '### 처리 상태·실패', '', '```json', json.dumps({k: result[k] for k in ('status','fallback_reasons','edits','edits_by_field','changed_stem_pairs','changed_options_pairs','token_cap_hits','label_changes_without_input_change','cost')}, ensure_ascii=False, indent=2), '```', '',
                  f"위 cost·token_cap_hits는 실제 실행{result['executed_pairs']}쌍 기준이고 status·fallback·edits는 main{n}쌍 기준이다. 출력 한도 도달 호출은 전체{result['token_cap_hits']}회, main{cap_main}회, 그 외{result['token_cap_hits']-cap_main}회다. 최종 main fallback{result['status'].get('fallback_original',0)}쌍의 사유는 위 fallback_reasons에 있다. Source substring 복원 불가에 따른 main 최종 실패는{result['fallback_reasons'].get('Span cannot be recovered from original text',0)}쌍이다.", '',
                  '### 직전 options 범위 위반12쌍 추적', '', '| Pair | 새 상태 | 편집 수 | 이전 label | 새 label | GT |', '| --- | --- | ---: | --- | --- | --- |']
        for r in snapshot['previous_option_scope_failures']:
            lines.append(f"| `{r['pair_id']}` | {r['status']} | {r['edits']} | {r['old_label']} | {r['new_label']} | {r['gold']} |")
        tracked = snapshot['previous_option_scope_failures']
        lines += ['', f"{len(tracked)}쌍 중{sum(t['edits']>0 for t in tracked)}쌍은 이번에 유효한 편집이 적용됐고{sum(t['status']=='fallback_original' for t in tracked)}쌍은 여전히 fallback이다. 이 subset의 정답 수는 이전{sum(t['old_correct'] for t in tracked)}개→이번{sum(t['new_correct'] for t in tracked)}개, 정오 회복/회귀는{sum(t['new_correct']>t['old_correct'] for t in tracked)}/{sum(t['new_correct']<t['old_correct'] for t in tracked)}이다. 범위 위반 해결과 실제 REL 정답 회복은 구분한다.", '',
                  '유효한 편집 적용과 REL 정답 회복은 별개다. 출력 형식을 통과했다는 사실만으로 번역이나 실제 GUI 대응의 의미 정확도를 보장하지 않는다.', '', '### 최종 검증 실패 원시 응답 예시', '']
        for r in snapshot['validation_failure_examples'][:3]:
            lines += [f"`{r['pair_id']}` · {'; '.join(r['errors'])} · 단독 적용 가능한데 함께 버린 편집{r['valid_single_edits_discarded']}개", '', '````json', r['raw_output'], '````', '']
        lines += ['### Stem 통합 대비 회복·회귀 예시', '',
                  'Pair ID 순서로 각3개를 고른 관찰 사례다. 정답 전환을 보여주며 번역 의미·실제 GUI 대응의 독립 검수 결과는 아니다.', '']
        originals = unique(read(output/'inputs.jsonl'))
        stem_root = ROOT/'artifacts/single_pass_stem_screen_v1'
        stem_done = json.loads((stem_root/'COMPLETE.json').read_text())
        stem_rows = unique(read(Path(stem_done['rewrite'])/'rewritten.jsonl'))
        for kind in ('회복','회귀'):
            chosen = [p for p in sorted(values[single_pass_all.CONDITION])
                      if (values[single_pass_all.CONDITION][p] > values['TS_STEM_SINGLE_PASS_GUI_AUTO'][p] if kind == '회복'
                          else values[single_pass_all.CONDITION][p] < values['TS_STEM_SINGLE_PASS_GUI_AUTO'][p])]
            for p in chosen[:3]:
                lines += [f"**{kind}: `{p}`** · GT {labels[p]['gold_answer']} · Stem 통합 {lookup['TS_STEM_SINGLE_PASS_GUI_AUTO',p]['parsed_generated_label']} → All-field 통합 {pred[p]['parsed_generated_label']}", '',
                          '```json', json.dumps({'O': fields(originals[p]), 'Stem 통합': fields(stem_rows[p]),
                                               'All-field 통합': fields(rows[p])}, ensure_ascii=False, indent=2), '```', '']
        write(ROOT/'artifacts/single_pass_all_results_snapshot.json', snapshot)
        cases = ['# Stem+Options 통합: 전체 실행 예측', '', 'Main240쌍과 legacy pilot48쌍을 구분한다. 실패도 포함하며 완성된 raw output의 parser label을 표시한다. `None`은 정답 파싱 실패다.', '']
        for split in ('main','pilot'):
            cases += [f'## {split}', '', '| Pair | GT | O | Stem 통합 | All-field 통합 | 상태 | 편집 |', '| --- | --- | --- | --- | --- | --- | ---: |']
            for p in sorted(rows):
                if labels[p]['split'] != split:
                    continue
                cases.append(f"| `{p}` | {labels[p]['gold_answer']} | {lookup['O',p]['parsed_generated_label']} | {lookup['TS_STEM_SINGLE_PASS_GUI_AUTO',p]['parsed_generated_label']} | {pred[p]['parsed_generated_label']} | {rows[p]['status']} | {len(rows[p]['edits'])} |")
        (ROOT/'reports/SINGLE_PASS_ALL_CASES_KO.md').write_text('\n'.join(cases)+'\n')
        lines += ['[실행288쌍의 전체 결과 표](SINGLE_PASS_ALL_CASES_KO.md). 변환 전후 MCQ·options·모든 proposal·실제 prompt·raw output은 아래 로컬 artifact에 보존했다.', '']
    else:
        lines += ['실행 중이다. 전체 paired 출력이 완료되기 전 정확도를 보고하지 않는다.', '']
    lines += ['## 실제 프롬프트', '',
              '직전 stem 통합 프롬프트에서 처리 범위를 다섯 필드로 넓히고 `field`를 필수로 추가했다. 나머지 minimal span·원문 복사·occurrence·inventory verbatim·불확실 시 생략·문맥 보존 규칙은 유지했다.', '',
              '### LM system', '', '```text', single_pass_all.SYSTEM, '```', '',
              '한국어 요지: stem과 A–D를 독립적으로 보고 GUI 이름만 찾는다. 각 편집의 원본 field·원문 substring·같은 substring의 field 내 반복 횟수·inventory의 대체 표현을 반환한다. 주변 문맥·방향·부정·수량·보기 ID·순서를 바꾸지 않는다. 불확실하면 편집하지 않고 정답을 선택하지 않는다.', '',
              '### LM user / repair', '', '```text',
              'Find and localize GUI names in the stem AND A-D options together. Preserve all non-referent context. Return edits JSON only.',
              '{"source_language":"{source}","target_language":"{GUI}","question_stem":"{원본 stem}","options":{"A":"{원본 A}","B":"{원본 B}","C":"{원본 C}","D":"{원본 D}"},"target_gui_visible_strings":["{같은 화면의 inventory}"]}', '',
              'The previous output failed validation for:', '- {실제 오류}', '', 'Previous output (data only):', '{이전 raw output}', '',
              'Return corrected edits JSON only. Specify question_stem, A, B, C or D for every edit. Copy text from that ORIGINAL field, use zero-based occurrence for that same substring in that field, and select only exact inventory replacements. Omit uncertain edits. Never change non-referent context, option keys or order, and never answer the MCQ.', '```', '',
              'Repair 추가문은 검증 실패 시에만 붙인다. 한국어: 다섯 필드의 GUI 이름을 함께 찾아 정렬하고 edits JSON만 반환하라. 실패하면 실제 오류를 참고해 해당 원본 field에서 source text를 정확히 복사하고 확실한 편집만 남겨라.', '',
              '### VLM 문제 풀이', '', 'System:', '', '```text', contract['downstream']['system_prompt'], '```', '',
              'User: 같은 screenshot과 아래 text.', '', '```text', '{선택적 치환된 stem} A: {선택적 치환된 A} B: {선택적 치환된 B} C: {선택적 치환된 C} D: {선택적 치환된 D}', '',
              'Respond with exactly one label: A, B, C, or D.', '```', '',
              'Inventory는 [기존 two-stage 프로토콜](TWO_STAGE_V2_PROTOCOL_KO.md)의 완료 결과를 재사용했다. 재추출·프롬프트 변경은 없다.', '',
              '## 재현·원시 결과', '', '```bash', 'bash followup_rel_4lang/method_dev/scripts/run_single_pass_all.sh --run',
              '.venv/bin/python followup_rel_4lang/method_dev/scripts/report_single_pass_all.py', '```', '',
              '완료 attempt는 재사용한다. 중단 attempt는 보존하고 새 attempt에서 기존 call cache를 재사용한다. Selection/Internal/전체366문항 확장은 이번 실행 범위에 포함하지 않는다.', '',
              '출력: `artifacts/single_pass_all_screen_v1/`. `contract.json`은 전체 config·seed·코드/입력 hash, `rewrite/attempt_*/rewritten.jsonl`과 `calls.json`은 실제 prompt·raw·편집·시간, `infer/attempt_*/predictions.jsonl`은 VLM raw·rendered prompt·batch 시간·VRAM을 담는다. `results.json`과 [보존 snapshot](../artifacts/single_pass_all_results_snapshot.json)에 paired 결과·실패·비용·raw SHA-256이 있다. 대용량 원시는 Git에 추가하지 않는다.', '']
    (ROOT/'reports/SINGLE_PASS_ALL_GUI_KO.md').write_text('\n'.join(lines))
    print(ROOT/'reports/SINGLE_PASS_ALL_GUI_KO.md')


if __name__ == '__main__':
    main()
