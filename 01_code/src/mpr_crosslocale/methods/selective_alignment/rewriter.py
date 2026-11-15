from .schemas import FIELDS,fields


def apply_edits(row, edits, *, reject_collisions=True):
    """Offsets are Python character offsets; preserve every unedited character."""
    source=fields(row);result=dict(source);seen=set()
    for field in FIELDS:
        group=sorted((e for e in edits if e['field']==field),key=lambda e:e['start'])
        end=0
        for e in group:
            if (type(e['start']) is not int or type(e['end']) is not int or
                not 0<=e['start']<e['end']<=len(source[field]) or e['start']<end or
                source[field][e['start']:e['end']]!=e['text'] or not isinstance(e['replacement'],str) or not e['replacement']):
                raise ValueError('Invalid/overlapping edit or source offset')
            if e['span_id'] in seen:raise ValueError('Duplicate edit ID')
            seen.add(e['span_id']);end=e['end']
        for e in reversed(group):result[field]=result[field][:e['start']]+e['replacement']+result[field][e['end']:]
    if any(e['field'] not in FIELDS for e in edits):raise ValueError('Unknown edit field')
    if reject_collisions and len({source[k] for k in 'ABCD'})==4 and len({result[k] for k in 'ABCD'})<4:
        raise ValueError('New duplicate options')
    return result
