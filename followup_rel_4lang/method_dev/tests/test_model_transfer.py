import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import run_model_transfer as transfer
from followup_rel_4lang.method_dev.tests.test_visual_selective_rewrite import fixture
from followup_rel_4lang.method_dev import stem_refinement_2x2 as method


def test_transfer_changes_both_vlm_roles_and_preserves_fixed_lm_and_execution_contract(tmp_path, monkeypatch):
    old_config = {'version': 'old', 'models': {'inventory': {'model_id': 'vl8b', 'revision': '8'*40,
                  'family': 'qwen3_vl', 'path': 'old'},
                  'text': {'model_id': 'fixed-lm', 'revision': '1'*40, 'path': 'fixed'}},
                  'downstream': {'model_config': {'model_id': 'vl8b', 'revision': '8'*40,
                                  'attn_implementation': 'sdpa', 'max_pixels': 2097152},
                                 'batch_size': 3, 'system_prompt': 'unchanged'}, 'seed': 42}
    folder = tmp_path/'artifacts/e1_stem_full_dev_v1'
    folder.mkdir(parents=True)
    (folder/'contract.json').write_text(json.dumps({'config': old_config}))
    cfg = tmp_path/'transfer.json'
    cfg.write_text(json.dumps({'version': 'transfer', 'vlm': {'model_id': 'Qwen/Qwen3-VL-4B-Instruct',
                         'revision': '4'*40, 'family': 'qwen3_vl'}}))
    monkeypatch.setattr(transfer, 'ROOT', tmp_path)
    monkeypatch.setenv('HF_HOME', str(tmp_path/'hf'))
    result, _ = transfer.transfer_config(cfg)
    assert result['models']['inventory'] == result['models']['editor_vlm']
    assert result['models']['text'] == old_config['models']['text']
    expected = copy.deepcopy(old_config)
    expected['version'] = 'transfer'
    expected['models']['inventory'] = result['models']['inventory']
    expected['models']['editor_vlm'] = result['models']['inventory']
    expected['downstream']['model_config'].update(model_id='Qwen/Qwen3-VL-4B-Instruct', revision='4'*40)
    assert result == expected
    assert result['models']['inventory']['path'].startswith(str(tmp_path/'hf/hub'))


def extraction_trace():
    row = fixture()
    text_model = {'model_id': 'fixed-lm', 'revision': '1'*40}
    def backend(stage, role, system, user):
        return {'stage': stage, 'role': role, 'system_prompt': system, 'user_prompt': user,
                **text_model, 'raw_output': '{"referents":[{"field":"question_stem","text":"Settings","occurrence":0}]}'}
    return row, method.extract(row, backend), text_model


def test_source_extraction_replay_accepts_only_identical_prompt_model_and_resolved_spans():
    row, result, text_model = extraction_trace()
    transfer.replay_extraction(row, result, text_model)
    bad = copy.deepcopy(result)
    bad['attempts'][0]['user_prompt'] += ' gold answer A'
    with pytest.raises(ValueError, match='prompt differs'):
        transfer.replay_extraction(row, bad, text_model)
    with pytest.raises(ValueError, match='model differs'):
        transfer.replay_extraction(row, result, {**text_model, 'model_id': 'different-lm'})
    bad = copy.deepcopy(result)
    bad['referents'][0]['text'] = 'changed'
    with pytest.raises(ValueError, match='cannot be reproduced'):
        transfer.replay_extraction(row, bad, text_model)


def test_pinned_model_readiness_rejects_missing_shards(tmp_path):
    path = tmp_path/'snapshot'
    path.mkdir()
    (path/'model.safetensors.index.json').write_text(json.dumps({'weight_map': {'x': 'missing.safetensors'}}))
    for name in ('config.json', 'tokenizer_config.json'):
        (path/name).write_text('{}')
    config = {'models': {role: {'path': str(path)} for role in ('inventory', 'text')}}
    assert transfer.model_ready(config) == ['inventory: missing.safetensors', 'text: missing.safetensors']
    (path/'missing.safetensors').write_bytes(b'placeholder')
    assert transfer.model_ready(config) == []
