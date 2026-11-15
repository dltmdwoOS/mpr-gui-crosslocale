"""5개 모델 결과를 한 표로 모은다. 읽기만 하고, 출력은 argv[1] 경로 하나."""
import json, csv, sys, os
R = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(R)
new = {'Qwen3-VL-4B': 'qwen3_vl_4b', 'InternVL3.5-4B': 'internvl35_4b', 'UI-TARS-1.5-7B': 'uitars_15_7b'}
res = {k: json.load(open(f'{R}/{v}/results.json')) for k, v in new.items()}
ctx = res['UI-TARS-1.5-7B']['context_8b']
order = ['Qwen3-VL-8B', 'InternVL3.5-8B', 'Qwen3-VL-4B', 'InternVL3.5-4B', 'UI-TARS-1.5-7B']
def rel(m, scope):
    return (ctx[m]['rel'][scope]['dependent'] if m in ctx else res[m]['rel']['generation_correct'][scope]['dependent'])
def expa(m, scope):
    return (ctx[m]['expa'][scope]['generation_correct'] if m in ctx else res[m]['expa'][scope]['generation_correct'])
def thai(m):
    return (ctx[m]['thai_indicator_a'] if m in ctx else res[m]['thai_indicator_a'])
csvs = {'Qwen3-VL-8B': f'{ROOT}/expA_results_20261114/analysis_qwen3/contrasts.csv',
        'InternVL3.5-8B': f'{ROOT}/expA_results_20261114/analysis_internvl35/contrasts.csv'}
for k, v in new.items(): csvs[k] = f'{R}/{v}/expA_analyze/contrasts.csv'
def sub(m, setname, con):
    for r in csv.DictReader(open(csvs[m])):
        if r['set'] == setname and r['outcome'] == 'generation_correct' and r['contrast'] == con:
            return r
def f(e, lo, hi, p=None):
    s = f"{e:+.1f} [{lo:+.1f}, {hi:+.1f}]"
    return s + (f" ({p:.4f})" if p is not None else '')
out = []
for scope, lab in [('all4', '4언어 전체'), ('noTH_both', '태국어 제외(질문·화면)')]:
    out.append(f"\n### REL 의존 문항, {lab} (차이 %p [95% CI] (Holm p))\n\n| 모델 | R−O | C−O | F−C | F−R |\n|---|---|---|---|---|")
    for m in order:
        x = rel(m, scope)
        out.append(f"| {m} | " + ' | '.join(f(x[c]['est_pp'], x[c]['lo'], x[c]['hi'], x[c]['p_holm']) for c in ['R_minus_O', 'C_minus_O', 'F_minus_C', 'F_minus_R']) + ' |')
    out.append(f"\n### 실험 A, {lab}\n\n| 모델 | 쌍 | O | T | R | T−O | R−T | R−O |\n|---|---|---|---|---|---|---|---|")
    for m in order:
        x = expa(m, scope); a = x['acc']
        cells = [f(x[c]['pp'], x[c]['lo'], x[c]['hi'], x[c].get('p_holm_primary2')) if c != 'R_minus_O' else f(x[c]['pp'], x[c]['lo'], x[c]['hi']) for c in ['T_minus_O', 'R_minus_T', 'R_minus_O']]
        out.append(f"| {m} | {x['pairs']} | {a['O']:.1f} | {a['T']:.1f} | {a['R']:.1f} | " + ' | '.join(cells) + ' |')
out.append("\n### 실험 A 뜻 보존 쌍(sub2, 708쌍)과 화면 언어별(sub5) (차이 [CI], 괄호는 해당 묶음 Holm p)\n\n| 모델 | 뜻 보존 T−O | 뜻 보존 R−T | en T−O | zh T−O | ru T−O | th T−O | th R−T |\n|---|---|---|---|---|---|---|---|")
for m in order:
    cells = []
    for s, c in [('sub2_meaning_preserved', 'T_minus_O'), ('sub2_meaning_preserved', 'R_minus_T'), ('sub5_gui_en', 'T_minus_O'), ('sub5_gui_zh', 'T_minus_O'), ('sub5_gui_ru', 'T_minus_O'), ('sub5_gui_th', 'T_minus_O'), ('sub5_gui_th', 'R_minus_T')]:
        r = sub(m, s, c)
        cells.append('없음' if r is None else f(float(r['pp']), float(r['ci_lo']), float(r['ci_hi']), float(r['p_holm_primary2']) if r.get('p_holm_primary2') else None))
    out.append(f"| {m} | " + ' | '.join(cells) + ' |')
out.append("\n### 태국어 읽기 지표 (a) (REL R 정답률, 태국어 화면 ÷ 영어 화면; 기준 정의 eligible_only, 0.7 미만 표시, 문턱은 사후)\n\n| 모델 | eligible_only | all_rows |\n|---|---|---|")
for m in order:
    t = thai(m); out.append(f"| {m} | {t['eligible_only']['ratio']:.3f} | {t['all_rows']['ratio']:.3f} |")
open(sys.argv[1], 'w').write('# 5개 모델 결과표 (자동 생성)\n\n생성: compile_five_models.py. 생성 답 정오, 문항 부트스트랩 B=10,000. REL seed 42·Holm 4개, 실험 A seed 20261113·Holm 2개(T−O, R−T). p 하한은 약 0.0002(원시)/0.0004~0.0008(Holm).\n' + '\n'.join(out) + '\n')
