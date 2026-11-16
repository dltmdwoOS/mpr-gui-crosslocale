"""Read-only rolling results: complete transformation blocks are not VLM predictions."""
import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(REPO),str(REPO/'01_code/src'),str(Path(__file__).parent)]
from followup_rel_4lang.method_dev.two_stage_v2 import prompts
from mpr_crosslocale.methods.selective_alignment.schemas import digest,fields,render
from search_pipeline import EXCLUDED,paired_bootstrap
from two_stage_completed import add_completed,render_completed

COHORTS=('screen','selection','internal_evaluation')


def snapshot_lines(path):
    """Ignore only an unfinished trailing write; never score an incomplete condition."""
    data=path.read_bytes();lines=data.splitlines(keepends=True)
    rows=[json.loads(line) for line in lines if line.endswith(b'\n') and line.strip()]
    return rows,{'path':str(path.relative_to(REPO)),'captured_bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'complete_lines':len(rows)}


def index(rows,key):
    out={}
    for row in rows:
        value=key(row)
        if value in out:raise ValueError('Duplicate row: '+str(value))
        out[value]=row
    return out


def latest(directory,complete=False):
    items=sorted(directory.glob('attempt_*'))
    if complete:items=[p for p in items if (p/'COMPLETE').exists()]
    return items[-1] if items else None


def source_stats(rows,all_fields,stem_only,oracle):
    unique={(r['parallel_id'],r['source_language']):r for r in rows}
    result={'source_mcqs':len(unique),'paired':{},'scopes':{}}
    scopes={'all_fields':all_fields,'stem_only':stem_only}
    for name,data in scopes.items():
        counts=Counter();tp=fp=fn=0;fail_fields=Counter()
        for row in unique.values():
            key=digest(prompts.extraction_payload(row,stem_only=name=='stem_only'));entry=data[key]
            counts['failed']+=entry['status']=='failed';counts['repair_attempted']+=len(entry['attempts'])>1
            counts['repair_recovered']+=len(entry['attempts'])>1 and entry['status']=='success'
            counts['valid_but_no_stem_ref']+=entry['status']=='success' and not any(x['field']=='question_stem' for x in entry['referents'] or [])
            if entry['status']=='failed':
                fail_fields.update(entry['failure_fields'])
                counts['option_only_failed']+=bool(entry['failure_fields']) and all(f in ('A','B','C','D') for f in entry['failure_fields'])
            gold={(x['field'],x['start'],x['end']) for x in oracle[row['pair_id']] if x['field']=='question_stem'}
            found={(x['field'],x['start'],x['end']) for x in entry['referents'] or [] if x['field']=='question_stem'}
            tp+=len(gold&found);fp+=len(found-gold);fn+=len(gold-found)
        result['scopes'][name]={**dict(counts),'failure_fields':dict(fail_fields),'stem_spans':{'tp':tp,'fp':fp,'fn':fn,
            'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}}
    paired=Counter()
    for row in unique.values():
        a=all_fields[digest(prompts.extraction_payload(row))]['status']
        b=stem_only[digest(prompts.extraction_payload(row,stem_only=True))]['status']
        paired[a+'->'+b]+=1
    result['paired']=dict(paired)
    return result


def transformation_stats(rows,originals,inventories):
    calls=[a for r in rows for a in r['attempts']];misses=[c for c in calls if not c['cache_hit']]
    result={'pairs':len(rows),'status':dict(Counter(r['status'] for r in rows)),
        'initial_calls':sum(a['stage']=='full' for a in calls),'structure_repairs':sum(a['stage']=='full_repair' for a in calls),
        'semantic_repairs':sum(a['stage']=='full_semantic_repair' for a in calls),'semantic_repairs_accepted':sum(bool(r.get('semantic_repair_accepted')) for r in rows),
        'remaining_semantic_pairs':sum(bool(r.get('semantic_reasons')) for r in rows),'remaining_semantic_reasons':dict(Counter(reason for r in rows for reason in r.get('semantic_reasons',[]))),
        'diagnostic_pairs':sum(bool(r.get('diagnostics')) for r in rows),'diagnostics':dict(Counter(reason.split(':',1)[0] for r in rows for reason in r.get('diagnostics',[]))),
        'inventory_failed_pairs':sum(r.get('inventory_status') not in (None,'success') for r in rows) if any(r.get('inventory_status') is not None for r in rows) else None,
        'changed_pairs':sum(fields(r)!=fields(originals[r['pair_id']]) for r in rows),'new_call_runtime_seconds':sum(a['runtime_ms'] for a in misses)/1000,
        'model_load_seconds':sum(a['model_load_ms'] for a in misses)/1000,'peak_reserved_gib':max((a['peak_reserved_bytes'] or 0 for a in calls),default=0)/2**30}
    result['by_gui']={gui:{'pairs':len(selected),'semantic_repairs':sum(any(a['stage']=='full_semantic_repair' for a in r['attempts']) for r in selected),
        'remaining_semantic_pairs':sum(bool(r.get('semantic_reasons')) for r in selected)} for gui in sorted({r['gui_language'] for r in rows}) if (selected:=[r for r in rows if r['gui_language']==gui])}
    return result


def accuracy_if_complete(rows,originals,labels,candidate):
    values=index([r for r in rows if r['condition'] in ('O',candidate)],lambda r:(r['condition'],r['pair_id']))
    expected=set(originals)
    if any({p for c,p in values if c==condition}!=expected for condition in ('O',candidate)):return None
    if any(r['execution_mode']!='gpu' for r in values.values()):raise ValueError('Mock cannot enter empirical accuracy')
    ids=sorted(p for p in expected if labels[p]['split']=='main' and p!=EXCLUDED)
    if not ids:return None
    correct={condition:{p:int(values[condition,p]['status']=='success' and values[condition,p]['parsed_generated_label']==labels[p]['gold_answer']) for p in ids} for condition in ('O',candidate)}
    return {'n':len(ids),'correct':sum(correct[candidate].values()),'O_correct':sum(correct['O'].values()),'vs_O':paired_bootstrap(correct[candidate],correct['O'],labels,20261115,10000)}


def collect(run):
    sources={}
    def read(path):
        rows,info=snapshot_lines(path);sources[info['path']]=info;return rows
    contract=json.loads((run/'contract.json').read_text())
    if contract['mode']!='gpu':raise ValueError('GPU run required')
    for filename,sha in contract['source_hashes'].items():
        if hashlib.sha256((REPO/filename).read_bytes()).hexdigest()!=sha:raise ValueError('Live execution source changed: '+filename)
    labels=index(read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'),lambda r:r['pair_id'])
    annotated=read(ROOT/'artifacts/dataset_audit/oracle_spans_DIAGNOSTIC_ONLY.jsonl')
    if digest(labels)!=contract['base_data_contract']['labels'] or digest(annotated)!=contract['base_data_contract']['oracle']:raise ValueError('Evaluation artifacts changed')
    oracle={r['pair_id']:r['referents'] for r in annotated}
    result={'as_of_utc':datetime.now(timezone.utc).isoformat(),'run':str(run.relative_to(REPO)),'cohorts':{},'source_captures':sources,
        'interpretation':'Completed transformation is not completed downstream inference. Historical invalidated results are not reused.',
        'analysis_source_sha256':{name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in ['update_two_stage_results.py','two_stage_completed.py','reference_comparison.py']}}
    for cohort in COHORTS:
        work=run/cohort
        if not (work/'inputs.jsonl').exists():continue
        original_rows=read(work/'inputs.jsonl');originals=index(original_rows,lambda r:r['pair_id'])
        plan=json.loads((work/'plan.json').read_text())
        if digest(original_rows)!=plan['input_sha256']:raise ValueError('Input plan changed')
        groups={'all':original_rows,'main':[r for r in original_rows if labels[r['pair_id']]['split']=='main' and r['pair_id']!=EXCLUDED],
                'pilot':[r for r in original_rows if labels[r['pair_id']]['split']=='pilot']}
        group_ids={name:{r['pair_id'] for r in selected} for name,selected in groups.items()}
        progress={'pairs':len(original_rows),'primary_pairs':len(groups['main']),'stages':{},'transformations':{},'accuracies':{}}
        progress['cohort_complete']=(work/'COMPLETE.json').exists()
        completed={}
        for stage,filename,key in [('inventory','inventories.jsonl','image_sha256'),('extract','extractions.jsonl','source_key'),('extract_stem','extractions.jsonl','source_key')]:
            attempt=latest(work/stage,True)
            if not attempt:
                active=latest(work/stage);progress['stages'][stage]={'complete':False,'started':active is not None};continue
            stage_contract=json.loads((attempt/'contract.json').read_text())
            if stage_contract['execution_mode']!='gpu' or stage_contract['input_sha256']!=plan['input_sha256']:raise ValueError('Mixed stage contract')
            data=read(attempt/filename);completed[stage]=index(data,lambda r:r[key])
            progress['stages'][stage]={'complete':True,'rows':len(data),'attempt':str(attempt.relative_to(REPO)),
                'cost':json.loads((attempt/'cost.json').read_text())}
        if 'inventory' in completed:
            progress['inventory']={}
            for name,selected in groups.items():
                hashes={r['image_sha256'] for r in selected};entries=[completed['inventory'][h] for h in hashes]
                progress['inventory'][name]={'images':len(entries),'success':sum(e['status']=='success' for e in entries),'repair_attempted':sum(len(e['attempts'])>1 for e in entries),
                    'repair_recovered':sum(len(e['attempts'])>1 and e['status']=='success' for e in entries),'failed':sum(e['status']!='success' for e in entries),
                    'affected_pairs':sum(completed['inventory'][r['image_sha256']]['status']!='success' for r in selected)}
            progress['inventory_failures']=[{'parallel_id':r['parallel_id'],'gui_language':r['gui_language'],'errors':completed['inventory'][r['image_sha256']]['errors']} for r in {r['image_sha256']:r for r in original_rows}.values() if completed['inventory'][r['image_sha256']]['status']!='success']
        if {'extract','extract_stem'}<=set(completed):
            progress['extraction']={name:source_stats(selected,completed['extract'],completed['extract_stem'],oracle) for name,selected in groups.items() if selected}
        rewrite=latest(work/'rewrite');predictions=latest(work/'infer');pred=[]
        if predictions and (predictions/'predictions.jsonl').exists():pred=read(predictions/'predictions.jsonl')
        progress['inference_rows']=len(pred)
        for condition in contract['conditions']:
            path=rewrite/(condition+'.jsonl') if rewrite else None
            transformed=read(path) if path and path.exists() else []
            complete=len(transformed)==len(originals) and {r['pair_id'] for r in transformed}==set(originals)
            entry={'transformation_rows':len(transformed),'expected_rows':len(originals),'transformation_complete':complete,
                   'inference_rows':sum(r['condition']==condition for r in pred)}
            if complete:
                if any(r['execution_mode']!='gpu' or r['condition']!=condition or r['modified_question']!=render(fields(r)) for r in transformed):raise ValueError('Invalid completed transformation')
                for row in transformed:
                    if any(row[k]!=originals[row['pair_id']][k] for k in ['image_sha256','image_path','parallel_id','source_language','gui_language','option_order']):raise ValueError('Paired metadata changed')
                # Full transforms have meaningful full/semantic-repair counters. Selective/hybrid are summarized by status.
                entry['groups']={name:(transformation_stats([r for r in transformed if r['pair_id'] in group_ids[name]],originals,completed.get('inventory')) if condition.startswith('TS_FULL_') else {'pairs':len(selected),'status':dict(Counter(r['status'] for r in transformed if r['pair_id'] in group_ids[name]))}) for name,selected in groups.items() if selected}
                entry['flagged_examples']=[{'pair_id':r['pair_id'],'source_stem':originals[r['pair_id']]['question_stem'],'target_stem':r['question_stem'],
                    'source_options':originals[r['pair_id']]['options'],'target_options':r['options'],
                    'semantic_reasons':r.get('semantic_reasons',[]),'diagnostics':r.get('diagnostics',[])} for r in transformed if labels[r['pair_id']]['split']=='main' and (r.get('semantic_reasons') or r.get('diagnostics'))]
            progress['transformations'][condition]=entry
            accuracy=accuracy_if_complete(pred,originals,labels,condition) if pred else None
            if accuracy:progress['accuracies'][condition]=accuracy
        result['cohorts'][cohort]=progress
    add_completed(result,run,REPO,ROOT,labels,contract,read)
    return result


def markdown(s):
    out=['# Two-stage 재정비 실험 중간 결산','',
        '후속 개발 실험: [Stem 추출·정렬 통합 조건](SINGLE_PASS_STEM_GUI_KO.md). 기존 inventory·baseline을 재사용한 별도 실행이며, 아래 표의 기존 결과는 그대로 보존한다.','',
        f"집계 시각: {s['as_of_utc']}. 실행: `{s['run']}`. 실행 중인 코드·config·캐시·출력 파일을 변경하거나 GPU 추론을 추가하지 않았다.",'',
        '**번역·변환 완료와 문제 풀이 완료를 구분한다.** 현재 pipeline은 각 cohort에서 모든 조건의 변환이 끝난 뒤 O와 각 조건의 VLM 문제 풀이를 수행한다. 아래 정확도는 전체 paired 출력이 완성된 조건에서만 표시한다.','',
        '## 진행 상태','', '| Cohort | 조건 | 변환 | 문제 풀이 출력 |','| --- | --- | ---: | ---: |']
    for cohort,g in s['cohorts'].items():
        for c,p in g['transformations'].items():out.append(f"| {cohort} | {c} | {p['transformation_rows']}/{g['pairs']} | {p['inference_rows']}/{g['pairs']} |")
    any_accuracy=any(c['accuracies'] for c in s['cohorts'].values())
    if not any_accuracy:out+=['','**아직 완료된 downstream 정확도는 없다.** 번역 파일의 `status=success`는 JSON·변환 검증 결과이며 REL 정답을 맞혔다는 뜻이 아니다. 과거 O/R/T/F 예측을 대신 붙여 새 정확도를 만들지 않았다.']
    else:
        out+=['','| Cohort | 조건 | 정답 | O 정답 | ΔO | 95% CI | 회복/회귀 |','| --- | --- | ---: | ---: | ---: | --- | ---: |']
        for cohort,g in s['cohorts'].items():
            for name,a in g['accuracies'].items():
                c=a['vs_O'];out.append(f"| {cohort} | {name} | {a['correct']}/{a['n']} | {a['O_correct']}/{a['n']} | {c['difference']*100:+.2f}pp | [{c['ci95'][0]*100:+.2f}, {c['ci95'][1]*100:+.2f}] | {c['recovery']}/{c['regression']} |")
    if any('completed_evaluation' in g for g in s['cohorts'].values()):out+=['',render_completed(s)]
    for cohort,g in s['cohorts'].items():
        if 'inventory' not in g:continue
        out+=['',f'## {cohort}: 완료 단계 비용','', '| 단계 | 출력 수 | Wall·분 |','| --- | ---: | ---: |']
        for name,v in g['stages'].items():
            if v['complete']:out.append(f"| {name} | {v['rows']} | {v['cost']['wall_seconds']/60:.2f} |")
        out+=['',f'## {cohort}: Inventory','', '| 범위 | 고유 이미지 | 성공 | repair 시도 | repair 후 회복 | 최종 실패 | 실패 evidence를 받는 pair |','| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
        for name,v in g['inventory'].items():out.append(f"| {name} | {v['images']} | {v['success']} | {v['repair_attempted']} | {v['repair_recovered']} | {v['failed']} | {v['affected_pairs']} |")
        out+=['','실패 image는 삭제하지 않고 빈 inventory로 포함한다. Full GUI는 이 경우 일반 번역을 수행할 수 있으므로 변환 성공과 GUI evidence 사용 성공이 다르다. OCR 문자열 내용의 정확도는 이번 집계에서 독립 검수하지 않았다.']
        for v in g['inventory_failures']:out.append(f"\n- `{v['parallel_id']}` / GUI {v['gui_language']}: {', '.join(v['errors'])}")
        if 'extraction' in g:
            out+=['',f'## {cohort}: 전체 필드 추출 vs stem-only','', '| 범위 | 고유 source MCQ | 전체 필드 실패 | Stem-only 실패 | 실패→성공 | 성공→실패 |','| --- | ---: | ---: | ---: | ---: | ---: |']
            for name,v in g['extraction'].items():out.append(f"| {name} | {v['source_mcqs']} | {v['scopes']['all_fields'].get('failed',0)} | {v['scopes']['stem_only'].get('failed',0)} | {v['paired'].get('failed->success',0)} | {v['paired'].get('success->failed',0)} |")
            main=g['extraction'].get('main')
            if main:
                out+=['','### Main의 stem source-span 품질','', '| 추출 방식 | Precision | Recall | F1 | 유효하지만 stem ref 없음 |','| --- | ---: | ---: | ---: | ---: |']
                for name,v in main['scopes'].items():
                    a=v['stem_spans'];formatted=['—' if a[k] is None else f"{a[k]*100:.2f}%" for k in ['precision','recall','f1']]
                    out.append(f"| {name} | {' | '.join(formatted)} | {v.get('valid_but_no_stem_ref',0)} |")
                a=main['scopes']['all_fields'];out+=['',f"기존 main 실패 {a.get('failed',0)}개 중 options field만 검증 실패한 것은 {a.get('option_only_failed',0)}개다. 전체 필드 추출 실패를 모두 options 때문이라고 보지는 않는다. 이는 parser/span 검증 실패의 분류이며 형식이 유효한 options의 의미 오류까지 분해한 결과는 아니다. Stem-only는 실패를 줄이고 recall을 올렸지만 annotation과 일치하지 않는 추가 경계도 늘었다. 이는 source annotation의 exact span 경계 지표이며 GUI 대응 정답률이 아니다. 실패 응답은 실제 pipeline처럼 빈 추출로 취급하므로 모델의 raw 추출 능력뿐 아니라 검증 정책의 영향도 포함한다.",'',
                    'MCQ 단위는 (semantic item, source language)로 dedup했다. Main은 같은 source가 세 GUI로 반복되므로 pair 240개를 독립 source 240개로 세지 않는다. 기존 전체 필드와 stem-only는 prompt/scope가 달라진 pipeline 비교이며 단일 오류 유형의 순수 인과 효과가 아니다.']
        for condition,t in g['transformations'].items():
            if not t['transformation_complete'] or not condition.startswith('TS_FULL_'):continue
            out+=['',f'## {cohort}: {condition} 변환 완료','', '| 범위 | N | 구조상 성공 | 구조 repair | 의미 repair 시도 | 의미 repair 채택 | 잔여 의미 경고 pair | 숫자 등 진단 pair |','| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
            for name,v in t['groups'].items():out.append(f"| {name} | {v['pairs']} | {v['status'].get('success',0)} | {v['structure_repairs']} | {v['semantic_repairs']} | {v['semantic_repairs_accepted']} | {v['remaining_semantic_pairs']} | {v['diagnostic_pairs']} |")
            if 'main' in t['groups']:
                m=t['groups']['main'];out+=['','| Main GUI | N | 의미 repair | 잔여 의미 경고 |','| --- | ---: | ---: | ---: |']
                for gui,v in sorted(m['by_gui'].items()):out.append(f"| {gui} | {v['pairs']} | {v['semantic_repairs']} | {v['remaining_semantic_pairs']} |")
            out+=['','구조상 성공은 의미 보존을 보장하지 않는다. 의미 repair 채택은 자동 점수가 낮아졌다는 뜻이며 경고가 모두 사라졌다는 뜻은 아니다. 잔여 경고는 자동 휴리스틱이며, DND 같은 acronym 유지가 정당한 경우도 포함할 수 있다. 숫자 token 차이 역시 실제 GUI label 변화인지 번역 오류인지 별도 확인해야 한다.','', '### 검토할 원문/번역 사례']
            for e in t['flagged_examples']:
                out+=['',f"- `{e['pair_id']}`: {', '.join(e['semantic_reasons']+e['diagnostics'])}",'', '```text','Source: '+e['source_stem'],'Target: '+e['target_stem'],'```']
                for field in sorted({d.split(':')[1] for d in e['diagnostics'] if d.startswith(('number_tokens_changed:','file_format_tokens_changed:'))} & set('ABCD')):
                    out+=['', '```text',field+' source: '+e['source_options'][field],field+' target: '+e['target_options'][field],'```']
            v=t['groups']['all'];out+=['',f"완료된 {condition}의 신규 call runtime 합계는 {v['new_call_runtime_seconds']/60:.2f}분, model-load 합계 {v['model_load_seconds']/60:.2f}분이다. Call runtime은 generation/preprocessing 구간이며 전체 조건 wall time은 아니다. Peak reserved는 {v['peak_reserved_gib']:.2f}GiB였다."]
    out+=['','Full GUI와 Full TXT는 각각 과거 lexical/contextual prompt를 사용하므로 inventory 제공뿐 아니라 prompt 규칙도 다르다. 자동 경고 수 차이를 inventory만의 순수 인과 효과로 해석하지 않는다.','',
        '## 다음 집계에서 확인할 것','',
        '- 나머지 변환이 끝나면 O와 각 조건의 VLM generation accuracy 및 paired 회복/회귀를 확인한다.',
        '- Hybrid의 옵션이 Full과 동일한지, stem 선택적 정렬의 이득이 있는지 본다.',
        '- Stem-only의 낮은 parser 실패율이 실제 의미 오류 감소로 이어지는지 검토한다. 이전 NO-GO를 구조 통과율만으로 해제하지 않는다.','',
        '진행 중 파일은 완성된 newline 행만 읽었다. 변환은 전체 pair ID가 갖춰진 조건만 요약했고, 정확도는 O/조건 모두 전체 출력이 갖춰져야 계산한다. 숫자는 snapshot 시점 기준이며 계속 증가할 수 있다.','',
        '재집계 명령(추론 없음):','','```bash','.venv/bin/python followup_rel_4lang/method_dev/scripts/update_two_stage_results.py','```','',
        '[집계 snapshot](../artifacts/two_stage_results_snapshot.json) · [Hybrid 설정](HYBRID_CONTROL_KO.md) · [기본 prompt/config](TWO_STAGE_V2_PROTOCOL_KO.md).']
    return '\n'.join(out)+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-dir',type=Path,default=ROOT/'artifacts/two_stage_v2_hybrid');a=p.parse_args()
    snapshot=collect(a.run_dir.resolve());report=ROOT/'reports/TWO_STAGE_RESULTS_KO.md'
    report.write_text(markdown(snapshot));(ROOT/'artifacts/two_stage_results_snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'report':str(report),'as_of_utc':snapshot['as_of_utc'],'accuracy_conditions':{c:list(g['accuracies']) for c,g in snapshot['cohorts'].items()}},ensure_ascii=False))


if __name__=='__main__':main()
