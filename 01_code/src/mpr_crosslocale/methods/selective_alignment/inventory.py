"""Query-blind inventory parsing; normalization ported from rq4_gui_lexical."""
import json
import unicodedata
from .schemas import digest


def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC',text).split()).casefold()


def parse_inventory(raw):
    try:
        data=json.loads(raw)
        if set(data) != {'visible_strings'} or not isinstance(data['visible_strings'],list):
            raise ValueError('Expected visible_strings array')
        originals=data['visible_strings']
        if len(originals)>80 or any(not isinstance(s,str) or not s.strip() for s in originals):
            raise ValueError('Invalid inventory entry/count')
        canonical={}
        for text in originals:
            cleaned=' '.join(unicodedata.normalize('NFKC',text).split())
            canonical.setdefault(normalize(text),{'text':text,'normalized':cleaned})
        entries=[canonical[k] for k in sorted(canonical)]
        return {'status':'success' if entries else 'empty','raw_output':raw,'original_strings':originals,
                'entries':entries,'inventory_sha256':digest(entries),'errors':[]}
    except (ValueError,TypeError,KeyError) as exc:
        return {'status':'failed','raw_output':raw,'original_strings':[],'entries':[],
                'inventory_sha256':digest([]),'errors':[str(exc)]}
