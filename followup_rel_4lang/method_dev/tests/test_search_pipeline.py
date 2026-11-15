import json,struct
from pathlib import Path
from types import SimpleNamespace
import pytest
from followup_rel_4lang.method_dev.scripts.search_pipeline import shortlist,decide,descriptive,paired_bootstrap,weight_bytes


def test_promotion_preserves_best_and_fast_near_best():
    rows=[{'id':'accurate','accuracy':.8,'method_ms_per_pair':100},{'id':'cheap','accuracy':.795,'method_ms_per_pair':10},{'id':'bad','accuracy':.7,'method_ms_per_pair':1}]
    chosen=shortlist(rows,'accuracy','method_ms_per_pair',2,.01)
    assert [x['id'] for x in chosen]==['accurate','cheap']
    assert decide(rows,.01)['id']=='cheap' and decide(rows,.001)['id']=='accurate'


def test_primary_exclusion_and_pilot_are_not_pooled_for_selection():
    excluded='rel::5/forest_9.jpg::zh::ru';labels={'main':{'split':'main','parallel_id':'m','gold_answer':'B'},'pilot':{'split':'pilot','parallel_id':'p','gold_answer':'A'},excluded:{'split':'main','parallel_id':'e','gold_answer':'B'}}
    # Valid language-pair ID structure for descriptive GUI summaries.
    main='rel::2/x::en::zh';pilot='rel::1/y::en::zh';labels[main]=labels.pop('main');labels[pilot]=labels.pop('pilot')
    rows=[{'pair_id':pid,'condition':c,'execution_mode':'gpu','status':'success','parsed_generated_label':'A'} for pid in labels for c in ('O','GUI_EXACT')]
    result=descriptive(rows,labels,'GUI_EXACT')
    assert result['groups']['main_primary']['n']==1 and result['groups']['main_primary']['accuracy']==0
    assert result['groups']['legacy_pilot']['accuracy']==1
    with pytest.raises(ValueError,match='paired'):descriptive(rows[:-1],labels,'GUI_EXACT')
    with pytest.raises(ValueError,match='Mock'):descriptive([{**r,'execution_mode':'mock'} for r in rows],labels,'GUI_EXACT')


def test_bootstrap_clusters_pairs_by_semantic_item():
    labels={'a':{'parallel_id':'one'},'b':{'parallel_id':'one'}}
    result=paired_bootstrap({'a':1,'b':0},{'a':0,'b':0},labels,17,100)
    assert result['items']==1 and result['pairs']==2 and result['ci95']==[.5,.5]


def test_safetensors_header_counts_data_bytes_without_loading_weights(tmp_path):
    header=json.dumps({'w':{'dtype':'BF16','shape':[8],'data_offsets':[0,16]}}).encode()
    (tmp_path/'model.safetensors').write_bytes(struct.pack('<Q',len(header))+header+bytes(16))
    assert weight_bytes(tmp_path)==16


def test_downstream_token_budget_is_checked_before_device_transfer(monkeypatch):
    from mpr_crosslocale.models.qwen25vl import Qwen25VLAdapter
    import qwen_vl_utils
    monkeypatch.setattr(qwen_vl_utils,'process_vision_info',lambda *a,**k:(None,None))
    class Inputs:
        input_ids=SimpleNamespace(shape=(1,4097))
        def to(self,*a):raise AssertionError('must reject before GPU copy')
    class Processor:
        tokenizer=SimpleNamespace(padding_side='left')
        def apply_chat_template(self,*a,**k):return 'prompt'
        def __call__(self,**kwargs):return Inputs()
    adapter=Qwen25VLAdapter.__new__(Qwen25VLAdapter);adapter.processor=Processor();adapter.model=SimpleNamespace(device='cuda:0');adapter.model_family='qwen3_vl';adapter.max_input_tokens=4096
    with pytest.raises(ValueError,match='budget'):adapter.generate_batch([{'image_paths':[],'question_raw':'x'}],'mpr_label_only_v1',{'max_new_tokens':2})
