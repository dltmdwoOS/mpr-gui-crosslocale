"""CPU-only editor input-length check, including full output-budget repair payloads."""
import argparse
from pathlib import Path
import sys
from run_editor_matrix import ROOT, DEFAULT, actor_config, load
from run_stem_only_gui import read, write
from followup_rel_4lang.method_dev import editor_matrix as matrix, stem_refinement_2x2 as refinement
from mpr_crosslocale.methods.selective_alignment.schemas import digest


def preflight(output):
    from transformers import AutoTokenizer
    c = load(output / 'contract.json')
    rows = read(output / 'inputs.jsonl')
    inv = {r['image_sha256']: r for r in read(Path(c['inventory_path']))}
    ext = {r['source_key']: r for r in read(Path(c['fixed_extraction']))}
    result = {'mode': 'CPU-tokenizer-only', 'max_input_tokens': 4096, 'models': {}, 'contract_sha256': digest(c)}
    for actor in ('L', 'V8', 'V4'):
        cfg = actor_config(c, actor)
        spec = cfg['models']['text' if actor == 'L' else 'editor_vlm']
        tokenizer = AutoTokenizer.from_pretrained(spec['path'], local_files_only=True)
        maxima = {}
        def count(stage, system, user):
            text = tokenizer.apply_chat_template([{'role':'system','content':system}, {'role':'user','content':user}],
                         tokenize=False, add_generation_prompt=True, **({'enable_thinking':False} if actor == 'L' else {}))
            n = len(tokenizer.encode(text, add_special_tokens=False))
            maxima[stage] = max(maxima.get(stage, 0), n)
        for row in rows:
            refs = ext[digest(matrix.prompts.extraction_payload(row, stem_only=True))]['referents']
            for form, scope in (('D','S'), ('D','H'), ('J','S'), ('J','H')):
                name = form + '-' + scope
                inventory = inv[row['image_sha256']]
                if form == 'D' and scope == 'S':
                    if refs:
                        count(name, matrix.prompts.SELECTIVE_GUI_SYSTEM, matrix.prompts.selective_user(row, refs, inventory))
                        count(name+'-repair', matrix.prompts.SELECTIVE_GUI_SYSTEM,
                              matrix.prompts.selective_user(row, refs, inventory, ' x'*512, ['Invalid output']))
                else:
                    count(name, matrix.system(form, scope), matrix.payload(row, inventory, refs, form, scope))
                    count(name+'-repair', matrix.system(form, scope), matrix.payload(row, inventory, refs, form, scope,
                          previous=' x' * matrix.LIMITS['matrix_' + scope], errors={'validation':'Representative error text for source recovery or inventory membership'}))
            count('E1', refinement.EXTRACT_SYSTEM, matrix.prompts.extraction_user(row, stem_only=True))
            count('E1-repair', refinement.EXTRACT_SYSTEM,
                  matrix.prompts.extraction_user(row, ' x'*768, ['Invalid source substring or occurrence'], stem_only=True))
        result['models'][actor] = {'revision': spec['revision'], 'maxima': maxima,
                                   'synthetic_repair_history_tokens': 'up to output cap using one-token x; actual errors and segmentation vary'}
        print('TOKEN PREFLIGHT', actor, maxima, flush=True)
        if max(maxima.values()) > 4096:
            raise ValueError('Repair input may exceed input cap; revise explicitly before running')
    write(output / 'token_preflight.json', result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, default=DEFAULT)
    preflight(p.parse_args().output_dir.resolve())
