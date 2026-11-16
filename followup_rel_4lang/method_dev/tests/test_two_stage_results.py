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


def completed_fixture(tmp_path):
    from followup_rel_4lang.method_dev.scripts.two_stage_completed import completed_summary
    from mpr_crosslocale.methods.selective_alignment.schemas import fields,render
    work=tmp_path/'screen';work.mkdir();rewrite=work/'rewrite';infer=work/'infer'
    for path in [rewrite,infer]:
        path.mkdir();(path/'COMPLETE').write_text('done\n')
    def write(path,data):path.write_text(json.dumps(data)+'\n')
    def jsonl(path,rows):path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    def read(path):return [json.loads(l) for l in path.read_text().splitlines()]
    rows=[dict(pair_id=f'p{i}',parallel_id=f'item{i}',source_language='en',gui_language='zh',question_stem='Which Settings?',
               options=dict(A='Home',B='Help',C='Exit',D='About'),image_path='unused.png',image_sha256='unused',option_order=list('ABCD')) for i in (1,2)]
    originals={r['pair_id']:r for r in rows};labels={p:dict(parallel_id=r['parallel_id'],split='main',gold_answer='A') for p,r in originals.items()}
    names=['TS_FULL_GUI','TS_QSEL_OFULL_GUI_AUTO'];contract={'conditions':names,'config':{'downstream':{'fixture':True}}}
    ic=dict(execution_mode='gpu',downstream=contract['config']['downstream'],input_sha256=digest(rows),condition_order=['O',*names])
    write(infer/'contract.json',ic)
    predictions=[dict(pair_id=p,parallel_id=r['parallel_id'],condition=c,execution_mode='gpu',status='success',generated_text='A',parsed_generated_label='A',
                      batch_id=c+':0',batch_size=2,batch_runtime_ms=10,peak_reserved_bytes=1024) for c in ['O',*names] for p,r in originals.items()]
    jsonl(infer/'predictions.jsonl',predictions)
    for c in names:
        jsonl(rewrite/(c+'.jsonl'),[dict(r,modified_question=render(fields(r)),edits=[],extracted_referents=[],status='no_op_no_edits',errors=[],
            components=dict(stem_extraction_failed=False,stem_alignment_failed=False,options_full_pipeline_failed=False,options_changed=0)) for r in rows])
    from followup_rel_4lang.method_dev.scripts.search_pipeline import paired_bootstrap
    saved={'conditions':{c:dict(n=2,correct=2,vs_O=None if c=='O' else paired_bootstrap(dict(p1=1,p2=1),dict(p1=1,p2=1),labels,20261115,10000)) for c in ['O',*names]}}
    write(work/'results.json',saved)
    complete=dict(execution_mode='gpu',rewrite=str(rewrite),predictions=str(infer))
    for stage in ('inventory','extract','extract_stem'):
        p=work/stage;p.mkdir();write(p/'cost.json',dict(wall_seconds=1,calls=1,cache_hits=0,new_runtime_ms=1));complete[stage]=str(p)
    write(rewrite/'cost.json',dict(wall_seconds=1,calls=1,cache_hits=0,new_runtime_ms=1))
    write(work/'COMPLETE.json',complete)
    refs={name:{p:dict(status='success',parsed_generated_label='A') for p in originals} for name in ('T_REF','R_REF','F_REF')}
    return completed_summary,work,contract,originals,labels,read,refs,predictions


def test_completed_report_rechecks_real_rows_and_shared_hybrid_options(tmp_path):
    fn,work,contract,originals,labels,read,refs,_=completed_fixture(tmp_path)
    result=fn(work,contract,originals,labels,read,refs)
    assert result['prediction_rows']==6 and result['primary_pairs']==2
    assert result['hybrid']['TS_QSEL_OFULL_GUI_AUTO']['options_equal_full']
    assert result['inference_batch_seconds']==.03
    path=work/'rewrite/TS_QSEL_OFULL_GUI_AUTO.jsonl';rows=read(path)
    rows[0]['options']['A']='changed'
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    with pytest.raises(ValueError,match='Hybrid options differ'):
        fn(work,contract,originals,labels,read,refs)


def test_completed_marker_cannot_hide_missing_predictions(tmp_path):
    fn,work,contract,originals,labels,read,refs,preds=completed_fixture(tmp_path)
    path=work/'infer/predictions.jsonl';path.write_text(''.join(json.dumps(r)+'\n' for r in preds[:-1]))
    with pytest.raises(ValueError,match='Completed prediction set differs'):
        fn(work,contract,originals,labels,read,refs)
