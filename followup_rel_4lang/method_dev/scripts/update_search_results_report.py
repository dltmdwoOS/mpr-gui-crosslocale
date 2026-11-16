"""Read-only snapshots of completed GPU jobs; preserve the report's manual notes on update."""
import argparse,hashlib,json,statistics,sys
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent;ROOT=HERE.parent
sys.path[:0]=[str(REPO/'01_code/src'),str(HERE)]
from mpr_crosslocale.methods.selective_alignment.schemas import digest,render,fields
from search_pipeline import paired_bootstrap,EXCLUDED
from reference_comparison import load_references,compare_cohorts,render_comparison

START='<!-- AUTO_RESULTS_START -->';END='<!-- AUTO_RESULTS_END -->'
ORDER=['GUI_EXACT','GUI_MATCH_LM','GUI_TARGETED_VLM','GUI_DIRECT_VLM','TXT_SEL','TXT_DIRECT_LM','TXT_DIRECT_VLM','TXT_FULL','GUI_FULL']
NAMES={'GUI_EXACT':'참조 번역 후 화면 문자열과 exact match','GUI_MATCH_LM':'LM이 inventory에서 대응 표현 선택','GUI_TARGETED_VLM':'추출한 참조를 화면에서 개별 확인','GUI_DIRECT_VLM':'이미지와 MCQ에서 edit 직접 제안','TXT_SEL':'같은 자동 참조만 text-only 번역','TXT_DIRECT_LM':'고정 LM의 직접 edit','TXT_DIRECT_VLM':'이미지 없는 VLM의 직접 edit','TXT_FULL':'MCQ 전체 text-only 번역','GUI_FULL':'Inventory를 제공한 MCQ 전체 번역'}


METHOD_DETAILS={
'GUI_EXACT':(
    '원본 MCQ에서 공통 추출기가 찾아낸 표현만 고정 Qwen3-8B로 GUI 언어로 번역한다. 번역기는 표현과 언어 정보를 받으며, 이 단계에서는 screenshot이나 inventory를 보지 않는다. 별도로 평가 VLM이 screenshot만 보고 전사한 inventory를 준비하고, 코드가 번역문과 화면 문자열을 정규화한 뒤 exact match한다. 맞는 문자열만 원문 span에 넣으며, 나머지 문맥과 보기 순서는 코드가 그대로 둔다.',
    '이는 현재 GCSA의 가장 보수적인 구현이다. TXT_SEL과 같은 추출·번역 결과를 사용하면서 화면에 실제로 전사된 표현만 허용하므로, 화면 lexical evidence의 추가 효과를 비교할 수 있다. 가령 번역이 房间인데 inventory에는 客房만 있으면 의미가 가까워도 치환하지 않는다. 화면 근거 없는 표현을 줄이는 대신 동의어·OCR 누락·낮은 추출 recall 때문에 실제 편집을 못 하는 경우가 많아질 수 있다. 독립적인 semantic retrieval이나 LaBSE는 이 조건에 없다.'),
'GUI_MATCH_LM':(
    '공통 추출기가 찾은 source 표현 전체와 target GUI inventory를 고정 Qwen3-8B에 함께 준다. GUI_EXACT의 독립 번역→exact match 대신, LM 한 호출이 각 span ID에 대응하는 inventory 문자열 또는 null을 고른다. 모델은 screenshot과 원래 공간 관계 문장 전체를 보지 않고, 추출된 표현·field·언어·순서 없는 화면 문자열 목록을 본다.',
    '의미상 같은데 독립 번역의 단어 선택이 달라 exact match가 실패하는 문제를 줄이려는 조건이다. 모델이 선택한 문자열이 inventory에 원문 그대로 들어 있는 문자열인지 코드가 다시 검사하며, 입력으로 준 span ID가 빠지거나 추가되어도 응답 전체를 거절한다. 따라서 잘못된 표현을 억제할 수 있지만 올바른 다른 제안도 한 오류와 함께 버려질 수 있다. GUI_EXACT와 비교할 때 추출기는 같고, 대응 결정을 코드가 하느냐 LM이 하느냐가 주된 차이다.'),
'GUI_TARGETED_VLM':(
    '먼저 공통 text extractor가 source 표현을 찾는다. 그다음 Qwen3-VL에 target screenshot과 모든 추출 표현의 ID·field·원문을 주고, 화면에 명확히 보이는 대응 label 또는 null을 반환하게 한다. 화면 전체 문자열 목록을 먼저 만들지 않으며, 원래 MCQ의 공간 관계 문장 전체도 이 확인 단계에 주지 않는다. Stem과 A–D에서 추출된 표현을 같은 규칙으로 모두 처리한다.',
    '전체 inventory 생성 시간을 줄이고 필요한 label만 화면에서 확인할 수 있는지를 보는 조건이다. GUI_EXACT처럼 독립 inventory membership를 코드로 검증할 수 없으므로, 반환한 표현이 실제 화면 표기인지 별도 검수가 필요하다. Matching 실패가 적다고 자동으로 정확한 grounding이라고 볼 수 없다. 실제 span ID 대신 예시의 span_id라는 키를 반환한 경우도 있어, 현재 정확도에는 시각 인식 외에 출력 인터페이스 실패도 포함된다.'),
'GUI_DIRECT_VLM':(
    'Qwen3-VL 한 호출에 원본 stem·A–D, source/GUI 언어, target screenshot을 주고 교체할 원문 substring과 target label을 함께 제안하게 한다. 별도 referent extractor도 inventory도 사용하지 않는다. 출력은 field·text·occurrence·replacement의 edit 목록이며, 최종 MCQ는 LLM이 자유롭게 다시 쓰지 않고 코드가 source span을 복원해 수정한다.',
    '단계를 통합하면 추출 오류의 전파와 여러 호출 비용을 줄일 수 있는지가 목적이다. TXT_DIRECT_VLM은 같은 VLM·같은 edit 지시에 이미지가 없는 대조다. 다만 GUI_DIRECT_VLM은 전체 이미지와 문제를 함께 보므로, 좋아지더라도 효과를 순수한 lexical alignment에만 귀속할 수 없다. 원문 text 자리에 번역된 label을 넣으면 source span을 복원할 수 없어 전체 원문으로 fallback한다. 따라서 현재 낮은 변경률은 이미지가 무용해서라고 단정할 수 없고, edit 프로토콜을 따르는 능력도 함께 평가한 결과다.'),
'TXT_SEL':(
    'GUI_EXACT와 같은 공통 추출 span과 같은 고정 Qwen3-8B의 표현별 번역 결과를 사용한다. 차이는 inventory와 screenshot을 전혀 사용하지 않고, 번역문을 곧바로 원래 span에 넣는다는 것이다. 번역 대상은 stem의 기준 표현뿐 아니라 A–D 안의 표현도 포함한다. 선택한 span 밖의 원문은 코드로 보존한다.',
    '이는 화면 없이 참조만 번역하는 automatic selective 기준이다. GUI_EXACT와 비교하면 화면 문자열로 제한한 덕분에 생기는 이득과, 제한 때문에 못 바꾼 표현의 손실을 함께 볼 수 있다. 추출기가 문맥을 잘못 span에 포함하면 이 조건도 그 문맥을 번역할 수 있으며, 애초에 추출하지 못한 표현은 그대로 남는다. 역사적 T_REF는 gold span과 Gemma를 썼으므로 TXT_SEL과 같은 실험이 아니다.'),
'TXT_DIRECT_LM':(
    '고정 text-only Qwen3-8B가 MCQ 전체와 source/target 언어를 받아 참조 추출과 번역을 한 edit 제안으로 처리한다. Screenshot·inventory와 별도 extraction 결과는 주지 않는다. GUI_DIRECT_VLM 및 TXT_DIRECT_VLM과 같은 edit task 지시를 사용하고, 반환한 원문 위치는 같은 코드로 검증한다.',
    '여러 단계 없이 text-only 모델 한 번으로 selective translation을 수행할 수 있는지를 보는 실용 기준이다. TXT_SEL과 비교하면 같은 고정 LM을 쓰지만 전체 MCQ를 보며 span과 번역을 동시에 결정한다는 차이가 있다. 모델은 target 화면의 실제 단어를 확인할 수 없어 정확한 GUI label을 보장하지 못한다. TXT_DIRECT_VLM과의 차이는 이미지 유무가 아니라 checkpoint·학습 이력·chat template를 포함하므로 단순한 vision 효과로 해석하면 안 된다.'),
'TXT_DIRECT_VLM':(
    'Qwen3-VL의 vision 입력을 비우고, MCQ 전체와 언어 정보만으로 직접 edit 목록을 만들게 한다. GUI_DIRECT_VLM과 같은 VLM 가중치·같은 edit 지시·같은 검증을 사용하되 screenshot을 제거한 조건이다. 고정 text-only Qwen3-8B를 호출하는 TXT_DIRECT_LM과 구별된다.',
    '직접 시각 edit가 좋아질 때 실제로 이미지가 추가 가치를 주는지 확인하는 핵심 대조다. 동시에 별도 inventory/extractor 없이 현재 평가 VLM을 text editor로 쓰는 방법 자체의 성능도 보여준다. 화면 정보는 없으므로 성공하더라도 GUI에서 독립적으로 검증한 alignment라고 부르지 않는다. Selection에서 점수가 높았지만 GUI 구조4개만 자동 winner로 고르는 정책 때문에 선택 후보는 아니었고, 내부 평가의 대조로는 유지했다.'),
'TXT_FULL':(
    '고정 Qwen3-8B가 원본 MCQ 다섯 필드를 모두 target GUI 언어로 번역한다. Referent뿐 아니라 방향·관계·설명 문맥과 보기의 자연어 부분도 번역한다. Screenshot·inventory·공통 extraction 결과는 사용하지 않고, 정확한 다섯 필드를 가진 JSON을 받아 최종 MCQ를 구성한다.',
    'Selective 편집보다 단순한 전체 번역이 충분한지 확인하는 기준이다. GUI_FULL과는 translator와 full-translation 지시가 같고 inventory 제공 여부가 다르다. 숫자·필드·중복 보기 등은 코드가 검사하지만 방향·부정·의미 보존 전체를 자동 보장하지는 못한다. 따라서 차이는 언어 이해와 번역 오류가 함께 반영된 pipeline 효과다. Full 조건의 edits 배열이 비어 있어도 실제 MCQ는 크게 바뀔 수 있어, 변경률은 최종 문자열로 다시 계산했다.'),
'GUI_FULL':(
    '평가 VLM이 query 없이 target screenshot을 전사한 inventory를 만들고, 고정 Qwen3-8B가 이 목록과 원본 MCQ를 받아 다섯 필드를 모두 target 언어로 번역한다. 번역 LM에는 screenshot 자체나 위치 정보가 없고, 정렬된 문자열 목록만 lexical evidence로 준다. Referent 추출 단계는 사용하지 않는다.',
    'TXT_FULL과 비교하면 같은 전체 번역에서 화면 어휘가 더해지는 효과를 본다. GUI_EXACT와 비교하면 화면 evidence는 공유하지만 context까지 번역하는 full pipeline과 selective pipeline의 차이를 볼 수 있다. 다만 span 추출·호출 구조도 달라 selectivity 하나의 순수 인과 효과는 아니다. GUI_MATCH_LM과 달리 full 출력의 각 단어가 반드시 inventory member여야 한다는 코드 제약은 없고, 대응이 불확실하면 일반 번역을 할 수 있다. Inventory가 실패해 빈 목록이 들어가도 pair를 버리지 않으므로 그 실패도 주 정확도에 포함된다.')}


def method_explanation(snapshot,method):
    paragraphs=[f'#### {method} — {NAMES[method]}',*METHOD_DETAILS[method]]
    observed=[]
    for stage in ['screen','selection','internal_evaluation']:
        record=snapshot['records'].get(stage,{}).get(method)
        if record:
            g=record['groups']['main']
            observed.append(f"{stage} {g['correct']}/{g['n']} ({pct(g['correct'],g['n'])}, O 대비 {pp((g['correct']-g['O_correct'])/g['n'])})")
    paragraphs.append('완료 결과를 따라 읽으면 '+', '.join(observed)+'다.' if observed else '아직 완료된 main 문제 풀이 결과가 없어 정확도를 제시하지 않는다.')
    record=snapshot['records'].get('internal_evaluation',{}).get(method)
    if record:
        g=record['groups']['main'];paragraphs.append(f"완료된 내부 평가에서 실제 MCQ 변경은 {record['main_changed']}/{g['n']}쌍, 오류 fallback은 {record['main_fallback']}쌍이었다. 이 결과는 실패와 무변경을 포함한 전체 pair 성능이며, 성공한 출력만 따로 골라 계산한 정확도가 아니다.")
    elif method in (snapshot.get('decision') or {}).get('evaluation_recipes',[]):
        paragraphs.append('이 조건의 내부 평가는 아직 완료되지 않았으므로 부분 출력의 정답률은 위 설명에 넣지 않았다.')
    else:
        paragraphs.append('이 조건은 이번 고정 내부 평가 대상에 포함되지 않았다. 개발 단계까지의 결과와 내부 평가 결과를 혼동하지 않는다.')
    return '\n\n'.join(paragraphs)


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
    snapshot['progress']={}
    decision=snapshot['decision'] or {}
    for condition in decision.get('evaluation_recipes',[]):
        extractor=decision['extractor'];base=run/'jobs/internal_evaluation'
        transformations=sorted((base/(extractor+'_'+condition)).glob('attempt_*'))
        predictions=sorted((base/('pred_'+extractor+'_'+condition)).glob('attempt_*'))
        td=transformations[-1] if transformations else None;pd=predictions[-1] if predictions else None
        if condition in snapshot['records']['internal_evaluation']:state='변환·문제 풀이·집계 완료'
        elif pd and completed(pd,cutoff):state='문제 풀이 완료·집계 대기'
        elif pd:state='문제 풀이 진행 중'
        elif td and completed(td,cutoff):state='변환 완료·문제 풀이 대기'
        elif td:state='변환 진행 중'
        else:state='미시작'
        f=pd/'predictions.jsonl' if pd else None
        count=sum(1 for line in f.open() if line.endswith('\n')) if f and f.exists() else 0
        snapshot['progress'][condition]={'state':state,'prediction_lines':count,'expected_lines':2*len(originals['internal_evaluation'])}
    snapshot['O_anchor_agreement']={s:all(x==maps[0] for x in maps) for s,maps in anchors.items() if maps}
    snapshot['contrasts']={}
    winner=(snapshot['decision'] or {}).get('winner','GUI_EXACT')
    for stage in ['screen','selection','internal_evaluation']:
        cs=[]
        for left,right in [(winner,'O'),(winner,'TXT_SEL'),(winner,'GUI_FULL'),('GUI_FULL','O'),('TXT_DIRECT_VLM','O'),('TXT_FULL','O'),('TXT_SEL','O'),('GUI_FULL','TXT_FULL'),('GUI_DIRECT_VLM','TXT_DIRECT_VLM')]:
            if left in outcomes[stage] and right in outcomes[stage]:
                cs.append({'left':left,'right':right,**paired_bootstrap(outcomes[stage][left],outcomes[stage][right],labels,meta['policy']['seed'],meta['policy']['bootstrap_replicates'])})
        snapshot['contrasts'][stage]=cs
    # Reference joins remain outside automatic method execution.
    use(HERE/'reference_comparison.py')
    data_contract=json.loads(use(run/'data_contract.json').read_text())
    refs,reference_meta,aliases=load_references(REPO,labels,originals,use,meta['models']['evaluation_vlm'],data_contract['baseline_contract'])
    snapshot['reference_comparison']=compare_cohorts(refs,reference_meta,aliases,outcomes,anchors,labels,snapshot['records'],run,originals,{**meta['policy'],'winner':winner},oracle)
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
        g=internal[winner]['groups']['main'];add(f"\n- 내부 평가에서 `{winner}`: **{g['correct']}/{g['n']} ({pct(g['correct'],g['n'])})**, O: **{g['O_correct']}/{g['n']} ({pct(g['O_correct'],g['n'])})**. 차이는 **{pp((g['correct']-g['O_correct'])/g['n'])}**, 회복{g['recovery']} / 회귀{g['regression']}다. 선택된 method의 점추정은 O 대비 개선을 보이지 않는다." if g['correct']<g['O_correct'] else f"\n- 완료된 내부 평가 `{winner}`: {pct(g['correct'],g['n'])}, O 대비 {pp((g['correct']-g['O_correct'])/g['n'])}.")
    for method in ['GUI_FULL','TXT_DIRECT_VLM','TXT_FULL','TXT_SEL']:
        if method in internal:
            g=internal[method]['groups']['main']
            add(f"- 완료된 내부 평가 `{method}`: **{g['correct']}/{g['n']} ({pct(g['correct'],g['n'])})**, O 대비 **{pp((g['correct']-g['O_correct'])/g['n'])}**, 회복{g['recovery']} / 회귀{g['regression']}.")
    if 'GUI_FULL' in internal and 'TXT_DIRECT_VLM' in internal:
        add('- GUI_FULL은 순증가가 작아도 많은 문항의 정오를 바꿨다. Selection에서 높았던 TXT_DIRECT_VLM도 내부 평가에서는 O를 넘지 못했다. 작은 선택 집합의 순위를 최종 성능으로 해석하면 안 된다.')
    if 'GUI_FULL' in screen and winner in screen:
        g=screen['GUI_FULL']['groups']['main'];w=screen[winner]['groups']['main'];add(f"- Screen main240쌍: GUI_FULL **{pct(g['correct'],g['n'])}**, {winner} **{pct(w['correct'],w['n'])}**, O **{pct(g['O_correct'],g['n'])}**. 현재 selective 구현이 full localization보다 낫다는 결과는 아니다.")
    if selection:
        best=max(selection,key=lambda k:selection[k]['groups']['main']['correct']);g=selection[best]['groups']['main'];add(f"- Selection의 최고 관측 대조는 `{best}` **{g['correct']}/{g['n']} ({pct(g['correct'],g['n'])})**. 자동 선택 `{winner}`는 GUI 후보4개 안에서 고른 잠정 후보이며 전체9조건의 최고를 뜻하지 않는다.")
    add('- 추출·matching·edit 프로토콜의 실패가 많이 남아 있다. 특히 원문 span 대신 번역문을 반환하거나 span ID를 잘못 반환하면 안전한 원문 fallback으로 처리됐다. 이를 화면 정보 자체가 효과 없다는 증거로 일반화하지 않는다.')
    add('- 독립 화면 검수가 없어 **GUI matching precision은 미측정**이다. Annotation span 경계 일치율을 replacement 정답률로 부르지 않는다.')
    rc=snapshot['reference_comparison']['cohorts'].get('internal_evaluation')
    if rc and winner in rc['methods']:
        values=rc['references'];r=rc['methods'][winner]
        add(f"- 같은 내부 평가{rc['n']}쌍의 reference는 T_REF **{pct(values['T_REF']['correct'],rc['n'])}**, R_REF **{pct(values['R_REF']['correct'],rc['n'])}**, F_REF **{pct(values['F_REF']['correct'],rc['n'])}**다. {winner}의 R 대비 차이는 **{pp(r['contrasts']['R_REF']['difference'])}**, F 대비 차이는 **{pp(r['contrasts']['F_REF']['difference'])}**다. 문항 범위는 같지만 과거 실행과의 batch/장비 차이는10절에 명시했다.")

    if snapshot.get('progress'):
        add('\n현재 내부 평가 진행 상태(파일 진행 수는 집계 시 읽은 참고값):\n\n| 조건 | 상태 | 기록된 문제 풀이/O 행 |\n| --- | --- | ---: |')
        for method,state in snapshot['progress'].items():add(f"| {method} | {state['state']} | {state['prediction_lines']}/{state['expected_lines']} |")
        add('\n행 수는 O와 해당 조건을 합친 실행 진행량이다. 완료되지 않은 행에서 정답률을 계산하지 않았다.')
    add('\n## 2. 범위와 조건\n\nQwen3-VL-8B-Instruct가 inventory·시각적 edit·문제 풀이를 수행하고, 고정 Qwen3-8B가 추출·번역·text matching을 맡는다. VL 추출 대조는 전체 VLM을 이미지 없이 호출하며 raw backbone 분리가 아니다. 원본 MCQ·A–D 순서·target screenshot·gold를 고정했다. 정답과 parallel annotation은 사후 평가에서만 사용한다.')
    add('\n| 단계 | Semantic item | 원문 MCQ | pair | 주 accuracy 분모 |\n| --- | ---: | ---: | ---: | --- |')
    for stage in ['probe','screen','selection','internal_evaluation']:
        c=snapshot['cohorts'][stage];n={'probe':'32 legacy','screen':'240 main + 48 legacy 별도','selection':'239 main (전체240은 민감도)','internal_evaluation':'1,416 main'}[stage]
        add(f"| {stage} | {c['semantic_items']} | {len({(r['parallel_id'],r['source_language']) for r in read(REPO/snapshot['run_dir']/'plan'/(stage+'.jsonl'))})} | {c['pairs']} | {n} |")
    add('\nScreen32개는 pilot12 + calibration20이다. Selection은 나머지 calibration20, 내부 평가는 기존118이다. 사전 제외 `rel::5/forest_9.jpg::zh::ru`는 selection에서만 빠진다. 전체158개는 역사적으로 관찰된 development cohort다. Pilot과 main, 반복 튜닝한 screen과 selection, 내부 평가를 합쳐 하나의 일반화 accuracy로 보고하지 않는다.')
    add('\n### 단계를 나눈 이유\n\nProbe는 작은 기존 pilot에서 프롬프트가 빈 목록만 내는지, span/JSON 형식을 지키는지와 호출 비용을 확인하는 단계다. Screen은 기존 pilot과 calibration 일부에서 후보를 비교하고 추출기와 구조 shortlist를 고르는 개발 단계다. 자동화 버전은 작은 probe의 우연한 점수로 구조를 버리지 않도록 9개 구조를 모두 screen에서 실행했다.\n\nSelection은 남겨둔 20개 calibration item으로 shortlist 2개를 비교하는 단계다. 그 결과로 선택과 대조 조건을 동결한 뒤 118개 internal evaluation을 실행한다. 내부 평가 결과로 winner를 다시 선택하거나 프롬프트를 수정하지 않는다. 다만 전체 cohort 자체는 역사적으로 관찰됐으므로 이 분할만으로 완전히 독립적인 최종 검증이 되지는 않는다.')
    add('\n### 공통 절차와 O 대조\n\n주 평가 대상은 text-dependent REL의 객관식 문제다. Point나bbox를 출력하는 grounding task의 정확도와 구별한다. 또한 GUI_FULL은 이번에 자동 번역으로 만든 조건이므로, 기존 ORCF의parallel F 입력과 같지 않다. GUI_EXACT도 기존 R_REF를 그대로 사용한 조건이 아니다.\n\nSource는 원래 문제 언어, GUI 언어는 screenshot에 실제 표시된 언어다. Referent는 질문의 기준 요소나 선택지가 가리키는 이름이고, context는 방향·관계·일반 설명이다. 예를 들어 blue Search button에서 바꾸려는 최소 이름은 Search이며 blue와 button은 유지할 문맥이다. Span은 원문에서 교체할 부분의 문자 범위, edit는 그 부분을 어떤 표현으로 바꿀지에 대한 제안이다. Matching은 source 이름과 화면 표기를 연결하는 단계이고, fallback은 검증에 실패한 제안을 버리고 원래 문제를 사용하는 처리다. 이하 Rooms→房间/客房 같은 예시는 절차 설명용 가상 예시이고 실제 성공 출력으로 제시한 것은 아니다.\n\nO는 screenshot과 원본 MCQ를 그대로 평가 VLM에 주는 mismatch 기준이다. 모든 변환 조건도 마지막에는 동일한 Qwen3-VL이 해당 screenshot과 최종 MCQ를 받아 A–D 한 글자를 답한다. Transform 단계가 내놓은 답을 채택하는 실험은 아니다. 정답은 이 마지막 평가 경계에서만 읽는다.\n\nInventory는 screenshot만 보고 추출한 화면 문자열 목록이다. Query나 A–D를 주지 않으며, 정규화·중복 제거·사전식 정렬 후 공유하므로 위치나 읽기 순서는 전달하지 않는다. 공통 referent extractor는 반대로 source MCQ와 source 언어만 보며 screenshot·inventory·GUI 언어는 보지 않는다. 두 입력 경계를 분리해 화면 어휘의 추가 효과를 비교한다.')
    add('\n| ID | 방법 |\n| --- | --- |')
    for key in ORDER:add(f'| {key} | {NAMES[key]} |')
    add('\n설정: BF16·SDPA·2MP, patch Conv3D channels_last_3d, method batch1/최대768token, 문제 풀이 batch3/최대2token. 전체 입력4096token 상한이며 초과 시 무음 truncation하지 않는다. 원문에서 복원할 수 없는 edit나 새 중복 보기는 거절하고 원문을 유지한다. 실제 prompt는 [원문 해설](PROMPTS_AND_GO_NO_GO_KO.md)과 [현재 후보 코드](../../../01_code/src/mpr_crosslocale/methods/selective_alignment/search.py), 선택 규칙은 [pipeline/OOM 문서](PIPELINE_OOM_AUDIT_KO.md)를 참고한다.')
    add('\n### 각 변환 실험의 입력·절차·비교 목적')
    for method in ORDER:add('\n'+method_explanation(snapshot,method))
    add('\n## 3. 참조 추출 결과\n\nP는 추출한 표현 중 맞은 비율, R은 찾아야 할 표현 중 찾은 비율, F1은 둘을 함께 반영한 값이다. 여기서는 원문 character span의 exact match로 판정한다. 응답 전체가 span 검증에서 실패하면 빈 결과로 포함한다. `검증 실패`에는 JSON syntax뿐 아니라 원문 substring·occurrence·중첩 오류도 들어간다. 정상 빈 목록과 구분한다.')
    add('\n### 추출 프롬프트 3종은 무엇이 다른가\n\n`original`은 GUI를 가리키는 최소 표현을 찾되 공간 관계·부정·수량을 제외하라는 기존 지시다. field/text/occurrence와 label/icon/brand 등의 kind를 반환하게 했다. 이것은 이전 빈 목록 현상을 다시 확인하는 기준이며, 이 연구에서 이미 잘 작동한다고 검증된 prompt가 아니다.\n\n`minimal`은 바꿀 대상을 화면에 쓰인 최소 이름으로 더 구체화했다. 색상·button/input field 같은 요소 종류·공간 관계·일반 문맥은 span에 포함하지 않고, 이름 안의 숫자와 파일 확장자는 유지하게 했다. 인용부호가 없어도 이름을 찾고, 이름 없는 아이콘 설명은 그대로 둔다. 일반 kind 분류도 요구하지 않아 original과는 경계 정의뿐 아니라 출력 과제의 복잡도도 달라진다.\n\n`contrastive`는 minimal에 경계·제외 예시를 붙였다. 예를 들어 red Launch button에서는 Launch만, Archive 2024.zip에서는 숫자와 확장자까지 포함하고, 이름 없는 방향 기반 아이콘 설명은 추출하지 않는다는 synthetic 예시다. RU/ZH/TH의 복사 예시도 있다. Benchmark 정답이나 parallel 참조는 예시로 사용하지 않았다. 따라서 비교 대상은 단어 한두 개만 바꾼 prompt가 아니라 예시를 포함한 task instruction이다.')
    add('\n### 모델 2종과 CPU 기준은 어떻게 비교했나\n\n`fixed_original/minimal/contrastive`는 고정 text-only Qwen3-8B를 쓰며 non-thinking template을 명시했다. `vl_original/minimal/contrastive`는 같은 세 지시를 Qwen3-VL에 이미지 없이 준다. 후자는 평가 VLM의 multimodal 학습 후 language weights를 활용하는 비교지만 vision 모듈을 제거한 raw backbone 실험은 아니다. 같은 prompt를 두 모델에 주었으므로 모델별 응답 성향을 볼 수 있고, 한 모델 안에서는 세 prompt의 차이를 볼 수 있다. 모두 같은 generation 상한과 검증 규칙을 사용했다.\n\n`cpu_quoted`는 따옴표 안 문자열을 규칙으로 복사하는 진단 대조다. 빠르고 source span이 명확하지만 따옴표가 없는 이름이나 묘사를 놓친다. 이 조건의 좋은 F1은 따옴표 단서가 유용하다는 결과이며, 전체 언어·GUI를 해결했다는 뜻이 아니다. 이번 정책에서는 LM 후보 승격에서 제외했고 downstream recipe와 결합해 평가하지 않았다.')
    for stage,rows in snapshot['extractors'].items():
        add(f'\n### {stage}: {rows[0]["metrics"]["mcqs"]}개 원문 MCQ\n\n| 조건 | P | R | F1 | 정상 빈 목록 | 검증 실패 | 완전한 span set | 초/MCQ¹ |\n| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |')
        for r in rows:
            m=r['metrics'];lat='— (미계측 CPU)' if r['cpu_latency_unmeasured'] else f"{r['ms_per_mcq']/1000:.2f}"
            add(f"| {r['id']} | {pct(m['tp'],m['predicted']) if m['predicted'] else 'N/A'} | {pct(m['tp'],m['gold'])} | {100*(m['f1'] or 0):.2f}% | {r['valid_empty']} | {m['schema_failed']} | {m['complete_span_set']}/{m['mcqs']} | {lat} |")
    add('\n¹ Load 제외 고유 backend runtime의 평균이며 cache hit도 원래 측정값으로 산입한다. CPU 기준의0 기록은 GPU 호출이 없다는 뜻이지 실제 CPU 시간이0초라는 뜻은 아니다.')
    add('\nProbe에서 VL original은 정상 빈 목록이30/32개였다. 예시를 추가한 VL contrastive는 빈 응답을 줄였지만 낮은 precision이 남았다. 고정 LM도 prompt 보정으로 좋아졌으나, screen fixed_contrastive의 recall39.40%·F1 53.12%라 충분히 해결됐다고 보기 어렵다. CPU quoted의 probe F1이55.42%로 가장 높았지만, 이 조건은 인용부호 한정 진단 기준이라 자동 LM 승격 대상에서 제외됐다.')
    add('\nScreen fixed_contrastive는 minimal보다 precision이 높고 recall은 약간 낮았다. F1 차이는0.45%p로 작으며, 자동 정책은 F1 최고에서0.02(2%p) 이내면 비용을 비교한다. 이 단계에서는 contrastive가 더 빨라 고정됐다. 이를 모든 언어·문항에서 우월한 prompt라는 결론으로 확대하지 않는다.')
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
    add('\nSelection에서는 GUI_EXACT의 회복4/회귀2와 GUI_FULL의 회복27/회귀25가 같은 순증가2를 만들었다. 평균 정확도가 같아도 바뀐 문항과 회귀 위험은 다르다. 아래 완료된 내부 평가에서도 같은 관점으로 읽어야 한다.')
    if winner in internal and 'GUI_FULL' in internal:
        w=internal[winner]['groups']['main'];g=internal['GUI_FULL']['groups']['main']
        add(f"\n내부 평가에서는 {winner}의 회복{w['recovery']}/회귀{w['regression']}와 GUI_FULL의 회복{g['recovery']}/회귀{g['regression']}를 비교할 수 있다. GUI_FULL이 정오를 바꾼 수는 {g['recovery']+g['regression']}쌍이지만 순변화는 {g['correct']-g['O_correct']:+}개다. {winner}보다 {g['correct']-w['correct']:+}개 맞혔다는 점추정과, item별 변동을 반영한 CI를 함께 봐야 한다.")
    if 'TXT_DIRECT_VLM' in internal:
        g=internal['TXT_DIRECT_VLM']['groups']['main'];s=selection['TXT_DIRECT_VLM']['groups']['main']
        add(f"\nTXT_DIRECT_VLM은 selection에서 {pct(s['correct'],s['n'])}였지만 내부 평가에서는 {pct(g['correct'],g['n'])}였다. 두 집합의 난이도가 달라 절대값 하락만으로 과적합을 확정할 수는 없지만, 같은 내부 집합의 O 대비 {pp((g['correct']-g['O_correct'])/g['n'])}이므로 selection의 우세가 그대로 이어졌다고 볼 수 없다.")
    if 'GUI_FULL' in internal and 'TXT_FULL' in internal:
        g=internal['GUI_FULL']['groups']['main'];t=internal['TXT_FULL']['groups']['main']
        add(f"\n완료된 전체 번역 대조에서는 GUI_FULL {pct(g['correct'],g['n'])}와 TXT_FULL {pct(t['correct'],t['n'])} 사이에 {pp((g['correct']-t['correct'])/g['n'])} 차이가 있다. 같은 번역 모델·전체 번역 task에 화면 문자열을 추가한 pipeline이 더 나았다는 관찰이다. 반면 GUI_FULL 자체의 O 대비 차이는 {pp((g['correct']-g['O_correct'])/g['n'])}이며 CI도 함께 확인해야 한다. 이를 참조 표현의 alignment 하나만의 인과 효과로 읽거나, 전체 번역이 원본보다 확실히 우수하다고 결론 내리지는 않는다.")
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
    add('\n'+render_comparison(snapshot['reference_comparison'],ORDER))
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
