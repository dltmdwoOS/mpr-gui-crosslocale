"""Post-hoc full development report and case table; no model loading/inference."""
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO=Path(__file__).resolve().parents[3];ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(REPO/'01_code/src'),str(REPO),str(Path(__file__).parent)]
from run_stem_only_gui import read,write,unique
from run_e1_stem_full_dev import verify_sources,COHORTS
from run_stem_refinement_2x2 import latest,extraction
from compare_end_to_end import call_map,call_seconds,batch_share
from search_pipeline import EXCLUDED,paired_bootstrap
from mpr_crosslocale.methods.selective_alignment.schemas import digest,fields,validate_input
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits
from mpr_crosslocale.inference.answer_parser import parse_label
from report_visual_selective_rewrite import normalize_context
from followup_rel_4lang.method_dev.two_stage_v2 import prompts


def main():
    output=ROOT/'artifacts/e1_stem_full_dev_v1';captures={}
    def use(p):captures[str(p.relative_to(REPO))]=hashlib.sha256(p.read_bytes()).hexdigest();return p
    def load(p):return json.loads(use(p).read_text())
    def rows(p):return read(use(p))
    use(Path(__file__));c=load(output/'contract.json');done=load(output/'COMPLETE.json');saved=load(output/'results.json')
    if done['execution_mode']!='gpu' or done['contract_sha256']!=digest(c):raise ValueError('Completed frozen GPU run required')
    verify_sources(c)
    labels=unique(rows(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels)!=c['labels_sha256']:raise ValueError('Labels changed')
    annotations=unique(rows(ROOT/'artifacts/dataset_audit/oracle_spans_DIAGNOSTIC_ONLY.jsonl'))
    newpred={};oldpred={};allrows={};logical_cost={};incremental={};values={};changes=[];source_counts={};input_agreement={}
    reuse_count=0;pred_cache={}
    for cohort in ('screen',*COHORTS):
        d=c['descriptors'][cohort]
        if cohort=='screen':
            inputs=Path(d['inputs']);rewrite=Path(d['rewrite']);infer=Path(d['infer']);origin=ROOT/'artifacts/stem_refinement_2x2_screen_v1'
            inventory_path=Path(json.loads((origin/'contract.json').read_text())['inventory_path'])
        else:
            origin=output/cohort;inputs=origin/'inputs.jsonl';rewrite=latest(origin/'E1_M0','rewrite');infer=latest(origin/'E1_M0','infer');inventory_path=Path(d['inventory_path'])
            ecost=load(latest(origin/'extraction','E1')/'cost.json');mcost=load(rewrite/'cost.json');icost=load(infer/'evaluation/cost.json')
            incremental[cohort]={'extract':ecost,'match':mcost,'infer':icost}
        original=unique(rows(inputs));rr=unique(rows(rewrite/'rewritten.jsonl'));pr=rows(infer/'evaluation/predictions.jsonl');pred=unique(pr);old=unique(rows(Path(d['baseline_pred'])));oldrr=unique(rows(Path(d['baseline_rewrite'])))
        if set(original)!=set(rr) or set(rr)!=set(pred):raise ValueError('Incomplete paired records')
        ids=sorted(p for p in original if labels[p]['split']=='main' and p!=EXCLUDED)
        for p in rr:
            if rr[p]['options']!=original[p]['options'] or apply_edits(original[p],rr[p]['edits'])!=fields(rr[p]):raise ValueError('Non-span/options changed')
            for key in ('parallel_id','source_language','gui_language','image_path','image_sha256','option_order'):
                if rr[p][key]!=original[p][key]:raise ValueError('Paired linkage changed')
            if parse_label(pred[p]['generated_text'])!=pred[p]['parsed_generated_label'] or pred[p]['execution_mode']!='gpu':raise ValueError('Invalid GPU prediction')
        v={p:int(pred[p]['status']=='success' and pred[p]['parsed_generated_label']==labels[p]['gold_answer']) for p in ids}
        b={p:int(old[p]['status']=='success' and old[p]['parsed_generated_label']==labels[p]['gold_answer']) for p in ids}
        if sum(v.values())!=saved['summary'][cohort]['correct']['E1_M0'] or sum(b.values())!=saved['summary'][cohort]['correct']['E0_M0']:raise ValueError('Independent score differs')
        if paired_bootstrap(v,b,labels,20261115,10000)!=saved['summary'][cohort]['contrasts']['E0_M0']:raise ValueError('Contrast differs')
        values[cohort]=v;newpred[cohort]=pred;oldpred[cohort]=old;allrows[cohort]=rr
        same=[p for p in ids if fields(rr[p])==fields(oldrr[p])]
        input_agreement[cohort]={'unchanged_MCQs':len(same),'changed_MCQs':len(ids)-len(same),
            'unchanged_MCQs_label_differences':sum(pred[p]['parsed_generated_label']!=old[p]['parsed_generated_label'] for p in same),
            'format_only_correctness_transitions':[p for p in ids if v[p]!=b[p] and normalize_context(rr[p]['question_stem'])==normalize_context(oldrr[p]['question_stem'])]}
        source_counts[cohort]={}
        for name,records in [('E0',oldrr),('E1',rr)]:
            gold=found=matched=0
            for p in ids:
                gs={(s['start'],s['end']) for s in annotations[p]['referents'] if s['field']=='question_stem'}
                fs={(s['start'],s['end']) for s in records[p]['extracted_referents'] or []}
                gold+=len(gs);found+=len(fs);matched+=len(gs&fs)
            source_counts[cohort][name]={'gold':gold,'predicted':found,'matched':matched}
        for p in ids:
            if v[p]!=b[p]:changes.append({'cohort':cohort,'pair_id':p,'transition':'recovery' if v[p] else 'regression','gold':labels[p]['gold_answer'],'old':old[p]['parsed_generated_label'],'new':pred[p]['parsed_generated_label']})
        if cohort!='screen':
            groups=defaultdict(list)
            for r in pr:groups[r['batch_id']].append(r)
            for batch in groups.values():
                if len(batch)!=batch[0]['batch_size']:raise ValueError('Incomplete batch')
                if not batch[0]['cache_hit']:continue
                prov=batch[0]['reuse_provenance'];path=Path(prov['source'])
                if path not in pred_cache:
                    groups_old=defaultdict(list)
                    for r in rows(path):groups_old[r['batch_id']].append(r)
                    pred_cache[path]=groups_old
                prior=pred_cache[path][prov['batch_id']]
                if [(r['pair_id'],r['rendered_prompt'],r['generated_text']) for r in batch]!=[(r['pair_id'],r['rendered_prompt'],r['generated_text']) for r in prior]:raise ValueError('Reused batch differs')
                reuse_count+=len(batch)
            incremental[cohort]['new_answer_seconds']=batch_share([{**r,'batch_runtime_ms':r['new_batch_runtime_ms']} for r in pr],lambda r:True)['seconds']
        inventories={r['image_sha256']:r for r in rows(inventory_path)};ex=extraction(origin,1)
        invcalls=call_map([inventories[sha] for sha in {original[p]['image_sha256'] for p in ids}])
        excalls=call_map([ex[digest(prompts.extraction_payload(original[p],stem_only=True))] for p in ids]);matcalls=call_map([rr[p] for p in ids])
        logical_cost[cohort]={'inventory_seconds':call_seconds(invcalls),'extraction_seconds':call_seconds(excalls),'matching_seconds':call_seconds(matcalls),'answer_seconds':batch_share(pr,lambda r:r['pair_id'] in ids)['seconds']}
        logical_cost[cohort]['total_seconds']=sum(logical_cost[cohort].values())
    if len({p for group in values.values() for p in group})!=1895:raise ValueError('Full 158-item denominator differs')
    exported=[]
    input_keys=('pair_id','parallel_id','source_language','gui_language','image_path','image_sha256','question_stem','options','option_order')
    for cohort in ('screen',*COHORTS):
        for p in sorted(allrows[cohort]):
            if labels[p]['split']!='main':continue
            row={k:allrows[cohort][p][k] for k in input_keys};validate_input(row);exported.append(row)
    exported.sort(key=lambda r:r['pair_id'])
    if len(exported)!=1896 or len(unique(exported))!=1896:raise ValueError('Main input export differs')
    export_path=output/'inputs_E1_M0_main1896.jsonl'
    export_path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in exported))
    manifest={'method':'E1_M0','main_items':158,'main_executed_pairs':1896,'main_primary_pairs':1895,'legacy_pilot_rows_reused':48,
        'inputs_path':str(export_path.relative_to(REPO)),'inputs_sha256':hashlib.sha256(export_path.read_bytes()).hexdigest(),
        'excluded_primary_pair':EXCLUDED,'input_order':'pair_id sorted data export. Stored predictions retain original cohort batches including Screen pilot companions.',
        'cohorts':c['descriptors'],'prompt_sha256':c['prompt_sha256']}
    write(output/'full_set_manifest.json',manifest)
    combined_extraction={}
    for name in ('E0','E1'):
        counts={key:sum(source_counts[co][name][key] for co in source_counts) for key in ('gold','predicted','matched')}
        combined_extraction[name]={**counts,'precision':counts['matched']/counts['predicted'],'recall':counts['matched']/counts['gold'],
            'f1':2*counts['matched']/(counts['predicted']+counts['gold'])}
    summary=saved['summary'];snapshot={'results':saved,'wall_seconds':done['wall_seconds'],'incremental_costs':incremental,'logical_recipe_costs':logical_cost,
        'reused_answer_rows_remaining':reuse_count,'new_answer_rows_remaining':1656-reuse_count,'transitions':changes,'contract_sha256':digest(c),'raw_and_source_sha256':captures}
    snapshot['export_manifest']=manifest;snapshot['combined_source_extraction']=combined_extraction;snapshot['input_agreement']=input_agreement
    write(ROOT/'artifacts/e1_stem_full_dev_results_snapshot.json',snapshot)
    s=summary['all_158'];delta=s['contrasts']['E0_M0']
    lines=['# 수정 추출 E1 + 기존 matcher M0: 전체 개발 집합 결과','',
        f"**158개 semantic item·1,895 주 분석 pair 완료.** 전체main1,896쌍 중 기존 사전 제외1쌍을 제외했다. Screen20문항240쌍(실행288쌍·pilot48포함)은 완료 결과를 재사용했고, 남은138문항1,656쌍만 새로 실행했다. 새 실행 wall은{done['wall_seconds']/60:.2f}분이다.",'',
        '**현재 결론:** 전체 정확도는73.98%→74.09%로 정답2개(+0.11pp) 증가에 그쳤고, 차이의 탐색95% CI[−0.47,+0.69]pp는0을 포함한다. Source 추출은 좋아졌지만 end-to-end 정확도 개선은 확인되지 않았다. 사용자가 선택한 E1 prompt는 바꾸지 않고 전체 산출물을 완성했다.','',
        '## 고정한 방법','',
        'Qwen3-VL의 기존 query-blind inventory → 고정 Qwen3-8B의 수정 stem referent 추출 E1 → 기존 GUI-conditioned 문자열 matcher M0 → source span의 결정적 치환 → Qwen3-VL MCQ 풀이. Options는 원본 그대로다. E1 prompt와 M0 prompt/model/decoding은 Screen2×2 이후 변경하지 않았다. 새 inventory 생성·M1·options 전체 번역·언어별 routing은 수행하지 않았다.','',
        '## 정확도','', '| 범위 | n | 기존 O | 기존 E0/M0 | 새 E1/M0 | R_stem |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for co,ss in summary.items():lines.append(f"| {co} | {ss['n']} | "+' | '.join(f"{ss['correct'][key]}/{ss['n']} ({ss['correct'][key]/ss['n']:.2%})" for key in ('O_B200','E0_M0','E1_M0','R_stem'))+' |')
    lines += ['', '| 범위 | 새−기존 E0/M0 | 95% item bootstrap CI | 회복/회귀 |','| --- | ---: | --- | ---: |']
    for co,ss in summary.items():
        x=ss['contrasts']['E0_M0'];lines.append(f"| {co} | {x['difference']*100:+.2f}pp | [{x['ci95'][0]*100:+.2f}, {x['ci95'][1]*100:+.2f}] | {x['recovery']}/{x['regression']} |")
    lines += ['', 'R_stem은 parallel stem 표현을 사용한 과거 reference이며 실제 screenshot exact-label oracle이 아니다. 모델/revision/system은 같으나 과거 RTX4090·batch4·혼합 조건 큐와 현재 B200·batch3의 차이가 있다. 전체158문항과 모든 부분 집합은 이미 반복 관찰한 development data다. 모든CI는 item 단위10,000회 bootstrap의 보정 전 탐색 구간이며 독립적인 confirmatory claim이 아니다.','',
        '## Source 추출과 처리 상태','', '| 집합 | Precision | Recall | F1 | 실제 수정 | fallback |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for co,q in saved['quality'].items():
        x=q['source_extraction'];lines.append(f"| {co} | {x['precision']:.2%} | {x['recall']:.2%} | {x['f1']:.2%} | {q['changed']} | {q['status'].get('fallback_original',0)} |")
    lines += ['', f"전체 source exact-span F1은기존{combined_extraction['E0']['f1']:.2%}→수정{combined_extraction['E1']['f1']:.2%}다. Selection에서는F1이83.68%→91.10%로 올라도 정확도는74.48%→73.22%로 낮아졌고, Internal에서는F1이88.96%→93.49%로 올라도 정확도는74.08%→74.22%였다. 추출 지표 개선을 곧바로 정렬/REL 개선으로 간주하지 않는다.",'',
        '새/기존 MCQ가 완전히 같은 사례에서 label이 달라진 것은0쌍이다. 정오가 바뀐26쌍 중1쌍(Screen)은 이름 내용이 같고 따옴표만 바뀐 기존 관찰 사례다. 모든 순증가를 의미 대응 개선으로 귀속하지 않는다.','']
    lines += ['', '추출 점수는 GT source span을 생성 후에만 읽은 pair-weighted exact-boundary 진단이다. Target matching 품질을 직접 뜻하지 않는다. 추출/출력 실패는 사전 원문 fallback으로 평가에 포함했다.','',
        '## GUI 언어별','', '| 집합 | GUI | n | 기존 E0/M0 | 새 E1/M0 | O | R_stem |','| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for co in ('selection','internal_evaluation','all_158'):
        for lang,g in summary[co]['by_gui'].items():lines.append(f"| {co} | {lang.upper()} | {g['n']} | "+' | '.join(f"{g['correct'][key]/g['n']:.2%}" for key in ('E0_M0','E1_M0','O_B200','R_stem'))+' |')
    lines += ['', '## 비용과 재사용','',f"남은 두 cohort의 실제 추가 wall은{done['wall_seconds']/60:.2f}분이다. Screen은 재실행하지 않았고 inventory 신규 호출은0회다. 새1,656개 풀이 행 중{reuse_count}개는 동일한 전체 ordered batch로 검증해 재사용하고{1656-reuse_count}개만 새로 계산했다.",'',
        '| 집합 | 새 추출 호출/캐시 hit | 새 matching 호출/캐시 hit | 실제 새 풀이 batch |','| --- | ---: | ---: | ---: |']
    for co,k in incremental.items():lines.append(f"| {co} | {k['extract']['calls']-k['extract']['cache_hits']}/{k['extract']['cache_hits']} | {k['match']['calls']-k['match']['cache_hits']}/{k['match']['cache_hits']} | {k['infer']['new_batches']} |")
    lines += ['', '| 주 분석 범위 | Inventory | E1 추출 | M0 matching | 풀이 | 처음부터 기록 구간 합 |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for co,q in logical_cost.items():lines.append(f"| {co} | "+' | '.join(f"{q[key]/60:.2f}분" for key in ('inventory_seconds','extraction_seconds','matching_seconds','answer_seconds','total_seconds'))+' |')
    lines += ['', '이 표는 cached 호출도 원래 runtime으로 청구한 standalone recipe 비용이다. 모델 적재·일부 CPU 작업은 제외하고 pilot 혼합 batch는 문항 수로 안분했다. 실제 새 실행 시간과 구별하며 서로 다른 시점의 cached 호출이 섞여 통제된 속도 벤치마크는 아니다.','',
        '## 보존·재현','',
        '원시와 계약은 `artifacts/e1_stem_full_dev_v1/`, Screen 원시는 기존 `artifacts/stem_refinement_2x2_screen_v1/`에 그대로 있다. source·prompt·model/config hash와 실제 cache provenance를 저장했다. 전체366문항 확장은 수행하지 않았다.','',
        '새 main MCQ 전체1,896쌍은 `artifacts/e1_stem_full_dev_v1/inputs_E1_M0_main1896.jsonl`로 모았다. 정답·GT span 없는 allowlist 입력이며 checksum·분모·cohort 원시 경로는 `full_set_manifest.json`에 있다. 이 export는pair ID순 데이터 파일이며 과거 예측의 실제 배치 구성과 구별한다.','',
        '[전체1,944행 예측 표](E1_STEM_FULL_DEV_CASES_KO.md) · [결과 snapshot](../artifacts/e1_stem_full_dev_results_snapshot.json) · [변경하지 않은 E1/M0 프롬프트](STEM_REFINEMENT_2X2_PROTOCOL_KO.md)','',
        '```bash','.venv/bin/python followup_rel_4lang/method_dev/scripts/report_e1_stem_full_dev.py','```','']
    (ROOT/'reports/E1_STEM_FULL_DEV_RESULTS_KO.md').write_text('\n'.join(lines).rstrip()+'\n')
    cases=['# E1/M0 전체 개발 집합 예측','','Main1,896+legacy pilot48행. 주 분석은main사전제외1쌍을 뺀1,895행.','',
        '| Cohort | Pair | split | 주 분석 | GT | 기존 E0/M0 | 새 E1/M0 | 상태 |','| --- | --- | --- | --- | --- | --- | --- | --- |']
    for co in ('screen',*COHORTS):
        for p in sorted(allrows[co]):cases.append(f"| {co} | `{p}` | {labels[p]['split']} | {'포함' if labels[p]['split']=='main' and p!=EXCLUDED else '제외'} | {labels[p]['gold_answer']} | {oldpred[co][p]['parsed_generated_label']} | {newpred[co][p]['parsed_generated_label']} | {allrows[co][p]['status']} |")
    (ROOT/'reports/E1_STEM_FULL_DEV_CASES_KO.md').write_text('\n'.join(cases)+'\n')
    print(json.dumps({'correct':s['correct'],'n':s['n'],'new_minus_old':delta,'wall_minutes':done['wall_seconds']/60,'reused_rows_remaining':reuse_count},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
