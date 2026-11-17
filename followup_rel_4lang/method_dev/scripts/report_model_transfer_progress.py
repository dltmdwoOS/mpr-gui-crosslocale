"""CPU-only report and compact archive of COMPLETE transfer cohorts; never alter run contracts."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO/'01_code/src'), str(REPO), str(Path(__file__).parent)]
from run_model_transfer import verify, latest, read, unique
from search_pipeline import EXCLUDED, paired_bootstrap
from compare_end_to_end import call_map, call_seconds, batch_share
from mpr_crosslocale.methods.selective_alignment.schemas import digest, fields
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits
from mpr_crosslocale.inference.answer_parser import parse_label
from followup_rel_4lang.method_dev.two_stage_v2 import prompts


def report(run):
    c = verify(run)
    if c['execution_mode'] != 'gpu':
        raise ValueError('Empirical GPU run required')
    labels = unique(read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels) != c['labels_sha256']:
        raise ValueError('Labels changed')
    stages = ('inventory', 'rewrite', 'infer_O', 'infer_E1_M0')
    completed, pending, paths, values, costs, quality = [], [], [run/'contract.json'], {}, {}, {}
    shared_records = {'inventory_seconds': [], 'extraction_seconds': [], 'matching_seconds': []}
    for cohort in c['cohorts']:
        work = run/cohort
        try:
            dirs = {s: latest(work, s) for s in stages}
        except ValueError:
            pending.append(cohort)
            continue
        completed.append(cohort)
        original = unique(read(work/'inputs.jsonl'))
        if digest(list(original.values())) != json.loads((work/'contract.json').read_text())['inputs_sha256']:
            raise ValueError('Inputs changed')
        ids = sorted(p for p in original if labels[p]['split'] == 'main' and p != EXCLUDED)
        if len(ids) != {'screen': 240, 'selection': 239, 'internal_evaluation': 1416}[cohort]:
            raise ValueError('Wrong primary denominator')
        values[cohort] = {}
        predictions = {}
        for condition in ('O', 'E1_M0'):
            directory = dirs['infer_'+condition]/'evaluation'
            pp = read(directory/'predictions.jsonl')
            pred = unique(pp)
            ec = json.loads((directory/'contract.json').read_text())
            if ec['downstream'] != c['downstream'] or set(pred) != set(original):
                raise ValueError('Incomplete/profile-mismatched predictions')
            if any(r['execution_mode'] != 'gpu' or r['condition'] != condition or parse_label(r['generated_text']) != r['parsed_generated_label'] for r in pp):
                raise ValueError('Invalid prediction provenance/parser')
            values[cohort][condition] = {p: int(pred[p]['status'] == 'success' and pred[p]['parsed_generated_label'] == labels[p]['gold_answer']) for p in ids}
            predictions[condition] = pp
        rw = unique(read(dirs['rewrite']/'rewritten.jsonl'))
        inv = {r['image_sha256']: r for r in read(dirs['inventory']/'inventories.jsonl')}
        extpath = work/'extraction/E1/attempt_import/extractions.jsonl'
        ext = {r['source_key']: r for r in read(extpath)}
        if set(rw) != set(original) or any(rw[p]['options'] != original[p]['options'] or any(e['field'] != 'question_stem' for e in rw[p]['edits']) for p in rw):
            raise ValueError('Pair/option/stem scope invariant failed')
        for p, row in rw.items():
            if any(row[k] != original[p][k] for k in ('parallel_id','source_language','gui_language','image_path','image_sha256','option_order')):
                raise ValueError('Paired identity differs')
            if apply_edits(original[p], row['edits']) != fields(row):
                raise ValueError('Non-referent context changed')
        spec = c['config']['models']['inventory']
        if any(a['model_id'] != spec['model_id'] or a['revision'] != spec['revision'] or r['query_content_exposed'] for r in inv.values() for a in r['attempts']):
            raise ValueError('Wrong inventory model/query exposure')
        images = {original[p]['image_sha256'] for p in ids}
        quality[cohort] = {'executed_pairs': len(original), 'main_pairs': len(ids),
            'inventory_main': dict(Counter(inv[s]['status'] for s in images)),
            'inventory_all': dict(Counter(r['status'] for r in inv.values())),
            'rewrite_status': dict(Counter(rw[p]['status'] for p in ids)),
            'errors': dict(Counter(e for p in ids for e in rw[p]['errors'])),
            'changed': sum(fields(rw[p]) != fields(original[p]) for p in ids),
            'invalid_labels': {k: sum(r['parsed_generated_label'] not in ('A','B','C','D') for r in pp if r['pair_id'] in ids) for k, pp in predictions.items()}}
        stage_cost = {s: json.loads((dirs[s]/('evaluation/cost.json' if s.startswith('infer') else 'cost.json')).read_text()) for s in stages}
        recipe = {'inventory_seconds': call_seconds(call_map([inv[s] for s in images])),
                  'extraction_seconds': call_seconds(call_map([ext[digest(prompts.extraction_payload(original[p], stem_only=True))] for p in ids])),
                  'matching_seconds': call_seconds(call_map([rw[p] for p in ids])),
                  'answer_seconds': batch_share(predictions['E1_M0'], lambda r: r['pair_id'] in ids)['seconds']}
        recipe['total_seconds'] = sum(recipe.values())
        shared_records['inventory_seconds'] += [inv[s] for s in images]
        shared_records['extraction_seconds'] += [ext[digest(prompts.extraction_payload(original[p], stem_only=True))] for p in ids]
        shared_records['matching_seconds'] += [rw[p] for p in ids]
        costs[cohort] = {'executed_pairs': len(original), 'primary_pairs': len(ids), 'stage_wall': stage_cost,
                         'method_stage_wall_seconds': sum(stage_cost[s]['wall_seconds'] for s in ('inventory','rewrite','infer_E1_M0')),
                         'primary_logical_recipe': recipe,
                         'O_primary_answer_seconds': batch_share(predictions['O'], lambda r: r['pair_id'] in ids)['seconds']}
        paths += [work/'inputs.jsonl', work/'contract.json', extpath, work/'extraction/E1/attempt_import/cost.json']
        for s, directory in dirs.items():
            paths += [p for p in directory.rglob('*') if p.is_file() and 'view' not in p.relative_to(directory).parts and p.name != 'calls.json']
    if not completed:
        raise ValueError('No complete cohorts')
    if len(completed) > 1:
        values['combined'] = {k: {p: v for cohort in completed for p, v in values[cohort][k].items()} for k in ('O','E1_M0')}
    summary = {}
    for cohort, v in values.items():
        ids = sorted(v['O'])
        summary[cohort] = {'n': len(ids), 'items': len({labels[p]['parallel_id'] for p in ids}),
            'correct': {k: sum(a.values()) for k, a in v.items()},
            'contrast': paired_bootstrap(v['E1_M0'],v['O'],labels,20261115,10000),
            'by_gui': {g: {'n': sum(p.endswith('::'+g) for p in ids), 'correct': {k: sum(a[p] for p in ids if p.endswith('::'+g)) for k,a in v.items()}} for g in ('en','zh','th','ru')}}
    combined_recipe = {k: call_seconds(call_map(records)) for k, records in shared_records.items()}
    combined_recipe['answer_seconds'] = sum(v['primary_logical_recipe']['answer_seconds'] for v in costs.values())
    combined_recipe['total_seconds'] = sum(combined_recipe.values())
    total_cost = {'primary_pairs': sum(v['primary_pairs'] for v in costs.values()),
                  'executed_pairs': sum(v['executed_pairs'] for v in costs.values()),
                  'primary_logical_recipe': combined_recipe,
                  'method_stage_wall_seconds': sum(v['method_stage_wall_seconds'] for v in costs.values()),
                  'all_stages_wall_seconds': sum(s['wall_seconds'] for v in costs.values() for s in v['stage_wall'].values())}
    full_development = not pending and set(completed) == {'screen', 'selection', 'internal_evaluation'}
    if full_development:
        marker = json.loads((run/'COMPLETE.json').read_text())
        runner_result = json.loads((run/'results.json').read_text())
        if marker['execution_mode'] != 'gpu' or marker['contract_sha256'] != digest(c) or runner_result['contract_sha256'] != digest(c):
            raise ValueError('Final run completion contract differs')
        if total_cost['primary_pairs'] != 1895 or total_cost['executed_pairs'] != 1944:
            raise ValueError('Full development denominator differs')
        for cohort, ss in summary.items():
            saved = runner_result['summary'][cohort]
            if (ss['n'], ss['correct'], ss['contrast']) != (saved['n'], saved['correct'], saved['method_minus_O']):
                raise ValueError('Independent summary differs from completed runner')
        total_cost['full_run_latest_invocation_wall_seconds'] = marker['latest_invocation_wall_seconds']
        paths += [run/'COMPLETE.json', run/'results.json']
    previous = json.loads((ROOT/'artifacts/e1_stem_full_dev_results_snapshot.json').read_text())
    previous_contract = json.loads((ROOT/'artifacts/e1_stem_full_dev_v1/contract.json').read_text())
    if previous_contract['labels_sha256'] != c['labels_sha256'] or previous_contract['prompt_sha256'] != c['prompt_sha256']:
        raise ValueError('8B comparison dataset/method differs')
    previous_summary = {k: previous['results']['summary']['all_158' if k == 'combined' else k] for k in summary if k != 'combined' or full_development}
    paths += [ROOT/'artifacts/e1_stem_full_dev_results_snapshot.json', ROOT/'artifacts/e1_stem_full_dev_v1/contract.json']
    paths += [Path(__file__)] + [REPO/p for p in c['source_sha256'] if p.endswith('.py') and '/artifacts/' not in p]
    paths = sorted(set(paths))
    manifest = {str(p.relative_to(REPO)): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size} for p in paths}
    archive = ROOT/'artifacts/transfer_qwen3_vl_4b_completed.tar.gz'
    # Include pilot/excluded labels as evaluation-only data to reproduce all archived outputs.
    executed = {r['pair_id'] for cohort in completed for r in read(run/cohort/'inputs.jsonl')}
    with tarfile.open(archive, 'w:gz', compresslevel=6) as tf:
        for path in paths:
            tf.add(path, arcname=str(path.relative_to(REPO)), recursive=False)
        extra = {'MANIFEST.json': json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',
                 'evaluation_labels_completed.jsonl': ''.join(json.dumps(labels[p],ensure_ascii=False)+'\n' for p in sorted(executed))}
        for name, text in extra.items():
            data = text.encode(); info = tarfile.TarInfo(name); info.size = len(data)
            tf.addfile(info,io.BytesIO(data))
    result = {'as_of_utc': datetime.now(timezone.utc).isoformat(), 'development_only': True,
        'completed_cohorts': completed, 'pending_cohorts': pending, 'summary': summary, 'quality': quality, 'costs': costs,
        'total_cost': total_cost, 'prior_8b_summary': previous_summary,
        'config': c['config'], 'prompt_sha256': c['prompt_sha256'], 'contract_sha256': digest(c), 'source_and_raw_sha256': manifest,
        'archive': {'path': str(archive.relative_to(REPO)), 'bytes': archive.stat().st_size, 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()},
        'cost_note': 'Primary logical recipe includes historical fixed-LM extraction and reused call timings; batch time is allocated by rows. Stage wall uses complete executed cohort and excludes imported E1 extraction and parent orchestration. These are amortized seconds/pair, not interactive single-query latency.'}
    snapshot = ROOT/'artifacts/transfer_qwen3_vl_4b_results_snapshot.json'
    snapshot.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    lines = ['# Qwen3-VL-4B: E1/M0 완료 결과', '', '완료 범위: '+', '.join(completed)+'. 미완료: '+(', '.join(pending) or '없음')+'.', '',
             '고정 Qwen3-8B LM과 E1/M0 prompt를 유지하고, inventory·최종 풀이만 4B로 수행했다. Options는 원문 그대로다. 세부 설정과 모든 초기·repair raw 응답은 snapshot 및 압축 원시에 보존했다.', '',
             '| 범위 | 문항 | n | O | Method | 차이 | 95% item bootstrap CI | 회복/회귀 |',
             '| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |']
    for cohort, s in summary.items():
        n=s['n']; x=s['contrast']; a=s['correct']['O']; b=s['correct']['E1_M0']
        lines.append(f'| {cohort} | {s["items"]} | {n} | {a}/{n} ({a/n:.2%}) | {b}/{n} ({b/n:.2%}) | {100*x["difference"]:+.2f}pp | [{100*x["ci95"][0]:+.2f}, {100*x["ci95"][1]:+.2f}] | {x["recovery"]}/{x["regression"]} |')
    overall = summary.get('combined', next(iter(summary.values())))
    ci = overall['contrast']['ci95']
    interpretation = ('합산 차이의 CI는 0보다 높아 이 개발 집합에서 O 대비 양의 차이를 보인다.' if ci[0] > 0 else
                      '합산 차이의 CI는 0보다 낮아 이 개발 집합에서 O 대비 음의 차이를 보인다.' if ci[1] < 0 else
                      '합산 차이의 CI가 0을 포함하므로 개선을 확정하지 않는다.')
    lines += ['', 'Pilot 48쌍과 사전 제외 1쌍은 주 분석에서 제외했다. 처리 실패는 원문 fallback으로 분모에 포함했다. CI는 semantic item 단위 10,000회 bootstrap이다. '+interpretation+' 반복 관찰한 development set의 탐색 결과이며 독립적인 일반화 검증은 아니다.', '',
              '| 범위 | GUI | n | O | Method | 차이 |', '| --- | --- | ---: | ---: | ---: | ---: |']
    for cohort, s in summary.items():
        for gui,g in s['by_gui'].items():
            n=g['n']; a=g['correct']['O']; b=g['correct']['E1_M0']
            lines.append(f'| {cohort} | {gui.upper()} | {n} | {a/n:.2%} | {b/n:.2%} | {100*(b-a)/n:+.2f}pp |')
    lines += ['', '| 범위 | Inventory 성공/전체 main | MCQ 수정 | 원문 fallback | Label 파싱 실패 |', '| --- | ---: | ---: | ---: | ---: |']
    for cohort,q in quality.items():
        lines.append(f'| {cohort} | {q["inventory_main"].get("success",0)}/{sum(q["inventory_main"].values())} | {q["changed"]}/{q["main_pairs"]} | {q["rewrite_status"].get("fallback_original",0)} | {sum(q["invalid_labels"].values())} |')
    lines += ['', '| 범위 | 8B O | 8B E1/M0 | 8B 차이 | 4B O | 4B E1/M0 | 4B 차이 |',
              '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for cohort, old in previous_summary.items():
        ss=summary[cohort]; n=ss['n']
        if old['n'] != n:
            raise ValueError('8B/4B comparison denominator differs')
        a=old['correct']['O_B200']/n; b=old['correct']['E1_M0']/n
        x=ss['correct']['O']/n; y=ss['correct']['E1_M0']/n
        lines.append(f'| {cohort} | {a:.2%} | {b:.2%} | {100*(b-a):+.2f}pp | {x:.2%} | {y:.2%} | {100*(y-x):+.2f}pp |')
    lines += ['', '8B와 4B는 같은 개발 문항·E1/M0·고정 LM을 사용했다. Inventory와 최종 풀이 checkpoint가 모두 달라 이 표는 pipeline 전이 비교다. 각 모델의 O 대비 효과와 모델 간 정확도를 구분한다. 과거 R/T/F·R_stem reference의 모델·장비·batch 차이도 남아 있다.']
    lines += ['', '| 범위 | 주 분석 n | Inventory+추출+정렬+풀이 초 | 초/pair | 실제 신규 method stage wall / 실행pair | 초/pair |', '| --- | ---: | ---: | ---: | ---: | ---: |']
    for cohort,cc in costs.items():
        n=cc['primary_pairs']; e=cc['executed_pairs']; t=cc['primary_logical_recipe']['total_seconds']; w=cc['method_stage_wall_seconds']
        lines.append(f'| {cohort} | {n} | {t:.2f} | {t/n:.3f} | {w:.2f}초 / {e} | {w/e:.3f} |')
    n=total_cost['primary_pairs']; e=total_cost['executed_pairs']; t=combined_recipe['total_seconds']; w=total_cost['method_stage_wall_seconds']
    lines.append(f'| 전체 완료 범위 | {n} | {t:.2f} | {t/n:.3f} | {w:.2f}초 / {e} | {w/e:.3f} |')
    if full_development:
        wall=total_cost['full_run_latest_invocation_wall_seconds']
        lines += ['', f'전체 실행기의 이번 invocation wall은 {wall/60:.2f}분({wall/3600:.2f}시간)이다. O와 method 두 조건, 신규 inventory·정렬·적재·worker 기동을 포함하며 다운로드 및 과거에 완료한 E1 추출은 제외한다. 1,944개 실행pair마다 두 조건을 처리한 운영 시간으로, method 단독 초/pair와 다르다.']
    lines += ['', '첫 비용은 cache hit도 원래 runtime으로 청구하고 과거 고정 LM 추출을 포함한 단독 recipe 계산 구간이다. 모델 적재·일부 CPU 작업은 제외한다. 실제 신규 stage wall은 inventory+정렬+method 풀이이며 O baseline과 재사용 E1 추출은 제외한다. 서로 다른 집계 기준을 나눠 제시했다. 초/pair는 데이터셋 공유·batch를 반영한 상각 처리량이며 단일 질의 latency가 아니다.', '',
              '[고정 프로토콜](QWEN3_VL_4B_TRANSFER_PROTOCOL_KO.md) · [설정·검증·시간 snapshot](../artifacts/transfer_qwen3_vl_4b_results_snapshot.json) · [완료 원시 archive](../artifacts/transfer_qwen3_vl_4b_completed.tar.gz)', '',
              'Archive는 **빈 디렉터리**에 해제한다. 완료 cohort의 입력·inventory·E1 source 추출·M0 치환·O/method 예측·환경·설정·체크섬과 평가 전용 label을 포함한다. 모델 가중치·이미지·진행 중 출력은 포함하지 않는다. 평가 label은 automatic method 입력과 별도 파일이다.', '',
              '재집계: `.venv/bin/python followup_rel_4lang/method_dev/scripts/report_model_transfer_progress.py`. GPU 추론 없이 완료 cohort만 읽는다. 실행 중인 runner·contract·출력·완료 marker는 변경하지 않는다.', '']
    (ROOT/'reports/QWEN3_VL_4B_TRANSFER_RESULTS_KO.md').write_text('\n'.join(lines))
    print(json.dumps({'completed':completed,'pending':pending,'summary':summary,'archive':result['archive']},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',type=Path,default=ROOT/'artifacts/transfer_qwen3_vl_4b_e1m0_all_v1')
    report(p.parse_args().run_dir.resolve())
