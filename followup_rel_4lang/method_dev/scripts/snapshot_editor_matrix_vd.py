"""Record completed V-D cohorts per solver without touching a running experiment."""
from datetime import datetime, timezone
from pathlib import Path

from run_editor_matrix_remaining import DEFAULT, LABELS, ROOT, REPO, COHORTS, SOLVERS, CELLS, actor, load, sha
from run_stem_only_gui import read, unique, write
from report_editor_matrix_remaining import aggregate, cohort_data
from mpr_crosslocale.methods.selective_alignment.schemas import digest

SNAPSHOT = ROOT / 'artifacts/ppocr_editor_matrix_vd_snapshot.json'


def snapshot(output):
    contract = load(output / 'contract.json')
    if contract['execution_mode'] != 'gpu':
        raise ValueError('Snapshot requires real GPU results')
    for filename, expected in contract['source_sha256'].items():
        if sha(REPO / filename) != expected:
            raise ValueError('Frozen source changed: ' + filename)
    labels = unique(read(LABELS))
    if digest(labels) != contract['labels_sha256']:
        raise ValueError('Evaluation label digest differs')
    summary = {}
    for solver in SOLVERS:
        completed = ['screen']
        predictions = {}
        for cohort in ('screen', *COHORTS):
            root = Path(contract['screen_run']) if cohort == 'screen' else output / cohort
            folder = root / actor(solver)
            if not (folder / 'COMPLETE').is_file():
                continue
            if cohort != 'screen':
                completed.append(cohort)
            for cell in CELLS:
                evaluation = folder / 'infer' / cell
                if not (evaluation / 'COMPLETE').is_file():
                    raise ValueError('Missing cell completion marker')
                if cohort != 'screen':
                    evaluation_contract = load(evaluation / 'contract.json')
                    expected = digest({**contract, **contract['cohorts'][cohort]})
                    if evaluation_contract['parent_sha256'] != expected:
                        raise ValueError('Evaluation belongs to a different contract')
                path = evaluation / 'predictions.jsonl'
                predictions[str(path.relative_to(REPO))] = sha(path)
        groups = {c: cohort_data(output, contract, c, solver, labels) for c in completed}
        summary[solver] = {
            'completed_cohorts': completed, 'pending_cohorts': [c for c in COHORTS if c not in completed],
            'by_cohort': {c: aggregate([group], labels) for c, group in groups.items()},
            'pooled_completed': aggregate(list(groups.values()), labels),
            'prediction_sha256': predictions,
            'remaining_run_actor_costs': {c: [load(p) for p in sorted((output / c / actor(solver)).glob('cost_*.json'))]
                                         for c in completed if c != 'screen'},
        }
    write(SNAPSHOT, {
        'as_of_utc': datetime.now(timezone.utc).isoformat(), 'execution_mode': 'gpu',
        'development_only': True, 'remaining_run_contract_sha256': digest(contract),
        'complete': all(not s['pending_cohorts'] for s in summary.values()), 'solvers': summary,
    })
    print(SNAPSHOT)


if __name__ == '__main__':
    snapshot(DEFAULT)
