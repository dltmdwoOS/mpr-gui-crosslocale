"""Read COMPLETE external-baseline stages; CPU paired analysis and cost report."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile

REPO=Path(__file__).resolve().parents[3];ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(REPO/'01_code/src'),str(REPO),str(Path(__file__).parent)]
from run_external_baselines import verify,COHORTS
from run_stem_refinement_2x2 import latest
from run_stem_only_gui import read,write,unique,jsonl
from search_pipeline import EXCLUDED,paired_bootstrap
from compare_end_to_end import call_map,call_seconds,batch_share
from mpr_crosslocale.methods.selective_alignment.schemas import digest
from followup_rel_4lang.method_dev import external_baselines as method
from mpr_crosslocale.inference.answer_parser import parse_label


def cue_audit(before,after):
    """Surface cues for review only; UI names/paraphrases can yield false positives."""
    directions={
        'en': {'above':r'\b(?:above|over)\b','below':r'\b(?:below|under|beneath)\b','left':r'\bleft\b','right':r'\bright\b','negation':r'\b(?:not|no|without|neither)\b'},
        'ru': {'above':r'выше|сверху|\bнад\b','below':r'ниже|снизу|\bпод\b','left':r'слева|левее','right':r'справа|правее','negation':r'\b(?:не|нет|без)\b'},
        'zh': {'above':r'上方|上面|之上','below':r'下方|下面|之下','left':r'左','right':r'右','negation':r'不|没有|沒有|不是'},
        'th': {'above':r'เหนือ|ด้านบน|ข้างบน','below':r'ใต้|ด้านล่าง|ข้างล่าง','left':r'ซ้าย','right':r'ขวา','negation':r'ไม่|ไม่มี'},
    }
    flagged=[]
    for field in ('question_stem','A','B','C','D'):
        src=before['question_stem'] if field=='question_stem' else before['options'][field]
        tgt=after['question_stem'] if field=='question_stem' else after['options'][field]
        a={k for k,v in directions[before['source_language']].items() if re.search(v,src,re.IGNORECASE)}
        b={k for k,v in directions['en'].items() if re.search(v,tgt,re.IGNORECASE)}
        if a!=b:flagged.append({'field':field,'source_cues':sorted(a),'english_cues':sorted(b)})
    return flagged


def smoke_summary(run):
    c=verify(run);out={}
    for stage in ('translate','alignment'):
        d=latest(run,stage);records=read(d/'transformations.jsonl')
        out[stage]={'sources':len(records),'status':dict(Counter(r['status'] for r in records)),
            'cap_hits':sum(a['output_tokens']==a['generation']['max_new_tokens'] for r in records for a in r['attempts']),
            'peak_reserved_bytes':max((a.get('peak_reserved_bytes') or 0 for r in records for a in r['attempts']),default=0),
            'wall_seconds':json.loads((d/'cost.json').read_text())['wall_seconds']}
    for stage in ('infer_tt','infer_clp'):
        records=read(latest(run/'screen',stage)/'evaluation/predictions.jsonl')
        if len(records)!=3 or any(r['execution_mode']!='gpu' for r in records):raise ValueError('Real 3-row GPU smoke required')
        out[stage]={'rows':len(records),'valid_labels':sum(r['parsed_generated_label'] in ('A','B','C','D') for r in records),
            'output_cap_hits':sum(r.get('output_cap_hit',False) for r in records),
            'output_tokens':[r['output_tokens'] for r in records],
            'peak_reserved_bytes':max(r['peak_reserved_bytes'] for r in records),'max_input_tokens':max(r['prompt_tokens'] for r in records)}
    write(run/'SMOKE_CHECK.json',{'functionality_only':True,'accuracy_not_evaluated':True,'contract_sha256':digest(c),**out})
    print(json.dumps(out,ensure_ascii=False,indent=2))


def report(run):
    c=verify(run)
    if c['execution_mode']!='gpu':raise ValueError('No mock performance report')
    if c['smoke']:smoke_summary(run);return
    labels=unique(read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels)!=c['labels_sha256']:raise ValueError('Labels changed')
    values={};cost={};quality={};audit_examples={};captures=[run/'contract.json',Path(__file__),ROOT/'reports/EXTERNAL_BASELINES_PROTOCOL_KO.md']
    for path in c['source_sha256']:
        if path.endswith('.py') or '/configs/' in path:captures.append(REPO/path)
    for cohort in c['cohorts']:
        work=run/cohort;original=unique(read(work/'inputs.jsonl'));ids=sorted(p for p in original if labels[p]['split']=='main' and p!=EXCLUDED)
        values[cohort]={};cost[cohort]={};quality[cohort]={};captures += [work/'inputs.jsonl']
        refs={}
        for name,key,condition in [('O','O_predictions','O'),('E1_M0','E1_M0_predictions','E1_M0')]:
            pred=unique([r for r in read(Path(c['descriptors'][cohort][key])) if r['condition']==condition])
            if not set(original)<=set(pred):raise ValueError('Historical comparison incomplete')
            values[cohort][name]={p:int(pred[p]['status']=='success' and pred[p]['parsed_generated_label']==labels[p]['gold_answer']) for p in ids}
            for p in original:
                refs[name,p]={k:pred[p][k] for k in ('pair_id','parallel_id','condition','execution_mode','status','generated_text','parsed_generated_label')}
        refpath=work/'comparison_references.jsonl';jsonl(refpath,list(refs.values()));captures.append(refpath)
        for condition,transform,stage in [(method.TT,'translate','infer_tt'),(method.CLP,'alignment','infer_clp')]:
            try:td=latest(run,transform);inf=latest(work,stage)
            except ValueError:continue
            pp=read(inf/'evaluation/predictions.jsonl');pred=unique(pp)
            if set(pred)!=set(original):raise ValueError('Incomplete paired baseline')
            parser=parse_label if condition==method.TT else method.parse_clp_answer
            if any(r['execution_mode']!='gpu' or r['condition']!=condition or parser(r['generated_text'])!=r['parsed_generated_label'] for r in pp):raise ValueError('Invalid prediction provenance/parser')
            values[cohort][condition]={p:int(pred[p]['status']=='success' and pred[p]['parsed_generated_label']==labels[p]['gold_answer']) for p in ids}
            transformed={r['source_key']:r for r in read(td/'transformations.jsonl')}
            source_ids={digest(method.source_payload(original[p])) for p in ids};required=[transformed[k] for k in source_ids]
            lm=call_seconds(call_map(required));answer=batch_share(pp,lambda r:r['pair_id'] in ids)['seconds']
            cost[cohort][condition]={'primary_pairs':len(ids),'items':len({labels[p]['parallel_id'] for p in ids}),
                'source_mcqs':len(source_ids),'LM_seconds':lm,'answer_seconds':answer,'total_seconds':lm+answer,
                'seconds_per_pair':(lm+answer)/len(ids),'inference_new_wall':json.loads((inf/'evaluation/cost.json').read_text()),
                'shared_transform_wall_all_sources':json.loads((td/'cost.json').read_text())['wall_seconds']}
            quality[cohort][condition]={'source_status':dict(Counter(r['status'] for r in required)),
                'LM_cap_hits_unique_sources':sum(any(a['output_tokens']==a['generation']['max_new_tokens'] for a in r['attempts']) for r in required),
                'invalid_final_label_pairs':sum(pred[p]['parsed_generated_label'] not in ('A','B','C','D') for p in ids),
                'solver_cap_hits_pairs':sum(pred[p].get('output_cap_hit',False) for p in ids),
                'generated_output_tokens':sum(pred[p]['output_tokens'] for p in ids)}
            if condition==method.TT:
                rewritten=unique(read(inf/'view/rewrite/rewritten.jsonl'))
                flags={p:cue_audit(original[p],rewritten[p]) for p in ids}
                quality[cohort][condition].update(digit_change_pairs=sum(bool(rewritten[p]['diagnostics']['digit_sequence_changed_fields']) for p in ids),
                    duplicate_option_pairs=sum(rewritten[p]['diagnostics']['new_duplicate_options'] for p in ids),
                    fallback_pairs=sum(rewritten[p]['status']=='fallback_original' for p in ids),
                    surface_direction_or_negation_cue_flags=sum(bool(v) for v in flags.values()),
                    unchanged_MCQs_label_changes=sum(rewritten[p]['question_stem']==original[p]['question_stem'] and rewritten[p]['options']==original[p]['options'] and pred[p]['parsed_generated_label']!=refs['O',p]['parsed_generated_label'] for p in ids))
                for p in ids:
                    key=digest(method.source_payload(original[p]))
                    if flags[p] or rewritten[p]['diagnostics']['digit_sequence_changed_fields'] or rewritten[p]['diagnostics']['new_duplicate_options']:
                        audit_examples.setdefault(key,{'pair_id':p,'source':method.source_payload(original[p]),'translated':{'question_stem':rewritten[p]['question_stem'],'options':rewritten[p]['options']},
                            'cue_flags':flags[p],'other_flags':rewritten[p]['diagnostics']})
            captures += [p for p in td.rglob('*') if p.is_file() and p.name!='calls.json']
            captures += [p for p in inf.rglob('*') if p.is_file() and 'reuse_' not in p.name and p.name!='calls.json']
    common=set.intersection(*(set(v) for v in values.values()))
    values['combined']={k:{p:x for cohort in c['cohorts'] for p,x in values[cohort][k].items()} for k in sorted(common)}
    summary={}
    for cohort,v in values.items():
        ids=sorted(v['O']);summary[cohort]={'n':len(ids),'items':len({labels[p]['parallel_id'] for p in ids}),
            'correct':{k:sum(x.values()) for k,x in v.items()},
            'versus_O':{k:paired_bootstrap(x,v['O'],labels,20261115,10000) for k,x in v.items() if k!='O'},
            'E1_versus_external':{k:paired_bootstrap(v['E1_M0'],v[k],labels,20261115,10000) for k in (method.TT,method.CLP) if k in v},
            'by_gui':{g:{'n':sum(p.endswith('::'+g) for p in ids),'correct':{k:sum(x[p] for p in ids if p.endswith('::'+g)) for k,x in v.items()}} for g in ('en','zh','th','ru')}}
    saved=json.loads((ROOT/'artifacts/e1_stem_full_dev_results_snapshot.json').read_text())['results']['summary']
    for cohort,ss in summary.items():
        ref=saved['all_158' if cohort=='combined' else cohort]
        if (ss['n'],ss['correct']['O'],ss['correct']['E1_M0'])!=(ref['n'],ref['correct']['O_B200'],ref['correct']['E1_M0']):
            raise ValueError('Historical O/E1 comparison does not reproduce completed 8B report')
    if (run/'COMPLETE.json').exists():
        done=json.loads((run/'COMPLETE.json').read_text())
        if done['contract_sha256']!=digest(c) or common!={'O','E1_M0',method.TT,method.CLP}:raise ValueError('Completion differs')
        if summary['combined']['n']!=1895 or summary['combined']['items']!=158:raise ValueError('Full cohort denominator differs')
        captures.append(run/'COMPLETE.json')
    else:done=None
    captures=sorted(set(captures));manifest={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in captures}
    snapshot={'as_of_utc':datetime.now(timezone.utc).isoformat(),'development_only':True,'summary':summary,'costs':cost,'quality':quality,
        'config':c['config'],'clp_profile':c['clp_profile'],'adaptations':c['spec'],'contract_sha256':digest(c),'complete':done,
        'source_and_raw_sha256':manifest,'interpretation':'GUI task adaptations, not original-paper reproduction. CLP has longer solver budget; comparison is pipeline-level. No independent confirmatory claim.'}
    write(ROOT/'artifacts/external_baselines_results_snapshot.json',snapshot)
    write(run/'translation_audit_flags.json',list(audit_examples.values()))
    audit_lines=['# Translate-Test 내용 보존 검토 후보','','숫자/새 보기중복 및 방향·부정 표면 cue 차이를 표시한 검수 후보다. 의역·UI 이름으로 인한 오탐이 있어 의미 오류율로 해석하지 않는다. 자동 출력의 채택/수정/repair/점수에 사용하지 않았다.','']
    for language in ('ru','zh','th'):
        sample=[v for v in audit_examples.values() if v['source']['source_language']==language][:4]
        for example in sample:
            audit_lines += ['## '+example['pair_id'],'','```json',json.dumps(example,ensure_ascii=False,indent=2),'```','']
    (ROOT/'reports/EXTERNAL_BASELINES_TRANSLATION_AUDIT_KO.md').write_text('\n'.join(audit_lines))
    archive=ROOT/'artifacts/external_baselines_completed.tar.gz'
    with tarfile.open(archive,'w:gz',compresslevel=6) as tf:
        for path in captures:tf.add(path,arcname=str(path.relative_to(REPO)),recursive=False)
    write(ROOT/'artifacts/external_baselines_archive_manifest.json',{'path':str(archive.relative_to(REPO)),'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':manifest})
    lines=['# 외부 baseline GUI 이식 결과','','[고정 프로토콜과 원 논문·공식 구현](EXTERNAL_BASELINES_PROTOCOL_KO.md). TT는 Qwen3-8B English 전체 번역, CLP는 고정 LM의 English 이해 응답을 대화에 보존한 뒤 Qwen3-VL-8B가 이미지를 보며 단계별 풀이한다. Google Translate/GPT-3.5 원 결과의 재현과 구분한다.','',
        '| 범위 | n | O | E1/M0 | Translate-Test EN | CLP GUI |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for cohort,ss in summary.items():
        n=ss['n'];cells=[f'{ss["correct"][k]}/{n} ({ss["correct"][k]/n:.2%})' if k in ss['correct'] else '미완료' for k in ('O','E1_M0',method.TT,method.CLP)]
        lines.append(f'| {cohort} | {n} | '+' | '.join(cells)+' |')
    lines += ['','| 범위 | 비교 | 차이 | 95% item bootstrap CI | 회복/회귀 |','| --- | --- | ---: | --- | ---: |']
    for cohort,ss in summary.items():
        for name,x in ss['E1_versus_external'].items():lines.append(f'| {cohort} | E1/M0 − {name} | {100*x["difference"]:+.2f}pp | [{100*x["ci95"][0]:+.2f}, {100*x["ci95"][1]:+.2f}] | {x["recovery"]}/{x["regression"]} |')
    lines += ['','전체 주 분석은 pilot 48쌍과 사전 제외 1쌍을 뺀 main 1895쌍이다. 실패·미변환·CLP 최종 label 실패를 제거하지 않았다. 이미 관찰한 158개 개발 문항의 탐색 결과다. 모든 CI는 semantic item 단위 10,000회 bootstrap이며, 반복 개발·다중 비교를 보정한 독립 검증은 아니다.','',
        '| 범위 | 조건 | 비용n | LM 초 | 풀이VLM 초 | 합계 초 | 초/pair | 초/item |','| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for cohort,cc in cost.items():
        for name,x in cc.items():lines.append(f'| {cohort} | {name} | {x["primary_pairs"]} | {x["LM_seconds"]:.2f} | {x["answer_seconds"]:.2f} | {x["total_seconds"]:.2f} | {x["seconds_per_pair"]:.3f} | {x["total_seconds"]/x["items"]:.2f} |')
    lines += ['',
        '위 시간은 고유 source 처리를 공유한 recipe 계산 구간이다. Cache도 원래 runtime으로 청구하고 batch는 선택행비율로 안분했다. 모델적재·worker기동·일부CPU처리는 제외한다. 초/pair는 상각 처리량이며 단일 query latency가 아니다. COMPLETE는 마지막 재개 invocation wall, stage cost는 완료 attempt wall을 기록한다. 중단된 이전 attempt의 wall이 없을 수 있으므로 이를 모든 시도 합산 wall로 부르지 않는다. 원래 cache 호출 runtime은 recipe에 보존한다.','',
        'CLP는 VLM출력512tokens로 기존 label-only2tokens보다 큰 예산이다. E1/M0와의 차이는GUI inventory 하나의 순수 효과가아니다. 숫자/보기중복 경고는의미 오류율이아니며, 번역의 방향·부정 의미 보존을 자동 보장하지 않는다.','',
        '## 처리 진단','', '```json',json.dumps(quality,ensure_ascii=False,indent=2),'```','',
        '[전체 설정·비용·언어별 결과 snapshot](../artifacts/external_baselines_results_snapshot.json) · [번역 내용 보존 검토 후보](EXTERNAL_BASELINES_TRANSLATION_AUDIT_KO.md) · [완료 raw archive](../artifacts/external_baselines_completed.tar.gz) · [archive checksum](../artifacts/external_baselines_archive_manifest.json)','']
    (ROOT/'reports/EXTERNAL_BASELINES_RESULTS_KO.md').write_text('\n'.join(lines))
    print('REPORTED',list(common),run,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-dir',type=Path,default=ROOT/'artifacts/external_baselines_v1')
    report(p.parse_args().run_dir.resolve())
