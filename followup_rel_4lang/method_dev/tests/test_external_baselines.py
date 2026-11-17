import copy
import json
import sys
from pathlib import Path

import pytest

from followup_rel_4lang.method_dev import external_baselines as methods
from followup_rel_4lang.method_dev.tests.test_visual_selective_rewrite import fixture
from mpr_crosslocale.methods.selective_alignment.schemas import fields


def test_translation_has_source_only_input_and_english_identity_uses_no_lm():
    row=fixture()
    assert methods.translate(row,None)['output']==fields(row)
    row['source_language']='zh';seen=[]
    def backend(stage,role,system,user):
        seen.append(json.loads(user))
        return {'raw_output':json.dumps({'question_stem':'English stem','options':row['options']})}
    result=methods.translate(row,backend)
    assert set(seen[0])=={'source_language','question_stem','options'}
    assert result['output']['question_stem']=='English stem'
    assert not any(k in seen[0] for k in ('gui_language','image_path','gold_answer','inventory'))


def test_translation_repair_once_then_original_fallback_does_not_drop_pair():
    row=fixture();row['source_language']='ru';calls=[];before=copy.deepcopy(row)
    def backend(stage,role,system,user):
        calls.append(stage);return {'raw_output':'{"options":{"A":"x"}}'}
    result=methods.translate(row,backend)
    assert calls==['translate','translate_repair'] and result['status']=='fallback_original'
    assert result['output']==fields(row) and row==before


@pytest.mark.parametrize('raw,expected',[
    ('The original option A is a distractor.\nAnswer: C','C'),
    ('A is near B, but no answer was given.',None),
    ('Answer: B\nThis is an unfinished explanation',None),
    ('Reasoning.\n**Answer: [D]**','D'),('A','A'),('',None)])
def test_clp_parser_requires_final_answer_instead_of_reasoning_option_mentions(raw,expected):
    assert methods.parse_clp_answer(raw)==expected


def test_clp_keeps_two_turn_dialogue_and_image_only_in_solver_turn():
    row=fixture();messages=methods.solver_messages(row,'English interpretation',Path('/repo'))
    assert [m['role'] for m in messages]==['system','user','assistant','user']
    assert messages[2]['content'][0]['text']=='English interpretation'
    assert sum(x['type']=='image' for m in messages for x in m['content'])==1
    assert messages[3]['content'][0]['type']=='image'
    assert methods.alignment_user(row) in messages[1]['content'][0]['text']
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    from run_external_baselines import CLPAdapter
    assert CLPAdapter.build_messages({'messages':messages},'external_clp_dialogue','unused')==messages


def test_gold_annotation_cannot_enter_transform_or_solver_prompts():
    row=fixture();row['gold_answer']='D'
    with pytest.raises(ValueError):methods.source_payload(row)
    with pytest.raises(ValueError):methods.alignment_user(row)
    with pytest.raises(ValueError):methods.solver_messages(row,'alignment',Path('/repo'))
