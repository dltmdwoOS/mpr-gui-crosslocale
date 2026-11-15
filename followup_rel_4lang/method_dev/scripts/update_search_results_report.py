"""Read-only snapshots of completed GPU jobs; preserve the report's manual notes on update."""
import argparse,hashlib,json,statistics,sys
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent;ROOT=HERE.parent
sys.path[:0]=[str(REPO/'01_code/src'),str(HERE)]
from mpr_crosslocale.methods.selective_alignment.schemas import digest,render,fields
from search_pipeline import paired_bootstrap,EXCLUDED

START='<!-- AUTO_RESULTS_START -->';END='<!-- AUTO_RESULTS_END -->'
ORDER=['GUI_EXACT','GUI_MATCH_LM','GUI_TARGETED_VLM','GUI_DIRECT_VLM','TXT_SEL','TXT_DIRECT_LM','TXT_DIRECT_VLM','TXT_FULL','GUI_FULL']
NAMES={'GUI_EXACT':'참조 번역 후 화면 문자열과 exact match','GUI_MATCH_LM':'LM이 inventory에서 대응 표현 선택','GUI_TARGETED_VLM':'추출한 참조를 화면에서 개별 확인','GUI_DIRECT_VLM':'이미지와 MCQ에서 edit 직접 제안','TXT_SEL':'같은 자동 참조만 text-only 번역','TXT_DIRECT_LM':'고정 LM의 직접 edit','TXT_DIRECT_VLM':'이미지 없는 VLM의 직접 edit','TXT_FULL':'MCQ 전체 text-only 번역','GUI_FULL':'Inventory를 제공한 MCQ 전체 번역'}


def read(path):return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
def completed(directory,cutoff):
    marker=directory/'COMPLETE'
    return marker.is_file() and marker.stat().st_mtime<=cutoff

def update_region(existing,generated):
    if not existing:return '# Qwen3 선택적 정렬 개발 실험 결과\n\n'+START+'\n'+generated+'\n'+END+'\n\n## 검토 메모 — 자동 갱신 시 보존\n\n이 영역에는 추가 해석·질문·후속 분석 메모를 이어 적을 수 있다.\n'
    if existing.count(START)!=1 or existing.count(END)!=1 or existing.index(START)>=existing.index(END):raise ValueError('Report markers invalid; refusing to overwrite manual content')
    before,rest=existing.split(START,1);_,after=rest.split(END,1)
    return before+START+'\n'+generated+'\n'+END+after

def error_kind(message):
    rules=[('Span cannot be recovered','원문 text/occurrence 복원 실패'),('Overlapping','span 중첩'),('Missing extraction','상위 추출 실패'),
        ('Missing or unexpected span IDs','span ID 누락/추가'),('Replacement absent','inventory 밖 문자열'),('Invalid edit','edit 필드/schema'),
        ('duplicate options','보기 중복'),('Duplicate options','보기 중복'),('Full output must','전체 번역 필드/schema')]
    for prefix,label in rules:
        if prefix in message:return label
    if any(t in message for t in ['Expecting','Unterminated','Invalid \\u','Extra data']):return 'JSON 파싱'
    return message[:80] or '기타'

def qstats(values):
    if not values:return {'median':None,'p95':None}
    v=sorted(values);pos=(len(v)-1)*.95;lo=int(pos);hi=min(lo+1,len(v)-1)
    return {'median':statistics.median(v),'p95':v[lo]+(v[hi]-v[lo])*(pos-lo)}

def analyze_predictions(rows,originals,labels,condition):
    expected=set(originals);lookup={}
    for r in rows:
        if r.get('execution_mode')!='gpu':raise ValueError('Mock predictions cannot enter empirical report')
        key=r['pair_id'],r['condition']
        if key in lookup:raise ValueError('Duplicate predictions')
        lookup[key]=r
    if set(lookup)!={(pid,c) for pid in expected for c in ['O',condition]}:raise ValueError('Incomplete paired predictions')
    correctness={c:{pid:int(lookup[pid,c].get('status')=='success' and lookup[pid,c].get('parsed_generated_label')==labels[pid]['gold_answer']) for pid in expected} for c in ['O',condition]}
    groups={};subsets={'main':[p for p in expected if labels[p]['split']=='main' and p!=EXCLUDED],
        'legacy':[p for p in expected if labels[p]['split']=='pilot'],'all':sorted(expected)}
    for name,ids in subsets.items():
        if not ids:continue
        ok=correctness[condition];base=correctness['O']
        groups[name]={'n':len(ids),'items':len({labels[p]['parallel_id'] for p in ids}),'correct':sum(ok[p] for p in ids),'O_correct':sum(base[p] for p in ids),
                     'recovery':sum(ok[p]>base[p] for p in ids),'regression':sum(ok[p]<base[p] for p in ids)}
    primary=subsets['main'] or subsets['legacy'];gui={};directions={}
    for key_fn,bucket in [(lambda p:p.rsplit('::',1)[1],gui),(lambda p:'→'.join(p.rsplit('::',2)[1:]),directions)]:
        for key in sorted({key_fn(p) for p in primary}):
            ids=[p for p in primary if key_fn(p)==key];bucket[key]={'n':len(ids),'correct':sum(correctness[condition][p] for p in ids),'O_correct':sum(correctness['O'][p] for p in ids)}
    return {'groups':groups,'by_gui':gui,'by_direction':directions},correctness,lookup


def collect(run,cutoff):
    sources={}
    def use(path):
        sources[str(path.relative_to(REPO))]=hashlib.sha256(path.read_bytes()).hexdigest();return path
    meta=json.loads(use(run/'pipeline_contract.json').read_text());plan=json.loads(use(run/'plan/manifest.json').read_text())
    if meta['mode']!='gpu':raise ValueError('Refuse empirical report of mock pipeline')
    labels={r['pair_id']:r for r in read(use(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))}
    originals={stage:{r['pair_id']:r for r in read(use(run/'plan'/(stage+'.jsonl')))} for stage in plan['cohorts']}
    oracle={r['pair_id']:r['referents'] for r in read(use(ROOT/'artifacts/dataset_audit/oracle_spans_DIAGNOSTIC_ONLY.jsonl'))}
    snapshot={'as_of_utc':datetime.fromtimestamp(cutoff,timezone.utc).isoformat(timespec='seconds'),'cutoff_unix_seconds':cutoff,'run_dir':str(run.relative_to(REPO)),
        'pipeline_complete':(run/'COMPLETE.json').is_file() and (run/'COMPLETE.json').stat().st_mtime<=cutoff,
        'policy':meta['policy'],'models':meta['models'],'cohorts':plan['cohorts'],'records':{},'extractors':{},'sources_sha256':sources,
        'decision':json.loads(use(run/'frozen_policy.json').read_text()) if (run/'frozen_policy.json').exists() else None}
    outcomes={};anchors={};all_jobs=[]
    for path in sorted(run.glob('jobs/**/contract.json')):
        directory=path.parent
        if not completed(directory,cutoff):continue
        all_jobs.append(directory)
        contract=json.loads(use(path).read_text())
        if contract.get('execution_mode')!='gpu':raise ValueError('Mixed execution modes')
    # Group extractor tables only after their underlying job is complete.
    for stage in ['probe','screen']:
        table=run/'tables'/(stage+'_extractors.json')
        if not table.exists():continue
        results=[]
        for r in json.loads(use(table).read_text()):
            directories=[d for d in all_jobs if d.parent.name==r['id']+'_extraction' and d.parent.parent.name==stage]
            if not directories:continue
            d=sorted(directories)[-1];rows=read(use(d/'extractions.jsonl'));calls=json.loads(use(d/'calls.json').read_text())
            failures=Counter(error_kind(x.get('error') or '') for x in rows if x['status']!='success')
            r={**r,'valid_empty':sum(x['status']=='success' and not x['referents'] for x in rows),'error_types':dict(failures),
               'runtime_ms_distribution':qstats([c['runtime_ms'] for c in calls]),'peak_gib':max([c.get('peak_allocated_bytes') or 0 for c in calls],default=0)/2**30,
               'cpu_latency_unmeasured':r['id']=='cpu_quoted'}
            results.append(r)
        snapshot['extractors'][stage]=results
    for stage in ['probe','screen','selection','internal_evaluation']:
        bucket={};outcomes[stage]={};anchors[stage]=[]
        for condition in ORDER:
            table=run/'tables'/stage/(condition+'.json')
            if not table.exists():continue
            saved=json.loads(table.read_text());trial=run/saved['trial'];pred=run/saved['predictions']
            if not completed(trial,cutoff) or not completed(pred,cutoff):continue
            use(table);rewrites=read(use(trial/'rewritten.jsonl'));predictions=read(use(pred/'predictions.jsonl'));calls=json.loads(use(trial/'calls.json').read_text())
            if len(rewrites)!=len(originals[stage]) or {r['pair_id'] for r in rewrites}!=set(originals[stage]):raise ValueError('Missing rewrites')
            measured,correctness,lookup=analyze_predictions(predictions,originals[stage],labels,condition)
            main_ids={p for p in originals[stage] if labels[p]['split']=='main' and p!=EXCLUDED};primary=main_ids or set(originals[stage])
            actual_changed={r['pair_id']:r['modified_question']!=render(fields(originals[stage][r['pair_id']])) for r in rewrites}
            selected_rows=[r for r in rewrites if r['pair_id'] in primary];errors=Counter(error_kind(r['details'].get('error','')) for r in selected_rows if r['generation_status']=='fallback_original')
            edits=[e for r in selected_rows for e in r['edits']]
            inv={r['image_sha256']:r['inventory'] for r in rewrites if r.get('inventory') is not None};failed_raw={i['raw_output'] for i in inv.values() if i['status']=='failed'}
            inv_calls=[c for c in calls if c['stage']=='inventory'];unique_calls={c['cache_key']:c for c in calls}
            batch_times={r['batch_id']:r['batch_runtime_ms'] for r in predictions}
            record={**measured,'trial':saved['trial'],'predictions':saved['predictions'],'quality':saved['quality'],'cost':saved['cost'],
                'main_changed':sum(actual_changed[p] for p in primary),'main_fallback':sum(r['generation_status']=='fallback_original' for r in selected_rows),
                'main_edits':len(edits),'main_exact_edit_spans':sum(any(e['field']==g['field'] and e['start']==g['start'] and e['end']==g['end'] for g in oracle[r['pair_id']]) for r in selected_rows for e in r['edits']),
                'main_error_types':dict(errors),'inventory_images':len(inv),'inventory_failed_images':sum(i['status']=='failed' for i in inv.values()),
                'inventory_failed_at_token_cap':sum(c['raw_output'] in failed_raw and c['output_tokens']==meta['spec']['max_new_tokens'] for c in inv_calls),
                'runtime_ms_distribution':qstats([c['runtime_ms'] for c in unique_calls.values()]),'downstream_compute_seconds':sum(batch_times.values())/1000,
                'method_wall_seconds':saved['cost']['wall_ms']/1000,'pred_wall_seconds':(pred/'COMPLETE').stat().st_mtime-(pred/'contract.json').stat().st_mtime,
                'method_peak_gib':max([c.get('peak_allocated_bytes') or 0 for c in calls],default=0)/2**30,
                'downstream_peak_gib':max([r.get('peak_allocated_bytes') or 0 for r in predictions],default=0)/2**30,
                'transitions_without_own_edit':sum(not actual_changed[p] and correctness[condition][p]!=correctness['O'][p] for p in primary)}
            if abs((saved['groups'].get('main_primary') or saved['groups']['legacy_pilot'])['accuracy']-record['groups'].get('main',record['groups'].get('legacy'))['correct']/len(primary))>1e-12:raise ValueError('Table disagrees with raw predictions')
            bucket[condition]=record;outcomes[stage][condition]={p:correctness[condition][p] for p in primary}
            outcomes[stage].setdefault('O',{p:correctness['O'][p] for p in primary})
            anchors[stage].append({p:lookup[p,'O']['parsed_generated_label'] for p in primary})
        snapshot['records'][stage]=bucket
    use(Path(__file__))
    if snapshot['pipeline_complete'] and (run/'analysis.json').exists():
        analysis=json.loads(use(run/'analysis.json').read_text())
        if analysis['execution_mode']!='gpu':raise ValueError('Final analysis is mock')
        snapshot['final_primary_contrasts']=analysis['contrasts']
    snapshot['O_anchor_agreement']={s:all(x==maps[0] for x in maps) for s,maps in anchors.items() if maps}
    snapshot['contrasts']={}
    winner=(snapshot['decision'] or {}).get('winner','GUI_EXACT')
    for stage in ['screen','selection','internal_evaluation']:
        cs=[]
        for left,right in [(winner,'O'),(winner,'TXT_SEL'),(winner,'GUI_FULL'),('GUI_FULL','TXT_FULL'),('GUI_DIRECT_VLM','TXT_DIRECT_VLM')]:
            if left in outcomes[stage] and right in outcomes[stage]:
                cs.append({'left':left,'right':right,**paired_bootstrap(outcomes[stage][left],outcomes[stage][right],labels,meta['policy']['seed'],meta['policy']['bootstrap_replicates'])})
        snapshot['contrasts'][stage]=cs
    # Historical reference results are post-hoc diagnostics, never candidate input.
    history=REPO/'followup_rel_4lang/artifacts/new_models_expA_20261115/analysis/expA_8b_20261114/qwen3/expA_qwen3/full/predictions.jsonl'
    historical={}
    if history.exists():
        use(history)
        with history.open() as f:
            for line in f:
                r=json.loads(line)
                if r['condition'] in ['O','T','R'] and r['pair_id'] in labels:
                    if r['gold_answer']!=labels[r['pair_id']]['gold_answer']:raise ValueError('Historical label mismatch')
                    historical[r['pair_id'],r['condition']]=r
        snapshot['historical_reference']={}
        for stage,values in outcomes.items():
            if not values or stage=='probe':continue
            ids=set(values['O']);summary={}
            for condition in ['O','T','R']:
                if all((p,condition) in historical for p in ids):summary[condition]={'n':len(ids),'correct':sum(historical[p,condition].get('status')=='success' and historical[p,condition].get('parsed_generated_label')==labels[p]['gold_answer'] for p in ids)}
            summary['O_agreement']={'n':len(ids),'same':sum(historical[p,'O']['parsed_generated_label']==anchors[stage][0][p] for p in ids)}
            snapshot['historical_reference'][stage]=summary
    # Examples of protocol failures, not claimed GUI matching errors.
    snapshot['examples']=[]
    for condition in ['GUI_DIRECT_VLM','GUI_TARGETED_VLM','GUI_MATCH_LM']:
        rec=snapshot['records']['screen'].get(condition)
        if not rec:continue
        rows=read(run/rec['trial']/'rewritten.jsonl')
        row=next((r for r in rows if r['generation_status']=='fallback_original' and r['details'].get('raw_output')),None)
        if row:snapshot['examples'].append({'condition':condition,'pair_id':row['pair_id'],'source_A':originals['screen'][row['pair_id']]['options']['A'],'error':row['details']['error'],'raw_output':row['details']['raw_output'][:1600]})
    snapshot['completed_jobs']=len(all_jobs);snapshot['method_acquired_runtime_seconds']=0;snapshot['method_load_seconds']=0
    for job in all_jobs:
        cost=job/'cost.json'
        if cost.exists():
            c=json.loads(use(cost).read_text());snapshot['method_acquired_runtime_seconds']+=c['acquired_runtime_ms']/1000;snapshot['method_load_seconds']+=c['acquired_model_load_ms']/1000
    return snapshot


def pct(k,n):return f'{100*k/n:.2f}%'
def pp(x):return f'{100*x:+.2f}pp'
def markdown(snapshot):
    out=[]
    def add(text=''):out.append(text)
    records=snapshot['records'];decision=snapshot['decision'] or {};winner=decision.get('winner','GUI_EXACT')
    add(f"집계 기준 (UTC): **{snapshot['as_of_utc']}**. 상태: **{'전체 pipeline 완료' if snapshot['pipeline_complete'] else '진행 중 — 완료 조건만 집계'}**.")
    add('\n이 문서는 실제 GPU 결과만 집계한다. 변환·문제 풀이에 모두 `COMPLETE`가 있는 조건만 정확도 표에 넣고, 진행 중인 출력은 분모에서 제외한다. 원시 결과는 수정하지 않았다. 수동 메모는 자동 생성 영역 밖에 보존한다.')
    add('\n## 1. 현재 핵심 결과')
    screen=records['screen'];selection=records['selection'];internal=records['internal_evaluation']
    if winner in internal:
        g=internal[winner]['groups']['main'];add(f"\n- 내부 평가에서 `{winner}`: **{g['correct']}/{g['n']} ({pct(g['correct'],g['n'])})**, O: **{g['O_correct']}/{g['n']} ({pct(g['O_correct'],g['n'])})**. 차이는 **{pp((g['correct']-g['O_correct'])/g['n'])}**, 회복{g['recovery']} / 회귀{g['regression']}다. 이 완료된 한 조건의 점추정은 개선을 보이지 않는다." if g['correct']<g['O_correct'] else f"\n- 완료된 내부 평가 `{winner}`: {pct(g['correct'],g['n'])}, O 대비 {pp((g['correct']-g['O_correct'])/g['n'])}.")
    if 'GUI_FULL' in screen and winner in screen:
        g=screen['GUI_FULL']['groups']['main'];w=screen[winner]['groups']['main'];add(f"- Screen main240쌍: GUI_FULL **{pct(g['correct'],g['n'])}**, {winner} **{pct(w['correct'],w['n'])}**, O **{pct(g['O_correct'],g['n'])}**. 현재 selective 구현이 full localization보다 낫다는 결과는 아니다.")
    if selection:
        best=max(selection,key=lambda k:selection[k]['groups']['main']['correct']);g=selection[best]['groups']['main'];add(f"- Selection의 최고 관측 대조는 `{best}` **{g['correct']}/{g['n']} ({pct(g['correct'],g['n'])})**. 자동 선택 `{winner}`는 GUI 후보4개 안에서 고른 잠정 후보이며 전체9조건의 최고를 뜻하지 않는다.")
    add('- 추출·matching·edit 프로토콜의 실패가 많이 남아 있다. 특히 원문 span 대신 번역문을 반환하거나 span ID를 잘못 반환하면 안전한 원문 fallback으로 처리됐다. 이를 화면 정보 자체가 효과 없다는 증거로 일반화하지 않는다.')
    add('- 독립 화면 검수가 없어 **GUI matching precision은 미측정**이다. Annotation span 경계 일치율을 replacement 정답률로 부르지 않는다.')
    add('\n## 2. 범위와 조건\n\nQwen3-VL-8B-Instruct가 inventory·시각적 edit·문제 풀이를 수행하고, 고정 Qwen3-8B가 추출·번역·text matching을 맡는다. VL 추출 대조는 전체 VLM을 이미지 없이 호출하며 raw backbone 분리가 아니다. 원본 MCQ·A–D 순서·target screenshot·gold를 고정했다. 정답과 parallel annotation은 사후 평가에서만 사용한다.')
    add('\n| 단계 | Semantic item | 원문 MCQ | pair | 주 accuracy 분모 |\n| --- | ---: | ---: | ---: | --- |')
    for stage in ['probe','screen','selection','internal_evaluation']:
        c=snapshot['cohorts'][stage];n={'probe':'32 legacy','screen':'240 main + 48 legacy 별도','selection':'239 main (전체240은 민감도)','internal_evaluation':'1,416 main'}[stage]
        add(f"| {stage} | {c['semantic_items']} | {len({(r['parallel_id'],r['source_language']) for r in read(REPO/snapshot['run_dir']/'plan'/(stage+'.jsonl'))})} | {c['pairs']} | {n} |")
    add('\nScreen32개는 pilot12 + calibration20이다. Selection은 나머지 calibration20, 내부 평가는 기존118이다. 사전 제외 `rel::5/forest_9.jpg::zh::ru`는 selection에서만 빠진다. 전체158개는 역사적으로 관찰된 development cohort다. Pilot과 main, 반복 튜닝한 screen과 selection, 내부 평가를 합쳐 하나의 일반화 accuracy로 보고하지 않는다.')
    add('\n| ID | 방법 |\n| --- | --- |')
    for key in ORDER:add(f'| {key} | {NAMES[key]} |')
    add('\n설정: BF16·SDPA·2MP, patch Conv3D channels_last_3d, method batch1/최대768token, 문제 풀이 batch3/최대2token. 전체 입력4096token 상한이며 초과 시 무음 truncation하지 않는다. 원문에서 복원할 수 없는 edit나 새 중복 보기는 거절하고 원문을 유지한다. 실제 prompt는 [원문 해설](PROMPTS_AND_GO_NO_GO_KO.md)과 [현재 후보 코드](../../../01_code/src/mpr_crosslocale/methods/selective_alignment/search.py), 선택 규칙은 [pipeline/OOM 문서](PIPELINE_OOM_AUDIT_KO.md)를 참고한다.')
    add('\n## 3. 참조 추출 결과\n\nP는 추출한 표현 중 맞은 비율, R은 찾아야 할 표현 중 찾은 비율, F1은 둘을 함께 반영한 값이다. 여기서는 원문 character span의 exact match로 판정한다. 응답 전체가 span 검증에서 실패하면 빈 결과로 포함한다. `검증 실패`에는 JSON syntax뿐 아니라 원문 substring·occurrence·중첩 오류도 들어간다. 정상 빈 목록과 구분한다.')
    for stage,rows in snapshot['extractors'].items():
        add(f'\n### {stage}: {rows[0]["metrics"]["mcqs"]}개 원문 MCQ\n\n| 조건 | P | R | F1 | 정상 빈 목록 | 검증 실패 | 완전한 span set | 초/MCQ¹ |\n| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |')
        for r in rows:
            m=r['metrics'];lat='— (미계측 CPU)' if r['cpu_latency_unmeasured'] else f"{r['ms_per_mcq']/1000:.2f}"
            add(f"| {r['id']} | {pct(m['tp'],m['predicted']) if m['predicted'] else 'N/A'} | {pct(m['tp'],m['gold'])} | {100*(m['f1'] or 0):.2f}% | {r['valid_empty']} | {m['schema_failed']} | {m['complete_span_set']}/{m['mcqs']} | {lat} |")
    add('\n¹ Load 제외 고유 backend runtime의 평균이며 cache hit도 원래 측정값으로 산입한다. CPU 기준의0 기록은 GPU 호출이 없다는 뜻이지 실제 CPU 시간이0초라는 뜻은 아니다.')
    add('\nProbe에서 VL original은 정상 빈 목록이30/32개였다. 예시를 추가한 VL contrastive는 빈 응답을 줄였지만 낮은 precision이 남았다. 고정 LM도 prompt 보정으로 좋아졌으나, screen fixed_contrastive의 recall39.40%·F1 53.12%라 충분히 해결됐다고 보기 어렵다. CPU quoted의 probe F1이55.42%로 가장 높았지만, 이 조건은 인용부호 한정 진단 기준이라 자동 LM 승격 대상에서 제외됐다.')
    add('\nScreen fixed_contrastive는 minimal보다 precision이 높고 recall은 약간 낮았다. F1 차이는0.45%p로 작으며, 자동 정책은 F1 최고에서0.02 이내면 비용을 비교한다. 이 단계에서는 contrastive가 더 빨라 고정됐다. 이를 모든 언어·문항에서 우월한 prompt라는 결론으로 확대하지 않는다.')
    add('\nExact span 평가에서는 의미상 타당해 보이는 넓은 표현도 경계가 다르면 틀린 것으로 센다. 이름 없는 아이콘 유지 정책과 annotation 범위의 차이도 별도 검토해야 한다. 반면 원문 text/occurrence 복원 실패와 span 중첩은 로그로 확인한 실제 프로토콜 오류다. CPU 인용부호 기준은 downstream method로 실행하지 않았으므로, 높은 추출 F1만으로 최종 정답률까지 우수하다고 결론 내릴 수 없다.')
    add('\n## 4. 완료된 문제 풀이 결과\n\n각 행의 O는 같은 조건과 짝지어 재실행한 baseline이다. 모든 조건은 실패/fallback을 포함한다. 회복=O 오답→정답, 회귀=O 정답→오답이다.')
    for stage in ['probe','screen','selection','internal_evaluation']:
        rows=records[stage];add(f'\n### {stage}')
        if not rows:add('\n완료된 문제 풀이 조건 없음.');continue
        group='legacy' if stage=='probe' else 'main';base=next(iter(rows.values()))['groups'][group]
        add(f"\nO: **{base['O_correct']}/{base['n']} ({pct(base['O_correct'],base['n'])})**. O anchor 조건 간 일치: {'전부 일치' if snapshot['O_anchor_agreement'][stage] else '불일치 있음 — 원시 예측 확인 필요'}.")
        add('\n| 조건 | 정답/분모 | 정확도 | O 대비 | 회복 | 회귀 | method 초/쌍² |\n| --- | ---: | ---: | ---: | ---: | ---: | ---: |')
        for method in ORDER:
            if method not in rows:continue
            r=rows[method];g=r['groups'][group];n=snapshot['cohorts'][stage]['pairs'];seconds=r['cost']['standalone_unique_runtime_ms']/1000/n
            add(f"| {method} | {g['correct']}/{g['n']} | {pct(g['correct'],g['n'])} | {pp((g['correct']-g['O_correct'])/g['n'])} | {g['recovery']} | {g['regression']} | {seconds:.2f} |")
        if stage=='screen':
            add('\nLegacy pilot48쌍은 위 main 표와 분리한다.')
            add('\n| 조건 | Legacy 정답/48 | 전체288 정답 |\n| --- | ---: | ---: |')
            for method,r in rows.items():add(f"| {method} | {r['groups']['legacy']['correct']}/48 | {r['groups']['all']['correct']}/288 |")
        if stage=='selection':
            add('\n제외1쌍을 포함한240쌍에서는 GUI_EXACT·GUI_DIRECT_VLM·GUI_FULL이 각각174/240=72.50%, TXT_DIRECT_VLM은179/240=74.58%였다. Primary239쌍과 혼동하지 않는다.')
        if stage=='internal_evaluation':
            pending=[m for m in decision.get('evaluation_recipes',[]) if m not in rows];add('\n미완료로 제외한 조건: '+(', '.join(pending) or '없음')+'. 부분 출력으로 정확도를 추정하지 않았다.')
    add('\n² 각 stage 전체 pair에서 공유 가능한 inventory/extraction을 한 번씩 계산한 runtime/쌍이다. Screen 비용은288쌍 기준이지만 정확도 주요 표는 main240쌍이다. CPU 전처리+GPU 실행을 포함하고 모델 load·downstream은 제외한다. 단일 query cold latency도, 이번 실행에서 새로 쓴 시간도 아니다. Stage 간 sample·공유량·cached historical timing이 달라 직접적인 속도 순위로 해석하지 않는다.')
    add('\n## 5. 선택 기록과 해석\n\nProbe→screen 추출 shortlist는 fixed_contrastive/minimal, 고정 추출기는 fixed_contrastive다. Screen의 GUI 후보4개 중 GUI_EXACT와 GUI_DIRECT_VLM을 selection 전에 고정했다. Selection에서는 둘 다173/239였고 method 시간은 각각4.99초/쌍과5.27초/쌍이라 GUI_EXACT가 선택됐다.')
    add('\n중요한 한계는 선택 범위다. TXT_DIRECT_VLM은178/239로 더 높았지만 GUI 후보가 아닌 대조군이라 자동 winner 후보에 포함되지 않았다. GUI_FULL도 전체 번역 대조군이었다. 따라서 `winner=GUI_EXACT`는 전체 방법의 최고 정확도나 GCSA의 성공 판정이 아니다. Screen에서 네 GUI selective 후보 모두 O보다 낮았다는 사실도 보존한다.')
    add('\nSelection에서는 GUI_EXACT의 회복4/회귀2와 GUI_FULL의 회복27/회귀25가 같은 순증가2를 만들었다. 평균 정확도가 같아도 바뀐 문항과 회귀 위험은 다르다. 내부 평가 조건들이 모두 끝나면 같은 관점으로 비교를 추가한다.')
    add('\n## 6. Paired 차이와 불확실성\n\nSemantic item을10,000회 bootstrap한95% CI다. 탐색·선택에 사용한 screen/selection은 확증 검정이 아니다. 내부 평가도 역사적으로 관찰된 development cohort이며, 일부 조건만 완료된 동안 p값이나 최종 승리 판정을 제시하지 않는다.')
    add('\n| 집합 | 대비 | 차이 | 95% CI | Item / pair |\n| --- | --- | ---: | --- | ---: |')
    for stage,cs in snapshot['contrasts'].items():
        for c in cs:add(f"| {stage} | {c['left']} − {c['right']} | {pp(c['difference'])} | [{pp(c['ci95'][0])}, {pp(c['ci95'][1])}] | {c['items']} / {c['pairs']} |")
    if snapshot.get('final_primary_contrasts'):
        add('\n최종 pipeline 집계가 완료되어 다음 내부 평가 primary Holm 보정값을 추가했다. 선택 후 고정 대비의 탐색적 bootstrap p이며 confirmatory claim이 아니다.\n\n| 대비 | Bootstrap p | Holm p |\n| --- | ---: | ---: |')
        for name,c in snapshot['final_primary_contrasts'].items():
            if 'holm_primary_p' in c:add(f"| {name} | {c['exploratory_bootstrap_centered_p']:.4f} | {c['holm_primary_p']:.4f} |")
    add('\n## 7. GUI 언어별 결과')
    for stage in ['screen','selection','internal_evaluation']:
        rows=records[stage]
        if not rows:continue
        methods=[m for m in ['GUI_EXACT','GUI_FULL','TXT_SEL','TXT_DIRECT_VLM'] if m in rows];add(f'\n### {stage}\n\n| GUI | 분모 | O | '+' | '.join(methods)+' |\n| --- | ---: | ---: | '+' | '.join(['---:']*len(methods))+' |')
        for gui in ['en','zh','th','ru']:
            base=next(iter(rows.values()))['by_gui'][gui]
            add(f"| {gui.upper()} | {base['n']} | {pct(base['O_correct'],base['n'])} | "+' | '.join(pct(rows[m]['by_gui'][gui]['correct'],base['n']) for m in methods)+' |')
    add('\nTH GUI는 여러 조건에서 낮지만 단일한 target-language 난이도 효과로 단정하지 않는다. 화면 OCR, 참조 추출, target 표현 선택, 모델의 GUI 이해가 함께 작용한다. Screen에서 GUI_FULL의 TH 개선이 보였지만 다른 집합에서 크기가 달라지고, 개별 언어 표본·CI를 고려해야 한다.')
    add('\n## 8. 실제 변환 범위와 실패 원인\n\nFull 조건의 `edits=[]`는 변환이 없다는 뜻이 아니다. 아래 변경 수는 실제 최종 MCQ를 원본과 비교해 다시 계산했다. Fallback 수와 정상적인 no-op도 구별한다.')
    for stage in ['screen','selection','internal_evaluation']:
        rows=records[stage]
        if not rows:continue
        add(f'\n### {stage}\n\n| 조건 | 실제 MCQ 변경/주 분모 | 오류 fallback | 적용 edit 수 | Annotation과 경계 일치³ |\n| --- | ---: | ---: | ---: | ---: |')
        for method,r in rows.items():
            n=r['groups']['main']['n'];boundary=f"{r['main_exact_edit_spans']}/{r['main_edits']}" if r['main_edits'] else '—'
            add(f"| {method} | {r['main_changed']}/{n} | {r['main_fallback']} | {r['main_edits'] if method not in ['TXT_FULL','GUI_FULL'] else '전체 번역'} | {boundary} |")
    add('\n³ 오직 **source span 경계**가 annotation과 같은지 검사한다. Target replacement의 화면 대응 정답률이 아니다. 같은 문항의 GUI pair 반복을 독립 annotation 사례처럼 취급하지 않는다.')
    if 'GUI_EXACT' in screen:
        r=screen['GUI_EXACT'];add(f"\nScreen inventory: 고유 이미지{r['inventory_images']}개 중{r['inventory_failed_images']}개 실패했고, 실패{r['inventory_failed_at_token_cap']}개 모두 출력768token 상한에 도달했다. JSON이 닫히지 않은 실제 응답이 있으므로 token-budget truncation과 일관된 실패다. 화면에 텍스트가 없다는 뜻이 아니다.")
    add('\nScreen main240쌍에서의 fallback 분류:')
    add('\n| 조건 | 원인별 건수 |\n| --- | --- |')
    for method,r in screen.items():add(f"| {method} | "+(', '.join(f'{k} {v}' for k,v in r['main_error_types'].items()) or '없음')+' |')
    add('\n특히 직접 시각 edit는 source `text`에 target GUI 문자열을 넣는 오류가 많았다. Targeted VLM은 실제 span ID 대신 예시의 리터럴 `span_id`를 키로 반환하기도 했다. Strict validation은 이런 응답을 전체 원문 fallback으로 처리하므로, 한 잘못된 edit/ID가 같은 응답의 다른 유효 제안도 막을 수 있다. 현재 결과에는 이 정책의 비용이 포함된다. 지금 실행 중인 정책을 중간에 바꾸지는 않았다.')
    for example in snapshot['examples'][:2]:
        add(f"\n예: `{example['condition']}`, `{example['pair_id']}`. 원래 A: `{example['source_A']}`. 거절 이유: `{example['error']}`.\n\n```json\n{json.dumps(json.loads(example['raw_output']),ensure_ascii=False,indent=2)}\n```")
    add('\n추가 확인: 자기 MCQ에 edit가 없는데 O와 예측이 달라진 건수도 집계했다. 이 경우 batch 동반 입력·padding에 따른 변화를 해당 문항 자체의 localization 효과로 단정하면 안 된다.')
    add('\n| 집합 | 조건 | 자기 edit 없는 정오 전환 |\n| --- | --- | ---: |')
    for stage,rows in records.items():
        for method,r in rows.items():
            if r['transitions_without_own_edit']:add(f"| {stage} | {method} | {r['transitions_without_own_edit']} |")
    if not any(r['transitions_without_own_edit'] for rs in records.values() for r in rs.values()):add('| 전체 완료 조건 | — | 0 |')
    add('\n## 9. 비용·메모리 실측\n\n완료된 job만 합산한 method 신규 runtime은 **'+f"{snapshot['method_acquired_runtime_seconds']/3600:.2f}시간"+'**, method model-load 합계는 **'+f"{snapshot['method_load_seconds']/60:.2f}분"+'**이다. Downstream·현재 진행 job·상위 스케줄링 대기 시간은 이 합계에 들어가지 않는다. Cache hit 비용을 다시 청구한 합계가 아니다.')
    add('\n| 집합 | 조건 | Method wall 분 | Downstream wall 분 | Method peak GiB | Downstream peak GiB |\n| --- | --- | ---: | ---: | ---: | ---: |')
    for stage,rows in records.items():
        if stage=='probe':continue
        for method,r in rows.items():add(f"| {stage} | {method} | {r['method_wall_seconds']/60:.2f} | {r['pred_wall_seconds']/60:.2f} | {r['method_peak_gib']:.2f} | {r['downstream_peak_gib']:.2f} |")
    add('\nMethod wall은 cache·모델 교체를 포함한 해당 실행 시간이다. Peak는 generation 구간의 allocated memory이며 CUDA reserved/cold-load 전체 peak와 다르다. Cached call의 peak는 원래 측정값일 수 있다. GPU memory 수치만으로 다른 GPU/배치의 OOM 여부를 보장하지 않는다. 이번 관찰 속도를 이전 단건58–66초나RTX4090 결과와 직접 비교해 디바이스 속도 차이라고 해석하지 않는다.')
    add('\n## 10. Historical O/T/R reference — 신규 자동 method와 분리\n\n기존 ExpA의 완료 예측을 같은 pair ID·정답으로 결합했다. T는 Gemma와 gold span을, R은 parallel reference span을 사용한 역사적 조건이다. 현재 자동 Qwen3 extractor/translator와 정보량·백본이 달라 공정한 순수 모델 대조로 부르지 않는다.')
    add('\n| 집합 | 기존 O | T_REF | R_REF | 현재 O와 기존 O label 일치 |\n| --- | ---: | ---: | ---: | ---: |')
    for stage,h in snapshot.get('historical_reference',{}).items():
        add('| '+stage+' | '+' | '.join(f"{h[c]['correct']}/{h[c]['n']} ({pct(h[c]['correct'],h[c]['n'])})" if c in h else '미확보' for c in ['O','T','R'])+' | '+f"{h['O_agreement']['same']}/{h['O_agreement']['n']}"+' |')
    add('\n## 11. 이어서 채울 항목\n\n이 보고서는 아래 명령으로 동일 파일의 자동 생성 영역을 갱신한다. GPU 추론을 실행하지 않으며, 완료된 새 조건만 추가한다. 아래 수동 메모는 유지된다. Pipeline 자체가 만드는 `REPORT_KO.md`와 이 누적 보고서는 서로 다른 파일이다.')
    add('\n```bash\n.venv/bin/python followup_rel_4lang/method_dev/scripts/update_search_results_report.py\n```')
    all_done=set(decision.get('evaluation_recipes',[]))<=set(internal) and bool(decision)
    add('\n- ['+('x' if all_done else ' ')+'] 내부 평가 winner + TXT_SEL/GUI_FULL/TXT_FULL/TXT_DIRECT_VLM 전 조건 완료 비교\n- ['+('x' if snapshot.get('final_primary_contrasts') else ' ')+'] 최종3 primary 대비·CI·Holm 결과와 최종 O anchor 확인\n- [ ] 독립 화면 matching 검수와 Thai GUI 실패의 단계별 분리\n- [ ] Finalist의 대표 회복·회귀 사례와 원문/최종 MCQ 대조\n- [ ] 최종 총 wall·신규 소비 비용·공유 비용·raw artifact 보존 manifest\n- [ ] GCSA 개선이 없는 경우도 포함한 최종 개발 결론과 RFA 진행 여부')
    add('\n## 부록 A. 완료 조건의12방향 결과\n\n각 셀은 정답률이다. 분모는 해당 row의N이며, screen/selection/internal의 main primary만 사용한다. Probe는4개 순환 방향이라 제외했다.')
    for stage in ['screen','selection','internal_evaluation']:
        rows=records[stage]
        if not rows:continue
        methods=[m for m in ORDER if m in rows];add(f'\n### {stage}\n\n| 언어쌍 | N | O | '+' | '.join(methods)+' |\n| --- | ---: | ---: | '+' | '.join(['---:']*len(methods))+' |')
        base=next(iter(rows.values()))['by_direction']
        for direction,d in sorted(base.items()):add(f"| {direction} | {d['n']} | {pct(d['O_correct'],d['n'])} | "+' | '.join(pct(rows[m]['by_direction'][direction]['correct'],d['n']) for m in methods)+' |')
    add('\n## 부록 B. 재현·완료 판정\n\n집계 원본: `'+snapshot['run_dir']+'`. 대응 snapshot은 [search_report_snapshot.json](../artifacts/search_report_snapshot.json)이며 cutoff·입력SHA-256·완료 job 경로·집계값을 보존한다. 데이터/정답/annotation은 현재 audit artifact에서 읽었고, method 실행 입력으로 주입하지 않았다. 새 분석 코드는 실행 중인 pipeline의 코드·설정·raw 결과를 변경하지 않는다. 원시 대용량 산출물은 로컬 artifacts에 유지한다.')
    return '\n'.join(out)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-dir',type=Path,default=ROOT/'artifacts/search_pipeline_v1');p.add_argument('--report',type=Path,default=ROOT/'reports/SEARCH_RESULTS_KO.md');p.add_argument('--snapshot',type=Path,default=ROOT/'artifacts/search_report_snapshot.json');a=p.parse_args()
    cutoff=datetime.now(timezone.utc).timestamp();snapshot=collect(a.run_dir.resolve(),cutoff);text=markdown(snapshot)
    existing=a.report.read_text() if a.report.exists() else '';updated=update_region(existing,text)
    for path,content in [(a.snapshot,json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n'),(a.report,updated)]:
        path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix(path.suffix+'.tmp')
        temporary.write_text(content);temporary.replace(path)
    print(json.dumps({'report':str(a.report),'as_of_utc':snapshot['as_of_utc'],'completed_conditions':{s:list(r) for s,r in snapshot['records'].items()}},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
