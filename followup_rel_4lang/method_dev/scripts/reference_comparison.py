"""Privileged post-hoc reference joins. Never imported by automatic method execution."""
import gzip,hashlib,json
from collections import Counter
from pathlib import Path
from mpr_crosslocale.methods.selective_alignment.schemas import digest,fields,render
try:
    from .search_pipeline import paired_bootstrap,EXCLUDED
except ImportError:
    from search_pipeline import paired_bootstrap,EXCLUDED


def stream(path):
    opener=gzip.open if path.suffix=='.gz' else open
    with opener(path,'rt',encoding='utf-8') as f:
        for line in f:
            if line.strip():yield json.loads(line)


def index_unique(rows,key):
    result={}
    for row in rows:
        k=key(row)
        if k in result:raise ValueError('Duplicate historical prediction; resolve attempts explicitly: '+str(k))
        result[k]=row
    return result


def resolve_orcf(pair_id,condition,conditions,predictions,original):
    row=conditions[pair_id,condition];representative=row['equivalent_to_condition'];alias=conditions[pair_id,representative]
    for k in ('question_stem','options','image_path','gold_answer','option_order'):
        if row[k]!=alias[k]:raise ValueError('ORCF representative is not identical: '+pair_id+'/'+k)
    for k in ('parallel_id','option_order'):
        if row[k]!=original[k]:raise ValueError('ORCF identity/order mismatch: '+pair_id)
    if row['gold_answer']!=original['gold_answer'] or 'followup_rel_4lang/'+row['image_path']!=original['image_path']:
        raise ValueError('ORCF gold/image mismatch: '+pair_id)
    if row['query_language']!=original['source_language'] or row['gui_language']!=original['gui_language']:
        raise ValueError('ORCF language-pair mismatch')
    pred=predictions[pair_id,representative]
    if pred['input_id']!='rel_orcf::'+pair_id+'::'+representative:raise ValueError('ORCF input ID mismatch')
    return pred,representative


def load_references(repo,labels,originals,use,expected_vlm,baseline_digest):
    base=repo/'followup_rel_4lang';expa=base/'artifacts/new_models_expA_20261115/analysis/expA_8b_20261114/qwen3/expA_qwen3/full';orcf=base/'artifacts/qwen3_single4090_20261107/full_rel'
    lock=json.loads(use(base/'dataset_lock.json').read_text());path=use(base/'data/rel_all_366/conditions_4lang.jsonl')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=lock['conditions_sha256']:raise ValueError('Frozen conditions checksum mismatch')
    contracts={name:json.loads(use(root/'run_contract.json').read_text()) for name,root in [('ExpA',expa),('ORCF',orcf)]}
    if digest(contracts['ExpA'])!=baseline_digest:raise ValueError('ExpA contract differs from method baseline contract')
    for c in contracts.values():
        if c['dataset_sha256']!=lock['conditions_sha256']:raise ValueError('Historical dataset lock differs')
        if any(c['model_config'][k]!=expected_vlm[k] for k in ('model_id','revision')):raise ValueError('Historical VLM mismatch')
    if contracts['ExpA']['model_config']!=contracts['ORCF']['model_config'] or contracts['ExpA']['system_prompt']!=contracts['ORCF']['system_prompt']:
        raise ValueError('Reference generation/model/system settings differ; review comparison explicitly')
    wanted=set(labels);conditions=index_unique((r for r in stream(path) if r['pair_id'] in wanted),lambda r:(r['pair_id'],r['condition']))
    ep=use(expa/'predictions.jsonl');op=use(orcf/'predictions.jsonl.gz')
    expa_rows=index_unique((r for r in stream(ep) if r['pair_id'] in wanted and r['condition'] in ('O','T','R')),lambda r:(r['pair_id'],r['condition']))
    orcf_rows={}
    for r in stream(op):
        if not r['input_id'].startswith('rel_orcf::'):raise ValueError('Unexpected ORCF ID schema')
        pid,c=r['input_id'][len('rel_orcf::'):].rsplit('::',1)
        if pid not in wanted:continue
        if (pid,c) in orcf_rows:raise ValueError('Duplicate ORCF prediction')
        orcf_rows[pid,c]=r
    refs={key:{} for key in ['O_EXP_A','T_REF','R_REF','O_ORCF','R_ORCF','F_REF']};aliases={}
    originals={pid:row for selected in originals.values() for pid,row in selected.items()}
    for pid,lab in labels.items():
        if lab['split']!='main':continue
        original={**originals[pid],'gold_answer':lab['gold_answer']}
        for old,new in [('O','O_EXP_A'),('T','T_REF'),('R','R_REF')]:
            r=expa_rows[pid,old]
            if r['gold_answer']!=lab['gold_answer'] or r['parallel_id']!=lab['parallel_id'] or r['query_language']!=original['source_language'] or r['gui_language']!=original['gui_language']:
                raise ValueError('ExpA paired identity/gold mismatch')
            if r.get('experiment_fingerprint')!=contracts['ExpA']['experiment_fingerprint']:raise ValueError('Mixed historical runs')
            refs[new][pid]=r
        for old,new in [('O','O_ORCF'),('R','R_ORCF'),('F','F_REF')]:
            r,alias=resolve_orcf(pid,old,conditions,orcf_rows,original)
            if r.get('experiment_fingerprint')!=contracts['ORCF']['experiment_fingerprint']:raise ValueError('Mixed ORCF runs')
            refs[new][pid]=r
            if old=='F':aliases[pid]=alias
    metadata={'definitions':{'T_REF':'ExpA: gold span + Gemma referent translation; source context retained','R_REF':'ExpA: gold span + parallel GUI-language referents; source context retained','F_REF':'ORCF: parallel GUI-language context and referents; not automatic GUI_FULL'},
        'source_runs':{name:{'path':str((expa if name=='ExpA' else orcf).relative_to(repo)),'batch_size':c['batch_size'],'model_config':c['model_config'],'system_prompt':c['system_prompt'],'software_versions':c.get('software_versions'),'fingerprint':c['experiment_fingerprint'],'hardware':next(iter(expa_rows.values()))['hardware'] if name=='ExpA' else next(iter(orcf_rows.values()))['hardware']} for name,c in contracts.items()},
        'identical_model_config_and_system':True,'different_batch_and_queue':True,'shared_dataset_sha256':lock['conditions_sha256'],
        'legacy_pilot_policy':'ExpA T/R cover main only; do not silently shrink or invent references for legacy pilot',
        'row_identity_checks':['pair_id','parallel_id','source/GUI language','gold','option order','ORCF image path','F representative exact field equality']}
    return refs,metadata,aliases


def is_correct(row,gold):return int(row.get('status')=='success' and row.get('parsed_generated_label')==gold)


def compare_cohorts(refs,metadata,aliases,outcomes,anchors,labels,records,run,originals,policy,oracle=None):
    result={'metadata':metadata,'cohorts':{}}
    for stage,methods in outcomes.items():
        ids={p for p in methods.get('O',{}) if labels[p]['split']=='main' and p!=EXCLUDED}
        if not ids:continue
        if any(set(values)!=ids for values in methods.values()):raise ValueError('New-method pair denominators differ')
        for name,values in refs.items():
            if not ids<=set(values):raise ValueError('Missing historical pairs; refusing denominator shrink: '+name)
        correct={name:{p:is_correct(values[p],labels[p]['gold_answer']) for p in ids} for name,values in refs.items()}
        by_gui={gui:{'n':sum(p.rsplit('::',1)[1]==gui for p in ids),'correct':{name:sum(values[p] for p in ids if p.rsplit('::',1)[1]==gui) for name,values in correct.items()},'new_O_correct':sum(methods['O'][p] for p in ids if p.rsplit('::',1)[1]==gui),'methods':{name:sum(values[p] for p in ids if p.rsplit('::',1)[1]==gui) for name,values in methods.items() if name!='O'}} for gui in sorted({p.rsplit('::',1)[1] for p in ids})}
        c={'n':len(ids),'items':len({labels[p]['parallel_id'] for p in ids}),'pair_ids_sha256':digest(sorted(ids)),
           'references':{name:{'correct':sum(values.values()),'n':len(ids)} for name,values in correct.items()},
           'new_O_correct':sum(methods['O'].values()),'by_gui':by_gui,'F_representatives':dict(Counter(aliases[p] for p in ids)),
           'O_EXP_A_agreement':sum(refs['O_EXP_A'][p]['parsed_generated_label']==anchors[stage][0][p] for p in ids),
           'O_ORCF_agreement':sum(refs['O_ORCF'][p]['parsed_generated_label']==anchors[stage][0][p] for p in ids),
           'R_cross_run_agreement':sum(refs['R_REF'][p]['parsed_generated_label']==refs['R_ORCF'][p]['parsed_generated_label'] for p in ids),'methods':{}}
        for method,values in methods.items():
            if method=='O':continue
            contrasts={}
            for reference in ['T_REF','R_REF','F_REF']:
                contrasts[reference]=paired_bootstrap(values,correct[reference],labels,policy['seed'],policy['bootstrap_replicates'])
            c['methods'][method]={'correct':sum(values.values()),'n':len(ids),'contrasts':contrasts}
        winner=policy.get('winner','GUI_EXACT')
        if winner in methods:
            trial=run/records[stage][winner]['trial'];rewrites={r['pair_id']:r for r in stream(trial/'rewritten.jsonl')}
            misses={p for p in ids if correct['R_REF'][p] and not methods[winner][p]};buckets=Counter();coverage=Counter();missed_recovery=0
            for p in misses:
                r=rewrites[p];changed=r['modified_question']!=render(fields(originals[stage][p]));extraction=r.get('extraction') or {}
                if extraction.get('status')=='failed':bucket='추출 검증 실패'
                elif (r.get('inventory') or {}).get('status')=='failed':bucket='Inventory 생성 실패'
                elif r['generation_status']=='fallback_original':bucket='후속 번역/출력 검증 실패'
                elif not changed:
                    matches=r['details'].get('matches',[])
                    bucket='유효 처리·exact match 채택 없음' if matches and not any(m['decision']=='match' for m in matches) else '유효 처리·최종 원문 유지'
                else:bucket='편집 적용 후에도 오답'
                buckets[bucket]+=1;missed_recovery+=not methods['O'][p]
                if oracle is not None:
                    predicted=r.get('extracted_referents')
                    if extraction.get('status')=='failed':coverage['추출 검증 실패']+=1
                    elif predicted is None:coverage['추출 span 미노출 조건']+=1
                    else:
                        gold={(x['field'],x['start'],x['end']) for x in oracle[p]};found={(x['field'],x['start'],x['end']) for x in predicted}
                        coverage['유효 추출·annotation span 전부 포함' if gold<=found else '유효 추출·annotation span 일부/전체 누락']+=1

            c['R_gap_diagnostic']={'R_correct_method_wrong':len(misses),'method_correct_R_wrong':sum(methods[winner][p] and not correct['R_REF'][p] for p in ids),
                'R_recovery_not_recovered':missed_recovery,'exclusive_observed_buckets':dict(buckets),'source_span_coverage':dict(coverage),'causal_attribution':False}
        result['cohorts'][stage]=c
    return result


def render_comparison(data,order):
    def percent(n,d):return f'{n/d*100:.2f}%'
    def pp(x):return f'{x*100:+.2f}pp'
    lines=['## 10. O/R/T/F와 같은 범위에서 비교','',
        '주 비교는 screen main240쌍, selection main239쌍, internal evaluation main1,416쌍으로 각각 고정한다. 모든 조건에 같은 pair ID·semantic item·source→GUI 언어·정답·보기 순서·원본 이미지 연결을 사용한다. 실패 예측은 오답으로 포함하고, 누락된 reference가 있으면 교집합으로 분모를 줄이지 않고 오류로 중단한다. 과거 ORCF 전체366문항의 요약치를 옮긴 것이 아니라 raw 예측을 현재 cohort와 ExpA의 사전 제외 규칙으로 다시 집계했다. Legacy pilot에는 ExpA T/R가 없어 별도 표를 유지하며 이4조건 비교에 섞지 않는다.','',
        '**Reference의 뜻:** T_REF는 annotation span을 Gemma로 번역한 과거 T, R_REF는 annotation span과 parallel 표현을 쓴 과거 R이다. 두 조건은 context를 source 언어로 유지한다. F_REF는 context와 referent 모두 GUI 언어인 parallel F다. 현재 자동 추출을 쓰는 TXT_SEL/GUI_EXACT 및 자동 전체 번역 GUI_FULL과 정보량·입력 생성 방식이 다르다. F_REF는 screenshot exact-label oracle이라고 보장된 조건도 아니다.','',
        '### 같은 분모의 정확도','', '| 조건 | screen (240) | selection (239) | internal evaluation (1,416) |','| --- | ---: | ---: | ---: |']
    stages=['screen','selection','internal_evaluation'];cohorts=data['cohorts']
    for name in ['O_CURRENT','O_EXP_A','O_ORCF','T_REF','R_REF','R_ORCF','F_REF',*order]:
        values=[]
        for stage in stages:
            c=cohorts.get(stage)
            if not c:values.append('미완료');continue
            hit=c['new_O_correct'] if name=='O_CURRENT' else c['references'].get(name,{}).get('correct') if name in c['references'] else c['methods'].get(name,{}).get('correct')
            values.append(f"{hit}/{c['n']} ({percent(hit,c['n'])})" if hit is not None else '미실행/미완료')
        lines.append('| '+name+' | '+' | '.join(values)+' |')
    lines+=['','O_CURRENT는 현재 method와 함께 재실행한 O다. O_EXP_A는 R/T와 같은 과거 실행, O_ORCF는 F와 같은 과거 실행의 O이며, 새 method가 아니다. R_REF의 기본 출처는 batch3 ExpA이고, R_ORCF는 F 실행과의 연결 확인용으로 별도 보존한다.','', '### 각 method의 R/T/F 대비 paired 차이','',
        '아래 Δ는 method − reference이며 같은 pair에서 계산했다. 회복/회귀와 item 단위10,000회 bootstrap95% CI는 snapshot JSON에 모든 완료 method에 대해 저장한다. 본문 CI는 선택된 GUI_EXACT와 전체 번역 GUI_FULL을 중심으로 제시한다. 실행 환경 차이로 생기는 변동은 bootstrap CI에 포함되지 않는다.']
    for stage,c in cohorts.items():
        lines+=['',f'#### {stage}', '', '| Method | 정확도 | ΔO_CURRENT | ΔT_REF | ΔR_REF | ΔF_REF |','| --- | ---: | ---: | ---: | ---: | ---: |']
        for method in order:
            if method not in c['methods']:continue
            r=c['methods'][method];lines.append(f"| {method} | {percent(r['correct'],c['n'])} | {pp((r['correct']-c['new_O_correct'])/c['n'])} | "+' | '.join(pp(r['contrasts'][ref]['difference']) for ref in ['T_REF','R_REF','F_REF'])+' |')
    lines+=['','| 집합 | 대비 | 차이 | 95% CI | 회복 / 회귀 |','| --- | --- | ---: | --- | ---: |']
    for stage,c in cohorts.items():
        for method in ['GUI_EXACT','GUI_FULL']:
            if method not in c['methods']:continue
            for ref,r in c['methods'][method]['contrasts'].items():lines.append(f"| {stage} | {method} − {ref} | {pp(r['difference'])} | [{pp(r['ci95'][0])}, {pp(r['ci95'][1])}] | {r['recovery']} / {r['regression']} |")
    lines+=['','### 실행 계약과 비교의 한계','',
        '모델 ID/revision·BF16·SDPA·2MP·system prompt·label-only/greedy/최대2token은 계약상 일치한다. 그러나 ExpA R/T는 batch3, ORCF F는 batch4이며 현재 method는 batch3다. 과거 RTX4090과 현재 B200 MIG, batch 동반 입력·queue와 소프트웨어 일부 버전도 다르다. 따라서 **문항 범위는 맞췄지만 동일 실행 조건으로 재측정한 대조는 아니다.** 작은 차이는 특히 조심해서 읽는다. 새 GPU 추론으로 reference를 재실행한 결과는 아니다.','',
        '| 집합 | 현재 O vs ExpA O label 일치 | 현재 O vs ORCF O | ExpA R vs ORCF R | F 대표 조건 |','| --- | ---: | ---: | ---: | --- |']
    for stage,c in cohorts.items():lines.append(f"| {stage} | {c['O_EXP_A_agreement']}/{c['n']} | {c['O_ORCF_agreement']}/{c['n']} | {c['R_cross_run_agreement']}/{c['n']} | "+', '.join(f'{k}: {v}' for k,v in c['F_representatives'].items())+' |')
    lines+=['','ORCF는 동일 pair 안의 동일 질문을 한 번만 추론했다. F가 다른 조건과 정확히 같으면 frozen conditions의 `equivalent_to_condition`을 따라 **질문·보기·이미지·정답·순서가 모두 같은 대표 예측**을 사용했다. Screen의 F238개는 직접 F 예측,2개는 F와 동일한 R 예측이다. 이는 누락을 임의 보간하거나 다른 pair의 답을 복사한 것이 아니다.','',
        '### GUI 언어별 reference 비교','']
    for stage,c in cohorts.items():
        lines += ['',f'#### {stage}', '', '| GUI | N | O_CURRENT | T_REF | R_REF | F_REF | GUI_EXACT | GUI_FULL |','| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
        for gui,v in c['by_gui'].items():lines.append(f"| {gui.upper()} | {v['n']} | {percent(v['new_O_correct'],v['n'])} | "+' | '.join(percent(v['correct'][ref],v['n']) for ref in ['T_REF','R_REF','F_REF'])+' | '+' | '.join(percent(v['methods'][name],v['n']) if name in v['methods'] else '미완료' for name in ['GUI_EXACT','GUI_FULL'])+' |')
    lines+=['','### R이 맞히지만 현재 GUI_EXACT가 놓치는 사례','',
        '다음은 결과 차이에 대한 관찰적 분해다. 우선순위를 둔 상호 배타적 분류로 각 pair를 한 번만 센다. 예를 들어 추출과 inventory가 함께 실패해도 먼저 추출 실패로 분류한다. 이 표만으로 해당 단계가 오답의 단독 원인이라고 입증하지 않는다.','',
        '| 집합 | R 정답·method 오답 | Method 정답·R 오답 | 그중 O도 오답이어서 회복을 놓친 수 |','| --- | ---: | ---: | ---: |']
    for stage,c in cohorts.items():
        d=c.get('R_gap_diagnostic')
        if d:lines.append(f"| {stage} | {d['R_correct_method_wrong']} | {d['method_correct_R_wrong']} | {d['R_recovery_not_recovered']} |")
    lines+=['','| 집합 | 관찰된 상태 | Pair 수 |','| --- | --- | ---: |']
    for stage,c in cohorts.items():
        for label,n in c.get('R_gap_diagnostic',{}).get('exclusive_observed_buckets',{}).items():lines.append(f'| {stage} | {label} | {n} |')
    lines+=['','R이 맞히고 method가 틀린 사례에서 source 추출을 별도로 다시 보면 다음과 같다. Annotation span 전부 포함은 recall에 대한 exact 진단이며 과다 추출이나 target matching의 정확성을 보장하지 않는다.','', '| 집합 | Source span 관찰 | Pair 수 |','| --- | --- | ---: |']
    for stage,c in cohorts.items():
        for label,n in c.get('R_gap_diagnostic',{}).get('source_span_coverage',{}).items():lines.append(f'| {stage} | {label} | {n} |')
    lines+=['','### Method를 더 개발할 때 우선할 일','',
        '현재 결과는 GCSA의 이득을 입증하지 못했고, R/F reference와의 격차가 크다. 여러 prompt를 실행했다는 사실만으로 구현이 충분히 성숙했다고 볼 수 없다. 일부 구조는 출력 계약과 coverage가 불안정한 상태로 큰 비교에 들어갔다. 다음 버전에서는 소규모 개발 표본에서 유효한 편집이 실제로 적용되는지 먼저 확인하고, 아래 병목을 분리해서 해결해야 한다.','',
        '1. **출력 인터페이스를 단순화한다.** 정답 annotation이 아닌 자동으로 얻고 원문에서 검증한 source 후보와 screenshot inventory 후보에만 안정적인 ID를 부여하고, 모델은 source ID→target 후보 ID/null을 고르게 하는 후보를 검토한다. 모델이 원문을 번역해 `text`에 넣거나 literal span_id를 반환하는 문제를 줄이는 것이 목적이다. 올바른 edit까지 한 오류 때문에 모두 버리는 정책도 per-edit 유효성·중복 보기·문맥 보존을 유지하면서 별도 ablation으로 비교한다.','',
        '2. **낮은 coverage의 원인을 나눈다.** 추출 recall, 원문 검증 실패, OCR 누락, 동의어 때문에 생긴 exact-match 거절, 실제 잘못된 label 선택을 따로 본다. Source 이름이 이미 주어진 뒤에도 matching이 실패하는지 oracle-span 진단으로 확인할 수 있지만, 이는 oracle_span 결과로 명시하고 automatic method 성능으로 합치지 않는다.','',
        '3. **Inventory의 잘림을 먼저 해결한다.** 출력 상한에 걸린 JSON 실패가 확인됐다. Compact 출력·중복 억제·필요시 query-blind 분할 전사 또는 출력 budget 확장을 각각 분리된 버전으로 검증한다. 더 긴 출력이나 crop은 비용과 정보량도 바꾸므로 prompt 보정과 동시에 섞어 성능 원인을 흐리지 않는다.','',
        '4. **Exact match를 넘어서는 대응을 안정화한다.** 단순 번역의 동의어를 화면 label에 연결하는 능력이 필요하다. ID 기반 inventory 선택과 독립 화면 검수를 우선하고, confidence는 확률처럼 취급하지 않는다. Span 경계 일치율이 높아도 target label이 틀릴 수 있다.','',
        '5. **선택과 검증 범위를 정직하게 관리한다.** 현재118개 내부 평가 결과도 이미 관찰했다. 이를 보고 v2를 고치고 같은 집합을 다시 사용하면 untouched evaluation이 아니라 development iteration이다. 기존 frozen artifact는 유지하고 변경 버전을 새로 기록한다. 최종 일반화는 별도 단계다. GUI 후보 최선과 전체 실용 baseline 최선도 나눠 보고하며, TXT_DIRECT_VLM을 포함해 고르는 것만으로 문제가 해결된다고 가정하지 않는다.','',
        '이 항목들은 현재 실패에 근거한 다음 개발 우선순위다. 새 method를 구현·실측해서 개선됐다는 결과가 아니며, 진행 중인 실험이나 reference artifact는 수정하지 않았다.']
    return '\n'.join(lines)
