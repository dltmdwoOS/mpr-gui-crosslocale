"""Model-independent transformation logic. No gold/dataset readers."""
import json
from . import legacy,prompts
from mpr_crosslocale.methods.selective_alignment.schemas import validate_input,fields
from mpr_crosslocale.methods.selective_alignment.referent_extractor import resolve_referents
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits


def inventory(row,backend):
    """Only screenshot identity reaches the model. Original initial and repair messages."""
    attempts=[];strings=[];errors=[];events=[]
    for repair in [False,True]:
        system=legacy.INVENTORY_REPAIR_SYSTEM_PROMPT if repair else legacy.INVENTORY_SYSTEM_PROMPT
        user=legacy.INVENTORY_USER_PROMPT+(legacy.INVENTORY_REPAIR_SUFFIX if repair else '')
        result=backend('inventory_repair' if repair else 'inventory','inventory',system,user,image={'image_path':row['image_path'],'image_sha256':row['image_sha256']})
        parsed,errors,events=legacy.parse_visible_string_output_detailed(result['raw_output'])
        if repair and errors and result['output_tokens']==backend.limits['inventory_repair']:
            recovered,recovery_events=legacy.recover_truncated_repetition_prefix(result['raw_output'])
            if recovered is not None:parsed=recovered;errors=[];events=recovery_events
        attempts.append({**result,'errors':errors,'normalization_events':events})
        if not errors and parsed is not None:strings=parsed;break
    return {'status':'failed_after_repair' if errors else 'success','visible_strings':legacy.canonicalize_visible_strings(strings),
            'original_strings':strings,'attempts':attempts,'errors':errors,'query_content_exposed':False}


def extraction_failure_fields(row,raw,*,stem_only=False):
    """Localize schema/offset validation failures without another model call."""
    try:
        response=json.loads(raw)
        if not isinstance(response,dict) or set(response)!={'referents'} or not isinstance(response['referents'],list) or any(not isinstance(r,dict) for r in response['referents']):return ['schema']
        failed=[]
        for field in sorted({str(r.get('field','schema')) for r in response['referents']}):
            group=[r for r in response['referents'] if str(r.get('field','schema'))==field]
            try:
                if stem_only and field!='question_stem':raise ValueError('Forbidden field')
                resolve_referents(row,json.dumps({'referents':group},ensure_ascii=False))
            except (ValueError,KeyError,TypeError):failed.append(field)
        return failed or ['schema']
    except (ValueError,KeyError,TypeError):return ['schema']


def extract(row,backend,*,stem_only=False):
    validate_input(row);attempts=[];errors=[];raw=''
    for repair in [False,True]:
        user=prompts.extraction_user(row,raw if repair else None,errors,stem_only=stem_only)
        stage=('extract_stem_repair' if repair else 'extract_stem') if stem_only else ('extract_repair' if repair else 'extract')
        result=backend(stage,'text',prompts.EXTRACT_STEM_SYSTEM if stem_only else prompts.EXTRACT_SYSTEM,user)
        raw=result['raw_output']
        try:
            if stem_only:
                response=json.loads(raw)
                if not isinstance(response,dict) or not isinstance(response.get('referents'),list) or any(not isinstance(r,dict) or r.get('field')!='question_stem' for r in response['referents']):raise ValueError('Stem-only extraction must return only question_stem referents')
            refs=resolve_referents(row,raw);errors=[]
        except (ValueError,KeyError,TypeError) as exc:refs=None;errors=[str(exc)]
        failure_fields=extraction_failure_fields(row,raw,stem_only=stem_only) if errors else []
        attempts.append({**result,'errors':errors,'failure_fields':failure_fields})
        if not errors:break
    return {'status':'failed' if errors else 'success','referents':refs,'attempts':attempts,'errors':errors,'failure_fields':failure_fields}


def full(row,backend,inv=None):
    validate_input(row);source=prompts.original(row,inv);gui=inv is not None;attempts=[]
    system=legacy.LEXICAL_SYSTEM_PROMPT if gui else legacy.SYSTEM_PROMPT
    initial=legacy.build_lexical_user_prompt if gui else legacy.build_user_prompt
    repair=legacy.build_lexical_repair_prompt if gui else legacy.build_repair_prompt
    semantic=legacy.build_lexical_semantic_repair_prompt if gui else legacy.build_semantic_repair_prompt
    semantic_flags=legacy.lexical_semantic_flags if gui else legacy.semantic_diagnostic_flags
    parsed=None;errors=[];raw='';diagnostics=[]
    for retry in [False,True]:
        result=backend('full_repair' if retry else 'full','text',system,repair(source,raw,errors) if retry else initial(source))
        raw=result['raw_output'];parsed,errors,diagnostics=legacy.validate_lexical_structured_output(raw,source)
        attempts.append({**result,'hard_errors':errors,'diagnostics':diagnostics})
        if not errors:break
    if errors:return {'output':fields(row),'edits':[],'status':'fallback_original','attempts':attempts,'errors':errors}
    flags=semantic_flags(source,parsed);reasons=legacy.semantic_repair_reasons(source,parsed,flags);semantic_accepted=False
    if reasons:
        result=backend('full_semantic_repair','text',system,semantic(source,raw,reasons))
        candidate,hard,diag=legacy.validate_lexical_structured_output(result['raw_output'],source)
        candidate_reasons=legacy.semantic_repair_reasons(source,candidate,semantic_flags(source,candidate)) if not hard else reasons
        semantic_accepted=legacy.should_accept_semantic_repair(reasons,hard,candidate_reasons)
        attempts.append({**result,'hard_errors':hard,'diagnostics':diag,'semantic_reasons':candidate_reasons,'accepted':semantic_accepted})
        if semantic_accepted:parsed=candidate;reasons=candidate_reasons;diagnostics=diag
    output={'question_stem':parsed['question_stem'],**parsed['options']}
    return {'output':output,'edits':[],'status':'success','attempts':attempts,'errors':[],'diagnostics':diagnostics,'semantic_reasons':reasons,'semantic_repair_accepted':semantic_accepted}


def validate_selective(row,refs,raw,inv=None):
    response=json.loads(raw)
    if not isinstance(response,dict) or set(response)!={'translations'} or not isinstance(response['translations'],dict):raise ValueError('Expected translations object')
    mapping=response['translations']
    if set(mapping)!={r['span_id'] for r in refs}:raise ValueError('Missing or extra span IDs')
    edits=[]
    for ref in refs:
        target=mapping[ref['span_id']]
        if target is None:continue
        if not isinstance(target,str) or not target.strip():raise ValueError('Invalid target value')
        if inv is not None and target not in inv['visible_strings']:raise ValueError('Target is not a verbatim inventory member')
        if target!=ref['text']:edits.append({**ref,'replacement':target})
    return apply_edits(row,edits),edits


def selective(row,refs,backend,inv=None):
    validate_input(row)
    if refs is None:return {'output':fields(row),'edits':[],'status':'fallback_original','attempts':[],'errors':['source_extraction_failed']}
    if not refs:return {'output':fields(row),'edits':[],'status':'no_op_no_referents','attempts':[],'errors':[]}
    system=prompts.SELECTIVE_GUI_SYSTEM if inv is not None else prompts.SELECTIVE_TXT_SYSTEM
    attempts=[];errors=[];raw=''
    for retry in [False,True]:
        result=backend('selective_repair' if retry else 'selective','text',system,prompts.selective_user(row,refs,inv,raw if retry else None,errors))
        raw=result['raw_output']
        try:out,edits=validate_selective(row,refs,raw,inv);errors=[]
        except (ValueError,TypeError,KeyError) as exc:errors=[str(exc)]
        attempts.append({**result,'errors':errors})
        if not errors:return {'output':out,'edits':edits,'status':'success' if edits else 'no_op_no_edits','attempts':attempts,'errors':[]}
    return {'output':fields(row),'edits':[],'status':'fallback_original','attempts':attempts,'errors':errors}


def hybrid(row,stem_refs,backend,inv=None):
    """Query selective + options from the exact shared Full recipe, without option spans."""
    validate_input(row)
    if stem_refs is not None and any(r['field']!='question_stem' for r in stem_refs):raise ValueError('Hybrid received option referents')
    # Both stages receive the original MCQ, never each other's translated output.
    stem=selective(row,stem_refs,backend,inv)
    options=full(row,backend,inv)  # Identical prompt/payload; v2 backend reuses Full call cache.
    stem_failed=stem['status']=='fallback_original';options_failed=options['status']=='fallback_original'
    output={'question_stem':stem['output']['question_stem'],**{k:options['output'][k] for k in 'ABCD'}}
    changed=output!=fields(row)
    status='fallback_original' if stem_failed and options_failed else 'partial_fallback' if stem_failed or options_failed else 'success' if changed else 'no_op_no_edits'
    return {'output':output,'edits':stem['edits'],'status':status,
            'attempts':[{**a,'component':'stem_alignment'} for a in stem['attempts']]+[{**a,'component':'options_full_pipeline'} for a in options['attempts']],
            'errors':['stem: '+e for e in stem['errors']]+['options_full: '+e for e in options['errors']],
            'components':{'stem_extraction_failed':stem_refs is None,'stem_alignment_failed':stem_failed and stem_refs is not None,
                          'options_full_pipeline_failed':options_failed,'stem_status':stem['status'],'options_status':options['status'],
                          'stem_changed':output['question_stem']!=row['question_stem'],
                          'options_changed':sum(output[k]!=row['options'][k] for k in 'ABCD'),
                          'options_source_recipe':'TS_FULL_GUI' if inv is not None else 'TS_FULL_TXT',
                          'full_generated_stem_discarded':True},
            'options_diagnostics':options.get('diagnostics',[]),'options_semantic_reasons':options.get('semantic_reasons',[])}
