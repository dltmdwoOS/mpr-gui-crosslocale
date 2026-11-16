import pytest
from followup_rel_4lang.method_dev.scripts.reference_comparison import resolve_orcf,index_unique,compare_cohorts


def fixture():
    pid='rel::2/x::en::zh'
    source={'pair_id':pid,'parallel_id':'rel::2/x','source_language':'en','gui_language':'zh','image_path':'followup_rel_4lang/assets/x.png','gold_answer':'A','option_order':list('ABCD')}
    row={'parallel_id':source['parallel_id'],'query_language':'en','gui_language':'zh','question_stem':'目标','options':dict(A='一',B='二',C='三',D='四'),'image_path':'assets/x.png','gold_answer':'A','option_order':list('ABCD')}
    conditions={(pid,'R'):{**row,'equivalent_to_condition':'R'},(pid,'F'):{**row,'equivalent_to_condition':'R'}}
    predictions={(pid,'R'):{'input_id':'rel_orcf::'+pid+'::R','status':'success','parsed_generated_label':'A'}}
    return pid,source,conditions,predictions


def test_f_can_use_only_exact_same_pair_representative():
    pid,source,conditions,predictions=fixture()
    pred,alias=resolve_orcf(pid,'F',conditions,predictions,source)
    assert alias=='R' and pred is predictions[pid,'R']
    conditions[pid,'F']['question_stem']='different'
    with pytest.raises(ValueError,match='identical'):resolve_orcf(pid,'F',conditions,predictions,source)


def test_f_rejects_changed_image_gold_or_option_order():
    for key,value in [('image_path','followup_rel_4lang/assets/other.png'),('gold_answer','B'),('option_order',list('BACD'))]:
        pid,source,conditions,predictions=fixture();source[key]=value
        with pytest.raises(ValueError):resolve_orcf(pid,'F',conditions,predictions,source)


def test_duplicate_attempts_never_silently_overwrite():
    with pytest.raises(ValueError,match='Duplicate'):index_unique([{'id':'p','attempt':1},{'id':'p','attempt':2}],lambda r:r['id'])


def test_reference_missing_pair_is_not_an_implicit_smaller_denominator(tmp_path):
    pid,source,conditions,predictions=fixture()
    refs={key:{pid:{'status':'success','parsed_generated_label':'A'}} for key in ['O_EXP_A','T_REF','R_REF','O_ORCF','R_ORCF','F_REF']}
    refs['F_REF']={}
    outcomes={'screen':{'O':{pid:1},'OTHER':{pid:1}}};anchors={'screen':[{pid:'A'}]};labels={pid:{'split':'main','parallel_id':'rel::2/x','gold_answer':'A'}}
    with pytest.raises(ValueError,match='denominator shrink'):compare_cohorts(refs,{}, {pid:'R'},outcomes,anchors,labels,{},tmp_path,{}, {'seed':1,'bootstrap_replicates':10,'winner':'GUI_EXACT'})
