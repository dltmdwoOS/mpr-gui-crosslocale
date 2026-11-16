"""Source-span intervention tests; no GPU and no oracle target expressions."""
import copy
import json

import pytest

from followup_rel_4lang.method_dev.scripts import run_oracle_exact as oracle
from mpr_crosslocale.methods.selective_alignment.inventory import parse_inventory
from mpr_crosslocale.methods.selective_alignment.referent_extractor import resolve_referents
from mpr_crosslocale.methods.selective_alignment.schemas import fields, render


def sample():
    return dict(pair_id='rel::test::en::zh', parallel_id='rel::test',
                source_language='en', gui_language='zh', image_path='unused.png',
                image_sha256='unused', question_stem="Which is below 'Search' and not 'Search'?",
                options=dict(A='Adults', B='帮助 帮助', C='Home', D='Cancel'),
                option_order=list('ABCD'))


def annotation(row, *selections):
    spans=[]
    for field, text, occurrence in selections:
        offset=0
        for _ in range(occurrence+1):
            start=fields(row)[field].index(text, offset)
            offset=start+len(text)
        spans.append(dict(field=field, text=text, start=start, end=offset,
                          span_id='old-gold-id', ref_id='unused-parallel-id'))
    return dict(pair_id=row['pair_id'], oracle_span=True, referents=spans)


def test_oracle_uses_automatic_id_order_and_utf8_offsets():
    row=sample()
    selections=[('question_stem','Search',1),('B','帮助',1),('A','Adults',0)]
    refs=oracle.source_refs(row, annotation(row,*selections))
    automatic=resolve_referents(row,json.dumps({'referents':[
        dict(field=f,text=t,occurrence=o) for f,t,o in selections]}))
    assert refs==automatic
    assert refs[1]['utf8_start']==7
    assert refs[1]['occurrence']==1
    assert all('ref_id' not in ref for ref in refs)


@pytest.mark.parametrize('change', ['offset','overlap','target','answer','bbox','pair'])
def test_invalid_or_leaking_source_annotations_fail_closed(change):
    row=sample();gold=annotation(row,('A','Adults',0))
    if change=='offset':gold['referents'][0]['start']=1
    elif change=='overlap':gold['referents'].append(copy.deepcopy(gold['referents'][0]))
    elif change=='pair':gold['pair_id']='another-pair'
    else:gold['referents'][0][{'target':'replacement','answer':'gold_answer','bbox':'bbox'}[change]]='forbidden'
    with pytest.raises(ValueError):oracle.source_refs(row,gold)


def test_rewrite_uses_unchanged_translation_interface_and_deterministic_edit():
    row=sample();refs=oracle.source_refs(row,annotation(row,('A','Adults',0)))
    calls=[]
    def backend(stage,prompt,payload):
        calls.append(stage)
        assert stage=='translate'
        assert set(payload)=={'source_language','target_language','referents'}
        assert payload['referents']==[dict(span_id='A:0:6',field='A',text='Adults')]
        assert 'unused-parallel-id' not in json.dumps(payload)
        return json.dumps({'A:0:6':'成人'})
    inventory=parse_inventory('{"visible_strings":["成人"]}')
    result=oracle.rewrite(row,'GUI_EXACT',backend,refs,inventory)
    assert calls==['translate']
    assert result['output']=={**fields(row),'A':'成人'}
    assert result['status']=='success'


def test_inventory_failure_and_strict_fallback_remain_unchanged():
    row=sample();refs=oracle.source_refs(row,annotation(row,('A','Adults',0)))
    failed=parse_inventory('truncated JSON')
    result=oracle.rewrite(row,'GUI_EXACT',lambda *_:'{"A:0:6":"成人"}',refs,failed)
    assert result['output']==fields(row) and result['status']=='no_op_no_edits'
    assert result['details']['matches'][0]['reason']=='inventory_empty_or_failed'
    result=oracle.rewrite(row,'GUI_EXACT',lambda *_:'{"wrong-id":"成人"}',refs,failed)
    assert result['output']==fields(row) and result['status']=='fallback_original'


def test_queue_preserves_automatic_candidate_groups_and_option_order():
    row=sample();originals={row['pair_id']:row};labels={row['pair_id']:{'gold_answer':'D'}}
    result={**row,'condition':oracle.CONDITION,'modified_question':render(fields(row))}
    queue=[r for r in oracle.build_queue([result],originals,labels) if r['condition']==oracle.CONDITION]
    assert len(queue)==1 and queue[0]['question_raw'].endswith('D: Cancel')
    assert queue[0]['pair_id']==row['pair_id']
    with pytest.raises(ValueError,match='identity'):
        oracle.build_queue([{**result,'option_order':list('BACD')}],originals,labels)


def test_mock_predictions_cannot_become_empirical_results(tmp_path):
    row=sample();work=tmp_path/'work';trial=tmp_path/'trial';prediction=tmp_path/'prediction'
    for path in [work,trial,prediction]:path.mkdir()
    labels={r['pair_id']:r for r in oracle.read(oracle.ROOT/'artifacts/dataset_audit/evaluation_labels_PRIVATE.jsonl')}
    oracle.write(work/'plan.json',{'labels_sha256':oracle.digest(labels)})
    oracle.jsonl(trial/'rewritten.jsonl',[row])
    oracle.jsonl(prediction/'predictions.jsonl',[dict(pair_id=row['pair_id'],execution_mode='mock')])
    with pytest.raises(ValueError,match='Mock predictions'):
        oracle.summarize(work,trial,prediction,mock=False)
    assert not (work/'results.json').exists()


def test_cache_seed_is_read_through_and_does_not_overwrite_old_results(tmp_path):
    base=tmp_path/'base';old=base/'cache';new=tmp_path/'new'
    old.mkdir(parents=True)
    oracle.write(old/'translation.json',dict(stage='translate',raw_output='unchanged'))
    oracle.write(old/'inventory.json',dict(stage='inventory'))
    before=(old/'translation.json').read_bytes()
    assert oracle.seed_translation_cache(base,new)==1
    assert (new/'translation.json').is_symlink()
    assert not (new/'inventory.json').exists()
    assert oracle.seed_translation_cache(base,new)==0
    assert (old/'translation.json').read_bytes()==before


def test_report_formatter_uses_paired_references_with_synthetic_outputs(tmp_path,monkeypatch):
    """Pure fixture test: generated tables here are not experimental measurements."""
    import reference_comparison
    root=tmp_path/'root';data=root/'artifacts/dataset_audit';data.mkdir(parents=True)
    row=sample();labels={row['pair_id']:dict(pair_id=row['pair_id'],parallel_id=row['parallel_id'],split='main',gold_answer='B')}
    oracle.jsonl(data/'evaluation_labels_PRIVATE.jsonl',list(labels.values()))
    monkeypatch.setattr(oracle,'ROOT',root)
    work=tmp_path/'work';trial=tmp_path/'trial';prediction=tmp_path/'prediction';automatic=tmp_path/'automatic';base=tmp_path/'base'
    for d in [work,trial,prediction,automatic,base/'plan']:d.mkdir(parents=True)
    for cohort in oracle.COHORTS:oracle.jsonl(base/'plan'/(cohort+'.jsonl'),[row])
    question=render(fields(row));rewritten={**row,'modified_question':question,'generation_status':'no_op_no_edits','details':{},'edits':[]}
    oracle.jsonl(work/'inputs.jsonl',[row]);oracle.jsonl(trial/'rewritten.jsonl',[rewritten]);oracle.jsonl(automatic/'rewritten.jsonl',[rewritten])
    auto=dict(pair_id=row['pair_id'],status='success',parsed_generated_label='B')
    oracle.jsonl(automatic/'predictions.jsonl',[dict(auto,condition=c) for c in ['O','GUI_EXACT']])
    oracle.jsonl(prediction/'predictions.jsonl',[dict(auto,condition=oracle.CONDITION,parsed_generated_label='A',execution_mode='gpu')])
    oracle.write(work/'plan.json',dict(cohort='screen',labels_sha256=oracle.digest(labels),base_run=str(base),automatic_trial=str(automatic),automatic_predictions=str(automatic),
        baseline_contract=dict(model_config={},baseline_contract_sha256='fixture')))
    def references(*args):
        return {c:{row['pair_id']:auto} for c in ['T_REF','R_REF','F_REF']},{'fixture':True},{}
    monkeypatch.setattr(reference_comparison,'load_references',references)
    oracle.summarize(work,trial,prediction,mock=False)
    result=json.loads((work/'results.json').read_text())
    assert result['primary_pairs']==1
    assert result['correct']=={'Oracle':0,'Automatic':1,'O':1,'T_REF':1,'R_REF':1,'F_REF':1}
    assert result['contrasts']['Automatic']['regression']==1
    assert result['prediction_changes_without_question_change']==1
    assert result['by_gui']['zh']['correct']['Oracle']==0
    assert oracle.read(work/'paired_outcomes.jsonl')[0]['transition']=='regression'
    assert 'F_REF' in (work/'REPORT_KO.md').read_text()
