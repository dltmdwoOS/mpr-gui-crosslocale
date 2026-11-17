import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_ocr_4b as runner
from mpr_crosslocale.methods.selective_alignment.schemas import digest
from mpr_crosslocale.methods.selective_alignment.referent_extractor import resolve_referents
from followup_rel_4lang.method_dev.tests.test_visual_selective_rewrite import fixture


def profiles():
    before = {'seed': 42, 'labels_sha256': 'same',
              'downstream': {'batch_size': 3, 'system_prompt': 'same', 'model_config': {'model_id': '8B', 'revision': 'old', 'attn_implementation': 'sdpa'}},
              'config': {'models': {'text': {'model_id': 'Qwen3-8B'}}},
              'inference_config': {'models': {'editor_vlm': {'model_id': '8B'}}}}
    after = copy.deepcopy(before)
    after['downstream']['model_config'].update(model_id='4B', revision='new')
    after['config']['models']['editor_vlm'] = {'model_id': '4B'}
    return before, after


def test_only_solver_checkpoint_changes_and_inputs_are_not_mutated():
    before, after = profiles()
    saved = copy.deepcopy(before)
    cfg, profile = runner.four_b_profile(before, after)
    assert cfg['models']['editor_vlm']['model_id'] == '4B'
    assert profile['model_config']['model_id'] == '4B'
    assert before == saved


@pytest.mark.parametrize('changed', ['batch', 'system', 'seed', 'LM', 'labels'])
def test_changed_method_or_evaluation_contract_is_rejected(changed):
    before, after = profiles()
    if changed == 'batch': after['downstream']['batch_size'] = 4
    if changed == 'system': after['downstream']['system_prompt'] = 'different'
    if changed == 'seed': after['seed'] = 99
    if changed == 'LM': after['config']['models']['text']['model_id'] = 'other LM'
    if changed == 'labels': after['labels_sha256'] = 'other labels'
    with pytest.raises(ValueError):
        runner.four_b_profile(before, after)


def test_shared_preprocessing_hash_and_selective_scope_are_checked(tmp_path):
    source = tmp_path / 'source8'
    source.mkdir()
    row = fixture()
    (source / 'inputs.jsonl').write_text(json.dumps(row) + '\n')
    contract = {'execution_mode': 'gpu'}
    (source / 'contract.json').write_text(json.dumps(contract))
    (source / 'COMPLETE.json').write_text(json.dumps({'contract_sha256': digest(contract)}))
    rewrite = source / 'rewrite/attempt_0001'
    rewrite.mkdir(parents=True)
    (rewrite / 'COMPLETE').write_text('complete\n')
    refs = resolve_referents(row, json.dumps({'referents': [{'field': 'question_stem', 'text': 'Settings', 'occurrence': 0}]}))
    changed = {**row, 'question_stem': row['question_stem'].replace('Settings', '设置'),
               'edits': [{**refs[0], 'replacement': '设置'}]}
    path = rewrite / 'rewritten.jsonl'
    path.write_text(json.dumps(changed) + '\n')
    cfg = {'descriptors': {'screen': {'source8': str(source)}}}
    _, binding = runner.bind_preprocessing(cfg, 'screen')
    assert binding['rewritten_path'] == str(path)
    changed['options'] = {**row['options'], 'A': 'rewritten option'}
    path.write_text(json.dumps(changed) + '\n')
    with pytest.raises(ValueError, match='selective scope'):
        runner.bind_preprocessing(cfg, 'screen')


def test_resume_accepts_json_key_reordering_but_rejects_contract_content_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'COHORTS', ('screen',))
    parent = {'setting': 3, 'version': 'same'}
    monkeypatch.setattr(runner.remaining, 'verify', lambda _: {'version': 'same', 'setting': 3})
    source = tmp_path / 'source8'
    source.mkdir()
    child = {'parent': 'same', 'batch_size': 3}
    (source / 'contract.json').write_text(json.dumps({'batch_size': 3, 'parent': 'same'}))
    output = tmp_path / 'output4'
    (output / 'screen').mkdir(parents=True)
    rows = [fixture()]
    (output / 'screen/inputs.jsonl').write_text(json.dumps(rows[0]) + '\n')
    cfg = {'source_sha256': {}, 'base8': str(source), 'base8_contract_sha256': digest(parent),
           'descriptors': {'screen': {'source8': str(source), 'source8_contract_sha256': digest(child)}},
           'originals_sha256': {'screen': digest(rows)}}
    (output / 'contract.json').write_text(json.dumps(cfg))
    assert runner.verify(output) == cfg
    (source / 'contract.json').write_text(json.dumps({**child, 'batch_size': 4}))
    with pytest.raises(ValueError, match='content changed'):
        runner.verify(output)
