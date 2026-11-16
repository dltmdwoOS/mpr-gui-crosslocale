import copy
import json

import pytest

from followup_rel_4lang.method_dev import direct_selective_rewrite as method
from mpr_crosslocale.methods.selective_alignment.schemas import fields


def fixture():
    return dict(pair_id='x::en::zh',parallel_id='x',source_language='en',gui_language='zh',
                image_path='unused.png',image_sha256='unused',question_stem='Which is not below "Settings"?',
                options=dict(A='The "Privacy" item',B='Home',C='Help',D='Exit'),option_order=list('ABCD'))


def complete(row):
    return {'question_stem':row['question_stem'],'options':dict(row['options'])}


def test_complete_fields_are_accepted_without_any_edit_metadata():
    row=fixture();before=copy.deepcopy(row);proposal=complete(row)
    proposal['question_stem']='Which is not below "设置"?';proposal['options']['A']='The "隐私" item'
    calls=[]
    def backend(*args,**kwargs):
        calls.append((args,kwargs));return {'raw_output':json.dumps(proposal)}
    result=method.rewrite(row,backend)
    assert len(calls)==1 and result['status']=='success'
    assert result['output']['A']=='The "隐私" item' and row==before
    assert set(calls[0][1]['image'])=={'image_path','image_sha256'}
    assert 'inventory' not in json.loads(calls[0][0][3].split('\n\n',1)[1])
    assert 'edits' not in result and 'extracted_referents' not in result


@pytest.mark.parametrize('raw', ['invalid', '{"edits":[]}', '{"question_stem":"x","options":{"A":"a"}}',
    '{"question_stem":"","options":{"A":"a","B":"b","C":"c","D":"d"}}',
    '{"question_stem":"x","options":{"A":1,"B":"b","C":"c","D":"d"}}'])
def test_only_structure_errors_trigger_bounded_repair_and_fallback(raw):
    row=fixture();calls=[]
    def backend(*args,**kwargs):
        calls.append(args[0]);return {'raw_output':raw}
    result=method.rewrite(row,backend)
    assert calls==['visual_rewrite','visual_rewrite_repair']
    assert result['status']=='fallback_original' and result['output']==fields(row)


def test_context_and_digit_changes_are_recorded_without_hidden_rejection():
    row=fixture();proposal=complete(row)
    proposal['question_stem']='Which is above "设置" in 2025?'
    proposal['options']['B']=proposal['options']['C']='帮助'
    calls=[]
    def backend(*args,**kwargs):
        calls.append(args);return {'raw_output':json.dumps(proposal)}
    result=method.rewrite(row,backend)
    assert result['status']=='success' and len(calls)==1
    assert result['diagnostics']['new_duplicate_options'] is True
    assert result['diagnostics']['digit_sequence_changed_fields']==['question_stem']
    assert result['diagnostics']['semantic_equivalence_verified'] is False


def test_json_key_order_is_canonicalized_without_repair():
    row=fixture();proposal=complete(row)
    proposal['options']={k:proposal['options'][k] for k in 'DCBA'}
    result=method.validate_output(json.dumps(proposal))
    assert list(result)==['question_stem','A','B','C','D'] and result==fields(row)


def test_gold_answer_and_inventory_are_not_method_input():
    row=fixture();row['gold_answer']='A'
    with pytest.raises(ValueError,match='allowlisted'):
        method.user_prompt(row)


def test_unicode_diff_reconstructs_actual_source_and_target_fragments():
    row=fixture();row['question_stem']='ตั้งค่าの下？';output=fields(row);output['question_stem']='设置の下？'
    diffs=method.diff_fields(row,output)
    assert diffs and all(d['field']=='question_stem' for d in diffs)
    assert any('ตั้งค่า' in d['before'] for d in diffs)


def test_structure_repair_can_succeed_then_stop():
    row=fixture();responses=iter(['{',json.dumps(complete(row))])
    result=method.rewrite(row,lambda *args,**kwargs:{'raw_output':next(responses)})
    assert result['status']=='no_op_no_changes' and len(result['attempts'])==2


def test_posthoc_context_check_allows_name_changes_but_flags_direction_change():
    from followup_rel_4lang.method_dev.scripts.report_visual_selective_rewrite import protected_context_matches
    source='Which is below Settings and above Privacy?'
    spans=[{'start':source.index(t),'end':source.index(t)+len(t),'text':t} for t in ('Settings','Privacy')]
    assert protected_context_matches(source,'Which is below 设置 and above 隐私?',spans)
    assert not protected_context_matches(source,'Which is above 设置 and above 隐私?',spans)


def test_posthoc_format_check_keeps_negation_protected():
    from followup_rel_4lang.method_dev.scripts.report_visual_selective_rewrite import protected_context_matches,normalize_context
    source='Which is not below "Settings"?';start=source.index('Settings')
    spans=[dict(start=start,end=start+8,text='Settings')]
    target='which is not below “设置”？'
    assert not protected_context_matches(source,target,spans)
    assert protected_context_matches(source,target,spans,normalize_context)
    assert not protected_context_matches(source,'which is below “设置”？',spans,normalize_context)


def test_posthoc_no_annotation_requires_copy_and_bad_annotation_is_not_ignored():
    from followup_rel_4lang.method_dev.scripts.report_visual_selective_rewrite import protected_context_matches
    assert protected_context_matches('below','below',[])
    assert not protected_context_matches('below','above',[])
    with pytest.raises(ValueError,match='annotation'):
        protected_context_matches('below','below',[dict(start=0,end=5,text='above')])
