"""Conservative downstream reuse: entire ordered batch, never a lone matching row."""
from collections import defaultdict
import math

from mpr_crosslocale.methods.selective_alignment.schemas import digest


def batch_key(profile, seed, rows, images, environment):
    return digest({'downstream': profile, 'seed': seed, 'environment': environment,
                   'ordered_inputs': [(r['pair_id'], images[r['pair_id']], r['rendered_prompt']) for r in rows]})


def build_index(sources, profile, seed, images, environment):
    """Sources contain predictions plus frozen profile/seed/environment and provenance."""
    index, conflicts = {}, set()
    for source in sources:
        if source['downstream'] != profile or source['seed'] != seed or source['environment'] != environment:
            continue
        groups = defaultdict(list)
        for row in source['predictions']:
            groups[row['batch_id']].append(row)
        for batch in groups.values():
            first = batch[0]
            if len(batch) != first['batch_size']:
                raise ValueError('Incomplete historical batch')
            runtime = first['batch_runtime_ms']
            if not isinstance(runtime, (int, float)) or not math.isfinite(runtime) or runtime < 0:
                raise ValueError('Invalid historical batch runtime')
            if any(r['execution_mode'] != 'gpu' or r['status'] != 'success' or
                   r['batch_size'] != len(batch) or r['batch_runtime_ms'] != runtime for r in batch):
                raise ValueError('Invalid historical prediction metadata')
            key = batch_key(profile, seed, batch, images, environment)
            if key in conflicts:
                continue
            if key in index and [r['generated_text'] for r in index[key]['rows']] != [r['generated_text'] for r in batch]:
                del index[key]
                conflicts.add(key)
            else:
                index.setdefault(key, {'rows': batch, 'source': source['path'], 'batch_id': first['batch_id']})
    return index, conflicts
