import json
import pytest
from followup_rel_4lang.method_dev.scripts import update_two_stage_results as report
from mpr_crosslocale.methods.selective_alignment.schemas import digest


def test_snapshot_ignores_only_the_current_unterminated_write(tmp_path,monkeypatch):
    monkeypatch.setattr(report,'REPO',tmp_path)
    path=tmp_path/'live.jsonl';path.write_bytes(b'{"pair_id":"complete"}\n{"pair_id":"par')
    rows,meta=report.snapshot_lines(path)
    assert rows==[{'pair_id':'complete'}] and meta['complete_lines']==1


def test_incomplete_paired_inference_is_not_accuracy_even_if_transform_finished():
    originals={'p1':{},'p2':{}}
    labels={p:{'parallel_id':p,'split':'main','gold_answer':'A'} for p in originals}
    rows=[dict(pair_id=p,condition=c,execution_mode='gpu',status='success',parsed_generated_label='A') for p,c in [('p1','O'),('p2','O'),('p1','TS_FULL_GUI')]]
    assert report.accuracy_if_complete(rows,originals,labels,'TS_FULL_GUI') is None
    rows.append(dict(pair_id='p2',condition='TS_FULL_GUI',execution_mode='gpu',status='failed',parsed_generated_label='A'))
    result=report.accuracy_if_complete(rows,originals,labels,'TS_FULL_GUI')
    assert result['n']==2 and result['correct']==1
    assert result['vs_O']['regression']==1
    with pytest.raises(ValueError,match='Duplicate'):
        report.accuracy_if_complete(rows+[rows[0]],originals,labels,'TS_FULL_GUI')


def test_source_span_metrics_deduplicate_gui_pairs():
    base=dict(parallel_id='item',source_language='en',question_stem='Settings',options=dict(A='Home',B='Help',C='Exit',D='About'))
    rows=[dict(base,pair_id='p1'),dict(base,pair_id='p2')]
    span=dict(field='question_stem',start=0,end=8)
    failed=dict(status='failed',referents=None,attempts=[{},{}],failure_fields=['A'])
    good=dict(status='success',referents=[span],attempts=[{}],failure_fields=[])
    all_fields={digest(report.prompts.extraction_payload(rows[0])):failed}
    stem={digest(report.prompts.extraction_payload(rows[0],stem_only=True)):good}
    result=report.source_stats(rows,all_fields,stem,{'p1':[span],'p2':[span]})
    assert result['source_mcqs']==1
    assert result['scopes']['stem_only']['stem_spans']['tp']==1
    assert result['paired']['failed->success']==1
    assert result['scopes']['all_fields']['option_only_failed']==1
