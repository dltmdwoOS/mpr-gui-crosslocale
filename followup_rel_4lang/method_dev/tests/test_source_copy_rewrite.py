import copy
import json

import pytest

from followup_rel_4lang.method_dev import source_copy_rewrite as method
from followup_rel_4lang.method_dev.exact_batch_reuse import batch_key, build_index
from followup_rel_4lang.method_dev.tests.test_visual_selective_rewrite import fixture


def test_prompt_preserves_non_english_source_and_does_not_receive_gold():
    row = fixture(); row['source_language'] = 'ru'
    prompt = method.user_prompt(row)
    assert 'source_language_to_preserve' in prompt and 'gui_language_for_names_only' in prompt
    assert 'Что находится' in method.SYSTEM and 'สิ่งใด' in method.SYSTEM and '哪个' in method.SYSTEM
    assert 'weekday/month identities' in method.SYSTEM
    row['gold_answer'] = 'A'
    with pytest.raises(ValueError):
        method.user_prompt(row)


def test_rewrite_has_same_output_interface_and_only_structure_repair():
    row = fixture(); before = copy.deepcopy(row)
    proposal = {'question_stem': 'Which is not below "设置"?', 'options': row['options']}
    outputs = iter(['{', json.dumps(proposal)])
    result = method.rewrite(row, lambda *a, **k: {'raw_output': next(outputs)})
    assert row == before and len(result['attempts']) == 2 and result['status'] == 'success'


def source(labels=('A', 'B', 'C')):
    rows = [dict(pair_id=str(i), rendered_prompt='p'+str(i), generated_text=label,
        execution_mode='gpu', status='success', batch_size=3, batch_id='b', batch_runtime_ms=42.)
        for i, label in enumerate(labels)]
    return dict(path='frozen.jsonl', downstream={'batch_size': 3}, seed=42,
                environment={'hardware': 'gpu'}, predictions=rows)


def test_reuse_requires_whole_ordered_batch_and_exact_environment():
    s = source(); images = {str(i): 'sha'+str(i) for i in range(3)}
    index, conflicts = build_index([s], s['downstream'], 42, images, s['environment'])
    key = lambda r: batch_key(s['downstream'], 42, r, images, s['environment'])
    assert key(s['predictions']) in index and not conflicts
    changed = copy.deepcopy(s['predictions']); changed[1]['rendered_prompt'] += 'changed'
    assert key(changed) not in index and key(list(reversed(s['predictions']))) not in index
    assert not build_index([s], s['downstream'], 43, images, s['environment'])[0]
    assert not build_index([s], s['downstream'], 42, images, {'hardware': 'different'})[0]


def test_conflicting_outputs_are_not_silently_reused_and_incomplete_batches_fail():
    s = source(); other = source(('D', 'B', 'C')); images = {str(i): 'sha' for i in range(3)}
    index, conflicts = build_index([s, other, s], s['downstream'], 42, images, s['environment'])
    assert not index and len(conflicts) == 1
    s['predictions'].pop()
    with pytest.raises(ValueError, match='Incomplete'):
        build_index([s], s['downstream'], 42, images, s['environment'])
