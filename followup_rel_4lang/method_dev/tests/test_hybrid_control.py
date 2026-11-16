import json
import pytest
from followup_rel_4lang.method_dev.two_stage_v2 import pipeline,prompts
from followup_rel_4lang.method_dev.scripts.run_two_stage_v2 import hybrid_comparisons
from mpr_crosslocale.methods.selective_alignment.schemas import fields


def row():
    return dict(pair_id='rel::test::en::zh',parallel_id='rel::test',source_language='en',gui_language='zh',image_path='unused',image_sha256='unused',
                question_stem='What is directly above Settings?',options=dict(A='Privacy panel',B='Home button',C='Help menu',D='Exit button'),option_order=list('ABCD'))


def refs():
    r=row();start=r['question_stem'].index('Settings')
    return [dict(span_id=f'question_stem:{start}:{start+8}',field='question_stem',text='Settings',start=start,end=start+8,kind='label')]


def full_output():
    return {'question_stem':'哪个元素位于设置正上方？','options':dict(A='隐私面板',B='主页按钮',C='帮助菜单',D='退出按钮')}


class Backend:
    def __init__(self,*outputs):self.outputs=list(outputs);self.calls=[]
    def __call__(self,stage,role,system,user):
        self.calls.append(dict(stage=stage,system=system,user=user))
        value=self.outputs.pop(0)
        return {'raw_output':value if isinstance(value,str) else json.dumps(value,ensure_ascii=False),'output_tokens':0}


def test_query_extractor_never_receives_options_and_rejects_option_fields():
    backend=Backend({'referents':[{'field':'A','text':'Privacy','occurrence':0}]},
                    {'referents':[{'field':'question_stem','text':'Settings','occurrence':0}]})
    result=pipeline.extract(row(),backend,stem_only=True)
    assert result['status']=='success'
    assert [c['stage'] for c in backend.calls]==['extract_stem','extract_stem_repair']
    assert all(set(json.JSONDecoder().raw_decode(c['user'])[0]['fields'])=={'question_stem'} for c in backend.calls)
    assert 'Privacy panel' not in backend.calls[0]['user']
    assert all(r['field']=='question_stem' for r in result['referents'])


def test_failure_diagnostics_distinguish_invalid_option_occurrence_from_stem():
    raw=json.dumps({'referents':[{'field':'question_stem','text':'Settings','occurrence':0},
                                {'field':'A','text':'Privacy','occurrence':1}]})
    assert pipeline.extraction_failure_fields(row(),raw)==['A']
    assert pipeline.extraction_failure_fields(row(),'invalid JSON')==['schema']


def test_hybrid_stem_is_selective_and_options_match_full_recipe_exactly():
    ref=refs()[0];backend=Backend({'translations':{ref['span_id']:'设置'}},full_output())
    result=pipeline.hybrid(row(),[ref],backend,{'visible_strings':['设置','隐私面板']})
    assert result['output']['question_stem']=='What is directly above 设置?'
    assert {k:result['output'][k] for k in 'ABCD'}==full_output()['options']
    assert result['components']['options_source_recipe']=='TS_FULL_GUI'
    assert result['components']['full_generated_stem_discarded'] is True
    assert [c['stage'] for c in backend.calls]==['selective','full']
    assert 'Privacy panel' in backend.calls[0]['user']  # Context allowed during matching, not extraction.
    assert 'What is directly above Settings?' in backend.calls[1]['user']


def test_stem_failure_does_not_discard_successful_option_translation():
    result=pipeline.hybrid(row(),None,Backend(full_output()),{'visible_strings':['设置']})
    assert result['status']=='partial_fallback'
    assert result['output']['question_stem']==row()['question_stem']
    assert result['output']['A']=='隐私面板'
    assert result['components']['stem_extraction_failed']
    assert not result['components']['options_full_pipeline_failed']


def test_full_failure_does_not_discard_successful_query_edit():
    ref=refs()[0];backend=Backend({'translations':{ref['span_id']:'设置'}},'bad','bad')
    result=pipeline.hybrid(row(),[ref],backend,{'visible_strings':['设置']})
    assert result['status']=='partial_fallback'
    assert result['output']['question_stem']=='What is directly above 设置?'
    assert all(result['output'][k]==row()['options'][k] for k in 'ABCD')
    assert result['components']['options_full_pipeline_failed']


def test_empty_stem_referents_still_localize_all_options_without_alignment_call():
    backend=Backend(full_output());result=pipeline.hybrid(row(),[],backend)
    assert result['status']=='success' and result['edits']==[]
    assert [c['stage'] for c in backend.calls]==['full']


def test_hybrid_refuses_option_spans_and_keeps_original_text_control_inventory_free():
    with pytest.raises(ValueError,match='option referents'):
        pipeline.hybrid(row(),[dict(field='A')],Backend())
    backend=Backend({'translations':{refs()[0]['span_id']:'设置'}},full_output())
    pipeline.hybrid(row(),refs(),backend)
    assert all('target_gui_visible_strings' not in c['user'] for c in backend.calls)


def test_paired_failure_comparison_counts_both_recovery_and_new_failures():
    hybrid='TS_QSEL_OFULL_GUI_AUTO';baseline='TS_SEL_GUI_AUTO';full='TS_FULL_GUI'
    labels={p:{'parallel_id':p} for p in ['p1','p2']}
    component=dict(stem_extraction_failed=False,stem_alignment_failed=False,options_full_pipeline_failed=False,stem_changed=True,options_changed=4)
    rewritten={hybrid:[dict(pair_id='p1',extracted_referents=[],components=component),dict(pair_id='p2',extracted_referents=None,components={**component,'stem_extraction_failed':True})],
               baseline:[dict(pair_id='p1',extracted_referents=None),dict(pair_id='p2',extracted_referents=[])]}
    values={hybrid:dict(p1=1,p2=0),baseline:dict(p1=0,p2=1),full:dict(p1=0,p2=0)}
    result=hybrid_comparisons(rewritten,values,labels)[hybrid]
    assert result['extraction_comparison']['all_field_failed_stem_succeeded']==1
    assert result['extraction_comparison']['all_field_succeeded_stem_failed']==1
    assert result['contrasts'][baseline]['recovery']==result['contrasts'][baseline]['regression']==1
