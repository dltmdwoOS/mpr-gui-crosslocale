import pytest

from followup_rel_4lang.method_dev.scripts.analyze_oracle_exact import (
    correct, gap_diagnostic, stage_metrics, unique,
)


def test_prediction_failure_stays_in_denominator_and_duplicates_fail():
    assert correct({'status':'failed','parsed_generated_label':'A'},'A')==0
    assert correct({'status':'success','parsed_generated_label':None},'A')==0
    with pytest.raises(ValueError,match='Duplicate'):
        unique([{'pair_id':'p'},{'pair_id':'p'}],lambda r:r['pair_id'])


def test_matching_coverage_is_not_source_recall_and_unlogged_spans_are_explicit():
    span={'field':'A','start':0,'end':4}
    rows={'p':{'extracted_referents':[span],'edits':[],'generation_status':'fallback_original','details':{'error':'New duplicate options'}}}
    result=stage_metrics(rows,{'p':[span]})
    assert result['annotation_recall']==1
    assert result['logged_match_decisions']==0 and result['unlogged_referents']==1
    assert result['fallback_reasons']=={'New duplicate options':1}


def test_R_gap_separates_recovered_old_misses_from_new_regressions():
    span={'field':'A','start':0,'end':4}
    def row(refs,status='success',edits=None):
        return {'extracted_referents':refs,'extraction':{'status':status},'edits':edits or [],
                'generation_status':'success','inventory':{'status':'success'},
                'details':{'matches':[{'decision':'abstain'}]}}
    automatic={'p1':row(None,'failed'),'p2':row([]),'p3':row([span]),'p4':row([span])}
    oracle={pid:row([span]) for pid in automatic}
    oracle['p3']['edits']=[{'field':'A'}]
    values={'R_REF':dict.fromkeys(automatic,1),'Automatic':dict(p1=0,p2=0,p3=1,p4=1),'Oracle':dict(p1=1,p2=0,p3=0,p4=1)}
    result=gap_diagnostic(values,automatic,oracle)
    assert result['old_gap']==result['new_gap']==2
    assert result['recovered_old_gap']==result['remaining_old_gap']==result['newly_lost_R_correct']==1
    assert result['old_gap_source_coverage']['추출 검증 실패']=={'n':1,'recovered':1}
    assert result['remaining_observed_states']=={'Exact match 채택 없음':1,'편집 적용 후에도 오답':1}
    assert result['causal_attribution'] is False
