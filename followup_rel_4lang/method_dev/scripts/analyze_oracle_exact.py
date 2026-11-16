"""Read-only analysis of completed Oracle GPU runs. Never calls an inference backend."""
import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO=Path(__file__).resolve().parents[3]
ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(REPO/'01_code/src'),str(Path(__file__).parent)]
from mpr_crosslocale.methods.selective_alignment.schemas import digest,fields,render
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits
from mpr_crosslocale.methods.selective_alignment.matcher import match
from mpr_crosslocale.inference.answer_parser import parse_label
from search_pipeline import paired_bootstrap,EXCLUDED
from reference_comparison import load_references

COHORTS=['screen','selection','internal_evaluation']
NAMES=['O','Automatic','Oracle','T_REF','R_REF','F_REF']


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def unique(rows,key):
    result={}
    for row in rows:
        k=key(row)
        if k in result:raise ValueError('Duplicate record: '+str(k))
        result[k]=row
    return result


def correct(row,gold):
    return int(row.get('status')=='success' and row.get('parsed_generated_label')==gold)


def stage_metrics(rows,gold):
    refs=sum(len(r['extracted_referents'] or []) for r in rows.values())
    matches=[m for r in rows.values() for m in r['details'].get('matches',[])]
    tp=fp=fn=0
    for pid,row in rows.items():
        predicted={(x['field'],x['start'],x['end']) for x in row['extracted_referents'] or []}
        annotated={(x['field'],x['start'],x['end']) for x in gold[pid]}
        tp+=len(predicted&annotated);fp+=len(predicted-annotated);fn+=len(annotated-predicted)
    return dict(referents=refs,changed_pairs=sum(bool(r['edits']) for r in rows.values()),
        edits=sum(len(r['edits']) for r in rows.values()),generation_status=dict(Counter(r['generation_status'] for r in rows.values())),
        match_reasons=dict(Counter(m['reason'] for m in matches)),logged_match_decisions=len(matches),unlogged_referents=refs-len(matches),
        source_span_tp=tp,source_span_fp=fp,source_span_fn=fn,annotation_recall=tp/(tp+fn) if tp+fn else None,
        fallback_reasons=dict(Counter(r['details'].get('error','unknown') for r in rows.values() if r['generation_status']=='fallback_original')))


def matching_coverage(rows,*,include_pairs=False):
    """Recompute matching from saved translations, including edits rejected downstream."""
    counts=Counter();hist=Counter();ratios=[];records=[]
    for row in rows:
        refs=row['extracted_referents'];n=len(refs)
        counts['pairs']+=1;counts['referents']+=n
        if not n:
            counts['no_referents']+=1;records.append({'pair_id':row['pair_id'],'referents':0,'matched':None,'state':'no_referents'});continue
        try:
            translated=json.loads(row['details']['raw_output'])
            if not isinstance(translated,dict) or set(translated)!={r['span_id'] for r in refs} or any(not isinstance(t,str) or not t.strip() for t in translated.values()):raise ValueError('Invalid translation IDs/values')
        except (ValueError,TypeError,KeyError):
            counts['unknown_pairs']+=1;counts['unknown_referents']+=n
            records.append({'pair_id':row['pair_id'],'referents':n,'matched':None,'state':'translation_invalid'});continue
        computed=[match(r,translated[r['span_id']],row['inventory']['entries'],1.0,.05) for r in refs]
        if 'matches' in row['details']:
            if computed!=row['details']['matches']:raise ValueError('Stored matching differs from deterministic replay')
        else:
            counts['replayed_unlogged_pairs']+=1;counts['replayed_unlogged_referents']+=n
            counts['replayed_unlogged_matches']+=sum(m['decision']=='match' for m in computed)
        k=sum(m['decision']=='match' for m in computed)
        counts['matched']+=k;counts['known_referents']+=n;counts['known_pairs']+=1;ratios.append(k/n)
        state='all' if k==n else 'partial' if k else 'none'
        counts[state]+=1;counts['any']+=k>0
        hist[f'{k}/{n}']+=1
        records.append({'pair_id':row['pair_id'],'referents':n,'matched':k,'state':state})
    result=dict(counts)
    for key in ['matched','known_pairs','known_referents','unknown_pairs','unknown_referents','no_referents','all','partial','none','any','replayed_unlogged_pairs','replayed_unlogged_referents','replayed_unlogged_matches']:result.setdefault(key,0)
    result.update(micro_confirmed_ratio=counts['matched']/counts['referents'] if counts['referents'] else None,
        macro_confirmed_ratio=sum(ratios)/counts['pairs'] if counts['pairs'] else None,
        mean_matched_per_pair=counts['matched']/counts['pairs'] if counts['pairs'] else None,
        mean_referents_per_pair=counts['referents']/counts['pairs'] if counts['pairs'] else None,
        histogram=dict(sorted(hist.items())))
    if include_pairs:result['pair_records']=records
    return result


def remaining_bucket(row):
    """Mutually exclusive observed states, not a causal attribution."""
    if row['generation_status']=='fallback_original':return '편집 검증 실패'
    if row['inventory']['status']=='failed':return 'Inventory 생성 실패'
    if row['edits']:return '편집 적용 후에도 오답'
    matches=row['details'].get('matches',[])
    if matches and not any(m['decision']=='match' for m in matches):return 'Exact match 채택 없음'
    return '기타 원문 유지'


def gap_diagnostic(values,automatic,oracle):
    old={p for p in values['Oracle'] if values['R_REF'][p] and not values['Automatic'][p]}
    new={p for p in values['Oracle'] if values['R_REF'][p] and not values['Oracle'][p]}
    coverage={}
    for pid in sorted(old):
        before=automatic[pid];after=oracle[pid]
        gold={(r['field'],r['start'],r['end']) for r in after['extracted_referents']}
        predicted={(r['field'],r['start'],r['end']) for r in before['extracted_referents'] or []}
        name='추출 검증 실패' if (before.get('extraction') or {}).get('status')=='failed' else 'Annotation span 전부 포함' if gold<=predicted else 'Annotation span 일부/전체 누락'
        group=coverage.setdefault(name,{'n':0,'recovered':0})
        group['n']+=1;group['recovered']+=values['Oracle'][pid]
    return dict(old_gap=len(old),new_gap=len(new),recovered_old_gap=len(old-new),remaining_old_gap=len(old&new),newly_lost_R_correct=len(new-old),
        old_gap_source_coverage=coverage,remaining_observed_states=dict(Counter(remaining_bucket(oracle[p]) for p in sorted(new))),causal_attribution=False)


def collect(run):
    sources={}
    def use(path):
        sources[str(path.relative_to(REPO))]=hashlib.sha256(path.read_bytes()).hexdigest()
        return path
    use(Path(__file__).resolve())
    labels=unique(read(use(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl')),lambda r:r['pair_id'])
    plans={c:json.loads(use(run/c/'plan.json').read_text()) for c in COHORTS}
    base=Path(plans['screen']['base_run'])
    original_cohorts={c:unique(read(use(run/c/'inputs.jsonl')),lambda r:r['pair_id']) for c in COHORTS}
    fingerprint=json.loads(use(base/'pipeline_contract.json').read_text())
    for name,expected in fingerprint['source_hashes'].items():
        if digest(use(REPO/name).read_text())!=expected:raise ValueError('Frozen implementation changed: '+name)
    refs,refmeta,_=load_references(REPO,labels,original_cohorts,use,plans['screen']['baseline_contract']['model_config'],plans['screen']['baseline_contract']['baseline_contract_sha256'])
    result={'as_of_utc':datetime.now(timezone.utc).isoformat(),'execution_mode':'gpu','diagnostic_only':True,'gold_target_used_for_rewrite':False,
        'source_run':str(run.relative_to(REPO)),'reference_metadata':refmeta,'cohorts':{}}
    pooled={name:{} for name in NAMES}
    examples=[]
    for cohort in COHORTS:
        directory=run/cohort;plan=plans[cohort];original=original_cohorts[cohort]
        complete=json.loads(use(directory/'COMPLETE.json').read_text())
        if complete['execution_mode']!='gpu' or complete['plan_sha256']!=digest(plan):raise ValueError('Complete GPU Oracle run required')
        if digest(list(original.values()))!=plan['inputs_sha256'] or digest(labels)!=plan['labels_sha256']:raise ValueError('Inputs or labels changed')
        if digest(use(ROOT/'scripts/run_oracle_exact.py').read_text())!=plan['runner_sha256']:raise ValueError('Oracle runner changed')
        trial=Path(complete['trial']);prediction=Path(complete['predictions'])
        for directory_stage in [trial,prediction]:
            if not (directory_stage/'COMPLETE').exists():raise ValueError('Incomplete stage')
            contract=json.loads(use(directory_stage/'contract.json').read_text())
            if contract['execution_mode']!='gpu' or contract['plan_sha256']!=digest(plan):raise ValueError('Mixed Oracle contracts')
        for path,key in [(Path(plan['automatic_trial'])/'rewritten.jsonl','automatic_rewrite_sha256'),(Path(plan['automatic_predictions'])/'predictions.jsonl','automatic_prediction_sha256')]:
            if hashlib.sha256(use(path).read_bytes()).hexdigest()!=plan[key]:raise ValueError('Automatic comparison changed')
        oracle_all=unique(read(use(trial/'rewritten.jsonl')),lambda r:r['pair_id'])
        predictions=unique(read(use(prediction/'predictions.jsonl')),lambda r:r['pair_id'])
        automatic_all=unique(read(Path(plan['automatic_trial'])/'rewritten.jsonl'),lambda r:r['pair_id'])
        automatic_predictions=unique(read(Path(plan['automatic_predictions'])/'predictions.jsonl'),lambda r:(r['pair_id'],r['condition']))
        if set(original)!=set(oracle_all) or set(original)!=set(predictions) or set(original)!=set(automatic_all):raise ValueError('Pair set differs')
        golden=unique(read(use(run/cohort/'oracle_source_spans.jsonl')),lambda r:r['pair_id'])
        inventory=json.loads(use(run/cohort/'frozen_inventories.json').read_text())
        if digest(list(golden.values()))!=plan['canonical_spans_sha256'] or digest(inventory)!=plan['inventories_sha256']:raise ValueError('Prepared Oracle artifacts changed')
        for pid,row in oracle_all.items():
            if row['execution_mode']!='gpu' or predictions[pid]['execution_mode']!='gpu':raise ValueError('Mock data in GPU report')
            if row['extracted_referents']!=golden[pid]['referents'] or row['inventory']!=inventory[row['image_sha256']]:raise ValueError('Oracle intervention changed')
            for k in ['parallel_id','source_language','gui_language','image_path','image_sha256','option_order']:
                if row[k]!=original[pid][k]:raise ValueError('Paired metadata changed')
            expected=apply_edits(original[pid],row['edits'])
            if expected!=fields(row) or render(expected)!=row['modified_question']:raise ValueError('Deterministic edit invariant failed')
            if parse_label(predictions[pid]['generated_text'])!=predictions[pid]['parsed_generated_label']:raise ValueError('Answer parse mismatch')
        ids=sorted(p for p in original if labels[p]['split']=='main' and p!=EXCLUDED)
        oracle={p:oracle_all[p] for p in ids};automatic={p:automatic_all[p] for p in ids}
        values={name:{} for name in NAMES}
        for pid in ids:
            gold=labels[pid]['gold_answer']
            for name,pred in [('O',automatic_predictions[pid,'O']),('Automatic',automatic_predictions[pid,'GUI_EXACT']),('Oracle',predictions[pid])]:values[name][pid]=correct(pred,gold)
            for name in ['T_REF','R_REF','F_REF']:values[name][pid]=correct(refs[name][pid],gold)
        saved=json.loads(use(run/cohort/'results.json').read_text())
        counts={name:sum(v.values()) for name,v in values.items()}
        contrasts={name:paired_bootstrap(values['Oracle'],values[name],labels,20261115,10000) for name in NAMES if name!='Oracle'}
        if len(ids)!=saved['primary_pairs'] or counts!=saved['correct'] or contrasts!=saved['contrasts']:raise ValueError('Saved results cannot be reproduced')
        by_gui={}
        by_direction={}
        for pid in ids:
            src,gui=original[pid]['source_language'],original[pid]['gui_language']
            for table,key in [(by_gui,gui),(by_direction,src+'→'+gui)]:
                g=table.setdefault(key,dict(n=0,correct={name:0 for name in NAMES},recovery=0,regression=0))
                g['n']+=1
                for name,v in values.items():g['correct'][name]+=v[pid]
                g['recovery']+=values['Oracle'][pid]>values['Automatic'][pid]
                g['regression']+=values['Oracle'][pid]<values['Automatic'][pid]
        calls=json.loads(use(trial/'calls.json').read_text());cost=json.loads(use(trial/'cost.json').read_text())
        if any(c['stage']!='translate' or c['execution_mode']!='gpu' for c in calls):raise ValueError('Unexpected method call')
        batches={}
        for row in predictions.values():
            identity=(row['batch_runtime_ms'],row['batch_size'])
            if row['batch_id'] in batches and batches[row['batch_id']]!=identity:raise ValueError('Inconsistent batch costs')
            batches[row['batch_id']]=identity
        same_question=sum(oracle[p]['modified_question']==automatic[p]['modified_question'] for p in ids)
        same_question_label_changes=sum(oracle[p]['modified_question']==automatic[p]['modified_question'] and predictions[p]['parsed_generated_label']!=automatic_predictions[p,'GUI_EXACT']['parsed_generated_label'] for p in ids)
        group=dict(executed_pairs=len(original),primary_pairs=len(ids),items=len({labels[p]['parallel_id'] for p in ids}),correct=counts,contrasts=contrasts,
            stages={name:stage_metrics(rows,{p:golden[p]['referents'] for p in ids}) for name,rows in [('Automatic',automatic),('Oracle',oracle)]},
            oracle_matching_coverage=matching_coverage(list(oracle.values())),
            oracle_matching_by_gui={gui:matching_coverage([r for r in oracle.values() if r['gui_language']==gui]) for gui in by_gui},
            by_gui=by_gui,by_direction=by_direction,same_question=same_question,same_question_label_changes=same_question_label_changes,
            R_gap=gap_diagnostic(values,automatic,oracle),cost=dict(method_wall_seconds=cost['wall_ms']/1000,new_call_runtime_seconds=cost['new_runtime_ms']/1000,
                new_model_load_seconds=cost['new_load_ms']/1000,calls=cost['calls'],cache_hits=cost['cache_hits'],
                inference_batch_seconds=sum(v[0] for v in batches.values())/1000,
                new_input_tokens=sum(c['input_tokens'] or 0 for c in calls if not c['cache_hit']),new_output_tokens=sum(c['output_tokens'] or 0 for c in calls if not c['cache_hit']),
                inference_input_tokens=sum(r['prompt_tokens'] or 0 for r in predictions.values()),inference_output_tokens=sum(r['output_tokens'] or 0 for r in predictions.values()),
                inference_peak_reserved_gib=max(r['peak_reserved_bytes'] for r in predictions.values())/2**30),
            prediction_status=dict(Counter(p['status'] for p in predictions.values())),attempts={s:len(list((run/cohort/s).glob('attempt_*'))) for s in ['rewrite','infer']})
        result['cohorts'][cohort]=group
        for name in NAMES:
            if set(pooled[name])&set(values[name]):raise ValueError('Cohorts overlap')
            pooled[name].update(values[name])
        if cohort=='internal_evaluation':
            selected=['rel::2/freeform_10.png::ru::th','rel::3/clock_2.jpg::en::th','rel::2/clock_9.png::ru::th','rel::2/note_2.png::zh::th']
            for pid in selected:
                examples.append(dict(pair_id=pid,original_question=render(fields(original[pid])),automatic_question=automatic[pid]['modified_question'],oracle_question=oracle[pid]['modified_question'],
                    automatic_edits=[{k:e[k] for k in ['field','text','replacement']} for e in automatic[pid]['edits']],oracle_edits=[{k:e[k] for k in ['field','text','replacement']} for e in oracle[pid]['edits']],
                    correct={name:v[pid] for name,v in values.items()},automatic_extraction_status=(automatic[pid].get('extraction') or {}).get('status')))
    result['pooled_descriptive']={'n':len(pooled['Oracle']),'correct':{name:sum(v.values()) for name,v in pooled.items()}}
    result['examples']=examples
    result['sources_sha256']=sources
    return result


def pct(k,n):return f'{k/n*100:.2f}%'
def escape(value):return str(value).replace('|','\\|').replace('\n',' ')


def markdown(s):
    rows=s['cohorts'];internal=rows['internal_evaluation'];n=internal['primary_pairs'];a=internal['stages']['Automatic'];o=internal['stages']['Oracle'];gap=internal['R_gap']
    out=['# Qwen3 Oracle source-span 진단 결과','',
        '**추출을 annotation으로 교정하면 기존 GUI_EXACT보다 개선되지만, 이것만으로 R의 효과를 재현하지는 못했다.** Internal 1,416쌍에서 69.56% → 71.54%(+1.98pp)였다. 원본 O 대비 +1.13pp의 95% CI는 0을 포함한다. 큰 시스템을 추가하기 전에 번역→화면 표현 대응의 coverage와 편집 후 회귀를 확인하는 것이 다음 과제다.','',
        f"집계 시각: {s['as_of_utc']}. 실제 GPU 실행 3 cohort 모두 완료, 총 1,944쌍. 아래 accuracy는 pilot 48쌍과 사전 제외 1쌍을 뺀 main 1,895쌍만 사용한다. 기존 예측과 hash·pair ID·span·inventory·deterministic edit를 재검증했고 저장된 정확도와 bootstrap CI를 독립 재계산해 일치시켰다. 추가 추론은 하지 않았다.",'',
        '## 1. 무엇을 바꾼 실험인가','',
        '기존 Automatic GUI_EXACT는 자동 추출한 referent를 Qwen3-8B로 번역하고, Qwen3-VL이 전사한 GUI inventory와 정규화 exact match하는 표현만 교체했다. Oracle은 **자동 추출 결과 대신 annotation의 source span**을 사용한다. 번역 모델·프롬프트·ID 규칙·inventory·matching·fallback·downstream Qwen3-VL 설정은 유지했다. Inventory의 기존 실패도 재생성하지 않았다.','',
        'Gold target 표현·R 질문·정답·bbox를 번역/편집 모델에 주지 않았다. O와 Automatic은 완료된 기존 예측을 재사용했고 Oracle 질문만 새로 풀었다. 따라서 이 실험은 **oracle_span 진단**이며 automatic method 성능이 아니다. 참조 집합이 바뀌면 공동 번역 payload와 번역 응답도 달라지므로, 추출 recall만의 순수 효과나 엄밀한 정확도 상한으로 해석하지 않는다.','',
        'T_REF는 annotation span + 기존 Gemma 번역, R_REF는 parallel referent alignment, F_REF는 parallel 전체 localization이다. 같은 pair로 맞췄지만 기존 ExpA는 RTX4090·batch3, ORCF는 RTX4090·batch4, 이번 Automatic/Oracle은 B200 MIG·batch3으로 GPU와 queue가 다르다. F_REF와 자동 GUI_FULL은 다른 조건이다.','',
        '## 2. 전체 결과','',
        '| 집합 | 주 분석 N | O | Automatic | Oracle | T_REF | R_REF | F_REF |','| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for cohort,g in rows.items():out.append('| '+cohort+' | '+str(g['primary_pairs'])+' | '+' | '.join(pct(g['correct'][name],g['primary_pairs']) for name in NAMES)+' |')
    pooled=s['pooled_descriptive'];out.append('| main 전체·기술 통계 | '+str(pooled['n'])+' | '+' | '.join(pct(pooled['correct'][name],pooled['n']) for name in NAMES)+' |')
    out+=['','Screen과 selection은 calibration에 속하며, internal과 구분한다. 전체 합계는 개발 표본의 기술 통계다. 이 158개 item은 이전 실험에서도 관찰됐으므로 독립적인 최종 일반화 평가로 취급하지 않는다.','',
        '| 집합 | Oracle − Automatic | 95% CI | 회복 | 회귀 | Oracle − O | 95% CI |','| --- | ---: | --- | ---: | ---: | ---: | --- |']
    for cohort,g in rows.items():
        c=g['contrasts']['Automatic'];d=g['contrasts']['O']
        out.append(f"| {cohort} | {c['difference']*100:+.2f}pp | [{c['ci95'][0]*100:+.2f}, {c['ci95'][1]*100:+.2f}] | {c['recovery']} | {c['regression']} | {d['difference']*100:+.2f}pp | [{d['ci95'][0]*100:+.2f}, {d['ci95'][1]*100:+.2f}] |")
    out+=['','CI는 semantic item을 단위로 10,000회 bootstrap한 탐색적 95% 구간이다. 아래 여러 비교에 대한 보정된 유의성을 주장하지 않는다. Screen / Selection / Internal에서 자기 질문이 Automatic과 같은데 출력 label이 달라진 pair는 각각 0 / 1 / 0개였다. Selection의 작은 순증가를 해석할 때도 이 변동을 고려한다.','',
        '### Internal에서 reference와 비교','',
        '| 대비 | 정답 수 차이 | 정확도 차이 | 95% CI | 회복 / 회귀 |','| --- | ---: | ---: | --- | ---: |']
    for name in ['Automatic','O','T_REF','R_REF','F_REF']:
        c=internal['contrasts'][name]
        out.append(f"| Oracle − {name} | {internal['correct']['Oracle']-internal['correct'][name]:+d} | {c['difference']*100:+.2f}pp | [{c['ci95'][0]*100:+.2f}, {c['ci95'][1]*100:+.2f}] | {c['recovery']} / {c['regression']} |")
    out+=['','## 3. 추출을 교정하면 어느 단계가 달라졌는가','',
        '| Internal 지표 | Automatic | Oracle |','| --- | ---: | ---: |']
    for label,key in [('Source referent 수·pair 반복 포함','referents'),('실제 질문이 바뀐 pair','changed_pairs'),('적용된 edit 수','edits')]:out.append(f"| {label} | {a[key]:,} | {o[key]:,} |")
    out.append(f"| 오류 fallback pair | {a['generation_status'].get('fallback_original',0)} | {o['generation_status'].get('fallback_original',0)} |")
    out.append(f"| Annotation source span recall | {a['annotation_recall']*100:.2f}% | 100.00%·정의상 |")
    out.append(f"| 저장된 exact match 채택 수 | {a['match_reasons'].get('normalized_exact',0):,}/{a['logged_match_decisions']:,} | {o['match_reasons'].get('normalized_exact',0):,}/{o['logged_match_decisions']:,} |")
    out+=['',f"Automatic fallback {a['generation_status'].get('fallback_original',0)}건 중 {a['fallback_reasons'].get('Missing extraction',0)}건은 추출 검증 실패로 referent를 전달하지 못한 경우이고, 나머지는 번역 JSON 오류였다. Oracle에서는 이 경로가 제거됐고, 남은 fallback 1건은 **번역 후 보기 중복**으로 인한 편집 검증 실패였다. 이를 번역 JSON 실패로 분류하지 않는다.",'',
        f"Oracle에서는 편집 대상과 실제 치환이 늘었지만, 저장된 match 판단 {o['logged_match_decisions']:,}개 중 {o['match_reasons'].get('normalized_exact',0):,}개({o['match_reasons'].get('normalized_exact',0)/o['logged_match_decisions']*100:.2f}%)만 exact match했다. {o['match_reasons'].get('low_similarity_or_missing_evidence',0):,}개는 번역문과 inventory가 일치하지 않았고 {o['match_reasons'].get('inventory_empty_or_failed',0):,}개는 inventory가 비거나 실패했다. 편집 검증 fallback에 걸린 {o['unlogged_referents']}개 referent는 기존 로그가 중간 match 판단을 보존하지 않아 이 분모에서 빠진다. 이 수치는 **matching 정확도가 아니라 채택 coverage**다.",'',
        f"자기 질문이 Automatic과 동일한 pair는 {internal['same_question']}/{n}개이며, 이 중 출력 label이 바뀐 것은 {internal['same_question_label_changes']}개였다. 실제 추가/변경 편집이 있는 사례에서 관찰된 회복과 회귀를 아래에서 본다. Batch 구성원을 유지했어도 동반 질문 길이와 padding은 달라질 수 있다.",'',
        '### 문항 전체가 exact match한 비율','',
        '| 집합 | Referent별 확인된 match | 문항별 match 비율 평균 | 1개 이상 match | 모든 referent match |','| --- | ---: | ---: | ---: | ---: |']
    for cohort,g in rows.items():
        c=g['oracle_matching_coverage'];size=c['pairs']
        out.append(f"| {cohort} | {c['matched']:,}/{c['referents']:,} ({c['micro_confirmed_ratio']*100:.2f}%) | {c['macro_confirmed_ratio']*100:.2f}% | {c['any']}/{size} ({c['any']/size*100:.2f}%) | {c['all']}/{size} ({c['all']/size*100:.2f}%) |")
    c=internal['oracle_matching_coverage']
    out+=['',f"Internal에서는 한 문항·언어쌍에 평균 {c['mean_referents_per_pair']:.2f}개의 annotation referent가 있고, 그중 평균 {c['mean_matched_per_pair']:.2f}개가 match했다. **전체 referent가 match한 것은 {c['all']}/{n}쌍({c['all']/n*100:.2f}%)**뿐이다. 일부만 match한 {c['partial']}쌍과 하나도 match하지 않은 {c['none']}쌍을 구분한다. Referent가 없는 field는 분모에 억지로 넣지 않는다.",'',
        '위 표는 저장된 번역 JSON에서 matcher를 CPU로 재실행한 값이다. Internal의 보기 중복 fallback 1쌍에서 중간 로그가 빠졌던 5개 referent를 복원했고, 이 중 2개가 match했다. 따라서 전체 matching 단계 기준은 1,968/6,420이며, 앞의 저장된 match 로그 기준 1,966/6,415와 다르다. 최종 적용 edit 1,904개와도 다른 지표다. 이미 같은 숫자/이름도 exact match로 센다.','',
        'Screen에서는 번역 JSON 실패 2쌍의 7개 referent를 판정할 수 없다. 표의 전체 분모에는 유지하되 확인된 match 분자에는 넣지 않았고, 실제 no-match와 구별한다. 전체 match는 모델이 제안한 번역과 inventory의 일치이며 R_REF와의 표현 동일성이나 실제 GUI 대응 정답률을 뜻하지 않는다.','',
        '### 기존 R gap 259건은 얼마나 회복됐나','',
        f"기존 R 정답·Automatic 오답 {gap['old_gap']}건 중 Oracle이 {gap['recovered_old_gap']}건을 회복했다. {gap['remaining_old_gap']}건은 여전히 오답이며, 반대로 R과 Automatic이 맞혔지만 Oracle이 새로 틀린 {gap['newly_lost_R_correct']}건이 생겼다. 그 결과 R 정답·Oracle 오답은 {gap['new_gap']}건이다.",'',
        '| 기존 R gap의 source span 상태 | 기존 N | Oracle 회복 |','| --- | ---: | ---: |']
    for name,g in gap['old_gap_source_coverage'].items():out.append(f"| {name} | {g['n']} | {g['recovered']} |")
    out+=['','| R 정답·Oracle 오답의 관찰 상태 | 건수 |','| --- | ---: |']
    for name,count in gap['remaining_observed_states'].items():out.append(f'| {name} | {count} |')
    out+=['','상태 분류는 편집 검증 실패 → inventory 실패 → 편집 적용 → exact match 미채택 → 기타 순서로 상호 배타적으로 집계했다. **원인의 인과 분해는 아니다.** 예를 들어 편집 후 오답은 잘못된 치환, 일부 참조만 치환, 또는 REL 문제 풀이 오류일 수 있다. Inventory 실패 수만으로 OCR의 전체 영향 크기를 정할 수도 없다.','',
        '## 4. 이득은 Thai GUI에 집중됐다','',
        '| GUI | N | O | Automatic | Oracle | Oracle − Automatic | 회복 / 회귀 | R_REF |','| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for gui in ['en','zh','th','ru']:
        g=internal['by_gui'][gui];v=g['correct'];size=g['n']
        out.append(f"| {gui.upper()} | {size} | {pct(v['O'],size)} | {pct(v['Automatic'],size)} | {pct(v['Oracle'],size)} | {(v['Oracle']-v['Automatic'])/size*100:+.2f}pp | {g['recovery']} / {g['regression']} | {pct(v['R_REF'],size)} |")
    out+=['','Thai GUI에서 +24개가 늘어 전체 순증가 +28개의 85.7%를 차지했다. 추출 교정이 Thai에서 특히 유용했지만 Oracle 54.52%와 R 83.62% 사이에는 큰 차이가 남는다. 이것만으로 target 언어 난이도가 원인이라고 확정하지는 않는다. 번역 표현 선택·OCR·표기 차이와 부분 치환을 나눠 확인해야 한다.','',
        '## 5. 실제 회복·회귀 예시','',
        '아래는 raw 기록에서 선택한 internal 사례다. 화면을 새로 검수한 matching 정답 판정은 아니며, 각 치환이 왜 모델 답을 바꿨는지까지 확정하지 않는다. 전체 pair별 비교는 각 cohort의 `paired_outcomes.jsonl`에 있다.']
    for e in s['examples']:
        v=e['correct'];transition='회복' if v['Oracle']>v['Automatic'] else '회귀'
        out+=['',f"### {transition}: `{e['pair_id']}`",'',f"정오(O / Automatic / Oracle / T / R / F): {' / '.join(str(v[name]) for name in NAMES)}. Automatic 추출 상태: `{e['automatic_extraction_status']}`.",'',
            '| 조건 | field: 원문 → 치환 |','| --- | --- |']
        for name,key in [('Automatic','automatic_edits'),('Oracle','oracle_edits')]:out.append('| '+name+' | '+('; '.join(escape(f"{r['field']}: {r['text']} → {r['replacement']}") for r in e[key]) or '치환 없음')+' |')
        out+=['','원본 MCQ:','', '```text',e['original_question'],'```']
    out+=['','Freeform 회복 사례에서는 기존 추출에서 빠진 A의 펜 설정 표현이 추가됐고, clock 회복에서는 stem의 Additional settings가 추가됐다. 두 사례의 기존 추출은 형식 검증에는 성공했지만 필요한 표현을 놓쳤다. 반면 clock 회귀는 Oracle이 보기에 태국어를 넣은 후 기존 정답을 잃은 사례다. Note 사례에서는 두 조건 모두 A의 拷贝 span을 사용했지만, Automatic 번역은 คัดลอก, Oracle 번역은 สำเนา였다. Inventory와 exact match한 전자만 적용됐고 Oracle은 A의 치환을 잃었다. 전체 referent 집합이 바뀌면 같은 표현도 공동 번역 결과가 달라질 수 있으므로, 항상 자동 span에 gold span을 단순 추가한 실험으로 보면 안 된다.','',
        '## 6. 추가 계산 비용과 완료 상태','',
        '| Cohort | 번역 wall·분 | 새 번역 호출 / 전체 | Inference batch 합계·분 | Inference peak reserved·GiB |','| --- | ---: | ---: | ---: | ---: |']
    for cohort,g in rows.items():
        c=g['cost'];out.append(f"| {cohort} | {c['method_wall_seconds']/60:.2f} | {c['calls']-c['cache_hits']}/{c['calls']} | {c['inference_batch_seconds']/60:.2f} | {c['inference_peak_reserved_gib']:.2f} |")
    totalwall=sum(g['cost']['method_wall_seconds'] for g in rows.values())/60;totalinfer=sum(g['cost']['inference_batch_seconds'] for g in rows.values())/60
    out+=['',f"번역 단계 wall 합계 {totalwall:.2f}분, downstream batch 시간 합계 {totalinfer:.2f}분이다. 후자는 batch당 값을 한 번만 셌고 inference 모델 적재·전체 프로세스 기동·보고서 생성 시간은 포함하지 않는다. 따라서 두 값을 전체 실행 wall time으로 부르지 않는다. 비용 분모는 pilot·사전 제외 pair를 포함한 실행 1,944쌍이다.",'',
        '각 cohort의 rewrite와 inference는 attempt 1회씩 완료됐다. 예측은 전부 GPU 모드·success였으며 OOM으로 인한 batch 축소나 표본 제외는 없었다. Inventory와 extractor 신규 호출은 0회다. 캐시 hit의 과거 runtime을 신규 비용으로 다시 합산하지 않았다. Dollar 비용은 기록이 없어 추정하지 않았다. Token 사용량과 원시 파일 SHA-256은 snapshot에 보존한다.','',
        '## 7. 다음에 할 최소 변경','',
        '1. **같은 Oracle source span을 고정한 채 남은 matching 실패를 표본 검수한다.** 번역문 불일치인지, inventory 누락인지, 원래 화면에 직접 대응하지 않는 표현인지 구별한다. 현재 exact-match 미채택 80건은 R 정답·Oracle 오답의 한 관찰 집단이며 전체 번역/OCR 오류 수는 아니다.',
        '2. 그 원인에 맞는 **유연한 matching 한 조건만** 기존 Oracle+Exact와 비교한다. 번역기·span·inventory·fallback은 함께 바꾸지 않는다. Inventory에 없는 표현을 허용하려면 별도 ablation으로 표시한다.',
        '3. 편집 후에도 틀린 136건과 새 회귀 24건을 함께 본다. 부분 치환 및 잘못된 대응을 확인하지 않고 coverage만 올리면 회귀도 늘 수 있다.',
        '4. 유망한 matching이 확인되면 그때 자동 추출기로 되돌려 실제 method의 이득과 비용을 평가한다. 현재 결과만으로 NER 도입이나 inventory 제거를 결정할 근거는 부족하다.','',
        '새 GPU 실험은 이번 집계에서 실행하지 않았다. 이번 결과는 extraction 개선이 무의미하다는 결론도, extraction만 개선하면 충분하다는 결론도 지지하지 않는다. 현 pipeline에서 추출 교정으로 일부 회복했고, 큰 잔여 gap이 남았다는 범위까지 확인했다.','',
        '## 부록: Internal 12방향 결과','',
        '| Source → GUI | N | O | Automatic | Oracle | T_REF | R_REF | F_REF | 회복 / 회귀 |','| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for direction,g in sorted(internal['by_direction'].items()):out.append('| '+direction+' | '+str(g['n'])+' | '+' | '.join(pct(g['correct'][name],g['n']) for name in NAMES)+f" | {g['recovery']} / {g['regression']} |")
    out+=['','재현 명령:','', '```bash','.venv/bin/python followup_rel_4lang/method_dev/scripts/analyze_oracle_exact.py','```','',
        '실행 설정: [Oracle 실행안](ORACLE_SPAN_EXACT_KO.md). 원시 결과 루트: `'+s['source_run']+'`. 집계값·입력 SHA-256: [oracle_exact_results_snapshot.json](../artifacts/oracle_exact_results_snapshot.json). 기존 method 탐색 결과: [SEARCH_RESULTS_KO.md](SEARCH_RESULTS_KO.md).']
    return '\n'.join(out)+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',type=Path,default=ROOT/'artifacts/oracle_span_exact_v1')
    p.add_argument('--report',type=Path,default=ROOT/'reports/ORACLE_RESULTS_KO.md')
    p.add_argument('--snapshot',type=Path,default=ROOT/'artifacts/oracle_exact_results_snapshot.json')
    args=p.parse_args();snapshot=collect(args.run_dir.resolve())
    for path,value in [(args.report,markdown(snapshot)),(args.snapshot,json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n')]:
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value)
    print(json.dumps({'report':str(args.report),'snapshot':str(args.snapshot),'completed_cohorts':list(snapshot['cohorts'])},ensure_ascii=False))


if __name__=='__main__':main()
