from __future__ import annotations
import hashlib
import json
FIELDS = ('question_stem','A','B','C','D')
INPUT_KEYS = {'pair_id','parallel_id','source_language','gui_language','image_path','image_sha256','question_stem','options','option_order'}


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate_input(row):
    if set(row) != INPUT_KEYS:
        raise ValueError('Method input must contain only the allowlisted original fields')
    if row['source_language'] not in ('en','zh','th','ru') or row['gui_language'] not in ('en','zh','th','ru'):
        raise ValueError('Unknown language')
    if list(row['options']) != list('ABCD') or row['option_order'] != list('ABCD'):
        raise ValueError('Option keys/order must be A-D')
    if not isinstance(row['question_stem'],str) or any(not isinstance(v,str) for v in row['options'].values()):
        raise ValueError('All MCQ fields must be strings')
    return row


def fields(row):
    return {'question_stem':row['question_stem'],**row['options']}


def render(value):
    return value['question_stem']+' '+' '.join(f'{k}: {value[k]}' for k in 'ABCD')
