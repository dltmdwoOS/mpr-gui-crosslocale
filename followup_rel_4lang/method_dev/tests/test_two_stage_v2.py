import ast
import hashlib
import json
from pathlib import Path
import pytest

from followup_rel_4lang.method_dev.two_stage_v2 import legacy,pipeline,prompts
from followup_rel_4lang.method_dev.two_stage_v2.backend import Backend
from mpr_crosslocale.methods.selective_alignment.schemas import fields


def row():
    return dict(pair_id='rel::test::en::zh',parallel_id='rel::test',source_language='en',gui_language='zh',
        image_path='unused.png',image_sha256='unused',question_stem='Which element is directly above Settings?',
        options=dict(A='Privacy',B='Home',C='Help',D='Exit'),option_order=list('ABCD'))


def translated():
    return {'question_stem':'哪个元素位于设置正上方？','options':dict(A='隐私',B='主页',C='帮助',D='退出')}


class Scripted:
    limits={'inventory_repair':3072}
    def __init__(self,*outputs):self.outputs=list(outputs);self.calls=[]
    def __call__(self,stage,role,system,user,**kwargs):
        self.calls.append(dict(stage=stage,role=role,system=system,user=user,**kwargs))
        raw=self.outputs.pop(0)
        return {'raw_output':json.dumps(raw,ensure_ascii=False) if not isinstance(raw,str) else raw,'output_tokens':0}


def refs():
    r=row();text='Settings';start=r['question_stem'].index(text)
    return [dict(span_id=f'question_stem:{start}:{start+len(text)}',field='question_stem',text=text,start=start,end=start+len(text),kind='label')]


def test_all_vendored_symbols_match_original_source_segments():
    directory=Path(legacy.__file__).parent;source=Path(legacy.__file__).read_text()
    manifest=json.loads((directory/'legacy_manifest.json').read_text());found={}
    for node in ast.parse(source).body:
        targets=[node.name] if isinstance(node,ast.FunctionDef) else [t.id for t in node.targets if isinstance(t,ast.Name)] if isinstance(node,ast.Assign) else [node.target.id] if isinstance(node,ast.AnnAssign) and isinstance(node.target,ast.Name) else []
        for name in targets:
            if name in manifest['symbols']:found[name]=hashlib.sha256(ast.get_source_segment(source,node).encode()).hexdigest()
    assert set(found)==set(manifest['symbols'])
    assert all(value==manifest['symbols'][name]['sha256'] for name,value in found.items())


def test_inventory_uses_exact_initial_and_repair_messages_without_query():
    backend=Scripted('truncated',{'visible_strings':['  Settings ','Settings','搜索']})
    result=pipeline.inventory(row(),backend)
    assert result['status']=='success' and len(result['visible_strings'])==2
    assert backend.calls[0]['system']==legacy.INVENTORY_SYSTEM_PROMPT
    assert backend.calls[0]['user']==legacy.INVENTORY_USER_PROMPT
    assert backend.calls[1]['system']==legacy.INVENTORY_REPAIR_SYSTEM_PROMPT
    assert backend.calls[1]['user']==legacy.INVENTORY_USER_PROMPT+legacy.INVENTORY_REPAIR_SUFFIX
    assert all('Privacy' not in call['user'] and set(call['image'])=={'image_path','image_sha256'} for call in backend.calls)


def test_legacy_parser_does_not_apply_the_old_search_eighty_string_rejection():
    backend=Scripted({'visible_strings':[f'Label{i}' for i in range(81)]})
    assert len(pipeline.inventory(row(),backend)['visible_strings'])==81


def test_failed_inventory_after_repair_is_explicit_empty_evidence():
    result=pipeline.inventory(row(),Scripted('bad','bad'))
    assert result['status']=='failed_after_repair' and result['visible_strings']==[]
    assert len(result['attempts'])==2


def test_full_gui_receives_complete_mcq_inventory_and_legacy_prompt():
    backend=Scripted(translated());inv={'visible_strings':['设置','隐私','主页','帮助','退出']}
    result=pipeline.full(row(),backend,inv)
    assert result['status']=='success'
    assert backend.calls[0]['system']==legacy.LEXICAL_SYSTEM_PROMPT
    assert backend.calls[0]['user']==legacy.build_lexical_user_prompt(prompts.original(row(),inv))
    assert 'Copy such target-locale wording exactly' in backend.calls[0]['system']
    assert 'target_gui_visible_strings' in backend.calls[0]['user'] and 'Privacy' in backend.calls[0]['user']


def test_full_structure_repair_keeps_legacy_payload_and_instructions():
    inv={'visible_strings':['设置']};backend=Scripted('bad',translated())
    result=pipeline.full(row(),backend,inv)
    assert result['status']=='success' and [c['stage'] for c in backend.calls]==['full','full_repair']
    assert backend.calls[1]['user']==legacy.build_lexical_repair_prompt(prompts.original(row(),inv),'bad',['invalid_json:Expecting value'])


def test_full_semantic_repair_requires_a_strict_improvement():
    unchanged={'question_stem':row()['question_stem'],'options':row()['options']}
    backend=Scripted(unchanged,translated())
    result=pipeline.full(row(),backend,{'visible_strings':['设置']})
    assert result['semantic_repair_accepted'] is True
    assert backend.calls[-1]['stage']=='full_semantic_repair'
    backend=Scripted(unchanged,'bad')
    result=pipeline.full(row(),backend,{'visible_strings':['设置']})
    assert result['semantic_repair_accepted'] is False and result['output']==fields(row())


def test_full_failure_is_kept_as_original_not_dropped():
    result=pipeline.full(row(),Scripted('bad','bad'),{'visible_strings':[]})
    assert result['status']=='fallback_original' and result['output']==fields(row())


def test_text_full_control_exposes_no_inventory():
    backend=Scripted(translated());pipeline.full(row(),backend)
    assert backend.calls[0]['system']==legacy.SYSTEM_PROMPT
    assert 'target_gui_visible_strings' not in backend.calls[0]['user']


def test_selective_gui_gets_full_context_and_rewrites_only_fixed_span():
    ref=refs()[0];backend=Scripted({'translations':{ref['span_id']:'设置'}})
    result=pipeline.selective(row(),[ref],backend,{'visible_strings':['设置']})
    assert result['output']=={**fields(row()),'question_stem':'Which element is directly above 设置?'}
    user=backend.calls[0]['user']
    assert 'target_gui_visible_strings' in user and 'Privacy' in user and 'directly above Settings' in user
    assert all(word not in user for word in ('gold_answer','bbox','ref_id','oracle_span'))
    assert 'Translate the complete MCQ' not in backend.calls[0]['system']


def test_selective_membership_and_missing_ids_trigger_one_explicit_repair():
    ref=refs()[0];backend=Scripted({'translations':{ref['span_id']:'invented'}},{'translations':{ref['span_id']:None}})
    result=pipeline.selective(row(),[ref],backend,{'visible_strings':['设置']})
    assert result['status']=='no_op_no_edits' and len(backend.calls)==2
    assert backend.calls[1]['stage']=='selective_repair'
    assert 'not a verbatim inventory member' in backend.calls[1]['user']
    result=pipeline.selective(row(),[ref],Scripted({'translations':{}},{'translations':{}}),{'visible_strings':[]})
    assert result['status']=='fallback_original'


def test_text_selective_control_uses_same_source_span_without_inventory():
    ref=refs()[0];backend=Scripted({'translations':{ref['span_id']:'设置'}})
    result=pipeline.selective(row(),[ref],backend)
    assert result['status']=='success' and 'target_gui_visible_strings' not in backend.calls[0]['user']


def test_method_input_rejects_answers_and_reference_targets():
    contaminated={**row(),'gold_answer':'A'}
    with pytest.raises(ValueError,match='allowlist'):pipeline.full(contaminated,Scripted(),{'visible_strings':[]})


def test_backend_mock_records_distinct_initial_and_repair_output_budgets(tmp_path):
    cfg=json.loads((Path(legacy.__file__).parent.parent/'configs/two_stage_v2.json').read_text())
    backend=Backend(cfg,Path('/home/jovyan/seungjae/mpr-gui-crosslocale'),tmp_path,mock=True)
    image={'image_path':'unused.png','image_sha256':'unused'}
    first=backend('inventory','inventory',legacy.INVENTORY_SYSTEM_PROMPT,legacy.INVENTORY_USER_PROMPT,image=image)
    repair=backend('inventory_repair','inventory',legacy.INVENTORY_REPAIR_SYSTEM_PROMPT,legacy.INVENTORY_USER_PROMPT+legacy.INVENTORY_REPAIR_SUFFIX,image=image)
    assert first['generation']['max_new_tokens']==768 and repair['generation']['max_new_tokens']==3072
    assert first['cache_key']!=repair['cache_key']
    assert first['execution_mode']=='mock'
