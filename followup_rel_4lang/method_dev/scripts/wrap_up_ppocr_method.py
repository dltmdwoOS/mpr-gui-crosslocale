"""Post-hoc, CPU-only PP-OCR method/reference/external-baseline comparison."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / '01_code/src'), str(REPO), str(Path(__file__).parent)]
from run_gpu_ocr_remaining import DEFAULT_OUTPUT, SCREEN, ALL_COHORTS, verify, load
from run_stem_only_gui import read, unique, write
from run_stem_refinement_2x2 import latest
from reference_comparison import load_references, stream, is_correct
from search_pipeline import EXCLUDED, paired_bootstrap
from mpr_crosslocale.methods.selective_alignment.schemas import digest
from mpr_crosslocale.inference.answer_parser import parse_label
from followup_rel_4lang.method_dev import external_baselines

REPORT = ROOT / 'reports/PPOCR_STEM_ALIGNMENT_WRAPUP_KO.md'
SNAPSHOT = ROOT / 'artifacts/ppocr_method_wrapup_snapshot.json'


def main():
    c = verify(DEFAULT_OUTPUT)
    g = load(DEFAULT_OUTPUT / 'results.json')
    if load(DEFAULT_OUTPUT / 'COMPLETE.json')['contract_sha256'] != digest(c) or g['contract_sha256'] != digest(c) or g['pending_conditions']:
        raise ValueError('Completed full GPU OCR run required')
    sources = {}
    def use(path):
        path = Path(path).resolve()
        sources[str(path.relative_to(REPO))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path
    def jload(path):
        return load(use(path))
    for path in (Path(__file__), ROOT / 'scripts/ppocr_wrapup_report.py', DEFAULT_OUTPUT / 'contract.json',
                 DEFAULT_OUTPUT / 'COMPLETE.json', DEFAULT_OUTPUT / 'results.json'):
        use(path)
    labels = unique(read(use(ROOT / 'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl')))
    if digest(labels) != c['labels_sha256']:
        raise ValueError('Labels changed')
    originals, ids_by_cohort, scores = {}, {}, {}
    ext = ROOT / 'artifacts/external_baselines_v1'
    ec = jload(ext / 'contract.json')
    if jload(ext / 'COMPLETE.json')['contract_sha256'] != digest(ec) or ec['labels_sha256'] != c['labels_sha256']:
        raise ValueError('External baseline source changed')
    for name, sha in ec['source_sha256'].items():
        if hashlib.sha256((REPO / name).read_bytes()).hexdigest() != sha:
            raise ValueError('Frozen external baseline code/data changed')
    for cohort in ALL_COHORTS:
        work = SCREEN / 'ppocrv5_cuda' if cohort == 'screen' else DEFAULT_OUTPUT / cohort / 'ppocrv5_cuda'
        rows = unique(read(use(work / 'inputs.jsonl')))
        if rows != unique(read(use(ext / cohort / 'inputs.jsonl'))):
            raise ValueError('External baseline originals differ')
        ids_by_cohort[cohort] = {p for p in rows if labels[p]['split'] == 'main' and p != EXCLUDED}
        originals[cohort] = {p: rows[p] for p in ids_by_cohort[cohort]}
        pp = unique(read(use(latest(work, 'infer_8B') / 'evaluation/predictions.jsonl')))
        sc = jload(work / 'contract.json')
        if ec['config']['downstream'] != sc['solvers']['8B']['downstream']:
            raise ValueError('TT/current 8B downstream differs')
        old = unique([r for r in read(use(Path(sc['solvers']['8B']['O_predictions']))) if r['condition'] == 'O'])
        local = {'PPOCR_STEM': pp, 'O': old,
                 'TT': unique(read(use(latest(ext / cohort, 'infer_tt') / 'evaluation/predictions.jsonl'))),
                 'CLP': unique(read(use(latest(ext / cohort, 'infer_clp') / 'evaluation/predictions.jsonl')))}
        for name, records in local.items():
            if not ids_by_cohort[cohort] <= set(records):
                raise ValueError('Missing paired predictions')
            parser = external_baselines.parse_clp_answer if name == 'CLP' else parse_label
            if any(records[p]['execution_mode'] != 'gpu' or parser(records[p]['generated_text']) != records[p]['parsed_generated_label'] for p in ids_by_cohort[cohort]):
                raise ValueError('Invalid raw parser/provenance')
            scores.setdefault(name, {}).update({p: is_correct(records[p], labels[p]['gold_answer']) for p in ids_by_cohort[cohort]})
    selected = set(scores['O'])
    if len(selected) != 1895 or len({labels[p]['parallel_id'] for p in selected}) != 158:
        raise ValueError('Primary denominator differs')
    expa_dir = ROOT.parent / 'artifacts/new_models_expA_20261115/analysis/expA_8b_20261114/qwen3/expA_qwen3/full'
    expa = jload(expa_dir / 'run_contract.json')
    current = jload(SCREEN / 'ppocrv5_cuda/contract.json')['downstream']
    if expa['model_config'] != current['model_config'] or expa['system_prompt'] != current['system_prompt']:
        raise ValueError('Reference model/system differs')
    refs, metadata, aliases = load_references(REPO, {p: labels[p] for p in selected}, originals,
        use, current['model_config'], digest(expa))
    for name, records in refs.items():
        scores[name] = {p: is_correct(records[p], labels[p]['gold_answer']) for p in selected}
    old_meta = jload(ROOT / 'artifacts/search_report_snapshot.json')['reference_comparison']['metadata']
    if metadata != old_meta:
        raise ValueError('Reference run provenance differs from previously audited source')
    rdir = ROOT.parent / 'results/rstem_ropts_20261110/qwen3/raw'
    rc = jload(rdir / 'run_contract.json')
    lock = jload(ROOT.parent / 'rstem_ropts_inputs/input_lock.json')
    mixed = use(ROOT.parent / 'rstem_ropts_inputs/mixed_conditions.jsonl')
    if hashlib.sha256(mixed.read_bytes()).hexdigest() != rc['mixed_inputs_sha256'] or rc['mixed_inputs_sha256'] != lock['generated_sha256']['mixed_conditions.jsonl']:
        raise ValueError('R_stem input lock differs')
    if rc['model_config'] != current['model_config'] or rc['system_prompt'] != current['system_prompt']:
        raise ValueError('R_stem model/system differs')
    rstem = unique([r for r in stream(use(rdir / 'predictions.jsonl.gz')) if r['pair_id'] in selected and r['condition'] == 'R_stem'])
    if set(rstem) != selected:
        raise ValueError('R_stem coverage differs')
    for p, row in rstem.items():
        if row['gold_answer'] != labels[p]['gold_answer'] or row['parallel_id'] != labels[p]['parallel_id'] or row['query_language'] != originals[next(k for k in ALL_COHORTS if p in originals[k])][p]['source_language']:
            raise ValueError('R_stem pair linkage differs')
    scores['R_stem'] = {p: is_correct(rstem[p], labels[p]['gold_answer']) for p in selected}
    expected = {'O': 1330, 'T_REF': 1335, 'R_REF': 1591, 'F_REF': 1551, 'R_stem': 1472, 'TT': 1348, 'CLP': 1250, 'PPOCR_STEM': 1420}
    if any(sum(scores[name].values()) != n for name, n in expected.items()):
        raise ValueError('Previously reported aggregate differs')
    historical_O = {name: sum(scores[name].values()) for name in ('O_EXP_A', 'O_ORCF')}
    contrast = {name: paired_bootstrap(scores['PPOCR_STEM'], scores[name], labels, 20261115, 10000)
                for name in ('O', 'T_REF', 'R_REF', 'F_REF', 'R_stem', 'TT', 'CLP')}
    costs = jload(ROOT / 'artifacts/tt_efficiency_comparison_snapshot.json')['costs']['combined']
    clp = jload(ROOT / 'artifacts/current_experiment_summary_snapshot.json')['clp_diagnostics']['counts']
    cohort_scores = {cohort: {m: sum(v[p] for p in ids) for m, v in scores.items()} for cohort, ids in ids_by_cohort.items()}
    data = {'as_of_utc': datetime.now(timezone.utc).isoformat(), 'development_only': True,
        'primary_items': 158, 'primary_pairs': 1895, 'comparison_model': 'Qwen3-VL-8B-Instruct',
        'correct': {m: sum(v.values()) for m, v in scores.items()}, 'contrasts_ppocr_minus_baseline': contrast,
        'by_cohort_correct': cohort_scores, 'references': metadata, 'F_aliases': {v: sum(x == v for x in aliases.values()) for v in set(aliases.values())},
        'historical_O': historical_O, 'R_stem_contract': {'batch_size': rc['batch_size'], 'fingerprint': rc['experiment_fingerprint']},
        'automatic_method_costs': {'O': costs['O'], 'TT': costs['TT'], 'CLP': costs['CLP'],
            'PPOCR_STEM': g['summary']['all_158']['8B']['methods']['ppocrv5_cuda']['cost']},
        'transfer_4b': g['summary']['all_158']['4B'], 'clp_diagnostics': clp,
        'sources_sha256': sources, 'policy': 'Post-hoc comparison only; no inference or frozen-artifact changes. '
            'Reference costs not ranked against B200 automatic methods. TT/CLP measured for 8B only. No independent confirmatory claims.'}
    write(SNAPSHOT, data)
    from ppocr_wrapup_report import render_report
    REPORT.write_text(render_report(data))
    print('WRAP UP verified: same1895 pairs; PP-OCR vs O/R/T/F/R_stem/TT/CLP; no inference')
    print('REPORT', REPORT)


if __name__ == '__main__':
    main()
