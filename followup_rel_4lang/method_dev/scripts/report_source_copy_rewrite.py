"""Post-hoc failure analysis and one copy-first revision report; no generation."""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO/'01_code/src'), str(REPO), str(Path(__file__).parent)]
from report_visual_selective_rewrite import collect, protected_context_matches, normalize_context
from run_stem_only_gui import read, write, unique
from compare_end_to_end import batch_share, call_map, call_seconds
from search_pipeline import paired_bootstrap, EXCLUDED
from mpr_crosslocale.methods.selective_alignment.schemas import fields, FIELDS, digest
from mpr_crosslocale.inference.answer_parser import parse_label
from followup_rel_4lang.method_dev import source_copy_rewrite as method

OLD = 'VISUAL_SELECTIVE_REWRITE'
NAMES = {OLD:'Screenshot 직접 rewrite · 이전',method.CONDITION:'Screenshot 직접 rewrite · 원문 복사 강화',
    'O':'Original O','R_REF':'R_REF','T_REF':'T_REF','F_REF':'F_REF',
    'TS_QSEL_OFULL_GUI_AUTO':'Hybrid GUI','TS_ALL_SINGLE_PASS_GUI_AUTO':'Stem+Options 통합 · inventory',
    'TS_STEM_ONLY_GUI_AUTO':'Stem 분리 · inventory','TS_STEM_SINGLE_PASS_GUI_AUTO':'Stem 통합 · inventory',
    'TS_FULL_GUI':'Full GUI','TS_SEL_GUI_AUTO':'Selective GUI Auto','GUI_DIRECT_VLM_OLD':'과거 edit 목록 VLM'}


def audit(rows, originals, annotations, ids):
    result = []
    for p in ids:
        before, after = fields(originals[p]), fields(rows[p]); spans = annotations[p]['referents']
        literal = [f for f in FIELDS if not protected_context_matches(before[f], after[f], [s for s in spans if s['field']==f])]
        normalized = [f for f in FIELDS if not protected_context_matches(before[f], after[f], [s for s in spans if s['field']==f], normalize_context)]
        result.append(dict(pair_id=p, source_language=rows[p]['source_language'], gui_language=rows[p]['gui_language'],
            changed=before!=after, literal_compatible=not literal, format_compatible=not normalized,
            format_flagged_fields=normalized, literal_flagged_fields=literal,
            digit_changed_fields=rows[p]['diagnostics']['digit_sequence_changed_fields'],
            new_duplicate_options=rows[p]['diagnostics']['new_duplicate_options'], source=before, rewritten=after))
    return result


def failure_report(snapshot, values, labels):
    audits = snapshot['audits']; old = values[OLD]
    wrong = [a for a in audits if not old[a['pair_id']]]
    n = len(audits)
    lines = ['# Screenshot 직접 rewrite: 수정 전 실패 분석','',
        'Main20개 semantic item·240쌍, 이전 조건171정답·69오답. 기존 예측과 원시 출력만 읽었다. 생성·fallback 규칙을 소급 변경하지 않았다.','',
        '| 정오 | 문맥 호환 | 문맥 경고 | 합계 |','| --- | ---: | ---: | ---: |']
    for flag, name in [(True,'정답'),(False,'오답')]:
        group=[a for a in audits if bool(old[a['pair_id']])==flag]
        compatible=sum(a['format_compatible'] for a in group)
        lines.append(f'| {name} | {compatible} | {len(group)-compatible} | {len(group)} |')
    lines += ['', '문맥 호환은 source annotation 바깥의 문자를 보존했을 가능성을 뜻한다. 올바른 target label을 고른 증거가 아니다. 공백·구두점·대소문자 차이는 허용했다. Annotation 누락도 경고를 만들 수 있어 이 표를 의미 오류율이나 인과적 오답 분해로 해석하지 않는다.','',
        '| Source | O 정답 | 이전 rewrite 정답 | R 정답 | 문맥 경고 | O→rewrite 회귀 |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for lang in ('en','zh','th','ru'):
        ids=[a['pair_id'] for a in audits if a['source_language']==lang]
        lines.append(f"| {lang.upper()} | {sum(values['O'][p] for p in ids)}/60 | {sum(old[p] for p in ids)}/60 | {sum(values['R_REF'][p] for p in ids)}/60 | {sum(a['source_language']==lang and not a['format_compatible'] for a in audits)}/60 | {sum(values['O'][p] and not old[p] for p in ids)} |")
    rwrong=[a for a in wrong if values['R_REF'][a['pair_id']]]
    lines += ['', f"R이 맞히고 이전 rewrite가 틀린 것은 {len(rwrong)}쌍이다. 이 중 문맥 경고 {sum(not a['format_compatible'] for a in rwrong)}쌍, 문맥 호환 {sum(a['format_compatible'] for a in rwrong)}쌍이다. 전체 오답69쌍 중 숫자 변화 {sum(bool(a['digit_changed_fields']) for a in wrong)}쌍, 보기 중복 {sum(a['new_duplicate_options'] for a in wrong)}쌍이다. 이 분류는 서로 배타적인 오류 원인 분해가 아니다.",'',
        '## 실제 출력에서 확인한 문제','',
        '1. **문맥 통번역:** 비영어 원문의 질문 문맥을 GUI 언어로 바꾼다. 정답에서도 많이 발생하므로 정확도만으로 selective 규칙 준수를 검증할 수 없다.',
        '2. **기준 요소 정체성 변경:** `note_1` EN→TH에서 Draw with Finger를 Auto-minimize에 해당하는 화면의 위쪽 행 이름으로 바꿨다. Screenshot을 직접 확인하면 Auto-minimize·Draw with Finger·Pencil Settings 순으로 별개 행이다. 위치 관계로 답을 찾는 작업과 원래 이름의 대응을 찾는 작업이 섞일 수 있다.',
        '3. **달력 값 변경:** `calendar_6` EN→TH에서 Thursday를 พุธ.(Wednesday)로, Tuesday를 จันทร์(Monday)로 바꿨다. 숫자가 없어 digit 검사로 잡히지 않으며 source span 내부라 문맥 검사도 통과한다. 날짜·요일 identity 보존이 필요하다. 다만 병렬 GUI 화면 자체의 날짜 차이는 데이터 검토와 구별해야 한다.',
        '4. **실제 데이터 대응 오류:** `map_9` Thai source의 เลี่ยงทางหลวง는 Avoid Highways를 뜻하나, 기존 mapping audit에는 Avoid Tolls 자리에 들어간 `mapping_error`로 이미 기록돼 있다. TH→EN/RU/ZH의 3쌍은 reference와의 불일치만으로 새 방법의 오역으로 단정할 수 없다. 원문·GT를 고치거나 이 3쌍을 분모에서 빼지 않았다.',
        '5. **정상 수정 후 남은 실패:** 문맥 호환 오답16쌍에는 잘못된 referent 대응과 실제 downstream REL 실패가 섞일 수 있다. 모든 오답을 문맥 번역 탓으로 돌리거나, R의 정답을 실제 화면 label의 oracle로 간주하지 않는다.','',
        '6. **번역만으로 설명되지 않는 공통 실패:** `music_3`은 O·R·F·이전 직접 rewrite 모두 0/12다. EN→ZH 생성은 화면의 #1 共5首歌와 #3 共4首歌를 대응시켰고, 화면에서도 #3이 #1 위에 놓여 있다. `wallet_8`도 R·F가 0/12다. 이 두 문항의 이전 오답22쌍을 모두 localization 실패로 셀 수는 없다. Downstream의 공간 관계 처리나 데이터/프롬프트 해석을 따로 검토해야 하며, 이번에는 정답/문항을 수정하지 않는다.','',
        '## 문항별 반복 실패','',
        '| Semantic item | O | 이전 rewrite | R | F | Inventory 통합 |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for item in sorted({labels[p]['parallel_id'] for p in old}):
        ids = [p for p in old if labels[p]['parallel_id']==item]
        scores = [sum(values[c][p] for p in ids) for c in ('O',OLD,'R_REF','F_REF','TS_ALL_SINGLE_PASS_GUI_AUTO')]
        lines.append('| `'+item+'` | '+' | '.join(f'{x}/12' for x in scores)+' |')
    lines += ['', '같은 semantic item의12방향은 독립 문항12개가 아니다. 특정 문항에 몰린 실패와 언어쌍 전반의 실패를 구별하기 위한 표다.','',
        '## 이번 수정으로 검증하는 범위','',
        '원문 복사·비영어 예시·같은 요소 identity·요일 보존 지시를 한 프롬프트에 고정했다. Gold 기반 validator나 추가 모델은 넣지 않았다. 따라서 결과는 이 prompt bundle의 효과이며 각 문장/예시의 개별 효과를 분리하지 않는다. 모든 fallback을 포함한 정확도와 수정 coverage를 함께 평가한다.','',
        '## 전체 오답69쌍','', '| Pair | GT | O | 이전 rewrite | R | 문맥 경고 field | 숫자 | 중복 |','| --- | --- | --- | --- | --- | --- | --- | --- |']
    for a in wrong:
        p=a['pair_id']
        # Labels alone are provided here for case navigation; raw outputs stay in the appendix.
        lines.append(f"| `{p}` | {labels[p]['gold_answer']} | {'정답' if values['O'][p] else '오답'} | 오답 | {'정답' if values['R_REF'][p] else '오답'} | {', '.join(a['format_flagged_fields']) or '없음'} | {','.join(a['digit_changed_fields']) or '-'} | {'yes' if a['new_duplicate_options'] else '-'} |")
    lines += ['', '[69쌍의 원문과 생성문 전체](VISUAL_REWRITE_FAILURE_CASES_KO.md). 조건별 전체288쌍 label은 [기존 표](VISUAL_SELECTIVE_REWRITE_CASES_KO.md)에 있다.','']
    (ROOT/'reports/VISUAL_REWRITE_FAILURES_KO.md').write_text('\n'.join(lines))
    details=['# 수정 전 오답69쌍: 원문과 생성문','', 'Post-hoc 검토용. 생성 모델에 제공되지 않은 평가 자료다.','']
    for a in wrong:
        p=a['pair_id'];details += [f'## {p}','',f"GT {labels[p]['gold_answer']}; 문맥 경고: {', '.join(a['format_flagged_fields']) or '없음'}.",'','```json',json.dumps({'source':a['source'],'rewrite':a['rewritten']},ensure_ascii=False,indent=2),'```','']
    (ROOT/'reports/VISUAL_REWRITE_FAILURE_CASES_KO.md').write_text('\n'.join(details))


def main():
    oldout=ROOT/'artifacts/visual_selective_rewrite_screen_v1'
    previous,values,labels,oldrows,oldpred,lookup=collect(oldout)
    failure_report(previous,values,labels)
    output=ROOT/'artifacts/visual_source_copy_rewrite_screen_v1'
    if not (output/'COMPLETE.json').exists():
        print('Failure report complete; revised run not finished');return
    c=json.loads((output/'contract.json').read_text());done=json.loads((output/'COMPLETE.json').read_text())
    if done['execution_mode']!='gpu' or done['contract_sha256']!=digest(c):raise ValueError('Not a completed GPU contract')
    for name,sha in c['source_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha:raise ValueError('Captured source changed: '+name)
    originals=unique(read(output/'inputs.jsonl')); rows=unique(read(Path(done['rewrite'])/'rewritten.jsonl'))
    preds=read(Path(done['infer'])/'predictions.jsonl');pred=unique(preds)
    if set(originals)!=set(rows) or set(rows)!=set(pred):raise ValueError('Incomplete paired data')
    ids=sorted(values[OLD]);n=len(ids)
    values[method.CONDITION]={p:int(pred[p]['status']=='success' and parse_label(pred[p]['generated_text'])==labels[p]['gold_answer']) for p in ids}
    annotations=unique(read(ROOT/'artifacts/dataset_audit/oracle_spans_DIAGNOSTIC_ONLY.jsonl'))
    audits=audit(rows,originals,annotations,ids)
    calls=call_map([rows[p] for p in ids]);editor=call_seconds(calls)
    final=batch_share(preds,lambda r:r['pair_id'] in ids)
    newfinal=batch_share([{**r,'batch_runtime_ms':r['new_batch_runtime_ms']} for r in preds],lambda r:r['pair_id'] in ids)
    contrasts={k:paired_bootstrap(values[method.CONDITION],v,labels,20261115,10000) for k,v in values.items() if k!=method.CONDITION}
    summary=lambda aa:{'pairs':len(aa),'changed_pairs':sum(a['changed'] for a in aa),
        'literal_compatible':sum(a['literal_compatible'] for a in aa),'format_compatible':sum(a['format_compatible'] for a in aa),
        'context_flagged':sum(not a['format_compatible'] for a in aa),
        'digit_changed':sum(bool(a['digit_changed_fields']) for a in aa),'duplicate_options':sum(a['new_duplicate_options'] for a in aa)}
    groups={axis:{lang:{'n':sum(rows[p][axis]==lang for p in ids),
        'correct':{k:sum(v[p] for p in ids if rows[p][axis]==lang) for k,v in values.items()},
        'audit':summary([a for a in audits if a[axis]==lang])} for lang in ('en','zh','th','ru')} for axis in ('source_language','gui_language')}
    infcost=json.loads((Path(done['infer'])/'cost.json').read_text());rwcost=json.loads((Path(done['rewrite'])/'cost.json').read_text())
    snapshot={'development_only':True,'primary_pairs':n,'semantic_items':20,'executed_pairs':len(rows),'correct':{k:sum(v.values()) for k,v in values.items()},
        'contrasts':contrasts,'audit_previous':summary(previous['audits']),'audit_revised':summary(audits),'by_language':groups,
        'status':dict(Counter(rows[p]['status'] for p in ids)),
        'repairs':sum(len(rows[p]['attempts'])-1 for p in ids),'cap_hits':sum(x['output_tokens']==x['generation']['max_new_tokens'] for x in calls.values()),
        'primary_time':{'editor_seconds':editor,'final_logical_seconds':final['seconds'],'final_new_seconds':newfinal['seconds'],
            'total_standalone_seconds':editor+final['seconds'],'total_new_compute_seconds':editor+newfinal['seconds'],
            'previous_total_seconds':previous['primary_time']['total_seconds']},
        'infer_cost':infcost,'rewrite_cost':rwcost,'execution_wall_seconds':done['execution_wall_seconds'],
        'prompt_sha256':c['prompt_sha256'],'config_sha256':digest(c['config']),'contract_sha256':digest(c),
        'config':c['config'],'captured_sources_sha256':c['source_sha256'],
        'raw_manifest':{str((Path(done[stage])/filename).relative_to(REPO)):hashlib.sha256((Path(done[stage])/filename).read_bytes()).hexdigest()
            for stage,filename in [('rewrite','rewritten.jsonl'),('rewrite','calls.json'),('infer','predictions.jsonl')]}}
    timing_path=ROOT/'artifacts/end_to_end_cost_snapshot.json'
    timing=json.loads(timing_path.read_text())
    measured={r['condition']:r for r in timing['current']}
    factor=1656/n
    direct_hours=(editor+final['seconds'])*factor/3600
    stem_hours=measured['TS_STEM_ONLY_GUI_AUTO']['cold_total_seconds']*factor/3600
    all_hours=measured['TS_ALL_SINGLE_PASS_GUI_AUTO']['cold_total_seconds']*factor/3600
    snapshot['remaining_eta']={'remaining_items':138,'executed_pairs':1656,'primary_pairs':1655,'unique_images':552,
        'copy_first_direct_compute_hours':direct_hours,'separate_stem_compute_hours':stem_hours,
        'inventory_all_joint_compute_hours':all_hours,'direct_plus_stem_compute_hours':direct_hours+stem_hours,
        'direct_plus_stem_with_15_to_25pct_buffer_hours':[(direct_hours+stem_hours)*1.15,(direct_hours+stem_hours)*1.25],
        'timing_source_sha256':hashlib.sha256(timing_path.read_bytes()).hexdigest(),
        'assumptions':'Screen averages linearly extrapolated; cold inventories, no predicted cache savings, no new O/R/T/F inference, excludes hard guarantees; existing internal observed in v1.'}
    wrong_ids=[p for p in ids if not values[method.CONDITION][p]]
    snapshot['failure_diagnostics']={'wrong_pairs':len(wrong_ids),
        'wrong_no_change':sum(rows[p]['status']=='no_op_no_changes' for p in wrong_ids),
        'wrong_after_change':sum(rows[p]['status']=='success' for p in wrong_ids),
        'changed_stem_pairs':sum(rows[p]['question_stem']!=originals[p]['question_stem'] for p in ids),
        'changed_options_pairs':sum(rows[p]['options']!=originals[p]['options'] for p in ids),
        'unchanged_prediction_difference_from_O':sum(rows[p]['status']=='no_op_no_changes' and pred[p]['parsed_generated_label']!=lookup['O',p]['parsed_generated_label'] for p in ids)}
    write(ROOT/'artifacts/source_copy_rewrite_results_snapshot.json',snapshot)
    (output/'context_audits.jsonl').write_text(''.join(json.dumps(a,ensure_ascii=False)+'\n' for a in audits))
    lines=['# Screenshot 직접 rewrite: 원문 복사 강화 결과','',
        '기존 실패를 보고 프롬프트를 한 번 수정한 Screen 개발 실험이다. Main20문항·240쌍, pilot48쌍 별도. Inventory나 extractor 없이 screenshot+원본 MCQ를 받아 완성형 MCQ를 생성한다. 결과를 본 뒤 추가 prompt sweep은 하지 않았다.','',
        '[수정 전 실패 분석](VISUAL_REWRITE_FAILURES_KO.md) · [실행 전 고정 설계](SOURCE_COPY_REVISION_DESIGN_KO.md)','',
        '## 정확도','', '| 조건 | 정답/240 | 정확도 |','| --- | ---: | ---: |']
    order=['O','T_REF','R_REF','F_REF','TS_QSEL_OFULL_GUI_AUTO','TS_STEM_ONLY_GUI_AUTO','TS_STEM_SINGLE_PASS_GUI_AUTO','TS_ALL_SINGLE_PASS_GUI_AUTO',OLD,method.CONDITION,'TS_FULL_GUI','TS_SEL_GUI_AUTO']
    for k in order:lines.append(f'| {NAMES[k]} | {sum(values[k].values())} | {sum(values[k].values())/n:.2%} |')
    lines += ['', '| 새 조건 − 기준 | 차이 | 95% item bootstrap CI | 회복/회귀 |','| --- | ---: | --- | ---: |']
    for k in ('O',OLD,'TS_QSEL_OFULL_GUI_AUTO','TS_ALL_SINGLE_PASS_GUI_AUTO','R_REF','F_REF'):
        r=contrasts[k];lines.append(f"| {NAMES[k]} | {r['difference']*100:+.2f}pp | [{r['ci95'][0]*100:+.2f}, {r['ci95'][1]*100:+.2f}] | {r['recovery']}/{r['regression']} |")
    lines += ['', '10,000회 semantic-item bootstrap이다. 이미 관찰한 20문항의 개발 결과로 독립 검증이 아니다. 구간은 다중 비교 보정 전 탐색 구간이며 확증적 유의성을 주장하지 않는다. R/T/F는 과거 parallel/annotated reference 조건이며 장비·배치 차이와 정보 우위를 고려한다. T_REF는 gold source span+Gemma 번역, R_REF는 parallel referent 정렬, F_REF는 전체 parallel localization이다.','',
        '## 규칙 준수와 수정 범위','', '| 진단 | 이전 | 새 조건 |','| --- | ---: | ---: |']
    for k,title in [('changed_pairs','실제 수정'),('literal_compatible','문자 그대로 문맥 호환'),('format_compatible','형식 정규화 후 문맥 호환'),('context_flagged','문맥 경고'),('digit_changed','숫자열 변화'),('duplicate_options','새 보기 중복')]:
        lines.append(f"| {title} | {snapshot['audit_previous'][k]}/240 | {snapshot['audit_revised'][k]}/240 |")
    lines += ['', '문맥 검사는 생성 후 source gold span 바깥 문자 보존을 검사한 진단이다. Matching/의미 정답률을 뜻하지 않는다. 유효한 전체 번역도 selective 조건에서는 경고된다. 이 검사로 출력을 버리거나 gold로 교정하지 않았다.','',
        f"주 분석 처리 상태: `{snapshot['status']}`; 구조 repair {snapshot['repairs']}회, 출력 cap hit {snapshot['cap_hits']}회.",'',
        '## 언어별 결과','']
    for axis,title in [('source_language','원문 언어'),('gui_language','GUI 언어')]:
        lines += [f'### {title}','', '| 언어 | O | 이전 직접 rewrite | 새 직접 rewrite | 새 문맥 경고 |','| --- | ---: | ---: | ---: | ---: |']
        for lang,g in groups[axis].items():lines.append(f"| {lang.upper()} | {g['correct']['O']}/60 | {g['correct'][OLD]}/60 | {g['correct'][method.CONDITION]}/60 | {g['audit']['context_flagged']}/60 |")
        lines.append('')
    oldwrong = [p for p in ids if not values[OLD][p]]
    newwrong = [p for p in ids if not values[method.CONDITION][p]]
    oldbad = {a['pair_id'] for a in previous['audits'] if not a['format_compatible']}
    newbad = {a['pair_id'] for a in audits if not a['format_compatible']}
    lines += ['## 이전 실패가 얼마나 해결됐는가','',
        f"이전 오답69쌍 중 {sum(values[method.CONDITION][p] for p in oldwrong)}쌍 회복, 이전 정답 중 {contrasts[OLD]['regression']}쌍 회귀했다. 새 오답은 {len(newwrong)}쌍이며 그중 {sum(p in newbad for p in newwrong)}쌍에 문맥 경고가 있다.",'',
        f"이전 문맥 경고174쌍 중 {len(oldbad-newbad)}쌍이 새 검사에서는 호환되고, 이전 호환66쌍 중 {len(newbad-oldbad)}쌍에 새 경고가 생겼다. 참조 이름 자체의 정체성까지 검증한 것은 아니다.",'',
        f"새 오답70쌍은 원문 유지22쌍과 수정 후 오답48쌍으로 나뉜다. Stem이 바뀐 것은 {snapshot['failure_diagnostics']['changed_stem_pairs']}쌍, options가 바뀐 것은 {snapshot['failure_diagnostics']['changed_options_pairs']}쌍이다. 원문 유지76쌍에서는 O와 label이 달라진 사례가 없었다. 다만 동일한 배치 전체를 확인하지 않은 개별 입력의 미래 일치를 보장하지는 않는다.",'',
        '남은 실제 오류는 문맥 번역만의 문제가 아니다. `message_2` RU→TH에서는 네 보기를 전부 같은 label로 만들었다. `forest_2`에서는 시간을15:22→15:48 등으로 바꾸거나 다른 achievement 이름을 선택한다. `phone_4` RU→TH에서는 서로 다른 설정 이름을 치환하고 숫자5까지 추가했다. 일부는 정답 label을 맞혀도 원래 문항을 보존한 올바른 변환이 아니다. 따라서 구조 성공288/288이나 문맥 호환227/240을 method 품질의 완성으로 보지 않는다.','',
        '**판단:** 문맥 통번역 억제는 크게 개선됐으나 정확도는171→170으로 향상되지 않았다. 기존 Stem-only175와 inventory 통합179를 대체할 근거는 없다. 이번 조건은 비용이 작은 비교 후보로 유지할 수 있지만, 새로운 참조 정렬의 우월성이 확인됐다고 보고하지 않는다. 추가 prompt 수정 없이 더 넓은 개발 문항에서 두 후보를 비교하거나, 다음 변경 전 실제 대응 identity/원문 유지의 영향을 분리하는 편이 낫다.','',
        '### 실제 수정 전후 예시','']
    for p in ('rel::2/note_1.png::en::th','rel::2/calendar_6.png::en::th','rel::2/map_9.png::th::en','rel::2/note_1.png::ru::th'):
        lines += [f'`{p}`','',f"GT {labels[p]['gold_answer']}; 이전 {oldpred[p]['parsed_generated_label']}, 새 조건 {pred[p]['parsed_generated_label']}.",'','```json',
            json.dumps({'source':fields(originals[p]),'previous':fields(oldrows[p]),'revised':fields(rows[p])},ensure_ascii=False,indent=2),'```','']
    t=snapshot['primary_time']
    lines += ['## 비용과 중복 방지','',f"Main240쌍: 변환 VLM **{editor/60:.2f}분** + 풀이 VLM **{final['seconds']/60:.2f}분** = 재사용 전 계산량 기준 **{t['total_standalone_seconds']/60:.2f}분**. 이전은{t['previous_total_seconds']/60:.2f}분이었다. LM/inventory 비용은 없다. 모델 적재는 이 합계에서 제외한다.",'',
        f"실제 새 풀이 계산은 {newfinal['seconds']/60:.2f}분이다. 전체288쌍에서 기존 전체 배치 재사용 {infcost['reused_batches']}묶음·{infcost['reused_rows']}쌍, 새 풀이 {infcost['new_batches']}묶음. 서로 다른 과거 출력 때문에 재사용을 막은 key는 {infcost['conflicting_cache_keys']}개다. 이미지·순서·문자열·설정·환경이 모두 일치하는 전체 배치만 재사용했으며 일부 문항만 같을 때는 배치를 다시 계산했다.",'',
        f"전체288쌍의 실행 wall은 {done['execution_wall_seconds']/60:.2f}분이다. Worker·모델 적재·요약을 포함한다. Main 재구성 시간과 분모·범위가 다르다.",'',
        '## 다음 6–7시간 실행안 산정','',
        f"남은 main138문항은 1,656 mismatch pair(주 분석1,655)다. 새 조건 실측의 선형 환산은 약 **{t['total_standalone_seconds']*1656/240/3600:.2f}시간**이다. 원본 크기·출력 길이·모델 적재에 따라 달라지므로 고정 ETA가 아니다. 새 조건 + 기존 Stem 분리 GUI를 함께 실행하면 inventory의 화면별 생성·재사용 비용이 추가된다. 구체적인 분할·큐는 이 결과를 검토한 뒤 고정한다. 이번에 남은138문항이나 밤샘 큐를 시작하지 않았다.",'',
        '| 남은 범위 실행안 | 계산 구간 선형 환산 |','| --- | ---: |',
        f'| 새 직접 rewrite 한 조건 | {direct_hours:.2f}시간 |',
        f'| 기존 Stem-only 분리 · inventory 포함 | {stem_hours:.2f}시간 |',
        f'| 위 두 조건 함께 | {direct_hours+stem_hours:.2f}시간 |',
        f'| 위 두 조건 + 15–25% 적재·변동 여유 | {(direct_hours+stem_hours)*1.15:.2f}–{(direct_hours+stem_hours)*1.25:.2f}시간 |',
        f'| 참고: inventory Stem+Options 통합 + 새 직접 rewrite | {all_hours+direct_hours:.2f}시간 · 여유 제외 |','',
        '두 후보를 유지한다면 실행 순서는 Selection20문항240쌍(주239)에서 두 조건을 실행한 뒤, 프롬프트를 더 바꾸지 않고 Internal118문항1,416쌍으로 이어가는 것이다. 나머지 화면552개 inventory는 한 번만 생성한다. 기존 O/R/T/F를 재추론하거나 모든 과거 후보를 재실행하는 비용은 포함하지 않았다. 동일 배치 재사용의 미래 hit 비율은 모르므로 ETA에서 절약을 가정하지 않았다. 두 방법은 변환 모델과 option 처리 범위도 달라 inventory만의 인과 효과 비교가 아니다. Internal은 v1에서 이미 관찰했으므로 untouched 평가로 부르지 않는다. 7시간 보장이나 hard deadline이 필요하면 후속 큐에 checkpoint/시간 예산 처리가 필요하다.','',
        '## 설정과 프롬프트','',
        'Qwen/Qwen3-VL-8B-Instruct revision `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`, BF16·SDPA·seed42, fast processor·channels_last_3d, min262144/max2097152pixels, max input4096. 변환batch1·768토큰, 풀이batch3·2토큰. JSON 구조 검증/repair 최대1회는 이전과 같다. 문맥·숫자 경고를 rejection에 쓰지 않았다.','',
        '### 변환 system','', '```text',method.SYSTEM,'```','',
        '한국어 요지: 질문 전체를 번역하지 말고 원문을 복사한다. 화면에서 확실히 읽히는 같은 요소의 이름만 바꾸고, 원문 언어 문맥·방향·요일·값·보기 identity는 유지한다. 불확실하거나 없는 이름은 그대로 둔다. 합성 비영어 예시로 혼합 언어 출력이 의도임을 명시했다.','',
        '### 실제 user 형식','', '```text',method.user_prompt(next(iter(originals.values()))),'```','',
        '구조 오류 때만 같은 screenshot과 이전 raw response·오류 메시지를 붙여 완성형 JSON을 한 번 더 요청한다. 전체 system/user/rendered prompt와 generation은 calls.json에 보존한다.','',
        '### 문제 풀이 system (변경 없음)','', '```text',c['downstream']['system_prompt'],'```','',
        'User: 같은 screenshot + 수정 stem A: 수정A B: 수정B C: 수정C D: 수정D + `Respond with exactly one label: A, B, C, or D.`. 모델에 GT를 주지 않는다.','',
        '## 재현','', '```bash','bash followup_rel_4lang/method_dev/scripts/run_source_copy_rewrite.sh --run','.venv/bin/python followup_rel_4lang/method_dev/scripts/report_source_copy_rewrite.py','```','',
        '완료 run은 재사용한다. Raw는 `artifacts/visual_source_copy_rewrite_screen_v1/`에 있고 작은 결과 snapshot·config/prompt/hash·raw checksum을 Git에 남긴다. 기존 결과를 덮어쓰지 않는다.','']
    (ROOT/'reports/SOURCE_COPY_REWRITE_RESULTS_KO.md').write_text('\n'.join(lines))
    cases=['# 원문 복사 강화: 전체288쌍 결과','', '| Pair | split | GT | O | 이전 | 새 조건 | 새 문맥 경고 | 풀이 재사용 |','| --- | --- | --- | --- | --- | --- | --- | --- |']
    amap={a['pair_id']:a for a in audits}
    for p in sorted(rows):cases.append(f"| `{p}` | {labels[p]['split']} | {labels[p]['gold_answer']} | {lookup['O',p]['parsed_generated_label']} | {oldpred[p]['parsed_generated_label']} | {pred[p]['parsed_generated_label']} | {','.join(amap[p]['format_flagged_fields']) or '-' if p in amap else 'pilot 미검사'} | {pred[p]['cache_hit']} |")
    cases += ['', '## 남은 문맥 경고: 변경된 field 원문/생성문','',
        '경고는 source annotation 밖 문자를 보존할 수 없다는 진단이다. 의미 손상이나 정렬 오답을 자동 확정하지 않는다.','']
    for a in audits:
        if a['format_compatible']:
            continue
        cases += [f"### {a['pair_id']}",'',f"GT {labels[a['pair_id']]['gold_answer']}, 새 예측 {pred[a['pair_id']]['parsed_generated_label']}.",'','```json',
            json.dumps({f:{'source':a['source'][f],'rewrite':a['rewritten'][f]} for f in a['format_flagged_fields']},ensure_ascii=False,indent=2),'```','']
    (ROOT/'reports/SOURCE_COPY_REWRITE_CASES_KO.md').write_text('\n'.join(cases).rstrip()+'\n')
    print(json.dumps({k:snapshot[k] for k in ('correct','audit_previous','audit_revised','primary_time','infer_cost')},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
