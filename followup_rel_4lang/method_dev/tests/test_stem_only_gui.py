import copy
import json
import pytest
from followup_rel_4lang.method_dev.scripts import run_stem_only_gui as experiment
from mpr_crosslocale.methods.selective_alignment.schemas import fields,render


def fixture():
    original=dict(pair_id='item::en::zh',parallel_id='item',source_language='en',gui_language='zh',image_path='unused.png',image_sha256='unused',
                  question_stem='Which is not below Settings?',options=dict(A='Privacy',B='Home',C='Help',D='Exit'),option_order=list('ABCD'))
    start=original['question_stem'].index('Settings')
    edit=dict(span_id='stem',field='question_stem',text='Settings',start=start,end=start+8,replacement='设置')
    hybrid={**copy.deepcopy(original),'question_stem':'Which is not below 设置?','options':dict(A='隐私',B='主页',C='帮助',D='退出'),
            'condition':experiment.HYBRID,'execution_mode':'gpu','edits':[edit],'extracted_referents':[edit],
            'components':dict(stem_extraction_failed=False,stem_alignment_failed=False,stem_status='success')}
    return original,hybrid


def test_stem_is_identical_to_frozen_hybrid_and_options_are_original():
    original,hybrid=fixture();before=copy.deepcopy(hybrid)
    result=experiment.compose(original,hybrid)
    assert result['question_stem']==hybrid['question_stem']
    assert result['options']==original['options'] and result['options']!=hybrid['options']
    assert result['modified_question']==render(fields(result))
    assert result['status']=='success' and result['new_translation_calls']==0
    assert hybrid==before


@pytest.mark.parametrize('mutation',['context','option_order','option_edit','option_ref','mock'])
def test_composition_refuses_changed_identity_or_nonreferent_stem(mutation):
    original,hybrid=fixture()
    if mutation=='context':hybrid['question_stem']='Which is above 设置?'
    elif mutation=='option_order':hybrid['option_order']=list('BACD')
    elif mutation=='option_edit':hybrid['edits'][0]['field']='A'
    elif mutation=='option_ref':hybrid['extracted_referents'][0]['field']='A'
    else:hybrid['execution_mode']='mock'
    with pytest.raises(ValueError):experiment.compose(original,hybrid)


def test_failed_stem_and_successful_hybrid_options_becomes_original_stem_only():
    original,hybrid=fixture();hybrid.update(question_stem=original['question_stem'],edits=[],extracted_referents=None)
    hybrid['components'].update(stem_extraction_failed=True,stem_status='fallback_original')
    result=experiment.compose(original,hybrid)
    assert fields(result)==fields(original) and result['status']=='fallback_original'


def test_duplicate_sources_are_not_silently_collapsed():
    original,_=fixture()
    with pytest.raises(ValueError,match='Duplicate'):experiment.unique([original,original])


def test_mock_result_has_no_accuracy_or_real_timing(tmp_path):
    experiment.write(tmp_path/'contract.json',{})
    original,hybrid=fixture();composed=experiment.compose(original,hybrid)
    experiment.jsonl(tmp_path/'rewritten.jsonl',[composed])
    prediction=tmp_path/'prediction';prediction.mkdir()
    experiment.jsonl(prediction/'predictions.jsonl',[dict(pair_id=original['pair_id'],execution_mode='mock')])
    experiment.summarize(tmp_path,prediction,mock=True)
    result=json.loads((tmp_path/'results.json').read_text())
    assert result['empirical'] is False and 'correct' not in result
