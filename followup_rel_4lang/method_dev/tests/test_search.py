import copy,json
import pytest
from mpr_crosslocale.methods.selective_alignment.search import direct_edits,match_edits,rewrite,quoted_referents
from mpr_crosslocale.methods.selective_alignment.schemas import fields
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits
from followup_rel_4lang.method_dev.scripts.build_search_plan import build
from followup_rel_4lang.method_dev.scripts.infer_search_trial import build_queue


def row(item='rel::2/x',q='en',g='zh',sha=None):
    return dict(pair_id=item+'::'+q+'::'+g,parallel_id=item,source_language=q,gui_language=g,image_path='screen.png',image_sha256=sha or item+g,
                question_stem="Which is not below the blue 'Launch' button?",options=dict(A="The 'Account' field",B='Archive 2024.zip',C='Home',D='Cancel'),option_order=list('ABCD'))


def test_grouped_plan_is_reproducible_and_preserves_internal_evaluation():
    assignment={f'rel::2/{i}':'calibration' if i<4 else 'internal_evaluation' for i in range(8)}
    rows=[row(i,q,g) for i in [*assignment,'rel::1/p0','rel::1/p1'] for q,g in [('en','zh'),('zh','en')]]
    split={'items':assignment};before=copy.deepcopy(split);spec={'seed':17,'screen_calibration_items':2,'probe_legacy_items':1,'version':'test'}
    manifest,cohorts=build(rows,split,spec);other,_=build(rows,split,spec)
    assert manifest==other and split==before
    assert len(manifest['screen_calibration_items'])==2 and len(manifest['selection_items'])==2
    assert set(manifest['screen_calibration_items']).isdisjoint(manifest['selection_items'])
    assert not any(assignment.get(r['parallel_id'])=='internal_evaluation' for selected in cohorts.values() for r in selected)
    rows[-1]['image_sha256']=rows[8]['image_sha256']
    with pytest.raises(ValueError,match='duplicate'):build(rows,split,spec)


def test_direct_proposals_preserve_context_and_reject_overlap_and_option_collision():
    r=row();raw=json.dumps({'edits':[{'field':'question_stem','text':'Launch','occurrence':0,'replacement':'启动'}]})
    edits=direct_edits(r,raw);out=apply_edits(r,edits)
    assert out['question_stem']=="Which is not below the blue '启动' button?"
    assert all(out[k]==r['options'][k] for k in 'ABCD')
    with pytest.raises(ValueError):direct_edits(r,'{"edits":[{"field":"question_stem","text":"missing","occurrence":0,"replacement":"x"}]}')
    with pytest.raises(ValueError):direct_edits(r,'{"edits":[{"field":"E","text":"Home","occurrence":0,"replacement":"x"}]}')
    with pytest.raises(ValueError):direct_edits(r,'{"edits":[],"answer":"A"}')
    collision=json.dumps({'edits':[{'field':'C','text':'Home','occurrence':0,'replacement':'Cancel'}]})
    with pytest.raises(ValueError,match='duplicate'):apply_edits(r,direct_edits(r,collision))


def test_inventory_evidence_and_explicit_abstention():
    refs=quoted_referents(row());inv={'entries':[{'text':'启动'}]}
    response={'matches':{r['span_id']:None for r in refs}}
    response['matches'][refs[-1]['span_id']]='invented'
    with pytest.raises(ValueError,match='absent'):match_edits(refs,json.dumps(response),inv)
    response['matches'][refs[-1]['span_id']]=None
    assert match_edits(refs,json.dumps(response),inv)==[]
    del response['matches'][refs[0]['span_id']]
    with pytest.raises(ValueError,match='span IDs'):match_edits(refs,json.dumps(response),inv)


def test_targeted_vlm_gets_all_referents_without_full_relation_question():
    r=row();refs=quoted_referents(r)
    def backend(stage,prompt,payload):
        assert stage=='ground_match'
        assert 'fields' not in payload and 'question_stem' not in payload
        assert {x['span_id'] for x in payload['referents']}=={x['span_id'] for x in refs}
        assert payload['image_sha256']==r['image_sha256']
        assert not {'gold_answer','bbox','reference_mappings'} & payload.keys()
        return json.dumps({'matches':{x['span_id']:None for x in refs}})
    result=rewrite(r,'GUI_TARGETED_VLM',backend,refs)
    assert result['status']=='no_op_no_edits' and result['output']==fields(r)


def test_invalid_proposal_falls_back_instead_of_dropping_pair():
    r=row();result=rewrite(r,'GUI_DIRECT_VLM',lambda *_:'{"edits":[{"field":"A","text":"wrong","occurrence":0,"replacement":"x"}]}')
    assert result['status']=='fallback_original' and result['output']==fields(r)
    assert result['details']['raw_output']


def test_inference_queue_keeps_identity_and_option_order():
    r=row();rewritten={**r,'condition':'GUI_DIRECT_VLM','modified_question':'altered question'}
    queue=build_queue([rewritten],{r['pair_id']:r},{r['pair_id']:{'gold_answer':'B'}})
    assert [x['condition'] for x in queue]==['O','GUI_DIRECT_VLM']
    assert queue[0]['question_raw'].endswith('D: Cancel') and queue[1]['question_raw']=='altered question'
    with pytest.raises(ValueError,match='identity'):build_queue([{**rewritten,'option_order':list('BACD')}],{r['pair_id']:r},{r['pair_id']:{'gold_answer':'B'}})


def test_cache_reuse_is_not_reported_as_new_gpu_measurement(tmp_path):
    from followup_rel_4lang.method_dev.scripts.run_search_trial import CachedBackend
    spec={'model_id':'LM','revision':'pinned','family':'text','path':'unused'}
    cfg={'models':{k:spec for k in ('inventory','translator','referent_extractor')},'max_new_tokens':768}
    backend=CachedBackend(None,cfg,tmp_path,mock=True)
    payload={'source_language':'en','target_language':'zh','referents':[{'span_id':'r','text':'Account'}]}
    first=backend('translate','prompt',payload);second=backend('translate','prompt',payload)
    assert first==second and [c['cache_hit'] for c in backend.calls]==[False,True]
    assert all(c['execution_mode']=='mock' and c['runtime_ms']==0 for c in backend.calls)
    backend('translate','changed prompt',payload)
    assert backend.calls[-1]['cache_hit'] is False


def test_infrastructure_failure_stops_trial_and_retains_failed_call_cost(tmp_path):
    from followup_rel_4lang.method_dev.scripts.run_search_trial import CachedBackend
    from mpr_crosslocale.methods.selective_alignment.search import BackendFailure
    class Broken:
        def __call__(self,*args):raise RuntimeError('simulated device failure')
    spec={'model_id':'LM','revision':'pinned','family':'text','path':'unused'}
    backend=CachedBackend(Broken(),{'models':{'translator':spec},'max_new_tokens':768},tmp_path,mock=True)
    backend.mock=False  # exercise the failure path without querying/allocating a real GPU
    with pytest.raises(BackendFailure):backend('direct_text_edit','prompt',{})
    assert backend.calls[0]['runtime_ms']>=0 and backend.calls[0]['input_tokens'] is None
    assert not list(tmp_path.glob('*.json'))
    with pytest.raises(BackendFailure):rewrite(row(),'TXT_DIRECT_LM',backend)
