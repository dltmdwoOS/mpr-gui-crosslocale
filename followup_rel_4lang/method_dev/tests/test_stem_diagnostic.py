from followup_rel_4lang.method_dev.scripts.diagnose_stem_only import source_span_state,membership,estimate_eta,batch_seconds


def test_source_boundaries_do_not_confuse_overwide_spans_with_missing_spans():
    gold=[dict(start=10,end=15)]
    assert source_span_state(gold,None)=='extraction_failed'
    assert source_span_state(gold,[dict(start=10,end=15)])=='exact_boundary'
    assert source_span_state(gold,[dict(start=8,end=17)])=='overwide_boundary'
    assert source_span_state(gold,[dict(start=11,end=15)])=='missing_or_partial_span'


def test_R_exact_absence_does_not_automatically_mean_OCR_omission():
    assert membership(['Search'],['SEARCH'],'success')=='exact'
    assert membership(['Search'],['Search places'],'success')=='substring_only'
    assert membership(['Начинающий планта...'],['Начинающий плантатор'],'success')=='ellipsis_prefix_only'
    assert membership(['Search'],[],'failed_after_repair')=='inventory_failed_or_empty'
    assert membership(['Search'],['Nearby'],'success')=='not_found_by_lexical_checks'


def test_ETA_counts_shared_stages_once_and_only_adds_full_for_Hybrid():
    keys=['inventory_seconds_per_image','stem_extract_seconds_per_source','stem_align_seconds_per_pair','stem_infer_seconds_per_pair','O_infer_seconds_per_pair',
          'full_gui_seconds_per_pair','hybrid_infer_seconds_per_pair','full_grid_inventory_wall_seconds_per_image','full_grid_extract_wall_seconds_per_source',
          'full_grid_stem_extract_wall_seconds_per_source','full_grid_rewrite_wall_seconds_per_pair','full_grid_infer_seconds_per_pair']
    result=estimate_eta(dict.fromkeys(keys,1),images=4,sources=4,pairs=12,baseline_overhead_seconds=0)
    assert result['stem_only_plus_O']['hours']==44/3600
    assert result['stem_and_hybrid_plus_O']['hours']==68/3600
    assert result['all_eight_v2_conditions_plus_stem_and_O']['hours']==48/3600
    assert result['stem_and_hybrid_plus_O']['prediction_rows']==36


def test_batch_time_is_not_summed_once_per_prediction_row():
    assert batch_seconds([dict(batch_id='a',batch_runtime_ms=100),dict(batch_id='a',batch_runtime_ms=100),dict(batch_id='b',batch_runtime_ms=50)])==.15
