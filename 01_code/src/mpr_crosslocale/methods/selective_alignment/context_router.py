"""Protect aligned referents while requesting context translation; no pivot fitting on evaluation."""
import json
from .schemas import FIELDS
from .validation import validate_full


def route_context(aligned, edits, translate, pivot):
    protected=dict(aligned);saved={}; shifts={f:0 for f in FIELDS}
    for i,e in enumerate(sorted(edits,key=lambda e:(e['field'],e['start']))):
        key=f'__GCSA_REF_{i}__'
        if any(key in v for v in aligned.values()):raise ValueError('Placeholder collision')
        f=e['field'];start=e['start']+shifts[f];end=start+len(e['replacement'])
        if protected[f][start:end]!=e['replacement']:raise ValueError('Aligned edit offset mismatch')
        saved[key]=(f,e['replacement']);protected[f]=protected[f][:start]+key+protected[f][end:]
        shifts[f]+=len(key)-(e['end']-e['start'])
    raw=translate('Translate non-placeholder context into '+pivot+'. Preserve every placeholder exactly in its original field. Preserve spatial directions, adjacency, negation and numbers. Return JSON of question_stem,A,B,C,D only. Data: '+json.dumps(protected,ensure_ascii=False))
    output=json.loads(raw)
    validate_full(protected,output)
    for key,(field,text) in saved.items():
        if output[field].count(key)!=1 or sum(v.count(key) for v in output.values())!=1:raise ValueError('Lost/moved/duplicated placeholder')
        output[field]=output[field].replace(key,text)
    if any('__GCSA_REF_' in v for v in output.values()):raise ValueError('Unexpected placeholder')
    return output
