import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_gpu_ocr_remaining as runner
from report_gpu_ocr_remaining import aggregate_cost, common_completed
from test_ocr_remaining import cohort_rows


def test_selection_and_internal_retain_fixed_execution_and_analysis_counts():
    assert runner.cpu.validate_remaining_rows(cohort_rows(20, excluded=True), 'selection') == {
        'executed_pairs': 240, 'primary_pairs': 239, 'items': 20, 'images': 80}
    assert runner.cpu.validate_remaining_rows(cohort_rows(118), 'internal_evaluation')['primary_pairs'] == 1416


def test_grouped_partitions_cannot_share_a_semantic_item():
    groups = {name: [{'parallel_id': name}] for name in runner.ALL_COHORTS}
    runner.validate_partitions(groups)
    groups['internal_evaluation'] = copy.deepcopy(groups['selection'])
    with pytest.raises(ValueError, match='overlap'):
        runner.validate_partitions(groups)


def test_conflicting_lm_responses_are_excluded_instead_of_arbitrarily_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'REPO', tmp_path)
    folders = [tmp_path / n for n in ('cpu', 'gpu')]
    key = 'a' * 64
    for i, folder in enumerate(folders):
        folder.mkdir()
        (folder / (key + '.json')).write_text(json.dumps({'cache_key': key, 'raw_output': str(i)}))
    selected, conflicts = runner.cache_plan(folders)
    assert selected == {} and conflicts == [key + '.json']
    target = tmp_path / 'new_cache'
    runner.link_cache(selected, target)
    assert list(target.iterdir()) == []
    assert json.loads((folders[0] / (key + '.json')).read_text())['raw_output'] == '0'


def test_seed_links_do_not_overwrite_existing_or_original_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'REPO', tmp_path)
    source = tmp_path / 'source'
    source.mkdir()
    key = 'b' * 64
    path = source / (key + '.json')
    path.write_text(json.dumps({'cache_key': key, 'raw_output': 'valid'}))
    selected, conflicts = runner.cache_plan([source])
    target = tmp_path / 'new'
    runner.link_cache(selected, target)
    assert (target / path.name).is_symlink() and not conflicts
    runner.link_cache(selected, target)
    assert json.loads(path.read_text())['raw_output'] == 'valid'
    other = tmp_path / 'conflict'
    other.mkdir()
    (other / path.name).write_text('{}')
    with pytest.raises(ValueError):
        runner.link_cache(selected, other)


def test_pooled_comparison_waits_for_all_four_completed_conditions():
    values = {cohort: {s: {'O': {}} for s in runner.SOLVERS} for cohort in runner.ALL_COHORTS}
    for s in runner.SOLVERS:
        values['screen'][s].update({b: {} for b in runner.BACKENDS})
    values['selection']['8B'][runner.BACKENDS[0]] = {}
    assert common_completed(values) == ['screen']
    for s in runner.SOLVERS:
        values['selection'][s].update({b: {} for b in runner.BACKENDS})
    assert common_completed(values) == ['screen', 'selection']


def test_global_preprocessing_cost_deduplicates_cache_but_adds_local_batch_shares():
    call = {'cache_key': 'lm', 'runtime_ms': 2000, 'execution_mode': 'gpu'}
    part = {'ocr': [{'cache_key': 'image', 'runtime_ms': 1000}], 'vlm_inventory': [],
            'extraction': [{'attempts': [call]}], 'matching': [], 'answer_seconds': 3}
    result = aggregate_cost([part, copy.deepcopy(part)], 4)
    assert result['inventory_seconds'] == 1 and result['extraction_seconds'] == 2
    assert result['answer_seconds'] == 6 and result['total_seconds'] == 9
    assert result['seconds_per_pair'] == 9 / 4
