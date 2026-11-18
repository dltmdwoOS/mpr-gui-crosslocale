"""Korean Markdown presentation of audited full-development GPU OCR results."""

NAMES = {'O': 'O', 'VLM_inventory': 'VLM inventory', 'EasyOCR_CPU': 'EasyOCR CPU',
         'easyocr_cuda': 'EasyOCR CUDA', 'ppocrv5_cuda': 'PP-OCRv5 GPU'}
COHORTS = ('screen', 'selection', 'internal_evaluation')
BACKENDS = ('easyocr_cuda', 'ppocrv5_cuda')


def render_summary(result, audit):
    pooled = result['summary']['all_158']
    lines = ['# GPU OCR 전체 개발 결과: Qwen3-VL-8B·4B', '',
        '**두 GPU OCR × 두 solver의 Screen·Selection·Internal 평가가 모두 완료됐다.** PP-OCRv5의 점추정 정확도는 8B 74.93%, 4B 73.09%로 이번 inventory 조건 중 가장 높았고, 총 recipe 시간은 67.07분·65.02분이다. 기존 VLM inventory 대비 시간은 크게 줄었지만 정확도 우위의 CI는 0을 포함한다.', '',
        '158개 main semantic item·1,895 mismatch pair가 주 분석이다. 조건당 실제 입력은 1,944행이며 Screen pilot 48행과 Selection 사전 제외 1행을 분석·비용에서 제외했다. 실패·fallback·미파싱을 삭제하지 않았다. 기존 Screen을 재사용하고 Selection/Internal만 추가 실행했으며, 결과 정리 과정에서 GPU 추론을 추가하지 않았다.', '',
        '## 정확도와 총 시간', '',
        '| Solver | Inventory | 정답/1,895 | 정확도 | 총 recipe | 초/pair |',
        '| --- | --- | ---: | ---: | ---: | ---: |']
    for solver in ('8B', '4B'):
        for name, row in pooled[solver]['methods'].items():
            cost = row['cost']
            lines.append(f"| {solver} | {NAMES[name]} | {row['correct']} | {row['accuracy']:.2%} | {cost['total_seconds']/60:.2f}분 | {cost['seconds_per_pair']:.3f} |")
    lines += ['', 'EasyOCR CUDA는 VLM inventory 대비 8B +1개, 4B −1개로 정답 수가 비슷했다. PP-OCRv5는 각각 +16개·+7개였다. GPU OCR 두 방법 사이에서는 PP-OCRv5가 +15개·+8개지만 차이의 불확실성이 남는다.', '',
        '시간은 OCR + 기존 E1 referent 추출 + M0 이름 정렬 + 최종 VLM 풀이의 호출 구간 합이다. 재사용한 단계도 원래 측정 시간을 청구하며, 공유 cache key는 한 번만 세고 batch 시간은 main 비율로 배분한다. 모델 적재·기동·다운로드는 제외한다. 각 solver를 단독 사용하는 recipe를 비교하므로 공통 전처리가 각 행에 포함된다.', '',
        '## 정확도 차이: paired 비교', '',
        '| Solver | 비교 | 차이 | Item bootstrap 95% CI | 회복/회귀 |',
        '| --- | --- | ---: | --- | ---: |']
    for solver in ('8B', '4B'):
        group = pooled[solver]
        comparisons = [('EasyOCR CUDA − VLM', group['methods']['easyocr_cuda']['contrasts']['VLM_inventory'])]
        comparisons += [('PP-OCRv5 − ' + NAMES[base], contrast) for base, contrast in group['methods']['ppocrv5_cuda']['contrasts'].items()]
        comparisons += [('PP-OCRv5 − EasyOCR CUDA', group['ppocrv5_minus_easyocr_cuda'])]
        for label, c in comparisons:
            lines.append(f"| {solver} | {label} | {100*c['difference']:+.2f}pp | [{100*c['ci95'][0]:+.2f}, {100*c['ci95'][1]:+.2f}]pp | {c['recovery']}/{c['regression']} |")
    lines += ['', 'Semantic-item bootstrap 10,000회다. PP-OCRv5−VLM과 PP-OCRv5−EasyOCR CUDA는 두 solver 모두 CI가 0을 포함한다. 8B PP−CPU의 구간도 하한이 0이므로 이 비교만으로 확정적 우월성을 주장하지 않는다. 이미 반복 관찰한 개발 집합의 탐색 결과이며, 동등성·비열등성이나 독립 일반화 검증도 아니다.', '',
        '## 집합별 결과', '', '| 집합 | n | Solver | VLM inventory | CPU OCR | CUDA EasyOCR | PP-OCRv5 |',
        '| --- | ---: | --- | ---: | ---: | ---: | ---: |']
    for cohort in COHORTS:
        for solver, s in result['summary'][cohort].items():
            lines.append('| ' + ' | '.join([cohort, str(s['n']), solver] + [f"{s['methods'][m]['correct']}/{s['n']} ({s['methods'][m]['accuracy']:.2%})" for m in ('VLM_inventory', 'EasyOCR_CPU', *BACKENDS)]) + ' |')
    lines += ['', '4B의 Selection에서는 EasyOCR CUDA 185개, PP-OCRv5 183개로 PP가 2개 적다. Internal에서는 1,015→1,025개로 10개 많았다. 모든 집합에서 같은 방향의 차이가 난 것은 아니다.', '',
        '## GUI 언어별', '', '| Solver | GUI | n | VLM inventory | EasyOCR CUDA | PP-OCRv5 | PP−VLM |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for solver, group in pooled.items():
        for g in ('en', 'zh', 'th', 'ru'):
            rows = [group['methods'][m]['by_gui'][g] for m in ('VLM_inventory', *BACKENDS)]
            n = rows[0]['n']
            lines.append('| ' + ' | '.join([solver, g.upper(), str(n)] + [f"{r['correct']}/{n} ({r['correct']/n:.2%})" for r in rows] + [f"{100*(rows[2]['correct']-rows[0]['correct'])/n:+.2f}pp"]) + ' |')
    lines += ['', '8B PP−VLM의 순증가 16개 중 TH GUI가 12개다. 4B는 ZH +8개·TH +6개를 얻었지만 RU에서 7개 잃었다. 태국어 GUI의 절대 성능은 여전히 낮으며, 전체 평균 개선이 모든 GUI 언어에 균일하게 적용되지는 않는다. 이 결과로 언어별 on/off 정책을 새로 만들지는 않았다.', '',
        '## 속도 개선과 남은 병목', '',
        '| 공통 inventory 방법 | OCR | E1 추출 | M0 정렬 | 8B 풀이 | 4B 풀이 |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for m in ('EasyOCR_CPU', *BACKENDS):
        a, b = (pooled[s]['methods'][m]['cost'] for s in ('8B', '4B'))
        lines.append('| ' + ' | '.join([NAMES[m]] + [f'{v/60:.2f}분' for v in (a['inventory_seconds'], a['extraction_seconds'], a['matching_seconds'], a['answer_seconds'], b['answer_seconds'])]) + ' |')
    easy = pooled['8B']['methods']['easyocr_cuda']['cost']
    pp = pooled['8B']['methods']['ppocrv5_cuda']['cost']
    cpu = pooled['8B']['methods']['EasyOCR_CPU']['cost']
    lines += ['', f"Main 632화면의 OCR 시간은 CPU {cpu['inventory_seconds']/60:.2f}분 → EasyOCR CUDA {easy['inventory_seconds']/60:.2f}분 → PP-OCRv5 {pp['inventory_seconds']/60:.2f}분이다. PP는 OCR 단계에서 CPU 대비 약 {cpu['inventory_seconds']/pp['inventory_seconds']:.1f}배, CUDA EasyOCR 대비 {easy['inventory_seconds']/pp['inventory_seconds']:.2f}배 빠르다.", '']
    for solver, group in pooled.items():
        total = group['methods']['ppocrv5_cuda']['cost']['total_seconds']
        before = group['methods']['VLM_inventory']['cost']['total_seconds']
        lines.append(f"- {solver}: PP 총시간은 VLM inventory 대비 {100*(1-total/before):.1f}% 감소했다.")
    lines += ['', f"PP의 8B recipe에서 OCR는 {100*pp['inventory_seconds']/pp['total_seconds']:.1f}%다. 이제 비용의 큰 부분은 E1 추출 {pp['extraction_seconds']/60:.2f}분·M0 정렬 {pp['matching_seconds']/60:.2f}분과 VLM 풀이 {pp['answer_seconds']/60:.2f}분이다. OCR를 더 빠르게 하는 것만으로 얻을 수 있는 총시간 절감은 작다.", '',
        '## 실제 새로 실행한 시간과 품질', '',
        '| 추가 집합 | OCR | Stage wall 합 | 8B 새 batch/전체 | 4B 새 batch/전체 |',
        '| --- | --- | ---: | ---: | ---: |']
    for cohort in COHORTS[1:]:
        for b in BACKENDS:
            q8, q4 = (result['quality'][cohort][b + '/' + s]['inference_stage_all_rows'] for s in ('8B', '4B'))
            cells = [cohort, NAMES[b], f"{audit['stage_wall_seconds'][cohort][b]['total_seconds']/60:.2f}분"]
            cells += [f"{q['new_batches']}/{q['new_batches']+q['reused_batches']}" for q in (q8, q4)]
            lines.append('| ' + ' | '.join(cells) + ' |')
    lines += ['', f"이번 Selection/Internal의 stage wall 합은 {audit['extension_stage_wall_seconds']/60:.2f}분이다.",
        '이는 두 OCR·두 solver를 모두 실행하면서 캐시로 절약한 실제 신규 stage 시간이며, 위의 main 단독 recipe와 다르다. Stage 안의 적재·I/O는 포함하지만 단계 사이 보고서 작성·parent 기동은 제외한다. PP는 재사용 가능한 LM 응답·풀이 batch가 더 적어 이번 추가 실행의 wall 합은 EasyOCR보다 길었다. 이를 PP의 cold recipe가 더 느리다는 뜻으로 읽으면 안 된다.', '',
        f"한 OCR의 전처리를 공유해 8B+4B를 함께 쓸 때의 main joint recipe는 EasyOCR CUDA {audit['joint_8b_4b_recipe_seconds']['easyocr_cuda']/60:.2f}분, PP-OCRv5 {audit['joint_8b_4b_recipe_seconds']['ppocrv5_cuda']/60:.2f}분이다.", '']
    for b in BACKENDS:
        qs = [result['quality'][cohort][b + '/8B'] for cohort in COHORTS]
        statuses = {k: sum(q['rewrite_status'].get(k, 0) for q in qs) for k in ('success', 'fallback_original', 'no_op_no_edits')}
        lines.append(f"- {NAMES[b]}: main 632화면 전사 성공. Stem 변경 {sum(q['changed_pairs'] for q in qs)}쌍, 원문 fallback {statuses['fallback_original']}쌍, 유효한 무편집 {statuses['no_op_no_edits']}쌍. 최종 미파싱은 8B·4B 모두 0이다.")
    same = {b: {s: {k: sum(audit['same_question_diagnostics'][cohort][b][s]['EasyOCR_CPU'][k] for cohort in COHORTS)
                    for k in ('same_MCQs', 'same_MCQs_label_differences')} for s in ('8B', '4B')} for b in BACKENDS}
    lines += ['', f"CPU OCR와 완성 MCQ가 같은 경우는 EasyOCR CUDA {same['easyocr_cuda']['8B']['same_MCQs']}/1,895쌍, PP-OCRv5 {same['ppocrv5_cuda']['8B']['same_MCQs']}/1,895쌍이었다. 동일 MCQ에서도 CPU 대비 label 변화가 8B에서 각각 {same['easyocr_cuda']['8B']['same_MCQs_label_differences']}/{same['ppocrv5_cuda']['8B']['same_MCQs_label_differences']}개, 4B에서 {same['easyocr_cuda']['4B']['same_MCQs_label_differences']}/{same['ppocrv5_cuda']['4B']['same_MCQs_label_differences']}개 있었다. Batch 구성·수치 변동의 영향이 남으므로 정오 변화 전체를 OCR 문자열 차이에만 귀속하지 않는다.", '',
        'OCR의 bbox/text/confidence는 보존했지만 문자 인식 GT를 별도 검수한 실험은 아니다. 별도 OCR accuracy와 REL accuracy를 구분한다. 12개 실행 queue의 이미지·질문·정답·rendered prompt hash와 7,776개 예측 행을 검증했으며, 상세 기록은 snapshot에 보존했다.', '',
        '## 재현과 현재 판단', '',
        'E1 stem-only 추출과 고정 Qwen3-8B M0는 유지했다. Options는 원본 그대로이며 8B/4B는 같은 OCR·LM 수정 질문을 공유한다. 최종 VLM은 BF16·SDPA·2MP·batch3·seed42·greedy2tokens다. EasyOCR 1.7.2 CUDA와 RapidOCR 3.10.0 + Paddle Inference 3.3.0 CUDA13의 PP-OCRv5 mobile 및 언어별 인식기를 사용했다. Detector 해상도·문자열 단위·전후처리 차이도 포함한 backend 비교다.', '',
        '**PP-OCRv5는 다음 단계의 실용적인 inventory 후보가 됐다.** 이번 inventory 조건 중 두 solver 모두 가장 높은 점추정과 가장 짧은 recipe를 보였지만, 정확도 우위를 확정하지는 않는다. 전체 366문항·추가 모델 일반화는 이번 실행 범위가 아니다.', '',
        '[전체 표·모든 대비·언어별 수치](GPU_OCR_FULL_DEV_TABLES_KO.md) · [실행 안내](GPU_OCR_FULL_DEV_RUNBOOK_KO.md) · [검증 snapshot](../artifacts/gpu_ocr_full_dev_results_snapshot.json) · [완료 raw archive](../artifacts/gpu_ocr_full_dev_completed.tar.gz) · [SHA manifest·복원 범위](../artifacts/gpu_ocr_full_dev_archive_manifest.json)', '']
    return '\n'.join(lines)
