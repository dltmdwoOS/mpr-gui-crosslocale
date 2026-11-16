import copy

import pytest

from followup_rel_4lang.method_dev.scripts.compare_end_to_end import batch_share, call_map, call_seconds


def batch():
    return [dict(pair_id=p, condition=c, batch_id='shared', batch_size=3, batch_runtime_ms=900.0)
            for p,c in [('main1','O'), ('main2','T'), ('pilot','R')]]


def test_full_batch_time_is_counted_once_instead_of_once_per_prediction():
    result = batch_share(batch(), lambda row: True)
    assert result['seconds'] == pytest.approx(.9)
    assert result['selected_rows'] == 3 and result['mixed_batches'] == 0


def test_main_and_condition_shares_use_the_complete_batch_denominator():
    rows = batch()
    main = batch_share(rows, lambda r: r['pair_id'].startswith('main'))
    assert main['seconds'] == pytest.approx(.6)
    assert main['mixed_batches'] == 1 and main['selected_rows'] == 2
    assert batch_share(rows, lambda r: r['condition'] == 'T')['seconds'] == pytest.approx(.3)


def test_allocations_partition_total_batch_time():
    rows = batch()+[dict(pair_id='other',condition='O',batch_id='second',batch_size=1,batch_runtime_ms=200)]
    total = batch_share(rows, lambda r: True)['seconds']
    selected = batch_share(rows, lambda r: r['pair_id'].startswith('main'))['seconds']
    remainder = batch_share(rows, lambda r: not r['pair_id'].startswith('main'))['seconds']
    assert selected+remainder == pytest.approx(total)


def test_incomplete_or_inconsistent_batch_is_not_silently_scaled():
    with pytest.raises(ValueError, match='Incomplete'):
        batch_share(batch()[:2], lambda r: True)
    rows = batch()
    rows[1]['batch_runtime_ms'] = 800
    with pytest.raises(ValueError, match='Conflicting'):
        batch_share(rows, lambda r: True)


def test_cache_hit_is_charged_original_cost_once_for_standalone_recipe():
    call = dict(cache_key='full-recipe',runtime_ms=1200,execution_mode='gpu',cache_hit=False)
    hit = {**copy.deepcopy(call), 'cache_hit': True, 'component': 'options_full_pipeline'}
    jobs = call_map([dict(attempts=[call]), dict(attempts=[hit])])
    assert len(jobs) == 1 and call_seconds(jobs) == pytest.approx(1.2)


def test_mock_or_conflicting_cache_measurements_are_rejected():
    call = dict(cache_key='job',runtime_ms=100,execution_mode='mock')
    with pytest.raises(ValueError, match='real GPU'):
        call_map([dict(attempts=[call])])
    call['execution_mode'] = 'gpu'
    with pytest.raises(ValueError, match='Conflicting'):
        call_map([dict(attempts=[call,{**call,'runtime_ms':200}])])
