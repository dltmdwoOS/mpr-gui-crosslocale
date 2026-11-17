"""Audit completed GPU OCR results, write a Korean report and archive reproducibility files."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tarfile

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / '01_code/src'), str(REPO), str(Path(__file__).parent)]
from run_gpu_ocr_screen import DEFAULT_OUTPUT, BACKENDS, SOLVERS, CPU, BASE4, verify, load, latest
from run_stem_only_gui import read, unique, write
from compare_end_to_end import call_map, call_seconds, batch_share
from mpr_crosslocale.methods.selective_alignment.schemas import digest, fields
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits
from mpr_crosslocale.inference.answer_parser import parse_label

REPORT = ROOT / 'reports/GPU_OCR_SCREEN_RESULTS_KO.md'
SNAPSHOT = ROOT / 'artifacts/gpu_ocr_screen_results_snapshot.json'
ARCHIVE = ROOT / 'artifacts/gpu_ocr_screen_completed.tar.gz'
MANIFEST = ROOT / 'artifacts/gpu_ocr_screen_archive_manifest.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_contrast(left, right, stored):
    recovery = sum(left[p] and not right[p] for p in left)
    regression = sum(right[p] and not left[p] for p in left)
    if stored['recovery'] != recovery or stored['regression'] != regression:
        raise ValueError('Paired transitions differ from stored result')
    if abs(stored['difference'] - (recovery - regression) / len(left)) > 1e-12:
        raise ValueError('Paired difference differs from stored result')


def main():
    output = DEFAULT_OUTPUT
    contracts = {b: verify(output / b) for b in BACKENDS}
    done = load(output / 'COMPLETE.json')
    if done['execution_mode'] != 'gpu' or done['contracts'] != {b: digest(c) for b, c in contracts.items()}:
        raise ValueError('Completed real GPU run required')
    result = load(output / 'results.json')
    if result['pending'] or result['primary_pairs'] != 240 or result['primary_items'] != 20:
        raise ValueError('Incomplete Screen result or changed denominator')
    labels = unique(read(ROOT / 'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl'))
    if digest(labels) != contracts[BACKENDS[0]]['labels_sha256']:
        raise ValueError('Evaluation label lock differs')
    orig = unique(read(output / BACKENDS[0] / 'inputs.jsonl'))
    ids = {p for p in orig if labels[p]['split'] == 'main'}
    if len(orig) != 288 or len(ids) != 240 or len({orig[p]['parallel_id'] for p in ids}) != 20:
        raise ValueError('Screen pair/item coverage differs')
    images = {orig[p]['image_sha256'] for p in ids}
    for row in {r['image_sha256']: r for r in orig.values()}.values():
        if sha(REPO / row['image_path']) != row['image_sha256']:
            raise ValueError('Screenshot bytes differ from input lock')
    stage_wall, shared_recipes, overlaps, inventories = {}, {}, {}, {}
    preds, vectors = {}, {}
    captured, expected = set(), {}
    for backend, c in contracts.items():
        work = output / backend
        if c['execution_mode'] != 'gpu' or load(work / 'COMPLETE.json')['contract_sha256'] != digest(c):
            raise ValueError('Incomplete backend')
        if unique(read(work / 'inputs.jsonl')) != orig:
            raise ValueError('Backend original input differs')
        inv = read(latest(work, 'ocr') / 'inventories.jsonl')
        inventories[backend] = {r['image_sha256']: r for r in inv}
        if len(inv) != 128 or len(inventories[backend]) != 128 or not images <= set(inventories[backend]):
            raise ValueError('Inventory image coverage differs')
        rw = unique(read(latest(work, 'rewrite') / 'rewritten.jsonl'))
        if set(rw) != set(orig):
            raise ValueError('Incomplete rewritten inputs')
        for p in orig:
            if rw[p]['options'] != orig[p]['options'] or apply_edits(orig[p], rw[p]['edits']) != fields(rw[p]):
                raise ValueError('Selective edit scope differs')
        stage_wall[backend], overlaps[backend] = {}, {}
        for solver in SOLVERS:
            stage = 'infer_' + solver
            attempt = latest(work, stage)
            ec = load(attempt / 'evaluation/contract.json')
            if ec['execution_mode'] != 'gpu' or ec['downstream'] != c['solvers'][solver]['downstream']:
                raise ValueError('Solver checkpoint/run contract differs')
            if ec['parent_sha256'] != digest(load(attempt / 'view/contract.json')):
                raise ValueError('Inference input contract linkage differs')
            pp = read(attempt / 'evaluation/predictions.jsonl')
            pred = unique(pp)
            if set(pred) != set(orig):
                raise ValueError('Incomplete solver predictions')
            if any(r['execution_mode'] != 'gpu' or r['condition'] != c['condition'] + '_' + solver
                   or parse_label(r['generated_text']) != r['parsed_generated_label'] for r in pp):
                raise ValueError('Prediction provenance differs')
            correct = {p: int(pred[p]['status'] == 'success' and pred[p]['parsed_generated_label'] == labels[p]['gold_answer']) for p in ids}
            stored = result['models'][solver][backend]
            if sum(correct.values()) != stored['correct']:
                raise ValueError('Accuracy differs from stored result')
            costs = stored['cost']
            recomputed = {'inventory_seconds': sum(inventories[backend][s]['runtime_ms'] for s in images) / 1000,
                          'matching_seconds': call_seconds(call_map([rw[p] for p in ids])),
                          'answer_seconds': batch_share(pp, lambda r: r['pair_id'] in ids)['seconds']}
            if any(abs(costs[k] - value) > 1e-8 for k, value in recomputed.items()):
                raise ValueError('Recorded recipe cost differs')
            if abs(costs['total_seconds'] - sum(costs[k] for k in ('inventory_seconds', 'extraction_seconds', 'matching_seconds', 'answer_seconds'))) > 1e-8:
                raise ValueError('Recipe total differs')
            preds[backend, solver], vectors[backend, solver] = pred, correct
            overlaps[backend][solver] = {'unparsed_primary': sum(pred[p]['parsed_generated_label'] not in ('A', 'B', 'C', 'D') for p in ids)}
            spec = c['solvers'][solver]
            for name, key, old_work in [('CPU', 'CPU_predictions', CPU),
                ('VLM', 'VLM_predictions', ROOT / 'artifacts/stem_refinement_2x2_screen_v1/E1_M0' if solver == '8B' else BASE4 / 'screen')]:
                old_rw = unique(read(latest(old_work, 'rewrite') / 'rewritten.jsonl'))
                old_pred = unique(read(Path(spec[key])))
                same = {p for p in ids if fields(old_rw[p]) == fields(rw[p])}
                overlaps[backend][solver][name] = {'same_MCQs': len(same),
                    'same_MCQs_label_differences': sum(pred[p]['parsed_generated_label'] != old_pred[p]['parsed_generated_label'] for p in same)}
                old_scores = {p: int(old_pred[p]['status'] == 'success' and old_pred[p]['parsed_generated_label'] == labels[p]['gold_answer']) for p in ids}
                checked_contrast(correct, old_scores, stored['contrasts']['EasyOCR_CPU' if name == 'CPU' else 'VLM_inventory'])
            stage_wall[backend][stage] = load(latest(work, stage) / 'evaluation/cost.json')['wall_seconds']
        for stage in ('ocr', 'rewrite'):
            stage_wall[backend][stage] = load(latest(work, stage) / 'cost.json')['wall_seconds']
        stage_wall[backend]['sum_seconds'] = sum(stage_wall[backend].values())
        a, b = (result['models'][s][backend]['cost'] for s in SOLVERS)
        if any(a[k] != b[k] for k in ('inventory_seconds', 'extraction_seconds', 'matching_seconds')):
            raise ValueError('8B/4B preprocessing cost differs')
        shared_recipes[backend] = a['total_seconds'] + b['answer_seconds']
        for name, h in c['source_sha256'].items():
            path = REPO / name
            if path in expected and expected[path] != h:
                raise ValueError('Conflicting frozen dependency')
            expected[path] = h
            captured.add(path)
        captured.update([work / 'contract.json', work / 'COMPLETE.json', work / 'inputs.jsonl'])
        for stage in ('ocr', 'rewrite', 'infer_8B', 'infer_4B'):
            captured.update(p for p in latest(work, stage).rglob('*') if p.is_file())
        smoke = latest(work, 'smoke')
        captured.update(p for p in smoke.iterdir() if p.is_file())
    for solver in SOLVERS:
        checked_contrast(vectors[BACKENDS[1], solver], vectors[BACKENDS[0], solver],
                         result['models'][solver]['ppocrv5_minus_easyocr_cuda'])
    snapshot = {'as_of_utc': datetime.now(timezone.utc).isoformat(), 'completed': True,
                'audit': {'completion_contracts': True, 'frozen_dependencies': True,
                          'pair_and_image_coverage': True, 'deterministic_stem_only_edits': True,
                          'solver_prediction_provenance': True, 'accuracy_and_cost': True},
                'result': result, 'same_question_diagnostics': overlaps,
                'joint_8b_4b_main_recipe_seconds': shared_recipes,
                'executed_288_stage_wall_seconds': stage_wall,
                'all_stage_wall_seconds': sum(x['sum_seconds'] for x in stage_wall.values()),
                'contracts': done['contracts'], 'raw_results_sha256': sha(output / 'results.json')}
    write(SNAPSHOT, snapshot)
    lines = ['# GPU OCR Screen 결과: Qwen3-VL-8B·4B', '',
             '네 조건을 모두 완료했고 입력·이미지·frozen code/weights·편집 범위·예측·시간을 재검증했다. 추가 GPU 추론은 수행하지 않았다.', '',
             'Main 20개 semantic item·240 mismatch pair 기준이다. 기존 batch 구성을 유지한 실제 입력은 조건당 288행이며 pilot 48행은 아래 성능·recipe 비용에서 제외했다. OCR는 backend당 128개 화면을 처리했고 main 비용에는 80개만 청구한다.', '',
             '## 성능과 총 처리 시간', '',
             '| Solver | Inventory | 정답/240 | 정확도 | OCR | 추출+정렬 | 최종 풀이 | 총 시간 | 초/pair |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for solver in SOLVERS:
        group = result['models'][solver]
        for name in ('O', 'VLM_inventory', 'EasyOCR_CPU', *BACKENDS):
            row, cost = group[name], group[name]['cost']
            label = {'VLM_inventory': 'VLM inventory', 'EasyOCR_CPU': 'EasyOCR CPU', 'easyocr_cuda': 'EasyOCR CUDA', 'ppocrv5_cuda': 'PP-OCRv5 GPU'}.get(name, name)
            lines.append(f"| {solver} | {label} | {row['correct']} | {row['accuracy']:.2%} | {cost['inventory_seconds']/60:.2f}분 | {(cost['extraction_seconds']+cost['matching_seconds'])/60:.2f}분 | {cost['answer_seconds']/60:.2f}분 | {cost['total_seconds']/60:.2f}분 | {cost['seconds_per_pair']:.3f} |")
    lines += ['', '**속도 개선은 크고, GPU OCR끼리의 정확도 차이는 작다.** CPU OCR의 main 80화면 894.92초가 EasyOCR CUDA 31.03초, PP-OCRv5 8.86초로 줄었다. OCR 단계만 보면 각각 약 28.8배·101.0배이며 PP-OCRv5는 EasyOCR CUDA보다 약 3.50배 빠르다. LM 정렬·최종 풀이가 남아 총시간은 두 GPU 방법 모두 약 10분이다.', '',
              '8B에서는 PP-OCRv5가 EasyOCR CUDA보다 정답 1개 많고 4B에서는 같다. CPU EasyOCR 대비 두 GPU 방법 모두 정답 수가 소폭 늘었지만, 별도 문자 인식 GT를 검수하지 않아 OCR 자체의 인식 정확도 우위를 뜻하지 않는다. 4B에서는 두 GPU 방법 모두 VLM inventory보다 4개 적다.', '',
              '시간은 OCR+기존 E1 추출+M0 정렬+VLM 풀이의 호출 구간 합이다. 캐시로 재사용한 추출·풀이도 원래 시간을 포함하고 batch 시간은 main 비율로 한 번만 배분한다. 모델 적재·기동·다운로드는 제외한다. 모든 비용을 이 서버의 Screen 측정치로 비교했으며 전체 158문항의 GPU OCR 속도는 측정하지 않았다.', '',
              '## 정확도 차이와 불확실성', '',
              '| Solver | 비교 | 차이 | Semantic-item bootstrap 95% CI | 회복/회귀 |',
              '| --- | --- | ---: | --- | ---: |']
    for solver in SOLVERS:
        group = result['models'][solver]
        contrasts = [(b + ' − ' + base, c) for b in BACKENDS for base, c in group[b]['contrasts'].items()]
        contrasts += [('PP-OCRv5 − EasyOCR CUDA', group['ppocrv5_minus_easyocr_cuda'])]
        for label, v in contrasts:
            lines.append(f"| {solver} | {label} | {v['difference']*100:+.2f}pp | [{v['ci95'][0]*100:+.2f}, {v['ci95'][1]*100:+.2f}]pp | {v['recovery']}/{v['regression']} |")
    lines += ['', '8B의 O 대비 CI는 양수지만 이미 반복 관찰한 개발 Screen의 탐색 결과다. PP-OCRv5와 EasyOCR CUDA 간 차이 및 각 방법의 VLM inventory 대비 차이는 CI가 0을 포함한다. 동등성·비열등성·전체 집합 우월성을 검증한 것은 아니다.', '',
              '## 언어별 정답 수', '', '| Solver | Inventory | EN /60 | ZH /60 | TH /60 | RU /60 |', '| --- | --- | ---: | ---: | ---: | ---: |']
    for solver in SOLVERS:
        for b in BACKENDS:
            g = result['models'][solver][b]['by_gui']
            lines.append('| ' + ' | '.join([solver, b] + [str(g[l]['correct']) for l in ('en', 'zh', 'th', 'ru')]) + ' |')
    lines += ['', '4B에서는 PP-OCRv5가 EasyOCR CUDA 대비 TH에서 +3개, ZH에서 −1개, RU에서 −2개로 전체 정답 수가 같다. 언어당 60 pair도 같은 20문항의 반복 관측이므로 언어별 일반 특성으로 해석하지 않는다.', '',
              '## 품질과 실제 신규 실행 비용', '',
              '두 backend 모두 128/128 화면을 전사했고 main 80개에서도 실패·빈 목록이 없었다. Main 240쌍 중 실제 stem 변경은 각각 231쌍이다. EasyOCR CUDA는 fallback 6쌍·유효한 무편집 3쌍, PP-OCRv5는 fallback 8쌍·무편집 1쌍이었다. 정렬 fallback을 분모에 포함했고 네 조건의 최종 label 미파싱은 모두 0이다.', '',
              'CPU OCR와 완성 MCQ가 같았던 것은 EasyOCR CUDA 236/240쌍, PP-OCRv5 197/240쌍이다. 이 동일 MCQ 부분집합에서는 각 solver의 CPU 대비 예측 label 차이가 0이었다. EasyOCR의 CPU/CUDA 전환도 완전히 같은 전사·질문을 보장하는 변경은 아니다.', '',
              '| Inventory | OCR wall | 정렬 wall | 8B wall | 4B wall | 합계 wall |', '| --- | ---: | ---: | ---: | ---: | ---: |']
    for b, w in stage_wall.items():
        lines.append(f"| {b} | {w['ocr']/60:.2f}분 | {w['rewrite']/60:.2f}분 | {w['infer_8B']/60:.2f}분 | {w['infer_4B']/60:.2f}분 | {w['sum_seconds']/60:.2f}분 |")
    lines += ['', f"실제 288행 실행의 stage wall 합은 **{snapshot['all_stage_wall_seconds']/60:.2f}분**이다. 기존 E1 추출을 재사용했고, EasyOCR CUDA는 solver별 96 batch 중 92개, PP-OCRv5는 64개를 재사용했다. 이 합은 새로 실행한 stage의 적재·I/O 등을 포함하지만 parent 기동·단계 사이 보고서 작성은 제외하며, main 240쌍을 처음부터 처리하는 위 recipe 시간과 다르다.", '',
              f"두 solver를 함께 사용할 때 main 전처리를 한 번만 청구한 joint recipe는 EasyOCR CUDA **{shared_recipes[BACKENDS[0]]/60:.2f}분**, PP-OCRv5 **{shared_recipes[BACKENDS[1]]/60:.2f}분**이다. 단독 solver 표의 총시간을 두 번 더하면 공유 전처리가 중복된다.", '',
              '## 설정과 다음 판단', '',
              '기존 E1 stem-only 추출 결과와 고정 Qwen3-8B M0 matcher를 유지하고 inventory 공급원만 바꿨다. Options는 원본 그대로다. VLM은 BF16·SDPA·2MP·batch 3·seed 42·greedy 2 tokens로 유지했고 8B/4B에 같은 수정 MCQ를 제공했다.', '',
              'EasyOCR 1.7.2 CUDA와 PP-OCRv5 mobile detector/언어별 mobile recognizer를 비교했다. PP-OCRv5는 RapidOCR 3.10.0 전후처리와 Paddle Inference 3.3.0 CUDA13을 사용한다. 해상도·분할 단위·전후처리 차이도 포함된 backend 비교다. ONNX Runtime 경로는 B200 커널 호환성 문제로 제외했다.', '',
              '**현재 선택은 속도와 두 solver의 결과를 함께 보면 PP-OCRv5가 유망하다.** 다만 GPU OCR의 Selection/Internal은 아직 수행하지 않았다. 다음 검증은 Screen 정확도 우위를 전제하지 않고 고정 설정 그대로 더 넓은 집합에서 측정하는 것이다. 기존 CPU OCR 전체 1,895쌍 결과와 이번 GPU OCR Screen 240쌍을 구분한다.', '',
              '[실행·설정 안내](GPU_OCR_SCREEN_RUNBOOK_KO.md) · [완료 결과 snapshot](../artifacts/gpu_ocr_screen_results_snapshot.json) · [원시 결과 archive](../artifacts/gpu_ocr_screen_completed.tar.gz) · [SHA manifest와 복원 범위](../artifacts/gpu_ocr_screen_archive_manifest.json)', '']
    REPORT.write_text('\n'.join(lines))
    captured.update([Path(__file__), REPORT, SNAPSHOT, output / 'COMPLETE.json', output / 'results.json', output / 'REPORT_KO.md',
                     ROOT / 'reports/GPU_OCR_SCREEN_RUNBOOK_KO.md', ROOT / 'artifacts/gpu_ocr_screen_readiness.json',
                     ROOT / 'tests/test_gpu_ocr_inventory.py'])
    # Include the baseline preprocessing used by this final audit, not just its predictions.
    for folder, stage, names in [(CPU, 'ocr', ('inventories.jsonl', 'cost.json', 'COMPLETE')),
                                 (CPU, 'rewrite', ('rewritten.jsonl', 'cost.json', 'COMPLETE')),
                                 (BASE4 / 'screen', 'rewrite', ('rewritten.jsonl', 'cost.json', 'COMPLETE'))]:
        captured.update(latest(folder, stage) / name for name in names)
    entries = {}
    for path in sorted(captured):
        if not path.resolve().is_relative_to(REPO) or 'PRIVATE' in str(path):
            raise ValueError('Private/outside file cannot enter archive')
        if path.suffix.lower() in ('.pth', '.safetensors', '.onnx', '.pdiparams', '.png', '.jpg', '.jpeg', '.pyc'):
            raise ValueError('Models/screenshots/bytecode cannot enter archive')
        h = sha(path)
        if path in expected and expected[path] != h:
            raise ValueError('Frozen source changed before archive')
        entries[str(path.relative_to(REPO))] = {'bytes': path.stat().st_size, 'sha256': h}
    with tarfile.open(ARCHIVE, 'w:gz', compresslevel=6, dereference=True) as archive:
        for name in entries:
            archive.add(REPO / name, arcname=name, recursive=False)
    with tarfile.open(ARCHIVE, 'r:gz') as archive:
        if set(archive.getnames()) != set(entries):
            raise ValueError('Archive coverage differs')
        for member in archive:
            if hashlib.sha256(archive.extractfile(member).read()).hexdigest() != entries[member.name]['sha256']:
                raise ValueError('Archive checksum differs')
    write(MANIFEST, {'as_of_utc': snapshot['as_of_utc'], 'archive': str(ARCHIVE.relative_to(REPO)),
          'bytes': ARCHIVE.stat().st_size, 'sha256': sha(ARCHIVE), 'files': entries,
          'scope': 'Completed two GPU OCR inventories, raw matcher responses/rewrites, 8B/4B predictions, '
                   'contracts, costs, environment, smoke summaries, reports and frozen repository dependencies. '
                   'No weights, screenshots, private label file, incomplete/mock attempts, redundant caches or large profiler traces.',
          'restore': 'Extract from repository root in a clean checkout; paths are overwritten. '
                     'Use dataset/model locks and runbook to restore images, checkpoints and OCR weights. '
                     'Historical contracts contain lab-specific absolute paths; archive does not include private evaluation labels.'})
    print('AUDITED four completed conditions; ARCHIVED', len(entries), 'files;', ARCHIVE.stat().st_size, 'bytes')
    print('REPORT', REPORT)


if __name__ == '__main__':
    main()
