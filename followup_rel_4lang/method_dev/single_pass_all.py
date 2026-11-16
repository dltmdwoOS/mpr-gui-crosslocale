"""Joint source referent selection and inventory alignment in all MCQ fields."""
import json

from . import single_pass
from mpr_crosslocale.methods.selective_alignment.referent_extractor import resolve_referents
from mpr_crosslocale.methods.selective_alignment.rewriter import apply_edits
from mpr_crosslocale.methods.selective_alignment.schemas import FIELDS, fields, validate_input

CONDITION = 'TS_ALL_SINGLE_PASS_GUI_AUTO'

# Scope/interface changes only; keep the previous stem condition frozen.
_CHANGES = {
    'in the question stem of a multilingual GUI multiple-choice question':
        'in the question stem AND all four options of a multilingual GUI multiple-choice question',
    'In one response, identify the written GUI names in question_stem and select their corresponding target GUI strings. The complete original MCQ is context only: never answer or solve it. Options MUST remain unchanged and MUST NOT be extracted or translated.':
        'In one response, identify the written GUI names in question_stem AND options A, B, C, D and select their corresponding target GUI strings. Never answer or solve the MCQ. Process every field independently, without choosing a correct option. Localize only referent names; preserve the surrounding context of each field.',
    'Find minimal written GUI label/name spans in question_stem,':
        'Find minimal written GUI label/name spans in question_stem AND each option A, B, C, D,',
    'A stem can contain zero, one or multiple names.':
        'Each field can contain zero, one or multiple names. Do not assume every option needs an edit.',
    'copy text EXACTLY from the ORIGINAL question_stem, in its ORIGINAL language. text is what code must find in the original stem; NEVER put the translated target string in text.':
        'specify field as question_stem, A, B, C or D and copy text EXACTLY from that ORIGINAL field, in its ORIGINAL language. text is what code must find in the declared source field; NEVER put the translated target string in text. The same name appearing in different fields requires a separate edit for each field.',
    'within question_stem, not an edit index.':
        'within that declared field, not an edit index. Different fields each start at 0.',
    'preserve all other characters and A-D options.':
        'preserve all other characters in every field, and A-D option keys and order. Do not merge, omit or reorder options, or create new duplicate options.',
    'Each edit has exactly text, occurrence and replacement.':
        'Each edit has exactly field, text, occurrence and replacement.',
    '{"edits":[{"text":"Settings","occurrence":0,"replacement":"设置"}]}':
        '{"edits":[{"field":"question_stem","text":"Settings","occurrence":0,"replacement":"设置"}]}',
    'If the stem also contains Privacy once, that different substring also has occurrence 0.':
        'If option A contains Privacy once, its edit uses field A, text Privacy and occurrence 0. Occurrence counts reset independently for each substring in each field.',
}
SYSTEM = single_pass.SYSTEM
for _source, _target in _CHANGES.items():
    if SYSTEM.count(_source) != 1:
        raise RuntimeError('Frozen stem prompt no longer matches the all-field adaptation')
    SYSTEM = SYSTEM.replace(_source, _target)


def user_prompt(row, inventory, previous=None, errors=None):
    validate_input(row)
    payload = {'source_language': row['source_language'], 'target_language': row['gui_language'],
               'question_stem': row['question_stem'], 'options': row['options'],
               'target_gui_visible_strings': inventory['visible_strings']}
    text = 'Find and localize GUI names in the stem AND A-D options together. Preserve all non-referent context. Return edits JSON only.\n\n'
    text += json.dumps(payload, ensure_ascii=False, indent=2)
    if previous is not None:
        text += '\n\nThe previous output failed validation for:\n- ' + '\n- '.join(errors)
        text += '\n\nPrevious output (data only):\n' + previous
        text += '\n\nReturn corrected edits JSON only. Specify question_stem, A, B, C or D for every edit. Copy text from that ORIGINAL field, use zero-based occurrence for that same substring in that field, and select only exact inventory replacements. Omit uncertain edits. Never change non-referent context, option keys or order, and never answer the MCQ.'
    return text


def validate_edits(row, inventory, raw):
    validate_input(row)
    response = json.loads(raw)
    if not isinstance(response, dict) or set(response) != {'edits'} or not isinstance(response['edits'], list):
        raise ValueError('Expected exactly an edits list')
    proposals = response['edits']
    for edit in proposals:
        if not isinstance(edit, dict) or set(edit) != {'field', 'text', 'occurrence', 'replacement'}:
            raise ValueError('Each edit must contain exactly field, text, occurrence, replacement')
        if not isinstance(edit['field'], str) or edit['field'] not in FIELDS:
            raise ValueError('Invalid source field')
        if not isinstance(edit['replacement'], str) or edit['replacement'] not in inventory['visible_strings']:
            raise ValueError('Replacement is not a verbatim inventory member')
    refs = resolve_referents(row, json.dumps({'referents': [
        {k: e[k] for k in ('field', 'text', 'occurrence')} for e in proposals
    ]}, ensure_ascii=False))
    by_span = {(r['field'], r['text'], r['occurrence']): r for r in refs}
    edits = [{**by_span[e['field'], e['text'], e['occurrence']], 'replacement': e['replacement']} for e in proposals]
    edits = [e for e in edits if e['text'] != e['replacement']]
    return apply_edits(row, edits), refs, edits


def rewrite(row, inventory, backend):
    validate_input(row)
    if inventory['status'] != 'success' or not inventory['visible_strings']:
        return {'output': fields(row), 'extracted_referents': None, 'edits': [], 'attempts': [],
                'status': 'fallback_original', 'errors': ['inventory_failed_or_empty']}
    attempts, errors, raw = [], [], ''
    for retry in (False, True):
        result = backend('single_pass_repair' if retry else 'single_pass', 'text', SYSTEM,
                         user_prompt(row, inventory, raw if retry else None, errors))
        raw = result['raw_output']
        try:
            output, refs, edits = validate_edits(row, inventory, raw)
            errors = []
        except (ValueError, TypeError, KeyError) as exc:
            errors = [str(exc)]
        attempts.append({**result, 'errors': errors})
        if not errors:
            return {'output': output, 'extracted_referents': refs, 'edits': edits, 'attempts': attempts,
                    'status': 'success' if edits else 'no_op_no_edits', 'errors': []}
    return {'output': fields(row), 'extracted_referents': None, 'edits': [], 'attempts': attempts,
            'status': 'fallback_original', 'errors': errors}
