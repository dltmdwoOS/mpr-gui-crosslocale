"""Post-hoc verification and Korean report for the completed Screen 2x2 study."""
import gzip
import hashlib
import json
import sys
from collections import Counter,defaultdict
from pathlib import Path

REPO=Path(__file__).resolve().parents[3];ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(REPO/'01_code/src'),str(REPO),str(Path(__file__).parent)]
from run_stem_only_gui import read,write,unique
from run_stem_refinement_2x2 import latest,extraction
from search_pipeline import paired_bootstrap
from compare_end_to_end import batch_share
from mpr_crosslocale.methods.selective_alignment.schemas import digest,fields,render
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits
from mpr_crosslocale.inference.answer_parser import parse_label
from followup_rel_4lang.method_dev.stem_refinement_2x2 import CELLS


def main():
    output=ROOT/'artifacts/stem_refinement_2x2_screen_v1';captures={}
    def use(p):captures[str(p.relative_to(REPO))]=hashlib.sha256(p.read_bytes()).hexdigest();return p
    def load(p):return json.loads(use(p).read_text())
    def rows(p):return read(use(p))
    use(Path(__file__));contract=load(output/'contract.json');done=load(output/'COMPLETE.json');saved=load(output/'results.json')
    if done['execution_mode']!='gpu' or done['contract_sha256']!=digest(contract):raise ValueError('Completed GPU run required')
    for path,sha in contract['source_sha256'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen source changed: '+path)
    original=unique(rows(output/'inputs.jsonl'));labels=unique(rows(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(list(original.values()))!=contract['inputs_sha256'] or digest(labels)!=contract['labels_sha256']:raise ValueError('Dataset lock differs')
    ids=sorted(p for p in original if labels[p]['split']=='main')
    if len(ids)!=240 or len(original)!=288:raise ValueError('Unexpected denominator')
    rr={};pp={};values={};costs={};details={};changes={};reused_verified=0;provenance_cache={}
    for cell in CELLS:
        work=output/cell;rewrite_dir=latest(work,'rewrite');infer_dir=latest(work,'infer')
        if not (rewrite_dir/'COMPLETE').exists() or not (infer_dir/'COMPLETE').exists():raise ValueError('Incomplete stage')
        rr[cell]=unique(rows(rewrite_dir/'rewritten.jsonl'));predrows=rows(infer_dir/'evaluation/predictions.jsonl');pp[cell]=unique(predrows)
        if set(rr[cell])!=set(original) or set(pp[cell])!=set(original):raise ValueError('Incomplete paired outputs')
        for p,r in rr[cell].items():
            before=original[p];pred=pp[cell][p]
            for key in ('parallel_id','source_language','gui_language','image_path','image_sha256','option_order'):
                if r[key]!=before[key]:raise ValueError('Pair identity changed')
            if r['options']!=before['options'] or any(e['field']!='question_stem' for e in r['edits']):raise ValueError('Options changed')
            if apply_edits(before,r['edits'])!=fields(r) or r['modified_question']!=render(fields(r)):raise ValueError('Non-span context changed')
            if pred['execution_mode']!='gpu' or pred['condition']!=cell or parse_label(pred['generated_text'])!=pred['parsed_generated_label']:raise ValueError('Invalid prediction')
        groups=defaultdict(list)
        for r in predrows:groups[r['batch_id']].append(r)
        for batch in groups.values():
            if len(batch)!=batch[0]['batch_size']:raise ValueError('Incomplete final batch')
            if any(r.get('cache_hit')!=batch[0].get('cache_hit') for r in batch):raise ValueError('Mixed reuse within batch')
            if batch[0].get('cache_hit'):
                prov=batch[0]['reuse_provenance'];path=Path(prov['source'])
                if path not in provenance_cache:
                    sources=rows(path);sg=defaultdict(list)
                    for r in sources:sg[r['batch_id']].append(r)
                    provenance_cache[path]=sg
                old=provenance_cache[path][prov['batch_id']]
                if [(r['pair_id'],r['rendered_prompt'],r['generated_text']) for r in batch]!=[(r['pair_id'],r['rendered_prompt'],r['generated_text']) for r in old]:raise ValueError('Reuse provenance differs')
                reused_verified+=len(batch)
        values[cell]={p:int(pp[cell][p]['status']=='success' and pp[cell][p]['parsed_generated_label']==labels[p]['gold_answer']) for p in ids}
        if sum(values[cell].values())!=saved['correct'][cell]:raise ValueError('Independent accuracy differs')
        details[cell]={'input_changed_vs_baseline':sum(fields(rr[cell][p])!=fields(rr['E0_M0'][p]) for p in ids),
            'unchanged_input_changed_label':sum(fields(rr[cell][p])==fields(rr['E0_M0'][p]) and pp[cell][p]['parsed_generated_label']!=pp['E0_M0'][p]['parsed_generated_label'] for p in ids),
            'primary_status':dict(Counter(rr[cell][p]['status'] for p in ids)),
            'string_null_fallbacks':[]}
        for p in ids:
            r=rr[cell][p]
            if r['errors']==['Unknown candidate ID']:
                data=json.loads(r['attempts'][-1]['raw_output'])
                if set(data['matches'].values())=={'null'}:
                    if len(r['extracted_referents'])!=1 or fields(r)!=fields(original[p]):raise ValueError('String null is not pure abstention')
                    details[cell]['string_null_fallbacks'].append(p)
        changes[cell]=[]
        for p in ids:
            old=values['E0_M0'][p];new=values[cell][p]
            if old==new:continue
            changes[cell].append({'pair_id':p,'transition':'recovery' if new else 'regression','gold':labels[p]['gold_answer'],
                'source':original[p]['question_stem'],'baseline':rr['E0_M0'][p]['question_stem'],'new':rr[cell][p]['question_stem'],
                'baseline_spans':rr['E0_M0'][p]['extracted_referents'],'new_spans':rr[cell][p]['extracted_referents'],
                'baseline_label':pp['E0_M0'][p]['parsed_generated_label'],'new_label':pp[cell][p]['parsed_generated_label']})
        if cell!='E0_M0':
            cost=load(rewrite_dir/'cost.json');infcost=load(infer_dir/'evaluation/cost.json')
            newtime=batch_share([{**r,'batch_runtime_ms':r['new_batch_runtime_ms']} for r in predrows],lambda r:True)
            costs[cell]={'rewrite':cost,'infer':infcost,'new_answer_seconds':newtime['seconds']}
            expected=paired_bootstrap(values[cell],values['E0_M0'],labels,20261115,10000)
            if expected!=saved['contrasts_vs_baseline'][cell]:raise ValueError('Independent contrast differs')
    for a,b in [('E0_M0','E0_M1'),('E1_M0','E1_M1')]:
        if any(rr[a][p]['extracted_referents']!=rr[b][p]['extracted_referents'] for p in original):raise ValueError('Shared extractor invariant failed')
    extraction_cost=load(latest(output/'extraction','E1')/'cost.json')
    new_lm_calls=extraction_cost['calls']-extraction_cost['cache_hits']+sum(c['rewrite']['calls']-c['rewrite']['cache_hits'] for c in costs.values())
    reused_new_cells=sum(c['infer']['reused_rows'] for c in costs.values());new_answer_rows=864-reused_new_cells
    extraction_changes={}
    e0=extraction(output,0);e1=extraction(output,1)
    from followup_rel_4lang.method_dev.two_stage_v2 import prompts
    keys={digest(prompts.extraction_payload(original[p],stem_only=True)) for p in ids}
    extraction_changes['unique_main_stems']=len(keys)
    extraction_changes['changed_unique_main_spans']=sum(e0[k]['referents']!=e1[k]['referents'] for k in keys)
    for e,records in [('E0',e0),('E1',e1)]:extraction_changes[e]={'failed_main_stems':sum(records[k]['status']!='success' for k in keys)}
    snapshot={'saved_results':saved,'verified_pairs_per_cell':288,'primary_pairs':240,'semantic_items':20,'wall_seconds':done['wall_seconds'],
        'details':details,'transitions_vs_baseline':changes,'incremental_costs':costs,'E1_extraction_cost':extraction_cost,
        'new_LM_calls':new_lm_calls,'new_answer_rows':new_answer_rows,'reused_answer_rows_new_cells':reused_new_cells,
        'reused_rows_verified_including_baseline':reused_verified,'source_extraction_changes':extraction_changes,
        'contract_sha256':digest(contract),'source_and_raw_sha256':captures,'empirical':True,'development_only':True}
    write(ROOT/'artifacts/stem_refinement_2x2_results_snapshot.json',snapshot)
    names={'E0_M0':'기존 추출 + 기존 matcher','E1_M0':'수정 추출 + 기존 matcher','E0_M1':'기존 추출 + 후보 ID matcher','E1_M1':'수정 추출 + 후보 ID matcher'}
    lines=['# Stem-only GUI 2×2 실험 결과','',
        '**현재 선택은 E1_M0: 추출 수정만 유지하고 기존 matcher를 쓰는 조건이다.** Screen240쌍에서178정답으로 가장 높았다. 다만 개선3쌍 중1쌍은 이름 내용이 같고 따옴표만 달라진 사례여서, 모두 의미 대응 개선이라고 해석하지 않는다. 후보 ID matcher는 변경/구조 성공을 늘렸으나 정확도를 높이지 못했다.','',
        '## 범위와 검증','',
        'Screen main20개 semantic item×12방향=240쌍이 주 분석이다. 기존 batch 구성을 보존하기 위해 pilot48쌍을 포함한288쌍씩 네 조건을 구성했다. E0_M0는 저장된 raw 응답과 예측을 재사용했고 신규3조건만 실행했다. 전체 wall은 '+f"{done['wall_seconds']/60:.2f}분이다. 추가 GPU 추론 없이 완료된 자료만 분석했다.",'',
        'Frozen source/data hash, 각 조건288행의 pair·이미지·정답 연결, source span 바깥과 options 불변, 두 matcher의 동일 extraction 입력, 재사용된 전체 배치의 source/prompt/output provenance를 검사했다. 독립 재계산한 정확도·paired bootstrap은 실행기 결과와 일치한다.','',
        '## 정확도와 R_stem 격차','', '| 조건 | 정답/240 | 정확도 | 기존 대비 | 회복/회귀 | R_stem 대비 |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for cell in CELLS:
        k=saved['correct'][cell];delta=(k-saved['correct']['E0_M0'])/240
        cc=saved['contrasts_vs_baseline'].get(cell)
        lines.append(f"| {cell} · {names[cell]} | {k} | {k/240:.2%} | {delta*100:+.2f}pp | {str(cc['recovery'])+'/'+str(cc['regression']) if cc else '기준'} | {(k-saved['reference_correct']['R_stem'])/240*100:+.2f}pp |")
    lines += ['', f"같은 범위 O는{saved['reference_correct']['O']}/240=67.50%, 과거 R_stem은{saved['reference_correct']['R_stem']}/240=77.08%다. R_stem−자동 방법의 정답 차이는10개에서7개로 줄었지만, 과거 reference는 RTX4090·batch4 실행이라 실행 환경이 완전히 같은 대조는 아니다.",'',
        '| 대비 | 차이 | 95% item bootstrap CI |','| --- | ---: | --- |']
    for cell,x in saved['contrasts_vs_baseline'].items():lines.append(f"| {cell} − E0_M0 | {x['difference']*100:+.2f}pp | [{x['ci95'][0]*100:+.2f}, {x['ci95'][1]*100:+.2f}] |")
    for name,x in saved['factorial'].items():lines.append(f"| {name} | {x['difference']*100:+.2f}pp | [{x['ci95'][0]*100:+.2f}, {x['ci95'][1]*100:+.2f}] |")
    lines += ['', 'Extractor 주 효과'+'는 두 matcher에서의 수정 효과 평균이고 matcher 주 효과는 두 extractor에서의 평균이다. Interaction은(E1M1−E1M0)−(E0M1−E0M0)다. 이 factorial 대비의 recovery/regression 필드는 일반적인 정오 전환 개수로 해석하지 않는다.','',
        '10,000회 semantic-item bootstrap이며 모든 구간은 다중 비교 보정 전 탐색 구간이다. E1_M0의 구간 하한은0이다. 반복 관찰한 개발 Screen이므로 우월성·동등성·독립 일반화 검증을 주장하지 않는다. M1은 프롬프트와 출력 표현을 함께 바꿨으므로 ID 자체의 순수 효과도 아니다.','',
        '## 추출 품질과 처리 상태','', '| Extractor | Precision | Recall | F1 |','| --- | ---: | ---: | ---: |']
    for e,q in saved['source_extraction_quality'].items():lines.append(f"| {e} | {q['precision']:.2%} | {q['recall']:.2%} | {q['f1']:.2%} |")
    lines += ['', 'Source annotation은 생성 후 source 경계 진단에만 사용했다. F1은80개 고유 main source stem이 GUI3방향으로 반복되는 pair-weighted exact-span 점수다. Target 이름 대응의 정확도를 직접 뜻하지 않는다.','',
        '| 조건 | 실제 수정 | 원문 fallback | ID/비인벤토리 오류 | 원문 전체가 기존과 다른 pair |','| --- | ---: | ---: | ---: | ---: |']
    for cell,q in saved['quality'].items():lines.append(f"| {cell} | {q['changed']} | {q['status'].get('fallback_original',0)} | {q['errors'].get('Unknown candidate ID',0)+q['errors'].get('Target is not a verbatim inventory member',0)} | {details[cell]['input_changed_vs_baseline']} |")
    lines += ['', 'M1의 Unknown candidate ID4쌍은 각 조건 모두 같은4쌍이며 실제 raw는 잘못된 후보 번호가 아니라 JSON null 대신 문자열 `"null"`을 반환한 경우다. 모두 referent1개이고 최종 입력은 원문이다. 이 타입 오류만 정상 abstention으로 처리해도 이 사례들의 MCQ는 그대로이므로 정확도 개선으로 이어지지 않는다. Frozen parser와 점수는 소급 변경하지 않았다.','',
        '## E1_M0가 회복한3쌍','']
    explanations={
        'rel::2/calendar_6.png::en::th':'day of the week라는 일반 표현 대신 실제 기준 이름 Thursday를 추출했다. 새 target은요일+날짜(พฤ.12) 형태라 원문의 값/표현 보존 문제는 별도 검수가 필요하다.',
        'rel::4/google_play_8.jpg::ru::en':'선택한 이름 Use device location은 같다. E1이 source guillemets까지 span에 포함해 치환하면서 따옴표가 사라졌다. 형식/배치 영향 가능성이 있어 semantic alignment 개선으로 확정하지 않는다. 새 prompt는 인용부호를 제외하라고 했으므로 지시 준수도 완전하지 않다.',
        'rel::6/camera_8.jpg::th::zh':'generic mode와 인용부호까지 잡던 span을 실제 이름 รูปภาพ로 좁혔다. Target도视频(video)에서照片(photo)로 바뀌었다.'}
    for change in changes['E1_M0']:
        p=change['pair_id'];lines += [f'`{p}`','',explanations.get(p,''),'','```text','원문: '+change['source'],'기존: '+change['baseline'],'수정: '+change['new'],f"예측: {change['baseline_label']} → {change['new_label']}; GT {change['gold']}",'```','']
    lines += ['## 후보 ID matcher가 해결하지 못한 것','',
        '유효한 inventory ID를 고르는 것과 올바른 referent 이름을 고르는 것은 별개였다. 예를 들어 E0_M1은 toll roads를避开高速公路(highways)로, 照片(photo)를วิดีโอ(video)로, alarm ringtone을call ringtone으로 바꿔 회귀했다. 후보가 목록 안에 존재해도 source 요소의 의미를 보존했다고 볼 수 없다.','',
        'E0_M1은6쌍을 회복했지만10쌍을 잃었고, E1_M1은8쌍을 회복했지만6쌍을 잃었다. 따라서 더 많은 edit 적용이나 더 적은 fallback을 곧바로 성공으로 평가하지 않는다.','',
        '## GUI 언어별 정확도','', '| GUI | n | E0_M0 | E1_M0 | E0_M1 | E1_M1 |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for gui,g in saved['by_gui'].items():lines.append(f"| {gui.upper()} | {g['n']} | "+' | '.join(f"{g['correct'][cell]}/{g['n']} ({g['correct'][cell]/g['n']:.2%})" for cell in CELLS)+' |')
    lines += ['', 'E1_M0는EN/ZH/TH에서각1쌍 순증가했고RU는같았다. E1_M1의RU 개선을 보고RU에만 새 matcher를 켜는 정책은 만들지 않았다. 언어별60쌍도20문항의 반복 관측이다.','',
        '## 계산 비용과 재사용','', '| 조건 | Inventory | 추출 LM | Matching LM | 풀이 VLM | 처음부터 계산 구간 |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for cell,q in saved['logical_recipe_cost'].items():lines.append(f"| {cell} | {q['inventory_seconds']/60:.2f}분 | {q['extraction_seconds']/60:.2f}분 | {q['matching_seconds']/60:.2f}분 | {q['answer_seconds']/60:.2f}분 | {q['cold_total_seconds']/60:.2f}분 |")
    lines += ['', '위 표는 main240쌍에서 해당 방법을 처음부터 수행한다고 볼 때의 기록 구간 합계다. 기존 호출도 원래 runtime을 청구하고 혼합 batch는 문항 비율로 안분했다. 모델 적재는 제외하며 cached/서로 다른 시점의 호출이 섞여 통제된 속도 벤치마크가 아니다.','',
        f"이번 실제 추가 실험은25.06분이고 inventory 신규 생성은0회다. E1 추출은고유128source에129호출(구조repair1회), 새 matching 호출은{new_lm_calls-(extraction_cost['calls']-extraction_cost['cache_hits'])}회다. 신규3조건의864개 풀이 행 중{reused_new_cells}개를 재사용하고{new_answer_rows}개(72batch)를 새로 계산했다. 기존E0_M0의288개도 전체 재사용했다.",'',
        '## 다음 판단','',
        'E1_M0를 다음 후보로 고정할 근거는 있지만 최종 method로 확정할 근거는 부족하다. 다음 확인은 기존 inventory와 M0를 유지한 채 E1_M0만 Selection/Internal에 적용하는 방향이 단순하다. 단, 두 cohort도 이미 관찰했고 설계에 활용한 개발 자료이므로 독립 검증으로 부르지 않는다. M1을 더 확장하거나 언어별 분기 정책을 추가하기보다 실제 이름 대응 회복과 형식 변화 효과를 구분해야 한다. 이번에는 추가 추론이나 후속 실행을 시작하지 않았다.','',
        '[실행 전 고정 프로토콜·전체 프롬프트](STEM_REFINEMENT_2X2_PROTOCOL_KO.md) · [전체288쌍 결과와 회복/회귀 원문](STEM_REFINEMENT_2X2_CASES_KO.md) · [결과·비용·checksum snapshot](../artifacts/stem_refinement_2x2_results_snapshot.json)','',
        '```bash','.venv/bin/python followup_rel_4lang/method_dev/scripts/report_stem_refinement_2x2.py','```','']
    (ROOT/'reports/STEM_REFINEMENT_2X2_RESULTS_KO.md').write_text('\n'.join(lines).rstrip()+'\n')
    cases=['# Screen 2×2 전체288쌍 예측','','Pilot48쌍은 주 분석에서 제외.','', '| Pair | split | GT | E0_M0 | E1_M0 | E0_M1 | E1_M1 |','| --- | --- | --- | --- | --- | --- | --- |']
    for p in sorted(original):cases.append(f"| `{p}` | {labels[p]['split']} | {labels[p]['gold_answer']} | "+' | '.join(str(pp[cell][p]['parsed_generated_label']) for cell in CELLS)+' |')
    cases += ['', '## 기준 대비 모든 회복·회귀의 실제 stem','']
    for cell in ('E1_M0','E0_M1','E1_M1'):
        for ch in changes[cell]:
            cases += [f"### {cell} · {ch['transition']} · {ch['pair_id']}",'', '```json',json.dumps(ch,ensure_ascii=False,indent=2),'```','']
    (ROOT/'reports/STEM_REFINEMENT_2X2_CASES_KO.md').write_text('\n'.join(cases).rstrip()+'\n')
    print(json.dumps({'correct':saved['correct'],'wall_minutes':done['wall_seconds']/60,'new_LM_calls':new_lm_calls,'reused_answer_rows_new_cells':reused_new_cells,'new_answer_rows':new_answer_rows,'source_changes':extraction_changes},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
