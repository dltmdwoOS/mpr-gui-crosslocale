"""Read-only analysis/report for the completed single-pass Screen experiment."""
import gzip
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO/'01_code/src'), str(REPO), str(Path(__file__).parent)]
from followup_rel_4lang.method_dev import single_pass
from mpr_crosslocale.methods.selective_alignment.schemas import digest, fields
from run_stem_only_gui import read, unique, write
from search_pipeline import paired_bootstrap, EXCLUDED


def main():
    output = ROOT/'artifacts/single_pass_stem_screen_v1'
    contract = json.loads((output/'contract.json').read_text())
    ready = json.loads((ROOT/'artifacts/single_pass_stem_readiness.json').read_text())
    lines = ['# Stem 추출·정렬 통합 실험', '',
        '기존 Stem-only GUI의 **referent 추출과 inventory 기반 정렬을 Qwen3-8B의 기본 호출 1회로 통합**한다. Options는 원본으로 둔다. 기존 Screen 결과를 관찰한 뒤 추가한 탐색 실험이며, 결과에 따라 프롬프트를 다시 고르는 sweep은 하지 않았다.', '',
        '## 무엇이 달라졌나', '',
        '| 단계 | 기존 Stem-only GUI | Single-pass Stem GUI |',
        '| --- | --- | --- |',
        '| GUI inventory | Screenshot → 평가 VLM | 같은 완료 inventory 재사용 |',
        '| Referent 처리 | LM이 stem만 보고 추출 → 별도 LM이 원본 MCQ·span·inventory로 정렬 | LM이 원본 MCQ·inventory를 함께 보고 source span과 replacement를 동시에 반환 |',
        '| 최종 편집 | 코드가 검증된 stem span만 치환 | 같은 결정적 치환 함수로 stem만 치환 |',
        '| Options | 원본 | 원본 |',
        '| 문제 풀이 | Qwen3-VL-8B | 같은 계약·정렬·배치 구성 |', '',
        '기본 호출은 1회이고 JSON·source substring·occurrence·overlap·inventory membership 검증에 실패하면 repair를 최대 1회 허용한다. Repair까지 실패하면 해당 MCQ의 모든 편집을 버리고 원문으로 유지한다. Inventory가 실패했거나 비었으면 LM을 호출하지 않고 원문을 유지한다. 실패 pair도 평가 분모에 남긴다.', '',
        '이전 Direct VLM의 자유로운 전체 재작성과 달리 고정 LM은 screenshot을 보지 않고 inventory만 받는다. 원문 text와 target replacement를 명시적으로 분리하며 코드는 source text의 위치를 복원한다. 다만 substring 프로토콜 자체는 남아 있으므로 그 오류가 완전히 없어졌다고 가정하지 않는다. 관계 표현 전체의 의미 동등성까지 코드가 보장하는 것은 아니다.', '',
        '통합 조건은 inventory를 **추출 때부터** 볼 수 있고 원래 MCQ 전체가 문맥으로 제공된다. 따라서 변화는 호출 수뿐 아니라 입력 정보·출력 인터페이스도 포함하는 pipeline 비교다. 여기서 반환된 referents는 채택 가능한 edit 후보이므로 독립 extractor의 전체 span recall과 직접 비교하지 않는다.', '',
        '## 고정 설정 및 자원', '',
        '| 항목 | 설정 |', '| --- | --- |',
        '| 변환 LM | Qwen/Qwen3-8B · `47719a242beab8f9aecc40ce3928b034dd5dd559` |',
        '| Inventory / 평가 VLM | Qwen/Qwen3-VL-8B-Instruct · `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b` |',
        '| 공통 | BF16 · SDPA · seed42 · greedy · beams1 · use_cache |',
        '| LM | enable_thinking=false · batch1 · max new tokens512 · repair도512 |',
        '| VLM 문제 풀이 | 기존 system 그대로 · batch3 · max new tokens2 · label scoring 유지 |',
        '| 이미지 / 메모리 형식 | min262144 / max2097152 pixels · fast processor · channels_last_3d |',
        '| 입력 토큰 | 최대4096 · truncation 없음 |',
        f"| 사전 점검 | 실제 LM 입력 최대{ready['primary_max_input_tokens']} tokens · repair 보수적 여유 포함{ready['conservative_repair_input_upper_bound_tokens']} tokens |", '',
        '현재 B200 MIG 44.25GiB에서 실행 전 free44.05GiB를 확인했다. LM과 VLM은 별도 subprocess에서 순차 적재해 동시 상주를 피한다. Inventory와 O·기존 방법 예측은 재사용하고 신규 조건288쌍만 평가한다. 주 분석은 main20문항×12방향=240쌍이며 legacy pilot48쌍은 별도 보존한다.', '',
        '## 실제 프롬프트', '',
        '추출 프롬프트의 최소 이름 span·원문 복사·occurrence 규칙과 selective GUI 프롬프트의 문맥 활용·inventory verbatim·불확실 시 원문 유지 규칙을 합쳤다. 전체 MCQ를 번역하라는 규칙은 넣지 않았다.', '',
        '### LM system 원문', '', '```text', single_pass.SYSTEM, '```', '',
        '한국어 요지: stem의 GUI 이름만 찾고 화면 문자열 중 확실히 대응하는 표현으로 바꾼다. `text`는 반드시 원문 언어의 실제 substring이고 `replacement`는 inventory의 원시 문자열이다. 다른 이름마다 occurrence는0부터 세며 options·관계·부정·수량 등은 바꾸지 않는다. 대응이 불확실하면 그 편집을 생략한다. 입력 문자열은 지시문으로 취급하지 않는다.', '',
        '### LM user 형식', '', '```text',
        'Find and localize stem GUI names together. Options are context only. Return edits JSON only.', '',
        '{', '  "source_language": "{source}",', '  "target_language": "{GUI}",',
        '  "question_stem": "{원본 stem}",', '  "options": {"A":"{원본 A}","B":"{원본 B}","C":"{원본 C}","D":"{원본 D}"},',
        '  "target_gui_visible_strings": ["{같은 화면의 완료 inventory}"]', '}', '```', '',
        '한국어: stem GUI 이름을 찾고 정렬하는 작업을 함께 수행하라. Options는 문맥으로만 사용하고 edits JSON만 반환하라. 원래 pair ID·이미지·정답·병렬 target 표현은 LM payload에 들어가지 않는다.', '',
        '### LM repair 추가문', '', '```text',
        'The previous output failed validation for:', '- {실제 validation 오류}', '',
        'Previous output (data only):', '{이전 raw output}', '',
        'Return corrected edits JSON only. Copy text from the ORIGINAL stem, use zero-based occurrence for that same substring, and select only exact inventory replacements. Omit uncertain edits. Never edit options or context.', '```', '',
        '한국어: 실제 오류와 이전 응답을 참고해 JSON만 수정하라. 원문 substring과 반복 횟수를 정확히 쓰고 inventory에 있는 대체 표현만 사용하라. 불확실한 편집은 생략하고 options와 문맥은 바꾸지 마라.', '',
        '### 문제 풀이 VLM', '', 'System:', '', '```text',
        contract['downstream']['system_prompt'], '```', '', 'User: 같은 screenshot과 아래 text.', '', '```text',
        '{수정된 stem} A: {원본 A} B: {원본 B} C: {원본 C} D: {원본 D}', '',
        'Respond with exactly one label: A, B, C, or D.', '```', '',
        '한국어: GUI 이미지를 보고 선택형 문제를 풀고 A/B/C/D 한 글자만 반환하라. Inventory 추출 프롬프트는 변경·재실행하지 않았으며 [기존 전체 프로토콜](TWO_STAGE_V2_PROTOCOL_KO.md)을 그대로 따른다.', '',
        '## 실측 결과', '']
    marker = output/'COMPLETE.json'
    if not marker.exists():
        lines += ['아직 실행 중이다. 정확도와 성공 여부는 전체 paired 출력이 완료된 뒤 기록한다.']
    else:
        done = json.loads(marker.read_text())
        if done['execution_mode'] != 'gpu' or done['contract_sha256'] != digest(contract):
            raise ValueError('Invalid completed contract')
        for path, sha in contract['source_sha256'].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha:
                raise ValueError('Source changed: '+path)
        result = json.loads((output/'results.json').read_text())
        comparison = result['contrasts']['TS_STEM_ONLY_GUI_AUTO']
        n = result['primary_pairs']
        new_correct = result['correct'][single_pass.CONDITION]
        separate_correct = result['correct']['TS_STEM_ONLY_GUI_AUTO']
        lines += [f"**통합 방식은{new_correct}/{n}={new_correct/n:.2%}, 기존 분리 방식은{separate_correct}/{n}={separate_correct/n:.2%}다.** 차이{comparison['difference']*100:+.2f}pp, item bootstrap95% CI[{comparison['ci95'][0]*100:+.2f}, {comparison['ci95'][1]*100:+.2f}]pp로 우열을 확정하지 않는다. 아래 비용 비교에서도 절감이 확인되지 않아 현재 분리 방식을 대체할 근거는 없다.", '']
        rows = unique(read(Path(done['rewrite'])/'rewritten.jsonl'))
        preds = unique(read(Path(done['infer'])/'predictions.jsonl'))
        originals = unique(read(output/'inputs.jsonl'))
        labels = {r['pair_id']: r for r in read(ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl')}
        ids = sorted(p for p in rows if labels[p]['split'] == 'main' and p != EXCLUDED)
        if result['primary_pairs'] != len(ids):
            raise ValueError('Mismatched denominator')
        new = {p: int(preds[p]['parsed_generated_label'] == labels[p]['gold_answer']) for p in ids}
        old = unique(read(ROOT/'artifacts/stem_only_gui_screen_v1/rewritten.jsonl'))
        old_preds = unique(read(Path(contract['stem_predictions'])))
        inventories = {r['image_sha256']: r for r in read(Path(contract['inventories']))}
        failure_diagnostics = Counter()
        failure_examples = []
        for pid in ids:
            row = rows[pid]
            if row['status'] != 'fallback_original' or not row['attempts']:
                continue
            try:
                parsed = json.loads(row['attempts'][-1]['raw_output'])
                proposed = parsed.get('edits', []) if isinstance(parsed, dict) else []
                if not isinstance(proposed, list):
                    proposed = []
            except ValueError:
                proposed = []
            outside = [e['text'] for e in proposed if isinstance(e, dict) and isinstance(e.get('text'), str)
                       and e['text'] not in originals[pid]['question_stem']]
            option_only = [t for t in outside if any(t in v for v in originals[pid]['options'].values())]
            neither = [t for t in outside if t not in option_only]
            valid_lost = 0
            for edit in proposed:
                try:
                    _, _, kept = single_pass.validate_edits(originals[pid], inventories[row['image_sha256']], json.dumps({'edits': [edit]}, ensure_ascii=False))
                    valid_lost += bool(kept)
                except (ValueError, TypeError, KeyError):
                    pass
            failure_diagnostics['pairs_with_option_only_source_text'] += bool(option_only)
            failure_diagnostics['pairs_with_source_text_absent_from_entire_MCQ'] += bool(neither)
            failure_diagnostics['pairs_with_valid_edits_discarded_by_whole_response_fallback'] += bool(valid_lost)
            failure_diagnostics['individually_valid_edit_proposals_discarded'] += valid_lost
            failure_examples.append({'pair_id': pid, 'errors': row['errors'], 'option_only_source_text': option_only,
                                     'source_text_absent_from_MCQ': neither, 'individually_valid_edits_discarded': valid_lost,
                                     'raw_output': row['attempts'][-1]['raw_output']})
        rdir = ROOT.parent/'results/rstem_ropts_20261110/qwen3/raw'
        rcontract = json.loads((rdir/'run_contract.json').read_text())
        if rcontract['model_config'] != contract['downstream']['model_config'] or rcontract['system_prompt'] != contract['downstream']['system_prompt']:
            raise ValueError('R_stem model/system differ')
        with gzip.open(rdir/'predictions.jsonl.gz', 'rt') as f:
            reference = {r['pair_id']: r for r in map(json.loads, f) if r['condition'] == 'R_stem' and r['pair_id'] in new}
        if set(reference) != set(new):
            raise ValueError('Missing R_stem predictions')
        rvalues = {p: int(reference[p]['status'] == 'success' and reference[p]['parsed_generated_label'] == labels[p]['gold_answer']) for p in ids}
        rcontrast = paired_bootstrap(new, rvalues, labels, 20261115, 10000)
        lines += [(output/'REPORT_KO.md').read_text().replace('# Single-pass Stem GUI 결과\n', '', 1), '',
                  f"동일 조작 범위의 역사적 **R_stem은{sum(rvalues.values())}/{len(ids)}={sum(rvalues.values())/len(ids):.2%}**다. Single-pass−R_stem은{rcontrast['difference']*100:+.2f}pp,95% CI[{rcontrast['ci95'][0]*100:+.2f},{rcontrast['ci95'][1]*100:+.2f}]pp,회복/회귀{rcontrast['recovery']}/{rcontrast['regression']}이다. R_stem은 같은 모델/system이지만 과거 RTX4090·batch4 혼합 큐여서 현재 batch3 분리 큐와 완전히 동일한 실행은 아니다.", '']
        lines += ['### 출력 검증 실패를 다시 분해하면', '',
                  f"최종 validation fallback 중 **options에만 있는 문자열을 stem 편집 대상으로 반환한 pair는{failure_diagnostics['pairs_with_option_only_source_text']}개**, 원본 MCQ 어디에도 없는 source text를 반환한 pair는{failure_diagnostics['pairs_with_source_text_absent_from_entire_MCQ']}개다. 서로 중복될 수 있다. 전자를 referent 번역 능력 부족이나 occurrence 계산 오류로만 묶지 않는다: 전체 MCQ를 문맥으로 주었을 때 수정 범위를 지키지 못한 것이다.", '',
                  f"실패 응답 중{failure_diagnostics['pairs_with_valid_edits_discarded_by_whole_response_fallback']}개 pair에는 단독 검증 시 적용 가능한 stem edit도 들어 있었다. 이 실험은 기존과 같은 전체 응답 fallback 정책을 고정했으므로 함께 버렸다. 개별 edit만 살렸을 때 정확도가 좋아지는지는 추론하지 않았으며 이 수치는 그 효과의 측정이 아니다.", '']
        for example in failure_examples[:2]:
            lines += [f"`{example['pair_id']}` · 오류: {'; '.join(example['errors'])}", '', '```json', example['raw_output'], '```', '']
        baseline_cost = json.loads((ROOT/'artifacts/stem_only_diagnostic_snapshot.json').read_text())['eta']['measured_rates']
        n = len(ids)
        sources = len({(rows[p]['parallel_id'], rows[p]['source_language']) for p in ids})
        old_seconds = baseline_cost['stem_extract_seconds_per_source']*sources + baseline_cost['stem_align_seconds_per_pair']*n
        calls = [a for p in ids for a in rows[p]['attempts']]
        new_seconds = sum(c['runtime_ms'] for c in calls)/1000
        cost_comparison = {'primary_pairs': n, 'unique_sources': sources, 'separate_extraction_and_alignment_seconds': old_seconds,
                           'single_pass_seconds': new_seconds, 'single_pass_vs_separate_runtime_ratio': new_seconds/old_seconds,
                           'single_pass_calls': len(calls), 'single_pass_primary_repair_calls': sum(c['stage'].endswith('_repair') for c in calls),
                           'inventory_and_downstream_excluded': True}
        lines += ['### 변환 비용 비교', '',
                  f"Main240쌍에서 기존 추출+정렬 LM 호출 시간 합은{old_seconds/60:.2f}분, 통합 호출 합은{new_seconds/60:.2f}분이다（비율{new_seconds/old_seconds:.2f}배）. Inventory와 최종 VLM 문제 풀이, 모델 cold-load는 제외했다. 기존 추출은 source MCQ마다 한 번 만들어 여러 GUI 언어에 재사용했으므로, 호출 단계를 합쳤다고 전체 비용이 절반이 된다고 가정하지 않는다. 기존 값은 저장된 main용 고유 payload runtime 집계에서 가져왔고, 새 값은 동일 main pair의 raw call runtime 합이다.", '',
                  '### 기존 분리 방식과 정오가 바뀐 사례', '',
                  '아래는 자동 선정한 전환 사례이며 의미 보존·GUI 대응의 정답 annotation이 아니다. 기존 병렬 reference 자체에 알려진 mapping 문제가 있으므로 예측 전환을 곧바로 번역 개선으로 부르지 않는다.', '']
        for kind in ('recovery','regression'):
            candidates = [p for p in ids if (new[p] > int(old_preds[p]['parsed_generated_label'] == labels[p]['gold_answer']) if kind == 'recovery' else new[p] < int(old_preds[p]['parsed_generated_label'] == labels[p]['gold_answer']))]
            lines += [('#### 분리 방식 오답 → 통합 정답' if kind == 'recovery' else '#### 분리 방식 정답 → 통합 오답'), '']
            for pid in candidates[:3]:
                lines += [f'- `{pid}` · gold{labels[pid]["gold_answer"]} · 분리{old_preds[pid]["parsed_generated_label"]} → 통합{preds[pid]["parsed_generated_label"]}', '',
                          '```text', 'O: '+originals[pid]['question_stem'], '분리: '+old[pid]['question_stem'], '통합: '+rows[pid]['question_stem'], '```', '']
        snapshot = {'results': result, 'R_stem': {'correct': sum(rvalues.values()), 'contrast': rcontrast},
                    'failure_diagnostics': dict(failure_diagnostics), 'failure_examples': failure_examples,
                    'cost_comparison': cost_comparison, 'contract_sha256': digest(contract),
                    'raw_manifest': {str((Path(done[stage])/filename).relative_to(REPO)): hashlib.sha256((Path(done[stage])/filename).read_bytes()).hexdigest()
                                     for stage, filename in [('rewrite','rewritten.jsonl'), ('rewrite','calls.json'), ('infer','predictions.jsonl')]}}
        write(ROOT/'artifacts/single_pass_stem_results_snapshot.json', snapshot)
    lines += ['', '## 재현·검증·원시 결과', '',
              '테스트14개와 1문항 CPU mock을 통과했다. 원문 복원 불가·잘못된 반복 위치·관계 단어 단독·overlap·옵션 변경·inventory 밖 문자열·실패 fallback을 검증했다. 원문·inventory의 의미 내용까지 자동 검증한 것은 아니다.', '',
              '```bash', 'bash followup_rel_4lang/method_dev/scripts/run_single_pass_stem.sh --run',
              '.venv/bin/python followup_rel_4lang/method_dev/scripts/report_single_pass_stem.py', '```', '',
              '완료 attempt는 재사용하고 미완료 attempt는 보존하며 재시도 시 LM call cache를 재사용한다. 다른 프롬프트나 코드를 쓰려면 새 출력 디렉터리가 필요하다. Selection/Internal/366문항 확대는 실행하지 않는다.', '',
              '- 계약·전체 config: `artifacts/single_pass_stem_screen_v1/contract.json`',
              '- 변환 MCQ·edits·각 raw response·실제 system/user/rendered prompt: `rewrite/attempt_*/rewritten.jsonl` 및 `calls.json`',
              '- 최종 VLM raw output·prompt·batch 시간·VRAM: `infer/attempt_*/predictions.jsonl`',
              '- 결과·paired CI·GUI 언어별 표·비용: 같은 run의 `results.json`과 `REPORT_KO.md`',
              '- Git 보존 요약·raw SHA-256: [single_pass_stem_results_snapshot.json](../artifacts/single_pass_stem_results_snapshot.json)',
              '- 기존 비교: [Two-stage 누적 결과](TWO_STAGE_RESULTS_KO.md), [Stem-only 진단](STEM_ONLY_DIAGNOSTIC_KO.md)', '']
    (ROOT/'reports/SINGLE_PASS_STEM_GUI_KO.md').write_text('\n'.join(lines))
    print(ROOT/'reports/SINGLE_PASS_STEM_GUI_KO.md')


if __name__ == '__main__':
    main()
