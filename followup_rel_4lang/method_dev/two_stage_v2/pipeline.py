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


def extract(row,backend):
    validate_input(row);attempts=[];errors=[];raw=''
    for repair in [False,True]:
        user=prompts.extraction_user(row,raw if repair else None,errors)
        result=backend('extract_repair' if repair else 'extract','text',prompts.EXTRACT_SYSTEM,user)
        raw=result['raw_output']
        try:refs=resolve_referents(row,raw);errors=[]
        except (ValueError,KeyError,TypeError) as exc:refs=None;errors=[str(exc)]
        attempts.append({**result,'errors':errors})
        if not errors:break
    return {'status':'failed' if errors else 'success','referents':refs,'attempts':attempts,'errors':errors}


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
