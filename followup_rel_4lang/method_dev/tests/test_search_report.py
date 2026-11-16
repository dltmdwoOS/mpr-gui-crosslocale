import os,json
import pytest
from followup_rel_4lang.method_dev.scripts.update_search_results_report import completed,update_region,START,END,analyze_predictions,error_kind


def test_only_completed_before_cutoff_is_eligible(tmp_path):
    assert not completed(tmp_path,100)
    marker=tmp_path/'COMPLETE';marker.write_text('done');os.utime(marker,(200,200))
    assert not completed(tmp_path,100) and completed(tmp_path,200)


def test_updates_preserve_manual_notes_and_refuse_unmarked_document():
    report=update_region('', 'first data')+'\n내가 직접 쓴 검토 메모\n'
    updated=update_region(report,'second data')
    assert 'first data' not in updated and 'second data' in updated and '내가 직접 쓴 검토 메모' in updated
    assert updated.count(START)==updated.count(END)==1
    with pytest.raises(ValueError):update_region('manual document without markers','new')
    with pytest.raises(ValueError):update_region(END+START,'new')


def test_report_recomputes_primary_exclusion_and_requires_full_paired_set():
    excluded='rel::5/forest_9.jpg::zh::ru';main='rel::2/x::en::th';pilot='rel::1/y::en::zh'
    labels={p:{'split':'pilot' if p==pilot else 'main','parallel_id':p.rsplit('::',2)[0],'gold_answer':'A'} for p in [excluded,main,pilot]}
    originals={p:{} for p in labels}
    rows=[{'pair_id':p,'condition':c,'execution_mode':'gpu','status':'success','parsed_generated_label':'A' if c=='O' or p!=main else 'B'} for p in labels for c in ['O','GUI_EXACT']]
    result,_,_=analyze_predictions(rows,originals,labels,'GUI_EXACT')
    assert result['groups']['main']=={'n':1,'items':1,'correct':0,'O_correct':1,'recovery':0,'regression':1}
    assert result['groups']['legacy']['n']==1 and result['by_gui']['th']['n']==1
    with pytest.raises(ValueError,match='Incomplete'):analyze_predictions(rows[:-1],originals,labels,'GUI_EXACT')
    with pytest.raises(ValueError,match='Mock'):analyze_predictions([{**r,'execution_mode':'mock'} for r in rows],originals,labels,'GUI_EXACT')


def test_source_span_failure_is_not_misreported_as_json_syntax():
    assert error_kind('Span cannot be recovered from original text')=='원문 text/occurrence 복원 실패'
    assert error_kind("Expecting ',' delimiter: line 2")=='JSON 파싱'


def test_method_narrative_adds_only_completed_scores_and_explains_controls():
    from followup_rel_4lang.method_dev.scripts.update_search_results_report import method_explanation,METHOD_DETAILS,ORDER
    assert set(METHOD_DETAILS)==set(ORDER)
    snapshot={'records':{'screen':{'GUI_FULL':{'groups':{'main':{'correct':7,'n':10,'O_correct':6}}}},'selection':{},'internal_evaluation':{}},'decision':{'evaluation_recipes':['GUI_FULL']}}
    text=method_explanation(snapshot,'GUI_FULL')
    assert '7/10 (70.00%' in text and 'TXT_FULL' in text and '부분 출력' in text
    snapshot['records']['internal_evaluation']['GUI_FULL']={'groups':{'main':{'correct':8,'n':10,'O_correct':6}},'main_changed':9,'main_fallback':1}
    text=method_explanation(snapshot,'GUI_FULL')
    assert '8/10 (80.00%' in text and '변경은 9/10쌍' in text and '오류 fallback은 1쌍' in text
    assert '아직 완료되지' not in text
