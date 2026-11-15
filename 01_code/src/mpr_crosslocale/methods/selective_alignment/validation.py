import re
from collections import Counter
from .schemas import FIELDS


def validate_full(source, translated):
    if not isinstance(translated,dict) or set(translated)!=set(FIELDS) or any(not isinstance(v,str) or not v.strip() for v in translated.values()):
        raise ValueError('Full output must contain exactly five nonempty string fields')
    if len({translated[k] for k in 'ABCD'})<4 and len({source[k] for k in 'ABCD'})==4:
        raise ValueError('Duplicate options')
    for f in FIELDS:
        if Counter(re.findall(r'\d+(?:[.,]\d+)?',source[f])) != Counter(re.findall(r'\d+(?:[.,]\d+)?',translated[f])):
            raise ValueError('Numeric values changed')
    return translated
